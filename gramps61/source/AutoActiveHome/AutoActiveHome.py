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
Auto Active and Home Person - monkey-patch addon (draft).

Problem: adding the first person to a new tree sets neither the Active
Person nor the Home Person, so the Relationships view and many gramplets
stay blank.

Design (no overhead on established trees):

* When a tree is opened, it is checked once. If it already has a Home
  Person, nothing is connected and the addon does nothing more for that
  tree.
* Otherwise the addon listens to three person signals:
    - person-add / person-update: sent by normal edits (carry handles).
    - person-rebuild: sent once at the end of an import (batch imports
      and GEDCOM imports suppress the per-person signals).
* Core History.clear() already picks an Active Person after a rebuild
  (find_initial_person: the Home Person, else an arbitrary first row).
  In a tree without a Home Person that pick is replaced.
* Work is deferred to GLib idle, so it runs after the transaction and the
  other signal handlers, and several signals in a row cost one pass.
* Gramps handles start with a time stamp, so handle order is creation
  order: the smallest handle is the first Person created, the largest is
  the last one created (after an import, the final imported Person).
  Change times are not used: imports keep the change times from the
  source program (GEDCOM CHAN, Gramps XML change).
* When at least one Person exists:
    - no Active Person -> the last created Person becomes Active.
    - no Home Person (or a stale handle) -> the first created Person
      becomes Home.
  Since handles are unique, both are the same Person only when the tree
  has exactly one Person.
* Once both are set, all three handlers are disconnected.
"""

import logging

from gi.repository import GLib

LOG = logging.getLogger(".AutoActiveHome")

_PERSON_SIGNALS = ("person-add", "person-update", "person-rebuild")


# -------------------------------------------------------------------------
#
# Watcher
#
# -------------------------------------------------------------------------
class Watcher:
    """Watch one open tree until it has an Active and a Home Person."""

    def __init__(self, dbstate, uistate):
        self.dbstate = dbstate
        self.uistate = uistate
        self.db = None
        self.keys = []
        self.pending = False  # True while a settle pass is queued
        self.rebuilt = False  # a person-rebuild arrived since last pass
        dbstate.connect("database-changed", self.cb_database_changed)
        if dbstate.is_open():
            # Addon installed or enabled while a tree is open.
            self.cb_database_changed(dbstate.db)

    # -- connection management ---------------------------------------

    def cb_database_changed(self, db):
        """A tree was opened or closed: decide whether to listen."""
        self._disconnect()
        if db is None or not db.is_open():
            return
        if _has_home(db):
            LOG.debug("Tree has a Home Person; not watching.")
            return
        self.db = db
        self.keys = [
            db.connect("person-add", self.cb_person_changed),
            db.connect("person-update", self.cb_person_changed),
            db.connect("person-rebuild", self.cb_person_rebuild),
        ]
        LOG.debug("Watching person signals for Active/Home Person.")

    def _disconnect(self):
        if self.db is not None:
            for key in self.keys:
                try:
                    self.db.disconnect(key)
                except Exception:  # pylint: disable=broad-except
                    pass
        self.db = None
        self.keys = []
        self.pending = False
        self.rebuilt = False

    # -- signal handlers ---------------------------------------------

    def cb_person_changed(self, handles):
        """person-add / person-update (handles are not needed)."""
        self._queue()

    def cb_person_rebuild(self):
        """
        person-rebuild (end of an import).

        Core History.history_changed() answers this signal by calling
        History.clear(), which pushes db.find_initial_person(): the Home
        Person, or else whichever row the database returns first. That
        runs before this handler, so the Active Person is no longer
        empty; remember the rebuild so _settle() can replace that pick.
        """
        self.rebuilt = True
        self._queue()

    def _queue(self):
        if not self.pending:
            self.pending = True
            GLib.idle_add(self._settle)

    # -- the actual work ---------------------------------------------

    def _settle(self):
        self.pending = False
        rebuilt, self.rebuilt = self.rebuilt, False
        db = self.db
        if db is None or not db.is_open():
            return False
        need_home = not _has_home(db)
        # An empty Person history returns "", not None. After a rebuild in
        # a tree without a Home Person, the Active Person is the arbitrary
        # pick of find_initial_person(), so choose again.
        need_active = not self.uistate.get_active("Person") or (
            rebuilt and need_home
        )
        if need_active or need_home:
            handle_list = db.get_person_handles()
            if not handle_list:
                return False
            if need_active:
                active = max(handle_list)
                LOG.debug("Setting Active Person %s", active)
                self.uistate.set_active(active, "Person")
            if need_home:
                home = min(handle_list)
                LOG.debug("Setting Home Person %s", home)
                db.set_default_person_handle(home)

        if _has_home(db) and self.uistate.get_active("Person"):
            LOG.debug("Active and Home Person set; no longer watching.")
            self._disconnect()
        return False  # run once


# -------------------------------------------------------------------------
#
# Helpers
#
# -------------------------------------------------------------------------
def _has_home(db):
    """True when the Home Person handle points at an existing Person."""
    handle = db.get_default_handle()
    return bool(handle) and db.has_person_handle(handle)


# -------------------------------------------------------------------------
#
# Addon entry point
#
# -------------------------------------------------------------------------
_WATCHER = None


def load_on_reg(dbstate, uistate, plugin):
    """Install the watcher once per Gramps session (GUI only)."""
    global _WATCHER  # pylint: disable=global-statement
    if _WATCHER is None and uistate is not None and dbstate is not None:
        _WATCHER = Watcher(dbstate, uistate)
    return None
