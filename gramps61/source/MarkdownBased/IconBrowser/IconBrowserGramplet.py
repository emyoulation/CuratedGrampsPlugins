# Gramps - a GTK+/GNOME based genealogy program
# Copyright (C) 2026 Brian McCullough
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

"""Icon Browser gramplet for the Gramps Dashboard.

Inventories every icon available in the current GTK / Gramps icon-theme cascade
(per the `freedesktop Icon Theme Specification`_) and presents them in a
two-pane browser.

Gramps icon inventory (media/gramps_icon_inventory.json)
----------------------------------------------------------
In addition to the live theme-cascade browse mode, this gramplet defaults to
a fast, small "Gramps" filter mode: the icons Gramps itself ships plus the
handful of system-theme icons its own GUI is known to use (typically ~150
total), rather than eagerly enumerating the user's entire OS icon theme
(which can run into the thousands and make the widget noticeably laggy).
That set is cached as JSON in this gramplet's own ``media`` folder, next to
this file. The full live cascade only loads lazily, on an explicit Reload
click or the first time a context other than "Gramps" is selected -- and
switching back to "Gramps" flushes that full list back out again, keeping
the gramplet's footprint small as much as reasonably possible. Building or
rebuilding the inventory file itself (a scan of Gramps' installed source,
not the OS theme) shows a small progress dialog and runs off the GTK main
thread, since it can take a perceptible moment. See
:func:`_build_full_gramps_icon_inventory` for how the icon set is
discovered, :meth:`IconBrowserGramplet._rebuild_inventory_async` for the
progress-dialog rebuild, and :func:`_write_gramps_icon_inventory` /
:func:`_read_gramps_icon_inventory` for the on-disk format.

Generated-by: Gemini 1.5 Pro / Ultra (Google, gemini-model-cascade, 2026-05)
Revised-by: Claude Sonnet 5 (Anthropic, claude-sonnet-5, 2026-09)
Revision prompt: "How should the Icon Browser gramplet create an inventory
file (in its media folder) of Gramps-bundled icons, in a format immediately
usable by the IconBrowser as a list of icons for a default 'Gramps' filter?"
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import datetime
import json
import logging
import os
import re
import shutil
import sys
import threading
from typing import Callable

# ------------------------
# GNOME/GTK+ modules
# ------------------------
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gio, Gtk, Pango

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import IMAGE_DIR
from gramps.gen.const import ROOT_DIR
from gramps.gen.plug import Gramplet
from gramps.gui.display import display_url

# ------------------------
# Gramps specific
# ------------------------
# MarkdownUtils lives one directory level above this plugin's folder.
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from MarkdownUtils import (
        NAMESPACE_MAP,
        VIEW_NAMES,
        build_table_widget,
        define_tags,
        parse_markdown,
        resolve_icon_pixbuf,
    )

    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False

try:
    _ = glocale.get_addon_translator(__file__).gettext
except (ValueError, AttributeError):
    _ = glocale.translation.gettext

LOG = logging.getLogger(__name__)

DETAIL_SIZES = [16, 22, 24, 32, 48, 64, 96, 128]
KNOWN_CONTEXTS = [
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
THUMB_SIZE = 16

COL_PIXBUF = 0
COL_NAME = 1
COL_IN_THEME = 2
COL_CONTEXT = 3
COL_IS_GRAMPS = 4

#: The three states the found/not-found column header cycles through on
#: each click (see ``_on_flag_header_clicked``): show everything, show
#: only icons that resolve in the current theme, or show only ones that
#: don't -- the last being the one that matters most for debugging.
FOUND_FILTER_ANY = 0
FOUND_FILTER_FOUND_ONLY = 1
FOUND_FILTER_NOT_FOUND_ONLY = 2

#: Combo-box id for the "only icons Gramps itself bundles" filter. Deliberately
#: distinct from every freedesktop context name in KNOWN_CONTEXTS so it can't
#: collide with a real context bucket.
GRAMPS_FILTER_ID = "Gramps"

#: Filename of the on-disk inventory, written under this gramplet's own
#: ``media`` folder (see :func:`_gramplet_media_dir`).
INVENTORY_FILENAME = "gramps_icon_inventory.json"

#: Bumped only if the on-disk JSON structure changes incompatibly; lets
#: :func:`_read_gramps_icon_inventory` reject a stale file from an older
#: version of this gramplet instead of trusting a mismatched shape. Version
#: 2 added the "bundled" field and the icons Gramps *uses* from the host
#: OS/GTK theme, on top of version 1's hicolor-only asset list.
INVENTORY_SCHEMA_VERSION = 2

#: Maps a `hicolor/<size>/<context-dir>` folder name to the same freedesktop
#: context labels already used for the live theme cascade (KNOWN_CONTEXTS),
#: so a Gramps-bundled icon's context reads the same way whichever path
#: found it. Gramps' own "source" folder (pre-rendered SVG originals for a
#: couple of multi-size icons) isn't a real freedesktop context; it's folded
#: into "Actions" since every icon stored there is an action/view icon.
_HICOLOR_CONTEXT_MAP = {
    "actions": "Actions",
    "apps": "Apps",
    "mimetypes": "MimeTypes",
    "source": "Actions",
}

#: Regex patterns matching the ways Gramps' own GUI source asks for an icon
#: by name. Each has exactly one capture group: the icon name. These mirror
#: the manual `grep` passes used to build the accompanying
#: ``gramps_icon_inventory.md`` reference doc -- reimplemented here in pure
#: Python so this gramplet can regenerate the same result at runtime,
#: against whatever Gramps version is actually installed.
_ICON_NAME_SOURCE_PATTERNS = [
    re.compile(r'icon-name">([A-Za-z0-9_.-]+)<'),  # Glade UI XML property
    re.compile(r'new_from_icon_name\(\s*["\']([A-Za-z0-9_.-]+)["\']'),
    re.compile(r'SimpleButton\(\s*["\']([A-Za-z0-9_.-]+)["\']'),  # editors/displaytabs
    re.compile(
        r'stock_icon\s*=\s*["\']([A-Za-z0-9_.-]+)["\']'
    ),  # .gpr.py registrations
]

#: Subdirectories of the installed Gramps package worth scanning for icon
#: names: the desktop GUI proper, and the view/gramplet/report plugins that
#: register their own ``stock_icon=``. Deliberately excludes ``gen`` (the
#: headless core, which never touches GTK) to keep the scan fast.
_ICON_SOURCE_SUBDIRS = ("gui", "plugins")

#: File extensions worth grepping for icon-name references.
_ICON_SOURCE_EXTS = (".py", ".glade")


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


#: ``(path-prefix, url)`` rules mapping a resolved icon path to its
#: browsable *remote* source repository -- used only for the "View icon
#: source online" right-click menu item (see
#: :meth:`IconBrowserGramplet._on_label_populate_popup`), not for the
#: inline path hyperlink itself (see :func:`_linkify_path`). Most-specific
#: prefix first; the first match wins.
#:
#: - GTK's own compiled-in fallback icon resources. When
#:   :meth:`Gtk.IconInfo.get_filename` resolves an icon loaded via the
#:   ``USE_BUILTIN`` lookup flag, some GTK builds report a GResource-style
#:   virtual path such as ``/org/gtk/libgtk/icons/24x24/actions/
#:   gtk-index.png`` rather than a real file on disk -- there's no local
#:   folder to open for these at all, so the remote source link is the
#:   *only* way to reach anything for them.
#: - Gramps' own bundled ``IMAGE_DIR`` tree, linking back to the same file
#:   in the Gramps GitHub repo (appended right below, once ``IMAGE_DIR``
#:   is known). These *do* also have a real local folder, so they get both
#:   the inline local-folder link and this remote-source menu item.
_REMOTE_SOURCE_LINKS: list[tuple[str, str]] = [
    (
        "/org/gtk/libgtk/icons/",
        "https://gitlab.gnome.org/GNOME/gtk/-/tree/gtk-3-24/gtk/theme",
    ),
]
if IMAGE_DIR:
    _gramps_images_prefix = os.path.join(IMAGE_DIR, "")  # ensure trailing sep
    _REMOTE_SOURCE_LINKS.append(
        (
            _gramps_images_prefix,
            "https://github.com/gramps-project/gramps/tree/master/gramps/images",
        )
    )


def _remote_source_url(path: str) -> str | None:
    """Return the browsable remote-source URL for *path*, if any is known.

    :param path: Absolute filesystem path or GResource-style resource path,
        as returned by :meth:`Gtk.IconInfo.get_filename`.
    :returns: A URL from :data:`_REMOTE_SOURCE_LINKS` whose prefix matches
        *path*, or ``None`` if no mapping is known for it.
    """
    for prefix, url in _REMOTE_SOURCE_LINKS:
        if path.startswith(prefix):
            return url
    return None


#: URI scheme prefix for the "insert an override icon here" link, handled
#: by :meth:`IconBrowserGramplet._on_activate_link` alongside real
#: ``file://`` and ``https://`` links. Not a real URI scheme GIO or a
#: browser would understand -- purely an internal signal, parsed back out
#: of the label's own markup, so one shared ``activate-link`` handler can
#: still dispatch it correctly.
_OVERRIDE_URI_PREFIX = "gramps-icon-override:"


def _context_from_resource_path(path: str, default: str = "actions") -> str:
    """Best-effort extraction of the freedesktop context folder from a
    GResource-style icon path.

    For a path like ``/org/gtk/libgtk/icons/24x24/actions/gtk-index.png``,
    the segment right after the size directory (``actions`` here) is
    exactly the freedesktop context folder that same icon would need to
    sit under in a real icon theme -- so a per-user override for this
    icon should mirror that same context, rather than guessing.

    :param path: A GResource-style path such as
        ``/org/gtk/libgtk/icons/<size>/<context>/<name>.<ext>``.
    :param default: Context to fall back to if *path* doesn't match that
        shape (e.g. an unexpected GResource layout from some other app).
    :returns: The context folder name, e.g. ``"actions"``.
    """
    parts = [p for p in path.split("/") if p]
    if "icons" in parts:
        idx = parts.index("icons")
        if len(parts) > idx + 2:
            return parts[idx + 2]
    return default


def _user_icon_override_dir(context: str) -> str:
    """Return the per-user ``hicolor`` override folder for *context*.

    Mirrors the same freedesktop directory layout Gramps' own bundled
    icons use (``hicolor/scalable/<context>/<name>.svg``), just rooted
    under the user's own XDG data directory -- e.g.
    ``~/.local/share/icons/hicolor/scalable/actions`` on Linux -- rather
    than the Gramps installation, which the user typically can't write to
    without elevated privileges. ``GLib.get_user_data_dir()`` resolves the
    XDG-correct base on each platform (``$XDG_DATA_HOME`` or
    ``~/.local/share`` on Linux, ``%APPDATA%`` on Windows, and so on),
    matching exactly what GTK's own icon-theme cascade already scans by
    default -- no Gramps-specific configuration is needed for a file
    placed here to be found.

    :param context: Freedesktop context folder name, e.g. ``"actions"``.
    :returns: Absolute path to the (not-yet-necessarily-existing) override
        folder.
    """
    base = GLib.get_user_data_dir()
    return os.path.join(base, "icons", "hicolor", "scalable", context)


def _linkify_path(path: str, icon_name: str) -> str:
    """Return Pango markup for *path*, hyperlinking its containing folder.

    When *path* corresponds to a real, existing file on disk, the folder
    portion of the displayed text becomes a clickable ``file://`` link to
    that folder -- e.g. for
    ``/usr/share/icons/Adwaita/scalable/actions/list-add-symbolic.svg``,
    only the ``/usr/share/icons/Adwaita/scalable/actions/`` portion is
    linked, with the bare filename shown as plain text right after it, so
    clicking takes you straight to where the icon actually lives locally.

    GResource-only paths -- most notably GTK's own compiled-in fallback
    icons under ``/org/gtk/libgtk/icons/...`` -- don't correspond to a
    real file or folder at all: the actual pixel data for those is
    compiled directly into ``libgtk`` itself (via ``glib-compile-
    resources`` at GTK's build time) and only ever exists as bytes inside
    that binary, never as a loose file anywhere on the filesystem. There
    genuinely is no folder to open for these, so rather than silently
    showing plain text with no explanation (which reads as "this browser
    couldn't find it" rather than "there is nothing local to find"), a
    short note is appended saying so, plus a second link that opens a
    native file dialog rooted at exactly the per-user folder
    (:func:`_user_icon_override_dir`) where a hand-picked SVG for
    *icon_name* would need to go to actually override it -- see
    :meth:`IconBrowserGramplet._open_icon_override_dialog`. Their remote
    source, when one is known, is still reachable separately via the
    label's right-click "View icon source online" menu item (see
    :meth:`IconBrowserGramplet._on_label_populate_popup`).

    Any label showing this markup must also
    ``connect("activate-link", ...)`` -- see
    :meth:`IconBrowserGramplet._on_activate_link`.

    :param path: Absolute filesystem path or GResource-style resource path,
        as returned by :meth:`Gtk.IconInfo.get_filename`.
    :param icon_name: The icon name actually being looked up (not
        necessarily reflected in *path* itself, e.g. for a fallback-
        cascade row), used both as the suggested override filename and to
        build the ``gramps-icon-override:`` link's payload.
    :returns: Pango markup string, safe to pass to
        :meth:`Gtk.Label.set_markup`.
    """
    folder = os.path.dirname(path) if path else ""
    if path and os.path.isfile(path) and os.path.isdir(folder):
        folder_text = folder + os.sep
        # GLib.filename_to_uri percent-encodes spaces and other special
        # characters correctly; naive "file://" + folder string
        # concatenation breaks for any folder path containing them.
        file_uri = GLib.filename_to_uri(folder)
        return '<a href="{}" title="{}">{}</a>{}'.format(
            _esc(file_uri),
            _esc(folder),
            _esc(folder_text),
            _esc(os.path.basename(path)),
        )
    if path.startswith("/org/gtk/") or path.startswith("/org/gnome/"):
        context = _context_from_resource_path(path)
        override_uri = "{}{}:{}".format(_OVERRIDE_URI_PREFIX, icon_name, context)
        note = _(
            " (compiled into GTK itself \u2014 no local file exists; "
            "right-click for the online source, or "
        )
        link_text = _("open where an override SVG goes")
        tail = _(")")
        return (
            "{path}<span foreground='#999999'><i>{note}"
            '<a href="{href}">{link_text}</a>{tail}</i></span>'
        ).format(
            path=_esc(path),
            note=_esc(note),
            href=_esc(override_uri),
            link_text=_esc(link_text),
            tail=_esc(tail),
        )
    return _esc(path)


def _load_pixbuf(icon_theme: Gtk.IconTheme, name: str, size: int):
    flags = Gtk.IconLookupFlags.GENERIC_FALLBACK | Gtk.IconLookupFlags.USE_BUILTIN
    try:
        return icon_theme.load_icon(name, size, flags)
    except Exception:
        return None


def _load_pixbuf_with_stock_fallback(
    widget: Gtk.Widget, icon_theme: Gtk.IconTheme, name: str, size: int
):
    """Load *name*, falling back to GTK's legacy stock-icon table if needed.

    A handful of icon names Gramps' own source still references --
    ``gtk-edit``, ``gtk-index`` -- are GTK2-era ``Gtk.STOCK_*`` constants,
    not freedesktop icon-theme names, so :func:`_load_pixbuf` (which only
    consults :class:`Gtk.IconTheme`) correctly returns ``None`` for them
    even though GTK itself can still render them via its deprecated-but-
    functional stock-icon compatibility path
    (:meth:`Gtk.Widget.render_icon_pixbuf`). This tries the normal theme
    lookup first and only reaches for that compatibility path as a
    fallback, so it costs nothing for the overwhelming majority of names
    that resolve normally.

    :param widget: Any realized widget to render through (stock-icon
        rendering is a widget-context operation in GTK3's API, though the
        result doesn't depend on which widget is passed).
    :param name: GTK or Gramps icon name.
    :param size: Desired pixel size.
    :returns: A pixbuf, or ``None`` if neither mechanism can resolve *name*.
    """
    pb = _load_pixbuf(icon_theme, name, size)
    if pb is not None:
        return pb
    try:
        return widget.render_icon_pixbuf(name, Gtk.IconSize.SMALL_TOOLBAR)
    except Exception:
        return None


# ---------------------------------------------------------------------------
#
# Gramps-bundled icon inventory
#
# ---------------------------------------------------------------------------
def _gramplet_dir() -> str:
    """Return the folder containing this gramplet's own source file.

    :returns: Absolute path to the directory holding
        ``IconBrowserGramplet.py`` itself.
    """
    return os.path.dirname(os.path.abspath(__file__))


def _gramplet_media_dir() -> str:
    """Return this gramplet's ``media`` folder, creating it if needed.

    Every Gramps add-on folder is free to keep its own resource
    subdirectory alongside the plugin's ``.py``/``.gpr.py`` files; this
    gramplet uses ``media`` for its generated icon inventory so the file
    travels with the add-on (and survives a Gramps upgrade) rather than
    living under the user's profile directory.

    :returns: Absolute path to ``<gramplet-folder>/media``.
    """
    media_dir = os.path.join(_gramplet_dir(), "media")
    os.makedirs(media_dir, exist_ok=True)
    return media_dir


def _gramplet_media_icons_dir() -> str:
    """Return this gramplet's ``media/icons`` folder, creating it if needed.

    Used as the *starting* browse location in
    :meth:`IconBrowserGramplet._open_icon_override_dialog`'s file picker
    -- a place a curated set of candidate replacement icons can be kept
    (dropped there once, e.g. alongside installing this add-on) so the
    picker opens somewhere with something in it, rather than at the
    destination override folder, which is typically still empty the
    first time this is used. The file still gets *copied to* the correct
    per-user ``hicolor`` override folder regardless of where it was
    picked from.

    :returns: Absolute path to ``<gramplet-folder>/media/icons``.
    """
    icons_dir = os.path.join(_gramplet_media_dir(), "icons")
    os.makedirs(icons_dir, exist_ok=True)
    return icons_dir


#: Filename of the icon-override installation log, written directly in
#: this gramplet's own folder (next to ``IconBrowserGramplet.py`` itself,
#: not under ``media/``) so it's easy to find alongside the code -- see
#: :func:`_log_icon_override`.
_OVERRIDE_LOG_FILENAME = "icon_overrides.log"


def _log_icon_override(icon_name: str, dest_path: str) -> None:
    """Append a timestamped record of an installed icon override.

    Writes one line per installed override to ``icon_overrides.log`` in
    this gramplet's own folder -- a durable, human-readable, append-only
    record kept separate from Gramps' own (much noisier) application log,
    so it's easy to later answer "which icons did I override, and when"
    without digging through general log output.

    :param icon_name: The icon name the override was installed for.
    :param dest_path: Absolute path of the file that was written.
    """
    log_path = os.path.join(_gramplet_dir(), _OVERRIDE_LOG_FILENAME)
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    line = "{timestamp}\ticon={icon_name}\tpath={dest_path}\n".format(
        timestamp=timestamp, icon_name=icon_name, dest_path=dest_path
    )
    try:
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        LOG.exception("Could not write to icon override log at %s", log_path)


def _scan_gramps_bundled_icons() -> list[dict]:
    """Walk Gramps' own bundled ``hicolor`` icon-theme tree.

    Every icon Gramps ships with itself lives under
    ``IMAGE_DIR/hicolor/<size-or-scalable>/<context>/<name>.<ext>`` -- the
    same tree ``gramps/gui/grampsgui.py`` registers as a
    :class:`Gtk.IconTheme` search path at application start. Walking this
    tree directly, rather than hardcoding a name list in this add-on, means
    the inventory always matches whatever Gramps version is actually
    installed, including icons added, renamed, or removed by future
    releases -- the add-on never goes stale against its host application.

    Also includes the single "gramps" application icon
    (``IMAGE_DIR/gramps.svg``/``.png``): a genuine bundled Gramps asset, but
    one that lives at the root of ``IMAGE_DIR`` rather than under
    ``hicolor/``, resolved via GTK's icon-theme fallback lookup rather than
    the normal ``<size>/<context>`` structure (see the About dialog's
    ``icon-name="gramps"`` in ``gui/grampsgui.py``).

    :returns: List of ``{"name": str, "context": str, "path": str,
        "bundled": True}`` dicts, one per distinct icon name, sorted
        case-insensitively by name. When both a ``scalable`` SVG and a
        raster fallback exist for a name, the SVG's relative path is kept.
    """
    found: dict[str, dict] = {}

    hicolor_dir = os.path.join(IMAGE_DIR, "hicolor")
    if os.path.isdir(hicolor_dir):
        for root, _dirs, files in os.walk(hicolor_dir):
            parts = root.split(os.sep)
            try:
                idx = parts.index("hicolor")
            except ValueError:
                continue
            size_dir = parts[idx + 1] if len(parts) > idx + 1 else ""
            subdir = parts[idx + 2] if len(parts) > idx + 2 else ""
            context = _HICOLOR_CONTEXT_MAP.get(subdir.lower(), "Other")
            is_scalable = size_dir == "scalable"

            for fname in files:
                name, ext = os.path.splitext(fname)
                if ext.lower() not in (".svg", ".png"):
                    continue
                rel_path = os.path.relpath(os.path.join(root, fname), IMAGE_DIR)
                rel_path = rel_path.replace(os.sep, "/")
                existing = found.get(name)
                if existing is None or (is_scalable and not existing["_scalable"]):
                    found[name] = {
                        "name": name,
                        "context": context,
                        "path": rel_path,
                        "bundled": True,
                        "_scalable": is_scalable,
                    }

    for entry in found.values():
        del entry["_scalable"]

    # The single root-level "gramps" application icon: not under hicolor/,
    # so the walk above never sees it, but it's a real bundled asset (used
    # for the About dialog's window icon) and belongs in the inventory.
    if "gramps" not in found:
        for ext in (".svg", ".png"):
            root_icon = os.path.join(IMAGE_DIR, "gramps" + ext)
            if os.path.isfile(root_icon):
                found["gramps"] = {
                    "name": "gramps",
                    "context": "Apps",
                    "path": "gramps" + ext,
                    "bundled": True,
                }
                break

    return sorted(found.values(), key=lambda entry: entry["name"].casefold())


def _scan_system_theme_icons_used_by_gramps(
    bundled_names: set[str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Find icon names Gramps' GUI *uses* but does not ship itself.

    A number of icons referenced throughout the Gramps GUI -- the
    Add/Edit/Remove/Move/Jump buttons on every editor tab, the Note-tab
    rich-text formatting toolbar, assorted dialog icons -- are plain
    freedesktop/GTK icon-theme names (``list-add``, ``format-text-bold``,
    ``dialog-warning``, ...) resolved from whatever icon theme is installed
    on the user's system (typically Adwaita), not from a file Gramps ships.
    They're still icons someone browsing "the icons Gramps uses" would
    reasonably expect to find, so this scans the *installed* Gramps
    package's own GUI source for the same handful of call patterns used to
    build the reference ``gramps_icon_inventory.md`` doc, and returns
    whichever names aren't already accounted for by
    :func:`_scan_gramps_bundled_icons`.

    This is the slow part of a full inventory rebuild (reading every
    ``.py``/``.glade`` file under ``gui/`` and ``plugins/``), so it takes
    an optional progress callback rather than being expected to run
    instantly -- see :meth:`IconBrowserGramplet._rebuild_inventory_async`,
    which runs this off the GTK main thread specifically because of this
    cost.

    :param bundled_names: Names already found as genuine Gramps assets, so
        this function doesn't re-report ``gramps-font-color`` and similar
        names that happen to appear in the same source files.
    :param progress_cb: Optional callback invoked as
        ``progress_cb(files_done, files_total)`` after each source file is
        read, so a caller can drive a progress bar. Never called with
        ``files_total == 0``.
    :returns: List of ``{"name": str, "context": "System", "path": None,
        "bundled": False}`` dicts, sorted case-insensitively by name.
    """
    files_to_scan: list[str] = []
    for subdir in _ICON_SOURCE_SUBDIRS:
        base = os.path.join(ROOT_DIR, subdir)
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fname in files:
                if fname.endswith(_ICON_SOURCE_EXTS):
                    files_to_scan.append(os.path.join(root, fname))

    total = len(files_to_scan)
    found: set[str] = set()
    for done, fpath in enumerate(files_to_scan, start=1):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
        except OSError:
            text = ""
        for pattern in _ICON_NAME_SOURCE_PATTERNS:
            found.update(pattern.findall(text))
        if progress_cb is not None and total:
            progress_cb(done, total)

    return [
        {"name": name, "context": "System", "path": None, "bundled": False}
        for name in sorted(found, key=str.casefold)
        if name not in bundled_names
    ]


def _build_full_gramps_icon_inventory(
    progress_cb: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Combine the bundled-asset scan and the system-theme-usage scan.

    :param progress_cb: Optional progress callback, forwarded to
        :func:`_scan_system_theme_icons_used_by_gramps` (the slower half
        of this combined scan).
    :returns: The full icon list this gramplet writes to
        ``media/gramps_icon_inventory.json`` -- every icon Gramps ships
        itself, plus every additional icon name its own GUI source asks
        the system theme for.
    """
    bundled = _scan_gramps_bundled_icons()
    bundled_names = {entry["name"] for entry in bundled}
    system_only = _scan_system_theme_icons_used_by_gramps(bundled_names, progress_cb)
    return sorted(bundled + system_only, key=lambda entry: entry["name"].casefold())


def _write_gramps_icon_inventory(icons: list[dict]) -> str:
    """Serialize *icons* to this gramplet's media-folder inventory file.

    The format is a small, dependency-free JSON document -- readable by
    this gramplet, by any other Gramps add-on, or by a human with a text
    editor -- rather than a pickle or a Gramps-specific config format, so
    nothing beyond the standard library is needed to produce or consume it.

    :param icons: List of icon dicts as returned by
        :func:`_build_full_gramps_icon_inventory`.
    :returns: Absolute path of the file written.
    :raises OSError: if the file could not be written.
    """
    from gramps.version import VERSION

    payload = {
        "schema": INVENTORY_SCHEMA_VERSION,
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "gramps_version": VERSION,
        "source": "IMAGE_DIR/hicolor + gui|plugins icon-name usage scan",
        "icons": icons,
    }
    path = os.path.join(_gramplet_media_dir(), INVENTORY_FILENAME)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return path


def _read_gramps_icon_inventory() -> list[dict] | None:
    """Load a previously written inventory file, if present and valid.

    :returns: The ``icons`` list from the file, or ``None`` if the file is
        missing, unreadable, or was written by an incompatible schema
        version -- any of which should trigger a fresh
        :func:`_scan_gramps_bundled_icons` rather than trusting bad data.
    """
    path = os.path.join(_gramplet_media_dir(), INVENTORY_FILENAME)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        LOG.warning("Could not read Gramps icon inventory at %s", path)
        return None
    if payload.get("schema") != INVENTORY_SCHEMA_VERSION:
        return None
    return payload.get("icons") or []


class IconBrowserGramplet(Gramplet):
    """Dashboard gramplet: live GTK/Gramps icon-theme browser."""

    def on_load(self):
        pass

    def on_unload(self):
        # Set first: every progress-driven callback below checks this and
        # bails out harmlessly rather than touching a widget that may be
        # mid-teardown by the time it next runs.
        self._shutting_down = True

        if getattr(self, "_theme_handler_id", None) is not None:
            try:
                settings = Gtk.Settings.get_default()
                if settings is not None:
                    settings.disconnect(self._theme_handler_id)
            except Exception:
                pass
        self._theme_handler_id = None

        if getattr(self, "_search_timeout_id", None) is not None:
            GLib.source_remove(self._search_timeout_id)
            self._search_timeout_id = None

        if getattr(self, "_idle_inspector_id", None) is not None:
            GLib.source_remove(self._idle_inspector_id)
            self._idle_inspector_id = None

        # A full-cascade reload (chunked GLib.idle_add batches) or an
        # inventory rebuild (GLib.timeout_add polling a background
        # thread) may still be in flight when the gramplet is unloaded --
        # e.g. the person closes the Dashboard or removes this gramplet
        # mid-reload. Leaving that source registered means its callback
        # fires again later against widgets GTK has since destroyed,
        # producing exactly the "assertion 'GTK_IS_WIDGET (widget)'
        # failed" console criticals this once caused: cancel it and
        # destroy any dialog it left on screen.
        if getattr(self, "_progress_source_id", None) is not None:
            GLib.source_remove(self._progress_source_id)
            self._progress_source_id = None

        if getattr(self, "_progress_dialog", None) is not None:
            try:
                self._progress_dialog.destroy()
            except Exception:
                pass
            self._progress_dialog = None

    def init(self):
        gramps_sw = self.gui.get_container_widget()
        for child in gramps_sw.get_children():
            gramps_sw.remove(child)

        self._search_timeout_id = None
        self._idle_inspector_id = None
        #: Set by :meth:`on_unload`; every progress-driven idle/timeout
        #: callback (:meth:`_refresh_full`'s batch processor,
        #: :meth:`_rebuild_inventory_async`'s poll tick) checks this first
        #: and does nothing further if it's ``True``, since the widgets it
        #: would otherwise touch may already be gone.
        self._shutting_down = False
        #: GLib source id of whichever progress-driven idle/timeout loop
        #: is currently running, if any, so :meth:`on_unload` can cancel
        #: it. Only one such operation is ever active at a time in this
        #: gramplet.
        self._progress_source_id: int | None = None
        #: The currently-open progress dialog, if any, so
        #: :meth:`on_unload` can destroy it if the gramplet is torn down
        #: mid-operation.
        self._progress_dialog: Gtk.Dialog | None = None
        #: Names covered by the Gramps icon inventory, backing the
        #: "Gramps" filter; populated by :meth:`_rebuild_inventory_async`
        #: (build/rebuild path) or read directly from the cache file via
        #: :meth:`_get_cached_gramps_icon_names` (fast startup path -- see
        #: :meth:`_refresh_gramps_only`).
        self._gramps_icon_names: set[str] = set()
        #: Whether ``self._store`` currently holds the full live
        #: icon-theme cascade (thousands of icons) rather than just the
        #: Gramps inventory subset (typically ~150). Starts ``False``;
        #: flips to ``True`` the first time a full scan actually runs
        #: (explicit Reload, first switch away from the "Gramps" filter,
        #: or no cached inventory file existing yet at startup).
        self._full_list_loaded = False
        #: Name of the icon currently shown in the detail pane, if any --
        #: set by :meth:`_populate_detail`, read by
        #: :meth:`_open_icon_override_dialog` to decide whether an
        #: install needs to also refresh that pane.
        self._current_icon_name: str | None = None

        inner_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        browser_content = self._build_browser_content()
        footer_box = self._build_footer()

        inner_vbox.pack_start(browser_content, True, True, 0)
        inner_vbox.pack_end(Gtk.Separator(), False, False, 0)
        inner_vbox.pack_end(footer_box, False, False, 0)

        gramps_sw.add(inner_vbox)
        self.gui.WIDGET = inner_vbox
        inner_vbox.show_all()

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b".mono-text { font-family: monospace; }")
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        settings = Gtk.Settings.get_default()
        if settings is not None:
            self._theme_handler_id = settings.connect(
                "notify::gtk-theme-name", self._on_theme_changed
            )
        else:
            self._theme_handler_id = None

        GLib.idle_add(self._initial_refresh_idle)

    def _initial_refresh_idle(self):
        """Startup population: always ends up on the fast Gramps-only path.

        If a cached ``media/gramps_icon_inventory.json`` already exists,
        the gramplet opens showing just that (typically ~150 icons)
        instead of enumerating the entire live icon-theme cascade (which
        can run into the thousands and makes the whole widget noticeably
        laggy to open and scroll). The full cascade loads lazily instead,
        only on demand -- see :meth:`_on_context_changed` and
        :meth:`_on_refresh_clicked`.

        On a genuinely first run, with no inventory file yet, there is no
        fast subset to show yet either -- but the fix for that is to
        *build* the inventory (via :meth:`_rebuild_inventory_async`, with
        its own progress dialog for what can be a non-trivial source-tree
        scan), not to fall back to the far larger full cascade. Once the
        file exists, this still opens on the small Gramps-only set, same
        as every subsequent startup: the gramplet stays small as much as
        it reasonably can, even on its very first run.
        """
        cached_names = self._get_cached_gramps_icon_names()
        if cached_names is not None:
            self._refresh_gramps_only()
        else:
            self._rebuild_inventory_async(lambda _names: self._refresh_gramps_only())
        return False

    def _build_footer(self):
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
        refresh_btn.set_tooltip_text(
            _("Reload the full icon list (scans every icon in the current theme)")
        )
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        footer.pack_end(refresh_btn, False, False, 0)

        return footer

    def _build_browser_content(self):
        content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top_bar.set_border_width(4)
        top_bar.pack_start(Gtk.Label(label=_("Search:")), False, False, 0)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(_("filter icon names…"))
        self._search_entry.set_hexpand(True)
        self._search_entry.connect("search-changed", self._on_search_changed)
        top_bar.pack_start(self._search_entry, True, True, 0)

        self._ctx_combo = Gtk.ComboBoxText()
        self._ctx_combo.append("*", _("All"))
        self._ctx_combo.append(GRAMPS_FILTER_ID, _("Gramps"))
        for ctx in KNOWN_CONTEXTS:
            self._ctx_combo.append(ctx, ctx)
        self._ctx_combo.append("Other", _("Other"))
        self._ctx_combo.set_active_id(GRAMPS_FILTER_ID)
        self._ctx_combo.connect("changed", self._on_context_changed)
        top_bar.pack_start(self._ctx_combo, False, False, 0)

        # Rebuilding the "Gramps" filter's backing inventory means walking
        # the installed Gramps package's source tree -- real, if brief,
        # filesystem work -- so it's a deliberate, occasional action next
        # to the filter drop-down it feeds, not something re-run on every
        # gramplet startup (see _rebuild_inventory_async, which shows a
        # progress dialog for this).
        rebuild_btn = Gtk.Button()
        rebuild_img = Gtk.Image.new_from_icon_name(
            "view-refresh-symbolic", Gtk.IconSize.SMALL_TOOLBAR
        )
        rebuild_btn.set_image(rebuild_img)
        rebuild_btn.set_relief(Gtk.ReliefStyle.NONE)
        rebuild_btn.set_tooltip_text(
            _(
                "Rebuild the \u201cGramps\u201d filter's icon list "
                "(media/{filename}). Only needed occasionally, e.g. "
                "after a Gramps upgrade."
            ).format(filename=INVENTORY_FILENAME)
        )
        rebuild_btn.connect("clicked", self._on_rebuild_gramps_inventory_clicked)
        top_bar.pack_start(rebuild_btn, False, False, 0)

        content_vbox.pack_start(top_bar, False, False, 0)
        content_vbox.pack_start(Gtk.Separator(), False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)

        def _set_initial_split(widget, allocation):
            widget.set_position(allocation.width // 2)
            widget.disconnect(handler_id)

        handler_id = paned.connect("size-allocate", _set_initial_split)

        self._store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, bool, str, bool)
        self._filter = self._store.filter_new()
        self._filter.set_visible_func(self._row_visible)
        self._sort_model = Gtk.TreeModelSort(model=self._filter)
        self._sort_model.set_sort_func(COL_NAME, self._sort_by_name, None)

        #: Cycling filter state for the found/not-found column, advanced
        #: by clicking its header (see :meth:`_on_flag_header_clicked`):
        #: ``FOUND_FILTER_ANY`` (no filtering -- the initial state),
        #: ``FOUND_FILTER_FOUND_ONLY``, ``FOUND_FILTER_NOT_FOUND_ONLY``,
        #: then back to ``FOUND_FILTER_ANY``. Chosen over making that
        #: column *sortable* (which was the first approach here) because
        #: for the actual use case -- finding every broken icon during
        #: debugging -- hiding the found rows entirely beats merely
        #: reordering them to one end of a still-mixed list.
        self._found_filter_state = FOUND_FILTER_ANY

        self._tree = Gtk.TreeView(model=self._sort_model)
        self._tree.get_selection().connect("changed", self._on_selection_changed)
        # Per-row tooltips on the found/not-found flag column (see
        # _on_tree_query_tooltip); header tooltips are set directly on
        # each column's header button below instead, since GtkTreeView
        # tooltips are row-based, not header-based.
        self._tree.set_has_tooltip(True)
        self._tree.connect("query-tooltip", self._on_tree_query_tooltip)

        rend_flag = Gtk.CellRendererText()
        col_flag = Gtk.TreeViewColumn("", rend_flag)
        col_flag.set_cell_data_func(rend_flag, self._render_flag_cell)
        col_flag.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_flag.set_fixed_width(28)
        col_flag.set_clickable(True)
        col_flag.connect("clicked", self._on_flag_header_clicked)
        self._tree.append_column(col_flag)
        self._flag_column = col_flag  # identity check in the tooltip handler

        rend_pb = Gtk.CellRendererPixbuf()
        col_thumb = Gtk.TreeViewColumn("", rend_pb, pixbuf=COL_PIXBUF)
        col_thumb.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        col_thumb.set_fixed_width(24)
        self._tree.append_column(col_thumb)

        rend_txt = Gtk.CellRendererText()
        col_name = Gtk.TreeViewColumn(_("Icon Name"), rend_txt, text=COL_NAME)
        col_name.set_sort_column_id(COL_NAME)
        col_name.set_expand(True)
        self._tree.append_column(col_name)

        # Explicit header tooltips -- set directly on each column's own
        # header button widget (only reachable via get_button(), a
        # TreeViewColumn's title isn't itself a widget with a tooltip
        # API). This also happens to replace whatever generic default
        # GTK/accessibility tooltip a clickable, otherwise-undocumented
        # header button would otherwise fall back to showing.
        self._update_flag_header()  # sets its initial title + tooltip
        col_thumb.get_button().set_tooltip_text(_("A small live preview of the icon."))
        col_name.get_button().set_tooltip_text(
            _("The icon's name, as looked up in code. Click to sort alphabetically.")
        )

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

    def _refresh_full(self):
        """Populate the store from the entire live icon-theme cascade.

        This is the expensive path -- ``icon_theme.list_icons(None)`` can
        return several thousand names, each needing its own pixbuf load
        and a ``Gtk.ListStore`` row -- so it's only run on an explicit
        Reload click or the first time a context other than "Gramps" is
        selected. Unlike the inventory rebuild, this can't be moved to a
        background thread: loading icon pixbufs and mutating the list
        store are both GTK/GDK operations, safe only on the main thread.
        Instead, this processes the icon list in small batches via
        repeated ``GLib.idle_add`` calls, showing a real (determinate,
        since the total count is known up front) progress bar and letting
        the main loop breathe between batches -- so this no longer just
        freezes the gramplet for however long a multi-thousand-icon scan
        takes, which was the original complaint that led to the
        "Gramps"-filter fast path in the first place.

        By the time this can run at all, startup
        (:meth:`_initial_refresh_idle`) has already ensured the inventory
        file exists, so this only ever needs a cheap cached read, never a
        rebuild, to know which rows are "Gramps" ones.
        """
        self._store.clear()
        self._clear_detail()
        self._full_list_loaded = True

        icon_theme = Gtk.IconTheme.get_default()

        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:
            gtk_theme = gtk_settings.get_property("gtk-theme-name") or ""
            self._theme_label.set_markup(
                "<span foreground='#555555'><b>{}</b> {}</span>".format(
                    _("Theme:"), _esc(gtk_theme)
                )
            )

        all_names = sorted(icon_theme.list_icons(None) or [], key=str.casefold)
        name_to_ctx = {}
        for ctx in KNOWN_CONTEXTS:
            for name in icon_theme.list_icons(ctx) or []:
                if name not in name_to_ctx:
                    name_to_ctx[name] = ctx

        theme_dirs = set(icon_theme.get_search_path() or [])
        # Cheap cached read only -- never generates the inventory here.
        # In the ordinary flow the file already exists by the time this
        # can run (see _initial_refresh_idle); if it somehow doesn't yet,
        # rows just show as not-Gramps until the next rebuild rather than
        # popping a second progress dialog mid-refresh.
        cached_names = self._get_cached_gramps_icon_names()
        self._gramps_icon_names = cached_names if cached_names is not None else set()

        total = len(all_names)
        if total == 0:
            self._update_count_label()
            self._filter.refilter()
            return

        dialog, progress = self._build_progress_dialog(
            _("Loading Icon Theme"),
            _("Loading every icon in the current theme\u2026"),
        )

        batch_size = 200
        state = {"index": 0}

        def _process_batch() -> bool:
            if self._shutting_down:
                return False

            start = state["index"]
            end = min(start + batch_size, total)
            for i in range(start, end):
                name = all_names[i]
                ctx = name_to_ctx.get(name, "Other")
                pb = _load_pixbuf(icon_theme, name, THUMB_SIZE)

                info = icon_theme.lookup_icon(name, 22, 0)
                in_theme = False
                if info is not None:
                    fn = info.get_filename() or ""
                    in_theme = any(fn.startswith(d) for d in theme_dirs)

                is_gramps = name in self._gramps_icon_names
                self._store.append([pb, name, in_theme, ctx, is_gramps])
            state["index"] = end

            progress.set_fraction(end / total)
            progress.set_text(
                _("{done} of {total} icons").format(done=end, total=total)
            )

            if end < total:
                return True  # more batches to go -- keep this idle source

            dialog.destroy()
            self._progress_dialog = None
            self._progress_source_id = None
            self._update_count_label()
            self._filter.refilter()
            GLib.idle_add(self._select_default_icon, "gramps-view")
            return False

        self._progress_source_id = GLib.idle_add(_process_batch)

    def _refresh_gramps_only(self):
        """Populate the store from the cached Gramps icon inventory only.

        The fast default path: loads only the names the inventory file
        already lists as Gramps-relevant (bundled assets plus the handful
        of system-theme icons Gramps' own GUI is known to use --
        typically on the order of 150 icons), each looked up individually
        by name rather than by enumerating the entire theme cascade. Every
        row this produces is, by construction, a "Gramps" icon, so
        ``COL_IS_GRAMPS`` is simply ``True`` throughout.

        Does nothing useful if no inventory file exists yet -- callers
        should check :func:`_read_gramps_icon_inventory` first (see
        :meth:`_initial_refresh_idle`) and fall back to
        :meth:`_refresh_full` in that case, since a full scan is also how
        the inventory file itself first gets created.
        """
        self._store.clear()
        self._clear_detail()
        self._full_list_loaded = False

        icon_theme = Gtk.IconTheme.get_default()

        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:
            gtk_theme = gtk_settings.get_property("gtk-theme-name") or ""
            self._theme_label.set_markup(
                "<span foreground='#555555'><b>{}</b> {}</span>".format(
                    _("Theme:"), _esc(gtk_theme)
                )
            )

        icons = _read_gramps_icon_inventory() or []
        self._gramps_icon_names = {entry["name"] for entry in icons}

        theme_dirs = set(icon_theme.get_search_path() or [])
        for entry in sorted(icons, key=lambda e: e["name"].casefold()):
            name = entry["name"]
            ctx = entry.get("context") or "Other"
            # The stock-icon fallback matters specifically for
            # "bundled": false entries -- system-theme icon names found
            # by scanning Gramps' own source, a few of which (like
            # "gtk-edit") are GTK2-era stock IDs the icon theme itself
            # doesn't know how to resolve. If even that fails, show a
            # clear "unavailable" placeholder rather than a blank cell,
            # so it reads as "this can't be previewed" rather than as a
            # bug in the browser.
            pb = _load_pixbuf_with_stock_fallback(
                self._tree, icon_theme, name, THUMB_SIZE
            )
            if pb is None:
                pb = _load_pixbuf(icon_theme, "image-missing", THUMB_SIZE)

            info = icon_theme.lookup_icon(name, 22, 0)
            in_theme = False
            if info is not None:
                fn = info.get_filename() or ""
                in_theme = any(fn.startswith(d) for d in theme_dirs)

            self._store.append([pb, name, in_theme, ctx, True])

        self._update_count_label()
        self._filter.refilter()
        GLib.idle_add(self._select_default_icon, "gramps-view")

    def _select_default_icon(self, target_name):
        if not self._tree or not self._sort_model:
            return False

        it = self._sort_model.get_iter_first()
        while it is not None:
            name = self._sort_model.get_value(it, COL_NAME)
            if name == target_name:
                path = self._sort_model.get_path(it)
                self._tree.get_selection().select_path(path)
                self._tree.scroll_to_cell(path, None, True, 0.5, 0.0)
                break
            it = self._sort_model.iter_next(it)
        return False

    def _row_visible(self, model, it, _data):
        name = model.get_value(it, COL_NAME) or ""
        ctx = model.get_value(it, COL_CONTEXT) or ""
        active_ctx = self._ctx_combo.get_active_id() or "*"
        if active_ctx == GRAMPS_FILTER_ID:
            if not model.get_value(it, COL_IS_GRAMPS):
                return False
        elif active_ctx != "*" and ctx != active_ctx:
            return False

        if self._found_filter_state != FOUND_FILTER_ANY:
            in_theme = model.get_value(it, COL_IN_THEME)
            wants_found = self._found_filter_state == FOUND_FILTER_FOUND_ONLY
            if in_theme != wants_found:
                return False

        query = self._search_entry.get_text().strip().lower()
        return not query or query in name.lower()

    def _get_cached_gramps_icon_names(self) -> set | None:
        """Return the icon-name set from the cached inventory file, if any.

        Pure read of whatever's already on disk -- never generates or
        writes anything, so it's always cheap/instant. Building a fresh
        inventory (needed when this returns ``None``) is handled
        separately by :meth:`_rebuild_inventory_async`, which shows
        progress UI, since that involves reading potentially hundreds of
        Gramps source files and isn't something to do silently on the
        main thread.

        :returns: Set of icon-name strings, or ``None`` if no valid cached
            file exists yet.
        """
        icons = _read_gramps_icon_inventory()
        if icons is None:
            return None
        return {entry["name"] for entry in icons}

    def _build_progress_dialog(self, title: str, message: str):
        """Build and show a small modal "this may take a moment" dialog.

        Shared by both slow operations in this gramplet -- rebuilding the
        Gramps icon inventory and reloading the full live icon-theme
        cascade -- since both are the same basic UI need: a title, a
        one-line description, and a progress bar the caller drives.

        :param title: Dialog window title.
        :param message: One-line description shown above the progress bar.
        :returns: The ``(dialog, progress_bar)`` pair. The caller owns
            updating ``progress_bar`` and eventually calling
            ``dialog.destroy()`` when the operation finishes.
        """
        uistate = getattr(self, "uistate", None)
        parent_window = getattr(uistate, "window", None)

        dialog = Gtk.Dialog(title=title, transient_for=parent_window, modal=True)
        dialog.set_default_size(380, -1)
        dialog.set_deletable(False)

        content = dialog.get_content_area()
        content.set_border_width(12)
        content.set_spacing(8)

        label = Gtk.Label(label=message)
        label.set_halign(Gtk.Align.START)
        label.set_line_wrap(True)
        content.pack_start(label, False, False, 0)

        progress = Gtk.ProgressBar()
        progress.set_show_text(True)
        content.pack_start(progress, False, False, 0)

        dialog.show_all()
        self._progress_dialog = dialog
        return dialog, progress

    def _rebuild_inventory_async(self, on_done: Callable[[set], None]) -> None:
        """Rebuild the Gramps icon inventory file, with progress UI.

        Shows a small modal dialog with a progress bar while a background
        thread walks Gramps' bundled ``hicolor`` assets and its installed
        GUI/plugin source for icon-name usage -- real filesystem and
        text-scanning work (hundreds of files on a typical install) that
        would otherwise visibly freeze this single-threaded GTK gramplet
        for the whole scan. None of that scanning touches any GTK object,
        so it's safe to run off the main thread; only the small JSON
        write and *on_done* itself run back on the main thread once the
        background thread finishes.

        :param on_done: Called on the GTK main thread, with the freshly
            rebuilt set of icon-name strings, once the inventory file has
            been written.
        """
        dialog, progress = self._build_progress_dialog(
            _("Rebuilding Gramps Icon Inventory"),
            _("Scanning bundled icons and Gramps source for icon usage\u2026"),
        )

        # Simple int writes from the background thread, read back by the
        # main-thread tick below -- safe under the GIL for this purpose;
        # a stale read is cosmetic at worst (one frame of lag on the bar).
        progress_state = {"done": 0, "total": 0}

        def _progress_cb(done: int, total: int) -> None:
            progress_state["done"] = done
            progress_state["total"] = total

        result: dict = {}

        def _worker() -> None:
            result["icons"] = _build_full_gramps_icon_inventory(_progress_cb)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        def _tick() -> bool:
            if self._shutting_down:
                # Gramplet is being torn down mid-rebuild -- on_unload()
                # already destroyed the dialog; the background thread
                # will simply finish and its result gets discarded rather
                # than this callback touching now-invalid widgets.
                self._progress_source_id = None
                return False

            total = progress_state["total"]
            done = progress_state["done"]
            if total:
                progress.set_fraction(min(done / total, 1.0))
                progress.set_text(
                    _("{done} of {total} files").format(done=done, total=total)
                )
            else:
                progress.pulse()

            if thread.is_alive():
                return True

            icons = result.get("icons", [])
            try:
                path = _write_gramps_icon_inventory(icons)
                LOG.info(
                    "Wrote Gramps icon inventory (%d icons) to %s",
                    len(icons),
                    path,
                )
            except OSError:
                LOG.exception("Could not write Gramps icon inventory")

            dialog.destroy()
            self._progress_dialog = None
            self._progress_source_id = None
            on_done({entry["name"] for entry in icons})
            return False

        self._progress_source_id = GLib.timeout_add(100, _tick)

    def _apply_gramps_icon_flags(self) -> None:
        """Refresh COL_IS_GRAMPS on every already-loaded row.

        Cheap in-place update used after a manual rebuild: it re-checks
        each row already in ``self._store`` against the (possibly just
        regenerated) ``self._gramps_icon_names`` set, without repeating the
        expensive live icon-theme enumeration that :meth:`_refresh_full` does.
        """
        it = self._store.get_iter_first()
        while it is not None:
            name = self._store.get_value(it, COL_NAME)
            self._store.set_value(it, COL_IS_GRAMPS, name in self._gramps_icon_names)
            it = self._store.iter_next(it)

    def _on_rebuild_gramps_inventory_clicked(self, _widget):
        """Force-regenerate the Gramps icon inventory file (with progress UI).

        Deliberately avoids the expensive full live-cascade re-scan when
        it isn't needed: if the fast Gramps-only store is currently
        showing (``self._full_list_loaded`` is ``False``), that store *is*
        the filtered set, so it's simplest to just rebuild it directly
        from the freshly-written inventory. If the full cascade is already
        loaded, there's no need to reload it either -- only the already-
        loaded rows' "Gramps" flag needs re-checking against the new list.
        """

        def _on_built(names: set) -> None:
            self._gramps_icon_names = names
            if self._full_list_loaded:
                self._apply_gramps_icon_flags()
                self._filter.refilter()
                self._update_count_label()
            else:
                self._refresh_gramps_only()

        self._rebuild_inventory_async(_on_built)

    @staticmethod
    def _render_flag_cell(_col, renderer, model, it, _data):
        in_theme = model.get_value(it, COL_IN_THEME)
        renderer.set_property("foreground", "#006600" if in_theme else "#999999")
        renderer.set_property("text", "✓" if in_theme else "–")

    def _on_flag_header_clicked(self, _column) -> None:
        """Advance the found/not-found header through its 3-state cycle.

        Any -> Found only -> Not Found only -> Any, looping. Chosen over
        making this column sortable (which was tried first) because for
        the actual use case -- finding every icon that's broken in the
        current theme -- hiding the found rows outright beats merely
        moving them out of the way in a still-mixed list; the "Not Found
        only" state gets straight to exactly what a debugging session
        needs, with an accurate count of just those rows.
        """
        self._found_filter_state = (self._found_filter_state + 1) % 3
        self._update_flag_header()
        self._filter.refilter()
        self._update_count_label()

    def _update_flag_header(self) -> None:
        """Reflect ``self._found_filter_state`` in the flag column's header.

        There's no sort arrow to lean on here (this column is clickable
        for filtering, not sorting), so the header's own title text is
        what has to communicate the current state -- along with the
        tooltip, for anyone who doesn't immediately recognize the glyph.
        """
        titles = {
            FOUND_FILTER_ANY: "",
            FOUND_FILTER_FOUND_ONLY: "✓",
            FOUND_FILTER_NOT_FOUND_ONLY: "–",
        }
        tooltips = {
            FOUND_FILTER_ANY: _(
                "Showing all icons. Click to show only icons found in the "
                "current icon theme."
            ),
            FOUND_FILTER_FOUND_ONLY: _(
                "Showing only icons found in the current icon theme. "
                "Click to show only icons that are not found."
            ),
            FOUND_FILTER_NOT_FOUND_ONLY: _(
                "Showing only icons NOT found in the current icon theme. "
                "Click to show all icons again."
            ),
        }
        self._flag_column.set_title(titles[self._found_filter_state])
        self._flag_column.get_button().set_tooltip_text(
            tooltips[self._found_filter_state]
        )

    @staticmethod
    def _sort_by_name(model, iter_a, iter_b, _data):
        """Sort the Icon Name column case-insensitively.

        Registered explicitly rather than relying on
        :class:`Gtk.TreeSortable`'s untyped default string comparison, so
        this matches the case-insensitive ordering used everywhere else
        icon names are sorted in this gramplet (e.g. the inventory scan
        functions' own ``str.casefold()`` sort keys).

        :returns: Negative/zero/positive, per :class:`Gtk.TreeIterCompareFunc`.
        """
        name_a = (model.get_value(iter_a, COL_NAME) or "").casefold()
        name_b = (model.get_value(iter_b, COL_NAME) or "").casefold()
        return (name_a > name_b) - (name_a < name_b)

    def _on_tree_query_tooltip(self, tree, x, y, keyboard_tip, tooltip):
        """Show a per-row tooltip explaining the found/not-found flag cell.

        Only the flag column (leftmost, showing \u2713/\u2013) gets a
        row-specific tooltip here -- the pixbuf and name columns are
        adequately explained by their header tooltips alone (set once, in
        :meth:`_build_browser_content`), and don't need a tooltip that
        changes per row the way the flag's meaning does.

        :returns: ``True`` (and populates *tooltip*) when hovering a row's
            flag cell; ``False`` otherwise, so GTK shows no tooltip at all
            for every other position.
        """
        if keyboard_tip:
            path, col = tree.get_cursor()
        else:
            bin_x, bin_y = tree.convert_widget_to_bin_window_coords(x, y)
            hit = tree.get_path_at_pos(bin_x, bin_y)
            if hit is None:
                return False
            path, col, _cell_x, _cell_y = hit

        if path is None or col is not self._flag_column:
            return False

        model = tree.get_model()
        it = model.get_iter(path)
        found = model.get_value(it, COL_IN_THEME)
        tooltip.set_text(
            _("Found in the current icon theme")
            if found
            else _("Not found in the current icon theme")
        )
        tree.set_tooltip_row(tooltip, path)
        return True

    def _clear_detail(self):
        if getattr(self, "_idle_inspector_id", None) is not None:
            GLib.source_remove(self._idle_inspector_id)
            self._idle_inspector_id = None
        for child in self._detail_box.get_children():
            self._detail_box.remove(child)

    def _populate_detail(self, icon_name):
        self._current_icon_name = icon_name  # tracked so an icon-override
        # install can tell whether it needs to also refresh this pane
        self._clear_detail()
        icon_theme = Gtk.IconTheme.get_default()

        heading = Gtk.Label()
        heading.set_markup("<big><b>{}</b></big>".format(_esc(icon_name)))
        heading.set_halign(Gtk.Align.START)
        heading.set_selectable(True)
        self._detail_box.pack_start(heading, False, False, 0)

        strip_lbl = Gtk.Label()
        strip_lbl.set_markup("<b>{}</b>".format(_("Available sizes")))
        strip_lbl.set_halign(Gtk.Align.START)
        self._detail_box.pack_start(strip_lbl, False, False, 2)

        strip = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        strip.set_border_width(4)

        fallback_sizes = []
        self._current_available_sizes = []

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
                is_native = base == px or base == 0

            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            cell.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)

            colour = "#000000" if is_native else "#999999"
            size_lbl = Gtk.Label()
            size_lbl.set_markup("<span foreground='{}'>{}px</span>".format(colour, px))
            cell.pack_start(size_lbl, False, False, 0)
            strip.pack_start(cell, False, False, 4)

            if is_native:
                self._current_available_sizes.append(px)
            else:
                fallback_sizes.append(px)

        if not strip.get_children():
            stock_pb = None
            try:
                stock_pb = self._tree.render_icon_pixbuf(
                    icon_name, Gtk.IconSize.SMALL_TOOLBAR
                )
            except Exception:
                stock_pb = None

            if stock_pb is not None:
                # Renders fine, just not through the icon theme -- this is
                # the "gtk-edit" / "gtk-index" situation: a GTK2-era
                # Gtk.STOCK_* name with no freedesktop icon-theme entry at
                # all, so there's no per-size asset to show in the strip
                # above, only GTK's single built-in stock rendering.
                stock_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                stock_row.pack_start(
                    Gtk.Image.new_from_pixbuf(stock_pb), False, False, 0
                )
                note = Gtk.Label()
                note.set_markup(
                    "<span foreground='#555555'>{}</span>".format(
                        _esc(
                            _(
                                "Not a freedesktop icon-theme name -- this is a "
                                "legacy GTK stock-icon ID, rendered here via GTK's "
                                "built-in stock-icon compatibility table instead. "
                                "No per-size theme assets exist for it."
                            )
                        )
                    )
                )
                note.set_line_wrap(True)
                note.set_halign(Gtk.Align.START)
                stock_row.pack_start(note, True, True, 0)
                self._detail_box.pack_start(stock_row, False, False, 0)
                self._detail_box.show_all()
                return

            missing = Gtk.Label(
                label=_(
                    "(icon not found -- not present in the current icon theme, "
                    "and no GTK stock-icon fallback is available for this name "
                    "either)"
                )
            )
            missing.set_halign(Gtk.Align.START)
            missing.set_line_wrap(True)
            self._detail_box.pack_start(missing, False, False, 0)
            self._detail_box.show_all()
            return

        strip_sw = Gtk.ScrolledWindow()
        strip_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        strip_sw.set_min_content_height(DETAIL_SIZES[-1] + 36)
        strip_sw.add(strip)
        self._detail_box.pack_start(strip_sw, False, False, 0)

        self._detail_box.pack_start(Gtk.Separator(), False, False, 4)

        info_main = icon_theme.lookup_icon(
            icon_name, 48, Gtk.IconLookupFlags.GENERIC_FALLBACK
        )
        if info_main is not None:
            filepath = info_main.get_filename() or ""
            theme_note = Gtk.Label()
            theme_note.set_markup(
                "<span foreground='#555555'>{}</span>".format(
                    _linkify_path(filepath, icon_name)
                )
            )
            theme_note.set_halign(Gtk.Align.START)
            theme_note.set_line_wrap(True)
            theme_note.set_selectable(True)
            theme_note.connect("activate-link", self._on_activate_link)
            theme_note.connect(
                "populate-popup", self._on_label_populate_popup, filepath
            )
            self._detail_box.pack_start(theme_note, False, False, 0)

        if fallback_sizes:
            fb_lbl = Gtk.Label()
            fb_lbl.set_markup(
                "<span foreground='#999999'>{}: {}</span>".format(
                    _("Scaled (not native)"),
                    ", ".join(str(size) for size in fallback_sizes),
                )
            )
            fb_lbl.set_halign(Gtk.Align.START)
            self._detail_box.pack_start(fb_lbl, False, False, 0)

        self._detail_box.pack_start(Gtk.Separator(), False, False, 4)

        md_heading = Gtk.Expander(label=_("MarkdownDash gramps:icon syntax"))
        md_heading.set_expanded(True)

        md_grid = Gtk.Grid()
        md_grid.set_column_spacing(8)
        md_grid.set_row_spacing(4)
        md_grid.set_border_width(4)

        scalable_syntax = f"![](gramps:icon:{icon_name})"
        scalable_lbl = Gtk.Label(label=scalable_syntax)
        scalable_lbl.set_halign(Gtk.Align.START)
        scalable_lbl.set_selectable(True)
        scalable_lbl.set_hexpand(True)
        scalable_lbl.get_style_context().add_class("mono-text")
        md_grid.attach(Gtk.Image(), 0, 0, 1, 1)
        md_grid.attach(scalable_lbl, 1, 0, 1, 1)

        scalable_copy = Gtk.Button()
        scalable_copy.set_image(
            Gtk.Image.new_from_icon_name("edit-copy", Gtk.IconSize.SMALL_TOOLBAR)
        )
        scalable_copy.set_relief(Gtk.ReliefStyle.NONE)
        scalable_copy.set_tooltip_text(_("Copy scalable MarkdownDash syntax"))
        scalable_copy.connect("clicked", self._on_copy_syntax, scalable_syntax)
        md_grid.attach(scalable_copy, 2, 0, 1, 1)

        for row_idx, px in enumerate(self._current_available_sizes, start=1):
            pb = _load_pixbuf(icon_theme, icon_name, min(px, 32))
            md_grid.attach(
                Gtk.Image.new_from_pixbuf(pb) if pb else Gtk.Image(), 0, row_idx, 1, 1
            )

            syntax = f"![](gramps:icon:{icon_name}:{px})"
            src_lbl = Gtk.Label(label=syntax)
            src_lbl.set_halign(Gtk.Align.START)
            src_lbl.set_selectable(True)
            src_lbl.set_hexpand(True)
            src_lbl.get_style_context().add_class("mono-text")
            md_grid.attach(src_lbl, 1, row_idx, 1, 1)

            copy_btn = Gtk.Button()
            copy_btn.set_image(
                Gtk.Image.new_from_icon_name("edit-copy", Gtk.IconSize.SMALL_TOOLBAR)
            )
            copy_btn.set_relief(Gtk.ReliefStyle.NONE)
            copy_btn.set_tooltip_text(_("Copy to clipboard"))
            copy_btn.connect("clicked", self._on_copy_syntax, syntax)
            md_grid.attach(copy_btn, 2, row_idx, 1, 1)

        md_heading.add(md_grid)
        self._detail_box.pack_start(md_heading, False, False, 0)

        self._detail_box.pack_start(Gtk.Separator(), False, False, 4)

        py_heading = Gtk.Expander(label=_("GTK button snippet"))
        py_heading.set_expanded(False)

        py_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        py_box.set_border_width(4)

        py_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        short_snippet = (
            "icon_img = Gtk.Image.new_from_icon_name(\n"
            f'    "{icon_name}", Gtk.IconSize.SMALL_TOOLBAR\n'
            ")\n"
        )

        full_snippet = (
            "icon_btn = Gtk.Button()\n"
            "icon_img = Gtk.Image.new_from_icon_name(\n"
            f'    "{icon_name}", Gtk.IconSize.SMALL_TOOLBAR\n'
            ")\n"
            "icon_btn.set_image(icon_img)\n"
            "icon_btn.set_relief(Gtk.ReliefStyle.NONE)\n"
            f'icon_btn.set_tooltip_text(_("{icon_name}"))\n'
            'icon_btn.connect("clicked", self._on_icon_clicked)\n'
            "footer.pack_start(icon_btn, False, False, 0)\n"
        )

        short_copy_btn = Gtk.Button()
        short_copy_btn.set_image(
            Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR)
        )
        short_copy_btn.set_relief(Gtk.ReliefStyle.NONE)
        short_copy_btn.set_tooltip_text(_("Copy short GTK snippet"))
        short_copy_btn.connect("clicked", self._on_copy_syntax, short_snippet)
        py_row.pack_start(short_copy_btn, False, False, 0)

        name_lbl = Gtk.Label(label=icon_name)
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_hexpand(True)
        name_lbl.set_selectable(True)
        py_row.pack_start(name_lbl, True, True, 0)

        full_copy_btn = Gtk.Button()
        full_copy_btn.set_image(
            Gtk.Image.new_from_icon_name("edit-copy", Gtk.IconSize.SMALL_TOOLBAR)
        )
        full_copy_btn.set_relief(Gtk.ReliefStyle.NONE)
        full_copy_btn.set_tooltip_text(_("Copy snippet"))
        full_copy_btn.connect("clicked", self._on_copy_syntax, full_snippet)
        py_row.pack_start(full_copy_btn, False, False, 0)

        py_box.pack_start(py_row, False, False, 0)
        py_heading.add(py_box)
        self._detail_box.pack_start(py_heading, False, False, 0)

        self._detail_box.show_all()

        # DEFER PATH INSPECTOR GENERATION TO IDLE PROCESS TO REMOVE SELECTION STUTTER
        self._idle_inspector_id = GLib.idle_add(
            self._deferred_populate_inspector, icon_name
        )

    def _deferred_populate_inspector(self, icon_name):
        self._idle_inspector_id = None
        icon_theme = Gtk.IconTheme.get_default()

        # Build fallback layout cascade stack
        parts = icon_name.split("-")
        cascade_names = []
        for i in range(len(parts), 0, -1):
            cascade_names.append("-".join(parts[:i]))

        # Add Explicit Symbolic Checks & True Structural Missing Asset Fallback
        if not icon_name.endswith("-symbolic"):
            cascade_names.append(f"{icon_name}-symbolic")
        if "image-missing" not in cascade_names:
            cascade_names.append("image-missing")

        sep = Gtk.Separator()
        path_heading = Gtk.Expander(label=_("GTK Path Inspector"))
        path_heading.set_expanded(False)

        path_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        path_box.set_border_width(4)

        inspector_grid = Gtk.Grid()
        inspector_grid.set_column_spacing(12)
        inspector_grid.set_row_spacing(6)

        lbl_h_name = Gtk.Label()
        lbl_h_name.set_markup("<b>Fallback Name</b>")
        lbl_h_name.set_halign(Gtk.Align.START)
        inspector_grid.attach(lbl_h_name, 0, 0, 1, 1)

        lbl_h_preview = Gtk.Label()
        lbl_h_preview.set_markup("<b>Preview</b>")
        lbl_h_preview.set_halign(Gtk.Align.CENTER)
        inspector_grid.attach(lbl_h_preview, 1, 0, 1, 1)

        lbl_h_path = Gtk.Label()
        lbl_h_path.set_markup("<b>Resolved Absolute Path</b>")
        lbl_h_path.set_halign(Gtk.Align.START)
        inspector_grid.attach(lbl_h_path, 2, 0, 1, 1)

        target_sizes = [24, 22, 16]

        for idx, current_name in enumerate(cascade_names, start=1):
            name_lbl = Gtk.Label(label=current_name)
            name_lbl.set_halign(Gtk.Align.START)
            name_lbl.get_style_context().add_class("mono-text")
            inspector_grid.attach(name_lbl, 0, idx, 1, 1)

            resolved_info = None
            chosen_size = 24
            for size in target_sizes:
                info_check = icon_theme.lookup_icon(
                    current_name, size, Gtk.IconLookupFlags.USE_BUILTIN
                )
                if info_check is not None:
                    resolved_info = info_check
                    chosen_size = size
                    break

            img_widget = Gtk.Image()
            if resolved_info is not None:
                pb = _load_pixbuf(icon_theme, current_name, chosen_size)
                if pb:
                    img_widget.set_from_pixbuf(pb)
            else:
                img_widget.set_from_icon_name("dialog-error", Gtk.IconSize.MENU)
            inspector_grid.attach(img_widget, 1, idx, 1, 1)

            path_lbl = Gtk.Label()
            path_lbl.set_halign(Gtk.Align.START)
            path_lbl.set_selectable(True)
            path_lbl.set_line_wrap(True)
            path_lbl.connect("activate-link", self._on_activate_link)

            if resolved_info is not None:
                f_path = resolved_info.get_filename() or _("(Built-in binary resource)")
                path_markup = _linkify_path(f_path, icon_name)
                path_lbl.connect(
                    "populate-popup", self._on_label_populate_popup, f_path
                )
                if current_name == icon_name:
                    path_lbl.set_markup(
                        f"<span foreground='#006600'><b>{path_markup}</b></span>"
                    )
                elif "missing" in current_name:
                    path_lbl.set_markup(
                        f"<span foreground='#AA0000'><i>{path_markup}</i></span>"
                    )
                else:
                    path_lbl.set_markup(
                        f"<span foreground='#555555'>{path_markup}</span>"
                    )
            else:
                path_lbl.set_markup(
                    f"<span foreground='#999999'><i>{_('Not found in active themes')}</i></span>"
                )

            inspector_grid.attach(path_lbl, 2, idx, 1, 1)

        path_box.pack_start(inspector_grid, False, False, 0)
        path_heading.add(path_box)

        self._detail_box.pack_start(sep, False, False, 4)
        self._detail_box.pack_start(path_heading, False, False, 0)
        self._detail_box.show_all()
        return False

    def _on_selection_changed(self, selection):
        model, it = selection.get_selected()
        if it:
            self._populate_detail(model.get_value(it, COL_NAME))

    def _on_search_changed(self, _widget):
        if getattr(self, "_search_timeout_id", None) is not None:
            GLib.source_remove(self._search_timeout_id)
        self._search_timeout_id = GLib.timeout_add(500, self._do_search_filter)

    def _do_search_filter(self):
        self._search_timeout_id = None
        self._filter.refilter()
        self._update_count_label()
        return False

    def _on_context_changed(self, _widget):
        """Load the right dataset for the newly selected filter.

        Two lazy transitions, in opposite directions:

        - Switching *away* from "Gramps" to any other context implies
          "show me icons outside that ~150-icon subset" -- which the fast
          Gramps-only store can't do, since it never had them loaded in
          the first place. That triggers one full-cascade load.
        - Switching *to* "Gramps" while the full cascade (thousands of
          icons) is currently loaded flushes it back out and reloads the
          thin Gramps-only set instead, rather than merely filtering the
          big store down to a subset of itself -- keeping the browser's
          memory/row footprint small again once the person is back to
          just browsing Gramps' own icons, not just its visible rows.

        Every other context change (switching between two non-"Gramps"
        contexts, or back to "Gramps" while already thin) is just a cheap
        refilter of whichever store is already loaded.
        """
        active_ctx = self._ctx_combo.get_active_id() or "*"
        if active_ctx != GRAMPS_FILTER_ID and not self._full_list_loaded:
            GLib.idle_add(self._refresh_full_idle)
            return
        if active_ctx == GRAMPS_FILTER_ID and self._full_list_loaded:
            GLib.idle_add(self._refresh_gramps_only_idle)
            return
        self._filter.refilter()
        self._update_count_label()

    def _refresh_full_idle(self):
        self._refresh_full()
        return False

    def _on_refresh_clicked(self, _widget):
        """Explicit Reload: loads the full cascade and switches to "All".

        Deliberately doesn't reuse :meth:`_refresh_full_idle` here: this
        button should always end up showing the freshly reloaded full
        list, so the filter is switched to "All" right after
        :meth:`_refresh_full` finishes setting ``self._full_list_loaded``
        (which happens synchronously, at the very top of that method,
        before its own chunked loading even starts) -- by the time the
        combo box's own "changed" handler sees this, that flag is already
        ``True``, so it just does a cheap refilter rather than kicking off
        a second, redundant full reload. Leaving the filter on "Gramps"
        after a full reload would otherwise immediately hide almost
        everything that reload just spent time loading.
        """

        def _reload_then_show_all():
            self._refresh_full()
            self._ctx_combo.set_active_id("*")
            return False

        GLib.idle_add(_reload_then_show_all)

    def _on_theme_changed(self, _settings, _param):
        GLib.timeout_add(300, self._deferred_refresh)

    def _deferred_refresh(self):
        """Re-run whichever population mode (fast/full) was already active.

        A GTK theme switch can change which icons resolve and how they
        look either way, so the currently-shown data needs refreshing --
        but there's no reason a theme change should force the expensive
        full cascade if only the small Gramps subset was ever loaded.
        """
        if self._full_list_loaded:
            GLib.idle_add(self._refresh_full_idle)
        else:
            GLib.idle_add(self._refresh_gramps_only_idle)
        return False

    def _refresh_gramps_only_idle(self):
        self._refresh_gramps_only()
        return False

    def _on_copy_syntax(self, _widget, syntax):
        cb = Gtk.Clipboard.get_default(self.uistate.window.get_display())
        cb.set_text(syntax, -1)

    def _on_activate_link(self, _label, uri):
        """Open a hotlinked path's *uri* with the right kind of handler.

        Local ``file://`` folder links go through
        :meth:`_open_local_folder` (GIO's default-URI-handler mechanism,
        which resolves to the OS's native file manager).
        ``gramps-icon-override:`` links (see :func:`_linkify_path`) go
        through :meth:`_open_icon_override_dialog`, opening a native file
        dialog rooted at the right per-user override folder. Everything
        else (the remote GTK/Gramps source links) goes through
        ``display_url()``, mirroring ``on_activate_link()`` in
        ``gramps/gui/dialog.py`` so those open exactly the way a link
        inside a core Gramps dialog does.

        :param uri: The link target from the clicked ``<a href="...">``.
        :returns: ``True``, telling GTK the link was handled so its own
            default handler does not also try to open it.
        """
        if uri.startswith("file://"):
            self._open_local_folder(uri)
        elif uri.startswith(_OVERRIDE_URI_PREFIX):
            payload = uri[len(_OVERRIDE_URI_PREFIX) :]
            icon_name, _sep, context = payload.partition(":")
            self._open_icon_override_dialog(icon_name, context or "actions")
        else:
            display_url(uri)
        return True

    def _open_icon_override_dialog(self, icon_name: str, context: str) -> None:
        """Open a native file dialog for picking *icon_name*'s override.

        Creates :func:`_user_icon_override_dir` for *context* first if it
        doesn't exist yet (a fresh install won't have any ``~/.local/
        share/icons/hicolor/...`` folders at all) -- that's the
        *destination* a chosen file gets copied to. The dialog itself
        *starts* browsing at :func:`_gramplet_media_icons_dir` instead
        (``media/icons`` alongside this gramplet), so a curated set of
        candidate icons kept there is right where the picker opens,
        rather than at the destination folder, which is typically still
        empty. Shows a :class:`Gtk.FileChooserNative` -- GTK's wrapper
        that uses the platform's actual native file-picker where one is
        available. If the person picks an SVG or PNG, it's copied to the
        destination folder under *icon_name*'s own filename (so the icon
        theme will actually find it under the name being looked up,
        rather than leaving them to work out the right filename
        themselves) and the installation is recorded in
        :func:`_log_icon_override`; cancelling just leaves the
        (now-existing, empty) destination folder ready for later.

        :param icon_name: The icon name this override needs to be named
            after.
        :param context: Freedesktop context folder, e.g. ``"actions"``.
        """
        target_dir = _user_icon_override_dir(context)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError:
            LOG.exception("Could not create %s", target_dir)
            return

        uistate = getattr(self, "uistate", None)
        parent_window = getattr(uistate, "window", None)

        chooser = Gtk.FileChooserNative.new(
            _("Choose an SVG or PNG for \u201c{name}\u201d").format(name=icon_name),
            parent_window,
            Gtk.FileChooserAction.OPEN,
            _("_Open"),
            _("_Cancel"),
        )
        chooser.set_current_folder(_gramplet_media_icons_dir())

        image_filter = Gtk.FileFilter()
        image_filter.set_name(_("Icon images (*.svg, *.png)"))
        image_filter.add_pattern("*.svg")
        image_filter.add_pattern("*.png")
        chooser.add_filter(image_filter)

        response = chooser.run()
        if response == Gtk.ResponseType.ACCEPT:
            src = chooser.get_filename()
            if src:
                ext = os.path.splitext(src)[1].lower() or ".svg"
                dest = os.path.join(target_dir, icon_name + ext)
                try:
                    shutil.copy2(src, dest)
                    LOG.info("Installed icon override: %s", dest)
                    _log_icon_override(icon_name, dest)
                except OSError:
                    LOG.exception("Could not copy %s to %s", src, dest)
                else:
                    self._refresh_after_icon_override(icon_name)
        chooser.destroy()

    def _refresh_after_icon_override(self, icon_name: str) -> None:
        """Make a just-installed icon override show up without a restart.

        GTK's icon theme does watch its search-path directories and is
        supposed to notice new files on its own, but a directory that
        didn't exist yet a moment ago (as ``target_dir`` typically won't,
        the first time this feature is used for a given context) may not
        have had a filesystem watch established for it at all -- so
        rather than rely on that, :meth:`Gtk.IconTheme.rescan_if_needed`
        is called explicitly, which does a fresh, synchronous check of
        the theme's directories regardless of whether a watch fired.

        That alone only refreshes GTK's own internal cache, though; this
        gramplet's own :class:`Gtk.ListStore` was populated earlier and
        doesn't update itself. Rather than re-running a full population
        (which, in "full cascade" mode, would mean re-triggering the same
        slow, progress-bar-driven reload this whole "immediate" update is
        supposed to avoid), only the affected row(s) get their pixbuf and
        found-flag refreshed in place -- see
        :meth:`_update_single_row_pixbuf`. The detail pane is also
        re-populated if it's currently showing the icon that was just
        overridden.

        :param icon_name: The icon name that was just installed.
        """
        Gtk.IconTheme.get_default().rescan_if_needed()
        self._update_single_row_pixbuf(icon_name)
        self._filter.refilter()
        self._update_count_label()

        if self._current_icon_name == icon_name:
            self._populate_detail(icon_name)

    def _update_single_row_pixbuf(self, icon_name: str) -> None:
        """Reload just one row's pixbuf and found-flag, in place, by name.

        A targeted alternative to re-running a whole population pass,
        used specifically so an icon-override install can update the
        display immediately without the cost (and, in "full cascade"
        mode, the progress dialog) of a complete reload.

        :param icon_name: The icon name whose row(s) should be refreshed.
            Ordinarily matches at most one row, but every matching row is
            updated in the unlikely case of a duplicate.
        """
        icon_theme = Gtk.IconTheme.get_default()
        theme_dirs = set(icon_theme.get_search_path() or [])

        it = self._store.get_iter_first()
        while it is not None:
            if self._store.get_value(it, COL_NAME) == icon_name:
                pb = _load_pixbuf_with_stock_fallback(
                    self._tree, icon_theme, icon_name, THUMB_SIZE
                )
                if pb is None:
                    pb = _load_pixbuf(icon_theme, "image-missing", THUMB_SIZE)

                info = icon_theme.lookup_icon(icon_name, 22, 0)
                in_theme = False
                if info is not None:
                    fn = info.get_filename() or ""
                    in_theme = any(fn.startswith(d) for d in theme_dirs)

                self._store.set_value(it, COL_PIXBUF, pb)
                self._store.set_value(it, COL_IN_THEME, in_theme)
            it = self._store.iter_next(it)

    def _open_local_folder(self, uri: str) -> None:
        """Open a ``file://`` folder *uri* in the OS's native file manager.

        Deliberately does *not* go through ``display_url()``: that's
        built on Python's ``webbrowser`` module, which for a ``file://``
        URI often launches the default *web browser* to show a raw
        directory listing rather than the OS's file manager -- not what
        "open the folder this icon lives in" should mean.
        ``Gio.AppInfo.launch_default_for_uri()`` instead asks the
        desktop's own URI-handler registry, which for a ``file://``
        folder resolves to the native file manager (Nautilus, Explorer,
        Finder, ...) on every mainstream desktop.

        :param uri: A ``file://`` URI pointing at a local directory.
        """
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error:
            LOG.exception("Could not open folder %s", uri)

    def _on_label_populate_popup(self, _label, menu, resolved_path):
        """Add a "View icon source online" entry to a path label's menu.

        ``Gtk.Label::populate-popup`` fires just before a *selectable*
        label shows its default right-click menu (normally just "Copy" /
        "Select All"), letting an application add its own items to that
        same menu rather than building a whole separate context menu from
        scratch. Every resolved-path label in this gramplet connects this
        handler (see ``_populate_detail`` and
        ``_deferred_populate_inspector``); it only actually adds anything
        when :func:`_remote_source_url` recognizes *resolved_path*'s
        prefix -- otherwise the label's normal Copy/Select-All menu is
        left untouched.

        :param menu: The :class:`Gtk.Menu` about to be shown.
        :param resolved_path: The exact path string this particular label
            is displaying (captured at label-creation time), so the menu
            item opens the right icon's source even though many labels
            share this one handler.
        """
        url = _remote_source_url(resolved_path)
        if not url:
            return
        separator = Gtk.SeparatorMenuItem()
        menu.append(separator)
        item = Gtk.MenuItem(label=_("View icon source online"))
        item.connect("activate", lambda _item: display_url(url))
        menu.append(item)
        separator.show()
        item.show()

    def _update_count_label(self):
        visible = sum(
            1 for row in self._store if self._row_visible(self._store, row.iter, None)
        )
        self._count_label.set_markup("{} of {} icons".format(visible, len(self._store)))

    def main(self):
        pass
