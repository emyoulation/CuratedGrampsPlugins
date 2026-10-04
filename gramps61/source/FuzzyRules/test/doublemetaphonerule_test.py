"""
Tests for doublemetaphonerule.py: the encode() function against the
reference implementation's own documented behavior (including its
primary/secondary branching), and the HasDoubleMetaphoneNames rule's
set_list()/prepare()/apply_to_one()/apply() contract.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test._fakes import FakeName, FakePerson, install_gramps_stand_ins

install_gramps_stand_ins()

import doublemetaphonerule  # noqa: E402


class DoubleMetaphoneEncodeTest(unittest.TestCase):
    """encode()/_double_metaphone_raw() against the ported reference
    implementation's own doctests and README example."""

    def test_aubrey(self):
        self.assertEqual(doublemetaphonerule._double_metaphone_raw("aubrey"), ("APR", ""))

    def test_richard_has_a_primary_and_secondary_code(self):
        self.assertEqual(
            doublemetaphonerule._double_metaphone_raw("richard"), ("RXRT", "RKRT")
        )

    def test_katherine_and_catherine_are_identical(self):
        self.assertEqual(
            doublemetaphonerule._double_metaphone_raw("katherine"),
            doublemetaphonerule._double_metaphone_raw("catherine"),
        )

    def test_smith_and_schmidt_share_a_code(self):
        # The example the algorithm is named for: different primaries,
        # but a shared code all the same - this is exactly why encode()
        # returns a set rather than one string.
        self.assertEqual(doublemetaphonerule.encode("Smith"), {"SM0", "XMT"})
        self.assertEqual(doublemetaphonerule.encode("Schmidt"), {"XMT", "SMT"})
        self.assertEqual(
            doublemetaphonerule.encode("Smith") & doublemetaphonerule.encode("Schmidt"),
            {"XMT"},
        )

    def test_word_with_no_sound_left_codes_as_empty(self):
        self.assertEqual(doublemetaphonerule.encode(""), {""})
        self.assertEqual(doublemetaphonerule.encode("H"), {""})

    def test_encode_never_raises_on_odd_input(self):
        for name in (None, "123", "O'Brien", "-", "a" * 50):
            with self.subTest(name=name):
                codes = doublemetaphonerule.encode(name)
                self.assertIsInstance(codes, set)


class DoubleMetaphoneAlgorithmContractTest(unittest.TestCase):
    def test_algorithm_id_and_label(self):
        self.assertEqual(doublemetaphonerule.ALGORITHM_ID, "double_metaphone")
        self.assertTrue(doublemetaphonerule.ALGORITHM_LABEL)

    def test_encode_is_callable(self):
        self.assertTrue(callable(doublemetaphonerule.encode))


class HasDoubleMetaphoneNamesTest(unittest.TestCase):
    def setUp(self):
        # Miller/Jack/Jonathan/Meyer don't collide under Double
        # Metaphone (checked before writing these tests), so a match
        # below is never an accidental phonetic coincidence.
        primary = FakeName(surname="Miller", given="Jonathan", call="Jack")
        alternate = FakeName(surname="Meyer")
        self.person = FakePerson(primary, alternate_names=[alternate])

    def test_matches_surname_spelling_variant_by_default(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Millar"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_apply_matches_apply_to_one(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Millar"])
        rule.prepare(None, None)
        self.assertEqual(rule.apply(None, self.person), rule.apply_to_one(None, self.person))
        self.assertTrue(rule.apply(None, self.person))

    def test_matches_via_secondary_code_alone(self):
        # "Catherine" and "Katherine" share both their primary and
        # secondary codes - a person recorded as one should be found by
        # a search for the other via either code.
        primary = FakeName(surname="Catherine")
        person = FakePerson(primary)
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Katherine"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, person))

    def test_given_name_not_matched_by_default(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Jonathan"])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_given_name_matched_once_given_is_ticked(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Jonathan", "given,primary"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_alternate_surname_not_matched_by_default(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Meyer"])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_alternate_surname_matched_once_alternatives_is_ticked(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Meyer", "surname,alternate"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_one_argument_filter_gets_the_default_match_in(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Millar"])
        self.assertEqual(len(rule.list), 2)

    def test_no_name_given_matches_nobody(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames([""])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_prepare_is_optional_before_apply(self):
        rule = doublemetaphonerule.HasDoubleMetaphoneNames(["Millar"])
        self.assertTrue(rule.apply_to_one(None, self.person))


if __name__ == "__main__":
    unittest.main()
