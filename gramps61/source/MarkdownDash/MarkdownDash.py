#!/usr/bin/python
# -*- coding: utf-8 -*-
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

"""
Markdown Dash Gramplet  --  display and file-navigation framework.

This module is a thin shell.  All Markdown parsing, tag styling, icon
resolution, and table rendering are delegated to :mod:`MarkdownUtils`.

Features
--------
- Clickable hyperlinks (opens system browser / file manager).
- Relative ``.md`` links load inside the viewer.
- In-document anchor scroll navigation: links of the form ``[label](#slug)``
  scroll the viewer to the corresponding heading (``## Heading Text``).
- Inline image rendering with pixbuf (falls back to a clickable placeholder).
- Image placeholders are clickable (opens system image viewer).
- ``gramps:icon:<name>[:<size>]``  -- embeds a live GTK/Gramps theme icon inline.
- ``gramps:nav:<Type>:<handle>``   -- switches view & sets active object.
- ``gramps:edit:<Type>:<handle>``  -- opens the object editor.
- Uses only stdlib + GTK -- no WebKit, no extra packages.

Footer bar (left → right)
--------------------------
``[✎ edit]  [Loaded: file from dir …]  [▾ folder files]  [📂 browse]``

- **Edit button** (pencil icon, far left) -- opens the current file in the
  system default editor for ``.md`` files via ``Gio.AppInfo``.  Insensitive
  when no file is loaded.
- **Status label** -- shows the loaded filename / error messages; expands to
  fill available space.
- **Folder menu button** (unlabelled, chevron icon) -- popup menu listing all
  ``.md`` / ``.markdown`` files found in the same directory as the current
  file, sorted alphabetically.  The current file is shown with a bullet prefix
  (``•``) and reloads when clicked.  Insensitive when no file is loaded.
- **Browse button** (folder-open icon, far right) -- opens the GTK file chooser
  to load any Markdown file from anywhere on disk.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "restructure MarkdownDash gramplet — extract markdown handling into a
separate library module imported into the gramplet; gramplet becomes display
and file navigation framework; add in-document anchor scroll navigation for
header links such as [label](#anchor-slug)"
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import logging
import os
import subprocess
import traceback

# ------------------------
# Gramps modules
# ------------------------
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import Gramplet
from gramps.gui.dialog import ErrorDialog

# ------------------------
# Gramps specific
# ------------------------
from MarkdownUtils import (
    NAMESPACE_MAP,
    VIEW_NAMES,
    build_table_widget,
    define_tags,
    parse_markdown,
    resolve_icon_pixbuf,
)

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """XML-escape *text* for use inside Pango markup.

    :param text: Raw text string.
    :returns: XML-safe string.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
#
# MarkdownDash
#
# ---------------------------------------------------------------------------
class MarkdownDash(Gramplet):
    """Dashboard gramplet for viewing Markdown files.

    Acts as a display and file-navigation framework.  Markdown parsing is
    handled entirely by :mod:`MarkdownUtils`; this class is responsible for:

    - Building the GTK widget tree (TextView, footer, file chooser).
    - Populating a :class:`Gtk.TextBuffer` from the parsed
      :class:`~MarkdownUtils.Segment` list.
    - Managing :class:`Gtk.TextMark` anchors for in-document scroll navigation.
    - Dispatching clicks on hyperlinks, image placeholders, anchor links, and
      ``gramps:`` URIs.
    - Connecting to / disconnecting from GTK signals safely across Gramps
      gramplet lifecycle hooks.
    """

    def on_load(self) -> None:
        """Gramps lifecycle hook -- safe no-op."""

    def on_unload(self) -> None:
        """Disconnect all signal handlers before the widget tree is destroyed.

        Gramps tears down the Dashboard notebook during shutdown while GTK's
        event queue may still hold queued motion/button events.  If our
        handlers fire after the notebook tabs are gone, GTK emits spurious
        warnings for every queued event.  Disconnecting here prevents stale
        callbacks from running.
        """
        tv = getattr(self, "textview", None)
        if tv is None:
            return
        for sig_id in getattr(self, "_signal_ids", []):
            try:
                if tv.handler_is_connected(sig_id):
                    tv.disconnect(sig_id)
            except Exception:
                pass
        self._signal_ids = []

        for attr in ("_browse_btn", "_folder_btn", "_edit_btn"):
            btn = getattr(self, attr, None)
            sig_attr = attr + "_sids"
            if btn is not None:
                for sig_id in getattr(self, sig_attr, []):
                    try:
                        if btn.handler_is_connected(sig_id):
                            btn.disconnect(sig_id)
                    except Exception:
                        pass
                setattr(self, sig_attr, [])

        # Keep legacy name in sync so existing callers still work
        self._btn_signal_ids = []

        self._cursor_normal = None
        self._cursor_link = None

    def init(self) -> None:
        """Build the gramplet UI and wire it into the Gramps container.

        Footer pinning strategy
        -----------------------
        Gramps places each gramplet inside a :class:`Gtk.ScrolledWindow`
        (``self.gui.get_container_widget()``).  That ScrolledWindow is itself a
        child of some parent container (Frame / VBox depending on whether the
        gramplet is docked or detached).

        If we simply add our VBox as a child of the ScrolledWindow, the footer
        scrolls away with the document.  The correct approach is:

        1. Find the ScrolledWindow's current parent.
        2. Remove the ScrolledWindow from that parent.
        3. Build our outer VBox: ``[ ScrolledWindow (expand) | footer (fixed) ]``.
        4. Add the outer VBox back into the original parent.
        5. Add our TextView (without its own ScrolledWindow) into the Gramps
           ScrolledWindow where ``gui.textview`` used to be.
        """
        gramps_sw = self.gui.get_container_widget()
        sw_parent = gramps_sw.get_parent()

        outer_vbox, _footer_box = self._build_gui()

        if sw_parent is not None:
            sw_parent.remove(gramps_sw)
            gramps_sw.remove(self.gui.textview)
            gramps_sw.add(self.textview)
            outer_vbox.pack_start(gramps_sw, True, True, 0)
            outer_vbox.reorder_child(gramps_sw, 0)
            sw_parent.add(outer_vbox)
        else:
            gramps_sw.remove(self.gui.textview)
            fallback = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            fallback.pack_start(self.textview, True, True, 0)
            fallback.pack_start(Gtk.Separator(), False, False, 0)
            fallback.pack_start(_footer_box, False, False, 0)
            fallback.show_all()
            gramps_sw.add(fallback)

        self.gui.WIDGET = outer_vbox
        outer_vbox.show_all()

        self.current_file: str | None = None
        self._tags: dict = {}
        self._link_uris: dict = {}
        # anchor_slug -> Gtk.TextMark (populated each time _render() runs)
        self._anchor_marks: dict[str, Gtk.TextMark] = {}

        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        readme = os.path.join(plugin_dir, "README.md")
        if os.path.isfile(readme):
            self._load(readme)

    # ── GUI construction ───────────────────────────────────────────────

    def _build_gui(self) -> tuple[Gtk.Box, Gtk.Box]:
        """Create and return ``(outer_vbox, footer_box)``.

        ``outer_vbox`` is an empty VBox; :meth:`init` packs
        ``[Gramps-ScrolledWindow, Separator, footer_box]`` into it.
        ``footer_box`` is the status-label + browse-button bar.

        :returns: Tuple of ``(outer_vbox, footer_box)``.
        """
        # ── TextView ──────────────────────────────────────────────────────
        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_left_margin(12)
        self.textview.set_right_margin(12)
        self.textview.set_top_margin(8)
        self.textview.set_bottom_margin(4)
        self.textview.set_pixels_above_lines(2)
        self.textview.set_pixels_below_lines(2)
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

        self._signal_ids = [
            self.textview.connect("motion-notify-event", self._on_motion),
            self.textview.connect("button-press-event", self._on_click),
        ]

        # ── Footer ────────────────────────────────────────────────────────
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        footer.set_border_width(2)

        # ── Edit button (far left) ────────────────────────────────────────
        edit_img = Gtk.Image.new_from_icon_name(
            "document-edit", Gtk.IconSize.SMALL_TOOLBAR
        )
        self._edit_btn = Gtk.Button()
        self._edit_btn.set_image(edit_img)
        self._edit_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._edit_btn.set_tooltip_text(_("Edit current file in default editor"))
        self._edit_btn.set_sensitive(False)
        self._edit_btn_sids = [
            self._edit_btn.connect("clicked", self.cb_edit_file),
        ]
        footer.pack_start(self._edit_btn, False, False, 0)

        # ── Status label (expands) ────────────────────────────────────────
        self.info_label = Gtk.Label()
        self.info_label.set_halign(Gtk.Align.START)
        self.info_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.info_label.set_hexpand(True)
        self._set_status(_("Ready"))
        footer.pack_start(self.info_label, True, True, 4)

        # ── Folder files menu button ──────────────────────────────────────
        # An unlabelled MenuButton with a small chevron-down icon.
        # The popup menu is (re)built in _populate_folder_menu() each time
        # _set_loaded() is called so it always reflects the current folder.
        self._folder_menu = Gtk.Menu()
        folder_img = Gtk.Image.new_from_icon_name(
            "pan-down-symbolic", Gtk.IconSize.SMALL_TOOLBAR
        )
        self._folder_btn = Gtk.MenuButton()
        self._folder_btn.set_image(folder_img)
        self._folder_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._folder_btn.set_popup(self._folder_menu)
        self._folder_btn.set_tooltip_text(_("Files in current folder"))
        self._folder_btn.set_sensitive(False)
        # MenuButton handles its own popup; no extra signal needed.
        self._folder_btn_sids = []
        footer.pack_end(self._folder_btn, False, False, 0)

        # ── Browse button (far right) ─────────────────────────────────────
        browse_img = Gtk.Image.new_from_icon_name(
            "document-open", Gtk.IconSize.SMALL_TOOLBAR
        )
        self._browse_btn = Gtk.Button()
        self._browse_btn.set_image(browse_img)
        self._browse_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._browse_btn.set_tooltip_text(_("Open Markdown file\u2026"))
        self._browse_btn_sids = [
            self._browse_btn.connect("clicked", self.cb_browse),
        ]
        # Keep legacy attribute name so on_unload's loop still finds it
        self._btn_signal_ids = self._browse_btn_sids
        footer.pack_end(self._browse_btn, False, False, 0)

        # ── Outer VBox (populated by init()) ─────────────────────────────
        outer_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer_vbox.set_border_width(0)
        outer_vbox.pack_end(footer, False, False, 0)
        outer_vbox.pack_end(Gtk.Separator(), False, False, 0)

        return outer_vbox, footer

    # ── helpers ────────────────────────────────────────────────────────

    def _set_status(self, msg: str, error: bool = False) -> None:
        """Update the footer status label.

        :param msg:   Message to display.
        :param error: When ``True``, render the text in red.
        """
        label = getattr(self, "info_label", None)
        if label is None or not label.get_realized():
            return
        colour = "#cc0000" if error else "#555555"
        label.set_markup(
            '<small><span foreground="{}">{}</span></small>'.format(colour, _esc(msg))
        )

    def _set_loaded(self, path: str) -> None:
        """Show ``'Loaded: <filename> from <parent_dir>'`` in the status bar.

        Also enables the edit and folder-menu buttons and repopulates the
        folder popup menu with all Markdown files found in the same directory.

        :param path: Absolute path to the loaded Markdown file.
        """
        filename = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))
        grandparent = os.path.basename(os.path.dirname(os.path.dirname(path)))
        location = "{}/{}".format(grandparent, parent) if grandparent else parent
        self._set_status(_("Loaded: {} from {}").format(filename, location))

        # Enable footer action buttons now that a file is loaded
        edit_btn = getattr(self, "_edit_btn", None)
        if edit_btn is not None:
            edit_btn.set_sensitive(True)
        folder_btn = getattr(self, "_folder_btn", None)
        if folder_btn is not None:
            folder_btn.set_sensitive(True)
            self._populate_folder_menu(path)

    def _populate_folder_menu(self, current_path: str) -> None:
        """Rebuild the folder popup menu with ``.md`` files from the current folder.

        Files are listed in alphabetical order (case-insensitive).  The
        currently loaded file is prefixed with ``•`` to mark it visually.
        Clicking any item loads (or reloads) that file.

        :param current_path: Absolute path to the currently loaded file; used
                             to determine the folder and mark the active entry.
        """
        menu = getattr(self, "_folder_menu", None)
        if menu is None:
            return

        # Remove all existing items
        for child in menu.get_children():
            menu.remove(child)

        folder = os.path.dirname(current_path)
        try:
            entries = sorted(os.listdir(folder), key=str.casefold)
        except OSError:
            entries = []

        md_files = [
            e
            for e in entries
            if e.lower().endswith((".md", ".markdown"))
            and os.path.isfile(os.path.join(folder, e))
        ]

        if not md_files:
            item = Gtk.MenuItem(label=_("(no Markdown files in folder)"))
            item.set_sensitive(False)
            menu.append(item)
        else:
            current_name = os.path.basename(current_path)
            for fname in md_files:
                label = ("• " if fname == current_name else "  ") + fname
                item = Gtk.MenuItem(label=label)
                full_path = os.path.join(folder, fname)
                item.connect(
                    "activate",
                    lambda _mi, p=full_path: self._load(p),
                )
                menu.append(item)

        menu.show_all()

    def _browse_start_dir(self) -> str:
        """Return the directory the file-chooser dialog should open in.

        Prefers the grandparent of the current file (i.e. the add-ons folder),
        then the Gramps plug-ins directory, then the user's home directory.

        :returns: Absolute directory path string.
        """
        if self.current_file:
            candidate = os.path.dirname(os.path.dirname(self.current_file))
            if os.path.isdir(candidate):
                return candidate
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        plugins_dir = os.path.dirname(plugin_dir)
        if os.path.isdir(plugins_dir):
            return plugins_dir
        return os.path.expanduser("~")

    def _open_uri(self, uri: str) -> None:
        """Open *uri* with the system default handler.

        :param uri: URI to open (``http://``, ``file://``, etc.).
        """
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception:
            try:
                subprocess.Popen(["xdg-open", uri])
            except Exception:
                self._set_status(_("Could not open: {}").format(uri), error=True)

    def _resolve_path(self, path: str) -> str:
        """Resolve *path* relative to the currently loaded Markdown file.

        :param path: Absolute or relative filesystem path.
        :returns: Resolved absolute path (may not exist).
        """
        if os.path.isabs(path):
            return path
        if self.current_file:
            base = os.path.dirname(self.current_file)
            candidate = os.path.join(base, path)
            if os.path.isfile(candidate):
                return candidate
        return path

    def _seg_tag_at(self, x: int, y: int) -> tuple[str | None, str | None]:
        """Return ``(style, uri)`` for the topmost interactive tag at pixel ``(x, y)``.

        Looks up URIs from ``self._link_uris``.  *style* is one of:
        ``'hyperlink'``, ``'image_link'``, ``'gramps_link'``, or
        ``'anchor_link'``.

        :param x: Widget-relative X coordinate.
        :param y: Widget-relative Y coordinate.
        :returns: ``(style, uri)`` or ``(None, None)`` if no interactive tag
                  is under the cursor.
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

    def _scroll_to_anchor(self, slug: str) -> None:
        """Scroll the TextView to the :class:`Gtk.TextMark` for *slug*.

        Does nothing if no mark has been registered for *slug*.

        :param slug: Anchor slug string (e.g. ``'gtk-inspector'``).
        """
        mark = self._anchor_marks.get(slug)
        if mark is None:
            LOG.debug("Anchor not found: #%s", slug)
            self._set_status(_("Anchor not found: #{}").format(slug), error=True)
            return
        self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 0.1)

    # ── file loading ───────────────────────────────────────────────────

    def _load(self, path: str) -> None:
        """Load and render the Markdown file at *path*.

        :param path: Absolute (or ``~``-prefixed) path to a Markdown file.
        """
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            self._set_status(
                _("File not found: '{}'").format(os.path.basename(path)),
                error=True,
            )
            ErrorDialog(
                _("File Not Found"),
                _("'{}' does not exist or is not a regular file.").format(path),
                parent=self.uistate.window,
            )
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                md_text = fh.read()
            self.current_file = path
            self._render(md_text)
            self._set_loaded(path)
        except Exception as exc:
            traceback.print_exc()
            self._set_status(_("Error: {}").format(str(exc)), error=True)
            ErrorDialog(_("Error Loading File"), str(exc), parent=self.uistate.window)

    # ── rendering ──────────────────────────────────────────────────────

    def _render(self, md_text: str) -> None:
        """Parse *md_text* and populate the :class:`Gtk.TextBuffer` segment by segment.

        Creates a fresh buffer each call so the tag table is empty (reusing a
        buffer and calling ``create_tag()`` again raises "tag already exists").

        Heading segments that carry an ``anchor`` attribute get a
        :class:`Gtk.TextMark` placed at their start position so that
        anchor-link clicks can scroll to them.

        :param md_text: Raw Markdown document text.
        """
        buf = Gtk.TextBuffer()
        self.textview.set_buffer(buf)

        self._tags = define_tags(buf)
        self._link_uris = {}
        self._anchor_marks = {}
        link_counter = [0]

        def make_link_tag(style_tag_name: str, uri: str) -> Gtk.TextTag:
            """Create a per-link tag in *buf* and register it in ``_link_uris``.

            :param style_tag_name: Visual style key (``'hyperlink'``,
                                   ``'image_link'``, ``'gramps_link'``, or
                                   ``'anchor_link'``).
            :param uri:            The URI or ``#slug`` string for the link.
            :returns: The newly created :class:`Gtk.TextTag`.
            """
            link_counter[0] += 1
            name = "_link_{}".format(link_counter[0])
            if style_tag_name == "image_link":
                t = buf.create_tag(
                    name,
                    foreground="#0077aa",
                    underline=Pango.Underline.SINGLE,
                    background="#eef4ff",
                )
            elif style_tag_name == "gramps_link":
                t = buf.create_tag(
                    name,
                    foreground="#8800aa",
                    underline=Pango.Underline.SINGLE,
                    background="#f5eeff",
                )
            elif style_tag_name == "anchor_link":
                t = buf.create_tag(
                    name,
                    foreground="#006633",
                    underline=Pango.Underline.SINGLE,
                )
            else:
                t = buf.create_tag(
                    name,
                    foreground="#0055cc",
                    underline=Pango.Underline.SINGLE,
                )
            self._link_uris[name] = (uri, style_tag_name)
            return t

        segments = parse_markdown(md_text)
        it = buf.get_end_iter()

        for seg in segments:
            if seg.table_data:
                # ── embedded GTK TreeView table ───────────────────────────
                columns, align, body_rows, sep_widths = seg.table_data
                tbl_widget = build_table_widget(columns, align, body_rows, sep_widths)
                anchor = buf.create_child_anchor(it)
                self.textview.add_child_at_anchor(tbl_widget, anchor)
                tbl_widget.show_all()

            elif seg.gramps_icon:
                # ── inline GTK/Gramps theme icon ──────────────────────────
                icon_name, size = seg.gramps_icon
                pb = resolve_icon_pixbuf(icon_name, size)
                if pb:
                    buf.insert_pixbuf(it, pb)
                else:
                    start_mark = buf.create_mark(None, it, True)
                    buf.insert(it, "[{}]".format(icon_name))
                    start_it = buf.get_iter_at_mark(start_mark)
                    t = self._tags.get("blockquote")
                    if t:
                        buf.apply_tag(t, start_it, it)
                    buf.delete_mark(start_mark)

            elif seg.image_path:
                # ── embedded image or clickable placeholder ───────────────
                img_path = self._resolve_path(seg.image_path)
                inserted = False
                if os.path.isfile(img_path):
                    inserted = self._insert_image(buf, it, img_path, seg.text)
                if not inserted:
                    display = "[image: {}]".format(seg.text or seg.image_path)
                    link_tag = make_link_tag("image_link", seg.image_path)
                    start_mark = buf.create_mark(None, it, True)
                    buf.insert(it, display)
                    start_it = buf.get_iter_at_mark(start_mark)
                    buf.apply_tag(link_tag, start_it, it)
                    buf.delete_mark(start_mark)

            elif seg.url:
                # ── clickable link (web, file, gramps:, or #anchor) ───────
                if seg.url.startswith("#"):
                    link_tag = make_link_tag("anchor_link", seg.url)
                elif seg.url.startswith("gramps:"):
                    link_tag = make_link_tag("gramps_link", seg.url)
                else:
                    link_tag = make_link_tag("hyperlink", seg.url)
                start_mark = buf.create_mark(None, it, True)
                buf.insert(it, seg.text)
                start_it = buf.get_iter_at_mark(start_mark)
                buf.apply_tag(link_tag, start_it, it)
                buf.delete_mark(start_mark)

                # Place anchor mark if this heading segment has one
                if seg.anchor:
                    mark = buf.create_mark(
                        "anchor:{}".format(seg.anchor), start_it, True
                    )
                    self._anchor_marks[seg.anchor] = mark

            else:
                # ── styled plain text ─────────────────────────────────────
                start_mark = buf.create_mark(None, it, True)
                buf.insert(it, seg.text)
                start_it = buf.get_iter_at_mark(start_mark)

                # Place anchor mark at the start of this heading run
                if seg.anchor:
                    mark = buf.create_mark(
                        "anchor:{}".format(seg.anchor), start_it, True
                    )
                    self._anchor_marks[seg.anchor] = mark

                for attr in seg.attrs:
                    t = self._tags.get(attr)
                    if t:
                        buf.apply_tag(t, start_it, it)
                buf.delete_mark(start_mark)

            it = buf.get_end_iter()

    def _insert_image(
        self,
        buf: Gtk.TextBuffer,
        it: Gtk.TextIter,
        img_path: str,
        alt_text: str,
    ) -> bool:
        """Insert a scaled pixbuf into *buf* at *it*.

        Scales the image to fit within ``MAX_W`` pixels wide.  Appends a
        caption line below the image if *alt_text* is non-empty.

        :param buf:      The :class:`Gtk.TextBuffer` to insert into.
        :param it:       Insertion :class:`Gtk.TextIter`.
        :param img_path: Absolute path to the image file.
        :param alt_text: Alt text used as a caption; may be empty.
        :returns: ``True`` on success, ``False`` on any error.
        """
        try:
            MAX_W = 560
            pb = GdkPixbuf.Pixbuf.new_from_file(img_path)
            w, h = pb.get_width(), pb.get_height()
            if w > MAX_W:
                h = int(h * MAX_W / w)
                w = MAX_W
                pb = pb.scale_simple(w, h, GdkPixbuf.InterpType.BILINEAR)
            buf.insert_pixbuf(it, pb)
            buf.insert(it, "\n")
            caption_tag = self._tags.get("blockquote")
            if alt_text and caption_tag:
                start_mark = buf.create_mark(None, it, True)
                buf.insert(it, alt_text + "\n")
                start_it = buf.get_iter_at_mark(start_mark)
                buf.apply_tag(caption_tag, start_it, it)
                buf.delete_mark(start_mark)
            return True
        except Exception:
            return False

    # ── event handlers ─────────────────────────────────────────────────

    def cb_edit_file(self, _widget: Gtk.Button) -> None:
        """Callback: open the current file in the system default editor.

        Uses :func:`Gio.AppInfo.get_default_for_type` to honour the desktop's
        registered handler for ``text/markdown`` (and ``text/plain`` as a
        fallback).  Falls back to ``xdg-open`` on platforms where Gio is
        unavailable or returns no handler.

        :param _widget: The edit :class:`Gtk.Button` (unused).
        """
        path = getattr(self, "current_file", None)
        if not path or not os.path.isfile(path):
            self._set_status(_("No file loaded to edit"), error=True)
            return
        uri = "file://" + os.path.abspath(path)
        launched = False
        for mime in ("text/markdown", "text/x-markdown", "text/plain"):
            try:
                app = Gio.AppInfo.get_default_for_type(mime, False)
                if app:
                    app.launch_uris([uri], None)
                    launched = True
                    break
            except Exception:
                pass
        if not launched:
            # Last resort: generic URI open (xdg-open on Linux)
            self._open_uri(uri)

    def cb_browse(self, _widget: Gtk.Button) -> None:
        """Callback: open a file-chooser dialog and load the selected file.

        :param _widget: The browse :class:`Gtk.Button` (unused).
        """
        dialog = Gtk.FileChooserDialog(
            title=_("Open Markdown File"),
            parent=self.uistate.window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN,
            Gtk.ResponseType.OK,
        )
        dialog.set_current_folder(self._browse_start_dir())
        dialog.connect("realize", lambda d: self._set_dialog_sort(d))

        filt_md = Gtk.FileFilter()
        filt_md.set_name(_("Markdown files (*.md, *.markdown)"))
        filt_md.add_pattern("*.md")
        filt_md.add_pattern("*.markdown")
        dialog.add_filter(filt_md)

        filt_all = Gtk.FileFilter()
        filt_all.set_name(_("All files"))
        filt_all.add_pattern("*")
        dialog.add_filter(filt_all)

        if dialog.run() == Gtk.ResponseType.OK:
            self._load(dialog.get_filename())
        dialog.destroy()

    @staticmethod
    def _set_dialog_sort(dialog: Gtk.FileChooserDialog) -> None:
        """Sort the file-chooser tree by modification date (most-recent first).

        This is a best-effort heuristic; silently does nothing if the internal
        TreeView or sort model cannot be located.

        :param dialog: The :class:`Gtk.FileChooserDialog` to sort.
        """
        try:

            def find_treeview(widget: Gtk.Widget) -> Gtk.TreeView | None:
                """Recursively search *widget*'s children for a TreeView."""
                if isinstance(widget, Gtk.TreeView):
                    return widget
                if hasattr(widget, "get_children"):
                    for child in widget.get_children():
                        found = find_treeview(child)
                        if found:
                            return found
                return None

            tv = find_treeview(dialog)
            if tv:
                model = tv.get_model()
                if model and hasattr(model, "set_sort_column_id"):
                    model.set_sort_column_id(6, Gtk.SortType.DESCENDING)
        except Exception:
            pass

    def _on_motion(self, widget: Gtk.TextView, event: Gdk.EventMotion) -> bool:
        """Update the cursor shape when hovering over a link.

        Guards against calls that arrive after :meth:`on_unload` has run
        (stale events queued before signal disconnect took effect).

        :param widget: The :class:`Gtk.TextView`.
        :param event:  The :class:`Gdk.EventMotion` event.
        :returns: ``False`` (event not consumed).
        """
        if not getattr(self, "_signal_ids", None):
            return False
        if not widget.get_realized():
            return False
        style, _uri = self._seg_tag_at(int(event.x), int(event.y))
        cursor_normal = getattr(self, "_cursor_normal", None)
        cursor_link = getattr(self, "_cursor_link", None)
        if cursor_normal is None:
            return False
        cursor = cursor_link if style else cursor_normal
        win = widget.get_window(Gtk.TextWindowType.TEXT)
        if win:
            win.set_cursor(cursor)
        return False

    def _on_click(self, widget: Gtk.TextView, event: Gdk.EventButton) -> bool:
        """Handle left-click on hyperlinks, image placeholders, and Gramps links.

        :param widget: The :class:`Gtk.TextView`.
        :param event:  The :class:`Gdk.EventButton` event.
        :returns: ``True`` if the event was consumed, ``False`` otherwise.
        """
        if not getattr(self, "_signal_ids", None):
            return False
        if event.button != 1:
            return False
        style, uri = self._seg_tag_at(int(event.x), int(event.y))
        if not uri:
            return False

        if style == "anchor_link":
            # In-document scroll: strip the leading '#' to get the slug
            self._scroll_to_anchor(uri[1:])

        elif style == "image_link":
            resolved = self._resolve_path(uri)
            if os.path.isfile(resolved):
                self._open_uri("file://" + os.path.abspath(resolved))
            else:
                self._open_uri(uri)

        elif style == "gramps_link":
            self._handle_gramps_uri(uri)

        else:
            # Relative .md links load inside the viewer
            if not uri.startswith(("http://", "https://", "ftp://", "file://")):
                resolved = self._resolve_path(uri)
                if os.path.isfile(resolved) and resolved.endswith((".md", ".markdown")):
                    self._load(resolved)
                    return True
            self._open_uri(uri)

        return True

    def _handle_gramps_uri(self, uri: str) -> None:
        """Dispatch a ``gramps:`` URI to the appropriate Gramps action.

        Supported schemes::

          gramps:nav:<Type>:<GrampsID>        -- switch view, set active
          gramps:nav:<Type>:handle:<Handle>
          gramps:edit:<Type>:<GrampsID>       -- open object editor
          gramps:edit:<Type>:handle:<Handle>
          gramps:view:<category>              -- switch to named view category

        :param uri: The full ``gramps:`` URI string.
        """
        try:
            parts = uri.split(":")
            if len(parts) < 3:
                return
            action = parts[1]

            if action == "view" and len(parts) >= 3:
                self._gramps_switch_view(parts[2])
                return

            if action not in ("nav", "edit") or len(parts) < 4:
                return

            obj_type = parts[2]
            if parts[3] == "handle" and len(parts) >= 5:
                ref = "handle"
                value = parts[4]
            else:
                ref = "id"
                value = parts[3]

            info = NAMESPACE_MAP.get(obj_type)
            if not info:
                self._set_status(
                    _("Unknown object type: {}").format(obj_type), error=True
                )
                return

            getter_id, getter_handle, editor_name = info
            db = self.dbstate.db

            obj = (
                getattr(db, getter_handle)(value)
                if ref == "handle"
                else getattr(db, getter_id)(value)
            )

            if obj is None:
                self._set_status(
                    _("Not found: {} {}").format(obj_type, value), error=True
                )
                return

            if action == "edit":
                self._gramps_open_editor(editor_name, obj)
            else:
                self._gramps_navigate(obj_type, obj.get_handle())

        except Exception:
            traceback.print_exc()

    def _gramps_navigate(self, obj_type: str, handle: str) -> None:
        """Switch to the view for *obj_type* and set the active object.

        ``goto_page()`` is asynchronous; we defer ``set_active`` via a 150 ms
        timeout so the target view is fully constructed before we select into it.

        :param obj_type: Gramps object-type name (e.g. ``'Person'``).
        :param handle:   Database handle of the object to select.
        """
        try:
            cat_name = VIEW_NAMES.get(obj_type.lower(), obj_type + "s")
            vm = self.uistate.viewmanager
            for page_num, page_list in enumerate(vm.pages):
                for view_num, view in enumerate(page_list):
                    title = self._view_category_title(view)
                    if cat_name.lower() in title.lower():
                        vm.goto_page(page_num, view_num)
                        break
                else:
                    continue
                break

            def _do_set_active() -> bool:
                """Deferred callback: set the active object in the target view."""
                try:
                    self.uistate.set_active(obj_type, handle)
                except Exception:
                    traceback.print_exc()
                return False

            GLib.timeout_add(150, _do_set_active)

        except Exception:
            traceback.print_exc()

    @staticmethod
    def _view_category_title(view) -> str:
        """Return the category title string for *view*, trying all known APIs.

        :param view: A Gramps view object.
        :returns: Category title string, falling back to the class name.
        """
        try:
            return view.get_translated_category()
        except Exception:
            pass
        try:
            cat = view.category
            if isinstance(cat, (list, tuple)) and len(cat) > 1:
                return str(cat[1])
            return str(cat)
        except Exception:
            pass
        return type(view).__name__

    def _gramps_open_editor(self, editor_name: str, obj) -> None:
        """Open a Gramps object editor dialog.

        :param editor_name: Name of the editor class in ``gramps.gui.editors``
                            (e.g. ``'EditPerson'``).
        :param obj:         The Gramps object to edit.
        """
        try:
            import gramps.gui.editors as editors_mod

            editor_class = getattr(editors_mod, editor_name)
            editor_class(self.dbstate, self.uistate, [], obj)
        except Exception:
            traceback.print_exc()
            self._set_status(
                _("Cannot open editor: {}").format(editor_name), error=True
            )

    def _gramps_switch_view(self, category: str) -> None:
        """Switch to a named view category (e.g. ``'People'``, ``'dashboard'``).

        :param category: View category name or alias (case-insensitive).
        """
        try:
            target = VIEW_NAMES.get(category.lower(), category)
            vm = self.uistate.viewmanager
            for page_num, page_list in enumerate(vm.pages):
                for view_num, view in enumerate(page_list):
                    title = self._view_category_title(view)
                    if target.lower() in title.lower():
                        vm.goto_page(page_num, view_num)
                        return
        except Exception:
            traceback.print_exc()

    def main(self) -> None:
        """Gramps gramplet main hook -- no-op for this display-only gramplet."""
