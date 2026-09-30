#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Phonetic Matching Gramplet contributors
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""
"Match in:" name-field option shared by the Soundex, NYSIIS, Match
Rating Approach (MRA) and Metaphone person filter rules.

The option is two groups of name fields and an Include choice:

    Match in Given name parts:
      [ ] Title   [ ] Given    [x] Call    [ ] Nick
    Match in Surname parts:
      [ ] Prefix  [x] Surname  [ ] Suffix  [ ] Clan
    Include:
      [x] Preferred            [ ] Alternatives

It is stored in the filter as locale-independent keys, e.g.
``"call,surname,primary"``. A missing or empty value means that
default. One-argument filters saved by earlier versions, and the Fuzzy
Matching gramplet's "Define filter" action (which passes only the
surname), get the default.

* Every surname piece of a compound surname, and every word of a
  multi-word given name, is encoded separately.
* An empty Call field means the first given name, as in Gramps' own
  "common name" display.

The rules import this module by bare name, so it must be in the same
folder as them. Each rule guards that import: if this file is missing,
the rule still loads - important, because Gramps does not survive a
rule addon that fails to import - and falls back to matching the
preferred surname only, without the option.
"""

from __future__ import annotations

# ------------------------
# Python modules
# ------------------------
from collections.abc import Callable, Iterable
from typing import Any

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.lib import Name, Person

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

#: (key, check box label) for the given-name row, in display order.
GIVEN_PARTS = (
    ("title", _("Title")),
    ("given", _("Given")),
    ("call", _("Call")),
    ("nick", _("Nick")),
)

#: (key, check box label) for the surname row, in display order.
SURNAME_PARTS = (
    ("prefix", _("Prefix")),
    ("surname", _("Surname")),
    ("suffix", _("Suffix")),
    ("clan", _("Clan")),
)

#: (key, check box label) for which names to search, in display order.
INCLUDE_PARTS = (
    ("primary", _("Preferred")),
    ("alternate", _("Alternatives")),
)

_FIELD_KEYS = frozenset(key for key, _label in GIVEN_PARTS + SURNAME_PARTS)
_NAME_KEYS = frozenset(key for key, _label in INCLUDE_PARTS)

#: Every recognised key.
ALL_KEYS = _FIELD_KEYS | _NAME_KEYS

#: Behaviour when nothing is stored: the preferred name's surname and
#: call name.
DEFAULT_KEYS = frozenset({"surname", "call", "primary"})

#: Keys from the first draft of this option, which had a separate
#: "Alternatives" box on each row, always alongside the preferred name.
_LEGACY_KEYS = {
    "given_alt": ("primary", "alternate"),
    "surname_alt": ("primary", "alternate"),
}

#: Label of the rule option (second rule argument).
OPTION_LABEL = _("Match in:")

#: Stored-value shorthand for "every name field, in every name":
#: :func:`parse_parts` expands it to :data:`ALL_KEYS` at read time, so a
#: caller building a rule in code (e.g. the Fuzzy Matching gramplet's
#: "Define filter" action) can ask for everything without listing keys
#: that might change when name parts are added or removed. The Filter
#: Editor's widget writes explicit keys back when the filter is saved.
ALL_TOKEN = "all"


def parse_parts(text: str | None) -> frozenset[str]:
    """
    Turn a stored option value into a set of part keys.

    Missing pieces take their defaults: no name field means Surname and
    Call, and no Include choice means the preferred name only. The
    token ``"all"`` (:data:`ALL_TOKEN`) stands for every key.

    :param text: The stored value, e.g. ``"given,surname,primary"``, or
        ``"all"``.
    :returns: The recognised keys.
    """
    keys: set[str] = set()
    for token in (text or "").replace(" ", ",").split(","):
        token = token.strip()
        if token == ALL_TOKEN:
            keys |= ALL_KEYS
            continue
        for key in _LEGACY_KEYS.get(token, (token,)):
            if key in ALL_KEYS:
                keys.add(key)
    if not keys & _FIELD_KEYS:
        keys |= DEFAULT_KEYS & _FIELD_KEYS
    if not keys & _NAME_KEYS:
        keys |= DEFAULT_KEYS & _NAME_KEYS
    return frozenset(keys)


def format_parts(keys: Iterable[str]) -> str:
    """
    Turn a set of part keys into the stored option value, in display
    order.

    :param keys: Iterable of part keys.
    :returns: Comma-separated keys, e.g. ``"given,surname,primary"``.
    """
    wanted = set(keys)
    return ",".join(
        key
        for key, _label in GIVEN_PARTS + SURNAME_PARTS + INCLUDE_PARTS
        if key in wanted
    )


def _name_words(name: Name, keys: frozenset[str]) -> list[str]:
    """
    Collect the words of one name's fields selected by ``keys``.

    :param name: A :class:`gramps.gen.lib.Name`.
    :param keys: Part keys from :func:`parse_parts`.
    :returns: The selected field values, possibly empty strings.
    """
    words: list[str] = []
    if "title" in keys:
        words.append(name.get_title())
    if "given" in keys:
        words.extend(name.get_first_name().split())
    if "call" in keys:
        # An empty Call field means the first given name, as in Gramps'
        # own "common name" (%x) display: nick, call, else first given.
        given_words = name.get_first_name().split()
        first_given = given_words[0] if given_words else ""
        words.append(name.get_call_name() or first_given)
    if "nick" in keys:
        words.append(name.get_nick_name())
    for surname in name.get_surname_list():
        if "prefix" in keys:
            words.append(surname.get_prefix())
        if "surname" in keys:
            words.append(surname.get_surname())
    if "suffix" in keys:
        words.append(name.get_suffix())
    if "clan" in keys:
        words.append(name.get_family_nick_name())
    return words


def person_words(person: Person, keys: frozenset[str]) -> list[str]:
    """
    Collect the words of ``person``'s names selected by ``keys``: the
    chosen name fields of the preferred name (``primary``) and/or of
    every alternate name (``alternate``).

    :param person: A :class:`gramps.gen.lib.Person`.
    :param keys: Part keys from :func:`parse_parts`.
    :returns: Non-empty words, possibly with repeats.
    """
    names: list[Name] = []
    if "primary" in keys:
        names.append(person.get_primary_name())
    if "alternate" in keys:
        names.extend(person.get_alternate_names())
    words: list[str] = []
    for name in names:
        words.extend(_name_words(name, keys))
    return [word for word in words if word and word.strip()]


#: Signature of a rule module's ``encode`` function.
Encoder = Callable[[str], set[str]]


def person_matches(
    person: Person,
    keys: frozenset[str],
    target_codes: set[str],
    encoder: Encoder,
) -> bool:
    """
    Return True if any selected word of ``person``'s names encodes to one
    of ``target_codes``.

    :param person: A :class:`gramps.gen.lib.Person`.
    :param keys: Part keys from :func:`parse_parts`.
    :param target_codes: Codes of the name the rule was given.
    :param encoder: The rule module's own ``encode(name) -> set[str]``.
    :returns: True on a match.
    """
    if not target_codes:
        return False
    words = set(person_words(person, keys))
    return any(encoder(word) & target_codes for word in words)


def pad_args(arg: list[str] | None) -> list[str]:
    """
    Return the rule argument list with the "Match in:" value filled in
    when an older, one-argument filter (or a caller passing only the
    name) leaves it out.

    :param arg: The rule's argument list as given.
    :returns: A two-element list: the name and the "Match in:" value.
    """
    padded = list(arg or [])
    if len(padded) < 2:
        padded += [""] * (2 - len(padded))
        padded[1] = format_parts(DEFAULT_KEYS)
    return padded


def name_parts_widget(_db: Any) -> Any:
    """
    Filter Editor widget factory for the "Match in:" option.

    Used as the second element of a ``(label, factory)`` tuple in a
    rule's ``labels`` list, which Gramps 5.2 through 6.x's Filter
    Editor calls with the database to build a custom input widget.
    GTK is imported here, not at module level, so the rules stay usable
    without a GUI.

    :param _db: The database (unused).
    :returns: A :class:`Gtk.Grid` with ``get_text()``/``set_text()``.
    """
    # pylint: disable-next=import-outside-toplevel
    from gi.repository import GLib, Gtk

    # ------------------------------------------------------------
    #
    # NamePartsChooser
    #
    # ------------------------------------------------------------
    class NamePartsChooser(Gtk.Grid):  # type: ignore[misc]
        """
        Six rows: a heading and a row of check boxes for given-name
        parts, surname parts, and which names to include. Check boxes
        share columns, so each row lines up under the one above.
        """

        def __init__(self) -> None:
            """
            Build the headings and check boxes, ticked for the default.
            """
            Gtk.Grid.__init__(self)
            self.set_column_spacing(12)
            self.set_row_spacing(2)
            self._buttons: dict[str, Any] = {}
            sections = (
                (_("Match in Given name parts:"), GIVEN_PARTS, (0, 1, 2, 3)),
                (_("Match in Surname parts:"), SURNAME_PARTS, (0, 1, 2, 3)),
                (_("Include:"), INCLUDE_PARTS, (0, 2)),
            )
            row = 0
            for heading, parts, columns in sections:
                label = Gtk.Label(label=heading, halign=Gtk.Align.START)
                if row:
                    label.set_margin_top(4)
                self.attach(label, 0, row, 4, 1)
                row += 1
                width = 2 if len(parts) < 4 else 1
                for (key, text), col in zip(parts, columns):
                    button = Gtk.CheckButton(label=text)
                    if not col:
                        button.set_margin_start(12)
                    self._buttons[key] = button
                    self.attach(button, col, row, width, 1)
                row += 1
            self.set_text("")
            self.show_all()
            self.connect("parent-set", self.cb_parent_set)
            self.connect("state-flags-changed", self.cb_state_changed)

        def cb_state_changed(self, _widget: Any, _previous: Any) -> None:
            """
            Hide this rule's page while the Filter Editor greys it out.

            The Filter Editor makes the values area insensitive whenever
            no rule is selected - after a click on a category heading,
            or when its rule list loses the edited rule's selection -
            but leaves the last rule's page on screen. Making the page
            transparent keeps these options from lingering under "No
            rule selected"; they reappear when the rule is selected
            again. Opacity rather than hide(), because a hidden page
            would stop receiving the state change that brings it back.

            :param _widget: This widget.
            :param _previous: The previous state flags.
            """
            page = self.get_parent()
            if isinstance(page, Gtk.Grid):
                page.set_opacity(1.0 if self.is_sensitive() else 0.0)

        def cb_parent_set(self, _widget: Any, _old_parent: Any) -> None:
            """
            Schedule taking over the label column once placed.

            The Filter Editor puts each option's label in column 0,
            vertically centred beside its widget in column 1. The
            headings here already say "Match in ...", so the side label
            is dropped and this widget spans both columns, with the
            headings above the check boxes from the left edge. The label
            text stays in the rule's ``labels``, which Gramps also uses
            to summarise the rule in the filter list.

            :param _widget: This widget.
            :param _old_parent: The previous parent, if any.
            """
            if isinstance(self.get_parent(), Gtk.Grid):
                GLib.idle_add(self.cb_take_label_column)

        def cb_take_label_column(self) -> bool:
            """
            Remove the side label and span both grid columns.

            Leaves the layout untouched if the Filter Editor did not
            place this widget in column 1 of a grid.

            :returns: False, so the idle callback runs once.
            """
            grid = self.get_parent()
            if not isinstance(grid, Gtk.Grid):
                return False
            try:
                top = grid.child_get_property(self, "top-attach")
                if grid.child_get_property(self, "left-attach") != 1:
                    return False
                side_label = grid.get_child_at(0, top)
                if isinstance(side_label, Gtk.Label):
                    grid.remove(side_label)
                grid.child_set_property(self, "left-attach", 0)
                grid.child_set_property(self, "width", 2)
            except Exception:  # pylint: disable=broad-except
                pass  # leave the Filter Editor's own layout as it was
            return False

        def get_text(self) -> str:
            """
            Return the stored value for the ticked boxes.

            :returns: Comma-separated part keys, with defaults filled in.
            """
            keys = [k for k, b in self._buttons.items() if b.get_active()]
            return format_parts(parse_parts(",".join(keys)))

        def set_text(self, val: str) -> None:
            """
            Tick the boxes for a stored value.

            :param val: A stored "Match in:" value.
            """
            keys = parse_parts(val)
            for key, button in self._buttons.items():
                button.set_active(key in keys)

    return NamePartsChooser()
