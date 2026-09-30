#
# Gramps - a GTK+/GNOME based genealogy program
#
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
Unit tests for :mod:`fuzzy_match_display`.

Unlike ``fuzzy_match_index_test.py``, faking this module's dependencies
away entirely isn't practical: ``get_birth_or_fallback``/
``get_death_or_fallback`` and ``name_displayer.display`` are real
Gramps functions this module calls directly, with their own nontrivial
logic (walking a person's event reference list, applying the active
name-format preference) that a fake ``Person``/``Db`` pair can't
usefully stand in for. Instead, those three call sites are monkeypatched
per test via :func:`unittest.mock.patch`, with simple fakes that read
plain attributes set directly on :class:`FakePerson` - this tests
``fuzzy_match_display``'s own formatting/row-matching logic in
isolation, not Gramps' event-resolution or name-formatting logic
(which are Gramps' own responsibility, not this addon's).

Requires a real Gramps install for the same reason
``fuzzy_match_index_test.py`` does - see that file's own docstring.
"""

# ------------------------
# Python modules
# ------------------------
import unittest
from typing import Optional
from unittest.mock import patch

# ------------------------
# Gramps specific
# ------------------------
import fuzzy_match_display as fmd


class FakeDate:
    """Minimal stand-in for :class:`gramps.gen.lib.Date`."""

    def __init__(self, year: int) -> None:
        self._year = year

    def get_year(self) -> int:
        """Return the year, or 0 for "unknown" - matching Date's own convention."""
        return self._year


class FakeEvent:
    """Minimal stand-in for :class:`gramps.gen.lib.Event`."""

    def __init__(self, handle: str, year: int) -> None:
        self._handle = handle
        self._year = year

    def get_handle(self) -> str:
        """Return this event's handle."""
        return self._handle

    def get_date_object(self) -> FakeDate:
        """Return this event's date."""
        return FakeDate(self._year)


class FakePerson:
    """
    Minimal stand-in for :class:`gramps.gen.lib.Person`, carrying its
    birth/death :class:`FakeEvent` (or None) as plain attributes for
    :func:`fake_get_birth`/:func:`fake_get_death` to read.
    """

    def __init__(
        self,
        gramps_id: str,
        display_name: str,
        birth: Optional[FakeEvent] = None,
        death: Optional[FakeEvent] = None,
    ) -> None:
        self.gramps_id = gramps_id
        self.display_name = display_name
        self.birth = birth
        self.death = death

    def get_gramps_id(self) -> str:
        """Return this person's Gramps ID."""
        return self.gramps_id


def fake_get_birth(_db, person: FakePerson):
    """Stand-in for gramps.gen.utils.db.get_birth_or_fallback."""
    return person.birth


def fake_get_death(_db, person: FakePerson):
    """Stand-in for gramps.gen.utils.db.get_death_or_fallback."""
    return person.death


class FakeNameDisplayer:
    """Stand-in for gramps.gen.display.name.displayer."""

    def display(self, person: FakePerson) -> str:
        """Return the person's pre-set display name, unchanged."""
        return person.display_name


def _patch_display_deps():
    """Patch the three real-Gramps call sites format_person depends on."""
    return (
        patch.object(fmd, "get_birth_or_fallback", fake_get_birth),
        patch.object(fmd, "get_death_or_fallback", fake_get_death),
        patch.object(fmd, "name_displayer", FakeNameDisplayer()),
    )


class FormatPersonTest(unittest.TestCase):
    """Tests for :func:`fuzzy_match_display.format_person`."""

    def setUp(self) -> None:
        """Patch the birth/death/name-display dependencies for every test here."""
        for patcher in _patch_display_deps():
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_with_birth_and_death(self) -> None:
        """Both years present renders as "Name (birth-death) [ID]"."""
        person = FakePerson(
            "I0001",
            "Jane Smith",
            birth=FakeEvent("e1", 1900),
            death=FakeEvent("e2", 1980),
        )
        self.assertEqual(
            fmd.format_person(None, person), "Jane Smith (1900-1980) [I0001]"
        )

    def test_with_birth_only(self) -> None:
        """A missing death year leaves the far side of the dash blank."""
        person = FakePerson("I0002", "Jane Smith", birth=FakeEvent("e1", 1900))
        self.assertEqual(fmd.format_person(None, person), "Jane Smith (1900-) [I0002]")

    def test_with_neither_birth_nor_death(self) -> None:
        """No known dates at all omits the life-span parenthetical entirely."""
        person = FakePerson("I0003", "Jane Smith")
        self.assertEqual(fmd.format_person(None, person), "Jane Smith [I0003]")


class RefreshMatchingPersonRowsTest(unittest.TestCase):
    """Tests for :func:`fuzzy_match_display.refresh_matching_person_rows`."""

    def setUp(self) -> None:
        """Patch the birth/death/name-display dependencies for every test here."""
        for patcher in _patch_display_deps():
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_row_is_reformatted_when_its_birth_event_changed(self) -> None:
        """A row whose birth event was edited gets its display text redrawn."""
        birth = FakeEvent("e-birth", 1900)
        person = FakePerson("I0001", "Jane Smith", birth=birth)
        people = {"h1": person}

        # A (display, handle) row store - a plain list stands in for a
        # Gtk.ListStore here, since both support "for row in store" and
        # "row[0] = ..." (see the module docstring).
        person_store = [["stale text", "h1"]]

        db = _FakeDbLookup(people)
        fmd.refresh_matching_person_rows(db, person_store, ["e-birth"])
        self.assertEqual(person_store[0][0], "Jane Smith (1900-) [I0001]")

    def test_row_is_untouched_when_a_different_event_changed(self) -> None:
        """A row is left alone if the changed event isn't its birth or death."""
        person = FakePerson("I0001", "Jane Smith", birth=FakeEvent("e-birth", 1900))
        person_store = [["Jane Smith (1900-) [I0001]", "h1"]]
        db = _FakeDbLookup({"h1": person})

        fmd.refresh_matching_person_rows(db, person_store, ["some-other-event"])
        self.assertEqual(person_store[0][0], "Jane Smith (1900-) [I0001]")


class _FakeDbLookup:
    """Minimal db stand-in exposing only get_person_from_handle."""

    def __init__(self, people: dict) -> None:
        self._people = people

    def get_person_from_handle(self, handle: str):
        """Return the person with the given handle."""
        return self._people[handle]


if __name__ == "__main__":
    unittest.main()
