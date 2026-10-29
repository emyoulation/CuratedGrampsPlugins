#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
#
# Based on the HasValidDate / HasInValidDate sample rules
# Copyright (C) 2025  Kari Kujansuu
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
One custom filter rule for dates:
  Valid section   - any combination of date modifiers (Type and Quality)
  Invalid section - Text only dates, with an optional text search
The two sections are mutually exclusive (radio buttons).

The whole rule value is stored as ONE locale-independent string, e.g.
  valid|before,about|estimated
  invalid|abt
so filters saved in one language still work in another.
"""

import logging
import os
import re
import traceback

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import displayer
from gramps.gen.filters.rules import Rule
from gramps.gen.lib import Date

try:
    _ = glocale.get_addon_translator(__file__).sgettext
except ValueError:
    _ = glocale.translation.sgettext

LOG = logging.getLogger(".DateModifiersRule")


# -------------------------------------------------------------------------
#
# Diagnostics: Python stack for Gtk-CRITICAL messages
#
# Start Gramps with GRAMPS_GTK_DEBUG=1 to turn this on.  Each Gtk-CRITICAL
# (for example "gtk_tree_model_filter_get_path: assertion ... stamp ...
# failed") is then printed with the Python call stack that was running
# when GTK raised it, so the plugin or Gramps module that used a stale
# tree iter can be found.  The handler is installed when Gramps loads this
# rule module, and it stays for the rest of the session.
#
# -------------------------------------------------------------------------
def cb_gtk_critical(domain, level, message, _user_data=None):
    """Print a Gtk-CRITICAL message with the current Python stack."""
    stack = "".join(traceback.format_stack()[:-1])
    LOG.warning(
        "%s-CRITICAL: %s\nPython stack (most recent call last):\n%s",
        domain,
        message,
        stack,
    )


if os.environ.get("GRAMPS_GTK_DEBUG"):
    try:
        from gi.repository import GLib

        GLib.log_set_handler(
            "Gtk", GLib.LogLevelFlags.LEVEL_CRITICAL, cb_gtk_critical, None
        )
        LOG.warning("GRAMPS_GTK_DEBUG: Gtk-CRITICAL messages show a Python stack")
    except (ImportError, TypeError) as err:
        LOG.warning("GRAMPS_GTK_DEBUG: could not install the handler: %s", err)

# Same order as the Type menu of the Edit Date Calculator addon, with its
# Span and Range labels, in rows of similar modifiers:
#   single dates, open-ended dates, two-date dates.
# "Text only" is left out on purpose: those are the Invalid section.
DATE_TYPE_ROWS = [
    [
        ("regular", Date.MOD_NONE, _("Regular")),
        ("about", Date.MOD_ABOUT, _("About")),
    ],
    [
        ("from", Date.MOD_FROM, _("From")),
        ("to", Date.MOD_TO, _("To")),
        ("after", Date.MOD_AFTER, _("After")),
        ("before", Date.MOD_BEFORE, _("Before")),
    ],
    [
        ("span", Date.MOD_SPAN, _("Span (From-To)")),
        ("range", Date.MOD_RANGE, _("Range (Between)")),
    ],
]
DATE_TYPES = [choice for row in DATE_TYPE_ROWS for choice in row]
# Long labels that take two grid columns each, so they do not widen the
# columns of the short labels above them.
WIDE_CHOICES = {"span", "range"}
DATE_QUALITIES = [
    ("regular", Date.QUAL_NONE, _("Regular")),
    ("estimated", Date.QUAL_ESTIMATED, _("Estimated")),
    ("calculated", Date.QUAL_CALCULATED, _("Calculated")),
]
TYPE_BY_KEY = {key: value for key, value, _label in DATE_TYPES}
QUAL_BY_KEY = {key: value for key, value, _label in DATE_QUALITIES}

MODE_VALID = "valid"
MODE_INVALID = "invalid"


def parse_value(value):
    """
    Split the stored rule string into its parts.
    Returns (mode, set_of_type_keys, set_of_quality_keys, search_text).
    An empty or unknown string means "any valid date".
    """
    mode, _sep, rest = (value or "").partition("|")
    if mode == MODE_INVALID:
        return MODE_INVALID, set(), set(), rest
    types_str, _sep, quals_str = rest.partition("|")
    types = {key for key in types_str.split(",") if key in TYPE_BY_KEY}
    quals = {key for key in quals_str.split(",") if key in QUAL_BY_KEY}
    return MODE_VALID, types, quals, ""


def build_value(mode, types=(), quals=(), text=""):
    """Join the parts back into the stored rule string."""
    if mode == MODE_INVALID:
        return "%s|%s" % (MODE_INVALID, text)
    # keep the stored order stable (the order of the lists above)
    types_str = ",".join(k for k, _v, _l in DATE_TYPES if k in types)
    quals_str = ",".join(k for k, _v, _l in DATE_QUALITIES if k in quals)
    return "%s|%s|%s" % (MODE_VALID, types_str, quals_str)


# -------------------------------------------------------------------------
#
# DateModifierOptions - the editor widget (GUI only)
#
# The filter editor builds a widget from a (label, class) tuple in
# Rule.labels by calling class(db), then uses get_text()/set_text().
# On the command line there is no Gtk, so the label falls back to a
# plain string and the stored value is used as is.
#
# -------------------------------------------------------------------------
try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    class DateModifierOptions(Gtk.Box):
        """Valid (Types + Qualities) or Invalid (text search), not both."""

        def __init__(self, db=None):
            Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=4)

            # ---- Valid section ----
            self.valid_radio = Gtk.RadioButton.new_with_label(
                None, _("Valid dates")
            )
            self.valid_radio.set_tooltip_text(
                _(
                    "Match dates that Gramps can calculate with. "
                    "For Type and for Quality, a date may have any of the "
                    "checked choices. With nothing checked, all match."
                )
            )
            self.pack_start(self.valid_radio, False, False, 0)

            self.valid_grid = Gtk.Grid(column_spacing=12, row_spacing=2)
            self.valid_grid.set_margin_start(24)
            # Type: three rows of similar modifiers.  Quality: one row.
            self.type_checks = self._add_check_rows(
                self.valid_grid, 0, _("Type:"), DATE_TYPE_ROWS
            )
            self.qual_checks = self._add_check_rows(
                self.valid_grid, len(DATE_TYPE_ROWS), _("Quality:"), [DATE_QUALITIES]
            )
            self.pack_start(self.valid_grid, False, False, 0)

            # ---- Invalid section ----
            self.invalid_radio = Gtk.RadioButton.new_with_label_from_widget(
                self.valid_radio, _("Invalid dates (Text only)")
            )
            self.invalid_radio.set_tooltip_text(
                _(
                    "Match dates that Gramps could not understand and kept "
                    "as text. Leave the text box empty to match all of them."
                )
            )
            self.pack_start(self.invalid_radio, False, False, 0)

            self.text_entry = Gtk.Entry()
            self.text_entry.set_margin_start(24)
            self.text_entry.set_placeholder_text(_("text contains (optional)"))
            self.pack_start(self.text_entry, False, False, 0)

            self.valid_radio.connect("toggled", self.cb_mode_toggled)
            self.set_text("")
            self.show_all()

        @staticmethod
        def _add_check_rows(grid, top, title, rows):
            """Put a title and its rows of check buttons on the grid."""
            label = Gtk.Label(label=title, halign=Gtk.Align.START)
            grid.attach(label, 0, top, 1, 1)
            checks = {}
            for row_index, row in enumerate(rows):
                column = 1
                for key, _value, text in row:
                    width = 2 if key in WIDE_CHOICES else 1
                    check = Gtk.CheckButton(label=text)
                    grid.attach(check, column, top + row_index, width, 1)
                    checks[key] = check
                    column += width
            return checks

        def cb_mode_toggled(self, _button=None):
            """Only the chosen section can be edited."""
            valid = self.valid_radio.get_active()
            self.valid_grid.set_sensitive(valid)
            self.text_entry.set_sensitive(not valid)

        def get_text(self):
            """Return the value to save in the filter."""
            if self.invalid_radio.get_active():
                return build_value(MODE_INVALID, text=self.text_entry.get_text())
            types = {k for k, c in self.type_checks.items() if c.get_active()}
            quals = {k for k, c in self.qual_checks.items() if c.get_active()}
            return build_value(MODE_VALID, types, quals)

        def set_text(self, val):
            """Show a saved value."""
            mode, types, quals, text = parse_value(val)
            for key, check in self.type_checks.items():
                check.set_active(key in types)
            for key, check in self.qual_checks.items():
                check.set_active(key in quals)
            self.text_entry.set_text(text)
            if mode == MODE_INVALID:
                self.invalid_radio.set_active(True)
            else:
                self.valid_radio.set_active(True)
            self.cb_mode_toggled()

    RULE_LABELS = [(_("Date:"), DateModifierOptions)]

except (ImportError, ValueError):
    RULE_LABELS = [_("Date:")]


# -------------------------------------------------------------------------
#
# HasDateModifiers - the shared rule logic
#
# -------------------------------------------------------------------------
class HasDateModifiers(Rule):
    """Match objects by date modifiers, or by invalid date text."""

    labels = RULE_LABELS
    name = _("Date Modifiers")
    description = _(
        "Matches objects with a valid date of the checked types and "
        "qualities, or with an invalid (Text only) date containing a text"
    )
    category = _("General filters")
    allow_regex = True  # used by the Invalid section text only

    def __init__(self, arg, use_regex=False, use_case=False):
        super().__init__(arg, use_regex, use_case)
        self.mode = MODE_VALID
        self.types = set()
        self.quals = set()
        self.search = ""
        self.search_re = None

    def prepare(self, db, user):
        """Decode the stored value once per filter run."""
        value = self.list[0] if self.list else ""
        self.mode, type_keys, qual_keys, self.search = parse_value(value)
        self.types = {TYPE_BY_KEY[k] for k in type_keys}
        self.quals = {QUAL_BY_KEY[k] for k in qual_keys}

        # The base class compiles self.list as regexes, but our list holds
        # the encoded value, so the search text is compiled here instead.
        self.search_re = None
        if self.mode == MODE_INVALID and self.search and self.use_regex:
            flags = 0 if self.use_case else re.IGNORECASE
            try:
                self.search_re = re.compile(self.search, flags)
            except re.error as err:
                LOG.warning("Bad regular expression %r: %s", self.search, err)
                self.search_re = re.compile(re.escape(self.search), flags)

    def apply_to_one(self, db, obj):
        """Return True when the object's date matches."""
        date = obj.get_date_object()

        if self.mode == MODE_VALID:
            if not date.is_valid():
                return False
            if self.types and date.get_modifier() not in self.types:
                return False
            if self.quals and date.get_quality() not in self.quals:
                return False
            return True

        # Invalid section: not valid, but not blank either
        if date.is_valid() or date.is_empty():
            return False
        if not self.search:
            return True
        text = date.get_text() or displayer.display(date)
        if self.search_re is not None:
            return self.search_re.search(text) is not None
        if self.use_case:
            return self.search in text
        return self.search.casefold() in text.casefold()

    apply = apply_to_one  # Gramps 5.2 calls apply()


# -------------------------------------------------------------------------
#
# One registered rule per object type that has a single date
#
# -------------------------------------------------------------------------
class HasDateModifiersEvent(HasDateModifiers):
    """Events by date modifiers or invalid text."""

    description = _(
        "Matches events with a valid date of the checked types and "
        "qualities, or with an invalid (Text only) date containing a text"
    )


class HasDateModifiersCitation(HasDateModifiers):
    """Citations by date modifiers or invalid text."""

    description = _(
        "Matches citations with a valid date of the checked types and "
        "qualities, or with an invalid (Text only) date containing a text"
    )


class HasDateModifiersMedia(HasDateModifiers):
    """Media by date modifiers or invalid text."""

    description = _(
        "Matches media with a valid date of the checked types and "
        "qualities, or with an invalid (Text only) date containing a text"
    )
