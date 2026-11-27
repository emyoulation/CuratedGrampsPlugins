#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Brian McCullough
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# Patterned on the ExtendedAttributes gramplet
# Copyright (C) 2011 Nick Hall
# Copyright (C) 2011 Gary Burton
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
Person Addresses gramplet: a sortable table of the active Person's Addresses.
Double-click a row to open the Address editor.
"""

from gi.repository import Gtk

from gramps.gen.plug import Gramplet
from gramps.gen.datehandler import displayer as date_displayer
from gramps.gen.db import DbTxn
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import WindowActiveError
from gramps.gui.editors import EditAddress
from gramps.gui.listmodel import ListModel, NOSORT

from gramps.gen.const import GRAMPS_LOCALE as glocale

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

# Model column of the hidden address-list index
INDEX_COL = 10


class PersonAddresses(Gramplet):
    """
    Displays the Addresses of the active Person.
    """

    def init(self):
        self.person_handle = None
        self.gui.WIDGET = self.build_gui()
        container = self.gui.get_container_widget()
        container.remove(self.gui.textview)
        container.add(self.gui.WIDGET)
        self.gui.WIDGET.show()

    def build_gui(self):
        """
        Build the table. Click a column header to sort by it.
        """
        self.set_tooltip(_("Double-click on a row to edit the selected address."))
        top = Gtk.TreeView()
        # (title, sort column, min width); an empty title hides the column
        titles = [
            (_("Date"), 1, 100),
            ("", 1, 100),  # hidden date sort key
            (_("Street"), 2, 150),
            (_("Locality"), 3, 100),
            (_("City"), 4, 100),
            (_("County"), 5, 100),
            (_("State"), 6, 100),
            (_("Country"), 7, 100),
            (_("ZIP/Postal Code"), 8, 80),
            (_("Phone"), 9, 100),
            ("", NOSORT, 50),  # hidden index into the address list
        ]
        self.model = ListModel(top, titles, event_func=self.cb_edit_address)
        return top

    def db_changed(self):
        self.connect(self.dbstate.db, "person-update", self.cb_person_update)

    def active_changed(self, handle):
        self.update()

    def cb_person_update(self, handle_list):
        """Refresh only when the shown Person was changed."""
        if self.person_handle in handle_list:
            self.update()

    def update_has_data(self):
        active = self.get_active_object("Person")
        self.set_has_data(bool(active and active.get_address_list()))

    def main(self):
        self.model.clear()
        active = self.get_active_object("Person")
        self.person_handle = active.get_handle() if active else None
        if not active:
            self.set_has_data(False)
            return

        for index, addr in enumerate(active.get_address_list()):
            date = addr.get_date_object()
            if date.is_empty():
                date_text = date_sort = ""
            else:
                date_text = date_displayer.display(date)
                date_sort = "%012d" % date.get_sort_value()
            self.model.add(
                (
                    date_text,
                    date_sort,
                    addr.get_street(),
                    addr.get_locality(),
                    addr.get_city(),
                    addr.get_county(),
                    addr.get_state(),
                    addr.get_country(),
                    addr.get_postal_code(),
                    addr.get_phone(),
                    str(index),
                )
            )
        self.set_has_data(self.model.count > 0)

    def cb_edit_address(self, treeview):
        """
        Open the Address editor for the selected row; commit the Person
        when the editor's OK is pressed.
        """
        model, iter_ = treeview.get_selection().get_selected()
        if not iter_ or not self.person_handle:
            return
        person = self.dbstate.db.get_person_from_handle(self.person_handle)
        index = int(model.get_value(iter_, INDEX_COL))
        addr_list = person.get_address_list()
        if index >= len(addr_list):
            return
        addr = addr_list[index]

        def cb_commit(_addr):
            with DbTxn(
                _("Edit Person (%s)") % name_displayer.display(person),
                self.dbstate.db,
            ) as trans:
                self.dbstate.db.commit_person(person, trans)

        try:
            EditAddress(self.dbstate, self.uistate, [], addr, cb_commit)
        except WindowActiveError:
            pass
