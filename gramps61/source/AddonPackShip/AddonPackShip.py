#!/usr/bin/python
# -*- coding: utf-8 -*-

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
# along with this program; if not, see <https://www.gnu.org/licenses/>.

"""
Addon Pack and Ship Tool - GUI for packaging and publishing Gramps addons

Author: Brian McCullough
Development: AI-assisted using Claude (Anthropic)
Created: February 2026
Version: 1.9.0

A graphical tool for Gramps addon developers to simplify packaging and
distribution. Provides checkbox selection, MANIFEST file support, complete
metadata extraction, and ready-to-publish GitHub output structure.
"""

#------------------------------------------------------------------------
#
# Python modules
#
#------------------------------------------------------------------------
import os
import re
import sys
import glob
import json
import shutil
import datetime
import subprocess
import configparser
import urllib.request
import urllib.error

#------------------------------------------------------------------------
#
# GTK modules
#
#------------------------------------------------------------------------
from gi.repository import Gtk, GObject, GLib, Gdk

#------------------------------------------------------------------------
#
# Gramps modules
#
#------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
_ = glocale.translation.gettext
from gramps.version import major_version
from gramps.gui.plug import tool
from gramps.gui.dialog import OkDialog, ErrorDialog
from gramps.gui.managedwindow import ManagedWindow
from gramps.gen.simple import SimpleDoc, SimpleTable
# Import directly from _pluginreg so VIEW is always present (same as PluginManager Enhanced)
from gramps.gen.plug._pluginreg import PluginRegister, PTYPE_STR
from gramps.gui.pluginmanager import GuiPluginManager
try:
    from gramps.gen.plug import PTYPE_STR as _PTYPE_STR_PUB
except ImportError:
    _PTYPE_STR_PUB = PTYPE_STR

#------------------------------------------------------------------------
#
# Constants
#
#------------------------------------------------------------------------
GRAMPS_VERSION = "gramps52"  # Fallback used only if no make<NN>.py is found

# This tool only supports Gramps 5.2+, since that's when the addon
# listing format switched from a legacy line-based addons-<lang>.txt to
# proper addons-<lang>.json. Versions below this are never offered by
# "Update Scripts…" or the "Gramps Versions" checkboxes, even if an
# old make<NN>.py happens to already exist on disk from a prior run.
MIN_SUPPORTED_VERSION_DIGITS = 52

# Recognises bundled build engines like make52.py (Gramps 5.2) or
# make60.py (Gramps 6.0). Deliberately does not match make_addon.py.
MAKE_SCRIPT_RE = re.compile(r'^make(\d{2,3})\.py$')

# Where this tool's bundled make<NN>.py copies come from upstream, used
# by on_update_make_scripts() to fetch/refresh them on demand. The file
# is always named "make.py" on each maintenance/gramps<NN> branch.
GITHUB_ADDONS_SOURCE_RAW = (
    "https://raw.githubusercontent.com/gramps-project/addons-source"
    "/maintenance/gramps{digits}/make.py"
)
GITHUB_ADDONS_SOURCE_BRANCHES_API = (
    "https://api.github.com/repos/gramps-project/addons-source/branches"
    "?per_page=100"
)

# Reserved APS.ini section name (not a real named configuration) used to
# remember which configuration was active when the tool was last closed,
# so it can be restored automatically next time it's opened.
LAST_USED_CONFIG_SECTION = '__LastUsed__'

# Icon shown on the "save current configuration" button, and briefly
# swapped for a checkmark (see _animate_config_save_feedback()) as
# visual confirmation right after a save.
CONFIG_SAVE_ICON_NAME = 'gramps-preferences'

# Plugin type to number mapping (for JSON output)
PTYPE_TO_NUM = {
    'REPORT': 0,
    'QUICKREPORT': 1,
    'TOOL': 2,
    'IMPORT': 3,
    'EXPORT': 4,
    'DOCGEN': 5,
    'GENERAL': 6,
    'MAPSERVICE': 7,
    'VIEW': 8,
    'RELCALC': 9,
    'GRAMPLET': 10,
    'SIDEBAR': 11,
    'PERSIST': 12,
    'RULE': 13,
    'CITE': 14,
}

#------------------------------------------------------------------------
#
# AddonPackShip Tool
#
#------------------------------------------------------------------------
class AddonPackShip(tool.Tool, ManagedWindow):
    """
    GUI Tool for packaging Gramps addons with checkbox selection
    """

    def __init__(self, dbstate, user, options_class, name, callback=None):
        """
        Initialize the Addon Pack and Ship tool
        """
        tool.Tool.__init__(self, dbstate, options_class, name)
        ManagedWindow.__init__(self, user.uistate, [], self)

        self.user = user
        self.addon_info = {}  # Maps addon_dir_name to metadata
        self.checkboxes = {}       # plugin_id → CheckButton
        self.plugin_to_dir = {}    # plugin_id → addon_dir_name
        self.all_selections = {}   # plugin_id → bool (persists across filter changes)
        self._gang_in_progress = False  # re-entrancy guard for gang-select
        self.metadata_cache = {}   # Cache metadata to avoid re-reading files
        self.version_checkboxes = {}   # version code -> Gtk.CheckButton
        self.pending_version_bumps = set()  # addon names flagged to bump
        self.version_bump_widgets = {}      # addon name -> widget info dict

        # Scan for installed addons
        self.scan_installed_addons()

        # Detect which Gramps versions can be targeted (which make<NN>.py
        # scripts are bundled). Listing languages are no longer a separate
        # setting here -- delegated listing runs automatically pick up
        # every language the addon itself has a po/<lang>-local.po for.
        self.available_versions = self.detect_available_versions()

        if not self.addon_info:
            ErrorDialog(
                _("No Addons Found"),
                _("No third-party addons found. Install some addons first."),
                parent=user.uistate.window
            )
            return

        # Build the GUI
        self.build_interface()
        self.show()

    def scan_installed_addons(self):
        """
        Scan for installed addons using GuiPluginManager + PluginRegister.

        Addon directory resolution
        ──────────────────────────
        Gramps provides USER_PLUGINS (e.g. ~/.gramps/gramps52/plugins) as the
        authoritative root for user-installed addons.  Every user plugin has:
            pdata.fpath  — directory containing the .py file
            pdata.fname  — the .py filename

        Resolution:
          rel  = os.path.relpath(fpath, USER_PLUGINS)
          addon_dir_name = rel.split(os.sep)[0]

        This works for all layouts:
          CardView/src/card_view_person.py  →  rel='CardView/src'  →  'CardView'
          SomeAddon.py (flat)               →  rel='.'             →  fname stem

        Previous approaches using '/plugins/' string-splitting or multiple
        candidate roots all had edge cases that lost ~18 directories.
        Using USER_PLUGINS alone is unambiguous.

        CLI diagnostics
        ───────────────
        Set APS_DEBUG=1 to write a full trace to ~/aps_debug.log.
        The log is always overwritten on each scan.
        """
        from gramps.gen.const import USER_PLUGINS

        debug_path = os.path.expanduser('~/aps_debug.log')
        debug      = os.environ.get('APS_DEBUG', '').strip() not in ('', '0')
        _log       = open(debug_path, 'w', encoding='utf-8') if debug else None

        def _dbg(*args):
            if _log:
                print(*args, file=_log, flush=True)

        def _close_log():
            if _log:
                _log.close()

        up_norm = os.path.normpath(USER_PLUGINS)
        _dbg(f'USER_PLUGINS = {up_norm}')

        pgr  = PluginRegister.get_instance()
        pmgr = GuiPluginManager.get_instance()
        addon_dirs = {}

        def _register_pdata(pdata, ptype_label, source=''):
            fpath = getattr(pdata, 'fpath', None)
            fname = getattr(pdata, 'fname', None)
            pid   = getattr(pdata, 'id',    '?')

            if not fpath:
                _dbg(f'SKIP no-fpath  id={pid}  src={source}')
                return

            fpath_norm = os.path.normpath(fpath)
            fpath_fwd  = fpath_norm.replace('\\', '/')

            # ── Exclude built-in Gramps plugins ──────────────────────────
            if 'gramps/plugins' in fpath_fwd:
                _dbg(f'BUILTIN  id={pid}  fpath={fpath}')
                return

            # ── Determine addon_dir_name using USER_PLUGINS as root ───────
            if (fpath_norm == up_norm
                    or fpath_norm.startswith(up_norm + os.sep)):
                # Standard user plugin location
                rel = os.path.relpath(fpath_norm, up_norm)
                if rel == '.':
                    # fpath IS the plugins root → flat addon
                    addon_dir_name = os.path.splitext(fname or '')[0]
                    addon_path     = up_norm
                else:
                    addon_dir_name = rel.split(os.sep)[0]
                    addon_path     = os.path.join(up_norm, addon_dir_name)
            else:
                # Non-standard install: fall back to /plugins/ string heuristic
                if '/plugins/' in fpath_fwd:
                    after = fpath_fwd.rsplit('/plugins/', 1)[1]
                    addon_dir_name = after.split('/')[0].strip()
                    if not addon_dir_name:
                        addon_dir_name = os.path.splitext(fname or '')[0]
                    base = fpath_fwd.rsplit('/plugins/', 1)[0]
                    addon_path = (base + '/plugins/' + addon_dir_name
                                  ).replace('/', os.sep)
                    _dbg(f'NONSTANDARD  id={pid}  fpath={fpath}')
                else:
                    _dbg(f'SKIP not-under-USER_PLUGINS  id={pid}  fpath={fpath}')
                    return

            if not addon_dir_name:
                _dbg(f'SKIP no-dir-name  id={pid}  fpath={fpath}')
                return

            _dbg(f'ACCEPT  id={pid}  dir={addon_dir_name}'
                 f'  path={addon_path}  type={ptype_label}  src={source}')

            if addon_dir_name not in addon_dirs:
                addon_dirs[addon_dir_name] = {
                    'path':    addon_path,
                    'has_gpr': False,
                    'plugins': [],
                    'types':   set(),
                }
            if pdata not in addon_dirs[addon_dir_name]['plugins']:
                addon_dirs[addon_dir_name]['plugins'].append(pdata)
            addon_dirs[addon_dir_name]['types'].add(ptype_label)

        # ── Pass 1: GuiPluginManager success list ─────────────────────────
        try:
            success = pmgr.get_success_list()
            _dbg(f'Pass1 success_list: {len(success)} entries')
            for entry in success:
                try:
                    pdata   = entry[2]
                    typestr = PTYPE_STR.get(pdata.ptype, str(pdata.ptype))
                    _register_pdata(pdata, typestr, 'success_list')
                except Exception as e:
                    _dbg(f'Pass1 entry error: {e}')
        except Exception as e:
            _dbg(f'Pass1 failed: {e}')

        # ── Pass 2: PluginRegister type scan ──────────────────────────────
        for ptype, typestr in PTYPE_STR.items():
            try:
                for pdata in pgr.type_plugins(ptype):
                    _register_pdata(pdata, typestr,
                                    f'pgr.type_plugins({typestr})')
            except Exception as e:
                _dbg(f'Pass2 type={typestr} error: {e}')

        # ── Pass 3: ViewManager pages (belt-and-suspenders for VIEW) ──────
        # Gramps 5.2 vm.pages structure varies: it may be a flat list of
        # view objects OR a list-of-lists.  Handle both.
        try:
            vm = self.user.uistate.viewmanager
            raw_pages = vm.pages
            # Normalise to a flat iterable of view objects
            views_flat = []
            for item in raw_pages:
                try:
                    # Try iterating — works if item is a list/tuple of views
                    for v in item:
                        views_flat.append(v)
                except TypeError:
                    # item itself is a view object (flat list case)
                    views_flat.append(item)
            for view in views_flat:
                pdata = None
                for attr in ('_viewinfo', 'view_info', '_view_info',
                             'viewinfo'):
                    pdata = getattr(view, attr, None)
                    if pdata is not None:
                        break
                if pdata is None:
                    continue
                _register_pdata(pdata, 'VIEW', 'viewmanager')
        except Exception as e:
            _dbg(f'Pass3 failed: {e}')

        # ── gpr detection ─────────────────────────────────────────────────
        # Search order for each addon directory:
        #  1. addon_path/AddonDirName.gpr.py   (exact case)
        #  2. addon_path/adondirname.gpr.py    (lowercase)
        #  3. any *.gpr.py directly in addon_path   (e.g. card_view.gpr.py)
        #  4. any *.gpr.py in the fpath of each registered plugin
        #     — this catches addons like CardView where source files AND
        #       the .gpr.py are in a subdirectory (CardView/src/card_view.gpr.py)
        for addon_dir_name, info in addon_dirs.items():
            addon_path = info['path']

            # 1. Exact-case top-level
            if os.path.exists(os.path.join(addon_path,
                                           f'{addon_dir_name}.gpr.py')):
                info['has_gpr'] = True
                continue
            # 2. Lowercase top-level
            if os.path.exists(os.path.join(addon_path,
                                           f'{addon_dir_name.lower()}.gpr.py')):
                info['has_gpr'] = True
                continue
            # 3. Any .gpr.py in the top-level directory
            try:
                if any(f.endswith('.gpr.py')
                       for f in os.listdir(addon_path)):
                    info['has_gpr'] = True
                    continue
            except Exception:
                pass
            # 4. Any .gpr.py in the fpath of each registered plugin
            #    (handles layouts like CardView/src/card_view.gpr.py)
            found_in_subdir = False
            for pdata in info.get('plugins', []):
                fpth = getattr(pdata, 'fpath', None)
                if not fpth or os.path.normpath(fpth) == os.path.normpath(addon_path):
                    continue   # already checked this dir above
                try:
                    if any(f.endswith('.gpr.py')
                           for f in os.listdir(fpth)):
                        info['has_gpr'] = True
                        _dbg(f'GPR_IN_SUBDIR  dir={addon_dir_name}  subdir={fpth}')
                        found_in_subdir = True
                        break
                except Exception:
                    pass
            if found_in_subdir:
                continue

            _dbg(f'NO_GPR  dir={addon_dir_name}  path={addon_path}'
                 f'  fpaths_checked={list(set(getattr(p,"fpath","?") for p in info.get("plugins",[])))}')

        self.addon_info = {
            name: info for name, info in addon_dirs.items()
            if info['has_gpr']
        }
        _dbg(f'FINAL: {len(addon_dirs)} dirs, '
             f'{len(self.addon_info)} with gpr, '
             f'{sum(len(i["plugins"]) for i in self.addon_info.values())} plugins')
        _close_log()
        if debug:
            print(f'APS: debug log written to {debug_path}', flush=True)

    @staticmethod
    def _version_label(digits):
        """
        Format version digits like '52' as a human label like '5.2'.

        :param digits: Version digit string, e.g. '52' or '60'.
        :returns: formatted label.
        """
        return f"{digits[0]}.{digits[1:]}" if len(digits) >= 2 else digits

    @staticmethod
    def _is_supported_version(digits):
        """
        Return True if `digits` (e.g. '52', '60') is at or above
        MIN_SUPPORTED_VERSION_DIGITS -- i.e. Gramps 5.2+, the versions
        this tool generates JSON listings for.

        :param digits: Version digit string.
        :returns: bool.
        """
        try:
            return int(digits) >= MIN_SUPPORTED_VERSION_DIGITS
        except ValueError:
            return False

    @staticmethod
    def _running_gramps_version_code():
        """
        Return the version code (e.g. 'gramps52') for the Gramps major
        version currently running this tool, in the same
        'gramps<digits>' format used for :attr:`available_versions`
        codes and the "Gramps Versions" checkboxes.

        Derived from :data:`gramps.version.major_version` (e.g.
        '5.2'), the same value Gramps' own .gpr.py registration files
        use for `gramps_target_version`, rather than any bundled
        make<NN>.py script -- this is about which Gramps release is
        actually running the tool right now, independent of which
        packaging scripts happen to be present.

        :returns: version code string, e.g. 'gramps52'.
        """
        return f"gramps{major_version.replace('.', '')}"

    def detect_available_versions(self):
        """
        Detect which Gramps versions can be targeted for packaging by
        scanning this tool's own directory for bundled make<NN>.py build
        engines (e.g. make52.py -> Gramps 5.2, make60.py -> Gramps 6.0).
        Only versions with a matching script are offered, since the
        presence of that script is what documents which Gramps release
        packaging support has been prepared for. Versions below
        MIN_SUPPORTED_VERSION_DIGITS are skipped even if their script
        is present on disk (e.g. from a prior "Update Scripts…" run),
        since this tool only generates JSON listings.

        :returns: list of dicts with 'code' (e.g. 'gramps52'), 'label'
            (e.g. '5.2') and 'script' (e.g. 'make52.py'), sorted by code.
        """
        builder_dir = os.path.dirname(os.path.abspath(__file__))
        versions = []
        try:
            entries = os.listdir(builder_dir)
        except OSError:
            entries = []
        for fname in sorted(entries):
            match = MAKE_SCRIPT_RE.match(fname)
            if not match:
                continue
            digits = match.group(1)
            if not self._is_supported_version(digits):
                continue
            versions.append({
                'code': f'gramps{digits}',
                'label': self._version_label(digits),
                'script': fname,
            })
        return versions

    def get_selected_versions(self):
        """
        Return the Gramps version codes (e.g. ['gramps52']) currently
        checked in the "Gramps Versions" row. Falls back to whatever
        version was auto-detected (or the module default) when nothing
        is checked, so build/listing operations always have a target.

        :returns: list of version codes.
        """
        selected = [
            code for code, checkbox in self.version_checkboxes.items()
            if checkbox.get_active()
        ]
        if not selected:
            if self.available_versions:
                selected = [self.available_versions[0]['code']]
            else:
                selected = [GRAMPS_VERSION]
        return selected

    def _config_ini_path(self):
        """
        Return the path to APS.ini, where named configurations are
        stored -- alongside this tool's own .py files, not in the
        addon being packaged.
        """
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'APS.ini')

    def _list_saved_configs(self):
        """
        Return the names of every real named configuration currently
        saved in APS.ini, sorted alphabetically. Excludes the reserved
        [__LastUsed__] bookkeeping section.
        """
        ini_path = self._config_ini_path()
        if not os.path.isfile(ini_path):
            return []
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding='utf-8')
        except configparser.Error:
            return []
        return sorted(
            name for name in parser.sections()
            if name != LAST_USED_CONFIG_SECTION)

    def _save_last_used_config_name(self):
        """
        Remember whichever name is currently in the "Configuration"
        combo's entry, in APS.ini's reserved [__LastUsed__] section,
        so it can be restored automatically next time this tool opens.
        """
        if not hasattr(self, 'config_combo'):
            return
        entry = self.config_combo.get_child()
        name = entry.get_text().strip() if entry else ''
        if not name:
            return

        ini_path = self._config_ini_path()
        parser = configparser.ConfigParser()
        if os.path.isfile(ini_path):
            try:
                parser.read(ini_path, encoding='utf-8')
            except configparser.Error:
                pass
        if not parser.has_section(LAST_USED_CONFIG_SECTION):
            parser.add_section(LAST_USED_CONFIG_SECTION)
        parser.set(LAST_USED_CONFIG_SECTION, 'name', name)
        try:
            with open(ini_path, 'w', encoding='utf-8') as fh:
                parser.write(fh)
        except OSError:
            pass  # remembering the last-used name is a convenience only

    def _get_last_used_config_name(self):
        """
        Return the configuration name remembered from the previous
        session (APS.ini's [__LastUsed__] section), or '' if none.
        """
        ini_path = self._config_ini_path()
        if not os.path.isfile(ini_path):
            return ''
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding='utf-8')
        except configparser.Error:
            return ''
        return parser.get(LAST_USED_CONFIG_SECTION, 'name', fallback='')

    def _refresh_config_combo(self, select=None):
        """
        Repopulate the "Configuration" combo's dropdown list from
        APS.ini, without disturbing whatever name is currently typed
        into its entry (unless `select` is given).
        """
        if not hasattr(self, 'config_combo'):
            return
        entry = self.config_combo.get_child()
        current_text = entry.get_text() if entry else None

        self.config_combo.remove_all()
        for name in self._list_saved_configs():
            self.config_combo.append_text(name)

        if entry is not None:
            entry.set_text(select if select is not None
                            else (current_text or ''))

    def _collect_config_state(self):
        """
        Gather the current state of every saveable control -- build
        mode, Gramps version checkboxes, output location, filters, and
        which addons/plugins are selected -- into a plain dict, ready
        to write to one section of APS.ini.

        :returns: dict of state.
        """
        # Flush current visible checkbox states into self.all_selections
        # first, the same way rebuild_addon_list() does at its own start.
        for pid, checkbox in self.checkboxes.items():
            self.all_selections[pid] = checkbox.get_active()

        return {
            'build_mode': self.get_build_mode(),
            'versions': {code: checkbox.get_active()
                         for code, checkbox in self.version_checkboxes.items()},
            'output_dir': self.get_output_parent_dir(),
            'filter_text': (self.author_filter_entry.get_text()
                            if hasattr(self, 'author_filter_entry') else ''),
            'type_filter': (self.type_filter_combo.get_active_text()
                            if hasattr(self, 'type_filter_combo') else ''),
            'selected_plugins': dict(self.all_selections),
        }

    def save_named_config(self, name):
        """
        Save the current UI state under `name` in APS.ini, overwriting
        that section if a configuration with this name already exists.

        :param name: Configuration name (from the combo's entry).
        """
        name = name.strip()
        if not name or name == LAST_USED_CONFIG_SECTION:
            return

        ini_path = self._config_ini_path()
        parser = configparser.ConfigParser()
        if os.path.isfile(ini_path):
            try:
                parser.read(ini_path, encoding='utf-8')
            except configparser.Error:
                pass

        state = self._collect_config_state()
        if not parser.has_section(name):
            parser.add_section(name)
        parser.set(name, 'build_mode', state['build_mode'])
        parser.set(name, 'versions', json.dumps(state['versions']))
        parser.set(name, 'output_dir', state['output_dir'])
        parser.set(name, 'filter_text', state['filter_text'])
        parser.set(name, 'type_filter', state['type_filter'] or '')
        # Only the checked plugin IDs are worth storing -- unchecked is
        # already the default, so a full True/False dict just duplicates
        # every known plugin ID for no benefit.
        checked_plugins = sorted(
            pid for pid, checked in state['selected_plugins'].items()
            if checked)
        parser.set(name, 'selected_plugins', json.dumps(checked_plugins))

        try:
            with open(ini_path, 'w', encoding='utf-8') as fh:
                parser.write(fh)
        except OSError as exc:
            ErrorDialog(
                _("Could Not Save Configuration"), str(exc), parent=self.window)
            return

        self._refresh_config_combo(select=name)

    def load_named_config(self, name):
        """
        Apply the saved UI state for `name` from APS.ini to every
        control it covers (build mode, version checkboxes, output
        location, filters, addon/plugin selection).

        :param name: Configuration name to load.
        """
        ini_path = self._config_ini_path()
        if not os.path.isfile(ini_path):
            return
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding='utf-8')
        except configparser.Error:
            return
        if not parser.has_section(name):
            return

        if parser.get(name, 'build_mode', fallback='beta') == 'release':
            self.radio_release.set_active(True)
        else:
            self.radio_beta.set_active(True)

        try:
            versions = json.loads(parser.get(name, 'versions', fallback='{}'))
        except ValueError:
            versions = {}
        for code, checkbox in self.version_checkboxes.items():
            checkbox.set_active(bool(versions.get(code, checkbox.get_active())))

        output_dir = parser.get(name, 'output_dir', fallback='')
        if output_dir and os.path.isdir(output_dir):
            self.output_dir_chooser.set_filename(output_dir)

        if hasattr(self, 'author_filter_entry'):
            self.author_filter_entry.set_text(
                parser.get(name, 'filter_text', fallback=''))

        if hasattr(self, 'type_filter_combo'):
            wanted_type = parser.get(name, 'type_filter', fallback='')
            model = self.type_filter_combo.get_model()
            matched = False
            for idx, row in enumerate(model):
                if row[0] == wanted_type:
                    self.type_filter_combo.set_active(idx)
                    matched = True
                    break
            if not matched:
                self.type_filter_combo.set_active(0)

        try:
            checked_plugins = json.loads(
                parser.get(name, 'selected_plugins', fallback='[]'))
        except ValueError:
            checked_plugins = []
        self.all_selections = {pid: True for pid in checked_plugins}
        # rebuild_addon_list() normally flushes live checkboxes into
        # self.all_selections at its own start, which would immediately
        # overwrite what was just loaded -- clear it first so that
        # flush has nothing to clobber.
        self.checkboxes = {}
        self.rebuild_addon_list()

    def on_config_combo_changed(self, combo):
        """
        Handle the "Configuration" combo: loading only triggers when an
        existing entry is picked from the dropdown list (get_active()
        returns its index, >= 0) -- never while the user is still
        typing a name into the entry, which leaves get_active() at -1.

        The actual load is deferred to a GLib idle callback: running it
        synchronously here, while this combo's own dropdown popup is
        still closing, can trigger a GDK "Tried to map a popup with a
        non-top most parent" warning as soon as load_named_config()
        touches another popup-capable widget (the folder chooser) or
        rebuilds the addon list. Deferring runs it just after the
        dropdown has fully closed.
        """
        index = combo.get_active()
        if index < 0:
            return
        name = combo.get_active_text()
        if name:
            GLib.idle_add(self._load_named_config_idle, name)

    def _load_named_config_idle(self, name):
        """GLib.idle_add callback wrapper for load_named_config()."""
        self.load_named_config(name)
        return False

    def _seed_default_config_idle(self):
        """
        GLib.idle_add callback: save the current settings as a
        "default" named configuration -- see the call site in
        build_interface() for why this only runs on a genuinely fresh
        install, and why it's deferred this way.

        Re-checks for an existing "default" configuration at call
        time rather than trusting the check made when this was
        scheduled, in case one was created in the interim (e.g. the
        user typed "default" into the Configuration box and saved it
        manually before this idle callback got a turn to run).

        :returns: False, so GLib.idle_add doesn't repeat this call.
        """
        if 'default' not in self._list_saved_configs():
            self.save_named_config('default')
        return False

    def on_config_combo_activate(self, entry):
        """
        Handle pressing Enter in the "Configuration" name entry: save
        the current settings under whatever name is typed there,
        overwriting a configuration of the same name if it exists.
        """
        name = entry.get_text().strip()
        if name:
            self.save_named_config(name)
            self._animate_config_save_feedback()

    def on_config_save_button_clicked(self, _button):
        """
        Handle clicking the "Configuration" save icon: save the current
        settings under whatever name is typed in the combo's entry,
        exactly like pressing Enter there.
        """
        entry = self.config_combo.get_child()
        if entry is None:
            return
        name = entry.get_text().strip()
        if name:
            self.save_named_config(name)
            self._animate_config_save_feedback()

    def _animate_config_save_feedback(self):
        """
        Briefly swap the "save configuration" icon to a checkmark, with
        a fade transition, then fade back to its normal icon -- visual
        confirmation that a save just happened. Total round trip is
        about 2 seconds.

        Uses Gtk.Widget.set_opacity() stepped via a handful of
        GLib.timeout_add() calls, since GTK3 has no simpler built-in
        way to cross-fade a Gtk.Image's content.
        """
        icon_widget = getattr(self, 'config_icon', None)
        if icon_widget is None:
            return

        theme = Gtk.IconTheme.get_default()
        confirm_icon_name = (
            'gtk-apply' if theme.has_icon('gtk-apply')
            else 'emblem-ok-symbolic')

        fade_step_ms = 25
        fade_steps = 6
        hold_ms = 1200

        def _fade(start, end, on_done):
            delta = (end - start) / fade_steps
            state = {'step': 0, 'value': start}

            def _tick():
                state['step'] += 1
                state['value'] += delta
                icon_widget.set_opacity(max(0.0, min(1.0, state['value'])))
                if state['step'] >= fade_steps:
                    if on_done:
                        on_done()
                    return False
                return True

            GLib.timeout_add(fade_step_ms, _tick)

        def _show_confirm():
            icon_widget.set_from_icon_name(
                confirm_icon_name, Gtk.IconSize.BUTTON)
            _fade(0.0, 1.0, _hold_then_fade_back)

        def _hold_then_fade_back():
            GLib.timeout_add(hold_ms, _fade_out_confirm)

        def _fade_out_confirm():
            _fade(1.0, 0.0, _restore_original)
            return False

        def _restore_original():
            icon_widget.set_from_icon_name(
                CONFIG_SAVE_ICON_NAME, Gtk.IconSize.BUTTON)
            _fade(0.0, 1.0, None)

        # Fade the current icon out first, swap to the checkmark, fade
        # it in, hold briefly, then reverse the whole sequence.
        _fade(1.0, 0.0, _show_confirm)

    def get_output_parent_dir(self):
        """
        Return the parent folder under which this run's <version>/
        output folders (download/, listings/) should be created:
        whatever is chosen in the "Output Location" folder picker, or
        this tool's own folder if nothing has been chosen yet.

        This is independent of where the tool itself (and its
        make<NN>.py scripts) are installed -- see run_make_command(),
        which resolves those separately.

        :returns: absolute directory path.
        """
        chooser = getattr(self, 'output_dir_chooser', None)
        if chooser is not None:
            chosen = chooser.get_filename()
            if chosen:
                return chosen
        return os.path.dirname(os.path.abspath(__file__))

    def on_output_suggestion_changed(self, combo):
        """
        Apply the folder selected in the "Suggested" combo (detected
        local Git repo clones) to the "Output Location" folder chooser.
        The combo's first entry is a non-selectable placeholder.

        Deferred via GLib.idle_add for the same reason as
        on_config_combo_changed() -- avoids a GDK "non-top most
        parent" warning from touching the folder chooser while this
        combo's own dropdown popup is still closing.
        """
        index = combo.get_active()
        if index <= 0:
            return
        path = combo.get_active_text()
        if path and os.path.isdir(path):
            GLib.idle_add(self._apply_output_suggestion_idle, path)

    def _apply_output_suggestion_idle(self, path):
        """GLib.idle_add callback wrapper for applying a suggested folder."""
        self.output_dir_chooser.set_filename(path)
        return False

    def detect_local_git_repo_roots(self, max_results=25):
        """
        Suggest destination folders by scanning common GitHub-Desktop-
        style clone locations for existing local Git repositories (any
        directory containing a .git subdirectory).

        This deliberately does NOT read GitHub Desktop's own internal
        database. That data lives in an undocumented, version-fragile
        Chromium "Local Storage" LevelDB store under GitHub Desktop's
        own userData folder (not IndexedDB, despite what some AI
        assistants suggest) -- it uses Chromium's plain key/value
        Local Storage log format, locks while the app is running, and
        has no supported read API, so parsing it is liable to break on
        any GitHub Desktop update. Scanning the filesystem for real
        .git directories under GitHub Desktop's own default clone
        locations is slightly less exhaustive (it can't see a repo
        cloned somewhere unusual) but needs no extra dependencies and
        can't be broken by an app update.

        :param max_results: Cap on how many repo roots to return.
        :returns: sorted list of absolute directory paths.
        """
        home = os.path.expanduser('~')
        # GitHub Desktop's own default clone locations, plus a few other
        # common developer folders, across Windows/macOS/Linux.
        candidate_bases = [
            os.path.join(home, 'Documents', 'GitHub'),  # GH Desktop default
            os.path.join(home, 'GitHub'),
            os.path.join(home, 'Documents', 'Source', 'Repos'),
            os.path.join(home, 'source', 'repos'),
            os.path.join(home, 'Projects'),
            os.path.join(home, 'repos'),
            os.path.join(home, 'dev'),
        ]

        found = set()
        for base in candidate_bases:
            if not os.path.isdir(base):
                continue
            try:
                for entry in os.scandir(base):
                    if entry.is_dir() and os.path.isdir(
                            os.path.join(entry.path, '.git')):
                        found.add(entry.path)
                        if len(found) >= max_results:
                            break
            except OSError:
                continue
            if len(found) >= max_results:
                break
        return sorted(found)[:max_results]

    def _fetch_make_script_source(self, digits, timeout=15):
        """
        Download the current make.py from the gramps-project/
        addons-source 'maintenance/gramps<digits>' branch on GitHub.

        :param digits: Version digit string, e.g. '52'.
        :param timeout: Network timeout in seconds.
        :returns: (content_str, error_message) -- exactly one is None.
        """
        url = GITHUB_ADDONS_SOURCE_RAW.format(digits=digits)
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                if response.status != 200:
                    return None, f"HTTP {response.status}"
                return response.read().decode('utf-8'), None
        except urllib.error.HTTPError as exc:
            return None, f"HTTP {exc.code}"
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return None, str(exc)

    def _discover_upstream_versions(self, timeout=15):
        """
        Query the GitHub API for maintenance/gramps<NN> branches on
        gramps-project/addons-source, so newly released Gramps versions
        can be offered even before a local make<NN>.py exists for them.
        Only versions at or above MIN_SUPPORTED_VERSION_DIGITS (5.2+,
        which use JSON listings) are returned.

        :param timeout: Network timeout in seconds.
        :returns: sorted list of version digit strings (e.g. ['52',
            '60', '61']), or [] if the API could not be reached (no
            network, rate-limited, etc.) -- callers should treat that
            as "nothing new found", not as an error.
        """
        request = urllib.request.Request(
            GITHUB_ADDONS_SOURCE_BRANCHES_API,
            headers={'Accept': 'application/vnd.github+json'})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            return []
        digits = []
        for branch in data if isinstance(data, list) else []:
            match = re.match(r'^maintenance/gramps(\d{2,3})$',
                              branch.get('name', ''))
            if match and self._is_supported_version(match.group(1)):
                digits.append(match.group(1))
        return sorted(set(digits))

    def on_update_make_scripts(self, _widget):
        """
        Download the current make.py for every known (and newly
        discoverable) Gramps version from gramps-project/addons-source
        on GitHub, overwriting this tool's bundled make<NN>.py copies
        so upstream fixes are picked up on demand rather than requiring
        a manual re-port. Existing files are backed up with a timestamp
        before being overwritten. Restricted to Gramps 5.2+ (see
        MIN_SUPPORTED_VERSION_DIGITS), since that's when the addon
        listing format switched to JSON.
        """
        builder_dir = os.path.dirname(os.path.abspath(__file__))

        known_digits = sorted({
            entry['code'][len('gramps'):] for entry in self.available_versions
        })
        new_digits = [d for d in self._discover_upstream_versions()
                      if d not in known_digits]

        if not known_digits and not new_digits:
            OkDialog(
                _("No Versions Found"),
                _("Could not find any local make<NN>.py to update, and "
                  "the GitHub branch list could not be reached (check "
                  "your network connection)."),
                parent=self.window
            )
            return

        lines = []
        if known_digits:
            lines.append(_("Update existing scripts:"))
            lines.extend(
                f"  \u2022 make{d}.py  (Gramps {self._version_label(d)})"
                for d in known_digits)
        if new_digits:
            lines.append("")
            lines.append(_("Add newly available scripts:"))
            lines.extend(
                f"  \u2022 make{d}.py  (Gramps {self._version_label(d)})"
                for d in new_digits)
        lines.append("")
        lines.append(_(
            "Existing files are backed up (.bak) before being "
            "overwritten. Continue?"))

        from gramps.gui.dialog import QuestionDialog2
        question = QuestionDialog2(
            _("Update Scripts from GitHub?"),
            "\n".join(lines),
            _("Yes, Update"),
            _("Cancel"),
            parent=self.window
        )
        if not question.run():
            return

        results = []
        for digits in known_digits + new_digits:
            content, error = self._fetch_make_script_source(digits)
            script_name = f"make{digits}.py"
            script_path = os.path.join(builder_dir, script_name)

            if error:
                results.append(f"\u2717 {script_name}: {error}")
                continue

            if os.path.exists(script_path):
                with open(script_path, 'r', encoding='utf-8',
                          errors='replace') as fh:
                    current = fh.read()
                if current == content:
                    results.append(f"= {script_name}: already up to date")
                    continue
                timestamp = datetime.datetime.now().strftime(
                    '%Y%m%d-%H%M%S')
                backup_path = f"{script_path}.{timestamp}.bak"
                shutil.copy2(script_path, backup_path)
                note = f"backup: {os.path.basename(backup_path)}"
            else:
                note = "new file"

            try:
                with open(script_path, 'w', encoding='utf-8',
                          newline='') as fh:
                    fh.write(content)
                results.append(f"\u2713 {script_name}: updated ({note})")
            except OSError as exc:
                results.append(f"\u2717 {script_name}: could not write ({exc})")

        # Re-detect since new/updated scripts may have appeared
        self.available_versions = self.detect_available_versions()

        self.show_scrollable_dialog(
            _("Update Scripts Results"),
            _("Checked gramps-project/addons-source on GitHub:") + "\n\n"
            + "\n".join(results) + "\n\n"
            + _("Restart Addon Pack and Ship (or re-open this tool) to "
                "see any newly added Gramps version checkboxes.")
        )

    def build_interface(self):
        """
        Build the GTK interface
        """
        self.set_window(
            Gtk.Window(),
            Gtk.Label(_("Addon Pack and Ship")),
            _("Addon Pack and Ship")
        )

        window = self.window
        window.set_default_size(800, 650)
        window.set_border_width(12)

        # Main vertical box
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        window.add(vbox)

        # No separate title/info labels here -- the window titlebar
        # (set via set_window() above) already shows the tool name, and
        # the "Found N bundles…" summary moves to the bottom status row
        # (see update_selection_count()) so it's replaced by the live
        # "Selected bundles: …" readout as soon as something is checked.
        # "Select installed addons to package and publish" becomes a
        # tooltip on the addon list itself (see below) instead of taking
        # up a permanent line.
        total_plugins = sum(
            len(info['plugins']) for info in self.addon_info.values())
        self._total_bundles = len(self.addon_info)
        self._total_plugins = total_plugins

        # ── Filter Addons frame — contains select/mode row, filter row, action buttons ──
        filter_frame = Gtk.Frame(label=_("Filter Addons:"))
        filter_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        filter_box.set_border_width(6)
        filter_frame.add(filter_box)

        # Row 1: Select All / Deselect All  +  Build Mode radio buttons
        select_mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        select_all_btn = Gtk.Button(label=_("Select All Visible"))
        select_all_btn.connect("clicked", self.on_select_all)
        select_mode_box.pack_start(select_all_btn, False, False, 0)

        deselect_all_btn = Gtk.Button(label=_("Deselect All"))
        deselect_all_btn.connect("clicked", self.on_deselect_all)
        select_mode_box.pack_start(deselect_all_btn, False, False, 0)

        select_mode_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 6)

        mode_label = Gtk.Label()
        mode_label.set_markup(_("<b>Build Mode:</b>"))
        select_mode_box.pack_start(mode_label, False, False, 0)

        self.radio_beta = Gtk.RadioButton.new_with_label(None, _("β  Beta"))
        self.radio_beta.set_tooltip_text(
            _("Beta build — includes everything for testers and translators:\n"
              "• All core files (.py, .glade, .xml)\n"
              "• README.md and all *.md files\n"
              "• po/*.po translation source files\n"
              "• po/template.pot translation template\n"
              "• MANIFEST and MANIFEST.beta files\n"
              "• All subdirectory contents (data, layouts, etc.)\n"
              "• locale/*.mo compiled translations\n\n"
              "Uses MANIFEST.beta if present, otherwise auto-includes all extras.")
        )
        self.radio_beta.connect("toggled", self.on_build_mode_changed)
        select_mode_box.pack_start(self.radio_beta, False, False, 0)

        self.radio_release = Gtk.RadioButton.new_with_label_from_widget(
            self.radio_beta, _("Δ  Release")
        )
        self.radio_release.set_tooltip_text(
            _("Release build — clean end-user package:\n"
              "• All core files (.py, .glade, .xml)\n"
              "• README.md only (no other .md files)\n"
              "• locale/*.mo compiled translations only\n"
              "• MANIFEST extras (if MANIFEST present)\n\n"
              "⚠ Intentionally lossy — po/ source files,\n"
              "CHANGELOG, dev notes are NOT included.\n"
              "Uses MANIFEST if present.")
        )
        self.radio_release.connect("toggled", self.on_build_mode_changed)
        select_mode_box.pack_start(self.radio_release, False, False, 0)

        # Type filter combo — at the end of the mode row, no label needed
        select_mode_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 6)

        self.type_filter_combo = Gtk.ComboBoxText()
        self.type_filter_combo.append_text(_("All Types"))
        all_types = sorted(set(
            t for info in self.addon_info.values()
            for t in info['types']
            if t and t != 'UNKNOWN'
        ))
        for t in all_types:
            self.type_filter_combo.append_text(t)
        self.type_filter_combo.set_active(0)
        self.type_filter_combo.set_tooltip_text(
            _("Filter list by plugin type.\n"
              "VIEW = views/panels  GRAMPLET = dashboard gramplets\n"
              "TOOL = tools  REPORT = reports  GENERAL = utilities"))
        self.type_filter_combo.connect("changed", self.on_filter_changed)
        select_mode_box.pack_start(self.type_filter_combo, False, False, 0)

        filter_box.pack_start(select_mode_box, False, False, 0)

        # Row 2: SearchEntry with built-in magnifier and ✕ clear button
        self.author_filter_entry = Gtk.SearchEntry()
        self.author_filter_entry.set_placeholder_text(
            _("Search bundles and plugins…"))
        self.author_filter_entry.set_tooltip_text(
            _("Search across all plugin fields: name, type, id, path, "
              "authors, version, category, and more.\n"
              "All words must match (order ignored, case-insensitive)."))
        self.author_filter_entry.connect("search-changed", self.on_filter_changed)
        filter_box.pack_start(self.author_filter_entry, False, False, 0)

        # Row 3: individual operation buttons (always visible — outside scroll area)
        action_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        build_btn = Gtk.Button(label=_("Build Selected"))
        build_btn.connect("clicked", self.on_build)
        action_btn_box.pack_start(build_btn, False, False, 0)

        compile_btn = Gtk.Button(label=_("Compile Translations"))
        compile_btn.connect("clicked", self.on_compile)
        action_btn_box.pack_start(compile_btn, False, False, 0)

        listing_btn = Gtk.Button(label=_("Amend Listings"))
        listing_btn.set_tooltip_text(
            _("Create or amend the addons-<lang>.json listing(s) for"
              " selected addons, for each checked Gramps version above."
              " English plus any language the addon has a"
              " po/<lang>-local.po for is listed automatically.\n"
              "Adds/updates entries — other entries are preserved.\n"
              "To shrink a listing, delete that version's listings/"
              " folder first, then rebuild only the addons you want"
              " listed.")
        )
        listing_btn.connect("clicked", self.on_listing)
        action_btn_box.pack_start(listing_btn, False, False, 0)

        filter_box.pack_start(action_btn_box, False, False, 0)

        vbox.pack_start(filter_frame, False, False, 0)

        # ── Package Targets frame — which Gramps versions to build/list for ──
        targets_frame = Gtk.Frame(label=_("Package Targets:"))
        targets_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        targets_box.set_border_width(6)
        targets_frame.add(targets_box)

        # Row: which Gramps versions to build/list for
        version_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        version_label = Gtk.Label()
        version_label.set_markup(_("<b>Gramps Versions:</b>"))
        version_row.pack_start(version_label, False, False, 0)

        if self.available_versions:
            running_code = self._running_gramps_version_code()
            for entry in self.available_versions:
                checkbox = Gtk.CheckButton(label=entry['label'])
                # Default: only the Gramps version actually running this
                # tool is pre-checked. A loaded named configuration (see
                # load_named_config()) overrides this immediately after,
                # same as it overrides every other default below.
                checkbox.set_active(entry['code'] == running_code)
                checkbox.set_tooltip_text(
                    _("Build and list packages for Gramps {label}"
                      " (using {script}).\nThe same .addon.tgz is reused"
                      " (duplicated) across every checked version — it"
                      " is only rebuilt once.\nListing entries are"
                      " generated by delegating to the real {script} from"
                      " gramps-project/addons-source, so every language"
                      " the addon has a po/*-local.po for is listed"
                      " automatically.").format(
                          label=entry['label'], script=entry['script']))
                self.version_checkboxes[entry['code']] = checkbox
                version_row.pack_start(checkbox, False, False, 0)
        else:
            version_row.pack_start(
                Gtk.Label(_("No make<NN>.py scripts found — using"
                            " default '{}'.").format(GRAMPS_VERSION)),
                False, False, 0)

        update_scripts_btn = Gtk.Button(label=_("Update Scripts…"))
        update_icon = Gtk.Image.new_from_icon_name(
            "folder-download-symbolic", Gtk.IconSize.BUTTON)
        update_scripts_btn.set_image(update_icon)
        update_scripts_btn.set_always_show_image(True)
        update_scripts_btn.set_image_position(Gtk.PositionType.LEFT)
        update_scripts_btn.set_tooltip_text(
            _("Fetch the current Gramps 5.2+ packaging scripts from"
              " gramps-project/addons-source on GitHub, overwriting this"
              " tool's bundled copies (a timestamped backup is kept)."
              " Also offers to add a script for any newly released"
              " Gramps version not yet bundled here.\nThis is the only"
              " way these files are ever changed — they are never"
              " edited automatically."))
        update_scripts_btn.connect("clicked", self.on_update_make_scripts)
        version_row.pack_start(update_scripts_btn, False, False, 12)

        targets_box.pack_start(version_row, False, False, 0)

        vbox.pack_start(targets_frame, False, False, 0)

        # ── Output Location row — where <version>/download, listings go,
        # plus named configuration load/save ─────────────────────────────
        output_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        output_icon_label = Gtk.Label()
        output_icon_label.set_markup(_("<b>Output location:</b>"))
        output_box.pack_start(output_icon_label, False, False, 0)

        # Default folder is this tool's own installation directory; the
        # "Configuration" combo below (backed by APS.ini, not gramps.ini)
        # restores a different one automatically if a last-used named
        # configuration set output_dir to something else.
        default_output_dir = os.path.dirname(os.path.abspath(__file__))

        self.output_dir_chooser = Gtk.FileChooserButton(
            title=_("Choose a parent folder for the generated"
                    " version folders"),
            action=Gtk.FileChooserAction.SELECT_FOLDER)
        self.output_dir_chooser.set_filename(default_output_dir)
        self.output_dir_chooser.set_tooltip_text(
            _("Where the gramps52/, gramps60/, etc. output folders"
              " (each with download/ and listings/ subfolders) are"
              " created. Defaults to this tool's own folder.\nSave a"
              " named configuration (see the icon and box to the"
              " right) to remember a different folder across sessions"
              " -- point it at a local Git repository clone if you"
              " plan to commit and push the generated packages and"
              " listings with GitHub Desktop."))

        # GtkFileChooserButton's own compact dropdown only ever shows
        # recently-used folders plus "Other…" -- shortcuts added via
        # add_shortcut_folder() only appear once that "Other…" dialog is
        # open, so they're easy to miss. A separate, always-visible combo
        # makes detected Git repo folders actually discoverable.
        detected_repo_roots = self.detect_local_git_repo_roots()
        if detected_repo_roots:
            self.output_suggestions_combo = Gtk.ComboBoxText()
            self.output_suggestions_combo.append_text(
                _("(pick a detected Git repo folder…)"))
            for repo_root in detected_repo_roots:
                self.output_suggestions_combo.append_text(repo_root)
            self.output_suggestions_combo.set_active(0)
            self.output_suggestions_combo.set_tooltip_text(
                _("Local Git repository clones found under common"
                  " GitHub Desktop / developer folders (e.g."
                  " ~/Documents/GitHub). Selecting one sets the parent"
                  " folder on the right."))
            self.output_suggestions_combo.connect(
                "changed", self.on_output_suggestion_changed)
            output_box.pack_start(
                self.output_suggestions_combo, False, False, 0)

        for repo_root in detected_repo_roots:
            try:
                self.output_dir_chooser.add_shortcut_folder(repo_root)
            except GObject.GError:
                pass  # already a shortcut, or otherwise unavailable

        output_box.pack_start(self.output_dir_chooser, True, True, 0)

        # ── Named configuration load/save, sharing this same line ─────────
        config_icon = Gtk.Image.new_from_icon_name(
            CONFIG_SAVE_ICON_NAME, Gtk.IconSize.BUTTON)
        self.config_icon = config_icon  # kept for the save-feedback animation
        config_save_tooltip = _(
            "Save the current settings under the name typed in the box"
            " to the right (same as pressing Enter there). Overwrites a"
            " configuration of that name if one already exists.")
        config_icon.set_tooltip_text(config_save_tooltip)
        config_save_btn = Gtk.Button()
        config_save_btn.set_image(config_icon)
        config_save_btn.set_relief(Gtk.ReliefStyle.NONE)
        config_save_btn.set_tooltip_text(config_save_tooltip)
        config_save_btn.connect(
            "clicked", self.on_config_save_button_clicked)
        output_box.pack_start(config_save_btn, False, False, 0)

        self.config_combo = Gtk.ComboBoxText.new_with_entry()
        for name in self._list_saved_configs():
            self.config_combo.append_text(name)
        self.config_combo.set_tooltip_text(
            _("Named configurations, saved to APS.ini in this tool's"
              " own folder. Each one remembers build mode, Gramps"
              " version checkboxes, output location, filters, and"
              " which addons are selected.\nPick one to load it. Type a"
              " name (new or existing) and press Enter -- or click the"
              " icon to the left -- to save the current settings under"
              " that name, overwriting it if it already exists. The"
              " name shown here is also restored automatically the"
              " next time this tool is opened."))
        self.config_combo.connect("changed", self.on_config_combo_changed)
        config_entry = self.config_combo.get_child()
        if config_entry is not None:
            config_entry.set_placeholder_text(_("Configuration name…"))
            config_entry.connect("activate", self.on_config_combo_activate)
        output_box.pack_start(self.config_combo, False, False, 0)

        vbox.pack_start(output_box, False, False, 0)

        # Restore whichever configuration was active when this tool was
        # last closed. Deferred via idle_add, same as the combo change
        # handlers, so it runs after the window is fully realized.
        last_used = self._get_last_used_config_name()
        if last_used and last_used in self._list_saved_configs():
            if config_entry is not None:
                config_entry.set_text(last_used)
            GLib.idle_add(self._load_named_config_idle, last_used)
        elif not self._list_saved_configs():
            # Genuinely fresh install -- no named configurations saved
            # in APS.ini yet, so nothing above had anything to restore.
            # Persist the defaults just built (Gramps Versions limited
            # to the running major version, plus build mode, output
            # location, and filters as built above) as a "default"
            # named configuration, so there's always at least one
            # saved to load/reuse later. Deferred via GLib.idle_add,
            # for the same reason as the last-used-configuration
            # restore just above: run after the window is fully
            # realized, so the Output location this captures reflects
            # this tool's actual installed location under the running
            # OS's own registered path to it, not whatever
            # get_output_parent_dir() might return before the window
            # is mapped.
            GLib.idle_add(self._seed_default_config_idle)

        # Separator
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Scrolled window for addon list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_tooltip_text(
            _("Select installed addons to package and publish."))
        vbox.pack_start(scrolled, True, True, 0)

        # Addon selection area
        self.addon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.addon_box.set_border_width(6)
        scrolled.add(self.addon_box)

        # Build the addon list
        self.rebuild_addon_list()

        # Separator
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Bottom row: Help (leftmost) + status + Pack and Ship (centre) + Close
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # Help icon, leftmost -- prefers opening this tool's own
        # README.md in Markdown Dash's standalone viewer, falling back
        # to this tool's registered help_url in the default browser
        # (see on_help_icon_clicked()).
        icon_theme = Gtk.IconTheme.get_default()
        try:
            help_pixbuf = icon_theme.load_icon("help-browser", 32, 0)
            help_icon = Gtk.Image.new_from_pixbuf(help_pixbuf)
        except GLib.Error:
            help_icon = Gtk.Image.new_from_icon_name(
                "help-browser", Gtk.IconSize.DIALOG)
        help_btn = Gtk.Button()
        help_btn.set_image(help_icon)
        help_btn.set_relief(Gtk.ReliefStyle.NONE)
        help_btn.set_tooltip_text(
            _("Open this tool's documentation."))
        help_btn.connect("clicked", self.on_help_icon_clicked)
        bottom_box.pack_start(help_btn, False, False, 0)

        # Status label on the left of the bottom row
        self.bottom_status_label = Gtk.Label()
        self.bottom_status_label.set_halign(Gtk.Align.START)
        bottom_box.pack_start(self.bottom_status_label, True, True, 0)

        # Pack and Ship centred
        github_btn = Gtk.Button(label=_("📦 Pack and Ship"))
        github_btn.get_style_context().add_class('suggested-action')
        github_btn.connect("clicked", self.on_package_for_github)
        bottom_box.pack_start(github_btn, False, False, 0)

        # Spacer to balance the status label on the left
        bottom_box.pack_start(Gtk.Label(), True, True, 0)

        # Close button on the right
        close_btn = Gtk.Button(label=_("Close"))
        close_btn.connect("clicked", self.close)
        bottom_box.pack_end(close_btn, False, False, 0)

        vbox.pack_start(bottom_box, False, False, 0)

        window.show_all()

    def get_addon_metadata(self, addon_name, use_cache=True):
        """
        Get metadata from the registered PluginData object for this addon.
        Uses the first plugin entry as the source for shared addon-level fields.
        Note: 'maintainers' / 'maintainers_email' are custom fields not parsed
        by Gramps' PluginRegister; they will be empty until Gramps' register()
        API is extended to support them (see enhancement request).
        """
        if use_cache and addon_name in self.metadata_cache:
            return self.metadata_cache[addon_name]

        metadata = {
            'name': '',
            'authors': [],
            'authors_email': [],
            'maintainers': [],
            'maintainers_email': [],
        }

        if addon_name not in self.addon_info:
            return metadata

        plugins = self.addon_info[addon_name].get('plugins', [])
        if not plugins:
            return metadata

        plugin = plugins[0]

        def _to_list(val):
            if not val:
                return []
            if isinstance(val, list):
                return [v for v in val if v]
            if isinstance(val, str) and val:
                return [val]
            return []

        if hasattr(plugin, 'name') and plugin.name:
            metadata['name'] = plugin.name
        metadata['authors']       = _to_list(getattr(plugin, 'authors', []))
        metadata['authors_email'] = _to_list(getattr(plugin, 'authors_email', []))
        # maintainers/maintainers_email: not standard PluginData fields;
        # will be empty until the Gramps register() API supports them.
        metadata['maintainers']       = _to_list(getattr(plugin, 'maintainers', []))
        metadata['maintainers_email'] = _to_list(getattr(plugin, 'maintainers_email', []))

        self.metadata_cache[addon_name] = metadata
        return metadata

    def extract_string_value(self, line):
        """
        Extract a simple string value like: "maintainers": "Brian McCullough"
        or name = _("Virtual Keyboard")
        Strips translation markers _()
        """
        try:
            if ':' in line:
                value = line.split(':', 1)[1].strip()
            elif '=' in line:
                value = line.split('=', 1)[1].strip()
            else:
                return ""

            value = value.rstrip(',').strip()

            # Remove translation marker _( )
            if value.startswith('_('):
                value = value[2:]  # Remove _( from start
            if value.endswith(')'):
                value = value[:-1]  # Remove ) from end

            # Remove quotes
            value = value.strip('"').strip("'").strip()

            return value
        except:
            return ""

    def extract_list_from_line(self, line):
        """
        Extract list items from a line like: authors = ["Name1", "Name2"]
        Returns all items in the list
        Validates proper formatting
        """
        items = []
        try:
            # Find content between brackets
            start = line.find('[')
            end = line.rfind(']')
            if start != -1 and end != -1:
                list_str = line[start+1:end]

                # Check for malformed entries (comma inside a quoted string)
                # This would indicate ["Name1, Name2"] instead of ["Name1", "Name2"]
                in_quotes = False
                quote_char = None
                has_comma_in_quotes = False

                for i, char in enumerate(list_str):
                    if char in ['"', "'"]:
                        if not in_quotes:
                            in_quotes = True
                            quote_char = char
                        elif char == quote_char:
                            in_quotes = False
                            quote_char = None
                    elif char == ',' and in_quotes:
                        has_comma_in_quotes = True
                        break

                if has_comma_in_quotes:
                    # Return a special error marker
                    return ['__MALFORMED__']

                # Split by comma and clean up
                for item in list_str.split(','):
                    item = item.strip().strip('"').strip("'")
                    if item:  # Only add non-empty items
                        items.append(item)
        except:
            pass
        return items

    def _pdata_search_text(self, pdata, addon_name):
        """
        Build a single lowercase search string for one pdata object.
        Includes all registration key/value pairs plus the addon dir name.
        """
        parts = [addon_name]
        if pdata is None:
            return addon_name.lower()
        for val in (
            getattr(pdata, 'id',                    '') or '',
            getattr(pdata, 'name',                  '') or '',
            getattr(pdata, 'description',           '') or '',
            getattr(pdata, 'version',               '') or '',
            getattr(pdata, 'fname',                 '') or '',
            getattr(pdata, 'fpath',                 '') or '',
            getattr(pdata, 'help_url',              '') or '',
            getattr(pdata, 'gramps_target_version', '') or '',
            getattr(pdata, 'viewclass',             '') or '',
            getattr(pdata, 'optionclass',           '') or '',
            str(getattr(pdata, 'category',          '') or ''),
            str(getattr(pdata, 'load_on_reg',       '') or ''),
            ' '.join(getattr(pdata, 'authors',       []) or []),
            ' '.join(getattr(pdata, 'authors_email', []) or []),
            ' '.join(getattr(pdata, 'requires_mod',  []) or []),
            ' '.join(getattr(pdata, 'requires_exe',  []) or []),
            PTYPE_STR.get(getattr(pdata, 'ptype', None), ''),
        ):
            if val:
                parts.append(str(val))
        return ' '.join(parts).lower()

    def _plugin_matches(self, pdata, addon_name, filter_text, type_filter):
        """
        Return True if this individual plugin matches both filters.

        type_filter  — must match pdata.ptype's string label, or '' for all.
        filter_text  — all words must appear in the plugin's search text.
        """
        # Type filter: compare against this plugin's own type
        if type_filter and type_filter != _("All Types"):
            ptype_num = getattr(pdata, 'ptype', None)
            ptype_str = PTYPE_STR.get(ptype_num, '') if ptype_num is not None else ''
            if ptype_str != type_filter:
                return False

        # Text filter
        if filter_text:
            haystack = self._pdata_search_text(pdata, addon_name)
            for word in filter_text.lower().split():
                if word not in haystack:
                    return False
        return True

    def matches_filter(self, addon_name, filter_text, type_filter=''):
        """
        Return True if any plugin in this addon directory matches both filters.
        Used to decide whether to show the directory group at all.
        """
        info = self.addon_info.get(addon_name, {})
        plugins = info.get('plugins', [])
        if not plugins:
            # No pdata objects — fall back to directory-name text search
            if type_filter and type_filter != _("All Types"):
                return False
            return not filter_text or filter_text.lower() in addon_name.lower()
        return any(
            self._plugin_matches(p, addon_name, filter_text, type_filter)
            for p in plugins
        )

    def _get_type_filter(self):
        """Return the currently selected type filter string, or '' for All."""
        if not hasattr(self, 'type_filter_combo'):
            return ''
        text = self.type_filter_combo.get_active_text()
        if not text or text == _("All Types"):
            return ''
        return text

    @staticmethod
    def _bump_patch_version(version_str):
        """
        Return `version_str` with its last dot-separated numeric
        component incremented by one (e.g. '1.8.12' -> '1.8.13'),
        matching the patch-version bump upstream make.py's own 'build'
        command performs automatically (see make_addon.py's module
        docstring for why that's not done automatically here).

        :param version_str: Current version string, or None/empty.
        :returns: the bumped version string.
        """
        if not version_str:
            return '0.0.1'
        parts = version_str.split('.')
        if parts and parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + 1)
            return '.'.join(parts)
        return f"{version_str}.1"

    @staticmethod
    def _increment_gpr_version_files(addon_path):
        """
        Increment the patch version number in every *gpr.py file under
        addon_path in place, mirroring the same increment upstream
        make.py performs automatically during its own 'build' command
        -- but only ever run here for an addon explicitly flagged via
        the version control next to its name, never automatically.

        :param addon_path: Real path to the addon's source directory.
        :returns: list of (filename, old_version, new_version) for
            every file actually changed.
        """
        changed = []
        pattern = re.compile(r"(version\s*=\s*['\"])(\d+(?:\.\d+)*)(['\"])")
        for fname in glob.glob(os.path.join(addon_path, '*gpr.py')):
            try:
                with open(fname, 'r', encoding='utf-8') as fh:
                    content = fh.read()
            except OSError:
                continue

            bumped = {}

            def _bump(match, bumped=bumped):
                old = match.group(2)
                parts = old.split('.')
                if parts[-1].isdigit():
                    parts[-1] = str(int(parts[-1]) + 1)
                new = '.'.join(parts)
                bumped['old'], bumped['new'] = old, new
                return f"{match.group(1)}{new}{match.group(3)}"

            new_content = pattern.sub(_bump, content, count=1)
            if bumped.get('old') and bumped.get('new') \
                    and bumped['old'] != bumped['new']:
                try:
                    with open(fname, 'w', encoding='utf-8') as fh:
                        fh.write(new_content)
                    changed.append(
                        (os.path.basename(fname), bumped['old'], bumped['new']))
                except OSError:
                    pass
        return changed

    def _build_version_increment_widget(self, addon_name, version):
        """
        Build the clickable version control shown after an addon's
        name: a small icon + the current version, which toggles to a
        preview of the bumped version (dark red) when clicked. Flagged
        addons have their .gpr.py patch version actually incremented
        the next time they're built (see build_for_versions()).

        :param addon_name: Directory name of the addon.
        :param version: Current version string from its .gpr.py.
        :returns: a Gtk.ToggleButton.
        """
        button = Gtk.ToggleButton()
        button.set_relief(Gtk.ReliefStyle.NONE)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        icon = Gtk.Image.new_from_icon_name(
            "preferences-system-sharing-symbolic", Gtk.IconSize.MENU)
        label = Gtk.Label()
        box.pack_start(icon, False, False, 0)
        box.pack_start(label, False, False, 0)
        button.add(box)

        self.version_bump_widgets[addon_name] = {
            'button': button, 'icon': icon, 'label': label,
            'version': version,
        }
        self._refresh_version_bump_widget(addon_name)

        button.set_active(addon_name in self.pending_version_bumps)
        button.connect('toggled', self.on_toggle_version_bump, addon_name)
        return button

    def _refresh_version_bump_widget(self, addon_name):
        """
        Update an addon's version-control icon/label/tooltip to match
        self.pending_version_bumps, without touching its toggled state
        (used both right after creating the widget and from the toggle
        handler itself).
        """
        widget_info = self.version_bump_widgets.get(addon_name)
        if not widget_info:
            return
        button = widget_info['button']
        icon, label = widget_info['icon'], widget_info['label']
        current_version = widget_info['version']

        if addon_name in self.pending_version_bumps:
            bumped = self._bump_patch_version(current_version)
            add_png = os.path.join(
                os.path.expanduser('~'), '.local', 'share', 'gramps',
                'images', 'add.png')
            if os.path.isfile(add_png):
                icon.set_from_file(add_png)
            else:
                icon.set_from_icon_name("list-add", Gtk.IconSize.MENU)
            label.set_markup(
                '<small><span foreground="darkred"><b>{}</b></span>'
                '</small>'.format(bumped))
            button.set_tooltip_text(
                _("Will bump {} to {} on next build. Click to"
                  " cancel.").format(addon_name, bumped))
        else:
            icon.set_from_icon_name(
                "preferences-system-sharing-symbolic", Gtk.IconSize.MENU)
            label.set_markup(
                '<small>{}</small>'.format(current_version or '?'))
            button.set_tooltip_text(
                _("Click to flag {} for a patch version bump ({} →"
                  " {}) on its next build.").format(
                      addon_name, current_version or '?',
                      self._bump_patch_version(current_version)))

    def on_toggle_version_bump(self, button, addon_name):
        """
        Handle clicking an addon's version control: toggle whether its
        .gpr.py patch version will be bumped the next time it's built.
        """
        if button.get_active():
            self.pending_version_bumps.add(addon_name)
        else:
            self.pending_version_bumps.discard(addon_name)
        self._refresh_version_bump_widget(addon_name)

    def rebuild_addon_list(self):
        """
        Rebuild the addon checkbox list.

        Layout per addon directory
        ──────────────────────────
        Single-plugin addon:
            ☐ Plugin Name [TYPE]
              <small>path  •  types</small>

        Multi-plugin addon (e.g. CardView with 11 plugins):
            📁 CardView/   [VIEW, VIEW, ...]   📂
              <small>path</small>
              ☐  Citation Card [VIEW]
              ☐  Event Card [VIEW]
              ☐  Family Card [VIEW]
              …

        The header row for multi-plugin groups is a non-interactive label —
        it shows the directory name, combined type list, and the MANIFEST
        folder button.  Each plugin gets its own indented checkbox.
        Gang-select: checking/unchecking any plugin in a group syncs all
        others in that group.

        Filter behaviour
        ────────────────
        Both the text filter and type combo operate at the PLUGIN level.
        A directory group is shown if any of its plugins match.  Within a
        group, plugins that do NOT match the current filter are hidden while
        matching ones remain visible.
        """
        # Flush current visible checkbox states
        for pid, checkbox in self.checkboxes.items():
            self.all_selections[pid] = checkbox.get_active()

        for child in self.addon_box.get_children():
            self.addon_box.remove(child)
        self.checkboxes = {}

        filter_text  = (self.author_filter_entry.get_text().strip()
                        if hasattr(self, 'author_filter_entry') else '')
        type_filter  = self._get_type_filter()
        build_mode   = self.get_build_mode()
        manifest_fn  = 'MANIFEST.beta' if build_mode == 'beta' else 'MANIFEST'

        try:
            Gtk.Image.new_from_icon_name("color-select-symbolic", Gtk.IconSize.BUTTON)
            use_image = True
        except Exception:
            use_image = False

        filtered_plugin_count = 0

        for addon_name in sorted(self.addon_info.keys()):
            info    = self.addon_info[addon_name]
            plugins = info.get('plugins', [])

            # Filter at plugin level — keep only matching plugins
            def _pname(p):
                return getattr(p, 'name', '') or ''

            plugins_sorted = sorted(plugins, key=_pname)
            matching = [p for p in plugins_sorted
                        if self._plugin_matches(p, addon_name,
                                                filter_text, type_filter)]
            if not matching:
                # No matching plugins in this directory — skip the whole group
                continue

            is_multi = len(plugins_sorted) > 1  # multi = dir has >1 plugin total

            # ── MANIFEST folder button (shared by whole group) ────────────
            manifest_path   = os.path.join(info['path'], manifest_fn)
            manifest_exists = os.path.exists(manifest_path)

            def _make_folder_btn(aname=addon_name, mp=manifest_path,
                                 me=manifest_exists):
                btn = Gtk.Button()
                btn.set_relief(Gtk.ReliefStyle.NONE)
                if use_image:
                    btn.set_image(Gtk.Image.new_from_icon_name(
                        "color-select-symbolic", Gtk.IconSize.BUTTON))
                else:
                    btn.set_label("📂")
                tip = (_(
                    "Open {} for {}\n\nFile exists — will append a refreshed "
                    "directory listing and open in your text editor.\n\n"
                    "Path: {}"
                ).format(manifest_fn, aname, mp)
                       if me else
                       _(
                    "Create {} for {}\n\nFile does not exist yet — will create "
                    "it with a header and directory listing, then open in your "
                    "text editor.\n\nFolder: {}"
                ).format(manifest_fn, aname, info['path']))
                btn.set_tooltip_text(tip)
                btn.connect('clicked',
                            lambda w, n=aname: self.on_open_manifest_for_addon(n))
                return btn

            if is_multi:
                # ── Group header row (non-interactive) ────────────────────
                # Shows the directory name + combined types + version
                # control + MANIFEST button. Not a checkbox; just an
                # informational label (version applies to the whole
                # addon directory, i.e. its shared .gpr.py file(s)).
                hdr_hbox = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

                all_types_str = ', '.join(sorted(info['types']))
                hdr_label = Gtk.Label()
                hdr_label.set_markup(
                    '<b>📁 {}/</b>  <small>[{}]</small>'.format(
                        addon_name, all_types_str))
                hdr_label.set_halign(Gtk.Align.START)
                hdr_label.set_hexpand(True)

                path_label = Gtk.Label()
                path_label.set_markup(
                    '<small><i>{}</i></small>'.format(info['path']))
                path_label.set_halign(Gtk.Align.START)

                hdr_vbox = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL, spacing=1)
                hdr_vbox.pack_start(hdr_label,  False, False, 0)
                hdr_vbox.pack_start(path_label, False, False, 0)

                group_version = next(
                    (getattr(p, 'version', None) for p in matching
                     if getattr(p, 'version', None)), None)
                version_widget = self._build_version_increment_widget(
                    addon_name, group_version)

                hdr_hbox.pack_start(hdr_vbox,          True,  True,  0)
                hdr_hbox.pack_start(version_widget,     False, False, 0)
                hdr_hbox.pack_start(_make_folder_btn(), False, False, 0)
                self.addon_box.pack_start(hdr_hbox, False, False, 0)

                # ── One checkbox row per matching plugin ───────────────────
                for pdata in matching:
                    pid = getattr(pdata, 'id', None)
                    if not pid:
                        continue
                    self.plugin_to_dir[pid] = addon_name

                    cb_label = '  {}'.format(
                        getattr(pdata, 'name', pid) or pid)

                    plugin_id_label = getattr(pdata, 'id', '')
                    row = Gtk.Box(
                        orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                    cb = Gtk.CheckButton(label=cb_label)
                    cb.set_margin_start(20)
                    if pid in self.all_selections:
                        cb.set_active(self.all_selections[pid])
                    cb.connect('toggled', self.on_selection_changed, pid)

                    id_lbl = Gtk.Label()
                    id_lbl.set_markup(
                        '<small><tt>    {}</tt></small>'.format(plugin_id_label))
                    id_lbl.set_halign(Gtk.Align.START)

                    cb_vbox = Gtk.Box(
                        orientation=Gtk.Orientation.VERTICAL, spacing=0)
                    cb_vbox.pack_start(cb,     False, False, 0)
                    cb_vbox.pack_start(id_lbl, False, False, 0)

                    row.pack_start(cb_vbox, True, True, 0)
                    self.checkboxes[pid] = cb
                    self.addon_box.pack_start(row, False, False, 0)
                    filtered_plugin_count += 1

                # Separator after the group
                sep = Gtk.Separator()
                sep.set_margin_top(3)
                sep.set_margin_bottom(3)
                self.addon_box.pack_start(sep, False, False, 0)

            else:
                # ── Single-plugin addon: one combined row ──────────────────
                pdata = matching[0]
                pid   = getattr(pdata, 'id', None)
                if not pid:
                    continue
                self.plugin_to_dir[pid] = addon_name

                cb_label = getattr(pdata, 'name', pid) or pid

                row_hbox = Gtk.Box(
                    orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
                cb_vbox  = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL, spacing=1)

                cb = Gtk.CheckButton(label=cb_label)
                if pid in self.all_selections:
                    cb.set_active(self.all_selections[pid])
                cb.connect('toggled', self.on_selection_changed, pid)
                cb_vbox.pack_start(cb, False, False, 0)

                detail = Gtk.Label()
                detail.set_markup(
                    '<small><i>   {}  •  {}</i></small>'.format(
                        ', '.join(sorted(info['types'])), info['path']))
                detail.set_halign(Gtk.Align.START)
                cb_vbox.pack_start(detail, False, False, 0)

                version_widget = self._build_version_increment_widget(
                    addon_name, getattr(pdata, 'version', None))

                row_hbox.pack_start(cb_vbox,            True,  True,  0)
                row_hbox.pack_start(version_widget,     False, False, 0)
                row_hbox.pack_start(_make_folder_btn(), False, False, 0)

                self.checkboxes[pid] = cb
                self.addon_box.pack_start(row_hbox, False, False, 0)
                filtered_plugin_count += 1

        self.update_selection_count(filter_text, filtered_plugin_count)
        self.addon_box.show_all()

    def on_selection_changed(self, widget, pid=None):
        """
        Called when any checkbox is toggled.

        Gang-select: if the toggled plugin belongs to a multi-plugin addon
        directory, all other visible plugins in that same directory are set
        to the same state.  A re-entrancy guard prevents the gang callbacks
        from triggering further gang cascades.
        """
        if self._gang_in_progress:
            return

        # Save the state of the toggled plugin
        if pid is not None:
            self.all_selections[pid] = widget.get_active()

            # Gang-select: find all visible siblings in the same directory
            addon_dir = self.plugin_to_dir.get(pid)
            if addon_dir:
                new_state = widget.get_active()
                self._gang_in_progress = True
                try:
                    for sibling_pid, sibling_cb in self.checkboxes.items():
                        if (sibling_pid != pid
                                and self.plugin_to_dir.get(sibling_pid) == addon_dir):
                            sibling_cb.set_active(new_state)
                            self.all_selections[sibling_pid] = new_state
                finally:
                    self._gang_in_progress = False

        # Save all currently visible checkbox states
        for p, checkbox in self.checkboxes.items():
            self.all_selections[p] = checkbox.get_active()

        filter_text = ""
        if hasattr(self, 'author_filter_entry'):
            filter_text = self.author_filter_entry.get_text().strip()
        self.update_selection_count(filter_text, len(self.checkboxes))

    def on_build_mode_changed(self, widget):
        """
        Called when the β/Δ radio button changes — refresh per-row folder button
        tooltips so they always name the correct MANIFEST file.
        """
        # Rebuild the list so folder-button tooltips update to the new filename.
        self.rebuild_addon_list()

    def on_open_manifest_for_addon(self, addon_name):
        """
        Open or create the MANIFEST (or MANIFEST.beta) for a single addon.
        Temporarily selects only this addon's plugins so on_edit_manifest
        can find it, then restores the previous selection state.
        """
        saved_selections = dict(self.all_selections)

        # Temporarily select only plugin_ids belonging to this addon
        for pid in self.all_selections:
            self.all_selections[pid] = (
                self.plugin_to_dir.get(pid) == addon_name)

        # Sync visible checkboxes without firing gang-select
        self._gang_in_progress = True
        try:
            for pid, cb in self.checkboxes.items():
                cb.set_active(self.all_selections.get(pid, False))
        finally:
            self._gang_in_progress = False

        self.on_edit_manifest(None)

        # Restore
        self.all_selections = saved_selections
        self._gang_in_progress = True
        try:
            for pid, cb in self.checkboxes.items():
                cb.set_active(saved_selections.get(pid, False))
        finally:
            self._gang_in_progress = False

        filter_text = ""
        if hasattr(self, 'author_filter_entry'):
            filter_text = self.author_filter_entry.get_text().strip()
        self.update_selection_count(filter_text, len(self.checkboxes))

    def update_selection_count(self, filter_text, visible_plugin_count):
        """
        When nothing is selected, show the same "Found N bundles (M
        registered plugins) in your Gramps installation" summary that
        used to live in a permanent label at the top of the window.
        As soon as at least one bundle is selected, replace it with
        the live "Selected bundles: X/Y • Plugins: V/T" readout.
        X = selected bundle count, Y = total bundles
        V = visible plugins (after filter), T = total plugins
        The Plugins ratio uses V/T so the user can see filter effect at a glance.
        """
        if not hasattr(self, 'bottom_status_label'):
            return

        # Count unique selected bundles (directories)
        selected_dirs = set(
            self.plugin_to_dir[pid]
            for pid, checked in self.all_selections.items()
            if checked and pid in self.plugin_to_dir
        )
        selected_count = len(selected_dirs)
        total_bundles  = getattr(self, '_total_bundles',  len(self.addon_info))
        total_plugins  = getattr(self, '_total_plugins',
                                  sum(len(i['plugins'])
                                      for i in self.addon_info.values()))

        if selected_count == 0:
            self.bottom_status_label.set_markup(
                _("<small>Found <b>{bundle_count}</b> bundles"
                  " (<b>{plugin_count}</b> registered plugins) in your"
                  " Gramps installation.</small>").format(
                      bundle_count=total_bundles, plugin_count=total_plugins))
        else:
            self.bottom_status_label.set_markup(
                f"<small>Selected bundles: <b>{selected_count}/{total_bundles}</b>"
                f"  \u2022  "
                f"Plugins: <b>{visible_plugin_count}/{total_plugins}</b></small>"
            )

    def on_filter_changed(self, widget):
        """
        Handle filter text changes
        """
        self.rebuild_addon_list()

    def on_clear_filter(self, widget=None):
        """
        Clear the search entry and reset the type combo to 'All Types'.
        Called by the type combo reset path; the SearchEntry clears itself
        via its built-in ✕ button which fires search-changed automatically.
        """
        self.author_filter_entry.set_text("")
        if hasattr(self, 'type_filter_combo'):
            self.type_filter_combo.set_active(0)

    def get_selected_addons(self):
        """
        Return a deduplicated list of (addon_dir_name, addon_path) tuples
        for every addon directory that has at least one checked plugin_id.

        Because multiple plugin_ids map to the same directory (gang-select
        keeps them in sync), we collect unique directory names only.
        The returned list is sorted by directory name for reproducible output.
        """
        # Flush current visible checkbox states
        for pid, checkbox in self.checkboxes.items():
            self.all_selections[pid] = checkbox.get_active()

        seen_dirs = set()
        selected = []
        for pid, checked in self.all_selections.items():
            if not checked:
                continue
            addon_dir = self.plugin_to_dir.get(pid)
            if addon_dir and addon_dir not in seen_dirs:
                seen_dirs.add(addon_dir)
                if addon_dir in self.addon_info:
                    selected.append(
                        (addon_dir, self.addon_info[addon_dir]['path']))
        return sorted(selected, key=lambda t: t[0])

    def on_select_all(self, widget):
        """Select all visible plugin checkboxes (gang-select fires automatically)."""
        self._gang_in_progress = True
        try:
            for checkbox in self.checkboxes.values():
                checkbox.set_active(True)
        finally:
            self._gang_in_progress = False
        self.on_selection_changed(None)

    def on_deselect_all(self, widget):
        """Deselect ALL plugin checkboxes including ones hidden by filter."""
        for pid in list(self.all_selections):
            self.all_selections[pid] = False
        self._gang_in_progress = True
        try:
            for checkbox in self.checkboxes.values():
                checkbox.set_active(False)
        finally:
            self._gang_in_progress = False
        self.on_selection_changed(None)

    def run_make_command(self, addon_path, command, build_mode='beta',
                          version=None):
        """
        Run make_addon.py command using the bundled script.
        Pass plugin type number and build mode to the packaging engine.

        version:    Gramps version code (e.g. 'gramps52') selecting which
                    output subdirectory to build/list into. Defaults to
                    the module-level GRAMPS_VERSION when not given.
        build_mode: 'beta' or 'release'

        For 'listing', make_addon.py delegates to the matching bundled
        make<NN>.py when present, which generates every language the
        addon has a po/*-local.po for -- no separate language selection
        is needed here.
        """
        addon_name = os.path.basename(addon_path)
        version = version or GRAMPS_VERSION

        # Scripts (make_addon.py itself) always live alongside this
        # tool; output can be redirected elsewhere via "Output Location".
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        make_script = os.path.join(scripts_dir, 'make_addon.py')

        # Output directory - create <version> subdirectory (e.g. gramps52)
        # under the chosen output parent folder (defaults to scripts_dir).
        output_dir = os.path.join(self.get_output_parent_dir(), version)
        os.makedirs(output_dir, exist_ok=True)

        if not os.path.exists(make_script):
            return False, "", _("make_addon.py not found in AddonPackShip directory")

        try:
            env = os.environ.copy()

            # Pass plugin type number for listing command
            if command == 'listing' and addon_name in self.addon_info:
                ptype_nums = self.addon_info[addon_name].get('ptype_nums', set())
                if ptype_nums:
                    env['PLUGIN_TYPE_NUM'] = str(min(ptype_nums))

            # Pass build mode to packaging engine
            env['BUILD_MODE'] = build_mode

            # Pass the live sys.path so the subprocess can import Gramps.
            # Required for listing (exec+make_environment gpr parsing) and
            # compile (xgettext fallback). Avoids any GRAMPSPATH guessing.
            env['GRAMPS_PYTHONPATH'] = os.pathsep.join(
                p for p in sys.path if p  # skip empty-string entries
            )

            # Use sys.executable to run with the same Python that's running Gramps
            # This works on Windows with bundled Python, Linux, and macOS
            cmd = [sys.executable, make_script, command, addon_path, output_dir]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env
            )

            # Add output location info to stdout
            if result.returncode == 0:
                location_info = self.get_output_location_info(command, output_dir, addon_name)
                output = result.stdout + "\n" + location_info
            else:
                output = result.stdout

            return result.returncode == 0, output, result.stderr
        except Exception as e:
            return False, "", str(e)

    def build_for_versions(self, addon_path, build_mode, versions):
        """
        Build the addon package once for the first of `versions`, then
        duplicate the resulting .addon.tgz into the download/ directory
        of every other selected version.

        If this addon is flagged in self.pending_version_bumps (via its
        version control in the addon list), its .gpr.py patch version
        is incremented in place *before* building, so the new version
        number is what actually gets packaged -- then the flag is
        cleared and the addon list is refreshed to show the new
        current version.

        The archive's contents (.py, .gpr.py, locale/*.mo, etc.) do not
        depend on which Gramps version is being targeted, so duplicating
        the file avoids rebuilding an identical archive once per version.

        :returns: (success, stdout, stderr) for the primary build; any
            duplication notes are appended to stdout.
        """
        addon_name = os.path.basename(addon_path)
        primary, *other_versions = versions

        bump_notes = []
        if addon_name in self.pending_version_bumps:
            changed = self._increment_gpr_version_files(addon_path)
            for fname, old_version, new_version in changed:
                bump_notes.append(
                    _("  Version bumped in {}: {} → {}").format(
                        fname, old_version, new_version))
            self.pending_version_bumps.discard(addon_name)
            if changed:
                # Reflect the new version directly rather than
                # re-scanning: Gramps' plugin registry may still hold
                # the pre-bump value cached from when Gramps started,
                # so a rescan here isn't guaranteed to see the edit.
                widget_info = self.version_bump_widgets.get(addon_name)
                if widget_info:
                    widget_info['version'] = changed[0][2]
                    self._refresh_version_bump_widget(addon_name)

        success, stdout, stderr = self.run_make_command(
            addon_path, 'build', build_mode=build_mode, version=primary)
        if bump_notes:
            stdout = "\n".join(bump_notes) + "\n" + stdout
        if not success or not other_versions:
            return success, stdout, stderr

        builder_dir = self.get_output_parent_dir()
        src_tgz = os.path.join(
            builder_dir, primary, 'download', f"{addon_name}.addon.tgz")

        duplicate_notes = []
        if os.path.exists(src_tgz):
            for version in other_versions:
                dst_dir = os.path.join(builder_dir, version, 'download')
                os.makedirs(dst_dir, exist_ok=True)
                dst_tgz = os.path.join(dst_dir, f"{addon_name}.addon.tgz")
                try:
                    shutil.copy2(src_tgz, dst_tgz)
                    duplicate_notes.append(
                        _("  Duplicated package for {}").format(version))
                except OSError as exc:
                    duplicate_notes.append(
                        _("  Could not duplicate package for {}: {}").format(
                            version, exc))
        else:
            duplicate_notes.append(
                _("  Warning: built package not found — nothing to"
                  " duplicate for {}").format(", ".join(other_versions)))

        if duplicate_notes:
            stdout = stdout + "\n" + "\n".join(duplicate_notes)

        return success, stdout, stderr

    def get_output_location_info(self, command, output_dir, addon_name):
        """
        Get information about where output files were created
        """
        info_lines = []

        if command == 'build':
            tgz_path = os.path.join(output_dir, 'download', f"{addon_name}.addon.tgz")
            if os.path.exists(tgz_path):
                info_lines.append(f"📦 Package created: {tgz_path}")

        elif command == 'compile':
            # Compile puts locale in the addon directory, not output_dir
            addon_path = None
            for name, info in self.addon_info.items():
                if name == addon_name:
                    addon_path = info['path']
                    break
            if addon_path:
                locale_path = os.path.join(addon_path, 'locale')
                if os.path.exists(locale_path):
                    info_lines.append(f"🌍 Translations compiled in: {locale_path}")

        elif command == 'listing':
            listings_dir = os.path.join(output_dir, 'listings')
            listing_files = []
            if os.path.isdir(listings_dir):
                listing_files = sorted(
                    fn for fn in os.listdir(listings_dir)
                    if fn.startswith('addons-')
                    and (fn.endswith('.json') or fn.endswith('.txt'))
                )
            if listing_files:
                info_lines.append(
                    f"📋 Listing(s) updated: {', '.join(listing_files)}")
                if any(fn.endswith('.txt') for fn in listing_files):
                    info_lines.append(
                        "   (.txt = legacy listing format used by Gramps"
                        " versions before 5.2 — expected, not an error)")
            else:
                info_lines.append(f"⚠️  Listing file not created - may need to Build first")

        elif command == 'clean':
            info_lines.append(f"🧹 Cleaned temporary files from {addon_name}")

        return "\n".join(info_lines)

    def on_edit_manifest(self, widget):
        """
        Create or edit MANIFEST for the single selected addon.
        - Looks for existing MANIFEST in addon folder
        - Creates it if none exists
        - Appends 4-line spacer + full recursive directory listing
        - Opens in OS default text editor
        """
        selected = self.get_selected_addons()

        if len(selected) != 1:
            OkDialog(
                _("Single Selection Required"),
                _("Please select exactly one addon to edit its MANIFEST."),
                parent=self.window
            )
            return

        addon_name, addon_path = selected[0]
        build_mode = self.get_build_mode()
        manifest_filename = 'MANIFEST.beta' if build_mode == 'beta' else 'MANIFEST'
        manifest_path = os.path.join(addon_path, manifest_filename)
        is_new_file = not os.path.exists(manifest_path)

        # ── Build the annotated directory listing ──────────────────────────────
        # Shows EVERY file in the addon directory, annotated with whether it is
        # already auto-included or needs a MANIFEST entry to be packed.
        # Lines for auto-included files are prefixed with "# [auto]" so the user
        # can see the full package inventory at a glance.
        import datetime
        listing_lines = []
        listing_lines.append(
            f"# Full directory listing of {addon_name}/  —  {datetime.date.today()}"
        )
        listing_lines.append(
            f"# [auto]  = already included automatically in this build mode"
        )
        listing_lines.append(
            f"# [add?]  = NOT yet included — uncomment/copy to entries section above to add"
        )
        listing_lines.append(
            f"# [skip]  = intentionally excluded (temp/cache file)"
        )
        listing_lines.append("")

        # Extensions always auto-included by build_addon()
        always_auto_ext = {'.py', '.glade', '.xml'}
        # .mo files are auto-included after compile; locale/ dir is walked by build_addon
        # .md files auto-included in beta; README.md auto-included in release
        # .po / .pot auto-included in beta
        skip_ext   = {'.pyc', '.pyo'}   # never included
        always_auto_fnames = {'MANIFEST', 'MANIFEST.beta'}  # auto-included in beta

        for root, dirs, files in os.walk(addon_path):
            dirs[:] = sorted(
                d for d in dirs
                if not d.startswith('.')
                and d not in ('__pycache__',)
            )

            rel_root = os.path.relpath(root, os.path.dirname(addon_path))
            rel_root = rel_root.replace(os.sep, '/')

            for fname in sorted(files):
                ext = os.path.splitext(fname)[1].lower()

                # Determine annotation
                if fname.endswith('~') or ext in skip_ext:
                    tag = '[skip]'
                elif fname == manifest_filename:
                    # The MANIFEST file being edited is auto-included in beta,
                    # but don't show it as an entry to copy (it IS the file).
                    tag = '[auto]  ← this file'
                elif ext in always_auto_ext:
                    tag = '[auto]  ← .py/.glade/.xml always packed'
                elif ext == '.mo':
                    tag = '[auto]  ← compiled translation'
                elif rel_root.endswith('/locale') or '/locale/' in rel_root:
                    tag = '[auto]  ← locale/ tree always packed'
                elif fname in always_auto_fnames and build_mode == 'beta':
                    tag = '[auto]  ← included in β Beta builds'
                elif ext == '.md':
                    if build_mode == 'beta':
                        tag = '[auto]  ← *.md auto-included in β Beta'
                    elif fname == 'README.md':
                        tag = '[auto]  ← README.md included in Δ Release'
                    else:
                        tag = '[add?]'
                elif ext in ('.po', '.pot'):
                    if build_mode == 'beta':
                        tag = '[auto]  ← po/ files auto-included in β Beta'
                    else:
                        tag = '[skip]  ← po/ excluded from Δ Release'
                elif rel_root.endswith('/po') or '/po/' in rel_root:
                    if build_mode == 'beta':
                        tag = '[auto]  ← po/ auto-included in β Beta'
                    else:
                        tag = '[skip]  ← po/ excluded from Δ Release'
                else:
                    tag = '[add?]'

                listing_lines.append(f"# {tag}  {rel_root}/{fname}")

        listing_text = "\n".join(listing_lines)

        # ── Read existing MANIFEST for seeding ────────────────────────────────
        # When creating a new MANIFEST.beta, seed the entries section with
        # the content of any existing MANIFEST so nothing already documented
        # for Release is lost or has to be re-entered for Beta.
        existing_manifest_seed = ""
        if is_new_file and build_mode == 'beta':
            release_manifest_path = os.path.join(addon_path, 'MANIFEST')
            if os.path.exists(release_manifest_path):
                with open(release_manifest_path, 'r', encoding='utf-8') as f:
                    existing_manifest_seed = f.read().rstrip('\n')

        # ── Read or create MANIFEST / MANIFEST.beta ───────────────────────────
        if not is_new_file:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                existing = f.read()
            content = existing.rstrip('\n') + "\n\n" + listing_text + "\n"
            action = "updated"
        else:
            if build_mode == 'beta':
                header = (
                    f"# MANIFEST.beta for {addon_name}\n"
                    f"# β Beta/development build — lists additional files beyond auto-includes.\n"
                    f"# Auto-included in β Beta: *.py, *.gpr.py, *.glade, *.xml, locale/*.mo,\n"
                    f"#   *.md, po/*.po, po/template.pot, MANIFEST, MANIFEST.beta,\n"
                    f"#   and all subdirectory contents.\n"
                    f"# Use this file to OVERRIDE that behavior with explicit patterns,\n"
                    f"# or leave it absent to use all auto-includes.\n"
                    f"#\n"
                    f"# Examples:\n"
                    f"#   {addon_name}/data/*\n"
                    f"#   {addon_name}/layouts/*.csv\n"
                    f"#   {addon_name}/README.md\n"
                )
            else:
                header = (
                    f"# MANIFEST for {addon_name}\n"
                    f"# Δ Release build — lists extras beyond the release defaults.\n"
                    f"# Release defaults: *.py, *.gpr.py, *.glade, *.xml,\n"
                    f"#   locale/*.mo, README.md.\n"
                    f"# Add subdirectory contents, data files, etc. here.\n"
                    f"# NOTE: po/ source files are intentionally excluded from Release.\n"
                    f"#\n"
                    f"# Examples:\n"
                    f"#   {addon_name}/data/*\n"
                    f"#   {addon_name}/layouts/*.csv\n"
                )

            # Entry section: seed from existing MANIFEST if available,
            # otherwise leave blank for the user to fill in
            if existing_manifest_seed:
                seed_note = (
                    f"# --- Seeded from existing MANIFEST ---\n"
                    f"{existing_manifest_seed}\n"
                    f"# --- Add your entries below this line ---"
                )
                entries_section = "\n" + seed_note
            else:
                entries_section = "\n# --- Add your entries below this line ---"

            content = header + entries_section + "\n\n" + listing_text + "\n"
            action = "created"

        # Write the file
        with open(manifest_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # ── Open in default OS text editor ───────────────────────────────────
        try:
            if sys.platform.startswith('win'):
                os.startfile(manifest_path)
            elif sys.platform.startswith('darwin'):
                subprocess.Popen(['open', manifest_path])
            else:
                # Linux - try common editors in order
                for editor_cmd in ['xdg-open', 'gedit', 'kate', 'mousepad',
                                   'xed', 'geany', 'nano']:
                    try:
                        subprocess.Popen([editor_cmd, manifest_path])
                        break
                    except FileNotFoundError:
                        continue

            OkDialog(
                _("MANIFEST {}").format(action.capitalize()),
                _("{} has been {} for {}.\n\n"
                  "Location:\n  {}\n\n"
                  "The file has been opened in your default text editor.\n\n"
                  "The bottom of the file shows files not yet in the MANIFEST\n"
                  "(auto-included files like .py and .glade are omitted).\n"
                  "Copy any lines you want to include into the body above.").format(
                      manifest_filename, action, addon_name, manifest_path),
                parent=self.window
            )
        except Exception as e:
            OkDialog(
                _("MANIFEST {}").format(action.capitalize()),
                _("{} has been {} for {}.\n\n"
                  "Location:\n  {}\n\n"
                  "Could not open editor automatically: {}\n"
                  "Please open the file manually.").format(
                      manifest_filename, action, addon_name, manifest_path, str(e)),
                parent=self.window
            )

    def on_build(self, widget):
        """
        Build selected addons (after validation)
        """
        selected = self.get_selected_addons()
        if not selected:
            OkDialog(
                _("No Selection"),
                _("Please select at least one addon to build."),
                parent=self.window
            )
            return

        # Validate all selected addons first
        malformed = []
        for addon_name, addon_path in selected:
            metadata = self.get_addon_metadata(addon_name)
            if metadata.get('malformed'):
                malformed.append((addon_name, metadata['malformed']))

        if malformed:
            error_msg = _("Cannot build - the following addon(s) have malformed .gpr.py files:\n\n")
            for addon_name, fields in malformed:
                error_msg += f"• {addon_name}: {', '.join(fields)}\n"

            error_msg += _("\n\nProblem: These fields contain commas INSIDE quoted strings.\n\n")
            error_msg += _("Wrong:  authors = [\"Name1, Name2\"]\n")
            error_msg += _("Correct: authors = [\"Name1\", \"Name2\"]\n\n")
            error_msg += _("Please fix the .gpr.py file(s) and try again.")

            ErrorDialog(
                _("Malformed .gpr.py File"),
                error_msg,
                parent=self.window
            )
            return

        self.show_operation_results("Build", selected, "build")

    def on_compile(self, widget):
        """
        Compile translations for selected addons
        """
        selected = self.get_selected_addons()
        if not selected:
            OkDialog(
                _("No Selection"),
                _("Please select at least one addon to compile."),
                parent=self.window
            )
            return

        self.show_operation_results("Compile", selected, "compile")

    def on_listing(self, widget):
        """
        Create listings for selected addons (after validation)
        """
        selected = self.get_selected_addons()
        if not selected:
            OkDialog(
                _("No Selection"),
                _("Please select at least one addon to list."),
                parent=self.window
            )
            return

        # Validate all selected addons first
        malformed = []
        for addon_name, addon_path in selected:
            metadata = self.get_addon_metadata(addon_name)
            if metadata.get('malformed'):
                malformed.append((addon_name, metadata['malformed']))

        if malformed:
            error_msg = _("Cannot create listing - the following addon(s) have malformed .gpr.py files:\n\n")
            for addon_name, fields in malformed:
                error_msg += f"• {addon_name}: {', '.join(fields)}\n"

            error_msg += _("\n\nProblem: These fields contain commas INSIDE quoted strings.\n\n")
            error_msg += _("Wrong:  authors = [\"Name1, Name2\"]\n")
            error_msg += _("Correct: authors = [\"Name1\", \"Name2\"]\n\n")
            error_msg += _("Please fix the .gpr.py file(s) and try again.")

            ErrorDialog(
                _("Malformed .gpr.py File"),
                error_msg,
                parent=self.window
            )
            return

        # Get output directories for every selected Gramps version
        builder_dir = self.get_output_parent_dir()
        versions = self.get_selected_versions()

        # Check if the .tgz exists for every selected version
        missing_tgz = []
        for addon_name, addon_path in selected:
            missing_for = [
                v for v in versions
                if not os.path.exists(os.path.join(
                    builder_dir, v, 'download', f"{addon_name}.addon.tgz"))
            ]
            if missing_for:
                missing_tgz.append(addon_name)

        if missing_tgz:
            from gramps.gui.dialog import QuestionDialog2
            question = QuestionDialog2(
                _("Missing Package Files"),
                _("The following addons don't have .addon.tgz files yet:\n\n{}\n\n"
                  "Listings require built packages. Would you like to:\n"
                  "• Build these addons first (recommended), or\n"
                  "• Try creating listings anyway (may result in empty entries)").format(
                      "\n".join(f"  • {n}" for n in missing_tgz)),
                _("Build First"),
                _("Create Anyway"),
                parent=self.window
            )

            response = question.run()
            if response:  # Build First
                # Build the missing ones
                missing_addons = [(n, p) for n, p in selected if n in missing_tgz]
                self.show_operation_results("Build", missing_addons, "build")
                # Then proceed with listing

        self.show_operation_results("Listing", selected, "listing")

    def on_clean(self, widget):
        """
        Clean selected addons (with confirmation)
        """
        selected = self.get_selected_addons()
        if not selected:
            OkDialog(
                _("No Selection"),
                _("Please select at least one addon to clean."),
                parent=self.window
            )
            return

        # Show confirmation for Clean operation
        from gramps.gui.dialog import QuestionDialog2

        addon_names = [name for name, path in selected]

        question = QuestionDialog2(
            _("Clean Selected Addons?"),
            _("This will remove Python cache files from:\n\n{}\n\n"
              "═══════════════════════════════════════════\n"
              "WILL BE REMOVED (Python regenerates these):\n"
              "═══════════════════════════════════════════\n"
              "• __pycache__/ directories\n"
              "• *.pyc and *.pyo files (bytecode)\n"
              "• *~ backup files (editor temps)\n\n"
              "═══════════════════════════════════════════\n"
              "WILL BE PRESERVED (your work):\n"
              "═══════════════════════════════════════════\n"
              "• locale/ (compiled translations - needed!)\n"
              "• po/template.pot (translator reference)\n"
              "• po/*.po (translation source files)\n"
              "• All source code and data files\n\n"
              "Python will automatically regenerate cache files\n"
              "when you restart Gramps.\n\n"
              "Continue with Clean?").format("\n".join(f"  • {n}" for n in addon_names)),
            _("Yes, Clean Cache"),
            _("No, Cancel"),
            parent=self.window
        )

        response = question.run()
        if response:
            self.show_operation_results("Clean", selected, "clean")

    def get_build_mode(self):
        """Returns 'beta' or 'release' based on radio button state"""
        if hasattr(self, 'radio_release') and self.radio_release.get_active():
            return 'release'
        return 'beta'

    def on_package_for_github(self, widget):
        """
        Package selected addons for GitHub (template.pot, .tgz + .json) - after validation
        """
        selected = self.get_selected_addons()
        if not selected:
            OkDialog(
                _("No Selection"),
                _("Please select at least one addon to package."),
                parent=self.window
            )
            return

        # Validate all selected addons first
        malformed = []
        for addon_name, addon_path in selected:
            metadata = self.get_addon_metadata(addon_name)
            if metadata.get('malformed'):
                malformed.append((addon_name, metadata['malformed']))

        if malformed:
            error_msg = _("Cannot package - the following addon(s) have malformed .gpr.py files:\n\n")
            for addon_name, fields in malformed:
                error_msg += f"• {addon_name}: {', '.join(fields)}\n"

            error_msg += _("\n\nProblem: These fields contain commas INSIDE quoted strings.\n\n")
            error_msg += _("Wrong:  authors = [\"Name1, Name2\"]\n")
            error_msg += _("Correct: authors = [\"Name1\", \"Name2\"]\n\n")
            error_msg += _("Please fix the .gpr.py file(s) and try again.")

            ErrorDialog(
                _("Malformed .gpr.py File"),
                error_msg,
                parent=self.window
            )
            return

        build_mode = self.get_build_mode()

        # Warn before Release build - it is intentionally lossy
        if build_mode == 'release':
            addon_names = [name for name, path in selected]
            from gramps.gui.dialog import QuestionDialog2
            question = QuestionDialog2(
                _("Δ Release Build — Intentionally Lossy"),
                _("You are about to create a RELEASE package for:\n\n"
                  "{}\n\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                  "WILL BE INCLUDED:\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                  "• All core files (.py, .gpr.py, .glade, .xml)\n"
                  "• README.md (if present)\n"
                  "• Compiled translations (locale/*.mo)\n"
                  "• MANIFEST extras (if MANIFEST present)\n\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                  "INTENTIONALLY EXCLUDED:\n"
                  "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                  "• po/*.po translation source files\n"
                  "• po/template.pot\n"
                  "• CHANGELOG.md and other .md files\n"
                  "• MANIFEST.beta and development files\n\n"
                  "⚠  This package is NOT suitable for translators\n"
                  "   or beta testers who need source files.\n\n"
                  "Use β Beta mode for development sharing.\n\n"
                  "Continue with Release build?").format(
                      "\n".join(f"  • {n}" for n in addon_names)),
                _("Yes, Build Release"),
                _("No, Cancel"),
                parent=self.window
            )
            if not question.run():
                return

        self.show_combined_results("Pack and Ship", selected, build_mode)

    def _collect_command_result(self, results, details, addon_name,
                                 version_tag, command, addon_path,
                                 success, stdout, stderr):
        """
        Append one command invocation's outcome to the running results/
        details lists used by show_operation_results() and
        show_combined_results(). Factored out so 'build' and 'listing'
        can each be run once per selected Gramps version without
        duplicating the formatting logic.
        """
        status = "✓" if success else "✗"

        has_manifest = False
        if command == 'build':
            manifest_file = os.path.join(addon_path, 'MANIFEST')
            has_manifest = os.path.exists(manifest_file)

        if has_manifest:
            results.append(f"{status} {addon_name}{version_tag} 🔴 (MANIFEST)")
        else:
            results.append(f"{status} {addon_name}{version_tag}")

        if success and stdout:
            if 'MANIFEST' in stdout or 'manifest' in stdout:
                details.append("    🔴 Used MANIFEST file for packaging")
            for line in stdout.split('\n'):
                if line.strip():
                    details.append(f"    {line}")
        elif not success and stderr:
            details.append(f"    Error: {stderr[:200]}")

    def show_operation_results(self, operation, addons, command):
        """
        Show results for a single operation with detailed feedback in
        scrollable dialog.

        'build' is run once per addon and duplicated across every
        selected Gramps version (see build_for_versions()). 'listing'
        is run once per addon per selected version; each run delegates
        to the matching bundled make<NN>.py (when present) which
        generates every language the addon has translations for.
        """
        build_mode = self.get_build_mode()

        if command in ('build', 'listing'):
            versions = self.get_selected_versions()
        else:
            versions = [GRAMPS_VERSION]
        multi_version = len(versions) > 1

        results = []
        details = []

        for addon_name, addon_path in addons:
            if command == 'build':
                success, stdout, stderr = self.build_for_versions(
                    addon_path, build_mode, versions)
                version_tag = f" [{', '.join(versions)}]" if multi_version else ""
                self._collect_command_result(
                    results, details, addon_name, version_tag, command,
                    addon_path, success, stdout, stderr)
            elif command == 'listing':
                for version in versions:
                    success, stdout, stderr = self.run_make_command(
                        addon_path, command, version=version)
                    version_tag = f" [{version}]" if multi_version else ""
                    self._collect_command_result(
                        results, details, addon_name, version_tag, command,
                        addon_path, success, stdout, stderr)
            else:
                success, stdout, stderr = self.run_make_command(
                    addon_path, command, build_mode=build_mode)
                self._collect_command_result(
                    results, details, addon_name, "", command, addon_path,
                    success, stdout, stderr)

        # Combine results and details
        message_lines = [_("{} completed:").format(operation), ""]
        message_lines.extend(results)

        if details:
            message_lines.append("")
            message_lines.extend(details)

        message = "\n".join(message_lines)

        # Create custom scrollable dialog
        self.show_scrollable_dialog(_("{} Complete").format(operation), message)

    def show_scrollable_dialog(self, title, message):
        """
        Show a scrollable dialog that fits on screen.
        Uses Gtk.Dialog() without the deprecated flags constructor to avoid
        the GTK-CRITICAL 'gtk_notebook_get_tab_label: assertion list != NULL'
        error that fires when get_content_area() is called on a dialog
        constructed with the old flags-based API.
        """
        dialog = Gtk.Dialog()
        dialog.set_title(title)
        dialog.set_transient_for(self.window)
        dialog.set_modal(True)
        dialog.set_destroy_with_parent(True)
        dialog.add_button(_("OK"), Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        # Set reasonable size - max 80% of screen height
        screen = dialog.get_screen()
        screen_height = screen.get_height()
        max_height = int(screen_height * 0.8)
        dialog.set_default_size(600, min(400, max_height))

        # Create scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_size_request(580, min(350, max_height - 100))

        # Create text view
        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_wrap_mode(Gtk.WrapMode.WORD)
        textview.set_left_margin(10)
        textview.set_right_margin(10)
        textview.set_top_margin(10)
        textview.set_bottom_margin(10)

        # Set monospace font for better alignment
        from gi.repository import Pango
        font_desc = Pango.FontDescription("Monospace 10")
        textview.override_font(font_desc)

        buffer = textview.get_buffer()
        buffer.set_text(message)

        scrolled.add(textview)

        content_area = dialog.get_content_area()
        content_area.set_border_width(10)
        content_area.pack_start(scrolled, True, True, 0)

        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def show_combined_results(self, operation, addons, build_mode='beta'):
        """
        Show results for combined operations (build + listing), across
        every selected Gramps version.
        build_mode: 'beta' or 'release'
        """
        versions = self.get_selected_versions()
        multi_version = len(versions) > 1

        all_results = []
        mode_label = "β Beta" if build_mode == 'beta' else "Δ Release"

        # Build once per addon; the resulting .tgz is duplicated across
        # every other selected version (see build_for_versions()).
        for addon_name, addon_path in addons:
            success, stdout, stderr = self.build_for_versions(
                addon_path, build_mode, versions)
            status = "✓" if success else "✗"
            version_tag = f" [{', '.join(versions)}]" if multi_version else ""

            # Show which MANIFEST file was used
            manifest_beta = os.path.exists(os.path.join(addon_path, 'MANIFEST.beta'))
            manifest_rel  = os.path.exists(os.path.join(addon_path, 'MANIFEST'))

            if build_mode == 'beta' and manifest_beta:
                all_results.append(f"{status} Build: {addon_name}{version_tag} 🔴 (MANIFEST.beta)")
            elif build_mode == 'beta':
                all_results.append(f"{status} Build: {addon_name}{version_tag} [β auto-includes extras]")
            elif build_mode == 'release' and manifest_rel:
                all_results.append(f"{status} Build: {addon_name}{version_tag} 🔴 (MANIFEST)")
            else:
                all_results.append(f"{status} Build: {addon_name}{version_tag} [Δ release defaults]")

        # Listing — once per addon per selected version; each run
        # delegates to the matching bundled make<NN>.py (when present)
        # which generates every language the addon has translations for.
        for addon_name, addon_path in addons:
            for version in versions:
                success, stdout, stderr = self.run_make_command(
                    addon_path, "listing", version=version)
                status = "✓" if success else "✗"
                version_tag = f" [{version}]" if multi_version else ""
                all_results.append(
                    f"{status} Listing: {addon_name}{version_tag}")

        # Build mode is shown once, at the top of the body -- avoid
        # repeating "Pack and Ship Complete" here since the dialog
        # title (below) already says that.
        message_lines = [_("Build mode: {}").format(mode_label), ""]
        message_lines.extend(all_results)

        # Show location of output files for every selected version
        builder_dir = self.get_output_parent_dir()
        message_lines.append("")
        message_lines.append(_("📁 Output location(s):"))
        for version in versions:
            output_dir = os.path.join(builder_dir, version)
            message_lines.append(f"  {output_dir}/download/")
            message_lines.append(f"  {output_dir}/listings/")

        message_lines.append("")
        message_lines.append(_("Your addons are ready to share!"))

        self.show_scrollable_dialog(
            _("{} Complete").format(operation), "\n".join(message_lines))

    def _get_tool_pdata(self):
        """
        Return this tool's own PluginData (from AddonPackShip.gpr.py),
        looked up live via Gramps' plugin registry rather than cached
        here, so it can never drift out of sync with the .gpr.py file.
        Mirrors the same PluginRegister.get_instance() +
        type_plugins() pattern already used in scan_installed_addons().
        Shared by :meth:`_get_tool_help_url` and
        :meth:`_get_tool_readme_path` so both read from a single
        lookup.

        :returns: this tool's own PluginData, or ``None`` if it can't
                  be found in the registry.
        """
        try:
            pgr = PluginRegister.get_instance()
            for ptype in PTYPE_STR:
                for pdata in pgr.type_plugins(ptype):
                    if getattr(pdata, 'id', None) == 'addonpackship':
                        return pdata
        except Exception:  # pylint: disable=broad-except
            pass
        return None

    def _get_tool_help_url(self):
        """
        Return this tool's own registered help_url (from
        AddonPackShip.gpr.py).

        :returns: the help URL string, or '' if it can't be found.
        """
        pdata = self._get_tool_pdata()
        return getattr(pdata, 'help_url', '') or ''

    def _get_tool_readme_path(self):
        """
        Return the path to this tool's own README.md, if this tool is
        registered, its folder is known, and a README.md exists there.

        :returns: the README.md path, or '' if any of the above don't
                  hold.
        """
        pdata = self._get_tool_pdata()
        if pdata is None or not getattr(pdata, 'fpath', None):
            return ''
        readme_path = os.path.join(pdata.fpath, 'README.md')
        return readme_path if os.path.isfile(readme_path) else ''

    def _open_readme_in_markdown_dash(self, readme_path):
        """
        Try to open ``readme_path`` in the Markdown Dash gramplet's
        standalone viewer.

        Loads Markdown Dash (see ``MarkdownDash.gpr.py``,
        ``id="markdowndash"``) on demand via the Gramps plugin
        registry, then calls its public ``open_markdown_file()`` API
        (see ``MarkdownDash.py``'s module docstring). Any failure --
        Markdown Dash not registered, its module failing to load, or
        an older version lacking ``open_markdown_file()`` -- is
        treated as "can't show it this way" rather than an error, so
        the caller can fall back to opening the help_url in a browser
        instead (see :meth:`on_help_icon_clicked`).

        :param readme_path: path of the README.md to open.
        :returns: ``True`` if Markdown Dash opened the file, ``False``
                  if it could not be shown this way.
        """
        preg = PluginRegister.get_instance()
        pmgr = GuiPluginManager.get_instance()

        pdata = preg.get_plugin('markdowndash')
        if pdata is None or not pdata.fpath:
            return False

        mod = pmgr.load_plugin(pdata)
        if not mod:
            return False

        open_markdown_file = getattr(mod, 'open_markdown_file', None)
        if open_markdown_file is None:
            return False

        open_markdown_file(
            readme_path,
            self.user.uistate,
            parent=self.user.uistate.window,
            addon_name=_("Addon Pack and Ship"),
        )
        return True

    def _open_help_url_in_browser(self):
        """
        Open this tool's registered help_url in the default browser.

        This is the fallback help action, used when this tool's own
        README.md can't be shown directly (see
        :meth:`on_help_icon_clicked`).
        """
        url = self._get_tool_help_url()
        if not url:
            ErrorDialog(
                _("No Help URL"),
                _("This tool has no help_url registered in its"
                  " .gpr.py."),
                parent=self.window)
            return
        try:
            Gtk.show_uri_on_window(self.window, url, Gdk.CURRENT_TIME)
        except Exception:  # pylint: disable=broad-except
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:  # pylint: disable=broad-except
                ErrorDialog(
                    _("Could Not Open Browser"),
                    _("Could not open {}").format(url),
                    parent=self.window)

    def on_help_icon_clicked(self, _button):
        """
        Open this tool's own documentation.

        Prefers opening this tool's own README.md directly, in the
        Markdown Dash gramplet's standalone viewer (see
        :meth:`_open_readme_in_markdown_dash`). Falls back to opening
        this tool's registered help_url in the default browser (see
        :meth:`_open_help_url_in_browser`) when no README.md is found
        alongside this tool, or when it can't be shown via Markdown
        Dash for any reason -- Markdown Dash not being registered, its
        module failing to load, or an older version lacking the
        ``open_markdown_file()`` API it needs.
        """
        readme_path = self._get_tool_readme_path()
        if readme_path and self._open_readme_in_markdown_dash(readme_path):
            return
        self._open_help_url_in_browser()

    def build_menu_names(self, obj):
        """
        Return menu labels
        """
        return (_("Addon Pack and Ship"), _("Addon Pack and Ship"))

    def close(self, *args):
        """
        Close the window. Remembers whichever configuration name is
        currently in the "Configuration" entry (in APS.ini, under a
        reserved [__LastUsed__] section) so it can be restored the
        next time this tool is opened.
        """
        self._save_last_used_config_name()
        ManagedWindow.close(self, *args)

#------------------------------------------------------------------------
#
# AddonPackShipOptions
#
#------------------------------------------------------------------------
class AddonPackShipOptions(tool.ToolOptions):
    """
    Options for Addon Pack and Ship tool
    """
    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
