"""
Pruned Branch - working-subset editing session (draft prototype).

Gramps 6.0 or newer, DB-API backend. On SQLite the branch is cut with
TEMP keep-tables joined in SQL; other DB-API backends fall back to
per-handle reads.
"""

import functools
import logging
import os
import re
from time import perf_counter

from gi.repository import Gdk, GLib, Gtk

from gramps.gen import filters as gfilters
from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters import GenericFilter
from gramps.gen.filters.rules.person import HasTag
from gramps.gen.plug import TOOL_DBFIX
from gramps.gui import viewmanager as gramps_viewmanager
from gramps.gui.dialog import ErrorDialog
from gramps.gui.editors.editprimary import EditPrimary
from gramps.gui.editors.editreference import EditReference
from gramps.gui.editors.editsecondary import EditSecondary
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.widgets.grampletbar import DetachedWindow
from gramps.gui.widgets.grampletpane import GrampletWindow
from gramps.gui.plug import tool
from gramps.gui.plug.export import ExportAssistant
from gramps.gui.utils import open_file_with_default_application

from prunedbranch_bench import run_benchmark
from prunedbranch_db import (
    callback_keys,
    drop_duplicate_callbacks,
    STRATEGY_PYTHON,
    STRATEGY_SQL,
    TABLES,
    BranchDb,
    KeepTables,
    compute_keep_sets,
    count_callbacks,
    is_sqlite,
)

_ = glocale.translation.gettext
LOG = logging.getLogger(".PrunedBranch")

PLUGIN_ID = "PrunedBranch"
SESSION = None  # the active BranchSession, if any
LISTENERS = set()  # callables refreshed when a session starts or ends
CALLBACK_HISTORY = []  # (moment, total, long-op-start) across sessions
_PATCHED = False

# ------------------------------------------------------------
# Settings: PrunedBranch.ini next to this module
# ------------------------------------------------------------
# A file whose [meta] block does not match (another plugin id, an older
# schema, or no [meta] block at all) is ignored and replaced on the next
# save. Raise SCHEMA_VERSION whenever the stored structure changes.
SCHEMA_VERSION = "1"
MAX_RECENT_TAGS = 10

CONFIG = configman.register_manager(
    PLUGIN_ID, override=os.path.abspath(__file__), use_plugins_path=False
)
# The meta defaults are empty on purpose: ConfigManager comments out values
# that equal their default when it saves, and the real values must be
# written for the version check to work.
CONFIG.register("meta.plugin_id", "")
CONFIG.register("meta.schema_version", "")
# {tree id: {"tree": tree name, "tags": [tag handle, ...]}}, newest first.
# The tree name is only there to make the file readable.
CONFIG.register("tags.recent", {})
CONFIG.load()
if (
    CONFIG.get("meta.plugin_id") != PLUGIN_ID
    or CONFIG.get("meta.schema_version") != SCHEMA_VERSION
):
    if os.path.isfile(CONFIG.filename):
        LOG.warning(
            "Pruned Branch: ignoring settings from another version: %s",
            CONFIG.filename,
        )
    CONFIG.reset()
CONFIG.set("meta.plugin_id", PLUGIN_ID)
CONFIG.set("meta.schema_version", SCHEMA_VERSION)


def _tree_id(db):
    """Identifier of the open Family Tree (its folder name)."""
    try:
        return db.get_dbid() or ""
    except Exception:  # DummyDb or an old backend
        return ""


def recent_tag_handles(db):
    """Handles of the tags last used for this tree, newest first."""
    entry = CONFIG.get("tags.recent").get(_tree_id(db), {})
    return list(entry.get("tags", []))


def remember_tag(db, tag_handle):
    """Move tag_handle to the front of this tree's recent tags and save."""
    tree = _tree_id(db)
    if not tree or not tag_handle:
        return
    recent = dict(CONFIG.get("tags.recent"))
    tags = [h for h in recent.get(tree, {}).get("tags", []) if h != tag_handle]
    tags.insert(0, tag_handle)
    try:
        name = db.get_dbname()
    except Exception:
        name = ""
    recent[tree] = {"tree": name, "tags": tags[:MAX_RECENT_TAGS]}
    CONFIG.set("tags.recent", recent)
    CONFIG.save()

# ------------------------------------------------------------
# Session stylesheets
# ------------------------------------------------------------
# media/pruned_branch.css is the default and is replaced by addon updates.
# media/pruned_branch_user.css holds the user's changes. It is created on
# first use and is never part of the addon package, so updates leave it
# alone. It is loaded one priority step higher, so anything in it wins,
# including @define-color names that the default's mix() colors use.
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
CSS_FILE = os.path.join(MEDIA_DIR, "pruned_branch.css")
USER_CSS_FILE = os.path.join(MEDIA_DIR, "pruned_branch_user.css")
CSS_PRIORITY = Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 10
USER_CSS_PRIORITY = CSS_PRIORITY + 1

# The five colors the tool offers as swatches, in display order.
BASE_COLORS = [
    ("pruned_alert", _("Status bar button")),
    ("pruned_border", _("Borders and pane separators")),
    ("pruned_surface", _("Window background")),
    ("pruned_text", _("Text")),
    ("pruned_selected", _("Selected row, hovered menu item")),
]
# The tool rewrites only the lines between these two markers.
BLOCK_START = "/* --- Colors chosen in the Pruned Branch tool --- */"
BLOCK_END = "/* --- End of chosen colors --- */"
USER_CSS_TEMPLATE = """/* Pruned Branch - your session color changes.
 *
 * This file is yours: addon updates never include it, so it is kept.
 * It is loaded after pruned_branch.css, so anything here wins. Redefine
 * any @define-color name from that file, or add your own rules.
 *
 * The color swatches in the Pruned Branch tool rewrite the block between
 * the two markers below. Put your own changes after the block; a color
 * defined after it wins over the swatch.
 */

%s
%s
""" % (BLOCK_START, BLOCK_END)

_DEFINE_RE = re.compile(r"@define-color\s+([\w-]+)\s+([^;]+);")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def defined_colors(path):
    """Return {name: value} for every @define-color in a stylesheet.

    Commented-out lines are skipped; a later definition wins, as in GTK.
    """
    try:
        with open(path, encoding="utf-8") as css:
            text = _COMMENT_RE.sub("", css.read())
    except OSError:
        return {}
    return {name: value.strip() for name, value in _DEFINE_RE.findall(text)}


def ensure_user_css():
    """Create the user stylesheet from the template if it does not exist."""
    if not os.path.isfile(USER_CSS_FILE):
        with open(USER_CSS_FILE, "w", encoding="utf-8") as css:
            css.write(USER_CSS_TEMPLATE)


def save_user_colors(colors):
    """Rewrite the tool block of the user stylesheet.

    colors is {name: "#rrggbb"}; only colors that differ from the default
    belong in it. Everything outside the block is left as it is.
    """
    ensure_user_css()
    with open(USER_CSS_FILE, encoding="utf-8") as css:
        text = css.read()
    lines = [BLOCK_START]
    for name, _label in BASE_COLORS:
        if name in colors:
            lines.append("@define-color %s %s;" % (name, colors[name]))
    lines.append(BLOCK_END)
    block = "\n".join(lines)
    start, end = text.find(BLOCK_START), text.find(BLOCK_END)
    if start != -1 and end > start:
        text = text[:start] + block + text[end + len(BLOCK_END):]
    else:  # markers removed by hand: put the block back at the top
        text = block + "\n\n" + text
    with open(USER_CSS_FILE, "w", encoding="utf-8") as css:
        css.write(text)


def load_css(path, quiet=False):
    """Return a CssProvider for path, or None if it is missing or broken."""
    if not os.path.isfile(path):
        if not quiet:
            LOG.warning("Pruned Branch: stylesheet not found: %s", path)
        return None
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(path)
    except Exception as exc:  # GLib.Error on a CSS syntax error
        LOG.warning("Pruned Branch: cannot load CSS %s: %s", path, exc)
        return None
    return provider


def _notify():
    for listener in list(LISTENERS):
        try:
            listener()
        except Exception:  # a closed dialog must not break the session
            LOG.debug("listener failed", exc_info=True)


# ------------------------------------------------------------
# Monkey-patches: backups and exports always see the whole tree;
# other tools ask first.
# ------------------------------------------------------------
def _full_tree(orig, get_dbstate):
    @functools.wraps(orig)
    def inner(self, *args, **kwargs):
        sess = SESSION
        dbstate = get_dbstate(self, args)
        if sess is None or dbstate is None or dbstate.db is not sess.wrapper:
            return orig(self, *args, **kwargs)
        LOG.info("Pruned Branch: %s runs on the full tree", orig.__qualname__)
        dbstate.db = sess.real
        try:
            return orig(self, *args, **kwargs)
        finally:
            if dbstate.db is sess.real:
                dbstate.db = sess.wrapper

    return inner


def _guard_gui_tool(orig):
    names = (
        "dbstate",
        "user",
        "tool_class",
        "options_class",
        "translated_name",
        "name",
        "category",
        "callback",
    )

    @functools.wraps(orig)
    def inner(*args, **kwargs):
        call = dict(zip(names, args))
        call.update(kwargs)
        sess = SESSION
        if sess is None or call.get("name") == PLUGIN_ID:
            return orig(*args, **kwargs)
        choice = sess.ask_about_tool(
            call.get("translated_name", ""), call.get("category")
        )
        if choice == "cancel":
            return None
        if choice == "end" and not sess.end():
            return None
        return orig(*args, **kwargs)

    return inner


# ------------------------------------------------------------
# Open-editor guard
# ------------------------------------------------------------
EDITOR_CLASSES = (EditPrimary, EditSecondary, EditReference)


def _walk_windows(tree):
    for entry in tree:
        if isinstance(entry, list):
            yield from _walk_windows(entry)
        else:
            yield entry


def open_editor_titles(uistate):
    """
    Titles of the open record editors. Switching the database (session
    start or end) emits "database-changed", and EditPrimary closes on it
    without saving; its reference and secondary editors go with it.
    """
    gwm = getattr(uistate, "gwm", None)
    if gwm is None:
        return []
    seen = set()
    titles = []
    items = list(_walk_windows(getattr(gwm, "window_tree", [])))
    items.extend(getattr(gwm, "id2item", {}).values())
    for item in items:
        if id(item) in seen or not isinstance(item, EDITOR_CLASSES):
            continue
        seen.add(id(item))
        window = getattr(item, "window", None)
        title = window.get_title() if window is not None else ""
        titles.append(title or getattr(item, "titlelabel", "") or _("Editor"))
    return titles


def editors_block(uistate, action):
    """
    If record editors are open, explain and return True (do not switch).

    :param action: translated text naming what was refused
    """
    titles = open_editor_titles(uistate)
    if not titles:
        return False
    dialog = Gtk.MessageDialog(
        transient_for=uistate.window,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.OK,
        text=_("Close the open editors first"),
    )
    shown = titles[:10]
    if len(titles) > len(shown):
        shown.append(_("and %d more") % (len(titles) - len(shown)))
    dialog.format_secondary_text(
        _(
            "%(action)s reloads every view, and Gramps closes open editors "
            "without saving when that happens. Save or cancel these "
            "editors, then try again:"
        )
        % {"action": action}
        + "\n\n"
        + "\n".join("\u2022 " + title for title in shown)
    )
    dialog.run()
    dialog.destroy()
    return True


# ------------------------------------------------------------
# Session colors on detached gramplet windows
# ------------------------------------------------------------
# Detached gramplets are separate top-level windows, so the
# .pruned-branch class on the main window does not reach them. Names are
# checked as well as classes, in case another addon replaces a class.
GRAMPLET_WINDOW_CLASSES = (GrampletWindow, DetachedWindow)
GRAMPLET_WINDOW_NAMES = {"GrampletWindow", "DetachedWindow"}


def _is_gramplet_window(item):
    return isinstance(item, GRAMPLET_WINDOW_CLASSES) or any(
        cls.__name__ in GRAMPLET_WINDOW_NAMES for cls in type(item).__mro__
    )


def _gramplet_windows(uistate):
    gwm = getattr(uistate, "gwm", None)
    if gwm is None:
        return []
    items = list(_walk_windows(getattr(gwm, "window_tree", [])))
    items.extend(getattr(gwm, "id2item", {}).values())
    seen = set()
    found = []
    for item in items:
        if id(item) in seen or not _is_gramplet_window(item):
            continue
        seen.add(id(item))
        if getattr(item, "window", None) is not None:
            found.append(item.window)
    return found


def tint_gramplet_windows(uistate, on):
    """Add or remove the session class on every detached gramplet window."""
    for window in _gramplet_windows(uistate):
        context = window.get_style_context()
        if on:
            context.add_class("pruned-branch")
        else:
            context.remove_class("pruned-branch")


def _tint_new_windows(orig):
    """ManagedWindow.set_window: tint gramplets detached during a session."""

    @functools.wraps(orig)
    def inner(self, *args, **kwargs):
        result = orig(self, *args, **kwargs)
        try:
            if SESSION is not None and _is_gramplet_window(self):
                self.window.get_style_context().add_class("pruned-branch")
        except Exception:  # never break a window over colors
            LOG.debug("Pruned Branch: could not tint window", exc_info=True)
        return result

    return inner


def _install_patches():
    global _PATCHED
    if _PATCHED:
        return
    vm_class = gramps_viewmanager.ViewManager
    vm_class._ViewManager__backup = _full_tree(
        vm_class._ViewManager__backup, lambda self, args: self.dbstate
    )
    qb_class = gramps_viewmanager.QuickBackup
    qb_class.__init__ = _full_tree(
        qb_class.__init__, lambda self, args: args[0] if args else None
    )
    ExportAssistant.save = _full_tree(
        ExportAssistant.save, lambda self, args: getattr(self, "dbstate", None)
    )
    tool.gui_tool = _guard_gui_tool(tool.gui_tool)
    ManagedWindow.set_window = _tint_new_windows(ManagedWindow.set_window)
    _PATCHED = True
    LOG.info("Pruned Branch: patches installed")


# ------------------------------------------------------------
# BranchSession
# ------------------------------------------------------------
class BranchSession:
    """One limited editing session on the open tree."""

    def __init__(self, dbstate, uistate, people, label, strategy):
        self.dbstate = dbstate
        self.uistate = uistate
        self.real = dbstate.db
        self.people = people
        self.label = label
        self.sql_ok = is_sqlite(self.real)
        self.strategy = strategy if self.sql_ok else STRATEGY_PYTHON
        self.keep = None
        self.keep_tables = KeepTables(self.real) if self.sql_ok else None
        self.wrapper = None
        self.real_keys = []
        self.dbstate_key = None
        self.stats = {"build": {}, "switch": {}, "callbacks": CALLBACK_HISTORY}
        self._css = None
        self._user_css = None
        self._button = None
        self._orig_title = None

    def _record_callbacks(self, moment):
        CALLBACK_HISTORY.append(
            (
                moment,
                count_callbacks(self.real),
                count_callbacks(self.real, "long-op-start"),
            )
        )

    # --- start / end ------------------------------------------------
    def prepare(self):
        """
        Build the branch (keep sets, keep-tables, wrapper) without switching
        Gramps to it. start() uses this; so does a benchmark run while no
        session is active.
        """
        build = self.stats["build"]
        start = perf_counter()
        self.keep = compute_keep_sets(self.real, self.people)
        build["closure (ReferencedBy...)"] = perf_counter() - start
        if self.sql_ok:
            start = perf_counter()
            self.keep_tables.create(self.keep)
            build["TEMP keep-tables"] = perf_counter() - start
        self.wrapper = BranchDb(self.real, self.keep, self.strategy)

    def start(self):
        global SESSION
        self.prepare()

        active = self.uistate.get_active("Person")
        self._record_callbacks("before start")
        start = perf_counter()
        before = callback_keys(self.real)
        received = []
        probe = self.dbstate.connect(
            "database-changed", lambda db: received.append(db)
        )
        self.dbstate.change_database_noclose(self.wrapper)
        self.dbstate.signal_change()
        self.dbstate.disconnect(probe)
        self.stats["switch"]["start (to branch)"] = perf_counter() - start
        if not any(db is self.wrapper for db in received):
            # Gramps dropped the signal: views and gramplets would keep
            # showing the full tree while the window says "branch".
            LOG.error("Pruned Branch: Gramps did not accept the branch database")
            self.dbstate.change_database_noclose(self.real)
            self.dbstate.signal_change()
            if self.sql_ok:
                self.keep_tables.clear()
            raise RuntimeError(
                _("Gramps did not switch the views to the branch. "
                  "The session was not started.")
            )
        dropped = drop_duplicate_callbacks(self.real, before)
        LOG.debug("Pruned Branch: %d duplicate callbacks dropped", dropped)
        self._record_callbacks("after start")

        for table in TABLES:
            self.real_keys.append(
                self.real.connect(f"{table}-add", self._make_handler(self._on_add, table))
            )
            self.real_keys.append(
                self.real.connect(
                    f"{table}-delete", self._make_handler(self._on_delete, table)
                )
            )
        self.real_keys.append(
            self.real.connect("person-update", self._on_person_update)
        )
        self.real_keys.append(
            self.real.connect("family-update", self._on_family_update)
        )
        self.dbstate_key = self.dbstate.connect(
            "database-changed", self._on_database_changed
        )
        SESSION = self
        self._ui_on()
        if active:
            self.uistate.set_active(active, "Person")
        LOG.info(
            "Pruned Branch started: %s, %s",
            self.label,
            {t: len(h) for t, h in self.keep.items()},
        )
        _notify()

    @staticmethod
    def _make_handler(method, table):
        # Callback.emit() only calls plain functions and bound methods; it
        # skips functools.partial objects ("Badly formed entry").
        def handler(handles):
            method(table, handles)

        return handler

    def end(self, switch_back=True):
        """
        Leave the branch. switch_back=False when another tree was opened
        or the tree was closed (nothing to switch back to; Gramps has
        already closed the editors, so the open-editor guard is skipped).
        Return True when the session ended, False when open editors (or
        no matching session) kept it running.
        """
        global SESSION
        if SESSION is not self:
            return False
        if switch_back and editors_block(
            self.uistate, _("Ending the Pruned Branch session")
        ):
            return False
        SESSION = None
        active = self.uistate.get_active("Person")
        # Once SESSION is cleared, the red window, the status bar button and
        # the stylesheet must go whatever fails below; otherwise they stay
        # behind with nothing left to remove them (even after another tree
        # is opened).
        try:
            self._end_switch(switch_back)
        except Exception:
            LOG.exception("Pruned Branch: error while ending the session")
            if self.dbstate.db is self.wrapper:
                try:
                    self.dbstate.change_database_noclose(self.real)
                    self.dbstate.signal_change()
                except Exception:
                    LOG.exception("Pruned Branch: could not switch back")
        finally:
            try:
                self._ui_off(restore_title=switch_back)
            except Exception:
                LOG.exception("Pruned Branch: could not restore the window")
            _notify()
        if switch_back and active:
            self.uistate.set_active(active, "Person")
        LOG.info("Pruned Branch ended: %s", self.label)
        return True

    def _end_switch(self, switch_back):
        """Disconnect the session handlers and switch back to the real db."""
        if self.dbstate_key is not None:
            key, self.dbstate_key = self.dbstate_key, None
            self.dbstate.disconnect(key)
        keys, self.real_keys = self.real_keys, []
        for key in keys:
            self.real.disconnect(key)
        if switch_back and self.dbstate.db is self.wrapper:
            self._record_callbacks("before end")
            start = perf_counter()
            before = callback_keys(self.real)
            self.dbstate.change_database_noclose(self.real)
            self.dbstate.signal_change()
            self.stats["switch"]["end (to full tree)"] = perf_counter() - start
            dropped = drop_duplicate_callbacks(self.real, before)
            LOG.debug("Pruned Branch: %d duplicate callbacks dropped", dropped)
            self._record_callbacks("after end")
            if self.sql_ok and self.real.is_open():
                self.keep_tables.clear()

    def _on_database_changed(self, db):
        if db is self.wrapper or db is self.real:
            return  # our own switch
        # Another tree was opened or the tree was closed. End the session
        # right after this signal: ending disconnects this handler, and
        # removing a callback while DbState is still calling them makes
        # Gramps skip the next one (a view or gramplet would miss the new
        # tree).
        GLib.idle_add(self._end_after_tree_change)

    def _end_after_tree_change(self):
        self.end(switch_back=False)
        return False

    # --- keeping the branch current ---------------------------------------
    def _on_add(self, table, handles):
        keep = self.keep[table]
        new = [h for h in handles if h not in keep]
        if not new:
            return
        keep.update(new)
        if self.sql_ok:
            self.keep_tables.add(table, new)
        if table == "person":
            self._update_ui()

    def _on_delete(self, table, handles):
        keep = self.keep[table]
        gone = [h for h in handles if h in keep]
        if not gone:
            return
        keep.difference_update(gone)
        if self.sql_ok:
            self.keep_tables.remove(table, gone)
        if table == "person":
            self._update_ui()

    def _on_person_update(self, handles):
        families = set()
        for handle in handles:
            if handle in self.keep["person"]:
                person = self.real.get_person_from_handle(handle)
                if person:
                    families.update(person.get_family_handle_list())
                    families.update(person.get_parent_family_handle_list())
        self._on_add("family", list(families))

    def _on_family_update(self, handles):
        people = set()
        for handle in handles:
            if handle in self.keep["family"]:
                family = self.real.get_family_from_handle(handle)
                if family:
                    people.update(
                        h
                        for h in (family.get_father_handle(), family.get_mother_handle())
                        if h
                    )
                    people.update(ref.ref for ref in family.get_child_ref_list())
        self._on_add("person", list(people))

    # --- the obnoxious part -----------------------------------------------
    def _ui_on(self):
        win = self.uistate.window
        self._orig_title = win.get_title()
        self.reload_css()
        win.get_style_context().add_class("pruned-branch")
        tint_gramplet_windows(self.uistate, True)
        self._button = Gtk.Button()
        self._button.get_style_context().add_class("pruned-branch-alert")
        self._button.set_tooltip_text(_("Click to return to the full tree"))
        self._button.connect("clicked", lambda *obj: self.end())
        status = self.uistate.status
        # Center the button; the status message stays at the left and the
        # filter count at the right (the Gramps Statusbar is a Gtk.Box).
        if hasattr(status, "set_center_widget"):
            status.set_center_widget(self._button)
        else:
            status.pack_start(self._button, False, False, 6)
            status.reorder_child(self._button, 0)
        self._button.show()
        self._update_ui()

    def reload_css(self):
        """(Re)load both session stylesheets; changes show at once."""
        screen = self.uistate.window.get_screen()
        self._remove_css()
        self._css = load_css(CSS_FILE)
        self._user_css = load_css(USER_CSS_FILE, quiet=True)
        for provider, priority in (
            (self._css, CSS_PRIORITY),
            (self._user_css, USER_CSS_PRIORITY),
        ):
            if provider is not None:
                Gtk.StyleContext.add_provider_for_screen(screen, provider, priority)
        LOG.info(
            "Pruned Branch: colors from %s%s",
            CSS_FILE,
            " + " + USER_CSS_FILE if self._user_css else "",
        )

    def _remove_css(self):
        screen = self.uistate.window.get_screen()
        for attr in ("_css", "_user_css"):
            provider = getattr(self, attr)
            if provider is not None:
                Gtk.StyleContext.remove_provider_for_screen(screen, provider)
                setattr(self, attr, None)

    def _update_ui(self):
        if self._button is None:
            return
        text = _("PRUNED BRANCH: %(label)s (%(count)s of %(total)s people)") % {
            "label": self.label,
            "count": f"{len(self.keep['person']):,}",
            "total": f"{self.real.get_number_of_people():,}",
        }
        self.uistate.window.set_title(f"\u26d4 {text} \u26d4 {self._orig_title}")
        self._button.set_label(
            "\u26d4 " + text + "  " + _("Click for full tree")
        )

    def _ui_off(self, restore_title=True):
        win = self.uistate.window
        win.get_style_context().remove_class("pruned-branch")
        tint_gramplet_windows(self.uistate, False)
        self._remove_css()
        if self._button is not None:
            status = self.uistate.status
            if (
                hasattr(status, "get_center_widget")
                and status.get_center_widget() is self._button
            ):
                status.set_center_widget(None)
            self._button.destroy()
            self._button = None
        if restore_title and self._orig_title:
            win.set_title(self._orig_title)

    # --- tool launch guard --------------------------------------------------
    def ask_about_tool(self, tool_name, category):
        """Return "cancel", "end" or "run"."""
        dialog = Gtk.MessageDialog(
            transient_for=self.uistate.window,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text=_("A Pruned Branch session is active"),
        )
        if category == TOOL_DBFIX:
            dialog.format_secondary_text(
                _(
                    "'%s' repairs the whole Family Tree and cannot run on "
                    "a branch. End the Pruned Branch session first?"
                )
                % tool_name
            )
        else:
            dialog.format_secondary_text(
                _(
                    "'%(tool)s' would only see the branch "
                    "(%(count)s people). Run it on the branch, or end the "
                    "session and run it on the full tree?"
                )
                % {"tool": tool_name, "count": f"{len(self.keep['person']):,}"}
            )
        dialog.add_button(_("Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("End branch, then run"), 1)
        if category != TOOL_DBFIX:
            dialog.add_button(_("Run on branch"), 2)
        response = dialog.run()
        dialog.destroy()
        return {1: "end", 2: "run"}.get(response, "cancel")


# ------------------------------------------------------------
# Tool dialog
# ------------------------------------------------------------
class PrunedBranchOptions(tool.ToolOptions):
    """No stored options yet."""


class PrunedBranchTool(tool.Tool, ManagedWindow):
    """Start, end and benchmark a Pruned Branch session."""

    def __init__(self, dbstate, user, options_class, name, callback=None):
        self.user = user
        self.uistate = user.uistate
        self.dbstate = dbstate
        self.sources = []
        tool.Tool.__init__(self, dbstate, options_class, name)
        ManagedWindow.__init__(self, self.uistate, [], self.__class__)
        self._build()
        LISTENERS.add(self._refresh)
        self._refresh()
        self.show()

    def build_menu_names(self, obj):
        return (_("Pruned Branch"), None)

    def close(self, *obj):
        LISTENERS.discard(self._refresh)
        ManagedWindow.close(self, *obj)

    # --- layout ----------------------------------------------------------
    def _build(self):
        window = Gtk.Dialog()
        window.set_default_size(820, 560)
        area = window.get_content_area()
        area.set_spacing(6)
        area.set_border_width(6)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_line_wrap(True)
        area.pack_start(self.status_label, False, False, 0)

        grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        grid.attach(Gtk.Label(label=_("People:"), xalign=0), 0, 0, 1, 1)
        self.source_combo = Gtk.ComboBoxText(hexpand=True)
        self.source_combo.set_row_separator_func(self._is_separator)
        grid.attach(self.source_combo, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=_("Listing method:"), xalign=0), 0, 1, 1, 1)
        self.strategy_combo = Gtk.ComboBoxText()
        self.strategy_combo.append(STRATEGY_SQL, _("SQL keep-table join"))
        self.strategy_combo.append(STRATEGY_PYTHON, _("Python, one read per record"))
        self.strategy_combo.set_active_id(STRATEGY_SQL)
        self.strategy_combo.connect("changed", self.cb_strategy_changed)
        grid.attach(self.strategy_combo, 1, 1, 1, 1)
        area.pack_start(grid, False, False, 0)

        buttons = Gtk.Box(spacing=6)
        self.start_btn = Gtk.Button(label=_("Start branch"))
        self.start_btn.connect("clicked", self.cb_start)
        self.end_btn = Gtk.Button(label=_("End branch"))
        self.end_btn.connect("clicked", self.cb_end)
        self.bench_btn = Gtk.Button(label=_("Run benchmark"))
        self.bench_btn.set_tooltip_text(
            _("Times the full tree against the branch. With no session "
              "active, a trial branch is built from the People choice "
              "without switching to it. The People choice is also timed "
              "as a filter.")
        )
        self.bench_btn.connect("clicked", self.cb_benchmark)
        self.colors_btn = Gtk.ToggleButton(label=_("Customize colors"))
        self.colors_btn.set_tooltip_text(
            _("Show the session colors in the bottom panel instead of the report")
        )
        self.colors_btn.connect("toggled", self.cb_customize_colors)
        copy_btn = Gtk.Button(label=_("Copy report"))
        copy_btn.connect("clicked", self.cb_copy)
        close_btn = Gtk.Button(label=_("Close"))
        close_btn.connect("clicked", self.close)
        for btn in (
            self.start_btn,
            self.end_btn,
            self.bench_btn,
            copy_btn,
            self.colors_btn,
        ):
            buttons.pack_start(btn, False, False, 0)
        buttons.pack_end(close_btn, False, False, 0)
        area.pack_start(buttons, False, False, 0)

        self.report = Gtk.TextView(editable=False, monospace=True)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.add(self.report)
        self.bottom = Gtk.Stack()
        self.bottom.add_named(scroll, "report")
        self.bottom.add_named(self._build_colors(), "colors")
        area.pack_start(self.bottom, True, True, 0)

        self.set_window(window, None, _("Pruned Branch"))
        self._load_sources()

    def _build_colors(self):
        """The color panel: one swatch per base color, plus file links."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(6)
        intro = Gtk.Label(xalign=0)
        intro.set_line_wrap(True)
        intro.set_text(
            _("Every other session color is mixed from these five. Changes "
              "are saved at once and show right away during a session.")
        )
        box.pack_start(intro, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        self.swatches = {}
        for row, (name, label) in enumerate(BASE_COLORS):
            swatch = Gtk.ColorButton()
            swatch.set_use_alpha(False)
            swatch.set_title(label)
            swatch.connect("color-set", self.cb_color_set)
            self.swatches[name] = swatch
            grid.attach(swatch, 0, row, 1, 1)
            grid.attach(Gtk.Label(label=label, xalign=0), 1, row, 1, 1)
            css_name = Gtk.Label(label=name, xalign=0)
            css_name.get_style_context().add_class("dim-label")
            grid.attach(css_name, 2, row, 1, 1)
        box.pack_start(grid, False, False, 0)

        reset = Gtk.Button(label=_("Restore default colors"))
        reset.set_halign(Gtk.Align.START)
        reset.set_tooltip_text(
            _("Remove the swatch colors from %s. Your own lines in it are kept.")
            % os.path.basename(USER_CSS_FILE)
        )
        reset.connect("clicked", self.cb_restore_colors)
        box.pack_start(reset, False, False, 0)

        links = Gtk.Label(xalign=0)
        links.set_line_wrap(True)
        links.set_markup(
            _("Edit a stylesheet in your text editor: "
              "<a href=\"%(user_uri)s\">%(user)s</a> (your changes, kept by "
              "addon updates) or <a href=\"%(main_uri)s\">%(main)s</a> (the "
              "default, replaced by addon updates).\n"
              "Text edits apply the next time a session starts.")
            % {
                "user_uri": "pb-user",
                "user": os.path.basename(USER_CSS_FILE),
                "main_uri": "pb-main",
                "main": os.path.basename(CSS_FILE),
            }
        )
        links.connect("activate-link", self.cb_open_stylesheet)
        box.pack_start(links, False, False, 0)
        self._load_swatches()
        return box

    def _load_swatches(self):
        """Show the effective color of each swatch: user file, else default."""
        colors = defined_colors(CSS_FILE)
        colors.update(defined_colors(USER_CSS_FILE))
        for name, swatch in self.swatches.items():
            rgba = Gdk.RGBA()
            if not rgba.parse(colors.get(name, "")):
                rgba.parse("#808080")  # not a plain color (e.g. a mix())
            swatch.set_rgba(rgba)

    def _load_sources(self):
        """
        Fill the People list: the tags last used for this tree (newest
        first, the newest one selected), a separator, the other tags, a
        separator, then the Person custom filters.
        """
        real = SESSION.real if SESSION else self.dbstate.db
        self.sources = []
        self.source_combo.remove_all()
        tags = {tag.get_handle(): tag.get_name() for tag in real.iter_tags()}
        recent = [h for h in recent_tag_handles(real) if h in tags]
        for handle in recent:
            name = tags[handle]
            self.sources.append(("tag", (handle, name), _("Tag: %s") % name))
        others = sorted(
            (h for h in tags if h not in recent), key=lambda h: tags[h].lower()
        )
        if recent and others:
            self.sources.append(("separator", None, ""))
        for handle in others:
            name = tags[handle]
            self.sources.append(("tag", (handle, name), _("Tag: %s") % name))
        if gfilters.CustomFilters is None:
            gfilters.reload_custom_filters()
        person_filters = gfilters.CustomFilters.get_filters("Person")
        if tags and person_filters:
            self.sources.append(("separator", None, ""))
        for filt in person_filters:
            self.sources.append(
                ("filter", filt, _("Filter: %s") % filt.get_name())
            )
        for _kind, _value, label in self.sources:
            self.source_combo.append_text(label)
        if self.sources:
            self.source_combo.set_active(0)

    def _is_separator(self, _model, tree_iter):
        index = _model.get_path(tree_iter).get_indices()[0]
        return (
            index < len(self.sources) and self.sources[index][0] == "separator"
        )

    def _selected_filter(self):
        index = self.source_combo.get_active()
        if index < 0:
            return None, ""
        kind, value, label = self.sources[index]
        if kind == "separator":
            return None, ""
        if kind == "tag":
            filt = GenericFilter()
            filt.set_name(label)
            filt.add_rule(HasTag([value[1]]))
            return filt, label
        return value, label

    def _refresh(self):
        if SESSION:
            counts = ", ".join(
                f"{table} {len(handles):,}" for table, handles in SESSION.keep.items()
            )
            method = (
                _("SQL keep-table join")
                if SESSION.sql_ok
                else _("Python only (not SQLite)")
            )
            self.status_label.set_markup(
                "<b>%s</b> %s\n%s\n%s"
                % (
                    _("Pruned Branch ACTIVE:"),
                    SESSION.label,
                    counts,
                    _("Available listing method: %s") % method,
                )
            )
        else:
            self.status_label.set_markup(
                "<b>%s</b> %s"
                % (_("Full tree."), _("Choose people, then Start branch."))
            )
        self.start_btn.set_sensitive(SESSION is None)
        self.end_btn.set_sensitive(SESSION is not None)
        self.bench_btn.set_sensitive(self.dbstate.is_open())

    # --- callbacks -------------------------------------------------------
    def _write(self, line):
        if self.colors_btn.get_active():
            self.colors_btn.set_active(False)  # show the report again
        buf = self.report.get_buffer()
        buf.insert(buf.get_end_iter(), line + "\n")
        LOG.info("PrunedBranch bench: %s", line)
        while Gtk.events_pending():
            Gtk.main_iteration()

    def cb_start(self, *obj):
        if SESSION is not None:
            return
        filt, label = self._selected_filter()
        if filt is None:
            return
        if editors_block(self.uistate, _("Starting a Pruned Branch session")):
            return
        _install_patches()
        self.uistate.set_busy_cursor(True)
        try:
            start = perf_counter()
            people = filt.apply(self.dbstate.db, user=self.user)
            apply_time = perf_counter() - start
            if not people:
                self._write(_("No people match %s; nothing started.") % label)
                return
            session = BranchSession(
                self.dbstate,
                self.uistate,
                people,
                label,
                self.strategy_combo.get_active_id(),
            )
            session.stats["build"]["people filter apply"] = apply_time
            try:
                session.start()
            except RuntimeError as err:
                self._write(str(err))
                ErrorDialog(_("Pruned Branch"), str(err), parent=self.window)
            else:
                kind, value, _label = self.sources[self.source_combo.get_active()]
                if kind == "tag":
                    remember_tag(session.real, value[0])
                    self._load_sources()
        finally:
            self.uistate.set_busy_cursor(False)

    def cb_end(self, *obj):
        if SESSION is not None:
            SESSION.end()

    def cb_strategy_changed(self, *obj):
        if SESSION is not None and SESSION.wrapper is not None:
            wanted = self.strategy_combo.get_active_id()
            if wanted == STRATEGY_SQL and not SESSION.sql_ok:
                wanted = STRATEGY_PYTHON
            SESSION.wrapper._pb_strategy = wanted

    def cb_benchmark(self, *obj):
        """
        Benchmark the active session, or, with no session active, a trial
        branch built from the People choice. The trial branch is never
        shown: Gramps stays on the full tree, and its keep-tables are
        emptied afterward.
        """
        filt, label = self._selected_filter()
        if SESSION is None and filt is None:
            self._write(_("Choose a tag or filter in People first."))
            return
        self.report.get_buffer().set_text("")
        self.uistate.set_busy_cursor(True)
        trial = None
        try:
            if SESSION is not None:
                run_benchmark(SESSION, filt, label, self._write)
                return
            start = perf_counter()
            people = filt.apply(self.dbstate.db, user=self.user)
            apply_time = perf_counter() - start
            if not people:
                self._write(_("No people match %s; nothing to measure.") % label)
                return
            trial = BranchSession(
                self.dbstate,
                self.uistate,
                people,
                label,
                self.strategy_combo.get_active_id(),
            )
            trial.stats["build"]["people filter apply"] = apply_time
            trial.prepare()
            run_benchmark(trial, filt, label, self._write, trial=True)
        except Exception:
            LOG.error("Pruned Branch benchmark failed", exc_info=True)
            self._write(_("Benchmark failed; see the terminal for the traceback."))
        finally:
            if trial is not None and trial.sql_ok and SESSION is None:
                trial.keep_tables.clear()
            self.uistate.set_busy_cursor(False)

    def cb_copy(self, *obj):
        buf = self.report.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)

    def cb_customize_colors(self, *obj):
        if self.colors_btn.get_active():
            self._load_swatches()  # the user file may have been edited
            self.bottom.set_visible_child_name("colors")
        else:
            self.bottom.set_visible_child_name("report")

    def _save_colors(self):
        defaults = defined_colors(CSS_FILE)
        chosen = {}
        for name, swatch in self.swatches.items():
            rgba = swatch.get_rgba()
            value = "#%02x%02x%02x" % tuple(
                round(c * 255) for c in (rgba.red, rgba.green, rgba.blue)
            )
            if value.lower() != defaults.get(name, "").lower():
                chosen[name] = value
        try:
            save_user_colors(chosen)
        except OSError as err:
            ErrorDialog(_("Pruned Branch"), str(err), parent=self.window)
            return
        if SESSION is not None:
            SESSION.reload_css()

    def cb_color_set(self, *obj):
        self._save_colors()

    def cb_restore_colors(self, *obj):
        try:
            save_user_colors({})
        except OSError as err:
            ErrorDialog(_("Pruned Branch"), str(err), parent=self.window)
            return
        self._load_swatches()
        if SESSION is not None:
            SESSION.reload_css()

    def cb_open_stylesheet(self, _label, uri):
        if uri == "pb-user":
            try:
                ensure_user_css()
            except OSError as err:
                ErrorDialog(_("Pruned Branch"), str(err), parent=self.window)
                return True
            path = USER_CSS_FILE
        else:
            path = CSS_FILE
        open_file_with_default_application(path, self.uistate)
        return True  # handled; do not let GTK open the link itself
