#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
# Based on gramps/gui/exampleimport.py from Gramps PR 2388
# Copyright (C) 2025  The Gramps Project
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
Example Tree Prompt - monkey-patch addon port of Gramps PR 2388.

PR 2388 adds a startup prompt offering to import the bundled Example
Family Tree. In core, it is called from Gramps.__init__ right after the
Tip of the Day. An addon cannot edit that function, so instead:

* load_on_reg() runs while plugins register (inside ViewManager.__init__,
  i.e. before Gramps.__init__ reaches post_init_interface()).
* It wraps ViewManager.post_init_interface once. After the original runs
  (including any blocking Family Tree manager dialog), the prompt is
  queued with GLib.idle_add, so it appears once the main loop starts.
* Unlike the PR, the prompt also stays away when a tree is opened at
  startup (chosen in the Family Trees manager or loaded automatically).
* Unlike the PR (which shows both), Tip of the Day is skipped for any
  launch where the prompt appears, so two splash windows never open
  together. The Tip of the Day setting itself is left unchanged.
* Also beyond the PR: importing adds a labeled GTK bookmark for the
  practice tree media folder, so the sample media is easy to find in
  any file chooser.

The PR's other two pieces are handled here too:
* const.ENV gets the "GRAMPS_RESOURCES" key (so {GRAMPS_RESOURCES} in the
  example's media path expands correctly in installed packages).
* The zoom 0-2 OSM tiles ship in this addon's maps/ folder instead of
  Gramps' data folder.

The prompt setting lives in PR2388_ExampleTreePrompt.ini next to this file,
not in gramps.ini.
"""

import importlib.util
import logging
import os
import shutil

from gi.repository import Gio, GLib, Gtk

from gramps.cli.clidbman import CLIDbManager
from gramps.gen import const
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import IMAGE_DIR, LICENSE_FILE, USER_CACHE
from gramps.gen.db.utils import make_database
from gramps.gen.plug import BasePluginManager
from gramps.gen.utils.file import expand_path

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger(".PR2388_ExampleTreePrompt")

PLUGIN_ID = "PR2388_ExampleTreePrompt"
ADDON_DIR = os.path.dirname(os.path.abspath(__file__))

# The PR exports DOC_DIR from const.py; 5.2/6.0 do not, but LICENSE_FILE
# is built from the same _resources.doc_dir, so derive it from that.
DOC_DIR = os.path.dirname(LICENSE_FILE)

# The PR names the tree "Example Family Tree", but the file it imports is
# data.gramps; Gramps also ships the much larger example.gramps, so
# "Example" would point at the wrong file. data.gramps carries no tree
# name of its own, so use a name that describes no particular content:
# it stays correct if another data.gramps (e.g. a localized one) is used.
_EXAMPLE_TREE_NAME = _("sample tree data")
_EXAMPLE_DATA = os.path.join(DOC_DIR, "example", "gramps", "data.gramps")
_BUNDLED_TILES_DIR = os.path.join(ADDON_DIR, "maps", "openstreetmap")

PROMPT_KEY = "behavior.show-example-prompt"

# Link target for the "Read more about this sample tree" To Do note.
# Replaced by the help_url from the .gpr.py at registration.
_HELP_URL = "https://github.com/gramps-project/gramps/pull/2388"
_GLOSSARY_HOME_PERSON = (
    "https://gramps-project.org/wiki/index.php/Gramps_Glossary#home_person"
)

# Name of the GTK bookmark added for the practice tree media folder.
# (Application shortcuts cannot carry a name; bookmarks can.)
_BOOKMARK_LABEL = _("Gramps example data")

# Addon settings: PR2388_ExampleTreePrompt.ini in this addon's own folder.
CONFIG = config.register_manager(PLUGIN_ID, use_plugins_path=False)
CONFIG.register("meta.plugin_id", PLUGIN_ID)
CONFIG.register("meta.schema_version", "1")
CONFIG.register(PROMPT_KEY, True)
CONFIG.load()
if CONFIG.filename and not os.path.exists(CONFIG.filename):
    # Write it once so testers can find and reset the setting.
    CONFIG.save()

_PATCHED = False


# -------------------------------------------------------------------------
#
# Addon entry point (called by the plugin manager at registration)
#
# -------------------------------------------------------------------------
def load_on_reg(dbstate, uistate, plugin):
    """
    Install the monkey patches. Runs once per Gramps session.
    """
    global _PATCHED, _HELP_URL
    _HELP_URL = getattr(plugin, "help_url", None) or _HELP_URL
    if _PATCHED:
        return None

    if importlib.util.find_spec("gramps.gui.exampleimport") is not None:
        # PR 2388 (or its successor) is already in this Gramps; stand down.
        LOG.info("Gramps core has the example import prompt; addon idle.")
        _PATCHED = True
        return None

    _fix_gramps_resources_env()

    if uistate is None:
        # CLI session: the ENV fix still helps; no prompt.
        _PATCHED = True
        return None

    from gramps.gui.viewmanager import ViewManager

    original = ViewManager.post_init_interface

    def patched_post_init_interface(self, *args, **kwargs):
        # One-shot: put the original back before doing anything else.
        ViewManager.post_init_interface = original
        result = original(self, *args, **kwargs)
        if _launched_with_file(self) or _tree_opened_at_startup(self):
            # A tree or file was given on the command line (or Gramps was
            # started by opening a file), or a tree was chosen in the
            # Family Trees manager or is loading automatically; never
            # compete with that.
            return result
        tips_hidden = _hide_tip_of_day_if_prompting(self)
        GLib.idle_add(cb_idle_prompt, self, tips_hidden)
        return result

    ViewManager.post_init_interface = patched_post_init_interface
    _PATCHED = True
    return None


def _launched_with_file(vm):
    """
    Return True when Gramps was started with a tree or file to open or
    import, or with CLI actions/exports.

    That covers "gramps file.ged" (and opening a file from a file
    manager, which runs the same command), -O/--open, -C/--create,
    -i/--import, -e/--export and -a/--action. The ArgParser is reachable
    as vm.app.argparser (GrampsApplication keeps it).
    """
    argparser = getattr(getattr(vm, "app", None), "argparser", None)
    if argparser is None:
        return False
    for attr in ("open_gui", "open", "create", "imports", "exports", "actions"):
        if getattr(argparser, attr, None):
            return True
    return False


def _tree_opened_at_startup(vm):
    """
    Return True when a tree is open, or is about to open, at startup.

    - A tree chosen in the Family Trees manager is already open when
      post_init_interface() returns.
    - With "Load the last Family Tree" on, Gramps.__init__ opens it right
      after post_init_interface() returns, using the same check as below.
    """
    if vm.dbstate.is_open():
        return True
    if config.get("behavior.autoload"):
        filename = config.get("paths.recent-file")
        if filename and os.path.isfile(os.path.join(filename, "name.txt")):
            return True
    return False


def _hide_tip_of_day_if_prompting(vm):
    """
    Avoid two splash windows at once: when the prompt is going to appear,
    skip the Tip of the Day for this launch only.

    Gramps.__init__ checks "behavior.use-tips" right after
    post_init_interface() returns, so the setting is switched off here
    and switched back on in cb_idle_prompt(), which runs as soon as the
    main loop starts (before the user can open Preferences or quit).

    :returns: True if the setting was switched off and must be restored.
    """
    try:
        if config.get("behavior.use-tips") and _prompt_wanted(vm):
            config.set("behavior.use-tips", False)
            return True
    except Exception:
        LOG.exception("Could not check whether to skip Tip of the Day.")
    return False


def cb_idle_prompt(vm, tips_hidden=False):
    """
    Idle callback: restore Tip of the Day, then show the prompt once the
    main loop is running.
    """
    if tips_hidden:
        config.set("behavior.use-tips", True)
    if vm.dbstate.is_open():
        return False  # a tree was opened at startup after all
    try:
        maybe_prompt_example_import(vm)
    except Exception:
        LOG.exception("Example Tree Prompt failed.")
    return False  # run once


def _fix_gramps_resources_env():
    """
    PR 2388 const.py change: add GRAMPS_RESOURCES to the ENV dict.

    gramps.gen.utils.file imports this same dict object, so adding the
    key here is seen by expand_path() / media_path_full().
    """
    if "GRAMPS_RESOURCES" in const.ENV:
        return
    const.ENV["GRAMPS_RESOURCES"] = os.path.dirname(os.path.dirname(DOC_DIR))


# -------------------------------------------------------------------------
#
# ExampleImportDialog
#
# -------------------------------------------------------------------------
class ExampleImportDialog(Gtk.Dialog):
    """
    Dialog offering to import the bundled sample tree.

    The body copies the Tip of the Day layout (without its heading line):
    the Gramps splash picture on the left and wrapped text on the right. The tipofday.glade file itself cannot be reused, because in
    Gramps 6.0 it is a Gtk.Template bound to the TipOfDay class, so the
    same grid is built here, and the window title comes from the same
    set_titles() helper that Tip of the Day uses.
    """

    def __init__(self, parent_window):
        super().__init__(transient_for=parent_window, modal=True)
        self.set_default_size(550, 350)  # same as Tip of the Day
        self.set_border_width(8)

        grid = Gtk.Grid()
        grid.set_valign(Gtk.Align.START)

        image = Gtk.Image()
        image.set_valign(Gtk.Align.START)
        image.set_vexpand(True)
        image.set_from_file(os.path.join(IMAGE_DIR, "splash.jpg"))
        grid.attach(image, 0, 0, 1, 1)

        body = Gtk.Label()
        body.set_size_request(300, -1)
        body.set_halign(Gtk.Align.START)
        body.set_valign(Gtk.Align.START)
        body.set_margin_start(6)
        body.set_margin_end(6)
        body.set_margin_top(6)
        body.set_margin_bottom(6)
        body.set_hexpand(True)
        body.set_vexpand(True)
        body.set_line_wrap(True)
        body.set_xalign(0.0)
        body.set_markup(
            _(
                "Gramps without any family tree data can feel like an "
                "unfurnished room.\n\n"
                "Would you like to import a <b>practice Family Tree</b>? "
                "This small sample family lets you try out Gramps features (people, events, "
                "places, media, and maps) before you enter your own family "
                "information.\n\n"
                "Changes you make to the practice tree will not affect your "
                "own trees."
            )
        )
        grid.attach(body, 1, 0, 1, 1)

        self.dont_ask = Gtk.CheckButton(label=_("Do not ask again"))
        self.dont_ask.set_halign(Gtk.Align.CENTER)
        self.dont_ask.set_valign(Gtk.Align.START)
        grid.attach(self.dont_ask, 0, 1, 2, 1)

        self.get_content_area().pack_start(grid, True, True, 0)

        # Same window title treatment as Tip of the Day ("<text> - Gramps"
        # plus the Gramps window icon). No heading label in the body: it
        # only repeated the title bar.
        from gramps.gui.managedwindow import set_titles

        set_titles(self, None, _("Getting Started"))

        self.add_button(_("Skip"), Gtk.ResponseType.REJECT)
        btn = self.add_button(_("Import Practice Tree"), Gtk.ResponseType.ACCEPT)
        btn.get_style_context().add_class("suggested-action")
        self.set_default_response(Gtk.ResponseType.ACCEPT)

        self.get_content_area().show_all()


# -------------------------------------------------------------------------
#
# Prompt logic (same behavior as PR 2388)
#
# -------------------------------------------------------------------------
def _prompt_wanted(vm, log_missing=False):
    """
    Return True when the prompt should appear (same conditions as PR 2388).
    """
    if not CONFIG.get(PROMPT_KEY):
        return False

    if not os.path.isfile(_EXAMPLE_DATA):
        if log_missing:
            # The PR returns silently; for field testing, say why.
            LOG.warning("Example data not found at %s; no prompt.", _EXAMPLE_DATA)
        return False

    dbman = CLIDbManager(vm.dbstate)
    return dbman.get_family_tree_path(_EXAMPLE_TREE_NAME) is None


def maybe_prompt_example_import(vm):
    """
    Show the example-import prompt if conditions are met.

    Suppressed when:
    - the show-example-prompt setting is False,
    - a tree with the sample tree name already exists,
    - the bundled data.gramps file cannot be found.
    """
    if not _prompt_wanted(vm, log_missing=True):
        return

    parent = getattr(getattr(vm, "uistate", None), "window", None)
    dialog = ExampleImportDialog(parent)
    response = dialog.run()
    dont_ask = dialog.dont_ask.get_active()
    dialog.destroy()

    if dont_ask:
        # Only the checkbox turns the prompt off for good.
        # (PR 2388 also turns it off on Skip, Esc or the window close
        # button, which makes the checkbox matter only with Import.)
        CONFIG.set(PROMPT_KEY, False)
        CONFIG.save()

    if response != Gtk.ResponseType.ACCEPT:
        # Skip, Esc or window close: just skip it for this launch.
        return

    # Importing leaves the setting alone; the tree-name check handles
    # suppression, so renaming the tree re-triggers the prompt.
    _do_import(vm, _EXAMPLE_DATA)


def _do_import(vm, data_gramps_path):
    """
    Create the sample tree, import data.gramps into it, seed map
    tiles, then open the new tree in the main window.
    """
    dbid = config.get("database.backend")
    dbman = CLIDbManager(vm.dbstate)

    try:
        new_path, _title = dbman.create_new_db_cli(_EXAMPLE_TREE_NAME, dbid=dbid)
    except Exception:
        LOG.exception("Failed to create the sample tree database directory.")
        return

    dbase = None
    try:
        dbase = make_database(dbid)
        dbase.load(new_path)

        pmgr = BasePluginManager.get_instance()
        importer = None
        for plugin in pmgr.get_import_plugins():
            if plugin.get_extension() == "gramps":
                importer = plugin.get_import_function()
                break

        if importer is None:
            LOG.error("No .gramps XML importer found; cannot import example tree.")
            dbase.close()
            return

        from gramps.gui.user import User

        user = User(uistate=vm.uistate, dbstate=vm.dbstate)
        importer(dbase, data_gramps_path, user)
        mediapath = dbase.get_mediapath() or ""
    except Exception:
        LOG.exception("Error while importing example data.")
        if dbase is not None:
            try:
                dbase.close()
            except Exception:
                pass
        return

    dbase.close()

    _seed_map_tiles()
    _add_media_bookmark(mediapath, data_gramps_path)

    # Open the newly created tree in the main window.
    if vm.dbstate.is_open():
        vm.dbstate.db.close(user=vm.user)
    vm.db_loader.read_file(new_path)
    vm._post_load_newdb(new_path, "x-directory/normal", _EXAMPLE_TREE_NAME)

    _add_todo_notes(vm.dbstate.db)
    _show_dashboard(vm)


def _seed_map_tiles():
    """
    Copy the bundled zoom 0/1/2 OSM tiles into the user's tile cache.

    Only missing tiles are copied, so a previously cached (fresher) tile
    is left alone.
    """
    if not os.path.isdir(_BUNDLED_TILES_DIR):
        return

    geography_path = config.get("geography.path")
    if not geography_path:
        geography_path = os.path.join(USER_CACHE, "maps")

    dest_dir = os.path.join(geography_path, "openstreetmap")

    for zoom in os.listdir(_BUNDLED_TILES_DIR):
        zoom_src = os.path.join(_BUNDLED_TILES_DIR, zoom)
        if not os.path.isdir(zoom_src):
            continue
        for x_col in os.listdir(zoom_src):
            col_src = os.path.join(zoom_src, x_col)
            if not os.path.isdir(col_src):
                continue
            col_dst = os.path.join(dest_dir, zoom, x_col)
            os.makedirs(col_dst, exist_ok=True)
            for tile_file in os.listdir(col_src):
                src_tile = os.path.join(col_src, tile_file)
                dst_tile = os.path.join(col_dst, tile_file)
                if not os.path.exists(dst_tile):
                    try:
                        shutil.copy2(src_tile, dst_tile)
                    except OSError:
                        LOG.warning("Could not copy tile %s to %s", src_tile, dst_tile)


def _add_media_bookmark(mediapath, data_gramps_path):
    """
    Add a labeled GTK bookmark for the practice tree media folder.

    The folder is the tree's Base media path, expanded (for data.gramps
    that is {GRAMPS_RESOURCES}/doc/gramps/example/gramps); if that does
    not exist, the folder holding data.gramps is used instead.

    GTK 3 keeps bookmarks in <user config dir>/gtk-3.0/bookmarks, one
    "URI label" per line. The bookmark belongs to the user afterwards:
    it can be renamed or removed in any file chooser, and it is not
    added again if a bookmark for that folder already exists.
    """
    folder = expand_path(mediapath) if mediapath else ""
    if not os.path.isdir(folder):
        folder = os.path.dirname(data_gramps_path)
    if not os.path.isdir(folder):
        return

    uri = Gio.File.new_for_path(folder).get_uri()
    bookmarks = os.path.join(GLib.get_user_config_dir(), "gtk-3.0", "bookmarks")
    try:
        existing = ""
        if os.path.exists(bookmarks):
            with open(bookmarks, encoding="utf-8") as handle:
                existing = handle.read()
            for line in existing.splitlines():
                parts = line.split(" ", 1)
                if parts and parts[0].rstrip("/") == uri.rstrip("/"):
                    return  # already bookmarked (maybe renamed by the user)
        os.makedirs(os.path.dirname(bookmarks), exist_ok=True)
        with open(bookmarks, "a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("%s %s\n" % (uri, _BOOKMARK_LABEL))
    except OSError:
        LOG.warning("Could not add a bookmark for %s to %s", folder, bookmarks)


def _show_dashboard(vm):
    """
    Switch to the Dashboard category. If the Dashboard is empty or still
    has its default gramplets, and has no To Do gramplet, add it.
    """
    try:
        cat_num = None
        for num, cat_views in enumerate(vm.views or []):
            # category[0] is the untranslated id, category[1] the label.
            if cat_views and cat_views[0][0].category[0] == "Dashboard":
                cat_num = num
                break
        if cat_num is None:
            return
        page = vm.goto_page(cat_num, None)
        pane = getattr(page, "widget", None)
        if pane is None or not hasattr(pane, "add_gramplet"):
            return
        _add_todo_if_default(pane)
    except Exception:
        LOG.exception("Could not switch to the Dashboard.")


def _add_todo_if_default(pane):
    """
    Add the To Do gramplet when the Dashboard is empty or shows exactly
    the default gramplet set (Top Surnames and Welcome, unless changed),
    and To Do is not already there (open or detached).
    """
    from gramps.gui.widgets.grampletpane import (
        AVAILABLE_GRAMPLETS,
        get_gramplet_options_by_name,
    )

    shown = {g.gname for g in pane.gramplet_map.values() if g is not None}
    shown |= {g.gname for g in getattr(pane, "detached_gramplets", [])}
    if "To Do" in shown:
        return
    # The default set comes from the running Gramps (GrampletPane keeps
    # it), not from a list here. Like GrampletPane.load_gramplets(), skip
    # defaults that are not installed, so a missing one does not make a
    # default Dashboard look customized.
    available = AVAILABLE_GRAMPLETS()
    defaults = {n for n in getattr(pane, "default_gramplets", []) if n in available}
    if shown and shown != defaults:
        return  # the user has arranged the Dashboard; leave it alone

    opts = get_gramplet_options_by_name("To Do")
    if not opts:
        return
    # add_gramplet() looks gramplets up by translated name.
    pane.add_gramplet(opts["tname"])


def _add_todo_notes(db):
    """
    If the imported tree has no To Do notes, add one To Do note:

        Read more about this sample tree

        Start exploring with the Home Person, currently set to <name>.

    "Read more about this sample tree" links to the addon help_url,
    "Home Person" to its Gramps Glossary entry, and the name to the Home
    Person. The note is attached to the Home Person. If the tree has no
    Home Person, the second line says so and the person with the lowest
    Gramps ID is linked and attached instead. A tree with no
    people gets only the first line.
    """
    from gramps.gen.db import DbTxn
    from gramps.gen.display.name import displayer as name_displayer
    from gramps.gen.lib import (
        Note,
        NoteType,
        StyledText,
        StyledTextTag,
        StyledTextTagType,
    )

    try:
        for note in db.iter_notes():
            if note.get_type() == NoteType.TODO:
                return  # the data already has To Do notes; add nothing

        text = ""
        tags = []

        def add_link(label, url):
            nonlocal text
            tags.append(
                StyledTextTag(
                    StyledTextTagType.LINK, url, [(len(text), len(text) + len(label))]
                )
            )
            text += label

        add_link(_("Read more about this sample tree"), _HELP_URL)

        person = db.get_default_person()
        if person is not None:
            template = _(
                "Start exploring with the %(home_person)s, "
                "currently set to %(name)s."
            )
        else:
            # No Home Person: use the person with the lowest Gramps ID,
            # and say so. get_person_gramps_ids() lists the IDs without
            # reading every person record.
            first_id = min(db.get_person_gramps_ids(), default=None)
            person = db.get_person_from_gramps_id(first_id) if first_id else None
            template = _(
                "This tree has no %(home_person)s set, so this note is "
                "attached to the first person listed in the tree, %(name)s."
            )
        if person is not None:
            text += "\n\n"
            # Placeholders keep the sentence translatable in any word order.
            links = {
                "%(home_person)s": (_("Home Person"), _GLOSSARY_HOME_PERSON),
                "%(name)s": (
                    name_displayer.display(person),
                    "gramps://Person/handle/%s" % person.get_handle(),
                ),
            }
            rest = template
            while rest:
                # Find the next placeholder, copy the text before it.
                hits = [(rest.find(key), key) for key in links if key in rest]
                if not hits:
                    text += rest
                    break
                pos, key = min(hits)
                text += rest[:pos]
                add_link(*links[key])
                rest = rest[pos + len(key) :]

        note = Note()
        note.set_type(NoteType.TODO)
        note.set_styledtext(StyledText(text, tags))
        with DbTxn(_("Add sample tree To Do note"), db) as trans:
            db.add_note(note, trans)
            if person is not None:
                # Attach to the Home Person (or the first person) so the
                # To Do gramplet shows who the note belongs to.
                person.add_note(note.get_handle())
                db.commit_person(person, trans)
    except Exception:
        LOG.exception("Could not add the sample tree To Do note.")
