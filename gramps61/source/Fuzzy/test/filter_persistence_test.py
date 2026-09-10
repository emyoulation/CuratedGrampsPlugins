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
Regression test for a real, reported bug: a "Fuzzy match: ..." filter
built via the gramplet's own "Define filter" action worked immediately
after creation, but once saved and reloaded - which is what actually
happens the next time the Person View applies a saved custom filter -
silently matched every person in the tree instead of the handful that
actually shared a phonetic code.

Root cause, confirmed directly in the Gramps source rather than
guessed at: ``gramps.gen.filters._filterlist.FilterList.save`` writes
only the bare class name (``rule.__class__.__name__``) into the saved
XML, and ``gramps.gen.filters._filterparser.FilterParser`` reloads a
rule by trying to resolve that name as
``gramps.gen.filters.rules.<namespace>.<ClassName>`` - which only
works for a rule class that is actually an attribute of that module.
Gramps' own built-in rules (``HasSoundexName``) already are; a bare,
addon-provided rule module like this one's is not, unless something
makes it one - see ``phonetic_codes._make_rule_findable_via_import``.
Without that, the reload logs "Filter rule ... not found!", drops the
rule entirely, and an empty rule list is vacuously true for every
person (``all(())`` and equivalent "AND every rule in an empty list"
logic both evaluate to True), which is exactly the "matches the whole
tree" symptom reported.

None of the other tests in this addon would have caught this: they
call a rule's own ``prepare()``/``apply_to_one()`` directly, which
never exercises the save/reload machinery where the bug actually
lived. These tests build a real filter, save it to a real temporary
XML file with Gramps' own ``FilterList``, reload it in a *fresh*
``FilterList`` instance (so nothing from the original in-memory rule
object survives the round-trip), and apply it against real
``gramps.gen.lib.Person`` objects - the same path the Person View
actually uses, not a shortcut around it.
"""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import tempfile
import unittest

# ------------------------
# Gramps specific
# ------------------------
# This addon is not an installed package, so "phonetic_codes" and the
# individual rule modules cannot be reached with a package-relative
# import here - see the note at the top of FuzzyMatchingGramplet.py.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from gramps.gen.filters import GenericFilterFactory, FilterList
from gramps.gen.filters.rules.person import HasSoundexName
from gramps.gen.lib import Name, Person, Surname
from gramps.gen.plug import PluginRegister

import matchratingrule
import metaphonerule
import nysiisrule

# Trigger Gramps' own plugin-registration scan against this addon's
# own directory, exactly as its real startup would, so this addon's
# RULE-type .gpr.py registrations (and the namespace-injection they
# trigger via phonetic_codes) are in place before the tests run. Safe
# to call more than once - see test/phonetic_codes_test.py's own copy
# of this same pattern for why.
_ADDON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PluginRegister.get_instance().scan_dir(_ADDON_DIR, os.listdir(_ADDON_DIR))

import phonetic_codes  # noqa: E402  pylint: disable=wrong-import-position


def _make_person(handle: str, surname: str) -> Person:
    """
    Build a real, minimal :class:`gramps.gen.lib.Person` with just a
    primary name's surname set - enough for every rule in this addon,
    and for Gramps' own ``HasSoundexName``, to evaluate correctly.

    :param handle: A fake but unique handle for this person.
    :param surname: The surname to give them.
    :returns: The constructed Person.
    """
    person = Person()
    person.set_handle(handle)
    name = Name()
    surname_obj = Surname()
    surname_obj.set_surname(surname)
    name.set_surname_list([surname_obj])
    person.set_primary_name(name)
    return person


class _FakeDb:
    """Minimal stand-in for a Gramps database: person lookup only."""

    def __init__(self, people):
        self._people = {person.get_handle(): person for person in people}

    def get_person_from_handle(self, handle):
        """Return the fake person for this handle, or None."""
        return self._people.get(handle)

    def get_person_handles(self):
        """Return every fake handle."""
        return list(self._people.keys())


def _build_save_reload_apply(rule_class, target_name, db, tmp_path):
    """
    Build a one-rule Person filter, save it to ``tmp_path`` with
    Gramps' own :class:`FilterList`, reload it in a *fresh*
    ``FilterList`` instance, and apply the reloaded filter against
    ``db``.

    :param rule_class: The Rule subclass to build the filter from.
    :param target_name: The rule's ``<name>`` parameter.
    :param db: The (fake) database to apply the reloaded filter to.
    :param tmp_path: Where to write the intermediate XML.
    :returns: ``(reloaded_filter, matched_handles)``.
    """
    filter_class = GenericFilterFactory("Person")
    new_filter = filter_class()
    new_filter.set_name(f"Fuzzy match: {target_name} ({rule_class.__name__})")
    new_filter.add_rule(rule_class([target_name]))

    filterdb = FilterList(tmp_path)
    filterdb.add("Person", new_filter)
    filterdb.save()

    # A fresh FilterList/instance: nothing from the original in-memory
    # rule object can leak through and mask the bug.
    reloaded_db = FilterList(tmp_path)
    reloaded_db.load()
    reloaded_filter = reloaded_db.get_filters("Person")[0]

    return reloaded_filter, reloaded_filter.apply(db)


# ------------------------------------------------------------
#
# FilterSaveReloadTest
#
# ------------------------------------------------------------
class FilterSaveReloadTest(unittest.TestCase):
    """
    Confirms every rule this addon ships survives a real save/reload
    round-trip and still matches only the right people afterward - not
    the whole tree.
    """

    @classmethod
    def setUpClass(cls):
        # A context manager does not fit setUpClass/tearDownClass,
        # which are two separate methods - cleaned up explicitly in
        # tearDownClass below instead.
        # pylint: disable-next=consider-using-with
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.people = [
            _make_person("P1", "Boucher"),
            _make_person("P2", "Smith"),
            _make_person("P3", "Anderson"),
        ]
        cls.db = _FakeDb(cls.people)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _run(self, rule_class):
        path = os.path.join(self.tmpdir.name, f"{rule_class.__name__}.xml")
        return _build_save_reload_apply(rule_class, "Boucher", self.db, path)

    def test_soundex_survives_reload(self) -> None:
        """
        Gramps' own built-in rule is the control case: it should
        always have worked, reload or not.
        """
        reloaded, matched = self._run(HasSoundexName)
        self.assertEqual(len(reloaded.flist), 1)
        self.assertEqual(matched, ["P1"])

    def test_nysiis_survives_reload(self) -> None:
        """The exact bug reported: this used to come back as ['P1', 'P2', 'P3']."""
        reloaded, matched = self._run(nysiisrule.HasNysiisName)
        self.assertEqual(len(reloaded.flist), 1)
        self.assertEqual(matched, ["P1"])

    def test_match_rating_survives_reload(self) -> None:
        """The exact bug reported: this used to come back as ['P1', 'P2', 'P3']."""
        reloaded, matched = self._run(matchratingrule.HasMatchRatingName)
        self.assertEqual(len(reloaded.flist), 1)
        self.assertEqual(matched, ["P1"])

    def test_metaphone_survives_reload(self) -> None:
        """The exact bug reported: this used to come back as ['P1', 'P2', 'P3']."""
        reloaded, matched = self._run(metaphonerule.HasMetaphoneName)
        self.assertEqual(len(reloaded.flist), 1)
        self.assertEqual(matched, ["P1"])


# ------------------------------------------------------------
#
# Gramps52ApplyCompatibilityTest
#
# ------------------------------------------------------------
class Gramps52ApplyCompatibilityTest(unittest.TestCase):
    """
    Confirms both fixes together, the way Gramps 5.2 would actually
    exercise them: a rule reloaded from saved XML (the
    findable-via-import fix) must also respond correctly when called
    through Gramps 5.2's own method name, `apply()`, not just the
    Gramps 6.0+ name, `apply_to_one()` (the separate compatibility
    fix) - confirmed directly against the real Gramps 5.2 source
    (`maintenance/gramps52` branch), which calls `rule.apply(db, obj)`
    throughout, never `apply_to_one`.
    """

    @classmethod
    def setUpClass(cls):
        # A context manager does not fit setUpClass/tearDownClass,
        # which are two separate methods - cleaned up explicitly in
        # tearDownClass below instead.
        # pylint: disable-next=consider-using-with
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.people = [
            _make_person("P1", "Boucher"),
            _make_person("P2", "Smith"),
            _make_person("P3", "Anderson"),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def _reloaded_rule(self, rule_class):
        """Save a fresh one-rule filter, reload it, and return its one rule."""
        filter_class = GenericFilterFactory("Person")
        new_filter = filter_class()
        new_filter.set_name(f"Fuzzy match: Boucher ({rule_class.__name__})")
        new_filter.add_rule(rule_class(["Boucher"]))

        path = os.path.join(self.tmpdir.name, f"apply_{rule_class.__name__}.xml")
        filterdb = FilterList(path)
        filterdb.add("Person", new_filter)
        filterdb.save()

        reloaded_db = FilterList(path)
        reloaded_db.load()
        reloaded_filter = reloaded_db.get_filters("Person")[0]
        return reloaded_filter.flist[0]

    def _check(self, rule_class):
        rule = self._reloaded_rule(rule_class)
        rule.prepare(None, None)
        matched = [
            person.get_handle()
            for person in self.people
            if rule.apply(None, person)  # the Gramps 5.2 method name
        ]
        self.assertEqual(matched, ["P1"])

    def test_nysiis_apply_after_reload(self) -> None:
        """Reload + Gramps 5.2's apply(): the exact scenario reported."""
        self._check(nysiisrule.HasNysiisName)

    def test_match_rating_apply_after_reload(self) -> None:
        """Reload + Gramps 5.2's apply(): the exact scenario reported."""
        self._check(matchratingrule.HasMatchRatingName)

    def test_metaphone_apply_after_reload(self) -> None:
        """Reload + Gramps 5.2's apply(): the exact scenario reported."""
        self._check(metaphonerule.HasMetaphoneName)


# ------------------------------------------------------------
#
# MakeRuleFindableViaImportTest
#
# ------------------------------------------------------------
class MakeRuleFindableViaImportTest(unittest.TestCase):
    """
    Tests for :func:`phonetic_codes._make_rule_findable_via_import`
    directly, isolated from the save/reload round-trip above.
    """

    def test_discovered_rules_are_attributes_of_rules_person(self) -> None:
        """
        After discovery has run (see the module-level scan_dir/import
        above), every rule this addon ships should be reachable as
        gramps.gen.filters.rules.person.<ClassName> - not just
        importable from this addon's own module.
        """
        # Kept local: only this one test needs it, and a module-level
        # import would suggest (incorrectly) that other tests here
        # depend on gramps.gen.filters.rules.person too.
        # pylint: disable-next=import-outside-toplevel
        from gramps.gen.filters.rules import person as rules_person

        for algorithm_id, rule_class in phonetic_codes.ALGORITHM_FILTER_RULES.items():
            if rule_class is None:
                continue
            with self.subTest(algorithm=algorithm_id):
                self.assertIs(
                    getattr(rules_person, rule_class.__name__, None), rule_class
                )


if __name__ == "__main__":
    unittest.main()
