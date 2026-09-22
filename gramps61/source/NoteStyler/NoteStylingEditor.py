#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025      Kari Kujansuu (SuperTool script)
# Copyright (C) 2026      Brian McCullough
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

"""Note Styling Editor gramplet.

Gramplet form of Kari Kujansuu's SuperTool ``note-markup.py`` script.
Shows the :class:`~gramps.gen.lib.styledtexttag.StyledTextTag` markup on
a Note -- or, in any other note-holding category (Citation, Person,
Family, Event, Place, Source, Repository, Media), the first Note
attached to the active record there -- as a single-selectable
checklist, with buttons to strip selected markup or undo the last
change. Selecting a row scrolls the preview to, and briefly highlights,
the text that row's markup affects.

Gramps tracks a separate "active object" per category independently, so
this gramplet must know which ONE category's active object it should
actually be following, rather than checking several at once (which
would keep reflecting a stale one -- e.g. an old active Note left over
from earlier browsing -- instead of noticing that, say, the active
Family changed). It determines that once, in init(), by reading the
category of the page that's hosting it:
``self.gui.pane.pageview.navigation_type()`` -- ``self.gui.pane`` is the
GrampletBar this gramplet was created in (see
``gramps/gui/widgets/grampletbar.py``: ``GrampletBar.__init__`` stores
``self.pageview = pageview``, and constructs each gramplet's GUI
wrapper as ``TabGramplet(self, ...)``, i.e. with itself as that
wrapper's ``pane``). This stays correct even after the gramplet is
undocked into its own floating window: ``GrampletWindow`` only
reparents the existing widget, it never changes ``self.gui.pane`` --
so an undocked instance keeps tracking the category it was originally
placed in, regardless of what the main window later navigates to.

See ``help_doc_button.py`` / ``HelpDocButton.md`` (distributed
alongside this file) for the Help button in the lower-left corner: it
prefers an undocked Markdown Dash window for this addon's own
``README.md``, falling back to the ``help_url`` wiki page in a browser.

.. note::
   This file must be named ``NoteStylingEditor.py`` and this class must
   be named ``NoteStylingEditor``, to match ``fname=``/``gramplet=`` in
   ``NoteStylingEditor.gpr.py``.
"""

# pylint: disable=invalid-name
# Module filename must be CamelCase to match fname=/gramplet= in
# NoteStylingEditor.gpr.py -- Gramps' own plugin-loading convention,
# not a snake_case violation to fix.

# ------------------------
# Python modules
# ------------------------
from __future__ import annotations

import logging
from collections.abc import Iterator

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk

from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.errors import WindowActiveError
from gramps.gen.lib import Note
from gramps.gen.lib import StyledText
from gramps.gen.lib import StyledTextTag
from gramps.gen.plug import Gramplet
from gramps.gen.plug import PluginRegister
from gramps.gui.editors import EditNote
from gramps.gui.widgets import StyledTextEditor

# ------------------------
# Gramps specific
# ------------------------
from help_doc_button import add_help_button

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext

LOG = logging.getLogger(".gramplet.NoteStylingEditor")

#: Must match id= in NoteStylingEditor.gpr.py
MY_PLUGIN_ID = "Note Styling Editor"

# Settings persisted to NoteStylingEditor.ini, in this same folder --
# built with Gramps' core ConfigManager (gramps.gen.config), the same
# routine PhotoTaggingGramplet uses for its own .ini file. __file__ +
# use_plugins_path=False puts the .ini next to this module rather than
# in Gramps' shared config directory.
CONFIG = configman.register_manager(
    "NoteStylingEditor", __file__, use_plugins_path=False
)
CONFIG.register("layout.divider_position", 200)
CONFIG.register("meta.plugin_id", MY_PLUGIN_ID)
CONFIG.register("meta.schema_version", "1")
CONFIG.load()
# Stamp identifying metadata immediately, so the [meta] block is written
# out (matching PhotoTaggingGramplet.ini) even before any real setting
# has been changed from its default.
CONFIG.set("meta.plugin_id", MY_PLUGIN_ID)
CONFIG.set("meta.schema_version", "1")
CONFIG.save()

# Selecting a checklist row briefly cross-fades a highlight over the
# corresponding text in the preview pane, from these starting alpha
# values down to 0 (i.e. to the text's own normal appearance).
_HIGHLIGHT_DURATION_MS = 500
_HIGHLIGHT_STEP_MS = 40
_HIGHLIGHT_FG_ALPHA = 0.33
_HIGHLIGHT_BG_ALPHA = 0.66

# A single markup row, as produced by build_row_data(): a fresh,
# single-range StyledTextTag; its display name; its display value
# (never None -- normalized to ""); and the text snippet it covers.
RowData = tuple[StyledTextTag, str, str, str]

# Every primary-object category, besides Note itself, that can hold a
# note_list (i.e. every NoteBase subclass): navtype -> (Gramps db getter
# method name, db "-update" signal name). self.primary_navtype (set once
# in init(), see resolve_primary_navtype()) picks exactly one of these
# (or "Note" itself). Add/remove an entry here, and navtypes= in
# NoteStylingEditor.gpr.py, together to change which categories are
# supported.
_NOTE_LIST_RECORD_TYPES: dict[str, tuple[str, str]] = {
    "Citation": ("get_citation_from_handle", "citation-update"),
    "Person": ("get_person_from_handle", "person-update"),
    "Family": ("get_family_from_handle", "family-update"),
    "Event": ("get_event_from_handle", "event-update"),
    "Place": ("get_place_from_handle", "place-update"),
    "Source": ("get_source_from_handle", "source-update"),
    "Repository": ("get_repository_from_handle", "repository-update"),
    "Media": ("get_media_from_handle", "media-update"),
}


# ---------------------------------------------------------------------
#
# Pure logic
#
# Deliberately kept free of GTK/Gramps imports so it can be unit tested
# without a working PyGObject/Gramps install -- see
# test/note_styling_editor_test.py.
#
# ---------------------------------------------------------------------
def build_row_data(note: Note | None) -> list[RowData]:
    """Split note's styled-text tags into one row per (tag, range).

    row_tag is a fresh :class:`StyledTextTag` covering only that single
    range -- matching the original ``note-markup.py`` script, which
    builds one checkbox-able tag per range rather than per original
    (possibly multi-range) tag.

    :param note: the Note to read markup from, or None.
    :returns: a list of (row_tag, name, value, snippet) tuples, sorted
        by start position (subsorted by end position).
    """
    rows: list[RowData] = []
    if note is None:
        return rows
    full_text = note.get()
    for tag in note.get_styledtext().tags:
        for rng in tag.ranges:
            start, end = rng
            row_tag = StyledTextTag(tag.name, tag.value, [rng])
            rows.append((row_tag, tag.name, tag.value or "", full_text[start:end]))
    # row_tag.ranges[0] is (start, end); sorting on it directly sorts by
    # start, then subsorts by end -- exactly Python tuple-comparison
    # order, so no separate key expression is needed.
    rows.sort(key=lambda row: row[0].ranges[0])
    return rows


def kept_tags_after_clear(
    row_tags: list[StyledTextTag], checked_flags: list[bool]
) -> list[StyledTextTag]:
    """Return the row_tags NOT flagged for removal.

    A checked row is one the user wants stripped -- mirrors the
    original script's "keep it only if the checkbox is NOT active"
    filter.

    :param row_tags: one StyledTextTag per checklist row.
    :param checked_flags: the matching checkbox state for each row.
    :returns: row_tags, excluding any whose flag is True.
    """
    return [tag for tag, checked in zip(row_tags, checked_flags) if not checked]


# ---------------------------------------------------------------------
#
# NoteStylingEditor
#
# ---------------------------------------------------------------------
class NoteStylingEditor(Gramplet):
    # pylint: disable=attribute-defined-outside-init
    # Gramplet subclasses set their instance attributes in init(), the
    # framework's developer-facing constructor hook -- not Python's own
    # __init__, which Gramplet's base class already defines and uses to
    # call init() internally. Pylint doesn't know this convention.
    #
    # pylint: disable=too-many-public-methods
    # A GTK widget-holding gramplet legitimately needs one small method
    # per signal handler/refresh step (init, build_gui, db_changed,
    # main, resolve_primary_navtype, the row/preview/highlight
    # callbacks, the commit helpers); splitting further would hurt
    # clarity for no benefit (see AGENTS.md: pylint score should never
    # come at that cost).
    #
    # pylint: disable=too-many-instance-attributes
    # A GTK widget-holding gramplet legitimately needs a reference to
    # each of its widgets (paned, row_list, preview_editor, the two
    # buttons) plus its own note/selection/highlight state; splitting
    # this into further helper objects would hurt clarity for no benefit
    # (see AGENTS.md: pylint score should never come at that cost).
    """View/edit StyledText markup tags for the active Note, or the
    first Note on the active record in whichever other note-holding
    category (Citation, Person, Family, Event, Place, Source,
    Repository, Media) this instance was placed in -- determined once
    per instance by resolve_primary_navtype(), not hard-coded, since
    one .gpr.py registration with navtypes=[...] covers all of them.
    """

    def init(self) -> None:
        """External constructor -- see :meth:`Gramplet.init`."""
        self.primary_navtype: str = self.resolve_primary_navtype()
        self.note: Note | None = None
        self.note_handle: str | None = None
        self.active_record: Note | object | None = None
        self.old_tags: list[StyledTextTag] = []
        self.row_widgets: list[tuple[Gtk.CheckButton, StyledTextTag]] = []
        self._highlight_tag: Gtk.TextTag | None = None
        self._highlight_timeout_id: int | None = None
        self._highlight_start_time: int | None = None
        self.gui.WIDGET = self.build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)
        self.gui.WIDGET.show_all()

    def resolve_primary_navtype(self) -> str:
        """Determine which single category's active object this
        instance should track: "Note" itself, or a key of
        _NOTE_LIST_RECORD_TYPES.

        Reads it from the page that's hosting this gramplet --
        ``self.gui.pane`` is the GrampletBar this instance was created
        in (GrampletBar.__init__ stores ``self.pageview = pageview`` and
        builds each gramplet's GUI wrapper with itself as that wrapper's
        ``pane``); ``.pageview.navigation_type()`` gives that page's
        category, e.g. "Family". This is resolved once, here, rather
        than re-checked later, because it must stay fixed even after
        this gramplet is undocked into its own floating window --
        GrampletWindow only reparents the existing widget, it never
        changes ``self.gui.pane`` -- so an undocked instance keeps
        tracking the category it was originally placed in regardless of
        what the main window later navigates to.

        :returns: the resolved category, or "Note" as a safe fallback
            if that chain isn't available for any reason (e.g. a future
            Gramps version restructures it) or resolves to something
            this gramplet doesn't know how to handle.
        """
        try:
            navtype = self.gui.pane.pageview.navigation_type()
        except AttributeError:
            return "Note"
        if navtype != "Note" and navtype not in _NOTE_LIST_RECORD_TYPES:
            return "Note"
        return navtype

    def build_gui(self) -> Gtk.Box:
        """Build and return the gramplet's widget tree."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.info_label = Gtk.Label(label="")
        self.info_label.set_halign(Gtk.Align.START)
        outer.pack_start(self.info_label, False, False, 0)

        # A Paned's own drag handle is the resizable divider between the
        # markup checklist (top) and the preview/buttons (bottom) --
        # replacing a fixed Gtk.Separator, which can't be dragged.
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        self.paned.set_position(CONFIG.get("layout.divider_position"))
        self.paned.connect("button-release-event", self.cb_divider_released)

        self.row_list = Gtk.ListBox()
        self.row_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.row_list.connect("row-selected", self.cb_row_selected)
        tag_scroll = Gtk.ScrolledWindow()
        tag_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tag_scroll.add(self.row_list)
        self.paned.pack1(tag_scroll, resize=True, shrink=True)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.preview_editor = StyledTextEditor()
        self.preview_editor.set_editable(False)
        self.preview_editor.set_wrap_mode(Gtk.WrapMode.WORD)
        self.preview_editor.connect("button-press-event", self.cb_preview_button_press)
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        preview_scroll.add(self.preview_editor)
        bottom.pack_start(preview_scroll, True, True, 0)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        # Help button, lower-left -- see help_doc_button.py / HelpDocButton.md.
        # size=16 (not the function's 48px default, which suits a dialog's
        # own action area) to match the height of the text buttons beside it.
        pdata = PluginRegister.get_instance().get_plugin(MY_PLUGIN_ID)
        add_help_button(button_row, self.uistate, pdata, size=16)

        button_row.pack_start(Gtk.Box(), True, True, 0)  # spacer

        self.undo_button = Gtk.Button(label=_("Undo"))
        self.undo_button.connect("clicked", self.cb_undo)
        button_row.pack_end(self.undo_button, False, False, 0)

        self.clear_button = Gtk.Button(label=_("Clear Styling"))
        self.clear_button.connect("clicked", self.cb_clear_markup)
        button_row.pack_end(self.clear_button, False, False, 0)

        bottom.pack_start(button_row, False, False, 0)
        self.paned.pack2(bottom, resize=True, shrink=True)

        outer.pack_start(self.paned, True, True, 0)
        return outer

    # -- Gramplet framework hooks -----------------------------------
    # NOTE: refresh logic lives in main(), not update(). Gramplet.update()
    # is the base class's own dispatcher -- it checks whether this
    # gramplet is currently visible/the db is open before doing anything,
    # and it runs main() through a generator wrapped in a try/except that
    # reports gramplet errors without crashing all of Gramps. Overriding
    # update() directly (as an earlier revision of this file did) skips
    # both of those safeguards -- see the crash this fixes: it ran full
    # refresh logic at startup before any tree was open, and the
    # resulting exception took the whole app down instead of just this
    # gramplet.
    #
    # connect_signal() is registered here, in db_changed(), rather than
    # in init() -- matching every subclass in Gramps' own built-in
    # gramplets/notes.py (PersonNotes/EventNotes/etc. all do this).
    # db_changed() fires each time a tree actually opens, so the
    # active-changed history it binds to is the real tree's; registering
    # it once in init(), before any tree is loaded, was why this
    # gramplet wasn't correctly reflecting the already-active note.
    # connect_signal's callback is wired directly to self.update (the
    # framework's own dispatcher), not a separate active_changed()
    # method -- also matching that reference file.
    #
    # Only self.primary_navtype is connected here -- not every category
    # in _NOTE_LIST_RECORD_TYPES -- because Gramps tracks each
    # category's "active object" independently. An earlier revision
    # connected (and checked) every category from one shared instance,
    # so a stale active Note left over from browsing the Notes view
    # earlier kept winning even after switching, say, the active Family
    # elsewhere; resolve_primary_navtype() (see init()) now settles once
    # which single category this instance actually tracks.
    def db_changed(self) -> None:
        """Reconnect db and active-changed signals for the newly opened
        database -- see :meth:`Gramplet.db_changed`.
        """
        self.connect(self.dbstate.db, "note-update", self.update)
        if self.primary_navtype == "Note":
            self.connect_signal("Note", self.update)
            return
        _getter_name, signal_name = _NOTE_LIST_RECORD_TYPES[self.primary_navtype]
        self.connect(self.dbstate.db, signal_name, self.update)
        self.connect_signal(self.primary_navtype, self.update)

    def main(self) -> Iterator[bool]:
        """Refresh from the current active Note (or note-holding record).

        A generator (see the note above) so the framework's own
        try/except around its execution can catch and report a bug here
        instead of crashing the app.

        main() reruns on every relevant signal, including the
        "note-update" signal our own commit_note_tags() fires when
        Clear Styling/Undo commits a change -- unlike the original
        SuperTool script, which ran once per note and could safely
        snapshot old_tags unconditionally at the top. Snapshotting
        old_tags on every run (as an earlier revision did) meant that
        signal, from our own edit, immediately re-ran main() and
        recaptured the just-cleared tags as the new "original",
        silently breaking Undo right after its first use. old_tags is
        now only (re)captured when the active note's handle actually
        changes.

        :returns: a single-iteration generator yielding False.
        """
        self.active_record, self.note = self.get_active_record_and_note()
        handle = self.note.handle if self.note is not None else None
        if handle != self.note_handle:
            self.note_handle = handle
            self.old_tags = self.note.get_styledtext().tags[:] if self.note else []
        self.refresh_rows()
        self.refresh_preview()
        yield False

    def cb_divider_released(self, _widget: Gtk.Paned, _event: Gdk.EventButton) -> bool:
        """Persist the Paned's position as soon as a drag finishes."""
        CONFIG.set("layout.divider_position", self.paned.get_position())
        CONFIG.save()
        return False  # let the event propagate normally

    def on_save(self) -> None:
        """Framework hook, called when Gramps wants gramplets to persist
        their own state (e.g. on exit) -- belt-and-suspenders alongside
        cb_divider_released()'s save-on-drag-release.
        """
        CONFIG.set("layout.divider_position", self.paned.get_position())
        CONFIG.save()

    # -- data -------------------------------------------------------
    def get_active_record_and_note(self) -> tuple[object | None, Note | None]:
        """Resolve this instance's primary_navtype to (record, note).

        For primary_navtype == "Note", record and note are the same
        object. Otherwise record is the active Person/Family/etc. (used
        only to build the "no notes" message in refresh_rows()) and
        note is the first Note in its note_list, or None if it has none.

        :returns: (active_record, note) -- either may be None if no
            tree is open, or nothing is selected.
        """
        if not self.dbstate.db.is_open():
            return None, None
        if self.primary_navtype == "Note":
            note_handle = self.get_active("Note")
            if not note_handle:
                return None, None
            note = self.dbstate.db.get_note_from_handle(note_handle)
            return note, note
        record_handle = self.get_active(self.primary_navtype)
        if not record_handle:
            return None, None
        getter_name, _signal_name = _NOTE_LIST_RECORD_TYPES[self.primary_navtype]
        record = getattr(self.dbstate.db, getter_name)(record_handle)
        if record is None:
            return None, None
        note_list = record.get_note_list()
        note = self.dbstate.db.get_note_from_handle(note_list[0]) if note_list else None
        return record, note

    # -- GUI refresh --------------------------------------------------
    def refresh_rows(self) -> None:
        """Rebuild the checklist from self.note's current markup."""
        for child in list(self.row_list.get_children()):
            self.row_list.remove(child)
        self.row_widgets = []

        if self.note is None:
            if self.primary_navtype != "Note" and self.active_record is not None:
                self.info_label.set_text(
                    _("The %(gramps_id)s %(category)s has no Note to review.")
                    % {
                        "gramps_id": self.active_record.gramps_id,
                        "category": _(self.primary_navtype),
                    }
                )
            else:
                self.info_label.set_text(_("No note selected."))
            self.row_list.show_all()
            return

        rows = build_row_data(self.note)
        if not rows:
            self.info_label.set_text(_("This note has no styling."))
        else:
            self.info_label.set_text(
                _(
                    "Note %s -- click a row to locate it below, check it "
                    "to remove that styling:"
                )
                % self.note.gramps_id
            )

        for row_tag, name, value, snippet in rows:
            checkbutton = Gtk.CheckButton()
            checkbutton.set_active(False)
            lbl_name = Gtk.Label(label=str(name))
            lbl_name.set_halign(Gtk.Align.START)
            lbl_name.set_width_chars(10)
            lbl_value = Gtk.Label(label=str(value))
            lbl_value.set_halign(Gtk.Align.START)
            lbl_value.set_width_chars(10)
            lbl_text = Gtk.Label(label=snippet)
            lbl_text.set_halign(Gtk.Align.START)

            hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            hbox.pack_start(checkbutton, False, False, 0)
            hbox.pack_start(lbl_name, False, False, 0)
            hbox.pack_start(lbl_value, False, False, 0)
            hbox.pack_start(lbl_text, True, True, 0)

            listboxrow = Gtk.ListBoxRow()
            listboxrow.add(hbox)
            # Stashed for cb_row_selected -- an ordinary Python attribute
            # on a PyGObject widget instance, which is fine to do.
            listboxrow.markup_tag = row_tag
            # Clicking the checkbox toggles it (its own "toggled" signal,
            # unaffected by this) but GTK doesn't reliably also select
            # the row when a click lands on an interactive child widget
            # -- so select it explicitly here too, satisfying "click on
            # the row text or checkbox to select".
            checkbutton.connect("toggled", self.cb_row_checkbox_toggled, listboxrow)

            self.row_list.insert(listboxrow, -1)
            self.row_widgets.append((checkbutton, row_tag))
        self.row_list.show_all()

    def cb_row_checkbox_toggled(
        self, _checkbutton: Gtk.CheckButton, listboxrow: Gtk.ListBoxRow
    ) -> None:
        """Selecting a row by its checkbox, not just its label text."""
        self.row_list.select_row(listboxrow)

    def cb_row_selected(
        self, _list_box: Gtk.ListBox, row: Gtk.ListBoxRow | None
    ) -> None:
        """Scroll the preview to, and briefly highlight, the markup range
        for the newly selected row (row is None when selection clears).
        """
        row_tag = getattr(row, "markup_tag", None) if row is not None else None
        if row_tag is None or not row_tag.ranges:
            return
        start, end = row_tag.ranges[0]
        self.highlight_preview_range(start, end)

    def cb_preview_button_press(
        self, widget: StyledTextEditor, event: Gdk.EventButton
    ) -> bool:
        """Left-click in the preview selects the checklist row whose
        start position is closest to the click; double-click opens the
        Note Editor for the previewed note. Returns False either way, so
        the click still reaches the text view's own normal handling
        (e.g. placing the cursor).
        """
        if event.button != 1:
            return False
        buffer_x, buffer_y = widget.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(event.x), int(event.y)
        )
        result = widget.get_iter_at_location(buffer_x, buffer_y)
        # get_iter_at_location() is (found, iter) under some PyGObject
        # versions and just iter under others -- handle both.
        click_iter = result[1] if isinstance(result, tuple) else result
        if event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self.open_note_editor()
        else:
            self.select_row_nearest_offset(click_iter.get_offset())
        return False

    def select_row_nearest_offset(self, offset: int) -> None:
        """Select the checklist row whose start position is closest to
        offset (a character offset into the preview's text).
        """
        children = self.row_list.get_children()
        if not children:
            return
        nearest = min(
            children, key=lambda row: abs(row.markup_tag.ranges[0][0] - offset)
        )
        self.row_list.select_row(nearest)

    def open_note_editor(self) -> None:
        """Open Gramps' own Note Editor for the note shown in the preview."""
        if self.note is None:
            return
        try:
            EditNote(self.dbstate, self.uistate, self.track, self.note)
        except WindowActiveError:
            # An editor for this note is already open; bring-to-front is
            # handled by Gramps itself, nothing more to do here.
            pass

    def refresh_preview(self) -> None:
        """Refresh the read-only preview pane from self.note."""
        # Always route through StyledTextEditor.set_text(), which expects
        # a StyledText object -- never call
        # self.preview_editor.get_buffer().set_text() with a bare string;
        # StyledTextBuffer.set_text() unconditionally calls .get_tags()
        # on whatever it's given, which crashes on a plain str.
        self.cancel_highlight()
        styled_text = (
            self.note.get_styledtext() if self.note is not None else StyledText()
        )
        self.preview_editor.set_text(styled_text)

    def cancel_highlight(self) -> None:
        """Stop any highlight fade in progress (e.g. because the preview
        content is about to be replaced, making it meaningless).
        """
        if self._highlight_timeout_id is not None:
            GLib.source_remove(self._highlight_timeout_id)
            self._highlight_timeout_id = None
        self._highlight_tag = None

    def highlight_preview_range(self, start: int, end: int) -> None:
        """Scroll the preview to [start:end) and briefly cross-fade a
        highlight over it, from _HIGHLIGHT_FG_ALPHA/_HIGHLIGHT_BG_ALPHA
        down to 0 (i.e. to the text's own normal appearance) over
        _HIGHLIGHT_DURATION_MS -- drawing the eye to which part of the
        note the selected row's tag affects. Uses a plain Gtk.TextTag
        for this transient UI effect, separate from the note's own
        StyledTextTag markup that build_row_data()/refresh_rows() work
        with.

        :param start: character offset where the highlight begins.
        :param end: character offset where the highlight ends.
        """
        self.cancel_highlight()
        buffer = self.preview_editor.get_buffer()
        start_iter = buffer.get_iter_at_offset(start)
        end_iter = buffer.get_iter_at_offset(end)

        self.preview_editor.scroll_to_iter(start_iter, 0.1, False, 0.0, 0.0)

        tag = buffer.create_tag(
            None,
            foreground_rgba=Gdk.RGBA(0, 0, 0, _HIGHLIGHT_FG_ALPHA),
            background_rgba=Gdk.RGBA(0, 0, 0, _HIGHLIGHT_BG_ALPHA),
        )
        buffer.apply_tag(tag, start_iter, end_iter)
        self._highlight_tag = tag
        self._highlight_start_time = GLib.get_monotonic_time()
        self._highlight_timeout_id = GLib.timeout_add(
            _HIGHLIGHT_STEP_MS, self.cb_highlight_step
        )

    def cb_highlight_step(self) -> bool:
        """GLib.timeout_add callback: advance the highlight fade.

        :returns: True to keep the timeout running, False once the fade
            has completed and the tag has been removed.
        """
        elapsed_ms = (GLib.get_monotonic_time() - self._highlight_start_time) / 1000
        fraction = min(elapsed_ms / _HIGHLIGHT_DURATION_MS, 1.0)
        remaining = 1.0 - fraction
        self._highlight_tag.set_property(
            "foreground-rgba", Gdk.RGBA(0, 0, 0, _HIGHLIGHT_FG_ALPHA * remaining)
        )
        self._highlight_tag.set_property(
            "background-rgba", Gdk.RGBA(0, 0, 0, _HIGHLIGHT_BG_ALPHA * remaining)
        )
        if fraction >= 1.0:
            buffer = self.preview_editor.get_buffer()
            buffer_start, buffer_end = buffer.get_bounds()
            buffer.remove_tag(self._highlight_tag, buffer_start, buffer_end)
            self._highlight_tag = None
            self._highlight_timeout_id = None
            return False
        return True

    # -- commits ------------------------------------------------------
    def commit_note_tags(
        self, tags: list[StyledTextTag], transaction_message: str
    ) -> None:
        """Replace self.note's markup with tags and commit the change.

        :param tags: the complete new list of StyledTextTag for the note.
        :param transaction_message: shown in Gramps' undo history.
        """
        with DbTxn(transaction_message, self.dbstate.db) as trans:
            self.note.get_styledtext().tags = tags
            self.dbstate.db.commit_note(self.note, trans)
        self.refresh_rows()
        self.refresh_preview()

    def cb_clear_markup(self, _button: Gtk.Button) -> None:
        """Remove the markup for every checked row."""
        if self.note is None or not self.row_widgets:
            return
        row_tags = [tag for _cb, tag in self.row_widgets]
        checked_flags = [cb.get_active() for cb, _tag in self.row_widgets]
        kept = kept_tags_after_clear(row_tags, checked_flags)
        self.commit_note_tags(kept, _("Clear note stylings"))

    def cb_undo(self, _button: Gtk.Button) -> None:
        """Restore the markup this note had when it first became active."""
        if self.note is None:
            return
        self.commit_note_tags(self.old_tags, _("Undo note styling change"))
