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
"""EnvironmentInspector — five-tab reference gramplet for Gramps locale, locale
settings, translations and constants.

Tab order: Language, Locale Settings (envinsp_settings.py), Translation
Preview, Gramps Constants, Help (envinsp_help.py).

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

Tab 3 — Translation Preview
---------------------------
Previews another installed Gramps translation without changing the session:
samples (words, dates, a name, sort order) and the interface text of open
windows and visible gramplets, looked up in that language's catalog.
See envinsp_preview.py and envinsp_catalog.py.
"""

import logging
import os
import re
import sys
import webbrowser

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

import gramps.gen.const as _gramps_const
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import Gramplet
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gui.utils import open_file_with_default_application

# Sibling modules: Gramps puts the plugin folder on sys.path only while it
# imports this module, so these imports must stay at module level.
from envinsp_preview import TranslationPreview
from envinsp_settings import LocaleSettings
from envinsp_help import HelpTab
import envinsp_catalog
import envinsp_restart
from gramps.gen.config import config as _configman

# Settings file EnvironmentInspector.ini next to this module.
CONFIG = _configman.register_manager(
    "EnvironmentInspector", __file__, use_plugins_path=False
)
CONFIG.register("meta.plugin_id", "")
CONFIG.register("meta.schema_version", "")
CONFIG.register("language.restart-override", "")
CONFIG.register("language.restart-override-pid", 0)
# Status values hidden on the Windows sub-tab of the Translation Preview.
# Hidden ones are stored (not shown ones) so a new status starts visible.
CONFIG.register("preview.hidden-statuses", [])
CONFIG.load()
CONFIG.set("meta.plugin_id", "EnvironmentInspector")
CONFIG.set("meta.schema_version", "1")


def _consume_restart_override() -> None:
    """
    A language chosen for a restart is a one-off: once a new Gramps process
    loads this module, the choice was used (or abandoned), so clear it and
    remove the one-shot desktop menu entry.
    """
    code = CONFIG.get("language.restart-override")
    if code and CONFIG.get("language.restart-override-pid") != os.getpid():
        CONFIG.set("language.restart-override", "")
        CONFIG.set("language.restart-override-pid", 0)
        if envinsp_restart.is_linux():
            envinsp_restart.apply_desktop_override("")
        CONFIG.save()


_consume_restart_override()

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


# Bundled fallback icons (media/<icon-name>.svg) for icons that come from
# other desktops or applications (Cinnamon, Glade) and may be missing.
_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")


def _add_media_search_path() -> None:
    """
    Append the bundled media folder to the GTK icon theme search path.

    GTK uses an image file placed directly in a search-path folder only when
    the icon name is not found in the active icon theme or in hicolor, so
    the bundled copies never override the theme of the user.
    """
    theme = Gtk.IconTheme.get_default()
    if os.path.isdir(_MEDIA_DIR) and _MEDIA_DIR not in theme.get_search_path():
        theme.append_search_path(_MEDIA_DIR)


def _load_icon(icon_name: str, size: int) -> GdkPixbuf.Pixbuf | None:
    """Look up an icon in the active theme, then in the bundled media folder."""
    _add_media_search_path()
    theme = Gtk.IconTheme.get_default()
    try:
        return theme.load_icon(icon_name, size, Gtk.IconLookupFlags.USE_BUILTIN)
    except Exception:
        pass
    # Safety net in case the search path was reset by a theme change.
    for ext in (".svg", ".png"):
        path = os.path.join(_MEDIA_DIR, icon_name + ext)
        if os.path.isfile(path):
            try:
                return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
            except Exception:
                LOG.debug("EnvironmentInspector: cannot load %s", path)
    LOG.warning("EnvironmentInspector: icon '%s' not found in theme.", icon_name)
    return None


def _path_status(name: str, value: str) -> str:
    """Analyze a text element to check if it points to local files, remote URLs, or strings."""
    if name.startswith("URL_"):
        return "REMOTE dir"
    try:
        # Every Glade related constant (GLADE_DIR, GLADE_FILE, PERSON_GLADE,
        # ...) and any .glade file, so the type filter finds them together.
        if "GLADE" in name or (os.path.isfile(value) and value.lower().endswith(".glade")):
            return "GLADE dir" if os.path.isdir(value) else "GLADE"
        if os.path.isdir(value):
            if sys.platform.startswith("win"):
                import ctypes
                attrs = ctypes.windll.kernel32.GetFileAttributesW(value)
                hidden = attrs != -1 and bool(attrs & 2)
            else:
                hidden = os.path.basename(value).startswith(".")
            return "HIDDEN dir" if hidden else "VISIBLE dir"
        if os.path.isfile(value):
            return "FILE"
    except (OSError, ValueError):
        pass
    return "string"


def _status_icons_and_tips(status: str, value: str = "") -> tuple[str, str, str, str]:
    """Provide specific UI visual icon properties and matching translations based on type."""
    if status == "REMOTE dir":
        return ("folder-remote-symbolic", "", _("Remote Directory"), "")
    if status == "HIDDEN dir":
        return ("folder-symbolic", "view-conceal-symbolic", _("Directory"), _("Hidden"))
    if status == "VISIBLE dir":
        return ("folder-symbolic", "view-reveal-symbolic", _("Directory"), _("Not hidden"))
    if status == "GLADE dir":
        hidden = os.path.basename(value).startswith(".") if value else False
        return ("glade-brand-symbolic",
                "view-conceal-symbolic" if hidden else "view-reveal-symbolic",
                _("Glade Interface"), _("Hidden") if hidden else _("Not hidden"))
    if status == "GLADE":
        return ("glade-brand-symbolic", "", _("Glade Interface"), "")
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
        type_icon, vis_icon, type_tip, vis_tip = _status_icons_and_tips(status, value)
        rows.append((name, type_icon, vis_icon, value, type_tip, vis_tip))
    rows.sort(key=lambda r: r[0].casefold())

    # Inject an empty padding spacer row that always sorts to the bottom via character boundaries (\xff)
    rows.append(("\xff", "", "", "", "", ""))
    return rows


# Terminal output of a Gramps restarted from the Gramps Translations table.
_RESTART_LOG = os.path.join(_gramps_const.USER_CACHE, "environment-inspector-restart.log")

# Gramps Translations table columns
(_LC_ICON, _LC_CURRENT, _LC_REGION, _LC_CODE, _LC_NAME, _LC_ENDONYM,
 _LC_STRINGS, _LC_STRINGS_N, _LC_RANK) = range(9)
_LANG_TYPES = (str, str, str, str, str, str, str, int, int)


def _restart_icon_name() -> str:
    """The "reload" icon if the theme has it, else its newer names."""
    theme = Gtk.IconTheme.get_default()
    for name in ("reload", "view-refresh", "view-refresh-symbolic"):
        if theme.has_icon(name):
            return name
    return "view-refresh"


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
        self._lang_sw = lang_sw
        lang_sw.connect("size-allocate", self._cb_lang_area_allocated)
        self._preview = TranslationPreview(self.uistate, CONFIG)
        self._syncing_language = False
        self._preview.lang_combo.connect("changed", self._cb_preview_language_changed)
        self._notebook.append_page(lang_sw, Gtk.Label(label=_("Language")))
        self._notebook.append_page(LocaleSettings(), Gtk.Label(label=_("Locale Settings")))
        self._notebook.append_page(self._preview, Gtk.Label(label=_("Translation Preview")))
        self._notebook.append_page(const_box, Gtk.Label(label=_("Gramps Constants")))
        self._notebook.append_page(HelpTab(self.uistate), Gtk.Label(label=_("Help")))

        orig_sw.add(self._notebook)
        orig_sw.show_all()

    def _make_icon_header(self, icon_name: str, markup: str, clip_callback: object) -> Gtk.Box:
        """A section header: clickable icon (copies the section) and bold title."""
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
        ebox.connect("button-press-event", self._cb_header_icon_pressed, clip_callback)
        hbox.pack_start(ebox, False, False, 0)

        lbl = Gtk.Label()
        lbl.set_markup(markup)
        lbl.set_xalign(0.0)
        hbox.pack_start(lbl, False, False, 0)
        return hbox

    @staticmethod
    def _cb_header_icon_pressed(_widget: Gtk.Widget, event: Gdk.EventButton, clip_callback: object) -> bool:
        """A click on a header icon copies the section."""
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            clip_callback()
        return True

    def _insert_icon_header(self, icon_name: str, markup: str, clip_callback: object,
                            newline_before: bool = True, row_double_click: object = None) -> Gtk.Widget:
        """
        Insert a section header into the text view. With row_double_click,
        the header is put in an event box (widened to the tab on resize by
        the caller) and a double-click anywhere on it calls row_double_click.
        """
        if newline_before:
            self.append_text("\n")
        widget = self._make_icon_header(icon_name, markup, clip_callback)
        if row_double_click is not None:
            row = Gtk.EventBox()
            row.set_visible_window(False)
            row.add(widget)
            # A gesture in the capture phase sees every press on the row,
            # including presses on the icon, before any child handles them;
            # it works the same on X11 and Wayland.
            gesture = Gtk.GestureMultiPress.new(row)
            gesture.set_button(Gdk.BUTTON_PRIMARY)
            gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            gesture.connect(
                "pressed",
                lambda _g, n_press, _x, _y: n_press == 2 and row_double_click(),
            )
            row.envinsp_gesture = gesture  # a gesture must be kept referenced
            widget = row
        widget.show_all()
        buf = self.gui.textview.get_buffer()
        anchor = buf.create_child_anchor(buf.get_end_iter())
        self.gui.textview.add_child_at_anchor(widget, anchor)
        self.append_text("\n")
        return widget

    def _cb_toggle_language_expander(self) -> None:
        """Double-click on the Gramps Translations header: expand or collapse."""
        expander = getattr(self, "_expander", None)
        if expander is not None:
            expander.set_expanded(not expander.get_expanded())

    def _insert_language_expander(self, current_lang: str, current_name: str, langs: list[str], code_to_name: dict[str, str]) -> None:
        """Embed a collapsible, sortable table of the Gramps translations."""
        summary_markup = f"<i>{current_lang}: {current_name}</i>"
        self._expander = Gtk.Expander()
        self._expander.set_use_markup(True)
        self._expander.set_label(summary_markup)
        self._expander.set_expanded(False)

        self._lang_store = Gtk.ListStore(*_LANG_TYPES)
        self._lang_store.set_sort_column_id(_LC_RANK, Gtk.SortType.ASCENDING)
        self._lang_store.connect(
            "sort-column-changed", lambda *_a: GLib.idle_add(self._center_language_row)
        )
        view = Gtk.TreeView(model=self._lang_store)
        self._lang_view = view

        current_col = Gtk.TreeViewColumn(_("Current"))
        icon_renderer = Gtk.CellRendererPixbuf()
        current_col.pack_start(icon_renderer, False)
        current_col.add_attribute(icon_renderer, "icon-name", _LC_ICON)
        text_renderer = Gtk.CellRendererText()
        current_col.pack_start(text_renderer, False)
        current_col.add_attribute(text_renderer, "text", _LC_CURRENT)
        current_col.set_sort_column_id(_LC_RANK)
        current_col.set_resizable(True)
        view.append_column(current_col)
        for title, text_col, sort_col in (
            (_("Region"), _LC_REGION, _LC_REGION),
            (_("Code"), _LC_CODE, _LC_CODE),
            (_("Name"), _LC_NAME, _LC_NAME),
            (_("Endonym"), _LC_ENDONYM, _LC_ENDONYM),
            (_("Strings"), _LC_STRINGS, _LC_STRINGS_N),
        ):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=text_col)
            column.set_sort_column_id(sort_col)
            column.set_resizable(True)
            view.append_column(column)
        view.set_tooltip_text(
            _("Double-click a language to use it the next time Gramps starts; "
              "double-click it again to go back. Region: the region named in "
              "the translation code, or else the region Gramps pairs with the "
              "language for Windows. Strings: translated entries in the catalog.")
        )
        view.get_selection().connect("changed", self._cb_lang_selection_changed)
        view.connect("row-activated", self._cb_lang_row_activated)

        self._lang_scroller = Gtk.ScrolledWindow()
        self._lang_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._lang_scroller.set_size_request(-1, 280)
        self._lang_scroller.add(view)
        self._lang_scroller.set_margin_start(12)
        self._lang_scroller.set_margin_top(4)
        self._lang_scroller.set_margin_bottom(4)
        self._expander.add(self._lang_scroller)
        self._lang_rows = []
        # Loading every catalog takes a moment: do it on first expand only.
        self._expander.connect("notify::expanded", self._cb_language_expanded)
        self._expander.show_all()

        buf = self.gui.textview.get_buffer()
        anchor = buf.create_child_anchor(buf.get_end_iter())
        self._lang_anchor = anchor
        self.gui.textview.add_child_at_anchor(self._expander, anchor)
        self.append_text("\n")

    def _cb_lang_area_allocated(self, *_args: object) -> None:
        """Size the translations table to fill the visible Language tab."""
        anchor = getattr(self, "_lang_anchor", None)
        if anchor is None or anchor.get_deleted():
            return
        area = self._lang_sw.get_allocation()
        buf = self.gui.textview.get_buffer()
        top = self.gui.textview.get_iter_location(
            buf.get_iter_at_child_anchor(self._lang_anchor)
        ).y
        label = self._expander.get_label_widget()
        label_height = label.get_allocated_height() if label else 24
        width = max(200, area.width - 40)
        header = getattr(self, "_lang_header", None)
        if header is not None and header.get_size_request()[0] != width:
            header.set_size_request(width, -1)  # the whole row is the hotspot
        height = max(150, area.height - top - label_height - 24)
        if tuple(self._lang_scroller.get_size_request()) != (width, height):
            self._lang_scroller.set_size_request(width, height)

    def _cb_language_expanded(self, expander: Gtk.Expander, _pspec: object) -> None:
        """Fill the translations table the first time it is opened."""
        if expander.get_expanded():
            GLib.idle_add(lambda: self._cb_lang_area_allocated() or False)
        if not expander.get_expanded() or self._lang_rows:
            return
        self.uistate.set_busy_cursor(True)
        try:
            self._lang_rows = envinsp_catalog.language_rows(glocale)
        finally:
            self.uistate.set_busy_cursor(False)
        for row in self._lang_rows:
            region = f"{row['flag']} {row['region']}".strip()
            strings = f"{row['strings']:,}" if row["strings"] >= 0 else "—"
            self._lang_store.append(
                ["", "", region, row["code"], row["name"], row["endonym"],
                 strings, row["strings"], 0]
            )
        self._refresh_language_marks()
        self._select_language_row(self._preview.lang_combo.get_active_id())

    def _refresh_language_marks(self) -> None:
        """Mark the current language (✓) and a pending override (Restart)."""
        session = envinsp_catalog.session_language(glocale)
        override = CONFIG.get("language.restart-override")
        restart_icon = _restart_icon_name()
        # Changing the sort column values of a sorted store moves rows while
        # they are being visited: pause sorting, then restore it.
        sort_col, sort_order = self._lang_store.get_sort_column_id()
        self._lang_store.set_sort_column_id(
            Gtk.TREE_SORTABLE_UNSORTED_SORT_COLUMN_ID, Gtk.SortType.ASCENDING
        )
        for index, row in enumerate(self._lang_store):
            code = row[_LC_CODE]
            position = next(
                (i for i, r in enumerate(self._lang_rows) if r["code"] == code), index
            )
            if override and code == override and override != session:
                row[_LC_ICON], row[_LC_CURRENT] = restart_icon, _("Restart")
                row[_LC_RANK] = 1000 + position
            elif code == session:
                row[_LC_ICON], row[_LC_CURRENT] = "", "\u2713"
                row[_LC_RANK] = position
            else:
                row[_LC_ICON], row[_LC_CURRENT] = "", ""
                row[_LC_RANK] = 2000 + position
        if sort_col is None or sort_col < 0:
            sort_col, sort_order = _LC_RANK, Gtk.SortType.ASCENDING
        self._lang_store.set_sort_column_id(sort_col, sort_order)

    def _center_language_row(self) -> bool:
        """After a re-sort, center the selected row (or else the current language)."""
        if not self._lang_rows:
            return False
        model, tree_iter = self._lang_view.get_selection().get_selected()
        path = model.get_path(tree_iter) if tree_iter is not None else None
        if path is None:
            session = envinsp_catalog.session_language(glocale)
            path = next((row.path for row in self._lang_store if row[_LC_CODE] == session), None)
        if path is not None:
            self._lang_view.scroll_to_cell(path, None, True, 0.5, 0.0)
        return False  # run once

    # --- keeping the Language tab and the Translation Preview in step ----
    def _select_language_row(self, code: str | None) -> None:
        if not code or not self._lang_rows:
            return
        for row in self._lang_store:
            if row[_LC_CODE] == code:
                self._syncing_language = True
                try:
                    self._lang_view.get_selection().select_iter(row.iter)
                    self._lang_view.scroll_to_cell(row.path, None, False, 0, 0)
                finally:
                    self._syncing_language = False
                return

    def _cb_lang_selection_changed(self, selection: Gtk.TreeSelection) -> None:
        if self._syncing_language:
            return
        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return
        self._syncing_language = True
        try:
            self._preview.lang_combo.set_active_id(model[tree_iter][_LC_CODE])
        finally:
            self._syncing_language = False

    def _cb_preview_language_changed(self, combo: Gtk.ComboBox) -> None:
        if not self._syncing_language:
            self._select_language_row(combo.get_active_id())

    # --- language for the next Gramps start -----------------------------
    def _cb_lang_row_activated(self, _view: Gtk.TreeView, path: Gtk.TreePath, _col: object) -> None:
        """Double-click: set or unset the language for the next start."""
        code = self._lang_store[path][_LC_CODE]
        session = envinsp_catalog.session_language(glocale)
        old = CONFIG.get("language.restart-override")
        if code == old:
            new = ""
        elif code == session:
            if not old:
                return  # already the current language, nothing to change
            new = ""
        else:
            new = code
        CONFIG.set("language.restart-override", new)
        CONFIG.set("language.restart-override-pid", os.getpid() if new else 0)
        CONFIG.save()
        note = ""
        if envinsp_restart.is_linux():
            ok, message = envinsp_restart.apply_desktop_override(new)
            LOG.info("EnvironmentInspector: desktop entry: %s", message)
            if not ok:
                note = message
        self._refresh_language_marks()
        # A restart is needed to use a new language, or to leave the
        # override language this session was started in.
        if (new and new != session) or (not new and old == session):
            self._ask_restart(new, note)

    def _language_label(self, code: str) -> str:
        for row in self._lang_rows:
            if row["code"] == code:
                return f"{row['name']} ({row['endonym']})" if row["endonym"] != row["name"] else row["name"]
        return code

    def _ask_restart(self, code: str, note: str) -> None:
        target = self._language_label(code) if code else _("the system language")
        dialog = Gtk.MessageDialog(
            transient_for=self.gui.textview.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=_("Restart Gramps in %s?") % target,
        )
        details = [
            _("Gramps closes normally, including the backup on exit, and then starts again. "
              "Its terminal messages are written to %s.") % _RESTART_LOG
        ]
        if envinsp_restart.is_linux() and not note and code:
            details.append(_("This is for one start only. If you choose Later, the next start "
                             "from the desktop menu uses this language once; starting Gramps "
                             "from a terminal does not."))
        if note:
            details.append(_("Desktop menu entry not changed: %s") % note)
        if not envinsp_restart.can_restart():
            details.append(_("Restarting automatically is not available on this system; restart Gramps yourself."))
        else:
            details.append(_("Open editors with unsaved changes ask whether to save them "
                             "first. The family tree that is open now is opened again."))
        if code:
            details.append(_("Spell checking keeps using the dictionary of the system "
                             "language; see the Locale Settings tab."))
        dialog.format_secondary_text("\n\n".join(details))
        dialog.add_button(_("Later"), Gtk.ResponseType.CANCEL)
        if envinsp_restart.can_restart():
            dialog.add_button(_("Restart now"), Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        # Gramps quits without asking about open editors: settle them first.
        if not self._resolve_unsaved_editors():
            self._restart_cancelled()
            return
        if envinsp_restart.spawn_restart(code, _RESTART_LOG, self._open_tree_args()):
            LOG.warning("EnvironmentInspector: restarting Gramps; its output goes to %s", _RESTART_LOG)
            self.uistate.viewmanager.quit()

    def _dirty_editors(self) -> list:
        """Open primary-object editors (Edit Person, ...) with unsaved changes."""
        from gramps.gui.editors.editprimary import EditPrimary

        gwm = getattr(self.uistate, "gwm", None)
        editors = []
        for item in list(getattr(gwm, "id2item", {}).values()):
            try:
                if isinstance(item, EditPrimary) and item.data_has_changed():
                    editors.append(item)
            except Exception:  # editor half-closed: nothing to save
                LOG.debug("EnvironmentInspector: cannot check an editor", exc_info=True)
        return editors

    def _resolve_unsaved_editors(self) -> bool:
        """
        Ask Save / Close without saving / Cancel for every editor with
        unsaved changes, using the Save Changes dialog of Gramps. The dialog
        is shown even when "Do not ask again" was chosen before, because a
        restart must never discard work silently; that choice is kept.
        :returns: True when no editor with unsaved changes is left open.
        """
        from gramps.gui.dialog import SaveDialog

        dont_ask = _configman.get("interface.dont-ask")
        try:
            for editor in self._dirty_editors():
                if editor not in getattr(self.uistate.gwm, "id2item", {}).values():
                    continue  # closed together with an earlier editor
                editor.window.present()
                SaveDialog(
                    _("Save Changes?"),
                    _("Gramps is about to restart. If you close without saving, "
                      "the changes you have made will be lost."),
                    editor._do_close,
                    editor.save,
                    parent=editor.window,
                )
        finally:
            _configman.set("interface.dont-ask", dont_ask)
        return not self._dirty_editors()

    def _restart_cancelled(self) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self.gui.textview.get_toplevel(),
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=_("Restart cancelled"),
        )
        dialog.format_secondary_text(
            _("An editor still has unsaved changes. Save or close it, then "
              "double-click the language again, or restart Gramps yourself.")
        )
        dialog.run()
        dialog.destroy()

    def _open_tree_args(self) -> list[str]:
        """Command-line options that reopen the family tree open now."""
        dbstate = self.dbstate
        try:
            if dbstate is not None and dbstate.is_open():
                path = dbstate.db.get_save_path()
                if path and os.path.isdir(path):
                    return ["-O", path]
        except Exception:
            LOG.debug("EnvironmentInspector: cannot find the open tree", exc_info=True)
        return []

    def _cb_copy_locale_section(self) -> None:
        """Clipboard helper for the current environment metadata blocks."""
        _copy_to_clipboard(self._locale_clip_text)

    def _cb_copy_language_section(self) -> None:
        """Process specific visible sub-elements context lines for clipboard copying."""
        if self._expander.get_expanded() and self._lang_rows:
            header = "\t".join((_("Code"), _("Name"), _("Endonym"), _("Region"), _("Strings")))
            lines = [header] + [
                "\t".join((r["code"], r["name"], r["endonym"], r["region"],
                           str(r["strings"]) if r["strings"] >= 0 else ""))
                for r in self._lang_rows
            ]
            text = "\n".join(lines)
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
        # The English exonym, not the name in the session language (which
        # is the endonym when the session language is the one shown).
        english_name = (
            envinsp_catalog.english_name(envinsp_catalog.session_language(gl))
            or envinsp_catalog.english_name(lang_base or "")
            or code_to_name.get(lang_base, _("Unknown"))
        )
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

    def _language_fields(self, gl: GrampsLocale, info: _LocaleInfo) -> list[tuple[str, str]]:
        """Left column of Current Locale: the language Gramps chose."""
        fields = [
            (_("Locale Code"), gl.locale_code()),
            (_("Language"), info.lang_base),
            (_("Lang"), glocale.lang),
            (_("Region"), info.region_display),
            (_("English Name"), f"{info.english_name} ({info.lang_base})"),
            (_("Endonym"),
             envinsp_catalog.endonym(envinsp_catalog.session_language(glocale), glocale)),
        ]
        if info.localedir:
            fields.append((_("Locale Directory"), info.localedir))
        return fields

    @staticmethod
    def _field_grid(fields: list[tuple[str, str]]) -> Gtk.Grid:
        """A two-column grid of name: value labels (no wrapping)."""
        grid = Gtk.Grid(column_spacing=8, row_spacing=1)
        grid.set_valign(Gtk.Align.START)
        for row, (name, value) in enumerate(fields):
            name_lbl = Gtk.Label(label=f"{name}:", xalign=0.0)
            value_lbl = Gtk.Label(label=value, xalign=0.0)
            value_lbl.set_selectable(True)
            value_lbl.set_can_focus(False)  # no select-all highlight on focus
            grid.attach(name_lbl, 0, row, 1, 1)
            grid.attach(value_lbl, 1, row, 1, 1)
        return grid

    def _insert_locale_panels(self, gl: GrampsLocale, info: _LocaleInfo) -> None:
        """
        The Current Locale panel: icon header (copies the fields) above a
        grid of fields. The other locale settings are on the Locale
        Settings tab.
        """
        language = self._language_fields(gl, info)
        self._locale_clip_text = "\n".join(f"{n}: {v}" for n, v in language)
        panels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        panels.pack_start(
            self._make_icon_header(
                "preferences-desktop-locale",
                f"<b>{GLib.markup_escape_text(_('Current Locale'))}</b>",
                self._cb_copy_locale_section,
            ),
            False, False, 0,
        )
        panels.pack_start(self._field_grid(language), False, False, 0)
        panels.show_all()
        buf = self.gui.textview.get_buffer()
        anchor = buf.create_child_anchor(buf.get_end_iter())
        self.gui.textview.add_child_at_anchor(panels, anchor)
        self.append_text("\n")

    def _populate_language_tab(self) -> None:
        """Clear and refresh the Language reference pane information."""
        self.clear_text()
        gl = GrampsLocale()
        language_dict = gl.get_language_dict()
        code_to_name = {v: k for k, v in language_dict.items()}
        info = self._get_locale_info(gl)

        self._insert_locale_panels(gl, info)

        if info.localedir and os.path.isdir(info.localedir):
            # Only folders holding a Gramps translation (LC_MESSAGES/gramps.mo).
            # On Linux distribution packages the locale directory is the
            # system-wide /usr/share/locale, which has a folder for every
            # language that any installed program is translated into.
            langs = sorted(gl.get_available_translations())
            total = len(langs)
            if info.lang_base not in langs:
                total += 1
            _count_str = _("Gramps Translations (%d)") % total
            self._lang_header = self._insert_icon_header(
                "cs-language", f"<b>{_count_str}</b>", self._cb_copy_language_section,
                newline_before=True, row_double_click=self._cb_toggle_language_expander,
            )
            self._lang_header.set_tooltip_text(_("Double-click to expand or collapse the list"))
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
        types = ["All types", "Remote Directory", "Directory", "Glade Interface", "File", "Value"]
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
            if tip_text != _(self._selected_type_filter):
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
        elif os.path.isfile(value) and value.lower().endswith(".glade"):
            self._open_glade_file(value)
        elif os.path.isdir(value) or os.path.isfile(value):
            open_file_with_default_application(value, self.gui.uistate)

    def _open_glade_file(self, path: str) -> None:
        """
        Open a .glade file with the program set for Glade files, or else
        with the text editor.

        Glade files are XML, so without a program for Glade files the
        desktop falls back to the one for XML, often a web browser, which
        saves a copy in the Downloads folder instead of showing the file.
        Only a program that names the Glade file type itself counts, not
        one inherited from XML.
        """
        ctype, _uncertain = Gio.content_type_guess(path, None)
        default = Gio.AppInfo.get_default_for_type(ctype, False)
        exact = Gio.AppInfo.get_recommended_for_type(ctype)
        if default is not None and any(app.equal(default) for app in exact):
            app = default
        else:
            app = Gio.AppInfo.get_default_for_type("text/plain", False)
        if app is None:
            open_file_with_default_application(path, self.gui.uistate)
            return
        try:
            app.launch([Gio.File.new_for_path(path)], None)
        except GLib.Error as err:
            LOG.warning("EnvironmentInspector: cannot open %s with %s: %s",
                        path, app.get_name(), err.message)
            open_file_with_default_application(path, self.gui.uistate)

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