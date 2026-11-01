#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
"""
Environment Inspector - Help tab.

Shows the README.md of the addon (a translated README when one exists).
It is rendered with MarkdownUtils when that library is installed and not
deactivated in the Plugin Manager; otherwise the Markdown source is shown
as plain text. The check is made each time the tab is shown, so turning
MarkdownUtils on or off takes effect without restarting Gramps.

MarkdownUtils is registered with load_on_reg=True, so when it is active
Gramps has already imported it and a plain "import MarkdownUtils" works
from any addon folder.
"""

import logging
import os
import re

from gi.repository import Gdk, GLib, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
README = os.path.join(_ADDON_DIR, "README.md")
# A whole-line HTML comment, such as the GUI directive on line 2.
_DIRECTIVE = re.compile(r"^\s*<!--.*?-->\s*$", re.M)


def markdown_status():
    """
    Return (module, state): state is "ok" (module usable), "hidden"
    (deactivated in the Plugin Manager) or "missing" (not installed, or
    not registered so Gramps did not load it). Checked on every call.
    """
    try:
        from gramps.gui.pluginmanager import GuiPluginManager

        hidden = "MarkdownUtils" in GuiPluginManager.get_instance().get_hidden_plugin_ids()
    except Exception:  # cannot tell: do not refuse a working import
        LOG.debug("EnvironmentInspector: hidden-plugin check failed", exc_info=True)
        hidden = False
    if hidden:
        return None, "hidden"
    try:
        import MarkdownUtils
    except ImportError:
        return None, "missing"
    return MarkdownUtils, "ok"


def markdown_utils():
    """The MarkdownUtils module if it is usable, else None."""
    return markdown_status()[0]


_ALERT_CSS = b"""
#envinsp-help-alert {
    background-color: #c01c28;
    color: #ffffff;
    border-radius: 4px;
    padding: 6px 10px;
}
"""


def _localized(path, mdu):
    """A translated copy of path if MarkdownUtils finds one, else path."""
    if mdu is None or not hasattr(mdu, "resolve_localized_path"):
        return path
    try:
        result = mdu.resolve_localized_path(path)
    except Exception:
        LOG.debug("EnvironmentInspector: no localized README", exc_info=True)
        return path
    found = getattr(result, "path", result)
    found = str(found) if found else ""
    return found if os.path.isfile(found) else path


# ------------------------------------------------------------
# HelpTab
# ------------------------------------------------------------
class HelpTab(Gtk.Box):
    """The Help tab: README.md, formatted or as plain text."""

    def __init__(self, uistate=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.set_border_width(4)
        self.uistate = uistate
        self._mode = None  # "markdown" or "text", as last rendered
        self._current = README
        self._link_uris = {}
        self._anchor_marks = {}

        # Red alert, shown only when the help cannot be formatted. Moving
        # between help pages uses the navigation links in the pages.
        self.alert = Gtk.Box(spacing=10)
        self.alert.set_name("envinsp-help-alert")
        provider = Gtk.CssProvider()
        provider.load_from_data(_ALERT_CSS)
        self.alert.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        icon = Gtk.Image.new_from_icon_name("dialog-error", Gtk.IconSize.DIALOG)
        icon.set_valign(Gtk.Align.START)
        self.alert.pack_start(icon, False, False, 0)
        self.note = Gtk.Label(xalign=0.0)
        self.note.set_line_wrap(True)
        self.note.set_use_markup(True)
        self.alert.pack_start(self.note, True, True, 0)
        self.alert.show_all()
        self.alert.set_no_show_all(True)
        self.pack_start(self.alert, False, False, 0)

        self.textview = Gtk.TextView()
        self.textview.set_editable(False)
        self.textview.set_cursor_visible(False)
        self.textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.textview.set_left_margin(8)
        self.textview.set_right_margin(8)
        self.textview.connect("button-press-event", self.cb_click)
        self.textview.connect("motion-notify-event", self.cb_motion)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_vexpand(True)
        scroll.add(self.textview)
        self.pack_start(scroll, True, True, 0)

        self.connect("map", self.cb_map)

    # --- showing a document ------------------------------------------
    def cb_map(self, *obj):
        """Render on first show, and again if MarkdownUtils was toggled."""
        mode = "markdown" if markdown_utils() else "text"
        if mode != self._mode:
            self._show(self._current)

    def _show(self, path):
        mdu, state = markdown_status()
        self._mode = "markdown" if mdu else "text"
        self._current = path
        shown = _localized(path, mdu)
        try:
            with open(shown, encoding="utf-8") as handle:
                text = handle.read().replace("\r\n", "\n")
        except OSError as err:
            self._plain(_("Cannot read %(file)s: %(error)s")
                        % {"file": shown, "error": err.strerror})
            self._set_note("")
            return
        if mdu is None:
            self._plain(text)
            if state == "hidden":
                how = _("The Markdown rendering addon (MarkdownUtils) is installed "
                        "but deactivated. Activate it in Help > Plugin Manager "
                        "(Hide/Unhide).")
            else:
                how = _("The Markdown rendering addon (MarkdownUtils) is not "
                        "installed or not registered. Install it with Edit > Addon "
                        "Manager, from the same collection as Environment Inspector.")
            self._set_note(
                "<b>%s</b>\n%s"
                % (GLib.markup_escape_text(_("Help is shown unformatted.")),
                   GLib.markup_escape_text(how))
            )
            return
        base = os.path.dirname(shown)
        try:
            result = mdu.render_markdown(
                self.textview,
                _DIRECTIVE.sub("", text),
                resolve_path=lambda ref: ref if "://" in ref
                or os.path.isabs(ref) else os.path.join(base, ref),
            )
        except Exception as err:  # a renderer problem must not hide the help
            LOG.warning("EnvironmentInspector: MarkdownUtils failed: %s", err, exc_info=True)
            self._plain(text)
            self._set_note(
                "<b>%s</b>\n%s"
                % (GLib.markup_escape_text(_("Help is shown unformatted.")),
                   GLib.markup_escape_text(_("The Markdown rendering addon "
                                             "(MarkdownUtils) failed; see the "
                                             "terminal for details.")))
            )
            return
        self.textview.set_monospace(False)
        self._link_uris = result.get("link_uris", {}) or {}
        self._anchor_marks = result.get("anchor_marks", {}) or {}
        self._set_note("")
        self.textview.get_buffer().place_cursor(self.textview.get_buffer().get_start_iter())
        self.textview.scroll_to_iter(self.textview.get_buffer().get_start_iter(), 0, False, 0, 0)

    def _plain(self, text):
        buf = Gtk.TextBuffer()
        buf.set_text(text)
        self.textview.set_buffer(buf)
        self.textview.set_monospace(True)  # keeps Markdown tables lined up
        self._link_uris, self._anchor_marks = {}, {}

    # --- links ---------------------------------------------------------
    def _link_at(self, event):
        mdu = markdown_utils() if self._link_uris else None
        if mdu is None:
            return None
        try:
            _style, uri = mdu.markdown_link_at(
                self.textview, self._link_uris, int(event.x), int(event.y)
            )
        except Exception:
            return None
        return uri

    def cb_motion(self, view, event):
        window = view.get_window(Gtk.TextWindowType.TEXT)
        if window is not None:
            name = "pointer" if self._link_at(event) else "text"
            window.set_cursor(Gdk.Cursor.new_from_name(view.get_display(), name))
        return False

    def cb_click(self, _view, event):
        if event.type != Gdk.EventType.BUTTON_PRESS or event.button != 1:
            return False
        uri = self._link_at(event)
        if not uri:
            return False
        self._follow(uri)
        return True

    def _follow(self, uri):
        if uri.startswith("#"):
            mark = self._anchor_marks.get(uri[1:])
            if mark is not None:
                self.textview.scroll_to_mark(mark, 0, True, 0, 0)
            return
        if "://" in uri or uri.startswith("mailto:"):
            from gramps.gui.display import display_url

            display_url(uri)
            return
        path = uri.split("#", 1)[0]
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(self._current), path)
        if path.lower().endswith(".md") and os.path.isfile(path):
            self._show(os.path.normpath(path))
        elif os.path.exists(path):
            from gramps.gui.utils import open_file_with_default_application

            open_file_with_default_application(path, self.uistate)

    def _set_note(self, markup):
        self.note.set_markup(markup)
        self.alert.set_visible(bool(markup))
