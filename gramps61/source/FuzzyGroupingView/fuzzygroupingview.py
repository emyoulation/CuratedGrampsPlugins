# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2008       Gary Burton
# Copyright (C) 2009       Nick Hall
# Copyright (C) 2010       Benny Malengier
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Fuzzy Grouping person view

Forked from Gramps core gramps/plugins/view/persontreeview.py
(maintenance/gramps61, commit 5cebb2c55fdbb0a92428625d409918216409db70).
The grouping itself is done by PersonTreeModel.add_row() in
gramps/gui/views/treemodels/peoplemodel.py, so this addon subclasses that
model and groups by a phonetic code of the core group name (which still
honours "Group as" overrides and the surname group mapping table).

Soundex (gramps.gen.soundex) is the default and the fallback. Other
systems are discovered from installed RULE plugins whose id starts with
"FuzzyMatchingEncoder:" (the encoder contract of the Phonetic Filter Rules
addon: ALGORITHM_ID, ALGORITHM_LABEL, encode(name) -> set of codes).

Configure dialog additions:
  Columns tab    - a "Grouping:" choice (Fuzzy grouping ID / Sample Surname)
                   replaces the "first column cannot be changed" label.
  Subsorting tab - a sort-only Name format (never touches the application
                   Name format preference) and a numbered subsort order.
"""

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------
import logging
import os
import re
import weakref
from collections import Counter
from time import perf_counter
from urllib.parse import quote
from xml.sax.saxutils import escape

# -------------------------------------------------------------------------
#
# GTK modules
#
# -------------------------------------------------------------------------
from gi.repository import Gio, GLib, Gtk, Pango

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gui.views.listview import TEXT, MARKUP, ICON
from gramps.plugins.lib.libpersonview import BasePersonView
from gramps.gui.views.treemodels.peoplemodel import PersonTreeModel
from gramps.gen.lib import Name, Person, Surname, NameOriginType
from gramps.gen.errors import WindowActiveError
from gramps.gui.editors import EditPerson
from gramps.gen.utils.db import preset_name
from gramps.gen.config import config as global_config
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.plug import PluginRegister
from gramps.gen.plug._pluginreg import RULE
from gramps.gen.soundex import soundex as core_soundex
from gramps.gen.utils.keyword import get_keywords, get_translation_from_keyword
from gramps.gui.configure import GrampsPreferences, DisplayNameEditor
from gramps.gui.configure import COL_NUM
from gramps.gui.dialog import OkDialog
from gramps.gui.utils import ProgressMeter
from gramps.gui.pluginmanager import GuiPluginManager

try:  # Gramps 5.2: person data is a tuple
    from gramps.gui.views.treemodels.peoplemodel import COLUMN_NAME
except ImportError:  # Gramps 6.x: person data is a DataDict
    COLUMN_NAME = 3

# -------------------------------------------------------------------------
#
# Internationalization
#
# -------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)

# -------------------------------------------------------------------------
#
# Constants
#
# -------------------------------------------------------------------------
PLUGIN_ID = "fuzzygroupingview"  # matches id= in the .gpr.py
SCHEMA_VERSION = "1"
DEFAULT_SYSTEM = "soundex"
ENCODER_ID_PREFIX = "FuzzyMatchingEncoder:"  # Phonetic Filter Rules contract
MAX_HEADER_NAMES = 4  # spellings listed in a group header before "+N"
GROUP_BY_ID = "id"
GROUP_BY_SURNAME = "surname"
NAME_FORMAT_ROW = -1  # subsort list entry for the "Name format" line
SUBSORT_SEPARATOR = "\t"  # lowest non-ignorable collation weight
REFRESH_DELAY = 5  # seconds between a Configure change and the view refresh
PROGRESS_DELAY = 1.0  # seconds of index building before a progress dialog
PROGRESS_CHECK_EVERY = 256  # rows between elapsed-time checks

# Initial subsort: Name format, Birth Date, Death Date, Spouse, Last Changed,
# then the remaining columns in their Display list order.
INITIAL_SUBSORT_HEAD = [
    NAME_FORMAT_ROW,
    BasePersonView.COL_BDAT,
    BasePersonView.COL_DDAT,
    BasePersonView.COL_SPOUSE,
    BasePersonView.COL_CHAN,
]

# -------------------------------------------------------------------------
#
# View icon
#
# The .gpr.py cannot point icondir at our media folder: it is exec()'d
# without __file__, and a relative icondir is not resolved against the
# plugin folder. Gramps imports every view module at startup (before the
# toolbar and view buttons are built), so appending the folder to the icon
# theme search path here is early enough. A loose SVG in a search path
# folder is found by its file name stem.
#
# -------------------------------------------------------------------------
VIEW_ICON = "fuzzy-grouping"
FALLBACK_ICON = "gramps-tree-group"
_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
if os.path.isfile(os.path.join(_MEDIA_DIR, VIEW_ICON + ".svg")):
    Gtk.IconTheme.get_default().append_search_path(_MEDIA_DIR)
    ICON_NAME = VIEW_ICON
else:
    LOG.warning("Fuzzy Grouping: %s.svg not found in %s", VIEW_ICON, _MEDIA_DIR)
    ICON_NAME = FALLBACK_ICON

# -------------------------------------------------------------------------
#
# Settings (.ini in this addon's own folder)
#
# The .ini is not written until the user first opens the view, so its
# absence tells us to show the Configure dialog on first use.
#
# -------------------------------------------------------------------------
CONFIG = global_config.register_manager("FuzzyGrouping", use_plugins_path=False)
CONFIG.register("meta.plugin_id", "")
CONFIG.register("meta.schema_version", "")
CONFIG.register("grouping.system", DEFAULT_SYSTEM)
CONFIG.register("grouping.sort", GROUP_BY_ID)
CONFIG.register("subsort.name_format", 0)  # 0 = application default format
CONFIG.register("subsort.order", [])  # [] = INITIAL_SUBSORT_HEAD + rest
_INI_EXISTED = bool(CONFIG.filename) and os.path.isfile(CONFIG.filename)
CONFIG.init()


def save_config():
    """Write the .ini, with its [meta] identification block."""
    CONFIG.set("meta.plugin_id", PLUGIN_ID)
    CONFIG.set("meta.schema_version", SCHEMA_VERSION)
    CONFIG.save()


if _INI_EXISTED:
    save_config()
_FIRST_RUN = [not _INI_EXISTED]  # list so the view can clear it


# -------------------------------------------------------------------------
#
# Phonetic encoders
#
# -------------------------------------------------------------------------
def _soundex_codes(name):
    """Built-in Gramps Soundex, as a one-element set."""
    try:
        return {core_soundex(name)}
    except UnicodeEncodeError:
        return {core_soundex("")}


def discover_encoders():
    """
    Return {system_id: (label, encode)} with built-in Soundex first,
    then every installed encoder rule plugin, sorted by label.

    Encoder plugins the user hid/deactivated in the Plugin Manager are
    skipped: load_plugin() itself does not check that (see the
    "Deactivate" note in HelpDocButton.md), so it is checked here,
    live, on every call.
    """
    encoders = {DEFAULT_SYSTEM: (_("Soundex"), _soundex_codes)}
    found = []
    gpm = GuiPluginManager.get_instance()
    hidden = gpm.get_hidden_plugin_ids()
    for pdata in PluginRegister.get_instance().type_plugins(RULE):
        if not (pdata.id or "").startswith(ENCODER_ID_PREFIX):
            continue
        if pdata.id in hidden:
            continue
        try:
            module = gpm.load_plugin(pdata)
            system_id = module.ALGORITHM_ID
            label = module.ALGORITHM_LABEL
            encode = module.encode
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Fuzzy Grouping: skipping encoder %s", pdata.id, exc_info=True)
            continue
        if system_id == DEFAULT_SYSTEM or not callable(encode):
            continue  # the built-in Soundex always wins
        found.append((label, system_id, encode))
    for label, system_id, encode in sorted(found):
        encoders.setdefault(system_id, (label, encode))
    return encoders


# name format keywords that produce surname parts (case-insensitive;
# UPPERCASE variants only force upper case)
_SURNAME_KEYWORDS = re.compile(
    r"\b(?:surname|rawsurnames|notpatronymic|rest|prefix"
    r"|primary|patronymic)(?:\[(?:pre|sur|con)\])?",
    re.IGNORECASE,
)


def surnameless_format(fmt_str):
    """
    A name format string with every surname keyword removed, and the
    punctuation left behind tidied up. Falls back to "Given".
    """
    text = _SURNAME_KEYWORDS.sub("", fmt_str)
    text = re.sub(r"\(\s*\)|/\s*/|\[\s*\]", "", text)  # emptied brackets
    text = re.sub(r"\s*,(\s*,)+", ",", text)  # repeated commas
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ,;:/-")
    return text or "Given"


def default_sort_format():
    """The current Display name format, without its surname portion."""
    default = name_displayer.get_default_format()
    return surnameless_format(name_displayer.name_formats[default][1])


def name_format_string(num):
    """
    Format string for a name format number; 0 (the default), unknown or
    inactive formats use the Display name format without surnames.
    """
    formats = name_displayer.name_formats
    if not num or num not in formats or not formats[num][2]:
        return default_sort_format()
    return formats[num][1]


# -------------------------------------------------------------------------
#
# Help (from the HELP BUTTON BLOCK of help_doc_button.py, see
# HelpDocButton.md; here as a toolbar icon instead of a labeled button)
#
# -------------------------------------------------------------------------
_MARKDOWNDASH_ID = "markdowndash"
HELP_ICON_NAME = "help-browser"


def find_local_readme(pdata):
    """
    Return the canonical README.md path of the plugin, or None if the
    plugin has no README of any kind (README.md, README_<lang>.md or
    locale/<lang>/README.md, decided by MarkdownUtils when importable).
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # importable only once Markdown Dash has been loaded
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener():
    """
    Return Markdown Dash's open_markdown_file(), or None when Markdown
    Dash is deactivated, not registered, fails to load, or lacks it.
    """
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        return None
    return getattr(mod, "open_markdown_file", None)


def open_help_url(pdata, parent):
    """
    Open the plugin's registered help_url in the default browser; a bare
    wiki page title is resolved against gramps-project.org.
    """
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered help_url."),
            parent=parent,
        )
        return
    full_url = (
        help_url
        if help_url.startswith(("http://", "https://"))
        else "https://gramps-project.org/wiki/index.php?title="
        + quote(help_url, safe=":")
    )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("help: could not open help_url: %s", full_url)


def own_pdata():
    """This view's own PluginData."""
    return PluginRegister.get_instance().get_plugin(PLUGIN_ID)


def help_uses_readme():
    """True when a click on Help will show the README in Markdown Dash."""
    # Load Markdown Dash first: that makes MarkdownUtils importable,
    # which find_local_readme() uses to recognize translated READMEs.
    return (
        resolve_markdown_dash_opener() is not None
        and find_local_readme(own_pdata()) is not None
    )


def help_tooltip():
    """Tooltip saying which documentation a click on Help will show."""
    if help_uses_readme():
        return _("View the ReadMe markdown docs for the Fuzzy Grouping person view mode")
    return _("Browse to the Help URL for the Fuzzy Grouping person view mode")


def show_help(uistate):
    """README.md in Markdown Dash when possible, else the help_url."""
    pdata = own_pdata()
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None:
            open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            return
    open_help_url(pdata, uistate.window)


# -------------------------------------------------------------------------
#
# FuzzyGroupingTreeModel
#
# -------------------------------------------------------------------------
class FuzzyGroupingTreeModel(PersonTreeModel):
    """
    PersonTreeModel that groups by a phonetic code of the group name.

    The view sets the class attributes below before (re)building.
    """

    encode = staticmethod(_soundex_codes)
    group_sort = GROUP_BY_ID
    subsort = []  # model columns, NAME_FORMAT_ROW for the name format
    name_fmt_str = None

    def __init__(self, *args, **kwargs):
        # must exist before the base class builds the tree
        self._code_cache = {}  # group name -> group key
        self._members = {}  # group key -> Counter of group names
        self._handle_member = {}  # person handle -> (group key, group name)
        self._progress = None  # ProgressMeter, only once a build is slow
        self._progress_pct = 0
        self._build_count = 0
        self._build_total = 1
        self._build_start = 0.0
        PersonTreeModel.__init__(self, *args, **kwargs)

    def destroy(self):
        self._code_cache = self._members = self._handle_member = None
        PersonTreeModel.destroy(self)

    def rebuild_data(self, *args, **kwargs):
        self._members = {}
        self._handle_member = {}
        self._progress_begin()
        try:
            PersonTreeModel.rebuild_data(self, *args, **kwargs)
            if self.group_sort == GROUP_BY_SURNAME:
                self._resort_groups()
        finally:
            self._progress_end()

    # ---------------------------------------------------------------
    # progress dialog for a slow index build
    # ---------------------------------------------------------------
    def _progress_begin(self):
        self._progress = None
        self._progress_pct = 0
        self._build_count = 0
        self._build_start = perf_counter()
        try:
            self._build_total = max(1, self.number_items())
        except Exception:  # pylint: disable=broad-except
            self._build_total = 1  # no open database

    def _progress_tick(self):
        """
        Count one built row. After PROGRESS_DELAY seconds, open a progress
        dialog; it is advanced in whole percents (at most 100 updates),
        because every ProgressMeter step also runs pending GTK events.
        """
        self._build_count += 1
        if self._progress is None:
            if self._build_count % PROGRESS_CHECK_EVERY:
                return
            if perf_counter() - self._build_start < PROGRESS_DELAY:
                return
            self._progress = ProgressMeter(
                _("Fuzzy Grouping"),
                parent=self.uistate.window if self.uistate else None,
            )
            self._progress.set_pass(_("Building the fuzzy grouping index"), 100)
        percent = min(100, self._build_count * 100 // self._build_total)
        while self._progress_pct < percent:
            self._progress.step()
            self._progress_pct += 1

    def _progress_end(self):
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    def group_key(self, group_name):
        """Phonetic code for a group name ("" for no surname)."""
        key = self._code_cache.get(group_name)
        if key is None:
            key = ""
            if group_name.strip():
                try:
                    codes = self.encode(group_name)
                except Exception:  # pylint: disable=broad-except
                    LOG.debug("encoder failed on %r, using Soundex", group_name)
                    codes = _soundex_codes(group_name)
                if isinstance(codes, str):
                    codes = {codes}
                # multi-code systems: pick one code so the person lands
                # in exactly one group
                key = min(codes) if codes else ""
            self._code_cache[group_name] = key
        return key

    def sample_surname(self, key):
        """The most used spelling in a group (ties: alphabetical)."""
        counter = self._members.get(key) or Counter()
        if not counter:
            return ""
        return sorted(counter.items(), key=lambda i: (-i[1], i[0]))[0][0]

    def subsort_key(self, data, name_data):
        """
        One string holding every subsort value, separated by a tab.
        The tree collates it once, so the fields sort in order.
        """
        parts = []
        for col in self.subsort:
            if col == NAME_FORMAT_ROW:
                value = name_displayer.format_str_raw(name_data, self.name_fmt_str)
            else:
                value = self.smap[col](data)
            parts.append(str(value or "").replace(SUBSORT_SEPARATOR, " "))
        return SUBSORT_SEPARATOR.join(parts)

    def add_row(self, handle, data):
        """
        Add nodes to the node map for a single person.

        handle      The handle of the gramps object.
        data        The object data.
        """
        if self._in_build:
            self._progress_tick()
        try:
            name_data = data.primary_name  # Gramps 6.x
        except AttributeError:
            name_data = data[COLUMN_NAME]  # Gramps 5.2
        group_name = name_displayer.name_grouping_data(self.db, name_data)
        key = self.group_key(group_name)
        self._members.setdefault(key, Counter())[group_name] += 1
        self._handle_member[handle] = (key, group_name)

        if self.sort_col == 0 and self.subsort and self.name_fmt_str:
            sort_key = self.subsort_key(data, name_data)
        else:  # the user sorted on another column: core behavior
            sort_key = self.sort_func(data)

        if key not in self.tree:
            # group row; for Sample Surname it is re-sorted after a build
            if self.group_sort == GROUP_BY_SURNAME:
                group_sort_text = group_name or key
            else:
                group_sort_text = key
            self.add_node(None, key, group_sort_text, None, add_parent=False)
        self.add_node(key, handle, sort_key, handle)

    def _resort_groups(self):
        """After a full build, order group rows by their sample surname."""
        root = self.tree.get(None) if self.tree else None
        if root is None or not root.children:
            return
        entries = []
        for _oldkey, nodeid in root.children:
            node = self.nodemap.node(nodeid)
            node.sortkey = glocale.sort_key(self.sample_surname(node.ref))
            entries.append((node.sortkey, nodeid))
        entries.sort()
        root.children = entries
        prev_id = None
        for _sortkey, nodeid in entries:
            node = self.nodemap.node(nodeid)
            node.prev = prev_id
            node.next = None
            if prev_id is not None:
                self.nodemap.node(prev_id).next = nodeid
            prev_id = nodeid
        self.clear_path_cache()

    def delete_row_by_handle(self, handle):
        member = self._handle_member.pop(handle, None)
        if member:
            key, group_name = member
            counter = self._members.get(key)
            if counter:
                counter[group_name] -= 1
                if counter[group_name] <= 0:
                    del counter[group_name]
        PersonTreeModel.delete_row_by_handle(self, handle)

    def column_header(self, node):
        """Group row text: the spellings in the group, then the code."""
        key = node.ref
        if not key:
            return PersonTreeModel.column_header(self, node)
        counter = self._members.get(key) or Counter()
        names = [n for n, _c in sorted(counter.items(), key=lambda i: (-i[1], i[0]))]
        text = ", ".join(names[:MAX_HEADER_NAMES])
        if len(names) > MAX_HEADER_NAMES:
            text += " +%d" % (len(names) - MAX_HEADER_NAMES)
        return "%s [%s]" % (text, key)


# -------------------------------------------------------------------------
#
# SortNameFormat
#
# -------------------------------------------------------------------------
class SortNameFormat(GrampsPreferences):
    """
    Name format chooser for sorting only.

    Borrows the Preferences name format model and the Display Name Editor
    plumbing from GrampsPreferences without opening Preferences. Selecting
    a format here never changes the application Name format preference.
    """

    # pylint: disable=super-init-not-called
    def __init__(self, view, configdialog):
        self.view = view
        self.uistate = view.uistate
        self.dbstate = view.dbstate
        # The view Configure dialog is a leaf in the window manager tree
        # (no submenu), so the editor cannot be its child: open top level.
        self.track = []
        self.window = configdialog.window  # parent for editor error dialogs
        self.selected_fmt = ()
        self.old_format = None
        self.examplename = self._example_name()

        # fmt_model: the real formats, shared with the Display Name Editor.
        # combo_model: a "Default" row first, then a copy of fmt_model.
        self.fmt_model, _index = self._build_name_format_model(0)
        self.combo_model = Gtk.ListStore(int, str, str, str)
        self.sort_combo = Gtk.ComboBox(model=self.combo_model)
        cell = Gtk.CellRendererText()
        cell.set_property("ellipsize", Pango.EllipsizeMode.END)
        self.sort_combo.pack_start(cell, True)
        self.sort_combo.add_attribute(cell, "text", 1)
        self.changed_id = self.sort_combo.connect("changed", self.cb_name_changed)
        # The borrowed core editor code reads self.fmt_obox and expects its
        # model to be the editor model (duplicate-name check, Remove). Give
        # it a never-shown combo on fmt_model so that code works unchanged.
        self.fmt_obox = Gtk.ComboBox(model=self.fmt_model)
        self.refill_combo(CONFIG.get("subsort.name_format"))

        self.edit_button = Gtk.Button.new_from_icon_name("gtk-edit", Gtk.IconSize.BUTTON)
        self.edit_button.set_tooltip_text(_("Display Name Editor"))
        self.edit_button.connect("clicked", self.cb_name_dialog)

    @staticmethod
    def _example_name():
        """The same example name the Preferences dialog uses."""
        name = Name()
        name.set_title("Dr.")
        name.set_first_name("Edwin Jose")
        surname = Surname()
        surname.set_prefix("von der")
        surname.set_surname("Smith")
        surname.set_connector("and")
        name.add_surname(surname)
        surname = Surname()
        surname.set_surname("Weston")
        name.add_surname(surname)
        surname = Surname()
        surname.set_surname("Wilson")
        surname.set_origintype(NameOriginType(NameOriginType.PATRONYMIC))
        name.add_surname(surname)
        name.set_primary_surname(0)
        name.set_suffix("Sr")
        name.set_call_name("Jose")
        name.set_nick_name("Ed")
        name.set_family_nick_name("Underhills")
        return name

    def cb_name_dialog(self, obj):
        """
        gtk-edit button: open the Display Name Editor.

        Only one Display Name Editor can exist (its window id is the class
        itself), whether it was opened here or from Preferences. When one
        is already open, ManagedWindow presents it and raises
        WindowActiveError, so there is nothing more to do.
        """
        try:
            DisplayNameEditor(self.uistate, self.dbstate, self.track, self)
        except WindowActiveError:
            pass

    def refill_combo(self, select_num):
        """
        Rebuild the combo list (Default row + current formats) and select
        select_num, or the Default row if it no longer exists. Does not
        emit the combo "changed" callback.
        """
        fmt = default_sort_format()
        translated = re.sub(
            "|".join(re.escape(k) for k in get_keywords()),
            lambda m: get_translation_from_keyword(m.group()),
            fmt,
        )
        example = name_displayer.format_str(self.examplename, fmt)
        self.sort_combo.handler_block(self.changed_id)
        self.combo_model.clear()
        self.combo_model.append([0, _("Default: %s") % translated, fmt, example])
        active = 0
        for index, row in enumerate(self.fmt_model, start=1):
            self.combo_model.append(list(row))
            if row[COL_NUM] == select_num:
                active = index
        self.sort_combo.set_active(active)
        self.sort_combo.handler_unblock(self.changed_id)

    def name_changed_check(self):
        """
        Called by the Display Name Editor when it closes: pick up added or
        edited formats and select the format last selected in the editor.
        """
        if self.selected_fmt:
            num = self.selected_fmt[COL_NUM]
        else:
            num = CONFIG.get("subsort.name_format")
        self.refill_combo(num)
        self.cb_name_changed(self.sort_combo)

    def cb_name_changed(self, obj):
        """Combo changed: sort-only format (NOT preferences.name-format)."""
        row_iter = obj.get_active_iter()
        if row_iter is None:
            return
        self.view.set_sort_name_format(self.combo_model.get_value(row_iter, COL_NUM))


# -------------------------------------------------------------------------
#
# FuzzyGroupingView
#
# -------------------------------------------------------------------------
class FuzzyGroupingView(BasePersonView):
    """
    A hierarchical view of the people based on phonetically grouped family name.
    """

    # the first (fixed) column shows the groups
    COLUMNS = [(_("Grouping"),) + tuple(BasePersonView.COLUMNS[0][1:])] + list(
        BasePersonView.COLUMNS[1:]
    )

    def __init__(self, pdata, dbstate, uistate, nav_group=0):
        self.encoders = discover_encoders()
        self.system_id = CONFIG.get("grouping.system")
        if self.system_id not in self.encoders:
            # stored system was uninstalled: fall back to Soundex
            self.system_id = DEFAULT_SYSTEM
        self.subsort_store = None
        self._subsort_filling = False
        self._refresh_timer = None  # pending delayed refresh (GLib source id)
        self._system_listeners = []  # weakrefs, see connect_phonetic_system

        BasePersonView.__init__(
            self,
            pdata,
            dbstate,
            uistate,
            _("Fuzzy Grouping"),
            FuzzyGroupingTreeModel,
            nav_group=nav_group,
        )
        # kept as one list object so a system change can update it in place
        self.toolbar_ui = self._build_toolbar_ui()
        self.additional_uis.append(self.toolbar_ui)

    def get_viewtype_stock(self):
        """
        Override the default icon.  Set for hierarchical view.
        """
        return ICON_NAME

    # ---------------------------------------------------------------
    # settings -> model
    # ---------------------------------------------------------------
    def subsort_order(self):
        """Stored subsort order, or the initial one if missing/stale."""
        rank = self._config.get("columns.rank") if self._config else []
        rank = [col for col in rank if col != BasePersonView.COL_NAME]
        if not rank:
            rank = list(range(1, len(self.COLUMNS)))
        required = {NAME_FORMAT_ROW} | set(range(1, len(self.COLUMNS)))
        stored = list(CONFIG.get("subsort.order") or [])
        if len(stored) == len(required) and set(stored) == required:
            return stored
        return INITIAL_SUBSORT_HEAD + [c for c in rank if c not in INITIAL_SUBSORT_HEAD]

    def _push_settings_to_model(self):
        model = FuzzyGroupingTreeModel
        model.encode = staticmethod(self.encoders[self.system_id][1])
        model.group_sort = CONFIG.get("grouping.sort")
        model.subsort = self.subsort_order()
        model.name_fmt_str = name_format_string(CONFIG.get("subsort.name_format"))

    def build_tree(self, *args, **kwargs):
        self._cancel_refresh()  # this build covers any pending change
        self._push_settings_to_model()
        BasePersonView.build_tree(self, *args, **kwargs)

    def _rebuild(self):
        """Force a new model (not just a re-filter of the old one) now."""
        self._cancel_refresh()
        self.dirty = True
        self.build_tree()

    def _schedule_refresh(self):
        """
        Refresh the view REFRESH_DELAY seconds after the last Configure
        change, so several quick changes cost one rebuild.
        """
        self._cancel_refresh()
        self._refresh_timer = GLib.timeout_add_seconds(
            REFRESH_DELAY, self._cb_refresh_timer
        )

    def _cancel_refresh(self):
        if self._refresh_timer is not None:
            GLib.source_remove(self._refresh_timer)
            self._refresh_timer = None

    def _cb_refresh_timer(self):
        self._refresh_timer = None
        self._rebuild()
        return False

    def _cb_configure_closed(self, *args):
        """Closing Configure applies a pending change at once."""
        if self._refresh_timer is not None:
            self._rebuild()

    # ---------------------------------------------------------------
    # first use: show Configure when there is no .ini yet
    # ---------------------------------------------------------------
    def change_page(self):
        BasePersonView.change_page(self)
        # encoder plugins may have been hidden or shown since the last visit
        self._refresh_encoders()
        # README / Markdown Dash may have changed since the toolbar was built
        button = self.uimanager.get_widget("FuzzyGroupingHelpButton")
        if button is not None:
            button.set_tooltip_text(help_tooltip())
        if _FIRST_RUN[0]:
            _FIRST_RUN[0] = False
            GLib.idle_add(self._cb_first_run_configure)

    def _refresh_encoders(self):
        """
        Re-discover the encoders. When the set changed, rebuild the system
        menu; when the current system is gone, regroup with Soundex. The
        stored choice in the .ini is kept, so showing the plugin again
        brings it back on the next visit to the view.
        """
        encoders = discover_encoders()
        wanted = CONFIG.get("grouping.system")
        if list(encoders) == list(self.encoders) and (
            self.system_id == wanted or wanted not in encoders
        ):
            return
        self.encoders = encoders
        old_system = self.system_id
        self.system_id = wanted if wanted in encoders else DEFAULT_SYSTEM

        self._refresh_toolbar()
        if self.system_id != old_system:
            self._notify_system_listeners()
            self._rebuild()

    def _cb_first_run_configure(self):
        save_config()  # the dialog has been offered once; do not repeat
        self.configure()
        return False

    # ---------------------------------------------------------------
    # Configure dialog
    # ---------------------------------------------------------------
    def _get_configure_page_funcs(self):
        base_funcs = BasePersonView._get_configure_page_funcs(self)
        base_columnpage, others = base_funcs[0], base_funcs[1:]

        def columnpage(configdialog):
            title, widget = base_columnpage(configdialog)
            self._insert_grouping_choice(widget)
            configdialog.window.connect("destroy", self._cb_configure_closed)
            return title, widget

        def subsortpage(configdialog):
            return _("Subsorting"), self._build_subsort_page(configdialog)

        return [columnpage, subsortpage] + others

    def _insert_grouping_choice(self, column_order):
        """Replace the 'first column cannot be changed' label."""
        box = Gtk.Box(spacing=12)
        box.set_halign(Gtk.Align.CENTER)
        box.pack_start(Gtk.Label(label=_("Grouping:")), False, False, 0)
        by_id = Gtk.RadioButton.new_with_label(None, _("Fuzzy grouping ID"))
        by_surname = Gtk.RadioButton.new_with_label_from_widget(by_id, _("Sample Surname"))
        if CONFIG.get("grouping.sort") == GROUP_BY_SURNAME:
            by_surname.set_active(True)
        by_id.connect("toggled", self.cb_grouping_toggled, GROUP_BY_ID)
        by_surname.connect("toggled", self.cb_grouping_toggled, GROUP_BY_SURNAME)
        box.pack_start(by_id, False, False, 0)
        box.pack_start(by_surname, False, False, 0)
        box.show_all()

        header = _('Tree View: first column "%s" cannot be changed') % self.COLUMNS[0][0]
        position = 0
        for index, child in enumerate(column_order.get_children()):
            if isinstance(child, Gtk.Label) and child.get_text() == header:
                position = index
                column_order.remove(child)
                break
        column_order.pack_start(box, False, False, 0)
        column_order.reorder_child(box, position)

    def cb_grouping_toggled(self, button, value):
        """Grouping radio buttons: applied immediately."""
        if not button.get_active() or CONFIG.get("grouping.sort") == value:
            return
        CONFIG.set("grouping.sort", value)
        save_config()
        self._schedule_refresh()

    def _build_subsort_page(self, configdialog):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.set_border_width(12)

        chooser = SortNameFormat(self, configdialog)
        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label=_("%s: ") % _("Name format")), False, False, 0)
        row.pack_start(chooser.sort_combo, True, True, 0)
        row.pack_start(chooser.edit_button, False, False, 0)
        vbox.pack_start(row, False, False, 0)

        vbox.pack_start(
            Gtk.Label(label=_("Drag and drop, or edit the numbers, to change the subsort order")),
            False,
            False,
            0,
        )

        # order number, label, model column (NAME_FORMAT_ROW for Name format)
        self.subsort_store = Gtk.ListStore(int, str, int)
        self._fill_subsort_store(self.subsort_order())
        # a drag'n'drop reorder ends with "row-deleted" on the old row
        self.subsort_store.connect("row-deleted", self.cb_subsort_row_deleted)
        tree = Gtk.TreeView(model=self.subsort_store)
        tree.set_reorderable(True)  # drag'n'drop, as in the Columns tab

        number = Gtk.CellRendererSpin()
        number.set_property("editable", True)
        number.set_property(
            "adjustment", Gtk.Adjustment(1, 1, len(self.subsort_store), 1, 5, 0)
        )
        number.connect("edited", self.cb_subsort_number_edited)
        column = Gtk.TreeViewColumn(_("Order"), number, text=0)
        column.set_min_width(60)
        tree.append_column(column)
        column = Gtk.TreeViewColumn(_("Column Name"), Gtk.CellRendererText(), text=1)
        column.set_min_width(225)
        tree.append_column(column)

        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(300, 300)
        scroll.add(tree)
        vbox.pack_start(scroll, True, True, 0)
        return vbox

    def _fill_subsort_store(self, order):
        self._subsort_filling = True  # clear() emits row-deleted
        self.subsort_store.clear()
        for number, col in enumerate(order, start=1):
            label = _("Name format") if col == NAME_FORMAT_ROW else self.COLUMNS[col][0]
            self.subsort_store.append([number, label, col])
        self._subsort_filling = False

    def cb_subsort_row_deleted(self, store, path):
        """After a drag'n'drop: renumber, save, and refresh later."""
        if self._subsort_filling:
            return
        order = [row[2] for row in store]
        for number, row in enumerate(store, start=1):
            row[0] = number
        if order != list(CONFIG.get("subsort.order") or []):
            CONFIG.set("subsort.order", order)
            save_config()
            self._schedule_refresh()

    def cb_subsort_number_edited(self, renderer, path, new_text):
        """Move the edited row to its new number and renumber the rest."""
        try:
            new_pos = int(new_text)
        except ValueError:
            return
        order = [row[2] for row in self.subsort_store]
        new_pos = max(1, min(new_pos, len(order)))
        old_pos = int(path) + 1
        if new_pos == old_pos:
            return
        order.insert(new_pos - 1, order.pop(old_pos - 1))
        self._fill_subsort_store(order)
        CONFIG.set("subsort.order", order)
        save_config()
        self._schedule_refresh()

    def set_sort_name_format(self, num):
        """Sort-only name format chosen in the Subsorting tab."""
        if CONFIG.get("subsort.name_format") == num:
            return
        CONFIG.set("subsort.name_format", num)
        save_config()
        self._schedule_refresh()

    # ---------------------------------------------------------------
    # toolbar: phonetic system menu
    # ---------------------------------------------------------------
    def _build_toolbar_ui(self):
        """Toolbar menu button and its menu, for the current system."""
        items = "".join(
            """
          <item>
            <attribute name="action">win.FuzzyGroupingSystem</attribute>
            <attribute name="target">%s</attribute>
            <attribute name="label">%s</attribute>
          </item>"""
            % (escape(system_id), escape(label))
            for system_id, (label, _encode) in self.encoders.items()
        )
        menu = """
      <menu id="FuzzyGroupingSystemMenu">
        <section>%s
        </section>
      </menu>
    """ % items
        toolbar = """
    <placeholder id="MoreButtons">
    <child>
      <object class="GtkToolItem">
        <child>
          <object class="GtkMenuButton">
            <property name="tooltip_text">%s</property>
            <property name="menu-model">FuzzyGroupingSystemMenu</property>
            <property name="relief">GTK_RELIEF_NONE</property>
            <property name="use-popover">False</property>
            <child>
              <object class="GtkBox">
                <property name="visible">True</property>
                <property name="spacing">4</property>
                <child>
                  <object class="GtkImage">
                    <property name="visible">True</property>
                    <property name="icon-name">%s</property>
                  </object>
                </child>
                <child>
                  <object class="GtkLabel">
                    <property name="visible">True</property>
                    <property name="label">%s</property>
                  </object>
                </child>
                <child>
                  <object class="GtkImage">
                    <property name="visible">True</property>
                    <property name="icon-name">pan-down-symbolic</property>
                  </object>
                </child>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
    <child>
      <object class="GtkToolItem">
        <child>
          <object class="GtkButton" id="FuzzyGroupingHelpButton">
            <property name="action-name">win.FuzzyGroupingHelp</property>
            <property name="tooltip_text">%s</property>
            <property name="relief">GTK_RELIEF_NONE</property>
            <child>
              <object class="GtkImage">
                <property name="visible">True</property>
                <property name="icon-name">%s</property>
                <property name="icon_size">3</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
    </placeholder>
    """ % (
            escape(_("Select the phonetic system used to group people")),
            ICON_NAME,
            escape(self.encoders[self.system_id][0]),
            escape(help_tooltip()),
            HELP_ICON_NAME,
        )
        return [menu, toolbar]

    def cb_show_help(self, *args):
        """Toolbar Help icon."""
        show_help(self.uistate)

    def cb_set_phonetic_system(self, action, value):
        """Toolbar menu callback: regroup with the chosen system."""
        action.set_state(value)
        self.set_phonetic_system(value.get_string())

    def _refresh_toolbar(self):
        """
        Rebuild the toolbar fragments for the current system (same ids, so
        leaving the view still removes them). The live toolbar is only
        touched while this view is shown; otherwise the fragments are
        merged on the next visit.
        """
        self.toolbar_ui[:] = self._build_toolbar_ui()
        if not self.active:
            return
        if self.action_group is not None:
            action = self.uimanager.get_action(self.action_group, "FuzzyGroupingSystem")
            if action is not None:
                action.set_state(GLib.Variant("s", self.system_id))
        self.uimanager.add_ui_from_string(self.toolbar_ui)
        self.uimanager.update_menu()

    # ---------------------------------------------------------------
    # Phonetic system sync with gramplets docked in this view
    #
    # Duck-typed, so no addon imports another: a docked gramplet checks
    # getattr(self.gui.view, "PHONETIC_SYSTEM_SYNC", 0) >= 1, then uses
    # phonetic_system_id(), set_phonetic_system() and
    # connect_phonetic_system(). Used by Flat Filter and Fuzzy Matching.
    # ---------------------------------------------------------------
    PHONETIC_SYSTEM_SYNC = 1

    def phonetic_system_id(self):
        """The id of the phonetic system this view groups with."""
        return self.system_id

    def connect_phonetic_system(self, callback):
        """
        Call callback(system_id) when this view changes phonetic system.
        A bound method is held weakly, so a closed gramplet needs no
        disconnect.
        """
        try:
            ref = weakref.WeakMethod(callback)
        except TypeError:  # plain function
            ref = weakref.ref(callback)
        self._system_listeners.append(ref)

    def set_phonetic_system(self, system_id, source=None):
        """
        Group with system_id. Returns False when this view does not have
        that system (for example its plugin is hidden) or already uses it.

        source is the object asking (a docked gramplet); it is not called
        back. A change from a gramplet waits REFRESH_DELAY seconds before
        regrouping, so a following Find click does a single rebuild.
        """
        if system_id == self.system_id or system_id not in self.encoders:
            return False
        self.system_id = system_id
        CONFIG.set("grouping.system", system_id)
        save_config()
        self._refresh_toolbar()
        self._notify_system_listeners(source)
        if source is None:
            self._rebuild()
        else:
            self.dirty = True
            self._schedule_refresh()
        return True

    def _notify_system_listeners(self, source=None):
        for ref in list(self._system_listeners):
            callback = ref()
            if callback is None:
                self._system_listeners.remove(ref)
                continue
            if source is not None and getattr(callback, "__self__", None) is source:
                continue
            try:
                callback(self.system_id)
            except Exception:  # pylint: disable=broad-except
                LOG.exception("Fuzzy Grouping: phonetic system listener failed")

    def define_actions(self):
        """
        Define actions for the popup menu specific to the tree view.
        """
        BasePersonView.define_actions(self)

        self.action_list.extend(
            [
                ("OpenAllNodes", self.open_all_nodes),
                ("CloseAllNodes", self.close_all_nodes),
                ("FuzzyGroupingHelp", self.cb_show_help),
            ]
        )
        # radio action: its state is the selected system id
        self._add_toggle_action(
            "FuzzyGroupingSystem", self.cb_set_phonetic_system, "", self.system_id
        )

    additional_ui = BasePersonView.additional_ui[:]
    additional_ui.append(  # Defines the UI string for UIManager
        """
      <section id="PopUpTree">
        <item>
          <attribute name="action">win.OpenAllNodes</attribute>
          <attribute name="label" translatable="yes">"""
        """Expand all Nodes</attribute>
        </item>
        <item>
          <attribute name="action">win.CloseAllNodes</attribute>
          <attribute name="label" translatable="yes">"""
        """Collapse all Nodes</attribute>
        </item>
      </section>
    """
    )

    def add(self, *obj):
        person = Person()

        # attempt to get the current surname
        model, pathlist = self.selection.get_selected_rows()
        name = Name()
        # the editor requires a surname
        name.add_surname(Surname())
        name.set_primary_surname(0)
        basepers = None
        if len(pathlist) == 1:
            path = pathlist[0]
            pathids = path.get_indices()
            if len(pathids) == 1:
                path = Gtk.TreePath((pathids[0], 0))
            iter_ = model.get_iter(path)
            handle = model.get_handle_from_iter(iter_)
            basepers = self.dbstate.db.get_person_from_handle(handle)
        if basepers:
            preset_name(basepers, name)
        person.set_primary_name(name)
        try:
            EditPerson(self.dbstate, self.uistate, [], person)
        except WindowActiveError:
            pass

    def get_config_name(self):
        return __name__
