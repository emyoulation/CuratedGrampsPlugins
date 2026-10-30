# Based on Genealogy Capsule, Copyright (c) 2026 the Genealogy Capsule authors
# (mjlawless), MIT License:
# https://github.com/mjlawless/capsule-genealogy/blob/main/LICENSE
#
# Capsule Sources - Gramps tool window
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

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import PluginRegister
from gramps.gui.display import display_help, display_url
from gramps.gui.dialog import OkDialog, WarningDialog
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.plug import tool
from gramps.gui.utils import open_file_with_default_application

from capsule_import import import_captures, imported_capture_ids
from capsule_reader import default_captures_root, read_all

try:
    _ = glocale.get_addon_translator(__file__).gettext
except ValueError:
    _ = glocale.translation.gettext

LOG = logging.getLogger(".CapsuleSources")

PLUGIN_ID = "capsulesources"  # id= in CapsuleSources.gpr.py

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
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(_HELP_ICON_SVG, size, size, True)
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
CONFIG = configman.register_manager(
    "CapsuleSources", __file__, use_plugins_path=False
)
CONFIG.register("meta.plugin_id", PLUGIN_ID)
CONFIG.register("meta.schema_version", "1")
CONFIG.register("paths.captures-root", "")
CONFIG.register("options.show-superseded", False)
CONFIG.register("window.width", 1150)
CONFIG.register("window.height", 620)
CONFIG.register("window.pane-position", 760)
CONFIG.load()

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
CHIP = {
    "extracted": ("#f3e3c3", "#7a5418"),
    "reviewed": ("#dbe7f5", "#1f4f86"),
    "captured": ("#e8e8e8", "#555555"),
    "superseded": ("#e8e8e8", "#555555"),
    "not read yet": ("#fff2cc", "#7a6000"),
    "incomplete": ("#f8d4d4", "#b02a2a"),
    "in tree": ("#d8ecd8", "#2d6a2d"),
    "file": ("#ececec", "#444444"),
}
DASH = "\u2014"


def esc(text):
    return GLib.markup_escape_text(str(text or ""))


def chip(text, kind=None):
    bg, fg = CHIP.get(kind or text, CHIP["file"])
    return (
        f'<span background="{bg}" foreground="{fg}" size="small">'
        f"\u2009{esc(text)}\u2009</span>"
    )


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
            False, False, 0,
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

        self.captures = {}  # capture_id -> Capture
        self.in_tree = {}  # capture_id -> citation handle
        self.picked = set()  # capture ids ticked for import
        self.current = None  # Capture shown in the preview

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
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_border_width(8)

        # folder row
        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label=_("Capsule captures folder:")), False, False, 0)
        self.folder_button = Gtk.FileChooserButton(
            title=_("Select the Capsule captures folder"),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        self.folder_button.connect("file-set", self.on_folder_set)
        row.pack_start(self.folder_button, True, True, 0)
        vbox.pack_start(row, False, False, 0)

        # filter row, modeled on the Captures Index controls
        row = Gtk.Box(spacing=6)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text(_("Filter captures\u2026"))
        self.search.set_tooltip_text(
            _("Matches record type, person, site, status, citation, capture id, "
              "address, referenced documents and your notes.")
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
        close = Gtk.Button(label=_("Close"))
        close.connect("clicked", lambda *a: self.close())
        self.import_button = Gtk.Button(label=_("Import selected"))
        self.import_button.get_style_context().add_class("suggested-action")
        self.import_button.connect("clicked", self.on_import)
        bbox.pack_end(self.import_button, False, False, 0)
        bbox.pack_end(close, False, False, 0)
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

        for title, index, markup, expand, sort in (
            (_("Status"), COL_STATUS, True, False, COL_STATUS),
            (_("Record"), COL_RECORD, False, False, COL_RECORD),
            (_("Person"), COL_PERSON, False, True, COL_PERSON),
            (_("Site"), COL_SITE, False, False, COL_SITE),
            (_("Captured"), COL_CAPTURED, False, False, COL_SORT_TIME),
            (_("Files"), COL_FILES, True, False, None),
        ):
            cell = Gtk.CellRendererText()
            if index in (COL_PERSON, COL_SITE):
                cell.set_property("ellipsize", Pango.EllipsizeMode.END)
            if index == COL_SITE:
                cell.set_property("family", "monospace")
            if index == COL_RECORD:
                cell.set_property("weight", Pango.Weight.BOLD)
            if markup:
                col = Gtk.TreeViewColumn(title, cell, markup=index)
            else:
                col = Gtk.TreeViewColumn(title, cell, text=index)
            col.set_resizable(True)
            col.set_expand(expand)
            if sort is not None:
                col.set_sort_column_id(sort)
            self.view.append_column(col)
        self.store.set_sort_column_id(COL_SORT_TIME, Gtk.SortType.DESCENDING)
        self.view.get_selection().connect("changed", self.on_selection_changed)

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

        def caption(text):
            label = Gtk.Label(xalign=0)
            label.set_markup(f'<span size="small" alpha="70%">{esc(text.upper())}</span>')
            label.set_margin_top(4)
            return label

        self.pv_title = text_label()
        box.pack_start(self.pv_title, False, False, 0)
        self.pv_summary = text_label()
        box.pack_start(self.pv_summary, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=3)
        grid.set_margin_top(6)
        self.pv_values = {}
        keys = (
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
            if key == "local":
                cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                cell.pack_start(value, False, False, 0)
                self.open_folder_button = Gtk.Button(label=_("Open folder"))
                self.open_folder_button.set_halign(Gtk.Align.START)
                self.open_folder_button.connect("clicked", self.on_open_folder)
                cell.pack_start(self.open_folder_button, False, False, 0)
                grid.attach(cell, 1, row, 1, 1)
            else:
                grid.attach(value, 1, row, 1, 1)
            self.pv_values[key] = value
        box.pack_start(grid, False, False, 0)

        self.pv_problems = text_label()
        box.pack_start(self.pv_problems, False, False, 0)

        box.pack_start(heading(_("Citation")), False, False, 0)
        box.pack_start(caption(_("Reference note")), False, False, 0)
        self.pv_reference = text_label()
        box.pack_start(self.pv_reference, False, False, 0)
        copy = Gtk.Button(label=_("Copy"))
        copy.set_halign(Gtk.Align.START)
        copy.connect("clicked", self.on_copy_reference)
        box.pack_start(copy, False, False, 0)
        box.pack_start(caption(_("Short note")), False, False, 0)
        self.pv_short = text_label()
        box.pack_start(self.pv_short, False, False, 0)
        box.pack_start(caption(_("Source list entry")), False, False, 0)
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
        chips = [chip(cap.status)]
        if cap.superseded:
            chips.append(chip(_("superseded"), "superseded"))
        if cap.awaiting_reading:
            chips.append(chip(_("not read yet"), "not read yet"))
        if cap.verify_ok is False:
            chips.append(chip(_("incomplete"), "incomplete"))
        if cap.capture_id in self.in_tree:
            chips.append(chip(_("in tree"), "in tree"))
        return " ".join(chips)

    def files_markup(self, cap):
        parts = []
        if cap.gating == "gated":
            parts.append("\U0001F512")
        if cap.external_ref_count:
            parts.append(chip("\u2197 " + _("source")))
        parts.extend(chip(ftype) for ftype in cap.file_types)
        return " ".join(parts)

    def matches(self, cap, text):
        """Text box and every facet must agree, as in the Captures Index."""
        return (
            (not text or text in cap.search_blob)
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
            itr = self.store.append(
                [
                    active and cap.capture_id in self.picked,
                    self.status_markup(cap),
                    cap.category,
                    cap.primary_persona or DASH,
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
            self.pv_title.set_markup(f"<big><b>{esc(_('No capture selected'))}</b></big>")
            for label in (
                self.pv_summary, self.pv_problems, self.pv_reference,
                self.pv_short, self.pv_list_entry, self.pv_people, self.pv_notes,
                *values.values(),
            ):
                label.set_text("")
            self.open_folder_button.set_sensitive(False)
            return

        title = cap.primary_persona or cap.display_title
        self.pv_title.set_markup(f"<big><b>{esc(title)}</b></big>")
        self.pv_summary.set_text(cap.title or "")

        if cap.url:
            values["source"].set_markup(f'<a href="{esc(cap.url)}">{esc(cap.url)}</a>')
        else:
            values["source"].set_text(DASH)
        rtype = cap.record_type or DASH
        values["type"].set_text(f"{rtype} ({cap.category})")
        values["local"].set_text(cap.capture_id + "/")
        self.open_folder_button.set_sensitive(cap.folder.is_dir())
        values["captured"].set_text(cap.captured_at or DASH)
        values["accessed"].set_text(cap.access_date or DASH)
        values["gating"].set_text(cap.gating)
        values["copyright"].set_text(_("flagged") if cap.copyright_flag else _("not flagged"))
        values["media"].set_text(str(cap.media_count) if cap.media_count else DASH)
        values["transcribed"].set_text(stamp(cap.transcribed_at) or DASH)
        handle = self.in_tree.get(cap.capture_id)
        citation = self.db.get_citation_from_handle(handle) if handle else None
        values["intree"].set_text(
            _("yes, citation {id}").format(id=citation.get_gramps_id())
            if citation
            else _("no")
        )

        notes = []
        if cap.superseded:
            notes.append(
                _("Superseded by {id}.").format(id=cap.superseded_by)
                if cap.superseded_by
                else _("Superseded.")
            )
        if cap.verify_ok is False:
            notes.append(_("Incomplete: {why}").format(
                why="; ".join(cap.verify_shortfall) or _("the capture does not hold the record")
            ))
        notes.extend(cap.problems)
        self.pv_problems.set_markup(
            f'<span foreground="#b02a2a">{esc(chr(10).join(notes))}</span>' if notes else ""
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
    # callbacks
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
        picked = [self.captures[cid] for cid in sorted(self.picked) if cid in self.captures]
        if not picked:
            return
        result = import_captures(self.db, picked)
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
        return (self.title, None)

    def close(self, *args):
        width, height = self.window.get_size()
        CONFIG.set("window.width", width)
        CONFIG.set("window.height", height)
        CONFIG.set("window.pane-position", self.paned.get_position())
        CONFIG.save()
        ManagedWindow.close(self, *args)


# ------------------------------------------------------------
# CapsuleSourcesOptions
# ------------------------------------------------------------
class CapsuleSourcesOptions(tool.ToolOptions):
    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
