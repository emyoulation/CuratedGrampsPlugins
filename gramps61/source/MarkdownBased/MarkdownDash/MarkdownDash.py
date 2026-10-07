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

This module acts as a shell widget. All Markdown parsing, tag styling, icon
resolution, and table rendering are explicitly delegated to :mod:`MarkdownUtils`,
fully leveraging style context injection for cohesive cross-component design.

Navigation history (Back / Forward) is accessed via the standard Gramps
keybindings **Alt+Left** and **Alt+Right**, consistent with the rest of the
application.  The Home document is accessible from the folder-menu popup.

External API
------------
Other Gramps add-ons that want to show a Markdown help file should call the
module-level :func:`open_markdown_file` function rather than instantiating the
gramplet directly::

    from MarkdownDash import open_markdown_file
    open_markdown_file("/path/to/addon/README.md", uistate, parent=self.window)

The function resolves locale variants automatically (``locale/fr_FR/README.md``
→ ``locale/fr/README.md`` → ``README.md``; implemented once, in
:func:`MarkdownUtils.resolve_localized_path`), accepts remote ``https://`` URLs,
and renders a graceful inline error page — with a localisation-invitation notice
— when no file is found.  Callers never need to know about the gramplet
lifecycle or widget internals.

Locale path convention::

    <addon_dir>/
        README.md                    # English baseline (always present)
        locale/
            fr_FR/README.md          # full locale variant (highest priority)
            fr/README.md             # short-code variant
            de/README.md
            ...

Source-language convention
--------------------------
If an add-on's documentation was written in a language *other* than English,
name the baseline file with an ISO 639-1 suffix::

    README_fi.md    # documentation is in Finnish

When no ``README.md`` (unlabelled English baseline) exists but a
``README_<lang>.md`` is found, MarkdownDash treats that as the source language
and shows a translation-invitation notice appropriate to the situation:

- User's locale matches the file's language → shown normally, no notice.
- User's locale differs → file shown as fallback, invitation to translate
  either into the user's language or into English as the universal baseline.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "restructure MarkdownDash gramplet — extract markdown handling into a
separate library module; add in-document anchor scroll navigation; add
back/forward navigation history via Alt+Left/Alt+Right keybindings (no toolbar
buttons); render file-not-found errors as inline Markdown; remove .last_file.cache
session persistence; add public open_markdown_file() API; add README_<lang>.md
source-language convention with translation invitation; pin Home in folder menu"
Revision prompt (19 Sep 2026, Claude Sonnet 5, Anthropic, claude-sonnet-5): "extend MarkdownUtils
with the localization support so it can be trimmed out of the other modules
(including MarkdownDash.py) and call a common codebase" -- locale/path helpers
removed from this file and imported from MarkdownUtils.
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import logging
import os
import re
import subprocess
import tempfile
import traceback
import urllib.error
import urllib.request
from hashlib import sha1
from typing import Callable

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
from gramps.gen.errors import WindowActiveError
from gramps.gen.plug import Gramplet
from gramps.gui.managedwindow import ManagedWindow

# ------------------------
# Gramps specific
# ------------------------
from MarkdownUtils import (
    LANG_SUFFIX_RE,
    NAMESPACE_MAP,
    VIEW_NAMES,
    apply_table_no_wrap_tag,
    build_table_text,
    build_table_widget,
    define_tags,
    emit_enhanced_renderer_notice,
    locale_lang,
    parse_markdown,
    resolve_icon_pixbuf,
    resolve_localized_asset,
    resolve_localized_path,
    table_has_uninteractive_links,
)

# Backward-compatible names: these moved to MarkdownUtils. Kept so any
# add-on that still imports them from MarkdownDash keeps working; delete
# once nothing does.
_locale_lang = locale_lang
_LANG_SUFFIX_RE = LANG_SUFFIX_RE

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)


def _esc(text: str) -> str:
    """XML-escape *text* for use inside Pango markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Locale / path utilities live in MarkdownUtils ─────────────────────────────
# (locale_lang, PathResolution, LANG_SUFFIX_RE, resolve_localized_path,
# resolve_localized_asset) -- imported above.


def _fetch_remote(url: str, timeout: int = 10) -> str | None:
    """Download *url* and return its text content, or ``None`` on failure.

    Downloads to a temporary file so the caller can pass the temp path
    through the normal ``_load()`` pipeline unchanged.

    :param url:     ``https://`` or ``http://`` URL to fetch.
    :param timeout: Network timeout in seconds.
    :returns:       Temporary file path containing the downloaded content,
        or ``None`` if the fetch fails.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Gramps-MarkdownDash/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        tmp = tempfile.NamedTemporaryFile(
            mode="wb", suffix=".md", delete=False, prefix="gramps_mddash_"
        )
        with tmp:
            tmp.write(data)
        return tmp.name
    except (urllib.error.URLError, OSError):
        LOG.warning("MarkdownDash: failed to fetch remote URL: %s", url)
        return None


def open_markdown_file(
    path: str,
    uistate,
    parent: Gtk.Window | None = None,
    title: str | None = None,
    addon_name: str | None = None,
) -> Gtk.Dialog:
    """Open *path* in a standalone Markdown Dash dialog window.

    This is the **primary public API** for external Gramps add-ons that want
    to show their own Markdown help files.  Example usage::

        from MarkdownDash import open_markdown_file
        open_markdown_file(
            os.path.join(os.path.dirname(__file__), "README.md"),
            uistate,
            parent=self.window,
            addon_name=_("My Add-on"),
        )

    Locale resolution, remote URL fetching, and fallback error rendering are
    all handled automatically — the caller only needs to supply the path to the
    English-language baseline file.

    The dialog is registered with Gramps' own window manager
    (:class:`~gramps.gui.managedwindow.ManagedWindow`/``uistate.gwm``), the
    same as any other Gramps top-level window: it gets an entry under the
    **Windows** menu (labeled with *title*/*addon_name*, or "Markdown
    Dash"), calling this again for the *same resolved file* re-presents
    that existing window instead of opening a duplicate, and it's parented
    to Gramps' own main window by default — not whatever window the
    caller happens to be — so closing the caller's own window never
    closes this one along with it.

    :param path:       Filesystem path **or** ``https://`` URL to the Markdown
        file to display.  For local paths, the locale resolution convention
        (``locale/fr_FR/README.md`` etc.) is applied automatically.
    :param uistate:    The Gramps ``UiState`` object (used for window parenting
        and theme access).
    :param parent:     Optional ``Gtk.Window`` to use as a transient parent for
        the dialog, overriding the default of Gramps' own main window
        (``uistate.window``).
    :param title:      Window title.  Defaults to the ``# Heading`` in the
        file, or ``"Markdown Dash"`` if none is found.
    :param addon_name: Human-readable name of the calling add-on, used in the
        locale-invitation notice when no translation is available.
    :returns:          The ``Gtk.Dialog`` that was created (or, if a window
        for this same resolved file was already open, the existing one)
        and shown.  Callers may connect to its ``"response"`` signal if
        they need to react to the window closing.
    """
    is_remote = path.startswith("http://") or path.startswith("https://")
    resolved_path = path
    show_invite = False
    source_lang: str | None = None
    _tmp_path: str | None = None

    if is_remote:
        _tmp_path = _fetch_remote(path)
        if _tmp_path is not None:
            resolved_path = _tmp_path
        else:
            resolved_path = ""  # triggers the error page inside the gramplet
    else:
        res = resolve_localized_path(path)
        resolved_path = res.path
        show_invite = res.is_fallback
        source_lang = res.source_lang

    try:
        reader = _MarkdownReaderWindow(
            uistate,
            resolved_path=resolved_path,
            title=title,
            addon_name=addon_name,
            show_invite=show_invite,
            original_path=path,
            tmp_path=_tmp_path,
            source_lang=source_lang,
            parent=parent,
        )
    except WindowActiveError:
        # A window for this exact resolved file is already open --
        # ManagedWindow.__init__ itself already called _present() on it
        # (see gramps.gui.managedwindow.ManagedWindow.__init__) before
        # raising this, so just hand back its dialog rather than
        # building a second one for the same file.
        existing = uistate.gwm.get_item_from_id(
            _MarkdownReaderWindow.window_key_for(resolved_path)
        )
        return existing.dialog if existing is not None else None

    return reader.dialog


def _current_monitor_geometry() -> Gdk.Rectangle | None:
    """
    Return the work-area geometry of whichever monitor has the pointer.

    Used to size/position the reader window relative to *this* monitor
    every time it opens, rather than trusting
    ``ManagedWindow.setup_configs``'s own persisted width/height/
    position alone: those are saved once and restored verbatim on every
    later open, which is fine on a single-monitor setup but can produce
    a jarring flash-then-jump on a multi-monitor one -- a window first
    mapped at a stale position from a previous session (potentially on
    a different, or now-disconnected, monitor from Gramps' own main
    window) before the window manager or GTK itself relocates/resizes
    it into view, reported as exactly that: a small dialog momentarily
    appearing on the screen Gramps was launched on, followed by a
    full-size redraw on the screen the cursor is actually on.

    :returns: The work area (excludes panels/docks) of the monitor
        under the pointer, or ``None`` if the pointer position or a
        default display/screen isn't available (e.g. a non-interactive
        or headless test environment) -- callers should fall back to
        leaving ``setup_configs``'s own placement alone in that case.
    """
    display = Gdk.Display.get_default()
    if display is None:
        return None
    seat = display.get_default_seat()
    if seat is None:
        return None
    pointer = seat.get_pointer()
    if pointer is None:
        return None
    _screen, x, y = pointer.get_position()
    monitor = display.get_monitor_at_point(x, y)
    if monitor is None:
        return None
    return monitor.get_workarea()


def _size_and_center_on_current_monitor(
    window: Gtk.Window, fraction: float = 0.75
) -> None:
    """
    Resize and center *window* to ``fraction`` of the current monitor.

    "Current" means whichever monitor has the pointer right now -- see
    :func:`_current_monitor_geometry`. A no-op (leaving whatever
    ``ManagedWindow.setup_configs`` already applied in place) if that
    geometry isn't available for any reason, rather than guessing at a
    fallback size/position that might be wrong in a different way.

    :param window: The (already-realized) top-level window to place.
    :param fraction: Fraction of the monitor's work-area width/height
        to size the window to; defaults to 0.75 (75%).
    """
    workarea = _current_monitor_geometry()
    if workarea is None:
        return
    width = int(workarea.width * fraction)
    height = int(workarea.height * fraction)
    x = workarea.x + (workarea.width - width) // 2
    y = workarea.y + (workarea.height - height) // 2
    # Most window managers simply ignore resize()/move() requests while
    # a window is maximized -- and setup_configs() only ever persists
    # width/height/position, never window *state*, so a window that was
    # ever maximized in a previous session can come back still
    # maximized regardless of what this function asks for next,
    # matching a real report of the window opening at 100% of the
    # screen even with this function in place. Calling unmaximize()
    # first, unconditionally, is harmless on a window that was never
    # maximized to begin with.
    window.unmaximize()
    window.resize(width, height)
    window.move(x, y)


# ──────────────────────────────────────────────────────────────────────────────
#
# _MarkdownReaderWindow
#
# ──────────────────────────────────────────────────────────────────────────────
class _MarkdownReaderWindow(
    ManagedWindow
):  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """
    Thin ManagedWindow wrapper around a standalone _MarkdownViewer.

    Gives :func:`open_markdown_file`'s dialog a **Windows**-menu presence
    — registration, click-to-restore, and (keyed by the resolved file's
    own absolute path) reuse of an already-open window for that same
    file instead of a duplicate — the same as any other Gramps top-level
    window has, rather than the bare ``Gtk.Dialog`` this used to be
    before, which :class:`~gramps.gui.displaystate.GrampsWindowManager`
    has no way to know about at all.

    Internal to this module — external callers only ever see
    :func:`open_markdown_file`'s own return value, the underlying
    :class:`Gtk.Dialog` (:attr:`dialog`), exactly as before this class
    existed.
    """

    @staticmethod
    def window_key_for(resolved_path: str) -> str | None:
        """
        Return the ``uistate.gwm`` window-id a resolved file's own reader
        window is (or would be) registered under.

        A hash of the absolute path, not the path itself: this value
        also becomes part of a GTK action name
        (``gramps.gui.managedwindow.GrampsWindowManager.generate_id``,
        ``"wm-" + str(window_id)``, run through that module's own
        ``valid_action_name``). That sanitizer only replaces a handful
        of characters (space, underscore, parens, comma, apostrophe) —
        written for short plugin-id-like window keys, not a full
        filesystem path — and leaves ``/`` untouched, so a raw path
        produced a "wm-/home/.../README.md" action name GTK's own
        UIManager then rejected as invalid at menu-build time (logged as
        a WARNING, not raised, so registration itself still silently
        "worked," just with a menu action GTK would never actually
        invoke). A hex digest sides-steps this category of problem
        entirely rather than trying to keep pace with whatever character
        ``valid_action_name`` doesn't yet sanitize.

        :param resolved_path: the already locale-resolved file path (see
                               :func:`resolve_localized_path`), or ``""``
                               for the fetch-failed/error-page case
        :returns: a hex-digest string, stable and unique per distinct
                  absolute file path, or ``None`` for the ``""`` case,
                  where every window is its own private, never-reused
                  instance instead (there's no real *document* to key
                  reuse on when resolution itself failed entirely)
        """
        if not resolved_path:
            return None
        abs_path = os.path.abspath(resolved_path)
        return "md-" + sha1(abs_path.encode("utf-8")).hexdigest()

    def __init__(
        self,
        uistate,
        resolved_path: str,
        title: str | None,
        addon_name: str | None,
        show_invite: bool,
        original_path: str,
        tmp_path: str | None,
        source_lang: str | None,
        parent: Gtk.Window | None,
    ) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """
        Build and show the reader window.

        :param uistate: the Gramps ``UiState`` object
        :param resolved_path: the already locale-resolved file path (see
                               :func:`resolve_localized_path`)
        :param title: window/menu title override, or ``None`` to use the
                      file's own ``# Heading`` (resolved once the file
                      loads) or "Markdown Dash"
        :param addon_name: passed through to ``_MarkdownViewer`` for its
                            locale-invitation notice
        :param show_invite: passed through to ``_MarkdownViewer``
        :param original_path: passed through to ``_MarkdownViewer``
        :param tmp_path: passed through to ``_MarkdownViewer``
        :param source_lang: passed through to ``_MarkdownViewer``
        :param parent: an explicit transient-parent override; ``None``
                        keeps :class:`ManagedWindow`'s own default of
                        Gramps' own main window (``uistate.window``),
                        which is what a top-level (``track=[]``) window
                        gets automatically
        :raises WindowActiveError: if a reader window for this same
            resolved file is already open — raised by
            ``ManagedWindow.__init__`` itself, which also already
            presents the existing window before raising; see
            :func:`open_markdown_file`'s handling of this
        """
        # An explicit title= is a deliberate, permanent override; only
        # without one does the file's own "# Heading" get to drive the
        # titlebar/Windows-menu label (see _cb_title_changed) -- matching
        # this function's own documented default ("Defaults to the
        # # Heading in the file").
        self._title_override = title is not None
        self._menu_title = title or _("Markdown Dash")
        window_key = self.window_key_for(resolved_path) or id(self)
        ManagedWindow.__init__(self, uistate, [], window_key)

        # A top-level (track=[]) ManagedWindow already parents itself to
        # Gramps' own main window via self.parent_window, set just above
        # by ManagedWindow.__init__ -- overridden here only if the
        # caller explicitly asked for a different transient parent.
        if parent is not None:
            self.parent_window = parent

        self.dialog = Gtk.Dialog(
            title=self._menu_title, flags=Gtk.DialogFlags.DESTROY_WITH_PARENT
        )
        self.dialog.add_button(_("Close"), Gtk.ResponseType.CLOSE)
        self.dialog.connect("response", self._cb_response)
        self.set_window(self.dialog, None, self._menu_title)
        self.setup_configs("interface.markdowndash-reader", 700, 550)

        self.viewer = _MarkdownViewer(
            initial_path=resolved_path,
            uistate=uistate,
            show_locale_invite=show_invite,
            original_path=original_path,
            addon_name=addon_name,
            tmp_path=tmp_path,
            source_lang=source_lang,
            on_title_changed=self._cb_title_changed,
        )
        content = self.dialog.get_content_area()
        content.set_border_width(0)
        content.pack_start(self.viewer.widget, True, True, 0)

        # Only after the real content is packed in -- called any earlier
        # (as an earlier revision did, right after setup_configs()),
        # GTK recomputes the still-unmapped dialog's size from the
        # packed content's own natural size once show() actually runs,
        # silently overriding an explicit resize() made before there
        # was any content to size against. This is what actually
        # produced "still opens at 100% of the screen, not 75%" despite
        # the resize call being made. See this function's own docstring
        # for why a fresh, monitor-aware size/position is wanted here
        # at all, in place of setup_configs' own persisted values.
        _size_and_center_on_current_monitor(self.dialog)

        # A real report confirmed the window can still come back
        # maximized despite the above: neither Gramps' own
        # ManagedWindow.setup_configs() nor this addon persists any
        # "was maximized" flag anywhere (confirmed by inspecting
        # setup_configs itself -- it only ever saves width/height/
        # position), so whatever is restoring that state is doing so
        # entirely outside this addon's own code -- most likely the
        # desktop session/window manager's own window-state memory for
        # this window's role/class, which no application-level fix can
        # prevent from being *applied* in the first place. What this
        # addon *can* do is catch that state once it's actually applied
        # and immediately correct it: connecting to "window-state-event"
        # and reacting the first time MAXIMIZED shows up un-maximizes
        # and re-applies the target geometry right then, then stops
        # listening -- so a person who deliberately maximizes the
        # window later during this same session is left alone. This is
        # a real, deliberate choice not to introduce any settings file
        # of our own for this (no filter.ini equivalent here): a
        # colocated one next to the .md file makes no sense to manage,
        # and a single global one has no sensible meaning across
        # unrelated documents either -- always un-maximizing on open is
        # simpler and matches what was actually asked for.
        state_handler_id = None

        def cb_window_state_event(_widget, event):
            nonlocal state_handler_id
            if event.new_window_state & Gdk.WindowState.MAXIMIZED:
                self.dialog.unmaximize()
                # unmaximize() is itself an async X11 request; applying
                # the target geometry on the next main-loop iteration
                # (rather than immediately, back-to-back) gives it a
                # chance to actually land first, rather than racing it.
                GLib.idle_add(
                    lambda: _size_and_center_on_current_monitor(self.dialog) or False
                )
                if state_handler_id is not None:
                    self.dialog.disconnect(state_handler_id)
                    state_handler_id = None
            return False

        state_handler_id = self.dialog.connect("window-state-event", cb_window_state_event)

        self.show()

    def _cb_title_changed(self, new_title: str) -> None:
        """
        Sync this window's own titlebar and Windows-menu label with the
        file's own resolved title.

        Invoked by the shared ``_update_frame_title`` (see
        ``MarkdownDash``'s own method of that name) every time a file
        loads, including the first load — this is what actually
        implements this window's own ``title=None`` default of "use the
        file's own ``# Heading``" (see :meth:`__init__`'s docstring). A
        no-op whenever an explicit ``title`` was given instead, since
        that's a deliberate, permanent override the caller asked for.

        :param new_title: the file's own resolved title — its
                           ``# Heading``, or "Markdown Dash" if the file
                           has none
        """
        if self._title_override:
            return
        self._menu_title = new_title
        self.dialog.set_title(new_title)
        # gramps.gui.managedwindow.GrampsWindowManager.display_menu_list
        # reads each registered window's own self.menu_label attribute
        # directly -- it does NOT call build_menu_names() again -- and
        # that attribute was only ever set once, by ManagedWindow.__init__
        # caching build_menu_names()'s original return value. Rebuilding
        # the menu without also updating this cached attribute first
        # would just redraw the exact same (stale) label. build_menu_names
        # itself (below) already returns self._menu_title, so this keeps
        # both in step.
        self.menu_label = new_title
        gwm = getattr(self.uistate, "gwm", None)
        if gwm is not None:
            gwm.build_windows_menu()

    def _cb_response(self, dialog: Gtk.Dialog, _response_id: int) -> None:
        """
        Route the dialog's own **Close** button through :meth:`close`.

        ``ManagedWindow.set_window`` already wires the window-manager
        (title-bar X / Alt+F4) close path to :meth:`close` via a
        ``"delete-event"`` connection of its own; this dialog's explicit
        **Close** button fires GTK's ``"response"`` signal instead, which
        needs its own connection to go through the same
        window-manager-deregistration path, rather than just calling
        ``dialog.destroy()`` directly and leaving a stale entry in the
        **Windows** menu that would error if ever clicked afterward.

        :param dialog: this window's own ``Gtk.Dialog`` (same as
                        :attr:`dialog`)
        :param _response_id: the GTK response id (unused — the only
                              button is Close)
        """
        self.close()
        dialog.destroy()

    def build_menu_names(self, obj: object) -> tuple[str, str | None]:
        """
        Return this window's Gramps **Windows** menu label.

        Required by :class:`~gramps.gui.managedwindow.ManagedWindow`.
        ``None`` for the submenu label lists this window directly as a
        single leaf entry, since it never opens further ManagedWindow
        children of its own.

        :param obj: unused — required by the base class's call signature
        :returns: ``(menu_label, None)``
        """
        return (self._menu_title, None)

    def build_window_key(self, obj: object) -> object:
        """
        Return the ``uistate.gwm`` window-id to register/look this window
        up under.

        :class:`~gramps.gui.managedwindow.ManagedWindow`'s own default
        implementation returns ``id(obj)`` — the raw Python object
        identity of whatever *obj* is — which is exactly wrong for
        value-based reuse-by-file-path: two separate calls each build
        their own new (unequal, unstable) string object for the same
        path text, so keying on *their* identities could never actually
        collide/reuse. Overridden here to return *obj* itself instead —
        already the resolved key string window_key_for() computed
        (or an ``id(self)`` fallback for the no-real-document case) —
        the same value-based-key pattern Gramps' own primary-object
        editors use (see ``gramps.gui.editors.editprimary.build_window_key``,
        keying on a handle string the same way).

        :param obj: the key passed as ``ManagedWindow.__init__``'s own
                    ``obj`` parameter — here, always already the exact
                    key to use, computed by :meth:`window_key_for`
        :returns: *obj*, unchanged
        """
        return obj


# ──────────────────────────────────────────────────────────────────────────────
#
# _MarkdownViewer
#
# ──────────────────────────────────────────────────────────────────────────────
# ------------------------------------------------------------
#
# _MarkdownViewer
#
# ------------------------------------------------------------
class _MarkdownViewer:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Self-contained Markdown viewer widget used by :func:`open_markdown_file`.

    This class duplicates none of the rendering logic — it wires up the same
    ``_render`` / ``_load`` machinery used by :class:`MarkdownDash` but without
    the Gramps plugin lifecycle (no ``init()`` / ``on_load()`` / ``Gramplet``
    base class).  Public rendering methods are late-bound from
    :class:`MarkdownDash` at module load time (see ``_SHARED_METHODS``).
    It is intentionally private; external callers should use
    :func:`open_markdown_file`.
    """

    def __init__(
        self,
        initial_path: str,
        uistate,
        show_locale_invite: bool = False,
        original_path: str = "",
        addon_name: str | None = None,
        tmp_path: str | None = None,
        source_lang: str | None = None,
        on_title_changed: Callable[[str], None] | None = None,
    ) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """Initialise the viewer and immediately load *initial_path*.

        :param initial_path:      Resolved local path to display.  Empty string
            triggers the file-not-found error page.
        :param uistate:           Gramps UiState (for theme / window access).
        :param show_locale_invite: When ``True``, the error / fallback page
            includes a localisation-invitation notice.
        :param original_path:     The path the caller originally requested
            (before locale resolution); shown in error messages.
        :param addon_name:        Human-readable calling add-on name for the
            invitation notice.
        :param tmp_path:          Temporary file to delete on destruction
            (used for remote fetches).
        :param source_lang:       ISO 639-1 code of the file's authoring
            language (e.g. ``"fi"``), or ``None`` for unlabelled English.
        :param on_title_changed:  Optional callback invoked with the file's
            own resolved title (its ``# Heading``, or the "Markdown Dash"
            default) every time :meth:`_update_frame_title` runs — i.e. on
            every load, including the first. Used by
            :class:`_MarkdownReaderWindow` to keep its own titlebar and
            Gramps **Windows**-menu entry in sync with whatever file is
            currently loaded; ``None`` for any other caller that has no
            such window chrome of its own to update.
        """
        self.uistate = uistate
        self._show_locale_invite = show_locale_invite
        self._original_path = original_path or initial_path
        self._addon_name = addon_name
        self._tmp_path = tmp_path
        self._source_lang = source_lang
        self._on_title_changed = on_title_changed
        self.current_file: str | None = None
        self._asset_base: str | None = None
        self._tags: dict = {}
        self._link_uris: dict = {}
        self._anchor_marks: dict = {}
        self._history: list[str] = []
        self._history_index: int = -1
        self._signal_ids: list = []

        self.widget, self._footer_box = self._build_widget()

        if initial_path and os.path.isfile(initial_path):
            self._load(initial_path)  # pylint: disable=no-member
        else:
            self._render_error_md(self._original_path)

    # Delegate all rendering methods to MarkdownDash equivalents at runtime.
    # Rather than copy-paste them, we graft them in after class construction
    # so both classes share one canonical implementation.  See the bottom of
    # this module for the binding.

    def _build_widget(self) -> tuple[Gtk.Box, Gtk.Box]:
        """Build the viewer widget tree (textview + full footer toolbar)."""
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
            self.textview.connect(
                "motion-notify-event",
                self._on_motion,  # pylint: disable=no-member
            ),
            self.textview.connect(
                "button-press-event",
                self._on_click,  # pylint: disable=no-member
            ),
            self.textview.connect(
                "key-press-event",
                self._on_key_press,  # pylint: disable=no-member
            ),
        ]
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        # Disabling kinetic scrolling is a targeted response to a report of
        # persistent "gtk_widget_size_allocate(): ... negative height"
        # warnings surviving even after the table-widget child-anchor (the
        # confirmed, live-tested cause of the *original* report) was
        # replaced with plain text -- alongside a *second*, functional
        # symptom reported alongside it: the scroll position snapping to a
        # different spot on scroll-up, such that the top of the document
        # could not be reached at all. That second symptom in particular
        # points at GTK's own kinetic-scrolling/rubber-banding physics
        # (momentum + overscroll-bounce animation) on this ScrolledWindow,
        # not at anything in this module's own rendering -- a plain
        # Gtk.TextView with only bare paragraph text (no Markdown Dash
        # code involved at all) was not reproducible against a
        # programmatic, unclamped overscroll in this sandbox, but kinetic
        # scrolling's real behavior (momentum builds from a sequence of
        # real input events, not a single value change, and manifests
        # through a live compositor/input driver) could not be exercised
        # the same way here -- this could not be verified fixed, only
        # applied as the most targeted, low-risk thing to try next.
        sw.set_kinetic_scrolling(False)
        sw.add(self.textview)

        # Same footer (Edit / status-path / folder-history / Browse) the
        # embedded MarkdownDash gramplet itself uses — see
        # _build_footer_box, shared via _SHARED_METHODS so both classes
        # build one identical, single-source-of-truth toolbar rather
        # than each keeping their own, easily-diverging copy.
        footer = self._build_footer_box()  # pylint: disable=no-member

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.pack_start(sw, True, True, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        vbox.pack_start(footer, False, False, 0)

        return vbox, footer

    # _set_status intentionally has no override here (this class used to
    # have its own copy, byte-for-byte identical to MarkdownDash's own —
    # including the get_realized() bug fixed there, see that method's
    # own docstring) -- MarkdownDash's now-fixed version is shared in as
    # -is instead, the same as _set_loaded just below.
    # _set_loaded intentionally has no override here (unlike _set_status
    # and _update_nav_buttons just above/below it) -- MarkdownDash's own
    # fuller version (see _SHARED_METHODS) is shared in as-is instead,
    # now that _build_footer_box (also shared) gives this class the same
    # _edit_btn/_folder_btn/_populate_folder_menu it expects to update.

    def _render_error_md(self, attempted_path: str) -> None:
        """Render a file-not-found / network-error notice as inline Markdown.

        When *show_locale_invite* is ``True``, an additional section is
        appended inviting translation.  The message is tailored to the
        situation:

        - **No source_lang** (unlabelled English baseline shown as fallback):
          Invite translation into the user's language.
        - **source_lang set, differs from user lang** (e.g. Finnish README
          shown to an English user): Invite translation both into English
          (as the universal baseline) and into the user's own language.
        - **source_lang matches user lang** (Finnish user sees Finnish README):
          No invite — they are already reading the right language.

        :param attempted_path: The path or URL that could not be opened.
        """
        name = os.path.basename(attempted_path) or attempted_path
        is_url = attempted_path.startswith("http://") or attempted_path.startswith(
            "https://"
        )

        if is_url:
            heading = _("Remote File Unavailable")
            detail = _(f"Could not download: `{attempted_path}`")
            hint = _(
                "Check your internet connection or try again later. "
                "You can also browse for a local copy using the Open button."
            )
        else:
            heading = _("File Not Found")
            detail = f"**{_('Requested path:')}** `{attempted_path}`"
            hint = _(
                "The file may have been moved, renamed, or deleted. "
                "Use the \u2018Open\u2019 button to browse for it."
            )

        md = f"# \u274c {heading}\n\n{detail}\n\n> {hint}\n"

        if self._show_locale_invite:
            lang_full, user_short = locale_lang()
            src = self._source_lang  # e.g. "fi", or None for English baseline
            addon_label = f" ({self._addon_name})" if self._addon_name else ""
            md += "\n---\n\n"
            md += f"## \U0001f310 {_('Help us translate this add-on')}\n\n"

            if src and src.split("_")[0] != user_short:
                # Foreign-language baseline (e.g. README_fi.md) shown to a
                # different-language user (e.g. English)
                md += _(
                    "This add-on's documentation{addon} was written in "
                    "**{src_lang}** and no translation is available yet "
                    "for **{user_lang}**.\n\n"
                    "You can help by:\n\n"
                    "- Translating it into **English** first — this creates "
                    "a `README.md` that all future translators can work from.\n"
                    "- Or translating directly into **{user_lang}** and "
                    "placing it at `locale/{user_lang}/README.md`.\n\n"
                    "See the [Gramps Translation HOWTO]"
                    "(https://gramps-project.org/wiki/index.php/Translating_Gramps) "
                    "or ask on the "
                    "[Gramps Discourse forum](https://gramps.discourse.group/)."
                ).format(
                    addon=addon_label,
                    src_lang=src,
                    user_lang=lang_full,
                )
            else:
                # Unlabelled English baseline shown to a non-English user
                md += _(
                    "No translation is available for **{lang}** yet{addon}. "
                    "The English version has been shown as a fallback.\n\n"
                    "If you would like to contribute a translation, place your "
                    "translated file at `locale/{lang}/README.md` alongside "
                    "this add-on, then see the [Gramps Translation HOWTO]"
                    "(https://gramps-project.org/wiki/index.php/Translating_Gramps) "
                    "or open a request on the "
                    "[Gramps Discourse forum](https://gramps.discourse.group/)."
                ).format(lang=lang_full, addon=addon_label)
            md += "\n"

        self._render(md)  # pylint: disable=no-member
        self._set_status(_(f"File not found: '{name}'"), error=True)

    def _update_nav_buttons(self) -> None:
        """No-op for the dialog viewer (no nav toolbar in this shell)."""

    def __del__(self) -> None:
        """Clean up any temporary file created for a remote fetch."""
        if self._tmp_path and os.path.isfile(self._tmp_path):
            try:
                os.unlink(self._tmp_path)
            except OSError:
                pass


# ------------------------------------------------------------
#
# MarkdownDash
#
# ------------------------------------------------------------
class MarkdownDash(Gramplet):  # pylint: disable=too-many-instance-attributes
    """Dashboard gramplet for viewing Markdown files with style and control overrides.

    When used as a Dashboard gramplet the default startup file is
    ``README.md`` in the plugin directory.  External add-ons should use
    :func:`open_markdown_file` instead of instantiating this class directly.
    """

    def on_load(self) -> None:
        """Lifecycle hook — intentionally empty; setup is in :meth:`init`."""

    def on_unload(self) -> None:
        """Disconnect signals before widget tree destruction."""
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

        for attr in (
            "_browse_btn",
            "_folder_btn",
            "_edit_btn",
        ):
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

    def init(self) -> None:
        """Build interface layout safely within Gramps container tree frames.

        The startup file is resolved in this priority order:

        1. ``self._initial_path`` — set by :func:`open_markdown_file` or any
           other caller before ``init()`` runs (not used in normal Dashboard
           gramplet operation, but reserved for future integration).
        2. ``README.md`` in the plugin directory — the gramplet's own home
           document.
        3. No file found — the viewer is left in a *Ready* state showing an
           empty buffer.
        """
        self.current_file: str | None = None
        self._asset_base: str | None = None
        self._tags: dict = {}
        self._link_uris: dict = {}
        self._anchor_marks: dict = {}
        self._history: list[str] = []
        self._history_index: int = -1

        # Safe extraction of Gramps-managed container widgets
        gramps_sw = self.gui.get_container_widget()
        # See the matching, more detailed comment on the standalone
        # reader window's own Gtk.ScrolledWindow (_MarkdownViewer's
        # _build_widget) for why this is here -- same reasoning, applied
        # to the Gramps-framework-owned scrolled window this embedded
        # gramplet reuses rather than creating its own.
        if hasattr(gramps_sw, "set_kinetic_scrolling"):
            gramps_sw.set_kinetic_scrolling(False)
        sw_parent = gramps_sw.get_parent()

        outer_vbox, self._footer_box = self._build_gui()

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
            fallback.pack_start(self._footer_box, False, False, 0)
            fallback.show_all()
            gramps_sw.add(fallback)

        self.gui.WIDGET = outer_vbox
        outer_vbox.show_all()

        # Priority 1: caller-supplied initial path (e.g. from a Help button)
        initial = getattr(self, "_initial_path", None)
        if initial:
            self._load(initial)
            return

        # Priority 2: plugin-local README.md
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        readme = os.path.join(plugin_dir, "README.md")
        self._load(readme)
        # _load() calls _render_error_md() internally when the file is absent,
        # so no separate os.path.isfile() guard is needed here.

    def _build_gui(self) -> tuple[Gtk.Box, Gtk.Box]:
        """Create text display box layout views and action toolbars.

        :returns: Tuple of (outer_vbox, footer_box) where outer_vbox is the
            top-level container and footer_box holds the status-bar controls.
        """
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
            self.textview.connect("key-press-event", self._on_key_press),
        ]

        footer = self._build_footer_box()

        outer_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        outer_vbox.set_border_width(0)
        outer_vbox.pack_end(footer, False, False, 0)
        outer_vbox.pack_end(Gtk.Separator(), False, False, 0)

        return outer_vbox, footer

    def _build_footer_box(self) -> Gtk.Box:
        """
        Build the status/file-control footer bar.

        Shared (see ``_SHARED_METHODS``) between the embedded
        ``MarkdownDash`` gramplet's own :meth:`_build_gui` and the
        standalone ``_MarkdownViewer``'s own ``_build_widget`` — both
        packed the same four controls independently until this was
        factored out, which is how the standalone dialog ended up with
        only its status label and none of the Edit/Browse/folder-history
        controls the embedded gramplet has always had.

        :returns: the assembled ``Gtk.Box``, already populated with the
                  Edit, status/path label, folder-history menu, and
                  Browse controls — the caller packs this into its own
                  outer container.

        Every widget below whose visibility ``_load`` toggles per-file
        (via its ``<!-- controls=... -->`` directive) gets
        ``set_no_show_all(True)``: a standalone ``_MarkdownReaderWindow``
        calls ``Gtk.Window.show_all()`` once, when the window itself
        first opens (see ``ManagedWindow.show()``) — which recursively
        force-shows every descendant widget regardless of any ``.hide()``
        already called during that same file's initial load, *unless*
        that widget is marked ``no_show_all``. Without this, a file's
        own ``controls=false`` (or per-control ``edit=false`` etc.) was
        silently overridden the moment the window opened — the exact
        directives this footer exists to obey, undone by the one
        ``show_all()`` call the embedded gramplet never has to contend
        with (Gramplets are shown individually as they're added to their
        pane, never via one recursive sweep like this).
        """
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        footer.set_border_width(2)
        footer.set_no_show_all(True)

        edit_img = Gtk.Image.new_from_icon_name(
            "document-edit", Gtk.IconSize.SMALL_TOOLBAR
        )
        self._edit_btn = Gtk.Button()
        self._edit_btn.set_image(edit_img)
        self._edit_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._edit_btn.set_tooltip_text(_("Edit current file in default editor"))
        self._edit_btn.set_sensitive(False)
        self._edit_btn.set_no_show_all(True)
        self._edit_btn_sids = [self._edit_btn.connect("clicked", self.cb_edit_file)]
        footer.pack_start(self._edit_btn, False, False, 0)

        self.info_label = Gtk.Label()
        self.info_label.set_halign(Gtk.Align.START)
        self.info_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.info_label.set_hexpand(True)
        self.info_label.set_no_show_all(True)
        footer.pack_start(self.info_label, True, True, 4)

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
        self._folder_btn.set_no_show_all(True)
        footer.pack_end(self._folder_btn, False, False, 0)

        browse_img = Gtk.Image.new_from_icon_name(
            "document-open", Gtk.IconSize.SMALL_TOOLBAR
        )
        self._browse_btn = Gtk.Button()
        self._browse_btn.set_image(browse_img)
        self._browse_btn.set_relief(Gtk.ReliefStyle.NONE)
        self._browse_btn.set_tooltip_text(_("Open Markdown file\u2026"))
        self._browse_btn.set_no_show_all(True)
        self._browse_btn_sids = [self._browse_btn.connect("clicked", self.cb_browse)]
        footer.pack_end(self._browse_btn, False, False, 0)

        colour = "#555555"
        self.info_label.set_markup(
            f'<small><span foreground="{colour}">{_esc(_("Ready"))}</span></small>'
        )

        return footer

    def _parse_directives(self, lines: list[str]) -> tuple[str | None, dict, str]:
        """Recognise a leading title heading and/or options comment.

        Position is strict:

        - Line 1 (index 0) is the Gramplet title **only** if it is an ATX
          H1 heading (``# Title``). Any other first line is left as
          ordinary document content -- it is *not* eligible to become the
          title just because line 1 didn't qualify.
        - Line 2 (index 1) is the layout-options directive **only** if it
          is a single-line HTML comment (``<!-- key=value ... -->``). Any
          other second line is left as ordinary document content.

        The two checks are independent and non-contiguous: a file can have
        a title with no options comment, an options comment with no title
        (e.g. line 1 is a normal paragraph), both, or neither -- only the
        lines that actually matched their required position and format are
        removed from the returned Markdown text, never a blanket "first N
        lines" prefix.

        :param lines: Raw lines read from the Markdown file (each still
                      ending in ``\\n``, as returned by ``file.readlines()``).
        :returns: ``(title_or_None, options_dict, remaining_markdown_text)``.
        """
        title = None
        options: dict = {}
        skip_indices: set[int] = set()

        if lines:
            first = lines[0].strip()
            if "`" not in first and first.startswith("# "):
                title = first[2:].strip()
                skip_indices.add(0)

        if len(lines) > 1:
            second = lines[1].strip()
            if (
                "`" not in second
                and second.startswith("<!--")
                and second.endswith("-->")
            ):
                raw_options = second[4:-3].strip()
                matches = re.findall(r"(\w+)\s*=\s*([\w\-]+)", raw_options)
                for key, value in matches:
                    if value.lower() == "true":
                        options[key] = True
                    elif value.lower() == "false":
                        options[key] = False
                    else:
                        options[key] = value
                skip_indices.add(1)

        if title is None and not options:
            return None, {}, "".join(lines)

        remaining = "".join(
            line for idx, line in enumerate(lines) if idx not in skip_indices
        )
        return title, options, remaining

    def _get_localized_filepath(self, target_path: str) -> str:
        """Resolve *target_path* to the best available locale variant.

        Delegates to the module-level :func:`resolve_localized_path`.  The
        *is_fallback* and *source_lang* fields are discarded here because the
        gramplet-level error page does not carry the locale-invitation notice
        (that is reserved for the :func:`open_markdown_file` dialog path where
        the calling add-on identity is known).

        :param target_path: Baseline file path to resolve.
        :returns: Best-matching locale variant, or *target_path* unchanged.
        """
        return resolve_localized_path(target_path).path

    def _set_status(self, msg: str, error: bool = False) -> None:
        """Update status label.

        :param msg:   Status text to display.
        :param error: When ``True``, render the text in red.
        """
        label = getattr(self, "info_label", None)
        # No get_realized() check: set_markup() is a plain property
        # change, safe on a Gtk.Label whether or not it's been realized
        # (realization only matters for drawing operations, not property
        # changes) -- confirmed directly. That check previously meant
        # every status update attempted during a _MarkdownViewer's very
        # first _load() (called from within __init__, always before the
        # widget has ever been shown/realized) silently did nothing,
        # leaving _build_footer_box's initial "Ready" text in place
        # forever instead of the loaded file's own name/path. The
        # embedded MarkdownDash gramplet's info_label happens to already
        # be realized by the time it ever loads a file (Gramps' own
        # Gramplet framework shows a gramplet's widgets before calling
        # on_load()), so this never surfaced there.
        if label is None:
            return
        colour = "#cc0000" if error else "#555555"
        label.set_markup(
            f'<small><span foreground="{colour}">{_esc(msg)}</span></small>'
        )

    def _set_loaded(self, path: str) -> None:
        """Update layout tags, buttons, and populates the adjacent documents selector."""
        filename = os.path.basename(path)
        parent = os.path.basename(os.path.dirname(path))
        grandparent = os.path.basename(os.path.dirname(os.path.dirname(path)))

        _lang_full, lang_short = locale_lang()

        if parent in ("locale", lang_short) or (len(parent) <= 5 and "_" in parent):
            actual_dir = (
                os.path.dirname(os.path.dirname(path))
                if parent != "locale"
                else os.path.dirname(path)
            )
            parent = os.path.basename(os.path.abspath(actual_dir))

        location = f"{grandparent}/{parent}" if grandparent else parent
        self._set_status(_("Loaded: {} from {}").format(filename, location))

        if self._edit_btn:
            self._edit_btn.set_sensitive(True)
        if self._folder_btn:
            self._folder_btn.set_sensitive(True)
            self._populate_folder_menu(path)

    def _populate_folder_menu(self, current_path: str) -> None:
        """Fill the popup dropdown with session history and sibling files.

        A "Previous" entry is pinned at the top, backed by this Gramplet
        instance's own per-session navigation history (:attr:`_history`) --
        the same history used by :meth:`cb_back`/:meth:`cb_fwd` -- showing
        the filename it would return to, or disabled when there's nowhere
        to go back to yet.  Below a separator, the remaining entries are
        the sibling ``.md`` / ``.markdown`` files in the same folder,
        including any ``README_<lang>.md`` source-language variants, each
        tooltipped with its parent folder's name so that a generic
        filename like "README.md" is still identifiable at a glance. The
        file currently displayed is bulleted and boldfaced, but stays
        clickable like any other entry -- selecting it re-triggers
        :meth:`_load` on the same path, giving the user an explicit way to
        reload the current file rather than a disabled, greyed-out entry.

        :param current_path: The file currently displayed in the viewer.
        """
        menu = getattr(self, "_folder_menu", None)
        if menu is None:
            return
        for child in menu.get_children():
            menu.remove(child)

        # Use the canonical asset base so the menu always shows files from the
        # addon directory, not from inside locale/fi/ or similar.
        folder = getattr(self, "_asset_base", None) or os.path.dirname(current_path)
        if not folder:
            folder = os.path.dirname(current_path)
        # Belt-and-braces for the case _asset_base wasn't set yet
        locale_marker = os.sep + "locale" + os.sep
        if locale_marker in folder:
            folder = folder.split(locale_marker)[0]

        # ── Previous (per-session history) ──────────────────────────────
        has_previous = self._history_index > 0
        if has_previous:
            prev_name = os.path.basename(self._history[self._history_index - 1])
            prev_label = "\u2190 {}: {}".format(_("Previous"), prev_name)
        else:
            prev_label = "\u2190 {}".format(_("Previous"))
        prev_item = Gtk.MenuItem(label=prev_label)
        if has_previous:
            prev_item.connect("activate", lambda _mi: self.cb_back(None))
        else:
            prev_item.set_sensitive(False)
        menu.append(prev_item)
        menu.append(Gtk.SeparatorMenuItem())

        # ── Sibling files ───────────────────────────────────────────────
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
            folder_name = os.path.basename(folder.rstrip(os.sep)) or folder
            for fname in md_files:
                is_current = fname == current_name
                # Annotate source-language files so the user knows what they are
                lang_note = ""
                m = LANG_SUFFIX_RE.match(fname)
                if m:
                    _lg = m.group("lang")
                    lang_note = f" [{_lg}]"
                prefix = "• " if is_current else "  "
                label_text = f"{prefix}{fname}{lang_note}"
                full_path = os.path.join(folder, fname)
                if is_current:
                    # Boldface (rather than dim/disable) the file currently
                    # being viewed, and keep it clickable -- selecting it
                    # re-triggers _load() on the same path, giving the user
                    # an explicit "reload this file" action rather than a
                    # dead, greyed-out menu entry.
                    item = Gtk.MenuItem()
                    gtk_label = Gtk.Label(label=label_text)
                    gtk_label.set_xalign(0.0)
                    gtk_label.set_markup(
                        "<b>{}</b>".format(GLib.markup_escape_text(label_text))
                    )
                    item.add(gtk_label)
                else:
                    item = Gtk.MenuItem(label=label_text)
                item.set_tooltip_text(folder_name)
                item.connect("activate", lambda _mi, p=full_path: self._load(p))
                menu.append(item)

        menu.show_all()

    def _browse_start_dir(self) -> str:
        """Return the best starting directory for the file-browser dialog.

        Prefers ``_asset_base`` (the canonical document directory, independent
        of any locale subdirectory) so the browser opens where the user's
        Markdown files actually live, not inside ``locale/fi/``.

        :returns: Absolute path to the directory to open in the file chooser.
        """
        base = getattr(self, "_asset_base", None)
        if base and os.path.isdir(base):
            return base
        if self.current_file:
            candidate = os.path.dirname(self.current_file)
            # Belt-and-braces: strip locale subdirectory if _asset_base missing
            locale_marker = os.sep + "locale" + os.sep
            if locale_marker in candidate:
                candidate = candidate.split(locale_marker)[0]
            if os.path.isdir(candidate):
                return candidate
        return os.path.dirname(os.path.abspath(__file__))

    def _open_uri(self, uri: str) -> None:
        """Open system external paths safely."""
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
        except GLib.Error:
            try:
                # xdg-open is fire-and-forget; we intentionally don't wait on it
                # pylint: disable=consider-using-with
                subprocess.Popen(["xdg-open", uri])
                # pylint: enable=consider-using-with
            except OSError:
                self._set_status(_(f"Could not open: {uri}"), error=True)

    def _resolve_path(self, path: str) -> str:
        """Resolve a relative asset path against the canonical document base.

        Asset paths (images, local hyperlinks) in a Markdown file are always
        relative to the *canonical* (pre-locale-resolution) document directory,
        not the locale subdirectory where the rendered file actually lives.
        This means images sitting next to ``README.md`` are still found when a
        locale variant at ``locale/fi/README.md`` is being displayed.

        Resolution order for each relative *path*:

        1. Locale-specific asset: ``<asset_base>/locale/<lang>/<path>``
        2. Canonical asset:        ``<asset_base>/<path>``
        3. Absolute path returned unchanged.
        4. *path* returned as-is if nothing resolves (caller handles missing).

        :param path: Relative or absolute asset path from the Markdown source.
        The locale-aware lookup itself is
        :func:`MarkdownUtils.resolve_localized_asset`.

        :returns:    Best-matching absolute filesystem path.
        """
        if os.path.isabs(path):
            return path

        base = getattr(self, "_asset_base", None)
        if not base and self.current_file:
            # Fallback: strip locale subdirectory if _asset_base wasn't set
            base = os.path.dirname(self.current_file)
            locale_marker = os.sep + "locale" + os.sep
            if locale_marker in base:
                base = base.split(locale_marker)[0]

        if not base:
            return path

        return resolve_localized_asset(base, path)

    def _seg_tag_at(self, x: int, y: int) -> tuple[str | None, str | None]:
        """Fetch custom elements under point cursor locations."""
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
        """Navigate display scroll box down to matching internal anchors."""
        mark = self._anchor_marks.get(slug)
        if mark is None:
            self._set_status(_("Anchor not found: #{}").format(slug), error=True)
            return
        self.textview.scroll_to_mark(mark, 0.0, True, 0.0, 0.1)

    def _handle_transient_close(self, _widget, _event=None) -> bool:
        """Save settings when popup targets close out."""
        self.save_settings_to_gramps(active=False)
        return False

    # ── file loading ───────────────────────────────────────────────────

    def _update_frame_title(self, final_title: str) -> None:
        """Update window frame layout labels without triggering
        deletion lookup KeyErrors."""
        try:
            self.title = final_title
            if hasattr(self, "gui") and self.gui:
                if (
                    hasattr(self.gui, "frame")
                    and self.gui.frame
                    and hasattr(self.gui.frame, "set_label")
                ):
                    self.gui.frame.set_label(final_title)

                pane = getattr(self.gui, "pane", None)
                gramplet_map = getattr(pane, "gramplet_map", None) if pane else None
                current_gui_title = getattr(self.gui, "title", None)

                if gramplet_map and current_gui_title in gramplet_map:
                    self.gui.set_title(final_title)
                else:
                    self.gui.title = final_title

            # A standalone _MarkdownReaderWindow (see open_markdown_file)
            # has no self.gui at all -- it registers this hook instead
            # (see _MarkdownViewer's own on_title_changed parameter) so
            # its own titlebar and Windows-menu label can follow the
            # loaded file's own "# Heading", the same way the embedded
            # gramplet's frame label does above.
            on_title_changed = getattr(self, "_on_title_changed", None)
            if on_title_changed is not None:
                on_title_changed(final_title)
        except Exception:
            pass

    def _load(self, path: str, track_history: bool = True) -> None:
        """Read and render a Markdown file, optionally recording it in history.

        File-not-found conditions are rendered as an inline Markdown error page
        so the user sees the problem in context rather than a modal dialog.
        Genuine read/parse exceptions still surface as a status-bar message.

        :param path:          Filesystem path to the Markdown file.
        :param track_history: When ``True`` (default), push *path* onto the
            navigation history stack and update Back/Forward sensitivity.
            Pass ``False`` when navigating via Back/Forward buttons to avoid
            corrupting the stack.
        """
        path = os.path.abspath(os.path.expanduser(path))
        # Capture the canonical asset base BEFORE locale resolution.
        # All relative links and images in the file must resolve relative to
        # the directory of the originally-requested (canonical) file, not the
        # locale variant's subdirectory.  For example, if the Finnish locale
        # variant is at  locale/fi/README.md  but images live next to the
        # English README.md, _asset_base must point at the parent directory.
        # NOTE: path must be absolute here (os.path.abspath above) so that
        # os.path.dirname yields the plugin dir, not the process CWD.
        canonical_base = os.path.dirname(path)
        path = self._get_localized_filepath(path)

        if not os.path.isfile(path):
            self._render_error_md(path)
            return

        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()

            title, options, md_text = self._parse_directives(lines)
            final_title = title if title else _("Markdown Dash")

            self._update_frame_title(final_title)

            footer_visible = options.get("controls", True)
            show_edit = options.get("edit", True) if footer_visible else False
            show_status = options.get("status", True) if footer_visible else False
            show_browse = options.get("browse", True) if footer_visible else False
            show_folder = options.get("folder", True) if footer_visible else False

            icon_style_opt = options.get("icon_style", "auto")
            if icon_style_opt not in ("auto", "color", "symbolic"):
                icon_style_opt = "auto"

            table_style_opt = options.get("table_style", "widget")
            if table_style_opt not in ("widget", "text"):
                table_style_opt = "widget"

            if not footer_visible or (
                not show_edit
                and not show_status
                and not show_browse
                and not show_folder
            ):
                self._footer_box.hide()
            else:
                self._footer_box.show()
                # _MarkdownViewer's own "minimal toolbar" (see its
                # _build_widget) has only info_label — no edit/browse/
                # folder buttons of its own — unlike when this shared
                # method runs as the full MarkdownDash gramplet, which
                # always has all four (see its own footer construction).
                # Guarded with getattr rather than assumed present, so a
                # _MarkdownViewer just skips showing/hiding a button it
                # doesn't have, instead of raising AttributeError.
                edit_btn = getattr(self, "_edit_btn", None)
                if edit_btn is not None:
                    edit_btn.show() if show_edit else edit_btn.hide()
                self.info_label.show() if show_status else self.info_label.hide()
                browse_btn = getattr(self, "_browse_btn", None)
                if browse_btn is not None:
                    browse_btn.show() if show_browse else browse_btn.hide()
                folder_btn = getattr(self, "_folder_btn", None)
                if folder_btn is not None:
                    folder_btn.show() if show_folder else folder_btn.hide()

            # is_undocked/undock/get_toplevel are Gramplet-lifecycle
            # methods _MarkdownViewer doesn't have (it's not a Gramplet
            # subclass — see its class docstring); guarded the same way,
            # so an "undocked: true" directive is simply a no-op there
            # rather than an AttributeError, instead of assuming this
            # method only ever runs as the full MarkdownDash gramplet.
            if options.get("undocked") is True and hasattr(self, "undock"):
                if not self.is_undocked():
                    self.undock()
                top_window = self.get_toplevel()
                if top_window and isinstance(top_window, Gtk.Window):
                    top_window.connect("delete-event", self._handle_transient_close)

            self.current_file = path
            self._asset_base = canonical_base
            self._render(md_text, default_icon_style=icon_style_opt, table_style=table_style_opt)
            self._set_loaded(path)

            if track_history:
                # Truncate forward stack when branching to a new path
                if self._history_index < len(self._history) - 1:
                    self._history = self._history[: self._history_index + 1]
                self._history.append(path)
                self._history_index = len(self._history) - 1

            self._update_nav_buttons()

        except Exception as exc:
            traceback.print_exc()
            self._set_status(_(f"Error: {exc}"), error=True)

    # ── navigation history ─────────────────────────────────────────────

    def _on_key_press(self, widget: Gtk.TextView, event: Gdk.EventKey) -> bool:
        """Handle keyboard navigation shortcuts on the text view.

        Implements the standard Gramps / browser keybindings:

        - **Alt+Left**  → Back (navigate to previous file in history)
        - **Alt+Right** → Forward (navigate to next file in history)

        Also intercepts plain (no modifier) **Page Down**/**Page Up** to
        scroll by a direct, synchronous jump on the view's own vertical
        ``Gtk.Adjustment`` -- returning ``True`` so GTK's own default
        handling for these keys never runs at all. This is a confirmed
        fix, not a guess: a native (gdb) backtrace from a
        ``G_DEBUG=fatal-warnings`` reproduction of this addon's own
        long-standing "``gtk_widget_size_allocate(): ... negative
        height``" warning names the exact call chain --
        ``gdk_frame_clock_paint_idle`` → ``gtk_adjustment_on_frame_clock_update``
        → ``gtk_text_view_value_changed`` →
        ``gtk_widget_size_allocate_with_baseline``, the last of which is
        what actually computes and rejects the bad height. That chain
        is GTK's own frame-clock-driven *animated* scroll transition
        for Page Down/Up specifically -- a different mechanism from
        the touch/trackpad momentum scrolling ``Gtk.ScrolledWindow``'s
        own ``kinetic-scrolling`` property controls (already disabled
        on this view's ``Gtk.ScrolledWindow`` -- see ``_build_widget()``
        -- which is exactly why that earlier, reasonable-looking fix
        never actually stopped this warning: it was the wrong
        property for what turned out to be a different animation
        entirely). Also consistent with an observation made much
        earlier in this addon's history that plain mouse-wheel
        scrolling never triggered the warning while Page Down
        consistently did -- wheel scrolling never goes through this
        animated-transition code path; Page Down specifically does.
        Jumping the adjustment's value directly here bypasses that
        code path altogether rather than trying to fix what happens
        inside it.

        UPDATE, confirmed by a second live reproduction: the direct
        jump above eliminates the warning during ordinary paging, but
        ``gtk_text_view_value_changed()``'s defect turned out not to
        be specific to animated transitions after all -- calling
        ``vadj.set_value()`` with the *exact* value of one of the
        adjustment's own extremes (its lower bound, or
        ``upper - page_size``) triggers the identical
        ``gtk_widget_size_allocate_with_baseline()`` negative-height
        warning synchronously, confirmed by a native backtrace whose
        own ``gtk_adjustment_set_value`` frame traced directly back to
        this function's ``set_value()`` call, at the moment of hitting
        the top of the document while paging up.

        UPDATE #2, confirmed by a THIRD live reproduction: clamping to
        one pixel short of each boundary (rather than landing on it
        exactly) did *not* stop the crash -- the identical warning
        fired again at the identical call site, on the very next Page
        Up, with the value never actually at the true extreme. That
        falsifies "landing on the exact boundary value" as the
        trigger. What's consistent with all three reproductions
        together: this function's fix moves the adjustment by a full
        page in one synchronous ``set_value()`` call, where GTK's own
        (apparently more tolerant of this same underlying defect)
        frame-clock animation moved it in many small per-frame
        increments instead. So the current approach performs the same
        total scroll in several smaller synchronous steps rather than
        one large one -- still entirely bypassing GTK's own frame-clock
        animation, so the original animated-transition bug stays
        fixed, while no longer handing
        ``gtk_text_view_value_changed()`` one large jump to recompute
        against at once. Not yet confirmed to be the real variable
        either -- if this still fails, jump size joins boundary
        position on the list of plausible-but-wrong explanations, and
        the next thing to question would be whether a synchronous
        Python-side workaround can address this at all, versus needing
        a fix in GTK itself.

        Deliberately scoped to *no* modifier held (Shift/Ctrl+Page
        Down are left to GTK's own default handling untouched): this
        view is read-only (``set_editable(False)``), but a modified
        Page Down/Up may still be meaningful for extending a text
        selection to copy, which isn't reproducible as an animation
        related to this specific bug and isn't worth narrowing further
        without evidence it's also affected.

        :param widget: The ``Gtk.TextView`` whose own vertical
            ``Gtk.Adjustment`` is scrolled directly for a plain Page
            Down/Up.
        :param event:   The key-press event.
        :returns: ``True`` if the event was consumed, ``False`` to propagate.
        """
        state = event.state & Gtk.accelerator_get_default_mod_mask()
        kv = event.keyval
        if state == 0 and kv in (Gdk.KEY_Page_Down, Gdk.KEY_Page_Up):
            vadj = widget.get_vadjustment()
            if vadj is not None:
                page_size = vadj.get_page_size()
                delta = page_size if kv == Gdk.KEY_Page_Down else -page_size
                # UPDATE, confirmed by a THIRD live reproduction: the
                # 1px-short clamp above did not stop the crash either
                # -- the identical warning still fired at the exact
                # same call site, on the very next Page Up after the
                # first one succeeded. That falsifies "landing on the
                # exact boundary value" as the trigger; the value
                # itself was never 0 or upper-page_size in that run,
                # only 1 pixel away from it, and the defect fired
                # anyway. What's left, consistent with every
                # observation so far: our own fix's single `set_value()`
                # call moves the adjustment by a full page (hundreds of
                # pixels) in one synchronous step, where GTK's own
                # (buggy, but apparently tolerant of its own bug at
                # small step sizes) frame-clock animation moved it in
                # many small per-frame increments instead. The
                # difference this tests is jump *size*, not landing
                # position: the same total distance, moved in several
                # smaller synchronous steps instead of one large one,
                # still entirely bypassing GTK's own frame-clock
                # animation (so the original, already-fixed bug stays
                # fixed) while no longer feeding
                # gtk_text_view_value_changed() a single large change
                # to recompute against at once.
                lower_bound = vadj.get_lower()
                upper_bound = max(lower_bound, vadj.get_upper() - page_size)
                target = min(max(vadj.get_value() + delta, lower_bound), upper_bound)
                steps = 8
                start = vadj.get_value()
                for i in range(1, steps + 1):
                    vadj.set_value(start + (target - start) * i / steps)
                return True
        is_alt = bool(state & Gdk.ModifierType.MOD1_MASK)
        if not is_alt:
            return False
        if kv == Gdk.KEY_Left:
            self.cb_back(None)
            return True
        if kv == Gdk.KEY_Right:
            self.cb_fwd(None)
            return True
        return False

    def _render_error_md(self, attempted_path: str) -> None:
        """Render a file-not-found notice as inline Markdown in the viewer.

        This avoids a modal ``ErrorDialog`` for a routine UX condition (the
        user navigated to a path that no longer exists).  The status bar is
        also updated to reflect the error state.

        :param attempted_path: The path that could not be opened.
        """
        name = os.path.basename(attempted_path)
        _not_found = _("File Not Found")
        _req_path = _("Requested path:")
        _hint = _(
            "The file may have been moved, renamed, or deleted. "
            "Use the \u2018Open\u2019 button to browse for it."
        )
        md = (
            f"# \u274c {_not_found}\n\n"
            f"**{_req_path}** `{attempted_path}`\n\n"
            f"> {_hint}\n"
        )
        self._render(md)
        self._set_status(_(f"File not found: '{name}'"), error=True)

    def _update_nav_buttons(self) -> None:
        """No-op — navigation is keyboard-driven; no buttons to update."""

    def cb_back(self, _widget: Gtk.Widget | None) -> None:
        """Navigate to the previous file in history (Alt+Left).

        :param _widget: The event source (``None`` when called from keyboard).
        """
        if self._history_index > 0:
            self._history_index -= 1
            self._load(self._history[self._history_index], track_history=False)

    def cb_fwd(self, _widget: Gtk.Widget | None) -> None:
        """Navigate to the next file in history (Alt+Right).

        :param _widget: The event source (``None`` when called from keyboard).
        """
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self._load(self._history[self._history_index], track_history=False)

    def _home_path(self) -> str:
        """Return the canonical home document path for this viewer instance.

        Priority: ``_initial_path`` set by an external caller, then the
        plugin-local ``README.md`` (or the first ``README_*.md`` found).

        :returns: Absolute path to the home document (may not exist on disk).
        """
        initial = getattr(self, "_initial_path", None)
        if initial:
            return os.path.expanduser(initial)
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        readme = os.path.join(plugin_dir, "README.md")
        if os.path.isfile(readme):
            return readme
        # Fall back to any README_<lang>.md present
        try:
            for entry in sorted(os.listdir(plugin_dir)):
                m = LANG_SUFFIX_RE.match(entry)
                if m and m.group("stem").upper() == "README":
                    return os.path.join(plugin_dir, entry)
        except OSError:
            pass
        return readme  # return canonical path even if absent; _load() handles it

    # ── rendering ──────────────────────────────────────────────────────

    def _render(
        self, md_text: str, default_icon_style: str = "auto", table_style: str = "widget"
    ) -> None:
        """Parse text markup and fill display layouts segment by segment.

        :param md_text:            Markdown document text (directive lines
            already stripped by :meth:`_parse_directives`).
        :param default_icon_style: ``'auto'`` (default), ``'color'``, or
            ``'symbolic'`` -- the document-wide default for any
            ``gramps:icon:NAME[:SIZE]`` reference that doesn't specify its
            own ``:STYLE`` suffix, typically sourced from the file's
            ``icon_style=...`` control-comment option (see
            :meth:`_parse_directives`).
        :param table_style: ``'widget'`` (default) renders each GFM table
            as a real ``Gtk.Grid`` via :func:`build_table_widget`;
            ``'text'`` renders it as plain monospace markup text via
            :func:`build_table_text` instead -- no embedded widget, no
            per-cell icons, but immune to the child-anchor scroll
            instability :func:`build_table_widget`'s own docstring
            documents. Sourced from the file's ``table_style=...``
            control-comment option.
        """
        buf = Gtk.TextBuffer()
        self.textview.set_buffer(buf)

        self._tags = define_tags(buf)
        self._link_uris = {}
        self._anchor_marks = {}
        link_counter = [0]

        def make_link_tag(style_tag_name: str, uri: str) -> Gtk.TextTag:
            link_counter[0] += 1
            name = f"_link_{link_counter[0]}"
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
                    name, foreground="#006633", underline=Pango.Underline.SINGLE
                )
            else:
                t = buf.create_tag(
                    name, foreground="#0055cc", underline=Pango.Underline.SINGLE
                )
            self._link_uris[name] = (uri, style_tag_name)
            return t

        segments = parse_markdown(md_text, default_icon_style=default_icon_style)
        it = buf.get_end_iter()

        # Extract the widget context once prior to processing layout allocations
        current_style_ctx = self.textview.get_style_context()

        for seg in segments:
            if seg.table_data:
                columns, align, body_rows, sep_widths = seg.table_data
                if table_style == "text":
                    table_chunks = build_table_text(
                        columns,
                        align,
                        body_rows,
                        sep_widths,
                        default_icon_style=default_icon_style,
                    )
                    start_mark = buf.create_mark(None, it, True)
                    for kind, payload in table_chunks:
                        if kind == "icon":
                            buf.insert_pixbuf(it, payload)
                        else:
                            buf.insert_markup(it, payload, -1)
                    start_it = buf.get_iter_at_mark(start_mark)
                    apply_table_no_wrap_tag(buf, start_it, it)
                    buf.delete_mark(start_mark)
                else:
                    tbl_widget = build_table_widget(
                        columns,
                        align,
                        body_rows,
                        sep_widths,
                        default_icon_style=default_icon_style,
                    )
                    anchor = buf.create_child_anchor(it)
                    self.textview.add_child_at_anchor(tbl_widget, anchor)
                    tbl_widget.show_all()

                if table_has_uninteractive_links(columns, body_rows):
                    emit_enhanced_renderer_notice(buf, it, self._tags, make_link_tag)

            elif seg.gramps_icon:
                icon_name, size, icon_style = seg.gramps_icon

                # THEME ALIGNMENT: Inject live layout context to
                # stabilize color variations across GTK themes.
                pb = resolve_icon_pixbuf(
                    icon_name,
                    size,
                    style_context=current_style_ctx,
                    icon_style=icon_style,
                )

                if pb:
                    buf.insert_pixbuf(it, pb)
                else:
                    start_mark = buf.create_mark(None, it, True)
                    buf.insert(it, f"[{icon_name}]")
                    start_it = buf.get_iter_at_mark(start_mark)
                    t = self._tags.get("blockquote")
                    if t:
                        buf.apply_tag(t, start_it, it)
                    buf.delete_mark(start_mark)

            elif seg.image_path:
                img_path = self._resolve_path(seg.image_path)
                inserted = False
                if os.path.isfile(img_path):
                    inserted = self._insert_image(buf, it, img_path, seg.text)
                if not inserted:
                    display = f"[image: {seg.text or seg.image_path}]"
                    link_tag = make_link_tag("image_link", seg.image_path)
                    start_mark = buf.create_mark(None, it, True)
                    buf.insert(it, display)
                    start_it = buf.get_iter_at_mark(start_mark)
                    buf.apply_tag(link_tag, start_it, it)
                    buf.delete_mark(start_mark)

            elif seg.url:
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

                if seg.anchor:
                    mark = buf.create_mark(f"anchor:{seg.anchor}", start_it, True)
                    self._anchor_marks[seg.anchor] = mark
            else:
                start_mark = buf.create_mark(None, it, True)
                buf.insert(it, seg.text)
                start_it = buf.get_iter_at_mark(start_mark)

                if seg.anchor:
                    mark = buf.create_mark(f"anchor:{seg.anchor}", start_it, True)
                    self._anchor_marks[seg.anchor] = mark

                for attr in seg.attrs:
                    t = self._tags.get(attr)
                    if t:
                        buf.apply_tag(t, start_it, it)
                buf.delete_mark(start_mark)

            it = buf.get_end_iter()

    # Static, view-width-blind cap that _insert_image used to scale
    # against unconditionally. Still used as the ceiling / pre-allocation
    # fallback in _max_image_width() below -- see that method's docstring
    # for why a live viewport width is now consulted whenever one is
    # available, and the module docstring's "Next target for fixes" note
    # this addresses.
    _FALLBACK_MAX_IMAGE_WIDTH = 560

    def _max_image_width(self) -> int:
        """
        Return the widest an inline image should be scaled to right now.

        The table-widget fix elsewhere in this file (see
        ``build_table_widget``'s own trailing comments in
        ``MarkdownUtils.py``) root-caused one source of the
        "``gtk_widget_size_allocate(): ... negative height``" /
        ``pixman_region32_init_rect: Invalid rectangle passed`` warnings
        this module's own docstring lists under "Next target for fixes"
        to a ``Gtk.TextView`` child anchor reporting no fixed natural
        size, and fixed it by giving that anchor's widget an explicit
        size request. A plain image pixbuf anchor (this method's
        caller) always carries its own explicit, fixed width/height --
        so it isn't exposed to that *exact* mechanism -- but it was
        still being scaled against a single hardcoded
        :data:`_FALLBACK_MAX_IMAGE_WIDTH` regardless of how wide the
        ``Gtk.TextView`` displaying it actually is right now. That can
        never make an image *narrower* than its container demands: an
        image rendered while the reader window is docked as a narrow
        gramplet sidebar pane, or scaled once at open time and then
        left fixed-size while the user later shrinks the window, can
        end up wider than the ``Gtk.TextView``'s live allocation --
        exactly the kind of already-realized-anchor-wider-than-its-
        container mismatch the table-widget fix's own comments
        describe encountering during scroll. Capping to the live
        viewport width whenever a real one is available removes that
        specific mismatch as a possible contributor, alongside the
        already-fixed table case.

        :returns: Maximum image width in pixels, always at least 1.
        """
        allocated = self.textview.get_allocated_width()
        left = self.textview.get_left_margin()
        right = self.textview.get_right_margin()
        # A little breathing room beyond the margins alone, so the image
        # doesn't butt directly against them, and so a scrollbar
        # appearing/disappearing doesn't immediately reintroduce a
        # mismatch by itself.
        padding = 16
        if allocated > 1:
            return max(
                1,
                min(self._FALLBACK_MAX_IMAGE_WIDTH, allocated - left - right - padding),
            )
        # No real allocation yet (e.g. rendering before the widget has
        # ever been shown) -- fall back to the previous fixed behaviour
        # rather than guessing at a width that isn't available yet.
        return self._FALLBACK_MAX_IMAGE_WIDTH

    def _insert_image(
        self, buf: Gtk.TextBuffer, it: Gtk.TextIter, img_path: str, alt_text: str
    ) -> bool:
        """Insert a scaled pixbuf into display buffer layout configurations."""
        try:
            max_w = self._max_image_width()
            pb = GdkPixbuf.Pixbuf.new_from_file(img_path)
            w, h = pb.get_width(), pb.get_height()
            if w > max_w:
                # max(1, ...): an extreme-aspect-ratio source image could
                # otherwise round down to a *zero*-height scaled pixbuf,
                # which is a second, independent way to end up with a
                # degenerate (here: exactly-zero rather than negative,
                # but equally invalid) anchor size for the TextView to
                # lay out -- worth guarding even though it isn't the
                # scenario this specific bug report's image triggered.
                h = max(1, int(h * max_w / w))
                w = max_w
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
        """Callback: open current file in default system editor."""
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
            self._open_uri(uri)

    def cb_browse(self, _widget: Gtk.Button) -> None:
        """Callback: open file chooser dialog."""
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
        """Sort dialog items descending by modification time."""
        try:

            def find_treeview(widget: Gtk.Widget) -> Gtk.TreeView | None:
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
        """Change cursor when hovering hyperlinks."""
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
        """Left-click navigation routers."""
        if event.button != 1:
            return False
        style, uri = self._seg_tag_at(int(event.x), int(event.y))
        if not uri:
            return False

        if style == "anchor_link":
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
            if not uri.startswith(("http://", "https://", "ftp://", "file://")):
                resolved = self._resolve_path(uri)
                if os.path.isfile(resolved) and resolved.endswith((".md", ".markdown")):
                    self._load(resolved)
                    return True
            self._open_uri(uri)
        return True

    def _handle_gramps_uri(self, uri: str) -> None:
        """Process custom database actions."""
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

            # "nav"/"edit" links jump to, or open an editor for, a
            # specific database record — which needs an attached Family
            # Tree (self.dbstate.db). That's always present on the full
            # MarkdownDash gramplet, but a standalone _MarkdownViewer
            # (see its class docstring) has no database context of its
            # own at all. Reported plainly here rather than raising
            # AttributeError once self.dbstate.db is reached below.
            dbstate = getattr(self, "dbstate", None)
            if dbstate is None:
                self._set_status(
                    _("Gramps record links aren't available in this viewer"),
                    error=True,
                )
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
                self._set_status(_(f"Unknown object type: {obj_type}"), error=True)
                return

            getter_id, getter_handle, editor_name = info
            db = dbstate.db
            obj = (
                getattr(db, getter_handle)(value)
                if ref == "handle"
                else getattr(db, getter_id)(value)
            )

            if obj is None:
                self._set_status(_(f"Not found: {obj_type} {value}"), error=True)
                return

            if action == "edit":
                self._gramps_open_editor(editor_name, obj)
            else:
                self._gramps_navigate(obj_type, obj.get_handle())
        except Exception:
            traceback.print_exc()

    def _gramps_navigate(self, obj_type: str, handle: str) -> None:
        """Navigate to active database record profiles."""
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
        """Returns categories titles safely."""
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
        """Open a Gramps object editor."""
        try:
            import gramps.gui.editors as editors_mod

            editor_class = getattr(editors_mod, editor_name)
            editor_class(self.dbstate, self.uistate, [], obj)
        except Exception:
            traceback.print_exc()
            self._set_status(_(f"Cannot open editor: {editor_name}"), error=True)

    def _gramps_switch_view(self, category: str) -> None:
        """Change to views categories."""
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
        """Main runner hook."""


# ── Bind shared rendering methods to _MarkdownViewer ─────────────────────────
#
# _MarkdownViewer is a lightweight dialog shell that needs exactly the same
# rendering pipeline as MarkdownDash.  Rather than duplicating ~400 lines of
# code, we bind the relevant unbound methods from MarkdownDash onto
# _MarkdownViewer after both classes are fully defined.  This is equivalent
# to a mixin but avoids multiple-inheritance entanglement with Gramplet.
#
# This list was originally built by hand and, three times now, missed a
# transitively-called helper — each omission meant AttributeError the
# moment a _MarkdownViewer actually exercised that code path (loading a
# file, moving the mouse over it, rendering an image, Back/Forward,
# opening a non-Gramps link, the footer's own Edit/Browse/folder-history
# controls...), rather than at binding time. Verified complete this time
# with a small static-analysis pass — walk every method already in this
# tuple (transitively, following each further self.<name>(...) call it
# makes) and confirm every callee is either also in this tuple, or
# already defined directly on _MarkdownViewer itself (e.g. _set_status,
# _build_widget) — rather than by hand, reading each method and hoping
# nothing was missed again.
#
# _handle_gramps_uri (and the "nav"/"edit" halves of its own callees,
# _gramps_navigate/_gramps_open_editor) still assume a live
# self.dbstate.db — the one piece of Gramplet context a standalone
# _MarkdownViewer genuinely has no equivalent for, since it's not
# attached to any particular Family Tree. That's guarded explicitly
# inside _handle_gramps_uri itself (reports plainly, rather than
# raising AttributeError) rather than left out of this list, so a
# gramps://view:<category> link — which only needs self.uistate,
# already present either way — still works from a README.
_SHARED_METHODS = (
    "_render",
    "_insert_image",
    "_max_image_width",
    "_FALLBACK_MAX_IMAGE_WIDTH",
    "_on_motion",
    "_on_click",
    "_on_key_press",
    "_handle_gramps_link",
    "_handle_anchor_link",
    "_scroll_to_anchor",
    "_get_localized_filepath",
    "_load",
    "_parse_directives",
    "_home_path",
    "_update_frame_title",
    "_seg_tag_at",
    "_resolve_path",
    "_open_uri",
    "cb_back",
    "cb_fwd",
    "_handle_gramps_uri",
    "_gramps_navigate",
    "_view_category_title",
    "_gramps_open_editor",
    "_gramps_switch_view",
    # Footer controls (Edit / status-and-path / folder-history dropdown /
    # Browse) — previously only ever built for the embedded gramplet
    # (MarkdownDash._build_gui's own copy of this same construction
    # code); _build_footer_box is now the single shared implementation
    # both _build_gui and _MarkdownViewer's own _build_widget call, so a
    # standalone reader window gets the identical footer instead of the
    # bare status label it used to be limited to.
    "_build_footer_box",
    "_set_status",
    "_set_loaded",
    "_populate_folder_menu",
    "cb_edit_file",
    "cb_browse",
    "_browse_start_dir",
    "_set_dialog_sort",
)
for _method_name in _SHARED_METHODS:
    if hasattr(_MarkdownViewer, _method_name):
        continue
    # Read from MarkdownDash's own __dict__ rather than via getattr(): a
    # getattr() on the class unwraps a @staticmethod descriptor down to
    # its plain function, and re-attaching *that* to _MarkdownViewer
    # would make it bind self as its first argument like any ordinary
    # method — silently miscalling _set_dialog_sort/_view_category_title
    # with the wrong arguments every time (caught by their own broad
    # try/except and merely logged, not raised, which is exactly why
    # this went unnoticed rather than surfacing as an AttributeError
    # like every other gap this list has had). __dict__ access returns
    # the raw staticmethod/classmethod descriptor unchanged, so it's
    # reattached with its original binding behaviour intact.
    _member = MarkdownDash.__dict__.get(_method_name)
    if _member is not None:
        setattr(_MarkdownViewer, _method_name, _member)
del _method_name, _member, _SHARED_METHODS


# Revision-timestamp: 2026-06-03 14:10:00 CDT
