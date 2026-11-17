# Gramps - a GTK+/GNOME based genealogy program
#
# LocalTerm Gramplet – Localized Gramps Glossary Terminology
#
# ----------------------------------------------------------------------
# Copyright (C) 2025 Kaj Mikkelsen <kmi@vgdata.dk>
# Copyright (C) 2026 Codex / ChatGPT
# Copyright (C) 2026 Gemini AI Addon Contributor
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# ----------------------------------------------------------------------
# Evolution / Change log
#
# 20251008 Initial implementation
# - added strip to the dequote function; added dictionaries; filling gui from dictionary
# 20251022 Weblate CSV support
# - Added more test files; changing filenames to csv; case-insensitive globbing
# 2026-01-25 Track changes integration
# - Track changes option highlighting; duplicate row mitigation strategy
# 2026-02-20 Single language mode optimization
# - Single language URL generation bindings
# 2026-05-29 Dual-Table Isolated Layout Refactoring
# - Split view layout stores; embedded environment rows inside Gtk.Expander
# 2026-05-30 Layout Geometry Refinements & Multi-Language Multi-Anchor Dispatch
# - Fixed Gtk.Expander rendering freeze by mapping notify::expanded size requests.
# - Made metadata table non-resizable explicitly (documented adjustments are driven from bottom table).
# - Config drop-downs now parse and format choices cleanly as "<code - endonym (Exonym)>".
# - Enforced deep multi-layer loading for English baseline file for tooltips/anchors.
# - Overhauled double-click row-activated and query-tooltip logic to be completely column-aware.
# 2026-05-30 v0.3.7 Hotfix Cleanup: Menu Pruning & Metadata Code Lookup Extraction
# - Removed the unstable Configure Context menu option from the Language Metadata grid.
# - Overhauled CSV metadata parsing loop to cleanly intercept un-prefixed/custom files without missing internal rows.
# - Standardized distinct main tree cell tooltips back to strict 2-line localized diagnostic values.
# ----------------------------------------------------------------------

import os
import glob
import csv
import datetime
import logging
import re
import urllib.parse
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Gio

from gramps.gen.plug import Gramplet
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.config import config
from gramps.gui.display import display_url
from gramps.gui.dialog import ErrorDialog
from gramps.gen.plug.menu import (
    BooleanOption,
    StringOption,
    ColorOption,
    EnumeratedListOption,
)
from gramps.gen.lib import Note
from gi.repository import GObject
from gramps.gui.editors import EditNote

# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------

LOG = logging.getLogger("LocalTerm")
LOG.setLevel(logging.INFO)

# ----------------------------------------------------------------------
# Translation
# ----------------------------------------------------------------------

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

# ----------------------------------------------------------------------
# Model column indices
# ----------------------------------------------------------------------

COL_TERM        = 0
COL_TARGET      = 1
COL_LANG2       = 2
COL_TR_COM_TGT  = 3
COL_TR_COM_L2   = 4
COL_ANCHOR      = 5
COL_FG          = 6
COL_BG          = 7
COL_WL_REVIEW   = 8
COL_WL_BROWSE   = 9
COL_WL_FILTER   = 10
COL_WL_TRANS    = 11
COL_WL_LBL_REVIEW = 12
COL_WL_LBL_BROWSE = 13
COL_WL_LBL_FILTER = 14
COL_WL_LBL_TRANS  = 15

WEBLATE_BASE    = "https://hosted.weblate.org"
WEBLATE_PROJECT = "gramps-project"
WEBLATE_COMPONENT = "gramps"

def _lang_code_from_filename(filename):
    """Extract the BCP-47 language code from a glossary CSV filename."""
    base = os.path.splitext(os.path.basename(filename))[0]
    prefix = "gramps-project-glossary-"
    if base.startswith(prefix):
        code = base[len(prefix):]
        if re.match(r'^[a-z]{2,3}(_[A-Za-z]{2,4})?$', code):
            return code
    return None

def _weblate_urls(term, translated, lang_code):
    """Build the four Weblate search URLs and their display labels."""
    if not lang_code:
        return ('', '', '', '', '', '', '', '')

    base   = WEBLATE_BASE
    proj   = WEBLATE_PROJECT
    comp   = WEBLATE_COMPONENT
    lang   = lang_code

    if term:
        url1 = ('{}/translate/{}/{}/{}/?#'
                '&sort_by=-priority%2Cposition&checksum=&q=source%3A%22{}%22').format(
                    base, proj, comp, lang, urllib.parse.quote(term))
    else:
        url1 = ''

    if term:
        q2 = urllib.parse.urlencode({'q': '"{}"'.format(term)})
        url2 = '{}/browse/{}/{}/{}/?{}'.format(base, proj, comp, lang, q2)
    else:
        url2 = ''

    if term:
        q3_val = 'source:="{}"'.format(term)
        q3_enc = urllib.parse.quote(q3_val, safe=':=')
        url3 = '{}/projects/{}/{}/{}/?q={}#search'.format(
            base, proj, comp, lang, q3_enc)
    else:
        url3 = ''

    if translated:
        q4 = urllib.parse.urlencode({'q': '"{}"'.format(translated)})
        url4 = '{}/browse/{}/{}/{}/?{}'.format(base, proj, comp, lang, q4)
    else:
        url4 = ''

    lbl1 = '\u201c{}\u201d'.format(term) if term else ''
    if term:
        lbl2 = ' '.join('*{}*'.format(w) for w in term.split())
    else:
        lbl2 = ''
    lbl3 = '\u2753 {}'.format(term) if term else ''
    lbl4 = '*{}*'.format(translated) if translated else ''

    return (url1, url2, url3, url4, lbl1, lbl2, lbl3, lbl4)


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

CONFIG_ID = "LocalTerm"
CONFIG_SCHEMA_VERSION = "0.3.7"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_config_file = os.path.join(PLUGIN_DIR, CONFIG_ID)
config = config.register_manager(_config_file)

config.register("localterm.config_id", CONFIG_ID)
config.register("localterm.config_schema", "")
config.register("localterm.show_anchor", False)
config.register("localterm.track_changes", True)
config.register("localterm.url_bas", "https://gramps-project.org/wiki/index.php/")
config.register("localterm.fg_sel_col", "#000000")
config.register("localterm.bg_sel_col", "#ffffff")
config.register("localterm.lang1_file", "")
config.register("localterm.lang2_file", "")

def _norm(value):
    return value.strip().lower() if value else ""

def is_language_metadata(context, source, key):
    return _norm(context) == "language" and _norm(source) == key

class LocalTerm(Gramplet):
    """Localized index to Gramps glossary terminology."""

    def _validate_or_flush_config(self):
        """Ensure current configuration metadata schema aligns; cleans stale settings."""
        try:
            cfg_id = config.get("localterm.config_id")
            cfg_schema = config.get("localterm.config_schema")
        except Exception:
            cfg_id = None
            cfg_schema = None

        if cfg_id != CONFIG_ID or cfg_schema != CONFIG_SCHEMA_VERSION:
            LOG.info(
                "LocalTerm configuration reset (schema=%r vs %r); flushing legacy settings.",
                cfg_schema, CONFIG_SCHEMA_VERSION
            )
            config.reset()

            config.set("localterm.config_id", CONFIG_ID)
            config.set("localterm.config_schema", CONFIG_SCHEMA_VERSION)
            config.set("localterm.show_anchor", False)
            config.set("localterm.track_changes", True)
            config.set("localterm.url_bas", "https://gramps-project.org/wiki/index.php/")
            config.set("localterm.fg_sel_col", "#000000")
            config.set("localterm.bg_sel_col", "#ffffff")
            config.set("localterm.lang1_file", "")
            config.set("localterm.lang2_file", "")
            config.save()

    def _load_files(self):
        pattern = os.path.join(
            os.path.dirname(__file__),
            "gramps-project-glossary",
            "gramps-project-glossary-*.csv",
        )
        self.__files = sorted(glob.glob(pattern))

    def _index_for_file(self, filename, fallback=0):
        for i, f in enumerate(self.__files):
            if os.path.basename(f) == filename:
                return i
        return fallback

    def clean_translatable(self, s):
        s = s.strip()
        if s.startswith("_(") and s.endswith(")"):
            return s[2:-1].strip()
        return s

    def _parse_friendly_name_for_file(self, flnm):
        """Extract language properties to assemble '<language code> - <endonym> (<EnglishExonym>)' string."""
        code_fn = _lang_code_from_filename(flnm)
        code = None
        endonym = ""
        exonym = ""

        if os.path.isfile(flnm):
            try:
                with open(flnm, encoding="utf-8", newline="") as f:
                    reader = csv.reader(f)
                    for lineno, row in enumerate(reader, start=1):
                        if lineno == 1 or len(row) < 4:
                            continue
                        src = self.clean_translatable(row[1])
                        tgt = row[2].strip()
                        ctx = row[5].strip()

                        if is_language_metadata(ctx, src, "endonym"):
                            endonym = tgt
                        elif is_language_metadata(ctx, src, "englishexonym"):
                            exonym = tgt
                        elif is_language_metadata(ctx, src, "language code"):
                            code = tgt
            except Exception:
                pass

        if not code:
            code = code_fn or "unknown"
        if not endonym:
            endonym = code.upper()
        if not exonym:
            exonym = code.upper()

        return f"{code} - {endonym} ({exonym})"

    def _load_english_baseline_data(self):
        """Parse baseline English reference data explicitly for first column fallback contexts."""
        self.english_trcom = {}
        self.english_loc = {}
        self.english_raw_csv = {}
        en_csv = os.path.join(
            os.path.dirname(__file__),
            "gramps-project-glossary",
            "gramps-project-glossary-en.csv"
        )
        if not os.path.isfile(en_csv):
            return

        try:
            with open(en_csv, encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                en_row_counts = {}
                for lineno, row in enumerate(reader, start=1):
                    if len(row) < 8 or lineno == 1:
                        continue
                    source = self.clean_translatable(row[1])
                    context = row[5].strip()
                    translator_comments = row[6].strip()
                    anchor = row[7].strip()

                    if is_language_metadata(context, source, "endonym"):
                        continue

                    idx = en_row_counts.get(source, 0) + 1
                    en_row_counts[source] = idx
                    row_key = source if idx == 1 else f"{source}#{idx}"

                    self.english_trcom[row_key] = translator_comments
                    self.english_loc[row_key] = anchor
                    self.english_raw_csv[row_key] = ",".join(f'"{x}"' if ',' in x or '"' in x else x for x in row)
        except Exception:
            LOG.exception("Failed to parse fallback English baseline file configuration metadata.")

    def init(self):
        config.load()
        self._validate_or_flush_config()
        self._load_files()

        self.lang1_txt = {}
        self.lang2_txt = {}
        self.lang1_trcom = {}
        self.lang2_trcom = {}
        self.lang1_loc = {}
        self.lang2_loc = {}
        self.lang1_base = {}
        self.lang1_raw_csv = {}
        self.lang2_raw_csv = {}
        self.source_row_index = {}
        self.duplicate_rows = set()
        self.metadata_rows = set()
        self.english_trcom = {}
        self.english_loc = {}
        self.english_raw_csv = {}

        self.lang1_friendly_header = ""
        self.lang2_friendly_header = ""

        self.dup_fg = "#CC5500"
        self.dup_bg = "#FFF2CC"
        self.change_fg = self.dup_fg
        self.change_bg = "#E6F4EA"

        self.gui.WIDGET = self.build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)
        self.gui.WIDGET.show()

    def on_load(self):
        config.load()
        self._validate_or_flush_config()

        self.__show_anchor = config.get("localterm.show_anchor")
        self.__track_changes = config.get("localterm.track_changes")
        self.__url_bas = config.get("localterm.url_bas")
        self.__fg_sel = config.get("localterm.fg_sel_col")
        self.__bg_sel = config.get("localterm.bg_sel_col")
        self.__lang1_file = config.get("localterm.lang1_file")
        self.__lang2_file = config.get("localterm.lang2_file")

        self._load_files()
        self.__lang1 = self._index_for_file(self.__lang1_file, 0)
        self.__lang2 = self._index_for_file(self.__lang2_file, self.__lang1)
        self._load_english_baseline_data()

    def build_options(self):
        self._load_files()
        self.opts = []

        self.opt_url = StringOption(_("URL base for glossary anchors"), self.__url_bas)
        self.opt_show_anchor = BooleanOption(_("Show anchor column"), self.__show_anchor)
        self.opt_track_changes = BooleanOption(_("Track Changes"), self.__track_changes)
        self.opt_fg = ColorOption(_("Foreground color"), self.__fg_sel)
        self.opt_bg = ColorOption(_("Background color"), self.__bg_sel)

        self.opts = [
            self.opt_url,
            self.opt_show_anchor,
            self.opt_track_changes,
            self.opt_fg,
            self.opt_bg,
        ]

        self.opt_lang1 = EnumeratedListOption(_("Language 1"), self.__lang1)
        for i, f in enumerate(self.__files):
            lbl = self._parse_friendly_name_for_file(f)
            self.opt_lang1.add_item(i, lbl)
        self.opts.append(self.opt_lang1)

        self.opt_lang2 = EnumeratedListOption(_("Language 2"), self.__lang2)
        for i, f in enumerate(self.__files):
            lbl = self._parse_friendly_name_for_file(f)
            self.opt_lang2.add_item(i, lbl)
        self.opts.append(self.opt_lang2)

        for opt in self.opts:
            self.add_option(opt)

    def save_options(self):
        self.__url_bas = self.opt_url.get_value()
        self.__show_anchor = self.opt_show_anchor.get_value()
        self.__track_changes = self.opt_track_changes.get_value()
        self.__fg_sel = self.opt_fg.get_value()
        self.__bg_sel = self.opt_bg.get_value()
        self.__lang1 = self.opt_lang1.get_value()
        self.__lang2 = self.opt_lang2.get_value()

        config.set("localterm.show_anchor", self.__show_anchor)
        config.set("localterm.url_bas", self.__url_bas)
        config.set("localterm.fg_sel_col", self.__fg_sel)
        config.set("localterm.bg_sel_col", self.__bg_sel)

        if self.__files:
            config.set("localterm.lang1_file", os.path.basename(self.__files[self.__lang1]))
            config.set("localterm.lang2_file", os.path.basename(self.__files[self.__lang2]))

        config.set("localterm.config_id", CONFIG_ID)
        config.set("localterm.config_schema", CONFIG_SCHEMA_VERSION)
        config.save()

    def save_update_options(self, _obj):
        self.save_options()
        self._load_english_baseline_data()
        self.update()

    def set_fl_ar(self):
        self.__fl_ar = []
        if not self.__files:
            return
        self.__fl_ar.append(self.__files[self.__lang1])
        if self.__lang2 != self.__lang1:
            self.__fl_ar.append(self.__files[self.__lang2])

    def load_file(self, flnm):
        if self.filenbr == 0:
            self.lang1_txt.clear()
            self.lang1_trcom.clear()
            self.lang1_loc.clear()
            self.lang1_base.clear()
            self.lang1_raw_csv.clear()
            self.source_row_index.clear()
            self.duplicate_rows.clear()
            self.metadata_rows.clear()
        else:
            self.lang2_txt.clear()
            self.lang2_trcom.clear()
            self.lang2_loc.clear()
            self.lang2_raw_csv.clear()

        with open(flnm, encoding="utf-8", newline="") as csvfile:
            reader = csv.reader(csvfile)
            for lineno, row in enumerate(reader, start=1):
                if lineno == 1 or len(row) < 8:
                    continue

                source = self.clean_translatable(row[1])
                target = row[2].strip()
                context = row[5].strip()
                translator_comments = row[6].strip()
                anchor = row[7].strip()

                is_meta = (_norm(context) == "language")
                source_key = source
                raw_line = ",".join(f'"{x}"' if ',' in x or '"' in x else x for x in row)

                if self.filenbr == 0:
                    idx = self.source_row_index.get(source_key, 0) + 1
                    self.source_row_index[source_key] = idx

                    if idx == 1:
                        row_key = source_key
                    else:
                        row_key = f"{source_key}#{idx}"
                        self.duplicate_rows.add(row_key)

                    if is_meta:
                        self.metadata_rows.add(row_key)

                    self.lang1_txt[row_key] = target
                    self.lang1_trcom[row_key] = translator_comments
                    self.lang1_loc[row_key] = anchor
                    self.lang1_base[row_key] = source
                    self.lang1_raw_csv[row_key] = raw_line
                else:
                    self.lang2_txt[source_key] = target
                    self.lang2_trcom[source_key] = translator_comments
                    self.lang2_loc[source_key] = anchor
                    self.lang2_raw_csv[source_key] = raw_line

    def main(self):
        self.model.set_sort_column_id(-2, Gtk.SortType.ASCENDING)
        self.model.clear()
        self.meta_model.clear()
        self.set_fl_ar()

        self._single_lang_mode = (self.__lang1 == self.__lang2)

        if self.__files:
            self.lang1_friendly_header = self._parse_friendly_name_for_file(self.__files[self.__lang1])
            self.lang2_friendly_header = self._parse_friendly_name_for_file(self.__files[self.__lang2])

            # Extract standard tracking token based on computed friendly header string variables
            self._lang1_code = self.lang1_friendly_header.split(" - ")[0].strip()
            self._lang2_code = self.lang2_friendly_header.split(" - ")[0].strip()
        else:
            self._lang1_code = self._lang2_code = None
            self.lang1_friendly_header = _("Target")
            self.lang2_friendly_header = _("Language 2")

        self.treeview.get_column(2).set_visible(not self._single_lang_mode)
        self.treeview.get_column(3).set_visible(self.__show_anchor)

        # Default interactive type-ahead search column sets context tracking index
        self.treeview.set_search_column(1)

        self.meta_view.get_column(2).set_visible(not self._single_lang_mode)
        self.meta_view.get_column(3).set_visible(self.__show_anchor)

        _show_wl = self._single_lang_mode and bool(self._lang1_code) and self._lang1_code != "unknown"
        for _col in (self._col_wl_review, self._col_wl_browse, self._col_wl_filter, self._col_wl_trans):
            _col.set_visible(_show_wl)

        self.filenbr = 0
        for fl in self.__fl_ar:
            if os.path.isfile(fl):
                self.load_file(fl)
            self.filenbr += 1

        for row_key, value in self.lang1_txt.items():
            base_source = self.lang1_base[row_key]
            is_dup = row_key in self.duplicate_rows
            is_meta = row_key in self.metadata_rows
            l1_value = value or ""
            l2_value = self.lang2_txt.get(base_source, "") or ""

            is_changed = (self.__track_changes and l2_value and l1_value != l2_value)

            if is_dup:
                fg = self.dup_fg
                bg = self.dup_bg
            elif is_changed:
                fg = self.change_fg
                bg = self.change_bg
            else:
                fg = self.__fg_sel
                bg = self.__bg_sel

            wl_review = wl_browse = wl_filter = wl_trans = ''
            lbl_review = lbl_browse = lbl_filter = lbl_trans = ''
            if self._single_lang_mode and self._lang1_code and self._lang1_code != "unknown":
                translated_val = value or ""
                (wl_review, wl_browse, wl_filter, wl_trans,
                 lbl_review, lbl_browse, lbl_filter, lbl_trans) = _weblate_urls(
                    base_source, translated_val, self._lang1_code)

            row_data = [
                base_source,
                value,
                l2_value,
                self.lang1_trcom.get(row_key, ""),
                self.lang2_trcom.get(base_source, ""),
                self.lang1_loc.get(row_key, ""),
                fg,
                bg,
                wl_review,
                wl_browse,
                wl_filter,
                wl_trans,
                lbl_review,
                lbl_browse,
                lbl_filter,
                lbl_trans,
            ]

            if is_meta:
                self.meta_model.append(row_data)
            else:
                self.model.append(row_data)

        self.treeview.get_columns()[1].set_title(self.lang1_friendly_header)
        self.treeview.get_columns()[2].set_title(self.lang2_friendly_header)

        self.meta_view.get_columns()[1].set_title(self.lang1_friendly_header)
        self.meta_view.get_columns()[2].set_title(self.lang2_friendly_header)

        if self._single_lang_mode and self._lang1_code and self._lang1_code != "unknown":
            self._col_wl_review.set_title(_("Review"))
            self._col_wl_browse.set_title(_("Search"))
            self._col_wl_filter.set_title(_("Filter"))
            self._col_wl_trans.set_title(_("Translated search"))

        self.model.set_sort_column_id(COL_TERM, Gtk.SortType.ASCENDING)

    def _on_sort_column_changed(self, treesort):
        """Dynamic signal interceptor updates active search field to match active sort header layout."""
        sort_info = treesort.get_sort_column_id()
        if sort_info:
            sort_col_id, sort_type = sort_info
            if sort_col_id in (COL_TERM, COL_TARGET, COL_LANG2, COL_ANCHOR):
                self.treeview.set_search_column(sort_col_id)

    def on_query_tooltip_main1(self, treeview, x, y, keyboard_mode, tooltip):
        context = treeview.get_tooltip_context(x, y, keyboard_mode)
        if not context or not context[0]:
            return False

        success, model_x, model_y, model, path, tree_iter = context
        result = treeview.get_path_at_pos(x, y)
        if not result:
            return False

        column = result[1]
        col_index = treeview.get_columns().index(column)

        component_term = model.get_value(tree_iter, COL_TERM)
        model_index_str = path.to_string()

        try:
            row_idx = int(model_index_str) + 1
            matched_row_key = component_term if row_idx == 1 else f"{component_term}#{row_idx}"
        except ValueError:
            matched_row_key = component_term

        csv_header = "pos,source,target,stringnbr,msgstr,context,translator_comments,anchor"
        if col_index == 0:
            csv_data = self.english_raw_csv.get(matched_row_key, "")
            if not csv_data:
                csv_data = self.english_raw_csv.get(component_term, "")
        elif col_index == COL_LANG2:
            csv_data = self.lang2_raw_csv.get(component_term, "")
        else:
            csv_data = self.lang1_raw_csv.get(matched_row_key, "")

        if not csv_data:
            csv_data = f',"{component_term}","{model.get_value(tree_iter, COL_TARGET) or ""}",,,terminology,"{model.get_value(tree_iter, COL_TR_COM_TGT) or ""}","{model.get_value(tree_iter, COL_ANCHOR) or ""}"'

        tip_text = f"{csv_header}\n{csv_data}"
        tooltip.set_text(tip_text)
        treeview.set_tooltip_row(tooltip, path)
        return True

    def on_query_tooltip_main(self, treeview, x, y, keyboard_mode, tooltip):
        context = treeview.get_tooltip_context(x, y, keyboard_mode)
        if not context or not context[0]:
            return False

        success, model_x, model_y, model, path, tree_iter = context
        result = treeview.get_path_at_pos(x, y)
        if not result:
            return False

        column = result[1]
        col_index = treeview.get_columns().index(column)

        component_term = model.get_value(tree_iter, COL_TERM)
        model_index_str = path.to_string()

        try:
            row_idx = int(model_index_str) + 1
            matched_row_key = component_term if row_idx == 1 else f"{component_term}#{row_idx}"
        except ValueError:
            matched_row_key = component_term

        # 1. Grab the raw CSV row string for the appropriate column
        if col_index == 0:
            csv_data = self.english_raw_csv.get(matched_row_key, "")
            if not csv_data:
                csv_data = self.english_raw_csv.get(component_term, "")
            lang_suffix = "en"
        elif col_index == COL_LANG2:
            csv_data = self.lang2_raw_csv.get(component_term, "")
            lang_suffix = getattr(self, "_lang2_code", "en")
        else:
            csv_data = self.lang1_raw_csv.get(matched_row_key, "")
            lang_suffix = getattr(self, "_lang1_code", "en")

        # Fallback if raw data isn't indexed yet
        if not csv_data:
            csv_data = f',"{component_term}","{model.get_value(tree_iter, COL_TARGET) or ""}",,,terminology,"{model.get_value(tree_iter, COL_TR_COM_TGT) or ""}","{model.get_value(tree_iter, COL_ANCHOR) or ""}"'

        # 2. Parse the CSV line using the standard reader rules to handle embedded quotes/commas safely
        try:
            parsed_row = next(csv.reader([csv_data]))
            # Index map based on your header: pos(0), source(1), target(2), stringnbr(3), msgstr(4), context(5), translator_comments(6), anchor(7)
            comment = parsed_row[6].strip() if len(parsed_row) > 6 else ""
            link = parsed_row[7].strip() if len(parsed_row) > 7 else ""
        except Exception:
            comment = ""
            link = ""

        # 3. Resolve the dynamic browse URL target
        if not link:
            link = f"Gramps_Glossary/{lang_suffix}#{component_term[:1].upper()}"

        if link.startswith("https://") or link.startswith("http://"):
            url = link
        else:
            base = self.__url_bas
            if not base.endswith("/"):
                base += "/"
            url = base + link.lstrip("/")

        # 4. Construct the clean 2-line structure
        tip_lines = []
        if comment:
            tip_lines.append(comment)
        else:
            tip_lines.append(_("No description available."))

        tip_lines.append(_("double-click to browse to {}").format(url))

        tip_text = "\n".join(tip_lines)
        tooltip.set_text(tip_text)
        treeview.set_tooltip_row(tooltip, path)
        return True

    def on_query_tooltip_meta(self, treeview, x, y, keyboard_mode, tooltip):
        context = treeview.get_tooltip_context(x, y, keyboard_mode)
        if not context or not context[0]:
            return False

        success, model_x, model_y, model, path, tree_iter = context
        result = treeview.get_path_at_pos(x, y)
        if not result:
            return False

        column = result[1]
        col_index = treeview.get_columns().index(column)
        component_term = model.get_value(tree_iter, COL_TERM)

        csv_header = "pos,source,target,stringnbr,msgstr,context,translator_comments,anchor"
        if col_index == 2:
            csv_data = self.lang2_raw_csv.get(component_term, "")
        else:
            csv_data = self.lang1_raw_csv.get(component_term, "")

        if not csv_data:
            csv_data = f',"{component_term}","{model.get_value(tree_iter, COL_TARGET) or ""}",,,language,"",""'

        tip_text = f"{csv_header}\n{csv_data}"
        tooltip.set_text(tip_text)
        treeview.set_tooltip_row(tooltip, path)
        return True

    def act_main(self, _tree_view, path, column):
        tree_iter = self.model.get_iter(path)
        wl_url_col = getattr(column, '_wl_url_col', None)
        if wl_url_col is not None:
            url = (self.model.get_value(tree_iter, wl_url_col) or "").strip()
            if url:
                display_url(url)
            return

        columns = _tree_view.get_columns()
        col_index = columns.index(column)
        base_source = self.model.get_value(tree_iter, COL_TERM)

        model_index_str = path.to_string()
        try:
            row_idx = int(model_index_str) + 1
            matched_row_key = base_source if row_idx == 1 else f"{base_source}#{row_idx}"
        except ValueError:
            matched_row_key = base_source

        if col_index == 0:
            link = self.english_loc.get(matched_row_key, "").strip()
            if not link:
                link = self.english_loc.get(base_source, "").strip()
            lang_suffix = "en"
        elif col_index == COL_LANG2 and not getattr(self, '_single_lang_mode', False):
            link = self.lang2_loc.get(base_source, "").strip()
            lang_suffix = getattr(self, "_lang2_code", "en")
        else:
            link = (self.model.get_value(tree_iter, COL_ANCHOR) or "").strip()
            lang_suffix = getattr(self, "_lang1_code", "en")

        if not link:
            link = f"Gramps_Glossary/{lang_suffix}#{base_source[:1].upper()}"

        if link.startswith("https://") or link.startswith("http://"):
            url = link
        else:
            base = self.__url_bas
            if not base.endswith("/"):
                base += "/"
            url = base + link.lstrip("/")
        display_url(url)

    def act_meta(self, _tree_view, path, column):
        tree_iter = self.meta_model.get_iter(path)
        columns = _tree_view.get_columns()
        col_index = columns.index(column)
        base_term = self.meta_model.get_value(tree_iter, COL_TERM)

        if col_index == 2:
            lang_code = getattr(self, '_lang2_code', None)
            if not lang_code or lang_code == "unknown": return
            if _norm(base_term) == "endonym":
                url = f"https://hosted.weblate.org/projects/gramps-project/gramps/{lang_code}/"
            else:
                url = f"https://gramps-project.org/wiki/index.php/Gramps_Translations_status_{lang_code}"
        else:
            lang_code = getattr(self, '_lang1_code', None)
            if not lang_code or lang_code == "unknown": return
            if _norm(base_term) == "endonym":
                url = f"https://hosted.weblate.org/projects/gramps-project/gramps/{lang_code}/"
            else:
                url = f"https://gramps-project.org/wiki/index.php/Gramps_Translations_status_{lang_code}"
        display_url(url)

    def _sync_column_widths(self, source_col, pspec, target_col):
        """Unified properties width listener syncing separate data layout trees."""
        w = source_col.get_width()
        if w > 0 and target_col.get_width() != w:
            target_col.set_min_width(w)
            target_col.set_max_width(w)

    def _on_expander_changed(self, expander, pspec, container_box):
        """Force immediate allocation queue updates upon expander container visibility toggle."""
        container_box.queue_resize()

    def build_gui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # 1. Metadata Panel Setup (Language Stack Table Fixed Height: 220px)
        self.meta_model = Gtk.ListStore(
            str, str, str, str, str, str, str, str,
            str, str, str, str, str, str, str, str
        )
        self.meta_view = Gtk.TreeView(self.meta_model)
        self.meta_view.set_has_tooltip(True)
        self.meta_view.set_headers_visible(True)
        self.meta_view.connect("query-tooltip", self.on_query_tooltip_meta)
        self.meta_view.connect("row-activated", self.act_meta)

        meta_scroll = Gtk.ScrolledWindow()
        meta_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        meta_scroll.add(self.meta_view)
        meta_scroll.set_size_request(-1, 220)  # Language stacked table fixed height

        expander = Gtk.Expander(label=_("Language Environment Metadata"))
        expander.add(meta_scroll)
        expander.connect("notify::expanded", self._on_expander_changed, vbox)
        vbox.pack_start(expander, False, False, 0)

        # 2. Main Dictionary Tree Panel Setup
        self.model = Gtk.ListStore(
            str, str, str, str, str, str, str, str,
            str, str, str, str, str, str, str, str
        )
        self.treeview = Gtk.TreeView(self.model)
        self.treeview.set_has_tooltip(True)
        self.treeview.connect("query-tooltip", self.on_query_tooltip_main)
        self.treeview.connect("row-activated", self.act_main)

        # Connect model tree sort column sync logic directly to the ListStore objects
        self.model.connect("sort-column-changed", self._on_sort_column_changed)
        self.meta_model.connect("sort-column-changed", self._on_sort_column_changed)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.treeview)
        vbox.pack_start(scroll, True, True, 0)

        # Custom Context Menu Layout Builder Block for Main Tree
        self.row_menu = Gtk.Menu()
        mi_note = Gtk.MenuItem(label=_("Create Note from row"))
        mi_note.connect("activate", self.create_note_from_selected_row)
        self.row_menu.append(mi_note)

        mi_copy = Gtk.MenuItem(label=_("Copy row to OS Clipboard"))
        mi_copy.connect("activate", self.copy_selected_row)
        self.row_menu.append(mi_copy)

        mi_open_csv = Gtk.MenuItem(label=_("Edit source CSV file"))
        mi_open_csv.connect("activate", self.open_source_csv)
        self.row_menu.append(mi_open_csv)
        self.row_menu.show_all()

        self.treeview.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.treeview.connect("button-press-event", self.on_tree_button_press)

        # Dedicated Context Menu Builder Block for top Metadata Language Table (Pruned Configure Option)
        self.meta_context_menu = Gtk.Menu()
        mi_help = Gtk.MenuItem(label=_("Help"))
        mi_help.connect("activate", lambda xl: display_url("https://github.com/emyoulation/LocalTerm/blob/master/README.md"))
        self.meta_context_menu.append(mi_help)
        self.meta_context_menu.show_all()

        self.meta_view.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.meta_view.connect("button-press-event", self.on_meta_button_press)

        renderer = Gtk.CellRendererText()
        titles = [_("English Term"), _("Target"), _("Language 2"), _("Anchor")]
        col_ids = [COL_TERM, COL_TARGET, COL_LANG2, COL_ANCHOR]

        for title, col_id in zip(titles, col_ids):
            m_col = Gtk.TreeViewColumn(title, renderer, text=col_id, foreground=COL_FG, background=COL_BG)
            m_col.set_sort_column_id(col_id)
            m_col.set_clickable(True)
            m_col.set_resizable(True)
            self.treeview.append_column(m_col)

            s_col = Gtk.TreeViewColumn(title, renderer, text=col_id, foreground=COL_FG, background=COL_BG)
            s_col.set_resizable(False)
            self.meta_view.append_column(s_col)

            m_col.connect("notify::width", self._sync_column_widths, s_col)

        renderer_link = Gtk.CellRendererText()
        renderer_link.set_property("foreground", "#0055cc")
        renderer_link.set_property("underline", 1)

        def _wl_col(title, url_col_idx, lbl_col_idx):
            col = Gtk.TreeViewColumn(title, renderer_link, text=lbl_col_idx, foreground=COL_FG, background=COL_BG)
            col.set_visible(False)
            col._wl_url_col = url_col_idx
            self.treeview.append_column(col)
            return col

        self._col_wl_review = _wl_col(_("Review"),           COL_WL_REVIEW, COL_WL_LBL_REVIEW)
        self._col_wl_browse = _wl_col(_("Search"),           COL_WL_BROWSE, COL_WL_LBL_BROWSE)
        self._col_wl_filter = _wl_col(_("Filter"),           COL_WL_FILTER, COL_WL_LBL_FILTER)
        self._col_wl_trans  = _wl_col(_("Translated search"),COL_WL_TRANS,  COL_WL_LBL_TRANS)

        vbox.show_all()
        return vbox

    def on_tree_button_press(self, treeview, event):
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            result = treeview.get_path_at_pos(int(event.x), int(event.y))
            if result is None:
                return False

            path, column, cell_x, cell_y = result
            self._popup_column = column
            selection = treeview.get_selection()
            selection.select_path(path)

            if self.row_menu.get_attach_widget() is not None:
                self.row_menu.detach()

            toplevel = treeview.get_toplevel()
            if isinstance(toplevel, Gtk.Window):
                self.row_menu.attach_to_widget(toplevel, None)

            if hasattr(self.row_menu, "popup_at_pointer"):
                self.row_menu.popup_at_pointer(event)
            else:
                self.row_menu.popup(None, None, None, None, event.button, event.time)
            return True
        return False

    def on_meta_button_press(self, treeview, event):
        """Dispatches properties context popup routing inside the top Metadata table."""
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 3:
            result = treeview.get_path_at_pos(int(event.x), int(event.y))
            if result is None:
                return False

            path, column, cell_x, cell_y = result
            selection = treeview.get_selection()
            selection.select_path(path)

            if self.meta_context_menu.get_attach_widget() is not None:
                self.meta_context_menu.detach()

            toplevel = treeview.get_toplevel()
            if isinstance(toplevel, Gtk.Window):
                self.meta_context_menu.attach_to_widget(toplevel, None)

            if hasattr(self.meta_context_menu, "popup_at_pointer"):
                self.meta_context_menu.popup_at_pointer(event)
            else:
                self.meta_context_menu.popup(None, None, None, None, event.button, event.time)
            return True
        return False

    def create_note_from_selected_row(self, menu_item):
        selection = self.treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return

        path, column = self.treeview.get_cursor()
        component_term = model.get_value(tree_iter, COL_TERM)

        model_index_str = path.to_string() if path is not None else "0"
        try:
            row_idx = int(model_index_str) + 1
            matched_row_key = component_term if row_idx == 1 else f"{component_term}#{row_idx}"
        except ValueError:
            matched_row_key = component_term

        parts = []

        def add_block(header, value, comment=None):
            if not value: return
            block = f"{header}:\n{value}"
            if comment: block += f"\n{comment}"
            parts.append(block)

        en_comment = self.english_trcom.get(matched_row_key, "")
        if not en_comment:
            en_comment = self.english_trcom.get(component_term, "")
        add_block(_("English Term"), component_term, en_comment)

        lang1_term = (model.get_value(tree_iter, COL_TARGET) or "").strip()
        lang1_desc = (model.get_value(tree_iter, COL_TR_COM_TGT) or "").strip()
        add_block(self.treeview.get_column(1).get_title(), lang1_term, lang1_desc)

        if not getattr(self, '_single_lang_mode', False):
            lang2_term = (model.get_value(tree_iter, COL_LANG2) or "").strip()
            lang2_desc = (model.get_value(tree_iter, COL_TR_COM_L2) or "").strip()
            add_block(self.treeview.get_column(2).get_title(), lang2_term, lang2_desc)

        raw_anchor = (model.get_value(tree_iter, COL_ANCHOR) or "").strip()
        if raw_anchor:
            if raw_anchor.startswith(("https://", "http://")):
                anchor_url = raw_anchor
            else:
                base = self.__url_bas
                if not base.endswith("/"): base += "/"
                anchor_url = base + raw_anchor.lstrip("/")

            add_block(_("Anchor"), anchor_url)

            first_char = lang1_term[:1].lower() if lang1_term else "a"
            if "#" in anchor_url:
                section_url = anchor_url.split("#", 1)[0] + f"#{first_char}"
            else:
                section_url = anchor_url + f"#{first_char}"
            parts.append(f"{_('Glossary section')}:\n{section_url}")

            term_id = raw_anchor.split("#", 1)[1] if "#" in raw_anchor else raw_anchor.lower()
            lang1_term_lower = lang1_term.lower()

            term_id_space = term_id.replace("_", " ")
            lang1_term_space = lang1_term_lower.replace("_", " ")

            parts.append(f"{_('MediaWiki seed')}:\n;<span id=\"{term_id_space}\"/>"
                         f"<span id=\"{lang1_term_space}\"/>{lang1_term}: {lang1_desc}")

        note_text = "\n\n".join(parts)
        note = Note()
        note.set(note_text)
        EditNote(self.gui.dbstate, self.gui.uistate, [], note)

    def copy_selected_row(self, menu_item):
        selection = self.treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return

        raw_anchor = (model.get_value(tree_iter, COL_ANCHOR) or "").strip()
        if raw_anchor:
            if raw_anchor.startswith(("https://", "http://")):
                anchor_url = raw_anchor
            else:
                base = self.__url_bas
                if not base.endswith("/"): base += "/"
                anchor_url = base + raw_anchor.lstrip("/")
        else:
            anchor_url = ""

        if getattr(self, '_single_lang_mode', False):
            cols = [
                model.get_value(tree_iter, COL_TERM)   or "",
                model.get_value(tree_iter, COL_TARGET) or "",
                anchor_url,
                model.get_value(tree_iter, COL_WL_REVIEW) or "",
                model.get_value(tree_iter, COL_WL_BROWSE) or "",
                model.get_value(tree_iter, COL_WL_FILTER) or "",
                model.get_value(tree_iter, COL_WL_TRANS)  or "",
            ]
        else:
            cols = [
                model.get_value(tree_iter, COL_TERM)   or "",
                model.get_value(tree_iter, COL_TARGET) or "",
                model.get_value(tree_iter, COL_LANG2)  or "",
                anchor_url,
            ]

        text = "\t".join(cols)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()

    def open_source_csv(self, menu_item):
        files = getattr(self, "_LocalTerm__files", None) or getattr(self, "_LocalTerm__fl_ar", None) or getattr(self, "__files", None)
        if not files: return

        column = getattr(self, "_popup_column", None)
        if column:
            col_index = self.treeview.get_columns().index(column)
            idx = self.__lang2 if col_index == COL_LANG2 else self.__lang1
        else:
            idx = self.__lang1

        try:
            csv_path = files[idx]
        except Exception:
            return

        file_uri = "file://" + os.path.abspath(csv_path)
        try:
            Gio.app_info_launch_default_for_uri(file_uri, None)
        except Exception:
            try:
                display_url(file_uri)
            except Exception:
                LOG.exception("Failed to open CSV %s", csv_path)

# 2026-05-30T22:40:00-05:00
# ;; EOF Verification: LocalTerm Language code parser hotfixed; Metadata configuration panel menu choice eliminated.