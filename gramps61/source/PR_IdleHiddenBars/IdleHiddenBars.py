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
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""
Idle Hidden Bars: a monkey patch so that a hidden sidebar or bottombar
does no work.

Gramps keeps only the front tab of a gramplet bar active (the tabs behind
it wait until they are chosen), but hiding the bar with View > Sidebar or
View > Bottombar only hides the widget: its front tab stays active and
keeps updating, e.g. Person Details runs on every active-person change,
and PageView.set_active() re-activates it whenever the view is shown.

Patched, on GrampletBar only:
- set_active() does nothing while the bar is hidden;
- when the bar is hidden, its front tab is made inactive; when it is
  shown again (and its view is active) the tab is made active and, if it
  missed updates, updates at once.

Undocked (detached) gramplets are always active: they stay on screen
whether their bar is shown or hidden. Gramps never sets this when a
gramplet is undocked, so one undocked from a tab behind the front one (or
while its view was inactive) never updated in its own window. Patched,
on DetachedWindow:
- a gramplet placed in its undock window is made active (and updates at
  once if it missed updates);
- when it is docked back, the bar re-checks its tabs: only the front tab
  of a visible bar of the active view is active.
"""

# ------------------------
# Python modules
# ------------------------
import logging

# ------------------------
# Gramps modules
# ------------------------
from gramps.gui.widgets import grampletbar

LOG = logging.getLogger(".IdleHiddenBars")

_PATCH_FLAG = "_idle_hidden_bars_patched"


def activate(gramplet):
    """Make gramplet active; let it catch up on updates it missed."""
    pui = getattr(gramplet, "pui", None)
    if pui is not None and not pui.active:
        pui.active = True
        if pui.dirty:
            pui.update()


def sync_tabs(bar):
    """
    Only the front tab of a visible bar of the active view is active;
    every other tab of bar is inactive. Undocked gramplets are not tabs.
    """
    if bar.empty:
        return
    front = bar.get_nth_page(bar.get_current_page())
    awake = bar.get_visible() and getattr(bar.pageview, "active", False)
    for index in range(bar.get_n_pages()):
        gramplet = bar.get_nth_page(index)
        pui = getattr(gramplet, "pui", None)
        if pui is None:
            continue
        if awake and gramplet is front:
            activate(gramplet)
        else:
            pui.active = False


def cb_bar_visibility(bar, _pspec):
    """A bar was hidden or shown (View > Sidebar / Bottombar)."""
    sync_tabs(bar)


def patch_gramplet_bar():
    """Wrap GrampletBar and DetachedWindow (see the module docstring)."""
    bar_class = grampletbar.GrampletBar
    if getattr(bar_class, _PATCH_FLAG, False):
        return
    original_init = bar_class.__init__
    original_set_active = bar_class.set_active

    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.connect("notify::visible", cb_bar_visibility)

    def set_active(self):
        if self.get_visible():
            original_set_active(self)

    bar_class.__init__ = __init__
    bar_class.set_active = set_active

    window_class = grampletbar.DetachedWindow
    original_page_added = window_class.page_added
    original_close = window_class.close

    def page_added(self, notebook, gramplet, page_num):
        original_page_added(self, notebook, gramplet, page_num)
        activate(gramplet)  # undocked: on screen, so always active

    def close(self, *args):
        bar = self.grampletbar
        original_close(self, *args)
        sync_tabs(bar)  # docked back as a tab

    window_class.page_added = page_added
    window_class.close = close
    setattr(bar_class, _PATCH_FLAG, True)
    LOG.debug("GrampletBar patched: hidden bars idle, undocked gramplets active")


def load_on_reg(_dbstate, _uistate, _plugin):
    """Runs at plugin registration, before any view (and bar) exists."""
    patch_gramplet_bar()
    return []
