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
"""
Unit tests for the What's Next? gramplet (WhatsNext.py).

The tests cover the logic that does not need a running Gramps window: the
settings file and its meta block, the date descriptions, the tag rules,
the guidance text, the option tables, and the checks of people and
families (with small stand-in databases).

Run from the addon folder, with Gramps importable::

    python3 -m unittest discover -s test -p "*_test.py"

When running Gramps from a source checkout, set GRAMPS_RESOURCES to that
checkout first. The tests are skipped if GTK cannot be loaded.
"""

# ------------------------
# Python modules
# ------------------------
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from typing import Any
from unittest import mock

# ------------------------
# Gramps modules
# ------------------------
try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # noqa: F401  pylint: disable=unused-import

    from gramps.gen.datehandler import parser
    from gramps.gen.lib import (
        ChildRef,
        Event,
        EventRef,
        EventType,
        Family,
        FamilyRelType,
        Name,
        Person,
        Surname,
    )

    GRAMPS_AVAILABLE = True
except (ImportError, ValueError):  # no Gramps or no GTK 3 in this Python
    GRAMPS_AVAILABLE = False

# ------------------------
# Gramps specific
# ------------------------
ADDON_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W: Any = None  # the WhatsNext module, when Gramps is available
if GRAMPS_AVAILABLE:
    sys.path.insert(0, ADDON_FOLDER)
    import WhatsNext as W  # pylint: disable=import-error,wrong-import-position

PREFIX = "_WhatNextGramplet__"  # name mangling of the private members


# ------------------------------------------------------------
#
# FakeDb
#
# ------------------------------------------------------------
class FakeDb:
    """A small stand-in for a Gramps database, holding objects by handle."""

    def __init__(self) -> None:
        """Start with no objects."""
        self.people: dict[str, Person] = {}
        self.families: dict[str, Family] = {}
        self.events: dict[str, Event] = {}

    def is_open(self) -> bool:
        """
        The tree is always open.

        :returns: True.
        """
        return True

    def add_person(self, handle: str, first: str = "", surname: str = "") -> Person:
        """
        Add a person with a primary name.

        :param handle: The handle of the person.
        :param first: The first name.
        :param surname: The surname.
        :returns: The new person.
        """
        person = Person()
        person.set_handle(handle)
        name = Name()
        name.set_first_name(first)
        surname_obj = Surname()
        surname_obj.set_surname(surname)
        name.add_surname(surname_obj)
        person.set_primary_name(name)
        self.people[handle] = person
        return person

    def add_event(
        self, handle: str, event_type: int, date_text: str = "", place: str = ""
    ) -> Event:
        """
        Add an event.

        :param handle: The handle of the event.
        :param event_type: An EventType value.
        :param date_text: The date, as text for the Gramps date parser.
        :param place: A place handle, or "" for no place.
        :returns: The new event.
        """
        event = Event()
        event.set_handle(handle)
        event.set_type(EventType(event_type))
        if date_text:
            event.set_date_object(parser.parse(date_text))
        if place:
            event.set_place_handle(place)
        self.events[handle] = event
        return event

    def get_person_from_handle(self, handle: str) -> Person:
        """
        Get a person.

        :param handle: The handle.
        :returns: The person.
        """
        return self.people[handle]

    def get_family_from_handle(self, handle: str) -> Family:
        """
        Get a family.

        :param handle: The handle.
        :returns: The family.
        """
        return self.families[handle]

    def get_event_from_handle(self, handle: str) -> Event:
        """
        Get an event.

        :param handle: The handle.
        :returns: The event.
        """
        return self.events[handle]


# ------------------------------------------------------------
#
# FakeDbState
#
# ------------------------------------------------------------
class FakeDbState:  # pylint: disable=too-few-public-methods
    """A stand-in for the Gramps DbState, holding one FakeDb."""

    def __init__(self, db: FakeDb) -> None:
        """
        Hold the database.

        :param db: The stand-in database.
        """
        self.db = db


def make_gramplet(db: FakeDb | None = None) -> Any:
    """
    Make a gramplet object without the Gramps window around it.

    Only the state that the tested methods read is set up: all tests on,
    no tags chosen, and an empty report.

    :param db: The stand-in database, or None for an empty one.
    :returns: The gramplet object.
    """
    gramplet = W.WhatNextGramplet.__new__(W.WhatNextGramplet)
    gramplet.dbstate = FakeDbState(db or FakeDb())
    values = {
        "checks": dict(W.CHECKS),
        "steps": [],
        "show_next_steps": True,
        "complete_tag": "",
        "ignore_tag": "",
        "prune_tag": "",
        "complete_handle": None,
        "ignore_handle": None,
        "prune_handle": None,
        "processed_persons": set(),
        "processed_families": set(),
        "work": 0,
    }
    for name, value in values.items():
        setattr(gramplet, PREFIX + name, value)
    return gramplet


def private(gramplet: Any, name: str) -> Any:
    """
    Get a private member of the gramplet.

    :param gramplet: The gramplet object.
    :param name: The member name without its leading underscores.
    :returns: The member.
    """
    return getattr(gramplet, PREFIX + name)


# ------------------------------------------------------------
#
# SettingsFileTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class SettingsFileTest(unittest.TestCase):
    """The WhatsNext.ini settings file and its ";;" meta block."""

    def setUp(self) -> None:
        """Point the settings file at a temporary folder."""
        # Cleaned up in tearDown, so no with block.
        # pylint: disable-next=consider-using-with
        self.folder = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.folder.name, "WhatsNext.ini")
        self.saved_filename = W.CONFIG.filename
        W.CONFIG.filename = self.path
        W.CONFIG.reset()

    def tearDown(self) -> None:
        """Restore the settings file of the addon."""
        W.CONFIG.filename = self.saved_filename
        W.CONFIG.reset()
        W.CONFIG_WRITABLE = True
        self.folder.cleanup()

    def write(self, text: str) -> None:
        """
        Write a settings file.

        :param text: The content of the file.
        """
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_missing_file_has_no_meta(self) -> None:
        """A missing file has no meta block."""
        self.assertEqual(W.read_meta_block(self.path), {})

    def test_file_without_meta_block(self) -> None:
        """A file without a meta block is not recognized as ours."""
        self.write("[display]\nshow_next_steps=0\n")
        self.assertEqual(W.read_meta_block(self.path), {})

    def test_meta_lines_quote_the_apostrophe(self) -> None:
        """The plugin id "What's Next" is quoted so it can be read back."""
        self.assertEqual(
            W.meta_lines(3),
            ["[meta]", 'plugin_id="What\'s Next"', "schema_version='3'"],
        )

    def test_save_writes_meta_block_first(self) -> None:
        """The meta block is written at the top, before every section."""
        W.save_config()
        with open(self.path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertLess(text.index(";; [meta]"), text.index("["))
        meta = W.read_meta_block(self.path)
        self.assertEqual(meta["plugin_id"], W.PLUGIN_ID)
        self.assertEqual(meta["schema_version"], W.CONFIG_SCHEMA_VERSION)

    def test_round_trip_keeps_tags_of_each_tree(self) -> None:
        """Tags saved for two trees, one name with an apostrophe, load back."""
        tags = {
            "tree1": {"tree": "Example", "complete": "Done"},
            "tree2": {"tree": "Brian's Tree", "prune": "Dead end"},
        }
        W.CONFIG.set("trees.tags", tags)
        W.CONFIG.set("display.show_next_steps", False)
        W.save_config()
        W.CONFIG.reset()
        self.assertTrue(W.load_config())
        self.assertEqual(W.CONFIG.get("trees.tags"), tags)
        self.assertFalse(W.CONFIG.get("display.show_next_steps"))

    def test_file_without_meta_is_ignored(self) -> None:
        """Settings in a file without a meta block are not loaded."""
        self.write("[display]\nshow_next_steps=0\n")
        self.assertTrue(W.load_config())
        self.assertTrue(W.CONFIG.get("display.show_next_steps"))

    def test_file_of_another_plugin_is_ignored(self) -> None:
        """Settings in a file with another plugin id are not loaded."""
        self.write(
            ";; [meta]\n;; plugin_id='Other'\n;; schema_version='1'\n"
            "[display]\nshow_next_steps=0\n"
        )
        with self.assertLogs(W.LOG, level="WARNING"):
            self.assertTrue(W.load_config())
        self.assertTrue(W.CONFIG.get("display.show_next_steps"))

    def test_newer_schema_is_used_but_not_saved(self) -> None:
        """A file from a newer version is loaded, and never saved over."""
        self.write(
            ";; [meta]\n;; plugin_id=\"What's Next\"\n;; schema_version='99'\n"
            "[display]\nshow_next_steps=0\n"
        )
        with self.assertLogs(W.LOG, level="WARNING"):
            writable = W.load_config()
        self.assertFalse(writable)
        self.assertFalse(W.CONFIG.get("display.show_next_steps"))
        W.CONFIG_WRITABLE = writable
        before = os.path.getmtime(self.path)
        W.save_config()
        self.assertEqual(os.path.getmtime(self.path), before)


# ------------------------------------------------------------
#
# EventDateTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class EventDateTest(unittest.TestCase):
    """How the date and place of an event are described."""

    def describe(self, date_text: str, place: str = "P1", **checks: bool) -> list:
        """
        Check one Birth event.

        :param date_text: The date, as text for the Gramps date parser.
        :param place: A place handle, or "" for no place.
        :param checks: Tests to switch on or off, by key.
        :returns: The problems found.
        """
        gramplet = make_gramplet()
        private(gramplet, "checks").update(checks)
        event = FakeDb().add_event("E1", EventType.BIRTH, date_text, place)
        return private(gramplet, "process_event")(event, "person_event")

    def test_full_date_and_place(self) -> None:
        """A full date with a place is not reported."""
        self.assertEqual(self.describe("1794-05-12"), [])

    def test_no_date(self) -> None:
        """An event without a date is "date unknown"."""
        self.assertEqual(self.describe(""), ["Birth: date unknown"])

    def test_range_is_inexact(self) -> None:
        """A range is inexact, not incomplete."""
        self.assertEqual(
            self.describe("between 1794 and 1796"), ["Birth: date inexact"]
        )

    def test_inexact_dates(self) -> None:
        """Spans, about, before, after, estimated and calculated are inexact."""
        for text in (
            "from 1790 to 1795",
            "about 1794",
            "before 1800",
            "after 1790",
            "estimated 1794-05-12",
            "calculated 1794",
        ):
            with self.subTest(date=text):
                self.assertEqual(self.describe(text), ["Birth: date inexact"])

    def test_incomplete_dates(self) -> None:
        """A single date without its day or month is incomplete."""
        for text in ("1794", "May 1794"):
            with self.subTest(date=text):
                self.assertEqual(self.describe(text), ["Birth: date incomplete"])

    def test_text_only_date(self) -> None:
        """Text that is not a date is "date is text only"."""
        self.assertEqual(
            self.describe("sometime in spring"), ["Birth: date is text only"]
        )

    def test_missing_place(self) -> None:
        """A missing place is added to the same entry."""
        self.assertEqual(
            self.describe("1794", place=""),
            ["Birth: date incomplete, place unknown for the Event"],
        )

    def test_switched_off_tests_are_silent(self) -> None:
        """A test that is switched off reports nothing."""
        self.assertEqual(self.describe("about 1794", date_inexact=False), [])
        self.assertEqual(
            self.describe("1794-05-12", place=""),
            ["Birth: place unknown for the Event"],
        )
        self.assertEqual(self.describe("1794-05-12", place="", place_unknown=False), [])

    def test_problem_adds_its_step(self) -> None:
        """A problem adds the next step given by the caller."""
        gramplet = make_gramplet()
        event = FakeDb().add_event("E1", EventType.BIRTH, "1794")
        private(gramplet, "process_event")(event, "person_event")
        self.assertEqual(private(gramplet, "steps"), ["person_event"])


# ------------------------------------------------------------
#
# PersonCheckTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class PersonCheckTest(unittest.TestCase):
    """The checks of one person, with the report captured."""

    def setUp(self) -> None:
        """Make a gramplet whose reports are collected in a list."""
        self.db = FakeDb()
        self.gramplet = make_gramplet(self.db)
        self.reports: list[tuple[str, list[str], list[str]]] = []

        def report(_name: str, _link: str, handle: str, bits: list[str]) -> None:
            self.reports.append(
                (handle, list(bits), list(private(self.gramplet, "steps")))
            )

        setattr(self.gramplet, PREFIX + "report", report)

    def check(self, person: Person, alive: bool = True) -> None:
        """
        Run the checks of one person.

        :param person: The person.
        :param alive: What the "probably alive" check answers.
        """
        with mock.patch.object(W, "probably_alive", return_value=alive):
            private(self.gramplet, "process_person")(person, [])

    def add_birth(self, person: Person, date_text: str = "1794-05-12") -> None:
        """
        Give a person a preferred Birth event with a place.

        :param person: The person.
        :param date_text: The date of the event.
        """
        handle = "B" + person.get_handle()
        self.db.add_event(handle, EventType.BIRTH, date_text, "P1")
        ref = EventRef()
        ref.set_reference_handle(handle)
        person.add_event_ref(ref)
        person.set_birth_ref(ref)

    def test_complete_person_is_not_reported(self) -> None:
        """A named person with a full Birth event is not reported."""
        person = self.db.add_person("I1", "Ann", "Lee")
        self.add_birth(person)
        self.check(person)
        self.assertEqual(self.reports, [])

    def test_missing_names_and_birth(self) -> None:
        """Missing names and a missing Birth event share one line."""
        person = self.db.add_person("I1")
        self.check(person)
        handle, bits, steps = self.reports[0]
        self.assertEqual(handle, "I1")
        self.assertEqual(
            bits, ["first name unknown", "surname unknown", "Birth event missing"]
        )
        self.assertEqual(steps, ["name", "add_event"])

    def test_missing_death_only_when_not_alive(self) -> None:
        """A missing Death event is reported only for a person not alive."""
        person = self.db.add_person("I1", "Ann", "Lee")
        self.add_birth(person)
        self.check(person, alive=True)
        self.assertEqual(self.reports, [])
        self.check_again(person, alive=False)
        self.assertEqual(self.reports[0][1], ["Death event missing"])

    def check_again(self, person: Person, alive: bool) -> None:
        """
        Run the checks of a person again, as if not seen before.

        :param person: The person.
        :param alive: What the "probably alive" check answers.
        """
        private(self.gramplet, "processed_persons").clear()
        self.check(person, alive)

    def test_non_preferred_death_counts(self) -> None:
        """A Death event that is not the preferred one still counts."""
        person = self.db.add_person("I1", "Ann", "Lee")
        self.add_birth(person)
        self.db.add_event("D1", EventType.DEATH, "1850-01-01", "P1")
        ref = EventRef()
        ref.set_reference_handle("D1")
        person.add_event_ref(ref)  # not set as the preferred Death event
        self.check(person, alive=False)
        self.assertEqual(self.reports, [])

    def test_inexact_birth_date(self) -> None:
        """An inexact Birth date gets the event step."""
        person = self.db.add_person("I1", "Ann", "Lee")
        self.add_birth(person, "about 1794")
        self.check(person)
        _handle, bits, steps = self.reports[0]
        self.assertEqual(bits, ["Birth: date inexact"])
        self.assertEqual(steps, ["person_event"])

    def test_suppressed_person_is_hidden_but_followed(self) -> None:
        """A person with the Complete tag is hidden, but the search goes on."""
        person = self.db.add_person("I1")
        person.add_tag("T1")
        setattr(self.gramplet, PREFIX + "complete_handle", "T1")
        follow: list[Person] = []
        with mock.patch.object(W, "probably_alive", return_value=True):
            private(self.gramplet, "process_person")(person, follow)
        self.assertEqual(self.reports, [])
        self.assertEqual(follow, [person])


# ------------------------------------------------------------
#
# FamilyCheckTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class FamilyCheckTest(unittest.TestCase):
    """The checks of one family, and how its members are found."""

    def setUp(self) -> None:
        """Make a married couple with one child."""
        self.db = FakeDb()
        self.gramplet = make_gramplet(self.db)
        self.reports: list[tuple[list[str], list[str]]] = []

        def report(_name: str, _link: str, _handle: str, bits: list[str]) -> None:
            self.reports.append((list(bits), list(private(self.gramplet, "steps"))))

        setattr(self.gramplet, PREFIX + "report", report)
        self.father = self.db.add_person("F", "Tom", "Lee")
        self.mother = self.db.add_person("M", "Ann", "Ray")
        self.child = self.db.add_person("C", "Sam", "Lee")
        self.family = Family()
        self.family.set_handle("FAM")
        self.family.set_father_handle("F")
        self.family.set_mother_handle("M")
        self.family.set_relationship(FamilyRelType(FamilyRelType.MARRIED))
        ref = ChildRef()
        ref.set_reference_handle("C")
        self.family.add_child_ref(ref)
        self.db.families["FAM"] = self.family
        self.child.add_parent_family_handle("FAM")
        self.child.set_main_parent_family_handle("FAM")

    def process(self) -> None:
        """Run the checks of the family."""
        private(self.gramplet, "process_family")(
            self.family, self.father, self.mother, []
        )

    def test_married_without_marriage_event(self) -> None:
        """A married family without a Marriage event is reported."""
        self.process()
        self.assertEqual(self.reports, [(["marriage event missing"], ["marriage"])])

    def test_unknown_relationship_type(self) -> None:
        """A family of the "Unknown" type is reported."""
        self.family.set_relationship(FamilyRelType(FamilyRelType.UNKNOWN))
        self.process()
        self.assertEqual(
            self.reports, [(["relationship type unknown"], ["relationship"])]
        )

    def test_marriage_event_with_inexact_date(self) -> None:
        """A Marriage event with an inexact date gets the family event step."""
        self.db.add_event("E1", EventType.MARRIAGE, "about 1820", "P1")
        ref = EventRef()
        ref.set_reference_handle("E1")
        self.family.add_event_ref(ref)
        self.process()
        self.assertEqual(self.reports, [(["Marriage: date inexact"], ["family_event"])])

    def test_switched_off_family_tests(self) -> None:
        """With its test switched off, the missing Marriage is not reported."""
        private(self.gramplet, "checks")["marriage_missing"] = False
        self.process()
        self.assertEqual(self.reports, [])

    def test_parents_and_children_are_found(self) -> None:
        """The parents and the children of a family are found."""
        father, mother, family = private(self.gramplet, "get_parents")(self.child)
        self.assertEqual(
            (father, mother, family), (self.father, self.mother, self.family)
        )
        children = list(private(self.gramplet, "get_children")(self.family))
        self.assertEqual(children, [self.child])

    def test_missing_parent_family(self) -> None:
        """A person without a parent family is marked for reporting."""
        result = private(self.gramplet, "get_parents")(self.father)
        self.assertEqual(result, (W.UNKNOWN_PERSON, W.UNKNOWN_PERSON, W.UNKNOWN_FAMILY))

    def test_missing_father_and_partner(self) -> None:
        """A married family without a father is marked for reporting."""
        self.family.set_father_handle(None)
        father, _mother, _family = private(self.gramplet, "get_parents")(self.child)
        self.assertIs(father, W.UNKNOWN_PERSON)
        spouse = private(self.gramplet, "get_spouse")(self.mother, self.family)
        self.assertIs(spouse, W.UNKNOWN_PERSON)

    def test_pruned_child_is_not_followed(self) -> None:
        """A child with the Prune tag is not followed by the search."""
        self.child.add_tag("TP")
        setattr(self.gramplet, PREFIX + "prune_handle", "TP")
        self.assertEqual(list(private(self.gramplet, "get_children")(self.family)), [])


# ------------------------------------------------------------
#
# TagRuleTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class TagRuleTest(unittest.TestCase):
    """The rules for the Complete, Ignore and Prune tags."""

    def test_each_kind_needs_its_own_tag(self) -> None:
        """A tag chosen for two kinds counts only for the earlier kind."""
        gramplet = make_gramplet()
        setattr(gramplet, PREFIX + "complete_tag", "Done")
        setattr(gramplet, PREFIX + "prune_tag", "Done")
        effective = private(gramplet, "effective_tag")
        self.assertEqual(effective("complete"), "Done")
        self.assertEqual(effective("prune"), "")

    def test_default_tag_when_none_chosen(self) -> None:
        """With no tag chosen, the default tag is used and flagged."""
        gramplet = make_gramplet()
        name, color, is_default = private(gramplet, "tag_for_kind")("prune")
        self.assertEqual(name, W.DEFAULT_PRUNE_TAG)
        self.assertEqual(color, W.DEFAULT_PRUNE_COLOR)
        self.assertTrue(is_default)

    def test_chosen_tag_is_not_default(self) -> None:
        """A chosen tag is used as it is."""
        gramplet = make_gramplet()
        setattr(gramplet, PREFIX + "ignore_tag", "Later")
        name, _color, is_default = private(gramplet, "tag_for_kind")("ignore")
        self.assertEqual(name, "Later")
        self.assertFalse(is_default)


# ------------------------------------------------------------
#
# GuidanceTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class GuidanceTest(unittest.TestCase):
    """The "no tree loaded" guidance and the Import check."""

    @staticmethod
    def uistate(enabled: bool | None) -> Any:
        """
        Make a stand-in for the Gramps display state.

        :param enabled: Whether the Import action is enabled, or None for a
            display state without a view manager.
        :returns: The stand-in.
        """
        if enabled is None:
            return object()
        action = mock.Mock()
        action.get_enabled.return_value = enabled
        viewmanager = mock.Mock()
        viewmanager.uimanager.get_action.return_value = action
        return mock.Mock(viewmanager=viewmanager)

    def test_import_check(self) -> None:
        """The Import check follows the state of the Import action."""
        self.assertTrue(W.can_import_without_tree(self.uistate(True)))
        self.assertFalse(W.can_import_without_tree(self.uistate(False)))
        self.assertFalse(W.can_import_without_tree(self.uistate(None)))

    def test_import_ready_skips_empty_tree_step(self) -> None:
        """When Import works with no tree, no empty tree is asked for."""
        message = W.no_tree_message(True, import_ready=True)
        self.assertIn("genealogical tool", message)
        self.assertNotIn("empty tree", message)

    def test_import_not_ready_asks_for_empty_tree(self) -> None:
        """When Import needs a tree, an empty tree is created first."""
        self.assertIn("empty tree", W.no_tree_message(True, import_ready=False))

    def test_next_steps_can_be_hidden(self) -> None:
        """Without Next Steps, only the reason is shown."""
        message = W.no_tree_message(False)
        self.assertIn("not yet been loaded", message)
        self.assertNotIn("Next Steps", message)


# ------------------------------------------------------------
#
# OptionTableTest
#
# ------------------------------------------------------------
@unittest.skipUnless(GRAMPS_AVAILABLE, "Gramps or GTK 3 is not available")
class OptionTableTest(unittest.TestCase):
    """The tables behind the options and the next steps."""

    def test_every_option_is_a_known_test(self) -> None:
        """Every check box switches a test that the search knows."""
        for key, _label in W.CHECK_OPTIONS:
            with self.subTest(key=key):
                self.assertIn(key, W.CHECKS)

    def test_every_test_has_an_option(self) -> None:
        """Every test of the search can be switched in the options."""
        self.assertEqual({key for key, _label in W.CHECK_OPTIONS}, set(W.CHECKS))

    def test_option_labels_are_unique(self) -> None:
        """Gramps finds options by label, so no two labels may be the same."""
        labels = [label for _key, label in W.CHECK_OPTIONS]
        self.assertEqual(len(labels), len(set(labels)))

    def test_every_option_has_a_tooltip(self) -> None:
        """Every check box has a tooltip."""
        for key, _label in W.CHECK_OPTIONS:
            with self.subTest(key=key):
                self.assertTrue(W.CHECK_HELP.get(key))

    def test_steps_used_in_the_code_exist(self) -> None:
        """Every next step that the code asks for has a text."""
        path = os.path.join(ADDON_FOLDER, "WhatsNext.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        used = set(re.findall(r'add_step\("(\w+)"\)', source))
        used |= set(re.findall(r'process_event\(event, "(\w+)"\)', source))
        used |= set(
            re.findall(r'missing_link\(\s*person,.*?,\s*"(\w+)",?\s*\)', source, re.S)
        )
        self.assertTrue(used)
        for key in used:
            with self.subTest(step=key):
                self.assertIn(key, W.NEXT_STEPS)

    def test_every_step_is_used(self) -> None:
        """Every next step text is asked for somewhere in the code."""
        path = os.path.join(ADDON_FOLDER, "WhatsNext.py")
        with open(path, encoding="utf-8") as handle:
            body = handle.read().split("NEXT_STEPS = {", 1)[1].split("\n}\n", 1)[1]
        for key in W.NEXT_STEPS:
            with self.subTest(step=key):
                self.assertIn(f'"{key}"', body)


if __name__ == "__main__":
    unittest.main()
