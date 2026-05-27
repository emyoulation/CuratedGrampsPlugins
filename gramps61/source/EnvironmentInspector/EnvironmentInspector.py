#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
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
"""EnvironmentInspector — two-tab reference gramplet for Gramps locale and constants.

Tab 1 — Language
-----------------
Locale and installed-language information from GrampsLocale.

Section headers are Gtk.TextChildAnchor widgets (HBox: Gtk.Image + Gtk.Label).
Clicking the icon copies that section's content to the clipboard:
  - Current Locale icon → copies all field lines.
  - Installed Languages icon → copies the current-language summary line if the
    expander is collapsed, or the full installed-languages list if expanded.

The TextView is set non-focusable (set_can_focus(False)) to prevent the GTK
selection mechanism from drawing black highlights over child-anchor widgets and
the newline characters separating them when clicking headers.

Tab 2 — Gramps Constants
-------------------------
A searchable, sortable list of system properties from ``gramps.gen.const``.
Double-clicking a row triggers default OS actions (folders in file manager,
files in default viewers, text values ignored).
"""

import logging
import os
import re
import sys
import webbrowser

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk

import gramps.gen.const as _gramps_const
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import Gramplet
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gui.utils import open_file_with_default_application

LOG = logging.getLogger(__name__)

# Fallback setup for addon translations inside Gramps environment
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

# Table column definitions
_COL_NAME = 0
_COL_TYPE_ICON = 1
_COL_VIS_ICON = 2
_COL_VALUE = 3
_COL_TYPE_TIP = 4
_COL_VIS_TIP = 5

_ICON_SIZE_TV = 16
_ICON_SIZE_HEADER = 48
_TEXT_LEFT_MARGIN = 5


class _LocaleInfo:
    """Structure wrapper tracking calculated local variations."""
    __slots__ = ("lang_base", "english_name", "region_display", "localedir")

    def __init__(self, lang_base: str, english_name: str, region_display: str, localedir: str) -> None:
        self.lang_base = lang_base
        self.english_name = english_name
        self.region_display = region_display
        self.localedir = localedir


def _load_icon(icon_name: str, size: int) -> GdkPixbuf.Pixbuf | None:
    """Safely lookup and resolve a themed symbolic asset or icon graphic."""
    theme = Gtk.IconTheme.get_default()
    try:
        return theme.load_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)
    except Exception:
        LOG.warning("EnvironmentInspector: icon '%s' not found in theme.", icon_name)
        return None


def _path_status(name: str, value: str) -> str:
    """Analyze a text element to check if it points to local files, remote URLs, or strings."""
    if name.startswith("URL_"):
        return "REMOTE dir"
    try:
        if os.path.isdir(value):
            if sys.platform.startswith("win"):
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(value)
                hidden = attrs != -1 and bool(attrs & 2)
            else:
                hidden = os.path.basename(value).startswith(".")
            return "HIDDEN dir" if hidden else "VISIBLE dir"
        if os.path.isfile(value):
            if value.lower().endswith(".glade"):
                return "GLADE"
            return "FILE"
    except (OSError, ValueError):
        pass
    return "string"


def _status_icons_and_tips(status: str) -> tuple[str, str, str, str]:
    """Provide specific UI visual icon properties and matching translations based on type."""
    if status == "REMOTE dir":
        return ("folder-remote-symbolic", "", _("Remote Directory"), "")
    if status == "HIDDEN dir":
        return ("folder-symbolic", "view-conceal-symbolic", _("Directory"), _("Hidden"))
    if status == "VISIBLE dir":
        return ("folder-symbolic", "view-reveal-symbolic", _("Directory"), _("Not hidden"))
    if status == "GLADE":
        return ("glade-brand-symbolic", "", _("Glade interface layout file"), "")
    if status == "FILE":
        return ("folder-documents-symbolic", "", _("File"), "")
    return ("insert-text", "", _("Value"), "")


def _build_constants_rows() -> list[tuple[str, str, str, str, str, str]]:
    """Enumerate global uppercase variables declared in the Gramps constant namespace."""
    rows: list[tuple[str, str, str, str, str, str]] = []
    for name in dir(_gramps_const):
        if not name.isupper() or name.startswith("_"):
            continue
        value = getattr(_gramps_const, name)
        if not isinstance(value, str):
            continue
        status = _path_status(name, value)
        type_icon, vis_icon, type_tip, vis_tip = _status_icons_and_tips(status)
        rows.append((name, type_icon, vis_icon, value, type_tip, vis_tip))
    rows.sort(key=lambda r: r[0].casefold())

    # Inject an empty padding spacer row that always sorts to the bottom via character boundaries (\xff)
    rows.append(("\xff", "", "", "", "", ""))
    return rows


def _copy_to_clipboard(text: str) -> None:
    """Send arbitrary plain text payloads safely to the desktop clipboard."""
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)
    clipboard.store()


class EnvironmentInspector(Gramplet):
    """Dashboard pane evaluating platform environment parameters and tracking system variables."""

    # ------------------------------------------------------------------
    # Initialization and UI Construction
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Construct structural UI grids and map internal window view layouts."""
        self.set_use_markup(True)
        self._icon_cache = {}
        self._locale_clip_text = ""
        self._selected_type_filter = "All types"

        # Extract the default scroll container provided automatically by Gramps
        orig_sw = self.gui.get_container_widget()
        orig_sw.remove(self.gui.textview)

        # Repurpose and style original text view container elements
        self.gui.textview.set_can_focus(False)
        self.gui.textview.set_left_margin(_TEXT_LEFT_MARGIN)

        lang_sw = Gtk.ScrolledWindow()
        lang_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        lang_sw.add(self.gui.textview)

        const_box = self._build_constants_tab()

        # Consolidate views into tabbed sections
        self._notebook = Gtk.Notebook()
        self._notebook.set_show_border(True)
        self._notebook.append_page(lang_sw, Gtk.Label(label=_("Language")))
        self._notebook.append_page(const_box, Gtk.Label(label=_("Gramps Constants")))

        orig_sw.add(self._notebook)
        orig_sw.show_all()

    def _insert_icon_header(self, icon_name: str, markup: str, clip_callback: object, newline_before: bool = True) -> None:
        """Inject interactive anchor frameworks inside standard Gtk.TextBuffer objects."""
        if newline_before:
            self.append_text("\n")
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ebox = Gtk.EventBox()
        ebox.set_tooltip_text(_("Copy to clipboard"))
        img = Gtk.Image()
        pixbuf = _load_icon(icon_name, _ICON_SIZE_HEADER)
        if pixbuf is not None:
            img.set_from_pixbuf(pixbuf)
        else:
            img.set_from_icon_name(icon_name, Gtk.IconSize.DIALOG)
        ebox.add(img)
        ebox.connect("button-press-event", lambda _w, _e: clip_callback() or True)
        hbox.pack_start(ebox, False, False, 0)

        lbl = Gtk.Label()
        lbl.set_markup(markup)
        lbl.set_xalign(0.0)
        hbox.pack_start(lbl, False, False, 0)
        hbox.show_all()

        buf = self.gui.textview.get_buffer()
        anchor = buf.create_child_anchor(buf.get_end_iter())
        self.gui.textview.add_child_at_anchor(hbox, anchor)
        self.append_text("\n")

    def _insert_language_expander(self, current_lang: str, current_name: str, langs: list[str], code_to_name: dict[str, str]) -> None:
        """Embed an interactive Gtk.Expander container inside a running text flow."""
        summary_markup = f"<i>{current_lang}: {current_name}</i>"
        self._expander = Gtk.Expander()
        self._expander.set_use_markup(True)
        self._expander.set_label(summary_markup)
        self._expander.set_expanded(False)

        all_langs = sorted(langs)
        if current_lang not in all_langs:
            all_langs = [current_lang] + all_langs

        lines = "\n".join(f"  {lang}: {code_to_name.get(lang, _('Unknown'))}" for lang in all_langs)
        inner_label = Gtk.Label(label=lines)
        inner_label.set_xalign(0.0)
        inner_label.set_selectable(False)
        inner_label.set_margin_start(12)
        inner_label.set_margin_top(4)
        inner_label.set_margin_bottom(4)
        self._expander.add(inner_label)
        self._expander.show_all()

        buf = self.gui.textview.get_buffer()
        anchor = buf.create_child_anchor(buf.get_end_iter())
        self.gui.textview.add_child_at_anchor(self._expander, anchor)
        self.append_text("\n")

    # ------------------------------------------------------------------
    # Language Action Callbacks
    # ------------------------------------------------------------------

    def _cb_copy_locale_section(self) -> None:
        """Clipboard helper for the current environment metadata blocks."""
        _copy_to_clipboard(self._locale_clip_text)

    def _cb_copy_language_section(self) -> None:
        """Process specific visible sub-elements context lines for clipboard copying."""
        if self._expander.get_expanded():
            child = self._expander.get_child()
            text = child.get_text() if child else ""
        else:
            raw = self._expander.get_label() or ""
            text = re.sub(r"<[^>]+>", "", raw)
        _copy_to_clipboard(text.strip())

    # ------------------------------------------------------------------
    # Language Parsing & Layout Logic
    # ------------------------------------------------------------------

    def _get_locale_info(self, gl: GrampsLocale) -> _LocaleInfo:
        """Query and unpack localized target environment properties."""
        language_dict = gl.get_language_dict()
        code_to_name = {v: k for k, v in language_dict.items()}
        lang_base = gl.lang.split("_")[0] if gl.lang and "_" in gl.lang else gl.lang
        english_name = code_to_name.get(lang_base, _("Unknown"))
        region = _("N/A")
        variant = None
        if gl.lang and "_" in gl.lang:
            region = gl.lang.split("_", 1)[1]
        if english_name:
            match = re.search(r"\(([^)]+)\)", english_name)
            if match:
                variant = match.group(1)
        region_display = f"{region} ({variant})" if variant else region
        localedir = getattr(gl, "localedir", "") or ""
        return _LocaleInfo(lang_base, english_name, region_display, localedir)

    def _render_locale_fields(self, gl: GrampsLocale, info: _LocaleInfo) -> str:
        """Append translated platform strings into active visual text frames."""
        lines = [
            f"{_('Locale Code')}: {gl.locale_code()}",
            f"{_('Language')}: {info.lang_base}",
            f"{_('Lang')}: {glocale.lang}",
            f"{_('Region')}: {info.region_display}",
            f"{_('English Name')}: {info.english_name} ({info.lang_base})",
        ]
        if info.localedir:
            lines.append(f"{_('Locale Directory')}: {info.localedir}")
        for line in lines:
            self.render_text(f"{line}\n")
        return "\n".join(lines)

    def _populate_language_tab(self) -> None:
        """Clear and refresh the Language reference pane information."""
        self.clear_text()
        gl = GrampsLocale()
        language_dict = gl.get_language_dict()
        code_to_name = {v: k for k, v in language_dict.items()}
        info = self._get_locale_info(gl)

        self._insert_icon_header("preferences-desktop-locale", f"<b>{_('Current Locale')}</b>", self._cb_copy_locale_section, newline_before=False)
        self._locale_clip_text = self._render_locale_fields(gl, info)

        if info.localedir and os.path.isdir(info.localedir):
            langs = sorted(d for d in os.listdir(info.localedir) if os.path.isdir(os.path.join(info.localedir, d)) and d not in (".", ".."))
            total = len(langs)
            if info.lang_base not in langs:
                total += 1
            _count_str = _("Installed Languages (%d)") % total
            self._insert_icon_header("cs-language", f"<b>{_count_str}</b>", self._cb_copy_language_section, newline_before=True)
            self._insert_language_expander(info.lang_base, info.english_name, langs, code_to_name)

    # ------------------------------------------------------------------
    # Constants Tab UI Construction
    # ------------------------------------------------------------------

    def _build_constants_tab(self) -> Gtk.Widget:
        """Assemble the tree view grid layout and search filter systems for the constants tab."""
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_margin_top(4); vbox.set_margin_bottom(4)
        vbox.set_margin_start(4); vbox.set_margin_end(4)

        # Build horizontal search and type filter dropdown bar
        filter_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._const_search_entry = Gtk.SearchEntry()
        self._const_search_entry.set_placeholder_text(_("Filter by name or value…"))
        self._const_search_entry.connect("search-changed", self._cb_const_filter_changed)
        filter_hbox.pack_start(self._const_search_entry, True, True, 0)

        # Pop-up Menu Type Filter setup
        filter_btn = Gtk.MenuButton()
        filter_btn.set_image(Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON))
        filter_btn.set_tooltip_text(_("Filter constants by Type metadata"))

        type_menu = Gtk.Menu()
        types = ["All types", "Remote Directory", "Directory", "Glade interface layout file", "File", "Value"]
        for t in types:
            item = Gtk.MenuItem(label=_(t))
            item.connect("activate", self._cb_type_filter_selected, t)
            type_menu.append(item)
        type_menu.show_all()
        filter_btn.set_popup(type_menu)
        filter_hbox.pack_start(filter_btn, False, False, 0)
        vbox.pack_start(filter_hbox, False, False, 0)

        self._const_filter_store = Gtk.ListStore(str, str, str, str, str, str)
        for row in _build_constants_rows():
            self._const_filter_store.append(list(row))

        self._const_filter = self._const_filter_store.filter_new()
        self._const_filter.set_visible_func(self._cb_const_row_visible)

        sortable = Gtk.TreeModelSort(model=self._const_filter)
        tv = Gtk.TreeView(model=sortable)
        tv.set_headers_clickable(True)
        tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        tv.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

        # Custom cell data function to keep the padding row completely blank visually
        def name_cell_data_func(col, cell, model, it, data):
            name = model.get_value(it, _COL_NAME)
            if name == "\xff":
                cell.set_property("text", "")
            else:
                cell.set_property("text", name)

        name_renderer = Gtk.CellRendererText()
        name_col = Gtk.TreeViewColumn(_("Name"), name_renderer)
        name_col.set_cell_data_func(name_renderer, name_cell_data_func)
        name_col.set_resizable(True); name_col.set_sort_column_id(_COL_NAME)
        tv.append_column(name_col)

        self._append_icon_column(tv, _COL_TYPE_ICON, _COL_TYPE_TIP)
        self._append_icon_column(tv, _COL_VIS_ICON, _COL_VIS_TIP)

        value_renderer = Gtk.CellRendererText()
        value_renderer.set_property("wrap-mode", 2)
        value_renderer.set_property("wrap-width", 400)
        value_col = Gtk.TreeViewColumn(_("Value"), value_renderer, text=_COL_VALUE)
        value_col.set_resizable(True); value_col.set_expand(True); value_col.set_sort_column_id(_COL_VALUE)
        value_col.connect("notify::width", self._cb_value_col_width_changed, value_renderer)
        tv.append_column(value_col)

        sortable.set_sort_column_id(_COL_NAME, Gtk.SortType.ASCENDING)
        tv.set_has_tooltip(True)
        tv.connect("query-tooltip", self._cb_query_tooltip)
        tv.connect("row-activated", self._cb_row_activated)

        scr = Gtk.ScrolledWindow()
        scr.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scr.set_shadow_type(Gtk.ShadowType.IN)
        scr.add(tv)
        vbox.pack_start(scr, True, True, 0)
        return vbox

    def _append_icon_column(self, tv: Gtk.TreeView, icon_name_col: int, tooltip_col: int) -> None:
        """Append generic symbolic visual column nodes inside target table displays."""
        renderer = Gtk.CellRendererPixbuf()
        renderer.set_property("xpad", 2)
        column = Gtk.TreeViewColumn("", renderer)
        column.set_fixed_width(_ICON_SIZE_TV + 8)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.tip_col = tooltip_col

        def cell_data_func(_col, cell, model, it, data):
            icon_name = model.get_value(it, data) or ""
            if not icon_name:
                cell.set_property("pixbuf", None)
                return
            if icon_name not in self._icon_cache:
                self._icon_cache[icon_name] = _load_icon(icon_name, _ICON_SIZE_TV)
            cell.set_property("pixbuf", self._icon_cache[icon_name])

        column.set_cell_data_func(renderer, cell_data_func, icon_name_col)
        tv.append_column(column)

    # ------------------------------------------------------------------
    # Constants Signal Action Callbacks
    # ------------------------------------------------------------------

    def _cb_type_filter_selected(self, _menu_item: Gtk.MenuItem, type_name: str) -> None:
        """Update active type matching filter constraint flags."""
        self._selected_type_filter = type_name
        self._const_filter.refilter()

    def _cb_const_filter_changed(self, _search_entry: Gtk.SearchEntry) -> None:
        """Trigger instant list resets whenever the string matches change."""
        self._const_filter.refilter()

    def _cb_const_row_visible(self, model: Gtk.TreeModel, tree_iter: Gtk.TreeIter, _data: object) -> bool:
        """Evaluate visibility constraints based on text match and type dropdown selection."""
        name = model.get_value(tree_iter, _COL_NAME) or ""
        if name == "\xff":
            return True # Always keep bottom padding spacer row visible

        # Handle popup type filters
        if self._selected_type_filter != "All types":
            tip_text = model.get_value(tree_iter, _COL_TYPE_TIP) or ""
            if tip_text != self._selected_type_filter:
                return False

        needle = self._const_search_entry.get_text().casefold().strip()
        if not needle:
            return True
        name_fold = name.casefold()
        value_fold = (model.get_value(tree_iter, _COL_VALUE) or "").casefold()
        return needle in name_fold or needle in value_fold

    def _cb_value_col_width_changed(self, col: Gtk.TreeViewColumn, _pspec: object, renderer: Gtk.CellRendererText) -> None:
        """Dynamically adapt data text layouts to fit current table tracking sizes."""
        width = col.get_width()
        if width > 10:
            renderer.set_property("wrap-width", width - 4)

    def _cb_query_tooltip(self, tv: Gtk.TreeView, x: int, y: int, keyboard_mode: bool, tooltip: Gtk.Tooltip) -> bool:
        """Resolve and display translated help contextual tooltips inside the tree view row columns."""
        if keyboard_mode: return False
        result = tv.get_path_at_pos(x, y)
        if result is None: return False
        path, col, _, _ = result
        tip_col_idx = getattr(col, "tip_col", None)
        if tip_col_idx is None: return False
        model = tv.get_model()
        tree_iter = model.get_iter(path)
        if tree_iter is None: return False
        text = model.get_value(tree_iter, tip_col_idx) or ""
        if not text: return False
        tooltip.set_text(text)
        return True

    def _cb_row_activated(self, _tv: Gtk.TreeView, path: Gtk.TreePath, _col: Gtk.TreeViewColumn) -> None:
        """Handle target item interaction selections on double-click."""
        model = _tv.get_model()
        if model is None: return
        tree_iter = model.get_iter(path)
        if tree_iter is None: return

        name = model.get_value(tree_iter, _COL_NAME) or ""

        # Spacer padding action: copy all table rows to clipboard
        if name == "\xff":
            all_lines = []
            it = model.get_iter_first()
            while it:
                r_name = model.get_value(it, _COL_NAME) or ""
                if r_name != "\xff":
                    r_val = model.get_value(it, _COL_VALUE) or ""
                    all_lines.append(f"{r_name}: {r_val}")
                it = model.iter_next(it)
            _copy_to_clipboard("\n".join(all_lines))
            return

        value = model.get_value(tree_iter, _COL_VALUE) or ""
        _copy_to_clipboard(value) # Duplicate targeted row value directly to clipboard

        if name.startswith("URL_"):
            try:
                webbrowser.open(value)
            except Exception:
                LOG.warning("EnvironmentInspector: Failed to open URL route value via standard system browser.")
        elif os.path.isdir(value) or os.path.isfile(value):
            open_file_with_default_application(value, self.gui.uistate)

    # ------------------------------------------------------------------
    # Gramplet Lifecycle Entry point
    # ------------------------------------------------------------------

    def main(self) -> None:
        """Populate Language reference structures upon activation."""
        self._populate_language_tab()

        # Explicitly update the constants backing model pipeline
        if hasattr(self, "_const_filter"):
            self._const_filter.refilter()

        # Notify the display engine that layout geometries have updated
        if hasattr(self, "_notebook"):
            self._notebook.queue_draw()
            self._notebook.show_all()