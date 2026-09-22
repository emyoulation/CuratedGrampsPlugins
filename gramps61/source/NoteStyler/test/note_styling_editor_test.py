#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025      Kari Kujansuu (SuperTool script)
# Copyright (C) 2026      Brian McCullough
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
Standalone smoke test for the pure (non-GTK) markup-row logic used by
NoteStylingEditor.py: build_row_data and kept_tags_after_clear.

This sandbox has no working PyGObject and no Gramps install, so the real
gramplet module can't be imported (it imports gi.repository.Gtk and
several gramps.* modules at module scope). The two functions below are
copied verbatim from NoteStylingEditor.py; only StyledTextTag and Note
are stood in with light fakes, so this exercises the actual logic under
test, not a re-implementation of it.
"""

from __future__ import annotations

import unittest


# ---- fakes standing in for gramps.gen.lib.StyledTextTag / Note ------
class FakeStyledTextTag:
    def __init__(self, name, value, ranges):
        self.name = name
        self.value = value
        self.ranges = ranges


class FakeStyledText:
    def __init__(self, tags):
        self.tags = tags


class FakeNote:
    def __init__(self, text, tags, gramps_id="N0001"):
        self._text = text
        self._styled = FakeStyledText(tags)
        self.gramps_id = gramps_id

    def get(self):
        return self._text

    def get_styledtext(self):
        return self._styled


StyledTextTag = FakeStyledTextTag
Note = FakeNote  # only used in the type hints below; never evaluated,
# since this module uses `from __future__ import annotations`.
RowData = tuple[StyledTextTag, str, str, str]


# ---- the two functions, copied verbatim from NoteStylingEditor.py -----


def build_row_data(note: Note | None) -> list[RowData]:
    rows: list[RowData] = []
    if note is None:
        return rows
    full_text = note.get()
    for tag in note.get_styledtext().tags:
        for rng in tag.ranges:
            start, end = rng
            row_tag = StyledTextTag(tag.name, tag.value, [rng])
            rows.append((row_tag, tag.name, tag.value or "", full_text[start:end]))
    rows.sort(key=lambda row: row[0].ranges[0])
    return rows


def kept_tags_after_clear(
    row_tags: list[StyledTextTag], checked_flags: list[bool]
) -> list[StyledTextTag]:
    return [tag for tag, checked in zip(row_tags, checked_flags) if not checked]


# ------------------------------------------------------------------
# tests
# ------------------------------------------------------------------


class BuildRowDataTest(unittest.TestCase):
    def test_none_note_returns_empty(self):
        self.assertEqual(build_row_data(None), [])

    def test_no_tags_returns_empty(self):
        note = FakeNote("hello world", [])
        self.assertEqual(build_row_data(note), [])

    def test_single_tag_single_range(self):
        tag = FakeStyledTextTag("Bold", None, [(0, 5)])
        note = FakeNote("hello world", [tag])
        rows = build_row_data(note)
        self.assertEqual(len(rows), 1)
        row_tag, name, value, snippet = rows[0]
        self.assertEqual(name, "Bold")
        self.assertEqual(value, "")  # None normalized to "" for display
        self.assertEqual(snippet, "hello")
        self.assertEqual(row_tag.ranges, [(0, 5)])

    def test_tag_with_multiple_ranges_splits_into_one_row_each(self):
        # Regression check for the original script's behaviour: a single
        # tag covering two ranges must become two independent row_tags,
        # each with just its own range, not one row with a combined
        # range or two rows sharing a mutable range list.
        tag = FakeStyledTextTag("Fontcolor", "#ff0000", [(0, 5), (6, 11)])
        note = FakeNote("hello world", [tag])
        rows = build_row_data(note)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][3], "hello")
        self.assertEqual(rows[1][3], "world")
        self.assertEqual(rows[0][0].ranges, [(0, 5)])
        self.assertEqual(rows[1][0].ranges, [(6, 11)])
        self.assertEqual(rows[0][2], "#ff0000")
        self.assertEqual(rows[1][2], "#ff0000")

    def test_value_none_normalized_to_empty_string_for_display(self):
        tag = FakeStyledTextTag("Italic", None, [(0, 3)])
        note = FakeNote("abcdef", [tag])
        _row_tag, _name, value, _snippet = build_row_data(note)[0]
        self.assertEqual(value, "")

    def test_rows_sorted_by_start_regardless_of_tag_order(self):
        # Two separate tags whose ranges are given out of start order --
        # the note's own tags list order must not leak into the result.
        tag_late = FakeStyledTextTag("Bold", None, [(10, 15)])
        tag_early = FakeStyledTextTag("Italic", None, [(0, 3)])
        note = FakeNote("0123456789012345", [tag_late, tag_early])
        rows = build_row_data(note)
        self.assertEqual([row[1] for row in rows], ["Italic", "Bold"])

    def test_equal_start_subsorts_by_end(self):
        # Same start, different end: the shorter range sorts first.
        tag_long = FakeStyledTextTag("Fontcolor", "#ff0000", [(0, 10)])
        tag_short = FakeStyledTextTag("Bold", None, [(0, 3)])
        note = FakeNote("0123456789", [tag_long, tag_short])
        rows = build_row_data(note)
        self.assertEqual([row[1] for row in rows], ["Bold", "Fontcolor"])

    def test_multiple_ranges_of_one_tag_come_out_in_start_order(self):
        # A single multi-range tag whose ranges are stored out of order
        # (start descending) must still be split and sorted ascending.
        tag = FakeStyledTextTag("Highlight", None, [(6, 11), (0, 5)])
        note = FakeNote("hello world", [tag])
        rows = build_row_data(note)
        self.assertEqual([row[3] for row in rows], ["hello", "world"])


class KeptTagsAfterClearTest(unittest.TestCase):
    def test_no_rows_checked_keeps_everything(self):
        tags = [
            FakeStyledTextTag("Bold", None, [(0, 1)]),
            FakeStyledTextTag("Italic", None, [(1, 2)]),
        ]
        kept = kept_tags_after_clear(tags, [False, False])
        self.assertEqual(kept, tags)

    def test_checked_row_is_removed(self):
        bold = FakeStyledTextTag("Bold", None, [(0, 1)])
        italic = FakeStyledTextTag("Italic", None, [(1, 2)])
        kept = kept_tags_after_clear([bold, italic], [True, False])
        self.assertEqual(kept, [italic])

    def test_all_checked_clears_everything(self):
        tags = [
            FakeStyledTextTag("Bold", None, [(0, 1)]),
            FakeStyledTextTag("Italic", None, [(1, 2)]),
        ]
        kept = kept_tags_after_clear(tags, [True, True])
        self.assertEqual(kept, [])

    def test_mismatched_lengths_zip_truncates_silently(self):
        # Documents current behaviour rather than asserting it's ideal:
        # zip() stops at the shorter list, so a caller bug that supplies
        # a shorter checked_flags list silently drops the unmatched
        # trailing tags from the kept result (rather than keeping them,
        # or raising). Caller (cb_clear_markup) always builds both lists
        # from the same self.row_widgets pass in lockstep, so this
        # shouldn't occur in practice.
        tags = [FakeStyledTextTag("Bold", None, [(0, 1)])]
        kept = kept_tags_after_clear(tags, [])
        self.assertEqual(kept, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
