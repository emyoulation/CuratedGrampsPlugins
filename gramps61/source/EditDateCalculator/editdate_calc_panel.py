#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2010       Jakim Friant
# Copyright (c) 2015       Douglas S. Blank <doug.blank@gmail.com>
# Copyright (c) 2020       Jan Sparreboom <jan@sparreboom.net>
# Copyright (c) 2024-2025  Steve Youngs <steve@youngs.cc>
# Copyright (C) 2026       Brian McCullough
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
Date calculator panel, embedded in the Edit Date dialog by the
EditDateCalculator addon (see editdatecalculator.py).

Derived from the Date Calculator gramplet addon.  The logic is the same, but
it is packaged as a compact Gtk.Box so it can be embedded anywhere, and it can
exchange dates with its host through callbacks.
"""

import ast
import logging
import re

from gi.repository import Gdk, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import displayer, parser
from gramps.gen.lib import Date, Span
from gramps.gen.lib.date import DateError
from gramps.gui.utils import text_to_clipboard

LOG = logging.getLogger(".DateCalculatorPanel")
try:
    _ = glocale.get_addon_translator(__file__).sgettext
except ValueError:
    _ = glocale.translation.sgettext

# one "<number><unit>" item of an offset such as "-2y, 3m, 10d"
_UNIT_ITEM = re.compile(
    r"\s*([+-]?\d+)\s*(years?|yrs?|y|months?|mos?|m|days?|d)\b\s*,?", re.IGNORECASE
)


# "Age" / "Aged" ahead of an offset ("Aged 45y 3m") subtracts it, as a minus would
_AGE_PREFIX = re.compile(r"\s*aged?\b[\s:.]*", re.IGNORECASE)


def _parse_units(text):
    """
    Parse an offset written with units, like "2y, 3m, 10d" or "6 months".

    Return (years, months, days), or None if the text is not of that form.
    Each unit may appear once, in any order; missing units count as zero.
    """
    found = {}
    pos = 0
    while pos < len(text):
        match = _UNIT_ITEM.match(text, pos)
        if match is None:
            return None
        unit = match.group(2)[0].lower()
        if unit in found:
            return None
        found[unit] = int(match.group(1))
        pos = match.end()
    if not found:
        return None
    return (found.get("y", 0), found.get("m", 0), found.get("d", 0))


class DateCalculatorPanel(Gtk.Box):
    """
    Compact panel that performs date math.

    :param get_date: optional callable returning the host's current Date;
        it prefills the Reference date whenever the panel opens.
    :param use_date: optional callable taking a Date; enables the
        "Result to Start Date" button.
    :param use_second_date: optional callable taking a Date; enables the
        "Result to End Date" button.
    """

    # width in pixels; wide enough for the hints and typical results
    PANEL_WIDTH = 340
    # padding around the panel: less on the right, where the dialog's own
    # margin follows
    PAD = 6
    PAD_END = 3

    def __init__(self, get_date=None, use_date=None, use_second_date=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._get_date = get_date
        self._use_date = use_date
        self._use_second_date = use_second_date
        self._prefilled = ""
        # the field titles double as the names used in error messages
        self._reference_label = _("Reference date")
        self._offset_label = _("Date or offset")
        self._result_date = None
        self.set_margin_top(self.PAD)
        self.set_margin_bottom(self.PAD)
        self.set_margin_start(self.PAD)
        self.set_margin_end(self.PAD_END)
        self.set_size_request(self.PANEL_WIDTH - self.PAD - self.PAD_END, -1)

        self.reference = self._add_entry(
            self._reference_label,
            _("a valid Gramps date or date range"),
        )
        self.offset = self._add_entry(
            self._offset_label,
            _(
                "1. a Date\n"
                "2. a positive or negative number, representing years\n"
                "3. years, months and days: 2, 3, 10\n"
                "    or with units, in any order and each optional: 2y, 3m, 10d\n"
                "A leading minus, or Age / Aged (Aged 45y 3m), subtracts the "
                "whole offset."
            ),
        )
        example_date = displayer.display(Date(1900, 6, 15))
        self.offset.set_placeholder_text(
            _('"%(date)s" or "%(offset)s"')
            % {"date": example_date, "offset": "-2y, 3m, 10d"}
        )
        self.result = self._add_entry(_("Result"))
        self.result.set_editable(False)
        self.result.set_placeholder_text(_("Enter an expression above, then Calculate"))

        grid = Gtk.Grid(column_spacing=4, row_spacing=4, column_homogeneous=True)
        self.use_date_button = Gtk.Button(label=_("Result to Start Date"))
        self.use_date_button.set_tooltip_text(
            _("Load the result into the Start date fields of the dialog")
        )
        self.use_date_button.connect("clicked", self.cb_use_result)
        self.use_second_button = Gtk.Button(label=_("Result to End Date"))
        self.use_second_button.set_tooltip_text(
            _(
                "Copy the result to the End date of the dialog; if the End "
                "date is dimmed, From becomes a Span, After or any other Type "
                "a Range"
            )
        )
        self.use_second_button.connect("clicked", self.cb_use_result_second)
        calc_button = Gtk.Button(label=_("Calculate"))
        calc_button.connect("clicked", self.cb_calculate)
        copy_button = Gtk.Button(label=_("Copy"))
        copy_button.connect("clicked", self.cb_copy)
        clear_button = Gtk.Button(label=_("Clear"))
        clear_button.connect("clicked", self.cb_clear)
        # a blank line's worth of space before the second row
        calc_button.set_margin_top(12)
        copy_button.set_margin_top(12)
        grid.attach(self.use_date_button, 0, 0, 1, 1)
        grid.attach(self.use_second_button, 1, 0, 1, 1)
        grid.attach(calc_button, 0, 1, 1, 1)
        grid.attach(copy_button, 1, 1, 1, 1)
        grid.attach(clear_button, 0, 2, 2, 1)
        self.pack_start(grid, False, False, 4)

        self.reference.connect("changed", self.cb_reference_changed)
        # Text dropped on the panel, anywhere but inside an entry (those take
        # drops themselves, as usual), replaces the Reference date.
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_text_targets()
        self.connect("drag-data-received", self.cb_drag_data_received)
        self.cb_clear(None)

    def _add_entry(self, name, tooltip=""):
        """
        Add a labelled Gtk.Entry to the panel and return the entry.
        """
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        label = Gtk.Label(halign=Gtk.Align.START)
        label.set_markup("<b>%s</b>" % name)
        row.pack_start(label, True, True, 0)
        self.pack_start(row, False, False, 0)

        entry = Gtk.Entry()
        entry.set_tooltip_text(tooltip)
        entry.set_width_chars(10)
        entry.connect("activate", self.cb_calculate)
        self.pack_start(entry, False, False, 0)
        return entry

    @staticmethod
    def _parse_operand(text, message):
        """
        Turn the text of one entry into (negated, value).

        The value is an int (years), a tuple of ints (years, months, days) or
        a valid Date.  Raises ValueError(message) if none of these fit.

        An offset is negated by a leading minus, or by "Age" / "Aged" ahead
        of it, which must then be followed by an offset, never a date.
        """
        text = text.strip()
        aged = _AGE_PREFIX.match(text)
        if aged:
            text = text[aged.end() :].strip()
        negated = bool(aged) or text.startswith("-")
        if text.startswith("-"):
            text = text[1:].strip()

        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            value = None
        if isinstance(value, int) and not isinstance(value, bool):
            return negated, value
        if (
            isinstance(value, tuple)
            and 0 < len(value) <= 3
            and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
        ):
            return negated, value

        units = _parse_units(text)
        if units is not None:
            return negated, units

        if aged:
            raise ValueError(message)
        date = parser.parse(text)
        if date.is_empty() or not date.is_valid():
            raise ValueError(message)
        return negated, date

    def _compute(self, neg1, val1, neg2, val2):
        """
        Combine the two operands; at least one of them must be a Date.
        """
        if isinstance(val1, Date) and isinstance(val2, Date):
            return val2 - val1 if neg1 else val1 - val2
        if isinstance(val1, Date):
            return val1 - val2 if neg2 else val1 + val2
        if isinstance(val2, Date):
            return val2 - val1 if neg1 else val2 + val1
        raise ValueError(
            _("Error: %(field)s must be a date") % {"field": self._reference_label}
        )

    def cb_calculate(self, _widget):
        """
        Run the calculation and show the result.
        """
        self._reset_result()
        if not self.reference.get_text().strip():
            return
        try:
            neg1, val1 = self._parse_operand(
                self.reference.get_text(),
                _("Error: invalid %(field)s") % {"field": self._reference_label},
            )
            neg2, val2 = self._parse_operand(
                self.offset.get_text(),
                _("Error: invalid %(field)s") % {"field": self._offset_label},
            )
            result = self._compute(neg1, val1, neg2, val2)
        except ValueError as err:
            self.result.set_text(str(err))
            return
        except (TypeError, OverflowError, DateError):
            self.result.set_text(_("Error: could not calculate a result"))
            return

        if isinstance(result, Date):
            result.set_quality(Date.QUAL_CALCULATED)
            self._result_date = result
            self.use_date_button.set_sensitive(self._use_date is not None)
            self.use_second_button.set_sensitive(self._use_second_date is not None)
            text = displayer.display(result)
        elif isinstance(result, Span):
            text = result.format(3)
        else:
            text = str(result)
        self.result.set_text(text)

    def prefill_from_dialog(self):
        """
        Fill the reference entry with the host's current date or range.

        An entry the user has typed into is left alone; an empty entry, or
        one still holding the previous prefill, is refreshed.
        """
        date = self._get_date() if self._get_date else None
        if (
            date is None
            or date.is_empty()
            or date.get_modifier() == Date.MOD_TEXTONLY
        ):
            return
        text = displayer.display(date)
        current = self.reference.get_text()
        if not current or current == self._prefilled:
            self.reference.set_text(text)
            self._prefilled = text

    def cb_use_result(self, _widget):
        """
        Result to Date: hand the calculated Date to the host's Date fields.
        """
        if self._result_date is not None and self._use_date is not None:
            self._use_date(Date(self._result_date))

    def cb_use_result_second(self, _widget):
        """
        Result to Second Date: hand the calculated Date to the host's Second
        date fields.
        """
        if self._result_date is not None and self._use_second_date is not None:
            self._use_second_date(Date(self._result_date))

    def cb_drag_data_received(self, _widget, _context, _x, _y, data, _info, _time):
        """
        Text dropped on the panel replaces the Reference date.

        Drops inside an entry never get here: the entry takes them itself.
        """
        text = " ".join((data.get_text() or "").split())
        if text:
            self.reference.set_text(text)
            self._prefilled = ""

    def cb_copy(self, _widget):
        """
        Copy the result text to the clipboard.
        """
        text_to_clipboard(self.result.get_text())

    def _reset_result(self):
        """
        Empty the Result field, so that its hint shows again.
        """
        self._result_date = None
        self.use_date_button.set_sensitive(False)
        self.use_second_button.set_sensitive(False)
        self.result.set_text("")

    def cb_reference_changed(self, entry):
        """
        With a blank Reference date there is no result to show: bring back
        the hint in the Result field.
        """
        if not entry.get_text().strip():
            self._reset_result()

    def cb_clear(self, _widget):
        """
        Empty all three fields; the Result field shows its hint again.
        """
        self._prefilled = ""
        self.reference.set_text("")
        self.offset.set_text("")
        self._reset_result()
