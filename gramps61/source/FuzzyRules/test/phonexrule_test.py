"""
Tests for phonexrule.py: the encode() function against known Phonex
behavior, and the HasPhonexNames rule's set_list()/prepare()/
apply_to_one()/apply() contract.
"""

import sys
import unittest
from pathlib import Path

# Bare, non-package-relative import of the addon root - the same
# pattern FuzzyMatchingGramplet.py itself needs, and for the same
# reason (see FuzzyDev.md's "Running the tests" section).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from test._fakes import FakeName, FakePerson, install_gramps_stand_ins

install_gramps_stand_ins()

import phonexrule  # noqa: E402  (must follow the stand-in install above)


class PhonexEncodeTest(unittest.TestCase):
    """encode()/_phonex_raw() against known Phonex behavior."""

    def test_spelling_variants_share_a_code(self):
        self.assertEqual(phonexrule.encode("Smith"), phonexrule.encode("Smyth"))
        self.assertEqual(phonexrule.encode("Miller"), phonexrule.encode("Millar"))

    def test_leading_kn_folds_like_n(self):
        # The whole point of Phonex over plain Soundex: "Kn-" and "Wr-"
        # fold onto "N-"/"R-" instead of coding the silent letter.
        self.assertEqual(phonexrule.encode("Knight"), {"N230"})

    def test_leading_wr_folds_like_r(self):
        self.assertEqual(phonexrule.encode("Wright"), {"R230"})

    def test_r_l_vowel_adjacency_rule(self):
        # Hansen/Anson: same underlying letters coded differently
        # depending on what follows R/L/N - see phonexrule.py's own
        # docstring for the rule this exercises.
        self.assertEqual(phonexrule.encode("Hansen"), phonexrule.encode("Anson"))

    def test_word_that_vanishes_entirely_codes_as_empty(self):
        # A bare "H" is dropped by the leading-H rule and leaves
        # nothing behind - this must not raise, and must not silently
        # collide with a real code.
        self.assertEqual(phonexrule.encode("H"), {""})
        self.assertEqual(phonexrule.encode(""), {""})

    def test_encode_never_raises_on_odd_input(self):
        for name in (None, "123", "O'Brien", "-", "a" * 50):
            with self.subTest(name=name):
                codes = phonexrule.encode(name)
                self.assertIsInstance(codes, set)


class PhonexAlgorithmContractTest(unittest.TestCase):
    """The module-level contract phonetic_codes.py's discovery relies
    on - see phonetic_codes._resolve_discovered_entries."""

    def test_algorithm_id_and_label(self):
        self.assertEqual(phonexrule.ALGORITHM_ID, "phonex")
        self.assertTrue(phonexrule.ALGORITHM_LABEL)

    def test_encode_is_callable(self):
        self.assertTrue(callable(phonexrule.encode))


class HasPhonexNamesTest(unittest.TestCase):
    """The rule itself: set_list()/prepare()/apply_to_one()/apply()."""

    def setUp(self):
        # A person findable by their surname or call name by default,
        # by their given name only once "Given" is ticked, and by
        # their alternate surname only once "Alternatives" is ticked.
        # None of Miller/Jack/Jonathan/Meyer collide under Phonex, so a
        # match below is never an accidental phonetic coincidence.
        primary = FakeName(surname="Miller", given="Jonathan", call="Jack")
        alternate = FakeName(surname="Meyer")
        self.person = FakePerson(primary, alternate_names=[alternate])

    def test_matches_surname_spelling_variant_by_default(self):
        rule = phonexrule.HasPhonexNames(["Millar"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_apply_matches_apply_to_one(self):
        # Gramps 5.2 calls apply(), 6.0+ calls apply_to_one() - see
        # FuzzyDev.md for why both must exist and agree.
        rule = phonexrule.HasPhonexNames(["Millar"])
        rule.prepare(None, None)
        self.assertEqual(rule.apply(None, self.person), rule.apply_to_one(None, self.person))
        self.assertTrue(rule.apply(None, self.person))

    def test_given_name_not_matched_by_default(self):
        rule = phonexrule.HasPhonexNames(["Jonathan"])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_given_name_matched_once_given_is_ticked(self):
        rule = phonexrule.HasPhonexNames(["Jonathan", "given,primary"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_alternate_surname_not_matched_by_default(self):
        rule = phonexrule.HasPhonexNames(["Meyer"])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_alternate_surname_matched_once_alternatives_is_ticked(self):
        rule = phonexrule.HasPhonexNames(["Meyer", "surname,alternate"])
        rule.prepare(None, None)
        self.assertTrue(rule.apply_to_one(None, self.person))

    def test_one_argument_filter_gets_the_default_match_in(self):
        # Older saved filters (or a caller passing only the name) get
        # padded to the default "Match in" value - see pad_args().
        rule = phonexrule.HasPhonexNames(["Millar"])
        self.assertEqual(len(rule.list), 2)

    def test_no_name_given_matches_nobody(self):
        rule = phonexrule.HasPhonexNames([""])
        rule.prepare(None, None)
        self.assertFalse(rule.apply_to_one(None, self.person))

    def test_prepare_is_optional_before_apply(self):
        # apply_to_one() must self-prepare() if the caller skipped it -
        # some code paths in Gramps apply a rule without calling
        # prepare() first.
        rule = phonexrule.HasPhonexNames(["Millar"])
        self.assertTrue(rule.apply_to_one(None, self.person))


if __name__ == "__main__":
    unittest.main()
