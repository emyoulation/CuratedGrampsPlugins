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
Unit tests for :mod:`phonetic_codes`.

Tests for any one encoding system's actual algorithm (e.g. NYSIIS)
live next to that system's own rule module, in ``test/``, not here -
see ``test/nysiisrule_test.py``/``test/matchratingrule_test.py``/
``test/metaphonerule_test.py``. This
file covers the registry/discovery machinery in ``phonetic_codes.py``
itself: the hardcoded Soundex entry, contract validation for
discovered modules, and the id-prefix-based filtering that recognizes
which registered Gramps ``RULE`` plugins are this gramplet's encoding
systems, regardless of which addon they are physically packaged in.

Real Gramps ``RULE`` plugins are only found by
``phonetic_codes._discover_addon_rule_modules`` if Gramps' own
:class:`~gramps.gen.plug.PluginRegister` already knows about them,
which normally happens as part of Gramps' own startup scan - not
something a bare ``unittest`` run triggers on its own.
:func:`_ensure_addon_rules_are_registered` below does that scan
manually, once, against this addon's own directory, so
``phonetic_codes.ALGORITHMS`` reflects the real, full discovery (NYSIIS
and Match Rating Approach and Metaphone included) exactly as it would inside a
running Gramps, rather than only ever seeing the hardcoded Soundex
entry.
"""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import types
import unittest

# ------------------------
# Gramps specific
# ------------------------
# See the note in test/nysiisrule_test.py: this addon is not an
# installed package, so "phonetic_codes" cannot be reached with a
# package-relative import here.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from gramps.gen.plug import PluginRegister
from gramps.gen.plug._pluginreg import RULE


def _ensure_addon_rules_are_registered() -> None:
    """
    Trigger Gramps' own plugin-registration scan against this addon's
    own directory, so its ``RULE``-type ``.gpr.py`` registrations
    (``nysiisrule.gpr.py``, ``matchratingrule.gpr.py``,
    ``metaphonerule.gpr.py``) are present in
    :class:`gramps.gen.plug.PluginRegister` before ``phonetic_codes``
    is imported - matching what Gramps' own startup does, which a bare
    ``unittest`` run does not do on its own. Safe to call more than
    once: :meth:`PluginRegister.scan_dir` does not re-add a plugin id
    it has already seen.
    """
    addon_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    registry = PluginRegister.get_instance()
    registry.scan_dir(addon_dir, os.listdir(addon_dir))


_ensure_addon_rules_are_registered()

import phonetic_codes


class _FakePluginData:
    """Minimal stand-in for a Gramps PluginData, RULE-relevant fields only."""

    def __init__(self, plugin_id, mod_name, ruleclass, namespace="Person"):
        self.id = plugin_id
        self.mod_name = mod_name
        self.ruleclass = ruleclass
        self.namespace = namespace


class _FakeRegistry:
    """Minimal stand-in for PluginRegister, just enough for type_plugins(RULE)."""

    def __init__(self, plugins):
        self._plugins = plugins

    def type_plugins(self, ptype):
        """Return the fake plugin list, matching PluginRegister's own signature."""
        assert ptype == RULE
        return self._plugins


# ------------------------------------------------------------
#
# AlgorithmRegistryTest
#
# ------------------------------------------------------------
class AlgorithmRegistryTest(unittest.TestCase):
    """
    Tests for the real, fully-loaded registries, with this addon's own
    Gramps RULE plugins genuinely scanned and discovered (see
    ``_ensure_addon_rules_are_registered`` above) - not mocked.
    """

    def test_soundex_was_hardcoded(self) -> None:
        """The hardcoded Soundex entry must always be present."""
        self.assertIn("soundex", phonetic_codes.ALGORITHMS)

    def test_soundex_uses_the_real_builtin_rule(self) -> None:
        """Soundex's filter rule must be Gramps' own HasSoundexName."""
        from gramps.gen.filters.rules.person import HasSoundexName

        self.assertIs(phonetic_codes.ALGORITHM_FILTER_RULES["soundex"], HasSoundexName)

    def test_nysiis_and_match_rating_were_discovered(self) -> None:
        """
        This addon's own RULE plugins must be found via Gramps' plugin
        registry, given the scan in _ensure_addon_rules_are_registered.
        """
        self.assertIn("nysiis", phonetic_codes.ALGORITHMS)
        self.assertIn("match_rating", phonetic_codes.ALGORITHMS)
        self.assertIn("metaphone", phonetic_codes.ALGORITHMS)

    def test_default_algorithm_is_registered(self) -> None:
        """The default algorithm id must exist in the registry."""
        self.assertIn(phonetic_codes.DEFAULT_ALGORITHM, phonetic_codes.ALGORITHMS)

    def test_default_algorithm_is_soundex(self) -> None:
        """Soundex should be the default whenever it is present."""
        self.assertEqual(phonetic_codes.DEFAULT_ALGORITHM, "soundex")

    def test_every_algorithm_has_a_label(self) -> None:
        """Every registered algorithm must have a matching display label."""
        self.assertEqual(
            set(phonetic_codes.ALGORITHMS), set(phonetic_codes.ALGORITHM_LABELS)
        )

    def test_registered_algorithms_are_callable(self) -> None:
        """Every registered algorithm must accept a name and return a set."""
        for name, func in phonetic_codes.ALGORITHMS.items():
            with self.subTest(algorithm=name):
                result = func("Testname")
                self.assertIsInstance(result, set)
                self.assertTrue(result)

    def test_every_algorithm_has_a_description_entry(self) -> None:
        """
        Every registered algorithm must have a (possibly empty) entry
        in ALGORITHM_DESCRIPTIONS - the key set matches ALGORITHMS
        even if a module provided no description text.
        """
        self.assertEqual(
            set(phonetic_codes.ALGORITHMS), set(phonetic_codes.ALGORITHM_DESCRIPTIONS)
        )

    def test_every_bundled_algorithm_has_a_filter_rule(self) -> None:
        """
        Every encoder shipped with this addon should have a working
        filter rule - this is what makes the "Define filter"
        double-click meaningful for every Encoding system a user can
        actually select, not just some of them.
        """
        for algorithm_id, rule_class in phonetic_codes.ALGORITHM_FILTER_RULES.items():
            with self.subTest(algorithm=algorithm_id):
                self.assertIsNotNone(
                    rule_class,
                    f"{algorithm_id!r} has no filter rule class resolved",
                )


# ------------------------------------------------------------
#
# RegisterEncodersTest
#
# ------------------------------------------------------------
class RegisterEncodersTest(unittest.TestCase):
    """
    Tests for _register_encoders in isolation, using fake
    (algorithm_id, encode, label, description, rule_class) entries -
    this is what makes it safe for one broken or half-finished rule
    module to exist in this addon's folder without taking every other
    algorithm down with it.
    """

    def test_well_formed_entry_is_registered(self) -> None:
        """A well-formed entry should be registered as-is."""
        entry = ("dummy", lambda n: {"X"}, "Dummy", "A dummy algorithm.", object)
        algorithms, labels, descriptions, filter_rules = (
            phonetic_codes._register_encoders([entry])
        )
        self.assertEqual(set(algorithms), {"dummy"})
        self.assertEqual(labels["dummy"], "Dummy")
        self.assertEqual(algorithms["dummy"]("anything"), {"X"})
        self.assertEqual(descriptions["dummy"], "A dummy algorithm.")
        self.assertIs(filter_rules["dummy"], object)

    def test_duplicate_algorithm_id_keeps_first(self) -> None:
        """Two entries claiming the same id must not raise; the first wins."""
        first = ("dupe", lambda n: {"1"}, "First", "", None)
        second = ("dupe", lambda n: {"2"}, "Second", "", None)
        algorithms, labels, _descriptions, _filter_rules = (
            phonetic_codes._register_encoders([first, second])
        )
        self.assertEqual(labels["dupe"], "First")
        self.assertEqual(algorithms["dupe"]("anything"), {"1"})


# ------------------------------------------------------------
#
# ResolveDiscoveredEntriesTest
#
# ------------------------------------------------------------
class ResolveDiscoveredEntriesTest(unittest.TestCase):
    """
    Tests for the contract-validation logic applied to discovered
    modules, using fake in-memory modules so a broken module doesn't
    need a real Gramps plugin registration to test against.
    """

    def _resolve(self, modules_and_ruleclasses):
        """
        Call ``_resolve_discovered_entries`` with
        ``_discover_addon_rule_modules`` patched to return the given
        fake ``(module, ruleclass_name, namespace)`` triples, restoring
        the real function afterward.
        """
        original = phonetic_codes._discover_addon_rule_modules
        phonetic_codes._discover_addon_rule_modules = lambda: modules_and_ruleclasses
        try:
            return phonetic_codes._resolve_discovered_entries()
        finally:
            phonetic_codes._discover_addon_rule_modules = original

    def _make_module(
        self, algorithm_id, algorithm_label="Label", encode=None, description=None
    ):
        module = types.ModuleType(f"_fake_{id(object())}")
        if algorithm_id is not None:
            module.ALGORITHM_ID = algorithm_id
        module.ALGORITHM_LABEL = algorithm_label
        if encode is not None:
            module.encode = encode
        if description is not None:
            module.ALGORITHM_DESCRIPTION = description
        return module

    def test_well_formed_module_resolves(self) -> None:
        """A module satisfying the contract should resolve to an entry."""

        class FakeRule:
            """A stand-in filter rule class, never actually applied."""

        module = self._make_module("dummy", "Dummy", lambda n: {"X"}, "A dummy.")
        module.FakeRuleClass = FakeRule
        entries = self._resolve([(module, "FakeRuleClass", "Person")])
        self.assertEqual(len(entries), 1)
        algorithm_id, encode, label, description, rule_class = entries[0]
        self.assertEqual(algorithm_id, "dummy")
        self.assertEqual(encode("x"), {"X"})
        self.assertEqual(label, "Dummy")
        self.assertEqual(description, "A dummy.")
        self.assertIs(rule_class, FakeRule)

    def test_missing_description_defaults_to_empty_string(self) -> None:
        """ALGORITHM_DESCRIPTION is optional; absence should not fail."""
        module = self._make_module("dummy", "Dummy", lambda n: {"X"})
        module.FakeRuleClass = object
        entries = self._resolve([(module, "FakeRuleClass", "Person")])
        self.assertEqual(entries[0][3], "")

    def test_unresolvable_ruleclass_becomes_none(self) -> None:
        """
        If the module doesn't actually define the class Gramps' own
        .gpr.py said it would, the rule_class should be None (handled
        gracefully by the gramplet), not raise.
        """
        module = self._make_module("dummy", "Dummy", lambda n: {"X"})
        entries = self._resolve([(module, "NoSuchClass", "Person")])
        self.assertIsNone(entries[0][4])

    def test_module_missing_algorithm_id_is_skipped(self) -> None:
        """A module missing ALGORITHM_ID must be skipped, not raise."""
        module = self._make_module(None, "Dummy", lambda n: {"X"})
        entries = self._resolve([(module, "Whatever", "Person")])
        self.assertEqual(entries, [])

    def test_module_missing_encode_is_skipped(self) -> None:
        """A module missing encode entirely must be skipped, not raise."""
        module = self._make_module("dummy", "Dummy", encode=None)
        entries = self._resolve([(module, "Whatever", "Person")])
        self.assertEqual(entries, [])

    def test_module_with_non_callable_encode_is_skipped(self) -> None:
        """A module whose encode isn't callable must be skipped, not raise."""
        module = self._make_module("dummy", "Dummy", encode="not callable")
        entries = self._resolve([(module, "Whatever", "Person")])
        self.assertEqual(entries, [])

    def test_one_broken_module_does_not_affect_others(self) -> None:
        """A broken module among good ones should not prevent the rest."""
        broken = self._make_module(None, "Broken")
        good = self._make_module("good", "Good", lambda n: {"G"})
        good.GoodRule = object
        entries = self._resolve(
            [(broken, "Whatever", "Person"), (good, "GoodRule", "Person")]
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0][0], "good")


# ------------------------------------------------------------
#
# DiscoverAddonRuleModulesTest
#
# ------------------------------------------------------------
class DiscoverAddonRuleModulesTest(unittest.TestCase):
    """
    Tests for the id-prefix-based filtering itself, using a fake
    PluginRegister so this doesn't depend on what is or isn't actually
    registered in the real one at test time.
    """

    def _discover(self, plugins):
        """
        Call ``_discover_addon_rule_modules`` with
        ``PluginRegister.get_instance`` patched to return a fake
        registry containing ``plugins``, restoring the real one
        afterward.
        """
        original = phonetic_codes.PluginRegister.get_instance
        phonetic_codes.PluginRegister.get_instance = staticmethod(
            lambda: _FakeRegistry(plugins)
        )
        try:
            return phonetic_codes._discover_addon_rule_modules()
        finally:
            phonetic_codes.PluginRegister.get_instance = original

    def test_plugin_without_the_prefix_is_ignored(self) -> None:
        """
        A RULE plugin whose id does not start with _ENCODER_ID_PREFIX
        must be skipped, regardless of where it happens to be
        registered from - this is what lets an unrelated third-party
        addon's own Person rules coexist without being mistaken for
        one of this gramplet's encoding systems.
        """
        plugin = _FakePluginData("SomeOtherRule", "os", "path")
        self.assertEqual(self._discover([plugin]), [])

    def test_plugin_with_the_prefix_is_imported(self) -> None:
        """
        A RULE plugin whose id starts with _ENCODER_ID_PREFIX must
        resolve, regardless of which module it names - proving
        identity here is about the id, not about shared location with
        phonetic_codes.py itself.
        """
        plugin = _FakePluginData(
            phonetic_codes._ENCODER_ID_PREFIX + "nysiis",
            "nysiisrule",
            "HasNysiisName",
        )
        results = self._discover([plugin])
        self.assertEqual(len(results), 1)
        module, ruleclass_name, namespace = results[0]
        self.assertEqual(module.__name__, "nysiisrule")
        self.assertEqual(ruleclass_name, "HasNysiisName")
        self.assertEqual(namespace, "Person")

    def test_broken_module_import_is_skipped(self) -> None:
        """A plugin whose module fails to import must be skipped, not raise."""
        plugin = _FakePluginData(
            phonetic_codes._ENCODER_ID_PREFIX + "broken",
            "no_such_module_exists_for_this_test",
            "Whatever",
        )
        self.assertEqual(self._discover([plugin]), [])

    def test_id_missing_entirely_does_not_raise(self) -> None:
        """A plugin with no id at all (None) must not crash the startswith check."""
        plugin = _FakePluginData(None, "os", "path")
        self.assertEqual(self._discover([plugin]), [])


# ------------------------------------------------------------
#
# ChooseDefaultTest
#
# ------------------------------------------------------------
class ChooseDefaultTest(unittest.TestCase):
    """Tests for :func:`phonetic_codes._choose_default`."""

    def test_prefers_soundex_when_present(self) -> None:
        """soundex should win if it was discovered."""
        algorithms = {"soundex": lambda n: set(), "zzz-other": lambda n: set()}
        self.assertEqual(phonetic_codes._choose_default(algorithms), "soundex")

    def test_falls_back_to_first_sorted_id(self) -> None:
        """Without soundex, the first id (sorted) should win."""
        algorithms = {"zebra": lambda n: set(), "alpha": lambda n: set()}
        self.assertEqual(phonetic_codes._choose_default(algorithms), "alpha")

    def test_none_when_nothing_registered(self) -> None:
        """With no encoders at all, there is no default to choose."""
        self.assertIsNone(phonetic_codes._choose_default({}))


if __name__ == "__main__":
    unittest.main()
