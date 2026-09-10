# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Claude Sonnet 5
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
Tools > Debug > Config Inspector.

A general-purpose inspector for Gramps' various on-disk configuration
and layout caches, each of which gets its own tab in this tool's
window. Every tab is independent: its own listing, its own "what does
this cache versus what's currently true" comparison where one makes
sense, and its own confirmed flush action - a flush on one tab must
never touch what another tab manages, since the underlying files and
what "stale" means differ per cache.

The first tab, :class:`GrampletContainersTab`, covers the gramplet
layout .ini files described in the module-level docstring of that
class below. A second tab inspecting/flushing ``gramps.ini`` chunks is
the next planned addition (see the comment beside
:meth:`ConfigInspector._build_notebook` for where it plugs in) - not
implemented yet, so this module does not reference it.

Adding a further tab later means writing one more :class:`_InspectorTab`
subclass and appending it in :meth:`ConfigInspector._build_notebook`;
nothing about :class:`ConfigInspector` itself, or about
:class:`GrampletContainersTab`, needs to change to accommodate it.
"""

# ------------------------
# Python modules
# ------------------------
import configparser
import glob
import logging
import os

# ------------------------
# Gtk modules
# ------------------------
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import VERSION_DIR
from gramps.gen.plug import PluginRegister
from gramps.gui.dialog import OkDialog, QuestionDialog
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.plug import tool
from gramps.gui.utils import open_file_with_default_application

_ = glocale.translation.sgettext

LOG = logging.getLogger(__name__)


def _open_in_text_editor(path, uistate=None):
    """
    Open ``path`` in whatever the OS has configured as the default
    application for plain text (``text/plain``) - deliberately not
    whatever is associated with the file's own extension, since a
    .py/.gpr.py file's extension-based default is typically a code
    editor or IDE, not a quick-look text viewer, which is the whole
    point of this being a distinct helper rather than a call to
    :func:`gramps.gui.utils.open_file_with_default_application`.

    :param path: The file to open.
    :param uistate: Passed through to the fallback opener, if used.
    """
    if not os.path.exists(path):
        OkDialog(
            _("File not found"),
            path,
            parent=uistate.window if uistate else None,
        )
        return

    app_info = None
    try:
        app_info = Gio.AppInfo.get_default_for_type("text/plain", False)
    except GLib.Error:
        LOG.debug("Config Inspector: no default text/plain handler", exc_info=True)

    if app_info is not None:
        try:
            app_info.launch([Gio.File.new_for_path(path)], None)
            return
        except GLib.Error:
            LOG.warning(
                "Config Inspector: failed launching %s for %s, falling back",
                app_info.get_name(),
                path,
                exc_info=True,
            )

    # Only reached if no text/plain default application could be found
    # or launched at all - better than nothing, even though the OS
    # default for this specific file may not be a text editor.
    open_file_with_default_application(path, uistate)


def _find_gpr_file_for_plugin(pdata):
    """
    Best-effort: find the ``.gpr.py`` file that most likely registered
    ``pdata``.

    Gramps' own plugin scanner (``PluginRegister.scan_dir``) does not
    record which ``.gpr.py`` file produced a given
    :class:`~gramps.gen.plug._pluginreg.PluginData` - it just execs
    every ``.gpr.py`` in a directory and collects whatever
    ``register()`` calls happen inside. This function relies on the
    overwhelmingly common convention (used by every module in this
    addon, and most Gramps addons generally, though nothing enforces
    it) that a plugin's ``.gpr.py`` shares its base filename with its
    own module file, falling back to a plain substring search of every
    ``.gpr.py`` in that directory for this plugin's own id if that
    convention does not hold.

    :param pdata: A :class:`~gramps.gen.plug._pluginreg.PluginData`,
        or ``None``.
    :returns: A path, or ``None`` if nothing plausible was found.
    """
    if pdata is None or not pdata.fpath:
        return None

    base = os.path.splitext(pdata.fname or "")[0]
    candidate = os.path.join(pdata.fpath, base + ".gpr.py")
    if os.path.isfile(candidate):
        return candidate

    needle_double = 'id="%s"' % pdata.id
    needle_single = "id='%s'" % pdata.id
    for candidate in glob.glob(os.path.join(pdata.fpath, "*.gpr.py")):
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        if needle_double in text or needle_single in text:
            return candidate
    return None


def _rewrite_help_url_line(path, section, new_value):
    """
    Replace only the ``help_url=`` line within ``[section]`` of
    ``path``, leaving everything else in the file - including
    comments, key order, and every other section - untouched.

    A plain line-level rewrite rather than a
    :class:`configparser.ConfigParser` round-trip (read, mutate,
    ``write()``) deliberately: ``ConfigParser.write()`` does not
    preserve comments or the original ``;;``-style header these files
    use, so it would reformat the whole file as a side effect of
    fixing one value - too destructive for what should be a narrowly
    scoped fix.

    :param path: The .ini file to edit.
    :param section: The section name the ``help_url=`` line must be
        inside.
    :param new_value: The value to write.
    :returns: True if a line was found and replaced, False otherwise.
    """
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    in_section = False
    replaced = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_section = stripped[1:-1] == section
            continue
        if in_section and stripped.startswith("help_url="):
            lines[index] = "help_url=%s\n" % new_value
            replaced = True
            break

    if replaced:
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
    return replaced


# ------------------------------------------------------------
#
# _InspectorTab
#
# ------------------------------------------------------------
class _InspectorTab(Gtk.Box):
    """
    Base class for one tab of the Config Inspector.

    A tab owns exactly one concern (one kind of cached/on-disk
    configuration) and exposes :meth:`build_view`, :meth:`refresh`,
    and :meth:`flush_all` for this base class to call. Column shapes,
    renderers, per-cell coloring, icons, and double-click behavior
    differ enough between tabs (and are expected to differ even more
    once a second tab exists) that this base class does not prescribe
    any of it - it only owns the chrome every tab shares: a scrolled
    listing on top, a flush button below it.
    """

    #: Subclasses must set this to the label shown on the tab itself.
    tab_title = ""

    #: Subclasses must set this to the text shown on their flush
    #: button - phrased for what that tab actually flushes, since
    #: "Flush All Listed Files" does not make sense for every future
    #: tab (a gramps.ini chunk tab might flush chunks, not files).
    flush_button_label = _("Flush")

    def __init__(self, parent_window):
        """
        :param parent_window: The owning :class:`Gtk.Window`, used
            only to parent this tab's own confirmation/result dialogs.
        """
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)
        self._parent_window = parent_window

        self.view = self.build_view()

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.add(self.view)
        self.pack_start(scrolled, True, True, 0)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_halign(Gtk.Align.END)
        flush_button = Gtk.Button(label=self.flush_button_label)
        flush_button.connect("clicked", lambda _button: self.flush_all())
        button_box.pack_start(flush_button, False, False, 0)
        self.pack_start(button_box, False, False, 0)

        self.refresh()
        self.show_all()

    def build_view(self):
        """
        Build and return this tab's fully configured
        :class:`Gtk.TreeView` - model, columns, renderers, sorting,
        and any signal connections (for example row-activation for
        double-click behavior) all belong here. Subclasses must
        implement this.
        """
        raise NotImplementedError

    def refresh(self):
        """Clear and repopulate this tab's model. Subclasses must implement."""
        raise NotImplementedError

    def flush_all(self):
        """Confirm, then perform this tab's flush. Subclasses must implement."""
        raise NotImplementedError


# ------------------------------------------------------------
#
# GrampletContainersTab
#
# ------------------------------------------------------------
class GrampletContainersTab(_InspectorTab):
    """
    Lists every gramplet entry cached in this profile's saved
    dashboard, sidebar, and bottombar layout .ini files, and can flush
    all of them at once.

    Every dashboard "Gramplets" view page and every GrampletBar-hosted
    sidebar/bottombar saves its own gramplet layout to a small .ini
    file under the active profile directory (``VERSION_DIR``) the
    first time a gramplet is added, and never re-reads that gramplet's
    current .gpr.py registration again for that saved instance - only
    a genuine remove and re-add refreshes it (confirmed directly
    against ``gramps.gui.widgets.grampletbar.GrampletBar.__load``/
    ``__save`` and the equivalent dashboard-view save code, not
    assumed). That is by design, but it means a stale cached value (a
    leftover ``help_url`` from an earlier draft of an addon's .gpr.py,
    for example) can silently persist indefinitely, and there is no
    built-in way to see what is cached without opening each .ini file
    by hand and knowing which one belongs to which view.

    This tab finds every such file, lists what it has cached (per
    gramplet, per file), compares each cached value against what is
    *currently* registered for that same plugin id (via
    :class:`gramps.gen.plug.PluginRegister`) so a stale entry is
    visible at a glance, and can delete every listed file in one
    confirmed action - after which every affected view rebuilds its
    gramplet layout (default gramplets only) fresh, the next time that
    view is opened.

    A file is treated as a candidate if it lives directly under
    ``VERSION_DIR`` and has at least one section (other than the small
    set of known non-gramplet section names) with its own ``name=``
    key - the same key ``GrampletBar.__save()`` (and the dashboard
    view's equivalent) writes to identify which registered gramplet a
    section describes. This is deliberately structural rather than a
    hardcoded filename list, so it does not need updating if Gramps
    adds another gramplet-hosting view type with its own naming
    convention.
    """

    tab_title = _("Gramplet Containers")
    flush_button_label = _("Flush All Listed Files")

    #: Section names that can appear in a gramplet-bar/gramplet-pane
    #: .ini file but are not themselves a gramplet entry, so must not
    #: be listed or counted as one even though they satisfy the "not
    #: the gramplet itself" half of the structural check below.
    _NON_GRAMPLET_SECTIONS = {"Bar Options", "Options"}

    #: Store column indices, named for readability at every call site
    #: below instead of bare integers.
    _COL_CONTAINER = 0  # display: basename of the .ini file
    _COL_GRAMPLET = 1  # display: gramplet id
    _COL_CACHED_URL = 2  # display: cached help_url
    _COL_LIVE_URL = 3  # display: currently registered help_url
    _COL_STALE = 4  # hidden: bool, drives coloring/icon/sort
    _COL_ICON = 5  # hidden: refresh-icon Pixbuf, or None
    _COL_PATH = 6  # hidden: full path to the .ini file
    _COL_SECTION = 7  # hidden: section name within that .ini file

    #: Pixel size for the "Stale" column's refresh icon.
    _STALE_ICON_SIZE = 16

    def build_view(self):
        store = Gtk.ListStore(str, str, str, str, bool, GdkPixbuf.Pixbuf, str, str)
        self._store = store
        self._stale_icon = self._load_stale_icon()

        view = Gtk.TreeView(model=store)

        gramplet_renderer = Gtk.CellRendererText()
        gramplet_column = Gtk.TreeViewColumn(
            _("Gramplet"), gramplet_renderer, text=self._COL_GRAMPLET
        )
        gramplet_column.set_resizable(True)
        gramplet_column.set_sort_column_id(self._COL_GRAMPLET)
        view.append_column(gramplet_column)

        icon_renderer = Gtk.CellRendererPixbuf()
        stale_column = Gtk.TreeViewColumn(_("Stale"), icon_renderer, pixbuf=self._COL_ICON)
        stale_column.set_sort_column_id(self._COL_STALE)
        view.append_column(stale_column)
        self._stale_column = stale_column

        container_renderer = Gtk.CellRendererText()
        container_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        container_column = Gtk.TreeViewColumn(
            _("View mode container"), container_renderer, text=self._COL_CONTAINER
        )
        container_column.set_resizable(True)
        container_column.set_sort_column_id(self._COL_CONTAINER)
        view.append_column(container_column)
        self._container_column = container_column

        cached_renderer = Gtk.CellRendererText()
        cached_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        cached_renderer.set_property("foreground", "red")
        cached_column = Gtk.TreeViewColumn(
            _("Cached help_url"), cached_renderer, text=self._COL_CACHED_URL
        )
        cached_column.add_attribute(cached_renderer, "foreground-set", self._COL_STALE)
        cached_column.set_resizable(True)
        cached_column.set_expand(True)
        cached_column.set_sort_column_id(self._COL_CACHED_URL)
        view.append_column(cached_column)

        live_renderer = Gtk.CellRendererText()
        live_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        live_renderer.set_property("foreground", "red")
        live_column = Gtk.TreeViewColumn(
            _("Registered help_url"), live_renderer, text=self._COL_LIVE_URL
        )
        live_column.add_attribute(live_renderer, "foreground-set", self._COL_STALE)
        live_column.set_resizable(True)
        live_column.set_expand(True)
        live_column.set_sort_column_id(self._COL_LIVE_URL)
        view.append_column(live_column)
        self._live_column = live_column

        view.connect("row-activated", self._cb_row_activated)
        return view

    @staticmethod
    def _load_stale_icon(size=_STALE_ICON_SIZE):
        """
        Load the "view-refresh-symbolic" icon (present in the Adwaita
        icon theme) for the Stale column.

        :returns: A :class:`GdkPixbuf.Pixbuf`, or ``None`` if the icon
            theme has no such icon - the Stale column simply shows
            nothing for any row in that case, rather than raising.
        """
        icon_theme = Gtk.IconTheme.get_default()
        try:
            return icon_theme.load_icon(
                "view-refresh-symbolic", size, Gtk.IconLookupFlags.FORCE_SIZE
            )
        except GLib.Error:
            LOG.debug("Config Inspector: no view-refresh-symbolic icon", exc_info=True)
            return None

    def _cb_row_activated(self, view, path, column):
        """
        Dispatch a double-click (or Enter-key activation) to whichever
        of the three double-clickable columns it happened on.

        :param view: This tab's :class:`Gtk.TreeView`.
        :param path: The activated row's :class:`Gtk.TreePath`.
        :param column: The activated :class:`Gtk.TreeViewColumn`.
        """
        row = self._store[path]
        if column is self._container_column:
            _open_in_text_editor(row[self._COL_PATH])
        elif column is self._live_column:
            self._open_gpr_file(row[self._COL_GRAMPLET])
        elif column is self._stale_column:
            if row[self._COL_STALE]:
                self._refresh_stale_row(
                    row[self._COL_PATH], row[self._COL_SECTION], row[self._COL_LIVE_URL]
                )

    def _open_gpr_file(self, gramplet_id):
        """
        Open the ``.gpr.py`` that registers ``gramplet_id`` in a text
        editor, or report that none could be found.

        :param gramplet_id: A plugin id, as found in a section's
            ``name=`` value.
        """
        pdata = PluginRegister.get_instance().get_plugin(gramplet_id)
        gpr_path = _find_gpr_file_for_plugin(pdata)
        if gpr_path is None:
            OkDialog(
                _("Registration file not found"),
                _("Could not determine which .gpr.py file registers %s.")
                % gramplet_id,
                parent=self._parent_window,
            )
            return
        _open_in_text_editor(gpr_path)

    def _refresh_stale_row(self, path, section, live_value):
        """
        Overwrite the cached ``help_url=`` for one section with the
        currently registered value, then re-list everything.

        :param path: The .ini file containing ``section``.
        :param section: The section whose ``help_url=`` is stale.
        :param live_value: The value to write in its place.
        """
        if _rewrite_help_url_line(path, section, live_value):
            self.refresh()
        else:
            OkDialog(
                _("Could not update"),
                _("No help_url= line was found to update in that section."),
                parent=self._parent_window,
            )

    def _find_candidate_files(self):
        """
        Find every saved gramplet-layout .ini file directly under
        ``VERSION_DIR``.

        :returns: A list of ``(path, parser, gramplet_sections)``
            tuples, one per file that has at least one qualifying
            section - ``parser`` is the already-populated
            :class:`configparser.ConfigParser` for that file, so
            callers do not need to re-read it, and
            ``gramplet_sections`` is the list of section names within
            it that describe a gramplet.
        """
        candidates = []
        for path in sorted(glob.glob(os.path.join(VERSION_DIR, "*.ini"))):
            parser = configparser.ConfigParser()
            try:
                parser.read(path, encoding="utf-8")
            except (OSError, UnicodeDecodeError, configparser.Error):
                continue
            gramplet_sections = [
                section
                for section in parser.sections()
                if section not in self._NON_GRAMPLET_SECTIONS
                and parser.has_option(section, "name")
            ]
            if gramplet_sections:
                candidates.append((path, parser, gramplet_sections))
        return candidates

    def refresh(self):
        self._store.clear()
        registry = PluginRegister.get_instance()
        candidates = self._find_candidate_files()
        self._paths = [path for path, _parser, _sections in candidates]

        for path, parser, sections in candidates:
            for section in sections:
                gramplet_id = parser.get(section, "name").strip()
                cached_help_url = (
                    parser.get(section, "help_url").strip()
                    if parser.has_option(section, "help_url")
                    else ""
                )
                pdata = registry.get_plugin(gramplet_id)
                live_help_url = getattr(pdata, "help_url", "") or ""
                is_stale = bool(live_help_url) and cached_help_url != live_help_url
                self._store.append(
                    [
                        os.path.basename(path),
                        gramplet_id,
                        cached_help_url,
                        live_help_url,
                        is_stale,
                        self._stale_icon if is_stale else None,
                        path,
                        section,
                    ]
                )

        if not candidates:
            self._store.append(
                [_("(no cached gramplet layouts found)"), "", "", "", False, None, "", ""]
            )

    def flush_all(self):
        """
        Confirm, then delete every file recorded in :attr:`_paths`.

        A single confirmation covers every listed file, not a separate
        prompt per file.
        """
        if not self._paths:
            OkDialog(
                _("Nothing to flush"),
                _("No cached gramplet-layout files were found."),
                parent=self._parent_window,
            )
            return

        listing = "\n".join(sorted(os.path.basename(p) for p in self._paths))
        QuestionDialog(
            _("Flush all listed .ini files?"),
            _(
                "This deletes the following files. Every dashboard, "
                "sidebar, and bottombar gramplet layout they describe "
                "will be rebuilt from scratch (default gramplets only) "
                "the next time Gramps opens the affected view. This "
                "cannot be undone.\n\n"
            )
            + listing,
            _("_Flush"),
            self._do_flush,
            parent=self._parent_window,
        )

    def _do_flush(self):
        """Actually delete every path in :attr:`_paths`, after confirmation."""
        errors = []
        for path in self._paths:
            try:
                os.remove(path)
            except OSError as err:
                errors.append("%s: %s" % (os.path.basename(path), err))

        if errors:
            OkDialog(
                _("Some files could not be flushed"),
                "\n".join(errors),
                parent=self._parent_window,
            )
        else:
            OkDialog(
                _("Flushed"),
                _(
                    "All listed files were deleted. Restart Gramps for "
                    "every affected view to rebuild its gramplet layout."
                ),
                parent=self._parent_window,
            )
        self.refresh()


# ------------------------------------------------------------
#
# ConfigInspector
#
# ------------------------------------------------------------
class ConfigInspector(ManagedWindow, tool.Tool):
    """
    Tabbed window hosting every :class:`_InspectorTab`. Owns only the
    window chrome (title, Close button, the :class:`Gtk.Notebook`
    itself) - all actual inspecting/flushing behavior lives in each
    tab.
    """

    def __init__(self, dbstate, user, options_class, name, callback=None):
        """
        Build and show the inspector window.

        :param dbstate: The active :class:`gramps.gen.dbstate.DbState`
            (required by :class:`gramps.gui.plug.tool.Tool`, not
            otherwise used - every current tab only touches saved
            on-disk configuration, never the Family Tree database
            itself).
        :param user: The active :class:`gramps.cli.user.User`, used
            for ``uistate`` (window parenting).
        :param options_class: See :class:`ConfigInspectorOptions`;
            this tool has no configurable options, but the base
            :class:`~gramps.gui.plug.tool.Tool` class requires one.
        :param name: This tool's registered plugin id, passed through
            to :class:`~gramps.gui.plug.tool.Tool`.
        :param callback: Unused; part of the standard Tool signature.
        """
        tool.Tool.__init__(self, dbstate, options_class, name)
        uistate = user.uistate
        ManagedWindow.__init__(self, uistate, [], self.__class__)

        dialog = Gtk.Dialog(
            title=_("Config Inspector"),
            transient_for=uistate.window if uistate else None,
        )
        dialog.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        dialog.set_default_size(self._default_width(), 460)
        dialog.connect("response", lambda _dialog, _response: self.close())

        notebook = self._build_notebook(dialog)
        dialog.vbox.pack_start(notebook, True, True, 0)
        dialog.vbox.show_all()

        self.set_window(dialog, None, _("Config Inspector"))
        self.show()

    @staticmethod
    def _default_width():
        """
        95% of the width of the primary monitor (falling back to
        monitor 0, or a fixed 760px if no display/monitor can be
        determined at all - for example under a headless test
        harness), so the window opens usably wide regardless of
        screen size rather than a single fixed pixel width.

        :returns: A pixel width.
        """
        display = Gdk.Display.get_default()
        if display is None:
            return 760
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return 760
        return int(monitor.get_geometry().width * 0.95)

    def _build_notebook(self, parent_window):
        """
        Build the :class:`Gtk.Notebook` and append one page per
        available tab.

        :param parent_window: Passed through to each tab, for dialog
            parenting.
        :returns: The populated :class:`Gtk.Notebook`.
        """
        notebook = Gtk.Notebook()
        notebook.append_page(
            GrampletContainersTab(parent_window),
            Gtk.Label(label=GrampletContainersTab.tab_title),
        )
        # Next planned tab: a gramps.ini chunk lister/inspector/flusher.
        # Add it the same way once written:
        #     notebook.append_page(
        #         GrampsIniChunksTab(parent_window),
        #         Gtk.Label(label=GrampsIniChunksTab.tab_title),
        #     )
        return notebook

    def build_menu_names(self, obj):
        """Part of the Gramps window interface (:class:`ManagedWindow`)."""
        return (_("Config Inspector"), None)


# ------------------------------------------------------------
#
# ConfigInspectorOptions
#
# ------------------------------------------------------------
class ConfigInspectorOptions(tool.ToolOptions):
    """
    This tool has no configurable options; a bare
    :class:`~gramps.gui.plug.tool.ToolOptions` subclass is still
    required, since :class:`~gramps.gui.plug.tool.Tool` constructs one
    regardless.
    """
