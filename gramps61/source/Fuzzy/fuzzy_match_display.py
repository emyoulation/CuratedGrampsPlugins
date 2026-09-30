#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2026       Claude Sonnet 5
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
Shared display helpers for this addon's two person-list UIs -
``FuzzyMatchingGramplet.py``'s right Matches column and
``FuzzyMatchLookupWindow.py``'s own equivalent - factored out because
both previously carried byte-for-byte identical code.

No ``gi.repository`` import, same as :mod:`fuzzy_match_index`: nothing
here actually touches a live :class:`Gtk.Widget`, only a
``(display_text, handle)``-shaped row store (a :class:`Gtk.ListStore`
in both current callers, but nothing here assumes that specifically -
any object supporting ``for row in store: row[0] = ...`` and
iteration would do).

Note on imports: like this addon's other modules, imported by bare
module name (``import fuzzy_match_display``), not as a package - see
the equivalent, longer comment in ``FuzzyMatchingGramplet.py``.
"""

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import HandleError
from gramps.gen.utils.db import get_birth_or_fallback, get_death_or_fallback


def format_person(db, person) -> str:
    """
    Format a person for display as "Display Name (birth year-death
    year) [Gramps ID]".

    Birth/death years use
    :func:`gramps.gen.utils.db.get_birth_or_fallback`/
    :func:`~gramps.gen.utils.db.get_death_or_fallback`, so a
    baptism/christening or burial/cremation event is used when no
    exact birth/death event is recorded, matching how Gramps itself
    handles missing vital events elsewhere. The life-span
    parenthetical is omitted entirely if neither year is known.

    :param db: The active database (needed to resolve event
        references on ``person``).
    :param person: The :class:`gramps.gen.lib.Person` to format.
    :returns: The formatted display string.
    """
    birth = get_birth_or_fallback(db, person)
    death = get_death_or_fallback(db, person)
    birth_year = birth.get_date_object().get_year() if birth else 0
    death_year = death.get_date_object().get_year() if death else 0

    name = name_displayer.display(person)
    gramps_id = f"[{person.get_gramps_id()}]"
    if not birth_year and not death_year:
        return f"{name} {gramps_id}"

    life_span = f"{birth_year or ''}-{death_year or ''}"
    return f"{name} ({life_span}) {gramps_id}"


def person_sort_key(db, person):
    """
    Sort key for a right-hand Matches column row: given name
    (locale-aware), then birth date, then death date, then Gramps ID -
    deliberately *not* surname, so people with different surname text
    (most visibly: a compound/double surname vs. a plain one)
    interleave by name/age instead of being grouped apart by surname
    text, which read as men and women being segregated whenever a
    tree's compound surnames happened to fall mostly along one line.
    The Gramps ID only ever breaks a tie between two people who
    otherwise sort identically (same given name and, if recorded, the
    same birth/death dates), so the display order is fully
    deterministic instead of depending on incidental dict/list
    ordering.

    Likely to become a user-configurable choice (surname, given name,
    birth date, ...) rather than a fixed one - this is today's only
    option, not a framework for others yet.

    :param db: The active database (needed to resolve event
        references on ``person``).
    :param person: The :class:`gramps.gen.lib.Person` to key.
    :returns: A tuple sortable against another person's, in the
        priority order described above.
    """
    given_name = person.get_primary_name().get_first_name()
    birth = get_birth_or_fallback(db, person)
    death = get_death_or_fallback(db, person)
    birth_sort = birth.get_date_object().get_sort_value() if birth else 0
    death_sort = death.get_date_object().get_sort_value() if death else 0
    return (
        glocale.sort_key(given_name),
        birth_sort,
        death_sort,
        person.get_gramps_id(),
    )


def refresh_matching_person_rows(db, person_store, changed_event_handles) -> None:
    """
    Re-format any row in ``person_store`` whose person's birth or
    death event is among ``changed_event_handles``, in place.

    Exists because editing a birth or death event's date or place
    from the Person editor's Events tab commits only that
    :class:`~gramps.gen.lib.Event` object (the database's own
    ``event-update`` signal) - the person's own event reference list
    is unchanged, so nothing about the person object itself signals
    that this display text is now stale. Both
    ``FuzzyMatchingGramplet.cb_event_changed`` and
    ``FuzzyMatchLookupWindow._cb_event_changed`` connect to that
    signal and hand its handle list straight to this function. Only
    the rows already in ``person_store`` are touched - a cheap pass
    over however many people are currently displayed, not a database
    scan - and nothing about which people are displayed changes,
    since a birth/death date can't affect a surname match.

    :param db: The active database.
    :param person_store: A ``(display_text, handle)``-shaped row
        store - column 0 the display text to overwrite, column 1 the
        person handle to look up.
    :param changed_event_handles: Handles of the events that were
        updated, as passed by the database's ``event-update`` signal.
    """
    changed = set(changed_event_handles)
    for row in person_store:
        handle = row[1]
        try:
            person = db.get_person_from_handle(handle)
        except HandleError:
            continue
        birth = get_birth_or_fallback(db, person)
        death = get_death_or_fallback(db, person)
        event_handles = {
            event.get_handle() for event in (birth, death) if event is not None
        }
        if event_handles & changed:
            row[0] = format_person(db, person)
