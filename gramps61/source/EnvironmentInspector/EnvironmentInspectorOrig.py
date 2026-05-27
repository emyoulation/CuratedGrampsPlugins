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
"""EnvironmentInspector — two-tab reference gramplet for
     inspecting the Gramps locale and constants.

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
the newline characters that follow them.

Tab 2 — Gramps Constants
--------------------------
All uppercase string constants from gramps.gen.const displayed in a
searchable, sortable Gtk.TreeView.

Column layout (left to right):
  [Name] [Type icon] [Visibility icon] [Value]

A type-filter MenuButton sits to the right of the search entry.  Choosing a
type from the menu restricts the view to rows of that type; "All types" clears
the filter.

A blank sentinel row is always sorted to the bottom of the table regardless of
the active sort column.  Double-clicking it copies all currently-visible rows
(excluding the sentinel itself) to the clipboard.

Double-clicking any other row:
  - Copies the Value to the clipboard.
  - Opens the value with the appropriate application:
      directory  → file manager  (open_file_with_default_application)
      file       → default viewer (open_file_with_default_application)
      URL        → default browser (display_url)
      string     → no action beyond clipboard

Row classification (status)
  "VISIBLE dir"  local visible directory
  "HIDDEN dir"   local hidden directory (dot-prefixed on POSIX)
  "URL"          constant name starts with URL_ and value is http/https URL
  "GLADE"        value ends with .glade (subset of FILE; opens as file)
  "FILE"         value is an existing file (non-glade)
  "string"       anything else

Icon mapping
  Type column
    VISIBLE dir  →  folder-symbolic              tooltip: "Directory"
    HIDDEN dir   →  folder-symbolic              tooltip: "Directory"
    URL          →  folder-remote-symbolic       tooltip: "Remote Directory"
    GLADE        →  glade-brand-symbolic         tooltip: "Glade interface layout file"
    FILE         →  folder-documents-symbolic    tooltip: "File"
    string       →  insert-text                  tooltip: "Value"

  Visibility column (hidden/visible dirs only; empty for all other types)
    VISIBLE dir  →  view-reveal-symbolic         tooltip: "Not hidden"
    HIDDEN dir   →  view-conceal-symbolic        tooltip: "Hidden"

Widget-reparenting pattern
---------------------------
  orig_sw.remove(self.gui.textview)
  lang_sw = Gtk.ScrolledWindow(); lang_sw.add(self.gui.textview)
  notebook → orig_sw

AI attribution
---------------
Original single-tab version: ChatGPT (OpenAI), wish-coder style.
Refactoring iterations (v1.0.1 – v1.0.5):
  Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6,
                release 2026-05)
  Constraints:
    https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
    https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import logging
import os
import re
import sys

# ------------------------
# Gramps modules
# ------------------------
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

import gramps.gen.const as _gramps_const
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import Gramplet
from gramps.gen.utils.grampslocale import GrampsLocale

# ------------------------
# Gramps specific
# ------------------------
from gramps.gui.display import display_url
from gramps.gui.utils import open_file_with_default_application

LOG = logging.getLogger(__name__)  # pylint: disable=too-many-lines

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

# ---------------------------------------------------------------------------
# TreeView model column indices
# ---------------------------------------------------------------------------
_COL_NAME = 0  # str — constant name
_COL_TYPE_ICON = 1  # str — icon-name for the type column
_COL_VIS_ICON = 2  # str — icon-name for the visibility column
_COL_VALUE = 3  # str — constant value
_COL_TYPE_TIP = 4  # str — tooltip for the type icon column
_COL_VIS_TIP = 5  # str — tooltip for the visibility icon column
_COL_SENTINEL = 6  # int — 1 for the blank padding sentinel row, 0 otherwise

# Icon pixel size used for the TreeView icon columns
_ICON_SIZE_TV = 16

# Icon pixel size used for Language-tab section headers
_ICON_SIZE_HEADER = 48

# Left-margin padding (px) for the Language tab TextBuffer
_TEXT_LEFT_MARGIN = 5

# Sentinel sort key — must sort after any real name; chr(0x10FFFF) is the
# highest valid Unicode code point, so it always sorts last.
_SENTINEL_SORT_KEY = "\U0010ffff"

# Map from type_tip string → (icon_name, label) used to build the filter menu.
# Order defines menu item order.
_TYPE_FILTER_ITEMS: list[tuple[str, str, str]] = [
    (_("Directory"), "folder-symbolic", _("Directory")),
    (_("Remote Directory"), "folder-remote-symbolic", _("Remote Directory")),
    (_("Glade interface layout file"), "glade-brand-symbolic", _("Glade file")),
    (_("File"), "folder-documents-symbolic", _("File")),
    (_("Value"), "insert-text", _("String value")),
]


# ---------------------------------------------------------------------------
#
# _LocaleInfo
#
# ---------------------------------------------------------------------------
class _LocaleInfo:
    """Lightweight container for the locale fields rendered in Tab 1.

    :param lang_base:      Base language code (e.g. ``"en"``).
    :param english_name:   English language name (e.g. ``"English"``).
    :param region_display: Formatted region string (e.g. ``"US (USA)"``).
    :param localedir:      Path to the locale directory (may be empty).
    """

    __slots__ = ("lang_base", "english_name", "region_display", "localedir")

    def __init__(
        self,
        lang_base: str,
        english_name: str,
        region_display: str,
        localedir: str,
    ) -> None:
        """Initialise with all four locale display fields."""
        self.lang_base = lang_base
        self.english_name = english_name
        self.region_display = region_display
        self.localedir = localedir


# ---------------------------------------------------------------------------
#
# _load_icon
#
# ---------------------------------------------------------------------------
def _load_icon(icon_name: str, size: int) -> GdkPixbuf.Pixbuf | None:
    """Load a named icon from the current GTK icon theme.

    :param icon_name: Freedesktop icon name (e.g. ``"folder-symbolic"``).
    :param size:      Desired pixel size.
    :returns: A :class:`GdkPixbuf.Pixbuf`, or ``None`` if not available.
    """
    theme = Gtk.IconTheme.get_default()
    try:
        return theme.load_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)
    except Exception:  # pylint: disable=broad-except
        LOG.warning("EnvironmentInspector: icon '%s' not found in theme.", icon_name)
        return None


# ---------------------------------------------------------------------------
#
# _classify
#
# ---------------------------------------------------------------------------
def _classify(name: str, value: str) -> str:
    """Return the row-classification status string for a constant.

    Classification priority (first match wins):
      1. ``"URL"``        — name starts with ``URL_`` and value is an
                            http/https URL (used to open a browser).
      2. ``"HIDDEN dir"`` — value is an existing hidden local directory.
      3. ``"VISIBLE dir"``— value is an existing visible local directory.
      4. ``"GLADE"``      — value is an existing file ending in ``.glade``.
      5. ``"FILE"``       — value is any other existing file.
      6. ``"string"``     — everything else.

    :param name:  The constant name (e.g. ``"URL_HOMEPAGE"``).
    :param value: The string value of the constant.
    :returns: One of the six status strings listed above.
    """
    # URL check: name prefix + http/https scheme
    if name.startswith("URL_") and re.match(r"https?://", value):
        return "URL"
    # Filesystem checks
    try:
        if os.path.isdir(value):
            if sys.platform.startswith("win"):
                import ctypes  # pylint: disable=import-outside-toplevel

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


# ---------------------------------------------------------------------------
#
# _icons_and_tips
#
# ---------------------------------------------------------------------------
def _icons_and_tips(status: str) -> tuple[str, str, str, str]:
    """Return ``(type_icon, vis_icon, type_tip, vis_tip)`` for *status*.

    :param status: One of the values returned by :func:`_classify`.
    :returns: Four-tuple of icon names and translated tooltip strings.
    """
    if status == "HIDDEN dir":
        return (
            "folder-symbolic",
            "view-conceal-symbolic",
            _("Directory"),
            _("Hidden"),
        )
    if status == "VISIBLE dir":
        return (
            "folder-symbolic",
            "view-reveal-symbolic",
            _("Directory"),
            _("Not hidden"),
        )
    if status == "URL":
        return "folder-remote-symbolic", "", _("Remote Directory"), ""
    if status == "GLADE":
        return "glade-brand-symbolic", "", _("Glade interface layout file"), ""
    if status == "FILE":
        return "folder-documents-symbolic", "", _("File"), ""
    return "insert-text", "", _("Value"), ""


# ---------------------------------------------------------------------------
#
# _build_constants_rows
#
# ---------------------------------------------------------------------------
def _build_constants_rows() -> list[tuple[str, str, str, str, str, str, int]]:
    """Collect all uppercase string constants from gramps.gen.const.

    :returns: Sorted list of
              ``(name, type_icon, vis_icon, value, type_tip, vis_tip, sentinel)``
              tuples.  A single sentinel row ``("", …, 1)`` is appended last.
    """
    rows: list[tuple[str, str, str, str, str, str, int]] = []
    for attr_name in dir(_gramps_const):
        if not attr_name.isupper() or attr_name.startswith("_"):
            continue
        value = getattr(_gramps_const, attr_name)
        if not isinstance(value, str):
            continue
        status = _classify(attr_name, value)
        type_icon, vis_icon, type_tip, vis_tip = _icons_and_tips(status)
        rows.append((attr_name, type_icon, vis_icon, value, type_tip, vis_tip, 0))
    rows.sort(key=lambda r: r[0].casefold())
    # Sentinel row — always sorted last; double-clicking it copies all rows.
    rows.append(("", "", "", "", "", "", 1))
    return rows


# ---------------------------------------------------------------------------
#
# _copy_to_clipboard
#
# ---------------------------------------------------------------------------
def _copy_to_clipboard(text: str) -> None:
    """Copy *text* to the system clipboard.

    :param text: Plain text to place on the clipboard.
    """
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)
    clipboard.store()


# ---------------------------------------------------------------------------
#
# EnvironmentInspector
#
# ---------------------------------------------------------------------------
class EnvironmentInspector(Gramplet):  # pylint: disable=too-many-instance-attributes
    """Two-tab reference gramplet for locale and Gramps-constant inspection."""

    # Declared here to satisfy pylint W0201 (attribute-defined-outside-init).
    _const_filter_store: Gtk.ListStore
    _const_filter: Gtk.TreeModelFilter
    _const_search_entry: Gtk.SearchEntry
    _icon_cache: dict
    _expander: Gtk.Expander
    _locale_clip_text: str
    _active_type_filter: str
    _sortable: Gtk.TreeModelSort

    def init(self) -> None:
        """Initialise the gramplet and build the two-tab Notebook UI.

        Widget-reparenting steps:
          1. Remove textview from the original ScrolledWindow.
          2. Make textview non-focusable (prevents black selection highlights).
          3. Apply left-margin padding to textview.
          4. Wrap textview in a new ScrolledWindow → Tab 1 (Language).
          5. Build constants viewer → Tab 2 (Gramps Constants).
          6. Place Notebook into the original ScrolledWindow.
        """
        self.set_use_markup(True)

        self._const_filter_store = Gtk.ListStore(str, str, str, str, str, str, int)
        self._const_filter = self._const_filter_store.filter_new()
        self._const_search_entry = Gtk.SearchEntry()
        self._icon_cache = {}
        self._expander = Gtk.Expander()
        self._locale_clip_text = ""
        self._active_type_filter = ""
        self._sortable = Gtk.TreeModelSort(model=self._const_filter)

        orig_sw = self.gui.get_container_widget()
        orig_sw.remove(self.gui.textview)

        self.gui.textview.set_can_focus(False)
        self.gui.textview.set_left_margin(_TEXT_LEFT_MARGIN)

        lang_sw = Gtk.ScrolledWindow()
        lang_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        lang_sw.add(self.gui.textview)

        const_box = self._build_constants_tab()

        notebook = Gtk.Notebook()
        notebook.set_show_border(True)
        notebook.append_page(lang_sw, Gtk.Label(label=_("Language")))
        notebook.append_page(const_box, Gtk.Label(label=_("Gramps Constants")))

        orig_sw.add(notebook)
        orig_sw.show_all()

    # ------------------------------------------------------------------
    # Language tab — section-header anchor helper
    # ------------------------------------------------------------------

    def _insert_icon_header(
        self,
        icon_name: str,
        markup: str,
        clip_callback: object,
        newline_before: bool = True,
    ) -> None:
        """Insert an icon + label section header as a TextChildAnchor.

        Clicking the icon calls *clip_callback* to copy section content to the
        clipboard.

        :param icon_name:      Freedesktop icon name.
        :param markup:         Pango markup for the label text.
        :param clip_callback:  Zero-argument callable invoked on icon click.
        :param newline_before: If True, emit a blank line before the anchor.
        """
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
        ebox.connect(
            "button-press-event",
            lambda _w, _e: clip_callback() or True,
        )
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

    # ------------------------------------------------------------------
    # Language tab — expander anchor helper
    # ------------------------------------------------------------------

    def _insert_language_expander(
        self,
        current_lang: str,
        current_name: str,
        langs: list[str],
        code_to_name: dict[str, str],
    ) -> None:
        """Insert the collapsible installed-languages Gtk.Expander anchor.

        :param current_lang:  Base language code for the active locale.
        :param current_name:  English name of the active locale language.
        :param langs:         All installed language codes, sorted.
        :param code_to_name:  Mapping from language code to English name.
        """
        summary_markup = f"<i>{current_lang}: {current_name}</i>"
        self._expander = Gtk.Expander()
        self._expander.set_use_markup(True)
        self._expander.set_label(summary_markup)
        self._expander.set_expanded(False)

        all_langs = sorted(langs)
        if current_lang not in all_langs:
            all_langs = [current_lang] + all_langs

        lines = "\n".join(
            f"  {lang}: {code_to_name.get(lang, _('Unknown'))}" for lang in all_langs
        )
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
    # Language tab — clipboard helpers
    # ------------------------------------------------------------------

    def _cb_copy_locale_section(self) -> None:
        """Copy the Current Locale section content to the clipboard."""
        _copy_to_clipboard(self._locale_clip_text)

    def _cb_copy_language_section(self) -> None:
        """Copy the Installed Languages section to the clipboard.

        Copies only the summary line when collapsed; full list when expanded.
        """
        if self._expander.get_expanded():
            child = self._expander.get_child()
            text = child.get_text() if child else ""
        else:
            raw = self._expander.get_label() or ""
            text = re.sub(r"<[^>]+>", "", raw)
        _copy_to_clipboard(text.strip())

    # ------------------------------------------------------------------
    # Language tab — population
    # ------------------------------------------------------------------

    def _get_locale_info(self, gl: GrampsLocale) -> _LocaleInfo:
        """Extract and return the key locale fields from *gl*.

        :param gl: A :class:`GrampsLocale` instance.
        :returns: :class:`_LocaleInfo` populated from *gl*.
        """
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
        """Write locale detail fields into the Language tab buffer.

        :param gl:   Active :class:`GrampsLocale`.
        :param info: Pre-computed :class:`_LocaleInfo` for *gl*.
        :returns:    Plain-text copy of all rendered lines (for clipboard).
        """
        lines = [
            f"{_('Locale Code')}: {gl.locale_code()}",
            f"{_('Language')}: {info.lang_base}",
            f"{_('Lang')}: {gl.lang}",
            f"{_('Region')}: {info.region_display}",
            f"{_('English Name')}: {info.english_name} ({info.lang_base})",
        ]
        if info.localedir:
            lines.append(f"{_('Locale Directory')}: {info.localedir}")
        for line in lines:
            self.render_text(f"{line}\n")
        return "\n".join(lines)

    def _populate_language_tab(self) -> None:
        """Render locale information into the Language tab text buffer."""
        self.clear_text()

        gl = GrampsLocale()
        language_dict = gl.get_language_dict()
        code_to_name = {v: k for k, v in language_dict.items()}
        info = self._get_locale_info(gl)

        self._insert_icon_header(
            "preferences-desktop-locale",
            f"<b>{_('Current Locale')}</b>",
            self._cb_copy_locale_section,
            newline_before=False,
        )
        self._locale_clip_text = self._render_locale_fields(gl, info)

        if info.localedir and os.path.isdir(info.localedir):
            langs = sorted(
                d
                for d in os.listdir(info.localedir)
                if os.path.isdir(os.path.join(info.localedir, d))
                and d not in (".", "..")
            )
            total = len(langs) + (0 if info.lang_base in langs else 1)
            _count_str = _("Installed Languages (%d)") % total
            self._insert_icon_header(
                "cs-language",
                f"<b>{_count_str}</b>",
                self._cb_copy_language_section,
                newline_before=True,
            )
            self._insert_language_expander(
                info.lang_base, info.english_name, langs, code_to_name
            )

    # ------------------------------------------------------------------
    # Constants tab — builder
    # ------------------------------------------------------------------

    def _build_constants_tab(self) -> Gtk.Widget:
        """Build and return the Gramps Constants tab widget.

        Layout::

            HBox
            ├── SearchEntry
            └── MenuButton  (type filter pop-up)

            ScrolledWindow
            └── TreeView
                ├── Name   (sortable text)
                ├── Type   (icon, fixed-width, no title)
                ├── Vis    (icon, fixed-width, no title)
                └── Value  (sortable text, word-wrapping)

        A blank sentinel row is always sorted last.  Double-clicking it
        copies all currently-visible data rows to the clipboard.

        :returns: The outer Gtk.Box to be used as the notebook page.
        """
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_margin_top(4)
        vbox.set_margin_bottom(4)
        vbox.set_margin_start(4)
        vbox.set_margin_end(4)

        # ---- Search bar + type-filter menu --------------------------------
        search_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._const_search_entry = Gtk.SearchEntry()
        self._const_search_entry.set_placeholder_text(_("Filter by name or value…"))
        self._const_search_entry.connect(
            "search-changed", self._cb_const_filter_changed
        )
        search_bar.pack_start(self._const_search_entry, True, True, 0)

        filter_btn = self._build_type_filter_button()
        search_bar.pack_start(filter_btn, False, False, 0)

        vbox.pack_start(search_bar, False, False, 0)

        # ---- Data model ---------------------------------------------------
        # Columns: name, type_icon, vis_icon, value, type_tip, vis_tip, sentinel
        self._const_filter_store = Gtk.ListStore(str, str, str, str, str, str, int)
        for row in _build_constants_rows():
            self._const_filter_store.append(list(row))

        self._const_filter = self._const_filter_store.filter_new()
        self._const_filter.set_visible_func(self._cb_const_row_visible)

        self._sortable = Gtk.TreeModelSort(model=self._const_filter)
        self._install_sentinel_sort()

        scr = self._build_constants_treeview()
        vbox.pack_start(scr, True, True, 0)

        return vbox

    def _build_constants_treeview(self) -> Gtk.ScrolledWindow:
        """Build the TreeView and its ScrolledWindow for the Constants tab.

        Extracted from :meth:`_build_constants_tab` to keep statement count
        within pylint limits.

        :returns: A :class:`Gtk.ScrolledWindow` containing the TreeView.
        """
        tv = Gtk.TreeView(model=self._sortable)
        tv.set_enable_search(False)
        tv.set_headers_clickable(True)
        tv.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        tv.get_selection().set_mode(Gtk.SelectionMode.SINGLE)

        # Name column
        name_renderer = Gtk.CellRendererText()
        name_col = Gtk.TreeViewColumn(_("Name"), name_renderer, text=_COL_NAME)
        name_col.set_resizable(True)
        name_col.set_expand(False)
        name_col.set_sort_column_id(_COL_NAME)
        tv.append_column(name_col)

        # Icon columns
        self._append_icon_column(tv, _COL_TYPE_ICON, _COL_TYPE_TIP)
        self._append_icon_column(tv, _COL_VIS_ICON, _COL_VIS_TIP)

        # Value column — word-wrapping, no ellipsis
        value_renderer = Gtk.CellRendererText()
        value_renderer.set_property("wrap-mode", 2)  # Pango.WrapMode.WORD_CHAR
        value_renderer.set_property("wrap-width", 400)
        value_col = Gtk.TreeViewColumn(_("Value"), value_renderer, text=_COL_VALUE)
        value_col.set_resizable(True)
        value_col.set_expand(True)
        value_col.set_sort_column_id(_COL_VALUE)
        value_col.connect(
            "notify::width",
            self._cb_value_col_width_changed,
            value_renderer,
        )
        tv.append_column(value_col)

        self._sortable.set_sort_column_id(_COL_NAME, Gtk.SortType.ASCENDING)

        tv.set_has_tooltip(True)
        tv.connect("query-tooltip", self._cb_query_tooltip)
        tv.connect("row-activated", self._cb_row_activated)

        scr = Gtk.ScrolledWindow()
        scr.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scr.set_shadow_type(Gtk.ShadowType.IN)
        scr.add(tv)
        return scr

    def _build_type_filter_button(self) -> Gtk.MenuButton:
        """Build the type-filter MenuButton shown to the right of the search entry.

        The menu lists "All types" followed by one item per row classification.
        Choosing an item restricts the visible rows to that type.

        :returns: A configured :class:`Gtk.MenuButton`.
        """
        menu = Gtk.Menu()

        # "All types" item clears the type filter.
        all_item = Gtk.MenuItem(label=_("All types"))
        all_item.connect("activate", lambda _w: self._cb_set_type_filter(""))
        menu.append(all_item)
        menu.append(Gtk.SeparatorMenuItem())

        for tip, icon_name, label in _TYPE_FILTER_ITEMS:
            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            img = Gtk.Image()
            pb = _load_icon(icon_name, _ICON_SIZE_TV)
            if pb is not None:
                img.set_from_pixbuf(pb)
            else:
                img.set_from_icon_name(icon_name, Gtk.IconSize.MENU)
            hbox.pack_start(img, False, False, 0)
            hbox.pack_start(Gtk.Label(label=label), False, False, 0)
            item = Gtk.MenuItem()
            item.add(hbox)
            # Capture tip in default arg to avoid late-binding closure issue.
            item.connect(
                "activate",
                lambda _w, t=tip: self._cb_set_type_filter(t),
            )
            menu.append(item)

        menu.show_all()

        btn = Gtk.MenuButton()
        btn.set_popup(menu)
        btn.set_tooltip_text(_("Filter by type"))
        # Use a funnel/filter icon if available, else fall back to a label.
        pb = _load_icon("view-filter-symbolic", _ICON_SIZE_TV)
        if pb is None:
            pb = _load_icon("edit-find-symbolic", _ICON_SIZE_TV)
        if pb is not None:
            btn.set_label(_("Filter ▼"))
            # btn.set_image(Gtk.Image.new_from_pixbuf(pb))
        else:
            btn.set_label(_("Filter ▼"))
        return btn

    def _install_sentinel_sort(self) -> None:
        """Install custom sort functions that keep the sentinel row last.

        For every sortable column (Name = _COL_NAME, Value = _COL_VALUE) a
        custom comparator is registered on ``self._sortable``.  When either
        row is the sentinel it is always sorted after the other row,
        regardless of sort direction.
        """
        for col_id in (_COL_NAME, _COL_VALUE):
            self._sortable.set_sort_func(
                col_id,
                self._sentinel_sort_func,
                col_id,
            )

    def _sentinel_sort_func(
        self,
        model: Gtk.TreeModel,
        iter_a: Gtk.TreeIter,
        iter_b: Gtk.TreeIter,
        col_id: int,
    ) -> int:
        """Compare two rows, always placing the sentinel row last.

        :param model:  The data model.
        :param iter_a: Iterator for row A.
        :param iter_b: Iterator for row B.
        :param col_id: Model column to compare when neither row is sentinel.
        :returns: Negative, zero, or positive per the GLib sort convention.
        """
        sentinel_a = model.get_value(iter_a, _COL_SENTINEL)
        sentinel_b = model.get_value(iter_b, _COL_SENTINEL)
        if sentinel_a and not sentinel_b:
            return 1
        if sentinel_b and not sentinel_a:
            return -1
        val_a = (model.get_value(iter_a, col_id) or "").casefold()
        val_b = (model.get_value(iter_b, col_id) or "").casefold()
        if val_a < val_b:
            return -1
        if val_a > val_b:
            return 1
        return 0

    def _append_icon_column(
        self,
        tv: Gtk.TreeView,
        icon_name_col: int,
        tooltip_col: int,
    ) -> None:
        """Append a fixed-width pixbuf column to *tv*.

        :param tv:            Target Gtk.TreeView.
        :param icon_name_col: Model column index holding the icon-name string.
        :param tooltip_col:   Model column index for this column's tooltip.
        """
        renderer = Gtk.CellRendererPixbuf()
        renderer.set_property("xpad", 2)
        column = Gtk.TreeViewColumn("", renderer)
        column.set_fixed_width(_ICON_SIZE_TV + 8)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_resizable(False)
        column.set_expand(False)
        column.tip_col = tooltip_col  # type: ignore[attr-defined]

        def cell_data_func(
            _col: Gtk.TreeViewColumn,
            cell: Gtk.CellRendererPixbuf,
            model: Gtk.TreeModel,
            it: Gtk.TreeIter,
            data: int,
        ) -> None:
            """Resolve icon-name → pixbuf and assign to *cell*.

            :param _col:  Unused.
            :param cell:  CellRendererPixbuf to update.
            :param model: Data model.
            :param it:    Row iterator.
            :param data:  Model column index for the icon-name string.
            """
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
    # Callbacks
    # ------------------------------------------------------------------

    def _cb_set_type_filter(self, type_tip: str) -> None:
        """Set the active type filter and refilter the model.

        :param type_tip: The type_tip string to match, or ``""`` for all.
        """
        self._active_type_filter = type_tip
        self._const_filter.refilter()

    def _cb_const_filter_changed(self, _search_entry: Gtk.SearchEntry) -> None:
        """Refilter when the search text changes.

        :param _search_entry: The Gtk.SearchEntry that emitted the signal.
        """
        self._const_filter.refilter()

    def _cb_const_row_visible(
        self,
        model: Gtk.TreeModel,
        tree_iter: Gtk.TreeIter,
        _data: object,
    ) -> bool:
        """Return True if this row should be visible.

        The sentinel row is always visible.  Other rows must pass both the
        text filter (name or value contains the search needle) and the
        type filter (type_tip matches ``self._active_type_filter``).

        :param model:     The Gtk.ListStore being filtered.
        :param tree_iter: Iterator for the candidate row.
        :param _data:     Unused.
        :returns: ``True`` if the row should be visible.
        """
        # Sentinel row is always shown.
        if model.get_value(tree_iter, _COL_SENTINEL):
            return True

        # Type filter
        if self._active_type_filter:
            row_tip = model.get_value(tree_iter, _COL_TYPE_TIP) or ""
            if row_tip != self._active_type_filter:
                return False

        # Text filter
        needle = self._const_search_entry.get_text().casefold().strip()
        if not needle:
            return True
        name = (model.get_value(tree_iter, _COL_NAME) or "").casefold()
        value = (model.get_value(tree_iter, _COL_VALUE) or "").casefold()
        return needle in name or needle in value

    def _cb_value_col_width_changed(
        self,
        col: Gtk.TreeViewColumn,
        _pspec: object,
        renderer: Gtk.CellRendererText,
    ) -> None:
        """Keep Value cell wrap-width in sync with the column pixel width.

        :param col:      The Value Gtk.TreeViewColumn.
        :param _pspec:   GParamSpec (unused).
        :param renderer: The CellRendererText whose wrap-width to update.
        """
        width = col.get_width()
        if width > 10:
            renderer.set_property("wrap-width", width - 4)

    def _cb_query_tooltip(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        tv: Gtk.TreeView,
        x: int,
        y: int,
        keyboard_mode: bool,
        tooltip: Gtk.Tooltip,
    ) -> bool:
        """Show a per-column tooltip when hovering over an icon column.

        :param tv:            The Gtk.TreeView emitting the signal.
        :param x:             Pointer x (widget-relative).
        :param y:             Pointer y (widget-relative).
        :param keyboard_mode: True if triggered by keyboard.
        :param tooltip:       The Gtk.Tooltip to populate.
        :returns: ``True`` to display the tooltip.
        """
        if keyboard_mode:
            return False
        result = tv.get_path_at_pos(x, y)
        if result is None:
            return False
        path, col, _cx, _cy = result
        tip_col_idx = getattr(col, "tip_col", None)
        if tip_col_idx is None:
            return False
        model = tv.get_model()
        tree_iter = model.get_iter(path)
        if tree_iter is None:
            return False
        text = model.get_value(tree_iter, tip_col_idx) or ""
        if not text:
            return False
        tooltip.set_text(text)
        return True

    def _collect_visible_rows_text(self, tv: Gtk.TreeView) -> str:
        """Return a tab-separated text dump of all visible non-sentinel rows.

        :param tv: The Gtk.TreeView whose model to iterate.
        :returns:  Multi-line string: one ``name\\tvalue`` pair per line.
        """
        model = tv.get_model()
        lines: list[str] = []
        tree_iter = model.get_iter_first()
        while tree_iter is not None:
            if not model.get_value(tree_iter, _COL_SENTINEL):
                name = model.get_value(tree_iter, _COL_NAME) or ""
                value = model.get_value(tree_iter, _COL_VALUE) or ""
                lines.append(f"{name}\t{value}")
            tree_iter = model.iter_next(tree_iter)
        return "\n".join(lines)

    def _cb_row_activated(
        self,
        tv: Gtk.TreeView,
        path: Gtk.TreePath,
        _col: Gtk.TreeViewColumn,
    ) -> None:
        """Handle double-click / Enter on a TreeView row.

        For the sentinel row: copies all visible data rows to clipboard.
        For any other row: copies the value to clipboard, then opens it:
          - directory → file manager
          - file (including .glade) → default viewer
          - URL (http/https) → default browser
          - string → clipboard only

        :param tv:   The Gtk.TreeView that was activated.
        :param path: Tree path of the activated row.
        :param _col: Column of activation (unused).
        """
        model = tv.get_model()
        tree_iter = model.get_iter(path)
        if tree_iter is None:
            return

        # Sentinel row → copy all visible rows.
        if model.get_value(tree_iter, _COL_SENTINEL):
            _copy_to_clipboard(self._collect_visible_rows_text(tv))
            return

        value = model.get_value(tree_iter, _COL_VALUE) or ""
        # Always copy the value to clipboard.
        _copy_to_clipboard(value)

        # Open if it is a filesystem path or a URL.
        if os.path.isdir(value) or os.path.isfile(value):
            open_file_with_default_application(value, self.gui.uistate)
        elif re.match(r"https?://", value):
            display_url(value)

    # ------------------------------------------------------------------
    # Gramplet lifecycle
    # ------------------------------------------------------------------

    def main(self) -> None:
        """Populate both tabs when the gramplet first runs."""
        self._populate_language_tab()
