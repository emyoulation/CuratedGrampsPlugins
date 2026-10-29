#
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""
Fuzzy Grouping person view.

Forked from Gramps core gramps/plugins/view/persontreeview.py
(maintenance/gramps61, commit 5cebb2c55fdbb0a92428625d409918216409db70).
The grouping itself is done by PersonTreeModel.add_row() in
gramps/gui/views/treemodels/peoplemodel.py, so this addon subclasses that
model and groups by a phonetic code of the core group name (which still
honors "Group as" overrides and the surname group mapping table).

Soundex (gramps.gen.soundex) is the default and the fallback. Other
systems are discovered from installed RULE plugins whose id starts with
"FuzzyMatchingEncoder:" (the encoder contract of the Phonetic Filter Rules
addon: ALGORITHM_ID, ALGORITHM_LABEL, encode(name) -> set of codes).

Configure dialog additions:

- Columns tab: a "Grouping:" choice (Sample Surname / Fuzzy grouping ID)
  and the phonetic system list replace the "first column cannot be
  changed" label.
- Subsorting tab: a sort-only Name format (never touches the application
  Name format preference) and a numbered subsort order.

The right-click menu adds Expand/Collapse all Nodes and a Grouping submenu
with every available phonetic system.

Diagnostics: start Gramps with ``gramps -d fuzzygroupingview`` to get
DEBUG lines for every index build (trigger, filter, settings, time per
step), phonetic system changes and Expand all Nodes.
"""

# One view class with its model and Configure tab helpers; splitting it
# into several modules would only add imports between them.
# pylint: disable=too-many-lines

# ------------------------
# Python modules
# ------------------------
from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import weakref
from collections import Counter, defaultdict
from time import perf_counter
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from xml.sax.saxutils import escape

from gi.repository import Gdk, Gio, GLib, Gtk, Pango

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config as global_config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import WindowActiveError
from gramps.gen.lib import Name, NameOriginType, Person, Surname
from gramps.gen.plug import PluginRegister
from gramps.gen.plug._pluginreg import RULE
from gramps.gen.soundex import soundex as core_soundex
from gramps.gen.utils.db import preset_name
from gramps.gen.utils.keyword import KEYWORDS, get_translation_from_keyword
from gramps.gui.configure import COL_NUM, DisplayNameEditor, GrampsPreferences
from gramps.gui.dialog import OkDialog
from gramps.gui.editors import EditPerson
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.utils import ProgressMeter
from gramps.gui.views.treemodels.peoplemodel import PersonTreeModel
from gramps.gui.views.treemodels.treebasemodel import TreeBaseModel
from gramps.plugins.lib.libpersonview import BasePersonView

try:  # Gramps 5.2: person data is a tuple
    from gramps.gui.views.treemodels.peoplemodel import (  # type: ignore[attr-defined]
        COLUMN_NAME,
    )
except ImportError:  # Gramps 6.x: person data is a DataDict
    COLUMN_NAME = 3

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType

    from gramps.gen.plug._pluginreg import PluginData
    from gramps.gen.types import PersonHandle  # Gramps 6.1 and newer
    from gramps.gui.configure import ConfigureDialog
    from gramps.gui.displaystate import DisplayState

    #: An encoder: a name in, one code or a set of codes out.
    Encoder = Callable[[str], "set[str] | str"]

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)

# ------------------------
# Constants
# ------------------------
PLUGIN_ID = "fuzzygroupingview"  # matches id= in the .gpr.py
SCHEMA_VERSION = "1"
DEFAULT_SYSTEM = "soundex"
EXACT_SYSTEM = "none"  # no phonetic matching: group as Grouped People does
ENCODER_ID_PREFIX = "FuzzyMatchingEncoder:"  # Phonetic Filter Rules contract
MAX_HEADER_NAMES = 4  # spellings listed in a group header before "+N"
GROUP_BY_ID = "id"
GROUP_BY_SURNAME = "surname"
NAME_FORMAT_ROW = -1  # subsort list entry for the "Name format" line
SUBSORT_SEPARATOR = "\t"  # lowest non-ignorable collation weight
# Sidebar gramplet ids (the id= in each .gpr.py): Flat Filter first and
# Fuzzy Matching second when registered and not hidden, core Person Filter
# always last.
SIDEBAR_FLAT_FILTER = "Flat Filter"
SIDEBAR_FUZZY_MATCHING = "Fuzzy Matching"
SIDEBAR_PERSON_FILTER = "Person Filter"
AUTO_EXPAND_LIMIT = 50  # fewer people shown than this: open every group
REFRESH_DELAY = 2  # seconds between a Configure change and the view refresh
PROGRESS_DELAY = 1.0  # seconds of index building before a progress dialog
PROGRESS_CHECK_EVERY = 256  # rows between elapsed-time checks
EVENTS_EVERY = 0.2  # seconds between GTK event runs while the dialog is open
EXPAND_PROGRESS_DELAY = 2.0  # seconds of Expand all before a progress dialog

# Initial subsort: Name format, Birth Date, Death Date, Spouse, Last Changed,
# then the remaining columns in their Display list order.
INITIAL_SUBSORT_HEAD = [
    NAME_FORMAT_ROW,
    BasePersonView.COL_BDAT,
    BasePersonView.COL_DDAT,
    BasePersonView.COL_SPOUSE,
    BasePersonView.COL_CHAN,
]

# ------------------------
# View icon
#
# The .gpr.py cannot point icondir at our media folder: it is exec()'d
# without __file__, and a relative icondir is not resolved against the
# plugin folder. Gramps imports every view module at startup (before the
# toolbar and view buttons are built), so appending the folder to the icon
# theme search path here is early enough. A loose SVG in a search path
# folder is found by its file name stem.
# ------------------------
VIEW_ICON = "fuzzy-grouping"
FALLBACK_ICON = "gramps-tree-group"
_MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
if os.path.isfile(os.path.join(_MEDIA_DIR, VIEW_ICON + ".svg")):
    Gtk.IconTheme.get_default().append_search_path(_MEDIA_DIR)
    ICON_NAME = VIEW_ICON
else:
    LOG.warning("Fuzzy Grouping: %s.svg not found in %s", VIEW_ICON, _MEDIA_DIR)
    ICON_NAME = FALLBACK_ICON

# ------------------------
# Settings (.ini in this addon's own folder)
#
# CONFIG.init() writes the .ini with an empty [meta] block when there is
# none, at Gramps startup. The [meta] block is filled in only once the view
# has been shown (save_config()), so an empty plugin_id tells us to show
# the Configure dialog on first use, even when Gramps was restarted after
# the install before the view was opened.
# ------------------------
CONFIG = global_config.register_manager("FuzzyGrouping", use_plugins_path=False)
CONFIG.register("meta.plugin_id", "")
CONFIG.register("meta.schema_version", "")
CONFIG.register("grouping.system", DEFAULT_SYSTEM)
CONFIG.register("grouping.sort", GROUP_BY_SURNAME)
CONFIG.register("subsort.name_format", 0)  # 0 = application default format
CONFIG.register("subsort.order", [])  # [] = INITIAL_SUBSORT_HEAD + rest
# True: the user turned subsorting off, cancelled a slow build, or a build
# did not finish; only the first subsort field is used until it is turned
# on again on the Subsorting tab
CONFIG.register("subsort.suspended", False)
# True while an index build runs; still True at startup = the last build
# never finished (crash, hang, killed)
CONFIG.register("state.building", False)
CONFIG.init()


def save_config() -> None:
    """
    Write the .ini, with its [meta] identification block.
    """
    CONFIG.set("meta.plugin_id", PLUGIN_ID)
    CONFIG.set("meta.schema_version", SCHEMA_VERSION)
    CONFIG.save()


_FIRST_RUN = [not CONFIG.get("meta.plugin_id")]  # list so the view can clear it

# A statusbar message for the view to show after the next build, when the
# subsort was turned off by a cancel or by an unfinished build.
_NOTICE: list[str | None] = [None]
if CONFIG.get("state.building"):
    CONFIG.set("state.building", False)
    CONFIG.set("subsort.suspended", True)
    save_config()
    _NOTICE[0] = _(
        "Fuzzy Grouping: the last index build did not finish, so subsorting "
        "is off. To turn it on again, use Configure, Subsorting tab."
    )


# ------------------------
# Phonetic encoders
# ------------------------
def _exact_codes(name: str) -> set[str]:
    """
    The "None" system: the group name itself, so people group on an exact
    match of the preferred surname (or its Group as override), as in the
    core Grouped People view.

    :param name: The group name.
    :returns: A one-element set holding the name.
    """
    return {name}


def _soundex_codes(name: str) -> set[str]:
    """
    Built-in Gramps Soundex, as a one-element set.

    :param name: The group name.
    :returns: A one-element set holding the Soundex code.
    """
    try:
        return {core_soundex(name)}
    except UnicodeEncodeError:
        return {core_soundex("")}


def discover_encoders() -> dict[str, tuple[str, Encoder]]:
    """
    Return the phonetic systems: None and built-in Soundex first, then
    every installed encoder rule plugin, sorted by label.

    Encoder plugins the user hid/deactivated in the Plugin Manager are
    skipped: load_plugin() itself does not check that (see the
    "Deactivate" note in HelpDocButton.md), so it is checked here,
    live, on every call.

    :returns: A dict of system id to (label, encode function).
    """
    encoders: dict[str, tuple[str, Encoder]] = {
        EXACT_SYSTEM: (_("None"), _exact_codes),
        DEFAULT_SYSTEM: (_("Soundex"), _soundex_codes),
    }
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
        if system_id in (DEFAULT_SYSTEM, EXACT_SYSTEM) or not callable(encode):
            continue  # the built-in Soundex (and None) always win
        found.append((label, system_id, encode))
    for label, system_id, encode in sorted(found, key=lambda item: item[:2]):
        encoders.setdefault(system_id, (label, encode))
    return encoders


# Name format strings come in two forms: the built-in formats use codes
# ("%l, %f %s"), formats made in the Display Name Editor use keywords,
# English or translated ("Surname, Given Suffix"). Both are turned into
# codes before the surname parts are removed.
_COMMA = glocale.translation.gettext(",")  # the name format COMMAGLYPH
# codes that produce surname parts: full surname, primary surname and its
# parts, patronymic and its parts, raw surnames, not-patronymic, rest
# (non-primary surnames), prefixes
_SURNAME_CODES = re.compile(r"%[0-2]?[lmyqorpLMYQORP]")
_ANY_CODE = re.compile(r"%[0-2]?[a-zA-Z]")


def _keyword_replacements() -> list[tuple[str, str]]:
    """
    Keyword to code replacements, as the name displayer makes them.

    :returns: (text, code) pairs, longest text first.
    """
    pairs: dict[str, str] = {}
    for key, code, standard, upper in KEYWORDS:
        for text, new in (
            (standard, code),
            (upper, code.upper()),
            (key, code),
            (key.title(), code),
            (key.upper(), code.upper()),
        ):
            pairs.setdefault(text, "%" + new)
    return sorted(pairs.items(), key=lambda item: len(item[0]), reverse=True)


def format_codes(fmt_str: str) -> str:
    """
    Replace every keyword in a name format string by its % code.

    :param fmt_str: A name format string, in keywords or codes.
    :returns: The format string in % codes.
    """
    text = fmt_str.replace("%%", "\x00")
    for word, code in _keyword_replacements():
        text = text.replace(word, code)
    return text.replace("\x00", "%%")


def surnameless_format(fmt_str: str) -> str:
    """
    Remove every surname part from a name format string, and tidy up the
    punctuation left behind.

    :param fmt_str: A name format string, in keywords or codes.
    :returns: The format string in % codes without surname parts, or
        ``"%f"`` (Given) when nothing else is left.
    """
    text = format_codes(fmt_str).replace("%%", "\x00")
    text = _SURNAME_CODES.sub("", text)
    commas = f"[,{re.escape(_COMMA)}]"
    text = re.sub(r"\(\s*\)|/\s*/|\[\s*\]", "", text)  # emptied brackets
    text = re.sub(rf"\s*{commas}(\s*{commas})+", _COMMA, text)  # repeats
    text = re.sub(rf"\s+{commas}", _COMMA, text)  # no space before a comma
    text = re.sub(r"\s{2,}", " ", text)
    text = text.strip(" ,;:/-" + _COMMA).replace("\x00", "%%")
    return text if _ANY_CODE.search(text) else "%f"


def format_label(fmt_str: str) -> str:
    """
    A name format string as the Preferences show it.

    :param fmt_str: A name format string, in keywords or codes.
    :returns: The format string in translated keywords.
    """
    return _ANY_CODE.sub(
        lambda m: get_translation_from_keyword(m.group()), format_codes(fmt_str)
    )


def default_sort_format() -> str:
    """
    The current Display name format, without its surname portion.

    :returns: A name format string in % codes.
    """
    default = name_displayer.get_default_format()
    return surnameless_format(name_displayer.name_formats[default][1])


def name_format_string(num: int) -> str:
    """
    The format string for a name format number.

    :param num: A name format number; 0 is the "Default" choice.
    :returns: The format string; 0 (the default), unknown or inactive
        formats give the Display name format without surnames.
    """
    formats = name_displayer.name_formats
    if not num or num not in formats or not formats[num][2]:
        return default_sort_format()
    return formats[num][1]


# ------------------------
# Help (from the HELP BUTTON BLOCK of help_doc_button.py, see
# HelpDocButton.md; here as a toolbar icon instead of a labeled button)
# ------------------------
_MARKDOWNDASH_ID = "markdowndash"
HELP_ICON_NAME = "help-browser"  # from the icon theme, color variant only
#: Full-color help icon bundled in the media folder, used only when the
#: icon theme has no color help-browser icon (instead of its symbolic one).
HELP_ICON_FILE = os.path.join(_MEDIA_DIR, "Gnome-help-browser.svg")

# The toolbar is rebuilt from its XML by every UIManager.update_menu()
# call (for example when Gramps shows or hides actions), so an image set
# from code is lost at the next rebuild. The Help icon therefore goes in the
# XML as an icon name: a private, unique name whose only file is a copy of
# the chosen color icon. No theme has that name, and no "-symbolic" file
# exists for it, so GTK can only ever show that color icon.
_HELP_ICON_DIR = os.path.join(GLib.get_user_cache_dir(), "gramps-fuzzygrouping-icons")
_HELP_ICON_STATE: dict[str, Any] = {"source": None, "name": None, "serial": 0}


def _help_icon_source() -> str | None:
    """
    Find the color Help icon to show: the current icon theme help-browser
    icon in its regular (color) variant, or else the bundled SVG. Never a
    symbolic icon.

    :returns: The icon file path, or ``None`` if neither is available.
    """
    info = Gtk.IconTheme.get_default().lookup_icon(
        HELP_ICON_NAME, 48, Gtk.IconLookupFlags.FORCE_REGULAR
    )
    if info is not None and not info.is_symbolic():
        filename = info.get_filename()
        if filename and os.path.isfile(filename):
            return filename
    if os.path.isfile(HELP_ICON_FILE):
        return HELP_ICON_FILE
    LOG.warning("Fuzzy Grouping: no full-color Help icon (%s missing)", HELP_ICON_FILE)
    return None


def help_icon_name() -> str:
    """
    The private icon name for the Help icon, refreshed when the chosen
    source file changes (for example after an icon theme change).

    :returns: The icon name, or ``""`` if no color icon is available, so
        that no symbolic one shows.
    """
    source = _help_icon_source()
    state = _HELP_ICON_STATE
    if source is None:
        return ""
    if source == state["source"] and state["name"]:
        return state["name"]
    try:
        os.makedirs(_HELP_ICON_DIR, exist_ok=True)
        own_prefix = f"fuzzygrouping-help-{os.getpid()}-"
        for old in os.listdir(_HELP_ICON_DIR):  # earlier copies of this process
            if old.startswith(own_prefix):
                os.remove(os.path.join(_HELP_ICON_DIR, old))
        state["serial"] += 1
        # a new name each time, so GTK never serves a cached older image
        name = f"{own_prefix}{state['serial']}"
        extension = os.path.splitext(source)[1].lower() or ".png"
        shutil.copyfile(source, os.path.join(_HELP_ICON_DIR, name + extension))
    except OSError:
        LOG.warning("Fuzzy Grouping: cannot prepare the Help icon", exc_info=True)
        return ""
    theme = Gtk.IconTheme.get_default()
    if _HELP_ICON_DIR not in theme.get_search_path():
        theme.append_search_path(_HELP_ICON_DIR)
    else:
        # make the theme see the new file
        theme.set_search_path(theme.get_search_path())
    state["source"], state["name"] = source, name
    return name


def find_local_readme(pdata: PluginData | None) -> str | None:
    """
    Find the canonical README.md of a plugin.

    :param pdata: The plugin data, or ``None``.
    :returns: The README.md path, or ``None`` if the plugin has no README
        of any kind (README.md, README_<lang>.md or
        locale/<lang>/README.md, decided by MarkdownUtils when importable).
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # importable only once Markdown Dash has been loaded
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path  # type: ignore
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener() -> Callable[..., Any] | None:
    """
    Find the open_markdown_file() function of Markdown Dash.

    :returns: The function, or ``None`` when Markdown Dash is deactivated,
        not registered, fails to load, or lacks it.
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


def open_help_url(pdata: PluginData, parent: Gtk.Window | None) -> None:
    """
    Open the registered help_url of a plugin in the default browser; a
    bare wiki page title is resolved against gramps-project.org.

    :param pdata: The plugin data.
    :param parent: The parent window for the "no documentation" dialog.
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


def own_pdata() -> PluginData | None:
    """
    This view's own plugin data.

    :returns: The PluginData of this view, or ``None``.
    """
    return PluginRegister.get_instance().get_plugin(PLUGIN_ID)


def help_uses_readme() -> bool:
    """
    Tell which documentation a click on Help will show.

    :returns: ``True`` when the README will show in Markdown Dash.
    """
    # Load Markdown Dash first: that makes MarkdownUtils importable,
    # which find_local_readme() uses to recognize translated READMEs.
    return (
        resolve_markdown_dash_opener() is not None
        and find_local_readme(own_pdata()) is not None
    )


def help_tooltip() -> str:
    """
    The Help icon tooltip.

    :returns: A tooltip saying which documentation a click will show.
    """
    if help_uses_readme():
        return _(
            "View the ReadMe markdown docs for the Fuzzy Grouping person view mode"
        )
    return _("Browse to the Help URL for the Fuzzy Grouping person view mode")


def show_help(uistate: DisplayState) -> None:
    """
    Show the README.md in Markdown Dash when possible, else the help_url.

    :param uistate: The Gramps display state.
    """
    pdata = own_pdata()
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None and pdata is not None:
            open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            return
    if pdata is not None:
        open_help_url(pdata, uistate.window)


# ------------------------
# Diagnostics: index build timing
#
# With "gramps -d fuzzygroupingview", logs one START block before every
# index build (so a crash or a hang still leaves a trace) and DONE lines
# after it. Kept in the release for field reports of slow views; nothing
# is measured or logged without the -d flag.
# ------------------------
_TIMING: dict[str, Any] = {"serial": 0, "last_end": None}
# The page that was shown before the current one. Updated by a switch-page
# handler that runs AFTER the view manager's own handler (which is the one
# that calls set_active() and so builds the index), so while a switch builds
# our index, "shown" still names the view that the user came from.
_PAGE_TRACK: dict[str, Any] = {"connected": False, "shown": None}

# function name in the call chain -> what the user did
_TRIGGERS = {
    "set_active": None,  # view switch, described from _PAGE_TRACK
    "change_db": "family tree loaded",
    "object_build": "database rebuild signal (import, batch edit, undo...)",
    "search_build_tree": "search bar Find",
    "column_clicked": "column header click (sort)",
    "set_column_order": "Configure, Columns tab Apply",
    "cb_refresh_timer": "delayed refresh (Configure or gramplet change)",
    "cb_configure_closed": "Configure closed with a pending change",
    "_refresh_encoders": "encoder plugins hidden or shown",
}
# our own frames, left out of the logged call chain
_OWN_FRAMES = {
    "_timing_trigger",
    "_timing_start",
    "rebuild_data",
    "build_tree",
    "_rebuild",
    "make_model",
    "__init__",
}
_OWN_FILES = (
    "fuzzygroupingview.py",
    "listview.py",
    "treebasemodel.py",
    "peoplemodel.py",
)


def timing_on() -> bool:
    """
    Tell whether the timing log is wanted: Gramps was started with the
    debug flag for this module logger, ``gramps -d fuzzygroupingview``
    (the logger name is the module name, as Gramps imports plugin modules
    by name).

    :returns: ``True`` when DEBUG lines of this module are logged.
    """
    return LOG.isEnabledFor(logging.DEBUG)


def timing_print(msg: str) -> None:
    """
    Log one timing line, at DEBUG level (Gramps adds time and source).

    :param msg: The line to log.
    """
    LOG.debug(msg)


def _page_label(viewmanager: Any, page_num: int) -> str | None:
    """
    Describe a view manager page as "Category / View".

    :param viewmanager: The Gramps view manager.
    :param page_num: The notebook page number.
    :returns: The description, or ``None`` for an unknown page.
    """
    try:
        page = viewmanager.pages[page_num]
    except (AttributeError, IndexError, TypeError):
        return None
    category = getattr(page, "translated_category", "") or ""
    try:
        title = page.get_title()
    except Exception:  # pylint: disable=broad-except
        title = page.__class__.__name__
    return f"{category} / {title}" if category else str(title)


def cb_page_switched(
    _notebook: Gtk.Notebook, _page: Gtk.Widget, page_num: int, viewmanager: Any
) -> None:
    """
    Notebook "switch-page" handler: remember the page now shown.

    :param _notebook: The view manager notebook.
    :param _page: The page widget.
    :param page_num: The page number.
    :param viewmanager: The Gramps view manager.
    """
    _PAGE_TRACK["shown"] = _page_label(viewmanager, page_num)


def timing_track_pages(uistate: DisplayState) -> None:
    """
    Start following which view is shown (once per session).

    :param uistate: The Gramps display state.
    """
    if _PAGE_TRACK["connected"]:
        return
    viewmanager = getattr(uistate, "viewmanager", None)
    notebook = getattr(viewmanager, "notebook", None)
    if notebook is None:
        return
    # this view is being created inside a page switch: the page shown
    # right now is the one the user is leaving (none at startup)
    _PAGE_TRACK["shown"] = _page_label(viewmanager, notebook.get_current_page())
    notebook.connect("switch-page", cb_page_switched, viewmanager)
    _PAGE_TRACK["connected"] = True


def _timing_trigger() -> tuple[str, str]:
    """
    Describe what started this build, from the call stack.

    :returns: (what the user did, the call chain as text).
    """
    chain: list[str] = []
    label = None
    frame: FrameType | None = sys._getframe(1)  # pylint: disable=protected-access
    while frame is not None and len(chain) < 8:
        func = frame.f_code.co_name
        fname = os.path.basename(frame.f_code.co_filename)
        frame = frame.f_back
        if func in _OWN_FRAMES and fname in _OWN_FILES:
            continue
        chain.append(f"{func} ({fname})")
        if label is not None:
            continue
        if func in _TRIGGERS:
            if func == "set_active":
                came_from = _PAGE_TRACK["shown"]
                label = (
                    f"view switch from {came_from}"
                    if came_from
                    else "startup (first view shown)"
                )
            else:
                label = _TRIGGERS[func]
        elif func == "clicked" and "sidebarfilter" in fname:
            label = "sidebar filter Find"
        elif func == "set_phonetic_system":
            label = "phonetic system changed"
    return label or "other (see call chain)", " <- ".join(chain[:6])


def _describe_rule(rule: Any) -> str:
    """
    Describe one filter rule for the timing log.

    :param rule: A filter rule.
    :returns: The rule class name and its values.
    """
    values = [v for v in (getattr(rule, "list", None) or []) if v not in ("", None)]
    text = rule.__class__.__name__
    if values:
        text += repr(values)
    if getattr(rule, "use_regex", False):
        text += " regex"
    return text


def timing_filter_text(dfilter: Any) -> str:
    """
    Describe the filter or search that an index build applies.

    :param dfilter: A GenericFilter, a search filter, or ``None``.
    :returns: A short description.
    """
    if dfilter is None:
        return "none"
    if hasattr(dfilter, "get_rules"):  # GenericFilter (sidebar or custom)
        rules = [_describe_rule(r) for r in dfilter.get_rules()]
        try:
            name = dfilter.get_name()
        except Exception:  # pylint: disable=broad-except
            name = ""
        inverted = " inverted" if dfilter.get_invert() else ""
        return (
            f"filter {name or '(sidebar)'!r}, {dfilter.get_logical_op()}"
            f"{inverted}: {'; '.join(rules) or 'no rules'}"
        )
    if hasattr(dfilter, "text"):  # SearchFilter / ExactSearchFilter
        func = getattr(dfilter, "func", None)
        how = "equals" if "Exact" in dfilter.__class__.__name__ else "contains"
        inverted = " (inverted)" if getattr(dfilter, "invert", False) else ""
        return (
            f"search bar: {getattr(func, '__name__', '?')} {how} "
            f"{dfilter.text!r}{inverted}"
        )
    return dfilter.__class__.__name__


def _secs(value: float) -> str:
    """
    Seconds as text for the timing log.

    :param value: A time in seconds.
    :returns: The time with two decimals and " s".
    """
    return f"{value:.2f} s"


def _primary_name(data: Any) -> Any:
    """
    The primary name of person data from the model cursor or map.

    :param data: Person data: a DataDict (Gramps 6.x) or a tuple (5.2).
    :returns: The primary name data.
    """
    try:
        return data.primary_name  # Gramps 6.x
    except AttributeError:
        return data[COLUMN_NAME]  # Gramps 5.2


# ------------------------------------------------------------
#
# FuzzyGroupingTreeModel
#
# ------------------------------------------------------------
# pylint: disable-next=too-many-instance-attributes
class FuzzyGroupingTreeModel(PersonTreeModel):
    """
    PersonTreeModel that groups by a phonetic code of the group name.

    The view sets the class attributes below before (re)building.
    """

    encode: Encoder = staticmethod(_soundex_codes)  # type: ignore[assignment]
    group_sort: str = GROUP_BY_SURNAME
    subsort: list[int] = []  # model columns, NAME_FORMAT_ROW for the name format
    name_fmt_str: str | None = None
    # diagnostics context, set by the view
    system_label: str = ""
    subsort_labels: dict[int, str] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """
        Create the model; the base class builds the tree at once.

        :param args: Positional arguments for PersonTreeModel.
        :param kwargs: Keyword arguments for PersonTreeModel.
        """
        # must exist before the base class builds the tree
        self._code_cache: dict[str, str] = {}  # group name -> group key
        self._members: dict[str, Counter] = {}  # group key -> Counter of names
        # person handle -> (group key, group name)
        self._handle_member: dict[PersonHandle, tuple[str, str]] = {}
        self._progress: ProgressMeter | None = None  # only once a build is slow
        self._progress_pct = 0
        self._build_count = 0
        self._build_total = 1
        self._build_start = 0.0
        self._phase_header = ""
        self._check_every = PROGRESS_CHECK_EVERY
        self._last_events = 0.0
        self._cancelled = False
        self._timing_active = False
        # parent node id -> (children list id, length, {nodeid: index})
        self._positions: dict[int, tuple[int, int, dict[int, int]]] = {}
        self._rebuild_count = 0  # diagnostics: 0 while the model is new
        # diagnostics: seconds per build step, and per subsort field
        self._tstat: defaultdict[str, float] = defaultdict(float)
        self._tfield: defaultdict[int, float] = defaultdict(float)
        PersonTreeModel.__init__(self, *args, **kwargs)

    def destroy(self) -> None:
        """
        Release the grouping data, then the model.
        """
        self._code_cache = {}
        self._members = {}
        self._handle_member = {}
        PersonTreeModel.destroy(self)

    def rebuild_data(self, *args: Any, **kwargs: Any) -> None:
        """
        Rebuild the tree; for Sample Surname, sort the group rows, and
        break subsort ties afterward.

        :param args: Positional arguments for the core rebuild_data().
        :param kwargs: Keyword arguments for the core rebuild_data().
        """
        self._members = {}
        self._handle_member = {}
        if not (self.db is not None and self.db.is_open()):
            PersonTreeModel.rebuild_data(self, *args, **kwargs)
            return
        timing = timing_on()
        serial = self._timing_start(timing)
        t_start = perf_counter()
        t_resort = t_ties = 0.0
        CONFIG.set("state.building", True)
        save_config()
        self._progress_begin()
        self._timing_active = timing
        try:
            PersonTreeModel.rebuild_data(self, *args, **kwargs)
            if self.group_sort == GROUP_BY_SURNAME:
                t_resort = perf_counter()
                self._resort_groups()
                t_resort = perf_counter() - t_resort
            t_ties = perf_counter()
            self._break_ties()
            t_ties = perf_counter() - t_ties
        finally:
            self._timing_active = False
            self._progress_end()
            CONFIG.set("state.building", False)
            if self._cancelled:
                CONFIG.set("subsort.suspended", True)
                _NOTICE[0] = _(
                    "Fuzzy Grouping: the index build was cancelled, so subsorting "
                    "is off. To turn it on again, use Configure, Subsorting tab."
                )
            save_config()
        self._timing_done(serial, perf_counter() - t_start, t_resort, t_ties, timing)
        self._rebuild_count += 1

    # ---------------------------------------------------------------
    # subsort
    #
    # Computing every subsort field for every person is slow (place and
    # family lookups), and almost always only the first one or two fields
    # decide the order. So a build sorts by the first field only, and
    # _break_ties() then computes the next field only for people whose
    # keys are still equal, one field at a time. A person added or edited
    # later gets the full key; it can land beside an untied person with
    # the same first field in the wrong order until the next build.
    # ---------------------------------------------------------------
    def subsort_active(self) -> bool:
        """
        Tell whether the subsort applies.

        :returns: ``True`` when the view is sorted by the Grouping column
            with a subsort.
        """
        return self.sort_col == 0 and bool(self.subsort) and bool(self.name_fmt_str)

    def _field_value(self, col: int, data: Any, name_data: Any = None) -> str:
        """
        One subsort field.

        :param col: A model column, or NAME_FORMAT_ROW.
        :param data: The person data.
        :param name_data: The primary name data, when already known.
        :returns: The field as text, without the separator.
        """
        timing = self._timing_active
        t_field = perf_counter() if timing else 0.0
        if col == NAME_FORMAT_ROW:
            if name_data is None:
                name_data = _primary_name(data)
            value = name_displayer.format_str_raw(name_data, self.name_fmt_str)
        else:
            value = self.smap[col](data)
        value = str(value or "").replace(SUBSORT_SEPARATOR, " ")
        if timing:
            self._tfield[col] += perf_counter() - t_field
        return value

    def subsort_key(self, data: Any, name_data: Any, depth: int | None = None) -> str:
        """
        The subsort key of a person. The tree collates it once, so the
        fields sort in order.

        :param data: The person data.
        :param name_data: The primary name data.
        :param depth: How many subsort fields to use; ``None`` for all.
        :returns: The subsort values, separated by a tab.
        """
        cols = self.subsort if depth is None else self.subsort[:depth]
        return SUBSORT_SEPARATOR.join(
            self._field_value(col, data, name_data) for col in cols
        )

    def _break_ties(self) -> None:
        """
        After a build: for people with equal sort keys in a group, add the
        next subsort field to their keys, until the keys differ or the
        fields run out. Then re-sort the children of those groups.
        """
        if (
            self._cancelled
            or len(self.subsort) < 2
            or not self.subsort_active()
            or CONFIG.get("subsort.suspended")
        ):
            return
        root = self.tree.get(None) if self.tree else None
        if root is None:
            return
        work = []
        tied = 0
        for _key, group_id in root.children:
            group = self.nodemap.node(group_id)
            runs = self._tie_runs(group)
            if runs:
                work.append((group, runs))
                tied += sum(len(run) for run in runs)
        self._tstat["tied"] = tied
        if not work:
            return
        self._progress_set_phase(_("Subsorting people with equal sort values"), tied)
        for group, runs in work:
            for run in runs:
                if not self._resolve_run(run):
                    break
            self._set_children(
                group,
                [(self.nodemap.node(nid).sortkey, nid) for _k, nid in group.children],
            )
            if self._cancelled:
                break
        self.clear_path_cache()

    def _tie_runs(self, group: Any) -> list[list[Any]]:
        """
        Find the child nodes of a group with equal sort keys.

        :param group: A group node.
        :returns: Lists of 2 or more child nodes with equal sort keys.
        """
        runs = []
        run: list[Any] = []
        last = None
        for sortkey, nodeid in group.children:
            node = self.nodemap.node(nodeid)
            if run and sortkey == last:
                run.append(node)
            else:
                if len(run) > 1:
                    runs.append(run)
                run = [node]
            last = sortkey
        if len(run) > 1:
            runs.append(run)
        return runs

    def _resolve_run(self, run: list[Any]) -> bool:
        """
        Extend the keys of one run of tied nodes field by field.

        :param run: Nodes with equal sort keys.
        :returns: ``False`` when the user cancelled.
        """
        data_cache: dict[PersonHandle, Any] = {}
        stack = [(run, 1)]
        while stack:
            nodes, depth = stack.pop()
            if depth >= len(self.subsort):
                continue
            col = self.subsort[depth]
            for node in nodes:
                data = data_cache.get(node.handle)
                if data is None:
                    data = data_cache[node.handle] = self.map(node.handle)
                value = self._field_value(col, data) if data else ""
                node.name = (node.name or "") + SUBSORT_SEPARATOR + value
                node.sortkey = glocale.sort_key(node.name)
                if self._progress_tick():
                    return False
            by_key: dict[Any, list[Any]] = {}
            for node in nodes:
                by_key.setdefault(node.sortkey, []).append(node)
            stack.extend((sub, depth + 1) for sub in by_key.values() if len(sub) > 1)
        return True

    # ---------------------------------------------------------------
    # fast row paths
    #
    # The core do_get_path() finds a row's position by walking back
    # through its siblings until it meets one whose path is in a small
    # LRU cache (BaseModel._CACHE_SIZE). Expand all asks for the path of
    # every group; the children of each big group push the previous group
    # out of the cache, so each group walks back to the first one. With
    # thousands of groups that is quadratic: 40 s for 61,052 people in
    # 8,654 groups. Here a row's position comes from a dict per parent,
    # built once and dropped whenever the core drops its path cache.
    # ---------------------------------------------------------------
    def _position(self, parent: Any, nodeid: int) -> int | None:
        """
        The position of a node among the children of its parent.

        :param parent: The parent node.
        :param nodeid: The node id.
        :returns: The position (reversed for a descending sort), or
            ``None`` when the node is not a child of the parent.
        """
        entry = self._positions.get(id(parent))
        children = parent.children
        if entry is None or entry[0] != id(children) or entry[1] != len(children):
            entry = (
                id(children),
                len(children),
                {child_id: i for i, (_key, child_id) in enumerate(children)},
            )
            self._positions[id(parent)] = entry
        index = entry[2].get(nodeid)
        # pylint: disable-next=no-member
        if index is not None and self._TreeBaseModel__reverse:  # type: ignore
            index = len(children) - 1 - index
        return index

    # pylint: disable-next=redefined-builtin
    def do_get_path(self, iter: Gtk.TreeIter) -> Gtk.TreePath:
        """
        Gtk.TreeModel vfunc: the path of a row, from the position dicts.

        :param iter: The row iter.
        :returns: The row path.
        """
        # PyGObject installs this vfunc where core tree models also reach
        # it: in the Grouped People view it is called with a core
        # PersonTreeModel. Hand those straight to the core method.
        if not isinstance(self, FuzzyGroupingTreeModel):
            return TreeBaseModel.do_get_path(self, iter)
        try:
            node = self.nodemap.node(iter.user_data)
            parent = self.nodemap.node(node.parent) if node.parent else None
            if parent is None:
                return TreeBaseModel.do_get_path(self, iter)
            indexes = []
            while parent is not None:
                index = self._position(parent, id(node))
                if index is None:
                    return TreeBaseModel.do_get_path(self, iter)
                indexes.append(index)
                node = parent
                parent = self.nodemap.node(node.parent) if node.parent else None
            # the root node (parent None) holds the groups: stop there
            return Gtk.TreePath(tuple(reversed(indexes)))
        except Exception:  # pylint: disable=broad-except
            return TreeBaseModel.do_get_path(self, iter)

    def clear_path_cache(self) -> None:
        """
        Drop the position dicts with the core path cache.
        """
        self._positions = {}
        PersonTreeModel.clear_path_cache(self)

    def clear_cache(self, handle: PersonHandle | None = None) -> None:
        """
        Drop the position dicts with the core caches.

        :param handle: The person whose cached data is dropped, or
            ``None`` for all.
        """
        self._positions = {}
        PersonTreeModel.clear_cache(self, handle)

    def _set_children(self, parent: Any, entries: list[tuple[Any, int]]) -> None:
        """
        Sort the children of a parent node and relink them.

        :param parent: The parent node.
        :param entries: (sortkey, nodeid) pairs of its children.
        """
        entries.sort()
        parent.children = entries
        prev_id = None
        for _sortkey, nodeid in entries:
            node = self.nodemap.node(nodeid)
            node.prev = prev_id
            node.next = None
            if prev_id is not None:
                self.nodemap.node(prev_id).next = nodeid
            prev_id = nodeid

    # ---------------------------------------------------------------
    # diagnostics: index build timing
    # ---------------------------------------------------------------
    def _subsort_label(self, col: int) -> str:
        """
        The label of a subsort field for the timing log.

        :param col: A model column, or NAME_FORMAT_ROW.
        :returns: The column label.
        """
        if col == NAME_FORMAT_ROW:
            return _("Name format")
        return self.subsort_labels.get(col, str(col))

    def _timing_start(self, timing: bool) -> int:
        """
        Count a build and, with the timing log on, log its START block.

        :param timing: ``True`` when the timing log is on.
        :returns: The build serial number.
        """
        _TIMING["serial"] += 1
        serial = _TIMING["serial"]
        self._tstat = defaultdict(float)
        self._tfield = defaultdict(float)
        if not timing:
            return serial
        trigger, chain = _timing_trigger()
        try:
            people = self.db.get_number_of_people()
        except Exception:  # pylint: disable=broad-except
            people = "?"
        since = ""
        if _TIMING["last_end"] is not None:
            elapsed = _secs(perf_counter() - _TIMING["last_end"])
            since = f", {elapsed} after the end of the previous build"
        subsort = [self._subsort_label(col) for col in self.subsort]
        if CONFIG.get("subsort.suspended"):
            subsort = subsort[:1] + ["(rest suspended)"]
        model_kind = (
            "new model" if self._rebuild_count == 0 else "re-filter of the model"
        )
        subsort_text = (
            ", ".join(subsort) if self.subsort_active() else "off (core sort)"
        )
        timing_print(f"#{serial} START {trigger}{since}")
        timing_print(
            f"#{serial}   {model_kind}, {people} people in tree, "
            f"{timing_filter_text(self.current_filter)}"
        )
        timing_print(
            f"#{serial}   system {self.system_label or '?'}, groups by "
            f"{self.group_sort}, sort column {self.sort_col}, subsort {subsort_text}"
        )
        timing_print(f"#{serial}   call chain: {chain}")
        return serial

    # pylint: disable-next=too-many-arguments,too-many-positional-arguments
    def _timing_done(
        self, serial: int, total: float, t_resort: float, t_ties: float, timing: bool
    ) -> None:
        """
        With the timing log on, log the DONE lines of a build.

        :param serial: The build serial number.
        :param total: The whole build time, in seconds.
        :param t_resort: The group resort time, in seconds.
        :param t_ties: The tie-break time, in seconds.
        :param timing: ``True`` when the timing log is on.
        """
        _TIMING["last_end"] = perf_counter()
        if not timing:
            return
        root = self.tree.get(None) if self.tree else None
        groups = len(root.children) if root is not None else 0
        stat = self._tstat
        rate = int(self._build_count / total) if total > 0 else "?"
        timing_print(
            f"#{serial} DONE  {_secs(total)}, {groups} groups, {self.displayed()} "
            f"people shown of {self.total()} ({rate} rows/s)"
        )
        cancelled = " (CANCELLED)" if self._cancelled else ""
        timing_print(
            f"#{serial}   database + filter "
            f"{_secs(total - stat['add_row'] - t_resort - t_ties)} | add_row "
            f"{_secs(stat['add_row'])} = group name {_secs(stat['group_name'])}, "
            f"phonetic code {_secs(stat['group_key'])} "
            f"({len(self._code_cache)} distinct names), sort key "
            f"{_secs(stat['sort_key'])}, tree nodes {_secs(stat['add_node'])}, "
            f"progress dialog {_secs(stat['progress'])} | group resort "
            f"{_secs(t_resort)} | tie-break {_secs(t_ties)} for {int(stat['tied'])} "
            f"tied people{cancelled}"
        )
        if self._tfield:
            fields = ", ".join(
                f"{self._subsort_label(col)} {_secs(secs)}"
                for col, secs in sorted(
                    self._tfield.items(), key=lambda item: item[1], reverse=True
                )
            )
            timing_print(f"#{serial}   subsort fields, slowest first: {fields}")

    # ---------------------------------------------------------------
    # progress dialog for a slow index build
    # ---------------------------------------------------------------
    def _progress_begin(self) -> None:
        """
        Reset the progress counters for a new build.
        """
        self._progress = None
        self._progress_pct = 0
        self._build_count = 0
        self._build_start = perf_counter()
        self._cancelled = False
        self._phase_header = _("Grouping people")
        self._check_every = PROGRESS_CHECK_EVERY
        try:
            self._build_total = max(1, self.number_items())
        except Exception:  # pylint: disable=broad-except
            self._build_total = 1  # no open database

    def _progress_set_phase(self, header: str, total: int) -> None:
        """
        Start counting a new phase of the build (same dialog).

        :param header: The phase text shown in the dialog.
        :param total: The number of steps of the phase.
        """
        self._phase_header = header
        self._build_count = 0
        self._build_total = max(1, total)
        self._progress_pct = 0
        self._check_every = 16  # few, slow steps: check the time more often
        if self._progress is not None:
            self._progress.set_pass(header, 100)

    def _progress_tick(self) -> bool:
        """
        Count one step. After PROGRESS_DELAY seconds, open a progress
        dialog with a Cancel button; it is advanced in whole percents (at
        most 100 updates per phase), because every ProgressMeter step also
        runs pending GTK events.

        A cancel does not stop the first phase (the core database loop
        cannot be left safely, and it is fast); it stops the subsort phase,
        and turns subsorting off until the user turns it on again.

        :returns: ``True`` once the user cancelled.
        """
        self._build_count += 1
        if self._progress is None:
            if self._build_count % self._check_every:
                return False
            if perf_counter() - self._build_start < PROGRESS_DELAY:
                return False
            self._progress = ProgressMeter(
                _("Fuzzy Grouping"),
                can_cancel=True,
                parent=self.uistate.window if self.uistate else None,
            )
            self._progress.set_pass(self._phase_header, 100)
            self._last_events = perf_counter()
        percent = min(99, self._build_count * 100 // self._build_total)
        if self._progress_pct < percent:
            while self._progress_pct < percent:
                if self._progress.step():
                    self._cancelled = True
                self._progress_pct += 1
            self._last_events = perf_counter()
        elif perf_counter() - self._last_events > EVENTS_EVERY:
            # a slow phase: keep the Cancel button responsive
            while Gtk.events_pending():
                Gtk.main_iteration()
            self._last_events = perf_counter()
            if self._progress.get_cancelled():
                self._cancelled = True
        return self._cancelled

    def _progress_end(self) -> None:
        """
        Close the progress dialog, if it was opened.
        """
        if self._progress is not None:
            self._progress.close()
            self._progress = None

    # ---------------------------------------------------------------
    # grouping
    # ---------------------------------------------------------------
    def group_key(self, group_name: str) -> str:
        """
        The phonetic code for a group name.

        :param group_name: The core group name of a person.
        :returns: The code, or ``""`` for no surname.
        """
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

    def _spellings(self, key: str) -> list[str]:
        """
        The spellings in a group, most used first; ties between equally
        used spellings in locale collation order.

        :param key: The group key.
        :returns: The spellings.
        """
        counter = self._members.get(key) or Counter()
        ranked = sorted(counter.items(), key=lambda i: (-i[1], glocale.sort_key(i[0])))
        return [name for name, _count in ranked]

    def sample_surname(self, key: str) -> str:
        """
        The most used spelling in a group (ties: locale order).

        :param key: The group key.
        :returns: The spelling, or ``""`` for an empty group.
        """
        spellings = self._spellings(key)
        return spellings[0] if spellings else ""

    # the t_* locals time each step for the diagnostics log
    # pylint: disable-next=too-many-locals
    def add_row(self, handle: PersonHandle, data: Any) -> None:
        """
        Add nodes to the node map for a single person.

        :param handle: The handle of the person.
        :param data: The person data.
        """
        timing = self._timing_active and self._in_build
        stat = self._tstat
        t_0 = perf_counter() if timing else 0.0
        if self._in_build:
            self._progress_tick()
        if timing:
            t_1 = perf_counter()
            stat["progress"] += t_1 - t_0
        name_data = _primary_name(data)
        group_name = name_displayer.name_grouping_data(self.db, name_data)
        if timing:
            t_2 = perf_counter()
            stat["group_name"] += t_2 - t_1
        key = self.group_key(group_name)
        if timing:
            t_3 = perf_counter()
            stat["group_key"] += t_3 - t_2
        self._members.setdefault(key, Counter())[group_name] += 1
        self._handle_member[handle] = (key, group_name)

        if self.subsort_active():
            # a build (or a suspended subsort) uses the first field only;
            # _break_ties() adds the next fields where they are needed
            lazy = self._in_build or CONFIG.get("subsort.suspended")
            sort_key = self.subsort_key(data, name_data, 1 if lazy else None)
        else:  # the user sorted on another column: core behavior
            sort_key = self.sort_func(data)
        if timing:
            t_4 = perf_counter()
            stat["sort_key"] += t_4 - t_3

        if key not in self.tree:
            # group row; for Sample Surname it is re-sorted after a build
            if self.group_sort == GROUP_BY_SURNAME:
                group_sort_text = group_name or key
            else:
                group_sort_text = key
            self.add_node(None, key, group_sort_text, None, add_parent=False)
        self.add_node(key, handle, sort_key, handle)
        if timing:
            t_5 = perf_counter()
            stat["add_node"] += t_5 - t_4
            stat["add_row"] += t_5 - t_0

    def _resort_groups(self) -> None:
        """
        After a full build, order the group rows by their sample surname.
        """
        root = self.tree.get(None) if self.tree else None
        if root is None or not root.children:
            return
        entries = []
        for _oldkey, nodeid in root.children:
            node = self.nodemap.node(nodeid)
            node.sortkey = glocale.sort_key(self.sample_surname(node.ref))
            entries.append((node.sortkey, nodeid))
        self._set_children(root, entries)
        self.clear_path_cache()

    def delete_row_by_handle(self, handle: PersonHandle) -> None:
        """
        Delete a person row, and forget the spelling it added to its group.

        :param handle: The handle of the person.
        """
        member = self._handle_member.pop(handle, None)
        if member:
            key, group_name = member
            counter = self._members.get(key)
            if counter:
                counter[group_name] -= 1
                if counter[group_name] <= 0:
                    del counter[group_name]
        PersonTreeModel.delete_row_by_handle(self, handle)

    def column_header(self, node: Any) -> str:
        """
        The group row text: the spellings in the group, then the code.

        :param node: A group node.
        :returns: The group row text.
        """
        key = node.ref
        if not key or self.encode is _exact_codes:
            # no surname, or no phonetic matching: the plain group name,
            # exactly as in the Grouped People view
            return PersonTreeModel.column_header(self, node)
        names = self._spellings(key)
        text = ", ".join(names[:MAX_HEADER_NAMES])
        if len(names) > MAX_HEADER_NAMES:
            text += f" +{len(names) - MAX_HEADER_NAMES}"
        return f"{text} [{key}]"


# ------------------------------------------------------------
#
# SortNameFormat
#
# ------------------------------------------------------------
# pylint: disable-next=too-many-instance-attributes
class SortNameFormat(GrampsPreferences):
    """
    Name format chooser for sorting only.

    Borrows the Preferences name format model and the Display Name Editor
    plumbing from GrampsPreferences without opening Preferences. Selecting
    a format here never changes the application Name format preference.
    """

    # pylint: disable-next=super-init-not-called
    def __init__(self, view: FuzzyGroupingView, configdialog: ConfigureDialog) -> None:
        """
        Build the chooser combo and its edit button.

        :param view: The Fuzzy Grouping view.
        :param configdialog: The view Configure dialog.
        """
        self.view = view
        self.uistate = view.uistate
        self.dbstate = view.dbstate
        # The view Configure dialog is a leaf in the window manager tree
        # (no submenu), so the editor cannot be its child: open top level.
        self.track: list[Any] = []
        self.window = configdialog.window  # parent for editor error dialogs
        self.selected_fmt: tuple[Any, ...] = ()
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

        self.edit_button = Gtk.Button.new_from_icon_name(
            "gtk-edit", Gtk.IconSize.BUTTON
        )
        self.edit_button.set_tooltip_text(_("Display Name Editor"))
        self.edit_button.connect("clicked", self.cb_name_dialog)

    @staticmethod
    def _example_name() -> Name:
        """
        The same example name the Preferences dialog uses.

        :returns: The example Name.
        """
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

    def cb_name_dialog(self, _button: Gtk.Button) -> None:
        """
        The gtk-edit button: open the Display Name Editor.

        Only one Display Name Editor can exist (its window id is the class
        itself), whether it was opened here or from Preferences. When one
        is already open, ManagedWindow presents it and raises
        WindowActiveError, so there is nothing more to do.

        :param _button: The edit button.
        """
        try:
            DisplayNameEditor(self.uistate, self.dbstate, self.track, self)
        except WindowActiveError:
            pass

    def refill_combo(self, select_num: int) -> None:
        """
        Rebuild the combo list (Default row + current formats) without
        emitting the combo "changed" callback.

        :param select_num: The format number to select; the Default row is
            selected if it no longer exists.
        """
        # row 0 follows the Display name format of the Preferences,
        # without its surname parts, and is labeled with that cleaned format
        fmt = default_sort_format()
        example = name_displayer.format_str(self.examplename, fmt)
        self.sort_combo.handler_block(self.changed_id)
        self.combo_model.clear()
        self.combo_model.append([0, format_label(fmt), fmt, example])
        active = 0
        for index, row in enumerate(self.fmt_model, start=1):
            self.combo_model.append(list(row))
            if row[COL_NUM] == select_num:
                active = index
        self.sort_combo.set_active(active)
        self.sort_combo.handler_unblock(self.changed_id)

    def name_changed_check(self) -> None:
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

    def cb_name_changed(self, obj: Gtk.ComboBox) -> None:
        """
        The combo changed: set the sort-only format (NOT the
        preferences.name-format setting).

        :param obj: The name format combo.
        """
        row_iter = obj.get_active_iter()
        if row_iter is None:
            return
        self.view.set_sort_name_format(self.combo_model.get_value(row_iter, COL_NUM))


# ------------------------------------------------------------
#
# FuzzyGroupingView
#
# ------------------------------------------------------------
# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class FuzzyGroupingView(BasePersonView):
    """
    A hierarchical view of the people, grouped by phonetically similar
    family names.
    """

    # the first (fixed) column shows the groups
    COLUMNS = [(_("Grouping"),) + tuple(BasePersonView.COLUMNS[0][1:])] + list(
        BasePersonView.COLUMNS[1:]
    )

    def __init__(
        self,
        pdata: PluginData,
        dbstate: Any,
        uistate: DisplayState,
        nav_group: int = 0,
    ) -> None:
        """
        Create the view.

        :param pdata: The plugin data of this view.
        :param dbstate: The Gramps database state.
        :param uistate: The Gramps display state.
        :param nav_group: The navigation group.
        """
        self.encoders = discover_encoders()
        self.system_id = CONFIG.get("grouping.system")
        if self.system_id not in self.encoders:
            # stored system was uninstalled: fall back to Soundex
            self.system_id = DEFAULT_SYSTEM
        self.subsort_store: Gtk.ListStore | None = None
        self._subsort_filling = False
        self._subsort_check: Gtk.CheckButton | None = None
        self._subsort_check_filling = False
        self._subsort_sizes: Gtk.SizeGroup | None = None
        self._system_combo: Gtk.ComboBoxText | None = None
        self._system_changed_id = 0
        self._columns_buttons: Gtk.Widget | None = None
        self._refresh_timer: int | None = None  # pending delayed refresh
        self._help_tooltip_text = ""
        self.toolbar_ui: list[str] | None = None
        self.popup_ui: list[str] | None = None
        # a new icon theme restyles the Help icon too
        Gtk.IconTheme.get_default().connect("changed", self.cb_icon_theme_changed)
        self._system_listeners: list[Any] = []  # weakrefs, see connect_phonetic_system

        BasePersonView.__init__(
            self,
            pdata,
            dbstate,
            uistate,
            _("Fuzzy Grouping"),
            FuzzyGroupingTreeModel,
            nav_group=nav_group,
        )
        timing_track_pages(uistate)  # diagnostics: which view came before
        # encoder plugins hidden or shown in the Plugin Manager: update the
        # system lists at once (the Plugin Manager sets this key after its
        # own hidden set, so discover_encoders() already sees the change)
        global_config.connect("plugin.hiddenplugins", self.cb_hidden_plugins_changed)
        # kept as one list object so a system change can update it in place
        self.toolbar_ui = self._build_toolbar_ui()
        self.additional_uis.append(self.toolbar_ui)
        # replaces the empty "PopUpTree" section of the person view popup
        self.popup_ui = self._build_popup_ui()
        self.additional_uis.append(self.popup_ui)

    def get_default_gramplets(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """
        Default sidebar: Flat Filter first and Fuzzy Matching second, each
        only if registered and not hidden in the Plugin Manager, then any
        other core sidebar default, with the core Person Filter last. The
        bottom bar keeps the core Person view defaults.

        :returns: (sidebar gramplet ids, bottom bar gramplet ids).
        """
        core_sidebar, bottombar = BasePersonView.get_default_gramplets(self)
        # GuiPluginManager.get_reg_gramplets() leaves out hidden gramplets
        available = {
            pdata.id for pdata in GuiPluginManager.get_instance().get_reg_gramplets()
        }
        sidebar = [
            gramplet_id
            for gramplet_id in (SIDEBAR_FLAT_FILTER, SIDEBAR_FUZZY_MATCHING)
            if gramplet_id in available
        ]
        sidebar += [
            gramplet_id
            for gramplet_id in core_sidebar
            if gramplet_id not in sidebar and gramplet_id != SIDEBAR_PERSON_FILTER
        ]
        sidebar.append(SIDEBAR_PERSON_FILTER)
        return tuple(sidebar), bottombar

    def build_interface(self) -> Gtk.Widget:
        """
        Build the view, and make the sidebar "Restore default gramplets"
        use the defaults as they are when it is chosen: the gramplet bar
        keeps the list it was given when the view was first shown, and a
        gramplet may have been installed, hidden or shown since then.

        :returns: The view widget.
        """
        widget = BasePersonView.build_interface(self)
        sidebar = self.sidebar
        core_restore = sidebar.restore

        def restore() -> None:
            """
            Restore the sidebar defaults as they are now.
            """
            sidebar.defaults = self.get_default_gramplets()[0]
            core_restore()

        # GrampletBar looks up self.restore when the menu item is chosen
        sidebar.restore = restore
        return widget

    def get_viewtype_stock(self) -> str:
        """
        Override the default icon. Set for hierarchical view.

        :returns: The view icon name.
        """
        return ICON_NAME

    # ---------------------------------------------------------------
    # settings -> model
    # ---------------------------------------------------------------
    def subsort_order(self) -> list[int]:
        """
        The subsort order.

        :returns: The stored order, or the initial one if it is missing
            or stale.
        """
        rank = self._config.get("columns.rank") if self._config else []
        rank = [col for col in rank if col != BasePersonView.COL_NAME]
        if not rank:
            rank = list(range(1, len(self.COLUMNS)))
        required = {NAME_FORMAT_ROW} | set(range(1, len(self.COLUMNS)))
        stored = list(CONFIG.get("subsort.order") or [])
        if len(stored) == len(required) and set(stored) == required:
            return stored
        return INITIAL_SUBSORT_HEAD + [c for c in rank if c not in INITIAL_SUBSORT_HEAD]

    def _push_settings_to_model(self) -> None:
        """
        Copy the settings to the model class before a build.
        """
        model = FuzzyGroupingTreeModel
        model.encode = staticmethod(self.encoders[self.system_id][1])  # type: ignore
        model.group_sort = CONFIG.get("grouping.sort")
        model.subsort = self.subsort_order()
        model.name_fmt_str = name_format_string(CONFIG.get("subsort.name_format"))
        # diagnostics context
        model.system_label = f"{self.encoders[self.system_id][0]} ({self.system_id})"
        model.subsort_labels = {
            col: self.COLUMNS[col][0] for col in range(len(self.COLUMNS))
        }

    def build_tree(self, *args: Any, **kwargs: Any) -> None:
        """
        Build the tree with the current settings, then open every group
        of a small result.

        :param args: Positional arguments for the core build_tree().
        :param kwargs: Keyword arguments for the core build_tree().
        """
        self._cancel_refresh()  # this build covers any pending change
        if not self.active:
            if timing_on():
                trigger, chain = _timing_trigger()
                timing_print(f"build deferred (view not shown): {trigger} | {chain}")
            BasePersonView.build_tree(self, *args, **kwargs)  # only marks dirty
            return
        t_view = perf_counter()
        serial = _TIMING["serial"]
        self._push_settings_to_model()
        BasePersonView.build_tree(self, *args, **kwargs)
        t_expand = perf_counter()
        self._auto_expand()
        self._show_notice()
        if timing_on() and _TIMING["serial"] != serial:  # an index was built
            timing_print(
                f"#{_TIMING['serial']}   whole view refresh "
                f"{_secs(perf_counter() - t_view)} "
                f"(auto-expand {_secs(perf_counter() - t_expand)})"
            )

    def _expand_order(self, count: int) -> tuple[list[int], int | None]:
        """
        The order in which Expand all opens the groups: the groups on
        screen first, then the ones below, then the ones above.

        :param count: The number of groups.
        :returns: (group indexes in order, the index of the group at the
            top of the view, or ``None`` when nothing is shown).
        """
        visible = self.list.get_visible_range()
        if not visible:
            return list(range(count)), None
        first = visible[0].get_indices()[0]
        last = visible[1].get_indices()[0]
        order = (
            list(range(first, min(last + 1, count)))
            + list(range(last + 1, count))
            + list(range(0, first))
        )
        return order, first

    def open_all_nodes(self, *_obj: Any) -> None:
        """
        Expand all Nodes, one group at a time instead of the single
        Gtk.TreeView.expand_all() call of the core, so that a progress
        dialog with a Cancel button can appear after EXPAND_PROGRESS_DELAY
        seconds and keep the window responding. Afterward, the group that
        was at the top of the view is scrolled back to the top.

        :param _obj: Action arguments (not used).
        """
        model = self.model
        if model is None:
            return
        t_open = perf_counter()
        count = model.iter_n_children(None)
        order, top = self._expand_order(count)
        self.uistate.status_text(_("Updating display..."))
        self.uistate.set_busy_cursor(True)
        progress = None
        percent = 0
        opened = 0
        cancelled = False
        try:
            for opened, index in enumerate(order, start=1):
                if self.model is not model:  # rebuilt while events ran
                    break
                self.list.expand_row(Gtk.TreePath.new_from_indices([index]), False)
                if progress is None:
                    if perf_counter() - t_open < EXPAND_PROGRESS_DELAY:
                        continue
                    progress = ProgressMeter(
                        _("Fuzzy Grouping"),
                        can_cancel=True,
                        parent=self.uistate.window,
                    )
                    progress.set_pass(_("Opening the groups"), 100)
                target = opened * 100 // max(1, count)
                while percent < target:
                    if progress.step():  # also runs pending GTK events
                        cancelled = True
                    percent += 1
                if cancelled:
                    break
        finally:
            if progress is not None:
                progress.close()
            if top is not None and self.model is model and top < count:
                self.list.scroll_to_cell(
                    Gtk.TreePath.new_from_indices([top]), None, True, 0.0, 0.0
                )
            self.uistate.set_busy_cursor(False)
            self.uistate.modify_statusbar(self.dbstate)
        timing_print(
            f"Expand all Nodes took {_secs(perf_counter() - t_open)}, {opened} of "
            f"{count} groups opened{' (CANCELLED)' if cancelled else ''}"
        )

    def _show_notice(self) -> None:
        """
        After a build that turned subsorting off (cancel, or an unfinished
        build in the last session): say so in the statusbar, and update the
        Subsorting tab if Configure is open.
        """
        text = _NOTICE[0]
        if not text:
            return
        _NOTICE[0] = None
        timing_print(text)
        self.uistate.push_message(self.dbstate, text)
        if self._subsort_check is not None:
            self._subsort_check_filling = True
            self._subsort_check.set_active(not CONFIG.get("subsort.suspended"))
            self._subsort_check_filling = False

    def _auto_expand(self) -> None:
        """
        With fewer than AUTO_EXPAND_LIMIT people shown (a small tree, or a
        filter or search with few results), open every group, so nobody
        is hidden behind a closed group row.
        """
        model = getattr(self, "model", None)
        if model is None or not self.active:
            return
        try:
            shown = model.displayed()  # person rows, not group rows
        except Exception:  # pylint: disable=broad-except
            return
        if 0 < shown < AUTO_EXPAND_LIMIT:
            self.open_all_nodes()

    def _rebuild(self) -> None:
        """
        Force a new model (not just a re-filter of the old one) now.
        """
        self._cancel_refresh()
        self.dirty = True
        self.build_tree()

    def _schedule_refresh(self) -> None:
        """
        Refresh the view REFRESH_DELAY seconds after the last Configure
        change, so several quick changes cost one rebuild.
        """
        self._cancel_refresh()
        self._refresh_timer = GLib.timeout_add_seconds(
            REFRESH_DELAY, self.cb_refresh_timer
        )

    def _cancel_refresh(self) -> None:
        """
        Cancel a pending delayed refresh.
        """
        if self._refresh_timer is not None:
            GLib.source_remove(self._refresh_timer)
            self._refresh_timer = None

    def cb_refresh_timer(self) -> bool:
        """
        GLib timeout: the delayed refresh.

        :returns: ``False``, to run once.
        """
        self._refresh_timer = None
        self._rebuild()
        return False

    def cb_configure_closed(self, *_args: Any) -> None:
        """
        Configure closed: apply a pending change at once.

        :param _args: Signal arguments (not used).
        """
        if self._refresh_timer is not None:
            self._rebuild()

    # ---------------------------------------------------------------
    # page change; first use: show Configure when there is no .ini yet
    # ---------------------------------------------------------------
    def change_page(self) -> None:
        """
        The view is shown: pick up plugin and README changes, and open
        Configure on first use.
        """
        BasePersonView.change_page(self)
        # encoder plugins may have been hidden or shown since the last visit
        self._refresh_encoders()
        self._sync_system_action()
        # README / Markdown Dash may have changed since the toolbar was
        # built. The toolbar is rebuilt from XML at every update_menu(), so
        # the tooltip must change in the XML, not on the current widget.
        if help_tooltip() != self._help_tooltip_text:
            self._refresh_toolbar_ui()
        if _FIRST_RUN[0]:
            _FIRST_RUN[0] = False
            GLib.idle_add(self.cb_first_run_configure)

    def _refresh_encoders(self) -> None:
        """
        Re-discover the encoders. When the set changed, refill the system
        lists; when the current system is gone, regroup with Soundex. The
        stored choice in the .ini is kept, so showing the plugin again
        brings it back on the next visit to the view.
        """
        encoders = discover_encoders()
        wanted = CONFIG.get("grouping.system")
        if list(encoders) == list(self.encoders) and (
            self.system_id == wanted or wanted not in encoders
        ):
            return
        changed_list = list(encoders) != list(self.encoders)
        self.encoders = encoders
        old_system = self.system_id
        self.system_id = wanted if wanted in encoders else DEFAULT_SYSTEM

        self._fill_system_combo()
        if changed_list:
            self._refresh_popup_ui()
        self._sync_system_action()
        if self.system_id != old_system:
            self._notify_system_listeners()
            self._rebuild()

    def cb_hidden_plugins_changed(self, *_args: Any) -> None:
        """
        The hidden plugins setting changed: re-discover the encoders when
        GTK is idle.

        :param _args: Signal arguments (not used).
        """
        GLib.idle_add(self.cb_idle_refresh_encoders)

    def cb_idle_refresh_encoders(self) -> bool:
        """
        GLib idle callback: re-discover the encoders.

        :returns: ``False``, to run once.
        """
        self._refresh_encoders()
        return False

    def cb_first_run_configure(self) -> bool:
        """
        GLib idle callback: open Configure on first use.

        :returns: ``False``, to run once.
        """
        save_config()  # the dialog has been offered once; do not repeat
        self.configure()
        return False

    # ---------------------------------------------------------------
    # Configure dialog
    # ---------------------------------------------------------------
    def _get_configure_page_funcs(self) -> list[Callable[..., Any]]:
        """
        The Configure tabs: the core Columns tab with the Grouping choice,
        then the Subsorting tab, then the other core tabs.

        :returns: The page builder functions.
        """
        base_funcs = BasePersonView._get_configure_page_funcs(self)
        base_columnpage, others = base_funcs[0], base_funcs[1:]

        def columnpage(configdialog: ConfigureDialog) -> tuple[str, Gtk.Widget]:
            """
            The Columns tab, with the Grouping choice.

            :param configdialog: The Configure dialog.
            :returns: (tab title, tab widget).
            """
            title, widget = base_columnpage(configdialog)
            # the Subsorting tab sizes its table like this tab's table
            apply_button = getattr(widget, "apply_button", None)
            self._columns_buttons = apply_button.get_parent() if apply_button else None
            self._insert_grouping_choice(widget)
            configdialog.window.connect("destroy", self.cb_configure_closed)
            return title, widget

        def subsortpage(configdialog: ConfigureDialog) -> tuple[str, Gtk.Widget]:
            """
            The Subsorting tab.

            :param configdialog: The Configure dialog.
            :returns: (tab title, tab widget).
            """
            return _("Subsorting"), self._build_subsort_page(configdialog)

        return [columnpage, subsortpage] + list(others)

    def _insert_grouping_choice(self, column_order: Gtk.Box) -> None:
        """
        Replace the "first column cannot be changed" label with the group
        ordering radio buttons and, below them, the phonetic system list.

        :param column_order: The core Columns tab widget.
        """
        grouping = Gtk.Box(spacing=12)
        grouping.set_halign(Gtk.Align.CENTER)
        grouping.pack_start(Gtk.Label(label=_("Grouping:")), False, False, 0)
        by_surname = Gtk.RadioButton.new_with_label(None, _("Sample Surname"))
        by_id = Gtk.RadioButton.new_with_label_from_widget(
            by_surname, _("Fuzzy grouping ID")
        )
        if CONFIG.get("grouping.sort") == GROUP_BY_ID:
            by_id.set_active(True)
        by_surname.connect("toggled", self.cb_grouping_toggled, GROUP_BY_SURNAME)
        by_id.connect("toggled", self.cb_grouping_toggled, GROUP_BY_ID)
        grouping.pack_start(by_surname, False, False, 0)
        grouping.pack_start(by_id, False, False, 0)

        system = Gtk.Box(spacing=6)
        system.set_halign(Gtk.Align.CENTER)
        system.pack_start(
            Gtk.Label(label=_("Fuzzy (Phonetic encoding) system:")), False, False, 0
        )
        combo = Gtk.ComboBoxText()
        combo.set_tooltip_text(
            _("The phonetic system used to group people; None groups on exact surnames")
        )
        self._system_changed_id = combo.connect("changed", self.cb_system_combo_changed)
        combo.connect("destroy", self.cb_system_combo_destroyed)
        self._system_combo = combo
        self._fill_system_combo()
        system.pack_start(combo, False, False, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.pack_start(grouping, False, False, 0)
        box.pack_start(system, False, False, 0)
        box.show_all()

        # the core label text, so that the translated label is found too
        header = (
            _('Tree View: first column "%s" cannot be changed') % self.COLUMNS[0][0]
        )
        position = 0
        for index, child in enumerate(column_order.get_children()):
            if isinstance(child, Gtk.Label) and child.get_text() == header:
                position = index
                column_order.remove(child)
                break
        column_order.pack_start(box, False, False, 0)
        column_order.reorder_child(box, position)

    def _fill_system_combo(self) -> None:
        """
        (Re)fill the phonetic system list in Configure, if it is open, and
        select the current system, without running its "changed" handler.
        """
        combo = self._system_combo
        if combo is None:
            return
        combo.handler_block(self._system_changed_id)
        combo.remove_all()
        for system_id, (label, _encode) in self.encoders.items():
            combo.append(system_id, label)
        combo.set_active_id(self.system_id)
        combo.handler_unblock(self._system_changed_id)

    def cb_system_combo_destroyed(self, *_args: Any) -> None:
        """
        The phonetic system list was destroyed with Configure.

        :param _args: Signal arguments (not used).
        """
        self._system_combo = None

    def cb_system_combo_changed(self, combo: Gtk.ComboBoxText) -> None:
        """
        A phonetic system was chosen in Configure: regroup after the delay.

        :param combo: The phonetic system list.
        """
        system_id = combo.get_active_id()
        if system_id:
            self.set_phonetic_system(system_id, delayed=True)

    def cb_grouping_toggled(self, button: Gtk.RadioButton, value: str) -> None:
        """
        A Grouping radio button was chosen: save it, and refresh after the
        delay.

        :param button: The radio button.
        :param value: GROUP_BY_SURNAME or GROUP_BY_ID.
        """
        if not button.get_active() or CONFIG.get("grouping.sort") == value:
            return
        CONFIG.set("grouping.sort", value)
        save_config()
        self._schedule_refresh()

    def _build_subsort_page(self, configdialog: ConfigureDialog) -> Gtk.Box:
        """
        Build the Subsorting tab, laid out like the core Columns tab
        (gramps/gui/columnorder.py): centered lines separated by blank
        labels, then the table.

        :param configdialog: The Configure dialog.
        :returns: The tab widget.
        """
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.pack_start(Gtk.Label(label=" "), False, False, 0)

        chooser = SortNameFormat(self, configdialog)
        row = Gtk.Box(spacing=6)
        row.set_halign(Gtk.Align.CENTER)
        row.pack_start(Gtk.Label(label=_("%s: ") % _("Name format")), False, False, 0)
        row.pack_start(chooser.sort_combo, False, False, 0)
        row.pack_start(chooser.edit_button, False, False, 0)
        vbox.pack_start(row, False, False, 0)
        vbox.pack_start(Gtk.Label(label=" "), False, False, 0)

        vbox.pack_start(
            Gtk.Label(
                label=_(
                    "Drag and drop, or edit the numbers, to change the subsort order"
                )
            ),
            False,
            False,
            0,
        )
        vbox.pack_start(self._build_subsort_check(), False, False, 0)
        vbox.pack_start(Gtk.Label(label=" "), False, False, 0)
        vbox.pack_start(self._build_subsort_table(), True, True, 0)
        return vbox

    def _build_subsort_check(self) -> Gtk.CheckButton:
        """
        The "Use the whole list" check button. It is off after a cancelled
        or unfinished build: then only number 1 is used.

        :returns: The check button.
        """
        self._subsort_check_filling = True
        check = Gtk.CheckButton(
            label=_("Use the whole list (when off, only number 1 is used)")
        )
        check.set_active(not CONFIG.get("subsort.suspended"))
        check.set_tooltip_text(
            _(
                "Turned off by itself when a build is cancelled or does not "
                "finish. Number 1 alone is the fastest."
            )
        )
        check.connect("toggled", self.cb_subsort_check_toggled)
        check.connect("destroy", self.cb_subsort_check_destroyed)
        check.set_halign(Gtk.Align.CENTER)
        self._subsort_check = check
        self._subsort_check_filling = False
        return check

    def _build_subsort_table(self) -> Gtk.Box:
        """
        The numbered subsort list, in a row with a blank label that takes
        the left half and, on the right, a space as wide as the Columns
        tab Apply button, so that the tables of the two tabs sit in the
        same place.

        :returns: The row holding the table.
        """
        # order number, label, model column (NAME_FORMAT_ROW for Name format)
        store = Gtk.ListStore(int, str, int)
        self.subsort_store = store
        self._fill_subsort_store(self.subsort_order())
        # a drag and drop reorder ends with "row-deleted" on the old row
        store.connect("row-deleted", self.cb_subsort_row_deleted)
        tree = Gtk.TreeView(model=store)
        tree.set_reorderable(True)  # drag and drop, as in the Columns tab

        number = Gtk.CellRendererSpin()
        number.set_property("editable", True)
        number.set_property("adjustment", Gtk.Adjustment(1, 1, len(store), 1, 5, 0))
        number.connect("edited", self.cb_subsort_number_edited)
        column = Gtk.TreeViewColumn(_("Order"), number, text=0)
        column.set_min_width(60)
        tree.append_column(column)
        column = Gtk.TreeViewColumn(_("Column Name"), Gtk.CellRendererText(), text=1)
        column.set_min_width(225)
        tree.append_column(column)

        hbox = Gtk.Box(spacing=10)
        hbox.pack_start(Gtk.Label(label=" "), True, True, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_size_request(300, 300)
        scroll.add(tree)
        hbox.pack_start(scroll, True, True, 0)
        # stands in for the Apply button of the Columns tab
        placeholder = Gtk.Box()
        if self._columns_buttons is not None:
            sizes = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)
            sizes.add_widget(self._columns_buttons)
            sizes.add_widget(placeholder)
            self._subsort_sizes = sizes  # keep the group alive
        hbox.pack_start(placeholder, False, True, 0)
        return hbox

    def _fill_subsort_store(self, order: list[int]) -> None:
        """
        Fill the subsort list.

        :param order: Model columns in subsort order.
        """
        store = self.subsort_store
        if store is None:
            return
        self._subsort_filling = True  # clear() emits row-deleted
        store.clear()
        for number, col in enumerate(order, start=1):
            label = _("Name format") if col == NAME_FORMAT_ROW else self.COLUMNS[col][0]
            store.append([number, label, col])
        self._subsort_filling = False

    def _save_subsort_order(self, order: list[int]) -> None:
        """
        Save a changed subsort order, and refresh after the delay.

        :param order: Model columns in subsort order.
        """
        if order != list(CONFIG.get("subsort.order") or []):
            CONFIG.set("subsort.order", order)
            save_config()
            self._schedule_refresh()

    def cb_subsort_row_deleted(self, store: Gtk.ListStore, _path: Gtk.TreePath) -> None:
        """
        After a drag and drop: renumber, save, and refresh after the delay.

        :param store: The subsort list.
        :param _path: The deleted row (not used).
        """
        if self._subsort_filling:
            return
        order = [row[2] for row in store]
        for number, row in enumerate(store, start=1):
            row[0] = number
        self._save_subsort_order(order)

    def cb_subsort_number_edited(
        self, _renderer: Gtk.CellRendererSpin, path: str, new_text: str
    ) -> None:
        """
        A number was typed: move the row to its new number and renumber the
        rest.

        :param _renderer: The number cell renderer (not used).
        :param path: The edited row, as a string.
        :param new_text: The typed number.
        """
        store = self.subsort_store
        if store is None:
            return
        try:
            new_pos = int(new_text)
        except ValueError:
            return
        order = [row[2] for row in store]
        new_pos = max(1, min(new_pos, len(order)))
        old_pos = int(path) + 1
        if new_pos == old_pos:
            return
        order.insert(new_pos - 1, order.pop(old_pos - 1))
        self._fill_subsort_store(order)
        self._save_subsort_order(order)

    def cb_subsort_check_toggled(self, check: Gtk.CheckButton) -> None:
        """
        "Use the whole list" toggled: save it, and refresh after the delay.

        :param check: The check button.
        """
        if self._subsort_check_filling:
            return
        CONFIG.set("subsort.suspended", not check.get_active())
        save_config()
        self.dirty = True
        self._schedule_refresh()

    def cb_subsort_check_destroyed(self, *_args: Any) -> None:
        """
        The check button was destroyed with Configure.

        :param _args: Signal arguments (not used).
        """
        self._subsort_check = None

    def set_sort_name_format(self, num: int) -> None:
        """
        Set the sort-only name format chosen in the Subsorting tab.

        :param num: The name format number; 0 for Default.
        """
        if CONFIG.get("subsort.name_format") == num:
            return
        CONFIG.set("subsort.name_format", num)
        save_config()
        self._schedule_refresh()

    # ---------------------------------------------------------------
    # toolbar: Help icon
    # ---------------------------------------------------------------
    def _build_toolbar_ui(self) -> list[str]:
        """
        The toolbar XML with the Help icon (the phonetic system is set in
        Configure or in the right-click menu).

        :returns: The toolbar XML, as a one-element list.
        """
        self._help_tooltip_text = help_tooltip()
        toolbar = f"""
    <placeholder id="MoreButtons">
    <child>
      <object class="GtkToolItem">
        <child>
          <object class="GtkButton" id="FuzzyGroupingHelpButton">
            <property name="action-name">win.FuzzyGroupingHelp</property>
            <property name="tooltip_text">{escape(self._help_tooltip_text)}</property>
            <property name="relief">GTK_RELIEF_NONE</property>
            <child>
              <object class="GtkImage">
                <property name="visible">True</property>
                <property name="icon-name">{escape(help_icon_name())}</property>
                <property name="icon_size">3</property>
              </object>
            </child>
          </object>
        </child>
      </object>
    </child>
    </placeholder>
    """
        return [toolbar]

    def cb_icon_theme_changed(self, *_args: Any) -> None:
        """
        The icon theme changed: when the chosen Help icon file changes, put
        the new private icon name in the toolbar XML.

        :param _args: Signal arguments (not used).
        """
        if self.toolbar_ui is None:
            return  # toolbar not built yet; it will use the new icon
        old_name = _HELP_ICON_STATE["name"]
        if help_icon_name() != old_name:
            self._refresh_toolbar_ui()

    def _refresh_toolbar_ui(self) -> None:
        """
        Rebuild the toolbar XML; merge it now if this view is shown.
        """
        if self.toolbar_ui is None:
            return
        self.toolbar_ui[:] = self._build_toolbar_ui()
        if self.active:
            self.uimanager.add_ui_from_string(self.toolbar_ui)
            self.uimanager.update_menu()

    def cb_show_help(self, *_args: Any) -> None:
        """
        The toolbar Help icon: show the documentation.

        :param _args: Action arguments (not used).
        """
        show_help(self.uistate)

    # ---------------------------------------------------------------
    # right-click menu: Expand/Collapse all Nodes and a Grouping submenu
    # with None and every registered (not hidden) phonetic system
    # ---------------------------------------------------------------
    def _build_popup_ui(self) -> list[str]:
        """
        The right-click menu section. It is built per instance: its system
        list changes when encoder plugins are hidden or shown.

        :returns: The menu XML, as a one-element list.
        """

        def item(system_id: str, label: str) -> str:
            """
            One radio item of the Grouping submenu.

            :param system_id: The phonetic system id.
            :param label: The phonetic system label.
            :returns: The item XML.
            """
            return f"""
            <item>
              <attribute name="action">win.FuzzyGroupingSystem</attribute>
              <attribute name="target">{escape(system_id)}</attribute>
              <attribute name="label">{escape(label)}</attribute>
            </item>"""

        systems = "".join(
            item(system_id, label)
            for system_id, (label, _encode) in self.encoders.items()
            if system_id != EXACT_SYSTEM
        )
        return [f"""
      <section id="PopUpTree">
        <item>
          <attribute name="action">win.OpenAllNodes</attribute>
          <attribute name="label">{escape(_("Expand all Nodes"))}</attribute>
        </item>
        <item>
          <attribute name="action">win.CloseAllNodes</attribute>
          <attribute name="label">{escape(_("Collapse all Nodes"))}</attribute>
        </item>
        <submenu>
          <attribute name="label">{escape(_("Grouping (Phonetic encoding)"))}</attribute>
          <section>{item(EXACT_SYSTEM, self.encoders[EXACT_SYSTEM][0])}
          </section>
          <section>{systems}
          </section>
        </submenu>
      </section>
    """]

    def _refresh_popup_ui(self) -> None:
        """
        Rebuild the right-click menu XML; merge it now if this view is
        shown.
        """
        if self.popup_ui is None:
            return
        self.popup_ui[:] = self._build_popup_ui()
        if self.active:
            self.uimanager.add_ui_from_string(self.popup_ui)

    def _button_press(self, obj: Gtk.Widget, event: Gdk.EventButton) -> bool:
        """
        Right-click: pick up encoder plugins hidden or shown in the Plugin
        Manager before the menu opens (the core then rebuilds the menu).

        :param obj: The tree view.
        :param event: The button event.
        :returns: ``True`` when the event was handled.
        """
        if (
            event.type == Gdk.EventType.BUTTON_PRESS
            and event.button == 3
            and self.dbstate.is_open()
        ):
            self._refresh_encoders()
        return BasePersonView._button_press(self, obj, event)

    def cb_system_menu(self, _action: Gio.SimpleAction, value: GLib.Variant) -> None:
        """
        The Grouping submenu: regroup at once with the chosen system.

        :param _action: The radio action (not used).
        :param value: The chosen system id.
        """
        system_id = value.get_string()
        if not self.set_phonetic_system(system_id):
            self._sync_system_action()  # unchanged or unavailable: re-check

    def _sync_system_action(self) -> None:
        """
        Put the radio mark of the Grouping submenu on the current system.
        The stored action list is updated too, because the action is made
        again from it each time the view is shown.
        """
        group = getattr(self, "action_group", None)
        if group is None:
            return
        for index, entry in enumerate(group.actionlist):
            if entry[0] == "FuzzyGroupingSystem":
                group.actionlist[index] = entry[:3] + (self.system_id,)
        act_group = getattr(group, "act_group", None)
        action = act_group.lookup_action("FuzzyGroupingSystem") if act_group else None
        if action is not None and action.get_state().get_string() != self.system_id:
            action.set_state(GLib.Variant("s", self.system_id))

    # ---------------------------------------------------------------
    # Phonetic system sync with gramplets docked in this view
    #
    # Duck-typed, so no addon imports another: a docked gramplet checks
    # getattr(self.gui.view, "PHONETIC_SYSTEM_SYNC", 0) >= 1, then uses
    # phonetic_system_id(), set_phonetic_system() and
    # connect_phonetic_system(). Used by Flat Filter and Fuzzy Matching.
    # ---------------------------------------------------------------
    PHONETIC_SYSTEM_SYNC = 1

    def phonetic_system_id(self) -> str:
        """
        The phonetic system this view groups with.

        :returns: The phonetic system id.
        """
        return self.system_id

    def connect_phonetic_system(self, callback: Callable[[str], Any]) -> None:
        """
        Call callback(system_id) when this view changes phonetic system.
        A bound method is held weakly, so a closed gramplet needs no
        disconnect.

        :param callback: The function or bound method to call.
        """
        ref: Any
        try:
            ref = weakref.WeakMethod(callback)  # type: ignore[arg-type]
        except TypeError:  # plain function
            ref = weakref.ref(callback)
        self._system_listeners.append(ref)

    def set_phonetic_system(
        self, system_id: str, source: Any = None, delayed: bool | None = None
    ) -> bool:
        """
        Group with another phonetic system. A change from a gramplet, or
        from Configure (delayed=True), waits REFRESH_DELAY seconds before
        regrouping, so a following Find click or another Configure change
        costs a single rebuild.

        :param system_id: The phonetic system id.
        :param source: The object asking (a docked gramplet); it is not
            called back. ``None`` for this view itself.
        :param delayed: ``True`` to regroup after the delay, ``False`` to
            regroup at once; ``None`` delays only for a gramplet.
        :returns: ``False`` when this view does not have that system (for
            example its plugin is hidden) or already uses it.
        """
        if system_id == self.system_id or system_id not in self.encoders:
            return False
        t_set = perf_counter()
        asker = "Configure" if source is None else source.__class__.__name__
        timing_print(f"system change {self.system_id} -> {system_id}, from {asker}")
        self.system_id = system_id
        CONFIG.set("grouping.system", system_id)
        save_config()
        self._fill_system_combo()
        self._sync_system_action()
        self._notify_system_listeners(source)
        if delayed is None:
            delayed = source is not None
        timing_print(
            f"system change done in {_secs(perf_counter() - t_set)} "
            "(before the regroup)"
        )
        if delayed:
            self.dirty = True
            self._schedule_refresh()
        else:
            self._rebuild()
        return True

    def _notify_system_listeners(self, source: Any = None) -> None:
        """
        Tell the connected gramplets about a phonetic system change.

        :param source: The gramplet that made the change; it is skipped.
        """
        for ref in list(self._system_listeners):
            callback = ref()
            if callback is None:
                self._system_listeners.remove(ref)
                continue
            owner = getattr(callback, "__self__", None)
            if source is not None and owner is source:
                continue
            t_cb = perf_counter()
            try:
                callback(self.system_id)
            except Exception:  # pylint: disable=broad-except
                LOG.exception("Fuzzy Grouping: phonetic system listener failed")
            owner_name = owner.__class__.__name__ if owner is not None else ""
            timing_print(
                f"  listener {owner_name}.{getattr(callback, '__name__', '?')} "
                f"took {_secs(perf_counter() - t_cb)}"
            )

    def define_actions(self) -> None:
        """
        Define actions for the popup menu specific to the tree view.
        """
        BasePersonView.define_actions(self)

        self.action_list.extend(
            [
                ("OpenAllNodes", self.open_all_nodes),
                ("CloseAllNodes", self.close_all_nodes),
                ("FuzzyGroupingHelp", self.cb_show_help),
                # radio action: its state is the phonetic system id
                ("FuzzyGroupingSystem", self.cb_system_menu, "", self.system_id),
            ]
        )

    def add(self, *_obj: Any) -> None:
        """
        Add a person; the new person starts with the surname of the
        selected person.

        :param _obj: Action arguments (not used).
        """
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

    def get_config_name(self) -> str:
        """
        The name of the view settings file.

        :returns: The module name.
        """
        return __name__
