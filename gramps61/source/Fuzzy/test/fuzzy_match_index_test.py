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
Unit tests for :mod:`fuzzy_match_index`.

Uses small fake ``Db``/``Person``/``Name``/``Surname`` stand-ins (see
below) rather than a real :class:`~gramps.gen.db.base.DbReadBase` or
an actual Family Tree, since :class:`~fuzzy_match_index.FuzzyMatchIndex`
only ever calls three database methods
(``get_surname_list``/``get_person_handles``/``get_person_from_handle``)
and :func:`~fuzzy_match_index.person_surnames` (itself only
``get_primary_name().get_surname_list()`` plus each piece's own
``get_surname()``) - a real database is more than this needs to
exercise its own logic.

``FakeName`` supports one *or more* surname pieces specifically to
cover the compound/double-surname bug this module's ``person_surnames``
helper exists to fix - see
``test_compound_surname_person_is_found_by_either_piece`` and
``test_compound_surname_matches_even_when_get_surname_list_is_narrow``.

Like ``phonetic_codes_test.py``, this still imports the real
``phonetic_codes`` module (for ``ALGORITHMS``), which in turn imports
several real ``gramps.*`` modules at import time - see the project
README's "Running the tests" section for why ``GRAMPS_RESOURCES`` must
be set and this must run inside an environment with Gramps installed,
the same requirement that file already has.
"""

# ------------------------
# Python modules
# ------------------------
import unittest
from typing import List, Union

# ------------------------
# Gramps specific
# ------------------------
from fuzzy_match_index import FuzzyMatchIndex, person_surnames


class FakeSurname:
    """Minimal stand-in for one gramps.gen.lib.Surname piece."""

    def __init__(self, text: str) -> None:
        self._text = text

    def get_surname(self) -> str:
        """Return this piece's own text."""
        return self._text


class FakeName:
    """
    Minimal stand-in for :class:`gramps.gen.lib.Name`, supporting one
    or more :class:`FakeSurname` pieces - a compound/double surname
    (e.g. "Thompson McCullough") is two pieces on one name, not two
    words in one piece.
    """

    def __init__(self, surnames: Union[str, List[str]]) -> None:
        if isinstance(surnames, str):
            surnames = [surnames]
        self._pieces = [FakeSurname(text) for text in surnames]

    def get_surname_list(self) -> List[FakeSurname]:
        """Return every surname piece on this name."""
        return list(self._pieces)

    def get_surname(self) -> str:
        """
        Return the fully-formatted (space-joined) surname across every
        piece - what ``Name.get_surname()`` returns for a real
        multi-piece name, and exactly the string
        :func:`fuzzy_match_index.person_surnames` must NOT be
        confused with. Only used by tests that specifically want that
        joined form (see ``test_compound_surname_matches_even_when_
        get_surname_list_is_narrow``); everything else should read
        individual pieces via :meth:`get_surname_list`.
        """
        return " ".join(piece.get_surname() for piece in self._pieces)


class FakePerson:
    """Minimal stand-in for :class:`gramps.gen.lib.Person`."""

    def __init__(self, handle: str, surnames: Union[str, List[str]]) -> None:
        self._handle = handle
        self._name = FakeName(surnames)

    def get_handle(self) -> str:
        """Return this person's handle."""
        return self._handle

    def get_primary_name(self) -> FakeName:
        """Return this person's primary name."""
        return self._name


class FakeDb:
    """
    Minimal stand-in for :class:`gramps.gen.db.base.DbReadBase`,
    exposing only the handful of read methods
    :class:`~fuzzy_match_index.FuzzyMatchIndex` actually calls, plus
    ``add_person``/``remove_person``/``rename_person`` helpers for
    tests to mutate it between calls the way editing a real Family
    Tree would.

    ``get_surname_list`` here enumerates every individual surname
    piece across every person (the generous case this addon expects
    real Gramps to behave like) - see :class:`NarrowFakeDb` below for
    a deliberately pessimistic stand-in used to test the fallback path
    that doesn't depend on that assumption.
    """

    def __init__(self) -> None:
        self._people: dict = {}

    def add_person(self, handle: str, surnames: Union[str, List[str]]) -> None:
        """Add (or overwrite) a person with the given handle and surname(s)."""
        self._people[handle] = FakePerson(handle, surnames)

    def rename_person(self, handle: str, surnames: Union[str, List[str]]) -> None:
        """Give an existing handle new surname(s), as an edit would."""
        self._people[handle] = FakePerson(handle, surnames)

    def remove_person(self, handle: str) -> None:
        """Remove a person, as a deletion would."""
        del self._people[handle]

    def get_surname_list(self):
        """Return every unique surname piece currently present."""
        pieces = set()
        for person in self._people.values():
            pieces.update(person_surnames(person))
        return sorted(pieces)

    def get_person_handles(self, sort_handles: bool = False):
        """Return every person handle currently present."""
        handles = list(self._people.keys())
        if sort_handles:
            handles.sort()
        return handles

    def get_person_from_handle(self, handle: str) -> FakePerson:
        """Return the person with the given handle."""
        return self._people[handle]


class NarrowFakeDb(FakeDb):
    """
    A pessimistic :class:`FakeDb` whose ``get_surname_list`` returns
    only each person's single, fully-formatted (space-joined) surname
    string - as if the database's own surname index never broke a
    compound/double surname into its individual pieces at all. Used
    to prove :meth:`~fuzzy_match_index.FuzzyMatchIndex.build`'s
    Stage 1 self-correction (see that method's own comments) finds a
    phonetic code for a piece even when this, the narrowest plausible
    reading of what ``get_surname_list`` might return, holds.
    """

    def get_surname_list(self):
        """Return each person's single, joined surname string."""
        return sorted(
            {
                person.get_primary_name().get_surname()
                for person in self._people.values()
            }
        )


class FuzzyMatchIndexTest(unittest.TestCase):
    """Tests for :class:`fuzzy_match_index.FuzzyMatchIndex`."""

    def setUp(self) -> None:
        """Build a small fake tree: two Smiths and one Smyth."""
        self.db = FakeDb()
        self.db.add_person("h-smith-1", "Smith")
        self.db.add_person("h-smith-2", "Smith")
        self.db.add_person("h-smyth-1", "Smyth")
        self.index = FuzzyMatchIndex(self.db, "soundex")

    def test_not_ready_before_build(self) -> None:
        """Every find_* method returns empty results before the first build."""
        self.assertFalse(self.index.ready)
        self.assertEqual(self.index.find_surnames("Smith"), [])
        self.assertEqual(self.index.find_people("Smith"), [])
        self.assertEqual(self.index.find_matches("Smith"), {})

    def test_build_sync_finds_phonetic_matches(self) -> None:
        """A completed build finds both Smith and its phonetic match Smyth."""
        self.index.build_sync()
        self.assertTrue(self.index.ready)
        matches = self.index.find_matches("Smith")
        self.assertIn("Smith", matches)
        self.assertIn("Smyth", matches)
        self.assertCountEqual(matches["Smith"], ["h-smith-1", "h-smith-2"])
        self.assertCountEqual(matches["Smyth"], ["h-smyth-1"])

    def test_build_progress_callback_reports_both_phases(self) -> None:
        """The progress callback is invoked for both the surname and people phases."""
        phases_seen = []
        for _ in self.index.build(
            progress_callback=lambda phase, pos, total: phases_seen.append(phase)
        ):
            pass
        self.assertIn("surnames", phases_seen)
        self.assertIn("people", phases_seen)

    def test_on_person_changed_adds_new_person_to_existing_surname(self) -> None:
        """A newly-added person is filed under their surname's existing bucket."""
        self.index.build_sync()
        self.db.add_person("h-smith-3", "Smith")
        touched = self.index.on_person_changed(["h-smith-3"])
        self.assertEqual(touched, {"Smith"})
        self.assertIn("h-smith-3", self.index.find_people("Smith"))

    def test_on_person_changed_new_surname_is_indexed_immediately(self) -> None:
        """A person with a brand-new surname is phonetically matchable right away."""
        self.index.build_sync()
        self.db.add_person("h-jones-1", "Jones")
        touched = self.index.on_person_changed(["h-jones-1"])
        self.assertEqual(touched, {"Jones"})
        # Should be findable via its own phonetic match, not just an
        # exact-surname lookup - proves the code index itself, not
        # only surname_to_handles, was patched.
        self.assertIn("Jones", self.index.find_matches("Jones"))

    def test_on_person_changed_surname_edit_moves_handle(self) -> None:
        """Editing a person's surname moves their handle to the new bucket."""
        self.index.build_sync()
        self.db.rename_person("h-smith-1", "Jones")
        touched = self.index.on_person_changed(["h-smith-1"])
        self.assertEqual(touched, {"Smith", "Jones"})
        self.assertNotIn("h-smith-1", self.index.find_people("Smith"))
        self.assertIn("h-smith-1", self.index.find_people("Jones"))
        # The old surname had another person left under it, so it
        # must not have been dropped from the index entirely.
        self.assertIn("Smith", self.index.find_matches("Smith"))

    def test_on_person_deleted_removes_handle(self) -> None:
        """A deleted person's handle no longer appears under their surname."""
        self.index.build_sync()
        self.db.remove_person("h-smyth-1")
        touched = self.index.on_person_deleted(["h-smyth-1"])
        self.assertEqual(touched, {"Smyth"})
        self.assertEqual(self.index.find_people("Smyth"), [])

    def test_on_person_deleted_last_of_a_surname_removes_it_from_index(self) -> None:
        """Deleting the last person with a surname drops that surname entirely."""
        self.index.build_sync()
        self.db.remove_person("h-smyth-1")
        self.index.on_person_deleted(["h-smyth-1"])
        # Smyth had exactly one person; once they're gone, Smyth
        # should stop showing up as a match at all, not linger with a
        # permanently-empty handle list.
        matches = self.index.find_matches("Smith")
        self.assertNotIn("Smyth", matches)

    def test_on_person_deleted_before_build_is_a_no_op(self) -> None:
        """Calling on_person_deleted before the first build touches nothing."""
        touched = self.index.on_person_deleted(["h-smith-1"])
        self.assertEqual(touched, set())

    def test_on_rebuild_marks_not_ready(self) -> None:
        """on_rebuild clears the ready flag so a caller knows to rebuild."""
        self.index.build_sync()
        self.assertTrue(self.index.ready)
        self.index.on_rebuild()
        self.assertFalse(self.index.ready)


class PersonSurnamesTest(unittest.TestCase):
    """Direct tests for :func:`fuzzy_match_index.person_surnames`."""

    def test_single_surname_returns_one_piece(self) -> None:
        """An ordinary, single-surname person yields a one-element set."""
        person = FakePerson("h1", "Smith")
        self.assertEqual(person_surnames(person), {"Smith"})

    def test_compound_surname_returns_each_piece(self) -> None:
        """A compound/double surname yields every piece, not the joined string."""
        person = FakePerson("h1", ["Thompson", "McCullough"])
        self.assertEqual(person_surnames(person), {"Thompson", "McCullough"})
        # The bug this function exists to avoid: the joined string is
        # not itself a "piece", and must not appear here.
        self.assertNotIn("Thompson McCullough", person_surnames(person))

    def test_empty_surname_piece_is_excluded(self) -> None:
        """A blank surname piece contributes nothing."""
        person = FakePerson("h1", ["Smith", ""])
        self.assertEqual(person_surnames(person), {"Smith"})


class CompoundSurnameRegressionTest(unittest.TestCase):
    """
    Regression tests for the compound/double-surname bug: a person
    with more than one surname piece (e.g. "Thompson McCullough") was
    previously invisible to phonetic search entirely, findable under
    neither piece, because indexing used ``Name.get_surname()``'s
    single joined string instead of :func:`person_surnames`.
    """

    def test_compound_surname_person_is_found_by_either_piece(self) -> None:
        """A compound-surname person is found by a search for either piece."""
        db = FakeDb()
        db.add_person("h-other-thompson", "Thompson")
        db.add_person("h-compound", ["Thompson", "McCullough"])
        index = FuzzyMatchIndex(db, "soundex")
        index.build_sync()

        matches = index.find_matches("Thompson")
        self.assertIn("h-compound", matches.get("Thompson", []))
        self.assertIn("h-other-thompson", matches.get("Thompson", []))

        matches = index.find_matches("McCullough")
        self.assertIn("h-compound", matches.get("McCullough", []))

    def test_compound_surname_matches_even_when_get_surname_list_is_narrow(
        self,
    ) -> None:
        """
        Even if the database's own surname list never enumerates a
        compound surname's individual pieces (only the joined
        string), each piece still gets a phonetic code - see
        :meth:`~fuzzy_match_index.FuzzyMatchIndex.build`'s Stage 1
        self-correction.
        """
        db = NarrowFakeDb()
        db.add_person("h-compound", ["Thompson", "McCullough"])
        index = FuzzyMatchIndex(db, "soundex")
        index.build_sync()

        # Sanity check this test is actually exercising the narrow
        # case it claims to: the joined string, not the individual
        # pieces, is what get_surname_list() returns here.
        self.assertEqual(db.get_surname_list(), ["Thompson McCullough"])

        self.assertIn("Thompson", index.find_surnames("Thompson"))
        self.assertIn("h-compound", index.find_people("Thompson"))
        self.assertIn("McCullough", index.find_surnames("McCullough"))
        self.assertIn("h-compound", index.find_people("McCullough"))

    def test_editing_away_one_piece_of_a_compound_surname(self) -> None:
        """Removing one piece of a compound surname on edit updates both buckets."""
        db = FakeDb()
        db.add_person("h-compound", ["Thompson", "McCullough"])
        index = FuzzyMatchIndex(db, "soundex")
        index.build_sync()

        db.rename_person("h-compound", "McCullough")
        touched = index.on_person_changed(["h-compound"])

        self.assertEqual(touched, {"Thompson", "McCullough"})
        self.assertNotIn("h-compound", index.find_people("Thompson"))
        self.assertIn("h-compound", index.find_people("McCullough"))


if __name__ == "__main__":
    unittest.main()
