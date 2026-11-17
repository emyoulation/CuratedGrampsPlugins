#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Claude AI (wish coding by Brian McCullough)
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
The matching panel shared by the Fuzzy Matching gramplet and the Fuzzy
Match Lookup window: one "Surname, Given" field, the Encoding system
list, the Code(s) list, the busy row, and the two Matches columns.

Both front ends build a :class:`FuzzyMatchPanel` and add only what is
theirs: the gramplet adds the nearby-surname dropdown and the Select
Person button (and follows the active person); the lookup window adds
its Close bar and the "double-click picks this person" callback.

Everything else behaves the same in both:

* "Surname, Given" parsing (see :mod:`name_query`), with the lookup
  re-run a short moment after typing stops (:data:`QUERY_DELAY_MS`).
* A given part narrows the person column (plain text, see
  :func:`name_query.given_name_matches`); when it matches nobody,
  everyone is shown instead and the field turns the error color.
  The exact or closest given name is selected.
* No phonetic match: error color, and every surname in the tree is
  listed, scrolled to where the typed one would sort.
* "All <code>" rows grouping each code's surnames, with counts, and a
  total count beside "Matches:".
* Double-click a surname: a "Define filter" dialog for it.
* Drag a person out of the right column; drop one on the field.
* Typing while a list has the focus does not open GTK's own pop-up
  Find box (which covered the Close/Dock line at the bottom): the
  field is cleared and the typing goes there instead.

Imported by its bare module name, like this addon's other sibling
modules (see the import note in FuzzyMatchingGramplet.py).
"""

# ------------------------
# Python modules
# ------------------------
import contextlib
import logging
import pickle
import time
from bisect import bisect_left

# ------------------------
# Gtk modules
# ------------------------
from gi.repository import Gdk, GLib, Gtk

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import CUSTOM_FILTERS
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import HandleError
from gramps.gen.filters import FilterList, GenericFilterFactory
from gramps.gui.ddtargets import DdTargets
from gramps.gui.dialog import OkDialog
from gramps.gui.editors import EditFilter
from gramps.gui.makefilter import edit_filter_save

# ------------------------
# Gramps specific
# ------------------------
from fuzzy_match_display import format_person, person_sort_key, refresh_matching_person_rows
from fuzzy_match_index import FuzzyMatchIndex, person_surnames
from name_query import given_name_matches, parse_name_query, surname_words
from phonetic_codes import (
    ALGORITHM_DESCRIPTIONS,
    ALGORITHM_FILTER_RULES,
    ALGORITHM_LABELS,
    DEFAULT_ALGORITHM,
    connect_changed,
    get_encoder,
)

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)

#: Milliseconds after the last keystroke before the lookup re-runs.
QUERY_DELAY_MS = 350

#: Value for a phonetic filter rule's "Match in:" argument meaning every
#: name field (the Phonetic Filter Rules addon's ALL_TOKEN).
_MATCH_IN_ALL = "all"

#: Font weights for the person column's weight column.
WEIGHT_NORMAL = 400
WEIGHT_BOLD = 700

_HEADER_CSS = b"""
.fuzzy-matches-header {
    background-color: alpha(black, 0.08);
    padding: 3px 6px;
}
"""
_css_added = False


def _add_header_css() -> None:
    """Install the Matches header CSS once per screen."""
    global _css_added  # pylint: disable=global-statement
    if _css_added:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(_HEADER_CSS)
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _css_added = True


def primary_surname_text(person) -> str:
    """
    The one surname piece used to seed the field from a person: the
    primary surname, not the connector-joined ``get_surname()`` string,
    which would not phonetically match either piece of a compound
    surname under the non-Soundex systems.

    :param person: A Person.
    :returns: Their primary surname text, or "".
    """
    surname = person.get_primary_name().get_primary_surname()
    return surname.get_surname() if surname is not None else ""


# ------------------------------------------------------------
#
# FuzzyMatchPanel
#
# ------------------------------------------------------------
class FuzzyMatchPanel:
    """
    The shared matching widgets and their logic. Build one, add
    :attr:`widget` to a container, and connect the database signals to
    :meth:`cb_person_changed`, :meth:`cb_person_deleted`,
    :meth:`cb_person_rebuild` and :meth:`cb_event_changed`.

    Options (all keyword-only):

    :param algorithm_id: Encoding system to start with.
    :param suggestions: True for a dropdown on the field
        (:attr:`name_combo`, filled by the owner).
    :param extra_name_widgets: Widgets packed right of the field.
    :param request_build: ``callable(force)`` that (re)starts the
        background build by calling :meth:`build_steps`; None to use
        this panel's own idle driver (:meth:`start_build`).
    :param on_person_selected: ``callable(handle)`` for a selection in
        the person column made by the person (not by
        :meth:`focus_person`).
    :param on_person_activated: ``callable(person)`` for a double-click
        or Enter on a person.
    :param on_algorithm_changed: ``callable(algorithm_id)`` after the
        person picked another Encoding system.
    :param after_build: ``callable()`` run after each completed build.
    :param is_hosted: ``callable() -> bool``: docked in a view that
        shares its phonetic system (no selection allowed when the view
        uses a system this list lacks).
    :param preferred_algorithm: ``callable() -> str`` the system to
        keep when the list of systems is refilled.
    :param pane_fraction: Starting share of the surname column.
    """

    def __init__(
        self,
        dbstate,
        uistate,
        *,
        algorithm_id=None,
        suggestions=False,
        extra_name_widgets=(),
        request_build=None,
        on_person_selected=None,
        on_person_activated=None,
        on_algorithm_changed=None,
        after_build=None,
        is_hosted=None,
        preferred_algorithm=None,
        pane_fraction=1 / 3,
    ):
        self.dbstate = dbstate
        self.uistate = uistate
        self._request_build = request_build
        self._on_person_selected = on_person_selected
        self._on_person_activated = on_person_activated
        self._on_algorithm_changed = on_algorithm_changed
        self._after_build = after_build
        self._is_hosted = is_hosted or (lambda: False)
        self._preferred_algorithm = preferred_algorithm
        self._pane_fraction = pane_fraction
        self._pane_position_set = False
        self._query_timeout_id = 0
        self._build_idle_id = 0
        self._build_generator = None
        # (text, given_hint, handle) of the last seed, re-applied after
        # a build that was still running when it arrived
        self._pending = None
        self._given_hint = ""
        self._select_handle = None

        if algorithm_id not in ALGORITHM_LABELS:
            algorithm_id = DEFAULT_ALGORITHM
        self.index = FuzzyMatchIndex(dbstate.db, algorithm_id)
        self.name_combo = None
        self.widget = self._build_gui(suggestions, extra_name_widgets, algorithm_id)

    # -- GUI construction ------------------------------------------------

    def _build_gui(self, suggestions, extra_name_widgets, algorithm_id) -> Gtk.Grid:
        """Build the whole panel and return its top-level grid."""
        grid = Gtk.Grid()
        grid.set_border_width(6)
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)

        grid.attach(
            Gtk.Label(label=_("Surname, Given:"), halign=Gtk.Align.START), 0, 0, 1, 1
        )
        grid.attach(self._build_name_box(suggestions, extra_name_widgets), 1, 0, 1, 1)

        grid.attach(
            Gtk.Label(label=_("Encoding system:"), halign=Gtk.Align.START), 0, 1, 1, 1
        )
        self.algo_combo = Gtk.ComboBoxText()
        self._fill_algorithms()
        self.algo_combo.set_active_id(algorithm_id)
        self._algo_changed_id = self.algo_combo.connect(
            "changed", self.cb_algorithm_changed
        )
        connect_changed(self.cb_encoders_changed)
        grid.attach(self.algo_combo, 1, 1, 1, 1)
        self.update_algorithm_tooltip()

        grid.attach(Gtk.Label(label=_("Code(s):"), halign=Gtk.Align.START), 0, 2, 1, 1)
        self.code_store = Gtk.ListStore(str)
        self.code_view = Gtk.TreeView(model=self.code_store)
        self.code_view.set_headers_visible(False)
        self.code_view.append_column(
            Gtk.TreeViewColumn(_("Code"), Gtk.CellRendererText(), text=0)
        )
        self._redirect_typing(self.code_view)
        grid.attach(self.code_view, 1, 2, 1, 1)

        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_spinner = Gtk.Spinner()
        self.status_label = Gtk.Label(halign=Gtk.Align.START)
        self.status_box.pack_start(self.status_spinner, False, False, 0)
        self.status_box.pack_start(self.status_label, False, False, 0)
        self.status_box.set_no_show_all(True)
        grid.attach(self.status_box, 0, 3, 2, 1)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_hexpand(True)
        header.get_style_context().add_class("fuzzy-matches-header")
        header.pack_start(
            Gtk.Label(label=_("Matches:"), halign=Gtk.Align.START), False, False, 0
        )
        self.matches_count_label = Gtk.Label(label="", halign=Gtk.Align.START)
        header.pack_start(self.matches_count_label, False, False, 0)
        _add_header_css()
        grid.attach(header, 0, 4, 2, 1)

        grid.attach(self._build_matches_box(), 0, 5, 2, 1)
        grid.show_all()
        return grid

    def _build_name_box(self, suggestions, extra_name_widgets) -> Gtk.Box:
        """The "Surname, Given" field (a combo entry with suggestions)."""
        if suggestions:
            self.name_combo = Gtk.ComboBox.new_with_entry()
            self.name_combo.set_hexpand(True)
            self.name_entry = self.name_combo.get_child()
            field = self.name_combo
        else:
            self.name_entry = Gtk.Entry()
            self.name_entry.set_hexpand(True)
            field = self.name_entry
        self.name_entry.set_tooltip_text(
            _(
                "Type a surname, or \"Surname, Given\" to also narrow the "
                "people list to that given name. Without a comma, all of "
                "the text is the surname."
            )
        )
        self.name_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear"
        )
        self.name_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear"))
        self.name_entry.connect("icon-press", self._cb_clear_icon_pressed)
        self._name_changed_id = self.name_entry.connect("changed", self.cb_name_changed)
        self.name_entry.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [DdTargets.PERSON_LINK.target()],
            Gdk.DragAction.COPY,
        )
        self.name_entry.connect("drag-data-received", self.cb_name_drag_data_received)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.pack_start(field, True, True, 0)
        for widget in extra_name_widgets:
            box.pack_start(widget, False, False, 0)
        return box

    def _build_matches_box(self) -> Gtk.Paned:
        """The two Matches columns: surnames left, people right."""
        # (display, raw surname, code); raw surname "" = an "All <code>" row
        self.surname_store = Gtk.TreeStore(str, str, str)
        self.surname_view = Gtk.TreeView(model=self.surname_store)
        self.surname_view.set_headers_visible(False)
        self.surname_view.append_column(
            Gtk.TreeViewColumn(_("Surname"), Gtk.CellRendererText(), text=0)
        )
        self._surname_sel_id = self.surname_view.get_selection().connect(
            "changed", self.cb_surname_selected
        )
        self.surname_view.connect("row-activated", self.cb_surname_activated)
        self._redirect_typing(self.surname_view)

        # (display, handle, font weight)
        self.person_store = Gtk.ListStore(str, str, int)
        self.person_view = Gtk.TreeView(model=self.person_store)
        self.person_view.set_headers_visible(False)
        self.person_view.append_column(
            Gtk.TreeViewColumn(_("Person"), Gtk.CellRendererText(), text=0, weight=2)
        )
        self._person_sel_id = self.person_view.get_selection().connect(
            "changed", self.cb_person_selected
        )
        self.person_view.connect("row-activated", self.cb_person_activated)
        self.person_view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [DdTargets.PERSON_LINK.target()],
            Gdk.DragAction.COPY,
        )
        self.person_view.connect("drag-data-get", self.cb_person_drag_data_get)
        self._redirect_typing(self.person_view)

        self.matches_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        for pack, view in (
            (self.matches_paned.pack1, self.surname_view),
            (self.matches_paned.pack2, self.person_view),
        ):
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_hexpand(True)
            scrolled.set_vexpand(True)
            scrolled.add(view)
            pack(scrolled, True, True)
        self.matches_paned.connect("size-allocate", self._cb_paned_size_allocate)
        return self.matches_paned

    def _cb_paned_size_allocate(self, paned, allocation) -> None:
        """Set the starting divider position once a real width is known."""
        if self._pane_position_set or allocation.width <= 1:
            return
        self._pane_position_set = True
        paned.set_position(round(allocation.width * self._pane_fraction))

    def get_pane_fraction(self):
        """The divider position as a share of the width, or None."""
        width = self.matches_paned.get_allocated_width()
        if width <= 1:
            return None
        return self.matches_paned.get_position() / width

    @staticmethod
    def _cb_clear_icon_pressed(entry, position, _event) -> None:
        """Empty the field when its edit-clear icon is clicked."""
        if position == Gtk.EntryIconPosition.SECONDARY:
            entry.set_text("")

    # -- typing in a list goes to the field --------------------------------

    def _redirect_typing(self, view: Gtk.TreeView) -> None:
        """
        Turn off GTK's pop-up Find box on ``view`` and send typing to the
        "Surname, Given" field instead (see :meth:`cb_list_key_press`).

        :param view: A list in this panel.
        """
        view.set_enable_search(False)
        view.connect("key-press-event", self.cb_list_key_press)

    def cb_list_key_press(self, _view, event) -> bool:
        """
        A printable key pressed in one of the lists: clear the field, put
        the focus there and type the character into it. Space, Enter,
        arrows and shortcut keys keep their list meaning.

        :param _view: The list that has the focus.
        :param event: The key event.
        :returns: True when the key was taken for the field.
        """
        if event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK):
            return False
        code = Gdk.keyval_to_unicode(event.keyval)
        if not code:
            return False
        char = chr(code)
        if not char.isprintable() or char.isspace():
            return False
        self.name_entry.set_text(char)
        self.name_entry.grab_focus_without_selecting()
        self.name_entry.set_position(-1)
        return True

    # -- Encoding system ----------------------------------------------------

    def _fill_algorithms(self) -> None:
        """(Re)fill the Encoding system list from the installed systems."""
        self.algo_combo.remove_all()
        for algorithm_id, display_name in ALGORITHM_LABELS.items():
            self.algo_combo.append(algorithm_id, _(display_name))

    def current_algorithm(self) -> str:
        """The selected Encoding system's id, or the default one."""
        algorithm_id = self.algo_combo.get_active_id()
        if algorithm_id is not None:
            return algorithm_id
        assert DEFAULT_ALGORITHM is not None, "no phonetic systems registered"
        return DEFAULT_ALGORITHM

    def select_algorithm(self, system_id) -> bool:
        """
        Select ``system_id`` without the "changed" handler. When this list
        does not offer it: no selection while hosted, else the default.

        :param system_id: The wanted system id.
        :returns: True if the selection changed.
        """
        target = system_id
        if target not in ALGORITHM_LABELS:
            target = None if self._is_hosted() else DEFAULT_ALGORITHM
        if self.algo_combo.get_active_id() == target:
            return False
        self.algo_combo.handler_block(self._algo_changed_id)
        if target is None:
            self.algo_combo.set_active(-1)
        else:
            self.algo_combo.set_active_id(target)
        self.algo_combo.handler_unblock(self._algo_changed_id)
        self.update_algorithm_tooltip()
        return True

    def update_algorithm_tooltip(self) -> None:
        """Show the selected system's description as the list's tooltip."""
        if self.algo_combo.get_active_id() is None and self._is_hosted():
            self.algo_combo.set_tooltip_text(
                _(
                    "The view uses a phonetic system that this list does not "
                    "offer (for example None). Matches here use %s. Choose a "
                    "system to use it here and in the view."
                )
                % _(ALGORITHM_LABELS.get(DEFAULT_ALGORITHM, DEFAULT_ALGORITHM))
            )
            return
        description = ALGORITHM_DESCRIPTIONS.get(self.current_algorithm())
        if description:
            self.algo_combo.set_tooltip_text(_(description))

    def cb_algorithm_changed(self, _combo) -> None:
        """The person picked another Encoding system: re-index."""
        self.update_algorithm_tooltip()
        if self._on_algorithm_changed is not None:
            self._on_algorithm_changed(self.current_algorithm())
        self.algorithm_changed()

    def algorithm_changed(self) -> None:
        """Re-index for the selected system (also for a host view's change)."""
        self.update_algorithm_tooltip()
        if self.dbstate.is_open():
            self.request_build(force=True)

    def cb_encoders_changed(self) -> None:
        """
        An encoder plugin was hidden or shown: refill the list, keeping the
        current choice if it is still offered, else re-index.
        """
        before = self.current_algorithm()
        wanted = self._preferred_algorithm() if self._preferred_algorithm else before
        self.algo_combo.handler_block(self._algo_changed_id)
        self._fill_algorithms()
        self.algo_combo.handler_unblock(self._algo_changed_id)
        self.select_algorithm(wanted)
        if self.current_algorithm() != before:
            if self._on_algorithm_changed is not None:
                self._on_algorithm_changed(self.current_algorithm())
            self.algorithm_changed()
        else:
            self.update_algorithm_tooltip()

    # -- index building ------------------------------------------------------

    def index_current(self) -> bool:
        """True when the index is built for the selected system."""
        return self.index.ready and self.index.algorithm_id == self.current_algorithm()

    @property
    def building(self) -> bool:
        """True while this panel's own idle driver is building."""
        return bool(self._build_idle_id)

    def reset_index(self) -> None:
        """
        Clear the display and drop the index for a newly-opened database
        (before anything selects a row, which would look up a handle of
        the previous database).
        """
        self.stop_build()
        self.clear_matches()
        self.code_store.clear()
        self.index = FuzzyMatchIndex(self.dbstate.db, self.current_algorithm())

    def request_build(self, force=False) -> None:
        """
        (Re)start the background build: through the owner's driver if it
        gave one, else this panel's own.

        :param force: Restart even if a build is running.
        """
        if self._request_build is not None:
            self._request_build(force)
        elif force or not self.building:
            self.start_build()

    def build_steps(self):
        """
        Generator that (re)builds the index in chunks, then refreshes the
        display; drive it from GLib idle time.
        """
        if not self.dbstate.is_open():
            return
        self.index.algorithm_id = self.current_algorithm()
        self._set_busy(True, "", 0, 0)
        yield from self.index.build(progress_callback=self._cb_index_progress)
        self._set_busy(False)
        self.refresh(apply_pending=True)
        if self._after_build is not None:
            self._after_build()

    def start_build(self) -> None:
        """Run :meth:`build_steps` from this panel's own idle driver."""
        self.stop_build()
        self._build_generator = self.build_steps()
        self._build_idle_id = GLib.idle_add(self._cb_build_step)

    def stop_build(self) -> None:
        """Stop this panel's own idle driver, if running."""
        if self._build_idle_id:
            GLib.source_remove(self._build_idle_id)
            self._build_idle_id = 0
        self._build_generator = None

    def _cb_build_step(self) -> bool:
        """One chunk of :meth:`build_steps`; False when done."""
        try:
            next(self._build_generator)
            return True
        except StopIteration:
            self._build_idle_id = 0
            self._build_generator = None
            return False

    def _cb_index_progress(self, phase: str, position: int, total: int) -> None:
        """Index build progress: update the busy row."""
        self._set_busy(True, _(phase), position, total)

    def _set_busy(self, busy, phase="", position=0, total=0) -> None:
        """Show (with progress text) or hide the busy row."""
        if not busy:
            self.status_spinner.stop()
            self.status_box.hide()
            return
        self.status_box.set_no_show_all(False)
        self.status_box.show_all()
        self.status_spinner.start()
        if total:
            text = _("Indexing {phase}… {done} / {total}").format(
                phase=phase, done=position, total=total
            )
        elif phase:
            text = _("Indexing {phase}…").format(phase=phase)
        else:
            text = _("Indexing…")
        self.status_label.set_text(text)

    def shutdown(self) -> None:
        """Stop timers and builds (the owner is closing)."""
        self.stop_build()
        if self._query_timeout_id:
            GLib.source_remove(self._query_timeout_id)
            self._query_timeout_id = 0

    # -- database signals -------------------------------------------------

    def cb_person_changed(self, handles) -> None:
        """person-add / person-update: patch the index, refresh if needed."""
        self._refresh_if_touched(self.index.on_person_changed(handles))

    def cb_person_deleted(self, handles) -> None:
        """person-delete: patch the index, refresh if needed."""
        self._refresh_if_touched(self.index.on_person_deleted(handles))

    def cb_person_rebuild(self) -> None:
        """person-rebuild (import, batch tools): full background rebuild."""
        if not self.dbstate.is_open():
            return
        self.index.on_rebuild()
        self.request_build(force=True)

    def cb_event_changed(self, handles) -> None:
        """event-update: refresh shown rows whose birth/death changed."""
        refresh_matching_person_rows(self.dbstate.db, self.person_store, handles)

    def _refresh_if_touched(self, touched) -> None:
        """Re-run the query after an edit that touched shown surnames."""
        if not touched or not self.index_current():
            return
        surname = self.selected_surname()
        self.refresh(keep_selection=True)
        if surname and surname in touched:
            self._reselect_surname(surname)

    # -- the query ----------------------------------------------------------

    def query_text(self) -> str:
        """The field's current text."""
        return self.name_entry.get_text()

    def set_query(self, text: str, given_hint: str = "", select_handle=None) -> None:
        """
        Put ``text`` in the field and run the lookup now (no typing delay).

        :param text: "Surname, Given" text.
        :param given_hint: A given name to select the closest match to
            without filtering by it (when ``text`` has no given part).
        :param select_handle: A person to select once shown.
        """
        self._pending = (text, given_hint, select_handle)
        self.name_entry.handler_block(self._name_changed_id)
        self.name_entry.set_text(text)
        self.name_entry.handler_unblock(self._name_changed_id)
        self.refresh(apply_pending=True)

    def cb_name_changed(self, _entry) -> None:
        """The field changed (typing): re-run the lookup after a pause."""
        self._pending = None
        if self._query_timeout_id:
            GLib.source_remove(self._query_timeout_id)
        self._query_timeout_id = GLib.timeout_add(QUERY_DELAY_MS, self._cb_query_timeout)

    def _cb_query_timeout(self) -> bool:
        """Typing paused: run the lookup."""
        self._query_timeout_id = 0
        self.refresh()
        return False

    def refresh(self, apply_pending=False, keep_selection=False) -> None:
        """
        Run the lookup for the field's text against the index.

        :param apply_pending: Apply the last :meth:`set_query` seed's
            given-name hint and person, if the text is still the seed.
        :param keep_selection: Keep the selected person selected if they
            are still shown (after a database edit).
        """
        if self._query_timeout_id:
            GLib.source_remove(self._query_timeout_id)
            self._query_timeout_id = 0
        previous_handle = self.selected_handle() if keep_selection else None
        given_hint, select_handle = "", None
        text = self.query_text()
        if apply_pending and self._pending and self._pending[0] == text:
            _text, given_hint, select_handle = self._pending

        if not self.index_current():
            self.code_store.clear()
            self.clear_matches()
            self.request_build(force=False)
            return

        surname, given = parse_name_query(text)
        self._given_hint = given_hint
        self._select_handle = select_handle or previous_handle
        self.clear_matches()
        self.code_store.clear()
        if not surname:
            self._set_error(False)
            return

        encode = get_encoder(self.current_algorithm())
        codes = set(encode(surname))
        groups = [(code, self.index.find_surnames_for_code(code)) for code in codes]
        if not any(names for _code, names in groups) and len(surname_words(surname)) > 1:
            # a compound surname is indexed per piece: try each word
            codes = set()
            for word in surname_words(surname):
                codes.update(encode(word))
            groups = [(code, self.index.find_surnames_for_code(code)) for code in codes]
        groups = sorted((group for group in groups if group[1]), key=lambda g: g[0])
        for code in sorted(codes):
            self.code_store.append([code])

        if not groups:
            self._set_error(True)
            with self._blocked(self.surname_view, self._surname_sel_id):
                self._show_all_surnames(surname)
            self.matches_count_label.set_text(_("({count})").format(count=0))
            return
        self._set_error(False)

        wanted = {word.casefold() for word in [surname] + surname_words(surname)}
        exact_path = None
        first_path = None
        total = set()
        with self._blocked(self.surname_view, self._surname_sel_id):
            for code, names in groups:
                handles = set()
                for name in names:
                    handles.update(self.index.find_people(name))
                total.update(handles)
                parent = self.surname_store.append(
                    None,
                    [_("All {code} ({count})").format(code=code, count=len(handles)), "", code],
                )
                if first_path is None:
                    first_path = self.surname_store.get_path(parent)
                for name in sorted(names, key=glocale.sort_key):
                    row = self.surname_store.append(
                        parent,
                        [
                            _("{surname} ({count})").format(
                                surname=name, count=len(self.index.find_people(name))
                            ),
                            name,
                            code,
                        ],
                    )
                    if exact_path is None and name.strip().casefold() in wanted:
                        exact_path = self.surname_store.get_path(row)
        self.surname_view.expand_all()
        self.matches_count_label.set_text(_("({count})").format(count=len(total)))

        path = exact_path or first_path
        # fills the person column (cb_surname_selected), which then
        # applies the given name / pending person
        self.surname_view.get_selection().select_path(path)
        self.surname_view.scroll_to_cell(path, None, True, 0.5, 0.0)

    def _show_all_surnames(self, surname: str) -> None:
        """No phonetic match: list every surname, scrolled near ``surname``."""
        people = self.index.surname_to_handles
        names = sorted((n for n, h in people.items() if h), key=glocale.sort_key)
        for name in names:
            self.surname_store.append(
                None,
                [_("{surname} ({count})").format(surname=name, count=len(people[name])), name, ""],
            )
        if names:
            keys = [glocale.sort_key(name) for name in names]
            index = min(bisect_left(keys, glocale.sort_key(surname)), len(keys) - 1)
            self.surname_view.scroll_to_cell(Gtk.TreePath(index), None, True, 0.5, 0.0)

    def _set_error(self, error: bool) -> None:
        """Show the field in the theme's error color, or normally."""
        context = self.name_entry.get_style_context()
        if error:
            context.add_class("error")
        else:
            context.remove_class("error")

    # -- surname column ----------------------------------------------------

    @staticmethod
    @contextlib.contextmanager
    def _blocked(view: Gtk.TreeView, handler_id: int):
        """Block a selection handler for the ``with`` block."""
        selection = view.get_selection()
        selection.handler_block(handler_id)
        try:
            yield
        finally:
            selection.handler_unblock(handler_id)

    def clear_matches(self) -> None:
        """Empty both Matches columns and the total count."""
        with self._blocked(self.surname_view, self._surname_sel_id), self._blocked(
            self.person_view, self._person_sel_id
        ):
            self.surname_store.clear()
            self.person_store.clear()
        self.matches_count_label.set_text("")

    def selected_surname(self):
        """Raw surname of the selected left row ("" for "All"), or None."""
        model, tree_iter = self.surname_view.get_selection().get_selected()
        return None if tree_iter is None else model[tree_iter][1]

    def iter_surname_rows(self):
        """Every row of the surname column, children included."""

        def walk(tree_iter):
            while tree_iter is not None:
                yield self.surname_store[tree_iter]
                yield from walk(self.surname_store.iter_children(tree_iter))
                tree_iter = self.surname_store.iter_next(tree_iter)

        yield from walk(self.surname_store.get_iter_first())

    def _reselect_surname(self, surname: str) -> None:
        """Select ``surname``'s row again, if it is still listed."""
        for row in self.iter_surname_rows():
            if row[1] == surname:
                self.surname_view.get_selection().select_path(row.path)
                return

    def cb_surname_selected(self, selection) -> None:
        """
        Fill the person column for the selected surname (or every surname
        of an "All <code>" row), sorted by given name, then dates. A given
        part in the field narrows it (everyone when it matches nobody).
        Then select, in order: a pending person, the exact or closest given
        name, the only person, or the previously selected person (bolding
        the nearest row when they are no longer listed).
        """
        previous_handle, previous_key = self._selected_person_info()
        model, tree_iter = selection.get_selected()
        _surname, given = parse_name_query(self.query_text())
        no_match = False
        with self._blocked(self.person_view, self._person_sel_id):
            self.person_store.clear()
            if tree_iter is None:
                return
            surname, code = model[tree_iter][1], model[tree_iter][2]
            names = [surname] if surname else self.index.find_surnames_for_code(code)
            db = self.dbstate.db
            rows = []  # (sort key, display, handle, first name, passes filter)
            for name in names:
                for handle in self.index.find_people(name):
                    try:
                        person = db.get_person_from_handle(handle)
                    except HandleError:
                        continue
                    if person is None:
                        continue
                    first = person.get_primary_name().get_first_name()
                    rows.append(
                        (
                            person_sort_key(db, person),
                            format_person(db, person),
                            handle,
                            first,
                            given_name_matches(given, first),
                        )
                    )
            rows.sort(key=lambda row: row[0])
            no_match = bool(given) and bool(rows) and not any(row[4] for row in rows)
            shown = [row for row in rows if row[4] or no_match]
            for row in shown:
                self.person_store.append([row[1], row[2], WEIGHT_NORMAL])
        if given:
            self._set_error(no_match)

        target = self._select_handle
        self._select_handle = None
        hint = given or self._given_hint
        if target is not None and any(row[2] == target for row in shown):
            self.select_person(target)
        elif hint:
            self._select_closest_given(hint, shown)
        elif len(shown) == 1:
            self.select_person(shown[0][2])
        elif previous_handle is not None:
            self._restore_selection(previous_handle, previous_key, shown)

    def _selected_person_info(self):
        """``(handle, sort key)`` of the selected person, or Nones."""
        handle = self.selected_handle()
        if handle is None:
            return None, None
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
        except HandleError:
            return handle, None
        if person is None:
            return handle, None
        return handle, person_sort_key(self.dbstate.db, person)

    def _restore_selection(self, handle, sort_key, rows) -> None:
        """
        Reselect ``handle`` if listed; otherwise bold (without selecting,
        which could change the active person) the row sorting nearest.
        """
        for row in self.person_store:
            if row[1] == handle:
                self.select_person(handle)
                return
        if sort_key is None or not rows:
            return
        keys = [row[0] for row in rows]
        index = min(bisect_left(keys, sort_key), len(rows) - 1)
        path = Gtk.TreePath(index)
        self.person_store[path][2] = WEIGHT_BOLD
        self.person_view.scroll_to_cell(path, None, True, 0.5, 0.0)

    def _select_closest_given(self, given: str, rows) -> None:
        """
        Select the shown person whose given name is ``given`` (ignoring
        case), else the first one sorting at or after it.
        """
        if not rows:
            return
        wanted = given.strip().casefold()
        for row in rows:
            if row[3].strip().casefold() == wanted:
                self.select_person(row[2])
                return
        ordered = sorted(rows, key=lambda row: glocale.sort_key(row[3]))
        keys = [glocale.sort_key(row[3]) for row in ordered]
        index = min(bisect_left(keys, glocale.sort_key(given)), len(ordered) - 1)
        self.select_person(ordered[index][2])

    def cb_surname_activated(self, _view, path, _column) -> None:
        """
        Double-click on a surname: open "Define filter" with a People
        filter for it under the selected Encoding system (saved only if the
        person clicks OK there).
        """
        surname = self.surname_store[self.surname_store.get_iter(path)][1]
        if not surname:
            return
        algorithm_id = self.current_algorithm()
        label = _(ALGORITHM_LABELS.get(algorithm_id, algorithm_id))
        rule_class = ALGORITHM_FILTER_RULES.get(algorithm_id)
        if rule_class is None:
            OkDialog(
                _("No filter available for {algorithm}").format(algorithm=label),
                _(
                    "This Encoding system does not have a matching People"
                    " filter rule yet, so a filter cannot be created from it."
                ),
                parent=self.widget.get_toplevel(),
            )
            return
        new_filter = GenericFilterFactory("Person")()
        new_filter.set_name(
            _("Fuzzy match: {surname} ({algorithm})").format(
                surname=surname, algorithm=label
            )
        )
        rule_args = [surname]
        if len(getattr(rule_class, "labels", ())) > 1:
            rule_args.append(_MATCH_IN_ALL)
        new_filter.add_rule(rule_class(rule_args))
        now = time.localtime()
        new_filter.set_comment(
            _("Created on %(year)4d/%(month)02d/%(day)02d by Fuzzy Matching gramplet")
            % {"year": now.tm_year, "month": now.tm_mon, "day": now.tm_mday}
        )
        filterdb = FilterList(CUSTOM_FILTERS)
        filterdb.load()
        # [] track: a top-level window (a lookup window's own track is a
        # leaf and cannot parent another window)
        EditFilter(
            "Person",
            self.dbstate,
            self.uistate,
            [],
            new_filter,
            filterdb,
            lambda: edit_filter_save(self.uistate, filterdb, "Person"),
        )

    # -- person column -------------------------------------------------------

    def selected_handle(self):
        """Handle of the selected person, or None."""
        model, tree_iter = self.person_view.get_selection().get_selected()
        return None if tree_iter is None else model[tree_iter][1]

    def select_person(self, handle, notify=True) -> bool:
        """
        Select and center ``handle`` in the person column.

        :param handle: A person handle.
        :param notify: False to select without telling the owner
            (``on_person_selected``).
        :returns: True if the person is listed.
        """
        for row in self.person_store:
            if row[1] == handle:
                selection = self.person_view.get_selection()
                if notify:
                    selection.select_path(row.path)
                else:
                    with self._blocked(self.person_view, self._person_sel_id):
                        selection.select_path(row.path)
                self.person_view.scroll_to_cell(row.path, None, True, 0.5, 0.0)
                return True
        return False

    def cb_person_selected(self, selection) -> None:
        """A person was selected: clear the "nearest" bold, tell the owner."""
        for row in self.person_store:
            if row[2] != WEIGHT_NORMAL:
                row[2] = WEIGHT_NORMAL
        model, tree_iter = selection.get_selected()
        if tree_iter is not None and self._on_person_selected is not None:
            self._on_person_selected(model[tree_iter][1])

    def cb_person_activated(self, _view, path, _column) -> None:
        """Double-click or Enter on a person: hand them to the owner."""
        handle = self.person_store[self.person_store.get_iter(path)][1]
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
        except HandleError:
            return
        if person is not None and self._on_person_activated is not None:
            self._on_person_activated(person)

    def cb_person_drag_data_get(self, _view, _context, sel_data, _info, _time) -> None:
        """Drag a person out as a standard Gramps person-link."""
        handle = self.selected_handle()
        if handle is None:
            return
        sel_data.set(
            DdTargets.PERSON_LINK.atom_drag_type,
            8,
            pickle.dumps((DdTargets.PERSON_LINK.drag_type, id(self), handle, 0)),
        )

    def cb_name_drag_data_received(
        self, _widget, _context, _x, _y, sel_data, _info, _time
    ) -> None:
        """A person dropped on the field: look up their surname, select them."""
        data = sel_data.get_data() if sel_data is not None else None
        if not data:
            return
        drag_type, _idval, handle, _val = pickle.loads(data)
        if drag_type != DdTargets.PERSON_LINK.drag_type:
            return
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
        except HandleError:
            return
        if person is not None:
            # deferred: the entry's own text drop runs after this handler
            GLib.idle_add(self._cb_show_person_idle, handle)

    def _cb_show_person_idle(self, handle) -> bool:
        """Idle part of a drop (see :meth:`cb_name_drag_data_received`)."""
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
        except HandleError:
            return False
        if person is not None:
            self.show_person(person)
        return False

    def show_person(self, person) -> None:
        """
        Look up ``person``'s primary surname and select them.

        :param person: A Person.
        """
        self.set_query(primary_surname_text(person), select_handle=person.get_handle())

    def focus_person(self, person) -> None:
        """
        Select and center ``person`` in both columns if one of their
        surname pieces is listed, without telling the owner (used to
        follow the active person).

        :param person: A Person, or None.
        """
        if person is None:
            return
        pieces = person_surnames(person)
        handle = person.get_handle()
        if self.select_person(handle, notify=False):
            return  # already shown: keep the surname row as it is
        for row in self.iter_surname_rows():
            if row[1] in pieces:
                self._select_handle = None
                with self._blocked(self.person_view, self._person_sel_id):
                    self.surname_view.get_selection().select_path(row.path)
                self.surname_view.scroll_to_cell(row.path, None, True, 0.5, 0.0)
                self.select_person(handle, notify=False)
                return
