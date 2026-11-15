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
Clipboard Ref Menu

A monkey patch addon for the right-click menu of every clipboard built on the
core clipboard tree view (the Clipboard window and the Collections Clipboard
gramplet).

* Rows that are only a reference to a primary object (a child, a person
  reference, an event reference, a place reference, a media reference or a
  repository reference) had no context menu at all.  They now offer
  "Clip <object type>", which puts the referenced primary object on the
  clipboard.
* Place rows get "Clip Enclosing Places", which puts every place above them
  in the place hierarchy on the clipboard.

The core files are not modified.  The patch wraps one method at startup
(load_on_reg), so a full restart of Gramps is needed after installing it.
"""

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------
import logging
import pickle

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

LOG = logging.getLogger("ClipboardRefMenu")

try:
    # Not importable in command line (no GTK) mode: then there is nothing to patch.
    from gi.repository import Gtk
    from gramps.gui import clipboard as cbmod
    from gramps.gui.utils import is_right_click

    GUI_AVAILABLE = True
except Exception:  # pylint: disable=broad-except
    GUI_AVAILABLE = False

MARKER = "_clipboard_ref_menu_original"

# Wrapper class name -> (primary object class, how to read its handle).
REF_TARGETS = {
    "ClipPersonRef": ("Person", lambda obj: obj.get_reference_handle()),
    "ClipChildRef": ("Person", lambda obj: obj.get_reference_handle()),
    "ClipEventRef": ("Event", lambda obj: obj.ref),
    "ClipPlaceRef": ("Place", lambda obj: obj.ref),
    "ClipMediaRef": ("Media", lambda obj: obj.get_reference_handle()),
    "ClipRepoRef": ("Repository", lambda obj: obj.ref),
}


# -------------------------------------------------------------------------
#
# What a clipboard row points to, and putting it on the clipboard
#
# -------------------------------------------------------------------------
def ref_target(wrapper):
    """
    Return (objclass, handle) of the primary object a reference row points
    to, or None when the row is not a reference.
    """
    entry = REF_TARGETS.get(type(wrapper).__name__)
    if entry is None:
        return None
    objclass, get_handle = entry
    try:
        return objclass, get_handle(wrapper._obj)
    except AttributeError:
        return None


def clip_primary(view, objclass, handle):
    """
    Put a primary object on the clipboard of this tree view, the same way a
    drop would.  Return True if a row was added.
    """
    db = view.dbstate.db
    wrapper_class = cbmod.obj2class(objclass)
    model = view.get_model()
    if wrapper_class is None or model is None:
        return False
    if not db.method("has_%s_handle", objclass)(handle):
        return False
    drag_type = wrapper_class.DRAG_TARGET.drag_type
    clip = wrapper_class(pickle.dumps((drag_type, id(view), handle, 0)))
    data = [drag_type, clip, None, clip._type, clip._value, clip._dbid, clip._dbname]
    if cbmod.model_contains(model, data):
        return False
    model.append(data)
    return True


def enclosing_place_handles(db, handle):
    """
    Return the handles of every place above this one, nearest first.  A place
    can have several enclosing places (for example over time), so all of them
    are followed.
    """
    seen = {handle}
    found = []
    queue = [handle]
    while queue:
        place = db.get_place_from_handle(queue.pop(0))
        if place is None:
            continue
        for placeref in place.get_placeref_list():
            if placeref.ref not in seen:
                seen.add(placeref.ref)
                found.append(placeref.ref)
                queue.append(placeref.ref)
    return found


def clip_enclosing_places(view, handle):
    """
    Put every place enclosing this place on the clipboard.
    """
    for place_handle in enclosing_place_handles(view.dbstate.db, handle):
        clip_primary(view, "Place", place_handle)


# -------------------------------------------------------------------------
#
# The right-click menu
#
# -------------------------------------------------------------------------
def add_menu_item(popup, label, callback):
    """
    Append a menu item to the popup and show it.
    """
    menu_item = Gtk.MenuItem(label=label)
    menu_item.connect("activate", callback)
    popup.append(menu_item)
    menu_item.show()


def build_menu(view, store, paths):
    """
    Build the right-click menu.  The items for primary objects are what the
    core builds; the Clip items are the additions.
    """
    core_gettext = cbmod._
    popup = Gtk.Menu()
    node = store.get_iter(paths[0])
    first = store.get_value(node, 1) if node else None
    objclass = first._objclass if first else None
    handle = first._handle if first else None
    db = view.dbstate.db

    if cbmod.obj2class(objclass):
        trans_class = glocale.trans_objclass(objclass)
        if db.method("has_%s_handle", objclass)(handle):
            add_menu_item(
                popup,
                core_gettext("See %s details", "the object") % trans_class,
                lambda widget: view.edit_obj(objclass, handle),
            )
            add_menu_item(
                popup,
                core_gettext("Make %s active", "the object") % trans_class,
                lambda widget: view.uistate.set_active(handle, objclass),
            )
            if objclass == "Place":
                place = db.get_place_from_handle(handle)
                if place is not None and place.get_placeref_list():
                    add_menu_item(
                        popup,
                        _("Clip Enclosing Places"),
                        lambda widget: clip_enclosing_places(view, handle),
                    )
        gids = set()
        for path in paths:
            node = store.get_iter(path)
            if not node:
                continue
            clip = store.get_value(node, 1)
            if clip._objclass == objclass:
                if db.method("has_%s_handle", objclass)(clip._handle):
                    obj = db.method("get_%s_from_handle", objclass)(clip._handle)
                    gids.add(obj.gramps_id)
        if gids:
            add_menu_item(
                popup,
                core_gettext("Create Filter from %s selected...", "the object")
                % trans_class,
                lambda widget: cbmod.make_filter(
                    view.dbstate, view.uistate, objclass, gids, title=view.title
                ),
            )
    elif first is not None:
        targets = []
        for path in paths:
            node = store.get_iter(path)
            target = ref_target(store.get_value(node, 1)) if node else None
            if target and db.method("has_%s_handle", target[0])(target[1]):
                targets.append(target)
        if targets:
            add_menu_item(
                popup,
                _("Clip %s") % glocale.trans_objclass(targets[0][0]),
                lambda widget: [clip_primary(view, cls, hdl) for cls, hdl in targets],
            )
    return popup


def patch_clipboard_view():
    """
    Wrap on_button_press of the clipboard tree view.
    """
    # Gramps 6.0 and later call it ClipboardMultiTreeView.  In 5.2 the
    # clipboard's own MultiTreeView is the class to patch (in later versions
    # that name is the generic widget, which must be left alone).
    view_class = getattr(cbmod, "ClipboardMultiTreeView", None)
    if view_class is None:
        view_class = getattr(cbmod, "MultiTreeView", None)
    if view_class is None or getattr(view_class.on_button_press, MARKER, None):
        return
    original = view_class.on_button_press

    def on_button_press(self, widget, event):
        if not is_right_click(event):
            return original(self, widget, event)
        store, paths = widget.get_selection().get_selected_rows()
        if not paths:
            return None
        self.newmenu = build_menu(self, store, paths)
        if self.newmenu.get_children():
            self.newmenu.popup_at_pointer(event)
        return True

    setattr(on_button_press, MARKER, original)
    view_class.on_button_press = on_button_press


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
        patch_clipboard_view()
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Clipboard Ref Menu: could not patch the clipboard")


install()
