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
Unit tests for :mod:`nysiisrule`.

The reference vectors below are transcribed from Apache Commons
Codec's own ``NysiisTest.java`` (the same reference implementation
:func:`nysiisrule.encode` was ported from), covering every documented
rule and edge case, not just a handful of hand-picked names:
https://github.com/apache/commons-codec/blob/master/src/test/java/org/apache/commons/codec/language/NysiisTest.java

The ``HasNysiisName`` tests exercise the rule through its real
``prepare()``/``apply_to_one()`` lifecycle, the same way Gramps' own
filter execution does, not just by calling :func:`nysiisrule.encode`
directly - that would not catch a mistake in the rule's own glue code.
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
# This addon is not an installed package, so "nysiisrule" cannot be
# reached with a package-relative import here - see the note at the
# top of FuzzyMatchingGramplet.py for why.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

import nysiisrule

# (input, expected full/untruncated NYSIIS code) pairs from
# NysiisTest.java, using its `fullNysiis` (non-strict) encoder for
# every case.
REFERENCE_VECTORS = [
    # testBran
    ("Brian", "BRAN"),
    ("Brown", "BRAN"),
    ("Brun", "BRAN"),
    # testCap
    ("Capp", "CAP"),
    ("Cope", "CAP"),
    ("Copp", "CAP"),
    ("Kipp", "CAP"),
    # testDad
    ("Dent", "DAD"),
    # testDan
    ("Dane", "DAN"),
    ("Dean", "DAN"),
    ("Dionne", "DAN"),
    # testDropBy
    ("MACINTOSH", "MCANT"),
    ("KNUTH", "NAT"),
    ("KOEHN", "CAN"),
    ("PHILLIPSON", "FALAPSAN"),
    ("PFEISTER", "FASTAR"),
    ("SCHOENHOEFT", "SANAFT"),
    ("MCKEE", "MCY"),
    ("MACKIE", "MCY"),
    ("HEITSCHMIDT", "HATSNAD"),
    ("BART", "BAD"),
    ("HURD", "HAD"),
    ("HUNT", "HAD"),
    ("WESTERLUND", "WASTARLAD"),
    ("CASSTEVENS", "CASTAFAN"),
    ("VASQUEZ", "VASG"),
    ("FRAZIER", "FRASAR"),
    ("BOWMAN", "BANAN"),
    ("MCKNIGHT", "MCNAGT"),
    ("RICKERT", "RACAD"),
    ("DEUTSCH", "DAT"),
    ("WESTPHAL", "WASTFAL"),
    ("SHRIVER", "SRAVAR"),
    ("KUHL", "CAL"),
    ("RAWSON", "RASAN"),
    ("JILES", "JAL"),
    ("CARRAWAY", "CARY"),
    ("YAMADA", "YANAD"),
    # testFal
    ("Phil", "FAL"),
    # testOthers
    ("O'Daniel", "ODANAL"),
    ("O'Donnel", "ODANAL"),
    ("Cory", "CARY"),
    ("Corey", "CARY"),
    ("Kory", "CARY"),
    ("FUZZY", "FASY"),
    # testRule1
    ("MACX", "MCX"),
    ("KNX", "NX"),
    ("KX", "CX"),
    ("PHX", "FX"),
    ("PFX", "FX"),
    ("SCHX", "SX"),
    # testRule2
    ("XEE", "XY"),
    ("XIE", "XY"),
    ("XDT", "XD"),
    ("XRT", "XD"),
    ("XRD", "XD"),
    ("XNT", "XD"),
    ("XND", "XD"),
    # testRule4Dot1
    ("XEV", "XAF"),
    ("XAX", "XAX"),
    ("XEX", "XAX"),
    ("XIX", "XAX"),
    ("XOX", "XAX"),
    ("XUX", "XAX"),
    # testRule4Dot2
    ("XQ", "XG"),
    ("XZ", "X"),
    ("XM", "XN"),
    # testRule5
    ("XS", "X"),
    ("XSS", "X"),
    # testRule6
    ("XAY", "XY"),
    ("XAYS", "XY"),
    # testRule7
    ("XA", "X"),
    ("XAS", "X"),
    # testSnad
    ("Schmidt", "SNAD"),
    # testSnat
    ("Smith", "SNAT"),
    ("Schmit", "SNAT"),
    # testSpecialBranches
    ("Kobwick", "CABWAC"),
    ("Kocher", "CACAR"),
    ("Fesca", "FASC"),
    ("Shom", "SAN"),
    ("Ohlo", "OL"),
    ("Uhu", "UH"),
    ("Um", "UN"),
    # testTranan
    ("Trueman", "TRANAN"),
    ("Truman", "TRANAN"),
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
    Build ``HasNysiisName([target_name])``, run its real ``prepare()``/
    ``apply_to_one()`` lifecycle, and return whether it matches a
    person with ``surname``.
    """
    rule = nysiisrule.HasNysiisName([target_name])
    rule.prepare(None, None)
    return rule.apply_to_one(None, _FakePerson(surname))


# ------------------------------------------------------------
#
# NysiisEncodeTest
#
# ------------------------------------------------------------
class NysiisEncodeTest(unittest.TestCase):
    """Tests for :func:`nysiisrule.encode` against the full Apache
    Commons Codec reference vector set."""

    def test_reference_vectors(self) -> None:
        """encode() must match every reference (input, code) pair."""
        for name, expected in REFERENCE_VECTORS:
            with self.subTest(name=name):
                self.assertEqual(nysiisrule.encode(name), {expected})

    def test_empty_name_is_handled(self) -> None:
        """An empty name must not raise and returns an empty code."""
        self.assertEqual(nysiisrule.encode(""), {""})

    def test_non_letter_characters_are_stripped(self) -> None:
        """Punctuation must not cause a crash or leak into the code."""
        self.assertEqual(nysiisrule.encode("O'Daniel"), {"ODANAL"})


# ------------------------------------------------------------
#
# HasNysiisNameTest
#
# ------------------------------------------------------------
class HasNysiisNameTest(unittest.TestCase):
    """Tests for :class:`nysiisrule.HasNysiisName`."""

    def test_matches_identical_surname(self) -> None:
        """A person with the exact target surname must match."""
        self.assertTrue(_apply("Boucher", "Boucher"))

    def test_matches_nysiis_variant(self) -> None:
        """
        A NYSIIS-equivalent spelling must match, using a pair NYSIIS
        genuinely groups (see REFERENCE_VECTORS - "Cory"/"Corey"/"Kory"
        all encode to "CARY").
        """
        self.assertTrue(_apply("Cory", "Corey"))

    def test_does_not_match_unrelated_surname(self) -> None:
        """A clearly unrelated surname must not match."""
        self.assertFalse(_apply("Boucher", "Anderson"))

    def test_empty_target_matches_nothing(self) -> None:
        """An empty/unset target name must not match every empty-coded person."""
        self.assertFalse(_apply("", "Anderson"))

    def test_name_and_category(self) -> None:
        """The rule's own display metadata should be set."""
        self.assertEqual(
            nysiisrule.HasNysiisName.name, "NYSIIS match of People with the <n>"
        )
        self.assertEqual(nysiisrule.HasNysiisName.category, "General filters")

    def test_apply_matches_apply_to_one(self) -> None:
        """
        Gramps 5.2 calls a rule's `apply()` method; Gramps 6.0+ calls
        `apply_to_one()` instead (confirmed directly against both
        branches' real source, not assumed) - both must agree, since
        this one rule class has to work correctly on either.
        """
        rule = nysiisrule.HasNysiisName(["Boucher"])
        rule.prepare(None, None)
        person = _FakePerson("Boucher")
        self.assertEqual(rule.apply(None, person), rule.apply_to_one(None, person))
        self.assertTrue(rule.apply(None, person))


# ------------------------------------------------------------
#
# NysiisContractTest
#
# ------------------------------------------------------------
class NysiisContractTest(unittest.TestCase):
    """Confirms the module declares the encoder contract correctly."""

    def test_algorithm_id(self) -> None:
        """ALGORITHM_ID must be the stable registry key for this encoder."""
        self.assertEqual(nysiisrule.ALGORITHM_ID, "nysiis")

    def test_algorithm_label_is_a_string(self) -> None:
        """ALGORITHM_LABEL must be a display-ready string."""
        self.assertIsInstance(nysiisrule.ALGORITHM_LABEL, str)
        self.assertTrue(nysiisrule.ALGORITHM_LABEL)

    def test_encode_is_callable(self) -> None:
        """encode must be callable, per the encoder contract."""
        self.assertTrue(callable(nysiisrule.encode))


if __name__ == "__main__":
    unittest.main()
