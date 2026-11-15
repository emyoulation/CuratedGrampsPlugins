#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Claude AI (wish coding by Brian McCullough)
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
Undocked Gramplets

A monkey patch addon for the window a gramplet gets when it is undocked from
a sidebar or bottombar (the DetachedWindow class).  Any gramplet is affected,
not one in particular.  Gramplets undocked from the Dashboard use a different
window class and are not changed.

* The plain Close button becomes a Dock button showing the icon of the view
  the gramplet came from and whether it returns to the sidebar or the
  bottombar.
* The close button "x" in the title bar really closes the gramplet (it is
  removed from the bar, and can be added again from the bar menu).  Only the
  Dock button returns the gramplet to its bar.
* The standard Help button is replaced by the unlabeled smart Help button of
  MarkdownUtils, but only while the MarkdownUtils plugin is registered, is not
  hidden in the Plugin Manager, and provides add_help_button.  Otherwise the
  standard Help button stays exactly as it is.

The GTK terminal warning "Drawing a gadget with negative dimensions ... (node
arrow owner ...GrampletBar)", which the sidebar and bottombar tabs log
repeatedly, is filtered out.  Only that message is dropped.

The core files are not modified.  The patch wraps one method at startup
(load_on_reg), so a full restart of Gramps is needed after installing it.
"""

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------
import logging
import os

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger("UndockedGramplets")

try:
    # Not importable in command line (no GTK) mode: then there is nothing to patch.
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
    from gramps.gen.config import config as global_config
    from gramps.gen.plug import BasePluginManager
    from gramps.gui.widgets import grampletbar as gbmod
    from gramps.gui.navigator import CATEGORY_ICON

    GUI_AVAILABLE = True
except Exception:  # pylint: disable=broad-except
    GUI_AVAILABLE = False

MARKER = "_undocked_gramplets_original"

# GTK 3 draws the scroll arrows of the GrampletBar tabs before they are sized
# and logs this (harmless) warning over and over.
GADGET_WARNING = "Drawing a gadget with negative dimensions"
GADGET_OWNER = "GrampletBar"
warning_filter_installed = False

# id= of the MarkdownUtils GENERAL plugin (MarkdownUtils.gpr.py).
MARKDOWN_UTILS_ID = "MarkdownUtils"
HELP_ICON_SIZE = 22
# Space around the Help icon, so the button is a square of this size.
HELP_BUTTON_SIZE = HELP_ICON_SIZE + 8
PANE_ICON_SIZE = 16
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")


# -------------------------------------------------------------------------
#
# The Dock button
#
# -------------------------------------------------------------------------
def themed_image(*names):
    """
    Return an image for the first icon name the icon theme knows, or None.
    """
    theme = Gtk.IconTheme.get_default()
    for name in names:
        if name and theme.has_icon(name):
            return Gtk.Image.new_from_icon_name(name, Gtk.IconSize.BUTTON)
    return None


def pane_image(name, fallback):
    """
    Return an image of the SVG file media/<name>.svg of this addon.  If it
    cannot be loaded, use the theme icon called fallback, else None.
    """
    path = os.path.join(MEDIA_DIR, name + ".svg")
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
            path, PANE_ICON_SIZE, PANE_ICON_SIZE
        )
        return Gtk.Image.new_from_pixbuf(pixbuf)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Undocked Gramplets: could not load %s", path)
        return themed_image(fallback)


def view_icon_names(pageview):
    """
    Return the icon names to try for the view, best first.  The toolbar view
    buttons use the stock_icon of the view registration (pdata), else the
    category icon of the navigator.  get_viewtype_stock and get_stock are
    last resorts: many views only return generic icons from them.
    """
    pdata = getattr(pageview, "pdata", None)
    return (
        getattr(pdata, "stock_icon", None),
        CATEGORY_ICON.get(getattr(pageview, "category", None)),
        pageview.get_viewtype_stock(),
        pageview.get_stock(),
    )


def count_category_views(pageview):
    """
    Return how many enabled views the category of the view has.
    """
    pdata = getattr(pageview, "pdata", None)
    category = getattr(pdata, "category", None)
    if category is None:
        return 1
    key = category[0] if isinstance(category, tuple) else category
    hidden = global_config.get("plugin.hiddenplugins")
    count = 0
    for view in BasePluginManager.get_instance().get_reg_views():
        view_category = view.category
        view_key = (
            view_category[0] if isinstance(view_category, tuple) else view_category
        )
        if view_key == key and view.id not in hidden:
            count += 1
    return count


def strip_view_word(view_name):
    """
    Return the view name without a trailing word "View", because the
    tooltip adds "view" itself.  The name the user sees on the toolbar button
    (the registered name, such as "Place Tree") is used, not the title.
    """
    word = glocale.translation.gettext("View")
    if word and view_name.endswith(" " + word):
        return view_name[: -len(word)].rstrip()
    return view_name


def view_location(pageview):
    """
    Return the category name, followed by the view name when the category
    has more than one view: "Places" or "Places category Place Tree view".
    """
    if pageview is None:
        return ""
    category = getattr(pageview, "translated_category", None) or getattr(
        pageview, "category", ""
    )
    try:
        several = count_category_views(pageview) > 1
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not count the category views")
        several = False
    if several:
        pdata = getattr(pageview, "pdata", None)
        view_name = getattr(pdata, "name", None) or pageview.get_title()
        if view_name:
            view_name = strip_view_word(view_name)
            return _("%(category)s category %(view)s view") % {
                "category": category,
                "view": view_name,
            }
    return category


def make_dock_button_content(grampletbar):
    """
    Return [view icon] Dock [sidebar or bottombar icon], and the tooltip text.
    """
    pageview = grampletbar.pageview
    if grampletbar.orientation == Gtk.Orientation.VERTICAL:
        pane_icon = "sidebar-show-right-symbolic"
        pane_fallback = "view-right-pane-symbolic"
        tooltip = _("Dock this gramplet in the %s sidebar")
    else:
        pane_icon = "sidebar-show-bottom-symbolic"
        pane_fallback = "view-bottom-pane-symbolic"
        tooltip = _("Dock this gramplet in the %s bottombar")
    tooltip = tooltip % view_location(pageview)
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    if pageview is not None:
        view_image = themed_image(*view_icon_names(pageview))
        if view_image:
            box.pack_start(view_image, False, False, 0)
    box.pack_start(Gtk.Label(label=_("Dock")), False, False, 0)
    image = pane_image(pane_icon, pane_fallback)
    if image:
        box.pack_start(image, False, False, 0)
    box.show_all()
    return box, tooltip


def change_close_to_dock(detached, grampletbar):
    """
    Rebuild the Close button of the detached window as a Dock button.
    """
    button = detached.window.get_widget_for_response(Gtk.ResponseType.CLOSE)
    if button is None:
        return
    box, tooltip = make_dock_button_content(grampletbar)
    child = button.get_child()
    if child is not None:
        button.remove(child)
    button.add(box)
    button.set_tooltip_text(tooltip)


# -------------------------------------------------------------------------
#
# The smart Help button
#
# -------------------------------------------------------------------------
def get_add_help_button():
    """
    Return MarkdownUtils.add_help_button, or None unless the MarkdownUtils
    plugin is registered, not hidden in the Plugin Manager ("active"), and
    provides the function (older releases do not).
    """
    pmgr = BasePluginManager.get_instance()
    pdata = pmgr.get_plugin(MARKDOWN_UTILS_ID)
    if pdata is None:
        return None
    if MARKDOWN_UTILS_ID in global_config.get("plugin.hiddenplugins"):
        return None
    try:
        module = pmgr.import_plugin(pdata)
    except ImportError:
        return None
    add_help_button = getattr(module, "add_help_button", None)
    return add_help_button if callable(add_help_button) else None


def make_square(button_box, button):
    """
    Make an icon-only button a compact square.  A button box gives all its
    buttons the width of the widest one, and the theme adds side padding.
    """
    if hasattr(button_box, "set_child_non_homogeneous"):
        button_box.set_child_non_homogeneous(button, True)
    provider = Gtk.CssProvider()
    provider.load_from_data(b"button { padding: 0; min-width: 0; min-height: 0; }")
    button.get_style_context().add_provider(
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    button.set_size_request(HELP_BUTTON_SIZE, HELP_BUTTON_SIZE)
    button.set_halign(Gtk.Align.CENTER)
    button.set_valign(Gtk.Align.CENTER)


def replace_help_button(detached, gramplet):
    """
    Swap the standard Help button for the smart one; leave it alone when the
    smart one is not available.
    """
    add_help_button = get_add_help_button()
    if add_help_button is None:
        return
    old = detached.window.get_widget_for_response(Gtk.ResponseType.HELP)
    button_box = old.get_parent() if old is not None else None
    if button_box is None:
        return
    # The gramplet's gname is its plugin id.
    new = add_help_button(
        button_box, gramplet.uistate, gramplet.gname, size=HELP_ICON_SIZE
    )
    if new is None:
        return
    image = new.get_image()
    if image is not None:
        # The icon (and its tooltip) is enough: no text, no outline, so the
        # larger icon fits in the same space.  A text-only button keeps both.
        new.set_property("label", None)
        new.set_relief(Gtk.ReliefStyle.NONE)
        new.set_focus_on_click(False)
        if isinstance(image, Gtk.Image):
            image.set_pixel_size(HELP_ICON_SIZE)
        make_square(button_box, new)
    if hasattr(button_box, "set_child_secondary"):
        # Same lower-left spot the standard Help button has.
        button_box.set_child_secondary(new, True)
    new.show()
    button_box.remove(old)


# -------------------------------------------------------------------------
#
# Patch DetachedWindow
#
# -------------------------------------------------------------------------
def patch_detached_close(window_class):
    """
    Core DetachedWindow.close docks the gramplet, and it is called both by the
    Dock (formerly Close) button and by the "x" of the title bar.  The "x"
    passes the delete-event, so it can be told apart: it docks the gramplet
    and then removes it from the bar, as the bar menu "Remove a gramplet"
    does.  Anything else (the Dock button, or the bar docking its gramplets
    when the view closes) still only docks.
    """
    original_close = window_class.close
    if getattr(original_close, MARKER, None):
        return

    def close(self, *args):
        from_titlebar = any(isinstance(arg, Gdk.Event) for arg in args)
        grampletbar = self.grampletbar
        gramplet = self.gramplet
        result = original_close(self, *args)
        if from_titlebar:
            try:
                page_num = grampletbar.page_num(gramplet)
                if page_num >= 0:
                    grampletbar.remove_page(page_num)
            except Exception:  # pylint: disable=broad-except
                LOG.exception("Undocked Gramplets: could not remove the gramplet")
        return result

    setattr(close, MARKER, original_close)
    window_class.close = close


def patch_detached_window():
    """
    Wrap DetachedWindow.__init__ and close.
    """
    window_class = getattr(gbmod, "DetachedWindow", None)
    if window_class is None or getattr(window_class.__init__, MARKER, None):
        return
    patch_detached_close(window_class)
    original = window_class.__init__

    def init(self, grampletbar, gramplet, x_pos, y_pos):
        original(self, grampletbar, gramplet, x_pos, y_pos)
        # Independent of each other: one failing must not block the other.
        try:
            change_close_to_dock(self, grampletbar)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not change the Close button")
        try:
            replace_help_button(self, gramplet)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not change the Help button")

    setattr(init, MARKER, original)
    window_class.__init__ = init


# -------------------------------------------------------------------------
#
# Quiet the GrampletBar tab arrow warning
#
# -------------------------------------------------------------------------
def cb_gtk_warning(domain, level, message, _user_data):
    """
    Log handler for Gtk warnings: drop only the GrampletBar arrow warning and
    pass everything else on to the default handler.
    """
    if message and GADGET_WARNING in message and GADGET_OWNER in message:
        LOG.debug("Dropped GTK warning: %s", message)
        return
    GLib.log_default_handler(domain, level, message, None)


def install_warning_filter():
    """
    Install the Gtk warning filter once.
    """
    global warning_filter_installed  # pylint: disable=global-statement
    if warning_filter_installed:
        return
    GLib.log_set_handler("Gtk", GLib.LogLevelFlags.LEVEL_WARNING, cb_gtk_warning, None)
    warning_filter_installed = True


# -------------------------------------------------------------------------
#
# Install at startup (load_on_reg)
#
# -------------------------------------------------------------------------
def install():
    """
    Apply the patch.
    """
    if not GUI_AVAILABLE:
        return
    try:
        patch_detached_window()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not patch the detached window")
    try:
        install_warning_filter()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not install the warning filter")


install()
