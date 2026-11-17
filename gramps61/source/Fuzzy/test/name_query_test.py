#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Claude AI (wish coding by Brian McCullough)
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

"""Unit tests for name_query.py (the shared "Surname, Given" parser)."""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ------------------------
# Gramps specific
# ------------------------
from name_query import (  # pylint: disable=wrong-import-position
    format_name_query,
    given_name_matches,
    parse_name_query,
    surname_words,
)


class ParseNameQueryTest(unittest.TestCase):
    """parse_name_query / format_name_query."""

    def test_comma_splits(self):
        self.assertEqual(parse_name_query(" Smith ,  John Paul "), ("Smith", "John Paul"))

    def test_no_comma_is_all_surname(self):
        self.assertEqual(parse_name_query("Van Der Berg"), ("Van Der Berg", ""))

    def test_only_first_comma(self):
        self.assertEqual(parse_name_query("Smith, John, Jr"), ("Smith", "John, Jr"))

    def test_blank(self):
        self.assertEqual(parse_name_query("   "), ("", ""))

    def test_given_only(self):
        self.assertEqual(parse_name_query(", Mary"), ("", "Mary"))

    def test_format_round_trip(self):
        for surname, given in (("Smith", "John"), ("Van Der Berg", ""), ("", "Mary")):
            self.assertEqual(
                parse_name_query(format_name_query(surname, given)), (surname, given)
            )

    def test_format_no_trailing_comma(self):
        self.assertEqual(format_name_query("Smith", "  "), "Smith")

    def test_surname_words(self):
        self.assertEqual(surname_words("Thompson  McCullough"), ["Thompson", "McCullough"])


class GivenNameMatchesTest(unittest.TestCase):
    """given_name_matches."""

    def test_blank_matches_all(self):
        self.assertTrue(given_name_matches("", "Anyone"))

    def test_contains_ignoring_case(self):
        self.assertTrue(given_name_matches("ANN", "Joanne"))

    def test_recorded_word_is_prefix_of_typed(self):
        self.assertTrue(given_name_matches("Billy", "Bill Henry"))

    def test_no_match(self):
        self.assertFalse(given_name_matches("Bill", "William"))


if __name__ == "__main__":
    unittest.main()
