#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Claude Sonnet 4.5, Anthropic
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""Mock-database tests for ImmediateFamilyRules (no Gtk display needed)."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ImmediateFamilyRules as fnr  # pylint: disable=wrong-import-position

ALL = [
    "parents,spouses,children,associations",
    "siblings,parents_in_law,children_in_law",
    "siblings_in_law",
]
NONE = ["", "", ""]


def _person(handle, parents=(), spouses=(), assoc=()):
    p = MagicMock()
    p.get_handle.return_value = handle
    p.get_parent_family_handle_list.return_value = list(parents)
    p.get_family_handle_list.return_value = list(spouses)
    refs = []
    for h in assoc:
        r = MagicMock()
        r.ref = h
        refs.append(r)
    p.get_person_ref_list.return_value = refs
    return p


def _family(handle, father=None, mother=None, children=()):
    f = MagicMock()
    f.get_handle.return_value = handle
    f.get_father_handle.return_value = father
    f.get_mother_handle.return_value = mother
    kids = []
    for h in children:
        r = MagicMock()
        r.ref = h
        kids.append(r)
    f.get_child_ref_list.return_value = kids
    return f


def _db(people=(), families=(), pid=None, fid=None):
    pmap = {p.get_handle(): p for p in people}
    fmap = {f.get_handle(): f for f in families}
    db = MagicMock()
    db.get_person_from_handle.side_effect = pmap.get
    db.get_family_from_handle.side_effect = fmap.get
    db.get_person_from_gramps_id.side_effect = (pid or {}).get
    db.get_family_from_gramps_id.side_effect = (fid or {}).get
    return db


def _tree():
    """
    DAD+MOM (PF)    -> A, SIB
    A + SP (SF)     -> KID
    FIL+MIL (SPF)   -> SP, SIL
    SIB + SIBSP (BF)
    KID + KIDSP (KF)
    A associated with FRIEND
    """
    people = [
        _person("A", parents=["PF"], spouses=["SF"], assoc=["FRIEND"]),
        _person("SP", parents=["SPF"], spouses=["SF"]),
        _person("SIB", parents=["PF"], spouses=["BF"]),
        _person("KID", parents=["SF"], spouses=["KF"]),
    ]
    families = [
        _family("PF", "DAD", "MOM", ["A", "SIB"]),
        _family("SF", "A", "SP", ["KID"]),
        _family("SPF", "FIL", "MIL", ["SP", "SIL"]),
        _family("BF", "SIB", "SIBSP"),
        _family("KF", "KID", "KIDSP"),
    ]
    return _db(people, families, pid={"I1": people[0]}, fid={"F1": families[1]})


class HelpersTest(unittest.TestCase):
    def test_parse_keys(self):
        self.assertEqual(
            fnr._parse_keys(" parents, ,children "), {"parents", "children"}
        )
        self.assertEqual(fnr._parse_keys(""), set())

    def test_wanted(self):
        self.assertEqual(
            fnr._wanted(["person_id", "I1", "1", "parents", "", "siblings_in_law"]),
            (True, {"parents", "siblings_in_law"}),
        )
        self.assertEqual(fnr._wanted(["person_id", "I1", "0"] + NONE), (False, set()))

    def test_degree_label(self):
        self.assertEqual(fnr._degree_label(1), "1 degree:")
        self.assertEqual(fnr._degree_label(3), "3 degrees:")


class LabelsTest(unittest.TestCase):
    def test_label_counts(self):
        self.assertEqual(len(fnr.ImmediateFamilyPeople.labels), 6)
        self.assertEqual(len(fnr.ImmediateFamilyFamilies.labels), 6)

    def test_label_shapes(self):
        """Every row is a (text, factory) tuple; row 3 reuses Inclusive:."""
        for cls in (fnr.ImmediateFamilyPeople, fnr.ImmediateFamilyFamilies):
            for index, entry in enumerate(cls.labels):
                self.assertIsInstance(entry, tuple)
                self.assertFalse(entry[0].startswith("<class"))
            self.assertEqual(cls.labels[fnr._P_INCLUSIVE][0], "Inclusive:")


class PeopleRuleTest(unittest.TestCase):
    def _match(self, anchor_type, value, inclusive="1", rows=ALL, db=None):
        db = db or _tree()
        rule = fnr.ImmediateFamilyPeople([anchor_type, value, inclusive] + list(rows))
        rule.prepare(db, None)
        return rule.selected_handles

    def test_person_everything(self):
        self.assertEqual(
            self._match("person_id", "I1"),
            {
                "A",
                "DAD",
                "MOM",
                "SP",
                "KID",
                "FRIEND",
                "SIB",
                "FIL",
                "MIL",
                "KIDSP",
                "SIL",
                "SIBSP",
            },
        )

    def test_first_degree_only(self):
        self.assertEqual(
            self._match("person_id", "I1", "0", [ALL[0], "", ""]),
            {"DAD", "MOM", "SP", "KID", "FRIEND"},
        )

    def test_second_degree_only(self):
        self.assertEqual(
            self._match("person_id", "I1", "0", ["", ALL[1], ""]),
            {"SIB", "FIL", "MIL", "KIDSP"},
        )

    def test_siblings_in_law_both_sides(self):
        self.assertEqual(
            self._match("person_id", "I1", "0", ["", "", "siblings_in_law"]),
            {"SIL", "SIBSP"},
        )

    def test_inclusive_only(self):
        self.assertEqual(self._match("person_id", "I1", "1", NONE), {"A"})

    def test_family_anchor_partners(self):
        self.assertEqual(self._match("family_id", "F1", "1", NONE), {"A", "SP"})
        self.assertEqual(
            self._match("family_id", "F1", "0", ["spouses", "", ""]), set()
        )

    def test_home_person(self):
        db = _tree()
        db.get_default_person.return_value = db.get_person_from_gramps_id("I1")
        self.assertEqual(
            self._match("home_person", "ignored", "1", [ALL[0], "", ""], db=db),
            {"A", "DAD", "MOM", "SP", "KID", "FRIEND"},
        )

    def test_no_home_person_warns(self):
        db = _tree()
        db.get_default_person.return_value = None
        with self.assertLogs(fnr.LOG, level="WARNING"):
            self.assertEqual(self._match("home_person", "", db=db), set())

    def test_id_is_stripped(self):
        self.assertIn("A", self._match("person_id", "  I1 "))

    def test_unknown_id_warns(self):
        with self.assertLogs(fnr.LOG, level="WARNING"):
            self.assertEqual(self._match("person_id", "X9"), set())

    def test_unknown_anchor_type_warns(self):
        with self.assertLogs(fnr.LOG, level="WARNING"):
            self.assertEqual(self._match("", "I1"), set())

    def test_missing_family_skipped(self):
        a = _person("A", parents=["GONE"])
        db = _db([a], [], pid={"I1": a})
        self.assertEqual(self._match("person_id", "I1", db=db), {"A"})

    def test_person_filter(self):
        named = MagicMock()
        named.apply.return_value = ["A"]
        filters = MagicMock()
        filters.get_filters_dict.return_value = {"Mine": named}
        with patch.object(fnr, "_get_custom_filters", return_value=filters):
            result = self._match("person_filter", "Mine", "1", NONE)
        self.assertEqual(result, {"A"})
        filters.get_filters_dict.assert_called_with("Person")

    def test_missing_filter_warns(self):
        filters = MagicMock()
        filters.get_filters_dict.return_value = {}
        with patch.object(fnr, "_get_custom_filters", return_value=filters):
            with self.assertLogs(fnr.LOG, level="WARNING"):
                self.assertEqual(self._match("person_filter", "Nope"), set())

    def test_prepare_twice_resets(self):
        db = _tree()
        rule = fnr.ImmediateFamilyPeople(["person_id", "I1", "1"] + ALL)
        rule.prepare(db, None)
        rule.list[1] = "X9"
        with self.assertLogs(fnr.LOG, level="WARNING"):
            rule.prepare(db, None)
        self.assertFalse(rule.apply(db, _person("A")))


FAM_ALL = [
    "as_child,as_parent",
    "of_parents,of_siblings,of_spouses,of_parents_in_law,of_children",
    "of_siblings_in_law,of_children_in_law",
]
FAM_NONE = ["", "", ""]


def _family_tree():
    """
    GF+GM (GPF)       -> DAD
    DAD+MOM (PF)      -> A, SIB
    DAD+STEP (DF2)    -> HALF
    A + SP (SF)       -> KID
    FIL+MIL (SPF)     -> SP, SIL
    SP + EX (XF)
    SIL + SILSP (SILF)
    SIB + SIBSP (BF)
    SIBSPDAD (SBSPF)  -> SIBSP
    KID + KIDSP (KF)
    KIDSPDAD (KSPF)   -> KIDSP
    """
    people = [
        _person("A", parents=["PF"], spouses=["SF"]),
        _person("DAD", parents=["GPF"], spouses=["PF", "DF2"]),
        _person("MOM", spouses=["PF"]),
        _person("SIB", parents=["PF"], spouses=["BF"]),
        _person("SP", parents=["SPF"], spouses=["SF", "XF"]),
        _person("SIL", parents=["SPF"], spouses=["SILF"]),
        _person("SIBSP", parents=["SBSPF"], spouses=["BF"]),
        _person("KID", parents=["SF"], spouses=["KF"]),
        _person("KIDSP", parents=["KSPF"], spouses=["KF"]),
    ]
    families = [
        _family("GPF", "GF", "GM", ["DAD"]),
        _family("PF", "DAD", "MOM", ["A", "SIB"]),
        _family("DF2", "DAD", "STEP", ["HALF"]),
        _family("SF", "A", "SP", ["KID"]),
        _family("SPF", "FIL", "MIL", ["SP", "SIL"]),
        _family("XF", "SP", "EX"),
        _family("SILF", "SIL", "SILSP"),
        _family("BF", "SIB", "SIBSP"),
        _family("SBSPF", "SIBSPDAD", None, ["SIBSP"]),
        _family("KF", "KID", "KIDSP"),
        _family("KSPF", "KIDSPDAD", None, ["KIDSP"]),
    ]
    return _db(people, families, pid={"I1": people[0]}, fid={"F1": families[3]})


class FamiliesRuleTest(unittest.TestCase):
    def _match(self, anchor_type, value, inclusive, rows):
        rule = fnr.ImmediateFamilyFamilies([anchor_type, value, inclusive] + list(rows))
        rule.prepare(_family_tree(), None)
        return rule.selected_handles

    def _one(self, degree, keys):
        rows = ["", "", ""]
        rows[degree - 1] = keys
        return self._match("person_id", "I1", "0", rows)

    def test_first_degree(self):
        self.assertEqual(self._one(1, FAM_ALL[0]), {"PF", "SF"})
        self.assertEqual(self._one(1, "as_child"), {"PF"})

    def test_second_degree_groups(self):
        self.assertEqual(self._one(2, "of_parents"), {"GPF", "DF2"})
        self.assertEqual(self._one(2, "of_siblings"), {"BF"})
        self.assertEqual(self._one(2, "of_spouses"), {"XF"})
        self.assertEqual(self._one(2, "of_parents_in_law"), {"SPF"})
        self.assertEqual(self._one(2, "of_children"), {"KF"})

    def test_third_degree_groups(self):
        self.assertEqual(self._one(3, "of_siblings_in_law"), {"SILF", "SBSPF"})
        self.assertEqual(self._one(3, "of_children_in_law"), {"KSPF"})

    def test_everything(self):
        self.assertEqual(
            self._match("person_id", "I1", "0", FAM_ALL),
            {
                "PF",
                "SF",
                "GPF",
                "DF2",
                "BF",
                "XF",
                "SPF",
                "KF",
                "SILF",
                "SBSPF",
                "KSPF",
            },
        )

    def test_family_anchor(self):
        self.assertEqual(self._match("family_id", "F1", "1", FAM_NONE), {"SF"})
        # Both partners are anchors: the family SP grew up in is 1 degree
        # away, so it is not a 2-degree parents-in-law family.
        self.assertEqual(
            self._match("family_id", "F1", "0", [FAM_ALL[0], "", ""]),
            {"PF", "SPF", "XF"},
        )
        self.assertEqual(
            self._match("family_id", "F1", "0", ["", "of_parents_in_law", ""]),
            set(),
        )


class FilterEngineTest(unittest.TestCase):
    """Run the rules through a real Gramps filter, as the sidebar does."""

    def test_both_entry_points(self):
        for cls in (fnr.ImmediateFamilyPeople, fnr.ImmediateFamilyFamilies):
            self.assertIs(cls.apply, cls.apply_to_one)

    def test_people_rule_in_generic_filter(self):
        from gramps.gen.filters import GenericFilter

        db = _tree()
        rule = fnr.ImmediateFamilyPeople(["person_id", "I1", "0"] + ALL)
        filt = GenericFilter()
        filt.add_rule(rule)
        self.assertTrue(filt.match("SP", db))
        self.assertFalse(filt.match("A", db))

    def test_families_rule_in_generic_filter(self):
        from gramps.gen.filters import GenericFilterFactory

        db = _family_tree()
        db.get_default_person.return_value = db.get_person_from_gramps_id("I1")
        rule = fnr.ImmediateFamilyFamilies(["home_person", "", "1", "as_child", "", ""])
        filt = GenericFilterFactory("Family")()
        filt.add_rule(rule)
        self.assertTrue(filt.match("PF", db))
        self.assertFalse(filt.match("SF", db))


if __name__ == "__main__":
    unittest.main()
