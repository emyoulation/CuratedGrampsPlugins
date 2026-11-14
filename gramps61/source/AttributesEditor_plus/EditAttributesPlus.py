#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
#               2009       Gary Burton
# Copyright (C) 2011       Tim G L Lyons
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Edit Attributes Plus - monkey-patch addon (DRAFT).

Loaded once at plugin registration (load_on_reg=True). Patches, in place:

1. Attribute Editor (EditAttributeRoot / EditAttribute, so also
   EditSrcAttribute and EditFamilyAttribute): bundled Glade layout with a
   resizable top pane, multi-line word-wrapping Value field, and the
   Citations/Notes notebook in the bottom pane.
2. StandardCustomSelector.create_list: built-in and custom types sorted
   together; flat popups with more than WRAP_ITEM_THRESHOLD entries are
   shown as a WRAP_COLUMN_COUNT column grid.
3. GrampletBar (sidebar/bottombar) "Add a gramplet" submenu: same grid.
4. GrampletPane (Dashboard) right-click "Add a gramplet" submenu: same grid.

Each patch is applied independently; if the Gramps internals it relies on
are missing, that patch is skipped and logged rather than breaking startup.
"""

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------
import logging
import math
import os

# -------------------------------------------------------------------------
#
# GTK modules
#
# -------------------------------------------------------------------------
from gi.repository import Gtk

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.config import config
from gramps.gen.lib import NoteType

_ = glocale.translation.sgettext

LOG = logging.getLogger(".EditAttributesPlus")

ADDON_DIR = os.path.dirname(os.path.abspath(__file__))
GLADE_FILE = "editattribute.glade"

# Flat popups / menus with more than this many entries become a grid.
WRAP_ITEM_THRESHOLD = 12
# Number of grid columns once WRAP_ITEM_THRESHOLD is exceeded.
WRAP_COLUMN_COUNT = 3
# GTK combo-box wrapping fills left-to-right, row by row. The gramplet
# menus do the same so both kinds of popup read alike. Set True to fill
# the gramplet menus top-to-bottom, column by column instead.
FILL_DOWN_COLUMNS = False

# Marker so a second import (e.g. plugin reload) does not double-patch.
_PATCH_FLAG = "_edit_attributes_plus_patched"


# =========================================================================
#
# Shared helper: a Gtk.Menu laid out as a grid
#
# =========================================================================
def build_grid_menu(entries, on_activate):
    """
    Build a Gtk.Menu from (label, data) pairs. Once there are more than
    WRAP_ITEM_THRESHOLD entries, the items are attached as a
    WRAP_COLUMN_COUNT column grid (Gtk.Menu.attach) instead of one column.

    on_activate(data) is called when an item is chosen.
    """
    menu = Gtk.Menu()
    count = len(entries)
    use_grid = count > WRAP_ITEM_THRESHOLD
    rows = math.ceil(count / WRAP_COLUMN_COUNT) if use_grid else count

    for index, (label, data) in enumerate(entries):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda _item, value=data: on_activate(value))
        if use_grid:
            if FILL_DOWN_COLUMNS:
                col, row = divmod(index, rows)
            else:
                row, col = divmod(index, WRAP_COLUMN_COUNT)
            menu.attach(item, col, col + 1, row, row + 1)
        else:
            menu.append(item)
        item.show()
    return menu


def _submenu_item(label, entries, on_activate):
    """
    A Gtk.MenuItem carrying a grid submenu; insensitive when empty.
    """
    item = Gtk.MenuItem(label=label)
    if entries:
        item.set_submenu(build_grid_menu(entries, on_activate))
    else:
        item.set_sensitive(False)
    item.show()
    return item


def _sorted_pairs(pairs):
    """Sort (label, data) pairs by locale-aware label."""
    return sorted(pairs, key=lambda pair: glocale.sort_key(pair[0]))


# =========================================================================
#
# 1. Attribute Editor
#
# =========================================================================
def _patch_attribute_editor():
    from gramps.gui.editors import editattribute
    from gramps.gui.glade import Glade
    from gramps.gui.widgets import (
        MonitoredDataType,
        MonitoredText,
        PrivacyButton,
        UndoableBuffer,
    )
    from gramps.gui.editors.displaytabs import CitationEmbedList, NoteTab

    root = editattribute.EditAttributeRoot
    full = editattribute.EditAttribute
    if getattr(root, _PATCH_FLAG, False):
        return

    def _local_init(self):
        self.top = Glade(GLADE_FILE, dirname=ADDON_DIR)
        self.set_window(
            self.top.toplevel, self.top.get_object("title"), _("Attribute Editor")
        )
        self.setup_configs("interface.attribute", 600, 350)

    def _setup_fields(self):
        # UndoableBuffer has no __gtype_name__, so Glade cannot create it;
        # swap it in for the plain GtkTextBuffer here.
        value_widget = self.top.get_object("attr_value")
        value_widget.set_buffer(UndoableBuffer())
        self.value_field = MonitoredText(
            value_widget,
            self.obj.set_value,
            self.obj.get_value,
            self.db.readonly,
        )
        self.priv = PrivacyButton(
            self.top.get_object("private"), self.obj, self.db.readonly
        )
        self.type_selector = MonitoredDataType(
            self.top.get_object("attr_menu"),
            self.obj.set_type,
            self.obj.get_type,
            self.db.readonly,
            custom_values=self.alist,
        )

    def _root_tabbed_pages(self):
        notebook = Gtk.Notebook()
        self._setup_notebook_tabs(notebook)
        notebook.show_all()
        self.top.get_object("main_paned").pack2(notebook, resize=True, shrink=True)

    def _full_tabbed_pages(self):
        notebook = Gtk.Notebook()
        self.srcref_list = CitationEmbedList(
            self.dbstate,
            self.uistate,
            self.track,
            self.obj.get_citation_list(),
            "attribute_editor_citations",
        )
        self._add_tab(notebook, self.srcref_list)
        self.track_ref_for_deletion("srcref_list")

        self.note_tab = NoteTab(
            self.dbstate,
            self.uistate,
            self.track,
            self.obj.get_note_list(),
            "attribute_editor_notes",
            notetype=NoteType.ATTRIBUTE,
        )
        self._add_tab(notebook, self.note_tab)
        self.track_ref_for_deletion("note_tab")

        self._setup_notebook_tabs(notebook)
        notebook.show_all()
        self.top.get_object("main_paned").pack2(notebook, resize=True, shrink=True)

    root._local_init = _local_init
    root._setup_fields = _setup_fields
    root._create_tabbed_pages = _root_tabbed_pages
    full._create_tabbed_pages = _full_tabbed_pages
    setattr(root, _PATCH_FLAG, True)


# =========================================================================
#
# 2. Type popups (StandardCustomSelector)
#
# =========================================================================
def _patch_custom_selector():
    from gramps.gui import autocomp

    selector = autocomp.StandardCustomSelector
    if getattr(selector, _PATCH_FLAG, False):
        return
    if hasattr(autocomp, "WRAP_ITEM_THRESHOLD"):
        # The core autocomp.py already carries this change.
        LOG.info("autocomp.py already wraps type popups; not patched")
        return

    def create_list(self):
        store = Gtk.ListStore(int, str)
        entries = [
            (key, self.mapping[key]) for key in self.mapping if key != self.custom_key
        ]
        if self.additional:
            for extra in self.additional:
                pair = self.get_key_and_value(extra)
                if pair:  # get_key_and_value() returns None for (int, "")
                    entries.append(pair)
        entries.sort(key=lambda entry: glocale.sort_key(entry[1]))

        for index, (key, value) in enumerate(entries):
            store.append(row=[key, value])
            if key == self.active_key:
                self.active_index = index

        if not self.menu and len(entries) > WRAP_ITEM_THRESHOLD:
            self.selector.set_wrap_width(WRAP_COLUMN_COUNT)
        return store

    selector.create_list = create_list
    setattr(selector, _PATCH_FLAG, True)


# =========================================================================
#
# 3. Gramplet bars (sidebar / bottombar)
#
# =========================================================================
def _patch_grampletbar():
    from gramps.gui.widgets import grampletbar

    bar = grampletbar.GrampletBar
    if getattr(bar, _PATCH_FLAG, False):
        return

    if hasattr(bar, "_GrampletBar__refresh_menu"):
        # Gramps 6.0 / 6.1: the drop-down is a Gtk.MenuButton fed from a
        # Gio.Menu model, which cannot lay items out in a grid. Replace the
        # model with a real Gtk.Menu, rebuilt whenever core would have
        # refreshed the model (init, page added, page removed).
        original_refresh = bar._GrampletBar__refresh_menu

        def find_menu_button(self):
            """
            Locate the bar's drop-down Gtk.MenuButton. Core sets it directly
            as the notebook action widget, but a customized grampletbar.py
            may pack it inside a box with other buttons, so search the
            action widgets' children too. Prefer the button that owns the
            core Gio.Menu model. Cache the result: once set_popup() is used
            the button no longer reports that model.
            """
            cached = getattr(self, "_eap_menu_button", None)
            if cached is not None:
                return cached

            candidates = []

            def walk(widget):
                if widget is None:
                    return
                if isinstance(widget, Gtk.MenuButton):
                    candidates.append(widget)
                elif isinstance(widget, Gtk.Container):
                    for child in widget.get_children():
                        walk(child)

            for pack in (Gtk.PackType.END, Gtk.PackType.START):
                walk(self.get_action_widget(pack))

            model = getattr(self, "menu", None)
            button = next(
                (cand for cand in candidates if cand.get_menu_model() is model),
                candidates[0] if candidates else None,
            )
            if button is not None:
                self._eap_menu_button = button
            return button

        def refresh_menu(self):
            button = find_menu_button(self)
            if button is None:
                # Not found (yet, or ever): keep the core Gio.Menu menu
                # working rather than leaving the bar without one.
                LOG.debug("Gramplet bar menu button not found; using core menu")
                original_refresh(self)
                return

            menu = Gtk.Menu()
            nav_type = self.pageview.navigation_type()
            add_list = grampletbar.GET_GRAMPLET_LIST(nav_type, self.all_gramplets())
            menu.append(
                _submenu_item(
                    _("Add a gramplet"), _sorted_pairs(add_list), self.add_gramplet
                )
            )

            if not (self.empty or config.get("interface.grampletbar-close")):
                remove_list = [
                    (gramplet.title, gramplet.gname)
                    for gramplet in self.get_children() + self.detached_gramplets
                ]
                menu.append(
                    _submenu_item(
                        _("Remove a gramplet"),
                        _sorted_pairs(remove_list),
                        self.remove_gramplet,
                    )
                )

            restore = Gtk.MenuItem(label=_("Restore default gramplets"))
            restore.connect(
                "activate",
                lambda _item: self._GrampletBar__restore_clicked(None, None, None),
            )
            menu.append(restore)
            menu.append(Gtk.SeparatorMenuItem())

            bar_help = Gtk.MenuItem(label=_("Gramplet Bar Help"))
            bar_help.connect(
                "activate",
                lambda _item: self.on_help_grampletbar_clicked(None, None, None),
            )
            menu.append(bar_help)

            about = Gtk.MenuItem(label=_("About Gramplets"))
            about.connect(
                "activate",
                lambda _item: self.on_help_gramplets_clicked(None, None, None),
            )
            menu.append(about)

            menu.show_all()
            # set_popup() also detaches the Gio.Menu model from the button.
            button.set_popup(menu)

        bar._GrampletBar__refresh_menu = refresh_menu

    elif hasattr(bar, "_GrampletBar__create_submenu"):
        # Gramps 5.2: the menu is a plain Gtk.Menu built on each click;
        # only the submenu builder needs replacing.
        def create_submenu(self, main_menu, gramplet_list, callback_func):
            if main_menu:
                entries = _sorted_pairs(gramplet_list)
                submenu = build_grid_menu(
                    entries, lambda gname: callback_func(None, gname)
                )
                main_menu.set_submenu(submenu)

        bar._GrampletBar__create_submenu = create_submenu

    else:
        LOG.warning("Unknown GrampletBar layout; gramplet bar menu not patched")
        return

    setattr(bar, _PATCH_FLAG, True)


# =========================================================================
#
# 4. Dashboard (GrampletPane right-click menu)
#
# =========================================================================
def _patch_dashboard():
    from gramps.gui.widgets import grampletpane
    from gramps.gui.utils import is_right_click

    pane = grampletpane.GrampletPane
    if getattr(pane, _PATCH_FLAG, False):
        return

    def button_press(self, obj, event):
        if not is_right_click(event):
            return False
        self._popup_xy = (event.x, event.y)

        plugs = [
            gplug
            for gplug in grampletpane.PLUGMAN.get_reg_gramplets()
            if gplug.navtypes == [] or "Dashboard" in gplug.navtypes
        ]
        add_entries = _sorted_pairs([(plug.name, plug.name) for plug in plugs])

        names = [gramplet.title for gramplet in self.closed_gramplets]
        names.extend(opts["title"] for opts in self.closed_opts)
        restore_entries = _sorted_pairs([(name, name) for name in names])

        menu = Gtk.Menu()
        menu.append(_submenu_item(_("Add a gramplet"), add_entries, self.add_gramplet))
        menu.append(
            _submenu_item(
                _("Restore a gramplet"), restore_entries, self.restore_gramplet
            )
        )
        menu.attach_to_widget(obj, None)
        menu.show_all()
        # Keep a reference so the menu is not garbage collected while shown.
        self._eap_popup_menu = menu
        menu.popup_at_pointer(event)
        return True

    # The event box connects self._button_press when each Dashboard is
    # built; this addon loads at registration, before any view exists.
    pane._button_press = button_press
    setattr(pane, _PATCH_FLAG, True)


# =========================================================================
#
# Apply
#
# =========================================================================
for _patch in (
    _patch_attribute_editor,
    _patch_custom_selector,
    _patch_grampletbar,
    _patch_dashboard,
):
    try:
        _patch()
        LOG.debug("EditAttributesPlus: %s applied", _patch.__name__)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("EditAttributesPlus: %s failed", _patch.__name__)
