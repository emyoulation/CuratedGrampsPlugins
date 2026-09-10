#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025  Phonetic Matching Gramplet contributors
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
Unit tests for :mod:`matchratingrule`.

The reference vectors below were produced by running the real
``jellyfish`` library's ``match_rating_codex`` (version 0.8.9)
directly against each name and recording its output - not transcribed
from documentation, which for this specific function turned out to be
stale (jellyfish's own README claims
``match_rating_codex('Jellyfish') == 'JLLFSH'``; the actual installed
0.8.9 library returns ``'JLYFSH'``, confirmed by running it directly).
That mismatch is exactly why this file checks against the live library
rather than trusting the documented example.

The ``HasMatchRatingName`` tests exercise the rule through its real
``prepare()``/``apply_to_one()`` lifecycle, the same way Gramps' own
filter execution does, not just by calling
:func:`matchratingrule.encode` directly - that would not catch a
mistake in the rule's own glue code.
"""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import unittest

# ------------------------
# Gramps specific
# ------------------------
# This addon is not an installed package, so "matchratingrule" cannot
# be reached with a package-relative import here - see the note at
# the top of FuzzyMatchingGramplet.py for why.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

import matchratingrule

# (input, expected codex) pairs, each independently confirmed against
# a real, installed jellyfish==0.8.9 (jellyfish.match_rating_codex).
REFERENCE_VECTORS = [
    ("Smith", "SMTH"),
    ("Smyth", "SMYTH"),
    ("Johnson", "JHNSN"),
    ("Johnsen", "JHNSN"),
    ("Johnston", "JHNSTN"),
    ("Anderson", "ANDRSN"),
    ("Andersen", "ANDRSN"),
    ("Robert", "RBRT"),
    ("Rupert", "RPRT"),
    ("Catherine", "CTHRN"),
    ("Katherine", "KTHRN"),
    ("Meyer", "MYR"),
    ("Meier", "MR"),
    ("Boucher", "BCHR"),
    ("MacDonald", "MCDNLD"),
    ("McDonald", "MCDNLD"),
    ("Schmidt", "SCHMDT"),
    ("Schmit", "SCHMT"),
    ("Jellyfish", "JLYFSH"),
    ("Mississippi", "MSSP"),
    ("Bookkeeper", "BKPR"),
    ("Aardvark", "ARDVRK"),
    ("Zzyzx", "ZYZX"),
    ("A", "A"),
    ("AB", "AB"),
    ("ABC", "ABC"),
    ("Wright", "WRGHT"),
    ("Write", "WRT"),
    ("Knight", "KNGHT"),
    ("Night", "NGHT"),
    ("Phillip", "PHLP"),
    ("Filip", "FLP"),
    ("Yancey", "YNCY"),
    ("Xerox", "XRX"),
    ("Aaaaaaa", "A"),
    ("Bbbbccc", "BC"),
    ("Washington", "WSHGTN"),
    ("Jefferson", "JFRSN"),
    ("Lincoln", "LNCLN"),
    ("Roosevelt", "RSVLT"),
    ("Eisenhower", "ESNHWR"),
    ("Kennedy", "KNDY"),
    ("Nixon", "NXN"),
    ("Reagan", "RGN"),
    ("Clinton", "CLNTN"),
    ("Obama", "OBM"),
    ("Trump", "TRMP"),
    ("Biden", "BDN"),
]


class _FakeName:
    """Minimal stand-in for a Gramps primary name."""

    def __init__(self, surname):
        self._surname = surname

    def get_surname(self):
        """Return the fake surname."""
        return self._surname


class _FakePerson:
    """Minimal stand-in for a Gramps Person, surname-only."""

    def __init__(self, surname):
        self._name = _FakeName(surname)

    def get_primary_name(self):
        """Return the fake primary name."""
        return self._name


def _apply(target_name, surname):
    """
    Build ``HasMatchRatingName([target_name])``, run its real
    ``prepare()``/``apply_to_one()`` lifecycle, and return whether it
    matches a person with ``surname``.
    """
    rule = matchratingrule.HasMatchRatingName([target_name])
    rule.prepare(None, None)
    return rule.apply_to_one(None, _FakePerson(surname))


# ------------------------------------------------------------
#
# MatchRatingEncodeTest
#
# ------------------------------------------------------------
class MatchRatingEncodeTest(unittest.TestCase):
    """Tests for :func:`matchratingrule.encode`."""

    def test_reference_vectors(self) -> None:
        """encode() must match every jellyfish-confirmed (input, codex) pair."""
        for name, expected in REFERENCE_VECTORS:
            with self.subTest(name=name):
                self.assertEqual(matchratingrule.encode(name), {expected})

    def test_empty_name_is_handled(self) -> None:
        """An empty name must not raise and returns an empty codex."""
        self.assertEqual(matchratingrule.encode(""), {""})

    def test_non_letter_characters_do_not_crash(self) -> None:
        """
        Punctuation, hyphens, and accented letters must not crash
        encode(), unlike the jellyfish library this was ported from,
        which raises ValueError on exactly this input.
        """
        for name in ("O'Brien", "Jean-Luc", "Müller", "D'Angelo-Smith III"):
            with self.subTest(name=name):
                result = matchratingrule.encode(name)
                self.assertIsInstance(result, set)
                self.assertEqual(len(result), 1)


# ------------------------------------------------------------
#
# HasMatchRatingNameTest
#
# ------------------------------------------------------------
class HasMatchRatingNameTest(unittest.TestCase):
    """Tests for :class:`matchratingrule.HasMatchRatingName`."""

    def test_matches_identical_surname(self) -> None:
        """A person with the exact target surname must match."""
        self.assertTrue(_apply("Boucher", "Boucher"))

    def test_does_not_match_unrelated_surname(self) -> None:
        """A clearly unrelated surname must not match."""
        self.assertFalse(_apply("Boucher", "Anderson"))

    def test_empty_target_matches_nothing(self) -> None:
        """An empty/unset target name must not match every empty-coded person."""
        self.assertFalse(_apply("", "Anderson"))

    def test_name_and_category(self) -> None:
        """The rule's own display metadata should be set."""
        self.assertEqual(
            matchratingrule.HasMatchRatingName.name,
            "Match Rating Approach match of People with the <n>",
        )
        self.assertEqual(matchratingrule.HasMatchRatingName.category, "General filters")

    def test_apply_matches_apply_to_one(self) -> None:
        """
        Gramps 5.2 calls a rule's `apply()` method; Gramps 6.0+ calls
        `apply_to_one()` instead (confirmed directly against both
        branches' real source, not assumed) - both must agree, since
        this one rule class has to work correctly on either.
        """
        rule = matchratingrule.HasMatchRatingName(["Boucher"])
        rule.prepare(None, None)
        person = _FakePerson("Boucher")
        self.assertEqual(rule.apply(None, person), rule.apply_to_one(None, person))
        self.assertTrue(rule.apply(None, person))


# ------------------------------------------------------------
#
# MatchRatingContractTest
#
# ------------------------------------------------------------
class MatchRatingContractTest(unittest.TestCase):
    """Confirms the module declares the encoder contract correctly."""

    def test_algorithm_id(self) -> None:
        """ALGORITHM_ID must be the stable registry key for this encoder."""
        self.assertEqual(matchratingrule.ALGORITHM_ID, "match_rating")

    def test_algorithm_label_is_a_string(self) -> None:
        """ALGORITHM_LABEL must be a display-ready string."""
        self.assertIsInstance(matchratingrule.ALGORITHM_LABEL, str)
        self.assertTrue(matchratingrule.ALGORITHM_LABEL)

    def test_encode_is_callable(self) -> None:
        """encode must be callable, per the encoder contract."""
        self.assertTrue(callable(matchratingrule.encode))


if __name__ == "__main__":
    unittest.main()
