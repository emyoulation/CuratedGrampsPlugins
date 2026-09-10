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
Unit tests for :mod:`metaphonerule`.

The exact-code vectors and name groups below are transcribed from
Apache Commons Codec's own ``MetaphoneTest.java`` (the same reference
implementation :func:`metaphonerule.encode` was ported from) -
47 direct assertions plus every "these names must all share a code"
group in that file, covering over 200 name comparisons total, not just
a handful of hand-picked names:
https://github.com/apache/commons-codec/blob/master/src/test/java/org/apache/commons/codec/language/MetaphoneTest.java

The ``HasMetaphoneName`` tests exercise the rule through its real
``prepare()``/``apply_to_one()`` lifecycle, the same way Gramps' own
filter execution does, not just by calling :func:`metaphonerule.encode`
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
# This addon is not an installed package, so "metaphonerule" cannot be
# reached with a package-relative import here - see the note at the
# top of FuzzyMatchingGramplet.py for why.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

import metaphonerule

# (input, expected code) pairs, transcribed from MetaphoneTest.java's
# individual assertEquals calls (default max code length of 4).
REFERENCE_VECTORS = [
    ("SCIENCE", "SNS"),
    ("SCENE", "SN"),
    ("SCY", "S"),
    ("GNU", "N"),
    ("SIGNED", "SNT"),
    ("GHENT", "KNT"),
    ("BAUGH", "B"),
    ("HOWL", "HL"),
    ("TESTING", "TSTN"),
    ("THE", "0"),
    ("QUICK", "KK"),
    ("BROWN", "BRN"),
    ("FOX", "FKS"),
    ("JUMPED", "JMPT"),
    ("OVER", "OFR"),
    ("LAZY", "LS"),
    ("DOGS", "TKS"),
    ("PHISH", "FX"),
    ("SHOT", "XT"),
    ("ODSIAN", "OTXN"),
    ("PULSION", "PLXN"),
    ("RETCH", "RX"),
    ("WATCH", "WX"),
    ("OTIA", "OX"),
    ("PORTION", "PRXN"),
    ("SCHEDULE", "SKTL"),
    ("SCHEMATIC", "SKMT"),
    ("DISCHARGE", "TSKR"),
    ("ECHO", "EX"),
    ("TEACH", "TX"),
    ("CHERI", "XR"),
    ("CHIP", "XP"),
    ("CHRIST", "XRST"),
    ("CIAO", "X"),
    ("CITY", "ST"),
    ("CAT", "KT"),
    ("DODGY", "TJ"),
    ("DODGE", "TJ"),
    ("ADGIEMTI", "AJMT"),
    ("WHY", ""),
    ("COMB", "KM"),
    ("TOMB", "TM"),
    ("WOMB", "WM"),
    ("CIAPO", "XP"),
]

# ("these names must all share one Metaphone code") groups, transcribed
# from MetaphoneTest's assertIsMetaphoneEqual/assertMetaphoneEqual calls.
EQUIVALENCE_GROUPS = [
    ("Case", ["case", "CASE"]),
    ("caSe", ["cAsE"]),
    ("quick", ["cookie"]),
    ("Lawrence", ["Lorenza"]),
    ("Gary", ["Cahra"]),
    ("Aero", ["Eure"]),
    ("Albert", ["Ailbert", "Alberik", "Albert", "Alberto", "Albrecht"]),
    (
        "Gary",
        [
            "Cahra",
            "Cara",
            "Carey",
            "Cari",
            "Caria",
            "Carie",
            "Caro",
            "Carree",
            "Carri",
            "Carrie",
            "Carry",
            "Cary",
            "Cora",
            "Corey",
            "Cori",
            "Corie",
            "Correy",
            "Corri",
            "Corrie",
            "Corry",
            "Cory",
            "Gray",
            "Kara",
            "Kare",
            "Karee",
            "Kari",
            "Karia",
            "Karie",
            "Karrah",
            "Karrie",
            "Karry",
            "Kary",
            "Keri",
            "Kerri",
            "Kerrie",
            "Kerry",
            "Kira",
            "Kiri",
            "Kora",
            "Kore",
            "Kori",
            "Korie",
            "Korrie",
            "Korry",
        ],
    ),
    (
        "John",
        [
            "Gena",
            "Gene",
            "Genia",
            "Genna",
            "Genni",
            "Gennie",
            "Genny",
            "Giana",
            "Gianna",
            "Gina",
            "Ginni",
            "Ginnie",
            "Ginny",
            "Jaine",
            "Jan",
            "Jana",
            "Jane",
            "Janey",
            "Jania",
            "Janie",
            "Janna",
            "Jany",
            "Jayne",
            "Jean",
            "Jeana",
            "Jeane",
            "Jeanie",
            "Jeanna",
            "Jeanne",
            "Jeannie",
            "Jen",
            "Jena",
            "Jeni",
            "Jenn",
            "Jenna",
            "Jennee",
            "Jenni",
            "Jennie",
            "Jenny",
            "Jinny",
            "Jo Ann",
            "Jo-Ann",
            "Jo-Anne",
            "Joan",
            "Joana",
            "Joane",
            "Joanie",
            "Joann",
            "Joanna",
            "Joanne",
            "Joeann",
            "Johna",
            "Johnna",
            "Joni",
            "Jonie",
            "Juana",
            "June",
            "Junia",
            "Junie",
        ],
    ),
    (
        "Knight",
        [
            "Hynda",
            "Nada",
            "Nadia",
            "Nady",
            "Nat",
            "Nata",
            "Natty",
            "Neda",
            "Nedda",
            "Nedi",
            "Netta",
            "Netti",
            "Nettie",
            "Netty",
            "Nita",
            "Nydia",
        ],
    ),
    (
        "Mary",
        [
            "Mair",
            "Maire",
            "Mara",
            "Mareah",
            "Mari",
            "Maria",
            "Marie",
            "Mary",
            "Maura",
            "Maure",
            "Meara",
            "Merrie",
            "Merry",
            "Mira",
            "Moira",
            "Mora",
            "Moria",
            "Moyra",
            "Muire",
            "Myra",
            "Myrah",
        ],
    ),
    ("Paris", ["Pearcy", "Perris", "Piercy", "Pierz", "Pryse"]),
    (
        "Peter",
        [
            "Peadar",
            "Peder",
            "Pedro",
            "Peter",
            "Petr",
            "Peyter",
            "Pieter",
            "Pietro",
            "Piotr",
        ],
    ),
    ("Ray", ["Ray", "Rey", "Roi", "Roy", "Ruy"]),
    (
        "Susan",
        [
            "Siusan",
            "Sosanna",
            "Susan",
            "Susana",
            "Susann",
            "Susanna",
            "Susannah",
            "Susanne",
            "Suzann",
            "Suzanna",
            "Suzanne",
            "Zuzana",
        ],
    ),
    (
        "White",
        [
            "Wade",
            "Wait",
            "Waite",
            "Wat",
            "Whit",
            "Wiatt",
            "Wit",
            "Wittie",
            "Witty",
            "Wood",
            "Woodie",
            "Woody",
        ],
    ),
    ("Wright", ["Rota", "Rudd", "Ryde"]),
    (
        "Xalan",
        [
            "Celene",
            "Celina",
            "Celine",
            "Selena",
            "Selene",
            "Selina",
            "Seline",
            "Suellen",
            "Xylina",
        ],
    ),
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
    Build ``HasMetaphoneName([target_name])``, run its real
    ``prepare()``/``apply_to_one()`` lifecycle, and return whether it
    matches a person with ``surname``.
    """
    rule = metaphonerule.HasMetaphoneName([target_name])
    rule.prepare(None, None)
    return rule.apply_to_one(None, _FakePerson(surname))


# ------------------------------------------------------------
#
# MetaphoneEncodeTest
#
# ------------------------------------------------------------
class MetaphoneEncodeTest(unittest.TestCase):
    """Tests for :func:`metaphonerule.encode` against the full Apache
    Commons Codec reference vector set."""

    def test_reference_vectors(self) -> None:
        """encode() must match every reference (input, code) pair."""
        for name, expected in REFERENCE_VECTORS:
            with self.subTest(name=name):
                self.assertEqual(metaphonerule.encode(name), {expected})

    def test_equivalence_groups(self) -> None:
        """Every name in each group must share the same Metaphone code."""
        for source, matches in EQUIVALENCE_GROUPS:
            all_names = [source] + matches
            codes = {name: metaphonerule.encode(name) for name in all_names}
            with self.subTest(group=source):
                self.assertEqual(
                    len({frozenset(c) for c in codes.values()}),
                    1,
                    f"not all names in the {source!r} group share a code: {codes}",
                )

    def test_empty_name_is_handled(self) -> None:
        """An empty name must not raise and returns an empty code."""
        self.assertEqual(metaphonerule.encode(""), {""})

    def test_smith_and_smyth_match(self) -> None:
        """
        Metaphone should agree with Soundex on Smith/Smyth, unlike
        NYSIIS - this is the actual reason for offering more than one
        Encoding system (see the module docstring).
        """
        self.assertEqual(metaphonerule.encode("Smith"), metaphonerule.encode("Smyth"))


# ------------------------------------------------------------
#
# HasMetaphoneNameTest
#
# ------------------------------------------------------------
class HasMetaphoneNameTest(unittest.TestCase):
    """Tests for :class:`metaphonerule.HasMetaphoneName`."""

    def test_matches_identical_surname(self) -> None:
        """A person with the exact target surname must match."""
        self.assertTrue(_apply("Boucher", "Boucher"))

    def test_matches_metaphone_variant(self) -> None:
        """
        A Metaphone-equivalent spelling must match, using a pair
        Metaphone genuinely groups (see EQUIVALENCE_GROUPS).
        """
        self.assertTrue(_apply("Gary", "Cory"))

    def test_does_not_match_unrelated_surname(self) -> None:
        """A clearly unrelated surname must not match."""
        self.assertFalse(_apply("Boucher", "Anderson"))

    def test_empty_target_matches_nothing(self) -> None:
        """An empty/unset target name must not match every empty-coded person."""
        self.assertFalse(_apply("", "Anderson"))

    def test_name_and_category(self) -> None:
        """The rule's own display metadata should be set."""
        self.assertEqual(
            metaphonerule.HasMetaphoneName.name,
            "Metaphone match of People with the <n>",
        )
        self.assertEqual(metaphonerule.HasMetaphoneName.category, "General filters")

    def test_apply_matches_apply_to_one(self) -> None:
        """
        Gramps 5.2 calls a rule's `apply()` method; Gramps 6.0+ calls
        `apply_to_one()` instead (confirmed directly against both
        branches' real source, not assumed) - both must agree, since
        this one rule class has to work correctly on either.
        """
        rule = metaphonerule.HasMetaphoneName(["Boucher"])
        rule.prepare(None, None)
        person = _FakePerson("Boucher")
        self.assertEqual(rule.apply(None, person), rule.apply_to_one(None, person))
        self.assertTrue(rule.apply(None, person))


# ------------------------------------------------------------
#
# MetaphoneContractTest
#
# ------------------------------------------------------------
class MetaphoneContractTest(unittest.TestCase):
    """Confirms the module declares the encoder contract correctly."""

    def test_algorithm_id(self) -> None:
        """ALGORITHM_ID must be the stable registry key for this encoder."""
        self.assertEqual(metaphonerule.ALGORITHM_ID, "metaphone")

    def test_algorithm_label_is_a_string(self) -> None:
        """ALGORITHM_LABEL must be a display-ready string."""
        self.assertIsInstance(metaphonerule.ALGORITHM_LABEL, str)
        self.assertTrue(metaphonerule.ALGORITHM_LABEL)

    def test_encode_is_callable(self) -> None:
        """encode must be callable, per the encoder contract."""
        self.assertTrue(callable(metaphonerule.encode))


if __name__ == "__main__":
    unittest.main()
