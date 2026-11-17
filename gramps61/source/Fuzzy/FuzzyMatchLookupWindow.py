#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2017       Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2026       Claude Sonnet 5
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
Fuzzy Match Lookup - a small, standalone "does someone like this
already exist" window, backed by :class:`fuzzy_match_index.FuzzyMatchIndex`.

This is a companion to the Fuzzy Matching gramplet, not that gramplet
itself: it is a plain :class:`~gramps.gui.managedwindow.ManagedWindow`
dialog, built the same way this addon suite's own
``PluginManagerPlus.PluginStatus`` window is (a ``Gtk.Dialog`` wrapped
with ``ManagedWindow.__init__``/``set_window``, with its own
``build_menu_names`` so it appears as a normal entry under Gramps'
**Windows** menu), rather than an attempt to pop the actual gramplet's
own widget tree out of a docked pane into a floating window - the
latter needs Gramps' private ``GuiGramplet``/``GrampletWindow``
machinery, which has shifted across the 5.2-6.2 range this addon
targets and is not something to depend on sight-unseen.

Intended usage from another plugin (e.g. a Photo Tagging-style
gramplet that has just parsed a Surname and Given Name out of image
metadata, and wants to check whether that person might already be in
the tree before offering to create one)::

    try:
        from FuzzyMatchLookupWindow import show_fuzzy_lookup
    except ImportError:
        pass  # Fuzzy Matching isn't installed/enabled - skip the check
    else:
        show_fuzzy_lookup(
            dbstate, uistate, track, surname=parsed_surname,
            given_name=parsed_given_name,
        )

``show_fuzzy_lookup`` opens this window (or re-seeds and raises the
one already open - see the module-level singleton handling at the
bottom of this file) and returns immediately; it does not block for a
result. This addon's own :meth:`FuzzyMatchIndex.find_matches` is
available separately for a caller that wants the raw
``{surname: [handle, ...]}`` data without any window appearing at all.

The window shows one "Surname, Given" field, the same one the Fuzzy
Matching gramplet has: both build the shared
:class:`fuzzy_match_panel.FuzzyMatchPanel`, so they parse the field and
match the same way (see that module's docstring for the behavior).

Seeding (see :func:`show_fuzzy_lookup`):

* ``query``: "Surname, Given" text put in the field as typed, so its
  given part narrows the person list (everyone is shown when it
  matches nobody). The Data Entry and Photo Tagging gramplets pass this.
* ``surname`` and ``given_filter``: the older two-part form of the
  same thing, joined into "Surname, Given".
* ``given_name``: selects the closest given name without narrowing the
  list - kept for callers that parsed the name from metadata and want
  a nickname or initial not to hide anyone. It applies only while the
  field still holds the seeded text.

:func:`update_fuzzy_lookup` re-queries an already open window as its
caller's own field changes (live, after the same typing pause), without
opening or raising it.
"""

# ------------------------
# Python modules
# ------------------------
import logging

# ------------------------
# Gtk modules
# ------------------------
from gi.repository import Gdk, Gtk

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import WindowActiveError
from gramps.gui.editors import EditPerson
from gramps.gui.managedwindow import ManagedWindow

# ------------------------
# Gramps specific
# ------------------------
# Bare, top-level imports of this addon's own sibling modules - see the
# equivalent comment in FuzzyMatchingGramplet.py.
from fuzzy_match_panel import FuzzyMatchPanel
from name_query import format_name_query

# Also exposed whole, as ``<API module>.phonetic_codes`` and
# ``<API module>.name_query``, so other addons can list the installed
# encoding systems and their filter rules, and parse or build "Surname,
# Given" text the same way - see FuzzyMatchAPI.md.
import name_query  # pylint: disable=unused-import,wrong-import-position
import phonetic_codes  # pylint: disable=unused-import,wrong-import-position

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)

TITLE = _("Fuzzy Match Lookup")

#: The Encoding system chosen the last time any lookup window was open
#: this session (session only), so reopening does not reset to Soundex.
#: Independent of the gramplet's own choice.
_last_algorithm_id = None


# ------------------------------------------------------------
#
# FuzzyMatchLookupWindow
#
# ------------------------------------------------------------
class FuzzyMatchLookupWindow(ManagedWindow):
    """
    A small standalone window: type (or be handed) "Surname, Given", see
    every surname in the tree that phonetically matches and who carries
    each one, without the Fuzzy Matching gramplet open anywhere. Builds
    its own :class:`~fuzzy_match_panel.FuzzyMatchPanel` (and so its own
    index), kept current through the database signals while open and
    disconnected again on close (see :meth:`_cleanup`).
    """

    def __init__(
        self,
        dbstate,
        uistate,
        track,
        surname="",
        given_name="",
        on_select=None,
        given_filter="",
        select_hint="",
        query=None,
    ):
        """
        :param dbstate: The current :class:`~gramps.gen.dbstate.DbState`.
        :param uistate: The current
            :class:`~gramps.gui.displaystate.DisplayState`.
        :param track: ``ManagedWindow`` track list from the caller.
        :param surname: Surname for the field (see :meth:`set_query`).
        :param given_name: Given name to select the closest match to,
            without narrowing the list.
        :param on_select: Optional callback, called with a double-clicked
            Person instead of opening the Person editor (see
            :meth:`set_on_select`).
        :param given_filter: Given name for the field, narrowing the list.
        :param select_hint: Terse bottom-bar phrase saying what a
            double-click does (see :meth:`set_on_select`).
        :param query: "Surname, Given" text for the field; when given,
            ``surname`` and ``given_filter`` are not used.
        """
        self.dbstate = dbstate
        self.uistate = uistate
        self._on_select = on_select
        self._db_handlers = []  # [(signal_obj, handler_id), ...]
        self._database_changed_id = None

        self.window = Gtk.Dialog(title=TITLE)
        self.window.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        self.window.set_resizable(True)
        self.window.set_default_size(480, 480)
        ManagedWindow.__init__(self, uistate, track, self.__class__)
        self.set_window(self.window, None, TITLE, None)

        self.panel = FuzzyMatchPanel(
            dbstate,
            uistate,
            algorithm_id=_last_algorithm_id,
            on_person_activated=self._cb_person_activated,
            on_algorithm_changed=self._cb_algorithm_changed,
        )
        self.window.vbox.pack_start(self.panel.widget, True, True, 0)
        self.window.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        # Hint at the far left of the bottom bar: where a double-click
        # sends the person (text set by set_on_select).
        self.hint_label = Gtk.Label(halign=Gtk.Align.START, xalign=0.0)
        action_area = self.window.get_action_area()
        action_area.pack_start(self.hint_label, True, True, 0)
        action_area.set_child_secondary(self.hint_label, True)
        action_area.set_child_non_homogeneous(self.hint_label, True)
        self.hint_label.show()

        self.set_on_select(on_select, select_hint)
        self.window.connect("response", self.done)
        self._connect_db_signals()
        self._database_changed_id = self.dbstate.connect(
            "database-changed", self._cb_database_changed
        )
        self.window.show_all()
        self.panel.start_build()
        self.set_query(surname, given_name, given_filter, query)

    # -- ManagedWindow interface ------------------------------------------

    def build_menu_names(self, _obj) -> tuple:
        """
        This window's Windows menu label: a single leaf entry.

        :param _obj: unused
        :returns: ``(TITLE, None)``
        """
        return (TITLE, None)

    def done(self, _obj, _response_id) -> None:
        """
        Close button or the window manager's close: disconnect, close, and
        forget this window (see :func:`show_fuzzy_lookup`).

        :param _obj: unused (the dialog)
        :param _response_id: unused
        """
        self._cleanup()
        self.close()
        _forget_active_window(self)

    def _cleanup(self) -> None:
        """
        Disconnect the database signals and the database-changed watch,
        and stop the panel's build and typing timers. Idempotent.
        """
        for signal_obj, handler_id in self._db_handlers:
            try:
                signal_obj.disconnect(handler_id)
            except Exception:  # pylint: disable=broad-except
                pass
        self._db_handlers = []
        if self._database_changed_id is not None:
            try:
                self.dbstate.disconnect(self._database_changed_id)
            except Exception:  # pylint: disable=broad-except
                pass
            self._database_changed_id = None
        self.panel.shutdown()

    def _cb_database_changed(self, _db) -> None:
        """
        Another Family Tree was opened: close rather than re-index (the
        caller can reopen it through :func:`show_fuzzy_lookup`).

        :param _db: unused
        """
        self._cleanup()
        self.close()
        _forget_active_window(self)

    def _connect_db_signals(self) -> None:
        """Connect the panel to the database's change signals."""
        db = self.dbstate.db
        for signal, handler in (
            ("person-add", self.panel.cb_person_changed),
            ("person-update", self.panel.cb_person_changed),
            ("person-delete", self.panel.cb_person_deleted),
            ("person-rebuild", self.panel.cb_person_rebuild),
            ("event-update", self.panel.cb_event_changed),
        ):
            self._db_handlers.append((db, db.connect(signal, handler)))

    @staticmethod
    def _cb_algorithm_changed(algorithm_id: str) -> None:
        """
        Remember the picked Encoding system for the next window this
        session (see :data:`_last_algorithm_id`).

        :param algorithm_id: The newly selected system.
        """
        global _last_algorithm_id  # pylint: disable=global-statement
        _last_algorithm_id = algorithm_id

    # -- query / selection ---------------------------------------------------

    def set_on_select(self, on_select, select_hint: str = "") -> None:
        """
        Replace the double-click callback - what :func:`show_fuzzy_lookup`
        calls on an already open window, so a pick always lands on
        whichever caller (or caller's row) asked most recently.

        :param on_select: ``callable(person)``, or None to open the Person
            editor on double-click.
        :param select_hint: Terse bottom-bar phrase, e.g. "updates Data
            Entry New Person"; empty picks a default.
        """
        self._on_select = on_select
        if not select_hint:
            if on_select is None:
                select_hint = _("opens the Edit Person dialog")
            else:
                select_hint = _("updates {caller}").format(
                    caller=_caller_name(on_select)
                )
        self.hint_label.set_text(select_hint)
        # translators: {action} is a phrase such as "opens the Edit Person dialog"
        self.hint_label.set_tooltip_text(
            _("Double-clicking a person in the list on the right {action}.").format(
                action=select_hint
            )
        )

    def owned_by(self, on_select) -> bool:
        """
        Whether this window's double-click goes to ``on_select``.

        :param on_select: A callback (bound methods compare equal when
            they are the same method of the same object).
        :returns: True if it is the current callback.
        """
        return on_select is not None and self._on_select == on_select

    def set_query(
        self, surname: str = "", given_name: str = "", given_filter: str = "", query=None
    ) -> None:
        """
        Seed the field, look it up and raise the window.

        :param surname: Surname for the field (when ``query`` is None).
        :param given_name: Given name to select the closest match to,
            without narrowing the list.
        :param given_filter: Given name for the field (when ``query`` is
            None), narrowing the list.
        :param query: "Surname, Given" text for the field.
        """
        if query is None:
            query = format_name_query(surname, given_filter)
        self.panel.set_query(query, given_hint=given_name)
        self.window.present()

    def update_query(self, query: str) -> None:
        """
        Put ``query`` in the field as if typed (looked up after the typing
        pause), without raising the window.

        :param query: "Surname, Given" text.
        """
        if query != self.panel.query_text():
            self.panel.name_entry.set_text(query)

    def _cb_person_activated(self, person) -> None:
        """
        Double-click on a person: hand them to the caller's on_select, or
        open the Person editor. ``[]`` as the editor's track: this window
        is a window-manager leaf and cannot parent another window.

        :param person: The double-clicked Person.
        """
        if self._on_select is not None:
            self._on_select(person)
            return
        try:
            EditPerson(self.dbstate, self.uistate, [], person)
        except WindowActiveError:
            pass


# ---------------------------------------------------------------------------
#
# Public entry points for other plugins
#
# ---------------------------------------------------------------------------

#: The single currently open :class:`FuzzyMatchLookupWindow`, or None.
_active_window = None


def _caller_name(on_select) -> str:
    """
    Name the addon behind an ``on_select`` callback, for the default
    bottom-bar hint.

    :param on_select: The callback.
    :returns: e.g. "PhotoTaggingGramplet", or a generic phrase.
    """
    owner = getattr(on_select, "__self__", None)
    if owner is not None:
        return type(owner).__name__
    first = getattr(on_select, "__qualname__", "").split(".")[0]
    if first and not first.startswith("<"):
        return first
    return _("the calling addon")


def show_fuzzy_lookup(
    dbstate,
    uistate,
    track=None,
    surname="",
    given_name="",
    on_select=None,
    given_filter="",
    select_hint="",
    query=None,
):
    """
    Open the Fuzzy Match Lookup window seeded with a name, or re-seed and
    raise the one already open (also re-anchoring ``on_select``).

    :param dbstate: The current :class:`~gramps.gen.dbstate.DbState`.
    :param uistate: The current
        :class:`~gramps.gui.displaystate.DisplayState`.
    :param track: ``ManagedWindow`` track list from the caller, or None.
    :param surname: Surname to look up (when ``query`` is None).
    :param given_name: Given name to select the closest match to, without
        narrowing the list (for a name parsed from metadata).
    :param on_select: Optional ``callable(person)`` for a double-clicked
        person, instead of opening the Person editor.
    :param given_filter: Given name that narrows the list (when ``query``
        is None).
    :param select_hint: Terse bottom-bar phrase for what a double-click
        does, e.g. "updates Data Entry New Person".
    :param query: "Surname, Given" text for the field, as typed; its given
        part narrows the list. Newer than the other parameters: check
        for it with ``inspect.signature`` before passing it.
    :returns: The open :class:`FuzzyMatchLookupWindow` (or None).
    """
    global _active_window  # pylint: disable=global-statement
    if _active_window is not None:
        _active_window.set_query(surname, given_name, given_filter, query)
        _active_window.set_on_select(on_select, select_hint)
        return _active_window
    try:
        _active_window = FuzzyMatchLookupWindow(
            dbstate,
            uistate,
            track or [],
            surname,
            given_name,
            on_select,
            given_filter,
            select_hint,
            query,
        )
    except WindowActiveError:
        pass
    return _active_window


def update_fuzzy_lookup(query: str, on_select=None) -> bool:
    """
    Live update: re-query an already open lookup window with "Surname,
    Given" text, after the usual typing pause, without opening, raising or
    focusing it. With ``on_select``, only a window whose double-click still
    goes to that callback is updated, so typing in one addon does not take
    over a window another addon opened.

    :param query: "Surname, Given" text.
    :param on_select: The caller's own on_select callback, or None to
        update whatever window is open.
    :returns: True if a window was updated.
    """
    window = _active_window
    if window is None:
        return False
    if on_select is not None and not window.owned_by(on_select):
        return False
    window.update_query(query)
    return True


def _forget_active_window(window) -> None:
    """
    Clear :data:`_active_window` once ``window`` closes.

    :param window: The window that just closed.
    """
    global _active_window  # pylint: disable=global-statement
    if _active_window is window:
        _active_window = None
