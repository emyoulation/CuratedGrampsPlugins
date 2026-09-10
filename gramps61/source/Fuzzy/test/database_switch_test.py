#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025  Phonetic Matching Gramplet contributors
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
Regression test for a real, reported crash: switching to a different
open Family Tree while the Fuzzy Matching gramplet was showing results
raised an unhandled ``gramps.gen.errors.HandleError`` inside
``cb_surname_selected``, from a handle that belonged to the *previous*
database, not the one Gramps had already switched ``dbstate.db`` to.

Root cause: :attr:`FuzzyMatchingGramplet._surname_to_handles` (and
:attr:`_surname_index`) are only ever rebuilt by :meth:`main`'s
background generator, which does not run synchronously - so right
after a database switch, before that background rebuild has run even
once, they still held handles from the tree that was just closed.
:meth:`FuzzyMatchingGramplet.db_changed` itself calls
:meth:`FuzzyMatchingGramplet._focus_active_person`, which can select a
row in the (still stale) left column, firing
:meth:`FuzzyMatchingGramplet.cb_surname_selected` - which then looked
up one of those stale handles in ``self.dbstate.db``, already the
*new* database, and raised. The fix,
:meth:`FuzzyMatchingGramplet._reset_phonetic_index`, discards both
dicts (and the two Matches columns) as the very first thing
``db_changed`` does, before anything else touches the database.

This test does not call ``db_changed()`` directly, or otherwise
shortcut the mechanism that is supposed to invoke it: switching
databases is expected to happen through Gramps' own Callback/Signal
system (``gramps.gen.dbstate.DbState``, a real ``Callback`` subclass,
whose ``"database-changed"`` signal the real
``gramps.gen.plug._gramplet.Gramplet.__init__`` connects to
``self._db_changed``, confirmed directly in the Gramps source), not
something this addon invents its own mechanism for. So this test uses
the real ``DbState``, calls its real ``signal_change()`` to actually
``emit()`` the signal, and lets that real, already-connected chain
invoke ``db_changed()`` - not a shortcut that would leave open the
possibility of the fix working through direct calls but not through
the actual signal path a real database switch uses. A first attempt at
this test used a database stand-in that was not a genuine
``gramps.gen.db.base.DbReadBase`` subclass; ``Callback.emit()``
type-checks its arguments and silently returns, calling no connected
callback at all, if that check fails - confirmed directly by reading
``gramps.gen.utils.callback.Callback.emit``, not assumed - so a
database stand-in that skips this would make the test pass for the
wrong reason (nothing ran at all) rather than genuinely exercising the
fix.

Needs a real (or virtual, e.g. ``xvfb-run``) display: constructing the
actual gramplet, not a stand-in, means constructing its real GTK
widgets too.
"""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import unittest

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

# ------------------------
# Gramps specific
# ------------------------
# This addon is not an installed package, so "FuzzyMatchingGramplet"
# cannot be reached with a package-relative import here - see the note
# at the top of FuzzyMatchingGramplet.py.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from gramps.gen.db.base import DbReadBase
from gramps.gen.dbstate import DbState
from gramps.gen.errors import HandleError
from gramps.gen.lib import Name, Person, Surname
from gramps.gen.plug import PluginRegister

# Trigger Gramps' own plugin-registration scan against this addon's
# own directory, exactly as its real startup would, before importing
# FuzzyMatchingGramplet (and, transitively, phonetic_codes): phonetic_codes'
# own discovery of this addon's RULE-type .gpr.py registrations runs once,
# at import time, so whichever test file imports it first needs to have
# already triggered the scan - see test/filter_persistence_test.py's own
# copy of this same pattern for why. Safe to call more than once.
_ADDON_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PluginRegister.get_instance().scan_dir(_ADDON_DIR, os.listdir(_ADDON_DIR))

from FuzzyMatchingGramplet import (
    FuzzyMatchingGramplet,
)  # noqa: E402  pylint: disable=wrong-import-position


def _make_person(handle: str, surname: str) -> Person:
    """
    Build a real, minimal :class:`gramps.gen.lib.Person` with just a
    primary name's surname set.

    :param handle: A fake but unique handle for this person.
    :param surname: The surname to give them.
    :returns: The constructed Person.
    """
    person = Person()
    person.set_handle(handle)
    name = Name()
    surname_obj = Surname()
    surname_obj.set_surname(surname)
    name.set_surname_list([surname_obj])
    person.set_primary_name(name)
    return person


class _FakeTreeDb(DbReadBase):
    """
    A minimal but genuine :class:`gramps.gen.db.base.DbReadBase`
    subclass - being a real subclass, not just duck-typed, matters:
    see the module docstring for why a stand-in that skips this would
    make this test pass without exercising anything.
    """

    def __init__(self, people):
        super().__init__()
        self._people = {person.get_handle(): person for person in people}

    def is_open(self):
        """This fake database is always open once constructed."""
        return True

    def get_surname_list(self):
        """Every distinct surname among the fake people, sorted."""
        return sorted(
            {
                person.get_primary_name().get_surname()
                for person in self._people.values()
            }
        )

    def get_person_handles(self, sort_handles=False):
        """Every fake handle."""
        del sort_handles
        return list(self._people.keys())

    def get_person_from_handle(self, handle):
        """
        :raises HandleError: if ``handle`` is not one of this fake
            database's own people - matching the real backend's own
            behavior (confirmed directly in
            ``gramps.gen.db.generic``), which is what the original bug
            report's traceback came from.
        """
        if handle not in self._people:
            raise HandleError(f"Handle {handle} not found")
        return self._people[handle]

    def get_family_from_handle(self, handle):
        """No families in this fake database."""
        del handle

    def set_prefixes(self, *args, **kwargs):
        """No-op: real DbState.change_database_noclose calls this."""


class _FakeHistory:
    """Minimal stand-in for Gramps' own navigation History."""

    def __init__(self):
        self.history = []
        self.index = -1
        self._callbacks = []

    def connect(self, _signal, callback):
        """Record a callback for cb_active_changed-style dispatch."""
        self._callbacks.append(callback)

    def push(self, handle):
        """Set the active handle and notify connected callbacks."""
        if not self.history or handle != self.history[-1]:
            self.history.append(handle)
            self.index += 1
        for callback in self._callbacks:
            callback(self.history[self.index])


class _FakeUistate:
    """Minimal stand-in for Gramps' own DisplayState/uistate."""

    def __init__(self):
        self.history = _FakeHistory()
        self.window = None

    def set_active(self, handle, _nav_type):
        """Push a new active handle."""
        self.history.push(handle)

    def get_active(self, _nav_type, _nav_group=0):
        """Return the current active handle, or None."""
        if not self.history.history:
            return None
        return self.history.history[self.history.index]


class _FakeGui:
    # pylint: disable=too-many-instance-attributes
    # Every attribute here is required by the real
    # gramps.gen.plug._gramplet.Gramplet.__init__ this stands in for;
    # trimming any would just move the AttributeError to construction
    # time instead of removing a real need.
    """
    Minimal stand-in for the real Gramplet GUI wrapper - just enough
    for the real ``gramps.gen.plug._gramplet.Gramplet.__init__`` to
    run without needing a full Gramps main window.
    """

    def __init__(self, dbstate, uistate):
        self.dbstate = dbstate
        self.uistate = uistate
        self.textview = Gtk.TextView()
        self._container = Gtk.Box()
        self._container.pack_start(self.textview, True, True, 0)
        self.gname = "Fuzzy Matching"
        self.tname = "Fuzzy Matching"
        self.help_url = "x"
        self.navtypes = []
        self.force_update = True
        self.title = "Fuzzy Matching"

    def get_container_widget(self):
        """Return the fake container the real Gramplet expects."""
        return self._container

    def on_button_press(self, *_args):
        """No-op: the real Gramplet.__init__ connects this signal."""
        return False

    def on_motion(self, *_args):
        """No-op: the real Gramplet.__init__ connects this signal."""
        return False


def _wait_until_idle(gramplet, iterations=200):
    """
    Pump the GTK main loop until the gramplet's background generator
    reports it has finished (or ``iterations`` is exhausted).

    :param gramplet: The gramplet whose ``_idle_id``/``status_box`` to
        watch.
    :param iterations: A generous ceiling so a genuine bug (the
        generator never finishing) fails the test instead of hanging
        it.
    """
    for _ in range(iterations):
        while Gtk.events_pending():
            Gtk.main_iteration()
        if gramplet._idle_id == 0 and not gramplet.status_box.get_visible():
            return


# ------------------------------------------------------------
#
# DatabaseSwitchTest
#
# ------------------------------------------------------------
class DatabaseSwitchTest(unittest.TestCase):
    """
    Confirms switching Family Trees, through Gramps' real
    Callback/Signal chain, neither crashes nor leaves stale data
    displayed - the exact scenario reported.
    """

    def setUp(self):
        old_db = _FakeTreeDb(
            [_make_person("OLD1", "Boucher"), _make_person("OLD2", "Smith")]
        )
        self.new_db = _FakeTreeDb(
            [_make_person("NEW1", "Anderson"), _make_person("NEW2", "Robinson")]
        )

        # A real DbState, not a stand-in - see the module docstring
        # for why this matters.
        self.dbstate = DbState()
        self.dbstate.change_database_noclose(old_db)
        self.uistate = _FakeUistate()
        self.uistate.set_active("OLD1", "Person")
        gui = _FakeGui(self.dbstate, self.uistate)

        self.gramplet = FuzzyMatchingGramplet(gui)
        _wait_until_idle(self.gramplet)

    def test_indexed_against_old_database_first(self) -> None:
        """Sanity check: the gramplet actually indexed the old database."""
        self.assertEqual(
            self.gramplet._surname_to_handles,
            {"Boucher": ["OLD1"], "Smith": ["OLD2"]},
        )

    def test_switching_database_does_not_crash(self) -> None:
        """
        The exact bug reported: this used to raise HandleError from
        inside cb_surname_selected.
        """
        self.dbstate.change_database_noclose(self.new_db)
        self.uistate.set_active("NEW1", "Person")
        try:
            self.dbstate.signal_change()  # the real signal emission
            _wait_until_idle(self.gramplet)
        except HandleError as err:
            self.fail(f"switching database raised HandleError: {err}")

    def test_index_rebuilds_for_new_database_only(self) -> None:
        """
        After the switch, the index must reflect only the new
        database - no leftover entries from the old one.
        """
        self.dbstate.change_database_noclose(self.new_db)
        self.uistate.set_active("NEW1", "Person")
        self.dbstate.signal_change()
        _wait_until_idle(self.gramplet)

        self.assertEqual(
            self.gramplet._surname_to_handles,
            {"Anderson": ["NEW1"], "Robinson": ["NEW2"]},
        )
        self.assertEqual(
            sorted(row[0] for row in self.gramplet.surname_store),
            ["Anderson"],
        )


if __name__ == "__main__":
    unittest.main()
