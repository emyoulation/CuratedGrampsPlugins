#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2017       Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2026       Claude Sonnet 5
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

Given Name, when passed to :func:`show_fuzzy_lookup`, is used to
select and scroll the right column to whichever person's given name
sorts closest to it - not to filter the list down first, and not
shown in the Given Name field afterward either (see
:meth:`FuzzyMatchLookupWindow.set_query` for why: filtering first, or
leaving the value sitting in the field as a filter for whatever gets
clicked next, both risk hiding the very person being sought, or
someone else entirely, if a recorded given name doesn't happen to
contain the one passed in - a nickname, an initial, a transcription
difference from photo metadata, and so on). A manual edit or
selection in that field, by the person actually using the window,
still filters normally - plainly and un-phonetically - the same as
always. A phonetic given-name match (for the "closest" comparison, or
as a filter) could reuse the same ``phonetic_codes.ALGORITHMS`` this
addon already has, but that's a distinct enhancement, not implemented
here.
"""

# ------------------------
# Python modules
# ------------------------
import logging
import pickle
from bisect import bisect_left

# ------------------------
# Gtk modules
# ------------------------
from gi.repository import Gdk, GLib, Gtk

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import HandleError, WindowActiveError
from gramps.gui.ddtargets import DdTargets
from gramps.gui.editors import EditPerson
from gramps.gui.managedwindow import ManagedWindow

# ------------------------
# Gramps specific
# ------------------------
# See the equivalent, longer comment in FuzzyMatchingGramplet.py for
# why this is a bare, top-level import rather than a package-relative
# one - the same reasoning applies to every sibling module in this
# addon's own folder.
from fuzzy_match_display import format_person, person_sort_key, refresh_matching_person_rows
from fuzzy_match_index import FuzzyMatchIndex
from phonetic_codes import ALGORITHM_DESCRIPTIONS, ALGORITHM_LABELS, DEFAULT_ALGORITHM

# Also exposed whole, as ``<API module>.phonetic_codes``, so other addons
# can list the installed encoding systems (ALGORITHM_LABELS) and get their
# filter rule classes (ALGORITHM_FILTER_RULES) - see FuzzyMatchAPI.md.
import phonetic_codes  # pylint: disable=unused-import,wrong-import-position

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)

TITLE = _("Fuzzy Match Lookup")

#: The Encoding system chosen the last time any FuzzyMatchLookupWindow
#: was open this session, remembered here (module level, not on the
#: instance) purely so reopening the window - even after fully closing
#: it - doesn't reset back to Soundex. This is session-only, not saved
#: to disk between Gramps runs; see cb_algorithm_changed() for where
#: it's updated. Not shared with FuzzyMatchingGramplet.py's own
#: Encoding system choice - each keeps its own, the same way each
#: keeps its own independent FuzzyMatchIndex (see the class docstring).
_last_algorithm_id = None


# ------------------------------------------------------------
#
# FuzzyMatchLookupWindow
#
# ------------------------------------------------------------
class FuzzyMatchLookupWindow(ManagedWindow):
    """
    A small standalone window: type (or be handed) a Surname, see
    every surname in the Family Tree that phonetically matches it and
    who carries each one - without needing the Fuzzy Matching gramplet
    open in any view. Has its own Encoding system selector (see
    :meth:`cb_algorithm_changed`) - deliberately independent of
    ``FuzzyMatchingGramplet.py``'s own, since this window's whole
    reason to exist is working without that gramplet open anywhere.

    Builds its own private :class:`~fuzzy_match_index.FuzzyMatchIndex`
    on construction and keeps it current for as long as this window
    stays open, via the database's own person/event signals (see
    :meth:`_connect_db_signals`) - the same incremental-patch approach
    ``FuzzyMatchingGramplet.py`` uses, not a rescan on every change.
    Unlike that gramplet (which lives for the whole Gramps session),
    this window's signal connections are explicitly disconnected when
    it closes (see :meth:`done`), since a plain
    :class:`~gramps.gui.managedwindow.ManagedWindow` has no framework
    equivalent of ``Gramplet.connect``/``Gramplet.disconnect`` doing
    that bookkeeping automatically.
    """

    def __init__(self, dbstate, uistate, track, surname="", given_name=""):
        """
        :param dbstate: The current :class:`~gramps.gen.dbstate.DbState`.
        :param uistate: The current
            :class:`~gramps.gui.displaystate.DisplayState`.
        :param track: ``ManagedWindow`` track list from the caller (an
            empty list is fine for a caller with no window of its own
            to nest this under).
        :param surname: Surname to seed the Surname field with.
        :param given_name: Given name to seed the Given Name filter
            with.
        """
        self.dbstate = dbstate
        self.uistate = uistate

        algorithm_id = _last_algorithm_id or DEFAULT_ALGORITHM
        self._index = FuzzyMatchIndex(dbstate.db, algorithm_id)
        self._build_generator = None
        self._build_idle_id = 0
        self._db_handlers = []  # [(signal_obj, handler_id), ...]

        self.window = Gtk.Dialog(title=TITLE)
        self.window.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        self.window.set_resizable(True)
        self.window.set_default_size(480, 480)
        ManagedWindow.__init__(self, uistate, track, self.__class__)
        self.set_window(self.window, None, TITLE, None)

        self._build_gui()
        self.window.connect("response", self.done)

        self._connect_db_signals()
        self._database_changed_id = self.dbstate.connect(
            "database-changed", self._cb_database_changed
        )

        self.window.show_all()
        self._start_build()
        self.set_query(surname, given_name)

    # -- GUI construction ------------------------------------------------

    def _build_gui(self) -> None:
        """Build the Surname/Given Name fields and the two Matches lists."""
        grid = Gtk.Grid()
        grid.set_border_width(6)
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)

        surname_label = Gtk.Label(label=_("Surname:"), halign=Gtk.Align.START)
        grid.attach(surname_label, 0, 0, 1, 1)
        self.surname_entry = Gtk.Entry()
        self.surname_entry.connect("changed", self._cb_query_changed)
        grid.attach(self.surname_entry, 1, 0, 1, 1)

        algorithm_label = Gtk.Label(label=_("Encoding system:"), halign=Gtk.Align.START)
        grid.attach(algorithm_label, 0, 1, 1, 1)
        self.algo_combo = Gtk.ComboBoxText()
        for algorithm_id, display_name in ALGORITHM_LABELS.items():
            self.algo_combo.append(algorithm_id, _(display_name))
        self.algo_combo.set_active_id(self._index.algorithm_id)
        self._update_algorithm_tooltip()
        self.algo_combo.connect("changed", self.cb_algorithm_changed)
        grid.attach(self.algo_combo, 1, 1, 1, 1)

        given_label = Gtk.Label(label=_("Given name contains:"), halign=Gtk.Align.START)
        grid.attach(given_label, 0, 2, 1, 1)
        self.given_entry = Gtk.Entry()
        self.given_entry.set_tooltip_text(
            _(
                "Optional. Narrows the right-hand list to people whose "
                "given name contains this text - not a phonetic match, "
                "just a plain filter on top of the surname match."
            )
        )
        self.given_entry.connect("changed", self._cb_query_changed)
        grid.attach(self.given_entry, 1, 2, 1, 1)

        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_spinner = Gtk.Spinner()
        self.status_label = Gtk.Label(halign=Gtk.Align.START)
        self.status_box.pack_start(self.status_spinner, False, False, 0)
        self.status_box.pack_start(self.status_label, False, False, 0)
        self.status_box.set_no_show_all(True)
        grid.attach(self.status_box, 0, 3, 2, 1)

        grid.attach(self._build_matches_box(), 0, 4, 2, 1)

        self.window.vbox.pack_start(grid, True, True, 0)
        self.window.add_button("_Close", Gtk.ResponseType.CLOSE)
        grid.show_all()

    def _build_matches_box(self) -> Gtk.Paned:
        """
        Build the two-column Matches display: surnames on the left,
        the people carrying whichever one is selected on the right -
        the same structure, drag-and-drop included, as the gramplet's
        own Matches columns (see :meth:`_cb_person_drag_data_get`).

        :returns: A :class:`Gtk.Paned` containing both columns.
        """
        self.surname_store = Gtk.ListStore(str, str)  # display, raw surname
        self.surname_view = Gtk.TreeView(model=self.surname_store)
        self.surname_view.set_headers_visible(False)
        self.surname_view.append_column(
            Gtk.TreeViewColumn(_("Surname"), Gtk.CellRendererText(), text=0)
        )
        self.surname_view.get_selection().connect("changed", self._cb_surname_selected)
        surname_scrolled = Gtk.ScrolledWindow()
        surname_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        surname_scrolled.set_hexpand(True)
        surname_scrolled.set_vexpand(True)
        surname_scrolled.add(self.surname_view)

        self.person_store = Gtk.ListStore(str, str)  # display, handle
        self.person_view = Gtk.TreeView(model=self.person_store)
        self.person_view.set_headers_visible(False)
        self.person_view.append_column(
            Gtk.TreeViewColumn(_("Person"), Gtk.CellRendererText(), text=0)
        )
        self.person_view.connect("row-activated", self._cb_person_activated)
        self.person_view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [DdTargets.PERSON_LINK.target()],
            Gdk.DragAction.COPY,
        )
        self.person_view.connect("drag-data-get", self._cb_person_drag_data_get)
        person_scrolled = Gtk.ScrolledWindow()
        person_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        person_scrolled.set_hexpand(True)
        person_scrolled.set_vexpand(True)
        person_scrolled.add(self.person_view)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.pack1(surname_scrolled, resize=True, shrink=True)
        paned.pack2(person_scrolled, resize=True, shrink=True)
        paned.set_position(160)
        return paned

    def _cb_person_drag_data_get(
        self,
        _tree_view: Gtk.TreeView,
        _context: Gdk.DragContext,
        sel_data: Gtk.SelectionData,
        _info: int,
        _time: int,
    ) -> None:
        """
        Supply the dragged person's handle when a row in the right
        Matches column is dragged - mirrors
        ``FuzzyMatchingGramplet.cb_person_drag_data_get`` exactly
        (see that method's own docstring for the payload shape and
        why it's accepted everywhere a dropped person already is,
        including a Photo Tagging row via
        ``PhotoTaggingGramplet.drag_data_received``).

        A no-op (``sel_data`` is left unset) if no row is currently
        selected.

        :param _tree_view: The right column's :class:`Gtk.TreeView`
            that emitted the signal.
        :param _context: The drag context.
        :param sel_data: The :class:`Gtk.SelectionData` to populate
            with the dragged person's handle.
        :param _info: The requested target's registered info id.
        :param _time: The event time.
        """
        model, tree_iter = self.person_view.get_selection().get_selected()
        if tree_iter is None:
            return
        handle = model[tree_iter][1]
        sel_data.set(
            DdTargets.PERSON_LINK.atom_drag_type,
            8,
            pickle.dumps((DdTargets.PERSON_LINK.drag_type, id(self), handle, 0)),
        )

    # -- ManagedWindow interface ------------------------------------------

    def build_menu_names(self, _obj) -> tuple:
        """
        Return this window's Gramps **Windows** menu label - see
        ``PluginManagerPlus.PluginStatus.build_menu_names`` for the
        reasoning behind a ``None`` submenu (a single leaf entry
        rather than a nested submenu).

        :param _obj: unused - required by the base class's call signature
        :returns: ``(TITLE, None)``
        """
        return (TITLE, None)

    def done(self, _obj, _response_id) -> None:
        """
        Disconnect this window's own database signal handlers, then
        close it. Connected to the dialog's own ``response`` signal,
        which fires for both the Close button and the window
        manager's own close control.

        Also clears this window from :data:`_active_window` (see the
        module-level singleton handling near :func:`show_fuzzy_lookup`
        at the bottom of this file), so the next call to that function
        opens a fresh window rather than trying to re-seed a destroyed
        one.

        :param _obj: unused (the dialog widget)
        :param _response_id: unused (the Gtk response id)
        """
        self._cleanup()
        self.close()
        _forget_active_window(self)

    def _cleanup(self) -> None:
        """
        Disconnect every signal this window connected outside of
        ``ManagedWindow``'s own bookkeeping - the database's
        person/event signals (see :meth:`_connect_db_signals`) and the
        ``database-changed`` watch (see :meth:`_cb_database_changed`)
        - and stop the background index build if one is still running.
        Idempotent, since :meth:`_cb_database_changed` also calls this
        before closing the window itself.
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

        if self._build_idle_id:
            GLib.source_remove(self._build_idle_id)
            self._build_idle_id = 0

    def _cb_database_changed(self, _db) -> None:
        """
        Close this window if the Family Tree changes while it's open,
        rather than trying to rebuild :attr:`_index` against a
        different database - this is meant to be a quick, occasional
        lookup tool, not something that needs to survive a Family Tree
        switch. The caller can always reopen it against the new
        database via :func:`show_fuzzy_lookup`.

        Also clears this window from :data:`_active_window` - see
        :meth:`done`.

        :param _db: unused (the newly-opened database)
        """
        self._cleanup()
        self.close()
        _forget_active_window(self)

    # -- index building ----------------------------------------------------

    def _connect_db_signals(self) -> None:
        """
        Connect this window's private :attr:`_index` to the
        database's own change signals, tracking each handler id in
        :attr:`_db_handlers` so :meth:`_cleanup` can disconnect them
        again on close - see that method's docstring for why this
        window (unlike ``FuzzyMatchingGramplet``) has to do this
        itself rather than relying on ``Gramplet.connect``.
        """
        db = self.dbstate.db
        for signal, handler in (
            ("person-add", self._cb_person_changed),
            ("person-update", self._cb_person_changed),
            ("person-delete", self._cb_person_deleted),
            ("person-rebuild", self._cb_person_rebuild),
            ("event-update", self._cb_event_changed),
        ):
            handler_id = db.connect(signal, handler)
            self._db_handlers.append((db, handler_id))

    def cb_algorithm_changed(self, _combo) -> None:
        """
        Switch :attr:`_index` to the newly-selected Encoding system
        and rebuild it in the background - mirrors
        ``FuzzyMatchingGramplet.cb_algorithm_changed`` exactly, except
        this window has no shared index to worry about disturbing
        (see the class docstring): it just restarts its own build.

        Also remembers the choice at module level (see
        :data:`_last_algorithm_id`) so the *next* Fuzzy Match Lookup
        window opened this session - even after this one is fully
        closed - starts on the same Encoding system instead of
        resetting to Soundex.

        :param _combo: The Encoding system combo box that emitted the
            signal.
        """
        self._update_algorithm_tooltip()
        global _last_algorithm_id
        _last_algorithm_id = self._current_algorithm()
        self._index.algorithm_id = _last_algorithm_id
        self._start_build()

    def _current_algorithm(self) -> str:
        """
        Return the identifier of the currently-selected Encoding system.

        :returns: An id key from :data:`phonetic_codes.ALGORITHMS`.
        """
        algorithm_id = self.algo_combo.get_active_id()
        if algorithm_id is not None:
            return algorithm_id
        assert DEFAULT_ALGORITHM is not None, (
            "phonetic_codes registered no algorithms at all - see "
            "phonetic_codes._hardcoded_soundex"
        )
        return DEFAULT_ALGORITHM

    def _update_algorithm_tooltip(self) -> None:
        """
        Set the Encoding system dropdown's tooltip to the currently
        selected algorithm's :data:`phonetic_codes.ALGORITHM_DESCRIPTIONS`
        entry - see ``FuzzyMatchingGramplet._update_algorithm_tooltip``,
        which this mirrors exactly.
        """
        description = ALGORITHM_DESCRIPTIONS.get(self._current_algorithm())
        if description:
            self.algo_combo.set_tooltip_text(_(description))

    def _start_build(self) -> None:
        """Kick off a background (re)build of :attr:`_index`."""
        self.status_box.set_no_show_all(False)
        self.status_box.show_all()
        self.status_spinner.start()
        self.status_label.set_text(_("Indexing…"))
        self._build_generator = self._index.build()
        self._build_idle_id = GLib.idle_add(self._cb_build_step)

    def _cb_build_step(self) -> bool:
        """
        Advance :attr:`_build_generator` by one chunk. Connected via
        ``GLib.idle_add`` from :meth:`_start_build`; returning True
        keeps it scheduled, False (on completion) stops it.

        :returns: True to be called again, False once the build has
            finished.
        """
        try:
            next(self._build_generator)
            return True
        except StopIteration:
            self._build_idle_id = 0
            self.status_spinner.stop()
            self.status_box.hide()
            self._refresh()
            return False

    def _cb_person_changed(self, handles) -> None:
        """Patch the index for added/edited people; see :meth:`_index`."""
        self._index.on_person_changed(handles)
        self._refresh()

    def _cb_person_deleted(self, handles) -> None:
        """Patch the index for deleted people; see :meth:`_index`."""
        self._index.on_person_deleted(handles)
        self._refresh()

    def _cb_person_rebuild(self) -> None:
        """Restart a full background rebuild after a batch operation."""
        self._index.on_rebuild()
        self._start_build()

    def _cb_event_changed(self, handles) -> None:
        """
        Refresh the display text of any currently-shown person whose
        birth or death event was just edited - see
        ``FuzzyMatchingGramplet.cb_event_changed`` for the full
        explanation of why ``event-update`` needs handling separately
        from ``person-update``. The actual row-matching and
        reformatting is
        :func:`fuzzy_match_display.refresh_matching_person_rows`,
        shared with that gramplet's identical need.

        :param handles: Handles of the events that were updated.
        """
        refresh_matching_person_rows(self.dbstate.db, self.person_store, handles)

    # -- query / display ----------------------------------------------------

    def set_query(self, surname: str, given_name: str = "") -> None:
        """
        Seed the Surname field, select whichever left-column row is
        an exact match for it (if any), and scroll/select the
        right-hand person list as close as possible to
        ``given_name``, then raise this window. This is what
        :func:`show_fuzzy_lookup` calls on an already-open window
        instead of creating a second one - see that function's
        docstring for the intended "surname/given name pulled from
        somewhere else" calling convention.

        The Given Name *field* is left blank throughout this call, not
        just while the surname row is being selected: filling it in
        with ``given_name`` afterward, for reference, was tried and
        reverted - it left that text sitting in the field as an active
        filter (see :meth:`_cb_surname_selected`) for whatever the
        person clicked next, silently emptying the right column again
        on a perfectly ordinary manual surname click if their actual
        given name didn't happen to contain it. Filtering by
        ``given_name`` at all here would have the same problem one
        step earlier: it could hide the very person this seeded a
        search for, if their recorded given name doesn't happen to
        contain the seeded one exactly (a nickname, an initial, a
        transcription difference from photo metadata, etc.) - showing
        everyone with the surname and scrolling to the closest match
        is more forgiving of exactly that mismatch, and leaving the
        field itself untouched keeps that forgiveness from expiring
        the moment this method returns.

        :param surname: Surname to look up and, if there's an exact
            match, select in the left column.
        :param given_name: Given name to scroll/select the closest
            match to in the right column, once populated - see above
            for why this is not applied as a filter, nor shown in the
            Given Name field, here.
        """
        self.surname_entry.set_text(surname)
        self.given_entry.set_text("")
        self._refresh()
        self._select_surname_row(surname, given_name)
        self.window.present()

    def _select_surname_row(self, surname: str, given_name: str = "") -> None:
        """
        Select ``surname``'s row in the left column if it's currently
        among the matches (a no-op otherwise - nothing to select),
        which populates the right column via the normal
        :meth:`_cb_surname_selected` selection-changed handler, then
        scrolls/selects that column as close as possible to
        ``given_name`` (see :meth:`_scroll_to_closest_given_name`).

        :param surname: The exact surname text to look for among the
            left column's current rows.
        :param given_name: Passed straight through to
            :meth:`_scroll_to_closest_given_name` once the right
            column is populated.
        """
        for row in self.surname_store:
            if row[1] == surname:
                self.surname_view.get_selection().select_path(row.path)
                self.surname_view.scroll_to_cell(row.path, None, True, 0.5, 0.0)
                self._scroll_to_closest_given_name(given_name)
                return

    def _scroll_to_closest_given_name(self, given_name: str) -> None:
        """
        Select and scroll the right column to whichever currently
        displayed row's given name sorts closest to ``given_name``,
        via the same locale-aware sort key :func:`fuzzy_match_display.
        person_sort_key` already sorts this column by - so "closest"
        matches how the list already reads top to bottom, not some
        separate notion of similarity. A no-op if ``given_name`` is
        blank or the right column is currently empty.

        "Closest" here means the first row at or after ``given_name``
        in that sort order (via :func:`bisect.bisect_left`), falling
        back to the last row if every name in the column sorts before
        it - a real nearest-neighbor pick would sometimes prefer the
        row just before that point instead, but this is close enough
        to be useful without adding a second string-distance metric on
        top of the sort key the column already uses.

        :param given_name: The given name to scroll/select closest to.
        """
        if not given_name:
            return
        db = self.dbstate.db
        candidates = []
        for row in self.person_store:
            try:
                person = db.get_person_from_handle(row[1])
            except HandleError:
                continue
            given = person.get_primary_name().get_first_name()
            candidates.append((glocale.sort_key(given), row.path))
        if not candidates:
            return

        candidates.sort(key=lambda item: item[0])
        target = glocale.sort_key(given_name)
        keys = [key for key, _path in candidates]
        index = min(bisect_left(keys, target), len(candidates) - 1)
        path = candidates[index][1]

        self.person_view.get_selection().select_path(path)
        self.person_view.scroll_to_cell(path, None, True, 0.5, 0.0)

    def _cb_query_changed(self, _entry) -> None:
        """Refresh the Matches columns as the Surname/Given Name fields change."""
        self._refresh()

    def _refresh(self) -> None:
        """
        Recompute the left Matches column from the current Surname
        field against :attr:`_index`. A no-op display-wise (empty
        list) before the first background build completes.
        """
        self.surname_store.clear()
        self.person_store.clear()
        surname = self.surname_entry.get_text()
        if not surname:
            return
        matches = self._index.find_matches(surname)
        for match_surname in sorted(matches, key=glocale.sort_key):
            count = len(matches[match_surname])
            display = _("{surname} ({count})").format(
                surname=match_surname, count=count
            )
            self.surname_store.append([display, match_surname])

    def _cb_surname_selected(self, selection) -> None:
        """
        Populate the right Matches column with every person who has
        the selected surname, filtered by the Given Name field if it
        is non-empty (see the module docstring - and
        :meth:`set_query`, which deliberately clears that field before
        selecting a row programmatically, for exactly the reason
        given there), sorted by given name (locale-aware), then birth
        date, then death date - see
        :func:`fuzzy_match_display.person_sort_key`.

        :param selection: The left column's :class:`Gtk.TreeSelection`.
        """
        model, tree_iter = selection.get_selected()
        self.person_store.clear()
        if tree_iter is None:
            return

        surname = model[tree_iter][1]
        given_filter = self.given_entry.get_text().strip().casefold()
        db = self.dbstate.db
        rows = []
        for handle in self._index.find_people(surname):
            try:
                person = db.get_person_from_handle(handle)
            except HandleError:
                continue
            if given_filter:
                given_name = person.get_primary_name().get_first_name()
                if given_filter not in given_name.casefold():
                    continue
            rows.append((person_sort_key(db, person), format_person(db, person), handle))
        rows.sort(key=lambda row: row[0])
        for _sort_key, display, handle in rows:
            self.person_store.append([display, handle])

    def _cb_person_activated(self, _tree_view, path, _column) -> None:
        """
        Open the standard Person editor for a double-clicked row.

        Passes ``[]``, not ``self.track``, as EditPerson's own track:
        this window registers itself with Gramps' window manager as a
        leaf, not a branch (see :meth:`build_menu_names`'s ``None``
        submenu - "a single leaf entry rather than a nested submenu"),
        and a leaf's own track is not a valid parent node for a further
        child window in that manager's tree - passing it crashes with
        ``AssertionError: Gwm: add_item: Incorrect track - Is parent
        not a leaf?`` the moment a person's edited from here.
        ``FuzzyMatchingGramplet.py``'s own equivalent code never hits
        this, since a Gramplet's own ``self.track`` is always ``[]``
        (Gramplets are never window-manager branches at all), not
        because it does anything different. ``[]`` also happens to be
        the right call regardless: it makes the Person editor its own
        top-level tracked window, so closing this lookup window later
        doesn't cascade into closing an editor someone opened from it.
        """
        tree_iter = self.person_store.get_iter(path)
        handle = self.person_store[tree_iter][1]
        person = self.dbstate.db.get_person_from_handle(handle)
        if person is not None:
            try:
                EditPerson(self.dbstate, self.uistate, [], person)
            except WindowActiveError:
                pass


# ---------------------------------------------------------------------------
#
# Public entry point for other plugins
#
# ---------------------------------------------------------------------------

#: The single currently-open :class:`FuzzyMatchLookupWindow`, or None.
#: A second call to :func:`show_fuzzy_lookup` while one is already open
#: re-seeds and raises that same window rather than opening another -
#: this is meant to be a quick, occasional lookup, not something a
#: caller would want several copies of stacked on screen.
_active_window = None


def show_fuzzy_lookup(dbstate, uistate, track=None, surname="", given_name=""):
    """
    Open the Fuzzy Match Lookup window seeded with ``surname`` -
    selecting it in the left column if it's an exact match among the
    phonetic results, which populates the right column with everyone
    who has it - and scroll/select that column as close as possible
    to ``given_name`` (see :meth:`FuzzyMatchLookupWindow.set_query`
    for exactly how, and why that's not the same as filtering by it).
    Calling this again while a window is already open re-seeds and
    raises that same window rather than opening a second one.

    :param dbstate: The current :class:`~gramps.gen.dbstate.DbState`.
    :param uistate: The current
        :class:`~gramps.gui.displaystate.DisplayState`.
    :param track: ``ManagedWindow`` track list from the caller, or
        None for a caller with no window of its own to nest this
        under.
    :param surname: Surname to look up and, if there's an exact
        match, select in the left column.
    :param given_name: Given name to scroll/select the closest match
        to in the right column, once populated - see
        :meth:`FuzzyMatchLookupWindow.set_query` for why this is not
        applied as a filter, and not shown in the Given Name field
        either, on this initial seed - a manual edit or selection in
        that field, from that point on, does filter normally.
    :returns: The (now open) :class:`FuzzyMatchLookupWindow`.
    """
    global _active_window
    if _active_window is not None:
        _active_window.set_query(surname, given_name)
        return _active_window

    try:
        _active_window = FuzzyMatchLookupWindow(
            dbstate, uistate, track or [], surname, given_name
        )
    except WindowActiveError:
        # Another ManagedWindow already claims this class/track combo
        # (a rare race, e.g. two callers in the same tick) - nothing
        # further to do; the window that won stays open as-is.
        pass
    return _active_window


def _forget_active_window(window) -> None:
    """
    Clear :data:`_active_window` once ``window`` closes, so the next
    :func:`show_fuzzy_lookup` call opens a fresh one instead of
    trying to re-seed a destroyed window. Called directly from
    :meth:`FuzzyMatchLookupWindow.done` and
    :meth:`FuzzyMatchLookupWindow._cb_database_changed`.

    :param window: The window that just closed.
    """
    global _active_window
    if _active_window is window:
        _active_window = None
