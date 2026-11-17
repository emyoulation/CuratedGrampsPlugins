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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
GUI widgets for genealogical_numbering options.

* GuiCenterPersonOption: a drop-down list (Home Person, Active person, then
  the bookmarked and recently viewed people) with a "Select a different
  person" button.
* GuiAttributeChoiceOption: a drop-down list whose "Attribute: <type>" item
  has a submenu with every attribute type.

genealogical_numbering registers them with the plugin manager when the
Gramps GUI is running; the command line never imports this module.
"""

# ------------------------
# Python modules
# ------------------------
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import GLib, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui import widgets
from gramps.gui.plug._guioptions import GuiEnumeratedListOption
from gramps.gui.selectors import SelectorFactory

if TYPE_CHECKING:
    from gramps.gen.plug.menu import Option

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext


# ------------------------------------------------------------
#
# GuiCenterPersonOption
#
# ------------------------------------------------------------
class GuiCenterPersonOption(GuiEnumeratedListOption):
    """
    Center Person drop-down with a person selector button.

    :param option: The CenterPersonOption.
    :param dbstate: The database state.
    :param uistate: The user interface state.
    :param track: The window tracking list.
    :param override: Passed to GuiEnumeratedListOption.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, option: Any, dbstate: Any, uistate: Any, track: list, override: bool
    ) -> None:
        self._cp_option = option
        self._cp_dbstate = dbstate
        self._cp_uistate = uistate
        self._cp_track = track
        active = None
        recent: list = []
        if uistate is not None:
            active = uistate.get_active("Person")
            history = uistate.get_history("Person")
            if history is not None:
                recent = list(history.mru)
        option.refresh(active, recent)
        GuiEnumeratedListOption.__init__(
            self, option, dbstate, uistate, track, override
        )
        self._cp_button = widgets.SimpleButton("gtk-index", self.cb_select_person)
        self._cp_button.set_tooltip_text(_("Select a different person"))
        self.pack_end(self._cp_button, False, True, 0)
        self._cp_availkey = option.connect("avail-changed", self.cb_avail_changed)
        self.cb_avail_changed()

    def cb_select_person(self, dummy_button: Gtk.Button) -> None:
        """
        Pick any person of the tree and make them the Center Person.

        :param dummy_button: The selector button.
        """
        select_person = SelectorFactory("Person")
        sel = select_person(
            self._cp_dbstate,
            self._cp_uistate,
            self._cp_track,
            _("Select a person for the report"),
        )
        person = sel.run()
        if person is not None:
            self._cp_option.add_person(person.get_handle())

    def cb_avail_changed(self) -> None:
        """Grey out the button together with the drop-down list."""
        self._cp_button.set_sensitive(self._cp_option.get_available())

    def clean_up(self) -> None:
        """Remove the signal handler that blocks garbage collection."""
        if self._cp_option is not None:
            self._cp_option.disconnect(self._cp_availkey)
        GuiEnumeratedListOption.clean_up(self)
        self._cp_option = None


# ------------------------------------------------------------
#
# GuiAttributeChoiceOption
#
# ------------------------------------------------------------
class GuiAttributeChoiceOption(Gtk.Box):  # pylint: disable=too-many-instance-attributes
    """
    Drop-down list for an AttributeChoiceOption: the top-level choices, then
    "Attribute: <type>" with a submenu of every attribute type. GTK shows
    the submenu's own row first, so the shown attribute type can be picked
    again directly. Picking another type makes it the shown one.

    :param option: The AttributeChoiceOption.
    :param dbstate: The database state (unused).
    :param uistate: The user interface state (unused).
    :param track: The window tracking list (unused).
    :param override: Unused.
    """

    VALUE, TEXT = 0, 1

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        option: Option,
        dbstate: Any,
        uistate: Any,
        track: list,
        override: bool,
    ) -> None:
        del dbstate, uistate, track, override  # same signature as other GuiOptions
        Gtk.Box.__init__(self)
        self._option: Any = option
        self._store = Gtk.TreeStore(str, str)
        self._combo = Gtk.ComboBox.new_with_model(self._store)
        cell = Gtk.CellRendererText()
        self._combo.pack_start(cell, True)
        self._combo.add_attribute(cell, "text", self.TEXT)
        evt_box = Gtk.EventBox()
        evt_box.add(self._combo)
        self.pack_start(evt_box, True, True, 0)

        self._updating = False
        self._changekey = self._combo.connect("changed", self.cb_changed)
        self._fill()
        self._valuekey = option.connect("value-changed", self.cb_value_changed)
        self._optionskey = option.connect("options-changed", self.cb_options_changed)
        self._availkey = option.connect("avail-changed", self.cb_avail_changed)
        self.cb_avail_changed()
        self.set_tooltip_text(option.get_help())

    def _fill(self) -> None:
        """Rebuild the tree from the option and show its value."""
        self._combo.handler_block(self._changekey)
        self._store.clear()
        for value, text, children in self._option.get_tree():
            row = self._store.append(None, [value, text])
            for child_value, child_text in children or []:
                self._store.append(row, [child_value, child_text])
        self._show(self._option.get_value())
        self._combo.handler_unblock(self._changekey)

    def _show(self, value: str) -> None:
        """
        Make the top-level row with this value the active one.

        :param value: The option value.
        """
        for row in self._store:
            if row[self.VALUE] == value:
                self._combo.set_active_iter(row.iter)
                return
        self._combo.set_active(-1)

    def cb_changed(self, combo: Gtk.ComboBox) -> None:
        """
        A row was picked: a submenu row becomes the shown attribute.

        :param combo: The drop-down list.
        """
        tree_iter = combo.get_active_iter()
        if tree_iter is None:
            return
        value = self._store[tree_iter][self.VALUE]
        in_submenu = self._store.iter_parent(tree_iter) is not None
        self._updating = True
        try:
            self._option.set_value(value)  # may rebuild: options-changed
        finally:
            self._updating = False
        if in_submenu:
            # show the picked type on the top-level row, once GTK has
            # finished with the closing popup
            GLib.idle_add(self.cb_refill)

    def cb_refill(self) -> bool:
        """
        Idle callback: rebuild the rows.

        :returns: ``False``, so the callback runs once.
        """
        if self._option is not None:
            self._fill()
        return False

    def cb_value_changed(self) -> None:
        """The option value was changed elsewhere."""
        if self._updating:
            return
        self._combo.handler_block(self._changekey)
        self._show(self._option.get_value())
        self._combo.handler_unblock(self._changekey)

    def cb_options_changed(self) -> None:
        """The option rebuilt its list (e.g. another attribute type)."""
        if not self._updating:
            self._fill()

    def cb_avail_changed(self) -> None:
        """Grey out the list when the option is not available."""
        self.set_sensitive(self._option.get_available())

    def clean_up(self) -> None:
        """Remove the signal handlers that block garbage collection."""
        if self._option is not None:
            for key in (self._valuekey, self._optionskey, self._availkey):
                self._option.disconnect(key)
        self._option = None
