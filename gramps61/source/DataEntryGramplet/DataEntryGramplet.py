#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2007-2009  Douglas S. Blank <doug.blank@gmail.com>
# Copyright (C) 2011       Gary Burton
# Copyright (C) 2026       Brian McCullough
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
Data Entry Gramplet: quick entry of people and their relatives.

The gramplet shows the active person in an editable block and a "New person"
block. The new person can be added to the tree on its own or as a parent,
spouse, sibling or child of the active person, together with up to four
events whose types are chosen from pop-up menus. A Source (by title) or an
existing Citation can be attached to everything that is created.
"""

# pylint: disable=too-many-lines
from __future__ import annotations

# ------------------------
# Python modules
# ------------------------
import contextlib
import inspect
import logging
import pickle
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from gi.repository import Gdk, GLib, Gtk, Pango

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config as global_config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import get_date, parser
from gramps.gen.db import DbTxn
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.display.place import displayer as place_displayer
from gramps.gen.errors import HandleError, ValidationError, WindowActiveError
from gramps.gen.lib import (
    ChildRef,
    Citation,
    Date,
    Event,
    EventRef,
    EventType,
    Family,
    FamilyRelType,
    Name,
    NameType,
    Person,
    PersonRef,
    Place,
    PlaceName,
    Source,
    Surname,
)
from gramps.gen.plug import BasePluginManager, Gramplet
from gramps.gen.utils.configmanager import ConfigManager
from gramps.gen.utils.db import get_birth_or_fallback, get_death_or_fallback
from gramps.gui import dialog as gramps_dialog
from gramps.gui import editors as gramps_editors
from gramps.gui import selectors as gramps_selectors
from gramps.gui.ddtargets import DdTargets

if TYPE_CHECKING:
    from gramps.gen.types import CitationHandle, PersonHandle

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

# Must match id= in DataEntryGramplet.gpr.py. Written to the [meta] section
# of the .ini so the file identifies the addon it belongs to.
PLUGIN_ID = "Data Entry Gramplet"

# Bump if the keys below ever change shape (rename, type or meaning change),
# so a later version can tell an old-format .ini from a current one.
# 1: gramplet.event_type_1..4 held the bare EventType number.
# 2: gramplet.event_type_row1..4 hold "number:Name" (see event_type_token).
SCHEMA_VERSION = "2"

# Default types of the four event rows (used until the user picks others).
DEFAULT_EVENT_TYPES = (
    EventType.BIRTH,
    EventType.RESIDENCE,
    EventType.DEATH,
    EventType.BURIAL,
)

# .ini key for each event row's type menu (row numbers start at 1).
EVENT_TYPE_KEY = "gramplet.event_type_row%d"

# .ini key of the remembered Associations (one per Family Tree).
ASSOCIATION_KEY = "association.by_tree"

# Space in pixels between the form and the left and right window edges.
FORM_MARGIN = 6

# Plugin id of the Fuzzy Matching addon's GENERAL "API" plugin (see that
# addon's FuzzyMatchingGramplet.gpr.py and FuzzyMatchAPI.md). Optional: the
# Fuzzy Match Lookup button is only shown while this plugin is registered.
FUZZY_API_ID = "Fuzzy Match API"


def fuzzy_match_registered() -> bool:
    """
    Return whether the Fuzzy Matching addon's API plugin is registered and
    active (not hidden in the Plugin Manager).

    A cheap registry lookup; nothing is imported.

    :returns: ``True`` if the "Fuzzy Match API" plugin is usable.
    """
    if BasePluginManager.get_instance().get_plugin(FUZZY_API_ID) is None:
        return False
    return FUZZY_API_ID not in global_config.get("plugin.hiddenplugins")


def get_fuzzy_match_lookup() -> Callable[..., Any] | None:
    """
    Import the Fuzzy Matching addon's API and return ``show_fuzzy_lookup``.

    Goes through Gramps' plugin registry rather than a bare import: Gramps
    only puts an addon's folder on sys.path while it imports that addon's
    own registered module, so a bare import from this addon fails. Same
    pattern as the Photo Tagging gramplet.

    :returns: The ``show_fuzzy_lookup`` function, or ``None`` if the Fuzzy
        Matching addon is not installed, not enabled, too old (before
        v0.5.1) or fails to import.
    """
    pmgr = BasePluginManager.get_instance()
    pdata = pmgr.get_plugin(FUZZY_API_ID)
    if pdata is None:
        return None
    try:
        module = pmgr.import_plugin(pdata)
    except ImportError:
        return None
    if module is None:
        return None
    return getattr(module, "show_fuzzy_lookup", None)


# Style class (and screen-wide CSS) that shows a menu in the theme's error
# color; see set_mismatch_style.
MISMATCH_CLASS = "dataentry-mismatch"
_MISMATCH_CSS_ADDED = False


def set_mismatch_style(widget: Gtk.Widget, mismatch: bool) -> None:
    """
    Show a widget (and its text) in the theme's error color, or normally.

    :param widget: The widget, e.g. a menu (ComboBoxText).
    :param mismatch: ``True`` for the error color.
    """
    global _MISMATCH_CSS_ADDED  # pylint: disable=global-statement
    if not _MISMATCH_CSS_ADDED:
        provider = Gtk.CssProvider()
        css = f".{MISMATCH_CLASS}, .{MISMATCH_CLASS} * {{ color: @error_color; }}"
        provider.load_from_data(css.encode())
        screen = Gdk.Screen.get_default()
        if screen is not None:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        _MISMATCH_CSS_ADDED = True
    context = widget.get_style_context()
    if mismatch:
        context.add_class(MISMATCH_CLASS)
    else:
        context.remove_class(MISMATCH_CLASS)


def split_name(text: str) -> tuple[str, str]:
    """
    Split a "Surname, Given" field into its two parts.

    :param text: The field text; without a comma it is all surname.
    :returns: ``(surname, given)``, both stripped.
    """
    if "," in text:
        surname, given = text.split(",", 1)
    else:
        surname, given = text, ""
    return surname.strip(), given.strip()


def event_type_token(value: int) -> str:
    """
    Return the string stored in the .ini for an event type.

    It is Gramps' number for the type plus its locale-independent name,
    e.g. ``"12:Birth"``.

    :param value: The EventType number.
    :returns: The ``number:Name`` token.
    """
    return f"{value}:{EventType(value).xml_str()}"


def parse_event_type_token(token: Any) -> int | None:
    """
    Return the EventType number for a stored ``number:Name`` token.

    The number AND the name must both match Gramps' current list of event
    types (that list can change between Gramps versions), otherwise the
    token is rejected.

    :param token: The value read from the .ini (normally a string).
    :returns: The EventType number, or ``None`` if the token is not valid.
    """
    try:
        number, name = token.split(":", 1)
        value = int(number)
    except (AttributeError, ValueError):
        return None
    if value in (EventType.UNKNOWN, EventType.CUSTOM):
        return None
    if value not in EventType().get_map():
        return None
    if EventType(value).xml_str() != name:
        return None
    return value


def _load_config() -> ConfigManager:
    """
    Register and load the addon's own .ini file.

    Gramps' ConfigManager puts it in this module's own folder
    (``use_plugins_path=False`` with no override), next to
    ``DataEntryGramplet.py``, and a ``[meta]`` block identifies the addon and
    the version of the .ini format.

    :returns: The registered ConfigManager.
    """
    config = global_config.register_manager("DataEntryGramplet", use_plugins_path=False)
    # ConfigManager writes any value equal to its registered default as a
    # ";;" comment line, so the [meta] keys are registered with "" defaults and
    # set below; that keeps them live (uncommented) in the file.
    config.register("meta.plugin_id", "")
    config.register("meta.schema_version", "")
    for number, default in enumerate(DEFAULT_EVENT_TYPES, 1):
        config.register(EVENT_TYPE_KEY % number, event_type_token(default))
    # The last Association entered, per Family Tree (handles only mean
    # something in the tree they came from): {database id: {...}}, see
    # DataEntryGramplet.save_association.
    config.register(ASSOCIATION_KEY, {})
    config.init()
    if (config.get("meta.plugin_id"), config.get("meta.schema_version")) != (
        PLUGIN_ID,
        SCHEMA_VERSION,
    ):
        # New file, or one from an older schema: migrate, then stamp it.
        # Schema 1 kept bare numbers under event_type_1..4 (unregistered keys
        # that ConfigManager keeps in its data dict, so remove them from there).
        for number in range(1, len(DEFAULT_EVENT_TYPES) + 1):
            old = config.data.get("gramplet", {}).pop(f"event_type_{number}", None)
            if isinstance(old, int) and parse_event_type_token(event_type_token(old)):
                config.set(EVENT_TYPE_KEY % number, event_type_token(old))
        config.set("meta.plugin_id", PLUGIN_ID)
        config.set("meta.schema_version", SCHEMA_VERSION)
        config.save()
    return config


CONFIG = _load_config()


@contextlib.contextmanager
def refusable_txn(txn: DbTxn) -> Iterator[DbTxn]:
    """
    Run a DbTxn like ``with txn:`` but let the body refuse to save anything.

    Raising :class:`~gramps.gen.errors.ValidationError` inside the body rolls
    the transaction back (DbTxn aborts on any exception) and shows the two
    arguments of the exception, a title and a message, in an error dialog.

    :param txn: The transaction to run.
    :returns: A context manager yielding the active transaction.
    """
    try:
        with txn as active_txn:
            yield active_txn
    except ValidationError as err:
        title = err.args[0] if err.args else ""
        body = err.args[1] if len(err.args) > 1 else ""
        gramps_dialog.ErrorDialog(title, body)


# ------------------------------------------------------------
#
# DataEntryGramplet
#
# ------------------------------------------------------------
# The Gramplet API builds the widgets in init() (not __init__) and hooks
# such as main() and db_changed() are called by the framework; the class is
# one form, so it has many widgets, attributes and callbacks:
# pylint: disable=attribute-defined-outside-init,too-many-instance-attributes
# pylint: disable=too-many-public-methods
class DataEntryGramplet(Gramplet):
    """
    Gramplet for quick entry of the active person and of new related people.
    """

    de_widgets: dict[str, Any]  # every widget of the form, by key
    trans: DbTxn  # the transaction of the Save / Add in progress
    show_source: bool
    _dirty_flag: bool
    _dirty_fields: list[str]
    _dirty_person: Person | None
    _dirty_family: Family | None
    _citation_handle: CitationHandle | None
    _linked_handle: PersonHandle | None  # existing person picked in lookup
    _linking: bool  # True while the form itself fills the New person name
    _fuzzy_button: Gtk.Button
    _offer: dict[str, int | None]  # recorded value offered as menu row 0
    _syncing: bool  # True while the form itself edits the NP menus
    _link_refresh_id: int
    _event_choices: list[tuple[str, int]] | None
    _abandon_button: Gtk.Button
    _grid: Gtk.Grid
    _grid_row: int
    _field_group: Gtk.SizeGroup

    NO_REL = 0
    AS_PARENT = 1
    AS_MOTHER = 2
    AS_FATHER = 3
    AS_SPOUSE = 4
    AS_WIFE = 5
    AS_HUSBAND = 6
    AS_SIBLING = 7
    AS_CHILD = 8
    AS_SELF = 9  # New person linked to the active person: update them
    AS_ASSOCIATION = 10  # add an Association (PersonRef), no family link
    # Keys of the sourceable fields: each has an entry, a ":Label" and a
    # ":Citation" check button (see :meth:`make_source_field`).
    SOURCE_KEYS = [
        "NPSource",
        "NPEvent1Source",
        "NPEvent2Source",
        "NPEvent3Source",
        "NPEvent4Source",
        "APSource",
        "APBirthSource",
        "APDeathSource",
    ]
    # The four event rows of the New person section, each with a type menu.
    # The defaults are used until the user picks (then the picks persist).
    EVENT_PREFIXES = ("NPEvent1", "NPEvent2", "NPEvent3", "NPEvent4")
    EVENT_DEFAULTS = DEFAULT_EVENT_TYPES

    def init(self) -> None:  # pylint: disable=too-many-statements
        """
        Build the widgets (Gramplet API hook, called once by the framework).

        The whole form is ONE grid, so every row shares the same columns:
        labels and event menus, main field, "Source:" label, source field.
        The form scrolls in its own window while the Add / Copy / Clear
        buttons stay pinned to the bottom of the gramplet.
        """
        self._dirty = False
        self._dirty_person = None
        self._dirty_family = None
        self._citation_handle = None
        self._linked_handle = None
        self._linking = False
        self._offer = {"NPRelation": None, "NPGender": None}
        self._syncing = False
        self._link_refresh_id = 0
        self._assoc_ref: PersonRef | None = None  # pending Association
        self._citation_preset = False  # Select Citation set without selector
        self._relation_picked = False  # a pick happened while the menu was open
        self.de_widgets = {}
        # The whole form is ONE grid so every row shares the same columns:
        #   0: labels / event-type menus   1: main field
        #   2: "Source:" label             3: source field
        # Columns 1 and 3 get the same width (size group), so the fields and
        # the "Source:" labels line up from row to row.
        self._grid = Gtk.Grid()
        self._grid.set_column_spacing(4)
        self._grid.set_row_spacing(4)
        # keep the fields (and the overlay scroll bar) off the window edges
        self._grid.set_margin_start(FORM_MARGIN)
        self._grid.set_margin_end(FORM_MARGIN)
        self._grid_row = 0
        self._field_group = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
        # Row 1: Active person <name> [edit]            Family: [edit]
        self.make_row(
            "Active person",
            _("Active person"),
            None,
            True,
            [
                ("Edit person", "", "button", self.cb_edit_person),
                ("Edit family", _("Family:"), "button", self.cb_edit_family),
            ],
            False,
            0,
            None,
        )
        # Row 2:      ( ) Enter Sources  ( ) Select Citation  ( ) None [index]
        self.make_source_mode_row()
        genders = [_("female"), _("male"), _("unknown"), _("other")]
        self._gender_labels = genders
        self.make_row("APName", _("Surname, Given"), mark_dirty=True)
        self.make_row(
            "APGender",
            _("Gender"),
            genders,
            mark_dirty=True,
            default=2,
            source=(_("Source"), "APSource"),
        )
        self.make_row(
            "APBirth",
            _("Birth"),
            mark_dirty=True,
            source=(_("Source"), "APBirthSource"),
        )
        self.make_row(
            "APDeath",
            _("Death"),
            mark_dirty=True,
            source=(_("Source"), "APDeathSource"),
        )

        # Save and Abandon (a FlowBox, so they wrap when the window is narrow)
        button_bar, buttons = self.make_button_bar(
            [
                (_("Save"), self.cb_save_data_edit, "document-save"),
                (_("Abandon"), self.cb_abandon_data_edit, "gtk-cancel"),
            ]
        )
        self._abandon_button = buttons[1]
        self._init_dirty_style(self._abandon_button)
        self.attach_row(span_all=button_bar)

        self.make_row("New person", _("New person"), readonly=True)
        self.make_row(
            "NPRelation",
            _("Add relation"),
            [
                _("No relation to active person"),
                _("Add as a Parent"),
                _("Add as a Mother"),
                _("Add as a Father"),
                _("Add as a Spouse"),
                _("Add as a Wife"),
                _("Add as a Husband"),
                _("Add as a Sibling"),
                _("Add as a Child"),
                _("Update self"),
                _("Add an Association"),
            ],
        )
        # Fuzzy Match Lookup button right of the name; only shown while the
        # Fuzzy Matching addon is registered (see refresh_fuzzy_button).
        self._fuzzy_button = Gtk.Button()
        image = Gtk.Image.new_from_icon_name("gtk-find", Gtk.IconSize.LARGE_TOOLBAR)
        image.set_pixel_size(22)
        # The button is set_no_show_all (so show_all() leaves it to
        # refresh_fuzzy_button), which also skips its child: show it here.
        image.show()
        self._fuzzy_button.add(image)
        self._fuzzy_button.set_relief(Gtk.ReliefStyle.NONE)
        self._fuzzy_button.set_focus_on_click(False)
        self._fuzzy_button.set_tooltip_text(
            _(
                "Fuzzy Match Lookup: look for people already in the tree "
                "whose surname sounds like this one (or like the Active "
                "person's surname, if the field is empty). Double-click a "
                "person there to add that existing person instead of a new one."
            )
        )
        self._fuzzy_button.set_no_show_all(True)
        self._fuzzy_button.connect("clicked", self.cb_fuzzy_lookup_clicked)
        self.make_row("NPName", _("Surname, Given"), trailing=self._fuzzy_button)
        name_entry = self.de_widgets["NPName"]
        name_entry.connect("changed", self.cb_np_name_changed)
        name_entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "edit-clear"
        )
        name_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, _("Clear"))
        name_entry.connect("icon-press", self.cb_name_icon_pressed)
        self.make_row(
            "NPGender",
            _("Gender"),
            genders,
            default=2,
            source=(_("Source"), "NPSource"),
        )

        for key in ("NPRelation", "NPGender"):
            self.de_widgets[key].connect("changed", self.cb_np_choice_changed, key)
        # Re-picking "Add an Association" (no "changed" signal) also opens
        # the editor: watch the menu closing.
        self.de_widgets["NPRelation"].connect(
            "notify::popup-shown", self.cb_relation_popup_shown
        )

        # Four event rows (default types: Birth, Residence, Death, Burial).
        # The type of each is chosen from a pop-up menu and remembered
        # between sessions (on_load / on_save).
        for prefix, default in zip(self.EVENT_PREFIXES, self.EVENT_DEFAULTS):
            self.make_event_row(prefix, default)

        # Layout: the form scrolls in its own ScrolledWindow while the Add /
        # Copy / Clear buttons stay pinned to the bottom of the gramplet.
        button_bar, buttons = self.make_button_bar(
            [
                (_("Add"), self.cb_add_data_entry, "gtk-add"),
                (_("Copy Active Data"), self.cb_copy_data_entry, "gtk-copy"),
                (_("Clear"), self.cb_clear_data_entry, "edit-clear-all"),
            ]
        )
        button_bar.set_margin_start(FORM_MARGIN)
        button_bar.set_margin_end(FORM_MARGIN)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_shadow_type(Gtk.ShadowType.NONE)
        scroller.set_min_content_height(80)
        scroller.set_propagate_natural_height(True)
        # The form sits in an EventBox so the gaps and labels of both areas
        # accept Person drops and open the area context menus.
        self._form_box = Gtk.EventBox()
        self._form_box.add(self._grid)
        self._form_box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._form_box.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [DdTargets.PERSON_LINK.target()],
            Gdk.DragAction.COPY,
        )
        self._form_box.connect("drag-data-received", self.cb_form_drag_received)
        self._form_box.connect("button-press-event", self.cb_form_button_press)
        # Text entries keep their own text drops and add Person drops.
        for key, widget in self.de_widgets.items():
            if isinstance(widget, Gtk.Entry) and key[:2] in ("AP", "NP"):
                self.accept_person_drops(widget, "new" if key[:2] == "NP" else "active")
        self._area_menu: Gtk.Menu | None = None
        scroller.add(self._form_box)
        outer = Gtk.VBox()
        outer.pack_start(scroller, True, True, 0)
        outer.pack_start(Gtk.Separator(), False, False, 2)
        outer.pack_start(button_bar, False, False, 0)

        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add_with_viewport(outer)
        outer.show_all()
        self.refresh_fuzzy_button()
        self.refresh_source_mode_widgets()
        self.cb_clear_data_entry(None)

    def main(self) -> None:
        """
        Fill the Active person block from the active person.

        Gramplet API hook, run by ``update()``. Nothing is refreshed while the
        user has unsaved edits in that block (the dirty flag is set).
        """
        # pylint: disable=too-many-statements
        self.refresh_fuzzy_button()
        self.schedule_link_refresh()
        if self._dirty:
            return
        self.de_widgets["Active person:Edit family"].hide()
        self.de_widgets["Active person:Edit family:Label"].hide()
        active_person = self.get_active_object("Person")
        self._dirty_person = active_person
        self._dirty_family = None
        if active_person:
            self.de_widgets["Active person:Edit person"].show()
            self.de_widgets["Active person:Edit family"].hide()
            self.de_widgets["Active person:Edit family:Label"].hide()
            # Fill in current person edits:
            name = name_displayer.display(active_person)
            self.de_widgets["Active person"].set_text(
                f"<i>{GLib.markup_escape_text(name)}</i> "
            )
            self.de_widgets["Active person"].set_use_markup(True)
            # Name:
            name_obj = active_person.get_primary_name()
            if name_obj:
                self.de_widgets["APName"].set_text(
                    f"{name_obj.get_surname()}, {name_obj.get_first_name()}"
                )
            self.de_widgets["APGender"].set_active(active_person.get_gender())  # gender
            # Birth:
            birth = get_birth_or_fallback(self.dbstate.db, active_person)
            birth_text = ""
            if birth:
                sdate = get_date(birth)
                birth_text += sdate + " "
                place_text = place_displayer.display_event(self.dbstate.db, birth)
                if place_text:
                    birth_text += _("in") + " " + place_text

            self.de_widgets["APBirth"].set_text(birth_text)
            # Death:
            death = get_death_or_fallback(self.dbstate.db, active_person)
            death_text = ""
            if death:
                sdate = get_date(death)
                death_text += sdate + " "
                place_text = place_displayer.display_event(self.dbstate.db, death)
                if place_text:
                    death_text += _("in") + " " + place_text
            self.de_widgets["APDeath"].set_text(death_text)
            family_list = active_person.get_family_handle_list()
            if len(family_list) > 0:
                self._dirty_family = self.dbstate.db.get_family_from_handle(
                    family_list[0]
                )
                self.de_widgets["Active person:Edit family"].show()
                self.de_widgets["Active person:Edit family:Label"].show()
            else:
                family_list = active_person.get_parent_family_handle_list()
                if len(family_list) > 0:
                    self._dirty_family = self.dbstate.db.get_family_from_handle(
                        family_list[0]
                    )
                    self.de_widgets["Active person:Edit family"].show()
                    self.de_widgets["Active person:Edit family:Label"].show()
            # lookup sources:
            self.de_widgets["APSource"].set_text(
                self.get_last_source_title(active_person)
            )
            self.de_widgets["APBirthSource"].set_text(self.get_last_source_title(birth))
            self.de_widgets["APDeathSource"].set_text(self.get_last_source_title(death))
            # "Use citation" is a one-shot action flag for the next Save,
            # not a persistent field value, so it does not survive a refresh:
            self.de_widgets["APSource:Citation"].set_active(False)
            self.de_widgets["APBirthSource:Citation"].set_active(False)
            self.de_widgets["APDeathSource:Citation"].set_active(False)
        else:
            self.clear_data_edit()
            self.de_widgets["Active person:Edit person"].hide()
            self.de_widgets["Active person:Edit family"].hide()
            self.de_widgets["Active person:Edit family:Label"].hide()
        self._dirty = False

    def make_button_bar(
        self, specs: list[tuple[str, Callable[..., None], str | None]]
    ) -> tuple[Gtk.FlowBox, list[Gtk.Button]]:
        """
        Build a row of equal-width buttons that keeps to one line.

        Long labels are ellipsized (the full label is the tooltip) when the
        window gets narrow.

        :param specs: A list of ``(label, callback, icon_name)`` tuples;
            ``icon_name`` (or ``None``) is shown left of the label.
        :returns: The FlowBox and the list of its buttons.
        """
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_min_children_per_line(len(specs))
        flow.set_max_children_per_line(len(specs))
        flow.set_column_spacing(4)
        flow.set_row_spacing(4)
        buttons = []
        for label, callback, icon_name in specs:
            button = Gtk.Button()
            text = Gtk.Label(label=label)
            text.set_ellipsize(Pango.EllipsizeMode.END)
            if icon_name:
                content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                content.set_halign(Gtk.Align.CENTER)
                content.pack_start(
                    Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON),
                    False,
                    False,
                    0,
                )
                content.pack_start(text, True, True, 0)
                button.add(content)
            else:
                button.add(text)
            button.set_hexpand(True)
            button.set_tooltip_text(label)
            button.connect("clicked", callback)
            flow.add(button)
            buttons.append(button)
        return flow, buttons

    def shrinkable(self, combo: Gtk.ComboBoxText) -> None:
        """
        Let a combo box shrink below the width of its longest item.

        The width it *requests* is capped so long menu items cannot widen its
        column; the combo still fills whatever space its column gets.

        :param combo: The combo box to adjust.
        """
        for cell in combo.get_cells():
            cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            cell.set_property("max-width-chars", 6)

    def attach_row(
        self,
        first: Gtk.Widget | None = None,
        middle: Gtk.Widget | None = None,
        source_label: Gtk.Label | None = None,
        source_entry: Gtk.Entry | None = None,
        span_all: Gtk.Widget | None = None,
    ) -> None:
        """
        Add one row to the form grid.

        :param first: Column 0 (a label or an event type menu).
        :param middle: Column 1; it spans to the right edge unless there is a
            source field.
        :param source_label: Column 2, the "Source:" label.
        :param source_entry: Column 3, the source field. It always gets the
            same width as ``middle``.
        :param span_all: One widget across all four columns.
        """
        row = self._grid_row
        if span_all is not None:
            span_all.set_hexpand(True)
            self._grid.attach(span_all, 0, row, 4, 1)
        if first is not None:
            self._grid.attach(first, 0, row, 1, 1)
        if middle is not None:
            middle.set_hexpand(True)
            if source_entry is None:
                self._grid.attach(middle, 1, row, 3, 1)
            else:
                source_entry.set_hexpand(True)
                self._grid.attach(middle, 1, row, 1, 1)
                self._grid.attach(source_label, 2, row, 1, 1)
                self._grid.attach(source_entry, 3, row, 1, 1)
                # the two fields of a row always get the same width:
                self._field_group.add_widget(middle)
                self._field_group.add_widget(source_entry)
        self._grid_row += 1

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def make_row(  # pylint: disable=too-many-locals,too-many-statements
        self,
        pos: str,
        text: str,
        choices: list[str] | None = None,
        readonly: bool = False,
        callback_list: list[tuple[str, str, str, Callable[..., None]]] | None = None,
        mark_dirty: bool = False,
        default: int = 0,
        source: tuple[str, str] | None = None,
        trailing: Gtk.Widget | None = None,
    ) -> None:
        """
        Create the widgets of one form row and add them to the grid.

        :param pos: Key under which the main widget is stored in ``de_widgets``.
        :param text: Row label.
        :param choices: Items of a pop-up menu; ``None`` makes a text entry.
        :param readonly: ``True`` for a section header (bold title, plus the
            name and edit buttons of ``callback_list``).
        :param callback_list: ``(key, label, kind, callback)`` edit buttons of
            a header row.
        :param mark_dirty: Whether editing the widgets marks the form dirty.
        :param default: Initially selected menu item.
        :param source: ``(label, key)`` of an optional Source field.
        :param trailing: Optional widget (e.g. an icon button) placed right
            of the main field, in the same column.
        """
        label = Gtk.Label()
        if readonly:
            # Section header: bold title in column 0; if there are edit
            # buttons, the name + buttons go across columns 1-3.
            label.set_text(f"<b>{GLib.markup_escape_text(text)}</b>")
            label.set_use_markup(True)
            self.de_widgets[pos + ":Title"] = label
            label.set_alignment(0.0, 0.5)
            value = Gtk.Label()
            value.set_alignment(0.0, 0.5)
            value.set_use_markup(True)
            value.set_ellipsize(Pango.EllipsizeMode.END)
            self.de_widgets[pos] = value
            box = None
            if callback_list:
                box = Gtk.HBox()
                # the name keeps its natural width (ellipsized only when the
                # window is too narrow), so the edit icon sits right after it
                box.pack_start(value, False, False, 0)
                for index, (name, button_text, _kind, callback) in enumerate(
                    callback_list
                ):
                    if index == 1:
                        # the next control follows after a 4-space gap
                        box.pack_start(Gtk.Label(label="    "), False, False, 0)
                    if button_text:
                        text_label = Gtk.Label()
                        text_label.set_text(button_text)
                        self.de_widgets[pos + ":" + name + ":Label"] = text_label
                        box.pack_start(text_label, False, False, 0)
                    button = Gtk.Button()
                    image = Gtk.Image()
                    image.set_from_stock(Gtk.STOCK_EDIT, Gtk.IconSize.MENU)
                    button.add(image)
                    button.set_relief(Gtk.ReliefStyle.NONE)
                    button.connect("clicked", callback)
                    self.de_widgets[pos + ":" + name] = button
                    box.pack_start(button, False, False, 0)
            self.attach_row(first=label, middle=box if box is not None else value)
            return
        label.set_text(f"{text}: ")
        label.set_alignment(1.0, 0.5)
        if choices is None:
            widget = Gtk.Entry()
            widget.set_width_chars(1)
        else:
            widget = Gtk.ComboBoxText()
            for add_type in choices:
                widget.append_text(add_type)
            self.shrinkable(widget)
            widget.set_active(default)
        self.de_widgets[pos] = widget
        if mark_dirty:
            widget.connect("changed", self.cb_mark_dirty)
        source_label = source_field = None
        if source:
            source_label, source_field = self.make_source_field(
                source[0], source[1], mark_dirty=mark_dirty
            )
        middle: Gtk.Widget = widget
        if trailing is not None:
            middle = Gtk.HBox()
            middle.pack_start(widget, True, True, 0)
            middle.pack_start(trailing, False, False, 0)
        self.attach_row(
            first=label,
            middle=middle,
            source_label=source_label,
            source_entry=source_field,
        )

    def make_source_field(
        self, label_text: str, key: str, mark_dirty: bool = False
    ) -> tuple[Gtk.Label, Gtk.Widget]:
        """
        Build the "Source:" label and the field that occupies its column.

        The field is a wrapper holding a plain text entry (used in Enter
        Sources mode) and a "Use citation" check button (used in Select
        Citation mode); :meth:`refresh_source_mode_widgets` shows exactly
        one of the two, or neither in None mode. The entry is stored in
        ``de_widgets`` under ``key`` (as before, so ``.get_text()`` /
        ``.set_text()`` call sites keep working) and the check button under
        ``key + ":Citation"``.

        :param label_text: Text of the "Source:" label (always "Source" today).
        :param key: Key under which the entry is stored in ``de_widgets``.
        :param mark_dirty: Whether editing either widget marks the form dirty.
        :returns: The label and the wrapper widget to attach in its place.
        """
        label = Gtk.Label()
        label.set_text(f"{label_text}: ")
        label.set_alignment(1.0, 0.5)
        entry = Gtk.Entry()
        entry.set_width_chars(1)
        self.de_widgets[key + ":Label"] = label
        self.de_widgets[key] = entry
        checkbox = Gtk.CheckButton(label=_("Use citation"))
        checkbox.set_active(False)
        self.de_widgets[key + ":Citation"] = checkbox
        if mark_dirty:
            entry.connect("changed", self.cb_mark_dirty)
            checkbox.connect("toggled", self.cb_mark_dirty)
        wrapper = Gtk.HBox()
        wrapper.pack_start(entry, True, True, 0)
        wrapper.pack_start(checkbox, True, True, 0)
        return label, wrapper

    def make_source_mode_row(self) -> None:
        """
        Add the "( ) Enter Sources  ( ) Select Citation  ( ) None" row, plus a
        second row below it showing the citation chosen in Select Citation
        mode.

        The three options are a radio group, so exactly one is selected at a
        time; selecting one always deselects the others. Selecting Select
        Citation opens the Citation selector (see :meth:`cb_toggle_citation`).
        Selecting None sources nothing: no Source field is used and no
        citation is attached. None needs no callback of its own — selecting
        it deselects whichever of the other two was active, and their own
        ``toggled`` handlers already hide the Source fields and forget a
        chosen citation when that happens.
        """
        sources = Gtk.RadioButton.new_with_label(None, _("Enter Sources"))
        sources.set_active(True)
        sources.connect("toggled", self.cb_toggle_sources)
        self.de_widgets["Active person:Show sources"] = sources
        citation = Gtk.RadioButton.new_with_label_from_widget(
            sources, _("Select Citation")
        )
        citation.connect("toggled", self.cb_toggle_citation)
        self.de_widgets["Active person:Show citation"] = citation
        none = Gtk.RadioButton.new_with_label_from_widget(sources, _("None"))
        self.de_widgets["Active person:Show none"] = none
        row = Gtk.HBox()
        row.pack_start(sources, False, False, 0)
        row.pack_start(Gtk.Label(label="    "), False, False, 0)  # 4 spaces
        row.pack_start(citation, False, False, 0)
        row.pack_start(Gtk.Label(label="    "), False, False, 0)  # 4 spaces
        row.pack_start(none, False, False, 0)
        self.de_widgets["Citation:Row"] = row
        self.attach_row(middle=row)

        info = Gtk.Label()
        info.set_alignment(0.0, 0.5)
        info.set_margin_start(6)
        info.set_ellipsize(Pango.EllipsizeMode.END)
        self.de_widgets["Citation:Info"] = info
        self.attach_row(middle=info)

    def make_event_row(self, prefix: str, default_type: int) -> None:
        """
        Add one event row: ``[type menu] [date in place]  Source: [...]``.

        The widgets are stored in ``de_widgets`` as ``prefix + "Type"``,
        ``prefix`` and ``prefix + "Source"`` (+ ``":Label"``).

        :param prefix: Key prefix of the row, one of ``EVENT_PREFIXES``.
        :param default_type: EventType number selected until the user picks.
        """
        combo = Gtk.ComboBoxText()
        for name, _value in self.event_type_choices():
            combo.append_text(name)
        self.shrinkable(combo)
        self.de_widgets[prefix + "Type"] = combo
        self.select_event_type(prefix, default_type)
        entry = Gtk.Entry()
        entry.set_width_chars(1)
        self.de_widgets[prefix] = entry
        label, source_field = self.make_source_field(_("Source"), prefix + "Source")
        self.attach_row(
            first=combo, middle=entry, source_label=label, source_entry=source_field
        )

    def event_type_choices(self) -> list[tuple[str, int]]:
        """
        Return the event types offered by the type menus.

        :returns: A list of ``(translated name, EventType number)`` sorted by
            name; Unknown and Custom are left out.
        """
        choices: list[tuple[str, int]] | None = getattr(self, "_event_choices", None)
        if choices is None:
            skip = (EventType.UNKNOWN, EventType.CUSTOM)
            choices = [
                (str(EventType(value)), value)
                for value in EventType().get_map()
                if value not in skip
            ]
            choices.sort(key=lambda item: item[0].lower())
            self._event_choices = choices
        return choices

    def select_event_type(self, prefix: str, value: int) -> None:
        """
        Select an event type in the menu of an event row.

        :param prefix: Key prefix of the event row.
        :param value: EventType number; ignored if the menu does not offer it.
        """
        for index, (_name, choice) in enumerate(self.event_type_choices()):
            if choice == value:
                self.de_widgets[prefix + "Type"].set_active(index)
                return

    def selected_event_type(self, prefix: str) -> int:
        """
        Return the event type selected in the menu of an event row.

        :param prefix: Key prefix of the event row.
        :returns: The EventType number (Unknown if nothing is selected).
        """
        index = self.de_widgets[prefix + "Type"].get_active()
        choices = self.event_type_choices()
        if 0 <= index < len(choices):
            return choices[index][1]
        return EventType.UNKNOWN

    def event_row_for_type(self, value: int) -> str | None:
        """
        Find the first event row whose menu is set to a given type.

        :param value: EventType number.
        :returns: The row's key prefix, or ``None`` if no row has that type.
        """
        for prefix in self.EVENT_PREFIXES:
            if self.selected_event_type(prefix) == value:
                return prefix
        return None

    def on_load(self) -> None:
        """
        Restore the event types saved in ``DataEntryGramplet.ini``.

        A row whose stored ``number:Name`` no longer matches Gramps' list of
        event types (or is unreadable) falls back to that row's default.
        """
        for number, prefix in enumerate(self.EVENT_PREFIXES, 1):
            value = parse_event_type_token(CONFIG.get(EVENT_TYPE_KEY % number))
            if value is None:
                LOG.warning(
                    "%s: ignoring invalid %s; using the default",
                    CONFIG.filename,
                    EVENT_TYPE_KEY % number,
                )
                value = self.EVENT_DEFAULTS[number - 1]
            self.select_event_type(prefix, value)
        # Connect only now, so restoring does not trigger saves:
        for prefix in self.EVENT_PREFIXES:
            self.de_widgets[prefix + "Type"].connect(
                "changed", self.cb_event_type_changed
            )

    def save_event_types(self) -> None:
        """
        Write the four menu choices to ``DataEntryGramplet.ini``.
        """
        for number, prefix in enumerate(self.EVENT_PREFIXES, 1):
            CONFIG.set(
                EVENT_TYPE_KEY % number,
                event_type_token(self.selected_event_type(prefix)),
            )
        CONFIG.save()

    def cb_event_type_changed(self, _combo: Gtk.ComboBoxText) -> None:
        """
        Save the event types as soon as one of the menus changes.

        :param _combo: The menu that changed (unused).
        """
        self.save_event_types()

    def on_save(self) -> None:
        """
        Save the event types (Gramplet API hook, called when the view closes).
        """
        self.gui.data = []  # drop anything an older version kept there
        self.save_event_types()

    # --- dirty-state flag -------------------------------------------------
    # _dirty is a property so that every existing "self._dirty = ..."
    # assignment also refreshes the Abandon button (red + tooltip).
    @property
    def _dirty(self) -> bool:
        """Whether the Active person block has unsaved edits."""
        return getattr(self, "_dirty_flag", False)

    @_dirty.setter
    def _dirty(self, value: bool) -> None:
        """
        Set or clear the dirty flag and refresh the Abandon button.

        :param value: The new state; clearing it also forgets which fields
            were edited.
        """
        self._dirty_flag = bool(value)
        if not self._dirty_flag:
            self._dirty_fields = []
        self._refresh_dirty_style()

    def _init_dirty_style(self, button: Gtk.Button) -> None:
        """
        Attach a CSS provider so the ``de-dirty`` class turns the button red.

        :param button: The Abandon button.
        """

        provider = Gtk.CssProvider()
        provider.load_from_data(
            b"button.de-dirty { background-image: none;"
            b" background-color: #c01c28; color: #ffffff; }"
        )
        button.get_style_context().add_provider(
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        button.set_tooltip_text(_("Nothing to abandon."))

    def _dirty_label(self, key: str) -> str:
        """
        Return the user-visible name of an Active person field.

        :param key: Key of the widget in ``de_widgets``.
        :returns: The translated field name (the key itself if unknown).
        """
        labels = {
            "APName": _("Name"),
            "APGender": _("Gender"),
            "APBirth": _("Birth"),
            "APDeath": _("Death"),
            "APSource": _("Person source"),
            "APBirthSource": _("Birth source"),
            "APDeathSource": _("Death source"),
        }
        return labels.get(key, key)

    def _dirty_tooltip(self) -> str:
        """
        Return the Abandon button's tooltip: what is unsaved, and whose it is.
        """
        fields = ", ".join(
            self._dirty_label(key) for key in getattr(self, "_dirty_fields", [])
        )
        text = _("Unsaved changes: %s") % (fields or _("(unknown)"))
        person = getattr(self, "_dirty_person", None)
        if person:
            text += "\n" + _("Person being edited: %s") % name_displayer.display(person)
        return text + "\n" + _("Click to discard them and reload.")

    def _refresh_dirty_style(self) -> None:
        """
        Make the Abandon button red (with a tooltip) while the form is dirty.
        """
        button = getattr(self, "_abandon_button", None)
        if button is None:
            return
        context = button.get_style_context()
        if self._dirty:
            context.add_class("de-dirty")
            button.set_tooltip_text(self._dirty_tooltip())
        else:
            context.remove_class("de-dirty")
            button.set_tooltip_text(_("Nothing to abandon."))

    def cb_mark_dirty(self, obj: Gtk.Widget) -> None:
        """
        Note that the user changed an Active person field.

        :param obj: The widget that changed.
        """
        fields = getattr(self, "_dirty_fields", [])
        for key, widget in self.de_widgets.items():
            if widget is obj and key not in fields:
                fields.append(key)
                break
        self._dirty_fields = fields
        self._dirty = True

    def cb_abandon_data_edit(self, _obj: Gtk.Button | None = None) -> None:
        """
        Discard the unsaved edits and reload the Active person block.

        :param _obj: The button that was clicked (unused).
        """
        self._dirty = False
        self.update()

    def cb_edit_done(self, _person: Person) -> None:
        """
        Reload after the person editor was closed.

        :param _person: The edited person (unused).
        """
        self._dirty = False
        self.update()

    def cb_edit_person(self, _obj: Gtk.Button | None = None) -> None:
        """
        Open the Edit Person dialog for the active person.

        :param _obj: The button that was clicked (unused).
        """
        if not self._dirty_person:
            return
        try:
            gramps_editors.EditPerson(
                self.gui.dbstate,
                self.gui.uistate,
                [],
                self._dirty_person,
                callback=self.cb_edit_done,
            )
        except WindowActiveError:
            pass

    def cb_edit_family(self, _obj: Gtk.Button | None = None) -> None:
        """
        Open the Edit Family dialog for the active person's family.

        :param _obj: The button that was clicked (unused).
        """
        if not self._dirty_family:
            return
        try:
            gramps_editors.EditFamily(
                self.gui.dbstate, self.gui.uistate, [], self._dirty_family
            )
        except WindowActiveError:
            pass

    def process_dateplace(self, text: str) -> tuple[Date | None, Place | None]:
        """
        Split ``date in place`` text, parse the date and find or create the place.

        :param text: What the user typed, e.g. ``1855-06-21 in Great Falls``.
        :returns: A ``(Date, Place)`` tuple; either may be ``None``.
        """
        if text == "":
            return None, None
        prep_in = _("in")  # word or phrase that separates date from place
        text = text.strip()
        date_text, place_text = text, ""
        if f" {prep_in} " in text:
            date_text, place_text = text.split(f" {prep_in} ", 1)
        elif text.startswith(f"{prep_in} "):
            date_text, place_text = text.split(f"{prep_in} ", 1)
        date = parser.parse(date_text.strip()) if date_text.strip() else None
        place = None
        if place_text.strip():
            place = self.get_or_create_place(place_text.strip())[1]
        return date, place

    def get_or_create_place(self, place_name: str) -> tuple[int, Place | None]:
        """
        Find a place by its displayed title, or create it.

        :param place_name: The place title.
        :returns: ``(-1, None)`` for an empty name, ``(0, place)`` if found,
            ``(1, place)`` if created.
        """
        if place_name == "":
            return (-1, None)
        place_list = self.dbstate.db.get_place_handles()
        for place_handle in place_list:
            place = self.dbstate.db.get_place_from_handle(place_handle)
            place_title = place_displayer.display(self.dbstate.db, place)
            if place_title.strip() == place_name:
                return (0, place)  # (old, object)
        place = Place()
        place.set_title(place_name)
        place.set_name(PlaceName(value=place_name))
        self.dbstate.db.add_place(place, self.trans)
        return (1, place)  # (new, object)

    def get_or_create_event(
        self, obj: Person, event_type: int, date: Date | None, place: Place | None
    ) -> tuple[int, Event | None]:
        """
        Update the person's event of a type, or create one.

        :param obj: The person.
        :param event_type: EventType number.
        :param date: The date to set, or ``None``.
        :param place: The place to set, or ``None``.
        :returns: ``(-1, None)`` if there is nothing to store, ``(0, event)``
            if an existing event was updated, ``(1, event)`` if created.
        """
        if date is None and place is None:
            return (-1, None)
        # first, see if it exists
        ref_list = obj.get_event_ref_list()
        # look for a match, and possible correction
        for ref in ref_list:
            event = self.dbstate.db.get_event_from_handle(ref.ref)
            if event is not None:
                if int(event.get_type()) == event_type:
                    # Match! Let's update
                    if date:
                        event.set_date_object(date)
                    if place:
                        event.set_place_handle(place.get_handle())
                    self.dbstate.db.commit_event(event, self.trans)
                    return (0, event)
        # else create it:
        event = Event()
        if event_type:
            event.set_type(EventType(event_type))
        if date:
            event.set_date_object(date)
        if place:
            event.set_place_handle(place.get_handle())
        self.dbstate.db.add_event(event, self.trans)
        return (1, event)

    def get_or_create_source(self, source_text: str) -> tuple[int, Source]:
        """
        Find a source by its title, or create it.

        :param source_text: The source title.
        :returns: ``(0, source)`` if found, ``(1, source)`` if created.
        """
        source_list = self.dbstate.db.get_source_handles()
        for source_handle in source_list:
            source = self.dbstate.db.get_source_from_handle(source_handle)
            if source.get_title() == source_text:
                return (0, source)
        source = Source()
        source.set_title(source_text)
        self.dbstate.db.add_source(source, self.trans)
        return (1, source)

    def get_last_source_title(self, obj: Person | Event | None) -> str:
        """
        Return the title of the source of the object's last citation.

        :param obj: A person or event, or ``None``.
        :returns: The source title, or an empty string.
        """
        if obj:
            citation_list = obj.get_citation_list()
            if len(citation_list) > 0:
                citation_handle = citation_list[-1]
                citation = self.dbstate.db.get_citation_from_handle(citation_handle)
                if citation:
                    source = self.dbstate.db.get_source_from_handle(
                        citation.get_reference_handle()
                    )
                    if source:
                        return source.get_title()
        return ""

    def make_event(
        self, event_type: int, date: Date | None, place: Place | None
    ) -> Event | None:
        """
        Create and add an event to the database.

        :param event_type: EventType number.
        :param date: The date, or ``None``.
        :param place: The place, or ``None``.
        :returns: The new event, or ``None`` if both date and place are empty.
        """
        if date is None and place is None:
            return None
        event = Event()
        event.set_type(EventType(event_type))
        if date:
            event.set_date_object(date)
        if place:
            event.set_place_handle(place.get_handle())
        self.dbstate.db.add_event(event, self.trans)
        return event

    def make_person(self, firstname: str, surname: str, gender: int) -> Person:
        """
        Create a Person object (not yet added to the database).

        :param firstname: Given name.
        :param surname: Surname.
        :param gender: Person gender constant.
        :returns: The new person.
        """
        person = Person()
        name = Name()
        name.set_type(NameType(NameType.BIRTH))
        name.set_first_name(firstname)
        surname_obj = Surname()
        surname_obj.set_surname(surname)
        name.set_surname_list([surname_obj])
        name.set_primary_surname(0)
        person.set_primary_name(name)
        person.set_gender(gender)
        return person

    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def cb_save_data_edit(self, _obj: Gtk.Button | None = None) -> None:
        """
        Save the edits made in the Active person block.

        Does nothing if there are no unsaved edits.

        :param _obj: The button that was clicked (unused).
        """
        if self._dirty:
            if not self.dbstate.is_open():
                gramps_dialog.ErrorDialog(
                    _("No Family Tree is open."),
                    _("Please open a Family Tree to edit data."),
                )
                return
            # Save the edits ----------------------------------
            person = self._dirty_person
            # First, get the data:
            gender = self.de_widgets["APGender"].get_active()
            if "," in self.de_widgets["APName"].get_text():
                surname, firstname = self.de_widgets["APName"].get_text().split(",", 1)
            else:
                surname, firstname = self.de_widgets["APName"].get_text(), ""
            surname = surname.strip()
            firstname = firstname.strip()
            if person:
                name = person.get_primary_name()
            else:
                return
            # Now, edit it:
            with DbTxn(
                _("Gramplet Data Edit: %s") % name_displayer.display(person),
                self.dbstate.db,
            ) as self.trans:
                surname_obj = name.get_primary_surname()
                surname_obj.set_surname(surname)
                name.set_first_name(firstname)
                person.set_gender(gender)
                birthdate, birthplace = self.process_dateplace(
                    self.de_widgets["APBirth"].get_text().strip()
                )
                _new, birthevent = self.get_or_create_event(
                    person, EventType.BIRTH, birthdate, birthplace
                )
                # reference it, if need be:
                birthref = person.get_birth_ref()
                if birthevent:
                    if birthref is None:
                        # need new
                        birthref = EventRef()
                    birthref.set_reference_handle(birthevent.get_handle())
                    person.set_birth_ref(birthref)
                    # Only add if there is an event:
                    source_text = self.de_widgets["APBirthSource"].get_text().strip()
                    if (
                        source_text
                        and self.de_widgets["Active person:Show sources"].get_active()
                    ):
                        _new, source = self.get_or_create_source(source_text)
                        self.add_source(birthevent, source)
                        self.dbstate.db.commit_event(birthevent, self.trans)
                    if self.add_selected_citation(
                        birthevent, "APBirthSource:Citation"
                    ):
                        self.dbstate.db.commit_event(birthevent, self.trans)
                deathdate, deathplace = self.process_dateplace(
                    self.de_widgets["APDeath"].get_text().strip()
                )
                _new, deathevent = self.get_or_create_event(
                    person, EventType.DEATH, deathdate, deathplace
                )
                # reference it, if need be:
                deathref = person.get_death_ref()
                if deathevent:
                    if deathref is None:
                        # need new
                        deathref = EventRef()
                    deathref.set_reference_handle(deathevent.get_handle())
                    person.set_death_ref(deathref)
                    # Only add if there is an event:
                    source_text = self.de_widgets["APDeathSource"].get_text().strip()
                    if (
                        source_text
                        and self.de_widgets["Active person:Show sources"].get_active()
                    ):
                        _new, source = self.get_or_create_source(source_text)
                        self.add_source(deathevent, source)
                        self.dbstate.db.commit_event(deathevent, self.trans)
                    if self.add_selected_citation(
                        deathevent, "APDeathSource:Citation"
                    ):
                        self.dbstate.db.commit_event(deathevent, self.trans)
                source_text = self.de_widgets["APSource"].get_text().strip()
                if (
                    source_text
                    and self.de_widgets["Active person:Show sources"].get_active()
                ):
                    _new, source = self.get_or_create_source(source_text)
                    self.add_source(person, source)
                self.add_selected_citation(person, "APSource:Citation")
                self.dbstate.db.commit_person(person, self.trans)
        self._dirty = False
        self.update()

    def add_source(self, obj: Person | Event, source: Source) -> None:
        """
        Cite a source on an object, reusing an existing citation of it.

        :param obj: The person or event to cite it on.
        :param source: The source.
        """
        found = 0
        for handle in obj.get_citation_list():
            citation = self.dbstate.db.get_citation_from_handle(handle)
            if citation.get_reference_handle() == source.get_handle():
                found = 1
                break
        if not found:
            citation = Citation()
            citation.set_reference_handle(source.get_handle())
            self.dbstate.db.add_citation(citation, self.trans)
        obj.add_citation(citation.get_handle())

    def cb_add_data_entry(self, _obj: Gtk.Button | None = None) -> None:
        """
        Add the New person (and its events) to the tree.

        The person is added on its own or as the parent, spouse, sibling or
        child of the active person, depending on the "Add relation" menu.
        Everything is saved in one transaction; if a check fails inside it
        (for example both partners have the same gender) the transaction is
        rolled back, so nothing is left behind, and the error is shown.

        :param _obj: The button that was clicked (unused).
        """
        # The relation handling below is long-standing code that is kept as it is:
        # pylint: disable=too-many-locals,too-many-branches,too-many-statements
        # pylint: disable=too-many-return-statements,too-many-nested-blocks
        # pylint: disable=no-else-return,no-else-break,no-else-raise
        if not self.dbstate.is_open():
            gramps_dialog.ErrorDialog(
                _("No Family Tree is open."),
                _("Please open a Family Tree before adding a person."),
            )
            return
        # First, get the data:
        surname, firstname = split_name(self.de_widgets["NPName"].get_text())
        gender = self.np_choice("NPGender")
        current_person: Any  # validated per relation below, before any writes
        if self._dirty:
            current_person = self._dirty_person
        else:
            current_person = self.get_active_object("Person")
        # An existing person picked in the Fuzzy Match Lookup window is used
        # instead of creating a new one (see _apply_fuzzy_match):
        existing: Person | None = None
        if self._linked_handle:
            try:
                existing = self.dbstate.db.get_person_from_handle(self._linked_handle)
            except HandleError:
                existing = None
            if existing is None:
                self.unlink_person()
                gramps_dialog.ErrorDialog(
                    _("The linked person is no longer in the tree."),
                    _("Can't add the linked person."),
                )
                return
        relation = self.np_choice("NPRelation")
        same_person = (
            existing is not None
            and current_person is not None
            and existing.get_handle() == current_person.get_handle()
        )
        if same_person and relation not in (self.AS_SELF, self.AS_ASSOCIATION):
            gramps_dialog.ErrorDialog(
                _("The linked person is the active person."),
                _('Choose "Update self" (or an Association) to update them.'),
            )
            return
        if relation == self.AS_SELF and not same_person:
            gramps_dialog.ErrorDialog(
                _("The New person is not linked to the active person."),
                _('"Update self" needs both areas to show the same person.'),
            )
            return
        association: PersonRef | None = None
        if relation == self.AS_ASSOCIATION:
            association = self._assoc_ref or self.default_association()
            if association is None or not association.ref:
                gramps_dialog.ErrorDialog(
                    _("Please choose the associated person."),
                    _("Can't add the Association."),
                )
                return
            if existing is not None and association.ref == existing.get_handle():
                gramps_dialog.ErrorDialog(
                    _("A person can't be associated with themselves."),
                    _("Can't add the Association."),
                )
                return
        # A relationship the linked person already has with the active
        # person is not added again (no duplicate family links); Add then
        # only adds the events, source and citation.
        skipped_relation = False
        skipped_association = False
        if (
            existing is not None
            and current_person is not None
            and self.relation_exists(relation, existing, current_person)
        ):
            skipped_relation = True
            relation = self.NO_REL
        # Pre-check to make sure everything is ok: -------------------------------------------
        if surname == "" and firstname == "":
            gramps_dialog.ErrorDialog(
                _("Please provide a name."), _("Can't add new person.")
            )
            return
        if relation == self.NO_REL:
            # "No relation to active person"
            pass
        elif relation == self.AS_PARENT:
            # "Add as a Parent"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a parent."),
                )
                return
            elif gender == Person.UNKNOWN:  # unknown
                gramps_dialog.ErrorDialog(
                    _("Please set the new person's gender."),
                    _("Can't add new person as a parent."),
                )
                return
        elif relation == self.AS_MOTHER:
            # "Add as a Mother"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a mother."),
                )
                return
        elif relation == self.AS_FATHER:
            # "Add as a Father"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a father."),
                )
                return
        elif relation == self.AS_SPOUSE:
            # "Add as a Spouse"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a spouse."),
                )
                return
            elif (
                gender == Person.UNKNOWN
                and current_person.get_gender() == Person.UNKNOWN
            ):  # both genders unknown
                gramps_dialog.ErrorDialog(
                    _("Please set the new person's gender."),
                    _("Can't add new person as a spouse."),
                )
                return
        elif relation == self.AS_WIFE:
            # "Add as a Wife"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a wife."),
                )
                return
        elif relation == self.AS_HUSBAND:
            # "Add as a Husband"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a husband."),
                )
                return
        elif relation == self.AS_SIBLING:
            # "Add as a Sibling"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a sibling."),
                )
                return
        elif relation == self.AS_CHILD:
            # "Add as a Child"
            if current_person is None:
                gramps_dialog.ErrorDialog(
                    _("Please set an active person."),
                    _("Can't add new person as a child."),
                )
                return
        # Update self and Association add no family link:
        if relation in (self.AS_SELF, self.AS_ASSOCIATION):
            relation = self.NO_REL
        # Start the transaction: ------------------------------------------------------------
        if existing is not None:
            person = existing
        else:
            person = self.make_person(firstname, surname, gender)
        added_ok = False
        with refusable_txn(
            DbTxn(
                _("Gramplet Data Edit: %s") % name_displayer.display(person),
                self.dbstate.db,
            )
        ) as self.trans:
            # New person --------------------------------------------------
            # The four event rows; each type comes from its pop-up menu.
            # A Birth (Death) event becomes the person's birth (death)
            # reference - the first one only; all others are plain events.
            birth_designated = death_designated = False
            for prefix in self.EVENT_PREFIXES:
                ev_type = self.selected_event_type(prefix)
                ev_date, ev_place = self.process_dateplace(
                    self.de_widgets[prefix].get_text().strip()
                )
                event = self.make_event(ev_type, ev_date, ev_place)
                if not event:
                    continue  # Only add if there is an event
                source_text = self.de_widgets[prefix + "Source"].get_text().strip()
                if (
                    source_text
                    and self.de_widgets["Active person:Show sources"].get_active()
                ):
                    _new, source = self.get_or_create_source(source_text)
                    self.add_source(event, source)
                    self.dbstate.db.commit_event(event, self.trans)
                if self.add_selected_citation(event, prefix + "Source:Citation"):
                    self.dbstate.db.commit_event(event, self.trans)
                event_ref = EventRef()
                event_ref.set_reference_handle(event.get_handle())
                # (an existing person keeps a birth/death reference it has)
                if (
                    ev_type == EventType.BIRTH
                    and not birth_designated
                    and person.get_birth_ref() is None
                ):
                    person.set_birth_ref(event_ref)
                    birth_designated = True
                elif (
                    ev_type == EventType.DEATH
                    and not death_designated
                    and person.get_death_ref() is None
                ):
                    person.set_death_ref(event_ref)
                    death_designated = True
                else:
                    person.add_event_ref(event_ref)
            if existing is None:
                # Need to add here to get a handle:
                self.dbstate.db.add_person(person, self.trans)
            # All error checking done; just add relation:
            if relation == self.NO_REL:
                # "No relation to active person"
                current_person = None
            elif relation == self.AS_PARENT:
                # "Add as a Parent"
                # Go through current_person parent families
                added = False
                for family_handle in current_person.get_parent_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        # find one that person would fit as a parent
                        fam_husband_handle = family.get_father_handle()
                        fam_wife_handle = family.get_mother_handle()
                        # can we add person as wife?
                        if (
                            fam_wife_handle is None
                            and person.get_gender() == Person.FEMALE
                        ):
                            # add the person
                            family.set_mother_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            added = True
                            break
                        elif (
                            fam_husband_handle is None
                            and person.get_gender() == Person.MALE
                        ):
                            # add the person
                            family.set_father_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            added = True
                            break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    family = Family()
                    self.dbstate.db.add_family(family, self.trans)
                    if person.get_gender() == Person.MALE:
                        family.set_father_handle(person.get_handle())
                    elif person.get_gender() == Person.FEMALE:
                        family.set_mother_handle(person.get_handle())
                    family.set_relationship(FamilyRelType.MARRIED)
                    # add curent_person as child
                    childref = ChildRef()
                    childref.set_reference_handle(current_person.get_handle())
                    family.add_child_ref(childref)
                    current_person.add_parent_family_handle(family.get_handle())
                    # finalize
                    person.add_family_handle(family.get_handle())
                    self.dbstate.db.commit_family(family, self.trans)
            elif relation == self.AS_MOTHER:
                # "Add as a Mother"
                # Go through current_person parent families
                added = False
                for family_handle in current_person.get_parent_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        fam_wife_handle = family.get_mother_handle()
                        # can we add person as mother?
                        if fam_wife_handle is None:
                            # add the person
                            family.set_mother_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            added = True
                            break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    family = Family()
                    self.dbstate.db.add_family(family, self.trans)
                    family.set_mother_handle(person.get_handle())
                    family.set_relationship(FamilyRelType.MARRIED)
                    # add curent_person as child
                    childref = ChildRef()
                    childref.set_reference_handle(current_person.get_handle())
                    family.add_child_ref(childref)
                    current_person.add_parent_family_handle(family.get_handle())
                    # finalize
                    person.add_family_handle(family.get_handle())
                    self.dbstate.db.commit_family(family, self.trans)
            elif relation == self.AS_FATHER:
                # "Add as a Father"
                # Go through current_person parent families
                added = False
                for family_handle in current_person.get_parent_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        fam_husband_handle = family.get_father_handle()
                        # can we add person as father?
                        if fam_husband_handle is None:
                            # add the person
                            family.set_father_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            added = True
                            break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    family = Family()
                    self.dbstate.db.add_family(family, self.trans)
                    family.set_father_handle(person.get_handle())
                    family.set_relationship(FamilyRelType.MARRIED)
                    # add curent_person as child
                    childref = ChildRef()
                    childref.set_reference_handle(current_person.get_handle())
                    family.add_child_ref(childref)
                    current_person.add_parent_family_handle(family.get_handle())
                    # finalize
                    person.add_family_handle(family.get_handle())
                    self.dbstate.db.commit_family(family, self.trans)
            elif relation == self.AS_SPOUSE:
                # "Add as a Spouse"
                added = False
                family = None
                for family_handle in current_person.get_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        fam_husband_handle = family.get_father_handle()
                        fam_wife_handle = family.get_mother_handle()
                        if current_person.get_handle() == fam_husband_handle:
                            # can we add person as wife?
                            if fam_wife_handle is None:
                                if person.get_gender() == Person.FEMALE:
                                    # add the person
                                    family.set_mother_handle(person.get_handle())
                                    family.set_relationship(FamilyRelType.MARRIED)
                                    person.add_family_handle(family.get_handle())
                                    added = True
                                    break
                                elif person.get_gender() == Person.UNKNOWN:
                                    family.set_mother_handle(person.get_handle())
                                    family.set_relationship(FamilyRelType.MARRIED)
                                    person.set_gender(Person.FEMALE)
                                    self.set_np_choice("NPGender", Person.FEMALE)
                                    person.add_family_handle(family.get_handle())
                                    added = True
                                    break
                        elif current_person.get_handle() == fam_wife_handle:
                            # can we add person as husband?
                            if fam_husband_handle is None:
                                if person.get_gender() == Person.MALE:
                                    # add the person
                                    family.set_father_handle(person.get_handle())
                                    family.set_relationship(FamilyRelType.MARRIED)
                                    person.add_family_handle(family.get_handle())
                                    added = True
                                    break
                                elif person.get_gender() == Person.UNKNOWN:
                                    family.set_father_handle(person.get_handle())
                                    family.set_relationship(FamilyRelType.MARRIED)
                                    person.add_family_handle(family.get_handle())
                                    person.set_gender(Person.MALE)
                                    self.set_np_choice("NPGender", Person.MALE)
                                    added = True
                                    break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    if person.get_gender() == Person.UNKNOWN:
                        if current_person is None:
                            raise ValidationError(
                                _("Please set Active person."),
                                _("Can't add new person as a spouse to no one."),
                            )
                        elif current_person.get_gender() == Person.UNKNOWN:
                            raise ValidationError(
                                _("Please set gender on Active or new person."),
                                _("Can't add new person as a spouse."),
                            )
                        elif current_person.get_gender() == Person.MALE:
                            family = Family()
                            self.dbstate.db.add_family(family, self.trans)
                            family.set_father_handle(current_person.get_handle())
                            family.set_mother_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.set_gender(Person.FEMALE)
                            self.set_np_choice("NPGender", Person.FEMALE)
                            person.add_family_handle(family.get_handle())
                            current_person.add_family_handle(family.get_handle())
                            self.dbstate.db.commit_family(family, self.trans)
                        elif current_person.get_gender() == Person.FEMALE:
                            family = Family()
                            self.dbstate.db.add_family(family, self.trans)
                            family.set_father_handle(person.get_handle())
                            family.set_mother_handle(current_person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.set_gender(Person.MALE)
                            self.set_np_choice("NPGender", Person.MALE)
                            person.add_family_handle(family.get_handle())
                            current_person.add_family_handle(family.get_handle())
                            self.dbstate.db.commit_family(family, self.trans)
                    elif person.get_gender() == Person.MALE:
                        if current_person.get_gender() == Person.UNKNOWN:
                            family = Family()
                            self.dbstate.db.add_family(family, self.trans)
                            family.set_father_handle(person.get_handle())
                            family.set_mother_handle(current_person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            current_person.set_gender(Person.FEMALE)
                            person.add_family_handle(family.get_handle())
                            current_person.add_family_handle(family.get_handle())
                            self.dbstate.db.commit_family(family, self.trans)
                        elif current_person.get_gender() == Person.MALE:
                            raise ValidationError(
                                _("Same genders on Active and new person."),
                                _("Can't add new person as a spouse."),
                            )
                        elif current_person.get_gender() == Person.FEMALE:
                            family = Family()
                            self.dbstate.db.add_family(family, self.trans)
                            family.set_father_handle(person.get_handle())
                            family.set_mother_handle(current_person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            current_person.add_family_handle(family.get_handle())
                            self.dbstate.db.commit_family(family, self.trans)
                    elif person.get_gender() == Person.FEMALE:
                        if current_person.get_gender() == Person.UNKNOWN:
                            family = Family()
                            self.dbstate.db.add_family(family, self.trans)
                            family.set_father_handle(current_person.get_handle())
                            family.set_mother_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            current_person.set_gender(Person.MALE)
                            person.add_family_handle(family.get_handle())
                            current_person.add_family_handle(family.get_handle())
                            self.dbstate.db.commit_family(family, self.trans)
                        elif current_person.get_gender() == Person.MALE:
                            family = Family()
                            self.dbstate.db.add_family(family, self.trans)
                            family.set_father_handle(current_person.get_handle())
                            family.set_mother_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            current_person.add_family_handle(family.get_handle())
                            self.dbstate.db.commit_family(family, self.trans)
                        elif current_person.get_gender() == Person.FEMALE:
                            raise ValidationError(
                                _("Same genders on Active and new person."),
                                _("Can't add new person as a spouse."),
                            )
            elif relation == self.AS_WIFE:
                # "Add as a Wife"
                added = False
                family = None
                for family_handle in current_person.get_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        fam_wife_handle = family.get_mother_handle()
                        # can we add person as wife?
                        if fam_wife_handle is None:
                            # add the person
                            family.set_mother_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            added = True
                            break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    family = Family()
                    self.dbstate.db.add_family(family, self.trans)
                    family.set_mother_handle(person.get_handle())
                    family.set_father_handle(current_person.get_handle())
                    family.set_relationship(FamilyRelType.MARRIED)
                    person.add_family_handle(family.get_handle())
                    current_person.add_family_handle(family.get_handle())
                    self.dbstate.db.commit_family(family, self.trans)
            elif relation == self.AS_HUSBAND:
                # "Add as a Husband"
                added = False
                family = None
                for family_handle in current_person.get_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        fam_husband_handle = family.get_father_handle()
                        # can we add person as husband?
                        if fam_husband_handle is None:
                            # add the person
                            family.set_father_handle(person.get_handle())
                            family.set_relationship(FamilyRelType.MARRIED)
                            person.add_family_handle(family.get_handle())
                            added = True
                            break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    family = Family()
                    self.dbstate.db.add_family(family, self.trans)
                    family.set_father_handle(person.get_handle())
                    family.set_mother_handle(current_person.get_handle())
                    family.set_relationship(FamilyRelType.MARRIED)
                    person.add_family_handle(family.get_handle())
                    current_person.add_family_handle(family.get_handle())
                    self.dbstate.db.commit_family(family, self.trans)
            elif (
                relation == self.AS_SIBLING
                and current_person is not None
            ):
                # "Add as a Sibling"
                added = False
                for family_handle in current_person.get_parent_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        childref = ChildRef()
                        childref.set_reference_handle(person.get_handle())
                        family.add_child_ref(childref)
                        person.add_parent_family_handle(family.get_handle())
                        added = True
                        break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    family = Family()
                    self.dbstate.db.add_family(family, self.trans)
                    childref = ChildRef()
                    childref.set_reference_handle(person.get_handle())
                    family.add_child_ref(childref)
                    childref = ChildRef()
                    childref.set_reference_handle(current_person.get_handle())
                    family.add_child_ref(childref)
                    person.add_parent_family_handle(family.get_handle())
                    current_person.add_parent_family_handle(family.get_handle())
                    self.dbstate.db.commit_family(family, self.trans)
            elif (
                relation == self.AS_CHILD
                and current_person is not None
            ):
                # "Add as a Child"
                added = False
                family = None
                for family_handle in current_person.get_family_handle_list():
                    family = self.dbstate.db.get_family_from_handle(family_handle)
                    if family:
                        childref = ChildRef()
                        childref.set_reference_handle(person.get_handle())
                        family.add_child_ref(childref)
                        person.add_parent_family_handle(family.get_handle())
                        added = True
                        break
                if added:
                    self.dbstate.db.commit_family(family, self.trans)
                else:
                    if current_person.get_gender() == Person.UNKNOWN:
                        raise ValidationError(
                            _("Please set gender on Active person."),
                            _("Can't add new person as a child."),
                        )
                    else:
                        family = Family()
                        self.dbstate.db.add_family(family, self.trans)
                        childref = ChildRef()
                        childref.set_reference_handle(person.get_handle())
                        family.add_child_ref(childref)
                        person.add_parent_family_handle(family.get_handle())
                        current_person.add_family_handle(family.get_handle())
                        if current_person.get_gender() == Person.FEMALE:
                            family.set_mother_handle(current_person.get_handle())
                        else:
                            family.set_father_handle(current_person.get_handle())
                        self.dbstate.db.commit_family(family, self.trans)
            # Commit changes -------------------------------------------------
            if current_person:  # if related to current person
                self.dbstate.db.commit_person(current_person, self.trans)
            if person:
                source_text = self.de_widgets["NPSource"].get_text().strip()
                if (
                    source_text
                    and self.de_widgets["Active person:Show sources"].get_active()
                ):
                    _new, source = self.get_or_create_source(source_text)
                    self.add_source(person, source)
                self.add_selected_citation(person, "NPSource:Citation")
                if association is not None:
                    if any(
                        ref.ref == association.ref
                        and ref.get_relation() == association.get_relation()
                        for ref in person.get_person_ref_list()
                    ):
                        skipped_association = True  # already recorded
                    else:
                        person.add_person_ref(association)
                self.dbstate.db.commit_person(person, self.trans)
            added_ok = True
        if added_ok and association is not None:
            self._assoc_ref = None  # the next one starts from the .ini again
            self.update_association_tooltip()
            if skipped_association:
                self.uistate.push_message(
                    self.dbstate,
                    _("That Association is already recorded; it was not added again."),
                )
        if added_ok and existing is not None:
            if skipped_relation:
                self.uistate.push_message(
                    self.dbstate,
                    _(
                        "%s is already in that family of the active person; "
                        "no family link was added."
                    )
                    % name_displayer.display(existing),
                )
            # Done with that person: a second Add would link them twice.
            self.unlink_person()

    def cb_copy_data_entry(self, _obj: Gtk.Button | None = None) -> None:
        """
        Copy the Active person's data into the New person block.

        Birth and Death go to the event rows whose menus are set to those
        types. If a citation is chosen, its date goes to the Residence row.

        :param _obj: The button that was clicked (unused).
        """
        self.de_widgets["NPName"].set_text(self.de_widgets["APName"].get_text())
        self.set_np_choice("NPGender", self.de_widgets["APGender"].get_active())
        self.de_widgets["NPSource"].set_text(self.de_widgets["APSource"].get_text())
        # Birth and Death go to the event row whose menu is set to that type:
        for ev_type, ap_key in (
            (EventType.BIRTH, "APBirth"),
            (EventType.DEATH, "APDeath"),
        ):
            prefix = self.event_row_for_type(ev_type)
            if prefix:
                self.de_widgets[prefix].set_text(self.de_widgets[ap_key].get_text())
                self.de_widgets[prefix + "Source"].set_text(
                    self.de_widgets[ap_key + "Source"].get_text()
                )
        # A chosen citation's date becomes the Residence date (e.g. a census):
        if self.de_widgets["Active person:Show citation"].get_active():
            citation = self.selected_citation()
            date_text = get_date(citation) if citation else ""
            prefix = self.event_row_for_type(EventType.RESIDENCE)
            if date_text and prefix:
                self.de_widgets[prefix].set_text(date_text)
        # FIXME: put cursor in add surname

    def clear_data_edit(self) -> None:
        """
        Empty the Active person block.
        """
        self.de_widgets["Active person"].set_text("")
        self.de_widgets["APName"].set_text("")
        self.de_widgets["APBirth"].set_text("")
        self.de_widgets["APDeath"].set_text("")
        self.de_widgets["APGender"].set_active(Person.UNKNOWN)
        self.de_widgets["APSource"].set_text("")
        self.de_widgets["APBirthSource"].set_text("")
        self.de_widgets["APDeathSource"].set_text("")
        self.de_widgets["APSource:Citation"].set_active(False)
        self.de_widgets["APBirthSource:Citation"].set_active(False)
        self.de_widgets["APDeathSource:Citation"].set_active(False)

    def cb_clear_data_entry(self, _obj: Gtk.Button | None = None) -> None:
        """
        Empty the New person block (the event types are kept).

        :param _obj: The button that was clicked (unused).
        """
        self.de_widgets["NPName"].set_text("")
        self.unlink_person()
        self._assoc_ref = None
        self.set_np_choice("NPRelation", self.NO_REL)
        self.set_np_choice("NPGender", Person.UNKNOWN)
        self.de_widgets["NPSource"].set_text("")
        self.de_widgets["NPSource:Citation"].set_active(False)
        for prefix in self.EVENT_PREFIXES:
            self.de_widgets[prefix].set_text("")
            self.de_widgets[prefix + "Source"].set_text("")
            self.de_widgets[prefix + "Source:Citation"].set_active(False)

    def refresh_fuzzy_button(self) -> None:
        """
        Show the Fuzzy Match Lookup button only while Fuzzy Matching is
        registered (it can be installed or enabled during a session).
        """
        self._fuzzy_button.set_visible(fuzzy_match_registered())

    def cb_fuzzy_lookup_clicked(self, _obj: Gtk.Button | None = None) -> None:
        """
        Open the Fuzzy Matching addon's Fuzzy Match Lookup window.

        The window is seeded with the New person's "Surname, Given": the
        surname is looked up and selected, and the given name goes into the
        window's "Given name contains" filter (Fuzzy Matching versions that
        accept ``given_filter``; older ones only scroll to the closest
        given name). If the surname is blank, the Active person's preferred
        surname is used; with neither, the window opens with a blank
        surname, ready to type into. A person double-clicked there is
        handed back to :meth:`_apply_fuzzy_match`.
        Same behavior as the Photo Tagging gramplet's "Fuzzy Match Lookup…"
        context menu item.

        :param _obj: The button that was clicked (unused).
        """
        if not self.dbstate.is_open():
            return
        show_fuzzy_lookup = get_fuzzy_match_lookup()
        if show_fuzzy_lookup is None:
            self.refresh_fuzzy_button()
            return
        surname, given = split_name(self.de_widgets["NPName"].get_text())
        if not surname:
            active = self.get_active_object("Person")
            name_obj = active.get_primary_name() if active else None
            if name_obj:
                surname = name_obj.get_surname().strip()
        kwargs: dict[str, Any] = {
            "surname": surname,
            "given_name": given,
            "on_select": self._apply_fuzzy_match,
        }
        try:
            params = inspect.signature(show_fuzzy_lookup).parameters
            accepts_filter = "given_filter" in params
        except (TypeError, ValueError):
            accepts_filter = False
        if accepts_filter:
            kwargs["given_filter"] = given
        if accepts_filter and "select_hint" in params:
            kwargs["select_hint"] = _("updates Data Entry New Person")
        show_fuzzy_lookup(self.dbstate, self.uistate, [], **kwargs)

    def _apply_fuzzy_match(self, person: Person) -> None:
        """
        ``on_select`` callback of the Fuzzy Match Lookup window.

        Deferred to idle time: it is called from inside the lookup window's
        own row-activated handler.

        :param person: The person double-clicked in the lookup window.
        """
        GLib.idle_add(self._cb_link_person_idle, person.get_handle())

    def _cb_link_person_idle(self, handle: PersonHandle) -> bool:
        """
        Link the New person block to an existing person (idle callback).

        The name and gender fields are filled from that person, and Add
        then adds the relation (and any events, source or citation) to the
        existing person instead of creating a new one.

        :param handle: Handle of the person picked in the lookup window.
        :returns: ``False`` (run once).
        """
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
        except HandleError:
            person = None
        if person is None:
            return False
        name_obj = person.get_primary_name()
        surname = name_obj.get_surname() if name_obj else ""
        given = name_obj.get_first_name() if name_obj else ""
        self._linking = True
        try:
            self.de_widgets["NPName"].set_text(
                ", ".join(part for part in (surname, given) if part)
            )
            self.set_np_choice("NPGender", person.get_gender())
            recorded = self.recorded_relation(person)
            if recorded not in (None, self.NO_REL):
                self.set_np_choice("NPRelation", recorded)
        finally:
            self._linking = False
        self._linked_handle = handle
        entry = self.de_widgets["NPName"]
        entry.set_icon_from_icon_name(
            Gtk.EntryIconPosition.PRIMARY, "emblem-symbolic-link"
        )
        entry.set_icon_tooltip_text(
            Gtk.EntryIconPosition.PRIMARY,
            _(
                "Linked to the existing person %s [%s]. Add uses this person "
                "instead of creating a new one. Edit the name to unlink."
            )
            % (name_displayer.display(person), person.get_gramps_id()),
        )
        self.refresh_link_state()
        return False

    def unlink_person(self) -> None:
        """
        Forget the existing person linked by the Fuzzy Match Lookup window;
        Add creates a new person again.
        """
        self._linked_handle = None
        entry = self.de_widgets["NPName"]
        entry.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY, None)
        self.refresh_link_state()

    def cb_name_icon_pressed(
        self, entry: Gtk.Entry, position: Gtk.EntryIconPosition, _event: Any
    ) -> None:
        """
        Empty the New person name when its right-end (edit-clear) icon is
        clicked; that also drops a link to an existing person.

        :param entry: The name entry.
        :param position: Which icon (only the secondary one clears).
        :param _event: The button event (unused).
        """
        if position == Gtk.EntryIconPosition.SECONDARY:
            entry.set_text("")

    def cb_np_name_changed(self, _entry: Gtk.Entry) -> None:
        """
        Editing the New person name by hand drops a link to an existing
        person (the text no longer describes that person).

        :param _entry: The name entry (unused).
        """
        if not self._linking and self._linked_handle:
            self.unlink_person()

    def cb_linked_person_deleted(self, handle_list: list[PersonHandle]) -> None:
        """
        Drop the link if the linked person is deleted from the tree.

        :param handle_list: Handles of the deleted people.
        """
        if self._linked_handle in handle_list:
            self.unlink_person()

    # -- Citation context menu ---------------------------------------------

    def on_citation_rows(self, y: float) -> bool:
        """
        Return whether a position is on the source mode row or the chosen
        citation line below it.

        :param y: Position in the form's (EventBox) coordinates.
        :returns: ``True`` on those two rows.
        """
        row = self.de_widgets.get("Citation:Row")
        info = self.de_widgets.get("Citation:Info")
        if row is None or info is None:
            return False
        top = row.get_allocation().y - 2
        bottom_alloc = info.get_allocation()
        return top <= y <= bottom_alloc.y + bottom_alloc.height + 2

    def build_citation_menu(self) -> Gtk.Menu:
        """
        Build the context menu of the source/citation rows, for the chosen
        (active) citation: Add, Edit and Quick View, as for a Citation.

        :returns: The menu (shown).
        """
        menu = Gtk.Menu()
        is_open = self.dbstate.is_open()
        try:
            citation = self.selected_citation() if is_open else None
        except HandleError:
            citation = None
        handle = citation.get_handle() if citation else None
        self.add_menu_item(menu, _("Add..."), self.cb_add_citation, sensitive=is_open)
        self.add_menu_item(
            menu, _("Edit..."), self.cb_edit_citation, sensitive=citation is not None
        )
        menu.append(Gtk.SeparatorMenuItem())
        # pylint: disable-next=import-outside-toplevel
        from gramps.gen.plug import CATEGORY_QR_CITATION

        self.add_quick_view_menu(menu, handle, CATEGORY_QR_CITATION)
        menu.show_all()
        return menu

    def cb_add_citation(self, _item: Gtk.MenuItem) -> None:
        """
        Open the Edit Citation dialog for a new citation; once saved it
        becomes the chosen citation (Select Citation mode).

        :param _item: The menu item (unused).
        """
        try:
            gramps_editors.EditCitation(
                self.dbstate,
                self.uistate,
                [],
                Citation(),
                callback=self.cb_citation_added,
            )
        except WindowActiveError:
            pass

    def cb_citation_added(self, citation: Citation) -> None:
        """
        Make a newly added citation the chosen citation.

        :param citation: The saved citation.
        """
        self.use_citation(citation.get_handle())

    def use_citation(self, handle: CitationHandle) -> None:
        """
        Choose a citation and select Select Citation, without opening the
        Citation selector.

        :param handle: The citation to use.
        """
        self._citation_handle = handle
        radio = self.de_widgets["Active person:Show citation"]
        if radio.get_active():
            self.update_citation_display()
            return
        self._citation_preset = True
        try:
            radio.set_active(True)
        finally:
            self._citation_preset = False

    def cb_edit_citation(self, _item: Gtk.MenuItem) -> None:
        """
        Open the Edit Citation dialog for the chosen citation.

        :param _item: The menu item (unused).
        """
        citation = self.selected_citation()
        if citation is None:
            return
        try:
            gramps_editors.EditCitation(self.dbstate, self.uistate, [], citation)
        except WindowActiveError:
            pass

    # -- Association -------------------------------------------------------

    def cb_relation_popup_shown(self, combo: Gtk.ComboBoxText, _pspec: Any) -> None:
        """
        Open the Association editor when "Add an Association" is picked
        again (the menu closes without a "changed" signal).

        :param combo: The "Add relation" menu.
        :param _pspec: The property (unused).
        """
        if combo.get_property("popup-shown"):
            self._relation_picked = False
            return
        # The menu closes before it reports a pick ("changed"), so decide
        # from idle, once any pick has arrived.
        GLib.idle_add(self._cb_relation_popup_closed_idle)

    def _cb_relation_popup_closed_idle(self) -> bool:
        """
        After the "Add relation" menu closed: if nothing new was picked and
        "Add an Association" is selected, it was re-picked, so open the
        editor.

        :returns: ``False`` (run once).
        """
        if not self._relation_picked and (
            self.np_choice("NPRelation") == self.AS_ASSOCIATION
        ):
            self._cb_open_association_idle()
        return False

    def _cb_open_association_idle(self) -> bool:
        """
        Open the Person Reference Editor for the pending Association (idle
        callback, so the menu has closed first).

        It edits the Association already entered since the last Add, or a
        new one made from the one remembered for this Family Tree (see
        :meth:`default_association`).

        :returns: ``False`` (run once).
        """
        if not self.dbstate.is_open():
            return False
        ref = self._assoc_ref or self.default_association() or PersonRef()
        try:
            gramps_editors.EditPersonRef(
                self.dbstate, self.uistate, [], ref, self.cb_association_saved
            )
        except WindowActiveError:
            pass
        return False

    def cb_association_saved(self, ref: PersonRef) -> None:
        """
        Keep the Association from the editor for the next Add and remember
        it for this Family Tree.

        :param ref: The edited Association.
        """
        self._assoc_ref = ref
        self.save_association(ref)
        self.update_association_tooltip()

    def tree_id(self) -> str:
        """
        Return the id of the open Family Tree (its database folder name),
        the key of the remembered Association.

        :returns: The database id, or "" if unknown.
        """
        get_dbid = getattr(self.dbstate.db, "get_dbid", None)
        try:
            return str(get_dbid() or "") if get_dbid else ""
        except Exception:  # pylint: disable=broad-except
            return ""

    def save_association(self, ref: PersonRef) -> None:
        """
        Remember an Association in the .ini for the open Family Tree.

        Kept: the association text, privacy, citations, notes and the
        associated person, unless that person is the active person
        (then it stays "unset", meaning "the active person" next time).

        :param ref: The Association.
        """
        dbid = self.tree_id()
        if not dbid:
            return
        active = self.get_active("Person")
        stored = dict(CONFIG.get(ASSOCIATION_KEY))
        stored[dbid] = {
            "tree": self.dbstate.db.get_dbname() or "",
            "relation": ref.get_relation(),
            "private": bool(ref.get_privacy()),
            "person": "" if ref.ref == active else (ref.ref or ""),
            "citations": list(ref.get_citation_list()),
            "notes": list(ref.get_note_list()),
        }
        CONFIG.set(ASSOCIATION_KEY, stored)
        CONFIG.save()

    def default_association(self) -> PersonRef | None:
        """
        Make a new Association from the one remembered for the open Family
        Tree, dropping citations, notes or a person no longer in the tree.

        The associated person is the remembered override person, or the
        active person if none was set.

        :returns: The new Association, or ``None`` with no person to use.
        """
        db = self.dbstate.db
        saved = CONFIG.get(ASSOCIATION_KEY).get(self.tree_id(), {})

        def exists(getter: Callable[[Any], Any], handle: Any) -> bool:
            try:
                return bool(handle) and getter(handle) is not None
            except HandleError:
                return False

        ref = PersonRef()
        ref.set_relation(saved.get("relation", ""))
        ref.set_privacy(bool(saved.get("private", False)))
        citations = saved.get("citations", [])
        notes = saved.get("notes", [])
        ref.set_citation_list(
            [h for h in citations if exists(db.get_citation_from_handle, h)]
        )
        ref.set_note_list([h for h in notes if exists(db.get_note_from_handle, h)])
        person = saved.get("person", "")
        if not exists(db.get_person_from_handle, person):
            person = self.get_active("Person")
        if not person:
            return None
        ref.ref = person
        return ref

    def update_association_tooltip(self) -> None:
        """
        Describe the pending Association in the "Add relation" tooltip.
        """
        combo = self.de_widgets["NPRelation"]
        ref = self._assoc_ref
        if ref is None or not ref.ref:
            combo.set_tooltip_text(None)
            return
        try:
            other = self.dbstate.db.get_person_from_handle(ref.ref)
            name = name_displayer.display(other)
        except HandleError:
            name = "?"
        combo.set_tooltip_text(
            _("Association: %(relation)s, with %(person)s")
            % {"relation": ref.get_relation() or _("(no description)"), "person": name}
        )

    # -- Linked New person: header, recorded relation/gender, mismatches ----

    def np_choice(self, key: str) -> int:
        """
        Return the selected item of the NPRelation / NPGender menu, as the
        index of its normal item list.

        While a recorded value is offered as an extra first row (see
        :meth:`set_offer`), that row stands for the offered value and the
        normal items are shifted down by one.

        :param key: ``"NPRelation"`` or ``"NPGender"``.
        :returns: The item index (a relation or gender constant).
        """
        index = self.de_widgets[key].get_active()
        offered = self._offer[key]
        if offered is None or index < 0:
            return index
        return offered if index == 0 else index - 1

    def set_np_choice(self, key: str, value: int) -> None:
        """
        Select an item of the NPRelation / NPGender menu by its normal
        index (see :meth:`np_choice`).

        :param key: ``"NPRelation"`` or ``"NPGender"``.
        :param value: The item index (a relation or gender constant).
        """
        shift = 0 if self._offer[key] is None else 1
        self.de_widgets[key].set_active(value + shift)

    def set_offer(self, key: str, value: int | None, text: str = "") -> None:
        """
        Show (or remove) the linked person's recorded value as the first
        row of a menu, keeping the current selection.

        :param key: ``"NPRelation"`` or ``"NPGender"``.
        :param value: The recorded value to offer, or ``None`` to remove
            the offer row.
        :param text: The text of the offer row.
        """
        if self._offer[key] == value:
            return
        combo = self.de_widgets[key]
        self._syncing = True
        try:
            current = self.np_choice(key)
            if self._offer[key] is not None:
                combo.remove(0)
                self._offer[key] = None
            if value is not None:
                combo.prepend_text(text)
                self._offer[key] = value
            self.set_np_choice(key, current)
        finally:
            self._syncing = False

    def cb_np_choice_changed(self, combo: Gtk.ComboBoxText, key: str) -> None:
        """
        React to a pick in the NPRelation / NPGender menu: picking the offer
        row selects the recorded value; any pick rechecks the mismatches.

        :param combo: The menu.
        :param key: ``"NPRelation"`` or ``"NPGender"``.
        """
        if self._syncing:
            return
        offered = self._offer[key]
        if offered is not None and combo.get_active() == 0:
            self._syncing = True
            try:
                combo.remove(0)
                self._offer[key] = None
                combo.set_active(offered)
            finally:
                self._syncing = False
        if key == "NPRelation":
            self._relation_picked = True
            if self.np_choice(key) == self.AS_ASSOCIATION:
                GLib.idle_add(self._cb_open_association_idle)
            else:
                self._assoc_ref = None
                self.update_association_tooltip()
        self.schedule_link_refresh()

    def schedule_link_refresh(self) -> None:
        """
        Run :meth:`refresh_link_state` once from idle (not from inside a
        menu's own "changed" signal).
        """
        if not self._link_refresh_id:
            self._link_refresh_id = GLib.idle_add(self._cb_link_refresh_idle)

    def _cb_link_refresh_idle(self) -> bool:
        """
        Idle callback of :meth:`schedule_link_refresh`.

        :returns: ``False`` (run once).
        """
        self._link_refresh_id = 0
        self.refresh_link_state()
        return False

    def recorded_relation(self, person: Person) -> int | None:
        """
        Return how ``person`` is already related to the active person, as
        an "Add relation" menu value.

        Checked in this order: parent (Father / Mother by family role),
        spouse (Husband / Wife by family role), child, sibling.

        :param person: The linked person.
        :returns: A relation constant, ``AS_SELF`` for the active person
            themselves, ``NO_REL`` if not related that way, or ``None``
            without an active person.
        """
        active = self._dirty_person or self.get_active_object("Person")
        if active is None:
            return None
        if active.get_handle() == person.get_handle():
            return self.AS_SELF
        db = self.dbstate.db
        handle = person.get_handle()

        def families(handles: list[Any]) -> Iterator[Family]:
            for family_handle in handles:
                try:
                    family = db.get_family_from_handle(family_handle)
                except HandleError:
                    continue
                if family is not None:
                    yield family

        def has_child(family: Family) -> bool:
            return any(ref.ref == handle for ref in family.get_child_ref_list())

        parent_families = list(families(active.get_parent_family_handle_list()))
        for family in parent_families:
            if family.get_father_handle() == handle:
                return self.AS_FATHER
            if family.get_mother_handle() == handle:
                return self.AS_MOTHER
        own_families = list(families(active.get_family_handle_list()))
        for family in own_families:
            if family.get_father_handle() == handle:
                return self.AS_HUSBAND
            if family.get_mother_handle() == handle:
                return self.AS_WIFE
        if any(has_child(family) for family in own_families):
            return self.AS_CHILD
        if any(has_child(family) for family in parent_families):
            return self.AS_SIBLING
        return self.NO_REL

    def relation_exists(self, chosen: int, person: Person, active: Person) -> bool:
        """
        Return whether ``person`` is already in the families Add would
        link them into, so Add must not link them again.

        Parent and Sibling choices change the active person's parent
        families; Spouse and Child choices change the active person's own
        families. Any role in those families (parent or child) counts:
        that covers the relationship itself (no duplicate) and a second
        role in the same family (no double link, e.g. a sibling added as a
        parent).

        :param chosen: The selected "Add relation" value.
        :param person: The linked (existing) person.
        :param active: The active person.
        :returns: ``True`` if that relationship is already recorded.
        """
        db = self.dbstate.db
        handle = person.get_handle()

        def families(handles: list[Any]) -> Iterator[Family]:
            for family_handle in handles:
                try:
                    family = db.get_family_from_handle(family_handle)
                except HandleError:
                    continue
                if family is not None:
                    yield family

        def in_role(family_handles: list[Any]) -> bool:
            return any(
                handle in (family.get_father_handle(), family.get_mother_handle())
                for family in families(family_handles)
            )

        def is_child(family_handles: list[Any]) -> bool:
            return any(
                ref.ref == handle
                for family in families(family_handles)
                for ref in family.get_child_ref_list()
            )

        if chosen in (self.AS_PARENT, self.AS_MOTHER, self.AS_FATHER, self.AS_SIBLING):
            target = active.get_parent_family_handle_list()
        elif chosen in (self.AS_SPOUSE, self.AS_WIFE, self.AS_HUSBAND, self.AS_CHILD):
            target = active.get_family_handle_list()
        else:
            return False
        return in_role(target) or is_child(target)

    def relation_matches(self, chosen: int, recorded: int) -> bool:
        """
        Return whether the chosen "Add relation" fits the recorded one.

        A generic choice (Parent, Spouse) fits its specific forms, a
        recorded "not related" fits any family choice (Add then adds that
        new relationship), an Association fits anyone, and "Update self"
        fits only the active person themselves.

        :param chosen: The selected relation.
        :param recorded: The recorded relation.
        :returns: ``True`` if there is no mismatch.
        """
        if chosen == recorded or chosen == self.AS_ASSOCIATION:
            return True
        if self.AS_SELF in (chosen, recorded):
            return False  # "Update self" only fits the active person
        if recorded == self.NO_REL:
            return True
        parents = (self.AS_PARENT, self.AS_MOTHER, self.AS_FATHER)
        spouses = (self.AS_SPOUSE, self.AS_WIFE, self.AS_HUSBAND)
        if chosen == self.AS_PARENT and recorded in parents:
            return True
        return chosen == self.AS_SPOUSE and recorded in spouses

    def relation_noun(self, value: int) -> str:
        """
        Return a short name for a relation value, for the offer row.

        :param value: A relation constant.
        :returns: e.g. "Father".
        """
        return {
            self.AS_FATHER: _("Father"),
            self.AS_MOTHER: _("Mother"),
            self.AS_PARENT: _("Parent"),
            self.AS_HUSBAND: _("Husband"),
            self.AS_WIFE: _("Wife"),
            self.AS_SPOUSE: _("Spouse"),
            self.AS_SIBLING: _("Sibling"),
            self.AS_CHILD: _("Child"),
            self.AS_SELF: _("Self"),
        }.get(value, _("Not related"))

    def refresh_link_state(self) -> None:
        """
        Update the New person area for its link to an existing person.

        Linked: the header reads "Update person:" with the person's name;
        "Add relation" and "Gender" are compared with what the tree records
        for that person, and a mismatching menu is shown in the error color
        with the recorded value offered as its first row. Unlinked: the
        header, colors and menus are reset.
        """
        if "New person:Title" not in self.de_widgets:
            return  # still building the form
        person = self.area_person("new")
        title = self.de_widgets["New person:Title"]
        value = self.de_widgets["New person"]
        if person is None:
            title.set_markup(f"<b>{GLib.markup_escape_text(_('New person'))}</b>")
            value.set_text("")
            recorded_relation = recorded_gender = None
        else:
            title.set_markup(
                f"<b>{GLib.markup_escape_text(_('Update person:'))}</b>"
            )
            value.set_markup(
                f"<i>{GLib.markup_escape_text(name_displayer.display(person))}</i>"
            )
            recorded_relation = self.recorded_relation(person)
            recorded_gender = person.get_gender()
        chosen = self.np_choice("NPRelation")
        relation_bad = (
            recorded_relation is not None
            and not self.relation_matches(chosen, recorded_relation)
        ) or (chosen == self.AS_SELF and recorded_relation != self.AS_SELF)
        gender_bad = (
            recorded_gender is not None
            and 0 <= recorded_gender < len(self._gender_labels)
            and self.np_choice("NPGender") != recorded_gender
        )
        # translators: offer row of a menu, e.g. "Recorded as: Father"
        offer = recorded_relation if relation_bad else None
        self.set_offer(
            "NPRelation",
            offer,
            _("Recorded as: %s") % self.relation_noun(recorded_relation or 0),
        )
        self.set_offer(
            "NPGender",
            recorded_gender if gender_bad else None,
            _("Recorded as: %s")
            % (self._gender_labels[recorded_gender] if gender_bad else ""),
        )
        set_mismatch_style(self.de_widgets["NPRelation"], relation_bad)
        set_mismatch_style(self.de_widgets["NPGender"], gender_bad)

    # -- Person drops ------------------------------------------------------

    @staticmethod
    def dropped_person_handle(sel_data: Gtk.SelectionData) -> PersonHandle | None:
        """
        Return the person handle of a Person drop, or ``None`` for any
        other kind of drop (e.g. plain text dropped on an entry).

        :param sel_data: The drop data.
        :returns: The dropped person's handle, or ``None``.
        """
        target = sel_data.get_target()
        if target is None or target.name() != DdTargets.PERSON_LINK.drag_type:
            return None
        try:
            data = pickle.loads(sel_data.get_data())
        except Exception:  # pylint: disable=broad-except
            return None
        if isinstance(data, tuple) and len(data) >= 3:
            return data[2]
        return None

    def area_at(self, y: float) -> str:
        """
        Return which area of the form a vertical position is in.

        :param y: Position in the form's (EventBox) coordinates.
        :returns: ``"new"`` for the New person area, else ``"active"``.
        """
        title = self.de_widgets.get("New person:Title")
        if title is None:
            return "active"
        return "new" if y >= title.get_allocation().y - 4 else "active"

    def accept_person_drops(self, entry: Gtk.Entry, area: str) -> None:
        """
        Let a text entry accept Person drops for its area as well as text.

        :param entry: The entry.
        :param area: ``"active"`` or ``"new"``.
        """
        targets = entry.drag_dest_get_target_list()
        if targets is None:
            targets = Gtk.TargetList.new([])
            entry.drag_dest_set_target_list(targets)
        person_link = DdTargets.PERSON_LINK
        targets.add(person_link.atom_drag_type, 0, person_link.app_id)
        entry.connect("drag-data-received", self.cb_entry_drag_received, area)

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def cb_entry_drag_received(
        self,
        entry: Gtk.Entry,
        context: Gdk.DragContext,
        _x: int,
        _y: int,
        sel_data: Gtk.SelectionData,
        _info: int,
        time: int,
        area: str,
    ) -> None:
        """
        Handle a Person dropped on a text entry; other drops (text) are
        left to the entry itself.

        :param entry: The entry dropped on.
        :param context: The drag context.
        :param sel_data: The drop data.
        :param time: The event time.
        :param area: ``"active"`` or ``"new"``.
        """
        handle = self.dropped_person_handle(sel_data)
        if handle is None:
            return
        entry.stop_emission_by_name("drag-data-received")
        Gtk.drag_finish(context, True, False, time)
        # Act only once the drag has fully ended (see cb_form_drag_received).
        GLib.idle_add(self._cb_person_dropped_idle, area, handle)

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def cb_form_drag_received(
        self,
        _widget: Gtk.Widget,
        _context: Gdk.DragContext,
        _x: int,
        y: int,
        sel_data: Gtk.SelectionData,
        _info: int,
        _time: int,
    ) -> None:
        """
        Handle a Person dropped on a label or gap of the form.

        :param y: Drop position in the form's coordinates.
        :param sel_data: The drop data.
        """
        handle = self.dropped_person_handle(sel_data)
        if handle is not None:
            # Changing the active person here, while the drag is still
            # finishing, makes the source view refresh under the drag and
            # GTK then reports criticals about the destroyed drag icon;
            # so act from idle, after the drag has ended.
            GLib.idle_add(self._cb_person_dropped_idle, self.area_at(y), handle)

    def _cb_person_dropped_idle(self, area: str, handle: PersonHandle) -> bool:
        """
        Idle callback for a Person drop (see :meth:`person_dropped`).

        :param area: ``"active"`` or ``"new"``.
        :param handle: The dropped person's handle.
        :returns: ``False`` (run once).
        """
        self.person_dropped(area, handle)
        return False

    def person_dropped(self, area: str, handle: PersonHandle) -> None:
        """
        Use a dropped person: Active person area makes them the active
        person; New person area links them (see
        :meth:`_cb_link_person_idle`).

        :param area: ``"active"`` or ``"new"``.
        :param handle: The dropped person's handle.
        """
        if not self.dbstate.is_open():
            return
        if area == "new":
            self._cb_link_person_idle(handle)
            return
        if handle == self.get_active("Person"):
            return
        if self._dirty and not self.confirm_abandon():
            return
        self._dirty = False
        self.set_active("Person", handle)

    def confirm_abandon(self) -> bool:
        """
        Ask whether to abandon the unsaved Active person edits.

        :returns: ``True`` to abandon them.
        """
        return gramps_dialog.QuestionDialog2(
            _("Abandon the unsaved edits?"),
            _("The Active person area has edits that are not saved yet."),
            _("Abandon"),
            _("Keep editing"),
            parent=self.uistate.window,
        ).run()

    # -- Area context menus ------------------------------------------------

    def area_person(self, area: str) -> Person | None:
        """
        Return the person an area is linked to.

        :param area: ``"active"`` or ``"new"``.
        :returns: The active person, the New person linked by a lookup or
            drop, or ``None``.
        """
        if not self.dbstate.is_open():
            return None
        if area == "active":
            return self._dirty_person or self.get_active_object("Person")
        if not self._linked_handle:
            return None
        try:
            return self.dbstate.db.get_person_from_handle(self._linked_handle)
        except HandleError:
            return None

    def cb_form_button_press(self, widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        """
        Open the context menu of the area that was right-clicked.

        :param widget: The form EventBox.
        :param event: The button event.
        :returns: ``True`` if a menu was shown.
        """
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        if not event.triggers_context_menu():
            return False
        window = widget.get_window()
        _win, _x, y, _mask = window.get_device_position(event.get_device())
        if self._area_menu is not None:
            self._area_menu.destroy()
        if self.on_citation_rows(y):
            self._area_menu = self.build_citation_menu()
        else:
            self._area_menu = self.build_area_menu(self.area_at(y))
        self._area_menu.attach_to_widget(widget, None)
        self._area_menu.popup_at_pointer(event)
        return True

    @staticmethod
    def add_menu_item(
        menu: Gtk.Menu,
        label: str,
        callback: Callable[..., Any] | None,
        *args: Any,
        sensitive: bool = True,
    ) -> Gtk.MenuItem:
        """
        Append a plain menu item.

        :param menu: The menu.
        :param label: The item text.
        :param callback: Called as ``callback(item, *args)``.
        :param args: Extra callback arguments.
        :param sensitive: Whether the item can be chosen.
        :returns: The item.
        """
        item = Gtk.MenuItem(label=label)
        if callback is not None:
            item.connect("activate", callback, *args)
        item.set_sensitive(sensitive)
        menu.append(item)
        return item

    def build_area_menu(self, area: str) -> Gtk.Menu:
        """
        Build the context menu of one area.

        A linked area starts with the items of a Person view's own context
        menu for that person, then the area's own commands.

        :param area: ``"active"`` or ``"new"``.
        :returns: The menu (shown).
        """
        menu = Gtk.Menu()
        person = self.area_person(area)
        if person is not None:
            self.add_person_items(menu, person, area)
            menu.append(Gtk.SeparatorMenuItem())
        if area == "active":
            self.add_menu_item(
                menu, _("Save"), self.cb_save_data_edit, sensitive=self._dirty
            )
            self.add_menu_item(
                menu, _("Abandon"), self.cb_abandon_data_edit, sensitive=self._dirty
            )
        else:
            if fuzzy_match_registered():
                self.add_menu_item(
                    menu, _("Fuzzy Match Lookup..."), self.cb_fuzzy_lookup_clicked
                )
            if self._linked_handle:
                self.add_menu_item(
                    menu, _("Unlink the existing person"), self.cb_unlink_menu
                )
            self.add_menu_item(menu, _("Add"), self.cb_add_data_entry)
            self.add_menu_item(menu, _("Copy Active Data"), self.cb_copy_data_entry)
            self.add_menu_item(menu, _("Clear"), self.cb_clear_data_entry)
        menu.show_all()
        return menu

    def cb_unlink_menu(self, _item: Gtk.MenuItem) -> None:
        """
        Unlink the New person area from its existing person (menu item).

        :param _item: The menu item (unused).
        """
        self.unlink_person()

    def add_person_items(self, menu: Gtk.Menu, person: Person, area: str) -> None:
        """
        Append the items of a Person view context menu for ``person``:
        Back, Forward, Home, Set Home Person; Add, Edit, Delete, Merge;
        Quick View and Web Connection submenus.

        Merge uses the person of the other area as the second person.

        :param menu: The menu.
        :param person: The area's person.
        :param area: ``"active"`` or ``"new"``.
        """
        db = self.dbstate.db
        history = self.uistate.get_history("Person")
        handle = person.get_handle()
        self.add_menu_item(
            menu, _("Back"), self.cb_history_step, -1, sensitive=not history.at_front()
        )
        self.add_menu_item(
            menu, _("Forward"), self.cb_history_step, 1, sensitive=not history.at_end()
        )
        self.add_menu_item(
            menu,
            _("Home"),
            self.cb_go_home,
            sensitive=db.get_default_handle() is not None,
        )
        self.add_menu_item(menu, _("Set Home Person"), self.cb_set_home, handle)
        menu.append(Gtk.SeparatorMenuItem())
        self.add_menu_item(menu, _("Add..."), self.cb_add_person_editor)
        self.add_menu_item(menu, _("Edit..."), self.cb_edit_person_menu, handle, area)
        self.add_menu_item(menu, _("Delete"), self.cb_delete_person, handle)
        other = self.area_person("new" if area == "active" else "active")
        can_merge = other is not None and other.get_handle() != handle
        self.add_menu_item(
            menu,
            _("Merge..."),
            self.cb_merge_people,
            handle,
            other.get_handle() if can_merge else None,
            sensitive=can_merge,
        )
        menu.append(Gtk.SeparatorMenuItem())
        self.add_quick_view_menu(menu, handle)
        self.add_web_connect_menu(menu, handle)

    def cb_history_step(self, _item: Gtk.MenuItem, step: int) -> None:
        """
        Go back or forward in the active person history (Back / Forward).

        :param _item: The menu item (unused).
        :param step: -1 for Back, 1 for Forward.
        """
        history = self.uistate.get_history("Person")
        if history.lock:
            return
        history.lock = True
        try:
            if step < 0 and not history.at_front():
                history.back()
            elif step > 0 and not history.at_end():
                history.forward()
            self.uistate.modify_statusbar(self.dbstate)
        finally:
            history.lock = False

    def cb_go_home(self, _item: Gtk.MenuItem) -> None:
        """
        Make the Home Person the active person.

        :param _item: The menu item (unused).
        """
        home = self.dbstate.db.get_default_handle()
        if home:
            self.person_dropped("active", home)

    def cb_set_home(self, _item: Gtk.MenuItem, handle: PersonHandle) -> None:
        """
        Make a person the Home Person.

        :param _item: The menu item (unused).
        :param handle: The person.
        """
        self.dbstate.db.set_default_person_handle(handle)

    def cb_add_person_editor(self, _item: Gtk.MenuItem) -> None:
        """
        Open the Edit Person dialog for a new, empty person.

        :param _item: The menu item (unused).
        """
        person = Person()
        person.primary_name.add_surname(Surname())
        person.primary_name.set_primary_surname(0)
        try:
            gramps_editors.EditPerson(self.dbstate, self.uistate, [], person)
        except WindowActiveError:
            pass

    def cb_edit_person_menu(
        self, _item: Gtk.MenuItem, handle: PersonHandle, area: str
    ) -> None:
        """
        Open the Edit Person dialog for an area's person.

        :param _item: The menu item (unused).
        :param handle: The person.
        :param area: ``"active"`` reloads the area when the editor closes.
        """
        if area == "active":
            self.cb_edit_person()
            return
        try:
            person = self.dbstate.db.get_person_from_handle(handle)
            gramps_editors.EditPerson(self.dbstate, self.uistate, [], person)
        except (HandleError, WindowActiveError):
            pass

    def cb_delete_person(self, _item: Gtk.MenuItem, handle: PersonHandle) -> None:
        """
        Delete a person from the tree, after confirmation.

        :param _item: The menu item (unused).
        :param handle: The person.
        """
        db = self.dbstate.db
        try:
            person = db.get_person_from_handle(handle)
        except HandleError:
            return
        name = name_displayer.display(person)
        if not gramps_dialog.QuestionDialog2(
            _("Delete %s?") % f"{name} [{person.get_gramps_id()}]",
            _("Deleting the person will remove the person from the database."),
            _("Delete"),
            _("Cancel"),
            parent=self.uistate.window,
        ).run():
            return
        with DbTxn(_("Delete Person (%s)") % name, db) as trans:
            db.delete_person_from_database(person, trans)

    def cb_merge_people(
        self, _item: Gtk.MenuItem, handle1: PersonHandle, handle2: PersonHandle | None
    ) -> None:
        """
        Open the Merge People dialog for the people of the two areas.

        :param _item: The menu item (unused).
        :param handle1: This area's person.
        :param handle2: The other area's person.
        """
        if not handle2:
            return
        from gramps.gui.merge import (  # pylint: disable=import-outside-toplevel
            MergePerson,
        )

        MergePerson(self.dbstate, self.uistate, [], handle1, handle2)

    def add_quick_view_menu(
        self, menu: Gtk.Menu, handle: Any, category: int | None = None
    ) -> None:
        """
        Append the Quick View submenu (quick reports of one category).

        :param menu: The menu.
        :param handle: The object the reports run on.
        :param category: A ``CATEGORY_QR_*`` constant; Person by default.
        """
        # pylint: disable=import-outside-toplevel
        from gramps.gen.plug import CATEGORY_QR_PERSON
        from gramps.gui.plug.quick import run_report
        from gramps.gui.pluginmanager import GuiPluginManager

        if category is None:
            category = CATEGORY_QR_PERSON
        pmgr = GuiPluginManager.get_instance()
        reports = sorted(
            (
                pdata
                for pdata in pmgr.get_reg_quick_reports()
                if pdata.supported and pdata.category == category
            ),
            key=lambda pdata: pdata.name,
        )
        item = Gtk.MenuItem(label=_("Quick View"))
        submenu = Gtk.Menu()
        for pdata in reports:
            sub = Gtk.MenuItem(label=pdata.name)
            sub.connect(
                "activate",
                lambda _w, pd=pdata: run_report(
                    self.dbstate, self.uistate, category, handle, pd
                ),
            )
            submenu.append(sub)
        item.set_submenu(submenu)
        item.set_sensitive(bool(reports) and bool(handle))
        menu.append(item)

    def add_web_connect_menu(self, menu: Gtk.Menu, handle: PersonHandle) -> None:
        """
        Append the Web Connection submenu (registered WebConnect plugins).

        :param menu: The menu.
        :param handle: The person the web searches use.
        """
        # pylint: disable=import-outside-toplevel
        from gramps.gui.pluginmanager import GuiPluginManager

        connections: list[Any] = []

        def flatten(items: Any) -> None:
            for entry in items:
                if isinstance(entry, (list, tuple)):
                    flatten(entry)
                else:
                    connections.append(entry)

        try:
            plugins = GuiPluginManager.get_instance().process_plugin_data("WebConnect")
            flatten(plug("Person") if callable(plug) else plug for plug in plugins)
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Web Connection plugins failed to load", exc_info=True)
            connections = []
        connections.sort(key=lambda connect: connect.name)
        item = Gtk.MenuItem(label=_("Web Connection"))
        submenu = Gtk.Menu()
        for connect in connections:
            callback = connect(self.dbstate, self.uistate, "Person", handle)
            sub = Gtk.MenuItem(label=connect.name)
            sub.connect("activate", lambda widget, cb=callback: cb(widget))
            submenu.append(sub)
        item.set_submenu(submenu)
        item.set_sensitive(bool(connections))
        menu.append(item)

    def db_changed(self) -> None:
        """
        Follow database changes (Gramplet API hook).

        If a person or family changes, the relatives of the active person
        might have changed. A chosen citation only makes sense in one tree,
        so it is forgotten when the tree changes.
        """
        self.connect(self.dbstate.db, "person-add", self.update)
        self.connect(self.dbstate.db, "person-delete", self.update)
        self.connect(self.dbstate.db, "person-update", self.update)
        self.connect(self.dbstate.db, "family-add", self.update)
        self.connect(self.dbstate.db, "family-delete", self.update)
        self.connect(self.dbstate.db, "person-rebuild", self.update)
        self.connect(self.dbstate.db, "family-rebuild", self.update)
        self._dirty = False
        self._dirty_person = None
        self.connect(self.dbstate.db, "person-delete", self.cb_linked_person_deleted)
        self.connect(self.dbstate.db, "citation-delete", self.cb_citation_deleted)
        self.connect(self.dbstate.db, "citation-update", self.cb_citation_updated)
        self._citation_handle = None
        self._linked_handle = None
        self._assoc_ref = None
        self.select_sources_mode()
        self.update_citation_display()
        self.cb_clear_data_entry(None)

    def active_changed(self, handle: PersonHandle) -> None:
        """
        Refresh when the active person changes (Gramplet API hook).

        :param handle: Handle of the new active person.
        """
        self.update()

    def select_sources_mode(self) -> None:
        """
        Select Enter Sources (only if not already selected).

        Selecting it deselects Select Citation through the radio group,
        which (via :meth:`cb_toggle_citation`) also forgets any chosen
        citation.
        """
        widget = self.de_widgets["Active person:Show sources"]
        if not widget.get_active():
            widget.set_active(True)

    def refresh_source_mode_widgets(self) -> None:
        """
        Show the right field for each sourceable row, hide the rest.

        Enter Sources shows the entry and its "Source:" label; Select
        Citation shows the "Use citation" check button instead; None hides
        both.
        """
        sources_on = self.de_widgets["Active person:Show sources"].get_active()
        citation_on = self.de_widgets["Active person:Show citation"].get_active()
        for key in self.SOURCE_KEYS:
            for name, visible in (
                (key, sources_on),
                (key + ":Label", sources_on),
                (key + ":Citation", citation_on),
            ):
                widget = self.de_widgets.get(name)
                if widget is not None:
                    widget.set_visible(visible)

    def cb_toggle_sources(self, _widget: Gtk.RadioButton) -> None:
        """
        Handle the Enter Sources radio button.

        The radio group keeps this mutually exclusive with Select Citation
        and None.

        :param _widget: The Enter Sources radio button (unused; its state
            is read directly by :meth:`refresh_source_mode_widgets`).
        """
        self.refresh_source_mode_widgets()

    def cb_toggle_citation(self, widget: Gtk.RadioButton) -> None:
        """
        Handle the Select Citation radio button.

        Selecting it opens the Citation selector and (through the radio
        group) deselects Enter Sources. If no valid citation is chosen,
        selection reverts to Enter Sources, which re-enters this callback
        (now deselected) to forget the citation.

        :param widget: The Select Citation radio button.
        """
        if widget.get_active() and self._citation_preset:
            pass  # citation already chosen (see use_citation)
        elif widget.get_active():
            if not self.pick_citation():
                self.select_sources_mode()
                return  # the revert re-enters here, deselected, to tidy up
        else:
            self._citation_handle = None
        self.update_citation_display()
        self.refresh_source_mode_widgets()

    def pick_citation(self) -> bool:
        """
        Open the Citation selector.

        :returns: ``True`` if a Citation was chosen (cancelling, or picking a
            Source row, gives ``False``).
        """
        if not self.dbstate.is_open():
            return False
        selector = gramps_selectors.SelectorFactory("Citation")(
            self.dbstate, self.uistate, self.track
        )
        picked = selector.run()
        if not isinstance(picked, Citation):  # cancelled, or a Source row
            return False
        self._citation_handle = picked.get_handle()
        return True

    def selected_citation(self) -> Citation | None:
        """
        Return the chosen Citation, or ``None`` (none chosen, or deleted).
        """
        if not self._citation_handle:
            return None
        return self.dbstate.db.get_citation_from_handle(self._citation_handle)

    def describe_citation(self) -> str | None:
        """
        Describe the chosen citation for the user.

        :returns: ``Date; Volume/Page; Source title`` (empty parts left out),
            or ``None`` if no citation is chosen.
        """
        citation = self.selected_citation()
        if citation is None:
            return None
        source = self.dbstate.db.get_source_from_handle(citation.get_reference_handle())
        parts = [
            get_date(citation),
            citation.get_page(),
            source.get_title() if source else "",
        ]
        return "; ".join(part for part in parts if part)

    def update_citation_display(self) -> None:
        """
        Show the chosen citation next to the Select Citation radio button.
        """
        text = self.describe_citation() or ""
        info = self.de_widgets["Citation:Info"]
        info.set_text(text)
        info.set_tooltip_text(text or None)
        self.de_widgets["Active person:Show citation"].set_tooltip_text(
            _("Choose a citation to attach to the new records (instead of Sources).")
        )

    def cb_citation_deleted(self, handle_list: list[CitationHandle]) -> None:
        """
        Select Enter Sources if the chosen citation was deleted.

        :param handle_list: Handles of the deleted citations.
        """
        if self._citation_handle in handle_list:
            self.select_sources_mode()

    def cb_citation_updated(self, handle_list: list[CitationHandle]) -> None:
        """
        Refresh the citation display if the chosen citation was edited.

        :param handle_list: Handles of the updated citations.
        """
        if self._citation_handle in handle_list:
            self.update_citation_display()

    def add_selected_citation(self, obj: Person | Event, checkbox_key: str) -> bool:
        """
        Attach the chosen citation to an object, field by field.

        Citation mode alone is not enough: the field's own "Use citation"
        check button (see :meth:`make_source_field`) must also be checked,
        the same way a Source field's text governs Enter Sources mode.

        :param obj: The person or event to attach it to.
        :param checkbox_key: Key of that field's "Use citation" check button.
        :returns: ``True`` if ``obj`` was changed, so the caller must commit it.
        """
        if (
            self.de_widgets["Active person:Show citation"].get_active()
            and self.de_widgets[checkbox_key].get_active()
            and self.selected_citation() is not None
        ):
            obj.add_citation(self._citation_handle)
            return True
        return False
