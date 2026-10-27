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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Edit Date Calculator: a monkey patch that adds two things to the stock Gramps
Edit Date dialog:

* the month calendars of Gramps 6.1 (PR 2209 by Serge Noiraud), for Gramps
  5.2 and 6.0, which do not have them, and
* a slide-out Date Calculator panel.

Gramps imports this module at startup (GENERAL plugin, load_on_reg=True) and
calls load_on_reg(), which patches the EditDate class in place:

* EditDate.show is wrapped so the calendars and the panel are built just
  before the dialog is first shown.  (EditDate.__init__ runs the dialog's
  modal loop itself, so wrapping __init__ would be too late.)
* revalidate, build_date_from_ui, switch_type and switch_calendar are
  wrapped: the stock code runs as usual, then the calendars follow it.
* EditDate._save_size is wrapped so the saved size leaves out the panel.
* The stock Help button is replaced by the Markdown-aware Help button
  (pasted from help_doc_button.py), which opens the README of this addon.
* After show(), the window manager's modal hint is dropped (GTK still blocks
  the other windows), so on GNOME the dialog is no longer attached to, and
  moved with, the Edit Event dialog behind it.
* The new methods are added to the class.

A Before or To date is shown and edited in the Second date block, with the
Date block dimmed and showing today.

Each part is skipped when EditDate already has it (Gramps 6.1 has the
calendars; a patched core file may have both).  The class itself is patched,
not replaced, so every place in Gramps that already imported EditDate gets
the changes.  To switch the addon off, hide this plugin in the Plugin Manager
and restart Gramps.
"""

from __future__ import annotations

import calendar as pycalendar
import logging
import os
from collections.abc import Callable
from urllib.parse import quote

from gi.repository import Gdk, Gio, GLib, GObject, Gtk

from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import displayer
from gramps.gen.lib.date import Date, Today
from gramps.gen.plug import PluginRegister
from gramps.gen.plug._pluginreg import PluginData
from gramps.gui.dialog import OkDialog
from gramps.gui.utils import text_to_clipboard
from gramps.gui.editors.editdate import EditDate, MOD_TEXT, QUAL_TEXT
from gramps.gui.pluginmanager import GuiPluginManager

from editdate_calc_panel import DateCalculatorPanel

LOG = logging.getLogger(".EditDateCalculator")
try:
    _ = glocale.get_addon_translator(__file__).sgettext
except ValueError:
    _ = glocale.translation.sgettext

# the id= in EditDateCalculator.gpr.py
PLUGIN_ID = "editdatecalculator"

# ======================================================================
# BEGIN HELP BUTTON BLOCK -- paste from here to the END marker.
# (Pasted from help_doc_button.py; this module's own `_` and LOG are used.)
# ======================================================================
_MARKDOWNDASH_ID = "markdowndash"
_HELP_ICON_NAME = "help-browser"


def resolve_help_icon(size: int = 16) -> Gtk.Image:
    """
    Return a Gtk.Image of the full-color help-browser icon.

    :param size: icon size in pixels (square).
    :returns: the image; empty (with a logged warning) if the theme has
        no such icon at that size.
    """
    theme = Gtk.IconTheme.get_default()
    flags = (
        Gtk.IconLookupFlags.FORCE_REGULAR  # color, not the symbolic variant
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE  # exactly `size`, not nearest
    )
    info = theme.lookup_icon(_HELP_ICON_NAME, size, flags)
    image = Gtk.Image()
    if info is not None:
        image.set_from_pixbuf(info.load_icon())
    else:
        # Deliberately no new_from_icon_name() fallback: that is the
        # unreliable variant/size lookup this function exists to avoid.
        LOG.warning(
            "resolve_help_icon: theme has no '%s' icon at size %d",
            _HELP_ICON_NAME,
            size,
        )
    return image


def find_local_readme(pdata: PluginData | None) -> str | None:
    """
    Return the canonical README.md path of the plugin, or None if the
    plugin has no README of any kind.

    "Any kind" is decided by ``MarkdownUtils.resolve_localized_path()``:
    ``README.md``, a source-language ``README_<lang>.md``, or a
    ``locale/<lang>/README.md`` translation. The returned path need not
    exist on disk; Markdown Dash resolves it to the best variant for the
    user's language, falling back to the English baseline. If
    MarkdownUtils cannot be imported, only a literal ``README.md`` counts.

    :param pdata: the plugin's PluginData; None is tolerated.
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # Imported here, not at module level, so a missing MarkdownUtils
        # never stops the host module from loading. Since MarkdownUtils
        # 0.2.1 (load_on_reg=True), Gramps imports it at startup, so this
        # normally succeeds; cb_show_help() also loads Markdown Dash
        # first, which imports it too, as a fallback for older installs.
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener() -> Callable[..., Gtk.Dialog] | None:
    """
    Return Markdown Dash's open_markdown_file(), or None.

    None means Markdown Dash is deactivated, not registered, fails to
    load, or lacks that function -- callers treat all four the same way
    (fall back to help_url). Each case logs a warning naming itself, so
    a Help button that unexpectedly opens the browser can be diagnosed
    from the terminal; they only appear when Help is clicked.
    """
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        LOG.warning("help button: Markdown Dash is deactivated")
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        LOG.warning("help button: no plugin registered as '%s'", _MARKDOWNDASH_ID)
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        LOG.warning(
            "help button: Markdown Dash at %s failed to load (see the "
            "'Plugin error' above, often a missing MarkdownUtils)",
            pdata.fpath,
        )
        return None
    opener = getattr(mod, "open_markdown_file", None)
    if opener is None:
        LOG.warning(
            "help button: Markdown Dash at %s has no open_markdown_file()",
            pdata.fpath,
        )
    return opener


def open_help_url(pdata: PluginData | None, parent: Gtk.Window | None) -> None:
    """
    Open the plugin's registered help_url in the default browser.

    A bare wiki page title is resolved against gramps-project.org; a full
    http(s) URL is used as-is.

    :param pdata: the plugin's PluginData.
    :param parent: transient parent for the "no documentation" notice.
    """
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered help_url."),
            parent=parent,
        )
        return
    full_url = (
        help_url
        if help_url.startswith(("http://", "https://"))
        else "https://gramps-project.org/wiki/index.php?title="
        + quote(help_url, safe=":")
    )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("help button: could not open help_url: %s", full_url)


def release_from_modal_grab(reader) -> None:
    """
    Let the reader window take input while a modal dialog is open.

    HOST CHANGE (not yet in help_doc_button.py).  A Help button inside a
    modal dialog, such as the Date selection dialog, opens the reader while
    that dialog still holds GTK's modal grab, which blocks input to every
    window in the same window group: the reader would show but ignore the
    mouse and keyboard until the dialog closed.  A window group of its own
    puts the reader outside that grab.  (The window keeps a reference to
    its group.)

    :param reader: what open_markdown_file() returned: the reader's
        Gtk.Window, or an object with a ``window`` attribute.
    """
    window = reader if isinstance(reader, Gtk.Window) else getattr(reader, "window", None)
    if isinstance(window, Gtk.Window):
        Gtk.WindowGroup().add_window(window)


def cb_show_help(_button: Gtk.Button, uistate, pdata: PluginData | None) -> None:
    """
    Show the best documentation available: the plugin's own README.md in
    a Markdown Dash window if possible, else its help_url in a browser.

    :param uistate: the Gramps UiState (its main window parents the reader).
    :param pdata: the calling plugin's own PluginData.
    """
    # Load Markdown Dash first. MarkdownUtils is normally already loaded at
    # startup (load_on_reg in MarkdownUtils 0.2.1), but loading Markdown
    # Dash also imports it, so find_local_readme() can recognize
    # translated READMEs even with an older MarkdownUtils installed.
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None:
            reader = open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            # HOST CHANGE (not yet in help_doc_button.py): see
            # release_from_modal_grab().
            release_from_modal_grab(reader)
            return
    open_help_url(pdata, uistate.window)


def add_help_button(
    container: Gtk.Box,
    uistate,
    plugin: PluginData | str | None,
    *,
    size: int = 16,
) -> Gtk.Button:
    """
    Pack a color "Help" button (icon plus visible label) into container.

    :param container: the Gtk.Box to pack into -- a gramplet's button row,
        or a dialog's action area.
    :param uistate: the Gramps UiState.
    :param plugin: the calling plugin's own registered id (the id= in its
        .gpr.py), or its PluginData.
    :param size: icon size in pixels; the default suits a row of ordinary
        text buttons.
    :returns: the created, already-packed button.
    """
    if isinstance(plugin, str):
        plugin_id = plugin
        plugin = PluginRegister.get_instance().get_plugin(plugin_id)
        if plugin is None:
            LOG.warning("add_help_button: no registered plugin '%s'", plugin_id)
    button = Gtk.Button()
    button.set_image(resolve_help_icon(size))
    button.set_always_show_image(True)  # else some themes hide the icon
    button.set_label(_("Help"))
    # Tooltip on the button: a Gtk.Image inside a button never shows its own.
    button.set_tooltip_text(_("Show documentation for this plugin"))
    button.connect("clicked", cb_show_help, uistate, plugin)
    container.pack_start(button, False, False, 0)
    button.show_all()
    return button


# END HELP BUTTON BLOCK

# Slide-out date calculator panel: width, and the tallest the dialog will
# grow (pixels) to make room for it
CALC_PANEL_WIDTH = DateCalculatorPanel.PANEL_WIDTH
CALC_PANEL_MAX_HEIGHT = 420
# what is left of the dialog's right margin once the open panel reaches into it
CALC_RIGHT_MARGIN = 7

# marker on the EditDate class, so a plugin reload never patches twice
_MARKER = "_edit_date_calculator_addon"
# EditDate methods as they were before patching
_ORIGINALS = {}


def _paired_modifier(modifier, default):
    """
    The Type a one-sided date becomes when its other side is filled in:
    From and To become a Span (From-To), Before and After a Range
    (Between).  Any other Type becomes `default`.
    """
    if modifier in (Date.MOD_FROM, Date.MOD_TO):
        return Date.MOD_SPAN
    if modifier in (Date.MOD_BEFORE, Date.MOD_AFTER):
        return Date.MOD_RANGE
    return default


def _set_type(dialog, modifier):
    """
    Select a Date modifier in the Type menu.
    """
    dialog.type_box.set_active([mod for mod, _text in MOD_TEXT].index(modifier))


# -------------------------------------------------------------------------
#
# _CalculatorMethods: copied onto EditDate by install()
#
# -------------------------------------------------------------------------
class _CalculatorMethods:
    """
    Holder for the methods added to EditDate.  Never instantiated: install()
    copies each function onto the EditDate class.  The code is the same as
    in the patched core editdate.py.
    """

    def _add_calculator_panel(self):
        """
        Add a slide-out date calculator on the right side of the dialog.

        The Glade-defined children of the content area are moved into a
        box, and a [original content | handle | revealer] row is placed
        above the action buttons.  The panel scrolls if the dialog is too
        short, and the dialog grows in height only while it is open.
        """
        content = self.window.get_content_area()
        action_area = self.window.get_action_area()
        keep_in_place = (action_area, action_area.get_parent())

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for child in content.get_children():
            if child in keep_in_place:
                continue
            expand, fill, padding, pack_type = content.query_child_packing(child)
            content.remove(child)
            if pack_type == Gtk.PackType.START:
                main_box.pack_start(child, expand, fill, padding)
            else:
                main_box.pack_end(child, expand, fill, padding)

        self.calc_panel = DateCalculatorPanel(
            get_date=self.cb_calc_get_date,
            use_date=self.cb_calc_use_date,
            use_second_date=self.cb_calc_use_second_date,
        )
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_min_content_width(CALC_PANEL_WIDTH)
        scroll.set_min_content_height(1)
        scroll.add(self.calc_panel)

        panel_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        panel_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0
        )
        panel_box.pack_start(scroll, True, True, 0)

        self.calc_revealer = Gtk.Revealer()
        self.calc_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.calc_revealer.set_transition_duration(200)
        self.calc_revealer.add(panel_box)
        self.calc_revealer.set_reveal_child(False)
        self.calc_revealer.connect("notify::child-revealed", self.cb_calc_revealed)
        self.calc_revealer.connect("size-allocate", self.cb_calc_panel_allocated)

        # the slide-out handle: a slim, full-height toggle with an arrow
        self.calc_arrow = Gtk.Image.new_from_icon_name(
            "pan-end-symbolic", Gtk.IconSize.BUTTON
        )
        self.calc_handle = Gtk.ToggleButton()
        self.calc_handle.set_focus_on_click(False)
        self.calc_handle.set_tooltip_text(_("Show or hide the date calculator"))
        self.calc_handle.add(self.calc_arrow)
        # keep the handle slim, with a small gutter before it
        handle_css = Gtk.CssProvider()
        handle_css.load_from_data(b"button.calc-handle { padding: 0 2px; min-width: 0; }")
        handle_style = self.calc_handle.get_style_context()
        handle_style.add_class("calc-handle")
        handle_style.add_provider(handle_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.calc_handle.set_margin_start(3)
        self.calc_handle.connect("toggled", self.cb_toggle_calculator)

        self.calc_main = main_box
        self.calc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.calc_row.pack_start(main_box, True, True, 0)
        self.calc_row.pack_start(self.calc_handle, False, True, 0)
        self.calc_row.pack_start(self.calc_revealer, False, False, 0)
        content.pack_start(self.calc_row, True, True, 0)
        content.reorder_child(self.calc_row, 0)
        self._calc_grown_height = 0
        self._calc_grown_width = 0
        self._calc_bleed = 0

        # show only our own widgets; the Glade children keep their own state
        self.calc_row.show()
        main_box.show()
        self.calc_revealer.show()
        panel_box.show_all()
        self.calc_handle.show_all()

    def _calc_set_bleed(self, bleed):
        """
        Let the row reach `bleed` pixels further into the dialog's right margin.

        That margin belongs to the content area (GTK ignores negative margins
        on the row itself), so it is narrowed there, and the same room is given
        back around the action buttons, which must not move.
        """
        change = bleed - self._calc_bleed
        content = self.window.get_content_area()
        actions = self.window.get_action_area().get_parent()
        content.set_margin_end(content.get_margin_end() - change)
        actions.set_margin_end(actions.get_margin_end() + change)
        self._calc_bleed = bleed

    def _calc_freeze_main(self):
        """
        Pin the dialog's own content at its current size.

        The window is resized in one step, but the panel takes a moment to
        slide.  Without this the content would be stretched to fill the gap
        and then squashed back as the panel grows (and the reverse when the
        panel slides away).  Frozen, only the panel area changes.
        """
        alloc = self.calc_main.get_allocation()
        self.calc_main.set_size_request(alloc.width, alloc.height)
        self.calc_main.set_halign(Gtk.Align.START)
        self.calc_main.set_valign(Gtk.Align.START)
        self.calc_main.set_hexpand(False)
        self.calc_main.set_vexpand(False)
        self.calc_row.set_child_packing(
            self.calc_main, False, False, 0, Gtk.PackType.START
        )

    def _calc_thaw_main(self, keep_width=False):
        """
        Let the dialog's content follow the window size again.

        With keep_width the content's width stays pinned, so that while the
        panel is open a resized window gives its extra width to the panel
        alone.
        """
        width = self.calc_main.get_size_request()[0] if keep_width else -1
        self.calc_main.set_size_request(width, -1)
        self.calc_main.set_valign(Gtk.Align.FILL)
        self.calc_main.set_vexpand_set(False)
        if keep_width:
            return
        # the panel is gone: the row no longer needs to reach into the margin
        self._calc_set_bleed(0)
        self.calc_main.set_halign(Gtk.Align.FILL)
        self.calc_main.set_hexpand_set(False)
        if self.calc_main.get_parent() is self.calc_row:
            self.calc_row.set_child_packing(
                self.calc_main, True, True, 0, Gtk.PackType.START
            )

    def _calc_thaw_when_sized(self, width, height):
        """
        Thaw the content once the window has really shrunk to this size.

        Thawing sooner would let the content stretch for a frame.  A timeout
        thaws it anyway should the window never reach the size.
        """
        state = {}

        def finish(*_args):
            if not state.get("done"):
                state["done"] = True
                if GObject.signal_handler_is_connected(self.window, state["handler"]):
                    self.window.disconnect(state["handler"])
                self._calc_thaw_main()
            return False

        def cb_size_allocate(window, _allocation):
            win_width, win_height = window.get_size()
            if win_width <= width + 1 and win_height <= height + 1:
                GLib.idle_add(finish)

        state["handler"] = self.window.connect("size-allocate", cb_size_allocate)
        GLib.timeout_add(500, finish)

    def cb_toggle_calculator(self, button):
        """
        Slide the calculator panel in or out.  Opening makes room for it by
        growing the window; closing hands the room back in cb_calc_revealed.
        """
        opened = button.get_active()
        self.calc_arrow.set_from_icon_name(
            "pan-start-symbolic" if opened else "pan-end-symbolic",
            Gtk.IconSize.BUTTON,
        )
        grown = bool(self._calc_grown_width or self._calc_grown_height)
        if not opened:
            # (reveal first: the panel's tracked width must stop updating)
            self.calc_revealer.set_reveal_child(False)
            if grown:
                self._calc_freeze_main()
                self.calc_row.set_child_packing(
                    self.calc_revealer, False, False, 0, Gtk.PackType.START
                )
            return

        self.calc_panel.prefill_from_dialog()
        if self.window.is_maximized() or grown:
            # (grown: closed and reopened mid-slide, the window is still wide)
            self.calc_revealer.set_reveal_child(True)
            return
        self._calc_freeze_main()
        # Let the open panel reach into the dialog's right margin, so that the
        # gap left beside it is CALC_RIGHT_MARGIN (plus the panel's own padding).
        content = self.window.get_content_area()
        margin = content.get_margin_end() + content.get_border_width()
        self._calc_set_bleed(max(0, margin - CALC_RIGHT_MARGIN))
        width, height = self.window.get_size()
        self._calc_grown_width = self.calc_panel.get_preferred_width()[1] + 1
        wanted = min(self.calc_panel.get_preferred_height()[1], CALC_PANEL_MAX_HEIGHT)
        available = self.calc_row.get_allocated_height()
        self._calc_grown_height = max(0, wanted - available)
        self.window.resize(
            width + self._calc_grown_width, height + self._calc_grown_height
        )
        self.calc_revealer.set_reveal_child(True)

    def cb_calc_revealed(self, revealer, _pspec):
        """
        Called when a slide has finished.  Fully open: the content keeps its
        width (it stays pinned when we grew the window), so the panel takes
        any later resizing.  Fully closed: give the window back the room the
        panel took, and let the content flex again.

        The shrink must wait for the end of the slide animation: until then
        the panel still asks for its width, and GTK will not shrink the
        window below what its contents ask for.
        """
        if revealer.get_child_revealed():
            pinned = bool(self._calc_grown_width)
            self._calc_thaw_main(keep_width=pinned)
            if pinned:
                # the panel, not the content, now takes any later resizing
                self.calc_row.set_child_packing(
                    self.calc_revealer, True, True, 0, Gtk.PackType.START
                )
            return
        grown = self._calc_grown_width or self._calc_grown_height
        if grown and not self.window.is_maximized():
            width, height = self.window.get_size()
            target = (
                max(width - self._calc_grown_width, 1),
                max(height - self._calc_grown_height, 1),
            )
            self.window.resize(*target)
            self._calc_thaw_when_sized(*target)
        else:
            self._calc_thaw_main()
        self._calc_grown_width = 0
        self._calc_grown_height = 0

    def cb_calc_panel_allocated(self, revealer, allocation):
        """
        Once the panel is fully open, track its real width: the window may
        have been resized, and closing must hand back exactly that much.
        """
        if (
            self._calc_grown_width
            and revealer.get_reveal_child()
            and revealer.get_child_revealed()
        ):
            # (the part reaching into the dialog's margin is not window width)
            self._calc_grown_width = allocation.width - self._calc_bleed

    def _save_size(self):
        """
        Save the dialog size, leaving out the room taken by the calculator
        panel, so the stored size is always that of the closed dialog.
        """
        _ORIGINALS["_save_size"](self)
        if self.width_key is not None and getattr(self, "_calc_grown_width", 0):
            config.set(self.width_key, config.get(self.width_key) - self._calc_grown_width)
            config.set(
                self.height_key, config.get(self.height_key) - self._calc_grown_height
            )
            config.save()

    def cb_calc_get_date(self):
        """
        Return the date as currently built in the dialog (or None).
        """
        return self.validated_date

    def cb_calc_use_date(self, date):
        """
        Result to Start Date: load a date computed by the calculator into
        the dialog's Start date fields.

        A simple date leaves a Range or Span as it is, End date included.
        For a Before or To date the Start date is dimmed: the Type becomes
        a Range (Before) or a Span (To), so both sides are active, and the
        End date stays.
        """
        modifier_index = 0
        for index, (modifier, dummy_text) in enumerate(MOD_TEXT):
            if modifier == date.get_modifier():
                modifier_index = index
        quality_index = 0
        for index, (quality, dummy_text) in enumerate(QUAL_TEXT):
            if quality == date.get_quality():
                quality_index = index
        current = MOD_TEXT[self.type_box.get_active()][0]
        to_pair = not date.is_compound() and current in (Date.MOD_BEFORE, Date.MOD_TO)
        keep_second = not date.is_compound() and (
            current in (Date.MOD_RANGE, Date.MOD_SPAN) or to_pair
        )

        # A dual date forces the Julian calendar, so handle it first.
        self.dual_dated.set_active(bool(date.get_slash()))
        if not date.get_slash():
            # repopulates the month names if the calendar changes
            self.calendar_box.set_active(date.get_calendar())
        if to_pair:
            _set_type(self, _paired_modifier(current, Date.MOD_RANGE))
        elif not keep_second:
            self.type_box.set_active(modifier_index)
        self.quality_box.set_active(quality_index)

        self.start_day.set_value(date.get_day())
        self.start_month_box.set_active(date.get_month())
        self.start_year.set_value(date.get_year())
        if not keep_second:
            self.stop_day.set_value(date.get_stop_day())
            self.stop_month_box.set_active(date.get_stop_month())
            self.stop_year.set_value(date.get_stop_year())
        self.new_year.set_text(date.newyear_to_str())
        self.revalidate()

    def cb_calc_use_second_date(self, date):
        """
        Result to End Date: copy a date computed by the calculator into the
        dialog's End date fields.  If the End date is dimmed (the Type is
        not a Range, Span, Before or To), the Type changes so both sides are
        active: From becomes a Span, After a Range, any other Type a Range.
        """
        calendar = self.calendar_box.get_active()
        second = Date(date)
        if second.get_calendar() != calendar:
            second.convert_calendar(calendar)
        current = MOD_TEXT[self.type_box.get_active()][0]
        if current not in (
            Date.MOD_RANGE,
            Date.MOD_SPAN,
            Date.MOD_BEFORE,
            Date.MOD_TO,
        ):
            _set_type(self, _paired_modifier(current, Date.MOD_RANGE))
        self.stop_day.set_value(second.get_day())
        self.stop_month_box.set_active(second.get_month())
        self.stop_year.set_value(second.get_year())
        self.revalidate()


# -------------------------------------------------------------------------
#
# _MonthCalendarMethods: the Gramps 6.1 month calendars (PR 2209)
#
# -------------------------------------------------------------------------
class _MonthCalendarMethods:
    """
    Holder for the month calendar methods added to EditDate.  Never
    instantiated: install() copies each function onto the EditDate class.
    show_on_calendar and date_change_in_calendar are the same as in Gramps
    6.1; the rest re-creates the 6.1 changes to __init__, revalidate,
    build_date_from_ui, switch_type and switch_calendar as wrappers.
    """

    def show_on_calendar(self, calendar, date):
        if self.calendar_box.get_active() != Date.CAL_GREGORIAN:
            return
        if date.is_empty():
            return
        date = date.to_calendar("gregorian")
        year = date.get_year()
        if year < 0:  # Gtk.Calendar only works for positive years
            date = Today()
            year = date.get_year()
        month = date.get_month()
        if month > 0 and month < 13:
            month -= 1
        else:
            month = 0
        if not self.showcal:
            # not set a date for any calendar other than the Gregorian calendar
            # only true after calendar change
            return
        calendar.select_month(month, date.get_year())
        calendar.select_day(date.get_day())

    def date_change_in_calendar(self, calendar, date):
        if self.calendar_box.get_active() != Date.CAL_GREGORIAN:
            return
        current = calendar.get_date()
        if date == "start" and current == self.ofdate:
            return False
        elif current == self.osdate:
            return False
        newdate = Date(current.year, current.month + 1, current.day)
        newdate = newdate.to_calendar(self.calendar_box.get_active())
        if date == "start":
            if self.ofdate.day != current.day:
                self.start_day.set_value(newdate.get_day())
            if self.ofdate.month != current.month:
                self.start_month_box.set_active(newdate.get_month())
            if self.ofdate.year != current.year:
                self.start_year.set_value(newdate.get_year())
            self.ofdate = current
        else:
            if self.osdate.day != current.day:
                self.stop_day.set_value(newdate.get_day())
            if self.osdate.month != current.month:
                self.stop_month_box.set_active(newdate.get_month())
            if self.osdate.year != current.year:
                self.stop_year.set_value(newdate.get_year())
            self.osdate = current

    def _add_month_calendars(self):
        """
        Add the two month calendars below the date fields (Gramps 6.1,
        EditDate.__init__).  Called from the wrapped show().
        """
        # The following is not described in the glade file.
        # glade is not for Gtk4.
        table48 = self.top.get_object("table48")
        self.first_date = Gtk.Calendar()
        self.first_date.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
            | Gtk.CalendarDisplayOptions.SHOW_HEADING
        )
        self.first_date.connect("day-selected", self.date_change_in_calendar, "start")
        self.second_date = Gtk.Calendar()
        self.second_date.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
            | Gtk.CalendarDisplayOptions.SHOW_HEADING
        )
        self.second_date.connect("day-selected", self.date_change_in_calendar, "stop")
        table48.attach(self.first_date, 0, 6, 3, 6)
        table48.attach(self.second_date, 3, 6, 5, 6)
        self.ofdate = self.first_date.get_date()
        self.osdate = self.second_date.get_date()
        self.showcal = True

        # Disable second date controls if not compound date
        if not self.date.is_compound():
            self.second_date.set_sensitive(0)

        # Disable the rest of controls if a text-only date
        if self.date.get_modifier() == Date.MOD_TEXTONLY:
            self.first_date.set_sensitive(0)
            self.second_date.set_sensitive(0)

        # 6.1 also resets the Type for a new (empty) date
        if self.date.is_empty():
            self.type_box.set_active(0)

        self.first_date.show()
        self.second_date.show()
        # stock __init__ already validated, before the calendars existed:
        # do it again so they show the date
        self.revalidate()

    def _calendars_follow_fields(self):
        """
        Show the date fields on the calendars (Gramps 6.1, the additions to
        build_date_from_ui).
        """
        new_cal = self.calendar_box.get_active()
        if new_cal != Date.CAL_GREGORIAN:
            return
        modifier = MOD_TEXT[self.type_box.get_active()][0]
        if modifier == Date.MOD_TEXTONLY:
            return
        dat1 = Date()
        dat1.set_yr_mon_day(
            self.start_year.get_value_as_int(),
            self.start_month_box.get_active(),
            self.start_day.get_value_as_int(),
        )
        dat1.set_calendar(new_cal)
        self.show_on_calendar(self.first_date, dat1)
        if modifier in (Date.MOD_RANGE, Date.MOD_SPAN):
            dat2 = Date()
            dat2.set_yr_mon_day(
                self.stop_year.get_value_as_int(),
                self.stop_month_box.get_active(),
                self.stop_day.get_value_as_int(),
            )
            dat2.set_calendar(new_cal)
            self.show_on_calendar(self.second_date, dat2)


# -------------------------------------------------------------------------
#
# _CalendarInteractionMethods: heading buttons, click/drag handling and the
# Text comment hook.  Used with the backported calendars and with the
# calendars Gramps 6.1 builds itself.
#
# -------------------------------------------------------------------------
class _CalendarInteractionMethods:
    """
    Holder for methods added to EditDate.  Never instantiated: install()
    copies each function onto the EditDate class.

    Behavior of the month calendars ("sheets"):

    * Clicking a day, or the Month or Year heading button, puts that date
      (day, month and year / month and year / year) in the fields of its
      block, Date or Second date.  A click that turns into a drag does not.
    * The heading arrows and Page Up / Page Down only browse the sheet.
    * A day, Month or Year dragged from one sheet and dropped anywhere on
      the other block (heading label, fields or sheet) acts as a click on
      that item would on the other sheet.  Dropped on a dimmed side, it
      changes the Type so both sides are active: From and To become a
      Span, Before and After a Range, any other Type a Span.
    """

    def _calendar_fields(self, which):
        """
        Return the (day, month, year) widgets of the Date ("start") or the
        Second date ("stop").
        """
        if which == "start":
            return self.start_day, self.start_month_box, self.start_year
        return self.stop_day, self.stop_month_box, self.stop_year

    def _enhance_calendars(self):
        """
        Give each sheet a heading row with Month and Year buttons, make day
        selection happen on release, and make the two blocks drop targets
        for each other.
        """
        self._calendar_press = {}
        self._calendar_syncing = False
        self._calendar_drag = None
        self._calendar_headers = {}
        pairs = (("start", self.first_date), ("stop", self.second_date))
        grid = self.first_date.get_parent()

        # make a free grid row directly above each sheet (rows at the
        # bottom first, so the positions above stay valid)
        tops = {grid.child_get_property(cal, "top-attach") for _w, cal in pairs}
        for top in sorted(tops, reverse=True):
            grid.insert_row(top)

        for which, cal in pairs:
            cal.set_display_options(Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES)
            header, measure = self._make_calendar_header(cal, which)
            left = grid.child_get_property(cal, "left-attach")
            top = grid.child_get_property(cal, "top-attach")
            width = grid.child_get_property(cal, "width")
            grid.attach(header, left, top - 1, width, 1)
            self._calendar_headers[which] = header
            cal.bind_property(
                "sensitive", header, "sensitive", GObject.BindingFlags.SYNC_CREATE
            )
            header.show_all()
            # now in the dialog, the labels have their real font
            measure()
            header.connect("style-updated", lambda _w, m=measure: m())

            cal.connect("button-press-event", self.cb_calendar_press, which)
            cal.connect("button-release-event", self.cb_calendar_release, which)
            cal.connect("key-press-event", self.cb_calendar_key_press)
            cal.connect("drag-begin", self.cb_calendar_drag_begin, which)
            cal.connect("drag-end", self.cb_calendar_drag_end, which)
            # after GTK's own handler, which would send the selected day
            cal.connect_after("drag-data-get", self.cb_calendar_drag_data_get, which)
            # drops are handled by the grid, for the whole block
            cal.drag_dest_unset()

        # Drops anywhere on a block land on the grid: the spin buttons and
        # sheets would otherwise take them (dimmed widgets already pass
        # them on).
        for widget in (self.start_day, self.start_year, self.stop_day, self.stop_year):
            widget.drag_dest_unset()
        grid.drag_dest_set(0, [], Gdk.DragAction.COPY)
        grid.drag_dest_add_text_targets()
        grid.connect("drag-motion", self.cb_block_drag_motion)
        grid.connect("drag-drop", self.cb_block_drag_drop)

    def _make_calendar_header(self, cal, which):
        """
        Build the heading row: < Month >   < Year >

        Returns the row and a function that pads the Month and Year labels
        to their widest text, so the arrows never move.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        target = _("Start date") if which == "start" else _("End date")

        def arrow(icon, months, tooltip):
            button = Gtk.Button()
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_focus_on_click(False)
            button.add(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
            button.set_tooltip_text(tooltip)
            button.connect(
                "clicked", lambda _b: self._browse_calendar(cal, which, months)
            )
            return button

        month_label = Gtk.Label()
        year_label = Gtk.Label()
        month_button = Gtk.Button()
        month_button.add(month_label)
        month_button.set_tooltip_text(
            _("Click to use this month and year as the %s; drag to copy them")
            % target
        )
        year_button = Gtk.Button()
        year_button.add(year_label)
        year_button.set_tooltip_text(
            _("Click to use this year as the %s; drag to copy it") % target
        )
        for button, kind in ((month_button, "month"), (year_button, "year")):
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.set_focus_on_click(False)
            self._make_label_button(button, cal, which, kind)

        box.pack_start(arrow("pan-start-symbolic", -1, _("Previous month")), False, False, 0)
        box.pack_start(month_button, False, False, 0)
        box.pack_start(arrow("pan-end-symbolic", 1, _("Next month")), False, False, 0)
        box.pack_end(arrow("pan-end-symbolic", 12, _("Next year")), False, False, 0)
        box.pack_end(year_button, False, False, 0)
        box.pack_end(arrow("pan-start-symbolic", -12, _("Previous year")), False, False, 0)

        names = [name for name in displayer.long_months if name]

        def cb_month_changed(calendar):
            year, month, _day = calendar.get_date()
            month_label.set_text(names[month] if month < len(names) else "")
            year_label.set_text(str(year))

        def measure():
            def widest(label, texts):
                return max(label.create_pango_layout(t).get_pixel_size()[0] for t in texts)

            month_label.set_size_request(widest(month_label, names), -1)
            year_label.set_size_request(widest(year_label, ["8888"]), -1)

        cal.connect("month-changed", cb_month_changed)
        cb_month_changed(cal)
        return box, measure

    def _make_label_button(self, button, cal, which, kind):
        """
        Month / Year heading button: a click fills the fields, a drag
        carries the month and year (or the year), as text and to the other
        block.
        """
        state = {"dragged": False}

        def cb_clicked(_button):
            if not state["dragged"]:
                self._date_to_fields(which, kind, tuple(cal.get_date()))

        def cb_drag_begin(_widget, _context):
            state["dragged"] = True
            self._calendar_drag = {
                "which": which,
                "kind": kind,
                "date": tuple(cal.get_date()),
            }

        def cb_drag_end(_widget, _context):
            self._calendar_drag = None
            # (after any click GTK might still deliver for this press)
            GLib.idle_add(state.__setitem__, "dragged", False)

        def cb_drag_data_get(_widget, _context, data, _info, _time):
            year, month, _day = cal.get_date()
            date = Date(year, 0 if kind == "year" else month + 1, 0)
            data.set_text(displayer.display(date), -1)

        button.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY
        )
        button.drag_source_add_text_targets()
        button.connect("clicked", cb_clicked)
        button.connect("drag-begin", cb_drag_begin)
        button.connect("drag-end", cb_drag_end)
        button.connect("drag-data-get", cb_drag_data_get)

    def _browse_calendar(self, cal, which, months):
        """
        Heading arrows: show another sheet, without touching the fields.
        The day is marked only on the sheet of the date in the fields.
        """
        year, month, _day = cal.get_date()
        new_year, new_month = divmod(year * 12 + month + months, 12)
        if new_year < 1:
            return
        day_w, month_w, year_w = self._calendar_fields(which)
        self._calendar_syncing = True
        try:
            cal.select_month(new_month, new_year)
            if (
                month_w.get_active() == new_month + 1
                and year_w.get_value_as_int() == new_year
            ):
                cal.select_day(day_w.get_value_as_int())
            else:
                cal.select_day(0)
        finally:
            self._calendar_syncing = False

    def cb_calendar_key_press(self, _cal, event):
        """
        Page Up / Page Down browse the sheet, like the heading arrows.
        """
        if event.keyval in (
            Gdk.KEY_Page_Up,
            Gdk.KEY_Page_Down,
            Gdk.KEY_KP_Page_Up,
            Gdk.KEY_KP_Page_Down,
        ):
            self._calendar_syncing = True
            # (GTK handles the key after this handler returns)
            GLib.idle_add(setattr, self, "_calendar_syncing", False)
        return False

    def _date_to_fields(self, which, kind, cal_date):
        """
        Put a sheet date in the fields of a block: the whole date ("day"),
        the month and year ("month") or the year ("year").  cal_date is a
        Gtk.Calendar (year, 0-based month, day).
        """
        if self.calendar_box.get_active() != Date.CAL_GREGORIAN:
            return
        year, month, day = cal_date
        day_w, month_w, year_w = self._calendar_fields(which)
        day_w.set_value(day if kind == "day" else 0)
        month_w.set_active(0 if kind == "year" else month + 1)
        year_w.set_value(year)

    def cb_calendar_press(self, cal, event, which):
        """
        Remember the selection and focus before GTK selects the pressed
        day; the fields only follow on release (cb_calendar_release).
        """
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            self._calendar_press[which] = {
                "down": True,
                "pending": False,
                "dragged": False,
                "prev": tuple(cal.get_date()),
                "focus": self.window.get_focus(),
            }
        return False

    def cb_calendar_release(self, cal, _event, which):
        """
        A click without a drag: the fields follow the selected day.
        """
        state = self._calendar_press.get(which)
        if state and state["down"]:
            state["down"] = False
            if state["pending"] and not state["dragged"]:
                state["pending"] = False
                self._date_to_fields(which, "day", tuple(cal.get_date()))
        return False

    def cb_calendar_drag_begin(self, cal, _context, which):
        """
        A drag started from a day: put back the selection and the focus
        as they were before the press, but drag the pressed day.
        """
        state = self._calendar_press.get(which)
        if not state:
            return
        state["dragged"] = True
        state["drag_date"] = tuple(cal.get_date())
        self._calendar_drag = {
            "which": which,
            "kind": "day",
            "date": state["drag_date"],
        }
        year, month, day = state["prev"]
        cal.select_month(month, year)
        cal.select_day(day)
        state["pending"] = False
        focus = state["focus"]
        if focus is not None and focus is not cal:
            focus.grab_focus()

    def cb_calendar_drag_end(self, _cal, _context, which):
        """
        The drag is over (the button release went to the drag).
        """
        self._calendar_press.pop(which, None)
        self._calendar_drag = None

    def cb_calendar_drag_data_get(self, _cal, _context, data, _info, _time, which):
        """
        Drag the pressed day, as a Gramps date (GTK would send the selected
        day, which cb_calendar_drag_begin has put back).
        """
        state = self._calendar_press.get(which)
        if state and state.get("drag_date"):
            year, month, day = state["drag_date"]
            data.set_text(displayer.display(Date(year, month + 1, day)), -1)

    def _block_at(self, grid, x, y):
        """
        Return "start" or "stop" if (x, y), in grid coordinates, is inside
        the rectangle enclosing the Date or Second date block (heading
        label, fields, sheet heading and sheet), else None.
        """
        blocks = {
            "start": (
                self.top.get_object("label411"),
                self.start_day,
                self.start_year,
                self._calendar_headers.get("start"),
                self.first_date,
            ),
            "stop": (
                self.top.get_object("label412"),
                self.stop_day,
                self.stop_year,
                self._calendar_headers.get("stop"),
                self.second_date,
            ),
        }
        for which, widgets in blocks.items():
            rects = []
            for widget in widgets:
                if widget is None:
                    continue
                origin = widget.translate_coordinates(grid, 0, 0)
                if origin is None:
                    continue
                left, top = origin
                rects.append(
                    (
                        left,
                        top,
                        left + widget.get_allocated_width(),
                        top + widget.get_allocated_height(),
                    )
                )
            if not rects:
                continue
            x0 = min(r[0] for r in rects)
            y0 = min(r[1] for r in rects)
            x1 = max(r[2] for r in rects)
            y1 = max(r[3] for r in rects)
            if x0 <= x < x1 and y0 <= y < y1:
                return which
        return None

    def _drop_target(self, grid, x, y):
        """
        Return the block a sheet drag may be dropped on at (x, y): only the
        other block than the one the drag came from.
        """
        drag = self._calendar_drag
        if drag is None or self.calendar_box.get_active() != Date.CAL_GREGORIAN:
            return None
        if MOD_TEXT[self.type_box.get_active()][0] == Date.MOD_TEXTONLY:
            return None
        target = self._block_at(grid, x, y)
        if target is None or target == drag["which"]:
            return None
        return target

    def cb_block_drag_motion(self, grid, context, x, y, time):
        """
        Accept a sheet drag over the other block.
        """
        if self._drop_target(grid, x, y):
            Gdk.drag_status(context, Gdk.DragAction.COPY, time)
        else:
            Gdk.drag_status(context, 0, time)
        return True

    def cb_block_drag_drop(self, grid, context, x, y, time):
        """
        A sheet drag dropped on the other block: as if that item had been
        clicked on the other sheet.  The Second date needs a Range or Span
        Type; any other Type becomes Span.
        """
        target = self._drop_target(grid, x, y)
        if target is None:
            Gtk.drag_finish(context, False, False, time)
            return True
        drag = self._calendar_drag
        modifier = MOD_TEXT[self.type_box.get_active()][0]
        new_type = None
        if target == "stop" and modifier not in (
            Date.MOD_RANGE,
            Date.MOD_SPAN,
            Date.MOD_BEFORE,
            Date.MOD_TO,
        ):
            # From -> Span, After -> Range, any other Type -> Span
            new_type = _paired_modifier(modifier, Date.MOD_SPAN)
        elif target == "start" and modifier in (Date.MOD_BEFORE, Date.MOD_TO):
            # Before -> Range, To -> Span
            new_type = _paired_modifier(modifier, Date.MOD_RANGE)
        if new_type is not None:
            _set_type(self, new_type)
        self._date_to_fields(target, drag["kind"], drag["date"])
        Gtk.drag_finish(context, True, False, time)
        return True

    def _add_text_comment_hook(self):
        """
        Editing the Text comment switches the Type to Text only: for any
        other Type the comment is not kept.
        """
        textonly = [mod for mod, _text in MOD_TEXT].index(Date.MOD_TEXTONLY)

        def cb_text_changed(entry):
            if entry.get_text().strip() and self.type_box.get_active() != textonly:
                self.type_box.set_active(textonly)

        self.text_entry.connect("changed", cb_text_changed)


def _replaced_date_change_in_calendar(self, cal, which):
    """
    Replaces date_change_in_calendar ("day-selected" handler).

    * While the calendar is only following the fields (show_on_calendar),
      nothing goes back to the fields: a Year-only date shows January, and
      that must not become the Month.
    * While the mouse button is down, wait: the release decides, and a drag
      changes nothing.
    * Otherwise (keyboard selection, a click on a day of the next or
      previous month) the fields follow.
    """
    if getattr(self, "_calendar_syncing", False):
        return False
    state = getattr(self, "_calendar_press", {}).get(which)
    if state and state["down"]:
        state["pending"] = True
        return False
    self._date_to_fields(which, "day", tuple(cal.get_date()))
    return False


def _wrapped_show_on_calendar(self, cal, date):
    """
    Stock show_on_calendar, marked as the calendar following the fields.
    """
    self._calendar_syncing = True
    try:
        return _ORIGINALS["show_on_calendar"](self, cal, date)
    finally:
        self._calendar_syncing = False


def _wrapped_build_date_from_ui(self):
    """
    Stock build_date_from_ui, then the calendars follow the date fields.
    """
    result = _ORIGINALS["build_date_from_ui"](self)
    if hasattr(self, "first_date"):
        self._calendars_follow_fields()
    return result


def _wrapped_revalidate(self, obj=None):
    """
    Stock revalidate; a valid date enables the first calendar only for the
    Gregorian calendar.
    """
    valid = _ORIGINALS["revalidate"](self, obj)
    if valid and hasattr(self, "first_date"):
        self.first_date.set_sensitive(
            self.calendar_box.get_active() == Date.CAL_GREGORIAN
        )
    return valid


def _wrapped_switch_type(self, obj):
    """
    Stock switch_type, then the calendars follow the Type.
    """
    result = _ORIGINALS["switch_type"](self, obj)
    if hasattr(self, "first_date"):
        modifier = MOD_TEXT[self.type_box.get_active()][0]
        if modifier in (Date.MOD_RANGE, Date.MOD_SPAN):
            stop_date_sensitivity = 1
            start_date_sensitivity = 1
        elif modifier == Date.MOD_TEXTONLY:
            stop_date_sensitivity = 0
            start_date_sensitivity = 0
        else:
            start_date_sensitivity = (
                self.calendar_box.get_active() == Date.CAL_GREGORIAN
            )
            stop_date_sensitivity = 0
        self.second_date.set_sensitive(stop_date_sensitivity)
        self.first_date.set_sensitive(start_date_sensitivity)
    return result


def _wrapped_switch_calendar(self, obj):
    """
    The calendars only work for the Gregorian calendar: set them up for the
    new calendar, then run the stock switch_calendar.
    """
    if hasattr(self, "first_date"):
        gregorian = self.calendar_box.get_active() == Date.CAL_GREGORIAN
        self.first_date.set_sensitive(gregorian)
        self.second_date.set_sensitive(gregorian)
        self.showcal = gregorian
    return _ORIGINALS["switch_calendar"](self, obj)


# -------------------------------------------------------------------------
#
# Before / To dates use the Second date block
#
# -------------------------------------------------------------------------
# A Before or To date is an end point, so the dialog shows it in the Second
# date block, with the Date block dimmed and showing today.  Gramps stores
# these dates in the first date, so build_date_from_ui reads the Second date
# fields for them, and changing the Type moves the date between the blocks.
END_MODIFIERS = (Date.MOD_BEFORE, Date.MOD_TO)
RANGE_MODIFIERS = (Date.MOD_RANGE, Date.MOD_SPAN)


def _current_modifier(dialog):
    """
    Return the Date modifier selected in the Type menu.
    """
    return MOD_TEXT[dialog.type_box.get_active()][0]


def _copy_fields(source, target):
    """
    Copy (day, month, year) values from one set of field widgets to another.
    """
    day, month, year = target
    day.set_value(source[0].get_value_as_int())
    month.set_active(source[1].get_active())
    year.set_value(source[2].get_value_as_int())


def _start_fields(dialog):
    return dialog.start_day, dialog.start_month_box, dialog.start_year


def _stop_fields(dialog):
    return dialog.stop_day, dialog.stop_month_box, dialog.stop_year


def _today_to_start(dialog):
    """
    Fill the (dimmed) Date fields with today, in the dialog's calendar.
    """
    today = Today()
    calendar = dialog.calendar_box.get_active()
    if calendar != Date.CAL_GREGORIAN:
        try:
            today.convert_calendar(calendar)
        except Exception:
            pass
    dialog.start_day.set_value(today.get_day())
    dialog.start_month_box.set_active(today.get_month())
    dialog.start_year.set_value(today.get_year())


def _apply_end_sensitivity(dialog):
    """
    For a Before or To date: the Date block is dimmed, the Second date
    block is active (its sheet only for the Gregorian calendar).
    """
    if _current_modifier(dialog) not in END_MODIFIERS:
        return
    for widget in _start_fields(dialog):
        widget.set_sensitive(False)
    for widget in _stop_fields(dialog):
        widget.set_sensitive(True)
    if hasattr(dialog, "first_date"):
        gregorian = dialog.calendar_box.get_active() == Date.CAL_GREGORIAN
        dialog.first_date.set_sensitive(False)
        dialog.second_date.set_sensitive(gregorian)


def _setup_end_swap(dialog):
    """
    Called from the wrapped show(): move a Before or To date to the Second
    date block when the dialog opens.
    """
    dialog._end_prev_modifier = _current_modifier(dialog)
    if dialog._end_prev_modifier in END_MODIFIERS:
        _copy_fields(_start_fields(dialog), _stop_fields(dialog))
        _today_to_start(dialog)
    dialog._end_swap_ready = True
    _apply_end_sensitivity(dialog)
    dialog.revalidate()


def _swap_build_date_from_ui(self):
    """
    Wrapped build_date_from_ui: a Before or To date comes from the Second
    date fields, and its sheet follows them.
    """
    result = _ORIGINALS["swap_build_date_from_ui"](self)
    if not getattr(self, "_end_swap_ready", False):
        return result
    quality, modifier, calendar, value, text, newyear = result
    if modifier not in END_MODIFIERS:
        return result
    value = (
        self.stop_day.get_value_as_int(),
        self.stop_month_box.get_active(),
        self.stop_year.get_value_as_int(),
        self.dual_dated.get_active(),
    )
    if hasattr(self, "second_date") and calendar == Date.CAL_GREGORIAN:
        shown = Date()
        shown.set_yr_mon_day(value[2], value[1], value[0])
        shown.set_calendar(calendar)
        self.show_on_calendar(self.second_date, shown)
    return (quality, modifier, calendar, value, text, newyear)


def _swap_revalidate(self, obj=None):
    """
    Wrapped revalidate: keep the Before / To sensitivity, which the stock
    code (and Gramps 6.1) would reset.
    """
    valid = _ORIGINALS["swap_revalidate"](self, obj)
    if valid and getattr(self, "_end_swap_ready", False):
        _apply_end_sensitivity(self)
    _update_evaluation(self, valid)
    return valid


def _swap_switch_type(self, obj):
    """
    Wrapped switch_type: move the date between the blocks when the Type
    changes to or from Before / To.

    * Regular, About, After, From (or Text only) to Before / To: the date
      moves to the Second date, the Date shows today.
    * Range / Span to Before / To: the Second date stays, the Date shows
      today.
    * Before / To to Regular, About, After or From: the date moves back to
      the Date block.
    * Before / To to Range / Span: the Second date stays as the end, and
      the Date (today) becomes editable as the start.
    """
    new = _current_modifier(self)
    old = getattr(self, "_end_prev_modifier", new)
    result = _ORIGINALS["swap_switch_type"](self, obj)
    if getattr(self, "_end_swap_ready", False) and new != old:
        if new in END_MODIFIERS and old not in END_MODIFIERS:
            if old not in RANGE_MODIFIERS:
                _copy_fields(_start_fields(self), _stop_fields(self))
            _today_to_start(self)
        elif (
            old in END_MODIFIERS
            and new not in END_MODIFIERS
            and new not in RANGE_MODIFIERS
            and new != Date.MOD_TEXTONLY
        ):
            _copy_fields(_stop_fields(self), _start_fields(self))
        _apply_end_sensitivity(self)
    self._end_prev_modifier = new
    return result


def _swap_switch_calendar(self, obj):
    """
    Wrapped switch_calendar: the stock code puts the converted date back in
    the Date fields; for Before / To move it to the Second date again.
    """
    result = _ORIGINALS["swap_switch_calendar"](self, obj)
    if getattr(self, "_end_swap_ready", False) and (
        _current_modifier(self) in END_MODIFIERS
    ):
        _copy_fields(_start_fields(self), _stop_fields(self))
        _today_to_start(self)
        _apply_end_sensitivity(self)
    return result


def _relabel_sections(dialog):
    """
    Rename the dialog's "Date" and "Second date" sections to "Start date"
    and "End date".  (set_text keeps the labels' bold attribute.)
    """
    for name, text in (("label411", _("Start date")), ("label412", _("End date"))):
        label = dialog.top.get_object(name)
        if label is not None:
            label.set_text(text)


def _relabel_type_menu(dialog):
    """
    Add what Range and Span mean to their Type menu items.
    """
    model = dialog.type_box.get_model()
    for index, (modifier, _text) in enumerate(MOD_TEXT):
        if modifier == Date.MOD_RANGE:
            model[index][0] = _("Range (Between)")
        elif modifier == Date.MOD_SPAN:
            model[index][0] = _("Span (From-To)")


def _evaluated_text(date):
    """
    Return the date as Gramps evaluates it when comparing dates: About,
    Before, After (and Estimated) widened by the ranges set in Preferences,
    a year or month alone stretched over the whole year or month.
    """
    if date is None or date.is_empty():
        return ""
    if date.get_modifier() == Date.MOD_TEXTONLY:
        return _("Text only: not evaluated as a date")
    try:
        start, stop = date.get_start_stop_range()

        def clamp(ymd):
            # (a month alone ends on day 31 there, whatever its length)
            year, month, day = ymd
            if year > 0 and 1 <= month <= 12:
                day = min(day, pycalendar.monthrange(year, month)[1])
            return day, month, year

        first, last = clamp(start), clamp(stop)
        result = Date()
        if first == last:
            result.set_yr_mon_day(first[2], first[1], first[0])
        else:
            result.set(
                modifier=Date.MOD_RANGE,
                value=first + (False,) + last + (False,),
            )
        text = displayer.display(result)
    except Exception:  # (years at the edge of the calendar, and the like)
        return ""
    return text[:1].upper() + text[1:]


def _add_evaluation_line(dialog):
    """
    Add, below the Text comment, a line showing the evaluated date.
    """
    row = dialog.text_entry.get_parent()
    column = row.get_parent()
    label = Gtk.Label(xalign=0)
    label.set_selectable(True)
    label.set_line_wrap(True)
    label.set_margin_start(6)
    label.set_tooltip_text(
        _(
            "How Gramps reads this date when comparing it with other dates, "
            "using the About, Before and After ranges set in Preferences.\n"
            "Double-click to copy the evaluated date."
        )
    )
    # A double-click copies the evaluated date. The handler runs before the
    # label's own (it returns True), so the double-click does not also
    # select a word; a single click or a drag still selects text as before.
    label.connect("button-press-event", _cb_evaluation_pressed, dialog)
    column.pack_start(label, False, False, 0)
    label.show()
    dialog._evaluation_label = label
    dialog._evaluation_value = ""
    dialog._evaluation_flash = 0
    _update_evaluation(dialog, True)


def _cb_evaluation_pressed(label, event, dialog):
    """
    Double-click on the Evaluates to line: copy the evaluated date (the
    value only, without "Evaluates to:") to the clipboard, and say so on
    the line for a moment.
    """
    if event.type != Gdk.EventType._2BUTTON_PRESS or event.button != 1:
        return False
    value = getattr(dialog, "_evaluation_value", "")
    if not value:  # nothing to copy: keep the usual double-click behavior
        return False
    text_to_clipboard(value)
    if dialog._evaluation_flash:
        GLib.source_remove(dialog._evaluation_flash)
    label.set_text(_("Copied to the clipboard: %s") % value)
    dialog._evaluation_flash = GLib.timeout_add(1500, _cb_evaluation_unflash, dialog)
    return True


def _cb_evaluation_unflash(dialog):
    """Put the Evaluates to text back after the "Copied" message."""
    dialog._evaluation_flash = 0
    _update_evaluation(dialog, dialog._evaluation_valid)
    return False


def _update_evaluation(dialog, valid):
    """
    Show the evaluated date (or nothing, while the date is not valid).
    """
    label = getattr(dialog, "_evaluation_label", None)
    if label is None:
        return
    dialog._evaluation_valid = valid
    date = dialog.validated_date if valid else None
    text = _evaluated_text(date) if valid else ""
    # only a real evaluated date can be copied, not the Text only notice
    is_date = bool(text) and date.get_modifier() != Date.MOD_TEXTONLY
    dialog._evaluation_value = text if is_date else ""
    if getattr(dialog, "_evaluation_flash", 0):
        GLib.source_remove(dialog._evaluation_flash)
        dialog._evaluation_flash = 0
    label.set_text(_("Evaluates to: %s") % text if text else "")


def _replace_help_button(dialog):
    """
    Put the Markdown-aware Help button where the stock Help button is
    (lower left), and hide the stock one.

    The stock button is a dialog response button, handled by the run() loop
    of EditDate.__init__ (it opens the wiki); hidden, it is never clicked,
    so that loop is untouched.  The new button opens the README of this
    addon in Markdown Dash, or else its help_url.
    """
    stock = dialog.window.get_widget_for_response(Gtk.ResponseType.HELP)
    area = stock.get_parent() if stock is not None else dialog.window.get_action_area()
    button = add_help_button(area, dialog.uistate, PLUGIN_ID)
    if stock is None:
        return
    area.reorder_child(button, area.child_get_property(stock, "position"))
    if isinstance(area, Gtk.ButtonBox):
        area.set_child_secondary(button, area.get_child_secondary(stock))
    stock.hide()
    # (ManagedWindow.show() calls show_all(), which would show it again)
    stock.set_no_show_all(True)


def _patched_show(self, *args, **kwargs):
    """
    EditDate.show replacement: build the month calendars and the calculator
    panel once, just before the dialog is first shown, then show it as usual.
    Calendars first, so the panel's layout includes them.
    """
    if _ORIGINALS.get("calendars") and not hasattr(self, "first_date"):
        try:
            self._add_month_calendars()
        except Exception:  # never let the addon stop a date from being edited
            LOG.exception("Edit Date Calculator: could not add the calendars")
    if hasattr(self, "first_date") and not hasattr(self, "_calendar_press"):
        try:
            self._enhance_calendars()
        except Exception:
            LOG.exception("Edit Date Calculator: could not change the calendars")
    if not getattr(self, "_sections_relabeled", False):
        self._sections_relabeled = True
        _relabel_sections(self)
        try:
            _relabel_type_menu(self)
            _add_evaluation_line(self)
        except Exception:
            LOG.exception("Edit Date Calculator: could not add the Type labels")
    if not getattr(self, "_help_replaced", False):
        self._help_replaced = True
        try:
            _replace_help_button(self)
        except Exception:
            LOG.exception("Edit Date Calculator: could not replace the Help button")
    if not getattr(self, "_end_swap_ready", False):
        try:
            _setup_end_swap(self)
        except Exception:
            LOG.exception("Edit Date Calculator: could not set up Before / To")
    if not getattr(self, "_text_hook_added", False):
        self._text_hook_added = True
        try:
            self._add_text_comment_hook()
        except Exception:
            LOG.exception("Edit Date Calculator: could not hook the Text comment")
    if _ORIGINALS.get("calculator") and not hasattr(self, "calc_panel"):
        try:
            self._add_calculator_panel()
        except Exception:
            LOG.exception("Edit Date Calculator: could not add the panel")
    result = _ORIGINALS["show"](self, *args, **kwargs)
    try:
        _detach_from_parent(self.window)
    except Exception:
        LOG.exception("Edit Date Calculator: could not detach the dialog")
    return result


def _release_modal_hint(window):
    """
    Drop the window manager's modal hint, keeping GTK's own modality.

    GTK still blocks input to the other Gramps windows (semi-modal), but the
    window manager no longer treats the dialog as modal, so GNOME does not
    attach it to its parent (which locks the two together and dims the
    parent): the dialog can be moved on its own.
    """
    gdk_window = window.get_window()
    if gdk_window is not None:
        gdk_window.set_modal_hint(False)
    return False  # (one-shot idle callback)


def _detach_from_parent(window):
    """
    Release the modal hint once Gtk.Dialog.run() has set it, and again
    whenever the dialog is mapped (GTK sends the hint again on mapping) or
    made modal again (a Gramps ManagedWindow opened from this dialog does
    that when it closes).

    EditDate.__init__ calls show() and then run(); run() makes the dialog
    modal, so the idle callback, which only fires inside run()'s loop,
    comes after it.
    """

    def cb_map_event(widget, _event):
        GLib.idle_add(_release_modal_hint, widget)
        return False

    def cb_modal_changed(widget, _pspec):
        # Gramps ManagedWindow: a child window opened from this dialog (such
        # as the Markdown Dash reader of the Help button) takes the modal
        # flag while it is open, and gives it back with set_modal(True) when
        # it closes, which sends the modal hint again.
        if widget.get_modal():
            GLib.idle_add(_release_modal_hint, widget)

    window.connect("map-event", cb_map_event)
    window.connect("notify::modal", cb_modal_changed)
    GLib.idle_add(_release_modal_hint, window)


def _copy_methods(holder):
    """
    Copy the functions defined on a holder class onto EditDate.
    """
    for name, value in vars(holder).items():
        if callable(value) and not name.startswith("__"):
            setattr(EditDate, name, value)


def install():
    """
    Patch EditDate in place.  Safe to call more than once.

    Returns True once the patch is in place.
    """
    if getattr(EditDate, _MARKER, False):
        return True
    native = vars(EditDate)
    # Gramps 6.1 (or a patched core file) already has the calendars
    calendars = "show_on_calendar" not in native
    # a patched core file, or a future Gramps, may have the calculator
    calculator = "_add_calculator_panel" not in native
    _ORIGINALS["calendars"] = calendars
    _ORIGINALS["calculator"] = calculator
    _ORIGINALS["show"] = EditDate.show
    if calendars:
        for name, wrapper in (
            ("build_date_from_ui", _wrapped_build_date_from_ui),
            ("revalidate", _wrapped_revalidate),
            ("switch_type", _wrapped_switch_type),
            ("switch_calendar", _wrapped_switch_calendar),
        ):
            _ORIGINALS[name] = getattr(EditDate, name)
            setattr(EditDate, name, wrapper)
        _copy_methods(_MonthCalendarMethods)
    # calendar clicks, drags and heading, and the Text comment hook: for the
    # backported calendars and for those Gramps 6.1 builds itself
    _copy_methods(_CalendarInteractionMethods)
    _ORIGINALS["show_on_calendar"] = EditDate.show_on_calendar
    EditDate.show_on_calendar = _wrapped_show_on_calendar
    EditDate.date_change_in_calendar = _replaced_date_change_in_calendar
    # Before / To dates in the Second date block: wraps whatever is there
    # now (the calendar wrappers above, or the Gramps 6.1 methods)
    for name, wrapper in (
        ("build_date_from_ui", _swap_build_date_from_ui),
        ("revalidate", _swap_revalidate),
        ("switch_type", _swap_switch_type),
        ("switch_calendar", _swap_switch_calendar),
    ):
        _ORIGINALS["swap_" + name] = getattr(EditDate, name)
        setattr(EditDate, name, wrapper)
    if calculator:
        _ORIGINALS["_save_size"] = EditDate._save_size
        _copy_methods(_CalculatorMethods)
    EditDate.show = _patched_show
    setattr(EditDate, _MARKER, True)
    LOG.debug(
        "Edit Date Calculator installed (calendars: %s, calculator: %s)",
        calendars,
        calculator,
    )
    return True


def load_on_reg(dbstate, uistate, plugin):
    """
    Called by the Gramps plugin manager at startup.  The command line
    interface passes no uistate and has no dialogs, so nothing is patched
    there.
    """
    if uistate is not None:
        install()
    return []
