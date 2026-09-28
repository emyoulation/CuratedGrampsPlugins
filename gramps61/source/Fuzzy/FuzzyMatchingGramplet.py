#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2025       Fuzzy Matching Gramplet contributors
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
* Using a plain :class:`Gtk.Entry` for the name field instead of a
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
:mod:`fuzzy_match_display`, also shared with that same window. This
gramplet is left holding only the GTK/Gramplet-framework side of
things: building widgets, driving the shared index's background build
via :meth:`main`, and wiring the database's signals to it.
"""

# ------------------------
# Python modules
# ------------------------
import contextlib
import logging
import pickle
import time
from bisect import bisect_left
from typing import List, Set

# Field reports (Gramps 5.2.5 / Python 3.6.9) confirm this addon needs
# to actually import successfully on Python 3.6, not just parse: see
# the equivalent, longer comment in phonetic_codes.py for why a bare
# `set[str]`/`list[str]` annotation only works on Python 3.9+, why
# `from __future__ import annotations` does not exist before 3.7 and
# so fails even earlier, and why `typing.Set`/`typing.List` were used
# for the handful of function signatures below instead. Every other
# annotation in this file (`self.attr: ...`, and local variables
# inside a function body) is never evaluated at runtime by any Python
# 3 version and needed no change.

# ------------------------
# Gtk modules
# ------------------------
from gi.repository import Gdk, Gtk

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config as global_config
from gramps.gen.const import CUSTOM_FILTERS
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import HandleError
from gramps.gen.filters import FilterList, GenericFilterFactory
from gramps.gen.plug import Gramplet
from gramps.gui.autocomp import fill_combo
from gramps.gui.ddtargets import DdTargets
from gramps.gui.dialog import OkDialog
from gramps.gui.editors import EditFilter, EditPerson
from gramps.gui.makefilter import edit_filter_save
from gramps.gui.selectors import SelectorFactory
from gramps.gui.widgets import SimpleButton

# ------------------------
# Gramps specific
# ------------------------
# See the module docstring above for why this is a bare, top-level
# import rather than "from .phonetic_codes import ...". The same
# reasoning applies to fuzzy_match_index/fuzzy_match_display below -
# this addon's own sibling modules, factored out so the phonetic
# indexing and person-display formatting each live in exactly one
# place, shared with FuzzyMatchLookupWindow.py.
from phonetic_codes import (
    ALGORITHM_DESCRIPTIONS,
    ALGORITHM_FILTER_RULES,
    ALGORITHM_LABELS,
    ALGORITHMS,
    DEFAULT_ALGORITHM,
)
from fuzzy_match_display import format_person, person_sort_key, refresh_matching_person_rows
from fuzzy_match_index import FuzzyMatchIndex, person_surnames

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)

#: Value for a phonetic filter rule's "Match in:" argument meaning
#: "every name field, in every name" - understood by the Phonetic
#: Filter Rules addon's ``phonetic_name_parts.ALL_TOKEN``. Spelled out
#: here rather than imported because that module lives in the
#: separately installed FuzzyRules addon, not in this one's folder. A
#: rule that predates the token ignores it and uses its own default.
_MATCH_IN_ALL = "all"

#: CSS for the "Matches:" row's header bar - a darker background band
#: giving a clear visual break between the encoding-system controls
#: above and the two Matches columns below, rather than relying on
#: row spacing alone. A translucent black overlay rather than a fixed
#: color, so it darkens whatever is underneath by a consistent amount
#: regardless of the active GTK theme (light or dark), instead of
#: picking one absolute color that could clash with either.
_MATCHES_HEADER_CSS = b"""
.fuzzy-matches-header {
    background-color: alpha(black, 0.08);
    padding: 3px 6px;
}
"""

#: How many steps of parent/child/spouse traversal from the active
#: person to include when suggesting nearby surnames in the name
#: field's dropdown. This set is small and bounded by family
#: structure, not tree size, regardless of how large the Family Tree
#: is, unlike the full surname list (see "Why the gramplet used to
#: freeze the whole application" above) - it exists purely as a
#: convenience shortlist, not as a way to reach every person in the
#: tree, which is what the "gtk-index" browse button next to the name
#: field is for.
NEARBY_DEGREES = 2

#: Starting split of the Matches paned: 1/3 to the surname column, 2/3
#: to the person column, rather than an even 50/50 - surnames are
#: single words and the person column needs the room for names, life
#: spans, and Gramps IDs.
DEFAULT_MATCHES_PANE_FRACTION = 1 / 3

#: Font weights for the right Matches column's hidden weight column
#: (see :meth:`FuzzyMatchingGramplet._build_matches_box`) - plain
#: PangoWeight ints (400/700 are the standard "normal"/"bold" values)
#: rather than an extra ``gi.repository.Pango`` import purely for two
#: well-known constants. Used to bold-highlight, without selecting, a
#: "nearest match" row :meth:`FuzzyMatchingGramplet._restore_person_selection`
#: could not find an exact previous selection for - see that method,
#: and :meth:`FuzzyMatchingGramplet.cb_person_selected`, which clears
#: it again once the user actually selects a row.
_WEIGHT_NORMAL = 400
_WEIGHT_BOLD = 700

#: This addon's own identity, matching the "id=" registered in
#: FuzzyMatchingGramplet.gpr.py. Recorded in the persisted .ini's
#: [meta] section (see CONFIG below) so the file identifies which
#: addon it belongs to if it is ever found on its own, matching the
#: convention used by this addon's sibling gramplets' own .ini files
#: (e.g. the Relationship Filter gramplet's [meta] block).
PLUGIN_ID = "Fuzzy Matching"

#: Schema version for the keys registered below. Bump this if they
#: ever change shape in a way that isn't just adding a new key with
#: its own default (renames, type changes, semantics changes), so a
#: future version can tell an old-shape .ini apart from a current one.
SCHEMA_VERSION = "1"

#: This gramplet's own persistent settings (currently just the
#: Matches paned position, once the user has dragged it), stored via
#: Gramps' own :class:`~gramps.gen.utils.configmanager.ConfigManager`
#: rather than a hand-rolled config file. ``use_plugins_path=False``
#: with no ``override`` makes ConfigManager use the *calling file's*
#: own directory for the .ini (see the "Simple.ini" example in
#: ``ConfigManager.register_manager``'s docstring) - i.e. this addon's
#: own folder, alongside FuzzyMatchingGramplet.py itself, rather than
#: Gramps' general per-user config directory. See :meth:`on_load`/
#: :meth:`on_save`, the Gramplet framework's own hooks for reading and
#: writing a gramplet's persisted state.
#:
#: The [meta] keys are registered with an empty placeholder default
#: rather than PLUGIN_ID/SCHEMA_VERSION directly, then immediately set
#: to the real value below: ConfigManager.save() comments out any key
#: whose current value equals its own registered default (its way of
#: distinguishing "still at default" from "genuinely set"), so
#: registering the real identifying values as their own defaults would
#: leave [meta] permanently commented-out in the .ini rather than
#: recording it as a live identifier the way this addon's sibling
#: gramplets' own .ini files do.
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
    Shows which surnames in the Family Tree phonetically match a given
    name, using a cached, per-database phonetic index so that the
    gramplet stays responsive on large trees.

    The index is (re)built by :meth:`main`, a generator that the
    Gramplet framework itself drives in the background via
    :meth:`gramps.gen.plug._gramplet.Gramplet.update`
    (``GLib.idle_add``), rather than by a plain synchronous method
    call from :meth:`db_changed`. On a large tree, building the index
    synchronously would freeze the GTK main loop for the whole
    operation with no way for the user to tell whether anything was
    happening; yielding periodically from a generator lets GTK keep
    processing events (repainting, handling input) between chunks, and
    lets this gramplet show progress while it works.
    """

    def init(self) -> None:
        """Build the widget tree and wire up the initial signal handlers."""
        # The phonetic index itself (surname <-> code, surname <->
        # person handles, and the incremental-update logic that keeps
        # both current without a full rebuild on every edit) lives in
        # fuzzy_match_index.FuzzyMatchIndex, shared with
        # FuzzyMatchLookupWindow.py, rather than duplicated here. This
        # gramplet only ever reads it (find_surnames/find_people/
        # find_matches) or hands it a signal's handle list to patch
        # itself (on_person_changed/on_person_deleted/on_rebuild) -
        # see db_changed, main, cb_person_changed, cb_person_deleted,
        # cb_person_rebuild, and _reset_phonetic_index.
        self._index = FuzzyMatchIndex(self.dbstate.db)

        self.gui.WIDGET = self.build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)

    def on_load(self) -> None:
        """
        Gramplet framework hook (see
        :meth:`gramps.gen.plug._gramplet.Gramplet.on_load`), called
        once right after :meth:`init` builds the widget tree.

        There is nothing to do here directly: the Matches paned's
        divider position is read from :data:`CONFIG` lazily, in
        :meth:`cb_matches_paned_size_allocate`, once the paned's real
        on-screen width is known (unavailable this early - the
        gramplet's container has not added/shown :attr:`gui.WIDGET`
        yet at this point in the framework's own startup sequence).
        This override exists mainly to document that intentionally,
        pairing with :meth:`on_save` below.
        """

    def on_save(self) -> None:
        """
        Gramplet framework hook (see
        :meth:`gramps.gen.plug._gramplet.Gramplet.on_save`), called by
        the gramplet pane/bar at sensible points (e.g. closing Gramps),
        not on every pixel of a paned drag.

        Persists the Matches paned's current divider position, as a
        fraction of its width so it scales sensibly if the gramplet is
        later shown at a different size, via Gramps' own
        :class:`~gramps.gen.utils.configmanager.ConfigManager`
        (:data:`CONFIG`) rather than a hand-rolled config file.
        """
        width = self.matches_paned.get_allocated_width()
        if width > 1:
            CONFIG.set(
                "gramplet.matches_pane_position",
                self.matches_paned.get_position() / width,
            )
        CONFIG.save()

    def build_gui(self) -> Gtk.Widget:
        """
        Build the GUI interface.

        :returns: The top-level widget for the gramplet.
        """
        grid = Gtk.Grid()
        grid.set_border_width(6)
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)

        name_label = Gtk.Label(label=_("Surname:"), halign=Gtk.Align.START)
        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(self._build_name_box(), 1, 0, 1, 1)

        algorithm_label = Gtk.Label(label=_("Encoding system:"), halign=Gtk.Align.START)
        grid.attach(algorithm_label, 0, 1, 1, 1)
        self.algo_combo = Gtk.ComboBoxText()
        for algorithm_id, display_name in ALGORITHM_LABELS.items():
            self.algo_combo.append(algorithm_id, _(display_name))
        self.algo_combo.set_active_id(DEFAULT_ALGORITHM)
        self._update_algorithm_tooltip()
        self.algo_combo.connect("changed", self.cb_algorithm_changed)
        grid.attach(self.algo_combo, 1, 1, 1, 1)

        code_label = Gtk.Label(label=_("Code(s):"), halign=Gtk.Align.START)
        grid.attach(code_label, 0, 2, 1, 1)
        grid.attach(self._build_code_view(), 1, 2, 1, 1)

        # Status row: hidden while idle, shown with a spinner and a
        # running count while the background index is (re)building, so
        # there is always a visible answer to "is anything happening".
        self.status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status_spinner = Gtk.Spinner()
        self.status_label = Gtk.Label(halign=Gtk.Align.START)
        self.status_box.pack_start(self.status_spinner, False, False, 0)
        self.status_box.pack_start(self.status_label, False, False, 0)
        self.status_box.set_no_show_all(True)
        grid.attach(self.status_box, 0, 3, 2, 1)

        matches_header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        matches_header_box.set_hexpand(True)
        matches_header_box.get_style_context().add_class("fuzzy-matches-header")
        matches_label = Gtk.Label(label=_("Matches:"), halign=Gtk.Align.START)
        self.matches_count_label = Gtk.Label(label="", halign=Gtk.Align.START)
        matches_header_box.pack_start(matches_label, False, False, 0)
        matches_header_box.pack_start(self.matches_count_label, False, False, 0)

        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(_MATCHES_HEADER_CSS)
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        grid.attach(matches_header_box, 0, 4, 2, 1)
        grid.attach(self._build_matches_box(), 0, 5, 2, 1)

        grid.show_all()
        return grid

    def _build_code_view(self) -> Gtk.TreeView:
        """
        Build the small "Code(s)" list: one selectable row per
        phonetic code the typed surname encodes to (most algorithms
        produce exactly one, but the registry in ``phonetic_codes.py``
        allows more).

        :returns: The unwrapped :class:`Gtk.TreeView` (small enough,
            typically one or two rows, that it does not need its own
            scrolled window).
        """
        self.code_store = Gtk.ListStore(str)
        self.code_view = Gtk.TreeView(model=self.code_store)
        self.code_view.set_headers_visible(False)
        self.code_view.append_column(
            Gtk.TreeViewColumn(_("Code"), Gtk.CellRendererText(), text=0)
        )
        return self.code_view

    def _build_matches_box(self) -> Gtk.Paned:
        """
        Build the two-column "Matches" display.

        The left column lists surnames phonetically matching the typed
        surname (via :attr:`_index`'s find_surnames); selecting one
        populates the right column with every person in the tree who
        has that exact surname (via :attr:`_index`'s find_people).
        Selecting a row in the right column makes that person the
        active person; double-clicking (or activating) a row opens the
        standard Person editor for them.

        The two columns sit in a :class:`Gtk.Paned` rather than a
        plain box, so the user can resize them; the starting split is
        :data:`DEFAULT_MATCHES_PANE_FRACTION` (or whatever the user
        last dragged it to - see :meth:`on_load`/:meth:`on_save`)
        rather than an even 50/50.

        Double-clicking (or activating) a row in the left column opens
        a "Define filter" dialog pre-filled with a People filter for
        that row's surname (not necessarily the typed Surname field -
        see :meth:`cb_surname_activated`).

        The right column also acts as a drag source for the standard
        Gramps "person-link" drag type
        (:attr:`gramps.gui.ddtargets.DdTargets.PERSON_LINK`), the same
        payload used throughout Gramps (e.g. the Relationships view,
        People view, and Person editor's reference lists) to let a
        person be dropped onto another view, gramplet, or editor field
        elsewhere - see :meth:`cb_person_drag_data_get`.

        :returns: A :class:`Gtk.Paned` containing both columns.
        """
        # Columns: (display text, raw surname, code). The raw-surname
        # and code columns are never added to the TreeView, so they
        # are not shown to the user; display text carries a "(count)"
        # suffix (see cb_name_changed) while every other method that
        # matches against a row's actual surname - cb_surname_selected,
        # cb_surname_activated, _focus_active_person - still has the
        # exact, un-annotated string to compare against, the same
        # display/lookup split already used below for person_store.
        #
        # This is a two-level Gtk.TreeStore, not a flat Gtk.ListStore:
        # a top-level "All <code>" row per phonetic code (raw surname
        # == "" - there is no single surname to filter to), with that
        # code's individual matching surnames as its children. See
        # cb_name_changed, which builds this, and cb_surname_selected,
        # which treats an empty raw-surname as "show every surname
        # under this code", not "show nobody".
        self.surname_store = Gtk.TreeStore(str, str, str)
        self.surname_view = Gtk.TreeView(model=self.surname_store)
        self.surname_view.set_headers_visible(False)
        self.surname_view.append_column(
            Gtk.TreeViewColumn(_("Surname"), Gtk.CellRendererText(), text=0)
        )
        # Handler ids are kept so store repopulation and
        # _focus_active_person can block the relevant handler (via
        # GObject's own handler_block/unblock) rather than the
        # gramplet tracking "is this a programmatic change" itself
        # with a hand-rolled flag - see cb_name_changed,
        # cb_surname_selected, cb_person_selected, and
        # _focus_active_person for why merely repopulating a
        # Gtk.ListStore, not just calling select_path(), needs this
        # too: clearing and refilling a TreeView's model while it has
        # keyboard focus can fire spurious TreeSelection "changed"
        # signals on its own, independent of any real selection.
        self._surname_selection_handler_id = self.surname_view.get_selection().connect(
            "changed", self.cb_surname_selected
        )
        self.surname_view.connect("row-activated", self.cb_surname_activated)
        surname_scrolled = Gtk.ScrolledWindow()
        surname_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        surname_scrolled.set_hexpand(True)
        surname_scrolled.set_vexpand(True)
        surname_scrolled.add(self.surname_view)

        # Columns: (display text, person handle, font weight). The
        # handle column is never added to the TreeView, so it is not
        # shown to the user. The weight column drives the "nearest
        # match" boldface :meth:`_restore_person_selection` sets on a
        # row it couldn't exactly reselect - see :data:`_WEIGHT_NORMAL`/
        # :data:`_WEIGHT_BOLD` - and is otherwise always
        # :data:`_WEIGHT_NORMAL`.
        self.person_store = Gtk.ListStore(str, str, int)
        self.person_view = Gtk.TreeView(model=self.person_store)
        self.person_view.set_headers_visible(False)
        person_renderer = Gtk.CellRendererText()
        self.person_view.append_column(
            Gtk.TreeViewColumn(_("Person"), person_renderer, text=0, weight=2)
        )
        self._person_selection_handler_id = self.person_view.get_selection().connect(
            "changed", self.cb_person_selected
        )
        self.person_view.connect("row-activated", self.cb_person_activated)
        self.person_view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK,
            [DdTargets.PERSON_LINK.target()],
            Gdk.DragAction.COPY,
        )
        self.person_view.connect("drag-data-get", self.cb_person_drag_data_get)
        person_scrolled = Gtk.ScrolledWindow()
        person_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        person_scrolled.set_hexpand(True)
        person_scrolled.set_vexpand(True)
        person_scrolled.add(self.person_view)

        self.matches_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.matches_paned.pack1(surname_scrolled, True, True)
        self.matches_paned.pack2(person_scrolled, True, True)
        # The paned's allocated width isn't known yet at construction
        # time, so the actual pixel position for the persisted/default
        # fraction is set the first time real width is available - see
        # cb_matches_paned_size_allocate, which disconnects itself
        # after doing this once so it never overrides the user's own
        # later drags.
        self._matches_pane_position_set = False
        self.matches_paned.connect("size-allocate", self.cb_matches_paned_size_allocate)
        return self.matches_paned

    def cb_matches_paned_size_allocate(
        self, paned: Gtk.Paned, allocation: Gdk.Rectangle
    ) -> None:
        """
        Set the Matches paned's initial divider position, once, the
        first time it is allocated a real width.

        Applies :data:`DEFAULT_MATCHES_PANE_FRACTION`, or the fraction
        persisted from a previous session (see :meth:`on_load`), as
        soon as ``allocation.width`` reflects the gramplet's actual
        on-screen size rather than the ``0``/placeholder width GTK
        reports before the first real layout pass. Disconnects itself
        (via the ``self._matches_pane_position_set`` guard) after doing
        this once, so it never overrides the user's own later drags.

        :param paned: The Matches :class:`Gtk.Paned` that emitted the
            signal.
        :param allocation: The new allocation; only ``.width`` is used.
        """
        if self._matches_pane_position_set or allocation.width <= 1:
            return
        self._matches_pane_position_set = True
        fraction = CONFIG.get("gramplet.matches_pane_position")
        paned.set_position(round(allocation.width * fraction))

    def _build_name_box(self) -> Gtk.Box:
        """
        Build the name-entry row: a combo box offering nearby surnames
        as a convenience dropdown, plus a "gtk-index" button that opens
        the standard Person selector for browsing the whole tree.

        The combo's dropdown only ever holds surnames from people
        within :data:`NEARBY_DEGREES` of the active person (see
        :meth:`_refresh_nearby_combo`), never the full surname list -
        see "Why the gramplet used to freeze the whole application" in
        the module docstring for why that distinction matters. The
        "gtk-index" browse button is Gramps' own established icon-name
        convention for "open an object selector dialog" (used the same
        way for person/family/note/media selectors throughout
        ``gramps.gui.plug._guioptions`` and several core edit dialogs).

        The entry is also a drop target for the standard Gramps
        "person-link" drag type
        (:attr:`gramps.gui.ddtargets.DdTargets.PERSON_LINK`): dropping
        a person dragged from elsewhere in Gramps (or from this
        gramplet's own right Matches column - see
        :meth:`cb_person_drag_data_get`) sets the field to that
        person's surname, the same way typing it or selecting the
        active person already does - see
        :meth:`cb_name_drag_data_received`.

        :returns: A :class:`Gtk.Box` containing the combo and button.
        """
        self.name_combo = Gtk.ComboBox.new_with_entry()
        self.name_combo.set_hexpand(True)
        self.name_entry = self.name_combo.get_child()
        self.name_entry.connect("changed", self.cb_name_changed)
        self.name_entry.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [DdTargets.PERSON_LINK.target()],
            Gdk.DragAction.COPY,
        )
        self.name_entry.connect("drag-data-received", self.cb_name_drag_data_received)

        self.browse_person_button = SimpleButton(
            "gtk-index", self.cb_browse_person_clicked
        )
        self.browse_person_button.set_relief(Gtk.ReliefStyle.NORMAL)
        self.browse_person_button.set_tooltip_text(
            _("Select a person from the whole Family Tree")
        )

        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        name_box.pack_start(self.name_combo, True, True, 0)
        name_box.pack_start(self.browse_person_button, False, False, 0)
        return name_box

    def db_changed(self) -> None:
        """
        React to a newly-opened database.

        First, and before anything else touches the (already-current)
        new database, discards the phonetic index built for whichever
        database was open before (:meth:`_reset_phonetic_index`) - see
        that method for the crash this specifically prevents. The rest
        is cheap, immediate work (seeding the name field from the
        active person, and refreshing the small nearby-surname dropdown
        - see :meth:`_refresh_nearby_combo`); the potentially expensive
        full-tree phonetic index and person-lookup rebuild happens in
        :meth:`main`, which the Gramplet framework schedules in the
        background right after this method returns (see
        :meth:`gramps.gen.plug._gramplet.Gramplet._db_changed`).
        """
        if not self.dbstate.is_open():
            return

        self._reset_phonetic_index()

        # Connected via this Gramplet base class's own connect()
        # wrapper (gramps.gen.plug._gramplet.Gramplet.connect) - the
        # same idiom the core LastChangeGramplet addon uses for its
        # own person-*/family-* hooks - rather than calling
        # self.dbstate.db.connect(...) directly. dbstate.db is a
        # brand-new database object every time db_changed runs (a
        # different Family Tree, or the same one reopened), so these
        # are (re)connected fresh each time rather than once in
        # init(); nothing further needs disconnecting first, since
        # whatever object a previous connection was made on is simply
        # no longer dbstate.db and nothing will ever emit from it
        # again. person-add/-update/-delete are handled as a scoped,
        # limited-size patch keyed off the handles the signal itself
        # provides (see cb_person_changed/cb_person_deleted) rather
        # than a full rescan of the tree on every edit; person-rebuild
        # covers batch operations (import, Tools that run in one
        # transaction) that fire that signal instead of individual
        # ones, where there is no handle list to scope a patch to and
        # a full main() rebuild is the only option; event-update
        # catches a birth/death event's date or place being edited in
        # place, which commits only the Event object and so never
        # fires person-update at all - see cb_event_changed.
        self.connect(self.dbstate.db, "person-add", self.cb_person_changed)
        self.connect(self.dbstate.db, "person-update", self.cb_person_changed)
        self.connect(self.dbstate.db, "person-delete", self.cb_person_deleted)
        self.connect(self.dbstate.db, "person-rebuild", self.cb_person_rebuild)
        self.connect(self.dbstate.db, "event-update", self.cb_event_changed)

        person = self.get_active_object("Person")
        self._refresh_nearby_combo(person)
        if person:
            self.name_entry.set_text(self._primary_surname_text(person))
        else:
            self.name_entry.set_text("")
        self._focus_active_person(person)

    def active_changed(self, _handle: str) -> None:
        """
        Update the displayed name and nearby-surname dropdown when the
        active person changes, and select/center their row in both
        Matches columns.

        This mirrors :meth:`db_changed`'s "seed the Surname field from
        the active person" behavior rather than leaving the field
        alone: this gramplet's core purpose is following along as the
        active person changes elsewhere in Gramps (the Home button,
        another view, another gramplet), so an active-person change
        that does not update what is shown here would defeat that
        purpose - :meth:`_focus_active_person` can only select a row
        that is already among the *current* Matches, so if the field
        is not updated to match, there is usually nothing for it to
        select at all.

        :param _handle: The handle of the newly-active person, as
            passed by the Gramplet framework. Unused directly, since
            the active object is fetched through
            :meth:`get_active_object`, which is a cheap O(1) handle
            lookup rather than a fresh database scan.
        """
        person = self.get_active_object("Person")
        self._refresh_nearby_combo(person)
        if person:
            self.name_entry.set_text(self._primary_surname_text(person))
        self._focus_active_person(person)

    @staticmethod
    def _primary_surname_text(person) -> str:
        """
        Return the single surname text this gramplet uses wherever it
        needs *one* representative surname for a person - seeding the
        Surname field from the active person, a browsed person, or a
        dropped person (see :meth:`db_changed`, :meth:`active_changed`,
        :meth:`cb_browse_person_clicked`, :meth:`cb_name_drag_data_received`).

        Deliberately :meth:`~gramps.gen.lib.Name.get_primary_surname`,
        not :meth:`~gramps.gen.lib.Name.get_surname`: the latter
        returns a *fully-formatted* string across every
        :class:`~gramps.gen.lib.Surname` on the name, joined with
        whatever connector each one has - for a compound/double
        surname such as "Thompson McCullough", that is the string
        ``"Thompson McCullough"`` itself. Encoding that whole joined
        string under a phonetic algorithm other than Soundex (NYSIIS,
        Metaphone, Match Rating Approach all process the *entire*
        input as one continuous run, unlike Soundex's fixed-length
        code) produces a code for the run-on string as a whole, which
        will not phonetically match "Thompson" alone at all - seeding
        the field this way would make the very feature this method
        exists for stop working, for exactly the people it matters
        most for. The primary surname alone avoids that regardless of
        algorithm. See :func:`fuzzy_match_index.person_surnames` for
        the complementary "every piece, for indexing/matching purposes"
        version this is not a replacement for.

        :param person: The :class:`gramps.gen.lib.Person` to read.
        :returns: Their primary name's primary surname text, or ``""``
            if they have no surname at all.
        """
        primary_surname = person.get_primary_name().get_primary_surname()
        if primary_surname is None:
            return ""
        return primary_surname.get_surname()

    def _refresh_nearby_combo(self, active_person) -> None:
        """
        Repopulate the name entry's dropdown with surnames from people
        within :data:`NEARBY_DEGREES` of ``active_person``.

        This set is bounded by family structure (a person only has so
        many parents, children, and spouses to walk through at each
        step), not by the size of the Family Tree, so - unlike the full
        surname list this gramplet used to put here - it is always
        cheap to compute and safe to hand to
        :func:`gramps.gui.autocomp.fill_combo`, regardless of how large
        the tree is.

        Suggests every surname *piece* a nearby relative carries (see
        :func:`fuzzy_match_index.person_surnames`), not just one
        representative string per relative - a relative with a
        compound surname contributes each of its pieces as its own
        suggestion, so typing either one is offered.

        :param active_person: The current active
            :class:`gramps.gen.lib.Person`, or None.
        """
        if active_person is None:
            fill_combo(self.name_combo, [])
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

        fill_combo(self.name_combo, sorted(surnames, key=glocale.sort_key))

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

    def cb_browse_person_clicked(self, _button: Gtk.Button) -> None:
        """
        Open the standard Person selector so the user can pick any
        person in the whole Family Tree, not just the nearby-surname
        shortlist in the dropdown.

        :param _button: The "gtk-index" browse button that emitted the
            signal.
        """
        select_class = SelectorFactory("Person")
        selector = select_class(
            self.dbstate,
            self.uistate,
            self.track,
            title=_("Select a person"),
        )
        person = selector.run()
        if person:
            self.name_entry.set_text(self._primary_surname_text(person))

    def _current_algorithm(self) -> str:
        """
        Return the identifier of the currently-selected phonetic algorithm.

        :returns: An id key from :data:`phonetic_codes.ALGORITHMS`.
        """
        algorithm_id = self.algo_combo.get_active_id()
        if algorithm_id is not None:
            return algorithm_id
        # phonetic_codes.DEFAULT_ALGORITHM is itself typed Optional[str]
        # (it could theoretically be None if no algorithm registered at
        # all) - see phonetic_codes._hardcoded_soundex, which exists
        # specifically so at least one algorithm is always available,
        # making the assert below a documented invariant, not a guess.
        assert DEFAULT_ALGORITHM is not None, (
            "phonetic_codes registered no algorithms at all - see "
            "phonetic_codes._hardcoded_soundex"
        )
        return DEFAULT_ALGORITHM

    def main(self):
        """
        Rebuild, in the background, :attr:`_index` - the two lookups
        this gramplet's Matches columns depend on (code -> surnames,
        and surname -> person handles). The indexing itself
        (:meth:`fuzzy_match_index.FuzzyMatchIndex.build`) lives in a
        module shared with :mod:`FuzzyMatchLookupWindow`; this method
        is just the Gramplet-framework glue around it - reading the
        currently-selected algorithm, driving the shared generator,
        and refreshing the display once it finishes.

        This is the Gramplet framework's generator hook (see
        :meth:`gramps.gen.plug._gramplet.Gramplet.main`): it is driven
        by :meth:`update` via ``GLib.idle_add``, one ``next()`` call
        per main-loop idle slot, rather than run straight through on
        the calling thread. ``yield True`` hands control back to GTK
        so it can repaint and handle input between chunks; ``yield
        False`` (implicit on ``return``/``StopIteration``) ends the
        background run.

        :returns: A generator; see above.
        """
        if not self.dbstate.is_open():
            return

        self._index.algorithm_id = self._current_algorithm()
        yield from self._index.build(progress_callback=self._cb_index_progress)

        self._set_busy(False)

        # The index just changed (new database, or new algorithm), so
        # refresh whatever is currently typed/selected against it.
        self.cb_name_changed(self.name_entry)
        self._focus_active_person(self.get_active_object("Person"))

    def _cb_index_progress(self, phase: str, position: int, total: int) -> None:
        """
        Drive the busy spinner/progress label from
        :meth:`fuzzy_match_index.FuzzyMatchIndex.build`'s progress
        callback. ``phase`` arrives as the plain, untranslated string
        ``"surnames"`` or ``"people"``; translating it for display is
        this gramplet's own job, not the shared index module's.

        :param phase: Which phase of the build is running.
        :param position: Number of items processed so far in this phase.
        :param total: Total number of items in this phase.
        """
        self._set_busy(True, _(phase), position, total)

    def cb_person_changed(self, handles: List[str]) -> None:
        """
        Patch the surname index in place for one or more added or
        edited people, instead of waiting for the next full
        :meth:`main` rebuild.

        Connected to the database's own ``person-add``/``person-update``
        signals in :meth:`db_changed`; both fire with the list of
        affected handles from a single commit or transaction. The
        patching itself is
        :meth:`fuzzy_match_index.FuzzyMatchIndex.on_person_changed` -
        this method is just the GTK side of it: hand it the handles,
        then refresh whatever is currently on screen if anything it
        touched could be affected - see :meth:`_refresh_display_if_touched`.

        :param handles: Handles of the people that were added or
            updated, as passed by the database's signal.
        """
        touched_surnames = self._index.on_person_changed(handles)
        self._refresh_display_if_touched(touched_surnames)

    def cb_person_deleted(self, handles: List[str]) -> None:
        """
        Patch the surname index in place for one or more deleted
        people, instead of waiting for the next full :meth:`main`
        rebuild - see :meth:`cb_person_changed`, which this mirrors,
        and
        :meth:`fuzzy_match_index.FuzzyMatchIndex.on_person_deleted`,
        which does the actual patching.

        Connected to the database's own ``person-delete`` signal in
        :meth:`db_changed`, which fires with the list of deleted
        handles.

        :param handles: Handles of the people that were deleted, as
            passed by the database's signal.
        """
        touched_surnames = self._index.on_person_deleted(handles)
        self._refresh_display_if_touched(touched_surnames)

    def cb_person_rebuild(self) -> None:
        """
        Fall back to a full background reindex when the database emits
        ``person-rebuild`` - fired instead of individual
        ``person-add``/``-update``/``-delete`` signals after batch
        operations (an import, or a Tool that runs in one transaction)
        that touch more people than it makes sense to enumerate
        individually. There is no per-handle list to patch the index
        with here, so this marks it stale
        (:meth:`fuzzy_match_index.FuzzyMatchIndex.on_rebuild`) and
        restarts :meth:`main` the same way a newly-opened database or
        a changed algorithm does.
        """
        if not self.dbstate.is_open():
            return
        self._index.on_rebuild()
        self.update()

    def cb_event_changed(self, handles: List[str]) -> None:
        """
        Refresh the display text of any person currently shown in the
        right Matches column whose birth or death event was just
        edited.

        Connected to the database's own ``event-update`` signal in
        :meth:`db_changed`. This exists because editing a birth or
        death event's date or place from the Person editor's Events
        tab commits only that :class:`~gramps.gen.lib.Event` object
        (``event-update``) - the person's own event reference list is
        unchanged, so ``person-update`` never fires and
        :meth:`cb_person_changed` never runs. The actual row-matching
        and reformatting is
        :func:`fuzzy_match_display.refresh_matching_person_rows`,
        shared with :class:`FuzzyMatchLookupWindow`'s identical need.

        :param handles: Handles of the events that were updated, as
            passed by the database's signal.
        """
        refresh_matching_person_rows(self.dbstate.db, self.person_store, handles)

    def _refresh_display_if_touched(self, touched_surnames: set) -> None:
        """
        Re-run the current search against the just-patched index if
        anything changed, so an add/edit/delete shows up without the
        user retyping the Surname field or reselecting a row.

        A no-op while the background index has not finished its first
        pass for the current algorithm (:meth:`main` will show
        everything current once it does), or if nothing was actually
        touched.

        :param touched_surnames: Surnames the index says were just
            added to, changed, or removed (see
            :meth:`fuzzy_match_index.FuzzyMatchIndex.on_person_changed`/
            ``on_person_deleted``'s return value).
        """
        if (
            not touched_surnames
            or not self._index.ready
            or self._index.algorithm_id != self._current_algorithm()
        ):
            return

        selected_surname = self._get_selected_surname()
        self.cb_name_changed(self.name_entry)
        if selected_surname is not None and selected_surname in touched_surnames:
            self._reselect_surname(selected_surname)

    def _get_selected_surname(self) -> str | None:
        """
        Return the raw surname (not the "Surname (count)" display
        text) currently selected in the left Matches column, ``""`` if
        the selected row is a top-level "All <code>" row, or None if
        nothing is selected.

        :returns: The selected surname, ``""`` for an "All <code>"
            row, or None.
        """
        model, tree_iter = self.surname_view.get_selection().get_selected()
        if tree_iter is None:
            return None
        return model[tree_iter][1]

    @staticmethod
    def _iter_tree_rows(store: Gtk.TreeStore):
        """
        Yield every row in ``store`` - both top-level "All <code>"
        rows and their surname children - since a plain ``for row in
        store`` only ever visits top-level rows on a
        :class:`Gtk.TreeStore`. Used wherever a specific surname's row
        needs finding regardless of which code it's nested under (see
        :meth:`_reselect_surname`, :meth:`_focus_active_person`).

        :param store: The :class:`Gtk.TreeStore` to walk.
        :returns: A generator yielding each row, parents before their
            own children, top to bottom.
        """

        def _walk(tree_iter):
            while tree_iter is not None:
                yield store[tree_iter]
                yield from _walk(store.iter_children(tree_iter))
                tree_iter = store.iter_next(tree_iter)

        yield from _walk(store.get_iter_first())

    def _reselect_surname(self, surname: str) -> None:
        """
        Reselect ``surname``'s row in the left Matches column after
        :meth:`cb_name_changed` has rebuilt :attr:`surname_store`, so
        the right column refreshes (via the normal
        :meth:`cb_surname_selected` selection-changed handler) to
        reflect whatever just changed. A no-op if ``surname`` is no
        longer among the current matches - for example, its last
        person was just deleted.

        :param surname: The raw surname to reselect.
        """
        for row in self._iter_tree_rows(self.surname_store):
            if row[1] == surname:
                self.surname_view.get_selection().select_path(row.path)
                return

    def _set_busy(
        self, busy: bool, phase: str = "", position: int = 0, total: int = 0
    ) -> None:
        """
        Show or hide the "indexing in progress" status row.

        :param busy: True to show the spinner and progress label,
            False to hide them again.
        :param phase: Which stage of :meth:`main` is running (e.g.
            "surnames" or "people"), used for the progress text.
            Ignored when ``busy`` is False.
        :param position: Number of items processed so far in this
            phase. Ignored when ``busy`` is False.
        :param total: Total number of items in this phase, used for
            the initial progress text. Ignored when ``busy`` is False.
        """
        if busy:
            self.status_box.set_no_show_all(False)
            self.status_box.show_all()
            self.status_spinner.start()
            self._update_progress(phase, position, total)
        else:
            self.status_spinner.stop()
            self.status_box.hide()

    def _update_progress(self, phase: str, position: int, total: int) -> None:
        """
        Update the status label shown while the index is (re)building.

        :param phase: Which stage of :meth:`main` is running (e.g.
            "surnames" or "people"), shown in the progress text.
        :param position: Number of items processed so far in this
            phase.
        :param total: Total number of items in this phase.
        """
        if total:
            self.status_label.set_text(
                _("Indexing {phase}… {done} / {total}").format(
                    phase=phase, done=position, total=total
                )
            )
        else:
            self.status_label.set_text(_("Indexing {phase}…").format(phase=phase))

    def cb_algorithm_changed(self, _combo: Gtk.ComboBoxText) -> None:
        """
        Update the tooltip for the newly-selected algorithm and
        re-index in the background.

        :param _combo: The algorithm combo box that emitted the signal.
        """
        self._update_algorithm_tooltip()
        if not self.dbstate.is_open():
            return
        self.update()

    def _update_algorithm_tooltip(self) -> None:
        """
        Set the Encoding system dropdown's tooltip to the currently
        selected algorithm's :data:`phonetic_codes.ALGORITHM_DESCRIPTIONS`
        entry, so a user can hover the dropdown to see what makes this
        algorithm different from the others, without a separate
        dialog. A no-op, leaving whatever tooltip was already there,
        if the current algorithm has no description on file.
        """
        description = ALGORITHM_DESCRIPTIONS.get(self._current_algorithm())
        if description:
            self.algo_combo.set_tooltip_text(_(description))

    def cb_name_changed(self, _entry: Gtk.Entry) -> None:
        """
        Recompute and display the phonetic matches for the typed
        Surname field.

        The field normally holds a bare surname, but also accepts a
        full "Surname, Given Name" query (see :meth:`_parse_query`) -
        only the part before a comma is ever used for the actual
        phonetic search, so a full name typed here still finds the
        right code(s). If a given name was supplied this way, the
        nearest-matching person is selected/centered in the right
        column once it's populated - see :meth:`_select_nearest_person_by_given_name`.

        Looks up the pre-computed code -> surnames index built by
        :meth:`main`, so typing does not trigger a fresh database scan.
        If the index is missing or stale (a new database was just
        opened, or the algorithm was just changed and the background
        rebuild triggered by :meth:`cb_algorithm_changed` hasn't
        finished yet), this clears the display and, if a rebuild isn't
        already running, starts one in the background rather than
        blocking here; :meth:`main` calls back into this method itself
        once the rebuild completes.

        The left column is built as one top-level "All <code>" row per
        matched code, each with its matching surnames as children (see
        :attr:`surname_store`'s own docstring in :meth:`_build_matches_box`).
        The first code's "All <code>" row is selected by default, which
        populates the right column with everyone under that code,
        sorted the same way selecting an individual surname would be -
        see :meth:`cb_surname_selected`.

        Also updates :attr:`matches_count_label` with the *total*
        number of people across every matching surname combined - not
        just whichever surname happens to be selected in the left
        column. This is deliberately the same total the "Define
        filter" action's resulting filter would return (see
        :meth:`cb_surname_activated`, which builds a filter matching
        any person whose surname's code is among these same codes), so
        it doubles as a quick way to confirm a saved Custom Filter
        applied elsewhere is returning what it should.

        :param _entry: The name entry widget that emitted the signal.
        """
        if (
            not self._index.ready
            or self._index.algorithm_id != self._current_algorithm()
        ):
            self.code_store.clear()
            self._clear_matches()
            if not self._idle_id:
                self.update()
            return

        surname, given_name = self._parse_query(self.name_entry.get_text())
        encode = ALGORITHMS[self._current_algorithm()]
        codes = encode(surname)
        self.code_store.clear()
        for code in sorted(codes):
            self.code_store.append([code])

        self._clear_matches()
        total_handles: Set[str] = set()
        default_path = None
        with self._blocked_selection_handlers(
            self.surname_view, self._surname_selection_handler_id
        ):
            for code in sorted(codes):
                surnames_for_code = self._index.find_surnames_for_code(code)
                code_handles: Set[str] = set()
                for matched_surname in surnames_for_code:
                    code_handles.update(self._index.find_people(matched_surname))
                total_handles.update(code_handles)

                all_display = _("All {code} ({count})").format(
                    code=code, count=len(code_handles)
                )
                parent_iter = self.surname_store.append(None, [all_display, "", code])
                if default_path is None:
                    default_path = self.surname_store.get_path(parent_iter)

                for matched_surname in sorted(surnames_for_code, key=glocale.sort_key):
                    count = len(self._index.find_people(matched_surname))
                    display = _("{surname} ({count})").format(
                        surname=matched_surname, count=count
                    )
                    self.surname_store.append(
                        parent_iter, [display, matched_surname, code]
                    )
        self.surname_view.expand_all()
        self.matches_count_label.set_text(_("({count})").format(count=len(total_handles)))

        if default_path is not None:
            # Selecting this row triggers cb_surname_selected (the
            # handler is unblocked again by now), synchronously
            # populating person_store with the default "All <code>"
            # view described above.
            self.surname_view.get_selection().select_path(default_path)

        if given_name:
            self._select_nearest_person_by_given_name(given_name)

    @staticmethod
    def _parse_query(text: str):
        """
        Split the Surname field's text into ``(surname, given_name)``.

        A comma is the only signal treated as "this is a full name,
        not a bare surname" - ``"Surname, Given Name"``, the format
        Gramps itself uses to display a name - so a multi-word surname
        typed alone (e.g. "Van Der Berg", with no comma) keeps working
        exactly as it always has: as one surname to phonetically match,
        with no given name involved.

        :param text: The Surname field's current text.
        :returns: ``(surname, given_name)``, both stripped of
            surrounding whitespace; ``given_name`` is ``""`` unless a
            comma was present.
        """
        if "," in text:
            surname, _sep, given_name = text.partition(",")
            return surname.strip(), given_name.strip()
        return text.strip(), ""

    def _select_nearest_person_by_given_name(self, given_name: str) -> None:
        """
        Select and center whichever row currently in the right Matches
        column has the given name sorting closest to ``given_name``,
        via the same locale-aware sort key :func:`fuzzy_match_display.
        person_sort_key` already sorts that column by, and the same
        ``bisect_left`` "closest at or after this point" approach
        :meth:`FuzzyMatchLookupWindow._scroll_to_closest_given_name`
        already uses for its own, separate Given Name field - not a
        real nearest-neighbor pick (that would sometimes prefer the
        row just before this point instead), but close enough to be
        useful without a second string-distance metric on top of the
        sort key the column already uses.

        Called from :meth:`cb_name_changed` when the Surname field
        held a full "Surname, Given Name" query - selecting a row here
        also makes that person the active person, the same as clicking
        it would (see :meth:`cb_person_selected`), which is the point:
        typing a full name should jump straight to that person if
        they're already in the tree.

        A no-op if the right column is currently empty.

        :param given_name: The given name to select/center closest to.
        """
        db = self.dbstate.db
        candidates = []
        for row in self.person_store:
            try:
                person = db.get_person_from_handle(row[1])
            except HandleError:
                continue
            candidates.append(
                (glocale.sort_key(person.get_primary_name().get_first_name()), row.path)
            )
        if not candidates:
            return

        candidates.sort(key=lambda item: item[0])
        target = glocale.sort_key(given_name)
        keys = [key for key, _path in candidates]
        index = min(bisect_left(keys, target), len(candidates) - 1)
        path = candidates[index][1]

        self.person_view.get_selection().select_path(path)
        self.person_view.scroll_to_cell(path, None, True, 0.5, 0.0)

    def cb_name_drag_data_received(
        self,
        _widget: Gtk.Entry,
        _context: Gdk.DragContext,
        _xpos: int,
        _ypos: int,
        sel_data: Gtk.SelectionData,
        _info: int,
        _time: int,
    ) -> None:
        """
        Set the Surname entry to a dropped person's surname.

        Accepts the standard Gramps "person-link" drag payload (see
        :meth:`cb_person_drag_data_get`) from any source that offers
        it - the People view, the Relationships view, other
        Person-reference drag sources, or this gramplet's own right
        Matches column - not just persons dragged from within this
        gramplet.

        Setting :attr:`name_entry`'s text fires :meth:`cb_name_changed`
        exactly as if the surname had been typed, so the Code(s) and
        Matches columns refresh the same way; no separate refresh call
        is needed here.

        A no-op if the drop carries no data, or carries a drag type
        other than :attr:`~gramps.gui.ddtargets.DdTargets.PERSON_LINK`
        (defensive: this widget only ever advertises that one target,
        but a well-behaved drop handler should not assume a source
        never offers more than what it asked for), or if the dropped
        handle no longer resolves to a person (for example: the person
        was deleted between the drag starting and the drop landing).

        :param _widget: The Surname entry that emitted the signal.
        :param _context: The drag context.
        :param _xpos: Drop x position within the widget.
        :param _ypos: Drop y position within the widget.
        :param sel_data: The :class:`Gtk.SelectionData` carrying the
            dropped person-link payload.
        :param _info: The matched target's registered info id.
        :param _time: The event time.
        """
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
            self.name_entry.set_text(self._primary_surname_text(person))

    def cb_surname_activated(
        self,
        _tree_view: Gtk.TreeView,
        path: Gtk.TreePath,
        _column: Gtk.TreeViewColumn,
    ) -> None:
        """
        Open a "Define filter" dialog pre-filled with a People filter
        for the double-clicked row's surname, mirroring the Clipboard
        module's "Create a filter from the selected..." feature
        (:func:`gramps.gui.makefilter.make_filter`) but built from a
        Matches row instead of a clipboard selection.

        Builds a :class:`gramps.gen.filters.GenericFilter` using
        whichever rule class
        :data:`phonetic_codes.ALGORITHM_FILTER_RULES` has on file for
        the *currently selected* Encoding system - not always
        ``HasSoundexName``: a filter for a NYSIIS or Match Rating
        Approach result needs a rule that actually tests NYSIIS/Match
        Rating Approach codes, which is exactly what
        ``nysiisrule.HasNysiisName``/``matchratingrule.HasMatchRatingName``
        are for (Soundex already has a matching rule built into Gramps
        itself, reused as-is - see ``phonetic_codes.py``). If the
        current algorithm has no rule on file, this tells the user
        that action is unavailable for it rather than silently doing
        nothing or building a filter with the wrong rule.

        A rule with a "Match in:" option (the Phonetic Filter Rules
        addon's) is created with every name field ticked, in both the
        preferred and alternate names, so the filter starts as wide as
        it can be and the user narrows it in the dialog; Gramps'
        built-in ``HasSoundexName`` fallback has no such option and
        already searches everything.

        The rule is built with the *activated row's* surname as its
        ``<name>`` parameter - not necessarily the Surname field's
        current text, since the left column can hold several
        phonetically-matching surnames at once and any of them may be
        double-clicked. Names the filter "Fuzzy match: <surname>
        (<encoding system>)", and sets a comment reading "Created on
        YYYY/MM/DD by Fuzzy Matching gramplet" - the same date format
        :func:`~gramps.gui.makefilter.make_filter` uses for its own
        Clipboard-created filters, with the source noted since this
        one was not created from a clipboard selection. Opens the
        result in :class:`gramps.gui.editors.EditFilter`. The filter
        is never saved by this method - :func:`edit_filter_save` is
        passed as the dialog's own save callback, so it is written
        only if the user chooses to click OK in the dialog, the same
        as it would be for any other filter edited that way.

        :param _tree_view: The left Matches column's
            :class:`Gtk.TreeView` that emitted the signal.
        :param path: The activated row's path, used to look up which
            surname was double-clicked.
        :param _column: The activated column.
        """
        tree_iter = self.surname_store.get_iter(path)
        surname = self.surname_store[tree_iter][1]
        if not surname:
            return

        algorithm_id = self._current_algorithm()
        algorithm_label = _(ALGORITHM_LABELS.get(algorithm_id, algorithm_id))
        rule_class = ALGORITHM_FILTER_RULES.get(algorithm_id)
        if rule_class is None:
            OkDialog(
                _("No filter available for {algorithm}").format(
                    algorithm=algorithm_label
                ),
                _(
                    "This Encoding system does not have a matching People"
                    " filter rule yet, so a filter cannot be created from it."
                ),
                parent=self.uistate.window,
            )
            return

        filter_name = _("Fuzzy match: {surname} ({algorithm})").format(
            surname=surname, algorithm=algorithm_label
        )

        filter_class = GenericFilterFactory("Person")
        new_filter = filter_class()
        new_filter.set_name(filter_name)
        rule_args = [surname]
        if len(getattr(rule_class, "labels", ())) > 1:
            # The rule has a "Match in:" option (Gramps' built-in
            # HasSoundexName, fallback for Soundex, does not): start
            # with every name field ticked; the user can narrow it in
            # the dialog before saving.
            rule_args.append(_MATCH_IN_ALL)
        new_filter.add_rule(rule_class(rule_args))
        struct_time = time.localtime()
        new_filter.set_comment(
            _(
                "Created on %(year)4d/%(month)02d/%(day)02d"
                " by Fuzzy Matching gramplet"
            )
            % {
                "year": struct_time.tm_year,
                "month": struct_time.tm_mon,
                "day": struct_time.tm_mday,
            }
        )

        filterdb = FilterList(CUSTOM_FILTERS)
        filterdb.load()

        EditFilter(
            "Person",
            self.dbstate,
            self.uistate,
            self.track,
            new_filter,
            filterdb,
            lambda: edit_filter_save(self.uistate, filterdb, "Person"),
        )

    def _clear_matches(self) -> None:
        """
        Clear both Matches columns and the total-match count shown
        next to the "Matches:" label.

        Clearing a :class:`Gtk.ListStore` while its :class:`Gtk.TreeView`
        has keyboard focus can, on its own, fire spurious
        :class:`Gtk.TreeSelection` "changed" signals - independent of
        any real selection - so both selection handlers are blocked for
        the duration (see the note on the handler ids in
        :meth:`_build_matches_box`).

        Deliberately does not also reset :attr:`_index` -
        :meth:`cb_name_changed` calls this to clear the *displayed*
        results while re-populating them (count included) from that
        same, still-valid index moments later. See
        :meth:`_reset_phonetic_index` for the version that also
        discards :attr:`_index`, used when it actually needs
        discarding (a database switch), not just a display refresh.
        """
        with self._blocked_selection_handlers(
            self.surname_view, self._surname_selection_handler_id
        ), self._blocked_selection_handlers(
            self.person_view, self._person_selection_handler_id
        ):
            self.surname_store.clear()
            self.person_store.clear()
        self.matches_count_label.set_text("")

    def _reset_phonetic_index(self) -> None:
        """
        Clear both Matches columns *and* discard :attr:`_index`,
        replacing it with a fresh, empty
        :class:`~fuzzy_match_index.FuzzyMatchIndex` for the
        now-current database.

        This is what actually fixes a real, reported crash: the old
        index is only ever rebuilt by :meth:`main`'s background
        generator, which does not run synchronously, so switching to a
        different Family Tree left it holding handles from the
        *previous* database until the next background index finished.
        If anything selected a surname row in that window - including
        this gramplet's own :meth:`_focus_active_person`, called from
        :meth:`db_changed` - :meth:`cb_surname_selected` would look up
        one of those stale handles in the *new*, already-current
        database and raise ``HandleError``, an unhandled exception.
        Calling this first thing in :meth:`db_changed`, before
        anything else touches the database, means there is nothing
        stale left for that to happen to.

        Unlike :meth:`_clear_matches` alone, this is only safe to call
        when the index itself is actually meant to be discarded (a
        database switch) - not from :meth:`cb_name_changed`'s normal
        "re-query the same, still-valid index for a different typed
        name" path, which would otherwise wipe the very index it is
        about to read from moments later.
        """
        self._clear_matches()
        self._index = FuzzyMatchIndex(self.dbstate.db)

    @staticmethod
    @contextlib.contextmanager
    def _blocked_selection_handlers(tree_view: Gtk.TreeView, handler_id: int):
        """
        Block ``handler_id`` on ``tree_view``'s selection for the
        duration of the ``with`` block, via GObject's own
        ``handler_block``/``handler_unblock``, rather than a
        gramplet-tracked flag the handler would have to remember to
        check.

        :param tree_view: The :class:`Gtk.TreeView` whose selection
            handler should be blocked.
        :param handler_id: The handler id returned by the original
            ``connect()`` call.
        """
        selection = tree_view.get_selection()
        selection.handler_block(handler_id)
        try:
            yield
        finally:
            selection.handler_unblock(handler_id)

    def cb_surname_selected(self, selection: Gtk.TreeSelection) -> None:
        """
        Populate the right Matches column with every person covered by
        the row selected in the left column, sorted by given name
        (locale-aware), then birth date, then death date, then Gramps
        ID - not by surname text, so people interleave by name/age
        rather than being grouped apart whenever their surname text
        happens to differ (most visibly: a compound/double surname vs.
        a plain one, which would otherwise read as men and women being
        segregated by which surname line was compound). See
        :func:`fuzzy_match_display.person_sort_key`.

        The selected row is either an individual surname (its own raw
        surname in column 1) or a top-level "All <code>" row (column 1
        is ``""``) - in the latter case, every surname :attr:`_index`
        currently files under that row's code (column 2) is shown
        together, not just one. Either way this uses the pre-computed
        surname -> person handles lookup built by :meth:`main`, so this
        is a dictionary lookup plus one pass over the relevant people,
        not a fresh database scan. The right column's own selection
        handler is blocked while it's rebuilt - see :meth:`_clear_matches`
        for why clearing/filling a store needs this even when no
        explicit ``select_path`` call is involved.

        Whoever was selected in the right column before this rebuild
        is restored afterward - exactly, if they're still part of the
        newly-selected group (e.g. switching from a surname to its
        "All <code>" parent, or back), otherwise to the closest row by
        sort position (e.g. switching to a surname that person doesn't
        carry) - see :meth:`_restore_person_selection`. Without this, a
        left-column selection change would otherwise leave the right
        column looking like nobody's selected at all, even though the
        person you were just looking at is (usually) still right there
        in the new list.

        :param selection: The left column's :class:`Gtk.TreeSelection`
            that emitted the signal.
        """
        previous_handle, previous_sort_key = self._get_selected_person_info()

        model, tree_iter = selection.get_selected()
        with self._blocked_selection_handlers(
            self.person_view, self._person_selection_handler_id
        ):
            self.person_store.clear()
            if tree_iter is None:
                return

            surname = model[tree_iter][1]
            code = model[tree_iter][2]
            surnames_to_show = (
                [surname] if surname else self._index.find_surnames_for_code(code)
            )

            db = self.dbstate.db
            rows = []
            for one_surname in surnames_to_show:
                for handle in self._index.find_people(one_surname):
                    try:
                        person = db.get_person_from_handle(handle)
                    except HandleError:
                        # The index can be briefly stale right after a
                        # database switch, before main() has rebuilt it -
                        # see db_changed(), which now clears this index
                        # synchronously for exactly this reason. Kept as
                        # a defensive fallback (skip this one handle
                        # rather than crash the whole gramplet) rather
                        # than relied on as the primary fix, since
                        # get_person_from_handle raises here rather than
                        # returning None, unlike what an earlier version
                        # of this method assumed.
                        continue
                    rows.append(
                        (person_sort_key(db, person), format_person(db, person), handle)
                    )
            rows.sort(key=lambda row: row[0])

            paths_by_handle = {}
            sort_keys_with_paths = []
            for sort_key, display, handle in rows:
                row_iter = self.person_store.append([display, handle, _WEIGHT_NORMAL])
                path = self.person_store.get_path(row_iter)
                paths_by_handle[handle] = path
                sort_keys_with_paths.append((sort_key, path))

        self._restore_person_selection(
            previous_handle, previous_sort_key, paths_by_handle, sort_keys_with_paths
        )

    def _get_selected_person_info(self):
        """
        Return ``(handle, sort_key)`` for whichever row is currently
        selected in the right Matches column, or ``(None, None)`` if
        nothing is. Called by :meth:`cb_surname_selected` before it
        clears :attr:`person_store` for a newly-selected left-column
        row, so that selection can be restored afterward - see
        :meth:`_restore_person_selection`.

        :returns: ``(handle, sort_key)``; ``sort_key`` is None if the
            handle no longer resolves to a person (deleted between the
            click and this call).
        """
        model, tree_iter = self.person_view.get_selection().get_selected()
        if tree_iter is None:
            return None, None
        handle = model[tree_iter][1]
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
        except HandleError:
            return handle, None
        return handle, person_sort_key(self.dbstate.db, person)

    def _restore_person_selection(
        self, previous_handle, previous_sort_key, paths_by_handle, sort_keys_with_paths
    ) -> None:
        """
        Reselect whichever person was selected in the right Matches
        column before the left column's selection changed (see
        :meth:`_get_selected_person_info`, called just before the
        rebuild), so switching between an "All <code>" row and one of
        its surnames - or between two different surnames - doesn't
        lose track of who was selected.

        If ``previous_handle`` isn't part of the freshly-rebuilt list
        (the newly-selected surname doesn't include that person), this
        does *not* select a different person instead - doing so would
        make that different person the active person too (see
        :meth:`cb_person_selected`), an unrelated, surprising side
        effect of merely browsing the left column. Instead, whichever
        row sorts closest to where they would have been - via the same
        ``bisect_left`` "closest at or after this point" approach
        :meth:`_select_nearest_person_by_given_name` uses - is bolded
        (:data:`_WEIGHT_BOLD`) and centered, without selecting it. That
        boldface is cleared again the moment the user actually selects
        a row - see :meth:`cb_person_selected`.

        A no-op if nothing was selected beforehand, or the new list is
        empty.

        :param previous_handle: The handle that was selected before,
            or None.
        :param previous_sort_key: That person's own
            :func:`fuzzy_match_display.person_sort_key`, or None (also
            None if they no longer resolve to a person at all).
        :param paths_by_handle: ``{handle: path}`` for every row just
            inserted into :attr:`person_store`.
        :param sort_keys_with_paths: ``[(sort_key, path), ...]`` for
            every row just inserted, already in the same sorted order
            as the store itself.
        """
        if previous_handle is None:
            return

        path = paths_by_handle.get(previous_handle)
        if path is not None:
            self.person_view.get_selection().select_path(path)
            self.person_view.scroll_to_cell(path, None, True, 0.5, 0.0)
            return

        if previous_sort_key is None or not sort_keys_with_paths:
            return
        keys = [key for key, _path in sort_keys_with_paths]
        index = min(bisect_left(keys, previous_sort_key), len(sort_keys_with_paths) - 1)
        nearest_path = sort_keys_with_paths[index][1]
        self.person_store[nearest_path][2] = _WEIGHT_BOLD
        self.person_view.scroll_to_cell(nearest_path, None, True, 0.5, 0.0)

    def cb_person_selected(self, selection: Gtk.TreeSelection) -> None:
        """
        Make the selected row in the right Matches column the active
        person, via Gramps' own active-object mechanism
        (:meth:`gramps.gui.displaystate.DisplayState.set_active`).

        Two independent protections against feeding a display-side
        update back into another active-person change:

        1. :meth:`_focus_active_person` blocks this exact handler (via
           GObject's ``handler_block``/``handler_unblock``, using the
           id stored in :attr:`_person_selection_handler_id`) while it
           selects/centers a row that is already the active person, so
           a purely-visual update is never even delivered here as a
           selection-changed event.
        2. Even so, this only calls ``set_active`` when the selected
           row's handle actually differs from the current active
           person. ``DisplayState.set_active`` -> ``History.push``
           unconditionally re-emits Gramps' own ``active-changed``
           signal at the end, even when the handle is unchanged; that
           signal is what previously triggered Gramps' own recursion
           guard ("Signal recursion blocked... active-changed") when
           something reselected an already-active person from inside
           an in-progress ``active-changed`` notification.

        Also clears the "nearest match, not exactly selected" boldface
        :meth:`_restore_person_selection` may have left on a row (see
        :data:`_WEIGHT_BOLD`) - once the user actually selects a
        person here (this row or any other), that hint has served its
        purpose and would be misleading left behind on a row that no
        longer means anything special.

        :param selection: The right column's :class:`Gtk.TreeSelection`
            that emitted the signal.
        """
        for row in self.person_store:
            if row[2] != _WEIGHT_NORMAL:
                row[2] = _WEIGHT_NORMAL

        model, tree_iter = selection.get_selected()
        if tree_iter is None:
            return
        handle = model[tree_iter][1]
        if handle != self.uistate.get_active("Person"):
            self.uistate.set_active(handle, "Person")

    def cb_person_activated(
        self,
        _tree_view: Gtk.TreeView,
        path: Gtk.TreePath,
        _column: Gtk.TreeViewColumn,
    ) -> None:
        """
        Open the standard Person editor for a double-clicked (or
        otherwise activated, e.g. Enter-key) row in the right Matches
        column.

        :param _tree_view: The right column's :class:`Gtk.TreeView`
            that emitted the signal.
        :param path: The activated row's :class:`Gtk.TreePath`.
        :param _column: The activated column.
        """
        tree_iter = self.person_store.get_iter(path)
        handle = self.person_store[tree_iter][1]
        person = self.dbstate.db.get_person_from_handle(handle)
        if person is not None:
            EditPerson(self.dbstate, self.uistate, self.track, person)

    def cb_person_drag_data_get(
        self,
        _tree_view: Gtk.TreeView,
        _context: Gdk.DragContext,
        sel_data: Gtk.SelectionData,
        _info: int,
        _time: int,
    ) -> None:
        """
        Supply the dragged person's handle when a row in the right
        Matches column is dragged, using the same "person-link"
        payload shape Gramps itself uses throughout (e.g.
        ``gramps.plugins.view.relview.RelationshipView`` and the
        Person editor's reference-list drag sources): a pickled
        ``(drag_type, id(self), handle, 0)`` tuple, set on
        ``sel_data`` under
        :attr:`gramps.gui.ddtargets.DdTargets.PERSON_LINK`'s own atom.
        Any Gramps view, gramplet, or editor field that already
        accepts a dropped person (the Relationships view, other
        Person-reference fields, and now this gramplet's own Surname
        entry - see :meth:`cb_name_drag_data_received`) can therefore
        accept a person dragged from here with no further change on
        its side.

        A no-op (``sel_data`` is left unset) if no row is currently
        selected, which simply results in no drag payload being
        available - GTK does not otherwise let a "no selection" case
        be signalled here.

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

    def _focus_active_person(self, active_person) -> None:
        """
        Select and center the active person's row in both Matches
        columns, if the background index is ready and their surname is
        currently among the left column's matches.

        This is a purely visual, display-side reaction to Gramps'
        own "the active person changed" notification (delivered
        through :meth:`db_changed`/:meth:`active_changed`/:meth:`main`,
        the Gramplet framework's built-in hooks for exactly this - see
        the class docstring). It must never itself cause another
        "active person changed" notification back into Gramps, so the
        right column's selection handler is blocked at the GObject
        level (:meth:`Gtk.TreeSelection.handler_block`) for the
        duration of the programmatic selection below, rather than
        relying on a gramplet-tracked flag the handler would have to
        remember to check.

        A no-op (returns without changing either selection) if
        ``active_person`` is None, if none of their surname pieces
        (see :func:`fuzzy_match_index.person_surnames`) is in the left
        column (for example: none phonetically match whatever is
        currently typed in the Surname field), or if the background
        rebuild in :meth:`main` has not populated the Matches columns
        yet - in the latter two cases, there is nothing yet to select.

        Checking every surname piece, not just the Surname field's own
        primary-surname text (see :meth:`_primary_surname_text`),
        matters for someone with a compound/double surname: the
        Surname field only ever holds one piece at a time, but the
        left column can be showing matches for a *different* piece the
        same person also carries - typing "McCullough" should still
        find and select someone whose primary surname piece is
        "Thompson", if "McCullough" is their other piece.

        :param active_person: The current active
            :class:`gramps.gen.lib.Person`, or None.
        """
        if active_person is None:
            return

        pieces = person_surnames(active_person)
        surname_path = None
        for row in self._iter_tree_rows(self.surname_store):
            if row[1] in pieces:
                surname_path = row.path
                break
        if surname_path is None:
            return

        # surname_store's rows are always left fully expanded (see
        # cb_name_changed), so a child surname row found above is
        # already visible/selectable without an explicit expand_row()
        # call here.
        #
        # Selecting this row triggers cb_surname_selected, which
        # repopulates person_store synchronously (GTK signal emission
        # is synchronous), so person_store already reflects this
        # surname by the time this method continues below. That
        # handler never touches the active person, so it is left
        # unblocked.
        self.surname_view.get_selection().select_path(surname_path)
        self.surname_view.scroll_to_cell(surname_path, None, True, 0.5, 0.0)

        handle = active_person.get_handle()
        with self._blocked_selection_handlers(
            self.person_view, self._person_selection_handler_id
        ):
            for row in self.person_store:
                if row[1] == handle:
                    self.person_view.get_selection().select_path(row.path)
                    self.person_view.scroll_to_cell(row.path, None, True, 0.5, 0.0)
                    break
