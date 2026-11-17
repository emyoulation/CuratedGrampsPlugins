#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2025       Fuzzy Matching Gramplet contributors
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
Tools/Utilities/Fuzzy Matching.

This gramplet is a fork of the core "SoundEx" gramplet
(``gramps/plugins/gramplet/soundgen.py``). It was created because the
original gramplet does not scale to large family trees: on every
database load it called ``dbstate.db.iter_people()`` and built the
unique-surname list with a ``list`` plus an ``in`` membership test,
which is an O(n^2) operation over the number of people in the tree.
For a tree with tens of thousands of people, that membership test
alone can take the gramplet several seconds to load, and it is redone
in full every time a different Family Tree is opened.

This fork fixes that by:

* Using :meth:`gramps.gen.db.base.DbReadBase.get_surname_list`, which
  the database backend already maintains, instead of scanning every
  person and deduplicating by hand. This is O(number of unique
  surnames) rather than O(number of people).
* Computing each surname's phonetic code exactly once per database
  load (or algorithm change) and caching the result in a code ->
  surnames dictionary, so that typing in the name field is an O(1)
  dictionary lookup instead of a fresh scan.
* Reading the active person via :meth:`get_active_object` (an O(1)
  handle lookup) instead of iterating every person to find one to seed
  the display with.
* Doing that indexing work as a generator driven by the Gramplet
  framework's own :meth:`update`/:meth:`main` background-idle
  machinery (see :mod:`gramps.gen.plug._gramplet`), instead of
  synchronously in :meth:`db_changed`, so it cannot freeze the GTK main
  loop, and showing a spinner and progress count while it runs so the
  user has feedback that something is happening.
* Using a plain text entry for the name field instead of a
  :class:`Gtk.ComboBox` populated with every surname in the tree via
  :func:`gramps.gui.autocomp.fill_combo`. That combo's
  ``set_model()`` call turned out to be the dominant cost on a large
  tree - see "Why the gramplet used to freeze the whole
  application" below - and a browsable dropdown of tens of thousands
  of surnames was never useful on a tree of that size anyway; the
  phonetic-match list below the entry already does the job an exact
  autocomplete dropdown would have.

On top of the performance fix, the gramplet now shows every surname in
the Family Tree that phonetically matches the entered name, rather
than only the raw code for a single typed name, which is the more
useful "matching" workflow for spotting spelling variants of the same
family.

The left Matches column also shows how many people share each
matching surname, e.g. "Smith (12)", rather than the surname alone -
see :meth:`FuzzyMatchingGramplet.cb_name_changed`.

Rows in the right Matches column can be dragged out as a standard
Gramps "person-link" (:class:`gramps.gui.ddtargets.DdTargets`), the
same drag type used throughout Gramps, so a match found here can be
dropped onto any other view, gramplet, or editor field that already
accepts a dragged person - see
:meth:`FuzzyMatchingGramplet.cb_person_drag_data_get`. The Surname
entry itself accepts that same drag type as a drop target: dropping a
person there sets the field to that person's surname - see
:meth:`FuzzyMatchingGramplet.cb_name_drag_data_received`.

Why the gramplet used to freeze the whole application
-------------------------------------------------------

An earlier version of this gramplet built its name-entry autocomplete
with :func:`gramps.gui.autocomp.fill_combo`, which attaches a
:class:`Gtk.ListStore` holding every unique surname to a
:class:`Gtk.ComboBox` via ``combo.set_model(store)``. Measured directly
(``Gtk.ComboBox.new_with_entry()``, GTK 3.24, off-screen/Xvfb, so this
is a floor, not a ceiling):

======================  ==================
Unique surnames         ``set_model()`` time
======================  ==================
5,000                   0.25 s
15,000                  1.2 s
30,000                  5.3 s
60,000                  31.6 s
======================  ==================

That is roughly quadratic in the number of rows, and it runs
synchronously on the GTK main loop with no progress feedback, which is
exactly what "completely unresponsive... no indication what is
happening" looks like from the outside. By contrast, the actual
phonetic-code indexing loop over the same 60,000 unique surnames takes
about 0.2 seconds in pure Python. The combo's model attachment, not
the gramplet's own indexing logic, was the bottleneck.

Note on imports: Gramps loads a gramplet's main module with a plain
``__import__()`` after inserting the addon's own folder onto
``sys.path`` (see ``gramps.gen.plug._manager.PluginManager.import_plugin``),
not as part of a package. A package-relative import such as
``from .phonetic_codes import ...`` therefore fails at runtime with
"attempted relative import with no known parent package", even though
it looks correct and imports fine under some test runners. The sibling
module is imported by its bare name below instead, exactly as it will
be found once the addon folder is on ``sys.path``.

Where the actual logic lives
-----------------------------

The phonetic index described above (surname <-> code, surname <->
person handles, and the incremental add/update/delete/rebuild patching
that keeps it current without a full rescan on every edit) is not
implemented in this file: it lives in
:class:`fuzzy_match_index.FuzzyMatchIndex`, a plain-Python, GTK-free
class shared with :mod:`FuzzyMatchLookupWindow` (this addon's
standalone "does someone like this already exist" popup, meant to be
called from other plugins - see that module's own docstring).
Similarly, formatting a person for display and refreshing a displayed
row after a birth/death event edit both live in
:mod:`fuzzy_match_display`, also shared with that same window. 
The widgets themselves - the "Surname, Given" field, the Encoding
system list, the Code(s) list and both Matches columns - and their
behavior live in :class:`fuzzy_match_panel.FuzzyMatchPanel`, which the
Fuzzy Match Lookup window builds too, so the two cannot drift apart.
This gramplet adds only what is its own: the nearby-surname dropdown,
the Select Person button, following the active person, following a
host view's phonetic system, and remembering the Matches divider.
"""

# ------------------------
# Python modules
# ------------------------
import logging
import weakref
from typing import List, Set

# ------------------------
# Gtk modules
# ------------------------
from gi.repository import Gtk

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config as global_config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import WindowActiveError
from gramps.gen.plug import Gramplet
from gramps.gui.autocomp import fill_combo
from gramps.gui.editors import EditPerson
from gramps.gui.selectors import SelectorFactory
from gramps.gui.widgets import SimpleButton

# ------------------------
# Gramps specific
# ------------------------
# Bare, top-level imports of this addon's own sibling modules - see the
# module docstring above for why not "from .fuzzy_match_panel import".
from fuzzy_match_index import person_surnames
from fuzzy_match_panel import FuzzyMatchPanel, primary_surname_text

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)

#: How many steps of parent/child/spouse traversal from the active
#: person to include when suggesting nearby surnames in the name
#: field's dropdown - a small set bounded by family structure, not tree
#: size (see "Why the gramplet used to freeze the whole application"
#: above). The Select Person button next to the field reaches everyone.
NEARBY_DEGREES = 2

#: Starting split of the Matches paned: 1/3 to the surname column.
DEFAULT_MATCHES_PANE_FRACTION = 1 / 3

#: This addon's own identity, matching the "id=" registered in
#: FuzzyMatchingGramplet.gpr.py; recorded in the .ini's [meta] block.
PLUGIN_ID = "Fuzzy Matching"

#: Schema version for the keys registered below.
SCHEMA_VERSION = "1"

#: Persistent settings in this addon's own folder (use_plugins_path=False).
#: The [meta] keys get an empty default and are then set, because
#: ConfigManager.save() comments out a key still at its default.
CONFIG = global_config.register_manager("FuzzyMatchingGramplet", use_plugins_path=False)
CONFIG.register("meta.plugin_id", "")
CONFIG.register("meta.schema_version", "")
CONFIG.register("gramplet.matches_pane_position", DEFAULT_MATCHES_PANE_FRACTION)
CONFIG.init()
CONFIG.set("meta.plugin_id", PLUGIN_ID)
CONFIG.set("meta.schema_version", SCHEMA_VERSION)
CONFIG.save()


# ------------------------------------------------------------
#
# FuzzyMatchingGramplet
#
# ------------------------------------------------------------
class FuzzyMatchingGramplet(Gramplet):
    """
    Shows which surnames in the Family Tree phonetically match a typed
    "Surname, Given", and who carries them, using a cached per-database
    index built in the background by :meth:`main` (the Gramplet
    framework's idle-driven generator hook), so the gramplet stays
    responsive on large trees. The widgets and matching behavior are the
    shared :class:`fuzzy_match_panel.FuzzyMatchPanel`.
    """

    def init(self) -> None:
        """Build the widget tree and wire up the initial signal handlers."""
        # Weak reference to a host view sharing its phonetic system (the
        # Fuzzy Grouping view); None when docked anywhere else.
        self._host_view_ref = None

        self.browse_person_button = SimpleButton(
            "gtk-index", self.cb_browse_person_clicked
        )
        self.browse_person_button.set_relief(Gtk.ReliefStyle.NORMAL)
        self.browse_person_button.set_tooltip_text(
            _("Select a person from the whole Family Tree")
        )
        self.panel = FuzzyMatchPanel(
            self.dbstate,
            self.uistate,
            suggestions=True,
            extra_name_widgets=(self.browse_person_button,),
            request_build=self.cb_request_build,
            on_person_selected=self.cb_person_selected,
            on_person_activated=self.cb_person_activated,
            on_algorithm_changed=self.cb_algorithm_changed,
            after_build=self.cb_after_build,
            is_hosted=lambda: self._host_view() is not None,
            preferred_algorithm=self._preferred_algorithm,
            pane_fraction=CONFIG.get("gramplet.matches_pane_position"),
        )
        self.gui.WIDGET = self.panel.widget
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)

        # Docked in a view that shares its phonetic system? Follow it both
        # ways. Duck-typed (PHONETIC_SYSTEM_SYNC protocol): no import.
        view = getattr(self.gui, "view", None)
        if getattr(view, "PHONETIC_SYSTEM_SYNC", 0) >= 1:
            self._host_view_ref = weakref.ref(view)
            view.connect_phonetic_system(self.cb_host_system_changed)
            # no re-index here: the normal first update() indexes with
            # whatever the list shows
            self.panel.select_algorithm(view.phonetic_system_id())

    def _host_view(self):
        """The host view followed for the phonetic system, or None."""
        return self._host_view_ref() if self._host_view_ref else None

    def _preferred_algorithm(self) -> str:
        """The system to keep when the list of systems is refilled."""
        host = self._host_view()
        if host is not None:
            return host.phonetic_system_id()
        return self.panel.current_algorithm()

    def cb_host_system_changed(self, system_id: str) -> None:
        """
        The host view changed phonetic system: select the same one here
        and re-index, without sending the change back to the view.

        :param system_id: The id of the system the view now uses.
        """
        if self.panel.select_algorithm(system_id):
            self.panel.algorithm_changed()

    def cb_algorithm_changed(self, algorithm_id: str) -> None:
        """
        The person picked another Encoding system here: tell a host view.

        :param algorithm_id: The newly selected system.
        """
        host = self._host_view()
        if host is not None:
            host.set_phonetic_system(algorithm_id, source=self)

    def on_load(self) -> None:
        """Nothing to load: the divider fraction was read in :meth:`init`."""

    def on_save(self) -> None:
        """Remember the Matches divider position (as a share of the width)."""
        fraction = self.panel.get_pane_fraction()
        if fraction is not None:
            CONFIG.set("gramplet.matches_pane_position", fraction)
        CONFIG.save()

    # -- background index ------------------------------------------------

    def cb_request_build(self, force: bool) -> None:
        """
        The panel needs its index (re)built: run :meth:`main` through the
        Gramplet framework's own idle machinery.

        :param force: Restart even if a build is already running.
        """
        if force or not self._idle_id:
            self.update()

    def main(self):
        """
        Gramplet framework generator hook: (re)build the shared index in
        the background (see :meth:`fuzzy_match_panel.FuzzyMatchPanel.build_steps`).
        """
        if not self.dbstate.is_open():
            return
        yield from self.panel.build_steps()

    def cb_after_build(self) -> None:
        """A build finished: select the active person if shown."""
        self.panel.focus_person(self.get_active_object("Person"))

    # -- database and active person ------------------------------------

    def db_changed(self) -> None:
        """
        A database was opened: drop the old index first (a stale handle
        from the previous tree would raise HandleError when a row is
        selected), reconnect the database signals, and seed the field from
        the active person. :meth:`main` then rebuilds the index in the
        background.
        """
        if not self.dbstate.is_open():
            return
        self.panel.reset_index()
        # dbstate.db is a new object each time, so connect afresh
        self.connect(self.dbstate.db, "person-add", self.panel.cb_person_changed)
        self.connect(self.dbstate.db, "person-update", self.panel.cb_person_changed)
        self.connect(self.dbstate.db, "person-delete", self.panel.cb_person_deleted)
        self.connect(self.dbstate.db, "person-rebuild", self.panel.cb_person_rebuild)
        self.connect(self.dbstate.db, "event-update", self.panel.cb_event_changed)

        person = self.get_active_object("Person")
        self._refresh_nearby_combo(person)
        self.panel.set_query(primary_surname_text(person) if person else "")

    def active_changed(self, handle: str) -> None:
        """
        Follow the active person: unless they are already selected here
        (this gramplet just made them active, perhaps from a typed given
        name - rewriting the field would throw that typing away), seed the
        field with their surname and select them.

        :param handle: The newly active person's handle.
        """
        person = self.get_active_object("Person")
        self._refresh_nearby_combo(person)
        if person is None:
            return
        if handle and handle == self.panel.selected_handle():
            return
        pieces = person_surnames(person)
        shown = any(row[1] in pieces for row in self.panel.iter_surname_rows())
        if not shown:
            self.panel.set_query(primary_surname_text(person))
        self.panel.focus_person(person)

    def cb_person_selected(self, handle: str) -> None:
        """
        A person selected here becomes the active person (only when it is
        a different person: set_active re-emits active-changed even for
        the same handle).

        :param handle: The selected person's handle.
        """
        if handle != self.uistate.get_active("Person"):
            self.uistate.set_active(handle, "Person")

    def cb_person_activated(self, person) -> None:
        """
        Double-click or Enter on a person: open the Person editor.

        :param person: The activated Person.
        """
        try:
            EditPerson(self.dbstate, self.uistate, self.track, person)
        except WindowActiveError:
            pass

    def cb_browse_person_clicked(self, _button: Gtk.Button) -> None:
        """
        Open the standard Person selector for anyone in the tree, then
        look up their surname and select them.

        :param _button: The "gtk-index" browse button.
        """
        selector = SelectorFactory("Person")(
            self.dbstate, self.uistate, self.track, title=_("Select a person")
        )
        person = selector.run()
        if person:
            self.panel.show_person(person)

    # -- nearby surnames dropdown -----------------------------------------

    def _refresh_nearby_combo(self, active_person) -> None:
        """
        Fill the field's dropdown with every surname piece carried by
        people within :data:`NEARBY_DEGREES` of ``active_person`` - cheap
        regardless of tree size (bounded by family structure).

        :param active_person: The active Person, or None.
        """
        if active_person is None:
            fill_combo(self.panel.name_combo, [])
            return
        db = self.dbstate.db
        handles = self._degrees_of_separation(
            db, active_person.get_handle(), NEARBY_DEGREES
        )
        surnames = set()
        for handle in handles:
            person = db.get_person_from_handle(handle)
            if person is not None:
                surnames.update(person_surnames(person))
        surnames.discard("")
        fill_combo(self.panel.name_combo, sorted(surnames, key=glocale.sort_key))

    @classmethod
    def _degrees_of_separation(cls, db, root_handle: str, degrees: int) -> Set[str]:
        """
        Return the set of person handles within ``degrees`` of
        ``root_handle``.

        This follows the same three-stage approach as the
        ``DegreesOfSeparationHome`` filter rule (a published Gramps
        addon: ``degreesofseparationhome.py``), rooted at the given
        person instead of the Home Person, and always including
        partners and all parent-relationship types (that rule's
        ``InclPartner``/``InclAllParents`` options, simplified away
        here since this is a convenience shortlist rather than a
        user-configurable filter):

        1. Walk upward from the root person, generation by generation,
           collecting ancestors up to ``degrees`` generations back.
        2. From *each* ancestor found (including the root), walk back
           downward up to ``degrees`` generations, collecting
           descendants. Doing this from every ancestor - not just the
           root - is what pulls in siblings, cousins, aunts and uncles,
           not just the direct ancestor/descendant line.
        3. Add the partners/spouses of everyone collected so far.

        :param db: The active database.
        :param root_handle: Handle of the person to measure degrees of
            separation from.
        :param degrees: How many generations to walk in each direction.
        :returns: A set of person handles within range.
        """
        ancestors = cls._collect_ancestors(db, root_handle, degrees)

        persons: set[str] = set()
        for ancestor_handle in ancestors:
            cls._collect_descendants(db, ancestor_handle, 0, degrees, persons)

        cls._add_partners(db, persons)
        return persons

    @staticmethod
    def _collect_ancestors(db, root_handle: str, degrees: int) -> List[str]:
        """
        Return ``root_handle`` and its ancestors up to ``degrees``
        generations back, adapted from
        ``DegreesOfSeparationHome.__get_ancestors``.

        :param db: The active database.
        :param root_handle: Handle of the person to walk upward from.
        :param degrees: How many generations of ancestors to include.
        :returns: A list of person handles, root first.
        """
        ancestors: list[str] = []
        queue = [(root_handle, 1)]
        while queue:
            handle, gen = queue.pop(0)
            if handle in ancestors:
                continue
            ancestors.append(handle)
            gen += 1
            if gen > degrees:
                continue
            person = db.get_person_from_handle(handle)
            if person is None:
                continue
            for family_handle in person.get_parent_family_handle_list():
                family = db.get_family_from_handle(family_handle)
                if family is None:
                    continue
                father_handle = family.get_father_handle()
                mother_handle = family.get_mother_handle()
                if father_handle:
                    queue.append((father_handle, gen))
                if mother_handle:
                    queue.append((mother_handle, gen))
        return ancestors

    @classmethod
    def _collect_descendants(
        cls,
        db,
        root_handle: str,
        gen: int,
        degrees: int,
        persons: Set[str],
    ) -> None:
        """
        Add ``root_handle`` and its descendants up to ``degrees``
        generations down into ``persons``, in place, adapted from
        ``DegreesOfSeparationHome.__get_desc``.

        :param db: The active database.
        :param root_handle: Handle of the person to walk downward from.
        :param gen: The current generation depth, relative to wherever
            this walk started (0 on the initial call).
        :param degrees: How many generations of descendants to include.
        :param persons: The set of handles collected so far; updated
            in place so repeated calls (once per ancestor) share one
            "already visited" set instead of re-walking shared
            descendants.
        """
        if root_handle in persons:
            return
        persons.add(root_handle)
        if gen >= degrees:
            return

        person = db.get_person_from_handle(root_handle)
        if person is None:
            return
        for family_handle in person.get_family_handle_list():
            family = db.get_family_from_handle(family_handle)
            if family is None:
                continue
            for child_ref in family.get_child_ref_list():
                cls._collect_descendants(db, child_ref.ref, gen + 1, degrees, persons)

    @staticmethod
    def _add_partners(db, persons: Set[str]) -> None:
        """
        Add the partners/spouses of everyone in ``persons``, in place,
        adapted from ``DegreesOfSeparationHome.__get_partners``.

        :param db: The active database.
        :param persons: The set of handles collected so far; updated in
            place with the additional partner handles.
        """
        for handle in list(persons):
            person = db.get_person_from_handle(handle)
            if person is None:
                continue
            for family_handle in person.get_family_handle_list():
                family = db.get_family_from_handle(family_handle)
                if family is None:
                    continue
                father_handle = family.get_father_handle()
                mother_handle = family.get_mother_handle()
                if father_handle:
                    persons.add(father_handle)
                if mother_handle:
                    persons.add(mother_handle)
