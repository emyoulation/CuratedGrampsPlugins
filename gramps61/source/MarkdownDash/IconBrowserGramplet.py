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
"""Icon Browser gramplet for the Gramps Dashboard.

Inventories every icon available in the current GTK / Gramps icon-theme cascade
(per the `freedesktop Icon Theme Specification
<https://specifications.freedesktop.org/icon-theme/latest/>`_) and presents
them in a two-pane browser.

Features
--------
- Tree-view inventory mapping every icon name available across the active desktop
  and custom application icon-theme cascades.
- Inline status checkmarks indicating whether a given icon size natively belongs
  to the theme directory search path or relies on fallback cascades.
- Search-as-you-type fuzzy string filtering paired with Freedesktop context grouping
  comboboxes (Actions, Apps, Status, Stock, etc.).
- Right-hand detail strip profiling all nominal pixel size renderings (16px to 128px)
  with visual indicators differentiating native sharp resources from scaled fallbacks.
- Live path resolution detailing the absolute on-disk source file or binary-builtin
  backing the selected icon asset.
- MarkdownDash clipboard integration: a dynamically populated layout grid generating
  valid `![](gramps:icon:name:size)` markup tags with instant click-to-copy buttons.
- Fluid layout geometry: splits list and detail elements at an exact 50%/50% center
  ratio on instantiation while remaining completely resizable.
- Zero-leak typing loop optimized using static style resource pooling across rapid
  search-filter cycles.

Generated-by: Gemini 1.5 Pro / Ultra (Google, gemini-model-cascade, release 2026-05)
Prompts: "render complete replacement IconBrowserGramplet.py; filter out fallback sizes
in MarkdownDash syntax grid section displaying only available sizes; rearrange tree columns
so checkmark comes first with fixed narrow width; compress thumbnail icon column; automatically
highlight and center-scroll to gramps-view icon on load via idle callback; safely handle GTK
parent container property lifecycle; isolate and fix rapid typing memory leaks caused by dynamic
Gtk.CssProvider instantiation by mapping static global class providers instead; alter Gtk.Paned
defaults to anchor on an initial fluid 50%/50% split via a single-shot size-allocate handler."
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import logging
from typing import NamedTuple

# ------------------------
# Gramps modules
# ------------------------
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gtk, Pango

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import Gramplet

# ------------------------
# Gramps specific
# ------------------------
try:
    _ = glocale.get_addon_translator(__file__).gettext
except (ValueError, AttributeError):
    _ = glocale.translation.gettext

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Standard icon sizes shown in the detail strip (px).
DETAIL_SIZES: list[int] = [16, 22, 24, 32, 48, 64, 96, 128]

#: Freedesktop standard contexts, in the order we want to display them.
KNOWN_CONTEXTS: list[str] = [
    "Actions",
    "Apps",
    "Categories",
    "Devices",
    "Emblems",
    "Emotes",
    "FileSystems",
    "International",
    "MimeTypes",
    "Places",
    "Status",
    "Stock",
]

#: Thumbnail size used in the left-pane list column.
THUMB_SIZE: int = 16

#: Column indices for the list :class:`Gtk.ListStore`.
COL_PIXBUF = 0
COL_NAME = 1
COL_IN_THEME = 2
COL_CONTEXT = 3


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """XML-escape *text* for safe use in Pango markup."""
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _load_pixbuf(
    icon_theme: Gtk.IconTheme, name: str, size: int
) -> GdkPixbuf.Pixbuf | None:
    """Load *name* from *icon_theme* at *size* px."""
    flags = (
        Gtk.IconLookupFlags.GENERIC_FALLBACK
        | Gtk.IconLookupFlags.USE_BUILTIN
    )
    try:
        return icon_theme.load_icon(name, size, flags)
    except Exception:
        return None


# ---------------------------------------------------------------------------
#
# IconBrowserGramplet
#
# ---------------------------------------------------------------------------
class IconBrowserGramplet(Gramplet):
    """Dashboard gramplet: live GTK/Gramps icon-theme browser."""

    def on_load(self) -> None:
        """Gramps lifecycle hook."""

    def on_unload(self) -> None:
        """Disconnect theme-change signal handler."""
        handler = getattr(self, "_theme_handler_id", None)
        if handler is not None:
            try:
                settings = Gtk.Settings.get_default()
                if settings is not None:
                    settings.disconnect(handler)
            except Exception:
                pass
            self._theme_handler_id = None

    def init(self) -> None:
        """Build the gramplet UI safely inside Gramps' layout architecture."""
        # 1. Get the container ScrolledWindow provided by Gramps
        gramps_sw = self.gui.get_container_widget()

        # 2. Clear out any default children Gramps packed inside it
        for child in gramps_sw.get_children():
            gramps_sw.remove(child)

        # 3. Create a layout container box to hold both the functional browser and the footer
        inner_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # 4. Generate the inner UI elements
        browser_content = self._build_browser_content()
        footer_box = self._build_footer()

        # 5. Pack them cleanly inside our nested box layout
        inner_vbox.pack_start(browser_content, True, True, 0)
        inner_vbox.pack_end(footer_box, False, False, 0)
        inner_vbox.pack_end(Gtk.Separator(), False, False, 0)

        # 6. Add our complete layout structure straight to Gramps' stable ScrolledWindow
        gramps_sw.add(inner_vbox)

        self.gui.WIDGET = inner_vbox
        inner_vbox.show_all()

        # 7. Safely register a single shared monospace class once to prevent typing leaks
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b".mono-text { font-family: monospace; }")
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Connect to GTK settings for theme-change auto-refresh
        settings = Gtk.Settings.get_default()
        if settings is not None:
            self._theme_handler_id = settings.connect(
                "notify::gtk-theme-name", self._on_theme_changed
            )
        else:
            self._theme_handler_id = None

        self._refresh()

    def _build_footer(self) -> Gtk.Box:
        """Create the footer layout skeleton."""
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        footer.set_border_width(3)

        self._theme_label = Gtk.Label()
        self._theme_label.set_halign(Gtk.Align.START)
        self._theme_label.set_hexpand(True)
        self._theme_label.set_ellipsize(Pango.EllipsizeMode.END)
        footer.pack_start(self._theme_label, True, True, 0)

        self._count_label = Gtk.Label()
        self._count_label.set_halign(Gtk.Align.END)
        footer.pack_start(self._count_label, False, False, 0)

        refresh_btn = Gtk.Button()
        refresh_img = Gtk.Image.new_from_icon_name(
            "view-refresh", Gtk.IconSize.SMALL_TOOLBAR
        )
        refresh_btn.set_image(refresh_img)
        refresh_btn.set_relief(Gtk.ReliefStyle.NONE)
        refresh_btn.set_tooltip_text(_("Refresh icon inventory"))
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        footer.pack_end(refresh_btn, False, False, 0)

        return footer

    def _build_browser_content(self) -> Gtk.Box:
        """Build the internal functional browser UI."""
        content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # -- Search / Context Bar --
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top_bar.set_border_width(4)

        search_lbl = Gtk.Label(label=_("Search:"))
        top_bar.pack_start(search_lbl, False, False, 0)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(_("filter icon names…"))
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        top_bar.pack_start(self._search_entry, True, True, 0)

        self._ctx_combo = Gtk.ComboBoxText()
        self._ctx_combo.append("*", _("All"))
        for ctx in KNOWN_CONTEXTS:
            self._ctx_combo.append(ctx, ctx)
        self._ctx_combo.append("Other", _("Other"))
        self._ctx_combo.set_active_id("*")
        self._ctx_combo.connect("changed", self._on_context_changed)
        top_bar.pack_start(self._ctx_combo, False, False, 0)

        content_vbox.pack_start(top_bar, False, False, 0)
        content_vbox.pack_start(Gtk.Separator(), False, False, 0)

        # -- List | Detail Paned view --
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        # Split layout evenly (50/50) automatically once size allocation resolves
        def _set_initial_split(widget, allocation):
            widget.set_position(allocation.width // 2)
            widget.disconnect(handler_id)

        handler_id = paned.connect("size-allocate", _set_initial_split)

        self._store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, bool, str)
        self._filter = self._store.filter_new()
        self._filter.set_visible_func(self._row_visible)
        self._sort_model = Gtk.TreeModelSort(model=self._filter)

        self._tree = Gtk.TreeView(model=self._sort_model)
        self._tree.get_selection().connect("changed", self._on_selection_changed)

        # 1. First Column: Theme Checkmark (No header title, ~25% width)
        rend_flag = Gtk.CellRendererText()
        col_flag = Gtk.TreeViewColumn("", rend_flag)
        col_flag.set_cell_data_func(rend_flag, self._render_flag_cell)
        col_flag.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_flag.set_fixed_width(20)
        self._tree.append_column(col_flag)

        # 2. Second Column: Thumbnail Icon (Compressed to 50% width)
        rend_pb = Gtk.CellRendererPixbuf()
        col_thumb = Gtk.TreeViewColumn("", rend_pb, pixbuf=COL_PIXBUF)
        col_thumb.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_thumb.set_fixed_width(24)
        self._tree.append_column(col_thumb)

        # 3. Third Column: Icon Name (Takes up remaining space fluidly)
        rend_txt = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn(_("Icon Name"), rend_txt, text=COL_NAME)
        col_name.set_sort_column_id(COL_NAME)
        col_name.set_expand(True)
        self._tree.append_column(col_name)

        list_sw = Gtk.ScrolledWindow()
        list_sw.add(self._tree)
        paned.pack1(list_sw, resize=True, shrink=False)

        detail_sw = Gtk.ScrolledWindow()
        self._detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._detail_box.set_border_width(8)
        detail_sw.add(self._detail_box)
        paned.pack2(detail_sw, resize=True, shrink=False)

        content_vbox.pack_start(paned, True, True, 0)
        return content_vbox

    def _refresh(self) -> None:
        """Inventory icons and populate list."""
        self._store.clear()
        self._clear_detail()
        icon_theme = Gtk.IconTheme.get_default()

        # Update theme label
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:
            gtk_theme = gtk_settings.get_property("gtk-theme-name") or ""
            self._theme_label.set_markup(
                "<small><span foreground='#555555'>{} <b>{}</b></span></small>".format(
                    _("Theme:"), _esc(gtk_theme)
                )
            )

        all_names = icon_theme.list_icons(None) or []
        name_to_ctx = {}
        for ctx in KNOWN_CONTEXTS:
            for n in (icon_theme.list_icons(ctx) or []):
                if n not in name_to_ctx:
                    name_to_ctx[n] = ctx

        theme_dirs = set(icon_theme.get_search_path() or [])
        for name in sorted(all_names, key=str.casefold):
            ctx = name_to_ctx.get(name, "Other")
            pb = _load_pixbuf(icon_theme, name, THUMB_SIZE)

            info = icon_theme.lookup_icon(name, 22, 0)
            in_theme = False
            if info:
                fn = info.get_filename() or ""
                in_theme = any(fn.startswith(d) for d in theme_dirs)

            self._store.append([pb, name, in_theme, ctx])

        self._update_count_label()
        self._filter.refilter()

        # Safely queue selecting and scrolling to 'gramps-view' on idle loop execution
        GLib.idle_add(self._select_default_icon, "gramps-view")

    def _select_default_icon(self, target_name: str) -> bool:
        """Finds target_name in the sorted model, selects it, and scrolls to it."""
        if not self._tree or not self._sort_model:
            return False

        it = self._sort_model.get_iter_first()
        while it is not None:
            name = self._sort_model.get_value(it, COL_NAME)
            if name == target_name:
                path = self._sort_model.get_path(it)
                selection = self._tree.get_selection()
                selection.select_path(path)
                self._tree.scroll_to_cell(path, None, True, 0.5, 0.0)
                break
            it = self._sort_model.iter_next(it)

        return False

    def _row_visible(self, model, it, _data) -> bool:
        """Filter logic for search and context."""
        name = model.get_value(it, COL_NAME) or ""
        ctx = model.get_value(it, COL_CONTEXT) or ""
        active_ctx = self._ctx_combo.get_active_id() or "*"
        if active_ctx != "*" and ctx != active_ctx:
            return False
        query = self._search_entry.get_text().strip().lower()
        return not query or query in name.lower()

    @staticmethod
    def _render_flag_cell(_col, renderer, model, it, _data) -> None:
        in_theme = model.get_value(it, COL_IN_THEME)
        renderer.set_property("foreground", "#006600" if in_theme else "#999999")
        renderer.set_property("text", "✓" if in_theme else "–")

    def _clear_detail(self) -> None:
        for child in self._detail_box.get_children():
            self._detail_box.remove(child)

    def _populate_detail(self, icon_name: str) -> None:
        """Fill the right-hand detail pane for *icon_name*."""
        self._clear_detail()

        icon_theme = Gtk.IconTheme.get_default()

        # ── heading ───────────────────────────────────────────────────
        heading = Gtk.Label()
        heading.set_markup(
            "<b><big>{}</big></b>".format(_esc(icon_name))
        )
        heading.set_halign(Gtk.Align.START)
        heading.set_selectable(True)
        self._detail_box.pack_start(heading, False, False, 0)

        # ── size strip ────────────────────────────────────────────────
        strip_lbl = Gtk.Label()
        strip_lbl.set_markup(
            "<small><b>{}</b></small>".format(_("Available sizes"))
        )
        strip_lbl.set_halign(Gtk.Align.START)
        self._detail_box.pack_start(strip_lbl, False, False, 2)

        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        strip.set_border_width(4)

        fallback_sizes: list[int] = []
        self._current_available_sizes: list[int] = []

        for px in DETAIL_SIZES:
            pb = _load_pixbuf(icon_theme, icon_name, px)
            if pb is None:
                continue

            info = icon_theme.lookup_icon(
                icon_name, px, Gtk.IconLookupFlags.USE_BUILTIN
            )
            is_native = False
            if info is not None:
                base = info.get_base_size()
                is_native = (base == px or base == 0)

            cell = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2
            )

            img_widget = Gtk.Image.new_from_pixbuf(pb)
            cell.pack_start(img_widget, False, False, 0)

            colour = "#000000" if is_native else "#999999"
            size_lbl = Gtk.Label()
            size_lbl.set_markup(
                "<small><span foreground='{}'>{}</span></small>".format(
                    colour, px
                )
            )
            cell.pack_start(size_lbl, False, False, 0)
            strip.pack_start(cell, False, False, 4)

            if is_native:
                self._current_available_sizes.append(px)
            else:
                fallback_sizes.append(px)

        if not strip.get_children():
            missing = Gtk.Label(
                label=_("(icon not found in current theme)")
            )
            missing.set_halign(Gtk.Align.START)
            self._detail_box.pack_start(missing, False, False, 0)
            self._detail_box.show_all()
            return

        strip_sw = Gtk.ScrolledWindow()
        strip_sw.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER
        )
        strip_sw.set_min_content_height(DETAIL_SIZES[-1] + 36)
        strip_sw.add(strip)
        self._detail_box.pack_start(strip_sw, False, False, 0)

        # ── fallback / theme notes ────────────────────────────────────
        self._detail_box.pack_start(Gtk.Separator(), False, False, 4)

        info_main = icon_theme.lookup_icon(
            icon_name, 48, Gtk.IconLookupFlags.GENERIC_FALLBACK
        )
        if info_main is not None:
            filepath = info_main.get_filename() or ""
            theme_note = Gtk.Label()
            theme_note.set_markup(
                "<small><span foreground='#555555'>{}</span></small>".format(
                    _esc(filepath)
                )
            )
            theme_note.set_halign(Gtk.Align.START)
            theme_note.set_line_wrap(True)
            theme_note.set_selectable(True)
            self._detail_box.pack_start(theme_note, False, False, 0)

        if fallback_sizes:
            fb_lbl = Gtk.Label()
            fb_lbl.set_markup(
                "<small><span foreground='#999999'>"
                "{}: {}</span></small>".format(
                    _("Scaled (not native)"),
                    ", ".join(str(s) for s in fallback_sizes),
                )
            )
            fb_lbl.set_halign(Gtk.Align.START)
            self._detail_box.pack_start(fb_lbl, False, False, 0)

        # ── MarkdownDash source ───────────────────────────────────────
        self._detail_box.pack_start(Gtk.Separator(), False, False, 4)

        md_heading = Gtk.Label()
        md_heading.set_markup(
            "<small><b>{}</b></small>".format(
                _("MarkdownDash gramps:icon syntax")
            )
        )
        md_heading.set_halign(Gtk.Align.START)
        self._detail_box.pack_start(md_heading, False, False, 0)

        # Build a grid: size | syntax | copy button
        md_grid = Gtk.Grid()
        md_grid.set_column_spacing(8)
        md_grid.set_row_spacing(4)
        md_grid.set_border_width(4)

        show_sizes = self._current_available_sizes
        for row_idx, px in enumerate(show_sizes):
            pb = _load_pixbuf(icon_theme, icon_name, min(px, 32))
            if pb:
                img_prev = Gtk.Image.new_from_pixbuf(pb)
            else:
                img_prev = Gtk.Image()
            md_grid.attach(img_prev, 0, row_idx, 1, 1)

            syntax = "![](gramps:icon:{}:{})".format(icon_name, px)
            src_lbl = Gtk.Label(label=syntax)
            src_lbl.set_halign(Gtk.Align.START)
            src_lbl.set_selectable(True)
            src_lbl.set_hexpand(True)

            # Assign style safely using the global static CSS class
            src_lbl.get_style_context().add_class("mono-text")
            md_grid.attach(src_lbl, 1, row_idx, 1, 1)

            copy_btn = Gtk.Button()
            copy_img = Gtk.Image.new_from_icon_name(
                "edit-copy", Gtk.IconSize.SMALL_TOOLBAR
            )
            copy_btn.set_image(copy_img)
            copy_btn.set_relief(Gtk.ReliefStyle.NONE)
            copy_btn.set_tooltip_text(_("Copy to clipboard"))
            copy_btn.connect(
                "clicked",
                self._on_copy_syntax,
                syntax,
            )
            md_grid.attach(copy_btn, 2, row_idx, 1, 1)

        self._detail_box.pack_start(md_grid, False, False, 0)

        # ── default-size note ─────────────────────────────────────────
        default_note = Gtk.Label()
        default_note.set_markup(
            "<small><span foreground='#666666'>"
            "{}: <tt>![](gramps:icon:{})</tt> → 16 px</span></small>".format(
                _("Default (no size suffix)"), _esc(icon_name)
            )
        )
        default_note.set_halign(Gtk.Align.START)
        default_note.set_line_wrap(True)
        self._detail_box.pack_start(default_note, False, False, 0)

        self._detail_box.show_all()

    def _on_selection_changed(self, selection) -> None:
        model, it = selection.get_selected()
        if it:
            self._populate_detail(model.get_value(it, COL_NAME))

    def _on_search_changed(self, _widget) -> None:
        self._filter.refilter()
        self._update_count_label()

    def _on_context_changed(self, _widget) -> None:
        self._filter.refilter()
        self._update_count_label()

    def _on_refresh_clicked(self, _widget) -> None:
        self._refresh()

    def _on_theme_changed(self, _settings, _param) -> None:
        GLib.timeout_add(300, self._deferred_refresh)

    def _deferred_refresh(self) -> bool:
        self._refresh()
        return False

    def _on_copy_syntax(self, _widget, syntax: str) -> None:
        cb = Gtk.Clipboard.get_default(self.uistate.window.get_display())
        cb.set_text(syntax, -1)

    def _update_count_label(self) -> None:
        visible = sum(1 for row in self._store if self._row_visible(self._store, row.iter, None))
        self._count_label.set_markup("<small>{} of {} icons</small>".format(visible, len(self._store)))

    def main(self) -> None:
        """Main loop hook."""