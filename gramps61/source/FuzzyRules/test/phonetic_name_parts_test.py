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
Unit tests for phonetic_name_parts.py: option parsing and formatting,
argument padding, and which name words are selected and matched.
"""

# ------------------------
# Python modules
# ------------------------
import unittest

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.lib import Name, Person, Surname

# ------------------------
# Gramps specific
# ------------------------
import phonetic_name_parts as parts


def make_person(
    first: str,
    surnames: list[str],
    call: str = "",
    nick: str = "",
    alternate_surname: str = "",
) -> Person:
    """
    Build a Person with one primary name and an optional alternate name.

    :param first: Given name(s).
    :param surnames: Surname pieces of the primary name.
    :param call: Call name.
    :param nick: Nick name.
    :param alternate_surname: Surname of an alternate name, if any.
    :returns: The new Person.
    """
    person = Person()
    name = Name()
    name.set_first_name(first)
    name.set_call_name(call)
    name.set_nick_name(nick)
    for text in surnames:
        piece = Surname()
        piece.set_surname(text)
        name.add_surname(piece)
    person.set_primary_name(name)
    if alternate_surname:
        alternate = Name()
        alternate.set_first_name("Other")
        piece = Surname()
        piece.set_surname(alternate_surname)
        alternate.add_surname(piece)
        person.add_alternate_name(alternate)
    return person


def identity(word: str) -> set[str]:
    """
    Trivial encoder for tests: the lower-cased word itself.

    :param word: The word to encode.
    :returns: A one-element set.
    """
    return {word.lower()}


# ------------------------------------------------------------
#
# ParsePartsTest
#
# ------------------------------------------------------------
class ParsePartsTest(unittest.TestCase):
    """Tests for parse_parts() and format_parts()."""

    def test_empty_gives_default(self) -> None:
        """A missing value means preferred surname and call name."""
        self.assertEqual(parts.parse_parts(""), parts.DEFAULT_KEYS)
        self.assertEqual(parts.parse_parts(None), parts.DEFAULT_KEYS)

    def test_missing_include_defaults_to_preferred(self) -> None:
        """Fields without an Include choice search the preferred name."""
        self.assertEqual(parts.parse_parts("given"), {"given", "primary"})

    def test_missing_fields_default_to_surname_and_call(self) -> None:
        """An Include choice without fields gets the default fields."""
        self.assertEqual(
            parts.parse_parts("alternate"), {"surname", "call", "alternate"}
        )

    def test_unknown_keys_ignored(self) -> None:
        """Unrecognised keys are dropped."""
        self.assertEqual(
            parts.parse_parts("surname,bogus,primary"), {"surname", "primary"}
        )

    def test_legacy_keys(self) -> None:
        """First-draft per-row Alternatives keys keep the preferred name."""
        self.assertEqual(
            parts.parse_parts("surname,surname_alt"),
            {"surname", "primary", "alternate"},
        )

    def test_format_is_display_order(self) -> None:
        """format_parts() orders keys as the check boxes are shown."""
        self.assertEqual(
            parts.format_parts({"primary", "surname", "given"}),
            "given,surname,primary",
        )

    def test_round_trip(self) -> None:
        """Formatting then parsing returns the same keys."""
        keys = frozenset({"title", "nick", "clan", "alternate"})
        self.assertEqual(parts.parse_parts(parts.format_parts(keys)), keys)


# ------------------------------------------------------------
#
# PadArgsTest
#
# ------------------------------------------------------------
class PadArgsTest(unittest.TestCase):
    """Tests for pad_args()."""

    def test_one_argument_gets_default(self) -> None:
        """A name alone is padded with the default option."""
        self.assertEqual(parts.pad_args(["Smith"]), ["Smith", "call,surname,primary"])

    def test_two_arguments_unchanged(self) -> None:
        """An explicit option is kept."""
        self.assertEqual(parts.pad_args(["Smith", "given"]), ["Smith", "given"])

    def test_none(self) -> None:
        """No arguments at all still gives two values."""
        self.assertEqual(parts.pad_args(None), ["", "call,surname,primary"])


# ------------------------------------------------------------
#
# PersonWordsTest
#
# ------------------------------------------------------------
class PersonWordsTest(unittest.TestCase):
    """Tests for person_words()."""

    def test_compound_surname_pieces_separate(self) -> None:
        """Each surname piece is a word of its own."""
        person = make_person("Ann", ["Thompson", "Johnson"])
        words = parts.person_words(person, frozenset({"surname", "primary"}))
        self.assertEqual(words, ["Thompson", "Johnson"])

    def test_given_words_separate(self) -> None:
        """Each word of a multi-word given name is a word of its own."""
        person = make_person("Joseph William", ["Baker"])
        words = parts.person_words(person, frozenset({"given", "primary"}))
        self.assertEqual(words, ["Joseph", "William"])

    def test_blank_call_is_first_given_name(self) -> None:
        """An empty Call field means the first given name."""
        person = make_person("John Henry", ["Smith"])
        words = parts.person_words(person, frozenset({"call", "primary"}))
        self.assertEqual(words, ["John"])

    def test_explicit_call_wins(self) -> None:
        """A recorded call name is used as is."""
        person = make_person("William Jack", ["Brown"], call="Jack")
        words = parts.person_words(person, frozenset({"call", "primary"}))
        self.assertEqual(words, ["Jack"])

    def test_alternate_names_only_when_included(self) -> None:
        """Alternate names are searched only with Alternatives ticked."""
        person = make_person("Paul", ["Smith"], alternate_surname="Johnson")
        preferred = parts.person_words(person, frozenset({"surname", "primary"}))
        both = parts.person_words(
            person, frozenset({"surname", "primary", "alternate"})
        )
        alternates = parts.person_words(person, frozenset({"surname", "alternate"}))
        self.assertEqual(preferred, ["Smith"])
        self.assertEqual(both, ["Smith", "Johnson"])
        self.assertEqual(alternates, ["Johnson"])


# ------------------------------------------------------------
#
# PersonMatchesTest
#
# ------------------------------------------------------------
class PersonMatchesTest(unittest.TestCase):
    """Tests for person_matches()."""

    def test_match_and_no_match(self) -> None:
        """A selected word must encode to one of the target codes."""
        person = make_person("Mary", ["Johnson"])
        keys = parts.DEFAULT_KEYS
        self.assertTrue(parts.person_matches(person, keys, {"johnson"}, identity))
        self.assertFalse(parts.person_matches(person, keys, {"john"}, identity))

    def test_no_target_codes(self) -> None:
        """An empty target never matches."""
        person = make_person("Mary", ["Johnson"])
        self.assertFalse(
            parts.person_matches(person, parts.DEFAULT_KEYS, set(), identity)
        )


if __name__ == "__main__":
    unittest.main()
