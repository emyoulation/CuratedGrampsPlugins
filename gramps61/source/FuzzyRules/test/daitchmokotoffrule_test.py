"""
Tests for daitchmokotoffrule.py: the encode() function against
reference codes published independently of the source this was ported
from (see the module docstring), and the HasDaitchMokotoffNames rule's
set_list()/prepare()/apply_to_one()/apply() contract.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test._fakes import FakeName, FakePerson, install_gramps_stand_ins

install_gramps_stand_ins()

import daitchmokotoffrule  # noqa: E402


class DaitchMokotoffEncodeTest(unittest.TestCase):
    """encode() against independently published D-M Soundex reference
    vectors - actian's docs, avotaynu.com's own worked examples, and
    Apache Commons Codec's javadoc example - not just this port's own
    output."""

    def test_peters_is_two_codes(self):
        self.assertEqual(daitchmokotoffrule.encode("Peters"), {"739400", "734000"})

    def test_peterson_is_two_codes(self):
        self.assertEqual(daitchmokotoffrule.encode("Peterson"), {"739460", "734600"})

    def test_moskowitz_and_moskovitz_share_a_code(self):
        # The original motivating example for the whole system (see the
        # module docstring): plain U.S. Soundex treats these
        # differently, D-M Soundex was built specifically to fix that.
        self.assertEqual(daitchmokotoffrule.encode("Moskowitz"), {"645740"})
        self.assertEqual(daitchmokotoffrule.encode("Moskovitz"), {"645740"})

    def test_jackson_is_four_codes(self):
        self.assertEqual(
            daitchmokotoffrule.encode("Jackson"),
            {"154600", "454600", "145460", "445460"},
        )

    def test_auerbach_is_two_codes(self):
        self.assertEqual(daitchmokotoffrule.encode("Auerbach"), {"097400", "097500"})

    def test_berlin_zero_pads_to_six_digits(self):
        self.assertEqual(daitchmokotoffrule.encode("Berlin"), {"798600"})

    def test_word_with_nothing_to_encode_is_empty(self):
        self.assertEqual(daitchmokotoffrule.encode(""), {""})

    def test_encode_never_raises_on_odd_input(self):
        for name in (None, "123", "O'Brien", "-", "a" * 50):
            with self.subTest(name=name):
                codes = daitchmokotoffrule.encode(name)
                self.assertIsInstance(codes, set)


class DaitchMokotoffAlgorithmContractTest(unittest.TestCase):
    def test_algorithm_id_and_label(self):
        self.assertEqual(daitchmokotoffrule.ALGORITHM_ID, "daitch_mokotoff")
        self.assertTrue(daitchmokotoffrule.ALGORITHM_LABEL)

    def test_encode_is_callable(self):
        self.assertTrue(callable(daitchmokotoffrule.encode))


class HasDaitchMokotoffNamesTest(unittest.TestCase):
    def setUp(self):
        # Miller/Jack/Jonathan/Meyer don't collide under D-M Soundex
        # (checked before writing these tests), so a match below is
        # never an accidental phonetic coincidence.
        primary = FakeName(surname="Miller", given="Jonathan", call="Jack")
        alternate = FakeName(surname="Meyer")
        self.person = FakePerson(primary, alternate_names=[alternate])

    def test_matches_surname_by_default(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Miller"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_apply_matches_apply_to_one(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Miller"])
        rule.prepare(None, None)
        self.assertEqual(rule.apply(None, self.person), rule.apply_to_one(None, self.person))
        self.assertTrue(rule.apply(None, self.person))

    def test_matches_via_any_one_of_several_branches(self):
        # A person recorded as "Jackson" should be found by a search
        # for "Jaxen" (or vice versa) via whichever of the four codes
        # they happen to share, not just the first one.
        primary = FakeName(surname="Jackson")
        person = FakePerson(primary)
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Jackson"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, person))

    def test_given_name_not_matched_by_default(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Jonathan"])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_given_name_matched_once_given_is_ticked(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Jonathan", "given,primary"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_alternate_surname_not_matched_by_default(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Meyer"])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_alternate_surname_matched_once_alternatives_is_ticked(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Meyer", "surname,alternate"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_one_argument_filter_gets_the_default_match_in(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Miller"])
        self.assertEqual(len(rule.list), 2)

    def test_no_name_given_matches_nobody(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames([""])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_prepare_is_optional_before_apply(self):
        rule = daitchmokotoffrule.HasDaitchMokotoffNames(["Miller"])
        self.assertTrue(rule.apply_to_one(None, self.person))


if __name__ == "__main__":
    unittest.main()
