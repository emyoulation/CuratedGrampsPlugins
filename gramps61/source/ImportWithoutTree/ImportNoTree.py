#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Brian McCullough
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
Import with No Tree Loaded (draft).

With no Family Tree loaded, Family Trees > Import... is normally hidden.
This addon shows an "Import..." item in its place (same label, so the core
translation is reused). It opens the standard Import Family Tree file
chooser. After the user picks a file and an importer, a new Family Tree is
created, named after the file plus a UTC timestamp, opened, and the file is
imported into it with the importer the user chose. Then the first imported
person becomes Home Person (if the file did not set one) and Active Person.

Cancel in the chooser creates nothing. There is no undo-history warning,
since there is no loaded tree whose history could be lost.
"""

import logging
import os
import time
import xml.etree.ElementTree as ET

from gramps.cli.clidbman import CLIDbManager
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui.dbloader import GrampsImportFileDialog
from gramps.gui.dialog import InfoDialog
from gramps.gui.uimanager import ActionGroup

_ = glocale.translation.gettext  # only core strings are used here

LOG = logging.getLogger(".ImportNoTree")

GROUP_NAME = "ImportNoTree"
ACTION_NAME = "ImportNoTree"
INSTALLED_FLAG = "_import_no_tree_installed"

# Same label text as the core menu item, so translators have nothing new.
MENU_XML = """
<section id="ImportNoTreeSection" groups="%s">
  <item>
    <attribute name="action">win.%s</attribute>
    <attribute name="label" translatable="yes">_Import...</attribute>
  </item>
</section>
""" % (
    GROUP_NAME,
    ACTION_NAME,
)


# ------------------------------------------------------------
#
# Helpers
#
# ------------------------------------------------------------
def make_import_title(filename, dbman):
    """
    Tree name from the import file plus a UTC timestamp, for example
    Genesis.ged -> Genesis_20261110-0013. Adds _2, _3 ... on collisions.
    """
    base = os.path.splitext(os.path.basename(filename))[0] or "Import"
    title = "%s_%s" % (base, time.strftime("%Y%m%d-%H%M", time.gmtime()))
    existing = {item[0] for item in dbman.current_names}
    candidate = title
    count = 2
    while candidate in existing:
        candidate = "%s_%d" % (title, count)
        count += 1
    return candidate


def set_home_and_active(dbstate, uistate):
    """
    Keep a Home Person that came with the file (Gramps XML can carry one);
    otherwise use the first person stored. Make that person Active.
    """
    db = dbstate.db
    person = db.find_initial_person()  # Home Person, else first stored row
    if person is None:
        return
    handle = person.get_handle()
    if not db.get_default_handle():
        db.set_default_person_handle(handle)
    uistate.set_active(handle, "Person")


# ------------------------------------------------------------
#
# NewTreeImportFileDialog
#
# ------------------------------------------------------------
class NewTreeImportFileDialog(GrampsImportFileDialog):
    """
    The stock Import Family Tree chooser, unchanged, except that just before
    importing it creates and opens a new tree named after the chosen file.
    """

    def __init__(self, viewmanager, callback=None):
        self.viewmanager = viewmanager
        GrampsImportFileDialog.__init__(
            self, viewmanager.dbstate, viewmanager.uistate, callback=callback
        )

    def do_import(self, importer, filename):
        if not self.dbstate.is_open():
            if not self.create_and_open_tree(filename):
                self.import_info = None
                return
        GrampsImportFileDialog.do_import(self, importer, filename)
        if self.dbstate.is_open():
            set_home_and_active(self.dbstate, self.uistate)

    def create_and_open_tree(self, filename):
        """
        Same housekeeping the command line and "Open with" path does,
        but through the GUI so menus, title and recent list update normally.
        """
        vm = self.viewmanager
        dbman = CLIDbManager(self.dbstate)
        title = make_import_title(filename, dbman)
        new_path, title = dbman.create_new_db_cli(title)
        LOG.debug("Created tree %r at %s", title, new_path)

        # The same two calls the Manage Family Trees "Load" button uses.
        vm.db_loader.read_file(new_path)
        if not self.dbstate.is_open():
            # read_file already showed the error. The empty tree stays.
            return False
        vm._post_load_newdb(new_path, "x-directory/normal", title)
        return True


# ------------------------------------------------------------
#
# Menu and action
#
# ------------------------------------------------------------
def cb_import_no_tree(viewmanager):
    """Return the action callback bound to this ViewManager."""

    def callback(*_args):
        if viewmanager.dbstate.is_open():
            viewmanager.import_data()  # normal path, should not happen
            return
        loader = viewmanager.db_loader
        loader.import_info = None
        NewTreeImportFileDialog(viewmanager, callback=loader.set_info)
        if not viewmanager.dbstate.is_open():
            return  # cancelled, or the tree could not be opened
        infotxt = loader.import_info_text()
        if infotxt:
            InfoDialog(_("Import Statistics"), infotxt, parent=viewmanager.window)
        # Same as the end of ViewManager.import_data (name-mangled method).
        post_load = getattr(viewmanager, "_ViewManager__post_load", None)
        if post_load:
            post_load()

    return callback


def add_menu_item(uimanager):
    """Put the section right after the Manage Family Trees / Recent section,
    where the hidden core Import item normally sits."""
    root = uimanager.et_xml
    if root.find(".//section[@id='ImportNoTreeSection']") is not None:
        return
    parent = root.find(".//section[@id='ftree']..")
    if parent is None:
        LOG.warning("Family Trees menu not found; Import item not added")
        return
    for index, child in enumerate(parent):
        if child.get("id") == "ftree":
            parent.insert(index + 1, ET.fromstring(MENU_XML))
            return


def set_visible(viewmanager, group):
    """Our item shows only while no tree is open."""
    viewmanager.uimanager.set_actions_visible(
        group, not viewmanager.dbstate.is_open()
    )


def install(viewmanager):
    """Add the action, menu item and the two visibility hooks."""
    uimanager = viewmanager.uimanager
    group = ActionGroup(GROUP_NAME, [(ACTION_NAME, cb_import_no_tree(viewmanager))])
    uimanager.insert_action_group(group)
    add_menu_item(uimanager)

    # A tree was opened (Manage Family Trees, Recent, command line, our own
    # import): hide our item. If the open failed, keep it.
    original_post_load_gui = viewmanager._post_load_newdb_gui

    def post_load_gui(*args, **kwargs):
        result = original_post_load_gui(*args, **kwargs)
        set_visible(viewmanager, group)
        uimanager.update_menu()
        return result

    viewmanager._post_load_newdb_gui = post_load_gui

    # The tree was closed: show our item. The original calls update_menu.
    original_post_close = viewmanager.post_close_db

    def post_close(*args, **kwargs):
        uimanager.set_actions_visible(group, True)
        return original_post_close(*args, **kwargs)

    viewmanager.post_close_db = post_close

    set_visible(viewmanager, group)
    # At startup init_interface() rebuilds the menu later anyway; when the
    # addon is installed mid-session this shows the change right away.
    uimanager.update_menu()
    setattr(viewmanager, INSTALLED_FLAG, True)


# ------------------------------------------------------------
#
# Entry point
#
# ------------------------------------------------------------
def load_on_reg(dbstate, uistate, plugin):
    """
    Called while ViewManager registers plugins (at startup, and again after
    Addon Manager installs). Install once per ViewManager; skip on the CLI.
    """
    if uistate is None:
        return
    viewmanager = getattr(uistate, "viewmanager", None)
    if viewmanager is None or getattr(viewmanager, INSTALLED_FLAG, False):
        return
    try:
        install(viewmanager)
    except Exception:  # never stop Gramps from starting
        LOG.error("ImportNoTree could not install", exc_info=True)
