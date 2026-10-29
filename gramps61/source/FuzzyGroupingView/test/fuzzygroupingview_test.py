#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Claude AI (wish coding by Brian McCullough)
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
Unit tests for the Fuzzy Grouping view module.

They test the logic that needs no open family tree: the encoders, the
name format clean-up, the group keys and group row text, the subsort
order and the Expand all order. Model and view methods are called on
plain namespace objects, so no Gtk.TreeModel or view is created.

Importing the view module needs Gramps and a display (it touches the
GTK icon theme), so the tests are skipped without them. Run them from
the addon folder:

    GRAMPS_RESOURCES=<gramps resources> python3 -m unittest discover -s test -p "*_test.py"
"""

# the tests call module internals on purpose
# pylint: disable=protected-access

# ------------------------
# Python modules
# ------------------------
import os
import sys
import unittest
from collections import Counter
from types import SimpleNamespace
from typing import Any

# ------------------------
# Gramps specific
# ------------------------
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INI_PATH = os.path.join(ADDON_DIR, "FuzzyGrouping.ini")
INI_EXISTED = os.path.isfile(INI_PATH)
sys.path.insert(0, ADDON_DIR)
try:
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    import fuzzygroupingview as fgv  # pylint: disable=wrong-import-position

    IMPORT_ERROR = None
except Exception as err:  # pylint: disable=broad-except
    fgv = None  # type: ignore[assignment]  # pylint: disable=invalid-name
    IMPORT_ERROR = err


def tearDownModule() -> None:  # pylint: disable=invalid-name
    """
    Remove the FuzzyGrouping.ini that importing the module wrote, so that
    no test file is left in the addon folder.
    """
    if not INI_EXISTED and os.path.isfile(INI_PATH):
        os.remove(INI_PATH)


# ------------------------------------------------------------
#
# SettingsTest
#
# ------------------------------------------------------------
@unittest.skipIf(fgv is None, f"cannot import the view module: {IMPORT_ERROR}")
class SettingsTest(unittest.TestCase):
    """
    Test the first-use detection.
    """

    @unittest.skipIf(INI_EXISTED, "a FuzzyGrouping.ini was already there")
    def test_first_run_without_ini(self) -> None:
        """
        The .ini written at import has an empty [meta] block, so the view
        still counts as never shown.
        """
        self.assertTrue(os.path.isfile(INI_PATH))
        self.assertEqual(fgv.CONFIG.get("meta.plugin_id"), "")
        self.assertTrue(fgv._FIRST_RUN[0])


# ------------------------------------------------------------
#
# EncoderTest
#
# ------------------------------------------------------------
@unittest.skipIf(fgv is None, f"cannot import the view module: {IMPORT_ERROR}")
class EncoderTest(unittest.TestCase):
    """
    Test the built-in encoders and the encoder discovery.
    """

    def test_exact_codes(self) -> None:
        """
        None groups on the group name itself.
        """
        self.assertEqual(fgv._exact_codes("Smith"), {"Smith"})

    def test_soundex_codes(self) -> None:
        """
        Soundex gives one code, the same for similar spellings.
        """
        self.assertEqual(fgv._soundex_codes("Smith"), {"S530"})
        self.assertEqual(fgv._soundex_codes("Smyth"), fgv._soundex_codes("Smith"))

    def test_discover_encoders_builtins_first(self) -> None:
        """
        None and Soundex are always offered, in that order.
        """
        encoders = fgv.discover_encoders()
        self.assertEqual(list(encoders)[:2], [fgv.EXACT_SYSTEM, fgv.DEFAULT_SYSTEM])


# ------------------------------------------------------------
#
# NameFormatTest
#
# ------------------------------------------------------------
@unittest.skipIf(fgv is None, f"cannot import the view module: {IMPORT_ERROR}")
class NameFormatTest(unittest.TestCase):
    """
    Test the sort-only name format clean-up.
    """

    def test_format_codes_keywords(self) -> None:
        """
        English keywords become % codes.
        """
        self.assertEqual(fgv.format_codes("Surname, Given Suffix"), "%l, %f %s")

    def test_format_codes_keeps_percent(self) -> None:
        """
        A literal %% stays as it is.
        """
        self.assertEqual(fgv.format_codes("Given %%"), "%f %%")

    def test_surnameless_codes(self) -> None:
        """
        The surname and the comma after it go away.
        """
        self.assertEqual(fgv.surnameless_format("%l, %f %s"), "%f %s")

    def test_surnameless_keywords(self) -> None:
        """
        A keyword format is cleaned the same way.
        """
        self.assertEqual(fgv.surnameless_format("Surname, Given Suffix"), "%f %s")

    def test_surnameless_brackets(self) -> None:
        """
        Brackets left empty go away.
        """
        self.assertEqual(fgv.surnameless_format("%t %f (%l)"), "%t %f")

    def test_surnameless_fallback(self) -> None:
        """
        A format of surnames only falls back to Given.
        """
        self.assertEqual(fgv.surnameless_format("%l"), "%f")


# ------------------------------------------------------------
#
# GroupingTest
#
# ------------------------------------------------------------
@unittest.skipIf(fgv is None, f"cannot import the view module: {IMPORT_ERROR}")
class GroupingTest(unittest.TestCase):
    """
    Test the group keys and the group row text of the model.
    """

    def make_model(self, encode: Any) -> Any:
        """
        A namespace that stands in for the model.

        :param encode: The encoder.
        :returns: The stand-in model.
        """
        model: Any = SimpleNamespace(encode=encode, _code_cache={}, _members={})
        model._spellings = lambda key: fgv.FuzzyGroupingTreeModel._spellings(model, key)
        return model

    def test_group_key_soundex(self) -> None:
        """
        Similar spellings get one key.
        """
        model = self.make_model(fgv._soundex_codes)
        key = fgv.FuzzyGroupingTreeModel.group_key(model, "Smith")
        self.assertEqual(key, "S530")
        self.assertEqual(fgv.FuzzyGroupingTreeModel.group_key(model, "Smyth"), key)
        self.assertEqual(model._code_cache, {"Smith": "S530", "Smyth": "S530"})

    def test_group_key_no_surname(self) -> None:
        """
        No surname gives the empty key.
        """
        model = self.make_model(fgv._soundex_codes)
        self.assertEqual(fgv.FuzzyGroupingTreeModel.group_key(model, "  "), "")

    def test_group_key_multi_code(self) -> None:
        """
        A system with several codes uses the lowest one.
        """
        model = self.make_model(lambda name: {"B2", "A1", "C3"})
        self.assertEqual(fgv.FuzzyGroupingTreeModel.group_key(model, "Kowal"), "A1")

    def test_group_key_string_code(self) -> None:
        """
        An encoder may return one code as a string.
        """
        model = self.make_model(lambda name: "X9")
        self.assertEqual(fgv.FuzzyGroupingTreeModel.group_key(model, "Kowal"), "X9")

    def test_group_key_failing_encoder(self) -> None:
        """
        A failing encoder falls back to Soundex.
        """

        def broken(name: str) -> set[str]:
            raise ValueError(name)

        model = self.make_model(broken)
        self.assertEqual(fgv.FuzzyGroupingTreeModel.group_key(model, "Smith"), "S530")

    def test_sample_surname(self) -> None:
        """
        The most used spelling is the sample; an empty group has none.
        """
        model = self.make_model(fgv._soundex_codes)
        model._members["S530"] = Counter({"Smyth": 1, "Smith": 3})
        sample = fgv.FuzzyGroupingTreeModel.sample_surname
        self.assertEqual(sample(model, "S530"), "Smith")
        self.assertEqual(sample(model, "Z000"), "")

    def test_column_header(self) -> None:
        """
        A group row lists four spellings, then +N, then the code.
        """
        model = self.make_model(fgv._soundex_codes)
        model._members["S530"] = Counter(
            {"Smith": 5, "Smyth": 4, "Smithe": 3, "Schmidt": 2, "Smit": 1, "Smitt": 1}
        )
        node: Any = SimpleNamespace(ref="S530")
        header = fgv.FuzzyGroupingTreeModel.column_header(model, node)
        self.assertEqual(header, "Smith, Smyth, Smithe, Schmidt +2 [S530]")


# ------------------------------------------------------------
#
# ViewOrderTest
#
# ------------------------------------------------------------
@unittest.skipIf(fgv is None, f"cannot import the view module: {IMPORT_ERROR}")
class ViewOrderTest(unittest.TestCase):
    """
    Test the subsort order and the Expand all order of the view.
    """

    def setUp(self) -> None:
        """
        Keep the stored subsort order, to restore it after each test.
        """
        self.saved_order = fgv.CONFIG.get("subsort.order")

    def tearDown(self) -> None:
        """
        Restore the stored subsort order (in memory only).
        """
        fgv.CONFIG.set("subsort.order", self.saved_order)

    def test_initial_subsort_order(self) -> None:
        """
        No stored order gives the initial order and every column once.
        """
        fgv.CONFIG.set("subsort.order", [])
        view: Any = SimpleNamespace(_config=None, COLUMNS=fgv.FuzzyGroupingView.COLUMNS)
        order = fgv.FuzzyGroupingView.subsort_order(view)
        head = fgv.INITIAL_SUBSORT_HEAD
        self.assertEqual(order[: len(head)], head)
        expected = {fgv.NAME_FORMAT_ROW} | set(range(1, len(view.COLUMNS)))
        self.assertEqual(set(order), expected)
        self.assertEqual(len(order), len(expected))

    def test_stored_subsort_order(self) -> None:
        """
        A complete stored order is used as it is.
        """
        view: Any = SimpleNamespace(_config=None, COLUMNS=fgv.FuzzyGroupingView.COLUMNS)
        stored = list(range(len(view.COLUMNS) - 1, 0, -1)) + [fgv.NAME_FORMAT_ROW]
        fgv.CONFIG.set("subsort.order", stored)
        self.assertEqual(fgv.FuzzyGroupingView.subsort_order(view), stored)

    def test_stale_subsort_order(self) -> None:
        """
        An incomplete stored order gives the initial order.
        """
        view: Any = SimpleNamespace(_config=None, COLUMNS=fgv.FuzzyGroupingView.COLUMNS)
        fgv.CONFIG.set("subsort.order", [fgv.NAME_FORMAT_ROW, 1])
        order = fgv.FuzzyGroupingView.subsort_order(view)
        self.assertEqual(order[0], fgv.NAME_FORMAT_ROW)
        self.assertEqual(len(order), len(view.COLUMNS))

    def test_expand_order_visible_first(self) -> None:
        """
        Groups on screen open first, then below, then above.
        """
        first = SimpleNamespace(get_indices=lambda: [3])
        last = SimpleNamespace(get_indices=lambda: [5])
        view: Any = SimpleNamespace(
            list=SimpleNamespace(get_visible_range=lambda: (first, last))
        )
        order, top = fgv.FuzzyGroupingView._expand_order(view, 8)
        self.assertEqual(order, [3, 4, 5, 6, 7, 0, 1, 2])
        self.assertEqual(top, 3)

    def test_expand_order_nothing_shown(self) -> None:
        """
        With nothing on screen, groups open in order.
        """
        view: Any = SimpleNamespace(
            list=SimpleNamespace(get_visible_range=lambda: None)
        )
        self.assertEqual(
            fgv.FuzzyGroupingView._expand_order(view, 3), ([0, 1, 2], None)
        )


if __name__ == "__main__":
    unittest.main()
