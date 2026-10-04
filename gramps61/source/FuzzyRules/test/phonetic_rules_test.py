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
Unit tests for the four phonetic filter rules (Soundex, NYSIIS, MRA,
Metaphone): the "Match in:" option, one-argument compatibility, and the
fallback when phonetic_name_parts.py is missing.
"""

# ------------------------
# Python modules
# ------------------------
import importlib
import sys
import unittest

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.soundex import soundex

# ------------------------
# Gramps specific
# ------------------------
import matchratingrule
import metaphonerule
import nysiisrule
import soundexrule

from .phonetic_name_parts_test import make_person

RULE_MODULES = (
    (soundexrule, "HasSoundexNames"),
    (nysiisrule, "HasNysiisName"),
    (matchratingrule, "HasMatchRatingName"),
    (metaphonerule, "HasMetaphoneName"),
)


def matches(rule_class: type, args: list[str], person: object) -> bool:
    """
    Prepare a rule with ``args`` and apply it to ``person``.

    :param rule_class: The rule class.
    :param args: The rule arguments.
    :param person: The Person to test.
    :returns: True on a match.
    """
    rule = rule_class(list(args))
    rule.requestprepare(None, None)
    return rule.apply_to_one(None, person)


# ------------------------------------------------------------
#
# RuleOptionsTest
#
# ------------------------------------------------------------
class RuleOptionsTest(unittest.TestCase):
    """The same behaviour is expected of every phonetic rule."""

    def setUp(self) -> None:
        """Build the test people."""
        self.john = make_person("John Henry", ["Smith"])
        self.mary = make_person("Mary", ["Johnson"])
        self.ann = make_person("Ann", ["Thompson", "Johnson"])
        self.paul = make_person("Paul", ["Smith"], alternate_surname="Johnson")
        self.henry = make_person("Henry John", ["Doe"])

    def test_default_surname(self) -> None:
        """By default, "Johnson" finds preferred surnames, not the Johns."""
        for module, class_name in RULE_MODULES:
            rule_class = getattr(module, class_name)
            with self.subTest(rule=class_name):
                self.assertTrue(matches(rule_class, ["Johnson"], self.mary))
                self.assertTrue(matches(rule_class, ["Johnson"], self.ann))
                self.assertFalse(matches(rule_class, ["Johnson"], self.paul))
                self.assertFalse(matches(rule_class, ["Johnson"], self.john))

    def test_default_call_falls_back_to_first_given(self) -> None:
        """By default, "John" finds a blank-Call John via his given name."""
        for module, class_name in RULE_MODULES:
            rule_class = getattr(module, class_name)
            with self.subTest(rule=class_name):
                self.assertTrue(matches(rule_class, ["John"], self.john))
                self.assertFalse(matches(rule_class, ["John"], self.henry))

    def test_given_option(self) -> None:
        """With Given ticked, any given-name word matches."""
        for module, class_name in RULE_MODULES:
            rule_class = getattr(module, class_name)
            with self.subTest(rule=class_name):
                self.assertTrue(matches(rule_class, ["John", "given"], self.henry))

    def test_alternates_option(self) -> None:
        """With Alternatives ticked, alternate surnames match."""
        for module, class_name in RULE_MODULES:
            rule_class = getattr(module, class_name)
            args = ["Johnson", "surname,primary,alternate"]
            with self.subTest(rule=class_name):
                self.assertTrue(matches(rule_class, args, self.paul))

    def test_one_argument_is_padded(self) -> None:
        """A one-argument rule stores the default option."""
        for module, class_name in RULE_MODULES:
            rule = getattr(module, class_name)(["Smith"])
            with self.subTest(rule=class_name):
                self.assertEqual(rule.list, ["Smith", "call,surname,primary"])

    def test_two_labels(self) -> None:
        """Each rule offers the Name and Match in options."""
        for module, class_name in RULE_MODULES:
            with self.subTest(rule=class_name):
                self.assertEqual(len(getattr(module, class_name).labels), 2)


# ------------------------------------------------------------
#
# SoundexRuleTest
#
# ------------------------------------------------------------
class SoundexRuleTest(unittest.TestCase):
    """Tests specific to soundexrule.py."""

    def test_encode_matches_gramps(self) -> None:
        """encode() uses Gramps' own Soundex code."""
        for name in ("Smith", "Smyth", "Baker", "Boucher", "O'Brien", ""):
            with self.subTest(name=name):
                self.assertEqual(soundexrule.encode(name), {soundex(name)})

    def test_class_name_does_not_shadow_builtin(self) -> None:
        """The rule class is not named like Gramps' HasSoundexName."""
        self.assertNotEqual(soundexrule.HasSoundexNames.__name__, "HasSoundexName")


# ------------------------------------------------------------
#
# MissingSharedModuleTest
#
# ------------------------------------------------------------
class MissingSharedModuleTest(unittest.TestCase):
    """Rules still load and match surnames without phonetic_name_parts."""

    def test_fallback(self) -> None:
        """Import each rule with the shared module made unimportable."""
        saved = {name: sys.modules.get(name) for name in ("phonetic_name_parts",)}
        try:
            sys.modules["phonetic_name_parts"] = None  # type: ignore[assignment]
            for module, class_name in RULE_MODULES:
                with self.subTest(rule=class_name):
                    with self.assertLogs(module.__name__, level="WARNING"):
                        reloaded = importlib.reload(module)
                    rule_class = getattr(reloaded, class_name)
                    self.assertEqual(len(rule_class.labels), 1)
                    ann = make_person("Ann", ["Thompson", "Johnson"])
                    self.assertTrue(matches(rule_class, ["Johnson"], ann))
                    john = make_person("John Henry", ["Smith"])
                    self.assertFalse(matches(rule_class, ["John"], john))
        finally:
            for name, value in saved.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
            for module, _class_name in RULE_MODULES:
                importlib.reload(module)


if __name__ == "__main__":
    unittest.main()
