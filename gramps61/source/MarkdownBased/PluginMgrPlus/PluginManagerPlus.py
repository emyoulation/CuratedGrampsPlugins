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
"""Enhanced Gramps 5.2 plugin manager.

Displays registry details and README content with :mod:`MarkdownUtils`, a
selection-driven Preview pane, and a sortable/filterable plugin list.  Addon
metadata and optional wiki thumbnails are cached under ``media/``.
"""

# ------------------------
# Python modules
# ------------------------
import difflib
import json
import logging
import os
import sys
import re
import shutil
import threading
import time
import urllib.request
from operator import itemgetter

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gdk, GdkPixbuf, GObject, Gio, Gtk, GLib
from gi.repository.GLib import markup_escape_text

from gramps.cli.grampscli import CLIManager
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import (
    AUDIENCETEXT,
    PluginRegister,
    load_addon_file,
    version_str_to_tup,
)
from gramps.gen.plug._pluginreg import (
    GRAMPLET,
    PTYPE_STR,
    REPORT,
    TOOL,
    VIEW,
)
from gramps.gen.plug.report._constants import standalone_categories

try:
    # RULE (custom-filter Rule plug-ins, with a `namespace` attribute like
    # `namespace = 'Person'`) — present in Gramps 5.1+. Guarded since this
    # addon targets 5.2 but RULE isn't part of the older, more stable
    # plugin-type set.
    from gramps.gen.plug._pluginreg import RULE
except ImportError:
    RULE = object()  # sentinel that will never equal a real pdata.ptype
from gramps.gen.utils.configmanager import safe_eval
from gramps.gui.dialog import OkDialog
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.navigator import CATEGORY_ICON
from gramps.gui.plug import tool
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.utils import open_file_with_default_application

# ------------------------
# Gramps specific
# ------------------------
# MarkdownUtils lives one directory level above this plugin's folder.
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from MarkdownUtils import (
        ICON_STYLE_COLOR,
        markdown_link_at,
        render_markdown,
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
ngettext = _trans.ngettext

LOG = logging.getLogger(".gui.plug")

TITLE = _("Plugin Manager plus")

# Fallback only — see _is_own_plugin_data, which primarily identifies
# this addon's own registry entry by comparing this running file's own
# directory against each candidate's registered ``fpath`` (a fact Gramps'
# registry already tracks, so it can't fall out of sync the way a
# separately hand-maintained id constant can across a rename). This
# constant is used only for candidates with no ``fpath`` at all (i.e.
# never for a real, installed "own" entry) and should still match the
# `id=` this addon registers under in PluginManagerPlus.gpr.py.
OWN_PLUGIN_ID = "PluginManagerPlus"
static = sys.modules[__name__]
static.panel = 0

# Dedicated ConfigManager for this addon's own persisted UI state (pane
# divider positions and plugin-list column widths — the "Show"
# checkboxes are intentionally never persisted at all, see
# PluginStatus.__init__), stored as PluginManagerPlus.ini alongside this
# file via Gramps' documented "own-directory" ConfigManager pattern
# (config.register_manager(name, __file__, use_plugins_path=False)),
# rather than under Gramps' central per-user config directory. This is
# separate from — and does not replace — self.options/PluginManagerOptions
# below (a tool.ToolOptions subclass kept for Gramps' Tool-plugin
# framework compliance); this addon simply doesn't rely on that class's
# own ini-file storage location.
#
# Section names mirror gramps.ini's own convention: window/pane geometry
# under [interface], column widths under [spacing].
_ini_manager = config.register_manager(
    "pluginmanagerplus", __file__, use_plugins_path=False
)
# [interface] — pane divider positions.
# list-pane-height: self.vpane's (VERTICAL) divider position — the
# height given to the upper Details/Preview area, with the List pane
# below it getting whatever height remains. 360 is 60% of the dialog's
# own 600px default height (see setup_configs("interface.pluginstatus",
# 800, 600)), giving roughly a 60/40 top/bottom split by default — an
# approximation, since the button bar and checkbox row above/below the
# vpane, plus the dialog's own chrome, aren't part of that 600px
# figure either.
_ini_manager.register("interface.list-pane-height", 360)
# preview-pane-width: self._thumb_right_vbox's (the upper-right
# "Preview" thumbnail/status pane) own allocated width — see
# _cb_info_pane_size_allocate, which derives self._info_pane's
# (HORIZONTAL) divider position from this on first layout, since a
# Paned's "position" is measured from its own start (left) edge, i.e.
# the *left* ("Details") pane's width, not the right one's.
_ini_manager.register("interface.preview-pane-width", 280)
# [spacing] — plugin-list column widths (see registered_plugins_panel).
# Type/Name/Status are genuine user preferences (the only way their
# width changes is the user dragging them), so they're persisted.
# Description is deliberately NOT persisted here: its column has
# set_expand(True) and is meant to just fill whatever space the
# dialog's current width leaves over after the other columns, so
# there's no stable "preference" to save — see _DESC_COL_MIN_WIDTH,
# used only as its initial/minimum width before the first real layout
# pass, in registered_plugins_panel.
_ini_manager.register("spacing.type-column-width", 170)
_ini_manager.register("spacing.name-column-width", 225)
# 108px (20% wider than the original 90px default) — see the Status
# column, pinned as the leftmost column in registered_plugins_panel so
# it stays visible without needing to scroll right.
_ini_manager.register("spacing.status-column-width", 108)
_ini_manager.load()

# Description column's initial/minimum fixed width (also its initial
# CellRendererText wrap_width) before set_expand(True) grows it to
# fill whatever space the dialog's actual width leaves over — see
# registered_plugins_panel. Deliberately a plain constant rather than
# an _ini_manager-persisted value (see the "[spacing]" comment above).
_DESC_COL_MIN_WIDTH = 400
# Extra pixels subtracted from the Description column's own on-screen
# width when computing its CellRendererText's live "wrap-width" (on
# top of the renderer's own "xpad" property, also subtracted) — covers
# the focus-rectangle GTK draws around a selected row's cell, which
# "xpad" alone doesn't account for. Without this, wrapped text can
# render a few pixels past the column's right edge. See
# _cb_desc_column_resized.
_DESC_WRAP_SAFETY_PX = 4

# Raw MediaWiki source of the addon-catalog table this plugin bundles a
# local copy of at media/Template_Addons5.2.txt. Used only to refresh that
# local copy when it is missing; normal operation never requires network
# access to render the info/thumbnail panel.
WIKI_TABLE_URL = (
    "https://gramps-project.org/wiki/index.php?" "title=Template:Addons5.2&action=raw"
)

# Required keys for a valid addon-listing record (one line of
# new_addons.txt / any future JSON-lines addon listing). See
# _parse_addon_listing_line().
_ADDON_RECORD_REQUIRED_KEYS = ("i", "n", "d", "t", "v", "z")

UPDATE_RES = 666
IGNORE_RES = 888

# Status bit mask values
INSTALLED = 1
AVAILABLE = 2
BUILTIN = 4
HIDDEN = 8
UPDATE = 16

# plug-ins model column numbers
R_TYPE = 0
R_STAT_S = 1
R_NAME = 2
R_DESC = 3
R_ID = 4
R_STAT = 5
# R_TYPE_DISPLAY holds the same category text as R_TYPE plus, for Tools
# and Reports with a known sub-category, a second markup line ("\n  " +
# sub-category label). Kept separate from R_TYPE so filtering (keyed on
# R_TYPE, see _apply_filter) still matches purely on the plain category
# name; see R_TYPE_SORT below for the equivalent separation for sorting.
R_TYPE_DISPLAY = 6
# R_TYPE_ICONS holds a composited horizontal strip of view-restriction
# icons (see _compose_icon_strip) for a Gramplet restricted to specific
# navtypes, or a single-icon strip for a Rule's object-type namespace, or
# None for every other row (including an unrestricted gramplet). Rendered
# as a second, stacked line under R_TYPE_DISPLAY.
R_TYPE_ICONS = 7
# R_TYPE_SORT is a plain (unescaped, unmarked-up) sort key: the type name
# plus, if there's a second Type-column line, that line's plain-text
# detail (sub-category label, or the joined navtypes/namespace labels for
# Gramplets/Rules) appended after a separator that sorts before any
# printable character — so rows with no second line sort first within
# their type, then rows group further by that detail. Used for col0's
# sort_column_id instead of R_TYPE so a Type-column sort groups by these
# extra lines too; see _cb_type_sort for the required within-type
# secondary sort by Name.
R_TYPE_SORT = 8
# R_HAS_README holds a 24px "document-page-setup" icon if the plugin has its own
# README.md, else None. Double-clicking this cell selects the row and
# shows that README in the info pane, same as clicking the Help button —
# see button_press_reg.
R_HAS_README = 9
# R_HAS_HELP holds a 24px "web-browser" icon if the plugin has a
# help_url, else None. Double-clicking this cell selects the row and
# opens the help link, same as clicking the "Help:" link in the details
# pane — see button_press_reg / _cb_open_help_url.
R_HAS_HELP = 10

_STABLE_PREVIEW_ICON = "gramps-addon"
_DEVEL_PREVIEW_ICON = "org.gnome.Extensions.Devel"

# Preview images larger than this are not loaded or thumbnailed; the
# Preview pane shows a complaint instead (see _render_preview).
_MAX_PREVIEW_IMAGE_BYTES = 5 * 1024 * 1024

# Left padding (px) for the Type column's second-line icon strip, so it
# lines up with the "\n  " (2-space) indent used for the Tool/Report
# sub-category text line instead of GtkCellAreaBox's default centering.
_TYPE_ICON_INDENT_PX = 16

# Pixel size for the Notes/Source indicator-icon columns.
_INDICATOR_ICON_SIZE = 25

# Ordered (canonical_key, label, icon_name) tuples for a gramplet's
# navtypes view restrictions. Always rendered in this fixed order in the
# plugin list's Type column, regardless of the order navtypes lists them
# in, so the icon strip reads consistently row to row.
_GRAMPLET_VIEW_ICONS = [
    ("dashboard", _("Dashboard"), "gramps-gramplet"),
    ("people", _("People"), "gramps-person"),
    ("relationship", _("Relationship"), "gramps-relation"),
    ("families", _("Families"), "gramps-family"),
    ("charts", _("Charts"), "gramps-pedigree"),
    ("events", _("Events"), "gramps-event"),
    ("places", _("Places"), "gramps-place"),
    ("geography", _("Geography"), "gramps-geo"),
    ("sources", _("Sources"), "gramps-source"),
    ("citations", _("Citations"), "gramps-citation"),
    ("repositories", _("Repositories"), "gramps-repository"),
    ("media", _("Media"), "gramps-media"),
    ("notes", _("Notes"), "gramps-notes"),
]

# Maps every raw navtypes value Gramps is known to use — singular
# primary-object names ("Person"), plural category names ("People"), and
# likely spelling variants for the non-object categories ("Charts",
# "Geography", "Relationship(s)") — to one of the canonical keys above,
# case-insensitively. Gramps' documented navtypes values are the
# singular primary-object forms; the plural/category forms are included
# defensively in case a gramplet registers with those instead.
_NAVTYPE_ALIASES = {
    "dashboard": "dashboard",
    "person": "people",
    "people": "people",
    "relationship": "relationship",
    "relationships": "relationship",
    "family": "families",
    "families": "families",
    "chart": "charts",
    "charts": "charts",
    "pedigree": "charts",
    # Gramps' own Pedigree/Fan/Descendant/etc. View plugins still register
    # under the legacy internal codename "Ancestry" (see
    # gramps/plugins/view/view.gpr.py — category=("Ancestry", _("Charts"))
    # — even though the user-facing category was renamed to "Charts"), so
    # it must resolve to the same canonical key as "charts"/"chart" above,
    # or those built-in Views fall through to the unrecognised-category
    # text fallback in __populate_reg_list's VIEW branch instead of
    # showing the "gramps-pedigree" icon.
    "ancestry": "charts",
    "event": "events",
    "events": "events",
    "place": "places",
    "places": "places",
    "geography": "geography",
    "geo": "geography",
    "source": "sources",
    "sources": "sources",
    "citation": "citations",
    "citations": "citations",
    "repository": "repositories",
    "repositories": "repositories",
    "media": "media",
    "note": "notes",
    "notes": "notes",
}


def _subcategory_label(ptype: object, category: object) -> str | None:
    """
    Return a Tool/Report's sub-category display label, if known.

    Looked up directly from the live Gramps engine registries — Tools:
    :data:`gramps.gui.plug.tool.tool_categories`; Reports:
    :data:`gramps.gen.plug.report._constants.standalone_categories` —
    each mapping a ``category`` value to a ``(codename, translated
    label)`` pair, rather than from a locally maintained copy. Both
    registries hold Gramps' own built-in Tools/Reports menu structure
    *and* any additional sub-categories an addon's own .gpr.py registers
    into them at import time (e.g. SuperTool.gpr.py's
    ``plug.tool.tool_categories["Isotammi"] = ("Isotammi", _("Isotammi
    tools"))``), so this also resolves those addon-defined sub-categories
    — a locally maintained dict of just Gramps' own built-in constants
    could not.

    :param ptype: the plugin's ``ptype`` (compared against ``TOOL``/``REPORT``)
    :param category: the plugin's ``category`` attribute value
    :returns: a translated label, or ``None`` if ``ptype`` isn't a Tool or
              Report, or ``category`` isn't a recognised value
    """
    if ptype == TOOL:
        entry = tool.tool_categories.get(category)
    elif ptype == REPORT:
        entry = standalone_categories.get(category)
    else:
        return None
    return entry[1] if entry else None


def _canonical_navtypes(navtypes: object) -> list[str]:
    """
    Normalise a gramplet's ``navtypes`` into canonical, ordered keys.

    :param navtypes: the plugin's ``navtypes`` attribute value (a list of
                      strings), or ``None``/empty if unrestricted
    :returns: canonical keys (see :data:`_GRAMPLET_VIEW_ICONS`) present in
              ``navtypes``, in the fixed display order — empty if
              ``navtypes`` is falsy or none of its values are recognised
    """
    if not navtypes:
        return []
    matched = set()
    for raw in navtypes:
        key = _NAVTYPE_ALIASES.get(str(raw).strip().lower())
        if key:
            matched.add(key)
    return [key for key, _label, _icon in _GRAMPLET_VIEW_ICONS if key in matched]


def _load_named_icon_pixbuf(icon_name: str, size: int) -> "GdkPixbuf.Pixbuf | None":
    """
    Resolve a themed/Gramps icon name to a pixbuf at the given size.

    Prefers :func:`MarkdownUtils.resolve_icon_pixbuf` (the same resolver
    used for ``gramps:icon:name:size`` images in the Markdown-rendered
    detail pane) for consistent results; falls back to the default
    :class:`Gtk.IconTheme` directly if MarkdownUtils is unavailable or
    doesn't know the icon.

    Always requests the *color* icon style, never
    :mod:`MarkdownUtils`'s own default ``'auto'`` — its own
    ``prefer_symbolic = size <= 32`` heuristic (reasonable for e.g.
    inline text, where a small symbolic glyph blends with surrounding
    prose better than a busy color one) otherwise means every caller
    here, all of which request compact 16-25px icons for quick visual
    scanning in the List panel and its Details pane, would get muted
    monochrome symbolic icons instead of the colorful, individually
    recognizable ones this UI actually wants.

    :param icon_name: a themed icon name (e.g. ``gramps-person``)
    :param size: the desired pixel size (square)
    :returns: a pixbuf, or ``None`` if the icon could not be resolved
    """
    if _MARKDOWN_AVAILABLE:
        try:
            pixbuf = resolve_icon_pixbuf(icon_name, size, icon_style=ICON_STYLE_COLOR)
            if pixbuf:
                return pixbuf
        except Exception:  # pylint: disable=broad-except
            LOG.debug("resolve_icon_pixbuf failed for '%s'", icon_name, exc_info=True)
    try:
        return Gtk.IconTheme.get_default().load_icon(icon_name, size, 0)
    except GLib.Error:
        LOG.debug("Could not load themed icon '%s'", icon_name, exc_info=True)
        return None


def _compose_icon_strip(
    icon_names: list[str], size: int = 23, gap: int = 3
) -> "GdkPixbuf.Pixbuf | None":
    """
    Composite several themed icons into one horizontal-strip pixbuf.

    Used to render a gramplet's view-restriction icons as a single
    pixbuf, since :class:`Gtk.CellRendererPixbuf` only shows one image
    per cell.

    :param icon_names: themed icon names, in the order they should
                        appear left to right
    :param size: pixel size (square) each icon is loaded/shown at
    :param gap: pixel gap between adjacent icons
    :returns: the composited strip, or ``None`` if no icon in
              ``icon_names`` could be resolved
    """
    pixbufs = [
        pb
        for pb in (_load_named_icon_pixbuf(name, size) for name in icon_names)
        if pb is not None
    ]
    if not pixbufs:
        return None
    total_w = sum(pb.get_width() for pb in pixbufs) + gap * (len(pixbufs) - 1)
    max_h = max(pb.get_height() for pb in pixbufs)
    strip = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, total_w, max_h)
    strip.fill(0x00000000)  # fully transparent background
    x = 0
    for pb in pixbufs:
        width, height = pb.get_width(), pb.get_height()
        y = (max_h - height) // 2
        pb.composite(
            strip,
            x,
            y,
            width,
            height,
            x,
            y,
            1.0,
            1.0,
            GdkPixbuf.InterpType.BILINEAR,
            255,
        )
        x += width + gap
    return strip


def _set_btn_icon_label(
    btn: "Gtk.Button",
    icon_name: str,
    label_text: str | None,
    use_mnemonic: bool = False,
) -> None:
    """
    Replace a :class:`Gtk.Button`'s child with an icon (+ optional label).

    :param btn: the button to restyle
    :param icon_name: themed icon name to display
    :param label_text: text shown next to the icon; pass ``None`` or an
                        empty string for an icon-only button
    :param use_mnemonic: whether *label_text* contains a ``_`` mnemonic
    """
    existing = btn.get_child()
    if existing is not None:
        btn.remove(existing)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    theme = Gtk.IconTheme.get_default()
    if theme.has_icon(icon_name):
        try:
            pb = theme.load_icon(
                icon_name,
                Gtk.icon_size_lookup(Gtk.IconSize.BUTTON)[1],
                Gtk.IconLookupFlags.FORCE_SIZE,
            )
            img = Gtk.Image.new_from_pixbuf(pb)
        except Exception:
            img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        hbox.pack_start(img, False, False, 0)

    if label_text:
        if use_mnemonic:
            lbl = Gtk.Label()
            lbl.set_text_with_mnemonic(label_text)
        else:
            lbl = Gtk.Label(label=label_text)
        hbox.pack_start(lbl, False, False, 0)

    hbox.show_all()
    btn.add(hbox)


class _MdInfoPane:
    """A :class:`Gtk.TextView` populated from Markdown via :mod:`MarkdownUtils`."""

    def __init__(self, uistate) -> None:
        self._uistate = uistate
        self._tags: dict = {}
        self._link_uris: dict = {}
        self.image_max_width = 560
        self.center_images = False
        self.show_image_captions = True
        self.image_adds_newline = True

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
        return self._sw

    def render(self, md_text: str, base_dir: str = "") -> None:
        """
        Render *md_text* into this pane, replacing its current content.

        Delegates the actual rendering work to
        :func:`MarkdownUtils.render_markdown` — the same shared engine
        the Markdown Dash gramplet and its standalone reader window use
        — rather than this pane keeping its own separate copy of that
        same segment-by-segment Gtk.TextBuffer-filling logic. The one
        thing genuinely specific to this pane is *base_dir*-relative
        path resolution (an image or bare-relative link resolves
        against wherever this particular Markdown document's own file
        lives, e.g. a plugin's directory), handled here via a small
        *resolve_path* closure passed in to do the resolving.

        :param md_text: the document text to render
        :param base_dir: directory *md_text*'s own image/relative-link
                          references resolve against; empty string if
                          *md_text* has no meaningful directory of its
                          own (e.g. synthetic Details-panel text)
        """
        if not _MARKDOWN_AVAILABLE:
            buf = Gtk.TextBuffer()
            buf.set_text(md_text)
            self.textview.set_buffer(buf)
            return

        def resolve_path(path: str) -> str:
            if os.path.isabs(path):
                return path
            if base_dir:
                candidate = os.path.join(base_dir, path)
                if os.path.isfile(candidate):
                    return candidate
            return path

        result = render_markdown(
            self.textview,
            md_text,
            resolve_path=resolve_path,
            image_max_width=self.image_max_width,
            center_images=self.center_images,
            show_image_captions=self.show_image_captions,
            image_adds_newline=self.image_adds_newline,
        )
        self._tags = result["tags"]
        self._link_uris = result["link_uris"]

    def _on_motion(self, widget: Gtk.TextView, event: Gdk.EventMotion) -> bool:
        if not widget.get_realized():
            return False
        style, _uri = markdown_link_at(
            self.textview, self._link_uris, int(event.x), int(event.y)
        )
        cursor = self._cursor_link if style else self._cursor_normal
        win = widget.get_window(Gtk.TextWindowType.TEXT)
        if win:
            win.set_cursor(cursor)
        return False

    def _on_click(self, widget: Gtk.TextView, event: Gdk.EventButton) -> bool:
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            return True
        if event.button != 1:
            return False
        style, uri = markdown_link_at(
            self.textview, self._link_uris, int(event.x), int(event.y)
        )
        if not uri:
            return False
        self.open_uri(uri, style)
        return True

    @staticmethod
    def resolve_help_full_url(help_url: str) -> str:
        """
        Resolve a plugin's ``help_url`` to the full URL its link opens.

        The single source of truth for this calculation: used both to
        build the clickable "Help:" line rendered by :meth:`render` and,
        via :class:`PluginStatus`, to open that same target when the
        plugin list's web-browser-indicator column is double-clicked (see
        ``_cb_open_help_url``), so the two can never disagree about
        which URL is meant.

        :param help_url: either a full URL or a Gramps wiki page title
        :returns: the resolved ``http(s)://`` URL
        """
        if not help_url.startswith(("http://", "https://")):
            return "https://gramps-project.org/wiki/index.php?title=%s" % help_url
        return help_url

    def open_uri(self, uri: str, style: str = "hyperlink") -> None:
        """
        Open ``uri`` exactly as though its rendered link text were clicked.

        Shared by the in-pane link click handler (:meth:`_on_click`) and
        any external caller — e.g. a plugin-list row's Source-indicator
        double-click — that needs to reproduce that same click, so the
        two can never compute or open the URL differently.

        :param uri: the URI (or local ``file://``/plain path) to open —
                    for ``"md_link"``, an already-resolved absolute path
                    (see the relative-reference handling in :meth:`render`)
        :param style: the link style, as produced by :meth:`render` —
                      ``"hyperlink"``/``"gramps_link"``/``"mailto_link"``
                      launch the desktop default handler; ``"file_link"``
                      opens a local file with the OS default application;
                      ``"md_link"`` re-renders another local ``.md`` file
                      in this same pane (e.g. a README's own navigation
                      links to sibling doc files in the same plugin
                      folder), rather than shelling out to the OS
        """
        if style in ("hyperlink", "gramps_link", "mailto_link"):
            self._launch_uri(uri)
        elif style == "file_link":
            path = uri[len("file://") :] if uri.startswith("file://") else uri
            if os.path.exists(path):
                try:
                    open_file_with_default_application(path, self._uistate)
                except Exception:  # pylint: disable=broad-except
                    pass
        elif style == "md_link":
            path = uri[len("file://") :] if uri.startswith("file://") else uri
            if not os.path.isfile(path):
                return
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    md_text = fh.read()
            except OSError:
                LOG.debug(
                    "Could not load linked Markdown file: %s", path, exc_info=True
                )
                return
            self.render(md_text, base_dir=os.path.dirname(path))

    @staticmethod
    def _launch_uri(uri: str) -> None:
        """
        Open ``uri`` with the desktop's default handler (e.g. a browser).

        :param uri: the URI to open
        """
        try:
            import gi as _gi

            _gi.require_version("Gio", "2.0")
            from gi.repository import Gio

            Gio.AppInfo.launch_default_for_uri(uri, None)
        except Exception:  # pylint: disable=broad-except
            try:
                import subprocess

                subprocess.Popen(["xdg-open", uri])
            except Exception:  # pylint: disable=broad-except
                pass


class _RemotePluginView:
    """
    Minimal :class:`~gramps.gen.plug._pluginreg.PluginData`-like stand-in.

    Built from one ``self.addons`` record (a parsed line of
    ``new_addons.txt``, see :meth:`PluginStatus._parse_addon_listing_line`)
    for an addon that is available but not yet installed, so
    :meth:`PluginStatus._show_plugin_details` and the wiki-table thumbnail
    lookup (:meth:`PluginStatus._match_wiki_entry`) can treat it the same
    as an installed/built-in :class:`PluginData`, keeping the upper-right
    thumbnail panel populated consistently regardless of install status.
    Any field the real registry would provide but this remote listing does
    not (readme, fpath, authors, ...) is simply left ``None``/empty.
    """

    def __init__(self, record: dict) -> None:
        """
        :param record: one parsed ``new_addons.txt`` addon record
        """
        self.id = record.get("i")
        self.name = record.get("n", self.id)
        self.description = record.get("d", "")
        self.version = record.get("v", "")
        self.ptype = record.get("t")
        self.fname = record.get("z")
        self.fpath = None
        self.help_url = None
        self.authors = []
        self.authors_email = []
        self.maintainers = []
        self.maintainers_email = []

    def statustext(self) -> str:
        """
        Mimic :meth:`PluginData.statustext` for fault tolerance.

        A ``new_addons.txt`` record carries no stability-status field at
        all, so there's genuinely nothing to report here — but existing
        callers (see :meth:`PluginStatus._show_plugin_details`) call
        ``pdata.statustext()`` unconditionally, the same way they would
        for a real, installed :class:`PluginData`. Providing this avoids
        an ``AttributeError`` there for a not-yet-installed addon.

        :returns: a fixed placeholder, since no real status data exists
                  for a plugin that isn't installed
        """
        return _("Unknown")


def _is_own_plugin_data(pdata: object, own_dir: str) -> bool:
    """
    Decide whether ``pdata`` is this addon's own registry entry.

    Primarily compares this running file's own directory (``own_dir``)
    against the candidate's registered directory (``pdata.fpath``) — the
    same fact Gramps' registry already records and this file already
    displays elsewhere (its "Directory Path" detail line) — rather than
    trusting a separately hand-maintained id/name constant to still
    agree with the ``.gpr.py`` registration after a rename. Falls back
    to matching :data:`OWN_PLUGIN_ID` against ``pdata.id`` only when
    ``pdata.fpath`` is missing/blank (e.g. :class:`_RemotePluginView`
    entries for not-yet-installed addons, which can never be "own").

    :param pdata: a candidate plugin-data object from the registry
    :param own_dir: this file's own directory, as returned by
                     :func:`os.path.realpath` on
                     ``os.path.dirname(__file__)``
    :returns: ``True`` if ``pdata`` looks like this addon's own entry
    """
    fpath = getattr(pdata, "fpath", None)
    if fpath:
        return os.path.normcase(os.path.realpath(fpath)) == os.path.normcase(own_dir)
    return getattr(pdata, "id", None) == OWN_PLUGIN_ID


class PluginStatus(tool.Tool, ManagedWindow):
    """Plugin manager loading controls."""

    def __init__(self, dbstate, uistate, track):
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
        # The "Show" checkboxes must always start fully open (all
        # selected), never remembered from a previous session — this
        # addon's own row (see _select_own_plugin_row) can only be
        # guaranteed visible by default if nothing is pre-filtered out.
        # Unlike self.vpane's position (see _ini_manager, above), these
        # three are therefore deliberately never loaded from — or saved
        # to — any ini file at all; only ever this hard-coded default.
        self.options_dict["show_hidden"] = True
        self.options_dict["show_builtins"] = True
        self.options_dict["show_addons"] = True
        self.window = Gtk.Dialog(title=TITLE)
        # A plain Gtk.Dialog defaults to the DIALOG window-manager type
        # hint, which most window managers decorate with just a Close
        # button — the same hint that made this window disappear from
        # (rather than restore via) the Windows menu before
        # build_menu_names was added, above. NORMAL asks for the same
        # decorations as an ordinary top-level window instead, which is
        # what actually gets a minimize and maximize button shown
        # alongside Close for most desktop environments. This is only a
        # hint, though, not something Gramps/GTK can force: the window
        # manager decides whether to honor it at all, and — like the
        # exact left-to-right button order — has final say over the
        # window's actual decorations, which this addon has no way to
        # query or override further from here.
        self.window.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        # Maximize is meaningless (and typically greyed out or omitted
        # by the window manager) on a window that can't resize; this
        # already defaults to True for a Gtk.Dialog, set explicitly here
        # so that stays true regardless of GTK's own default.
        self.window.set_resizable(True)
        ManagedWindow.__init__(self, uistate, track, self.__class__)
        self.set_window(self.window, None, TITLE, None)
        self._pmgr = GuiPluginManager.get_instance()
        self._preg = PluginRegister.get_instance()
        self._own_pdata = None
        self._addons_file_lock = threading.Lock()
        self.hidden = self._pmgr.get_hidden_plugin_ids()
        self.setup_configs("interface.pluginstatus", 800, 600)

        self._readme_showing: bool = False
        self._current_pid: str | None = None
        self._current_preview_pdata: object | None = None
        self._search_debounce_id: int | None = None
        self._search_debounce_generation = 0
        self._applied_filter_text = ""
        self._wiki_addon_index: dict[str, dict] | None = None
        self._wiki_image_lock = threading.Lock()
        # Active "major type" (plain R_TYPE value) filter, toggled by
        # clicking the Type cell of the already-selected row a second
        # time — see button_press_reg / _apply_filter. None = no filter.
        self._type_filter: str | None = None

        # Tracking dictionaries for async progress bars
        self._active_pbars = {}
        self._project_boxes = {}
        # Refresh is now exposed from the List context menu.  Retain this
        # attribute for the stale-state helper, which becomes a no-op without
        # a dedicated bottom-bar button.
        self._check_updates_btn = None

        # ── Bottom action bar ──────────────────────────────────────────────
        # add_button() requires (label_string, response_id) — two arguments.
        # The placeholder label is immediately replaced by _set_btn_icon_label.
        self._help_btn = self.window.add_button("_Help", Gtk.ResponseType.HELP)
        self.btn_box = self._help_btn.get_parent()
        self.btn_box.set_child_non_homogeneous(self._help_btn, True)
        _set_btn_icon_label(
            self._help_btn, "help-browser", _("_Help"), use_mnemonic=True
        )
        self._help_btn.set_tooltip_text(_("Show the Plugin Manager README"))

        self._count_label = Gtk.Label()
        self._count_label.set_markup("<small>Showing 0 of 0 plug-ins</small>")
        self.btn_box.pack_start(self._count_label, False, False, 4)
        self.btn_box.set_child_non_homogeneous(self._count_label, True)

        self.filter_entry = Gtk.SearchEntry()
        self.filter_entry.set_placeholder_text(_("Search..."))
        self.filter_entry.connect("changed", self._schedule_filter)
        self.filter_entry.connect("icon-press", self._cb_search_icon_press)

        # Shows the active major-type filter (see _type_filter) as a
        # label immediately before the search entry — e.g. "Exporter"
        # ahead of the entry's own magnifying-glass icon — so it's clear
        # only that type is being searched. Hidden when no type filter
        # is active. See _update_search_ui. Wrapped in a Gtk.EventBox
        # (a bare Gtk.Label has no window of its own to deliver button
        # events to) so double-clicking the label itself also clears the
        # filter — the same effect as double-clicking that type's Type
        # cell in the list — see _cb_toggle_type_filter and
        # _cb_type_filter_label_press.
        self._type_filter_label = Gtk.Label()
        self._type_filter_label.set_no_show_all(True)
        self._type_filter_label.set_margin_end(4)

        self._type_filter_label_box = Gtk.EventBox()
        self._type_filter_label_box.set_no_show_all(True)
        self._type_filter_label_box.add(self._type_filter_label)
        self._type_filter_label_box.connect(
            "button-press-event", self._cb_type_filter_label_press
        )

        self._search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self._search_box.pack_start(self._type_filter_label_box, False, False, 0)
        self._search_box.pack_start(self.filter_entry, True, True, 0)
        self.btn_box.pack_start(self._search_box, True, True, 0)
        self._search_box.show()

        cls_btn = self.window.add_button("_Close", Gtk.ResponseType.CLOSE)
        _set_btn_icon_label(cls_btn, "window-close", _("_Close"), use_mnemonic=True)
        self.btn_box.set_child_non_homogeneous(cls_btn, True)
        _w1, dummy = self._help_btn.get_preferred_width()
        _w2, dummy = cls_btn.get_preferred_width()
        _we = 800 - _w1 - _w2 - 60
        self.filter_entry.set_size_request(_we, -1)

        # ── Vertical pane: TOP = two-column info panel, BOTTOM = plugin list ──
        self.vpane = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.vpane.set_position(_ini_manager.get("interface.list-pane-height"))
        self.window.vbox.pack_start(self.vpane, True, True, 0)

        # ── Top pane: horizontal split (info text | thumbnail/status) ──────
        self._info_pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        self._md_pane = _MdInfoPane(uistate)
        self._info_pane.pack1(self._md_pane.widget, resize=True, shrink=False)
        # Adds "Open documentation reader" to this pane's own right-click
        # menu when applicable — see _cb_populate_info_pane_popup. One
        # connection covers both Details and README viewing modes, since
        # they're the same underlying Gtk.TextView either way (only its
        # rendered content differs — see _show_readme/_cursor_changed).
        self._md_pane.textview.connect(
            "populate-popup", self._cb_populate_info_pane_popup
        )

        self._thumb_right_vbox = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=0
        )
        self._thumb_right_vbox.set_size_request(
            _ini_manager.get("interface.preview-pane-width"), -1
        )

        # Normal preview content is Markdown-rendered, just like the Details
        # pane.  The alternate child is used only while repository polling is
        # active, because it contains live progress bars rather than document
        # content.
        self._preview_pane = _MdInfoPane(uistate)
        self._preview_pane.textview.set_left_margin(8)
        self._preview_pane.textview.set_right_margin(8)
        self._preview_pane.textview.set_top_margin(8)
        self._preview_pane.image_max_width = 260
        self._preview_pane.center_images = True
        self._preview_pane.show_image_captions = False
        self._preview_pane.image_adds_newline = False

        self._thumb_sw = Gtk.ScrolledWindow()
        self._thumb_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self._thumb_sw.set_vexpand(True)

        # Container used only for repository-sync progress indicators.
        self._thumb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._thumb_box.set_border_width(8)
        self._thumb_box.set_valign(Gtk.Align.START)
        self._thumb_box.set_halign(Gtk.Align.FILL)
        self._thumb_sw.add(self._thumb_box)
        self._preview_stack = Gtk.Stack()
        self._preview_stack.add_named(self._preview_pane.widget, "preview")
        self._preview_stack.add_named(self._thumb_sw, "progress")
        self._preview_stack.set_visible_child_name("preview")
        self._thumb_right_vbox.pack_start(self._preview_stack, True, True, 0)

        self._info_pane.pack2(self._thumb_right_vbox, resize=False, shrink=False)

        def _set_split(widget, allocation, handler_ref):
            # A Paned's "position" is measured from its own start (left)
            # edge — i.e. it's pack1's ("Details") width, not pack2's
            # ("Preview") — so recovering a *saved* Preview width means
            # computing position as whatever's left of the first real
            # allocation once Preview's width is subtracted back out,
            # rather than setting Preview's width directly.
            preview_width = _ini_manager.get("interface.preview-pane-width")
            widget.set_position(max(0, allocation.width - preview_width))
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

        self._action_btn_box = Gtk.ButtonBox()
        self._action_btn_box.set_layout(Gtk.ButtonBoxStyle.SPREAD)
        self._action_btn_box.set_margin_top(4)
        self._action_btn_box.set_margin_bottom(6)
        self._action_btn_box.set_margin_start(4)
        self._action_btn_box.set_margin_end(4)

        self._hide_btn = Gtk.Button(label=_("Deactivate"))
        self._hide_btn.set_tooltip_text(
            _("Disable the selected plugin until you reactivate it.")
        )
        self._action_btn_box.add(self._hide_btn)
        self._hide_btn.connect("clicked", self.__hide, self._list_reg)

        self._install_btn = Gtk.Button(label=_("Install"))
        self._install_btn.set_tooltip_text(_("Install or update the selected add-on."))
        self._action_btn_box.add(self._install_btn)
        self._install_btn.connect("clicked", self.__install, self._list_reg)

        self._load_btn = Gtk.Button(label=_("Load"))
        self._load_btn.set_tooltip_text(
            _("Load the selected plugin without restarting Gramps.")
        )
        self._load_btn.connect("clicked", self.__load, self._list_reg)
        if __debug__:
            self._action_btn_box.add(self._load_btn)

        self._action_sep = Gtk.Separator.new(Gtk.Orientation.HORIZONTAL)
        self._action_sep.set_margin_top(4)

        self._thumb_right_vbox.pack_end(self._action_sep, False, False, 0)
        self._thumb_right_vbox.pack_end(self._action_btn_box, False, False, 0)

        self._action_btn_box.show_all()
        self._action_btn_box.set_no_show_all(True)
        self._action_sep.set_no_show_all(True)
        self._action_btn_box.hide()
        self._action_sep.hide()

        self.restart_needed = False
        self.window.connect("response", self.done)

        # Show the dialog, but freeze the GDK window's actual on-screen
        # updates immediately afterward, before doing anything else —
        # freeze_updates() only suppresses compositing pixels to the
        # screen; it doesn't affect layout/allocation, so every widget
        # geometry query below (including _select_own_plugin_row's
        # scroll_to_cell) still works normally, just invisibly. Realizing
        # the window first, before populating, also means row content is
        # measured against the dialog's real screen/font context from the
        # start rather than a generic pre-realization one.
        #
        # This replaces an earlier attempt at eliminating the row-height
        # "flash" seen on open — populating before self.show() and
        # draining pending idle events, hoping that would force
        # GtkTreeView's (lazy, idle-time) row-height validation to finish
        # before the first paint. That helped but wasn't reliably
        # complete: the exact timing of that lazy validation isn't fully
        # under this file's control, so anything left outstanding could
        # still surface as a brief flash once the window was actually
        # mapped. Freezing updates sidesteps needing to know that timing
        # at all: nothing at all reaches the screen until explicitly
        # thawed below, once every affected widget has already settled.
        self.show()
        gdk_win = self.window.get_window()
        if gdk_win is not None:
            gdk_win.freeze_updates()
        try:
            # Wait for the toplevel window's real, final size before
            # doing anything else that depends on layout — see
            # _wait_for_stable_window_size for why a simple "wait for
            # any non-zero allocation" isn't actually sufficient here.
            self._wait_for_stable_window_size()

            self.__populate_reg_list()
            # See _force_row_height_recalc: cell row heights for wrapped
            # text (Description especially) get cached against the
            # *first* content they see, and are not automatically
            # recalculated just because a full model's worth of new row
            # data was loaded — only something like this nudge (or the
            # user resizing a column by hand) forces GTK to redo it.
            self._force_row_height_recalc()
            while Gtk.events_pending():
                Gtk.main_iteration()
            self._select_own_plugin_row()
            if len(self._tree_filter):
                self._cursor_changed(None)
            while Gtk.events_pending():
                Gtk.main_iteration()
            # Centering the selection directly here, on open, via
            # _recenter_on_selection() has proven unreliable in
            # practice — even though a sort-column change (which calls
            # that very same method, via _cb_sort_column_changed)
            # reliably centers correctly every time. Rather than keep
            # chasing whatever timing/state difference between those two
            # call sites causes that, drive the exact same,
            # already-proven-correct code path instead: toggle Name's
            # sort order away and back, which fires "sort-column-changed"
            # (and so _cb_sort_column_changed -> _recenter_on_selection)
            # the same way a real header click does. This also means
            # centering-on-open reuses the sort-change centering code
            # rather than duplicating a second, separate attempt at it.
            sortable = self._list_reg.get_model()
            sortable.set_sort_column_id(R_NAME, Gtk.SortType.DESCENDING)
            while Gtk.events_pending():
                Gtk.main_iteration()
            sortable.set_sort_column_id(R_NAME, Gtk.SortType.ASCENDING)
            while Gtk.events_pending():
                Gtk.main_iteration()
        finally:
            if gdk_win is not None:
                gdk_win.thaw_updates()

        # Kick off async network polling for remote repositories — once only.
        # Never triggered from __rebuild_reg_list to avoid an infinite loop.
        if self.options_dict.get("show_available", False):
            addon_projects = config.get("behavior.addons-projects")
            if addon_projects:
                self._initiate_async_polling(addon_projects)

    def build_menu_names(self, obj: object) -> tuple[str, str | None]:
        """
        Return this window's Gramps **Windows** menu label.

        Required by :class:`~gramps.gui.managedwindow.ManagedWindow`
        (see its docstring); left unimplemented, the base class's own
        default of ``("Undefined Menu", "Undefined Submenu")`` is used
        instead, which is what previously showed up as a nested
        "Undefined Submenu ▸ Undefined menu..." entry under **Windows**.
        A ``None`` submenu label, mirroring
        :meth:`gramps.gui.tipofday.TipOfDay.build_menu_names`, lists this
        window directly as a single leaf entry rather than a submenu,
        since this addon never opens further ManagedWindow children of
        its own from within it.

        :param obj: unused — required by the base class's call signature
        :returns: ``(menu_label, None)`` using the same title as this
                  window's own title bar (see :data:`TITLE`)
        """
        return (TITLE, None)

    def _own_plugin_dir(self) -> str:
        """
        Return this addon's own registered directory.

        ``self._own_pdata`` is set as a side effect of
        :meth:`__populate_reg_list`, which walks the full plugin registry
        (``PTYPE_STR`` / ``self._preg.type_plugins``) the same way it
        already does to show each plugin's "Directory Path" — this just
        keeps the entry :func:`_is_own_plugin_data` identifies as this
        addon's own.

        :returns: ``self._own_pdata.fpath`` once the registry traversal in
                  :meth:`__populate_reg_list` has run, otherwise a
                  ``__file__``-based fallback for use before that first
                  traversal completes.
        """
        if self._own_pdata is not None:
            return self._own_pdata.fpath
        return os.path.dirname(os.path.abspath(__file__))

    def _addons_cache_path(self) -> str:
        """
        Return the full path to this addon's cached ``new_addons.txt``.

        :returns: path to ``new_addons.txt`` inside this addon's own
                  registered directory.
        """
        return os.path.join(self._own_plugin_dir(), "media", "new_addons.txt")

    def cb_check_for_updates(self) -> None:
        """
        Manually trigger a fetch of the addon listing (the "Check for
        Updates" button).

        This is the only user-facing way to invoke
        :meth:`_initiate_async_polling` outside of dialog start-up (which
        itself only fires when the ``show_available`` option is set, and
        currently has no UI control that sets it). Re-uses the exact same
        polling machinery, config lookup (``behavior.addons-projects``),
        and cache file as the automatic start-up path.
        """
        if self._active_pbars:
            OkDialog(
                _("Check for Updates"),
                _("A repository check is already in progress."),
                parent=self.window,
            )
            return
        addon_projects = config.get("behavior.addons-projects")
        if not addon_projects:
            OkDialog(
                _("Check for Updates"),
                _(
                    "No addon repositories are enabled. Add or enable one "
                    "under Preferences \u2192 Addons, then try again."
                ),
                parent=self.window,
            )
            return
        LOG.info(
            "PluginManagerPlus: 'Check for Updates' clicked; polling %d " "project(s)",
            len(addon_projects),
        )
        self._initiate_async_polling(addon_projects)

    def _initiate_async_polling(self, addon_projects):
        """Build dynamic stacked layout rows for remote repositories.

        Spawns background network daemon threads, shielding the main thread
        from execution lockups.
        """
        LOG.info(
            "PluginManagerPlus: _initiate_async_polling() called for %d project(s)",
            len(addon_projects) if addon_projects else 0,
        )
        self._preview_stack.set_visible_child_name("progress")
        # Clear any lingering placeholder widgets
        for child in self._thumb_box.get_children():
            self._thumb_box.remove(child)

        # Start each polling batch from a clean cache file so results from
        # a previous session cannot linger next to fresh ones.
        cache_path = self._addons_cache_path()
        LOG.info("PluginManagerPlus: resetting addon cache file at '%s'", cache_path)
        with self._addons_file_lock:
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8"):
                    pass
            except OSError:
                LOG.warning(
                    "Could not reset the addon cache file at '%s'",
                    cache_path,
                    exc_info=True,
                )

        header = Gtk.Label()
        header.set_markup("<b>" + _("Syncing Addon Repositories:") + "</b>")
        header.set_xalign(0.0)
        self._thumb_box.pack_start(header, False, False, 4)

        for proj in addon_projects:
            proj_name = proj[0]
            proj_url = proj[1]
            proj_enabled = proj[2]

            if not proj_enabled:
                continue

            # Stacked two-line structural box setup
            row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row_box.set_margin_bottom(6)

            # Line 1: Long wrapped title text element
            name_label = Gtk.Label()
            name_label.set_markup(f"<small>{markup_escape_text(proj_name)}</small>")
            name_label.set_line_wrap(True)
            name_label.set_xalign(0.0)
            row_box.pack_start(name_label, False, False, 0)

            # Line 2: Slightly indented progress container block
            indent_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            indent_hbox.set_margin_start(12)

            pbar = Gtk.ProgressBar()
            pbar.set_fraction(0.0)
            pbar.set_show_text(True)
            pbar.set_hexpand(True)

            indent_hbox.pack_start(pbar, True, True, 0)
            row_box.pack_start(indent_hbox, False, False, 0)

            self._thumb_box.pack_start(row_box, False, False, 0)

            # Map elements for worker callbacks
            self._active_pbars[proj_url] = pbar
            self._project_boxes[proj_url] = (row_box, indent_hbox)

            # Spawn concurrent fetching daemon thread
            t = threading.Thread(
                target=self._network_worker_thread,
                args=(proj_name, proj_url),
                daemon=True,
            )
            t.start()

        self._thumb_box.show_all()

    def _network_worker_thread(self, name: str, url: str) -> None:
        """
        Background thread: fetch the addon listings for one project.

        Delegates to :func:`gramps.gen.plug.utils.available_updates`,
        which checks the currently configured ``behavior.addons-url`` and
        returns the new/updated addon metadata as an in-memory list — it
        does **not** write anything to disk itself. This method persists
        that list into this addon's own cached ``new_addons.txt`` so
        :meth:`__populate_reg_list` can find it afterwards. Progress is
        approximated with a pulse animation since the exact byte count is
        not available at this level.

        :param name: human-readable project name (used only for logging)
        :param url: the project base URL from ``behavior.addons-projects``
                    (note: :func:`available_updates` does not currently
                    accept a URL argument and always checks the single
                    globally configured ``behavior.addons-url``)
        """
        try:
            # Pulse the bar while work is in progress
            GLib.idle_add(self._update_pbar_pulse, url)

            from gramps.gen.plug.utils import available_updates

            addon_update_list = available_updates()
            self._append_addons_cache(addon_update_list)

            GLib.idle_add(self._finalize_project_safe, url, True, None)
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Addon fetch failed for '%s': %s", name, err)
            GLib.idle_add(self._finalize_project_safe, url, False, str(err))

    def _append_addons_cache(self, addon_update_list: list) -> None:
        """
        Append newly discovered/updated addon metadata to the local cache.

        Thread-safe: guarded by ``self._addons_file_lock`` since several
        background worker threads may call this concurrently.

        :param addon_update_list: the ``(status, download_url, plugin_dict)``
                                   tuples returned by
                                   :func:`gramps.gen.plug.utils.available_updates`
        """
        if not addon_update_list:
            LOG.info(
                "PluginManagerPlus: available_updates() returned no entries; "
                "nothing to write to '%s'",
                self._addons_cache_path(),
            )
            return
        lines = [
            repr(plugin_dict) for (_status, _dl_url, plugin_dict) in addon_update_list
        ]
        cache_path = self._addons_cache_path()
        LOG.info(
            "PluginManagerPlus: writing %d addon entries to '%s'",
            len(lines),
            cache_path,
        )
        with self._addons_file_lock:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "a", encoding="utf-8") as filep:
                filep.write("\n".join(lines) + "\n")

    def _update_pbar_pulse(self, url: str) -> bool:
        """
        Advance the progress bar one pulse step (called via GLib.idle_add).

        Reschedules itself with :func:`GLib.timeout_add` so the bar keeps
        animating while the background thread runs.

        :param url: key into ``self._active_pbars``
        :returns: ``False`` so GLib does not repeat this idle callback
        """
        if url in self._active_pbars:
            self._active_pbars[url].pulse()
            self._active_pbars[url].set_text(_("Downloading…"))
            GLib.timeout_add(200, self._update_pbar_pulse, url)
        return False

    def _finalize_project_safe(
        self, url: str, success: bool, error_message: str | None
    ) -> bool:
        """
        Thread-safe callback invoked when a background fetch completes.

        On success: removes the progress row from the thumbnail panel and
        marks the Update button as stale-resolved (the new_addons.txt on
        disk is now fresh). On failure: replaces the progress bar with a red
        error label. Once every in-flight fetch for this batch has finished
        (``self._active_pbars`` is empty), the visible list is rebuilt so
        the newly-fetched data actually appears.

        :param url: project URL key used in ``self._active_pbars``
        :param success: ``True`` if the fetch completed without exception
        :param error_message: exception text on failure, ``None`` on success
        :returns: ``False`` so GLib does not repeat this idle callback
        """
        if url not in self._project_boxes:
            return False

        row_box, indent_hbox = self._project_boxes[url]
        pbar = self._active_pbars.get(url)

        if success:
            self._thumb_box.remove(row_box)
            self._active_pbars.pop(url, None)
            self._project_boxes.pop(url, None)
            # new_addons.txt is now up to date — reset the stale indicator.
            self._set_update_btn_stale(False)
            self.__update_count_label()
        else:
            if pbar:
                indent_hbox.remove(pbar)
                self._active_pbars.pop(url, None)
            fail_label = Gtk.Label()
            fail_label.set_markup(
                '<span color="red">⚠ %s: %s</span>'
                % (
                    _("Failed"),
                    markup_escape_text(error_message or ""),
                )
            )
            fail_label.set_xalign(0.0)
            fail_label.set_line_wrap(True)
            indent_hbox.pack_start(fail_label, True, True, 0)
            indent_hbox.show_all()

        if not self._active_pbars:
            # This batch is fully done; integrate any freshly-fetched data.
            self.__rebuild_reg_list("0", rescan=False)
            self._preview_stack.set_visible_child_name("preview")
            self._cursor_changed(None)

        return False

    def _selected_plugin_dir(self) -> str | None:
        """
        Return the on-disk directory of the currently selected plugin.

        :returns: the selected row's ``pdata.fpath``, or ``None`` if
                  nothing is selected or the selection has no local
                  registry entry (e.g. a not-yet-installed remote addon).
        """
        model, node = self._selection_reg.get_selected()
        if not node:
            return None
        pid = model.get_value(node, R_ID)
        return self._plugin_dir_for_pid(pid)

    def _plugin_dir_for_pid(self, pid: str | None) -> str | None:
        """
        Return the on-disk directory registered for a given plugin id.

        :param pid: a plugin id, or ``None``
        :returns: ``pdata.fpath``, or ``None`` if ``pid`` is ``None`` or
                  has no local registry entry (e.g. a not-yet-installed
                  remote addon).
        """
        if pid is None:
            return None
        pdata = self._preg.get_plugin(pid)
        if pdata is None or not pdata.fpath:
            return None
        return pdata.fpath

    # Relative paths inside a plugin's own folder, in priority order: the
    # Gramps wiki's ``screenshots/1.png`` convention wins over this
    # addon's own ``media/screenshot.*`` convention.
    _CAPTURE_FILENAMES = (
        os.path.join("screenshots", "1.png"),
        os.path.join("screenshots", "1.webp"),
        os.path.join("media", "screenshot.png"),
        os.path.join("media", "screenshot.webp"),
    )

    def _find_capture_image(self, plugin_dir: str) -> str | None:
        """
        Look for a bundled screenshot inside a plugin's own folder.

        :param plugin_dir: a plugin's own registered directory
        :returns: full path of the first existing file among
                  ``screenshots/1.png``, ``screenshots/1.webp``,
                  ``media/screenshot.png`` and ``media/screenshot.webp``
                  (checked in that order), or ``None`` if none exists
        """
        if not plugin_dir:
            return None
        for rel_path in self._CAPTURE_FILENAMES:
            candidate = os.path.join(plugin_dir, rel_path)
            if os.path.isfile(candidate):
                return candidate
        return None

    def _show_readme(self) -> None:
        """
        Render the selected plugin's own ``README.md``, or a fallback.

        Looks for a plain ``README.md`` inside the currently selected
        plugin's own registered directory — this works for any installed
        addon, not just PluginManagerPlus itself. Falls back to
        ``README_fallback.md`` in this addon's own directory when the
        selection has no local directory (e.g. a not-yet-installed remote
        addon), has no ``README.md`` of its own, or the file cannot be
        read.
        """
        selected_dir = self._selected_plugin_dir()
        md_text = None
        render_dir = selected_dir
        if selected_dir:
            readme_path = os.path.join(selected_dir, "README.md")
            if os.path.isfile(readme_path):
                try:
                    with open(readme_path, "r", encoding="utf-8") as fh:
                        md_text = fh.read()
                except OSError:
                    LOG.debug(
                        "Could not load README.md for the selected plugin",
                        exc_info=True,
                    )

        if md_text is None:
            render_dir = self._own_plugin_dir()
            fallback_path = os.path.join(render_dir, "README_fallback.md")
            try:
                with open(fallback_path, "r", encoding="utf-8") as fh:
                    md_text = fh.read()
            except OSError:
                LOG.debug("Could not load README_fallback.md", exc_info=True)

        if md_text is not None:
            self._md_pane.render(md_text, base_dir=render_dir)

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

    @staticmethod
    def _oversized_image_size(image_path: str) -> int | None:
        """
        Report the size of a preview image if it is too big to thumbnail.

        :param image_path: full path of the candidate preview image
        :returns: the file size in bytes if it exceeds
                  ``_MAX_PREVIEW_IMAGE_BYTES``, otherwise ``None`` (also
                  when the size cannot be read)
        """
        try:
            size = os.path.getsize(image_path)
        except OSError:
            return None
        return size if size > _MAX_PREVIEW_IMAGE_BYTES else None

    def _render_preview(self, pdata: object, image_path: str | None = None) -> None:
        """Render the selected plugin's name, preview, then description.

        MarkdownUtils resolves both ordinary images and ``gramps:icon``
        references, keeping preview styling consistent with the Details pane.
        A bundled capture image always wins over a wiki image supplied by the
        caller.
        """
        plugin_dir = getattr(pdata, "fpath", None)
        capture_path = self._find_capture_image(plugin_dir) if plugin_dir else None
        if capture_path:
            image_path = capture_path
        oversized = self._oversized_image_size(image_path) if image_path else None
        if oversized is not None:
            preview = (
                "![](gramps:icon:dialog-warning:48)\n\n"
                + _(
                    "**Preview image too large** (%(size).1f MB; limit is "
                    "%(limit).0f MB): `%(name)s`"
                )
                % {
                    "size": oversized / (1024 * 1024),
                    "limit": _MAX_PREVIEW_IMAGE_BYTES / (1024 * 1024),
                    "name": os.path.basename(image_path),
                }
            )
        elif image_path:
            preview = "![](%s)" % image_path
        else:
            statustext = getattr(pdata, "statustext", None)
            status = str(statustext() if callable(statustext) else _("Unknown"))
            raw_status = getattr(pdata, "status", None)
            is_stable = raw_status in (0, "stable", "STABLE") or status.casefold() in (
                "stable",
                _("Stable").casefold(),
            )
            icon_name = _STABLE_PREVIEW_ICON if is_stable else _DEVEL_PREVIEW_ICON
            preview = "![](gramps:icon:%s:128)" % icon_name

        self._preview_pane.render(
            "## %s\n%s\n\n%s"
            % (getattr(pdata, "name", ""), preview, getattr(pdata, "description", ""))
        )
        self._preview_stack.set_visible_child_name("preview")

    def _set_update_btn_stale(self, stale: bool) -> None:
        """
        Style the Update button to indicate whether the addon list is current.

        When *stale* is ``True`` (no cached ``new_addons.txt`` found) the
        button label is rendered in bold red so the user knows an update
        would fetch available 3rd-party addons.  Returns to normal styling
        once the fetch completes successfully.

        :param stale: ``True`` to apply the warning style, ``False`` to reset
        """
        if self._check_updates_btn is None:
            return
        child = self._check_updates_btn.get_child()
        # Walk the button's child hierarchy to find the Label widget.
        labels: list[Gtk.Label] = []

        def _collect(widget: Gtk.Widget) -> None:
            if isinstance(widget, Gtk.Label):
                labels.append(widget)
            elif isinstance(widget, Gtk.Container):
                widget.foreach(_collect)

        if child:
            _collect(child)

        for lbl in labels:
            if stale:
                lbl.set_markup('<span color="red"><b>%s</b></span>' % _("Update"))
            else:
                lbl.set_text(_("Update"))
        self._check_updates_btn.set_tooltip_text(
            _(
                "Addon list is out of date — click to fetch the latest list "
                "of available 3rd-party addons"
            )
            if stale
            else _(
                "Fetch the addon listing from each enabled repository in "
                "Preferences \u2192 Addons and refresh new_addons.txt"
            )
        )

    @staticmethod
    def _parse_addon_listing_line(line: str, line_no: int) -> dict | None:
        """
        Defensively parse one line of an addon-listing file into a dict.

        Each line is expected to hold one addon's metadata, either as a
        JSON object or as a Python dict literal (the historical
        ``new_addons.txt`` format, read with
        :func:`gramps.gen.utils.configmanager.safe_eval`). Any line that
        is blank, unparsable, not a dict/object, or missing one of the
        keys this dialog actually depends on (``i`` id, ``n`` name,
        ``d`` description, ``t`` type, ``v`` version, ``z`` download
        filename) is skipped rather than raising: a single bad or
        unrecognized line item must never abort the whole import or
        crash a later lookup with a ``KeyError``.

        :param line: one raw line from the addon-listing file
        :param line_no: 1-based line number, for diagnostic logging only
        :returns: the parsed record, or ``None`` if it should be skipped
        """
        stripped = line.strip()
        if not stripped:
            return None

        record = None
        parse_errors = []
        # Try strict JSON first (the format a future/alternate addon
        # repository might use), then fall back to the legacy Python
        # dict-literal format used by the current new_addons.txt.
        for parser_name, parser in (
            ("json", json.loads),
            ("safe_eval", safe_eval),
        ):
            try:
                record = parser(stripped)
                break
            except Exception as err:  # pylint: disable=broad-except
                parse_errors.append("%s: %s" % (parser_name, err))

        if record is None and not parse_errors:
            # Both parsers "succeeded" with a None/empty result.
            return None
        if not isinstance(record, dict):
            LOG.warning(
                "Skipped addon-listing line %d (not a JSON/dict object): %s",
                line_no,
                stripped[:200],
            )
            return None

        missing = [k for k in _ADDON_RECORD_REQUIRED_KEYS if k not in record]
        if missing:
            LOG.warning(
                "Skipped addon-listing line %d (missing field(s) %s): %s",
                line_no,
                ", ".join(missing),
                stripped[:200],
            )
            return None

        return record

    def __populate_reg_list(self) -> None:
        """
        Build the plugin list from registry data and the cached addon file.
        """
        self.addons = []
        new_addons_file = self._addons_cache_path()
        _addons_stale = not os.path.isfile(new_addons_file)
        LOG.info(
            "PluginManagerPlus: checking for cached addon list at '%s' -> %s",
            new_addons_file,
            "found" if not _addons_stale else "NOT FOUND (stale)",
        )

        self._set_update_btn_stale(_addons_stale)

        skipped = 0
        try:
            with open(new_addons_file, encoding="utf-8") as filep:
                for line_no, line in enumerate(filep, start=1):
                    record = self._parse_addon_listing_line(line, line_no)
                    if record is None:
                        if line.strip():
                            skipped += 1
                        continue
                    self.addons.append(record)
        except FileNotFoundError:
            pass
        except OSError as err:
            LOG.warning("Failed to open addon status file: %s", err)
        if skipped:
            LOG.warning(
                "PluginManagerPlus: skipped %d unrecognized line item(s) in '%s'",
                skipped,
                new_addons_file,
            )

        # Calculate absolute total count across all categories regardless of filters
        total_unfiltered = 0
        for plugin_dict in self.addons:
            if not self._pmgr.get_plugin(plugin_dict["i"]):
                total_unfiltered += 1
        for _type in PTYPE_STR:
            total_unfiltered += len(list(self._preg.type_plugins(_type)))
        self._total_plugins_count = total_unfiltered

        addons = []
        updateable = []
        both_or_neither = self._show_builtins == self._show_addons

        for plugin_dict in self.addons:
            pid = plugin_dict["i"]
            plugin = self._pmgr.get_plugin(pid)
            if plugin:
                if version_str_to_tup(plugin_dict["v"], 3) > version_str_to_tup(
                    plugin.version, 3
                ):
                    updateable.append(pid)
            else:
                hidden = pid in self.hidden
                if hidden:
                    if not (
                        self._show_hidden and (both_or_neither or self._show_addons)
                    ):
                        continue
                elif not self._show_addons:
                    continue
                status_str = _("\u2022Available")
                status = AVAILABLE
                if hidden:
                    status_str = "<s>%s</s>" % status_str
                    status |= HIDDEN
                type_str = PTYPE_STR.get(plugin_dict["t"], _(str(plugin_dict["t"])))
                addons.append(
                    [
                        type_str,
                        status_str,
                        markup_escape_text(plugin_dict["n"]),
                        markup_escape_text(plugin_dict["d"]),
                        plugin_dict["i"],
                        status,
                        # An available-only listing carries no
                        # category/navtypes/namespace detail (that only
                        # exists in the full registration, seen once
                        # installed), so no second Type-column line is
                        # possible here.
                        "<b>%s</b>" % markup_escape_text(type_str),
                        None,
                        type_str,
                        # An available-only listing has no local
                        # directory or help_url either, so neither
                        # indicator icon is possible here.
                        None,
                        None,
                    ]
                )

        fail_list = self._pmgr.get_fail_list()
        own_dir = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
        for _type, typestr in PTYPE_STR.items():
            for pdata in self._preg.type_plugins(_type):
                if _is_own_plugin_data(pdata, own_dir):
                    self._own_pdata = pdata
                hidden = pdata.id in self.hidden
                is_builtin = "gramps/plugins" in pdata.fpath.replace("\\", "/")
                category_active = (
                    self._show_builtins if is_builtin else self._show_addons
                )
                if hidden:
                    if not (self._show_hidden and (both_or_neither or category_active)):
                        continue
                elif not category_active:
                    continue
                status_str = _("Built-in") if is_builtin else _("\u2022Installed")
                status = BUILTIN if is_builtin else INSTALLED
                for i in fail_list:
                    if pdata == i[2]:
                        status_str += ", " + '<span color="red">%s</span>' % _("Failed")
                        break
                if pdata.id in updateable:
                    status_str += ", " + _("Update Available")
                    status |= UPDATE
                if hidden:
                    status_str = "<s>%s</s>" % status_str
                    status |= HIDDEN

                type_display = "<b>%s</b>" % markup_escape_text(typestr)
                type_icons_pixbuf = None
                type_sort_extra = ""
                if pdata.ptype in (GRAMPLET, RULE):
                    if pdata.ptype == GRAMPLET:
                        canon = _canonical_navtypes(getattr(pdata, "navtypes", None))
                    else:
                        # A Rule has a single `namespace` (e.g. 'Person'),
                        # not a navtypes list — reuse the same alias
                        # table/canonical ordering via a one-item list.
                        canon = _canonical_navtypes([getattr(pdata, "namespace", None)])
                    if canon:
                        icon_names = [
                            icon
                            for key, _label, icon in _GRAMPLET_VIEW_ICONS
                            if key in canon
                        ]
                        type_icons_pixbuf = _compose_icon_strip(icon_names)
                        labels = [
                            label
                            for key, label, _icon in _GRAMPLET_VIEW_ICONS
                            if key in canon
                        ]
                        type_sort_extra = ", ".join(labels)
                elif pdata.ptype == VIEW:
                    # A View's own `category` is a (codename, translated
                    # label) pair, e.g. ("People", _("People")). The
                    # icon strip here can hold up to *two* icons, left to
                    # right: the generic category icon, then the View's
                    # own distinct mode icon within that category.
                    #
                    # The category icon is resolved with exactly the
                    # same three-step lookup Gramps' own sidebar
                    # (gramps.gui.navigator.Navigator) uses — see
                    # navigator.py's CATEGORY_ICON.get(...) /
                    # stock_category_icon fallback: first CATEGORY_ICON
                    # (Gramps' own public dict of its built-in category
                    # codenames — "People", "Ancestry", etc. — to a
                    # generic icon), then, if the codename isn't in
                    # there, the plugin's own registered
                    # `stock_category_icon` (an addon's way of supplying
                    # a generic icon for its own custom category, e.g. a
                    # "Tags" category — unset by CardView's
                    # card_view.gpr.py, so its Tag Card view has no
                    # category icon here, matching what Gramps' own
                    # sidebar would also show for it). No hand-maintained
                    # copy of Gramps' category-icon table is needed here.
                    #
                    # The mode icon is the View's own registered
                    # `stock_icon`, e.g. CardView's "gramps-personcard"
                    # (the same icon Gramps' sidebar shows on that
                    # category's per-mode toolbar button). Both values
                    # are read straight off the plugin registry, so no
                    # View plugin ever needs to be loaded/instantiated
                    # just to discover its icon(s).
                    category = getattr(pdata, "category", None)
                    cat_code = (
                        category[0]
                        if isinstance(category, (tuple, list)) and category
                        else category
                    )
                    category_icon_name = (
                        CATEGORY_ICON.get(cat_code) if cat_code else None
                    )
                    if category_icon_name is None:
                        category_icon_name = getattr(pdata, "stock_category_icon", None)
                    if (
                        category_icon_name is None
                        and isinstance(category, (tuple, list))
                        and len(category) > 1
                        and category[1]
                    ):
                        # Category not one of Gramps' own recognised
                        # codenames, and this View's own .gpr.py doesn't
                        # supply a stock_category_icon override either —
                        # fall back to its translated label as plain text
                        # (same fallback shape as the Tool/Report case,
                        # below) rather than showing nothing. This is a
                        # deliberate diagnostic: it flags a View whose
                        # category has no icon Gramps itself would show
                        # either — e.g. CardView's "Tags" — rather than
                        # silently hiding that it's unrecognised.
                        label = str(category[1])
                        type_display += "\n  " + markup_escape_text(label)

                    # Sort/group by the category's own translated label
                    # regardless of whether an icon was found for it.
                    if isinstance(category, (tuple, list)) and len(category) > 1:
                        type_sort_extra = str(category[1] or "")

                    mode_icon_name = getattr(pdata, "stock_icon", None)
                    # De-duplicated, order-preserving: a View whose own
                    # mode icon happens to match its category icon (e.g.
                    # pedigreeview registers stock_icon="gramps-pedigree",
                    # identical to the Charts/"Ancestry" category icon)
                    # shows that icon once, not twice.
                    icon_names = list(
                        dict.fromkeys(
                            name
                            for name in (category_icon_name, mode_icon_name)
                            if name
                        )
                    )
                    if icon_names:
                        type_icons_pixbuf = _compose_icon_strip(icon_names)
                else:
                    subcat = _subcategory_label(
                        pdata.ptype, getattr(pdata, "category", None)
                    )
                    if subcat:
                        type_display += "\n  " + markup_escape_text(subcat)
                        type_sort_extra = subcat

                # "\x01" sorts before any printable character, so a row
                # with no second-line detail (type_sort_extra == "") sorts
                # first within its type, ahead of rows that have one.
                type_sort_key = typestr + "\x01" + type_sort_extra

                readme_icon = None
                if pdata.fpath and os.path.isfile(
                    os.path.join(pdata.fpath, "README.md")
                ):
                    readme_icon = _load_named_icon_pixbuf(
                        "document-page-setup", _INDICATOR_ICON_SIZE
                    )
                help_icon = None
                if getattr(pdata, "help_url", None):
                    help_icon = _load_named_icon_pixbuf(
                        "web-browser", _INDICATOR_ICON_SIZE
                    )

                addons.append(
                    [
                        typestr,
                        status_str,
                        markup_escape_text(pdata.name),
                        markup_escape_text(pdata.description),
                        pdata.id,
                        status,
                        type_display,
                        type_icons_pixbuf,
                        type_sort_key,
                        readme_icon,
                        help_icon,
                    ]
                )

        for row in sorted(addons, key=itemgetter(R_TYPE_SORT, R_NAME)):
            self._model_reg.append(row)

        if self._own_pdata is None:
            # Diagnostic aid: if this ever fires, _select_own_plugin_row
            # will fall back to selecting row 0 instead of this addon's
            # own row. Logs every candidate directory actually seen, next
            # to what this file resolved its own directory to, so a
            # mismatch (e.g. a symlinked/relocated addons folder) can be
            # read straight out of the log instead of guessed at.
            LOG.warning(
                "PluginManagerPlus: could not find own registry entry "
                "(own_dir=%r); candidate fpaths seen: %r",
                own_dir,
                sorted(
                    {
                        os.path.realpath(pdata.fpath)
                        for pdata in (
                            p for t in PTYPE_STR for p in self._preg.type_plugins(t)
                        )
                        if getattr(pdata, "fpath", None)
                    }
                ),
            )

        self.__update_count_label()

    def __update_count_label(self) -> None:
        """
        Refresh the "Showing N of M plug-ins" status label using the absolute Total.

        The active major-type filter (see :attr:`_type_filter`), if any,
        is shown in the search field itself (see :meth:`_update_search_ui`)
        rather than here.
        """
        if not hasattr(self, "_tree_filter") or not hasattr(self, "_model_reg"):
            return
        visible = len(self._tree_filter)
        total = getattr(self, "_total_plugins_count", len(self._model_reg))
        self._count_label.set_markup(
            "<small>"
            + _("Showing %(vis)d of %(tot)d plugins") % {"vis": visible, "tot": total}
            + "</small>"
        )

    def _row_path_for_pid(self, pid: str | None) -> "Gtk.TreePath | None":
        """
        Find the currently-visible :class:`Gtk.TreePath` for a plugin id.

        Converts a row's path in ``self._model_reg`` (the base
        :class:`Gtk.ListStore`) through the filter model
        (``self._tree_filter``) and then the sort model
        (``self._list_reg.get_model()``) that sit between it and the
        visible :class:`Gtk.TreeView`.

        :param pid: the plugin id to locate, or ``None``
        :returns: the visible path, or ``None`` if ``pid`` is ``None``,
                  not found, or currently filtered out (not visible)
        """
        if pid is None:
            return None
        for row in self._model_reg:
            if row[R_ID] == pid:
                filter_path = self._tree_filter.convert_child_path_to_path(row.path)
                if filter_path is None:
                    return None  # currently filtered out / not visible
                sort_model = self._list_reg.get_model()
                return sort_model.convert_child_path_to_path(filter_path)
        return None

    def _select_own_plugin_row(self) -> None:
        """
        Select and center this addon's own row in the plugin list.

        Falls back to the first row if this addon's own entry cannot be
        found (see :func:`_is_own_plugin_data` — should not normally
        happen; if it does, :meth:`__populate_reg_list` logs a
        diagnostic warning) or is currently filtered out.
        """
        pid = self._own_pdata.id if self._own_pdata else None
        path = self._row_path_for_pid(pid) or Gtk.TreePath.new_from_string("0")
        self._selection_reg.select_path(path)
        self._recenter_on_selection()

    def _recenter_on_selection(self) -> None:
        """
        Center whatever row is currently selected, deferred to idle.

        Shared by :meth:`_select_own_plugin_row` (on open) and
        :meth:`_cb_sort_column_changed` (after the user changes the sort
        column/order) — both need exactly the same "once any pending
        reorder/layout has actually settled, center on whatever the
        selection turns out to be" behavior, so this is the one place
        that does it. A no-op if nothing is currently selected.

        The row is looked up fresh *inside* the deferred callback, not
        before scheduling it — capturing it up front and only deferring
        the ``scroll_to_cell`` call itself will silently center on the
        wrong row once a pending sort/reorder finishes, since the
        already-captured path would point at whatever ends up at that
        stale index rather than at the actual selected row.
        """

        def _recenter() -> bool:
            model, row_iter = self._selection_reg.get_selected()
            if row_iter is not None:
                path = model.get_path(row_iter)
                self._list_reg.scroll_to_cell(path, None, True, 0.5, 0)
            return False

        GLib.idle_add(_recenter)

    def _force_row_height_recalc(self) -> None:
        """
        Work around a well-known GtkTreeView row-height caching quirk.

        Row heights for cells with wrapped text (Type, Name, Description,
        Status here — see their FIXED-sizing column setup, above) are
        computed once and cached; unlike column *width*, they are not
        automatically recalculated just because a full set of new row
        data was loaded, even though the columns themselves are already
        correctly sized from the very first paint. In practice this
        mostly shows up on Description, whose text is long enough to
        regularly need more lines than whatever got cached — visibly
        cropped until something else forces GTK to redo the
        calculation. A user manually resizing a column is one such
        trigger (this is where "resizing the column corrects it" comes
        from); nudging a column's own fixed width by 1px and back,
        programmatically, is another — a known, if inelegant, workaround
        (see https://discourse.gnome.org/t/treeview-word-wrapping-and-row-height/590,
        a GTK maintainer confirming there's no native fix). Called after
        (re)populating the model, while every affected column already
        has real row content to measure against.
        """
        for column in (
            self._col_type,
            self._col_name,
            self._col_desc,
            self._col_status,
        ):
            width = column.get_fixed_width()
            column.set_fixed_width(width + 1)
            column.set_fixed_width(width)

    def _cb_desc_column_resized(
        self, column: Gtk.TreeViewColumn, _param: object
    ) -> None:
        """
        Keep the Description column's text wrapping in sync with its
        actual on-screen width.

        Fires on the Description TreeViewColumn's "notify::width"
        signal — i.e. whenever its real allocated width changes for
        any reason (the dialog being resized, set_expand(True)
        redistributing space after some other column is dragged, or
        the user dragging this column directly). Without this, the
        CellRendererText's "wrap-width" stays fixed at whatever it was
        given at construction time (_DESC_COL_MIN_WIDTH), so widening
        the column would just leave blank space instead of letting
        the text reflow into it.

        Two things this deliberately avoids, both previously wrong
        here:

        1. Setting "wrap-width" to the column's full width lets the
           cell's own padding (CellRendererText's "xpad" on both
           sides, plus a small safety margin for the focus-rectangle
           GTK draws around the selected row's cell) push the
           rendered text past the column's right edge — visible as
           text bleeding into the next column. _DESC_WRAP_SAFETY_PX
           and the renderer's own "xpad" are subtracted back out here
           so the wrapped text actually stays inside the column.
        2. The row-height cache still needs the same 1px-nudge
           workaround _force_row_height_recalc uses elsewhere in this
           file (GTK doesn't recompute a row's cached height just
           because wrap-width changed) — but nudging *this* column's
           own fixed-width would be self-defeating: with
           set_expand(True), a FIXED-sizing column's rendered width is
           its fixed-width property PLUS a share of whatever surplus
           space is left over, so writing the column's current grown
           width back into its own fixed-width permanently raises
           that baseline. The column would then never shrink below
           whatever width it last happened to reach — exactly the
           "grows on window-expand, never shrinks back on
           window-shrink" bug this replaced. Nudging any other,
           non-expanding column instead (self._col_status, here)
           still invalidates the same TreeView-wide row-height cache
           without touching Description's own baseline at all.

        :param column: the Description TreeViewColumn (self._col_desc)
        :param _param: unused (the GParamSpec for "width")
        """
        new_width = column.get_width()
        if new_width <= 0 or new_width == self._desc_last_width:
            return
        self._desc_last_width = new_width
        xpad = self._desc_renderer.get_property("xpad")
        wrap_width = max(new_width - (2 * xpad) - _DESC_WRAP_SAFETY_PX, 1)
        self._desc_renderer.set_property("wrap-width", wrap_width)
        status_width = self._col_status.get_fixed_width()
        self._col_status.set_fixed_width(status_width + 1)
        self._col_status.set_fixed_width(status_width)

    def _wait_for_stable_window_size(
        self, timeout_seconds: float = 2.0, stable_rounds: int = 3
    ) -> None:
        """
        Block-pump the main loop until self.window's allocation stabilizes.

        The root cause behind centering-on-open being unreliable turned
        out to be exactly here: this dialog's real, final size can
        depend on an asynchronous configure/map round-trip to the
        window manager, and how quickly that round-trip resolves
        empirically varies enough (observed correlating with whether
        PluginManagerPlus.ini already existed — larger, previously-saved
        pane/column sizes vs. this addon's smaller built-in defaults —
        though the ini file itself isn't actually the cause; it's
        incidental to the resulting window geometry) that a fixed
        "drain whatever's already pending, then proceed" pass can finish
        while the window still only has an early, provisional allocation
        rather than its true final one. Any centering math run against
        that provisional size will be wrong, even though every step
        after it appears to run without error.

        Unlike ``while Gtk.events_pending(): Gtk.main_iteration()``
        (non-blocking — only drains events that have *already* arrived),
        this uses the *blocking* form of ``Gtk.main_iteration()``, so it
        genuinely waits for further events (including a delayed WM
        response) rather than giving up the instant nothing happens to
        be queued yet. "Stable" here means the window's allocated size
        read the same on ``stable_rounds`` consecutive checks, each
        separated by waiting for (and draining) at least one more
        event — not just the first time it happens to be non-zero, which
        a too-early provisional allocation could also satisfy. Bounded
        by a wall-clock timeout so an unusual/misbehaving window manager
        can never hang Gramps outright.

        :param timeout_seconds: maximum wall-clock time to wait
        :param stable_rounds: how many consecutive matching reads count
                               as "stable"
        """
        deadline = time.monotonic() + timeout_seconds
        last_size = None
        stable = 0
        while time.monotonic() < deadline:
            while Gtk.events_pending():
                Gtk.main_iteration()
            size = (
                self.window.get_allocated_width(),
                self.window.get_allocated_height(),
            )
            if size == last_size and size[0] > 0 and size[1] > 0:
                stable += 1
                if stable >= stable_rounds:
                    return
            else:
                stable = 0
            last_size = size
            # Block for the next event (e.g. a delayed WM configure)
            # rather than spinning — nothing left pending right now
            # doesn't mean nothing more is coming.
            Gtk.main_iteration()

    def _collect_plugin_debug_info(self) -> dict:
        """
        Gather every known field for every plugin the registry/cache knows.

        Re-uses the exact same data sources as :meth:`__populate_reg_list`:
        ``self._preg`` (installed/built-in plug-ins, walked by
        ``PTYPE_STR`` category, the same way that produces "Directory
        Path" for the details panel) and ``self.addons`` (remote entries
        parsed from the cached ``new_addons.txt``). No separate scan or
        network access is performed here.

        :returns: a dict with two keys: ``"registered"`` — one entry per
                  locally-known :class:`PluginData`, covering every
                  attribute the registry exposes — and ``"remote_only"``
                  — the raw dictionaries read from ``new_addons.txt`` for
                  addons that are not (yet) installed locally.
        """
        fail_ids = {getattr(i[2], "id", None) for i in self._pmgr.get_fail_list()} - {
            None
        }
        registered: list[dict] = []
        for _type, typestr in PTYPE_STR.items():
            for pdata in self._preg.type_plugins(_type):
                registered.append(
                    {
                        "id": pdata.id,
                        "ptype": typestr,
                        "name": pdata.name,
                        "name_accell": getattr(pdata, "name_accell", None),
                        "description": pdata.description,
                        "version": pdata.version,
                        "status": pdata.statustext(),
                        # Raw `category` attribute as registered in the
                        # plugin's .gpr.py — e.g. a Tool's Isotammi-style
                        # custom sub-category string, a Report's
                        # CATEGORY_* constant, or a View's (codename,
                        # translated label) tuple — plus, for Tools and
                        # Reports, the resolved translated sub-category
                        # label (see _subcategory_label) that also
                        # appears as the List panel's Type-column second
                        # line and in the Details panel.
                        "category": getattr(pdata, "category", None),
                        "category_label": _subcategory_label(
                            pdata.ptype, getattr(pdata, "category", None)
                        ),
                        # View-only icon attributes (None for every other
                        # ptype) — see the VIEW branch of
                        # __populate_reg_list for how these two, plus
                        # CATEGORY_ICON (imported from
                        # gramps.gui.navigator, not addon-registered so
                        # not exported here), combine into the List
                        # panel's Type-column icon strip.
                        "stock_icon": getattr(pdata, "stock_icon", None),
                        "stock_category_icon": getattr(
                            pdata, "stock_category_icon", None
                        ),
                        "fname": pdata.fname,
                        "fpath": pdata.fpath,
                        "gramps_target_version": getattr(
                            pdata, "gramps_target_version", None
                        ),
                        "authors": list(getattr(pdata, "authors", []) or []),
                        "authors_email": list(
                            getattr(pdata, "authors_email", []) or []
                        ),
                        "maintainers": list(getattr(pdata, "maintainers", []) or []),
                        "maintainers_email": list(
                            getattr(pdata, "maintainers_email", []) or []
                        ),
                        "help_url": getattr(pdata, "help_url", None),
                        "include_in_listing": getattr(
                            pdata, "include_in_listing", None
                        ),
                        "load_on_reg": getattr(pdata, "load_on_reg", None),
                        "supported": getattr(pdata, "supported", None),
                        "depends_on": list(getattr(pdata, "depends_on", []) or []),
                        "icons": list(getattr(pdata, "icons", []) or []),
                        "icondir": getattr(pdata, "icondir", None),
                        "is_builtin": "gramps/plugins"
                        in pdata.fpath.replace("\\", "/"),
                        "is_hidden": pdata.id in self.hidden,
                        "is_failed": pdata.id in fail_ids,
                    }
                )
        return {
            "registered": registered,
            "remote_only": list(self.addons),
        }

    def cb_export_plugin_list(self) -> None:
        """
        Write every known field for the currently filtered plugins to JSON.

        Invoked from the List panel's context menu. The export is placed
        alongside this addon's own ``new_addons.txt`` cache (via
        :meth:`_own_plugin_dir`), and its linked path opens that folder.
        """
        visible_ids: set[str] = set()

        def _collect_visible_id(model, _path, tree_iter, _data) -> bool:
            visible_ids.add(model.get_value(tree_iter, R_ID))
            return False

        # The TreeView model is the filtered/sorted model, so foreach here
        # sees exactly the rows currently visible in the List panel.
        self._list_reg.get_model().foreach(_collect_visible_id, None)

        all_info = self._collect_plugin_debug_info()
        debug_info = {
            "registered": [
                entry for entry in all_info["registered"] if entry["id"] in visible_ids
            ],
            "remote_only": [
                entry
                for entry in all_info["remote_only"]
                if entry.get("i") in visible_ids
            ],
        }
        export_path = os.path.join(self._own_plugin_dir(), "plugin_debug_export.json")
        try:
            with open(export_path, "w", encoding="utf-8") as filep:
                json.dump(debug_info, filep, indent=2, default=str, sort_keys=True)
        except OSError as err:
            LOG.warning("Could not write plugin debug export: %s", err)
            OkDialog(
                _("Export Plugin List"),
                _("Could not write the export file:\n%s") % err,
                parent=self.window,
            )
            return
        LOG.info(
            "PluginManagerPlus: exported %d filtered registered and %d "
            "filtered remote-only plugin entries to '%s'",
            len(debug_info["registered"]),
            len(debug_info["remote_only"]),
            export_path,
        )
        folder_uri = Gio.File.new_for_path(os.path.dirname(export_path)).get_uri()
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=_("Export Plugin List"),
        )
        dialog.format_secondary_markup(
            _("Wrote %(registered)d registered and %(remote)d remote-only")
            % {
                "registered": len(debug_info["registered"]),
                "remote": len(debug_info["remote_only"]),
            }
            + _(' filtered plugin entries to:\n<a href="%(uri)s">%(path)s</a>')
            % {
                "uri": markup_escape_text(folder_uri),
                "path": markup_escape_text(export_path),
            }
        )
        dialog.run()
        dialog.destroy()

    def registered_plugins_panel(self, obj: object | None) -> tuple[str, Gtk.Widget]:
        """
        Build and return the plugin-list TreeView widget.

        :returns: tuple of (panel title string, container widget)
        """
        self._list_reg = Gtk.TreeView()
        self._list_reg.set_headers_visible(True)
        self._list_reg.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

        # model columns: type-str, status-markup, name-markup,
        #                description-markup, plugin-id, status-int,
        #                type-display-markup, type-view-icons-pixbuf,
        #                type-sort-key, has-readme-icon-pixbuf,
        #                has-help-icon-pixbuf
        self._model_reg = Gtk.ListStore(
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            GObject.TYPE_STRING,
            int,
            GObject.TYPE_STRING,
            GdkPixbuf.Pixbuf,
            GObject.TYPE_STRING,
            GdkPixbuf.Pixbuf,
            GdkPixbuf.Pixbuf,
        )
        self._selection_reg = self._list_reg.get_selection()

        # filter + sortable wrapper
        self._tree_filter = self._model_reg.filter_new()
        self._tree_filter.set_visible_func(self._apply_filter)
        self._list_reg.set_model(Gtk.TreeModelSort(model=self._tree_filter))
        # Clicking the Type header groups by R_TYPE_SORT (type name +
        # sub-category/navtypes detail), always sub-sorted by Name — a
        # plain set_sort_column_id only supports one key, so this needs a
        # custom compare function.
        self._list_reg.get_model().set_sort_func(R_TYPE_SORT, self._cb_type_sort, None)
        # The Notes/Source indicator columns hold a GdkPixbuf-or-None,
        # which Gtk can't compare directly — sort by presence of the
        # icon instead (rows with it first), then by Name.
        self._list_reg.get_model().set_sort_func(
            R_HAS_README, self._cb_indicator_sort, R_HAS_README
        )
        self._list_reg.get_model().set_sort_func(
            R_HAS_HELP, self._cb_indicator_sort, R_HAS_HELP
        )
        # Column headers' set_sort_column_id (below, on each
        # TreeViewColumn) only wires up *clicking* a header to sort by
        # it — it doesn't make any sort active. Explicitly activate Name
        # ascending as the initial sort here, on the model itself, so
        # the list opens name-sorted (with the Name header's sort arrow
        # shown) rather than in whatever order rows happened to be
        # appended in.
        self._list_reg.get_model().set_sort_column_id(R_NAME, Gtk.SortType.ASCENDING)
        # Sorting reorders every row's path, including the currently
        # selected one — re-center on it (same as _select_own_plugin_row
        # does on open) whenever the user changes the sort column/order
        # by clicking a header, so the selection doesn't end up scrolled
        # out of view. Deferred to idle so it runs after GTK has actually
        # finished reordering the rows for the new sort, rather than
        # possibly racing it.
        self._list_reg.get_model().connect(
            "sort-column-changed", self._cb_sort_column_changed
        )

        self._list_reg.connect("button-press-event", self.button_press_reg)
        self._list_reg.set_has_tooltip(True)
        self._list_reg.connect("query-tooltip", self._cb_list_tooltip)
        self._cursor_hndlr = self._selection_reg.connect(
            "changed", self._cursor_changed
        )

        # Status is pinned as the leftmost column so it stays visible
        # without needing to scroll right, ahead of the higher-detail
        # columns (Type, Name, the two indicator icons, Description).
        _status_col_width = _ini_manager.get("spacing.status-column-width")
        status_renderer = Gtk.CellRendererText(
            wrap_mode=2, wrap_width=_status_col_width
        )
        status_renderer.set_alignment(0.0, 0.0)  # top-align; see name_renderer
        col1 = Gtk.TreeViewColumn(
            cell_renderer=status_renderer,
            markup=R_STAT_S,
        )
        lbl1 = Gtk.Label(label=_("Status"))
        lbl1.show()
        lbl1.set_tooltip_markup(
            _(
                "'*' addon plug-ins are supplied by 3rd party authors,\n"
                "<s>strikeout</s> plug-ins are hidden"
            )
        )
        col1.set_widget(lbl1)
        col1.set_resizable(True)
        # 108px default (20% wider than the original 90px; still
        # user-resizable, and whatever width the user drags it to is
        # persisted — see "spacing.status-column-width" in
        # _ini_manager).
        col1.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col1.set_fixed_width(_status_col_width)
        col1.set_sort_column_id(R_STAT_S)
        self._list_reg.append_column(col1)
        self._col_status = col1

        # Custom vertical CellArea so the Type column can stack a second
        # line under the type name: either a Tool/Report sub-category
        # label (plain text, baked into R_TYPE_DISPLAY's markup) or a
        # Gramplet/Rule view-restriction icon strip (R_TYPE_ICONS, a
        # single composited pixbuf — see _compose_icon_strip). A row with
        # neither renders the pixbuf renderer at ~zero height, so it's
        # invisible without needing a per-row visibility cell-data-func.
        type_area = Gtk.CellAreaBox()
        type_area.set_orientation(Gtk.Orientation.VERTICAL)
        col0 = Gtk.TreeViewColumn.new_with_area(type_area)
        col0.set_title(_("Type"))
        _type_col_width = _ini_manager.get("spacing.type-column-width")
        type_text_renderer = Gtk.CellRendererText(
            wrap_mode=2, wrap_width=_type_col_width
        )
        type_text_renderer.set_alignment(0.0, 0.0)
        col0.pack_start(type_text_renderer, True)
        col0.add_attribute(type_text_renderer, "markup", R_TYPE_DISPLAY)
        type_icons_renderer = Gtk.CellRendererPixbuf()
        # Left-align and indent to roughly match the "\n  " (2-space)
        # indent used for the Tool/Report sub-category text line, instead
        # of GtkCellAreaBox's default centered alignment — keeps both
        # kinds of second line visually flush with each other.
        type_icons_renderer.set_alignment(0.0, 0.5)
        type_icons_renderer.set_padding(_TYPE_ICON_INDENT_PX, 0)
        col0.pack_start(type_icons_renderer, False)
        col0.add_attribute(type_icons_renderer, "pixbuf", R_TYPE_ICONS)
        col0.set_sort_column_id(R_TYPE_SORT)
        col0.set_resizable(True)
        # FIXED sizing (rather than the GTK default GROW_ONLY/AUTOSIZE)
        # gives this column a known width immediately, on the very first
        # layout pass — AUTOSIZE instead needs to measure every row's
        # content across the whole model to determine its natural width,
        # and that measurement can settle a frame or two after the
        # dialog's first paint. Until it does, this column's width (and
        # so how much width is left for Description, which wraps within
        # whatever width it's actually given) is provisional, and a
        # late correction is exactly what produces a visible "rows were
        # short, then grew" row-height flash on open. Still
        # user-resizable, exactly as before — see "spacing.*-column-width"
        # in _ini_manager, which persists whatever width the user drags
        # each column to.
        col0.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col0.set_fixed_width(_type_col_width)
        self._list_reg.append_column(col0)
        # Referenced by button_press_reg to detect clicks specifically in
        # the Type column, for the click-to-filter-by-major-type feature.
        self._col_type = col0

        _name_col_width = _ini_manager.get("spacing.name-column-width")
        name_renderer = Gtk.CellRendererText(wrap_mode=2, wrap_width=_name_col_width)
        # Top-align (rather than the default vertical-center) so Name
        # lines up with the top of the row instead of floating in the
        # middle whenever a taller neighboring cell (wrapped Type or
        # Description) makes the row taller than Name's own content
        # needs — same reasoning as type_text_renderer's alignment,
        # above.
        name_renderer.set_alignment(0.0, 0.0)
        col2 = Gtk.TreeViewColumn(
            title=_("Name"),
            cell_renderer=name_renderer,
            markup=R_NAME,
        )
        col2.set_sort_column_id(R_NAME)
        col2.set_resizable(True)
        # 50% wider than the original ~150px default (still user-resizable,
        # and whatever width the user drags it to is persisted — see
        # "spacing.name-column-width" in _ini_manager).
        col2.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col2.set_fixed_width(_name_col_width)
        self._list_reg.append_column(col2)
        self._col_name = col2

        # Notes indicator: a 24px icon if the plugin has its own
        # README.md, blank otherwise. Double-click selects the row and
        # shows the README, same as clicking the Help button.
        readme_renderer = Gtk.CellRendererPixbuf()
        # Top-align for the same reason as name_renderer, above — a
        # 16px icon otherwise floats vertically centered in a much
        # taller wrapped row.
        readme_renderer.set_alignment(0.5, 0.0)
        col_readme = Gtk.TreeViewColumn(
            cell_renderer=readme_renderer,
            pixbuf=R_HAS_README,
        )
        lbl_readme = Gtk.Image.new_from_icon_name(
            "document-page-setup", Gtk.IconSize.MENU
        )
        lbl_readme.set_pixel_size(16)
        lbl_readme.show()
        lbl_readme.set_tooltip_text(
            _("Has its own README.md — double-click to view it")
        )
        col_readme.set_widget(lbl_readme)
        col_readme.set_resizable(False)
        col_readme.set_sort_column_id(R_HAS_README)
        self._list_reg.append_column(col_readme)
        self._col_readme = col_readme

        # web-browser/help indicator: a 24px icon if the plugin has a
        # help_url, blank otherwise. Double-click selects the row and
        # opens the help link, same as clicking the "Help:" link.
        help_renderer = Gtk.CellRendererPixbuf()
        help_renderer.set_alignment(0.5, 0.0)  # top-align; see readme_renderer
        col_help = Gtk.TreeViewColumn(
            cell_renderer=help_renderer,
            pixbuf=R_HAS_HELP,
        )
        lbl_help = Gtk.Image.new_from_icon_name("web-browser", Gtk.IconSize.MENU)
        lbl_help.set_pixel_size(16)
        lbl_help.show()
        lbl_help.set_tooltip_text(
            _("Has a help_url — double-click to open the help link")
        )
        col_help.set_widget(lbl_help)
        col_help.set_resizable(False)
        col_help.set_sort_column_id(R_HAS_HELP)
        self._list_reg.append_column(col_help)
        self._col_help = col_help

        _desc_col_width = _DESC_COL_MIN_WIDTH
        # Kept as its own reference (rather than an anonymous renderer
        # passed straight to the TreeViewColumn constructor, as the
        # other columns do) so _cb_desc_column_resized can update its
        # "wrap-width" property live as the column's actual on-screen
        # width changes — see that method.
        self._desc_renderer = Gtk.CellRendererText(
            wrap_mode=2, wrap_width=_desc_col_width
        )
        self._desc_renderer.set_alignment(0.0, 0.0)  # top-align; see name_renderer
        col3 = Gtk.TreeViewColumn(
            title=_("Description"),
            cell_renderer=self._desc_renderer,
            markup=R_DESC,
        )
        col3.set_sort_column_id(R_DESC)
        col3.set_resizable(True)
        # Same reasoning as col0 (Type), above: FIXED sizing avoids a
        # deferred, model-wide natural-width measurement that could
        # settle after the first paint and retroactively change how
        # many lines this column's wrapped text needs. set_expand(True)
        # keeps its previous fill-remaining-space behavior: whatever
        # width the dialog's current size actually leaves over after
        # the other (persisted, user-resizable) columns is what this
        # column gets, recalculated on every resize rather than
        # reloaded from a stale saved value — see _DESC_COL_MIN_WIDTH.
        col3.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col3.set_fixed_width(_desc_col_width)
        col3.set_expand(True)
        self._list_reg.append_column(col3)
        self._col_desc = col3
        # The renderer's own "wrap-width" is otherwise fixed at
        # construction time and never revisited, so as this column
        # grows or shrinks afterward (dialog resize, expand
        # redistributing space, or the user dragging it) the wrapped
        # text would keep breaking at the original _DESC_COL_MIN_WIDTH
        # instead of reflowing to the column's real width. "notify::width"
        # fires whenever the column's actual allocated width changes,
        # regardless of the cause, so this keeps wrap-width in sync
        # with it live — see _cb_desc_column_resized.
        self._desc_last_width: int | None = None
        col3.connect("notify::width", self._cb_desc_column_resized)

        self._list_reg.set_search_column(R_NAME)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(self._list_reg)

        # checkbox row
        chk_box = Gtk.ButtonBox()
        chk_box.set_layout(Gtk.ButtonBoxStyle.SPREAD)

        self._show_hidden_chk = Gtk.CheckButton.new_with_label(
            _("Show deactivated plug-ins")
        )
        chk_box.add(self._show_hidden_chk)
        self._show_hidden = self.options_dict["show_hidden"]
        self._show_hidden_chk.set_active(self._show_hidden)
        self._show_hidden_chk.connect("clicked", self.__show_hidden_chk)

        self._show_builtin_chk = Gtk.CheckButton.new_with_label(
            _("Show Built-in plug-ins")
        )
        chk_box.add(self._show_builtin_chk)
        self._show_builtins = self.options_dict["show_builtins"]
        self._show_builtin_chk.set_active(self._show_builtins)
        self._show_builtin_chk.connect("clicked", self.__show_builtins_chk)

        self._show_addons_chk = Gtk.CheckButton.new_with_label(
            _("Show \u20223rd Party addons")
        )
        chk_box.add(self._show_addons_chk)
        self._show_addons = self.options_dict["show_addons"]
        self._show_addons_chk.set_active(self._show_addons)
        self._show_addons_chk.connect("clicked", self.__show_addons_chk)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.pack_start(sw, True, True, 0)
        vbox.pack_start(chk_box, False, False, 0)
        return _("Registered Plugins"), vbox

    def _cb_list_tooltip(
        self,
        widget: Gtk.TreeView,
        x: int,
        y: int,
        keyboard_tip: bool,
        tooltip: Gtk.Tooltip,
    ) -> bool:
        """
        Show a rollover tooltip over a Notes/Source indicator icon cell.

        Explains what double-clicking that specific icon does (see
        button_press_reg) — separate from, and complementary to, the
        column headers' own tooltips (set on lbl_readme/lbl_help in
        registered_plugins_panel), which instead explain what the
        column/icon *means*. Shown only when actually hovering directly
        over an icon that's present — a blank Notes/Source cell (no
        README/help_url for that row) gets no tooltip, since there's
        nothing to double-click there.

        :param widget: the plugin-list TreeView (self._list_reg)
        :param x: pointer x, in ``widget``'s own coordinates, per the
                  ``Gtk.Widget`` "query-tooltip" signal
        :param y: pointer y, in ``widget``'s own coordinates
        :param keyboard_tip: ``True`` if this query was triggered by
                              keyboard focus rather than the pointer, in
                              which case ``x``/``y`` are meaningless
        :param tooltip: the ``Gtk.Tooltip`` to populate if returning ``True``
        :returns: ``True`` if a tooltip was set, ``False`` to suppress
                  showing one
        """
        if keyboard_tip:
            return False
        bin_x, bin_y = widget.convert_widget_to_bin_window_coords(x, y)
        hit = widget.get_path_at_pos(bin_x, bin_y)
        if hit is None:
            return False
        path, column, _cell_x, _cell_y = hit
        if column is self._col_readme:
            indicator_col, text = R_HAS_README, _("Double-click to view ReadMe file")
        elif column is self._col_help:
            indicator_col, text = R_HAS_HELP, _(
                "Double-click to open Help webpage in browser"
            )
        else:
            return False
        model = widget.get_model()
        if model.get_value(model.get_iter(path), indicator_col) is None:
            return False
        tooltip.set_text(text)
        widget.set_tooltip_cell(tooltip, path, column, None)
        return True

    def button_press_reg(self, obj: Gtk.TreeView, event: Gdk.EventButton) -> None:
        """
        Handle clicks on a plugin row.

        - Double-click on the Notes-indicator cell selects that row and
          does the same as clicking the Help button: renders the
          plugin's ``README.md`` in the info pane and switches the Help
          button to Details mode (see ``_show_readme``).
        - Double-click on the web-browser-indicator cell selects that row
          and does the same as clicking the linked text next to the
          "Help:" line in the details pane: opens the plugin's help
          link (see ``_cb_open_help_url``).
        - Any other double-click just shows plugin details for the
          clicked row (the pre-existing behavior).
        - A single left-click on the Type cell of the *already-selected*
          row toggles a filter restricting the list to that row's major
          type (the plain type name, before any second Type-column
          line) — clicking it again on that same still-selected,
          still-filtered row releases the filter. A Type-cell click on a
          row that isn't already selected is left alone and just
          performs the normal click-to-select.

        :param obj: the TreeView widget
        :param event: the button-press event
        :returns: ``True`` to stop further handling of a click that was
                   fully handled here (selected a row and opened its
                   README/help link, or toggled the type filter);
                   ``False``/``None`` otherwise, letting normal handling
                   proceed
        """
        # pylint: disable=protected-access
        if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
            self._show_list_context_menu(event)
            return True

        if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
            hit = self._list_reg.get_path_at_pos(int(event.x), int(event.y))
            if hit is not None:
                path, column, _cell_x, _cell_y = hit
                model = self._list_reg.get_model()
                pid = model.get_value(model.get_iter(path), R_ID)
                if column is self._col_readme:
                    self._selection_reg.select_path(path)
                    self._show_readme()
                    return True
                if column is self._col_help:
                    self._selection_reg.select_path(path)
                    self._cb_open_help_url(pid)
                    return True
            self._cursor_changed(None)
            return None

        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            hit = self._list_reg.get_path_at_pos(int(event.x), int(event.y))
            if hit is not None:
                path, column, _cell_x, _cell_y = hit
                if column is self._col_type and self._selection_reg.path_is_selected(
                    path
                ):
                    self._cb_toggle_type_filter(path)
                    return True
        return None

    def _show_list_context_menu(self, event: Gdk.EventButton) -> None:
        """Show List-panel actions formerly provided by bottom-bar buttons."""
        menu = Gtk.Menu()

        refresh_item = Gtk.MenuItem.new_with_label(
            _("Refresh plugin registry and Addons Project lists")
        )
        refresh_item.connect("activate", lambda _item: self.cb_check_for_updates())
        menu.append(refresh_item)

        export_item = Gtk.MenuItem.new_with_label(
            _("Download Plugin list to a JSON file")
        )
        export_item.connect("activate", lambda _item: self.cb_export_plugin_list())
        menu.append(export_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    def _cb_open_help_url(self, pid: str) -> None:
        """
        Open a plugin's help link, the same as clicking the rendered
        "Help:" link in the details pane would (see
        :meth:`_MdInfoPane.resolve_help_full_url`).

        :param pid: id of the plugin whose help link should be opened
        """
        pdata = self._preg.get_plugin(pid)
        help_url = getattr(pdata, "help_url", None) if pdata else None
        if not help_url:
            wiki_entry = self._match_wiki_entry(pdata) if pdata else None
            help_url = wiki_entry.get("help_url") if wiki_entry else None
        if not help_url:
            return
        full_url = self._md_pane.resolve_help_full_url(help_url)
        try:
            self._md_pane.open_uri(full_url)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("PluginManagerPlus: could not open help_url for '%s'", pid)

    def _cb_toggle_type_filter(self, path: Gtk.TreePath) -> None:
        """
        Toggle the major-type filter for a Type-cell click on ``path``.

        :param path: path (in ``self._list_reg``'s current sort-model
                     coordinates) of the already-selected row that was
                     clicked
        """
        model = self._list_reg.get_model()
        tr_iter = model.get_iter(path)
        major_type = model.get_value(tr_iter, R_TYPE)
        pid = model.get_value(tr_iter, R_ID)

        if self._type_filter == major_type:
            self._type_filter = None
        else:
            self._type_filter = major_type

        self._tree_filter.refilter()
        self.__update_count_label()
        self._update_search_ui()

        new_path = self._row_path_for_pid(pid)
        if new_path is not None:
            self._list_reg.scroll_to_cell(new_path, None, True, 0.5, 0)

    def _cb_type_filter_label_press(
        self, _widget: Gtk.EventBox, event: Gdk.EventButton
    ) -> bool:
        """
        Clear the active major-type filter when its label is double-clicked.

        Mirrors the "click again to release" half of
        :meth:`_cb_toggle_type_filter`, giving the dark-red type-filter
        label next to the search entry (see :meth:`_update_search_ui`) the
        same double-click-to-clear behavior as that type's own Type cell
        in the list, without needing that row to still be selected/
        visible.

        :param _widget: the label's wrapping Gtk.EventBox (unused)
        :param event: the button-press event
        :returns: ``True`` if the double-click was handled here (the
                   filter was active and has been cleared); ``False``/
                   ``None`` otherwise, letting normal handling proceed
        """
        if event.type != Gdk.EventType._2BUTTON_PRESS or event.button != 1:
            return None
        if self._type_filter is None:
            return None
        self._type_filter = None
        self._tree_filter.refilter()
        self.__update_count_label()
        self._update_search_ui()
        return True

    def __show_hidden_chk(self, obj: Gtk.CheckButton) -> None:
        """
        Toggle display of hidden plugins.

        :param obj: the checkbox widget
        """
        self._show_hidden = obj.get_active()
        self.options_dict["show_hidden"] = self._show_hidden
        self.__rebuild_reg_list("0", rescan=False)

    def __show_builtins_chk(self, obj: Gtk.CheckButton) -> None:
        """
        Toggle display of built-in plugins.

        :param obj: the checkbox widget
        """
        self._show_builtins = obj.get_active()
        self.options_dict["show_builtins"] = self._show_builtins
        self.__rebuild_reg_list("0", rescan=False)

    def __show_addons_chk(self, obj: Gtk.CheckButton) -> None:
        """
        Toggle display of 3rd-party addons (installed or available).

        :param obj: the checkbox widget
        """
        self._show_addons = obj.get_active()
        self.options_dict["show_addons"] = self._show_addons
        self.__rebuild_reg_list("0", rescan=False)

    def _cb_type_sort(
        self,
        model: Gtk.TreeModel,
        iter_a: Gtk.TreeIter,
        iter_b: Gtk.TreeIter,
        _data: object,
    ) -> int:
        """
        Sort func for the Type column: by R_TYPE_SORT, then always by Name.

        Registered as ``self._list_reg.get_model()``'s sort func for the
        ``R_TYPE_SORT`` column id, so clicking the Type header groups rows
        by type name plus sub-category/navtypes detail (see
        :data:`R_TYPE_SORT`), and within an identical group, always
        further orders by Name — a plain ``set_sort_column_id`` only
        supports a single sort key, hence this custom comparator.

        :param model: the sorting model (``self._list_reg.get_model()``)
        :param iter_a: iterator for the first row being compared
        :param iter_b: iterator for the second row being compared
        :param _data: unused user-data argument required by GTK
        :returns: -1, 0, or 1, per :class:`Gtk.TreeIterCompareFunc`
        """
        key_a = (
            model.get_value(iter_a, R_TYPE_SORT),
            model.get_value(iter_a, R_NAME),
        )
        key_b = (
            model.get_value(iter_b, R_TYPE_SORT),
            model.get_value(iter_b, R_NAME),
        )
        if key_a < key_b:
            return -1
        if key_a > key_b:
            return 1
        return 0

    def _cb_indicator_sort(
        self,
        model: Gtk.TreeModel,
        iter_a: Gtk.TreeIter,
        iter_b: Gtk.TreeIter,
        column: int,
    ) -> int:
        """
        Sort func shared by the Notes and Source indicator columns.

        Those columns hold a ``GdkPixbuf`` or ``None`` (see
        :data:`R_HAS_README`/:data:`R_HAS_HELP`), which Gtk cannot
        compare directly, hence this custom comparator: rows that have
        the icon sort before rows that don't, and rows with the same
        presence/absence are then further ordered by Name.

        :param model: the sorting model (``self._list_reg.get_model()``)
        :param iter_a: iterator for the first row being compared
        :param iter_b: iterator for the second row being compared
        :param column: the model column being sorted — ``R_HAS_README``
                        or ``R_HAS_HELP`` — passed in as the sort func's
                        user-data
        :returns: -1, 0, or 1, per :class:`Gtk.TreeIterCompareFunc`
        """
        key_a = (
            model.get_value(iter_a, column) is None,
            model.get_value(iter_a, R_NAME),
        )
        key_b = (
            model.get_value(iter_b, column) is None,
            model.get_value(iter_b, R_NAME),
        )
        if key_a < key_b:
            return -1
        if key_a > key_b:
            return 1
        return 0

    def _cb_sort_column_changed(self, _sortable: Gtk.TreeSortable) -> None:
        """
        Re-center the current selection after the sort column/order changes.

        Sorting reorders every row's path, including whichever row is
        currently selected, so without this the selection can end up
        scrolled out of view the moment the user clicks a column header.
        Delegates to :meth:`_recenter_on_selection` — the same helper
        :meth:`_select_own_plugin_row` uses to do this on open — rather
        than duplicating that logic here.

        :param _sortable: the TreeModelSort whose sort changed (unused —
                           self._list_reg's own model, always the same
                           object this is connected to)
        """
        self._recenter_on_selection()

    def _apply_filter(
        self, model: Gtk.ListStore, tr_iter: Gtk.TreeIter, _data: object
    ) -> bool:
        """
        Determine visibility of a row based on the type filter/search text.

        Used as the visible-func for ``self._tree_filter``. A row must
        pass both the major-type filter (see :attr:`_type_filter`,
        toggled by clicking an already-selected row's Type cell) and the
        last debounced search value to be visible.

        :param model: the underlying ListStore
        :param tr_iter: iterator pointing at the row to test
        :param _data: unused user-data argument required by GTK
        :returns: ``True`` if the row should be visible
        """
        if (
            self._type_filter is not None
            and model.get_value(tr_iter, R_TYPE) != self._type_filter
        ):
            return False

        # Keep filtering against the last debounced value, not the text the
        # user is actively entering.  This also prevents an unrelated model
        # refilter (such as changing the Type filter) from applying a partial
        # search before its timeout has elapsed.
        filter_str = self._applied_filter_text.lower()
        if not filter_str:
            return True
        pdata = self._preg.get_plugin(model.get_value(tr_iter, R_ID))
        p_txt = ""
        if pdata:
            p_txt += pdata.fname or ""
            p_txt += " ".join(getattr(pdata, "authors", []) or [])
            p_txt += " ".join(getattr(pdata, "authors_email", []) or [])
            p_txt += " ".join(getattr(pdata, "maintainers", []) or [])
            p_txt += " ".join(getattr(pdata, "maintainers_email", []) or [])
        for col in (R_TYPE, R_STAT_S, R_NAME, R_DESC, R_ID):
            val = model[tr_iter][col]
            if val:
                p_txt += val
        p_txt = p_txt.lower()
        for word in filter_str.split():
            if word not in p_txt:
                return False
        return True

    def _cursor_changed(self, _obj: object) -> None:
        """
        Update action-button sensitivity when the selected row changes.
        """
        model, node = self._selection_reg.get_selected()
        if not node:
            return
        status = model.get_value(node, R_STAT)
        pid = model.get_value(node, R_ID)

        pdata = self._preg.get_plugin(pid)
        if pdata is None and (status & AVAILABLE):
            # Not-yet-installed addon: only known via the parsed
            # new_addons.txt listing, not the plugin registry. Build a
            # lightweight stand-in so the details/thumbnail panel is
            # populated the same way as for installed/built-in plugins.
            record = next((a for a in self.addons if a.get("i") == pid), None)
            pdata = _RemotePluginView(record) if record else None

        if pdata:
            # Preview is deliberately independent of the Details/README
            # toggle: it always follows the selected plugin.
            self._current_pid = pdata.id
            self._current_preview_pdata = pdata
            self._show_preview(pdata)

            has_fpath = bool(getattr(pdata, "fpath", None))
            if self._readme_showing:
                is_builtin = (
                    "gramps/plugins" in pdata.fpath.replace("\\", "/")
                    if has_fpath
                    else False
                )
                has_readme = (
                    os.path.isfile(os.path.join(pdata.fpath, "README.md"))
                    if has_fpath
                    else False
                )
                if is_builtin or not has_readme:
                    # Revert to details mode before refreshing layout elements
                    self._readme_showing = False
                    _set_btn_icon_label(
                        self._help_btn, "help-browser", _("_Help"), use_mnemonic=True
                    )
                    self._help_btn.set_tooltip_text(_("Show the Plugin Manager README"))

            if self._readme_showing:
                # Help mode follows the current selection just as Details
                # mode does, so the upper-left document never belongs to a
                # previously selected plugin.
                self._show_readme()
            else:
                self._show_plugin_details(pdata)

        if (status & (INSTALLED | BUILTIN)) and (
            VIEW == self._pmgr.get_plugin(pid).ptype
        ):
            self._hide_btn.set_sensitive(False)
        else:
            self._hide_btn.set_sensitive(True)
        if status & HIDDEN:
            self._hide_btn.set_label(_("Reactivate"))
            self._hide_btn.set_tooltip_text(_("Re-enable the selected plugin."))
        else:
            self._hide_btn.set_label(_("Deactivate"))
            self._hide_btn.set_tooltip_text(
                _("Disable the selected plugin until you reactivate it.")
            )

        show_load = False
        if status & (INSTALLED | BUILTIN):
            show_load = True
            success_list = self._pmgr.get_success_list()
            for i in success_list:
                if pid == i[2].id:
                    show_load = False
                    break
        self._load_btn.set_sensitive(show_load)

        if status & (AVAILABLE | UPDATE):
            self._install_btn.set_label(_("Install"))
            self._install_btn.set_tooltip_text(
                _("Install or update the selected add-on.")
            )
            self._install_btn.set_sensitive(True)
        elif status & INSTALLED:
            self._install_btn.set_label(_("Uninstall"))
            self._install_btn.set_tooltip_text(
                _("Remove the selected add-on from this installation.")
            )
            self._install_btn.set_sensitive(True)
        else:
            self._install_btn.set_sensitive(False)

        show_bar = bool(status & (INSTALLED | BUILTIN | AVAILABLE | UPDATE))
        if show_bar:
            self._action_btn_box.show()
            self._action_sep.show()
        else:
            self._action_btn_box.hide()
            self._action_sep.hide()

    def _wiki_table_paths(self) -> tuple[str, str]:
        """
        Return the local (source, cache) paths for the wiki addon table.

        :returns: a 2-tuple ``(table_path, catalog_json_path)`` where
                  ``table_path`` is this addon's local copy of the raw
                  ``Template:Addons5.2`` mediawiki source and
                  ``catalog_json_path`` is the parsed-catalog JSON sidecar
                  saved next to it.
        """
        media_dir = os.path.join(self._own_plugin_dir(), "media")
        return (
            os.path.join(media_dir, "Template_Addons5.2.txt"),
            os.path.join(media_dir, "addons_wiki_catalog.json"),
        )

    def _ensure_local_wiki_table_file(self, table_path: str) -> bool:
        """
        Make sure a local copy of the raw wiki addon table exists.

        If ``table_path`` is already present, this is a no-op (the bundled
        copy is used as-is; refreshing it is a separate, explicit action,
        not something that happens implicitly on every dialog open). If it
        is missing, this fetches the current table from
        :data:`WIKI_TABLE_URL` and saves it locally so future runs need no
        network access.

        :param table_path: local path the raw wikitext should live at
        :returns: ``True`` if a usable local file exists after this call
        """
        if os.path.isfile(table_path):
            return True
        try:
            with urllib.request.urlopen(WIKI_TABLE_URL, timeout=10) as resp:
                raw_bytes = resp.read()
        except (OSError, ValueError) as err:
            LOG.warning(
                "PluginManagerPlus: could not fetch wiki addon table from " "'%s': %s",
                WIKI_TABLE_URL,
                err,
            )
            return False
        try:
            os.makedirs(os.path.dirname(table_path), exist_ok=True)
            with open(table_path, "wb") as filep:
                filep.write(raw_bytes)
        except OSError as err:
            LOG.warning(
                "PluginManagerPlus: could not save fetched wiki addon table "
                "to '%s': %s",
                table_path,
                err,
            )
            return False
        LOG.info(
            "PluginManagerPlus: fetched wiki addon table from '%s' to '%s'",
            WIKI_TABLE_URL,
            table_path,
        )
        return True

    def _load_wiki_addon_table(self) -> dict[str, dict]:
        """
        Load the wiki addon catalog into a lookup table.

        The source is the Gramps wiki's ``Template:Addons5.2`` mediawiki
        table (one row per addon, with ``<!-- Column Name -->`` comments
        marking each cell), bundled locally at
        ``media/Template_Addons5.2.txt`` and fetched from
        :data:`WIKI_TABLE_URL` if that local copy is missing (see
        :meth:`_ensure_local_wiki_table_file`).

        Every column of the table is preserved for every row (under
        ``raw_columns`` in each entry) even though only a subset is
        currently used by the UI, since it is not yet known which of the
        remaining columns will become useful. The parsed catalog is
        cached as a local JSON sidecar
        (``media/addons_wiki_catalog.json``) so it only needs to be
        re-parsed when the source table file changes (by mtime); other
        tools can also read that JSON file directly. Also cached in
        ``self._wiki_addon_index`` for the life of the dialog.

        :returns: a dict keyed by every normalised identifier that could
                  plausibly match a :class:`PluginData` (the wiki page
                  slug and the download filename stem, both lower-cased),
                  mapping to a dict with keys ``help_url``,
                  ``display_name``, ``image_file``, ``description``,
                  ``rating``, ``contact``, ``use``, ``download_stem``,
                  and ``raw_columns`` (every column's raw wikitext cell,
                  keyed by column name). Empty if no table could be
                  loaded or fetched.
        """
        if self._wiki_addon_index is not None:
            return self._wiki_addon_index

        table_path, catalog_json_path = self._wiki_table_paths()
        self._ensure_local_wiki_table_file(table_path)

        # Reuse a previously-parsed JSON catalog if it is at least as new
        # as the source table (avoids re-parsing on every dialog open).
        try:
            table_mtime = os.path.getmtime(table_path)
            catalog_mtime = os.path.getmtime(catalog_json_path)
            if catalog_mtime >= table_mtime:
                with open(catalog_json_path, "r", encoding="utf-8") as filep:
                    index = json.load(filep)
                LOG.debug(
                    "PluginManagerPlus: loaded wiki addon catalog cache '%s'",
                    catalog_json_path,
                )
                self._wiki_addon_index = index
                return index
        except (OSError, ValueError):
            pass  # no usable cache; fall through and (re)parse

        index = self._parse_wiki_addon_table(table_path)
        try:
            with open(catalog_json_path, "w", encoding="utf-8") as filep:
                json.dump(index, filep, indent=2, sort_keys=True)
            LOG.info(
                "PluginManagerPlus: saved wiki addon catalog to '%s'",
                catalog_json_path,
            )
        except OSError as err:
            LOG.warning(
                "PluginManagerPlus: could not save wiki addon catalog to " "'%s': %s",
                catalog_json_path,
                err,
            )

        self._wiki_addon_index = index
        return index

    @staticmethod
    def _parse_wiki_addon_table(table_path: str) -> dict[str, dict]:
        """
        Parse a local copy of the ``Template:Addons5.2`` wikitext table.

        :param table_path: local path of the raw mediawiki table source
        :returns: a dict keyed by lower-cased wiki id / download stem, as
                  described in :meth:`_load_wiki_addon_table`. Empty if
                  the file is missing or unparsable.
        """
        index: dict[str, dict] = {}
        try:
            with open(table_path, "r", encoding="utf-8") as filep:
                text = filep.read()
        except OSError:
            LOG.debug("No wiki addon table found at '%s'", table_path)
            return index

        wikilink_re = re.compile(r"\[\[([^|\]]+)(?:\|([^\]]+))?\]\]")
        file_re = re.compile(r"\[\[File:([^|\]]+)")
        ext_link_re = re.compile(r"\[(\S+)\s+([^\]]+)\]")
        cell_re = re.compile(r"^\|<!--\s*(.*?)\s*-->\s*(.*)$")

        def _clean(cell_text: str) -> str:
            """Lightly convert mediawiki markup to plain/markdown text."""
            cell_text = wikilink_re.sub(lambda m: m.group(2) or m.group(1), cell_text)
            cell_text = ext_link_re.sub(r"[\2](\1)", cell_text)
            cell_text = cell_text.replace("<br />", ", ").replace("<br/>", ", ")
            return cell_text.strip()

        for block in text.split("\n|-"):
            # Preserve every column verbatim, whatever its name, so no
            # data from the table is silently dropped even if this parser
            # does not (yet) know what to do with a given column.
            cells: dict[str, str] = {}
            for line in block.splitlines():
                match = cell_re.match(line.strip())
                if match:
                    cells[match.group(1)] = match.group(2)
            if not cells:
                continue  # blank template row or unrecognised block

            doc_cell = cells.get("Plugin / Documentation", "")
            link_match = wikilink_re.search(doc_cell)
            if not link_match:
                continue  # row has no identifying link; can't be matched

            page_title = link_match.group(1).strip()
            display_name = (link_match.group(2) or page_title).strip()
            wiki_id = page_title.split(":", 1)[-1].strip()

            image_match = file_re.search(cells.get("Image", ""))
            image_file = image_match.group(1).strip() if image_match else None

            download_stem = None
            dl_match = ext_link_re.search(cells.get("Download", ""))
            if dl_match:
                download_name = dl_match.group(2).strip()
                download_stem = re.sub(
                    r"\.addon\.tgz$|\.tgz$", "", download_name, flags=re.IGNORECASE
                )

            entry = {
                "help_url": page_title,
                "display_name": display_name,
                "type": _clean(cells.get("Type", "")),
                "image_file": image_file,
                "description": _clean(cells.get("Description", "")),
                "use": _clean(cells.get("Use", "")),
                "rating": _clean(cells.get("Rating (out of 4)", "")),
                "contact": _clean(cells.get("Contact", "")),
                "download_stem": download_stem,
                # Every column, verbatim, keyed by its own wiki column
                # name — the "preserve everything" copy.
                "raw_columns": dict(cells),
            }

            for key in (wiki_id, download_stem):
                if key:
                    index[key.lower()] = entry

        LOG.info(
            "PluginManagerPlus: parsed %d addon(s) from wiki table '%s'",
            len({id(v) for v in index.values()}),
            table_path,
        )
        return index

    def _match_wiki_entry(self, pdata: object) -> dict | None:
        """
        Best-effort match a :class:`PluginData` to a wiki table entry.

        Tries, in order: the plugin id, the module filename stem, and
        finally a fuzzy match on the plugin's display name.

        :param pdata: a Gramps plugin-data object from the plugin registry
        :returns: the matched wiki entry dict, or ``None``
        """
        index = self._load_wiki_addon_table()
        if not index:
            return None

        candidates = []
        if getattr(pdata, "id", None):
            candidates.append(pdata.id.lower())
        if getattr(pdata, "fname", None):
            candidates.append(os.path.splitext(pdata.fname)[0].lower())
        for key in candidates:
            if key in index:
                return index[key]

        if getattr(pdata, "name", None):
            names = {v["display_name"].lower(): v for v in index.values()}
            close = difflib.get_close_matches(
                pdata.name.lower(), names.keys(), n=1, cutoff=0.8
            )
            if close:
                return names[close[0]]
        return None

    def _show_preview(self, pdata: object) -> None:
        """Render the selected plugin's Preview pane, fetching wiki art if needed."""
        if self._active_pbars:
            return
        pid = pdata.id
        wiki_entry = self._match_wiki_entry(pdata)
        capture_path = self._find_capture_image(getattr(pdata, "fpath", None) or "")
        if capture_path:
            self._render_preview(pdata, capture_path)
            return

        image_file = wiki_entry.get("image_file") if wiki_entry else None
        if not image_file:
            self._render_preview(pdata)
            return

        cache_dir = os.path.join(self._own_plugin_dir(), "media", "wiki_cache")
        cache_path = os.path.join(cache_dir, image_file)

        if os.path.isfile(cache_path):
            self._render_preview(pdata, cache_path)
            return

        # Not cached yet — show a placeholder now, fetch in the background.
        self._render_preview(pdata)
        thread = threading.Thread(
            target=self._fetch_wiki_image_thread,
            args=(pid, image_file, cache_dir, cache_path),
            daemon=True,
        )
        thread.start()

    def _fetch_wiki_image_thread(
        self, pid: str, image_file: str, cache_dir: str, cache_path: str
    ) -> None:
        """
        Background thread: download and cache a wiki preview image.

        :param pid: the plugin id this fetch was started for (race guard)
        :param image_file: the wiki ``File:`` name to fetch
        :param cache_dir: local directory to cache downloaded images in
        :param cache_path: full local path to write the downloaded image to
        """
        url = "https://gramps-project.org/wiki/Special:FilePath/" + image_file
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = resp.read()
            with self._wiki_image_lock:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_path, "wb") as filep:
                    filep.write(data)
            LOG.info(
                "PluginManagerPlus: cached wiki image '%s' to '%s'",
                image_file,
                cache_path,
            )
        except (OSError, ValueError) as err:
            LOG.debug("Could not fetch wiki image '%s': %s", image_file, err)
            return
        GLib.idle_add(self._apply_fetched_wiki_image, pid, cache_path)

    def _apply_fetched_wiki_image(self, pid: str, cache_path: str) -> bool:
        """
        Main-thread callback: display a freshly-downloaded wiki image.

        :param pid: the plugin id this fetch was started for (race guard)
        :param cache_path: local path of the downloaded image
        :returns: ``False`` so GLib does not repeat this idle callback
        """
        if pid == self._current_pid:
            pdata = self._preg.get_plugin(pid) or self._current_preview_pdata
            if pdata is not None:
                self._render_preview(pdata, cache_path)
        return False

    def _format_help_link(self, help_url: str) -> str:
        """
        Build a markdown link line for a plugin's help/documentation URL.

        :param help_url: either a full URL or a Gramps wiki page title
        :returns: a markdown ``**Help:** [...](...)`` line
        """
        full_url = self._md_pane.resolve_help_full_url(help_url)
        return "**%s:** [%s](%s)" % (_("Help"), help_url, full_url)

    def _show_plugin_details(self, pdata: object) -> None:
        """
        Render plugin registration metadata into the markdown info pane.

        Uses plain ``**Label:** value`` lines rather than a Markdown table so
        the text reflows naturally at any panel width. Name and description
        belong to the separate Preview pane, rather than the detail metadata.

        :param pdata: a Gramps plugin-data object from the plugin registry
        """
        wiki_entry = self._match_wiki_entry(pdata)

        lines = []

        # Comprehensive registration key/value listings matching original configurations
        lines.append("**%s:** `%s`" % (_("ID"), pdata.id))
        lines.append("**%s:** `%s`" % (_("Version"), pdata.version))
        lines.append(
            "**%s:** %s" % (_("Type"), PTYPE_STR.get(pdata.ptype, str(pdata.ptype)))
        )

        # Tool/Report sub-category (e.g. a Tool's Isotammi-style custom
        # submenu, or a Report's "Text Reports"/"Graphs"/etc.) — the same
        # lookup used for the List panel's Type-column second line, see
        # _subcategory_label. Not shown when unset/unrecognised
        # (Gramplets, Rules, and other plugin types either don't have a
        # comparable sub-category or already show their own
        # navtypes/namespace detail elsewhere in the List panel).
        subcategory = _subcategory_label(pdata.ptype, getattr(pdata, "category", None))
        if subcategory:
            lines.append("**%s:** %s" % (_("Category"), subcategory))
        elif pdata.ptype == VIEW:
            # A View's `category` is its own (codename, translated
            # label) pair rather than a _subcategory_label-recognised
            # value — same data driving the List panel's category icon,
            # see the VIEW branch of __populate_reg_list.
            category = getattr(pdata, "category", None)
            if (
                isinstance(category, (tuple, list))
                and len(category) > 1
                and category[1]
            ):
                lines.append("**%s:** %s" % (_("Category"), category[1]))

        # Target version
        target_version = getattr(pdata, "gramps_target_version", None) or getattr(
            pdata, "version_supported", "N/A"
        )
        lines.append("**%s:** `%s`" % (_("Target Gramps Version"), target_version))

        # Status/Experimental flag — pdata.statustext() is Gramps' own
        # resolver for this (see PluginData), already used correctly
        # elsewhere in this file (cb_export_plugin_list); this used to
        # instead re-derive it from a separate, hand-maintained
        # {0: "STABLE", 1: "UNSTABLE", 2: "EXPERIMENTAL"} mapping here,
        # which not only duplicated logic Gramps itself already provides
        # but was simply wrong — it didn't cover every status value
        # (e.g. BETA), so a plugin whose .gpr.py declared some other
        # status could still show up mislabeled as one of these three
        # instead of passing its real status through.
        #
        # Guarded with getattr/callable rather than calling it directly:
        # _RemotePluginView (a not-yet-installed addon; see its own
        # statustext()) already provides a fallback, but this stays
        # tolerant of any other pdata-like stand-in that might not.
        statustext = getattr(pdata, "statustext", None)
        status_display = statustext() if callable(statustext) else _("Unknown")
        lines.append("**%s:** %s" % (_("Status"), status_display))

        # Audience — AUDIENCETEXT is Gramps' own mapping for this (mirrors
        # STATUSTEXT above; also the "Everyone"/"Expert"/etc. filter
        # Gramps' own bundled Plugin Manager offers), so this is a direct
        # pass-through rather than a re-derived mapping — same as
        # pdata.statustext() above.
        audience = getattr(pdata, "audience", None)
        if audience is not None:
            lines.append(
                "**%s:** %s"
                % (_("Audience"), AUDIENCETEXT.get(audience, str(audience)))
            )

        if getattr(pdata, "authors", None):
            lines.append("**%s:** %s" % (_("Authors"), ", ".join(pdata.authors)))
        # Filter out blank entries — pdata.authors_email is parallel to
        # pdata.authors, so it can (and often does) contain empty
        # strings for authors who simply have no email on file; without
        # filtering those out, a blank entry rendered as a link produces
        # a stray, meaningless "[](mailto:)" in the details pane.
        author_emails = [e for e in getattr(pdata, "authors_email", None) or [] if e]
        if author_emails:
            emails = ", ".join("[%s](mailto:%s)" % (e, e) for e in author_emails)
            lines.append("**%s:** %s" % (_("Author Email"), emails))

        if getattr(pdata, "maintainers", None):
            lines.append(
                "**%s:** %s" % (_("Maintainers"), ", ".join(pdata.maintainers))
            )
        maintainer_emails = [
            e for e in getattr(pdata, "maintainers_email", None) or [] if e
        ]
        if maintainer_emails:
            emails = ", ".join("[%s](mailto:%s)" % (e, e) for e in maintainer_emails)
            lines.append("**%s:** %s" % (_("Maintainer Email"), emails))

        if getattr(pdata, "fname", None):
            lines.append("**%s:** `%s`" % (_("File Name"), pdata.fname))

        # Hotlinked Folder/Directory Path
        if getattr(pdata, "fpath", None):
            lines.append(
                "**%s:** [%s](file://%s)"
                % (_("Directory Path"), pdata.fpath, pdata.fpath)
            )

        if getattr(pdata, "help_url", None):
            lines.append(self._format_help_link(pdata.help_url))
        elif wiki_entry and wiki_entry.get("help_url"):
            lines.append(self._format_help_link(wiki_entry["help_url"]))

        md_text = "\n".join(lines)
        self._md_pane.render(md_text)
        self._current_pid = pdata.id

    def _schedule_filter(self, _widget: Gtk.SearchEntry) -> None:
        """Apply text searches only after typing has paused for 250 ms."""
        self._search_debounce_generation += 1
        generation = self._search_debounce_generation
        if self._search_debounce_id is not None:
            GLib.source_remove(self._search_debounce_id)
        self._search_debounce_id = GLib.timeout_add(
            250, self._apply_debounced_filter, generation
        )
        self._update_search_ui()

    def _apply_debounced_filter(self, generation: int) -> bool:
        """Run only the latest pending search timeout."""
        if generation != self._search_debounce_generation:
            return False
        self._search_debounce_id = None
        self._applied_filter_text = self.filter_entry.get_text()
        self.filter_str_changed(None)
        return False

    def filter_str_changed(self, _widget: Gtk.SearchEntry | None) -> None:
        """
        Refilter the plugin list when the search text changes.

        After refiltering, re-centers the view on whichever row was
        selected before the filter changed, provided that row still
        matches the new search text (is still visible). If it no longer
        matches, the view position is left as-is.

        :param _widget: the SearchEntry (unused; signal passes it automatically)
        """
        if not hasattr(self, "_tree_filter"):
            return
        selected_pid = self._current_pid
        self._tree_filter.refilter()
        self.__update_count_label()
        self._update_search_ui()

        path = self._row_path_for_pid(selected_pid)
        if path is not None:
            self._selection_reg.handler_block(self._cursor_hndlr)
            self._selection_reg.select_path(path)
            self._selection_reg.handler_unblock(self._cursor_hndlr)
            self._list_reg.scroll_to_cell(path, None, True, 0.5, 0)

    def _update_search_ui(self) -> None:
        """
        Reflect the active type filter / search text in the search field.

        Shows the active major-type filter (see :attr:`_type_filter`) as
        a bold, dark-red label immediately before the search entry —
        e.g. "Exporter" ahead of the entry's own magnifying-glass icon,
        making clear that only Exporter-type plugins are being searched.
        The dark-red color, matching the filtered row's own Type-cell
        highlight, doubles as a hint that double-clicking the label — see
        :meth:`_cb_type_filter_label_press` — clears the filter, the same
        as double-clicking that type's Type cell in the list — see
        :meth:`_cb_toggle_type_filter`. Also makes the entry's secondary
        (clear) icon visible and clickable whenever there is search text
        and/or a type filter active, so a single click resets both — see
        :meth:`_cb_search_icon_press`.
        """
        has_type = self._type_filter is not None
        has_text = bool(self.filter_entry.get_text())

        self._type_filter_label.set_text(self._type_filter if has_type else "")
        self._type_filter_label.set_visible(has_type)
        self._type_filter_label_box.set_visible(has_type)
        if has_type:
            self._type_filter_label.set_markup(
                '<span foreground="darkred"><b>%s</b></span>'
                % markup_escape_text(self._type_filter)
            )
            filter_tooltip = (
                _(
                    "Only %s plugins are being searched — click the search "
                    "field's clear icon, double-click this label, or "
                    "double-click this type's Type cell again, to remove "
                    "this filter"
                )
                % self._type_filter
            )
            # Set on both the label and its wrapping EventBox: the
            # EventBox owns the GdkWindow that receives pointer/tooltip
            # events, so a tooltip set only on the child Label may not
            # be queried while hovering over it.
            self._type_filter_label.set_tooltip_text(filter_tooltip)
            self._type_filter_label_box.set_tooltip_text(filter_tooltip)

        if has_type or has_text:
            self.filter_entry.set_icon_from_icon_name(
                Gtk.EntryIconPosition.SECONDARY, "edit-clear-symbolic"
            )
            self.filter_entry.set_icon_activatable(
                Gtk.EntryIconPosition.SECONDARY, True
            )
            if has_type and has_text:
                tooltip = _("Clear search text and type filter")
            elif has_type:
                tooltip = _("Clear type filter")
            else:
                tooltip = _("Clear search text")
            self.filter_entry.set_icon_tooltip_text(
                Gtk.EntryIconPosition.SECONDARY, tooltip
            )
        else:
            self.filter_entry.set_icon_from_icon_name(
                Gtk.EntryIconPosition.SECONDARY, None
            )

    def _cb_search_icon_press(
        self,
        entry: Gtk.SearchEntry,
        icon_pos: "Gtk.EntryIconPosition",
        _event: Gdk.Event,
    ) -> None:
        """
        Clear the search text and any active type filter together.

        Connected to the search entry's ``icon-press`` signal. Only the
        secondary (clear) icon does anything here; the primary
        (magnifying-glass) icon is left to its default behavior.

        :param entry: the SearchEntry
        :param icon_pos: which icon was pressed
        :param _event: the triggering button event (unused)
        """
        if icon_pos != Gtk.EntryIconPosition.SECONDARY:
            return
        entry.set_text("")
        self._search_debounce_generation += 1
        if self._search_debounce_id is not None:
            GLib.source_remove(self._search_debounce_id)
            self._search_debounce_id = None
        self._applied_filter_text = ""
        if self._type_filter is not None:
            self._type_filter = None
        self._tree_filter.refilter()
        self.__update_count_label()
        self._update_search_ui()

    def done(self, obj: Gtk.Dialog, res: int) -> None:
        """
        Save UI state and close the dialog.

        :param obj: the dialog widget
        :param res: the Gtk response ID that triggered this callback
        """
        if res == Gtk.ResponseType.HELP:
            try:
                self._cb_toggle_help_readme()
            except Exception:  # pylint: disable=broad-except
                # A silent exception here would make the Help button
                # appear to do nothing at all; log it loudly instead so
                # the real cause is visible rather than swallowed.
                LOG.exception("PluginManagerPlus: Help/Details toggle failed")
            return
        # self.options_dict's own copy of "pane_setting" is left alone
        # (still whatever load_previous_values loaded, or the class
        # default) and, per PluginManagerOptions, is never actually
        # non-default for "show_hidden"/"show_builtins"/"show_addons" at
        # this point either (see __init__) — so self.options.handler's
        # own ini file stays essentially empty of anything meaningful;
        # all the pane/column sizing that actually matters is saved via
        # _ini_manager, next to this file, instead.
        _ini_manager.set("interface.list-pane-height", self.vpane.get_position())
        _ini_manager.set(
            "interface.preview-pane-width",
            self._thumb_right_vbox.get_allocated_width(),
        )
        _ini_manager.set("spacing.type-column-width", self._col_type.get_width())
        _ini_manager.set("spacing.name-column-width", self._col_name.get_width())
        _ini_manager.set("spacing.status-column-width", self._col_status.get_width())
        _ini_manager.save()
        self.close()

    def _cb_toggle_help_readme(self) -> None:
        """
        Toggle the left-hand info pane between README and plugin details.
        """
        if self._readme_showing:
            self._readme_showing = False
            _set_btn_icon_label(
                self._help_btn, "help-browser", _("_Help"), use_mnemonic=True
            )
            self._help_btn.set_tooltip_text(_("Show the Plugin Manager README"))
            # re-render whatever plugin is currently selected
            self._cursor_changed(None)
        else:
            self._show_readme()

    def _cb_populate_info_pane_popup(
        self, _textview: Gtk.TextView, popup: Gtk.Widget
    ) -> None:
        """
        Add "Open documentation reader" to the info pane's right-click menu.

        Connected once, to the shared Details/README pane's own
        Gtk.TextView "populate-popup" signal (see :attr:`_md_pane`), so
        this single handler covers both viewing modes — the pane is the
        very same widget in either mode, only its rendered content
        differs (see :meth:`_show_readme`/:meth:`_cursor_changed`).

        The item is only added — never shown disabled — when the
        currently selected plugin has its own ``README.md`` (mirroring
        the same ``pdata.fpath``-based lookup :data:`R_HAS_README`
        itself uses); there's nothing for it to open otherwise.
        Availability of the Markdown Dash gramplet that actually does
        the opening (see ``MarkdownDash.gpr.py``, ``id="markdowndash"``)
        is *not* checked here — see :meth:`_cb_open_doc_reader` for why.

        :param _textview: the pane's Gtk.TextView (unused — this only
                           ever fires on :attr:`_md_pane`'s one textview)
        :param popup: the context menu GTK is about to show. Normally a
                      :class:`Gtk.Menu`; guarded with an
                      :func:`isinstance` check since only a
                      :class:`Gtk.MenuShell` accepts new
                      :class:`Gtk.MenuItem` children via ``append()`` —
                      GTK's own "populate-popup" documentation notes this
                      may occasionally be some other widget instead.
        """
        if not isinstance(popup, Gtk.MenuShell):
            return
        model, node = self._selection_reg.get_selected()
        if not node:
            return
        pid = model.get_value(node, R_ID)
        pdata = self._preg.get_plugin(pid)
        if pdata is None or not pdata.fpath:
            return
        readme_path = os.path.join(pdata.fpath, "README.md")
        if not os.path.isfile(readme_path):
            return

        # Prepended (top of menu) rather than appended: this is the
        # action someone reaching for this menu most likely wants, ahead
        # of the TextView's own default Cut/Copy/Paste/Select-All
        # entries below it. Order matters for Gtk.MenuShell.prepend, so
        # the separator goes in first — each prepend lands at index 0,
        # so inserting the separator, then the item, leaves the final
        # order as [item, separator, ...the pane's own default entries].
        sep = Gtk.SeparatorMenuItem()
        sep.show()
        popup.prepend(sep)

        item = Gtk.MenuItem(label=_("Open documentation reader"))
        item.show()
        item.connect("activate", self._cb_open_doc_reader, readme_path, pdata.name)
        popup.prepend(item)

    def _cb_open_doc_reader(
        self, _item: Gtk.MenuItem, readme_path: str, addon_name: str
    ) -> None:
        """
        Open a plugin's README.md in its own Markdown Dash window.

        Loads the Markdown Dash gramplet (see ``MarkdownDash.gpr.py``,
        ``id="markdowndash"``) on demand via the Gramps plugin registry
        — the same on-demand-load approach ``__load_selected`` uses for
        the plugin list's own **Load** action — then calls its public
        ``open_markdown_file()`` API (see ``MarkdownDash.py``'s module
        docstring) to pop the README open in its own standalone dialog,
        independent of this one.

        Deliberately parented to Gramps' own main window
        (:attr:`uistate`.window), never to this dialog's own
        :attr:`window` — closing Plugin Manager *plus* must not also
        close a documentation window opened from it, so a plugin's
        README can stay open and be read while exploring other plugins,
        or after closing this window entirely.

        If the info pane was showing this same README (Help mode) when
        the item was chosen, switches it back to Details mode first —
        see :meth:`_cb_toggle_help_readme` — since leaving the pane on
        the README that's now also open in its own window would be
        redundant.

        If Markdown Dash isn't found registered, this makes one
        rescan-and-retry attempt before giving up — Gramps' own core
        plugin scan (:class:`gramps.gen.plug._pluginreg.PluginRegister`)
        runs once at Gramps startup, before any database is even opened,
        and drops a plugin's registration entirely if it doesn't find
        that plugin's ``fname`` on disk at that exact moment; on some
        systems (e.g. a home directory mounted over a network, or an
        install script still copying files at that moment) that check
        can lose a race against a plugin's own files genuinely being
        there. :meth:`__rebuild_reg_list`'s existing rescan (the same
        one the **Update** action already triggers) re-runs that same
        core scan and, on a fresh pass, usually finds it. A message is
        only shown if Markdown Dash still can't be found or loaded after
        that retry, rather than failing silently either way.

        :param _item: the clicked Gtk.MenuItem (unused)
        :param readme_path: the ``README.md`` path captured when the
                             context menu was built (see
                             :meth:`_cb_populate_info_pane_popup`) —
                             deliberately not re-derived from the current
                             selection here, in case the selection
                             changed between the right-click and choosing
                             this item
        :param addon_name: the README's own plugin's translated
                            ``pdata.name``, captured the same way, passed
                            through to Markdown Dash's own locale-invite
                            wording
        """
        if self._readme_showing:
            self._cb_toggle_help_readme()

        pdata = self._preg.get_plugin("markdowndash")
        if pdata is None or not pdata.fpath:
            self.__rebuild_reg_list(rescan=True)
            pdata = self._preg.get_plugin("markdowndash")
        if pdata is None or not pdata.fpath:
            OkDialog(
                _("Markdown Dash not found"),
                _(
                    "The Markdown Dash gramplet isn't currently "
                    "registered, so this README can't be opened in its "
                    "own window. A rescan for new/changed plugins was "
                    "just attempted and still didn't find it — check "
                    "that Markdown Dash is installed and enabled."
                ),
                parent=self.window,
            )
            return

        mod = self._pmgr.load_plugin(pdata)
        if not mod:
            OkDialog(
                _("Could not load Markdown Dash"),
                _(
                    "Markdown Dash is registered, but its module failed "
                    "to load, so this README can't be opened in its own "
                    "window."
                ),
                parent=self.window,
            )
            return

        open_markdown_file = getattr(mod, "open_markdown_file", None)
        if open_markdown_file is None:
            OkDialog(
                _("Markdown Dash is out of date"),
                _(
                    "The installed version of Markdown Dash doesn't "
                    "provide the open_markdown_file() function this "
                    "needs, so this README can't be opened in its own "
                    "window. Try updating Markdown Dash."
                ),
                parent=self.window,
            )
            return

        open_markdown_file(
            readme_path,
            self.uistate,
            parent=self.uistate.window,
            addon_name=addon_name,
        )

    def __hide(self, _obj: object, list_obj: Gtk.TreeView) -> None:
        """
        Deactivate (Hide) or Reactivate (unhide) the selected plugin.

        :param _obj: unused (button widget)
        :param list_obj: the plugin TreeView
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

    def __load(self, _obj: object, list_obj: Gtk.TreeView) -> None:
        """
        Dynamically load the selected plugin without restarting Gramps.

        :param _obj: unused (button widget)
        :param list_obj: the plugin TreeView
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

    def __install(self, _obj: object, _list_obj: object) -> None:
        """
        Install, update, or uninstall the selected plugin.

        :param _obj: unused (button widget)
        :param _list_obj: unused (kept for signal-handler signature compatibility)
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
        fname = None
        name = pid
        for addon in self.addons:
            if addon["i"] == pid:
                name = addon["n"]
                fname = addon["z"]
                break
        if not fname:
            return
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
        if pdata and (status & UPDATE) and pdata.ptype in (VIEW, GRAMPLET):
            self.restart_needed = True

    def __uninstall(self, pid: str, path: object) -> None:
        """
        Remove the files for an installed addon.

        :param pid: the plugin ID to uninstall
        :param path: the TreeView path to re-select after the rebuild
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
                _(
                    "Error removing the '%s' directory. "
                    "The uninstall may have failed."
                )
                % pdata.fpath,
                parent=self.window,
            )
        self.__rebuild_reg_list(path)
        self.restart_needed = True

    def __rebuild_reg_list(self, path: object = None, rescan: bool = True) -> None:
        """
        Clear and repopulate the plugin list model.

        :param path: TreePath to re-select after rebuild; ``None`` preserves
                     the currently selected row (falls back to row 0)
        :param rescan: when ``True`` re-scans the plugin directories first
        """
        if not hasattr(self, "_model_reg"):
            return
        # Capture current selection before clearing the model
        if path is None:
            _model, _node = self._selection_reg.get_selected()
            if _node:
                path = _model.get_path(_node)

        self._selection_reg.handler_block(self._cursor_hndlr)
        self._model_reg.clear()
        if rescan:
            CLIManager.do_reg_plugins(self, self.dbstate, self.uistate, rescan=True)
            self._set_update_btn_stale(False)
        self.__populate_reg_list()
        # See _force_row_height_recalc — the same row-height caching
        # quirk that affects the initial population applies here too,
        # since this also loads a full model's worth of fresh row
        # content.
        self._force_row_height_recalc()
        self._selection_reg.handler_unblock(self._cursor_hndlr)

        # Restore selection
        if path is None or (hasattr(path, "__len__") and len(str(path)) == 0):
            path = "0"
        try:
            self._selection_reg.select_path(path)
            if len(self._tree_filter):
                self._list_reg.scroll_to_cell(path, None, True, 0.5, 0)
                self._cursor_changed(None)
        except Exception:  # pylint: disable=broad-except
            self._selection_reg.select_path("0")
        self.__update_count_label()


class PluginManagerOptions(tool.ToolOptions):
    """
    Defines options and provides handling interface for Plugin Manager plus.
    """

    def __init__(self, name: str, person_id: str | None = None) -> None:
        """
        Initialise options with defaults.

        :param name: the tool name key used by the options framework
        :param person_id: optional person ID (unused, required by base class)
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
        }
