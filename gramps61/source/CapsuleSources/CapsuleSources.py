# Based on Genealogy Capsule, Copyright (c) 2026 the Genealogy Capsule authors
# (mjlawless), MIT License:
# https://github.com/mjlawless/capsule-genealogy/blob/main/LICENSE
#
# Capsule Sources - Gramps tool window (CapsuleSources.py)
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
#
# GPL-2.0-or-later.
#
# DRAFT MODE: working and readable first; not yet commit-ready.

"""Tool window: list Capsule captures and import the selected ones."""

import logging
import os
import pickle

from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.lib import Name, Person, Surname
from gramps.gen.plug import BasePluginManager, PluginRegister
from gramps.gui.display import display_help, display_url
from gramps.gen.errors import WindowActiveError
from gramps.gui.dialog import ErrorDialog, OkDialog, WarningDialog
from gramps.gui.editors import EditCitation, EditFamily, EditPerson
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.plug import tool
from gramps.gui.selectors import SelectorFactory
from gramps.gui.utils import open_file_with_default_application

from capsule_import import (
    cite_person,
    get_person,
    import_captures,
    imported_capture_ids,
    uncite_person,
)
from capsule_people import CapturePeople, capsule_clue, split_placeholder_name
from capsule_reader import default_captures_root, read_all

try:
    _ = glocale.get_addon_translator(__file__).gettext
except ValueError:
    _ = glocale.translation.gettext

LOG = logging.getLogger(".CapsuleSources")

PLUGIN_ID = "CapsuleSources"  # id= in CapsuleSources.gpr.py

# ======================================================================
# BEGIN HELP BUTTON BLOCK -- smart Help button, modeled on the one in
# Addon Pack and Ship (AddonPackShip.py, on_help_icon_clicked()).
# Prefers this addon's README.md in Markdown Dash; falls back to the
# help_url from CapsuleSources.gpr.py in a browser.
# ======================================================================
_MARKDOWNDASH_ID = "markdowndash"
_HELP_ICON_NAME = "help-browser"
_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
_HELP_ICON_SVG = os.path.join(_MEDIA_DIR, "Gnome-help-browser.svg")


def resolve_help_icon(size=32):
    """Color help icon: icon theme first (keeps theming), then the bundled
    media/Gnome-help-browser.svg. Never a black-and-white symbolic icon."""
    theme = Gtk.IconTheme.get_default()
    info = theme.lookup_icon(_HELP_ICON_NAME, size, Gtk.IconLookupFlags.FORCE_SIZE)
    if info is not None and not info.is_symbolic():
        try:
            return Gtk.Image.new_from_pixbuf(info.load_icon())
        except GLib.Error:
            pass
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            _HELP_ICON_SVG, size, size, True
        )
        return Gtk.Image.new_from_pixbuf(pixbuf)
    except GLib.Error:
        LOG.warning("help button: no color help icon (missing %s?)", _HELP_ICON_SVG)
    return None


def find_local_readme(pdata):
    """Path of the addon's own README.md, or None."""
    if pdata is None or not pdata.fpath:
        return None
    path = os.path.join(pdata.fpath, "README.md")
    return path if os.path.isfile(path) else None


def resolve_markdown_dash_opener():
    """Markdown Dash open_markdown_file(), or None (logged) if unavailable."""
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        LOG.warning("help button: Markdown Dash is deactivated")
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        LOG.warning("help button: no plugin registered as '%s'", _MARKDOWNDASH_ID)
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        LOG.warning("help button: Markdown Dash at %s failed to load", pdata.fpath)
        return None
    opener = getattr(mod, "open_markdown_file", None)
    if opener is None:
        LOG.warning(
            "help button: Markdown Dash at %s has no open_markdown_file()",
            pdata.fpath,
        )
    return opener


def open_help_url(pdata, parent):
    """Open the registered help_url; a bare wiki title goes to the wiki."""
    url = getattr(pdata, "help_url", None) if pdata else None
    if not url:
        OkDialog(
            _("No help available"),
            _("This addon has no README.md and no help_url."),
            parent=parent,
        )
    elif url.startswith(("http://", "https://")):
        display_url(url)
    else:
        display_help(webpage=url)


def cb_show_help(_button, uistate, plugin_id, parent):
    pdata = PluginRegister.get_instance().get_plugin(plugin_id)
    readme = find_local_readme(pdata)
    if readme:
        opener = resolve_markdown_dash_opener()
        if opener:
            try:
                opener(readme, uistate, parent=parent, addon_name=_("Capsule Sources"))
                return
            except Exception:  # pylint: disable=broad-except
                LOG.warning("help button: Markdown Dash could not open %s", readme)
    open_help_url(pdata, parent)


def add_help_button(container, uistate, plugin_id, parent):
    """Pack the flat 32 px Help icon button at the start (left) of container."""
    button = Gtk.Button()
    image = resolve_help_icon(32)
    if image is not None:
        button.set_image(image)
    else:
        button.set_label(_("Help"))
    button.set_relief(Gtk.ReliefStyle.NONE)
    button.set_tooltip_text(_("Open the Capsule Sources documentation."))
    button.connect("clicked", cb_show_help, uistate, plugin_id, parent)
    container.pack_start(button, False, False, 0)
    return button


# END HELP BUTTON BLOCK
# ======================================================================
# ------------------------------------------------------------
# settings: CapsuleSources.ini next to this module
# ------------------------------------------------------------
CONFIG = configman.register_manager("CapsuleSources", __file__, use_plugins_path=False)
CONFIG.register("meta.plugin_id", PLUGIN_ID)
CONFIG.register("meta.schema_version", "1")
CONFIG.register("paths.captures-root", "")
CONFIG.register("options.show-superseded", False)
CONFIG.register("window.width", 1150)
CONFIG.register("window.height", 620)
CONFIG.register("window.pane-position", 760)
# column widths in pixels; 0 means "not set yet" (first run measures them)
for _key in ("status", "record", "person", "site", "captured", "files"):
    CONFIG.register(f"columns.{_key}", 0)
# viewer chosen for a content type when the desktop has no default for it,
# e.g. {"application/pdf": "google-chrome.desktop"}
CONFIG.register("viewers.by-type", {})
CONFIG.load()

_ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

# Context menu wording shared with the Photo Tagging gramplet
LINK_PERSON_TEXT = _("Link")
ADD_NEW_PERSON_TEXT = _("Add a new person")
CLEAR_REFERENCE_TEXT = _("Clear Reference")


def get_fuzzy_match_lookup():
    """show_fuzzy_lookup() from the Fuzzy Matching addon's "Fuzzy Match API"
    GENERAL plugin, or None when that addon is missing or too old. Same
    registry lookup as Photo Tagging's _get_fuzzy_match_lookup(): a bare
    import would fail, because Gramps puts another addon's folder on
    sys.path only while it imports that addon itself."""
    pmgr = BasePluginManager.get_instance()
    pdata = pmgr.get_plugin("Fuzzy Match API")
    if pdata is None:
        return None
    try:
        module = pmgr.import_plugin(pdata)
    except ImportError:
        return None
    return getattr(module, "show_fuzzy_lookup", None) if module else None


def placeholder_name(text):
    """Show a typed or Capsule-read name in the user's name display format
    (Preferences > Display > Name format), as Photo Tagging does."""
    given, surname = split_placeholder_name(text)
    if not given and not surname:
        return text or ""
    name = Name()
    name.set_first_name(given)
    if surname:
        surname_obj = Surname()
        surname_obj.set_surname(surname)
        name.set_surname_list([surname_obj])
    return name_displayer.display_name(name)


# list columns, in the order of the Capsule Captures Index
(
    COL_PICK,
    COL_STATUS,
    COL_RECORD,
    COL_PERSON,
    COL_SITE,
    COL_CAPTURED,
    COL_FILES,
    COL_ID,
    COL_ACTIVE,
    COL_SORT_TIME,
    COL_TOOLTIP,
) = range(11)

# chip colors (light background, dark text: readable in light and dark themes)
# chip tints: a see-through color behind the theme's own text color, so the
# chips read well in both light and dark themes
CHIP_ALPHA = "28%"
CHIP = {
    "extracted": "#c8861e",
    "reviewed": "#3a7bd5",
    "captured": "#808080",
    "superseded": "#808080",
    "not read yet": "#d4b000",
    "incomplete": "#d03030",
    "in tree": "#2e9e2e",
    "file": "#808080",
}
DASH = "\u2014"
CAPSULE_ICON = os.path.join(_MEDIA_DIR, "GenealogyCapsule-32.png")


def esc(text):
    return GLib.markup_escape_text(str(text or ""))


def chip(text, kind=None):
    tint = CHIP.get(kind or text, CHIP["file"])
    return (
        f'<span background="{tint}" bgalpha="{CHIP_ALPHA}" size="small">'
        f"\u2009{esc(text)}\u2009</span>"
    )


# rollover for the copy captions in the right panel: a faint tint of the
# theme text color behind the row, and the copy icon from dim to full
_COPY_CSS = b"""
.capsule-copy { border-radius: 3px; }
.capsule-copy image { opacity: 0.55; }
.capsule-copy:hover { background-color: alpha(currentColor, 0.12); }
.capsule-copy:hover image { opacity: 1; }
"""
_css_installed = False


def install_copy_css():
    global _css_installed  # pylint: disable=global-statement
    if _css_installed:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(_COPY_CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _css_installed = True


def stamp(iso):
    """2026-10-29T16:05:27Z -> 2026-10-29 16:05 UTC (Capsule writes UTC)."""
    if not iso or len(iso) < 16:
        return iso or ""
    return f"{iso[:10]} {iso[11:16]} UTC"


# ------------------------------------------------------------
# MultiFacet
# ------------------------------------------------------------
class MultiFacet:
    """Several-choice filter: a dropdown of tick boxes with counts and a
    Clear button, like the Record and Site filters of the Captures Index.
    Nothing ticked means everything passes."""

    def __init__(self, all_label, noun, on_change):
        self.all_label = all_label
        self.noun = noun
        self.on_change = on_change
        self.chosen = set()
        self.boxes = {}
        self.button = Gtk.MenuButton()
        self.label = Gtk.Label(label=all_label)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.set_max_width_chars(18)
        inner = Gtk.Box(spacing=4)
        inner.pack_start(self.label, True, True, 0)
        inner.pack_start(
            Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.BUTTON),
            False,
            False,
            0,
        )
        self.button.add(inner)
        self.popover = Gtk.Popover()
        self.button.set_popover(self.popover)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.list_box.set_border_width(8)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(360)
        scroll.add(self.list_box)
        self.popover.add(scroll)

    def set_values(self, counts):
        """Rebuild the tick boxes from {value: count}; keep surviving ticks."""
        self.chosen &= set(counts)
        for child in self.list_box.get_children():
            self.list_box.remove(child)
        self.boxes = {}
        for value in sorted(counts, key=str.lower):
            box = Gtk.CheckButton(label=f"{value} ({counts[value]})")
            box.set_active(value in self.chosen)
            box.connect("toggled", self.cb_toggled, value)
            self.list_box.pack_start(box, False, False, 0)
            self.boxes[value] = box
        clear = Gtk.Button(label=_("Clear"))
        clear.set_relief(Gtk.ReliefStyle.NONE)
        clear.set_halign(Gtk.Align.START)
        clear.connect("clicked", self.cb_clear)
        self.list_box.pack_start(clear, False, False, 0)
        self.list_box.show_all()
        self.summarize()

    def summarize(self):
        if not self.chosen:
            text = self.all_label
        elif len(self.chosen) == 1:
            text = next(iter(self.chosen))
        else:
            text = f"{len(self.chosen)} {self.noun}"
        self.label.set_text(text)
        self.button.set_tooltip_text(", ".join(sorted(self.chosen)) or None)

    def passes(self, value):
        return not self.chosen or value in self.chosen

    def cb_toggled(self, box, value):
        if box.get_active():
            self.chosen.add(value)
        else:
            self.chosen.discard(value)
        self.summarize()
        self.on_change()

    def cb_clear(self, *args):
        self.chosen.clear()
        for box in self.boxes.values():
            box.handler_block_by_func(self.cb_toggled)
            box.set_active(False)
            box.handler_unblock_by_func(self.cb_toggled)
        self.summarize()
        self.on_change()


# ------------------------------------------------------------
# SingleFacet
# ------------------------------------------------------------
class SingleFacet:
    """One-choice filter, like the Status and Read or not filters."""

    def __init__(self, all_label, on_change):
        self.all_label = all_label
        self.on_change = on_change
        self.combo = Gtk.ComboBoxText()
        self.handler = self.combo.connect("changed", lambda *a: self.on_change())
        self.set_values({})

    def set_values(self, counts, labels=None):
        """Rebuild the choices from {value: count}; keep the current choice."""
        current = self.combo.get_active_id() or ""
        labels = labels or {}
        self.combo.handler_block(self.handler)
        self.combo.remove_all()
        self.combo.append("", self.all_label)
        for value in sorted(counts):
            self.combo.append(value, f"{labels.get(value, value)} ({counts[value]})")
        if not self.combo.set_active_id(current):
            self.combo.set_active_id("")
        self.combo.handler_unblock(self.handler)

    def passes(self, value):
        current = self.combo.get_active_id() or ""
        return not current or value == current


# ------------------------------------------------------------
# CapsuleSources
# ------------------------------------------------------------
class CapsuleSources(tool.Tool, ManagedWindow):
    def __init__(self, dbstate, user, options_class, name, callback=None):
        uistate = user.uistate
        self.title = _("Capsule Sources")
        tool.Tool.__init__(self, dbstate, options_class, name)
        ManagedWindow.__init__(self, uistate, [], self.__class__)
        # tool.Tool keeps only dbstate.db; the editors and selectors need
        # dbstate itself
        self.dbstate = dbstate

        self.captures = {}  # capture_id -> Capture
        self.in_tree = {}  # capture_id -> citation handle
        self.picked = set()  # capture ids ticked for import
        self.current = None  # Capture shown in the preview
        self.people = CapturePeople(_ADDON_DIR)  # names and linked people
        self.tree_id = self.db.get_dbid()  # links are kept per family tree
        self.columns = {}  # config key -> Gtk.TreeViewColumn
        self.editing_person_path = None  # Person cell open for typing
        self.link_rgba = None
        self.db_keys = [
            self.db.connect(signal, self.cb_db_people_changed)
            for signal in ("person-update", "person-delete")
        ]

        window = Gtk.Window()
        window.set_default_size(CONFIG.get("window.width"), CONFIG.get("window.height"))
        window.connect("key-press-event", self.on_key_press)
        self.set_window(window, None, self.title)
        window.add(self.build_ui())

        root = CONFIG.get("paths.captures-root") or str(default_captures_root())
        if os.path.isdir(root):
            self.folder_button.set_filename(root)
        self.reload(root)
        self.show()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def build_ui(self):
        install_copy_css()
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_border_width(8)

        # folder row
        row = Gtk.Box(spacing=6)
        refresh = Gtk.Button()
        if os.path.isfile(CAPSULE_ICON):
            refresh.set_image(Gtk.Image.new_from_file(CAPSULE_ICON))
        else:
            refresh.set_label(_("Refresh"))
        refresh.set_relief(Gtk.ReliefStyle.NONE)
        refresh.set_tooltip_text(
            _(
                "Refresh: read the Capsule captures folder again, to show "
                "captures made since this window opened."
            )
        )
        refresh.connect("clicked", self.cb_refresh)
        row.pack_start(refresh, False, False, 0)
        row.pack_start(Gtk.Label(label=_("Capsule captures folder:")), False, False, 0)
        self.folder_button = Gtk.FileChooserButton(
            title=_("Select the Capsule captures folder"),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        self.folder_button.connect("file-set", self.on_folder_set)
        # about a third of the window wide (kept so in cb_vbox_allocate);
        # the rest of the row is the folder statistics readout
        self.folder_button.set_width_chars(8)
        self.folder_width = CONFIG.get("window.width") // 3
        self.folder_button.set_size_request(self.folder_width, -1)
        row.pack_start(self.folder_button, False, False, 0)
        self.folder_stats = Gtk.Label(xalign=1)  # butted against the right
        self.folder_stats.set_ellipsize(Pango.EllipsizeMode.START)
        self.folder_stats.set_margin_start(6)
        row.pack_start(self.folder_stats, True, True, 0)
        vbox.pack_start(row, False, False, 0)
        vbox.connect("size-allocate", self.cb_vbox_allocate)

        # filter row, modeled on the Captures Index controls
        row = Gtk.Box(spacing=6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text(_("Filter captures\u2026"))
        self.search.set_tooltip_text(
            _(
                "Matches record type, person, site, status, citation, capture id, "
                "address, referenced documents and your notes."
            )
        )
        self.search.connect("search-changed", lambda *a: self.fill_list())
        row.pack_start(self.search, True, True, 0)
        self.f_record = MultiFacet(_("All records"), _("record types"), self.fill_list)
        self.f_site = MultiFacet(_("All sites"), _("sites"), self.fill_list)
        self.f_status = SingleFacet(_("All statuses"), self.fill_list)
        self.f_read = SingleFacet(_("Read or not"), self.fill_list)
        self.f_tree = SingleFacet(_("In tree or not"), self.fill_list)
        row.pack_start(self.f_record.button, False, False, 0)
        row.pack_start(self.f_site.button, False, False, 0)
        row.pack_start(self.f_status.combo, False, False, 0)
        row.pack_start(self.f_read.combo, False, False, 0)
        row.pack_start(self.f_tree.combo, False, False, 0)
        self.show_superseded = Gtk.CheckButton(label=_("Show superseded"))
        self.show_superseded.set_active(CONFIG.get("options.show-superseded"))
        self.show_superseded.connect("toggled", self.on_show_superseded)
        row.pack_start(self.show_superseded, False, False, 0)
        self.shown_label = Gtk.Label()
        row.pack_start(self.shown_label, False, False, 0)
        vbox.pack_start(row, False, False, 0)

        # list (left) and preview (right)
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.paned.pack1(self.build_list_stack(), True, False)
        self.paned.pack2(self.build_preview(), False, False)
        self.paned.set_position(CONFIG.get("window.pane-position"))
        vbox.pack_start(self.paned, True, True, 0)

        self.status = Gtk.Label(xalign=0)
        vbox.pack_start(self.status, False, False, 0)
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # bottom row: Help (lower left) ... Close, Import selected
        bbox = Gtk.Box(spacing=6)
        add_help_button(bbox, self.uistate, PLUGIN_ID, self.window)  # lower left
        for label, handler in (
            (_("Select all new"), self.on_select_new),
            (_("Select none"), self.on_select_none),
        ):
            button = Gtk.Button(label=label)
            button.connect("clicked", handler)
            bbox.pack_start(button, False, False, 0)
        self.import_button = Gtk.Button(label=_("Import selected"))
        self.import_button.get_style_context().add_class("suggested-action")
        self.import_button.connect("clicked", self.on_import)
        bbox.pack_end(self.import_button, False, False, 0)
        vbox.pack_start(bbox, False, False, 0)

        vbox.show_all()
        return vbox

    def build_list_stack(self):
        """The capture list, or a centered Genealogy Capsule icon with a
        message when there is nothing to show."""
        self.list_stack = Gtk.Stack()
        self.list_stack.add_named(self.build_list(), "list")

        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty.set_valign(Gtk.Align.CENTER)
        empty.set_halign(Gtk.Align.CENTER)
        logo = os.path.join(_MEDIA_DIR, "GenealogyCapsule-128.png")
        if os.path.isfile(logo):
            empty.pack_start(Gtk.Image.new_from_file(logo), False, False, 0)
        self.empty_label = Gtk.Label()
        self.empty_label.set_justify(Gtk.Justification.CENTER)
        self.empty_label.set_line_wrap(True)
        self.empty_label.set_max_width_chars(48)
        empty.pack_start(self.empty_label, False, False, 0)
        self.list_stack.add_named(empty, "empty")
        return self.list_stack

    def show_empty(self, message):
        self.empty_label.set_markup(f"<big>{esc(message)}</big>")
        self.list_stack.set_visible_child_name("empty")

    def build_list(self):
        self.store = Gtk.ListStore(
            bool, str, str, str, str, str, str, str, bool, str, str
        )
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_tooltip_column(COL_TOOLTIP)

        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.on_toggle)
        col = Gtk.TreeViewColumn(_("Import"), toggle, active=COL_PICK)
        col.add_attribute(toggle, "visible", COL_ACTIVE)
        self.view.append_column(col)

        saved = {
            key: CONFIG.get(f"columns.{key}")
            for key in ("status", "record", "person", "site", "captured", "files")
        }
        first_run = not any(saved.values())
        for key, title, index, markup, sort in (
            ("status", _("Status"), COL_STATUS, True, COL_STATUS),
            ("record", _("Record"), COL_RECORD, False, COL_RECORD),
            ("person", _("Person"), COL_PERSON, False, COL_PERSON),
            ("site", _("Site"), COL_SITE, False, COL_SITE),
            ("captured", _("Captured"), COL_CAPTURED, False, COL_SORT_TIME),
            ("files", _("Files"), COL_FILES, True, None),
        ):
            cell = Gtk.CellRendererText()
            if index == COL_PERSON:
                # like the Name column of Photo Tagging: a linked Person
                # shows as a link; otherwise an editable red placeholder
                cell.connect("editing-started", self.cb_person_editing_started)
                cell.connect("editing-canceled", self.cb_person_editing_canceled)
                cell.connect("edited", self.cb_person_edited)
            if index in (COL_PERSON, COL_SITE):
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            if index == COL_SITE:
                cell.set_property("family", "monospace")
            if index == COL_RECORD:
                cell.set_property("weight", Pango.Weight.BOLD)
            if index == COL_PERSON:
                col = Gtk.TreeViewColumn(title, cell)
                col.set_cell_data_func(cell, self.cb_person_cell_data)
            elif markup:
                col = Gtk.TreeViewColumn(title, cell, markup=index)
            else:
                col = Gtk.TreeViewColumn(title, cell, text=index)
            col.set_resizable(True)
            if saved[key] > 0:
                col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
                col.set_fixed_width(saved[key])
            elif first_run and key == "person":
                col.set_expand(True)  # measured once, then split with Site
            if sort is not None:
                col.set_sort_column_id(sort)
            self.view.append_column(col)
            self.columns[key] = col
        self.store.set_sort_column_id(COL_SORT_TIME, Gtk.SortType.DESCENDING)
        self.view.get_selection().connect("changed", self.on_selection_changed)
        self.view.connect("row-activated", self.cb_row_activated)
        self.view.connect("button-press-event", self.cb_list_button_press)
        self.build_context_menu()
        self.first_allocate = None
        if first_run:
            self.first_allocate = self.view.connect(
                "size-allocate", self.cb_first_allocate
            )

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.view)
        return scroll

    def build_preview(self):
        """Right-hand panel modeled on the Captures Index detail panel."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)

        def text_label(selectable=True):
            label = Gtk.Label(xalign=0)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_selectable(selectable)
            return label

        def heading(text):
            label = Gtk.Label(xalign=0)
            label.set_markup(f"<b>{esc(text)}</b>")
            label.set_margin_top(8)
            return label

        def caption(text, field=None):
            """Section caption; with field, a copy icon at its left copies
            that Capsule field of the shown capture."""
            label = Gtk.Label(xalign=0)
            label.set_markup(
                f'<span size="small" alpha="70%">{esc(text.upper())}</span>'
            )
            if field is None:
                label.set_margin_top(4)
                return label
            row = Gtk.Box(spacing=4)
            row.set_margin_top(4)  # inside the EventBox, so it is clickable too
            icon = Gtk.Image.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.MENU)
            icon.set_pixel_size(18)
            row.pack_start(icon, False, False, 0)
            row.pack_start(label, False, False, 0)
            # the whole caption row, full width and height, is the click
            # target; an EventBox, not a button, so there is no outline and
            # no padding to make the row taller
            target = Gtk.EventBox()
            target.icon = icon
            target.get_style_context().add_class("capsule-copy")
            target.add_events(
                Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
            )
            target.connect("enter-notify-event", self.cb_copy_hover, True)
            target.connect("leave-notify-event", self.cb_copy_hover, False)
            target.set_hexpand(True)
            target.add(row)
            target.set_tooltip_text(
                _("Copy the {section}").format(section=text.lower())
            )
            target.connect("button-release-event", self.cb_copy_field, field)
            target.connect("realize", self.cb_hand_cursor)
            return target

        self.pv_title = text_label()
        box.pack_start(self.pv_title, False, False, 0)
        self.pv_summary = text_label()
        box.pack_start(self.pv_summary, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=3)
        grid.set_margin_top(6)
        self.pv_values = {}
        keys = (
            ("person", _("Primary person")),
            ("source", _("Source")),
            ("type", _("Record type")),
            ("local", _("Local")),
            ("captured", _("Captured")),
            ("accessed", _("Accessed")),
            ("gating", _("Gating")),
            ("copyright", _("Copyright")),
            ("media", _("Media")),
            ("transcribed", _("Transcribed")),
            ("intree", _("In this tree")),
        )
        for row, (key, title) in enumerate(keys):
            name = Gtk.Label(label=title, xalign=0, yalign=0)
            name.get_style_context().add_class("dim-label")
            grid.attach(name, 0, row, 1, 1)
            value = text_label()
            value.set_hexpand(True)
            grid.attach(value, 1, row, 1, 1)
            if key == "local":
                # the capture folder name is a link that opens the folder
                value.connect("activate-link", self.cb_local_link)
            if key == "intree":
                value.connect("activate-link", self.cb_intree_link)
            if key == "person":
                value.connect("activate-link", self.cb_person_link)
            self.pv_values[key] = value
        box.pack_start(grid, False, False, 0)

        self.pv_problems = text_label()
        box.pack_start(self.pv_problems, False, False, 0)

        # the archived files, each with Open and Open with... buttons, for
        # desktops (like a fresh Fedora) with no viewer set for PDF or HTML
        self.pv_files_heading = heading(_("Files"))
        box.pack_start(self.pv_files_heading, False, False, 0)
        self.pv_files = Gtk.Grid(column_spacing=6, row_spacing=3)
        box.pack_start(self.pv_files, False, False, 0)

        box.pack_start(heading(_("Citation")), False, False, 0)
        box.pack_start(caption(_("Reference note"), "reference_note"), False, False, 0)
        self.pv_reference = text_label()
        box.pack_start(self.pv_reference, False, False, 0)
        box.pack_start(caption(_("Short note"), "short_note"), False, False, 0)
        self.pv_short = text_label()
        box.pack_start(self.pv_short, False, False, 0)
        box.pack_start(
            caption(_("Source list entry"), "source_list_entry"), False, False, 0
        )
        self.pv_list_entry = text_label()
        box.pack_start(self.pv_list_entry, False, False, 0)

        self.pv_people_heading = heading(_("People on this record"))
        box.pack_start(self.pv_people_heading, False, False, 0)
        self.pv_people = text_label()
        box.pack_start(self.pv_people, False, False, 0)

        self.pv_notes_heading = heading(_("Your notes"))
        box.pack_start(self.pv_notes_heading, False, False, 0)
        self.pv_notes = text_label()
        box.pack_start(self.pv_notes, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_size_request(280, -1)
        scroll.add(box)
        return scroll

    # --------------------------------------------------------
    # data
    # --------------------------------------------------------
    def reload(self, root=None):
        if root is None:
            root = self.folder_button.get_filename() or ""
        self.captures = {c.capture_id: c for c in read_all(root)} if root else {}
        self.in_tree = imported_capture_ids(self.db)
        self.picked &= set(self.captures)
        self.picked -= set(self.in_tree)
        self.update_facets()
        self.fill_list()
        self.update_folder_stats(root)

    def update_folder_stats(self, root):
        """One-line readout for the chosen folder; the tooltip has the rest."""
        caps = list(self.captures.values())
        if not caps:
            self.folder_stats.set_text("")
            self.folder_stats.set_tooltip_text(None)
            return
        total = len(caps)
        intree = sum(1 for c in caps if c.capture_id in self.in_tree)
        superseded = sum(1 for c in caps if c.superseded)
        new = sum(1 for c in caps if self.is_active(c))
        sites = len({c.site_label for c in caps})
        unread = sum(1 for c in caps if c.awaiting_reading)
        private = sum(1 for c in caps if c.is_private)
        linked = len(set(self.people.links(self.tree_id)) & set(self.captures))
        days = sorted(c.captured_at[:10] for c in caps if c.captured_at)
        size = 0
        for cap in caps:
            for path in cap.folder.rglob("*"):
                try:
                    if path.is_file():
                        size += path.stat().st_size
                except OSError:
                    pass
        span = ""
        if days:
            span = days[0] if days[0] == days[-1] else f"{days[0]} \u2013 {days[-1]}"
        captures_text = _("Captures: {n}").format(n=total)
        sites_text = _("Sites: {n}").format(n=sites)
        self.folder_stats.set_text(f"{captures_text} \u00b7 {sites_text}")
        self.folder_stats.set_tooltip_text(
            "\n".join(
                (
                    captures_text,
                    _("In this tree: {n}").format(n=intree),
                    _("Not yet in this tree: {n}").format(n=new),
                    _("Superseded: {n}").format(n=superseded),
                    _("Not read yet: {n}").format(n=unread),
                    _("Private (subscription or copyright): {n}").format(n=private),
                    _("Linked to a person in this tree: {n}").format(n=linked),
                    sites_text,
                    _("Captured: {span}").format(span=span or DASH),
                    _("Size on disk: {size}").format(size=GLib.format_size(size)),
                )
            )
        )

    def cb_vbox_allocate(self, vbox, allocation):
        width = allocation.width // 3
        if abs(width - self.folder_width) > 4:
            self.folder_width = width
            # not during this allocation: resizing here would re-enter it
            GLib.idle_add(self.cb_set_folder_width)

    def cb_set_folder_width(self):
        self.folder_button.set_size_request(self.folder_width, -1)
        return False

    def visible_pool(self):
        """Captures the facets count: superseded ones only when shown."""
        show_old = self.show_superseded.get_active()
        return [c for c in self.captures.values() if show_old or not c.superseded]

    def update_facets(self):
        """Facet choices and counts come from the captures themselves."""

        def count(values):
            counts = {}
            for value in values:
                counts[value] = counts.get(value, 0) + 1
            return counts

        pool = self.visible_pool()
        self.f_record.set_values(count(c.category for c in pool))
        self.f_site.set_values(count(c.site_label for c in pool))
        self.f_status.set_values(count(c.status for c in pool))
        self.f_read.set_values(count(c.reading for c in pool))
        self.f_tree.set_values(
            count(self.tree_state(c) for c in pool),
            {"in": _("In this tree"), "out": _("Not in this tree")},
        )

    def tree_state(self, cap):
        return "in" if cap.capture_id in self.in_tree else "out"

    def is_active(self, cap):
        """Can this capture be ticked for import?"""
        return cap.capture_id not in self.in_tree and not cap.superseded

    def status_markup(self, cap):
        # "in tree" first, so it stays visible when the column is narrow
        chips = []
        if cap.capture_id in self.in_tree:
            chips.append(chip(_("in tree"), "in tree"))
        chips.append(chip(cap.status))
        if cap.superseded:
            chips.append(chip(_("superseded"), "superseded"))
        if cap.awaiting_reading:
            chips.append(chip(_("not read yet"), "not read yet"))
        if cap.verify_ok is False:
            chips.append(chip(_("incomplete"), "incomplete"))
        return " ".join(chips)

    def files_markup(self, cap):
        parts = []
        if cap.gating == "gated":
            parts.append("\U0001f512")
        if cap.external_ref_count:
            parts.append(chip("\u2197 " + _("source")))
        parts.extend(chip(ftype) for ftype in cap.file_types)
        return " ".join(parts)

    def matches(self, cap, text):
        """Text box and every facet must agree, as in the Captures Index."""
        return (
            (
                not text
                or text in cap.search_blob
                or text in self.person_text(cap).lower()
            )
            and self.f_record.passes(cap.category)
            and self.f_site.passes(cap.site_label)
            and self.f_status.passes(cap.status)
            and self.f_read.passes(cap.reading)
            and self.f_tree.passes(self.tree_state(cap))
        )

    def fill_list(self):
        selected_id = self.current.capture_id if self.current else None
        self.store.clear()
        text = self.search.get_text().strip().lower()
        shown = new = 0
        select_iter = None
        for cap in self.visible_pool():
            if not self.matches(cap, text):
                continue
            active = self.is_active(cap)
            tip = cap.capture_id
            if cap.record_type:
                tip += "\n" + _("Record type: {type}").format(type=cap.record_type)
            if cap.verify_ok is False and cap.verify_shortfall:
                tip += "\n" + "; ".join(cap.verify_shortfall)
            clue = capsule_clue(cap)
            if clue and self.people.manual_name(cap.capture_id) is not None:
                tip += "\n" + _("Genealogy Capsule read: {name}").format(name=clue)
            if cap.capture_id in self.in_tree:
                tip += "\n" + _("Double-click to edit its Citation.")
            itr = self.store.append(
                [
                    active and cap.capture_id in self.picked,
                    self.status_markup(cap),
                    cap.category,
                    self.person_text(cap),
                    cap.site_label,
                    stamp(cap.captured_at),
                    self.files_markup(cap),
                    cap.capture_id,
                    active,
                    cap.captured_at or "",
                    esc(tip),
                ]
            )
            if cap.capture_id == selected_id:
                select_iter = itr
            shown += 1
            new += active
        self.shown_label.set_text(
            _("{n} of {total} shown").format(n=shown, total=len(self.visible_pool()))
        )
        self.status.set_text(
            _("{new} of the captures shown are not yet in this tree.").format(new=new)
        )
        if select_iter is None:
            select_iter = self.store.get_iter_first()
        if select_iter is not None:
            self.list_stack.set_visible_child_name("list")
            self.view.get_selection().select_iter(select_iter)
        else:
            if self.captures:
                self.show_empty(_("No captures match these filters."))
            else:
                self.show_empty(_("Please select a Capsule Captures folder."))
            self.show_preview(None)
        self.update_import_button()

    def update_import_button(self):
        self.import_button.set_sensitive(bool(self.picked))

    # --------------------------------------------------------
    # preview
    # --------------------------------------------------------
    def show_preview(self, cap):
        self.current = cap
        values = self.pv_values
        if cap is None:
            self.pv_title.set_markup(
                f"<big><b>{esc(_('No capture selected'))}</b></big>"
            )
            for label in (
                self.pv_summary,
                self.pv_problems,
                self.pv_reference,
                self.pv_short,
                self.pv_list_entry,
                self.pv_people,
                self.pv_notes,
                *values.values(),
            ):
                label.set_text("")
            for key in ("local", "person", "intree"):
                values[key].set_tooltip_text(None)
            self.fill_files(None)
            return

        person = self.linked_person(cap.capture_id)
        title = (
            (name_displayer.display(person) if person else "")
            or self.people.effective_name(cap)
            or cap.display_title
        )
        if person:
            link = f'<a href="person">{esc(name_displayer.display(person))}</a>'
            values["person"].set_markup(f"{link} [{esc(person.get_gramps_id())}]")
            values["person"].set_tooltip_text(_("Click to edit the Person."))
        else:
            placeholder = placeholder_name(self.people.effective_name(cap))
            values["person"].set_markup(
                f'<span foreground="red">{esc(placeholder)}</span> '
                + esc(_("(not linked)"))
                if placeholder
                else DASH
            )
            values["person"].set_tooltip_text(
                _("Right-click the row in the list to link a person.")
            )
        self.pv_title.set_markup(f"<big><b>{esc(title)}</b></big>")
        self.pv_summary.set_text(cap.title or "")

        if cap.url:
            values["source"].set_markup(f'<a href="{esc(cap.url)}">{esc(cap.url)}</a>')
        else:
            values["source"].set_text(DASH)
        rtype = cap.record_type or DASH
        values["type"].set_text(f"{rtype} ({cap.category})")
        if cap.folder.is_dir():
            values["local"].set_markup(f'<a href="folder">{esc(cap.capture_id)}/</a>')
            values["local"].set_tooltip_text(
                _("Click to open the capture folder.\n{path}").format(path=cap.folder)
            )
        else:
            values["local"].set_text(cap.capture_id + "/")
            values["local"].set_tooltip_text(_("The capture folder is missing."))
        values["captured"].set_text(cap.captured_at or DASH)
        values["accessed"].set_text(cap.access_date or DASH)
        values["gating"].set_text(cap.gating)
        values["copyright"].set_text(
            _("flagged") if cap.copyright_flag else _("not flagged")
        )
        values["media"].set_text(str(cap.media_count) if cap.media_count else DASH)
        values["transcribed"].set_text(stamp(cap.transcribed_at) or DASH)
        handle = self.in_tree.get(cap.capture_id)
        citation = self.db.get_citation_from_handle(handle) if handle else None
        if citation:
            link = f'<a href="edit">{esc(citation.get_gramps_id())}</a>'
            values["intree"].set_markup(_("yes, citation {id}").format(id=link))
            values["intree"].set_tooltip_text(_("Click to edit the Citation."))
        else:
            values["intree"].set_text(_("no"))
            values["intree"].set_tooltip_text(None)
        self.fill_files(cap)

        notes = []
        if cap.superseded:
            notes.append(
                _("Superseded by {id}.").format(id=cap.superseded_by)
                if cap.superseded_by
                else _("Superseded.")
            )
        if cap.verify_ok is False:
            notes.append(
                _("Incomplete: {why}").format(
                    why="; ".join(cap.verify_shortfall)
                    or _("the capture does not hold the record")
                )
            )
        notes.extend(cap.problems)
        self.pv_problems.set_markup(
            f'<span foreground="#e5484d">{esc(chr(10).join(notes))}</span>'
            if notes
            else ""
        )

        self.pv_reference.set_text(cap.reference_note or DASH)
        self.pv_short.set_text(cap.short_note or DASH)
        self.pv_list_entry.set_text(cap.source_list_entry or DASH)

        people = "\n".join(
            f"{label} ({role})" if role else label for label, role in cap.personas
        )
        self.pv_people_heading.set_visible(bool(people))
        self.pv_people.set_visible(bool(people))
        self.pv_people.set_text(people)

        self.pv_notes_heading.set_visible(bool(cap.notes))
        self.pv_notes.set_visible(bool(cap.notes))
        self.pv_notes.set_text("\n\n".join(cap.notes))

    # --------------------------------------------------------
    # people
    # --------------------------------------------------------
    def linked_person(self, cid):
        """The primary Person linked to this capture in this tree, or None."""
        return get_person(self.db, self.people.link(cid, self.tree_id))

    def person_text(self, cap):
        """Plain text of the Person cell, for sorting and searching."""
        person = self.linked_person(cap.capture_id)
        if person is not None:
            return name_displayer.display(person)
        return placeholder_name(self.people.effective_name(cap)) or DASH

    def link_color(self):
        if self.link_rgba is None:
            rgba = self.view.get_style_context().get_color(Gtk.StateFlags.LINK)
            self.link_rgba = "#%02x%02x%02x" % (
                int(rgba.red * 255),
                int(rgba.green * 255),
                int(rgba.blue * 255),
            )
        return self.link_rgba

    def link_person(self, cap, person):
        """Make person (None to clear) the capture's primary Person. When
        the capture is in the tree, the Person also cites its Citation."""
        if cap is None:
            return False
        cid = cap.capture_id
        old = self.people.link(cid, self.tree_id)
        new = person.get_handle() if person is not None else None
        if old == new:
            return False
        citation = self.in_tree.get(cid)
        if citation and old:
            uncite_person(self.db, old, citation)
        self.people.set_link(cid, self.tree_id, new)
        if citation and new:
            cite_person(self.db, new, citation)
        GLib.idle_add(self.cb_after_person_change, cid)
        return False  # also used as a one-shot idle callback

    def update_person_row(self, cid):
        for row in self.store:
            if row[COL_ID] == cid:
                row[COL_PERSON] = self.person_text(self.captures[cid])
                break
        if self.current is not None and self.current.capture_id == cid:
            self.show_preview(self.current)

    def cb_after_person_change(self, cid):
        """Deferred row update. Changing the model from inside a cell's own
        "edited" signal, or another window's signal, risks the GtkTreeView
        crash Photo Tagging ran into (see its cb_name_cell_edited())."""
        if cid in self.captures:
            self.update_person_row(cid)
            # the "linked" count in the folder statistics tooltip
            self.update_folder_stats(self.folder_button.get_filename() or "")
        return False

    def cb_db_people_changed(self, handles):
        GLib.idle_add(self.cb_redraw_people)

    def cb_redraw_people(self):
        if self.editing_person_path is None:  # never under the typing cursor
            for row in self.store:
                cap = self.captures.get(row[COL_ID])
                if cap is not None:
                    row[COL_PERSON] = self.person_text(cap)
        if self.current is not None:
            self.show_preview(self.current)
        return False

    def edit_person(self, cap):
        person = self.linked_person(cap.capture_id) if cap else None
        if person is None:
            return
        try:
            EditPerson(
                self.dbstate,
                self.uistate,
                self.track,
                person,
                lambda *a, cid=cap.capture_id: GLib.idle_add(
                    self.cb_after_person_change, cid
                ),
            )
        except WindowActiveError:
            pass

    # --------------------------------------------------------
    # context menu (the person items follow Photo Tagging's)
    # --------------------------------------------------------
    def build_context_menu(self):
        self.menu = Gtk.Menu()
        self.menu.set_reserve_toggle_size(False)
        # attached, so on Wayland the menu has a real parent window to pop
        # up from rather than whichever window last had the pointer
        self.menu.attach_to_widget(self.view, None)
        self.menu_items = {}
        for key, label, handler in (
            ("details", _("See the person details"), self.cb_menu_details),
            ("ancestors", _("See ancestor family details"), self.cb_menu_ancestors),
            (
                "descendants",
                _("See descendant family details"),
                self.cb_menu_descendants,
            ),
            ("active", _("Make the person active"), self.cb_menu_active),
            ("link", LINK_PERSON_TEXT, self.cb_menu_link),
            ("add", ADD_NEW_PERSON_TEXT, self.cb_menu_add),
            ("clear", CLEAR_REFERENCE_TEXT, self.cb_menu_clear),
            (None, None, None),
            ("fuzzy", _("Fuzzy Match Lookup\u2026"), self.cb_menu_fuzzy),
            (None, None, None),
            ("citation", _("Edit the Citation"), self.cb_menu_citation),
            ("clipboard", _("Clipboard the Citation"), self.cb_menu_clipboard),
            ("folder", _("Open the capture folder"), self.on_open_folder),
            ("copy", _("Copy the reference note"), self.on_copy_reference),
        ):
            if key is None:
                self.menu.append(Gtk.SeparatorMenuItem())
                continue
            item = Gtk.MenuItem.new_with_label(label)
            item.connect("activate", handler)
            self.menu.append(item)
            self.menu_items[key] = item
        self.menu.show_all()

    def prepare_context_menu(self):
        cap = self.current
        person = self.linked_person(cap.capture_id) if cap else None
        has = person is not None
        items = self.menu_items
        items["details"].set_sensitive(has)
        items["ancestors"].set_sensitive(
            has and bool(person.get_parent_family_handle_list())
        )
        items["descendants"].set_sensitive(
            has and bool(person.get_family_handle_list())
        )
        items["active"].set_sensitive(has)
        items["link"].set_sensitive(cap is not None)
        items["add"].set_sensitive(cap is not None)
        items["clear"].set_sensitive(has)
        fuzzy = cap is not None and get_fuzzy_match_lookup() is not None
        items["fuzzy"].set_sensitive(fuzzy)
        items["fuzzy"].set_tooltip_text(
            None if fuzzy else _("Needs the Fuzzy Matching addon.")
        )
        items["clipboard"].set_sensitive(
            cap is not None and cap.capture_id in self.in_tree
        )
        items["citation"].set_sensitive(
            cap is not None and cap.capture_id in self.in_tree
        )
        items["folder"].set_sensitive(cap is not None and cap.folder.is_dir())
        items["copy"].set_sensitive(cap is not None and bool(cap.reference_note))

    def cb_list_button_press(self, view, event):
        if event.type != Gdk.EventType.BUTTON_PRESS or event.button != 3:
            return False
        hit = view.get_path_at_pos(int(event.x), int(event.y))
        if hit is None:
            return False
        view.get_selection().select_path(hit[0])  # updates self.current
        self.prepare_context_menu()
        self.menu.popup_at_pointer(event)
        return True

    def cb_menu_details(self, *args):
        self.edit_person(self.current)

    def edit_families(self, handles):
        for handle in handles:
            family = self.db.get_family_from_handle(handle)
            if family is None:
                continue
            try:
                EditFamily(self.dbstate, self.uistate, self.track, family)
            except WindowActiveError:
                pass

    def cb_menu_ancestors(self, *args):
        person = self.linked_person(self.current.capture_id)
        if person is not None:
            self.edit_families(person.get_parent_family_handle_list())

    def cb_menu_descendants(self, *args):
        person = self.linked_person(self.current.capture_id)
        if person is not None:
            self.edit_families(person.get_family_handle_list())

    def cb_menu_active(self, *args):
        person = self.linked_person(self.current.capture_id)
        if person is not None:
            self.uistate.set_active(person.get_handle(), "Person")

    def cb_menu_link(self, *args):
        cap = self.current
        select_person = SelectorFactory("Person")
        selector = select_person(
            self.dbstate,
            self.uistate,
            self.track,
            _("Select the primary person"),
            show_search_bar=True,
        )
        person = selector.run()
        if person is not None:
            self.link_person(cap, person)

    def cb_menu_add(self, *args):
        """New Person prefilled from the Person cell, linked once saved."""
        cap = self.current
        person = Person()
        given, surname = split_placeholder_name(self.people.effective_name(cap))
        if given or surname:
            name = Name()
            name.set_first_name(given)
            if surname:
                surname_obj = Surname()
                surname_obj.set_surname(surname)
                name.set_surname_list([surname_obj])
            person.set_primary_name(name)
        try:
            EditPerson(
                self.dbstate,
                self.uistate,
                self.track,
                person,
                lambda saved, cap=cap: self.link_person(cap, saved),
            )
        except WindowActiveError:
            pass

    def cb_menu_clear(self, *args):
        self.link_person(self.current, None)

    def cb_menu_fuzzy(self, *args):
        cap = self.current
        show_fuzzy_lookup = get_fuzzy_match_lookup()
        if cap is None or show_fuzzy_lookup is None:
            return
        given, surname = split_placeholder_name(self.people.effective_name(cap))
        show_fuzzy_lookup(
            self.dbstate,
            self.uistate,
            self.track,
            surname=surname,
            given_name=given,
            # cap bound now: the lookup window may be reused for another row
            on_select=lambda person, cap=cap: GLib.idle_add(
                self.link_person, cap, person
            ),
        )

    def cb_menu_clipboard(self, *args):
        """Put the capture's Citation on the Gramps Clipboard, ready to drag
        onto a Person, Event or other object. Same simulated drop as
        PageView.copy_to_clipboard() (Ctrl+C in the Gramps views)."""
        from gramps.gui.clipboard import ClipboardWindow, obj2target

        handle = self.in_tree.get(self.current.capture_id) if self.current else None
        drag_type = obj2target("Citation")
        if not handle or not drag_type:
            return
        clipboard = None
        for widget in self.uistate.gwm.window_tree:
            if isinstance(widget, ClipboardWindow):
                clipboard = widget
        if clipboard is None:
            clipboard = ClipboardWindow(self.dbstate, self.uistate)

        class Selection:
            def __init__(self, data):
                self.data = data

            def get_data(self):
                return self.data

        class Context:
            targets = [Gdk.atom_intern(drag_type.name(), False)]
            action = 1

            def list_targets(self):
                return Context.targets

            def get_actions(self):
                return Context.action

        data = (drag_type.name(), id(self), handle, 0)
        clipboard.object_list.object_drag_data_received(
            clipboard.object_list._widget,  # pylint: disable=protected-access
            Context(),
            0,
            0,
            Selection(pickle.dumps(data)),
            None,
            -1,
        )

    def cb_menu_citation(self, *args):
        if self.current is not None:
            self.edit_citation(self.current.capture_id)

    def fill_files(self, cap):
        for child in self.pv_files.get_children():
            self.pv_files.remove(child)
        files = cap.viewable_files if cap is not None else []
        self.pv_files_heading.set_visible(bool(files))
        self.pv_files.set_visible(bool(files))
        for row, cfile in enumerate(files):
            name = Gtk.Label(label=_(cfile.label), xalign=0)
            name.set_tooltip_text(cfile.rel_path)
            name.set_hexpand(True)
            self.pv_files.attach(name, 0, row, 1, 1)
            for col, (label, choose) in enumerate(
                ((_("Open"), False), (_("Open with\u2026"), True)), start=1
            ):
                button = Gtk.Button(label=label)
                button.connect(
                    "clicked", self.cb_open_file, str(cfile.abs_path), choose
                )
                self.pv_files.attach(button, col, row, 1, 1)
        self.pv_files.show_all()

    # --------------------------------------------------------
    # opening archived files
    # --------------------------------------------------------
    def remembered_viewer(self, ctype):
        app_id = CONFIG.get("viewers.by-type").get(ctype)
        desktop = getattr(Gio, "DesktopAppInfo", None)  # Linux/BSD only
        if not app_id or desktop is None:
            return None
        try:
            return desktop.new(app_id)
        except (TypeError, GLib.Error):
            return None

    def choose_viewer(self, gfile, ctype):
        """Ask which program should show this kind of file; remember it."""
        dialog = Gtk.AppChooserDialog.new(self.window, Gtk.DialogFlags.MODAL, gfile)
        dialog.set_heading(
            _(
                "Choose a program to show this kind of file. Capsule Sources "
                "will use it for these files from now on."
            )
        )
        # list every program, so a web browser (Chrome is installed for
        # Genealogy Capsule anyway) can open PDF, HTML and MHTML files
        dialog.get_widget().set_show_all(True)
        app = None
        if dialog.run() == Gtk.ResponseType.OK:
            app = dialog.get_app_info()
        dialog.destroy()
        if app is not None and app.get_id():
            viewers = dict(CONFIG.get("viewers.by-type"))
            viewers[ctype] = app.get_id()
            CONFIG.set("viewers.by-type", viewers)
            CONFIG.save()
        return app

    def open_file(self, path, choose=False):
        """Open with the remembered viewer, else the desktop default, else
        ask. choose=True (the Open with... button) always asks."""
        gfile = Gio.File.new_for_path(path)
        ctype = Gio.content_type_guess(path, None)[0]
        app = None
        if not choose:
            app = self.remembered_viewer(ctype) or Gio.AppInfo.get_default_for_type(
                ctype, False
            )
        if app is None:
            app = self.choose_viewer(gfile, ctype)
        if app is None:
            return
        try:
            app.launch([gfile], None)
        except GLib.Error as err:
            ErrorDialog(
                _("Could not open the file"),
                f"{path}\n\n{err.message}",
                parent=self.window,
            )

    # --------------------------------------------------------
    # Citation editor
    # --------------------------------------------------------
    def edit_citation(self, capture_id):
        handle = self.in_tree.get(capture_id)
        citation = self.db.get_citation_from_handle(handle) if handle else None
        if citation is None:
            return
        try:
            EditCitation(
                self.dbstate,
                self.uistate,
                self.track,
                citation,
                callback=lambda *a: self.reload(),
            )
        except WindowActiveError:
            pass

    # --------------------------------------------------------
    # callbacks
    # --------------------------------------------------------
    def cb_refresh(self, *args):
        self.reload()

    def cb_first_allocate(self, view, allocation):
        """First run only: give Person and Site equal shares of the room the
        expanding Person column and the Site column took together."""
        person = self.columns["person"].get_width()
        site = self.columns["site"].get_width()
        if person <= 1 or site <= 1:
            return
        view.disconnect(self.first_allocate)
        self.first_allocate = None
        GLib.idle_add(self.fix_column_widths, (person + site) // 2)

    def fix_column_widths(self, half):
        for key, col in self.columns.items():
            width = half if key in ("person", "site") else col.get_width()
            col.set_expand(False)
            col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            col.set_fixed_width(max(width, 20))
        return False  # run once

    def cb_row_activated(self, view, path, column):
        cap = self.captures.get(self.store[path][COL_ID])
        if column is self.columns.get("person"):
            # a linked Person opens; an unlinked cell is being typed in
            self.edit_person(cap)
            return
        self.edit_citation(cap.capture_id if cap else None)

    def cb_local_link(self, label, uri):
        self.on_open_folder()
        return True  # handled; "folder" is not a web address

    def cb_person_link(self, label, uri):
        self.edit_person(self.current)
        return True

    def cb_intree_link(self, label, uri):
        if self.current is not None:
            self.edit_citation(self.current.capture_id)
        return True  # handled; "edit" is not a web address

    def cb_person_cell_data(self, column, cell, model, itr, data=None):
        cap = self.captures.get(model[itr][COL_ID])
        person = self.linked_person(cap.capture_id) if cap else None
        if person is not None:
            cell.set_property("editable", False)
            cell.set_property(
                "markup",
                f'<span foreground="{self.link_color()}" underline="single">'
                f"{esc(name_displayer.display(person))}</span>",
            )
            return
        cell.set_property("editable", cap is not None)
        path = model.get_path(itr)
        if self.editing_person_path is not None and (
            path.compare(self.editing_person_path) == 0
        ):
            return  # leave the cell being typed in alone
        text = placeholder_name(self.people.effective_name(cap)) if cap else ""
        if text:
            # red, as in Photo Tagging: a name not yet confirmed as a Person
            cell.set_property("markup", f'<span foreground="red">{esc(text)}</span>')
        else:
            cell.set_property("markup", esc(DASH))

    def cb_person_editing_started(self, cell, editable, path):
        self.editing_person_path = Gtk.TreePath.new_from_string(path)
        cap = self.captures.get(self.store[path][COL_ID])
        # edit the name as typed or read, not as the display format shows it
        editable.set_text(self.people.effective_name(cap) if cap else "")

    def cb_person_editing_canceled(self, cell):
        self.editing_person_path = None

    def cb_person_edited(self, cell, path, text):
        """Store the typed name in CapsuleSources_captures.json. An empty
        name sticks: it means "not this", as in Photo Tagging."""
        self.editing_person_path = None
        cid = self.store[path][COL_ID]
        cap = self.captures.get(cid)
        if cap is None or self.linked_person(cid) is not None:
            return
        self.people.set_name(cap, text)
        GLib.idle_add(self.cb_after_person_change, cid)

    def cb_open_file(self, button, path, choose):
        self.open_file(path, choose)

    # --------------------------------------------------------
    # callbacks (lists, filters, import)
    # --------------------------------------------------------

    def on_selection_changed(self, selection):
        model, itr = selection.get_selected()
        cap = self.captures.get(model[itr][COL_ID]) if itr else None
        if cap is not None or itr is None:
            self.show_preview(cap)

    def on_folder_set(self, button):
        root = button.get_filename() or ""
        CONFIG.set("paths.captures-root", root)
        self.current = None
        self.reload(root)

    def on_show_superseded(self, button):
        CONFIG.set("options.show-superseded", button.get_active())
        self.update_facets()
        self.fill_list()

    def on_toggle(self, cell, path):
        row = self.store[path]
        if not row[COL_ACTIVE]:
            return
        row[COL_PICK] = not row[COL_PICK]
        if row[COL_PICK]:
            self.picked.add(row[COL_ID])
        else:
            self.picked.discard(row[COL_ID])
        self.update_import_button()

    def on_select_new(self, *args):
        for row in self.store:
            if row[COL_ACTIVE]:
                row[COL_PICK] = True
                self.picked.add(row[COL_ID])
        self.update_import_button()

    def on_select_none(self, *args):
        for row in self.store:
            row[COL_PICK] = False
        self.picked.clear()
        self.update_import_button()

    def on_open_folder(self, *args):
        if self.current is not None:
            open_file_with_default_application(str(self.current.folder), self.uistate)

    def cb_copy_field(self, widget, event, field):
        """Copy one citation field (reference note, short note or source
        list entry) of the shown capture to the desktop clipboard."""
        if event.button != 1 or self.current is None:
            return False
        text = getattr(self.current, field, None)
        if text:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
            # brief check mark: the copy happened
            widget.icon.set_from_icon_name("object-select-symbolic", Gtk.IconSize.MENU)
            GLib.timeout_add(900, self.cb_copy_icon_back, widget.icon)
        return True

    def cb_copy_icon_back(self, icon):
        icon.set_from_icon_name("edit-copy-symbolic", Gtk.IconSize.MENU)
        return False

    def cb_copy_hover(self, widget, event, inside):
        """Rollover: the :hover CSS state of the caption row."""
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        if inside:
            widget.set_state_flags(Gtk.StateFlags.PRELIGHT, False)
        else:
            widget.unset_state_flags(Gtk.StateFlags.PRELIGHT)
        return False

    def cb_hand_cursor(self, widget):
        window = widget.get_window()
        if window is not None:
            window.set_cursor(Gdk.Cursor.new_from_name(widget.get_display(), "pointer"))

    def on_copy_reference(self, *args):
        if self.current is not None and self.current.reference_note:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(self.current.reference_note, -1)

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    def on_import(self, *args):
        picked = [
            self.captures[cid] for cid in sorted(self.picked) if cid in self.captures
        ]
        if not picked:
            return
        root = self.folder_button.get_filename() or ""
        result = import_captures(
            self.db, picked, root=root, links=self.people.links(self.tree_id)
        )
        text = result.summary()
        if result.skipped:
            text += "\n" + _("{n} were already in the tree.").format(
                n=len(result.skipped)
            )
        if result.problems:
            lines = [f"{cid}: {msg}" for cid, msg in result.problems[:20]]
            if len(result.problems) > 20:
                lines.append("\u2026")
            WarningDialog(
                _("Imported with problems"),
                text + "\n\n" + "\n".join(lines),
                parent=self.window,
            )
        else:
            OkDialog(_("Import finished"), text, parent=self.window)
        self.picked.clear()
        self.reload()

    # --------------------------------------------------------
    # ManagedWindow
    # --------------------------------------------------------
    def build_menu_names(self, obj):
        # A submenu label (not None) lets this window own child windows:
        # Edit Citation, Edit Person, Select Person, Fuzzy Match Lookup.
        # With None, Gramps' window manager treats it as a leaf and refuses
        # them ("Gwm: add_item: Incorrect track - Is parent not a leaf?").
        return (self.title, self.title)

    def close(self, *args):
        width, height = self.window.get_size()
        CONFIG.set("window.width", width)
        CONFIG.set("window.height", height)
        CONFIG.set("window.pane-position", self.paned.get_position())
        for key, col in self.columns.items():
            width = col.get_width()
            if width > 1:  # 0 when the list was never shown
                CONFIG.set(f"columns.{key}", width)
        CONFIG.save()
        for key in self.db_keys:
            self.db.disconnect(key)
        self.db_keys = []
        ManagedWindow.close(self, *args)


# ------------------------------------------------------------
# CapsuleSourcesOptions
# ------------------------------------------------------------
class CapsuleSourcesOptions(tool.ToolOptions):
    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
