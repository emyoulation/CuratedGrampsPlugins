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
import sys
import glob
import subprocess
import shutil

#------------------------------------------------------------------------
#
# GTK modules
#
#------------------------------------------------------------------------
from gi.repository import Gtk, GObject

#------------------------------------------------------------------------
#
# Gramps modules
#
#------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
_ = glocale.translation.gettext
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
GRAMPS_VERSION = "gramps52"  # Can be changed to gramps60, etc.

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
        
        # Scan for installed addons
        self.scan_installed_addons()
        
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
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>" + _("Addon Pack and Ship") + "</b></big>")
        title.set_halign(Gtk.Align.START)
        vbox.pack_start(title, False, False, 0)
        
        # Info label — bundles (directories) and total plugin count
        total_plugins = sum(
            len(info['plugins']) for info in self.addon_info.values())
        self._total_bundles = len(self.addon_info)
        self._total_plugins = total_plugins
        info_text = _(
            "Select installed addons to package and publish.\n"
            "Found {bundle_count} bundles ({plugin_count} registered plugins)"
            " in your Gramps installation."
        ).format(bundle_count=self._total_bundles, plugin_count=self._total_plugins)
        info = Gtk.Label(info_text)
        info.set_halign(Gtk.Align.START)
        info.set_line_wrap(True)
        vbox.pack_start(info, False, False, 0)
        
        # Separator
        vbox.pack_start(Gtk.Separator(), False, False, 0)
        
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
            _("Create or amend the addons-en.json listing for selected addons.\n"
              "Adds/updates entries — other entries are preserved.\n"
              "To shrink the listing, delete the gramps52/listings/ folder first,\n"
              "then rebuild only the addons you want listed.")
        )
        listing_btn.connect("clicked", self.on_listing)
        action_btn_box.pack_start(listing_btn, False, False, 0)

        filter_box.pack_start(action_btn_box, False, False, 0)

        vbox.pack_start(filter_frame, False, False, 0)

        # Separator
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Scrolled window for addon list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        vbox.pack_start(scrolled, True, True, 0)

        # Addon selection area
        self.addon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.addon_box.set_border_width(6)
        scrolled.add(self.addon_box)

        # Build the addon list
        self.rebuild_addon_list()

        # Separator
        vbox.pack_start(Gtk.Separator(), False, False, 0)

        # Bottom row: Pack and Ship (centre) + status (left) + Close (right)
        bottom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

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
            Gtk.Image.new_from_icon_name("document-open", Gtk.IconSize.BUTTON)
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
                        "document-open", Gtk.IconSize.BUTTON))
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
                # Shows the directory name + combined types + MANIFEST button.
                # Not a checkbox; just an informational label.
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

                hdr_hbox.pack_start(hdr_vbox,          True,  True,  0)
                hdr_hbox.pack_start(_make_folder_btn(), False, False, 0)
                self.addon_box.pack_start(hdr_hbox, False, False, 0)

                # ── One checkbox row per matching plugin ───────────────────
                for pdata in matching:
                    pid = getattr(pdata, 'id', None)
                    if not pid:
                        continue
                    self.plugin_to_dir[pid] = addon_name

                    ptype_num  = getattr(pdata, 'ptype', None)
                    type_label = (PTYPE_STR.get(ptype_num, '?')
                                  if ptype_num is not None else '?')
                    cb_label   = '  {} [{}]'.format(
                        getattr(pdata, 'name', pid) or pid, type_label)

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

                ptype_num  = getattr(pdata, 'ptype', None)
                type_label = (PTYPE_STR.get(ptype_num, '?')
                              if ptype_num is not None else '?')
                cb_label   = '{} [{}]'.format(
                    getattr(pdata, 'name', pid) or pid, type_label)

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

                row_hbox.pack_start(cb_vbox,          True,  True,  0)
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
        Always show:  Selected bundles: X/Y  •  Plugins: V/T
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
    
    def run_make_command(self, addon_path, command, build_mode='beta'):
        """
        Run make_addon.py command using the bundled script.
        Pass plugin type number and build mode to the packaging engine.
        build_mode: 'beta' or 'release'
        """
        addon_name = os.path.basename(addon_path)
        
        # Get the directory where AddonPackShip is installed
        builder_dir = os.path.dirname(os.path.abspath(__file__))
        make_script = os.path.join(builder_dir, 'make_addon.py')
        
        # Output directory - create gramps52 subdirectory
        output_dir = os.path.join(builder_dir, GRAMPS_VERSION)
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
            listing_path = os.path.join(output_dir, 'listings', 'addons-en.json')
            if os.path.exists(listing_path):
                info_lines.append(f"📋 Listing updated: {listing_path}")
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
        
        # Get output directory
        builder_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(builder_dir, GRAMPS_VERSION)
        download_dir = os.path.join(output_dir, 'download')
        
        # Check if any .tgz files exist
        missing_tgz = []
        for addon_name, addon_path in selected:
            tgz_file = os.path.join(download_dir, f"{addon_name}.addon.tgz")
            if not os.path.exists(tgz_file):
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
    
    def show_operation_results(self, operation, addons, command):
        """
        Show results for a single operation with detailed feedback in scrollable dialog
        """
        results = []
        details = []
        
        for addon_name, addon_path in addons:
            success, stdout, stderr = self.run_make_command(addon_path, command)
            status = "✓" if success else "✗"
            
            # Check for MANIFEST file if this is a build operation
            has_manifest = False
            if command == 'build':
                manifest_file = os.path.join(addon_path, 'MANIFEST')
                has_manifest = os.path.exists(manifest_file)
            
            # Format result with MANIFEST indicator if applicable
            if has_manifest:
                results.append(f"{status} {addon_name} 🔴 (MANIFEST)")
            else:
                results.append(f"{status} {addon_name}")
            
            if success and stdout:
                # Check if stdout mentions MANIFEST
                if 'MANIFEST' in stdout or 'manifest' in stdout:
                    details.append(f"    🔴 Used MANIFEST file for packaging")
                
                # Include output details
                for line in stdout.split('\n'):
                    if line.strip():
                        details.append(f"    {line}")
            elif not success and stderr:
                details.append(f"    Error: {stderr[:200]}")
        
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
        Show results for combined operations (Translations, build + listing)
        build_mode: 'beta' or 'release'
        """
        all_results = []
        mode_label = "β Beta" if build_mode == 'beta' else "Δ Release"
        
        # Build
        for addon_name, addon_path in addons:
            success, stdout, stderr = self.run_make_command(
                addon_path, "build", build_mode=build_mode
            )
            status = "✓" if success else "✗"
            
            # Show which MANIFEST file was used
            manifest_beta = os.path.exists(os.path.join(addon_path, 'MANIFEST.beta'))
            manifest_rel  = os.path.exists(os.path.join(addon_path, 'MANIFEST'))
            
            if build_mode == 'beta' and manifest_beta:
                all_results.append(f"{status} Build: {addon_name} 🔴 (MANIFEST.beta)")
            elif build_mode == 'beta':
                all_results.append(f"{status} Build: {addon_name} [β auto-includes extras]")
            elif build_mode == 'release' and manifest_rel:
                all_results.append(f"{status} Build: {addon_name} 🔴 (MANIFEST)")
            else:
                all_results.append(f"{status} Build: {addon_name} [Δ release defaults]")
        
        # Listing
        for addon_name, addon_path in addons:
            success, stdout, stderr = self.run_make_command(addon_path, "listing")
            status = "✓" if success else "✗"
            all_results.append(f"{status} Listing: {addon_name}")
        
        message = _("{} completed [{}]:\n\n{}").format(
            operation,
            mode_label,
            "\n".join(all_results)
        )
        
        # Show location of output files
        builder_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(builder_dir, GRAMPS_VERSION)
        
        message += _("\n\n📁 Output location:\n  {}/download/\n  {}/listings/").format(
            output_dir, output_dir
        )
        
        OkDialog(
            _("Pack and Ship Complete"),
            message + _("\n\nYour addons are ready to share!"),
            parent=self.window
        )
    
    def build_menu_names(self, obj):
        """
        Return menu labels
        """
        return (_("Addon Pack and Ship"), _("Addon Pack and Ship"))
    
    def close(self, *args):
        """
        Close the window
        """
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
