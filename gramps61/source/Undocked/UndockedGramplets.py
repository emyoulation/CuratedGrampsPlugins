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

A monkey patch addon for the window a gramplet gets when it is undocked.
Any gramplet is affected, not one in particular.  Two window classes are
patched:

* DetachedWindow (grampletbar.py): gramplets undocked from a sidebar or
  bottombar.
* GrampletWindow (grampletpane.py): gramplets undocked from the Dashboard,
  or from another view an addon adds to the Dashboard category.

In both:

* The window title is the gramplet title without the redundant word
  "Gramplet" ("Filter - Gramps", not "Filter Gramplet - Gramps"), also
  after a rename.  The Windows menu entry keeps the word.
* The plain Close button becomes a Dock button showing the icon of the view
  the gramplet came from and, for a sidebar or bottombar, which one it
  returns to.
* The close button "x" in the title bar really closes the gramplet (it is
  removed from the bar or the Dashboard, and can be added again from the
  right-click menu).  Only the Dock button returns the gramplet.
* The standard Help button is replaced by the unlabeled smart Help button of
  MarkdownUtils, but only while the MarkdownUtils plugin is registered, is not
  hidden in the Plugin Manager, and provides add_help_button.  Otherwise the
  standard Help button stays exactly as it is.

Before undocking (GrampletBar tabs and the Dashboard drag button):

* The open hand pointer shows over what can be dragged.
* While dragging, a closed hand follows the pointer, with a green square
  and white check in its lower right corner where a drop works, and a red
  square and white x where it does not.
* Sidebar and bottombar: a tab dropped on its own bar, or within
  DROP_DEAD_ZONE pixels of it, is no longer undocked; the drag is cancelled.
  Dropping on the tabs still reorders them (or moves the gramplet to the
  other bar), and dropping clearly away from the bar undocks.
* Right-clicking a gramplet tab, or the title row of a Dashboard gramplet,
  shows Move (undock it) and Help (the smart Help when MarkdownUtils is
  active).
* Dashboard: the wrench on the "Drag to move; click to detach" button is
  replaced by the open hand of the pointer theme.

Dashboard only:

* The gramplet title row inside the window is hidden while undocked, since
  the window title bar shows the same name.  The title can still be edited
  (relabeled) once the gramplet is docked again.
* The 10 pixel border and frame around the gramplet are removed while
  undocked.  Both return when the gramplet is docked.

The GTK terminal warning "Drawing a gadget with negative dimensions ... (node
arrow owner ...GrampletBar)", which the sidebar and bottombar tabs log
repeatedly, is filtered out.  Only that message is dropped.

The core files are not modified.  The patch wraps methods at startup
(load_on_reg), so a full restart of Gramps is needed after installing it.
"""

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------
import logging
import os
import re
import weakref

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
    import cairo
    import gi

    # Lets Gdk draw a pixbuf on a cairo context (python3-gi-cairo, which
    # Gramps needs anyway).
    gi.require_foreign("cairo")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib
    from gramps.gen.config import config as global_config
    from gramps.gen.plug import BasePluginManager
    from gramps.gui.display import display_help, display_url
    from gramps.gui.utils import is_right_click
    from gramps.gui.widgets import grampletbar as gbmod
    from gramps.gui.widgets import grampletpane as gpmod
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
# A tab dropped in the view area (the main panel, the sidebar and the
# bottombar), or this close to it, is not undocked (the drag is cancelled).
# The toolbar, although next to the sidebar, always undocks.
DROP_DEAD_ZONE = 24
# Slack around the tabs, where a drop reorders the tabs.
TAB_SLACK = 8
# The good or bad badge shown while dragging.  GTK 3 always draws its own
# drag pointer, and an addon can neither hide it nor replace it with a hand
# (a hand drawn as the drag icon shows as a second pointer).  So only the
# badge is drawn, at the lower right corner of the pointer.
BADGE_SIZE = 16
# Target of a dragged GtkNotebook tab (as in gtknotebook.c).
NOTEBOOK_TAB_TARGET = "GTK_NOTEBOOK_TAB"
# The hand on the Dashboard drag button (formerly a 16 pixel wrench).  The
# button padding is trimmed so the title row keeps about the same height.
BUTTON_HAND_SIZE = 24
BUTTON_HAND_CSS = b"button { padding: 1px 5px; min-width: 0; min-height: 0; }"
DRAG_POLL_MS = 50
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


def make_dock_box(pageview, pane_icon=None, pane_fallback=None):
    """
    Return a box with [view icon] Dock [pane icon].  The pane icon (sidebar
    or bottombar) is left out when pane_icon is None, as for the Dashboard,
    where the view icon already shows the destination.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
    if pageview is not None:
        view_image = themed_image(*view_icon_names(pageview))
        if view_image:
            box.pack_start(view_image, False, False, 0)
    box.pack_start(Gtk.Label(label=_("Dock")), False, False, 0)
    if pane_icon:
        image = pane_image(pane_icon, pane_fallback)
        if image:
            box.pack_start(image, False, False, 0)
    box.show_all()
    return box


def set_dock_button(window, box, tooltip):
    """
    Rebuild the Close button of an undocked gramplet window as a Dock button.
    """
    button = window.get_widget_for_response(Gtk.ResponseType.CLOSE)
    if button is None:
        return
    child = button.get_child()
    if child is not None:
        button.remove(child)
    button.add(box)
    button.set_tooltip_text(tooltip)


def change_close_to_dock(detached, grampletbar):
    """
    Sidebar or bottombar window: [view icon] Dock [sidebar or bottombar icon].
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
    box = make_dock_box(pageview, pane_icon, pane_fallback)
    set_dock_button(detached.window, box, tooltip)


def change_dashboard_close_to_dock(gramplet_window):
    """
    Dashboard window: [Dashboard view icon] Dock.  Addons can add more views
    to the Dashboard category, each with its own gramplets, so the icon is
    that of the view the gramplet came from, and the tooltip names the view
    when the category has several: "Dock this gramplet in the Dashboard" or
    "Dock this gramplet in the Dashboard category <View name> view".
    """
    gramplet = gramplet_window.gramplet
    pageview = getattr(gramplet.pane, "pageview", None)
    box = make_dock_box(pageview)
    location = view_location(pageview) or glocale.translation.gettext("Dashboard")
    set_dock_button(
        gramplet_window.window, box, _("Dock this gramplet in the %s") % location
    )


# -------------------------------------------------------------------------
#
# The window title
#
# -------------------------------------------------------------------------
def set_window_title(window, gramplet_title):
    """
    Title the undocked window "<gramplet title> - Gramps", without the word
    "Gramplet" the core adds: the window plainly holds a gramplet.  The
    Windows menu entry keeps "<gramplet title> Gramplet", where the word
    tells the entry apart from editors and other windows.
    """
    window.set_title("%s - Gramps" % gramplet_title)


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
        # Independent of each other: one failing must not block the others.
        try:
            set_window_title(self.window, gramplet.title)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not change the window title")
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
# Patch GrampletWindow (Dashboard)
#
# -------------------------------------------------------------------------
# Remembers the frame border and shadow of a Dashboard gramplet while it is
# undocked, so docking restores exactly what the Dashboard had.
FRAME_STYLE = "_undocked_gramplets_frame_style"


def get_gramplet_frame(gramplet):
    """
    Return the frame (gvframe of grampletpane.glade) around a Dashboard
    gramplet, or None.  Its label widget is the title row: the properties,
    expand/collapse and delete buttons plus the clickable title.
    """
    xml = getattr(gramplet, "xml", None)
    frame = xml.get_object("gvframe") if xml is not None else None
    if isinstance(frame, Gtk.Frame):
        return frame
    for child in gramplet.mainframe.get_children():
        if isinstance(child, Gtk.Frame):
            return child
    return None


def trim_dashboard_gramplet(gramplet):
    """
    Hide the title row (the window title bar shows the same name) and drop
    the border and frame, while the gramplet is undocked.
    """
    frame = get_gramplet_frame(gramplet)
    if frame is None:
        return
    title_row = frame.get_label_widget()
    if title_row is not None:
        title_row.hide()
    if getattr(gramplet, FRAME_STYLE, None) is None:
        setattr(
            gramplet,
            FRAME_STYLE,
            (frame.get_border_width(), frame.get_shadow_type()),
        )
    frame.set_border_width(0)
    frame.set_shadow_type(Gtk.ShadowType.NONE)


def restore_dashboard_gramplet(gramplet):
    """
    Show the title row again and give back the border and frame, so the
    docked gramplet looks as it did (and its title can be relabeled).
    """
    frame = get_gramplet_frame(gramplet)
    if frame is None:
        return
    style = getattr(gramplet, FRAME_STYLE, None)
    if style is not None:
        border, shadow = style
        frame.set_border_width(border)
        frame.set_shadow_type(shadow)
        setattr(gramplet, FRAME_STYLE, None)
    title_row = frame.get_label_widget()
    if title_row is not None:
        title_row.show()
    # An edit of the title left open when the gramplet was undocked is
    # dropped; the title itself shows again.
    if getattr(gramplet, "titlelabel_entry", None) is not None:
        gramplet.titlelabel_entry.hide()
    titlelabel = getattr(gramplet, "titlelabel", None)
    if titlelabel is not None:
        titlelabel.show()


def patch_gramplet_window_close(window_class):
    """
    Core GrampletWindow.close docks the gramplet in its Dashboard column, and
    it is called both by the Dock (formerly Close) button and by the "x" of
    the title bar.  The "x" passes the delete-event: it docks and then
    closes the gramplet as its own delete button in the Dashboard does, so it
    is offered again under "Restore a gramplet" in the Dashboard right-click
    menu.  The Dock button only docks.
    """
    original_close = window_class.close
    if getattr(original_close, MARKER, None):
        return

    def close(self, *args):
        from_titlebar = any(isinstance(arg, Gdk.Event) for arg in args)
        gramplet = self.gramplet
        try:
            restore_dashboard_gramplet(gramplet)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not restore the title row")
        result = original_close(self, *args)
        if from_titlebar:
            try:
                gramplet.close()
            except Exception:  # pylint: disable=broad-except
                LOG.exception("Undocked Gramplets: could not close the gramplet")
        return result

    setattr(close, MARKER, original_close)
    window_class.close = close


def patch_gramplet_set_title():
    """
    Core GridGramplet.set_title retitles an undocked window
    "<title> Gramplet - Gramps" when the gramplet is renamed (for example
    from the Dashboard Configure dialog).  Retitle it without "Gramplet".
    """
    gramplet_class = getattr(gpmod, "GridGramplet", None)
    if gramplet_class is None:
        return
    original_set_title = gramplet_class.set_title
    if getattr(original_set_title, MARKER, None):
        return

    def set_title(self, new_title, set_override=True):
        result = original_set_title(self, new_title, set_override)
        if result and self.detached_window:
            try:
                set_window_title(self.detached_window.window, self.title)
            except Exception:  # pylint: disable=broad-except
                LOG.exception("Undocked Gramplets: could not retitle the window")
        return result

    setattr(set_title, MARKER, original_set_title)
    gramplet_class.set_title = set_title


def patch_gramplet_window():
    """
    Wrap GrampletWindow.__init__ and close, and GridGramplet.set_title.
    """
    window_class = getattr(gpmod, "GrampletWindow", None)
    if window_class is None or getattr(window_class.__init__, MARKER, None):
        return
    patch_gramplet_window_close(window_class)
    patch_gramplet_set_title()
    original = window_class.__init__

    def init(self, gramplet):
        original(self, gramplet)
        # Independent of each other: one failing must not block the others.
        try:
            set_window_title(self.window, gramplet.title)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not change the window title")
        try:
            change_dashboard_close_to_dock(self)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not change the Close button")
        try:
            trim_dashboard_gramplet(gramplet)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not hide the title row")
        try:
            replace_help_button(self, gramplet)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not change the Help button")

    setattr(init, MARKER, original)
    window_class.__init__ = init


# -------------------------------------------------------------------------
#
# Hand images
#
# -------------------------------------------------------------------------
image_cache = {}


def crop_transparent(pixbuf, x_hot, y_hot):
    """
    Cut the fully transparent margin off a pixbuf (cursor images are padded),
    keeping the hotspot at the same place in the picture.
    """
    if not pixbuf.get_has_alpha():
        return pixbuf, x_hot, y_hot
    width, height = pixbuf.get_width(), pixbuf.get_height()
    stride, channels = pixbuf.get_rowstride(), pixbuf.get_n_channels()
    pixels = pixbuf.get_pixels()
    left, top, right, bottom = width, height, -1, -1
    for y_pos in range(height):
        row = y_pos * stride
        for x_pos in range(width):
            if pixels[row + x_pos * channels + 3]:
                left, right = min(left, x_pos), max(right, x_pos)
                top, bottom = min(top, y_pos), max(bottom, y_pos)
    if right < 0:
        return pixbuf, x_hot, y_hot
    cropped = pixbuf.new_subpixbuf(left, top, right - left + 1, bottom - top + 1)
    return cropped.copy(), x_hot - left, y_hot - top


def cursor_image(name, size):
    """
    Return (pixbuf, x_hot, y_hot) of the pointer image the cursor theme uses
    for name ("grab" is the open hand, "grabbing" the closed hand), cropped
    and scaled to fit a square of size, or None if the theme has none.  The
    hand then always matches the pointers the user already knows.
    """
    key = (name, size)
    if key in image_cache:
        return image_cache[key]
    result = None
    try:
        cursor = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), name)
        pixbuf = cursor.get_image() if cursor is not None else None
        if pixbuf is not None:
            x_hot = int(pixbuf.get_option("x_hot") or 0)
            y_hot = int(pixbuf.get_option("y_hot") or 0)
            pixbuf, x_hot, y_hot = crop_transparent(pixbuf, x_hot, y_hot)
            scale = size / max(pixbuf.get_width(), pixbuf.get_height())
            if scale != 1:
                pixbuf = pixbuf.scale_simple(
                    max(1, round(pixbuf.get_width() * scale)),
                    max(1, round(pixbuf.get_height() * scale)),
                    GdkPixbuf.InterpType.BILINEAR,
                )
                x_hot, y_hot = round(x_hot * scale), round(y_hot * scale)
            result = (pixbuf, x_hot, y_hot)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Undocked Gramplets: no %s pointer image", name)
    image_cache[key] = result
    return result


def draw_badge(context, x_pos, y_pos, size, good):
    """
    Draw a green square with a white check mark (good drop point), or a red
    square with a white x (bad drop point).
    """
    if good:
        context.set_source_rgb(0.13, 0.55, 0.13)
    else:
        context.set_source_rgb(0.80, 0.10, 0.10)
    context.rectangle(x_pos, y_pos, size, size)
    context.fill()
    context.set_source_rgb(1, 1, 1)
    context.set_line_width(max(2, size // 6))
    context.set_line_cap(cairo.LINE_CAP_ROUND)
    context.set_line_join(cairo.LINE_JOIN_ROUND)
    inset = size * 0.25
    if good:
        context.move_to(x_pos + inset, y_pos + size * 0.52)
        context.line_to(x_pos + size * 0.43, y_pos + size - inset)
        context.line_to(x_pos + size - inset, y_pos + inset)
    else:
        context.move_to(x_pos + inset, y_pos + inset)
        context.line_to(x_pos + size - inset, y_pos + size - inset)
        context.move_to(x_pos + size - inset, y_pos + inset)
        context.line_to(x_pos + inset, y_pos + size - inset)
    context.stroke()


def badge_image(good):
    """
    Return the badge media/drop-point-good.svg or media/drop-point-bad.svg
    at BADGE_SIZE, or None if it cannot be loaded (then it is drawn).
    """
    name = "drop-point-good.svg" if good else "drop-point-bad.svg"
    path = os.path.join(MEDIA_DIR, name)
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(path, BADGE_SIZE, BADGE_SIZE)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Undocked Gramplets: could not load %s", path)
        return None


def drag_icon(good):
    """
    Return (pixbuf, x_hot, y_hot): the good or bad badge, placed at the lower
    right corner of the pointer (a negative hotspot of the pointer size), so
    it does not cover the pointer or its own small sign.
    """
    key = ("drag", good)
    if key in image_cache:
        return image_cache[key]
    pixbuf = badge_image(good)
    if pixbuf is None:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, BADGE_SIZE, BADGE_SIZE)
        draw_badge(cairo.Context(surface), 0, 0, BADGE_SIZE, good)
        pixbuf = Gdk.pixbuf_get_from_surface(surface, 0, 0, BADGE_SIZE, BADGE_SIZE)
    offset = pointer_size() - 4
    result = (pixbuf, -offset, -offset)
    image_cache[key] = result
    return result


def pointer_size():
    """
    Return the size of the pointer (24 unless the desktop says otherwise).
    """
    try:
        size = Gdk.Display.get_default().get_default_cursor_size()
    except Exception:  # pylint: disable=broad-except
        size = 0
    return size if 12 <= size <= 64 else 24


def grab_cursor():
    """
    Return the open hand pointer, or None.
    """
    try:
        return Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "grab")
    except Exception:  # pylint: disable=broad-except
        return None


# -------------------------------------------------------------------------
#
# Where the pointer is
#
# -------------------------------------------------------------------------
def pointer_position(widget):
    """
    Return the pointer position relative to widget, or None.  The position
    is read from the toplevel window, so it is known also while dragging.
    """
    toplevel = widget.get_toplevel()
    gdk_window = toplevel.get_window() if toplevel is not None else None
    if gdk_window is None:
        return None
    pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
    _window, x_pos, y_pos, _mask = gdk_window.get_device_position(pointer)
    return translate(toplevel, widget, x_pos, y_pos)


def translate(source, dest, x_pos, y_pos):
    """
    Gtk.Widget.translate_coordinates, as (x, y) or None.
    """
    result = source.translate_coordinates(dest, x_pos, y_pos)
    if not result:
        return None
    if len(result) == 3:
        found, x_pos, y_pos = result
        return (x_pos, y_pos) if found else None
    return result


def widget_rect(widget, relative_to):
    """
    Return (left, top, right, bottom) of a mapped widget, relative to
    another widget, or None.
    """
    if widget is None or not widget.get_mapped():
        return None
    origin = translate(widget, relative_to, 0, 0)
    if origin is None:
        return None
    return (
        origin[0],
        origin[1],
        origin[0] + widget.get_allocated_width(),
        origin[1] + widget.get_allocated_height(),
    )


def inside(rect, x_pos, y_pos, slack=0):
    """
    Return True if the point is in the rectangle grown by slack.
    """
    return (
        rect is not None
        and rect[0] - slack <= x_pos < rect[2] + slack
        and rect[1] - slack <= y_pos < rect[3] + slack
    )


# -------------------------------------------------------------------------
#
# DragFeedback
#
# -------------------------------------------------------------------------
class DragFeedback:
    """
    While a drag from widget runs, show the closed hand with a green check
    badge where a drop works and a red x badge where it does not.
    is_good_drop is called without arguments and returns True or False.
    """

    def __init__(self, widget, is_good_drop):
        self.is_good_drop = is_good_drop
        self.context = None
        self.good = None
        self.timer = None
        # After the class handler, which sets its own drag icon.
        widget.connect_after("drag-begin", self.cb_drag_begin)
        widget.connect("drag-end", self.cb_drag_end)

    def cb_drag_begin(self, _widget, context):
        """
        Start following the pointer.
        """
        self.context = context
        self.good = None
        self.update()
        if self.timer is None:
            self.timer = GLib.timeout_add(DRAG_POLL_MS, self.update)

    def cb_drag_end(self, _widget, _context):
        """
        Stop following the pointer.
        """
        self.context = None
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def update(self):
        """
        Change the drag icon when the pointer moves between good and bad
        drop points.
        """
        if self.context is None:
            self.timer = None
            return False
        try:
            good = bool(self.is_good_drop())
            if good != self.good:
                self.good = good
                pixbuf, x_hot, y_hot = drag_icon(good)
                Gtk.drag_set_icon_pixbuf(self.context, pixbuf, x_hot, y_hot)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: drag feedback failed")
            self.context = None
            self.timer = None
            return False
        return True


# -------------------------------------------------------------------------
#
# The context menu: Move and Help
#
# -------------------------------------------------------------------------
def plain_label(text):
    """
    Remove the mnemonic from a core menu string: "_Help" -> "Help", and
    "帮助(_H)" -> "帮助".
    """
    return re.sub(r"\s*\(_.\)", "", text).replace("_", "")


def open_standard_help(gramplet):
    """
    Open the help the standard Help button of an undocked gramplet opens.
    """
    help_url = gramplet.help_url
    if help_url:
        if help_url.startswith(("http://", "https://")):
            display_url(help_url)
        else:
            display_help(help_url)
    else:
        display_help(gpmod.WIKI_HELP_PAGE, gramplet.tname.replace(" ", "_"))


def open_help(gramplet):
    """
    Open the help of the gramplet the way the smart Help button does when
    MarkdownUtils is active, else the way the standard Help button does.
    The smart button is made off screen and clicked, so the menu and the
    button always open the same help.
    """
    add_help_button = get_add_help_button()
    if add_help_button is not None:
        try:
            box = Gtk.Box()
            button = add_help_button(
                box, gramplet.uistate, gramplet.gname, size=HELP_ICON_SIZE
            )
            if button is not None:
                button.clicked()
                return
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: smart Help failed")
    open_standard_help(gramplet)


def popup_gramplet_menu(widget, event, cb_move, gramplet):
    """
    Show the right-click menu of a gramplet tab or title: Move (undock the
    gramplet into its own window) and Help.
    """
    menu = Gtk.Menu()
    move_item = Gtk.MenuItem(label=_("Move"))
    move_item.set_tooltip_text(_("Undock this gramplet into its own window"))
    move_item.connect("activate", lambda _item: cb_move())
    menu.append(move_item)
    help_item = Gtk.MenuItem(label=plain_label(glocale.translation.gettext("_Help")))
    help_item.connect("activate", lambda _item: open_help(gramplet))
    menu.append(help_item)
    menu.attach_to_widget(widget, None)
    menu.show_all()
    menu.popup_at_pointer(event)


# -------------------------------------------------------------------------
#
# Sidebar and bottombar tabs
#
# -------------------------------------------------------------------------
# Every GrampletBar, so a tab can be dragged onto the tabs of another bar.
all_bars = weakref.WeakSet()
original_create_window = None


def tab_rects(bar):
    """
    Yield (page, rect of its tab label, rect of its close button) for the
    gramplet tabs of the bar, relative to the bar.
    """
    for page_num in range(bar.get_n_pages()):
        page = bar.get_nth_page(page_num)
        label = bar.get_tab_label(page)
        rect = widget_rect(label, bar)
        if rect is None:
            continue
        close = getattr(label, "closebtn", None)
        yield page, rect, widget_rect(close, bar)


def tab_at(bar, x_pos, y_pos):
    """
    Return the gramplet whose tab label (not its close button) is at the
    point, or None.
    """
    for page, rect, close_rect in tab_rects(bar):
        if inside(rect, x_pos, y_pos) and not inside(close_rect, x_pos, y_pos):
            return page if isinstance(page, gbmod.TabGramplet) else None
    return None


def over_tabs(bar):
    """
    Return True if the pointer is over the tabs of the bar, where a drop
    reorders the tabs (or moves the gramplet to that bar).
    """
    position = pointer_position(bar)
    if position is None:
        return False
    rects = [rect for _page, rect, _close in tab_rects(bar)]
    if not rects:
        return False
    strip = (
        min(rect[0] for rect in rects),
        min(rect[1] for rect in rects),
        max(rect[2] for rect in rects),
        max(rect[3] for rect in rects),
    )
    return inside(strip, position[0], position[1], TAB_SLACK)


def view_area(bar):
    """
    Return the widget holding the views (the notebook of the main window,
    whose pages hold the main panel, the sidebar and the bottombar), or the
    bar itself if it cannot be found.
    """
    parent = bar.get_parent()
    area = parent.get_ancestor(Gtk.Notebook) if parent is not None else None
    return area or bar


def main_toolbars(bar):
    """
    Return the toolbars of the main window outside the view area (the main
    toolbar), so toolbars of views and gramplets do not count.
    """
    toplevel = bar.get_toplevel()
    area = view_area(bar)
    found = []

    def walk(widget):
        if widget is area:
            return
        if isinstance(widget, Gtk.Toolbar):
            found.append(widget)
        elif isinstance(widget, Gtk.Container):
            widget.forall(walk)

    if isinstance(toplevel, Gtk.Container):
        walk(toplevel)
    return found


def over_toolbar(bar):
    """
    Return True if the pointer is over the main toolbar.
    """
    position = pointer_position(bar)
    if position is None:
        return False
    return any(
        inside(widget_rect(toolbar, bar), position[0], position[1])
        for toolbar in main_toolbars(bar)
    )


def in_dead_zone(bar):
    """
    Return True if the pointer is in the view area (the main panel, the
    sidebar or the bottombar), or within DROP_DEAD_ZONE of it, and not over
    the toolbar.  A drop there does not undock.
    """
    if over_toolbar(bar):
        return False
    position = pointer_position(bar)
    if position is None:
        return False
    return inside(
        widget_rect(view_area(bar), bar), position[0], position[1], DROP_DEAD_ZONE
    )


def is_good_tab_drop(bar):
    """
    A tab drop is good over the tabs of any bar (reorder or move), over the
    toolbar, or outside the view area (undock).
    """
    for other in list(all_bars):
        if other.get_mapped() and over_tabs(other):
            return True
    return not in_dead_zone(bar)


def undock_tab(bar, gramplet):
    """
    Undock a gramplet from the menu, as dropping its tab away from the bar
    does: make the window, then move the gramplet into it.
    """
    if original_create_window is None:
        return
    pointer = Gdk.Display.get_default().get_default_seat().get_pointer()
    _screen, x_pos, y_pos = pointer.get_position()
    notebook = original_create_window(bar, bar, gramplet, x_pos, y_pos)
    if notebook is None:
        return
    bar.remove(gramplet)
    notebook.append_page(gramplet, None)


# The main window accepts dropped gramplet tabs itself.  Without that, no
# widget accepts a tab over the toolbar or the navigator, so GTK shows its
# "no drop" pointer there although the drop undocks.  Now GTK shows its
# normal drag pointer where the badge is good and "no drop" where it is bad.
WINDOW_DEST = "_undocked_gramplets_window_dest"
# The scrollable setting of a bar, kept while its tab scroll arrows are off.
SCROLLABLE = "_undocked_gramplets_scrollable"
# The gramplet to undock once its drag has ended (good drop on the window).
PENDING_UNDOCK = "_undocked_gramplets_pending_undock"


def dragged_bar(context):
    """
    Return the GrampletBar a tab is dragged from, or None for other drags.
    """
    source = Gtk.drag_get_source_widget(context)
    return source if source in all_bars else None


def cb_window_drag_motion(window, context, _x_pos, _y_pos, time):
    """
    A gramplet tab over the main window (where no deeper widget took it):
    allow the drop where the badge is good.
    """
    bar = dragged_bar(context)
    if bar is None:
        return False
    good = is_good_tab_drop(bar)
    Gdk.drag_status(context, Gdk.DragAction.MOVE if good else 0, time)
    return True


def cb_window_drag_drop(window, context, _x_pos, _y_pos, time):
    """
    A gramplet tab dropped on the main window: undock it where the badge is
    good, else the tab stays.

    A good drop is only remembered here; the gramplet is undocked after the
    drag has ended and GTK has put the tab label back (cb_bar_drag_end).
    Removing the page while GTK still counts the tab as dragged makes
    GtkNotebook cancel the drag from its half-dismantled drag window
    ("g_object_ref: assertion 'G_IS_OBJECT (object)' failed" and
    "gtk_container_get_focus_child" criticals), and an idle call made from
    the drop could run before the drag ended.  The drop is reported as not
    taken, as for a cancelled drop, which is the path where GTK restores the
    tab; cb_bar_drag_failed skips the slide-back animation.
    """
    bar = dragged_bar(context)
    if bar is None:
        return False
    gramplet = getattr(bar, "undocked_dragged", None)
    if gramplet is not None and is_good_tab_drop(bar):
        setattr(bar, PENDING_UNDOCK, gramplet)
    Gtk.drag_finish(context, False, False, time)
    return True


def cb_bar_drag_failed(bar, _context, _result):
    """
    A good drop on the main window is reported as not taken: skip the GTK
    animation of the tab sliding back, which would look like a refusal.
    """
    return getattr(bar, PENDING_UNDOCK, None) is not None


def idle_undock_tab(bar, gramplet):
    """
    Undock after a drop, once GTK has put the tab back.
    """
    try:
        if bar.page_num(gramplet) >= 0:
            undock_tab(bar, gramplet)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not undock the gramplet")
    return False


def ensure_window_dest(bar):
    """
    Make the main window of the bar accept dropped gramplet tabs, once.  If
    the window already accepts other drops, the tab target is added to them
    and the handlers leave those drops alone.
    """
    window = bar.get_toplevel()
    if not isinstance(window, Gtk.Window) or getattr(window, WINDOW_DEST, False):
        return
    entry = Gtk.TargetEntry.new(NOTEBOOK_TAB_TARGET, Gtk.TargetFlags.SAME_APP, 0)
    targets = window.drag_dest_get_target_list()
    if targets is None:
        window.drag_dest_set(0, [entry], Gdk.DragAction.MOVE)
    else:
        targets.add(
            Gdk.Atom.intern(NOTEBOOK_TAB_TARGET, False), Gtk.TargetFlags.SAME_APP, 0
        )
    window.connect("drag-motion", cb_window_drag_motion)
    window.connect("drag-drop", cb_window_drag_drop)
    setattr(window, WINDOW_DEST, True)


def cb_bar_drag_begin(bar, _context):
    """
    Remember which gramplet is dragged (pressing a tab selects it), and make
    sure the main window accepts the drop.

    The tab scroll arrows are switched off for the drag.  GTK takes the
    dragged tab out of the bar while dragging; when it was the only tab, the
    arrows are sized with negative dimensions ("Drawing a gadget with
    negative dimensions ... node arrow owner GrampletBar") and can be drawn
    huge over the bar.
    """
    try:
        bar.undocked_dragged = bar.get_nth_page(bar.get_current_page())
        ensure_window_dest(bar)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not prepare the drop")
    try:
        if getattr(bar, SCROLLABLE, None) is None:
            setattr(bar, SCROLLABLE, bar.get_scrollable())
            bar.set_scrollable(False)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not hide the tab arrows")


def cb_bar_drag_end(bar, _context):
    """
    Switch the tab scroll arrows back on after the drag, and undock the
    gramplet of a good drop on the main window.  This handler runs before
    the GtkNotebook one that puts the tab back, so the undocking waits for
    an idle moment.
    """
    try:
        scrollable = getattr(bar, SCROLLABLE, None)
        if scrollable is not None:
            setattr(bar, SCROLLABLE, None)
            bar.set_scrollable(scrollable)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not show the tab arrows")
    gramplet = getattr(bar, PENDING_UNDOCK, None)
    if gramplet is not None:
        setattr(bar, PENDING_UNDOCK, None)
        GLib.idle_add(idle_undock_tab, bar, gramplet)


def cb_bar_button_press(bar, event):
    """
    Right-click on a gramplet tab: show Move and Help.
    """
    if not is_right_click(event):
        return False
    position = pointer_position(bar)
    gramplet = tab_at(bar, *position) if position else None
    if gramplet is None:
        return False
    popup_gramplet_menu(bar, event, lambda: undock_tab(bar, gramplet), gramplet)
    return True


def cb_bar_motion(bar, event):
    """
    Show the open hand over a gramplet tab, so it is clear it can be dragged.
    """
    position = pointer_position(bar)
    over = position is not None and tab_at(bar, *position) is not None
    if event.window is not None:
        event.window.set_cursor(grab_cursor() if over else None)
    return False


def cb_bar_leave(_bar, event):
    """
    Back to the normal pointer when leaving the tabs.
    """
    if event.window is not None:
        event.window.set_cursor(None)
    return False


def patch_bar_gramplet_names(bar_class):
    """
    Fix two core GrampletBar methods (same code in Gramps 5.2 to 6.1) for a
    bar whose last gramplet is undocked.  The bar then shows only its
    "Gramplet Bar" placeholder tab (a Gtk.Label), and:

    * all_gramplets() returned the undocked gramplet objects instead of
      their names, so has_gramplet() never found them;
    * remove_gramplet() asked every page for gname, including the
      placeholder, so "Restore to defaults" failed with
      "AttributeError: 'Label' object has no attribute 'gname'".
    """
    if getattr(bar_class.all_gramplets, MARKER, None):
        return
    original_all = bar_class.all_gramplets
    original_remove = bar_class.remove_gramplet

    def all_gramplets(self):
        names = [
            page.gname
            for page in self.get_children()
            if not self.empty and hasattr(page, "gname")
        ]
        return names + [gramplet.gname for gramplet in self.detached_gramplets]

    def remove_gramplet(self, gname):
        for gramplet in self.detached_gramplets:
            if gramplet.gname == gname:
                # pylint: disable-next=protected-access
                self._GrampletBar__dock_gramplet(gramplet)
                self.remove_page(self.page_num(gramplet))
                return
        for page_num in range(self.get_n_pages()):
            if getattr(self.get_nth_page(page_num), "gname", None) == gname:
                self.remove_page(page_num)
                return

    setattr(all_gramplets, MARKER, original_all)
    setattr(remove_gramplet, MARKER, original_remove)
    bar_class.all_gramplets = all_gramplets
    bar_class.remove_gramplet = remove_gramplet


def patch_grampletbar():
    """
    Wrap GrampletBar.__init__ (drag feedback, hand pointer, right-click menu)
    and the create-window handler (the drop dead zone).  The handler must be
    replaced on the class before any bar exists, because each bar connects
    it when it is made.
    """
    global original_create_window  # pylint: disable=global-statement
    bar_class = getattr(gbmod, "GrampletBar", None)
    if bar_class is None or getattr(bar_class.__init__, MARKER, None):
        return
    original_create_window = getattr(bar_class, "_GrampletBar__create_window", None)
    if original_create_window is not None:

        def create_window(self, grampletbar, gramplet, x_pos, y_pos):
            if in_dead_zone(self):
                # Returning no notebook cancels the drag: the tab stays.
                return None
            return original_create_window(self, grampletbar, gramplet, x_pos, y_pos)

        setattr(create_window, MARKER, original_create_window)
        setattr(bar_class, "_GrampletBar__create_window", create_window)

    patch_bar_gramplet_names(bar_class)
    original_init = bar_class.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            all_bars.add(self)
            self.connect("drag-begin", cb_bar_drag_begin)
            self.connect("drag-end", cb_bar_drag_end)
            self.connect("drag-failed", cb_bar_drag_failed)
            self.undocked_feedback = DragFeedback(self, lambda: is_good_tab_drop(self))
            self.add_events(
                Gdk.EventMask.POINTER_MOTION_MASK
                | Gdk.EventMask.LEAVE_NOTIFY_MASK
                | Gdk.EventMask.BUTTON_PRESS_MASK
            )
            self.connect("motion-notify-event", cb_bar_motion)
            self.connect("leave-notify-event", cb_bar_leave)
            self.connect("button-press-event", cb_bar_button_press)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not extend the gramplet bar")

    setattr(init, MARKER, original_init)
    bar_class.__init__ = init


# -------------------------------------------------------------------------
#
# Dashboard gramplets
#
# -------------------------------------------------------------------------
def is_good_pane_drop(gramplet):
    """
    A Dashboard drop is good on the Dashboard itself (the gramplet moves).
    Anywhere else nothing happens.
    """
    pane = gramplet.pane
    position = pointer_position(pane)
    if position is None:
        return False
    rect = (0, 0, pane.get_allocated_width(), pane.get_allocated_height())
    return inside(rect, position[0], position[1])


def cb_hand_enter(_button, event):
    """
    Show the open hand over the drag button.  The pointer belongs to the
    input window of the button, so it is back to normal on leaving.
    """
    if event.window is not None:
        event.window.set_cursor(grab_cursor())
    return False


def use_hand_icon(gramplet):
    """
    Show a hand instead of the wrench (document-properties) on the
    "Drag to move; click to detach" button: media/hand-grab.svg, else the
    open hand of the pointer theme, else the wrench stays.  Core re-sets this
    same image after docking, so the hand stays.
    """
    image = gramplet.xml.get_object("gvpropertiesimage")
    if image is None:
        return
    pixbuf = button_hand_image()
    if pixbuf is None:
        return
    image.set_from_pixbuf(pixbuf)
    provider = Gtk.CssProvider()
    provider.load_from_data(BUTTON_HAND_CSS)
    gramplet.gvproperties.get_style_context().add_provider(
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def button_hand_image():
    """
    Return the hand for the Dashboard drag button, or None.
    """
    if "button_hand" not in image_cache:
        path = os.path.join(MEDIA_DIR, "hand-grab.svg")
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(
                path, BUTTON_HAND_SIZE, BUTTON_HAND_SIZE
            )
        except Exception:  # pylint: disable=broad-except
            LOG.debug("Undocked Gramplets: could not load %s", path)
            hand = cursor_image("grab", BUTTON_HAND_SIZE)
            pixbuf = hand[0] if hand is not None else None
        image_cache["button_hand"] = pixbuf
    return image_cache["button_hand"]


def undock_dashboard_gramplet(gramplet):
    """
    Undock from the menu, as clicking the drag button does.
    """
    if gramplet.gstate != "detached":
        gramplet.detach()


def cb_title_button_press(_widget, event, gramplet):
    """
    Right-click on the title or the drag button: show Move and Help.
    """
    if not is_right_click(event):
        return False
    popup_gramplet_menu(
        gramplet.titlelabel,
        event,
        lambda: undock_dashboard_gramplet(gramplet),
        gramplet,
    )
    return True


def patch_grid_gramplet():
    """
    Wrap GridGramplet.__init__: hand icon and pointer, drag feedback, and
    the right-click menu on the title row.
    """
    gramplet_class = getattr(gpmod, "GridGramplet", None)
    if gramplet_class is None or getattr(gramplet_class.__init__, MARKER, None):
        return
    original_init = gramplet_class.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            use_hand_icon(self)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not show the hand icon")
        try:
            button = self.gvproperties
            button.connect("enter-notify-event", cb_hand_enter)
            self.undocked_feedback = DragFeedback(
                button, lambda: is_good_pane_drop(self)
            )
            for widget in (self.titlelabel, button):
                widget.connect("button-press-event", cb_title_button_press, self)
        except Exception:  # pylint: disable=broad-except
            LOG.exception("Undocked Gramplets: could not extend the gramplet")

    setattr(init, MARKER, original_init)
    gramplet_class.__init__ = init


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
        patch_gramplet_window()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not patch the Dashboard window")
    try:
        patch_grampletbar()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not patch the gramplet bar")
    try:
        patch_grid_gramplet()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not patch the Dashboard gramplet")
    try:
        install_warning_filter()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Undocked Gramplets: could not install the warning filter")


install()
