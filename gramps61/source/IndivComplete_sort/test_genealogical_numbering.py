#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Unit tests for genealogical_numbering: numbering systems, pedigree
collapse, labels, menu option values and the remembered attributes.

The test tree has a marriage between cousins, so the shared ancestors get
two Sosa numbers and the child of the cousins two descendant numbers::

    G + H
    ├── A + X ── C ─┐
    └── B + Y ── D ─┴── E (focal person for the ancestor tests)

Run from the addons-source root with::

    python3 -m unittest IndivComplete_sort.tests.test_genealogical_numbering -v
"""

# ------------------------
# Python modules
# ------------------------
import os
import shutil
import sys
import tempfile
import unittest

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.db import DbTxn
from gramps.gen.db.utils import make_database
from gramps.gen.lib import (
    Attribute,
    AttributeType,
    ChildRef,
    Family,
    Name,
    Person,
    Surname,
)
from gramps.gen.plug.menu import Menu

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

# pylint: disable=wrong-import-position
import genealogical_numbering as gn  # noqa: E402


# ------------------------------------------------------------
#
# NumberingTest
#
# ------------------------------------------------------------
class NumberingTest(unittest.TestCase):
    """Tests run against a small temporary SQLite tree."""

    db = None
    tmpdir = ""
    handles: dict[str, str] = {}
    families: dict[str, Family] = {}

    @classmethod
    def setUpClass(cls) -> None:
        """Build the test tree."""
        cls.tmpdir = tempfile.mkdtemp(prefix="genealogical_numbering_")
        cls.db = make_database("sqlite")
        cls.db.load(cls.tmpdir)
        people = {}
        with DbTxn("build test tree", cls.db) as txn:
            for key in "GHAXBYCDE":
                person = Person()
                name = Name()
                name.set_first_name(key)
                surname = Surname()
                surname.set_surname("Test")
                name.add_surname(surname)
                person.set_primary_name(name)
                person.set_gramps_id("I" + key)
                cls.db.add_person(person, txn)
                people[key] = person
            nickname = Attribute()
            nickname.set_type(AttributeType("Ahnentafel"))
            nickname.set_value("A-4")
            people["A"].add_attribute(nickname)
            for fid, father, mother, children in (
                ("FGH", "G", "H", "AB"),
                ("FAX", "A", "X", "C"),
                ("FYB", "Y", "B", "D"),
                ("FCD", "C", "D", "E"),
            ):
                family = Family()
                family.set_gramps_id(fid)
                family.set_father_handle(people[father].get_handle())
                family.set_mother_handle(people[mother].get_handle())
                for child in children:
                    ref = ChildRef()
                    ref.set_reference_handle(people[child].get_handle())
                    family.add_child_ref(ref)
                cls.db.add_family(family, txn)
                cls.families[fid] = family
                for parent in (father, mother):
                    people[parent].add_family_handle(family.get_handle())
                for child in children:
                    people[child].add_parent_family_handle(family.get_handle())
            for person in people.values():
                cls.db.commit_person(person, txn)
        cls.handles = {key: person.get_handle() for key, person in people.items()}

    @classmethod
    def tearDownClass(cls) -> None:
        """Remove the test tree."""
        cls.db.close()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def numbers(self, numbering: gn.Numbering) -> dict[str, list[str]]:
        """
        Return the numbers of every numbered test person.

        :param numbering: The Numbering.
        :returns: Numbers keyed by the test person letter.
        """
        return {
            key: numbering.numbers(handle)
            for key, handle in self.handles.items()
            if handle in numbering
        }

    def test_sosa_pedigree_collapse(self) -> None:
        """Shared ancestors keep both Sosa numbers, smallest first."""
        numbering = gn.Numbering(self.db, self.handles["E"], "sosa")
        self.assertEqual(
            self.numbers(numbering),
            {
                "E": ["1"],
                "C": ["2"],
                "D": ["3"],
                "A": ["4"],
                "X": ["5"],
                "Y": ["6"],
                "B": ["7"],
                "G": ["8", "14"],
                "H": ["9", "15"],
            },
        )
        order = [
            self.db.get_person_from_handle(h).get_gramps_id()
            for h in numbering.handles()
        ]
        self.assertEqual(order, ["IE", "IC", "ID", "IA", "IX", "IY", "IB", "IG", "IH"])
        self.assertEqual(numbering.generation(self.handles["G"]), 4)

    def test_ahnentafel_matches_sosa(self) -> None:
        """Ahnentafel gives the Sosa-Stradonitz numbers."""
        sosa = gn.Numbering(self.db, self.handles["E"], "sosa")
        ahnentafel = gn.Numbering(self.db, self.handles["E"], "ahnentafel")
        self.assertEqual(self.numbers(sosa), self.numbers(ahnentafel))

    def test_descendant_systems(self) -> None:
        """Each descendant system formats the same tree as expected."""
        expected = {
            "henry": {"G": ["1"], "A": ["11"], "B": ["12"], "C": ["111"],
                      "D": ["121"], "E": ["1111", "1211"]},
            "modified_henry": {"E": ["1111", "1211"]},
            "daboville": {"B": ["1.2"], "E": ["1.1.1.1", "1.2.1.1"]},
            "villiers_pama": {"C": ["a1b1c1"], "E": ["a1b1c1d1", "a1b2c1d1"]},
            "meurgey": {"G": ["I"], "A": ["II-1"], "B": ["II-2"], "E": ["IV-1"]},
            "record": {"G": ["1"], "A": ["2"], "B": ["3"], "C": ["4"],
                       "D": ["5"], "E": ["6"]},
            "simple": {"G": ["1"], "B": ["2"], "E": ["4"]},
        }  # fmt: skip
        for system_id, wanted in expected.items():
            with self.subTest(system=system_id):
                found = self.numbers(
                    gn.Numbering(self.db, self.handles["G"], system_id)
                )
                for key, numbers in wanted.items():
                    self.assertEqual(found[key], numbers)

    def test_henry_order_is_branch_by_branch(self) -> None:
        """Henry sorts each family branch together; Record by generation."""
        henry = gn.Numbering(self.db, self.handles["G"], "henry")
        record = gn.Numbering(self.db, self.handles["G"], "record")
        letters = {handle: key for key, handle in self.handles.items()}
        self.assertEqual(
            [letters[h] for h in henry.handles()], ["G", "A", "C", "E", "B", "D"]
        )
        self.assertEqual(
            [letters[h] for h in record.handles()], ["G", "A", "B", "C", "D", "E"]
        )

    def test_max_generations(self) -> None:
        """Numbering stops after the chosen number of generations."""
        numbering = gn.Numbering(self.db, self.handles["E"], "sosa", max_generations=2)
        self.assertEqual(sorted(self.numbers(numbering)), ["C", "D", "E"])

    def test_attribute_numbering_and_fallback(self) -> None:
        """An Attribute numbering falls back to the Label, then the Gramps ID."""
        label = gn.Label("attr:Nickname")  # nobody has a Nickname
        numbering = gn.Numbering(
            self.db,
            self.handles["E"],
            gn.attribute_system(gn.ANCESTOR),
            attribute="Ahnentafel",
            fallback=label,
        )
        found = self.numbers(numbering)
        self.assertEqual(found["A"], ["A-4"])
        self.assertEqual(found["G"], ["IG"])  # unique: one entry per person

    def test_labels(self) -> None:
        """Labels show nothing, the Gramps ID or an attribute value."""
        person_a = self.db.get_person_from_handle(self.handles["A"])
        person_b = self.db.get_person_from_handle(self.handles["B"])
        self.assertEqual(gn.Label(gn.NONE_ID)(person_a), "")
        self.assertFalse(gn.Label(gn.NONE_ID))
        self.assertEqual(gn.Label(gn.GRAMPS_ID)(person_a), "IA")
        self.assertEqual(gn.Label("attr:Ahnentafel")(person_a), "A-4")
        self.assertEqual(gn.Label("attr:Ahnentafel")(person_b), "IB")
        self.assertEqual(gn.Label(gn.GRAMPS_ID)(self.families["FAX"]), "FAX")

    def test_attribute_choice_values(self) -> None:
        """Saved Include Gramps ID values and attribute choices convert."""
        menu = Menu()
        option = gn.add_person_label_option(menu, "Identifiers", self.db)
        self.assertEqual(option.get_value(), gn.GRAMPS_ID)
        for saved, wanted in ((0, gn.NONE_ID), (1, gn.GRAMPS_ID), ("2", gn.GRAMPS_ID)):
            option.set_value(saved)
            self.assertEqual(option.get_value(), wanted)
        option.set_value("attr:Ahnentafel")
        self.assertEqual(option.get_value(), "attr:Ahnentafel")
        self.assertEqual(option.attribute, "Ahnentafel")
        self.assertEqual(option.get_tree()[-1][0], "attr:Ahnentafel")
        option.set_value("no such value")
        self.assertEqual(option.get_value(), gn.GRAMPS_ID)

    def test_center_person_values(self) -> None:
        """Any Gramps ID is accepted; unknown values give the Home Person."""
        option = gn.CenterPersonOption("Center Person", self.db)
        option.set_value("IC")
        self.assertEqual(option.get_value(), "IC")
        self.assertEqual(option.get_center_person(self.db).get_gramps_id(), "IC")
        option.set_value("NO-SUCH-ID")
        self.assertEqual(option.get_value(), gn.HOME_PERSON)

    def test_numbering_from_menu(self) -> None:
        """The menu helpers build the chosen numberings."""
        menu = Menu()
        gn.add_numbering_options(menu, "Identifiers", self.db)
        menu.get_option_by_name(gn.OPT_FOCAL).set_value("IE")
        menu.get_option_by_name(gn.OPT_ANCESTOR).set_value("sosa")
        menu.get_option_by_name(gn.OPT_DESCENDANT).set_value(gn.NONE_ID)
        anc, desc = gn.numbering_from_menu(self.db, menu)
        self.assertIsNone(desc)
        self.assertIsNotNone(anc)
        self.assertEqual(anc.numbers(self.handles["G"]), ["8", "14"])

    def test_register_system(self) -> None:
        """A new system is listed and validated."""

        class DashNumbering(gn.DescendantSystem):
            """Test system."""

            system_id = "test_dash"
            label = gn.N_("Dash numbering")

            def format(self, rec: gn.NumberRecord) -> str:
                return "-".join(str(i) for i in (1,) + rec.path)

        gn.register_system(DashNumbering())
        self.assertIn(gn.get_system("test_dash"), gn.get_systems(gn.DESCENDANT))
        numbering = gn.Numbering(self.db, self.handles["G"], "test_dash")
        self.assertEqual(numbering.numbers(self.handles["C"]), ["1-1-1"])
        with self.assertRaises(ValueError):
            gn.register_system(gn.NumberingSystem())


# ------------------------------------------------------------
#
# AttributeMemoryTest
#
# ------------------------------------------------------------
class AttributeMemoryTest(unittest.TestCase):
    """Tests of the remembered attribute types (.ini file)."""

    def setUp(self) -> None:
        """Create a temporary plugin folder."""
        self.folder = tempfile.mkdtemp(prefix="genealogical_numbering_ini_")

    def tearDown(self) -> None:
        """Remove the temporary plugin folder."""
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_remember_and_replace_foreign_ini(self) -> None:
        """Values persist; an .ini of another plugin id is replaced."""
        path = os.path.join(self.folder, "TestMemoryA.ini")
        with open(path, "w", encoding="utf-8") as ini:
            ini.write(
                "[meta]\nplugin_id='OtherPlugin'\nschema_version='3'\n\n"
                "[attributes]\ninc_id='Caste'\n"
            )
        memory = gn.AttributeMemory("TestMemoryA", self.folder)
        self.assertEqual(memory.get(gn.OPT_PERSON_LABEL), "")
        memory.set(gn.OPT_PERSON_LABEL, "Nickname")
        with open(path, encoding="utf-8") as ini:
            text = ini.read()
        self.assertIn("plugin_id='TestMemoryA'", text)
        self.assertIn("inc_id='Nickname'", text)
        self.assertEqual(memory.get("not_a_key"), "")


if __name__ == "__main__":
    unittest.main()
