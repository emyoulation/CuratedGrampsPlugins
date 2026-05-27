#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2008       Raphael Ackermann
# Copyright (C) 2010       Benny Malengier
# Copyright (C) 2010       Nick Hall
# Copyright (C) 2012       Doug Blank <doug.blank@gmail.com>
# Copyright (C) 2017       Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2026       Brian McCullough
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
"""Help/Plugin Manager

This module implements the enhanced Plugin manager.  The upper information
panel is rendered via :mod:`MarkdownUtils` into a two-column layout:
left column carries the MarkdownUtils-rendered plugin detail text; right
column shows a preview thumbnail.  The lower panel holds the plugin list
with action buttons and filter checkboxes.

Layout toggle
-------------
The bottom-bar **Help** button (label changes to **Details** when README is
showing) swaps the info panel content between:

* **Details mode** — plugin registration Markdown + placeholder icon.
  Button label: *Help*.
* **README mode** — ``README(PluginMgrPlus).md`` + screenshot
  ``media/PluginMgr_capture.png``.  Button label: *Details*.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "swap layout so info pane is top and plugin list is bottom; add
Help/Details toggle button that swaps README+screenshot vs plugin
details+icon; hotlink fname/fpath, help_url, author/maintainer emails;
render boolean flags as icons; remove Edit/Wiki buttons."
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
"""

# ------------------------
# Python modules
# ------------------------
import logging
import os
import shutil
import sys
import traceback
from operator import itemgetter

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gdk, GdkPixbuf, GObject, Gtk
from gi.repository.GLib import markup_escape_text

from gramps.cli.grampscli import CLIManager
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import URL_MANUAL_PAGE
from gramps.gen.plug import (
    AUDIENCETEXT,
    STATUSTEXT,
    PluginRegister,
    load_addon_file,
    version_str_to_tup,
)
from gramps.gen.plug._pluginreg import GRAMPLET, PTYPE_STR, VIEW
from gramps.gen.plug.utils import get_all_addons
from gramps.gen.utils.requirements import Requirements
from gramps.gui.dialog import OkDialog
from gramps.gui.display import display_help, display_url
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.plug import tool
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.utils import open_file_with_default_application

# ------------------------
# Gramps specific
# ------------------------
try:
    from MarkdownUtils import (
        build_table_widget,
        define_tags,
        parse_markdown,
        resolve_icon_pixbuf,
    )

    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext
ngettext = _trans.ngettext  # else "nearby" comments are ignored

LOG = logging.getLogger(".gui.plug")

WIKI_PAGE = "Addon:Plugin_ManagerV2"
TITLE = _("Plugin Manager plus")
# Some static data, available across instantiations
static = sys.modules[__name__]
static.check_done = False
static.panel = 0

RELOAD_RES = 777  # A custom Gtk response_type for the Reload button
UPDATE_RES = 666  # A custom Gtk response_type for the Update button
IGNORE_RES = 888  # A custom Gtk response_type for the checkboxes

# Status bit mask values
INSTALLED = 1  # INSTALLED, AVAILABLE, and BUILTIN are mutually exclusive
AVAILABLE = 2  # set = available
BUILTIN = 4  # set = builtin
HIDDEN = 8  # set = hidden
UPDATE = 16  # set = Update available

# Plugins model column numbers
R_TYPE = 0
R_STAT_S = 1
R_NAME = 2
R_DESC = 3
R_ID = 4
R_STAT = 5

# Preview placeholder icon names (cycled per plugin to vary the visual)
_PREVIEW_ICONS = [
    "gramps-addon",
    "gramps-viewmedia",
]

# pylint: disable=unused-argument


# ---------------------------------------------------------------------------
#
# _set_btn_icon_label  --  attach an icon + text child to a Gtk.Button
#
# ---------------------------------------------------------------------------
def _set_btn_icon_label(
    btn: "Gtk.Button",
    icon_name: str,
    label_text: str,
    use_mnemonic: bool = False,
) -> None:
    """Replace a :class:`Gtk.Button`'s child with an icon + label box.

    The button is first cleared of its existing child (the plain text label
    that ``add_button`` inserts), then a horizontal :class:`Gtk.Box` holding
    a :class:`Gtk.Image` and a :class:`Gtk.Label` is packed in.

    Falls back gracefully when the named icon is not available in the current
    theme: the icon slot is simply omitted and the label stands alone.

    :param btn:          The button whose child will be replaced.
    :param icon_name:    Freedesktop icon name (e.g. ``'help-browser'``).
    :param label_text:   Visible label string (may include mnemonic ``_``).
    :param use_mnemonic: When ``True`` the label honours underscore mnemonics.
    """
    # Remove whatever child add_button() placed there
    existing = btn.get_child()
    if existing is not None:
        btn.remove(existing)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

    # Icon — load as pixbuf explicitly to avoid the theme mapping the name to
    # its *.symbolic variant (which GTK does automatically when using
    # new_from_icon_name with a symbolic-capable style context).
    # Requesting the pixbuf directly bypasses that recolouring path.
    theme = Gtk.IconTheme.get_default()
    if theme.has_icon(icon_name):
        try:
            # FORCE_SIZE gives us a clean 16-px render; no FORCE_SYMBOLIC flag
            # so the full-colour PNG/SVG is used when available.
            pb = theme.load_icon(
                icon_name,
                Gtk.icon_size_lookup(Gtk.IconSize.BUTTON)[1],
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
            img = Gtk.Image.new_from_pixbuf(pb)
        except Exception:
            img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        hbox.pack_start(img, False, False, 0)

    if use_mnemonic:
        lbl = Gtk.Label()
        lbl.set_text_with_mnemonic(label_text)
    else:
        lbl = Gtk.Label(label=label_text)
    hbox.pack_start(lbl, False, False, 0)

    hbox.show_all()
    btn.add(hbox)


# ---------------------------------------------------------------------------
#
# _MdInfoPane  --  reusable MarkdownUtils-backed text pane
#
# ---------------------------------------------------------------------------
class _MdInfoPane:
    """A :class:`Gtk.TextView` populated from Markdown via :mod:`MarkdownUtils`.

    Provides :meth:`render` which accepts a Markdown string and renders it
    into a fresh :class:`Gtk.TextBuffer`, and :meth:`widget` which returns
    the :class:`Gtk.ScrolledWindow` that can be packed into any container.

    :param uistate: Gramps uistate (used for link-click dispatching if needed).
    """

    def __init__(self, uistate) -> None:
        """Initialise the text view and its containing scrolled window.

        :param uistate: Gramps uistate reference.
        """
        self._uistate = uistate
        self._tags: dict = {}
        self._link_uris: dict = {}
        self._link_counter: list[int] = [0]

        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_left_margin(10)
        self.textview.set_right_margin(8)
        self.textview.set_top_margin(6)
        self.textview.set_bottom_margin(4)
        self.textview.set_pixels_above_lines(1)
        self.textview.set_pixels_below_lines(1)
        self.textview.set_vexpand(True)
        self.textview.set_hexpand(True)

        self._cursor_normal = Gdk.Cursor.new_from_name(
            self.textview.get_display(), "default"
        )
        self._cursor_link = Gdk.Cursor.new_from_name(
            self.textview.get_display(), "pointer"
        )
        self.textview.set_events(
            self.textview.get_events()
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
        )
        self.textview.connect("motion-notify-event", self._on_motion)
        self.textview.connect("button-press-event", self._on_click)

        self._sw = Gtk.ScrolledWindow()
        self._sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._sw.add(self.textview)

    @property
    def widget(self) -> Gtk.ScrolledWindow:
        """Return the :class:`Gtk.ScrolledWindow` wrapping the text view.

        :returns: The containing scrolled window widget.
        """
        return self._sw

    def render(self, md_text: str, base_dir: str = "") -> None:
        """Parse *md_text* as Markdown and populate the text buffer.

        Relative image paths in ``![alt](path)`` tags are resolved against
        *base_dir* (typically the directory of the loaded ``.md`` file).
        When *base_dir* is empty or the resolved file does not exist the
        image falls back to a clickable ``[image: alt]`` placeholder styled
        in the ``image_link`` colour — matching the behaviour of
        :class:`MarkdownDash`.

        Falls back to inserting plain text if :mod:`MarkdownUtils` is not
        importable.

        :param md_text:  Markdown-formatted string to render.
        :param base_dir: Directory used to resolve relative image paths.
                         Pass the directory of the ``.md`` file being shown.
        """
        if not _MARKDOWN_AVAILABLE:
            buf = Gtk.TextBuffer()
            buf.set_text(md_text)
            self.textview.set_buffer(buf)
            return

        buf = Gtk.TextBuffer()
        self.textview.set_buffer(buf)
        self._tags = define_tags(buf)
        self._link_uris = {}
        self._link_counter[0] = 0

        import gi

        gi.require_version("Pango", "1.0")
        from gi.repository import Pango

        def _make_link_tag(style: str, uri: str) -> Gtk.TextTag:
            """Create a unique per-link tag in *buf*.

            :param style: Visual style key (``'hyperlink'``, ``'gramps_link'``).
            :param uri:   The URI string for the link.
            :returns:     Newly created :class:`Gtk.TextTag`.
            """
            self._link_counter[0] += 1
            name = "_link_{}".format(self._link_counter[0])
            colours = {
                "hyperlink": ("#0055cc", None),
                "gramps_link": ("#8800aa", "#f5eeff"),
                "image_link": ("#0077aa", "#eef4ff"),
                "anchor_link": ("#006633", None),
                "mailto_link": ("#007755", None),
                "file_link": ("#885500", "#fff8ee"),
            }
            fg, bg = colours.get(style, ("#0055cc", None))
            kw: dict = {"foreground": fg, "underline": Pango.Underline.SINGLE}
            if bg:
                kw["background"] = bg
            t = buf.create_tag(name, **kw)
            self._link_uris[name] = (uri, style)
            return t

        def _resolve_path(path: str) -> str:
            """Resolve *path* relative to *base_dir*.

            :param path: Absolute or relative image path from Markdown source.
            :returns:    Resolved absolute path (may not exist).
            """
            if os.path.isabs(path):
                return path
            if base_dir:
                candidate = os.path.join(base_dir, path)
                if os.path.isfile(candidate):
                    return candidate
            return path

        def _insert_image(img_path: str, alt_text: str) -> bool:
            """Load *img_path* as a pixbuf and insert it into *buf* at current end.

            Scales wide images to fit within 560 px.  Appends an italic
            caption line when *alt_text* is non-empty.

            :param img_path: Absolute path to an image file.
            :param alt_text: Alt / caption text; may be empty.
            :returns:        ``True`` on success, ``False`` on any error.
            """
            try:
                max_w = 560
                pb = GdkPixbuf.Pixbuf.new_from_file(img_path)
                w, h = pb.get_width(), pb.get_height()
                if w > max_w:
                    h = int(h * max_w / w)
                    w = max_w
                    pb = pb.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
                end_it = buf.get_end_iter()
                buf.insert_pixbuf(end_it, pb)
                end_it = buf.get_end_iter()
                buf.insert(end_it, "\n")
                caption_tag = self._tags.get("blockquote")
                if alt_text and caption_tag:
                    end_it = buf.get_end_iter()
                    sm = buf.create_mark(None, end_it, True)
                    buf.insert(end_it, alt_text + "\n")
                    si = buf.get_iter_at_mark(sm)
                    buf.apply_tag(caption_tag, si, buf.get_end_iter())
                    buf.delete_mark(sm)
                return True
            except Exception:
                LOG.debug("Could not insert image: %s", img_path, exc_info=True)
                return False

        segments = parse_markdown(md_text)
        it = buf.get_end_iter()

        for seg in segments:
            if seg.table_data:
                columns, align, body_rows, sep_widths = seg.table_data
                tbl = build_table_widget(columns, align, body_rows, sep_widths)
                anchor = buf.create_child_anchor(it)
                self.textview.add_child_at_anchor(tbl, anchor)
                tbl.show_all()

            elif seg.gramps_icon:
                icon_name, size = seg.gramps_icon
                pb = resolve_icon_pixbuf(icon_name, size)
                if pb:
                    buf.insert_pixbuf(it, pb)
                else:
                    sm = buf.create_mark(None, it, True)
                    buf.insert(it, "[{}]".format(icon_name))
                    si = buf.get_iter_at_mark(sm)
                    t = self._tags.get("blockquote")
                    if t:
                        buf.apply_tag(t, si, it)
                    buf.delete_mark(sm)

            elif seg.url:
                # Determine link style from URI scheme
                if seg.url.startswith("mailto:"):
                    style = "mailto_link"
                elif seg.url.startswith("file://"):
                    style = "file_link"
                elif seg.url.startswith("#"):
                    style = "anchor_link"
                elif seg.url.startswith("gramps:"):
                    style = "gramps_link"
                elif seg.url.startswith("image:"):
                    style = "image_link"
                else:
                    style = "hyperlink"
                link_tag = _make_link_tag(style, seg.url)
                sm = buf.create_mark(None, it, True)
                buf.insert(it, seg.text)
                si = buf.get_iter_at_mark(sm)
                buf.apply_tag(link_tag, si, it)
                buf.delete_mark(sm)

            elif seg.image_path:
                # Resolve path relative to base_dir and try to load as pixbuf.
                # Falls back to a clickable placeholder if file not found.
                resolved = _resolve_path(seg.image_path)
                inserted = False
                if os.path.isfile(resolved):
                    inserted = _insert_image(resolved, seg.text)
                if not inserted:
                    display = "[image: {}]".format(seg.text or seg.image_path)
                    link_tag = _make_link_tag("image_link", seg.image_path)
                    sm = buf.create_mark(None, it, True)
                    buf.insert(it, display)
                    si = buf.get_iter_at_mark(sm)
                    buf.apply_tag(link_tag, si, it)
                    buf.delete_mark(sm)

            else:
                sm = buf.create_mark(None, it, True)
                buf.insert(it, seg.text)
                si = buf.get_iter_at_mark(sm)
                for attr in seg.attrs:
                    t = self._tags.get(attr)
                    if t:
                        buf.apply_tag(t, si, it)
                buf.delete_mark(sm)

            it = buf.get_end_iter()

    # ── event helpers ──────────────────────────────────────────────────────

    def _tag_at(self, x: int, y: int) -> tuple[str | None, str | None]:
        """Return ``(style, uri)`` for the topmost interactive tag at ``(x,y)``.

        :param x: Widget-relative X pixel coordinate.
        :param y: Widget-relative Y pixel coordinate.
        :returns: ``(style, uri)`` or ``(None, None)`` if no link is found.
        """
        bx, by = self.textview.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
        it = self.textview.get_iter_at_position(bx, by)[1]
        for tag in it.get_tags():
            name = tag.get_property("name")
            entry = self._link_uris.get(name)
            if entry is not None:
                uri, style = entry
                return style, uri
        return None, None

    def _on_motion(self, widget: Gtk.TextView, event: Gdk.EventMotion) -> bool:
        """Switch cursor to a hand when hovering a link.

        :param widget: The :class:`Gtk.TextView`.
        :param event:  The motion event.
        :returns: ``False`` (event not consumed).
        """
        if not widget.get_realized():
            return False
        style, _uri = self._tag_at(int(event.x), int(event.y))
        cursor = self._cursor_link if style else self._cursor_normal
        win = widget.get_window(Gtk.TextWindowType.TEXT)
        if win:
            win.set_cursor(cursor)
        return False

    def _on_click(self, widget: Gtk.TextView, event: Gdk.EventButton) -> bool:
        """Dispatch a click on a link.

        :param widget: The :class:`Gtk.TextView`.
        :param event:  The button-press event.
        :returns: ``True`` if the event was consumed.
        """
        if event.button != 1:
            return False
        style, uri = self._tag_at(int(event.x), int(event.y))
        if not uri:
            return False
        if style in ("hyperlink", "gramps_link"):
            try:
                import gi as _gi

                _gi.require_version("Gio", "2.0")
                from gi.repository import Gio

                Gio.AppInfo.launch_default_for_uri(uri, None)
            except Exception:
                try:
                    import subprocess

                    subprocess.Popen(["xdg-open", uri])
                except Exception:
                    pass
        elif style == "mailto_link":
            try:
                import gi as _gi

                _gi.require_version("Gio", "2.0")
                from gi.repository import Gio

                Gio.AppInfo.launch_default_for_uri(uri, None)
            except Exception:
                pass
        elif style == "file_link":
            path = uri[len("file://") :]
            if os.path.isfile(path):
                try:
                    open_file_with_default_application(path, self._uistate)
                except Exception:
                    pass
        return True


# ---------------------------------------------------------------------------
#
# PluginStatus  --  Enhanced Plugin Manager
#
# ---------------------------------------------------------------------------
class PluginStatus(tool.Tool, ManagedWindow):
    """Plugin manager loading controls."""

    def __init__(self, dbstate, uistate, track):
        """Initialise the enhanced plugin manager dialog.

        :param dbstate: The Gramps database state object.
        :param uistate: The Gramps UI state object.
        :param track:   ManagedWindow tracking list.
        """
        self.uistate = uistate
        self.dbstate = dbstate
        self._show_builtins = None
        self._show_hidden = None
        self._show_available = None
        self._show_addons = None
        self.addons = []
        self.infodata = ""
        self.name = ""
        self.help = ""
        self.helpname = ""

        self.options = PluginManagerOptions("pluginmanager")
        self.options.load_previous_values()
        self.options_dict = self.options.handler.options_dict
        self.window = Gtk.Dialog(title=TITLE)
        ManagedWindow.__init__(self, uistate, track, self.__class__)
        self.set_window(self.window, None, TITLE, None)
        self._pmgr = GuiPluginManager.get_instance()
        self._preg = PluginRegister.get_instance()
        self.hidden = self._pmgr.get_hidden_plugin_ids()
        self.setup_configs("interface.pluginstatus", 800, 650)

        # Toggle state: False = plugin details shown (default); True = README shown.
        self._readme_showing: bool = False
        # Cache the last-selected pid so the Help↔Details toggle can redisplay it.
        self._current_pid: str | None = None

        # ── Bottom action bar ──────────────────────────────────────────────
        # The Help/Details toggle button — label and icon change with mode.
        # In details mode (default) the button shows "Help" (opens README).
        # In README mode the button shows "Details" (returns to plugin info).
        self._help_btn = self.window.add_button(  # pylint: disable=no-member
            "", Gtk.ResponseType.HELP
        )
        self.btn_box = self._help_btn.get_parent()
        self.btn_box.set_child_non_homogeneous(self._help_btn, True)
        _set_btn_icon_label(
            self._help_btn, "help-browser", _("_Help"), use_mnemonic=True
        )
        self._help_btn.set_tooltip_text(
            _("Show the Plugin Manager README and screenshot")
        )

        # count label LEFT of the search box
        self._count_label = Gtk.Label()
        self._count_label.set_markup("<small>Showing 0 of 0 plugins</small>")
        self.btn_box.pack_start(self._count_label, False, False, 4)
        self.btn_box.set_child_non_homogeneous(self._count_label, True)

        # filter input box
        self.filter_entry = Gtk.SearchEntry()
        self.filter_entry.set_tooltip_text(
            _(
                "Filter plugins by entering search terms.\n"
                "\n"
                "Default (all-words mode): every word must appear somewhere\n"
                "in the row data or filename.  Word order and case are ignored.\n"
                "\n"
                "Exact-phrase mode: wrap the query in double-quotes.\n"
                '  e.g.  "person card"  matches only rows that contain\n'
                "  that exact substring (still case-insensitive).\n"
                "\n"
                "All visible fields are searched: Type, Status, Name,\n"
                "Description, ID, filename, path, authors, version, category,\n"
                "target version, and other registration metadata."
            )
        )
        self.filter_entry.set_placeholder_text(_("Search..."))
        self.btn_box.pack_start(self.filter_entry, True, True, 0)
        self.filter_entry.connect("search-changed", self.filter_str_changed)

        if __debug__:
            reload_btn = self.window.add_button(  # pylint: disable=no-member
                "", RELOAD_RES
            )
            _set_btn_icon_label(reload_btn, "view-refresh-symbolic", _("Reload"))
            self.btn_box.set_child_non_homogeneous(reload_btn, True)
            _w0, _wx_ = reload_btn.get_preferred_width()
        else:
            _w0 = 0

        cls_btn = self.window.add_button(
            "", Gtk.ResponseType.CLOSE  # pylint: disable=no-member
        )
        _set_btn_icon_label(cls_btn, "window-close", _("_Close"), use_mnemonic=True)
        self.btn_box.set_child_non_homogeneous(cls_btn, True)
        _w1, dummy = self._help_btn.get_preferred_width()
        _w2, dummy = cls_btn.get_preferred_width()
        _we = 800 - _w0 - _w1 - _w2 - 60
        self.filter_entry.set_size_request(_we, -1)

        # ── Vertical pane: TOP = two-column info panel, BOTTOM = plugin list ──
        self.vpane = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.vpane.set_position(self.options_dict["pane_setting"])
        self.window.vbox.pack_start(self.vpane, True, True, 0)

        # ── Top pane: horizontal split (info text | thumbnail) ─────────────
        self._info_pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        # Left column: MarkdownUtils-rendered plugin information / README
        self._md_pane = _MdInfoPane(uistate)
        self._info_pane.pack1(self._md_pane.widget, resize=True, shrink=False)

        # Right column: fixed-structure vbox so action buttons are always
        # visible at the bottom regardless of how the vertical pane is sized.
        #
        #   _thumb_right_vbox  (Gtk.Box VERTICAL, packed into _info_pane)
        #     └─ _thumb_sw   (ScrolledWindow, expand=True)  ← icon / screenshot
        #     └─ _action_sep (Separator, shown in details mode only)
        #     └─ _action_btn_box (ButtonBox, shown in details mode only)
        #
        # _thumb_box lives inside _thumb_sw so only the image scrolls; the
        # buttons sit outside the ScrolledWindow and are never clipped.
        self._thumb_right_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0
        )
        self._thumb_right_vbox.set_size_request(150, -1)

        self._thumb_sw = Gtk.ScrolledWindow()
        self._thumb_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._thumb_sw.set_vexpand(True)
        self._thumb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._thumb_box.set_border_width(8)
        self._thumb_box.set_valign(Gtk.Align.START)
        self._thumb_box.set_halign(Gtk.Align.CENTER)
        self._thumb_sw.add(self._thumb_box)
        self._thumb_right_vbox.pack_start(self._thumb_sw, True, True, 0)

        self._info_pane.pack2(self._thumb_right_vbox, resize=False, shrink=False)

        # Anchor the horizontal split at 70/30 once allocated
        def _set_split(widget, allocation, handler_ref):
            """One-shot callback to set the initial horizontal split position.

            :param widget:      The :class:`Gtk.Paned` being allocated.
            :param allocation:  The :class:`Gdk.Rectangle` allocation.
            :param handler_ref: List holding the signal handler id so it can
                                be disconnected after the first call.
            """
            widget.set_position(int(allocation.width * 0.70))
            widget.disconnect(handler_ref[0])

        _hid_ref: list[int] = [0]
        _hid_ref[0] = self._info_pane.connect("size-allocate", _set_split, _hid_ref)

        upper_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        upper_vbox.pack_start(self._info_pane, True, True, 0)
        self.vpane.pack1(upper_vbox, resize=True, shrink=False)

        # ── Bottom pane: plugin list with buttons and filter checkboxes ────
        lower_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sep = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        lower_vbox.pack_start(sep, False, False, 3)
        _labeltitle, widget = self.registered_plugins_panel(None)
        lower_vbox.pack_start(widget, True, True, 0)
        self.vpane.pack2(lower_vbox, resize=True, shrink=False)

        # Separator + action buttons anchored at the bottom of the right column,
        # outside the ScrolledWindow so they are never clipped by pane resizing.
        # pack_end stacks in reverse: last packed = closest to bottom edge.
        # We want:  [separator]  then  [buttons]  at the very bottom,
        # so pack buttons last (they land at the bottom), sep before them.
        self._action_btn_box = Gtk.ButtonBox()
        self._action_btn_box.set_layout(Gtk.ButtonBoxStyle.SPREAD)
        self._action_btn_box.set_margin_top(4)
        self._action_btn_box.set_margin_bottom(6)
        self._action_btn_box.set_margin_start(4)
        self._action_btn_box.set_margin_end(4)

        self._hide_btn = Gtk.Button(label=_("Hide"))
        self._action_btn_box.add(self._hide_btn)
        self._hide_btn.connect("clicked", self.__hide, self._list_reg)

        self._install_btn = Gtk.Button(label=_("Install"))
        self._action_btn_box.add(self._install_btn)
        self._install_btn.connect("clicked", self.__install, self._list_reg)

        self._load_btn = Gtk.Button(label=_("Load"))
        self._load_btn.connect("clicked", self.__load, self._list_reg)
        if __debug__:
            self._action_btn_box.add(self._load_btn)

        self._action_sep = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        self._action_sep.set_margin_top(4)

        # pack_end: last packed = closest to bottom edge.
        # Desired visual order from top to bottom: [separator] [buttons]
        # So pack separator first (it ends up above), buttons last (at bottom).
        self._thumb_right_vbox.pack_end(self._action_sep, False, False, 0)
        self._thumb_right_vbox.pack_end(self._action_btn_box, False, False, 0)

        # Pre-call show_all on the button box so individual buttons are realised,
        # then hide both widgets until details mode activates them.
        self._action_btn_box.show_all()
        self._action_btn_box.set_no_show_all(True)
        self._action_sep.set_no_show_all(True)
        self._action_btn_box.hide()
        self._action_sep.hide()

        self.restart_needed = False
        self.window.connect("response", self.done)
        self.show()

        # Populate the list; _cursor_changed will render details for row 0
        # because _readme_showing starts False (details mode is the default).
        self.__populate_reg_list()

    def _show_readme(self) -> None:
        """Render ``README(PluginMgrPlus).md`` and show the screenshot.

        Loads ``media/PluginMgr_capture.png`` (relative to this file's
        directory) into the right thumbnail column.  Falls back to the icon
        placeholder when the file is not found.  Sets :attr:`_readme_showing`
        to ``True`` and relabels the toggle button to *Details*.
        """
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        readme_path = os.path.join(plugin_dir, "README(PluginMgrPlus).md")
        if not os.path.isfile(readme_path):
            readme_path = os.path.join(plugin_dir, "README.md")
        if os.path.isfile(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as fh:
                    md_text = fh.read()
                self._md_pane.render(md_text, base_dir=plugin_dir)
            except Exception:
                LOG.debug("Could not load README for PluginMgrPlus", exc_info=True)

        self._show_screenshot(plugin_dir)
        self._readme_showing = True
        _set_btn_icon_label(
            self._help_btn,
            "view-list-rtl-symbolic",
            _("_Details"),
            use_mnemonic=True,
        )
        self._help_btn.set_tooltip_text(
            _("Return to the selected plugin's registration details")
        )

    def _show_screenshot(self, plugin_dir: str) -> None:
        """Load ``media/PluginMgr_capture.png`` into the right thumbnail column.

        The action buttons (Hide / Install / Load) are hidden in this mode
        since they belong to plugin details, not the README overview.

        Falls back to the icon placeholder when the image file is absent or
        cannot be decoded.

        :param plugin_dir: Absolute path to the directory containing this file.
        """
        for child in self._thumb_box.get_children():
            self._thumb_box.remove(child)

        capture_path = os.path.join(plugin_dir, "media", "PluginMgr_capture.png")
        pb = None
        if os.path.isfile(capture_path):
            try:
                # Scale to fit the column while preserving aspect ratio
                pb_full = GdkPixbuf.Pixbuf.new_from_file(capture_path)
                target_w = 260
                w = pb_full.get_width()
                h = pb_full.get_height()
                if w > 0:
                    target_h = int(h * target_w / w)
                    pb = pb_full.scale_simple(
                        target_w, target_h, GdkPixbuf.InterpType.BILINEAR
                    )
            except Exception:
                LOG.debug("Could not load PluginMgr_capture.png", exc_info=True)

        if pb:
            img = Gtk.Image.new_from_pixbuf(pb)
            img.set_margin_top(8)
            self._thumb_box.pack_start(img, False, False, 0)
            lbl = Gtk.Label()
            lbl.set_markup(
                "<small><span foreground='#888888'>{}</span></small>".format(
                    _("Plugin Manager")
                )
            )
            lbl.set_margin_top(4)
            self._thumb_box.pack_start(lbl, False, False, 0)
        else:
            # Screenshot not available — show a plain placeholder icon only,
            # without action buttons (still in README mode).
            theme = Gtk.IconTheme.get_default()
            try:
                pb2 = theme.load_icon("gramps-addon", 128, 0)
            except Exception:
                pb2 = None
            if pb2:
                img2 = Gtk.Image.new_from_pixbuf(pb2)
            else:
                img2 = Gtk.Image.new_from_icon_name(
                    "image-missing", Gtk.IconSize.DIALOG
                )
            img2.set_margin_top(8)
            self._thumb_box.pack_start(img2, False, False, 0)

        # Action buttons are intentionally hidden in README mode.
        self._action_sep.hide()
        self._action_btn_box.hide()
        self._thumb_box.show_all()

    def _set_thumb_placeholder(self, plugin_index: int) -> None:
        """Populate the right thumbnail column with a placeholder icon.

        Used in **details mode** only.  Cycles between ``gramps-addon`` and
        ``gramps-viewmedia`` (alternating by row index) as a placeholder until
        per-plugin screenshot paths are defined in the registration data.

        :param plugin_index: Integer row index used to select the placeholder.
        """
        for child in self._thumb_box.get_children():
            self._thumb_box.remove(child)

        icon_name_raw = _PREVIEW_ICONS[plugin_index % len(_PREVIEW_ICONS)]
        # Try both raw name and common gramps- prefixed variants
        pb = None
        if _MARKDOWN_AVAILABLE:
            pb = resolve_icon_pixbuf(icon_name_raw, 128)
        if pb is None:
            theme = Gtk.IconTheme.get_default()
            flags = (
                Gtk.IconLookupFlags.GENERIC_FALLBACK | Gtk.IconLookupFlags.USE_BUILTIN
            )
            for candidate in (
                icon_name_raw,
                "gramps-" + icon_name_raw,
                "gramps-addon",
                "application-x-addon",
                "package",
            ):
                try:
                    pb = theme.load_icon(candidate, 128, flags)
                    if pb:
                        break
                except Exception:
                    continue

        if pb:
            img = Gtk.Image.new_from_pixbuf(pb)
        else:
            img = Gtk.Image.new_from_icon_name("image-missing", Gtk.IconSize.DIALOG)
        img.set_margin_top(8)
        self._thumb_box.pack_start(img, False, False, 0)

        lbl = Gtk.Label()
        lbl.set_markup(
            "<small><span foreground='#888888'>{}</span></small>".format(_("(preview)"))
        )
        lbl.set_margin_top(4)
        self._thumb_box.pack_start(lbl, False, False, 0)

        self._thumb_box.show_all()

        # Show the action buttons pinned at the bottom of the right column
        self._action_sep.show()
        self._action_btn_box.show()

    def done(self, dialog, response_id):
        """Handle dialog response buttons.

        ``Gtk.ResponseType.HELP`` is repurposed as the Help ↔ Details toggle:

        * When **README** is showing → switch to plugin details (if a plugin
          is selected) and relabel the button *Help*.
        * When **plugin details** are showing → switch to README + screenshot
          and relabel the button *Details*.

        :param dialog:      The dialog emitting the response.
        :param response_id: The :class:`Gtk.ResponseType` value.
        """
        if response_id == RELOAD_RES:
            self.__reload(dialog)
            return
        elif response_id == Gtk.ResponseType.HELP:
            self._cb_toggle_help_details()
            return
        elif response_id == IGNORE_RES:
            return
        else:
            if self.restart_needed:
                OkDialog(
                    _("Restart..."),
                    _(
                        "Please Restart Gramps so that your addon changes "
                        "can be safely completed."
                    ),
                    parent=self.window,
                )
            self.options_dict["pane_setting"] = self.vpane.get_position()
            self.options.handler.save_options()
            self.close(dialog)

    def _cb_toggle_help_details(self) -> None:
        """Toggle the info panel between README mode and plugin-details mode.

        * README mode → switch to details for the currently selected plugin
          (or do nothing if no plugin is selected, leaving README visible).
        * Details mode → switch to README + screenshot.
        """
        if self._readme_showing:
            # Try to show details for the currently selected plugin
            if self._current_pid is not None:
                md_text = self.__info_as_markdown(self._current_pid)
                self._md_pane.render(md_text)
                # Restore the placeholder icon for the current row
                model, node = self._selection_reg.get_selected()
                row_index = 0
                if node:
                    try:
                        row_index = int(str(model.get_path(node)))
                    except Exception:
                        pass
                self._set_thumb_placeholder(row_index)
                self._readme_showing = False
                _set_btn_icon_label(
                    self._help_btn,
                    "help-browser",
                    _("_Help"),
                    use_mnemonic=True,
                )
                self._help_btn.set_tooltip_text(
                    _("Show the Plugin Manager README and screenshot")
                )
            # If no plugin is selected, stay in README mode — nothing to show
        else:
            self._show_readme()

    def __reload(self, _obj):
        """Callback from the Reload button (debug mode only).

        :param _obj: Unused widget reference.
        """
        self._pmgr.reload_plugins()
        self.__rebuild_reg_list("0")

    def __show_hidden_chk(self, obj):
        """Callback from Hide hidden checkbox.

        :param obj: The :class:`Gtk.CheckButton` that was clicked.
        """
        self._show_hidden = obj.get_active()
        self.options_dict["show_hidden"] = self._show_hidden
        self.__rebuild_reg_list("0", rescan=False)

    def __show_builtins_chk(self, obj):
        """Callback from Hide builtins checkbox.

        :param obj: The :class:`Gtk.CheckButton` that was clicked.
        """
        self._show_builtins = obj.get_active()
        self.options_dict["show_builtins"] = self._show_builtins
        self.__rebuild_reg_list("0", rescan=False)

    def __show_available_chk(self, obj):
        """Callback from Show Uninstalled checkbox.

        :param obj: The :class:`Gtk.CheckButton` that was clicked.
        """
        self._show_available = obj.get_active()
        self.options_dict["show_available"] = self._show_available
        self.__rebuild_reg_list("0", rescan=False)

    def __show_addons_chk(self, obj):
        """Callback from Show Addons checkbox.

        :param obj: The :class:`Gtk.CheckButton` that was clicked.
        """
        self._show_addons = obj.get_active()
        self.options_dict["show_addons"] = self._show_addons
        self.__rebuild_reg_list("0", rescan=False)

    def __hide(self, _obj, list_obj):
        """Callback from the Hide button.

        :param _obj:     Unused widget reference.
        :param list_obj: The plugin :class:`Gtk.TreeView`.
        """
        selection = list_obj.get_selection()
        model, node = selection.get_selected()
        if not node:
            return
        path = model.get_path(node)
        pid = model.get_value(node, R_ID)
        if pid in self.hidden:
            self.hidden.remove(pid)
            self._pmgr.unhide_plugin(pid)
        else:
            self.hidden.add(pid)
            self._pmgr.hide_plugin(pid)
        self.__rebuild_reg_list(path, rescan=False)

    def __load(self, _obj, list_obj):
        """Callback from the Load button.

        :param _obj:     Unused widget reference.
        :param list_obj: The plugin :class:`Gtk.TreeView`.
        """
        selection = list_obj.get_selection()
        model, node = selection.get_selected()
        if not node:
            return
        idv = model.get_value(node, R_ID)
        pdata = self._preg.get_plugin(idv)
        if self._pmgr.load_plugin(pdata):
            self._load_btn.set_sensitive(False)
        else:
            path = model.get_path(node)
            self.__rebuild_reg_list(path, rescan=False)

    def __install(self, _obj, _list_obj):
        """Callback from the Install/Uninstall button.

        :param _obj:      Unused widget reference.
        :param _list_obj: Unused widget reference.
        """
        model, node = self._selection_reg.get_selected()
        if not node:
            return
        path = model.get_path(node)
        pid = model.get_value(node, R_ID)
        status = model.get_value(node, R_STAT)
        if (status & INSTALLED) and not (status & UPDATE):
            self.__uninstall(pid, path)
            return
        for addon in self.addons:
            if addon["i"] == pid:
                name = addon["n"]
                fname = addon["z"]
        url = "%s/download/%s" % (config.get("behavior.addons-url"), fname)
        load_ok = load_addon_file(url, callback=LOG.debug)
        if not load_ok:
            OkDialog(
                _("Installation Errors"),
                _("The following addons had errors: ") + name,
                parent=self.window,
            )
            return
        self.__rebuild_reg_list(path)
        pdata = self._pmgr.get_plugin(pid)
        if (
            pdata
            and (status & UPDATE)
            and (pdata.ptype == VIEW or pdata.ptype == GRAMPLET)
        ):
            self.restart_needed = True

    def __uninstall(self, pid, path):
        """Uninstall the plugin at *pid*.

        :param pid:  Plugin ID string.
        :param path: The tree path to reselect after removal.
        """
        pdata = self._pmgr.get_plugin(pid)
        try:
            if os.path.islink(pdata.fpath):
                os.unlink(pdata.fpath)
            elif os.stat(pdata.fpath).st_ino != os.lstat(pdata.fpath).st_ino:
                os.rmdir(pdata.fpath)
            else:
                shutil.rmtree(pdata.fpath)
        except Exception:  # pylint: disable=broad-except
            OkDialog(
                _("Error"),
                _("Error removing the '%s' directory, The uninstall may " "have failed")
                % pdata.fpath,
                parent=self.window,
            )
        self.__rebuild_reg_list(path)
        self.restart_needed = True

    def registered_plugins_panel(self, _configdialog):
        """Build and return the upper plugin-list panel.

        :param _configdialog: Unused (required by Gramps panel protocol).
        :returns: Tuple of ``(label_string, Gtk.Box)``.
        """
        vbox_reg = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        scrolled_window_reg = Gtk.ScrolledWindow()
        self._list_reg = Gtk.TreeView()
        self._list_reg.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

        self._model_reg = Gtk.ListStore(
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            int,
        )
        self._selection_reg = self._list_reg.get_selection()

        self._tree_filter = self._model_reg.filter_new()
        self._tree_filter.set_visible_func(self._apply_filter)
        self._list_reg.set_model(Gtk.TreeModelSort(model=self._tree_filter))
        self._list_reg.connect("button-press-event", self.button_press_reg)
        self._cursor_hndlr = self._selection_reg.connect(
            "changed", self._cursor_changed
        )

        col0_reg = Gtk.TreeViewColumn(
            title=_("Type"),
            cell_renderer=Gtk.CellRendererText(),
            text=R_TYPE,
        )
        col0_reg.set_sort_column_id(R_TYPE)
        col0_reg.set_resizable(True)
        self._list_reg.append_column(col0_reg)

        col1 = Gtk.TreeViewColumn(
            cell_renderer=Gtk.CellRendererText(wrap_mode=2, wrap_width=75),
            markup=R_STAT_S,
        )
        label = Gtk.Label(label=_("Status"))
        label.show()
        label.set_tooltip_markup(
            _(
                "'•' items are supplied by 3rd party authors,\n"
                "<s>strikeout</s> items are hidden"
            )
        )
        col1.set_widget(label)
        col1.set_resizable(True)
        col1.set_sort_column_id(R_STAT_S)
        self._list_reg.append_column(col1)

        col2_reg = Gtk.TreeViewColumn(
            title=_("Name"),
            cell_renderer=Gtk.CellRendererText(wrap_mode=2, wrap_width=225),
            markup=R_NAME,
        )
        col2_reg.set_sort_column_id(R_NAME)
        col2_reg.set_resizable(True)
        self._list_reg.append_column(col2_reg)

        col = Gtk.TreeViewColumn(
            title=_("Description"),
            cell_renderer=Gtk.CellRendererText(wrap_mode=2, wrap_width=400),
            markup=R_DESC,
        )
        col.set_sort_column_id(R_DESC)
        col.set_resizable(True)
        self._list_reg.append_column(col)
        self._list_reg.set_search_column(2)

        scrolled_window_reg.add(self._list_reg)
        vbox_reg.pack_start(scrolled_window_reg, True, True, 0)

        # Hide / Install / Load action buttons are built in __init__ and
        # live in the right thumbnail column (_thumb_box) so they are
        # visible only when plugin details are shown.  Nothing packed here.

        # ── checkbox row ──────────────────────────────────────────────────
        hbutbox2 = Gtk.ButtonBox()
        hbutbox2.set_layout(Gtk.ButtonBoxStyle.SPREAD)

        _show_hidden_chk = Gtk.CheckButton.new_with_label(_("Show hidden items"))
        hbutbox2.add(_show_hidden_chk)
        self._show_hidden = self.options_dict["show_hidden"]
        _show_hidden_chk.set_active(self._show_hidden)
        _show_hidden_chk.connect("clicked", self.__show_hidden_chk)

        _show_builtin_chk = Gtk.CheckButton.new_with_label(_("Show Built-in items"))
        hbutbox2.add(_show_builtin_chk)
        self._show_builtins = self.options_dict["show_builtins"]
        _show_builtin_chk.set_active(self._show_builtins)
        _show_builtin_chk.connect("clicked", self.__show_builtins_chk)

        _show_available_chk = Gtk.CheckButton.new_with_label(_("Show Uninstalled"))
        _show_available_chk.set_tooltip_text(
            _("Show plugins that are available online but not yet installed")
        )
        hbutbox2.add(_show_available_chk)
        self._show_available = self.options_dict["show_available"]
        _show_available_chk.set_active(self._show_available)
        _show_available_chk.connect("clicked", self.__show_available_chk)

        _show_addons_chk = Gtk.CheckButton.new_with_label(_("Show \u2022Addons"))
        _show_addons_chk.set_tooltip_text(
            _("Show \u2022 third-party addon plugins (installed or available)")
        )
        hbutbox2.add(_show_addons_chk)
        self._show_addons = self.options_dict["show_addons"]
        _show_addons_chk.set_active(self._show_addons)
        _show_addons_chk.connect("clicked", self.__show_addons_chk)

        vbox_reg.pack_start(hbutbox2, False, False, 0)
        return _("Plugins"), vbox_reg

    def button_press_reg(self, obj, event):
        """Handle double-click on a plugin row.

        :param obj:   The :class:`Gtk.TreeView`.
        :param event: The :class:`Gdk.EventButton`.
        """
        # pylint: disable=protected-access
        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            self._cursor_changed(obj)

    def filter_str_changed(self, _widget):
        """Called when the search filter string is changed.

        :param _widget: Unused widget reference.
        """
        self.__rebuild_reg_list(rescan=False)

    def _update_count_label(self) -> None:
        """Refresh the 'Showing x of y plugins' count label."""
        total = len(self._model_reg)
        visible = len(self._tree_filter)
        self._count_label.set_markup(
            "<small>Showing {} of {} plugins</small>".format(visible, total)
        )

    def _apply_filter(self, model, tr_iter, _data) -> bool:
        """Row visibility predicate for ``self._tree_filter``.

        Supports exact-phrase mode (query wrapped in ``"…"``) and all-words
        mode (bare words, any order, case-insensitive).

        :param model:   The :class:`Gtk.TreeModel`.
        :param tr_iter: The current :class:`Gtk.TreeIter`.
        :param _data:   Unused user data.
        :returns: ``True`` if the row should be visible.
        """
        raw = self.filter_entry.get_text()
        if not raw:
            return True
        stripped = raw.strip()
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 2:
            exact = stripped[1:-1].lower()
            if not exact:
                return True
            return exact in self._row_search_text(model, tr_iter).lower()
        p_txt = self._row_search_text(model, tr_iter).lower()
        for word in raw.lower().split():
            if word not in p_txt:
                return False
        return True

    def _row_search_text(self, model, tr_iter) -> str:
        """Build the full searchable text string for one row.

        Includes all model columns plus all diagnostic ``pdata`` attributes.

        :param model:   The :class:`Gtk.TreeModel`.
        :param tr_iter: The current :class:`Gtk.TreeIter`.
        :returns: Combined search string for this row.
        """
        pid = model.get_value(tr_iter, R_ID)
        parts = []
        for col in (R_TYPE, R_STAT_S, R_NAME, R_DESC, R_ID):
            parts.append(model[tr_iter][col])
        pdata = self._preg.get_plugin(pid)
        if pdata:
            _str = str
            for val in (
                pdata.fname,
                pdata.fpath,
                pdata.version,
                getattr(pdata, "gramps_target_version", ""),
                " ".join(pdata.authors or []),
                " ".join(pdata.authors_email or []),
                getattr(pdata, "help_url", "") or "",
                _str(getattr(pdata, "load_on_reg", "") or ""),
                _str(getattr(pdata, "require_active", "") or ""),
                _str(getattr(pdata, "viewclass", "") or ""),
                _str(getattr(pdata, "optionclass", "") or ""),
                _str(getattr(pdata, "category", "") or ""),
                " ".join(_str(m) for m in (getattr(pdata, "report_modes", None) or [])),
                " ".join(_str(m) for m in (getattr(pdata, "tool_modes", None) or [])),
                " ".join(getattr(pdata, "requires_mod", None) or []),
                " ".join(getattr(pdata, "requires_exe", None) or []),
            ):
                if val:
                    parts.append(val)
        return " ".join(parts)

    def __rebuild_reg_list(self, path=None, rescan=True):
        """Rebuild the plugin list model, optionally re-scanning the filesystem.

        :param path:   Tree path to reselect after the rebuild, or ``None``.
        :param rescan: When ``True`` call ``do_reg_plugins`` before rebuild.
        """
        self._selection_reg.handler_block(self._cursor_hndlr)
        self._model_reg.clear()
        if rescan:
            CLIManager.do_reg_plugins(self, self.dbstate, self.uistate, rescan=True)
        self.__populate_reg_list()
        self._tree_filter.refilter()
        self._update_count_label()
        self._selection_reg.handler_unblock(self._cursor_hndlr)
        if not path or int(str(path)) >= len(self._model_reg):
            path = "0"
        self._selection_reg.select_path(path)
        if len(self._tree_filter):
            self._list_reg.scroll_to_cell(path, None, True, 0.5, 0)
        self._cursor_changed(None)

    def _cursor_changed(self, _obj):
        """Update buttons and info pane when the selected row changes.

        Records the selected plugin ID in :attr:`_current_pid`.  If the panel
        is currently in **details mode** (not showing README) the details are
        refreshed immediately.  If in **README mode** the README stays visible
        — the user must press *Details* to switch, or select a different row
        in details mode.

        :param _obj: Unused widget reference (selection or None).
        """
        model, node = self._selection_reg.get_selected()
        if not node:
            self._current_pid = None
            self._show_readme()
            return

        status = model.get_value(node, R_STAT)
        pid = model.get_value(node, R_ID)
        self._current_pid = pid

        # ── Button sensitivity / labels ───────────────────────────────────
        if (status & (INSTALLED | BUILTIN)) and (
            VIEW == self._pmgr.get_plugin(pid).ptype
        ):
            self._hide_btn.set_sensitive(False)
        else:
            self._hide_btn.set_sensitive(True)
        if status & HIDDEN:
            self._hide_btn.set_label(_("Unhide"))
        else:
            self._hide_btn.set_label(_("Hide"))
        show_load = False
        if status & (INSTALLED | BUILTIN):
            show_load = True
            success_list = self._pmgr.get_success_list()
            for i in success_list:
                if pid == i[2].id:
                    show_load = False
                    break
        if __debug__:
            self._load_btn.set_sensitive(show_load)
        if status & (AVAILABLE | UPDATE):
            self._install_btn.set_label(_("Install"))
            self._install_btn.set_sensitive(True)
        elif status & INSTALLED:
            self._install_btn.set_label(_("Uninstall"))
            self._install_btn.set_sensitive(True)
        else:
            self._install_btn.set_sensitive(False)

        # ── Info panel update — only when in details mode ─────────────────
        if not self._readme_showing:
            md_text = self.__info_as_markdown(pid)
            self._md_pane.render(md_text)
            row_index = 0
            try:
                row_index = int(str(model.get_path(node)))
            except Exception:
                pass
            self._set_thumb_placeholder(row_index)

    # ── Markdown info builder ──────────────────────────────────────────────

    def __info_as_markdown(self, pid: str) -> str:
        """Build a Markdown string describing the plugin identified by *pid*.

        Layout rules (driven by MarkdownUtils renderer constraints):

        - **No GFM tables** — column widths render too narrow and row padding
          is excessive.  Use ``**Label:** value`` inline paragraphs instead.
        - **No HTML tags** — ``<small>``, ``<b>`` etc. pass through as literal
          text.  Use Markdown emphasis and heading levels instead.
        - **No ``---`` horizontal rules** — the fixed 48-char ``─`` string
          wraps in narrow panes.  Use a heading to mark section boundaries.
        - **Bullet lists** used sparingly (requirements, diagnostics) where
          the list_bullet prefix is an acceptable cost.
        - **Boolean flags** shown as an inline icon + bold label on their own
          line; only emitted when the flag is truthy so falsy flags disappear.
          ``![](gramps:icon:gtk-apply:16)`` used for true booleans.
        - **Load/fail status**: ``![](gramps:icon:gtk-apply:22)`` / ``gtk-cancel``
          icons are sharper than emoji for these prominent status lines.
        - **Author/maintainer emails**: shown as
          ``Name [addr](mailto:addr?subject=…)`` so the address is visible
          as plain text *and* clickable.
        - **Report/tool modes**: treated as boolean flags (``[1]`` → shown,
          absent → omitted).

        :param pid: Plugin ID string.
        :returns:   Markdown-formatted string ready for :meth:`_MdInfoPane.render`.
        """
        pdata = self._preg.get_plugin(pid)
        lines: list[str] = []

        # ── Collect raw data ───────────────────────────────────────────────
        if pdata:
            name = pdata.name
            typestr = PTYPE_STR[pdata.ptype]
            desc = pdata.description
            vers = pdata.version
            authors = list(pdata.authors or [])
            emails = list(pdata.authors_email or [])
            fname = pdata.fname or ""
            fpath = pdata.fpath or ""
            help_url = pdata.help_url if pdata.help_url else ""
            aud = AUDIENCETEXT[pdata.audience]
            status_txt = STATUSTEXT[pdata.status]

            reqs: list[tuple[str, str]] = []
            dep_re = pdata.requires_exe
            if dep_re:
                reqs.append((_("Executables"), " ".join(dep_re)))
            dep_rm = pdata.requires_mod
            if dep_rm:
                reqs.append((_("Python modules"), " ".join(dep_rm)))
            dep_rg = pdata.requires_gi
            if dep_rg:
                txt = dep_rg[0][0] + " " + dep_rg[0][1]
                for i in range(1, len(dep_rg)):
                    txt += ", " + dep_rg[i][0] + " " + dep_rg[i][1]
                reqs.append((_("GObject introspection modules"), txt))

        else:
            # From online addons list only
            for addon in self.addons:
                if addon["i"] == pid:
                    name = addon["n"]
                    typestr = PTYPE_STR[addon["t"]]
                    desc = addon["d"]
                    vers = addon["v"]
                    authors = []
                    emails = []
                    fname = addon["z"]
                    fpath = addon.get("_u", "")
                    help_url = addon.get("h", "")
                    aud = AUDIENCETEXT[addon["a"]]
                    status_txt = STATUSTEXT[addon["s"]]
                    reqs = []
                    info = Requirements().info(addon)
                    for i in range(0, len(info), 2):
                        req_label = info[i]
                        req_lst = info[i + 1]
                        txt = " ".join(req_lst[0])
                        for j in range(1, len(req_lst)):
                            txt += ", " + " ".join(req_lst[j])
                        reqs.append((req_label, txt))
                    break
            else:
                lines.append(_("*(Plugin data not found)*"))
                return "\n".join(lines)

        # ── Resolve wiki / help target ─────────────────────────────────────
        self.help = help_url
        self.helpname = ""
        if not self.help and pdata:
            if fpath and "gramplet" in fpath:
                self.help = URL_MANUAL_PAGE + "_-_Gramplets"
                self.helpname = name
            elif fpath and "tools" in fpath:
                self.help = URL_MANUAL_PAGE + "_-_Tools"
                self.helpname = name
            elif fpath and "report" in fpath:
                self.help = URL_MANUAL_PAGE + "_-_Reports"
                self.helpname = name

        if self.help:
            wiki_target = self.help
            if not wiki_target.startswith(("http://", "https://")):
                wiki_target = (
                    "https://gramps-project.org/wiki/index.php/"
                    + wiki_target.replace(" ", "_")
                )
            if self.helpname:
                wiki_target += "#" + self.helpname.replace(" ", "_")
        else:
            wiki_target = ""

        # ── Helper: build a mailto URI with a pre-filled subject ──────────
        def _mailto(addr: str) -> str:
            """Return a ``mailto:`` URI with a subject naming the plugin.

            :param addr: Raw e-mail address string.
            :returns:    Percent-encoded ``mailto:`` URI string.
            """
            subject = "about {} {} for Gramps".format(pid, vers)
            # Minimal percent-encoding for spaces in subject
            subject_enc = subject.replace(" ", "%20")
            return "mailto:{}?subject={}".format(addr, subject_enc)

        # ── Helper: inline gtk-apply icon (true boolean indicator) ────────
        _ICON_TRUE = "![](gramps:icon:gtk-apply:16)"
        _ICON_OK = "![](gramps:icon:gtk-apply:22)"
        _ICON_FAIL = "![](gramps:icon:gtk-cancel:22)"

        # ── Header ────────────────────────────────────────────────────────
        # h3 is large enough to stand out without being oversized
        lines.append("### {} [{}]".format(name, typestr))
        lines.append("")
        # Description immediately below the name, before the identity fields
        lines.append("*{}*".format(desc))
        lines.append("")

        # ── Core identity fields — one bold-label paragraph per field ─────
        lines.append(
            "**{}:** `{}`   **{}:** {}".format(_("ID"), pid, _("Version"), vers)
        )
        lines.append(
            "**{}:** {}   **{}:** {}".format(
                _("Audience"), aud, _("Status"), status_txt
            )
        )
        lines.append("")

        # ── File links ────────────────────────────────────────────────────
        if fname and fpath:
            full_path = os.path.join(fpath, fname)
            lines.append("**{}:** [{}](file://{})".format(_("File"), fname, full_path))
            lines.append("**{}:** [{}](file://{})".format(_("Location"), fpath, fpath))
        elif fname:
            lines.append("**{}:** `{}`".format(_("File"), fname))
        elif fpath:
            lines.append("**{}:** [{}](file://{})".format(_("Location"), fpath, fpath))

        # ── Wiki / help link ──────────────────────────────────────────────
        # Always show the raw help_url string (as declared in the .gpr.py)
        # as the visible label so developers can see what was registered;
        # the href is the fully-resolved https:// target.
        if wiki_target:
            lines.append(
                "**{}:** [{}]({})".format(_("Help"), help_url or self.help, wiki_target)
            )

        lines.append("")

        # ── Authors — Name <addr> pattern, address visible + clickable ────
        def _person_links(names: list[str], addrs: list[str], label: str) -> str:
            """Format a list of people with visible clickable e-mail addresses.

            Produces:  ``**Label:** Name1 [addr1](mailto:…), Name2 …``

            When an address is present the address text itself is the link
            label so it is visible as plain text *and* clickable, matching
            the HTML ``Name <addr>`` convention.

            :param names:  List of display names.
            :param addrs:  Parallel list of e-mail address strings.
            :param label:  Translated field label (e.g. ``'Authors'``).
            :returns:      Formatted Markdown line string.
            """
            parts: list[str] = []
            for idx, person_name in enumerate(names):
                addr = addrs[idx] if idx < len(addrs) else ""
                if addr:
                    parts.append("{} [{}]({})".format(person_name, addr, _mailto(addr)))
                else:
                    parts.append(person_name)
            return "**{}:** {}".format(label, ", ".join(parts))

        if authors:
            lines.append(_person_links(authors, emails, _("Authors")))

        if pdata:
            maintainers = getattr(pdata, "maintainers", None) or []
            maint_emails = getattr(pdata, "maintainers_email", None) or []
            if maintainers:
                lines.append(_person_links(maintainers, maint_emails, _("Maintainers")))

        lines.append("")

        # ── Requirements ──────────────────────────────────────────────────
        if reqs:
            lines.append("**{}:** ".format(_("Requires")))
            for req_label, req_txt in reqs:
                lines.append("- *{}:* {}".format(req_label, req_txt))
            lines.append("")

        # ── Extended / optional fields (pdata only) ────────────────────────
        # Boolean-like flags: only shown when truthy; rendered as icon + label
        # on a single compact line.  Non-boolean scalars use bold-label style.
        if pdata:
            gtv = getattr(pdata, "gramps_target_version", None)
            if gtv:
                lines.append("**{}:** {}".format(_("Target Gramps"), str(gtv)))
            cat = getattr(pdata, "category", None)
            if cat:
                lines.append("**{}:** {}".format(_("Category"), str(cat)))
            vc = getattr(pdata, "viewclass", None)
            if vc:
                lines.append("**{}:** `{}`".format(_("View class"), str(vc)))
            oc = getattr(pdata, "optionclass", None)
            if oc:
                lines.append("**{}:** `{}`".format(_("Option class"), str(oc)))

            # report_modes / tool_modes — list like [1] treated as boolean
            rm = getattr(pdata, "report_modes", None)
            if rm:
                lines.append("{} **{}**".format(_ICON_TRUE, _("Report modes")))
            tm = getattr(pdata, "tool_modes", None)
            if tm:
                lines.append("{} **{}**".format(_ICON_TRUE, _("Tool modes")))

            lor = getattr(pdata, "load_on_reg", None)
            if lor:
                lines.append("{} **{}**".format(_ICON_TRUE, _("Load on register")))
            ra = getattr(pdata, "require_active", None)
            if ra is not None and ra is not False:
                lines.append("{} **{}**".format(_ICON_TRUE, _("Require active")))

            lines.append("")

        # ── Load / hidden / fail status ───────────────────────────────────
        success_list = self._pmgr.get_success_list()
        fail_list = self._pmgr.get_fail_list()

        if pdata:
            for entry in success_list:
                if pdata.id == entry[2].id:
                    lines.append("{} **{}**".format(_ICON_OK, _("Loaded")))
                    break
        if pid in self.hidden:
            lines.append("{} **{}**".format(_ICON_FAIL, _("Hidden")))
        for entry in fail_list:
            if pdata == entry[2]:
                tb = "".join(
                    traceback.format_exception(entry[1][0], entry[1][1], entry[1][2])
                )
                lines.append("{} **{}**".format(_ICON_FAIL, _("Failed")))
                lines.append("")
                lines.append("```")
                lines.append(
                    "{}\n{}\n{}".format(str(entry[1][0]), str(entry[1][1]), tb)
                )
                lines.append("```")
                break

        # ── Diagnostics section ────────────────────────────────────────────
        # Heading used as section separator (avoids the fixed-width hr problem)
        lines.append("")
        lines.append("#### {}".format(_("Diagnostics")))

        if pdata:
            lines.append(
                "**ptype:** `{}` ({})".format(
                    pdata.ptype, PTYPE_STR.get(pdata.ptype, "?")
                )
            )
            in_success = any(pdata.id == e[2].id for e in success_list)
            icon_s = _ICON_OK if in_success else _ICON_FAIL
            lines.append("{} **{}**".format(icon_s, _("In success_list")))
            in_fail = any(pdata == e[2] for e in fail_list)
            if in_fail:
                lines.append("{} **{}**".format(_ICON_FAIL, _("In fail_list")))
            preg_pdata = self._preg.get_plugin(pid)
            icon_pr = _ICON_OK if preg_pdata is not None else _ICON_FAIL
            lines.append("{} **{}**".format(icon_pr, _("In PluginRegister")))
            # fpath / fname omitted — already shown as hotlinks above
        else:
            lines.append(
                "{} **pdata:** {}".format(_ICON_FAIL, _("NOT in PluginRegister"))
            )
            lines.append("**{}:** {}".format(_("Source"), _("Online addons list only")))

        return "\n".join(lines)

    def _web_help(self) -> None:
        """Open the Plugin Manager wiki page in the default browser.

        Not connected to the Help button (which is now the Details toggle),
        but kept for programmatic use and for any context-menu callers.
        """
        display_help(WIKI_PAGE)

    def __populate_reg_list(self):
        """Build the list of plugins in the model."""
        if not self.addons:
            self.addons = get_all_addons()

        addons = []
        updateable = []
        for plugin_dict in self.addons:
            pid = plugin_dict["i"]
            plugin = self._pmgr.get_plugin(pid)
            if plugin:
                LOG.debug(
                    "Comparing %s > %s",
                    version_str_to_tup(plugin_dict["v"], 3),
                    version_str_to_tup(plugin.version, 3),
                )
                if version_str_to_tup(plugin_dict["v"], 3) > version_str_to_tup(
                    plugin.version, 3
                ):
                    LOG.debug("Update for '%s'...", plugin_dict["z"])
                    updateable.append(pid)
                else:
                    LOG.debug("   '%s' is up to date", plugin_dict["n"])
            else:
                LOG.debug("   '%s' is not installed", plugin_dict["n"])
                if not self._show_available:
                    continue
                hidden = pid in self.hidden
                status_str = _("\u2022Available")
                status = AVAILABLE
                if hidden:
                    status_str = "<s>%s</s>" % status_str
                    status |= HIDDEN
                row = [
                    PTYPE_STR[plugin_dict["t"]],
                    status_str,
                    markup_escape_text(plugin_dict["n"]),
                    markup_escape_text(plugin_dict["d"]),
                    plugin_dict["i"],
                    status,
                ]
                addons.append(row)

        fail_list = self._pmgr.get_fail_list()
        for _type, typestr in PTYPE_STR.items():
            for pdata in self._preg.type_plugins(_type):
                if "gramps/plugins" in pdata.fpath.replace("\\", "/"):
                    status_str = _("Built-in")
                    status = BUILTIN
                    if not self._show_builtins:
                        continue
                else:
                    if not self._show_addons:
                        continue
                    status_str = _("\u2022Installed")
                    status = INSTALLED
                for i in fail_list:
                    if pdata == i[2]:
                        status_str += ", " + '<span color="red">%s</span>' % _("Failed")
                        break
                if pdata.id in updateable:
                    status_str += ", " + _("Update Available")
                    status |= UPDATE
                hidden = pdata.id in self.hidden
                if hidden:
                    status_str = "<s>%s</s>" % status_str
                    status |= HIDDEN
                addons.append(
                    [
                        typestr,
                        status_str,
                        markup_escape_text(pdata.name),
                        markup_escape_text(pdata.description),
                        pdata.id,
                        status,
                    ]
                )
        for row in sorted(addons, key=itemgetter(R_TYPE, R_NAME)):
            if self._show_hidden or (row[R_ID] not in self.hidden):
                self._model_reg.append(row)
        self._selection_reg.select_path("0")
        self._update_count_label()

    def build_menu_names(self, _obj):
        """Return menu names for the managed window title.

        :param _obj: Unused.
        :returns: Tuple of ``(title, subtitle)`` strings.
        """
        return (TITLE, " ")


# ---------------------------------------------------------------------------
#
# PluginManagerOptions
#
# ---------------------------------------------------------------------------
class PluginManagerOptions(tool.ToolOptions):
    """Defines options and provides handling interface."""

    def __init__(self, name, person_id=None):
        """Initialise plugin manager options.

        :param name:      Option namespace string.
        :param person_id: Unused; required by base class signature.
        """
        tool.ToolOptions.__init__(self, name, person_id)
        self.options_dict = {
            "show_hidden": True,
            "show_builtins": True,
            "show_available": False,
            "show_addons": True,
            "pane_setting": 400,
        }
        self.options_help = {
            "show_hidden": (
                "=0/1",
                "Show hidden Plugins",
                ["Do not show hidden Plugins", "Show hidden Plugins"],
                True,
            ),
            "show_builtins": (
                "=0/1",
                "Show builtin Plugins",
                ["Do not show builtin Plugins", "Show builtin Plugins"],
                True,
            ),
            "show_available": (
                "=0/1",
                "Show uninstalled/available Plugins",
                [
                    "Do not show uninstalled Plugins",
                    "Show uninstalled Plugins",
                ],
                False,
            ),
            "show_addons": (
                "=0/1",
                "Show third-party addon Plugins",
                ["Do not show addon Plugins", "Show addon Plugins"],
                True,
            ),
            "pane_setting": ("=num", "pane setting", "pane setting in pix"),
        }
