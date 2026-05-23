#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough <emyoulation@yahoo.com>
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
# Generated-by: Claude Sonnet 4.6 (Anthropic) via claude.ai
# Prompts: Design a Gramps 5.2 gramplet that displays a generation-numbered
#   breadcrumb path between a Proband, Progenitor, and optional Founder.
#   Show two formats: a single-line breadcrumb and a per-generation list.
#   Provide a context menu to copy plain text or open a pre-populated Note
#   editor. Use clickable Pango links to open EditPerson/EditFamily editors.
#   Companion formatting module in BreadcrumbFormatter.py.

"""PedigreeBreadcrumbs gramplet — v0.0.5

Displays the generation-numbered breadcrumb path among up to three people:

  Proband    (descending relative)   — numeric labels  2, 3, … N  (left)
  Progenitor (immigrant / anchor)    — numeric label   1
  Founder    (old-country ancestor)  — alpha labels    A, B, C … (right)

Person-selector rows
--------------------
Each row has:
  • An editable Gramps-ID field  — type an ID and press Enter to select
  • A plain text label (not an Entry box) showing "Surname, Given  YYYY–YYYY"
    The label's EventBox is a DnD target: drop a person object onto it to select
  • A person-selector button
  • A reset / clear button

Display area (right-click for context menu)
-------------------------------------------
  Breadcrumb:       Given⁶ SURNAME; Given⁵; … Given¹ SURNAME
  Generation list:  one line per person:
                    label: Full Name  YYYY–YYYY; GrampsID

Context menu
------------
  Copy breadcrumb to clipboard
  Copy generation list to clipboard
  ─────────────────────────────────
  Open breadcrumb as new Note
  Open generation list as new Note
  Open both formats as new Note

Note creation
-------------
A new Note() is created, pre-populated with StyledText that carries:
  • Superscript on each generation label (tag name "superscript")
  • Family links on given names in the breadcrumb (tag name "link",
    value "gramps://Family/handle/{handle}")
  • Person links on GrampsID strings in the list (tag name "link",
    value "gramps://Person/handle/{handle}")

The note is opened via EditNote(dbstate, uistate, track, note) WITHOUT being
committed to the database first.  The user decides to Save or Cancel.

This is the correct workflow and avoids the data_has_changed() crash that
occurred when the note was pre-committed: that crash happened because Gramps
compared the DB-serialized tuple form with the in-memory StyledText object
via StyledText.__eq__, which expects another StyledText — not a raw tuple.
A brand-new uncommitted Note has no DB record, so no such comparison occurs.

StyledTextTag construction
--------------------------
Tags are constructed as StyledTextTag(name_string, value_string, ranges_list),
matching the form used by Gramps internally and confirmed by the N0041
SuperTool script:
  StyledTextTag("superscript", "", [(s1,e1), (s2,e2), ...])
  StyledTextTag("link", "gramps://Family/handle/XXX", [(s, e)])
  StyledTextTag("link", "gramps://Person/handle/XXX", [(s, e)])
"""

# ── Standard library ──────────────────────────────────────────────────────────
import string
import os
import sys

# ── GTK ───────────────────────────────────────────────────────────────────────
from gi.repository import Gdk, Gtk

# ── Gramps ────────────────────────────────────────────────────────────────────
from gramps.gen.plug import Gramplet
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as nd
from gramps.gen.lib import Note, NoteType, StyledText, StyledTextTag
from gramps.gui.selectors import SelectorFactory

_ = glocale.translation.gettext

# ── BreadcrumbFormatter (companion module, same plugin directory) ─────────────
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from BreadcrumbFormatter import PedigreeEntry, FormattedText, format_all  # noqa: E402

# Gramps drag-and-drop MIME type for a person handle
_DND_TYPE = "gramps/person-handle"


# =============================================================================
# Small utilities
# =============================================================================

def _handle_valid(db, handle):
    """Return True iff handle refers to an existing Person in db."""
    if not handle:
        return False
    try:
        return db.has_person_handle(handle)
    except Exception:
        return False


def _year_str(date_obj):
    """Return 4-digit year string from a Gramps Date, or ""."""
    if date_obj and not date_obj.is_empty():
        yr = date_obj.get_year()
        if yr:
            return str(yr)
    return ""


def _person_summary(db, person):
    """Return "Surname, Given  YYYY–YYYY" for the row display label."""
    if person is None:
        return ""
    pname   = person.get_primary_name()
    given   = pname.get_first_name() or ""
    surname = pname.get_primary_surname().get_surname() or ""
    name_part = f"{surname}, {given}".strip(", ")

    birth_yr = death_yr = ""
    br = person.get_birth_ref()
    if br:
        ev = db.get_event_from_handle(br.ref)
        if ev:
            birth_yr = _year_str(ev.get_date_object())
    dr = person.get_death_ref()
    if dr:
        ev = db.get_event_from_handle(dr.ref)
        if ev:
            death_yr = _year_str(ev.get_date_object())

    if birth_yr or death_yr:
        return f"{name_part}  {birth_yr}\u2013{death_yr}"
    return name_part


def _alpha_label(n):
    """Convert 1-based integer to alphabetic label: 1→A, 2→B, …, 27→AA …"""
    letters = string.ascii_uppercase
    result = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = letters[rem] + result
    return result


# =============================================================================
# Relationship path helpers
# =============================================================================

def _apply_filter(db, rank, handle, plist, pmap):
    """Walk ancestors of handle recursively; record 0-based generation rank."""
    if not handle:
        return
    person = db.get_person_from_handle(handle)
    if person is None:
        return
    plist.add(handle)
    pmap[handle] = rank
    fam_id = person.parent_family_list[0] if person.parent_family_list else None
    if not fam_id:
        return
    family = db.get_family_from_handle(fam_id)
    if family:
        _apply_filter(db, rank + 1, family.father_handle, plist, pmap)
        _apply_filter(db, rank + 1, family.mother_handle, plist, pmap)


def _desc_list(db, handle, result_set, first=True):
    """Collect all descendants of handle into result_set recursively."""
    if not first:
        result_set.add(handle)
    person = db.get_person_from_handle(handle)
    if person is None:
        return
    for fam_id in person.family_list:
        fam = db.get_family_from_handle(fam_id)
        if fam:
            for child_ref in fam.child_ref_list:
                if child_ref.ref:
                    _desc_list(db, child_ref.ref, result_set, False)


def relationship_path(db, p1_handle, p2_handle):
    """
    Return {handle: 0-based rank} for every person on the direct path
    between p1 (rank 0) and p2, via their nearest common ancestor.
    Returns empty dict when no connection is found.
    """
    first_set,  first_map  = set(), {}
    second_set, second_map = set(), {}

    _apply_filter(db, 0, p1_handle, first_set,  first_map)
    _apply_filter(db, 0, p2_handle, second_set, second_map)

    common, best_rank = [], 9_999_999
    for handle in first_set & second_set:
        r = first_map[handle]
        if r < best_rank:
            best_rank, common = r, [handle]
        elif r == best_rank:
            common.append(handle)

    if not common:
        return {}

    path1, path2 = {p1_handle}, {p2_handle}
    for handle in common:
        desc = set()
        _desc_list(db, handle, desc, True)
        path1.update(desc & first_set)
        path2.update(desc & second_set)

    result = {}
    for h in path1 | path2 | set(common):
        rank = first_map.get(h, second_map.get(h, 0))
        result[h] = rank
    return result


def _is_ancestor(db, ancestor_handle, descendant_handle):
    """Return True iff ancestor_handle is a direct ancestor of descendant_handle."""
    visited, queue = set(), [descendant_handle]
    while queue:
        h = queue.pop()
        if h in visited:
            continue
        visited.add(h)
        if h == ancestor_handle:
            return True
        p = db.get_person_from_handle(h)
        if p is None:
            continue
        for fam_id in p.parent_family_list:
            fam = db.get_family_from_handle(fam_id)
            if fam:
                if fam.father_handle:
                    queue.append(fam.father_handle)
                if fam.mother_handle:
                    queue.append(fam.mother_handle)
    return False


# =============================================================================
# PedigreeEntry list builder
# =============================================================================

def _first_parent_family_handle(db, handle):
    """Return the handle of the person's first parent family, or ""."""
    person = db.get_person_from_handle(handle)
    if person and person.parent_family_list:
        return person.parent_family_list[0]
    return ""


def _make_entry(db, handle, label):
    """Build a PedigreeEntry for handle with the given label string."""
    person = db.get_person_from_handle(handle)
    if person is None:
        return None

    pname  = person.get_primary_name()
    given  = pname.get_first_name() or ""
    # Include name suffix (Jr., Sr., III, etc.) in the given-name field so that
    # the breadcrumb link covers the complete name token before the label.
    suffix = pname.get_suffix() or ""
    if suffix:
        given = (given + ", " + suffix).strip(", ")
    surname = pname.get_primary_surname().get_surname() or ""

    birth_yr = death_yr = ""
    br = person.get_birth_ref()
    if br:
        ev = db.get_event_from_handle(br.ref)
        if ev:
            birth_yr = _year_str(ev.get_date_object())
    dr = person.get_death_ref()
    if dr:
        ev = db.get_event_from_handle(dr.ref)
        if ev:
            death_yr = _year_str(ev.get_date_object())

    return PedigreeEntry(
        handle        = handle,
        family_handle = _first_parent_family_handle(db, handle),
        gramps_id     = person.get_gramps_id() or "",
        label         = label,
        given         = given,
        surname       = surname,
        name_full     = nd.display(person),
        birth_year    = birth_yr,
        death_year    = death_yr,
    )


def build_pedigree_entries(db, proband_path, progenitor_handle, founder_path=None):
    """
    Convert raw path dicts into an ordered list of PedigreeEntry records,
    youngest (proband) first, oldest (founder) last.
    """
    entries = []

    if proband_path:
        max_rank = max(proband_path.values())
        for handle, rank in sorted(proband_path.items(),
                                   key=lambda kv: -(max_rank + 1 - kv[1])):
            label = str(max_rank + 1 - rank)
            entry = _make_entry(db, handle, label)
            if entry:
                entries.append(entry)

    if founder_path:
        for handle, rank in sorted(founder_path.items(), key=lambda kv: kv[1]):
            if handle == progenitor_handle or rank < 1:
                continue
            label = _alpha_label(rank)
            entry = _make_entry(db, handle, label)
            if entry:
                entries.append(entry)

    return entries


# =============================================================================
# StyledText assembly
# =============================================================================

def _build_styled_text(formatted):
    """
    Convert a BreadcrumbFormatter ``FormattedText`` into a Gramps ``StyledText``.

    Tag construction uses string names as confirmed by the Gramps SuperTool
    script in N0041::

        StyledTextTag("superscript", "", [(s1,e1), (s2,e2), ...])
        StyledTextTag("link", "gramps://…/handle/XXX", [(s, e)])

    One superscript StyledTextTag covers all label ranges.
    One LINK StyledTextTag per person (each has a distinct URL).

    Parameters
    ----------
    formatted : FormattedText

    Returns
    -------
    StyledText
    """
    tags = []

    # Single "superscript" tag covering all label positions
    if formatted.sup_ranges:
        tags.append(StyledTextTag("superscript", "", formatted.sup_ranges))

    # One "link" tag per person/family (each needs its own URL value)
    for url, start, end in formatted.link_ranges:
        tags.append(StyledTextTag("link", url, [(start, end)]))

    return StyledText(formatted.plain, tags)


def _merge_formatted(fmt_a, fmt_b, separator="\n\n"):
    """
    Concatenate two ``FormattedText`` objects with *separator*, adjusting
    all character offsets in the second block accordingly.

    Returns a new ``FormattedText``.
    """
    offset = len(fmt_a.plain) + len(separator)

    sup_ranges = list(fmt_a.sup_ranges) + [
        (s + offset, e + offset) for s, e in fmt_b.sup_ranges
    ]
    link_ranges = list(fmt_a.link_ranges) + [
        (url, s + offset, e + offset) for url, s, e in fmt_b.link_ranges
    ]
    plain = fmt_a.plain + separator + fmt_b.plain

    return FormattedText(plain, sup_ranges, link_ranges)


# =============================================================================
# Note editor helper
# =============================================================================

def _open_note_editor(dbstate, uistate, track, styled_text, error_cb):
    """
    Open a new Note editor pre-populated with *styled_text*.

    The Note is NOT committed to the database before opening.  The user
    decides to Save (which commits it) or Cancel (which discards it).

    Parameters
    ----------
    dbstate      : Gramps DbState
    uistate      : Gramps UiState
    track        : gramplet track list
    styled_text  : StyledText — content to show in the editor body
    error_cb     : callable(msg) — called on exception
    """
    try:
        note = Note()
        note.set_type(NoteType.GENERAL)
        note.set(styled_text)
        from gramps.gui.editors import EditNote
        EditNote(dbstate, uistate, track, note)
    except Exception as exc:
        error_cb(_("Could not open Note editor: %s") % str(exc))


# =============================================================================
# Pango markup renderer  (gramplet display only — never stored in notes)
# =============================================================================

def _entries_to_pango(entries):
    """
    Render the breadcrumb as a Pango markup string for on-screen display.

    Uses:
      ``<a href="gramps://Family/handle/XXX">given</a>`` — clickable given name
        linking to the person's parent family (omitted when no family handle).
      ``<sup>label</sup>``  — superscript generation marker after given name.
      ``<span font_variant="smallcaps">SURNAME</span>``  — surname when shown.

    The ``activate-link`` signal on the Gtk.Label handles navigation.
    This markup must never be stored in Note._string.
    """
    from html import escape

    def _small_caps(text):
        return f'<span font_variant="smallcaps">{escape(text)}</span>'

    def _sup(text):
        return f'<sup>{escape(str(text))}</sup>'

    def _link(text, url):
        return f'<a href="{escape(url)}">{escape(text)}</a>'

    if not entries:
        return ""

    parts    = []
    prev_sn  = ""
    last_idx = len(entries) - 1

    for idx, e in enumerate(entries):
        show_sn = (idx == last_idx) or (e.surname != prev_sn)
        prev_sn = e.surname

        # Given name — wrap in a Family link when available
        if e.family_handle:
            given_markup = _link(
                e.given,
                f"gramps://Family/handle/{e.family_handle}",
            )
        else:
            given_markup = escape(e.given)

        markup = given_markup + _sup(e.label)
        if show_sn and e.surname:
            markup += " " + _small_caps(e.surname)
        parts.append(markup)

    return "; ".join(parts)


def _entries_to_list_pango(entries):
    """
    Render the generation list as a Pango markup string for on-screen display.

    Each line:  ``label: Full Name  YYYY–YYYY; <a href="gramps://Person/…">ID</a>``

    The GrampsID at line end is a clickable Person link.
    The ``activate-link`` signal on the Gtk.Label handles navigation.
    """
    from html import escape

    def _link(text, url):
        return f'<a href="{escape(url)}">{escape(text)}</a>'

    if not entries:
        return ""

    lines = []
    for e in entries:
        span = ""
        if e.birth_year or e.death_year:
            span = f"  {e.birth_year}\u2013{e.death_year}"
        person_link = _link(
            e.gramps_id,
            f"gramps://Person/handle/{e.handle}",
        )
        line = f"{escape(e.label)}: {escape(e.name_full)}{escape(span)}; {person_link}"
        lines.append(line)

    return "\n".join(lines)


# =============================================================================
# Gramplet
# =============================================================================

class PedigreeBreadcrumbs(Gramplet):
    """
    Shows the breadcrumb path and generation list for up to three people.

    Slots
    -----
    1 = Progenitor  — defaults to Home Person;   numeric label 1
    2 = Proband     — auto-follows Active Person; numeric labels 2…N
    3 = Founder     — optional;                  alpha labels A, B, C…
    """

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self):
        self._p1_handle = None
        self._p2_handle = None
        self._p3_handle = None
        self._p2_locked = False
        self._current_entries = []

        root = self._build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(root)
        root.show_all()

    def db_changed(self):
        db = self.dbstate.db
        self.connect(db, "person-update", self._on_db_change)
        self.connect(db, "person-delete", self._on_db_change)
        self.connect(db, "family-update", self._on_db_change)
        self.connect(db, "family-delete", self._on_db_change)
        self.connect_signal("Person", self._on_active_person_changed)
        self._validate_handles()
        self.update()

    def _on_db_change(self, *_args):
        self._validate_handles()
        self.update()

    def active_changed(self, handle):
        if not self._p2_locked:
            db = self.dbstate.db
            if handle and _handle_valid(db, handle):
                person = db.get_person_from_handle(handle)
                if person:
                    self._set_person(2, person, lock=False)
        self.update()

    def _on_active_person_changed(self, handle):
        self.active_changed(handle)

    def main(self):
        db = self.dbstate.db

        if not db.is_open():
            self._show_info(_("No database is open."))
            yield False
            return
        if db.get_number_of_people() == 0:
            self._show_info(_("The database contains no people."))
            yield False
            return

        if self._p1_handle is None:
            home = db.get_default_person()
            if home:
                self._set_person(1, home)

        if self._p2_handle is None:
            ah = self.get_active("Person")
            if ah and _handle_valid(db, ah):
                person = db.get_person_from_handle(ah)
                if person:
                    self._set_person(2, person, lock=False)

        self._refresh_result()
        yield False

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_handles(self):
        db = self.dbstate.db
        for slot, attr in [(1, "_p1_handle"), (2, "_p2_handle"), (3, "_p3_handle")]:
            h = getattr(self, attr)
            if h is not None and not _handle_valid(db, h):
                setattr(self, attr, None)
                self._clear_row_widgets(slot)

    def _clear_row_widgets(self, slot):
        mapping = {
            1: (self._p1_id_entry, self._p1_name_label),
            2: (self._p2_id_entry, self._p2_name_label),
            3: (self._p3_id_entry, self._p3_name_label),
        }
        if slot in mapping:
            id_entry, name_label = mapping[slot]
            id_entry.set_text("")
            name_label.set_text("")

    # ── GUI construction ──────────────────────────────────────────────────────

    def _build_gui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for m in ("margin_start", "margin_end", "margin_top", "margin_bottom"):
            setattr(vbox.props, m, 6)

        p2_row = self._build_person_row(
            slot=2, row_label=_("Proband:"),
            reset_icon="go-jump",
            reset_tip=_("Reset to Active Person (re-enables auto-follow)"),
            reset_cb=self._on_active_p2,
            select_tip=_("Select Proband"),
            select_cb=self._on_select_p2,
        )
        p1_row = self._build_person_row(
            slot=1, row_label=_("Progenitor:"),
            reset_icon="go-home",
            reset_tip=_("Reset to Home Person"),
            reset_cb=self._on_home_p1,
            select_tip=_("Select Progenitor"),
            select_cb=self._on_select_p1,
        )
        p3_row = self._build_person_row(
            slot=3, row_label=_("Founder:"),
            reset_icon="edit-clear",
            reset_tip=_("Clear Founder"),
            reset_cb=self._on_clear_p3,
            select_tip=_("Select Founder"),
            select_cb=self._on_select_p3,
        )

        vbox.pack_start(p2_row, False, False, 0)
        vbox.pack_start(p1_row, False, False, 0)
        vbox.pack_start(p3_row, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 4)

        # Breadcrumb display
        crumb_hdr = Gtk.Label()
        crumb_hdr.set_markup(f"<b>{_('Breadcrumb:')}</b>")
        crumb_hdr.set_halign(Gtk.Align.START)

        self._breadcrumb_label = Gtk.Label()
        self._breadcrumb_label.set_use_markup(True)
        self._breadcrumb_label.set_line_wrap(True)
        self._breadcrumb_label.set_halign(Gtk.Align.START)
        self._breadcrumb_label.set_valign(Gtk.Align.START)
        self._breadcrumb_label.set_selectable(True)
        self._breadcrumb_label.set_track_visited_links(False)
        self._breadcrumb_label.set_margin_bottom(4)
        self._breadcrumb_label.connect("button-press-event", self._on_result_click)
        self._breadcrumb_label.connect("activate-link", self._on_link_activated)

        # Generation list display
        list_hdr = Gtk.Label()
        list_hdr.set_markup(f"<b>{_('Generation list:')}</b>")
        list_hdr.set_halign(Gtk.Align.START)

        self._list_label = Gtk.Label()
        self._list_label.set_use_markup(True)
        self._list_label.set_line_wrap(False)
        self._list_label.set_halign(Gtk.Align.START)
        self._list_label.set_valign(Gtk.Align.START)
        self._list_label.set_selectable(True)
        self._list_label.set_track_visited_links(False)
        self._list_label.connect("button-press-event", self._on_result_click)
        self._list_label.connect("activate-link", self._on_link_activated)

        vbox.pack_start(crumb_hdr,              False, False, 0)
        vbox.pack_start(self._breadcrumb_label, False, False, 0)
        vbox.pack_start(list_hdr,               False, False, 0)
        vbox.pack_start(self._list_label,        True,  True,  0)
        return vbox

    def _build_person_row(self, slot, row_label,
                          reset_icon, reset_tip, reset_cb,
                          select_tip, select_cb):
        """
        Build one person-selector row.

        Layout:
          [Label]  [ID entry]  [Name  YYYY–YYYY]  [Select btn]  [Reset btn]

        The name display is a plain Gtk.Label (not an Entry) to avoid the
        sunken-box appearance that implies editability.  It is wrapped in an
        EventBox so it can receive DnD events.
        """
        row = Gtk.Box(spacing=4)

        lbl = Gtk.Label(label=row_label)
        lbl.set_width_chars(12)
        lbl.set_halign(Gtk.Align.END)
        lbl.set_xalign(1.0)

        # Editable ID field: type a Gramps ID and press Enter
        id_entry = Gtk.Entry()
        id_entry.set_width_chars(8)
        id_entry.set_max_width_chars(12)
        id_entry.set_placeholder_text(_("ID"))
        id_entry.set_tooltip_text(_("Type a Gramps ID and press Enter"))
        id_entry.connect("activate", self._make_id_activate_cb(slot))

        # Read-only name display — plain label, no Entry box
        name_label = Gtk.Label()
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3)      # PANGO_ELLIPSIZE_END
        name_label.set_hexpand(True)
        name_label.set_tooltip_text(_("Drop a person here to select"))

        # EventBox wrapper so the label can receive DnD drops
        name_box = Gtk.EventBox()
        name_box.add(name_label)
        name_box.set_hexpand(True)

        sel_btn = Gtk.Button()
        sel_btn.set_image(
            Gtk.Image.new_from_icon_name("gramps-person", Gtk.IconSize.BUTTON))
        sel_btn.set_tooltip_text(select_tip)
        sel_btn.connect("clicked", select_cb)

        rst_btn = Gtk.Button()
        rst_btn.set_image(
            Gtk.Image.new_from_icon_name(reset_icon, Gtk.IconSize.BUTTON))
        rst_btn.set_tooltip_text(reset_tip)
        rst_btn.connect("clicked", reset_cb)

        row.pack_start(lbl,      False, False, 0)
        row.pack_start(id_entry, False, False, 0)
        row.pack_start(name_box, True,  True,  0)
        row.pack_start(sel_btn,  False, False, 0)
        row.pack_start(rst_btn,  False, False, 0)

        # Register DnD on both the outer row and the name EventBox
        dnd_cb = self._make_dnd_cb(slot)
        for widget in (row, name_box):
            widget.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
            tl = Gtk.TargetList.new([])
            tl.add(Gdk.atom_intern(_DND_TYPE, False), 0, slot)
            widget.drag_dest_set_target_list(tl)
            widget.connect("drag-data-received", dnd_cb)

        # Store widget refs by slot number
        if slot == 1:
            self._p1_id_entry   = id_entry
            self._p1_name_label = name_label
        elif slot == 2:
            self._p2_id_entry   = id_entry
            self._p2_name_label = name_label
        elif slot == 3:
            self._p3_id_entry   = id_entry
            self._p3_name_label = name_label

        return row

    # ── ID-entry activate callback (factory) ─────────────────────────────────

    def _make_id_activate_cb(self, slot):
        """Return a callback that looks up the typed ID and selects the person."""
        def _cb(entry):
            raw = entry.get_text().strip()
            if not raw:
                return
            db = self.dbstate.db
            result = db.get_person_from_gramps_id(raw)
            if result is None:
                self._show_error(_('No person found with ID "%s".') % raw)
                return
            person = result if hasattr(result, "handle") \
                else db.get_person_from_handle(result)
            if person is None:
                self._show_error(_('No person found with ID "%s".') % raw)
                return
            # For Proband: typing an ID locks auto-follow
            self._set_person(slot, person, lock=(slot == 2))
            self._refresh_result()
        return _cb

    # ── DnD callback (factory) ────────────────────────────────────────────────

    def _make_dnd_cb(self, slot):
        """Return a drag-data-received handler that sets the person for slot."""
        def _cb(widget, drag_ctx, x, y, selection, info, timestamp):
            raw = selection.get_data()
            if not raw:
                drag_ctx.finish(False, False, timestamp)
                return
            handle = raw.decode("utf-8").strip()
            db = self.dbstate.db
            if not _handle_valid(db, handle):
                drag_ctx.finish(False, False, timestamp)
                return
            person = db.get_person_from_handle(handle)
            if person:
                # Dropping onto Proband row locks auto-follow
                self._set_person(slot, person, lock=(slot == 2))
                self._refresh_result()
                drag_ctx.finish(True, False, timestamp)
            else:
                drag_ctx.finish(False, False, timestamp)
        return _cb

    # ── Person selection callbacks ────────────────────────────────────────────

    def _open_selector(self, title):
        SelectPerson = SelectorFactory("Person")
        return SelectPerson(
            self.dbstate, self.uistate, self.track,
            title=title, show_search_bar=True,
        ).run()

    def _on_select_p1(self, _btn):
        p = self._open_selector(_("Select Progenitor"))
        if p:
            self._set_person(1, p)
            self._refresh_result()

    def _on_select_p2(self, _btn):
        p = self._open_selector(_("Select Proband"))
        if p:
            self._set_person(2, p, lock=True)
            self._refresh_result()

    def _on_select_p3(self, _btn):
        p = self._open_selector(_("Select Founder"))
        if p:
            self._set_person(3, p)
            self._refresh_result()

    def _on_home_p1(self, _btn):
        home = self.dbstate.db.get_default_person()
        if home:
            self._set_person(1, home)
            self._refresh_result()
        else:
            self._show_info(_("No Home Person is set in this database."))

    def _on_active_p2(self, _btn):
        self._p2_locked = False
        ah = self.get_active("Person")
        db = self.dbstate.db
        if ah and _handle_valid(db, ah):
            person = db.get_person_from_handle(ah)
            if person:
                self._set_person(2, person, lock=False)
                self._refresh_result()
                return
        self._show_info(_("No valid active person to reset to."))

    def _on_clear_p3(self, _btn):
        self._p3_handle = None
        self._p3_id_entry.set_text("")
        self._p3_name_label.set_text("")
        self._current_entries = []
        self._refresh_result()

    # ── State helpers ─────────────────────────────────────────────────────────

    def _set_person(self, slot, person, lock=True):
        db  = self.dbstate.db
        gid = person.get_gramps_id() or ""
        txt = _person_summary(db, person)
        if slot == 1:
            self._p1_handle = person.handle
            self._p1_id_entry.set_text(gid)
            self._p1_name_label.set_text(txt)
        elif slot == 2:
            self._p2_handle = person.handle
            self._p2_id_entry.set_text(gid)
            self._p2_name_label.set_text(txt)
            if lock:
                self._p2_locked = True
        elif slot == 3:
            self._p3_handle = person.handle
            self._p3_id_entry.set_text(gid)
            self._p3_name_label.set_text(txt)

    # ── Link navigation ───────────────────────────────────────────────────────

    def _on_link_activated(self, _label, uri):
        """
        Handle clicks on ``gramps://Type/handle/XXX`` links in either display label.

        Opens the appropriate Gramps object editor (EditPerson or EditFamily)
        for the clicked link rather than changing the active navigation object.
        This works regardless of which view is currently active.

        Returns True to prevent GTK from trying to open the URI in a browser.
        """
        try:
            # URI form: "gramps://ObjectType/handle/HANDLESTRING"
            if not uri.startswith("gramps://"):
                return False
            parts = uri[len("gramps://"):].split("/")
            # parts = ["Person"|"Family", "handle", "HANDLESTRING"]
            if len(parts) != 3 or parts[1] != "handle":
                return True
            obj_type = parts[0]
            handle   = parts[2]
            db = self.dbstate.db
            if obj_type == "Person":
                person = db.get_person_from_handle(handle)
                if person:
                    from gramps.gui.editors import EditPerson
                    EditPerson(self.dbstate, self.uistate, self.track, person)
            elif obj_type == "Family":
                family = db.get_family_from_handle(handle)
                if family:
                    from gramps.gui.editors import EditFamily
                    EditFamily(self.dbstate, self.uistate, self.track, family)
        except Exception:
            pass
        return True   # always suppress default URI handler

    def _show_info(self, msg):
        from html import escape
        self._breadcrumb_label.set_markup(f"<i>{escape(msg)}</i>")
        self._list_label.set_markup("")

    def _show_error(self, msg):
        from html import escape
        self._breadcrumb_label.set_markup(
            f'<span foreground="red"><i>{escape(msg)}</i></span>')
        self._list_label.set_markup("")

    # ── Core refresh ──────────────────────────────────────────────────────────

    def _refresh_result(self):
        db = self.dbstate.db

        if not db.is_open():
            self._show_info(_("No database is open."))
            return
        if db.get_number_of_people() == 0:
            self._show_info(_("The database contains no people."))
            return
        if not self._p1_handle:
            self._show_info(_(
                "No Progenitor selected. "
                "Use the selector button or set a Home Person."))
            return
        if not self._p2_handle:
            self._show_info(_(
                "No Proband selected. "
                "Navigate to a person or use the selector button."))
            return

        p1 = db.get_person_from_handle(self._p1_handle)
        p2 = db.get_person_from_handle(self._p2_handle)

        if p1 is None:
            self._show_error(_("Progenitor no longer exists — please re-select."))
            self._p1_handle = None
            self._clear_row_widgets(1)
            return
        if p2 is None:
            self._show_error(_("Proband no longer exists — please re-select."))
            self._p2_handle = None
            self._clear_row_widgets(2)
            return
        if self._p1_handle == self._p2_handle:
            self._show_info(_("Progenitor and Proband are the same person."))
            return
        if not _is_ancestor(db, self._p1_handle, self._p2_handle):
            self._show_info(_(
                "{progenitor} is not a direct ancestor of {proband}. "
                "Only direct ancestor \u2192 descendant paths are supported."
            ).format(progenitor=nd.display(p1), proband=nd.display(p2)))
            return

        proband_path = relationship_path(db, self._p2_handle, self._p1_handle)
        if not proband_path:
            self._show_info(_(
                "Could not compute a path between %s and %s."
            ) % (nd.display(p2), nd.display(p1)))
            return

        founder_path = None
        if self._p3_handle:
            p3 = db.get_person_from_handle(self._p3_handle)
            if p3 is None:
                self._show_error(_("Founder no longer exists — please re-select."))
                self._p3_handle = None
                self._clear_row_widgets(3)
            elif not _is_ancestor(db, self._p3_handle, self._p1_handle):
                self._show_error(_(
                    "{founder} is not a direct ancestor of Progenitor {progenitor}."
                ).format(founder=nd.display(p3), progenitor=nd.display(p1)))
            else:
                raw = relationship_path(db, self._p1_handle, self._p3_handle)
                if raw:
                    founder_path = {h: r for h, r in raw.items() if r > 0}

        entries = build_pedigree_entries(
            db, proband_path, self._p1_handle, founder_path)
        self._current_entries = entries

        if not entries:
            self._show_info(_("No path entries found."))
            return

        # Breadcrumb: Pango markup (smallcaps surnames, superscript labels, Family links)
        self._breadcrumb_label.set_markup(_entries_to_pango(entries))

        # Generation list: Pango markup (Person links on GrampsIDs)
        self._list_label.set_markup(_entries_to_list_pango(entries))

    # ── Context menu ──────────────────────────────────────────────────────────

    def _on_result_click(self, _widget, event):
        if event.button != 3:
            return False
        if not self._current_entries:
            return False

        menu = Gtk.Menu()

        def _item(label, cb):
            it = Gtk.MenuItem(label=label)
            it.connect("activate", cb)
            menu.append(it)

        _item(_("Copy breadcrumb to clipboard"),      self._on_copy_crumb)
        _item(_("Copy generation list to clipboard"), self._on_copy_list)
        menu.append(Gtk.SeparatorMenuItem())
        _item(_("Open breadcrumb as new Note"),       self._on_note_crumb)
        _item(_("Open generation list as new Note"),  self._on_note_list)
        _item(_("Open both formats as new Note"),     self._on_note_both)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    # ── Clipboard actions ─────────────────────────────────────────────────────

    def _on_copy_crumb(self, _item):
        fmt = format_all(self._current_entries)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(
            fmt["breadcrumb_plain"], -1)

    def _on_copy_list(self, _item):
        fmt = format_all(self._current_entries)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(
            fmt["list_plain"], -1)

    # ── Note actions ──────────────────────────────────────────────────────────

    def _on_note_crumb(self, _item):
        fmt = format_all(self._current_entries)
        _open_note_editor(
            self.dbstate, self.uistate, self.track,
            _build_styled_text(fmt["breadcrumb_tagged"]),
            self._show_error,
        )

    def _on_note_list(self, _item):
        fmt = format_all(self._current_entries)
        _open_note_editor(
            self.dbstate, self.uistate, self.track,
            _build_styled_text(fmt["list_tagged"]),
            self._show_error,
        )

    def _on_note_both(self, _item):
        fmt = format_all(self._current_entries)
        merged = _merge_formatted(fmt["breadcrumb_tagged"], fmt["list_tagged"],
                                  separator="\n\n")
        _open_note_editor(
            self.dbstate, self.uistate, self.track,
            _build_styled_text(merged),
            self._show_error,
        )
