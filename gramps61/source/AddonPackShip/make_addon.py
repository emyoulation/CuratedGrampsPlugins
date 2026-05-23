#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
Simplified make script bundled with AddonPackShip tool
Handles build, compile, listing, and clean operations for individual addons

Author: Brian McCullough
Development: AI-assisted using Claude (Anthropic)
Created: February 2026
"""

import os
import sys
import glob
import subprocess
import shutil
import tarfile
import json

# ── Bootstrap: inject Gramps into sys.path from parent process ───────────────
# AddonPackShip.py (the parent) passes its live sys.path via GRAMPS_PYTHONPATH
# so that this subprocess can import gramps without needing a separate GRAMPSPATH
# configuration.  This is the same technique make52.py/make60.py use, just
# delivered via env rather than a CLI arg.
_gramps_pythonpath = os.environ.get('GRAMPS_PYTHONPATH', '')
if _gramps_pythonpath:
    for _p in _gramps_pythonpath.split(os.pathsep):
        if _p and _p not in sys.path:
            sys.path.insert(0, _p)

# Plugin type to number mapping (for JSON output)
PTYPE_TO_NUM = {
    'REPORT': 0,
    'QUICKVIEW': 1,
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
    'DATABASE': 12,
    'RULE': 13,
    'THUMBNAILER': 14,
    'CITE': 15,
}

# Status to number mapping
STATUS_TO_NUM = {
    'UNSTABLE': 0,
    'EXPERIMENTAL': 1,
    'BETA': 2,
    'STABLE': 3,
}

# Audience to number mapping  
AUDIENCE_TO_NUM = {
    'EVERYONE': 0,
    'DEVELOPER': 1,
    'EXPERT': 2,
}

def get_version_from_gpr(addon_path):
    """Extract version from .gpr.py file"""
    addon_name = os.path.basename(addon_path)
    gpr_file = os.path.join(addon_path, f"{addon_name}.gpr.py")
    
    if not os.path.exists(gpr_file):
        return "0.0.0"
    
    try:
        with open(gpr_file, 'r') as f:
            for line in f:
                if 'version' in line and '=' in line:
                    # Extract version string
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        version = parts[1].strip().strip(',').strip('"').strip("'")
                        return version
    except:
        pass
    
    return "0.0.0"

def compile_translations(addon_path, output_dir):
    """
    Compile .po files to .mo files.

    If po/ does not exist it is created.
    If template.pot does not exist, xgettext is run first to generate it.
    Both behaviours match what make52.py/make60.py do in their 'init' command.
    """
    addon_name = os.path.basename(addon_path)

    po_dir = os.path.join(addon_path, 'po')

    # ── Create po/ if it doesn't exist (Bug 3 fix) ───────────────────────────
    if not os.path.exists(po_dir):
        print(f"  Creating po/ directory for {addon_name}...")
        os.makedirs(po_dir, exist_ok=True)

    # ── Generate template.pot if missing ─────────────────────────────────────
    template_pot = os.path.join(po_dir, 'template.pot')
    if not os.path.exists(template_pot):
        print(f"  Generating template.pot for {addon_name}...")

        py_files = glob.glob(os.path.join(addon_path, '*.py'))
        glade_files = glob.glob(os.path.join(addon_path, '*.glade'))

        if py_files:
            fnames = ' '.join(f'"{f}"' for f in py_files)
            cmd = (
                f'xgettext --language=Python --keyword=_ --keyword=_:1,2c --keyword=N_'
                f' --from-code=UTF-8 --add-comments=Translators'
                f' -o "{template_pot}" {fnames}'
            )
            ret = os.system(cmd)
            if ret == 0:
                print(f"  ✓ Created template.pot ({len(py_files)} Python file(s))")
            else:
                print(f"  Warning: xgettext failed (return code {ret})")
                print(f"  Install gettext tools: apt install gettext / dnf install gettext / brew install gettext")

            if glade_files:
                fnames_g = ' '.join(f'"{f}"' for f in glade_files)
                os.system(
                    f'xgettext -j --add-comments -L Glade --from-code=UTF-8'
                    f' -o "{template_pot}" {fnames_g}'
                )

            # Fix charset
            if os.path.exists(template_pot):
                with open(template_pot, 'r', encoding='utf-8', newline='\n') as fh:
                    contents = fh.read()
                contents = contents.replace('charset=CHARSET', 'charset=UTF-8')
                with open(template_pot, 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write(contents)
        else:
            print(f"  No .py files found — cannot generate template.pot")

    # ── Compile *-local.po files ──────────────────────────────────────────────
    po_files = [
        os.path.join(po_dir, fn)
        for fn in os.listdir(po_dir)
        if fn.endswith('-local.po')
    ]

    if not po_files:
        print(f"  No *-local.po translation files found in {addon_name}/po/")
        print(f"  Create {addon_name}/po/<lang>-local.po to add translations.")
        return True

    print(f"  Found {len(po_files)} translation file(s)")
    locale_dir = os.path.join(addon_path, 'locale')
    os.makedirs(locale_dir, exist_ok=True)

    compiled_count = 0
    for po_file in po_files:
        basename = os.path.basename(po_file)
        # fr-local.po → fr
        lang = basename[:-len('-local.po')]

        mo_dir = os.path.join(locale_dir, lang, 'LC_MESSAGES')
        os.makedirs(mo_dir, exist_ok=True)
        mo_file = os.path.join(mo_dir, 'addon.mo')

        try:
            result = subprocess.run(
                ['msgfmt', po_file, '-o', mo_file],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  Compiled {lang}: {basename}")
                compiled_count += 1
            else:
                print(f"  Warning: Failed to compile {lang}: {result.stderr}")
        except FileNotFoundError:
            print(f"  Error: msgfmt not found.")
            print(f"    Debian/Ubuntu: sudo apt install gettext")
            print(f"    Fedora: sudo dnf install gettext")
            print(f"    macOS: brew install gettext")
            return False

    if compiled_count > 0:
        print(f"  Successfully compiled {compiled_count} translation(s)")

    return True



def read_manifest(addon_path, filename='MANIFEST'):
    """
    Read a MANIFEST or MANIFEST.beta file and return list of patterns.
    Returns None if the file does not exist.
    """
    manifest_file = os.path.join(addon_path, filename)
    
    if not os.path.exists(manifest_file):
        return None
    
    patterns = []
    try:
        with open(manifest_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                patterns.append(line)
        
        print(f"  Using {filename} with {len(patterns)} pattern(s)")
        return patterns
    except Exception as e:
        print(f"  Warning: Could not read {filename}: {e}")
        return None

def expand_manifest_pattern(pattern, addon_path, addon_name):
    """
    Expand a MANIFEST pattern to actual file paths
    Supports:
    - AddonName/file.py (specific file)
    - AddonName/*.py (wildcard in directory)
    - AddonName/subdir/* (all files in subdirectory)
    - AddonName/subdir/*.csv (specific extension in subdirectory)
    """
    files = []
    
    # Remove addon name prefix if present
    if pattern.startswith(f"{addon_name}/"):
        pattern = pattern[len(addon_name)+1:]
    
    # Handle wildcards
    if '*' in pattern:
        # Glob pattern
        glob_pattern = os.path.join(addon_path, pattern)
        matched_files = glob.glob(glob_pattern, recursive=True)
        
        # Filter out directories
        files.extend([f for f in matched_files if os.path.isfile(f)])
    else:
        # Specific file
        file_path = os.path.join(addon_path, pattern)
        if os.path.isfile(file_path):
            files.append(file_path)
        elif os.path.isdir(file_path):
            # If it's a directory without wildcard, include all files
            for root, dirs, filenames in os.walk(file_path):
                for filename in filenames:
                    files.append(os.path.join(root, filename))
    
    return files

def build_addon(addon_path, output_dir):
    """
    Build .addon.tgz file.

    Build mode is read from the BUILD_MODE environment variable:
        'beta'    (default) – includes everything for testers and translators
        'release'           – clean end-user package, intentionally lossy

    Beta extras auto-included (beyond core .py/.glade/.xml):
        *.md, po/*.po, po/template.pot, MANIFEST, MANIFEST.beta,
        locale/*.mo, all subdirectory contents.
    
    If MANIFEST.beta is present, it is used INSTEAD of the auto-extras
    (still additive on top of core files).

    Release auto-included:
        core files, README.md only, locale/*.mo.
    
    If MANIFEST is present, its patterns are applied additively.
    """
    addon_name = os.path.basename(addon_path)
    build_mode = os.environ.get('BUILD_MODE', 'beta').lower()
    mode_label = "β Beta" if build_mode == 'beta' else "Δ Release"
    
    print(f"Building {addon_name} [{mode_label}]...")
    
    # Compile translations first (both modes)
    compile_translations(addon_path, output_dir)
    
    files_to_include = []

    # ── 1. Core files (always included in both modes) ────────────────────
    core_py = glob.glob(os.path.join(addon_path, '*.py'))
    files_to_include.extend(core_py)
    print(f"  Including {len(core_py)} core Python file(s)")

    glade_files = glob.glob(os.path.join(addon_path, '*.glade'))
    if glade_files:
        files_to_include.extend(glade_files)
        print(f"  Including {len(glade_files)} Glade file(s)")

    xml_files = glob.glob(os.path.join(addon_path, '*.xml'))
    if xml_files:
        files_to_include.extend(xml_files)
        print(f"  Including {len(xml_files)} XML file(s)")

    # ── 2. Compiled translations (always included in both modes) ─────────
    locale_dir = os.path.join(addon_path, 'locale')
    mo_count = 0
    if os.path.exists(locale_dir):
        for root, dirs, filenames in os.walk(locale_dir):
            for fname in filenames:
                if fname.endswith('.mo'):
                    files_to_include.append(os.path.join(root, fname))
                    mo_count += 1
    if mo_count:
        print(f"  Including {mo_count} compiled translation(s)")

    # ── 3. Mode-specific extras ───────────────────────────────────────────
    if build_mode == 'beta':
        manifest_beta_path = os.path.join(addon_path, 'MANIFEST.beta')
        manifest_rel_path  = os.path.join(addon_path, 'MANIFEST')

        if os.path.exists(manifest_beta_path):
            # Use MANIFEST.beta patterns (additive on top of core)
            patterns = read_manifest(addon_path, filename='MANIFEST.beta')
            if patterns:
                print(f"  β Beta: using MANIFEST.beta ({len(patterns)} pattern(s)):")
                for pattern in patterns:
                    matched = expand_manifest_pattern(pattern, addon_path, addon_name)
                    files_to_include.extend(matched)
                    if matched:
                        print(f"     '{pattern}' → {len(matched)} file(s)")
        else:
            # Auto-include all beta extras
            print(f"  β Beta: auto-including development extras")

            # All *.md files
            md_files = glob.glob(os.path.join(addon_path, '*.md'))
            if md_files:
                files_to_include.extend(md_files)
                print(f"    *.md: {len(md_files)} file(s)")

            # MANIFEST and MANIFEST.beta themselves
            for mf in ['MANIFEST', 'MANIFEST.beta']:
                mf_path = os.path.join(addon_path, mf)
                if os.path.exists(mf_path):
                    files_to_include.append(mf_path)
                    print(f"    {mf}: included")

            # po/*.po and po/template.pot
            po_dir = os.path.join(addon_path, 'po')
            if os.path.exists(po_dir):
                po_files = (
                    glob.glob(os.path.join(po_dir, '*.po')) +
                    glob.glob(os.path.join(po_dir, '*.pot'))
                )
                if po_files:
                    files_to_include.extend(po_files)
                    print(f"    po/: {len(po_files)} translation file(s)")

            # All subdirectories (excluding locale, __pycache__, po already handled)
            skip_dirs = {'locale', '__pycache__', 'po', '.git'}
            for entry in os.scandir(addon_path):
                if entry.is_dir() and entry.name not in skip_dirs:
                    for root, dirs, filenames in os.walk(entry.path):
                        dirs[:] = [d for d in dirs if d != '__pycache__']
                        for fname in filenames:
                            if not fname.endswith(('~', '.pyc', '.pyo')):
                                files_to_include.append(
                                    os.path.join(root, fname)
                                )
                    print(f"    {entry.name}/: subdirectory included")

            # Also apply MANIFEST if present (still additive)
            if os.path.exists(manifest_rel_path):
                patterns = read_manifest(addon_path, filename='MANIFEST')
                if patterns:
                    print(f"  Also applying MANIFEST ({len(patterns)} pattern(s)):")
                    for pattern in patterns:
                        matched = expand_manifest_pattern(
                            pattern, addon_path, addon_name
                        )
                        files_to_include.extend(matched)
                        if matched:
                            print(f"     '{pattern}' → {len(matched)} file(s)")

    else:  # release mode
        manifest_path = os.path.join(addon_path, 'MANIFEST')

        # README.md always included in release
        readme = os.path.join(addon_path, 'README.md')
        if os.path.exists(readme):
            files_to_include.append(readme)
            print(f"  Δ Release: README.md included")

        # MANIFEST extras (additive)
        if os.path.exists(manifest_path):
            patterns = read_manifest(addon_path, filename='MANIFEST')
            if patterns:
                print(f"  Δ Release: applying MANIFEST ({len(patterns)} pattern(s)):")
                for pattern in patterns:
                    matched = expand_manifest_pattern(
                        pattern, addon_path, addon_name
                    )
                    files_to_include.extend(matched)
                    if matched:
                        print(f"     '{pattern}' → {len(matched)} file(s)")
        else:
            print(f"  Δ Release: no MANIFEST (core + README.md + translations only)")

    # ── 4. De-duplicate, preserving order ────────────────────────────────
    seen = set()
    unique_files = []
    for fp in files_to_include:
        if fp not in seen:
            seen.add(fp)
            unique_files.append(fp)
    files_to_include = unique_files
    
    if not files_to_include:
        print(f"  Error: No files found to include in {addon_name}")
        if manifest_patterns:
            print(f"  Checked patterns: {manifest_patterns}")
        return False
    
    print(f"  Including {len(files_to_include)} file(s) in archive")
    
    # Create output directory
    download_dir = os.path.join(output_dir, 'download')
    os.makedirs(download_dir, exist_ok=True)
    
    # Create tarball
    tgz_file = os.path.join(download_dir, f"{addon_name}.addon.tgz")
    
    try:
        with tarfile.open(tgz_file, 'w:gz') as tar:
            for file_path in files_to_include:
                # Get relative path from addon parent directory
                arcname = os.path.relpath(file_path, os.path.dirname(addon_path))
                tar.add(file_path, arcname=arcname)
        
        print(f"  Created: {tgz_file}")
        return True
    except Exception as e:
        print(f"  Error creating tarball: {e}")
        return False

def create_listing(addon_path, output_dir):
    """
    Create / update the addons-en.json listing entry for this addon.

    Uses exec() + gramps.gen.plug.make_environment() to parse the .gpr.py
    file — the same approach as make52.py and make60.py.  This is reliable
    because Gramps is already importable in this subprocess (sys.path was
    bootstrapped from GRAMPS_PYTHONPATH passed by AddonPackShip.py).

    Falls back to the legacy custom parser only when Gramps cannot be
    imported, with a clear warning.
    """
    addon_name = os.path.basename(addon_path)

    # ── Find .gpr.py ─────────────────────────────────────────────────────────
    gpr_file = None
    for candidate in [
        os.path.join(addon_path, f"{addon_name}.gpr.py"),
        os.path.join(addon_path, f"{addon_name.lower()}.gpr.py"),
    ]:
        if os.path.exists(candidate):
            gpr_file = candidate
            break
    if gpr_file is None:
        for fn in os.listdir(addon_path):
            if fn.endswith('.gpr.py'):
                gpr_file = os.path.join(addon_path, fn)
                break

    if not gpr_file:
        print(f"  Error: No .gpr.py file found for {addon_name}")
        return False

    # ── Check .tgz exists ────────────────────────────────────────────────────
    tgz_file = os.path.join(output_dir, 'download', f"{addon_name}.addon.tgz")
    if not os.path.exists(tgz_file):
        # Exit 0 so the UI shows ✓ with a warning rather than ✗ with "Error:".
        # A missing .tgz is a workflow reminder ("Build first"), not a fault.
        print(f"  ⚠  {addon_name}.addon.tgz not found — run Build first.")
        print(f"  Skipping listing for {addon_name}.")
        sys.exit(0)

    # ── Parse .gpr.py with exec()+make_environment() ─────────────────────────
    plugins = []

    def register(ptype, **kwargs):
        kwargs['ptype'] = ptype
        plugins.append(kwargs)

    try:
        # Silence the PyGIWarning "Gtk was imported without specifying a
        # version first" that comes from gramps.gui transitively importing Gtk.
        # We target Gtk 3.0 because Gramps 5.2 uses Gtk 3.
        try:
            import gi
            gi.require_version('Gtk', '3.0')
        except (ImportError, ValueError):
            pass  # gi not available or version already set — harmless

        from gramps.gen.plug import make_environment
        from gramps.gen.const import GRAMPS_LOCALE as glocale

        glocale.language = ['en']
        local_gettext = glocale.get_addon_translator(
            gpr_file, languages=['en', 'en.UTF-8']
        ).gettext

        with open(gpr_file, encoding='utf-8', errors='backslashreplace') as fh:
            code = compile(fh.read(), gpr_file, 'exec')
        exec(code,
             make_environment(_=local_gettext),
             {'register': register, 'build_script': True})

        if not plugins:
            print(f"  Error: register() was never called in {os.path.basename(gpr_file)}")
            return False

    except ImportError as exc:
        print(f"  Warning: Could not import Gramps ({exc})")
        print(f"  Falling back to legacy gpr parser — help_url and some fields may be unreliable.")
        plugins = _parse_gpr_legacy(gpr_file, addon_name)
        if not plugins:
            return False

    # ── Build JSON entries ────────────────────────────────────────────────────
    listings_dir = os.path.join(output_dir, 'listings')
    os.makedirs(listings_dir, exist_ok=True)
    listing_file = os.path.join(listings_dir, 'addons-en.json')

    # Read existing entries
    existing_entries = []
    if os.path.exists(listing_file):
        try:
            with open(listing_file, 'r', encoding='utf-8') as fh:
                content = fh.read().strip()
                if content:
                    existing_entries = json.loads(content)
        except Exception:
            pass

    updated = False
    for p in plugins:
        if not p.get('include_in_listing', True):
            print(f"  Skipping (include_in_listing=False): {p.get('name', '?')}")
            continue

        # Convert symbolic constants to integers exactly as make52.py does:
        # make_environment() puts the integer values in the exec namespace, so
        # p['ptype'] and p['status'] are already integers when Gramps is available.
        ptype_val = p.get('ptype', 2)   # 2 = TOOL fallback
        status_val = p.get('status', 3) # 3 = STABLE fallback
        # When falling back to legacy parser they may still be strings
        if isinstance(ptype_val, str):
            ptype_val = PTYPE_TO_NUM.get(ptype_val.strip().upper(), 2)
        if isinstance(status_val, str):
            status_val = STATUS_TO_NUM.get(status_val.strip().upper(), 3)

        audience_val = p.get('audience', 0)
        if isinstance(audience_val, str):
            audience_val = AUDIENCE_TO_NUM.get(audience_val.strip().upper(), 0)

        json_entry = {
            "n": p.get('name', addon_name),
            "i": p.get('id', addon_name.lower()),
            "t": ptype_val,
            "d": p.get('description', ''),
            "v": p.get('version', '0.0.0'),
            "g": p.get('gramps_target_version', '5.2'),
            "s": status_val,
            "z": f"{addon_name}.addon.tgz",
        }

        # Optional fields — only add when present (same logic as make52/make60)
        if p.get('requires_mod'):
            json_entry['rm'] = p['requires_mod']
        if p.get('requires_gi'):
            json_entry['rg'] = p['requires_gi']
        if p.get('requires_exe'):
            json_entry['re'] = p['requires_exe']
        if p.get('help_url'):
            json_entry['h'] = p['help_url']
        if 'audience' in p:
            json_entry['a'] = audience_val

        # Debug output
        print(f"  Metadata from .gpr.py:")
        print(f"    name:  {json_entry['n']}")
        print(f"    id:    {json_entry['i']}")
        print(f"    type:  {ptype_val}")
        print(f"    v:     {json_entry['v']}")
        print(f"    g:     {json_entry['g']}")
        if 'h' in json_entry:
            print(f"    h:     {json_entry['h']}")

        # Upsert
        entry_found = False
        for idx, existing in enumerate(existing_entries):
            if existing.get('i') == json_entry['i']:
                existing_entries[idx] = json_entry
                entry_found = True
                break
        if not entry_found:
            existing_entries.append(json_entry)
        updated = True
        print(f"  ✓ Listed: {json_entry['n']}")

    if not updated:
        print(f"  Nothing listed for {addon_name}")
        return False

    try:
        with open(listing_file, 'w', encoding='utf-8') as fh:
            json.dump(existing_entries, fh, indent=2, ensure_ascii=False)
        print(f"  Updated: {listing_file}")
        return True
    except Exception as exc:
        print(f"  Error writing listing: {exc}")
        return False


def _parse_gpr_legacy(gpr_file, addon_name):
    """
    Fallback .gpr.py parser used only when Gramps cannot be imported.

    Limitations vs exec()+make_environment():
    - Cannot evaluate bare symbolic constants (STABLE, EXPERT, GRAMPLET …)
    - Multi-line values with bare constants may parse incorrectly

    Returns a list with one plugin dict (like register() would produce),
    or an empty list on failure.
    """
    metadata = {
        'id': addon_name.lower(),
        'name': addon_name,
        'description': '',
        'version': '0.0.0',
        'gramps_target_version': '5.2',
        'ptype': 'TOOL',
        'help_url': '',
        'status': 'STABLE',
        'audience': 'EVERYONE',
        'include_in_listing': True,
    }

    try:
        with open(gpr_file, 'r', encoding='utf-8') as fh:
            content = fh.read()

        # Extract ptype from register(PTYPE, …)
        import re
        m = re.search(r'register\s*\(\s*(\w+)', content)
        if m:
            metadata['ptype'] = m.group(1)

        # Extract simple quoted fields: field = "value" or field = 'value'
        # Handles _("..."), ("..." "..."), and single-quoted variants.
        for field in ['id', 'name', 'version', 'gramps_target_version',
                      'help_url', 'description']:
            # Two-pass: find the field assignment, then extract all quoted parts
            m = re.search(
                r'\b' + re.escape(field) + r'\s*=\s*(.+?)(?:,$|\),$)',
                content, re.DOTALL | re.MULTILINE
            )
            if m:
                raw = m.group(1)
                # Extract all quoted substrings (double or single) and join
                dq = re.findall(r'"([^"]*)"', raw)
                sq = re.findall(r"'([^']*)'" , raw)
                parts = dq if dq else sq
                if parts:
                    metadata[field] = ''.join(parts).strip()
                    metadata[field] = ''.join(parts).strip()

    except Exception as exc:
        print(f"  Legacy parser error: {exc}")
        return []

    return [metadata]



def extract_value(line):
    """
    Extract value from a line like: name = _("Something") 
    or multi-line: description = _("Line one " "Line two")
    Handles implicit string concatenation from Black formatting.
    """
    try:
        # Find = sign
        if '=' not in line:
            return ""
        
        value = line.split('=', 1)[1].strip()
        value = value.rstrip(',').strip()
        
        # Check if it's a variable reference (like major_version or MODULE_VERSION)
        if value in ['major_version', 'MODULE_VERSION']:
            # Try to resolve it by importing
            try:
                if value == 'major_version':
                    from gramps.version import major_version
                    return major_version
                elif value == 'MODULE_VERSION':
                    from gramps.version import MODULE_VERSION
                    return MODULE_VERSION
            except:
                return "5.2"  # fallback
        
        # Remove translation wrapper _( ) if present
        # Handle both _("...") and _('...')
        while value.startswith('_(') or value.startswith('glocale.translation.gettext('):
            if value.startswith('_('):
                value = value[2:].strip()
            elif value.startswith('glocale.translation.gettext('):
                value = value[28:].strip()
            
            # Remove trailing )
            if value.endswith(')'):
                value = value[:-1].strip()
        
        # Handle implicit string concatenation from multi-line Black formatting
        # e.g., "Packaging and distribution tool - create release-ready " 
        #       "Gramps addon plugin packages..."
        # Python concatenates adjacent string literals automatically
        parts = []
        current_part = ""
        in_quote = False
        quote_char = None
        
        i = 0
        while i < len(value):
            ch = value[i]
            
            if not in_quote:
                if ch in ('"', "'"):
                    in_quote = True
                    quote_char = ch
                    i += 1
                    continue
                elif ch.isspace():
                    i += 1
                    continue
            else:
                if ch == quote_char:
                    # Check if it's escaped
                    if i > 0 and value[i-1] == '\\':
                        current_part += ch
                    else:
                        # End of this string literal
                        parts.append(current_part)
                        current_part = ""
                        in_quote = False
                        quote_char = None
                    i += 1
                    continue
                else:
                    current_part += ch
            
            i += 1
        
        # If we exited while still in a quote, add what we have
        if current_part:
            parts.append(current_part)
        
        # Join all parts (Python's implicit concatenation)
        result = ''.join(parts)
        
        return result.strip()
    except Exception as e:
        print(f"  Warning: Could not extract value from '{line[:80]}...': {e}")
        return ""

def clean_addon(addon_path, output_dir):
    """Clean temporary Python cache files (safe for translation workflow)"""
    addon_name = os.path.basename(addon_path)
    print(f"Cleaning {addon_name}...")
    
    files_removed = 0
    
    # Remove __pycache__ directories
    pycache_dir = os.path.join(addon_path, '__pycache__')
    if os.path.exists(pycache_dir):
        shutil.rmtree(pycache_dir)
        print(f"  Removed: __pycache__/")
        files_removed += 1
    
    # Remove .pyc and .pyo files in root directory
    for pattern in ['*.pyc', '*.pyo']:
        for file in glob.glob(os.path.join(addon_path, pattern)):
            os.remove(file)
            print(f"  Removed: {os.path.basename(file)}")
            files_removed += 1
    
    # Remove backup files
    for file in glob.glob(os.path.join(addon_path, '*~')):
        os.remove(file)
        print(f"  Removed: {os.path.basename(file)}")
        files_removed += 1
    
    # Also check po directory for backup files
    po_dir = os.path.join(addon_path, 'po')
    if os.path.exists(po_dir):
        for file in glob.glob(os.path.join(po_dir, '*~')):
            os.remove(file)
            print(f"  Removed: po/{os.path.basename(file)}")
            files_removed += 1
    
    if files_removed == 0:
        print(f"  No temporary files found (already clean)")
    else:
        print(f"  Removed {files_removed} temporary file(s)")
    
    return True

def main():
    if len(sys.argv) < 4:
        print("Usage: make_addon.py <command> <addon_path> <output_dir>")
        print("Commands: build, compile, listing, clean")
        sys.exit(1)
    
    command = sys.argv[1]
    addon_path = sys.argv[2]
    output_dir = sys.argv[3]
    
    if not os.path.isdir(addon_path):
        print(f"Error: Addon path does not exist: {addon_path}")
        sys.exit(1)
    
    if command == 'build':
        success = build_addon(addon_path, output_dir)
    elif command == 'compile':
        success = compile_translations(addon_path, output_dir)
    elif command == 'listing':
        success = create_listing(addon_path, output_dir)
    elif command == 'clean':
        success = clean_addon(addon_path, output_dir)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
