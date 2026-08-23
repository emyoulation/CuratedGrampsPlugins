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
Handles build, compile, listing, and clean operations for individual addons.

'listing' is delegated to the real gramps-project/addons-source make.py
(bundled alongside this file as make<NN>.py, e.g. make52.py for Gramps
5.2) whenever one is present for the target version, via
run_upstream_command() -- so listing entries always follow the current
upstream rules instead of a separate reimplementation that could drift
out of sync. If no matching make<NN>.py is present, create_listing()
below is used as an English-only fallback.

'build', 'compile' and 'clean' are intentionally NOT delegated:
  - build: the upstream 'build' command auto-increments the addon's
    .gpr.py patch version on every run. This tool keeps version bumps
    under the developer's manual control, so build_addon() below never
    touches version numbers.
  - clean: the upstream 'clean' command deletes locale/ entirely.
    clean_addon() below preserves compiled translations so local
    testing isn't disrupted.
  - compile: simple msgfmt wrapping with negligible drift risk; kept
    bundled to avoid subprocess-staging overhead for no real benefit.

Author: Brian McCullough
Development: AI-assisted using Claude (Anthropic)
Created: February 2026
"""

import os
import sys
import ast
import glob
import subprocess
import shutil
import tarfile
import tempfile
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

def _build_listing_entry(plugin_data, addon_name):
    """
    Convert one parsed .gpr.py register() call into the compact JSON
    dict used by the Gramps addon listing format (same field layout as
    make52.py/make60.py).
    """
    # Convert symbolic constants to integers exactly as make52.py does:
    # make_environment() puts the integer values in the exec namespace, so
    # these are already integers when Gramps is available; the legacy
    # fallback parser may still supply strings.
    ptype_val = plugin_data.get('ptype', 2)     # 2 = TOOL fallback
    status_val = plugin_data.get('status', 3)   # 3 = STABLE fallback
    if isinstance(ptype_val, str):
        ptype_val = PTYPE_TO_NUM.get(ptype_val.strip().upper(), 2)
    if isinstance(status_val, str):
        status_val = STATUS_TO_NUM.get(status_val.strip().upper(), 3)

    audience_val = plugin_data.get('audience', 0)
    if isinstance(audience_val, str):
        audience_val = AUDIENCE_TO_NUM.get(audience_val.strip().upper(), 0)

    entry = {
        "n": plugin_data.get('name', addon_name),
        "i": plugin_data.get('id', addon_name.lower()),
        "t": ptype_val,
        "d": plugin_data.get('description', ''),
        "v": plugin_data.get('version', '0.0.0'),
        "g": plugin_data.get('gramps_target_version', '5.2'),
        "s": status_val,
        "z": f"{addon_name}.addon.tgz",
    }

    # Optional fields — only add when present (same logic as make52/make60)
    if plugin_data.get('requires_mod'):
        entry['rm'] = plugin_data['requires_mod']
    if plugin_data.get('requires_gi'):
        entry['rg'] = plugin_data['requires_gi']
    if plugin_data.get('requires_exe'):
        entry['re'] = plugin_data['requires_exe']
    if plugin_data.get('help_url'):
        entry['h'] = plugin_data['help_url']
    if 'audience' in plugin_data:
        entry['a'] = audience_val

    return entry


def _write_listing_file(listings_dir, lang, addon_entries):
    """
    Upsert this addon's entries into listings_dir/addons-<lang>.json,
    preserving entries already listed for every other addon.
    """
    listing_file = os.path.join(listings_dir, f"addons-{lang}.json")

    existing_entries = []
    if os.path.exists(listing_file):
        try:
            with open(listing_file, 'r', encoding='utf-8') as fh:
                content = fh.read().strip()
                if content:
                    existing_entries = json.loads(content)
        except (OSError, ValueError):
            pass

    for entry in addon_entries:
        entry_found = False
        for idx, existing in enumerate(existing_entries):
            if existing.get('i') == entry['i']:
                existing_entries[idx] = entry
                entry_found = True
                break
        if not entry_found:
            existing_entries.append(entry)

    try:
        with open(listing_file, 'w', encoding='utf-8') as fh:
            json.dump(existing_entries, fh, indent=2, ensure_ascii=False)
        print(f"  Updated: {listing_file}")
        return True
    except OSError as exc:
        print(f"  Error writing listing: {exc}")
        return False


def find_upstream_script(builder_dir, version_code):
    """
    Return the path to the bundled make<NN>.py for this Gramps version
    (version_code like 'gramps52' -> make52.py), or None if it isn't
    present. These files are verbatim mirrors of gramps-project/
    addons-source's own make.py (maintenance/gramps<NN> branch) and
    are never modified by this tool -- see AddonPackShip's "Update
    make.py Scripts" action for keeping them in sync with upstream.

    :param builder_dir: Directory this tool (and make<NN>.py, if
        present) is installed in.
    :param version_code: Version code such as 'gramps52'.
    :returns: absolute path to the script, or None.
    """
    digits = (version_code[len('gramps'):]
              if version_code.startswith('gramps') else version_code)
    candidate = os.path.join(builder_dir, f"make{digits}.py")
    return candidate if os.path.isfile(candidate) else None


def _version_digits(version_code):
    """Strip the 'gramps' prefix from a version code, e.g. 'gramps61' -> '61'."""
    return (version_code[len('gramps'):]
            if version_code.startswith('gramps') else version_code)


def _version_label(digits):
    """Format version digits like '61' as a human label like '6.1'."""
    return f"{digits[0]}.{digits[1:]}" if len(digits) >= 2 else digits


def _patch_listing_target_version(output_dir, addon_name, version_label):
    """
    Force the 'g' (gramps_target_version) field of this addon's own
    entries in every addons-<lang>.json / addons-<lang>.txt listing
    under output_dir/listings/ to `version_label`, overriding whatever
    value the addon's .gpr.py computed when it was exec'd.

    This correction is necessary because a .gpr.py normally sets
    `gramps_target_version = major_version`, which reflects whichever
    single Gramps installation is actually importable in this
    subprocess -- not which <version>/ output folder is currently
    being built for. Since a machine usually only has one Gramps
    installed, every version's listing would otherwise report that
    same single installed version's number in 'g', no matter which
    make<NN>.py / output folder actually produced it.

    Only entries whose 'z' (archive filename) matches this addon are
    touched, so nothing else in a shared listing file is disturbed.

    :param output_dir: <output_parent>/<version_code> for this build.
    :param addon_name: Directory name of the addon just listed.
    :param version_label: The correct target label, e.g. '6.1'.
    """
    listings_dir = os.path.join(output_dir, 'listings')
    if not os.path.isdir(listings_dir):
        return
    tgz_name = f"{addon_name}.addon.tgz"

    # ── JSON listings (Gramps 5.2+) ───────────────────────────────────────────
    for path in glob.glob(os.path.join(listings_dir, 'addons-*.json')):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
        except (OSError, ValueError):
            continue
        changed = False
        for entry in entries:
            if entry.get('z') == tgz_name and entry.get('g') != version_label:
                entry['g'] = version_label
                changed = True
        if changed:
            try:
                with open(path, 'w', encoding='utf-8') as fh:
                    json.dump(entries, fh, indent=2, ensure_ascii=False)
                print(f"  Corrected 'g' (target version) in "
                      f"{os.path.basename(path)} -> {version_label}")
            except OSError as exc:
                print(f"  Warning: could not update {path}: {exc}")

    # ── Legacy .txt listings (Gramps versions before 5.2) ─────────────────────
    # One Python-dict-literal per line, written by make.py itself as:
    #   {"t":'2',"i":'myaddon',"n":'My Addon',"v":'1.0.0',"g":'4.2',
    #    "d":'...',"z":'myaddon.addon.tgz'}
    # ast.literal_eval() reads this safely; the replacement line is
    # rendered with the exact same format make.py uses so older Gramps
    # clients can still parse it.
    for path in glob.glob(os.path.join(listings_dir, 'addons-*.txt')):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        changed = False
        new_lines = []
        for line in lines:
            entry = None
            if line.strip():
                try:
                    entry = ast.literal_eval(line)
                except (ValueError, SyntaxError):
                    entry = None
            if (isinstance(entry, dict) and entry.get('z') == tgz_name
                    and entry.get('g') != version_label):
                entry['g'] = version_label
                new_lines.append(
                    '{"t":\'%(t)s\',"i":\'%(i)s\',"n":\'%(n)s\','
                    '"v":\'%(v)s\',"g":\'%(g)s\',"d":\'%(d)s\','
                    '"z":\'%(z)s\'}' % entry
                )
                changed = True
            else:
                new_lines.append(line)
        if changed:
            try:
                with open(path, 'w', encoding='utf-8', newline='') as fh:
                    fh.write('\n'.join(new_lines) +
                             ('\n' if new_lines else ''))
                print(f"  Corrected 'g' (target version) in "
                      f"{os.path.basename(path)} -> {version_label}")
            except OSError as exc:
                print(f"  Warning: could not update {path}: {exc}")


def resolve_gramps_path():
    """
    Return the directory that should be passed as GRAMPSPATH to an
    upstream make.py subprocess: the directory containing the
    importable 'gramps' package. sys.path has already been bootstrapped
    from GRAMPS_PYTHONPATH near the top of this module, so a plain
    import is enough to locate it.

    :returns: absolute path, or None if Gramps could not be imported.
    """
    try:
        import gramps
    except ImportError:
        return None
    return os.path.dirname(os.path.dirname(os.path.abspath(gramps.__file__)))


def _copy_tree_contents(src_dir, dst_dir):
    """
    Copy every file under src_dir into the matching relative location
    under dst_dir, creating directories as needed. Used only by the
    copy-based staging fallback (real directory symlinks unavailable).
    """
    for root, _dirs, filenames in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dest_root = dst_dir if rel == '.' else os.path.join(dst_dir, rel)
        os.makedirs(dest_root, exist_ok=True)
        for fname in filenames:
            shutil.copy2(os.path.join(root, fname),
                          os.path.join(dest_root, fname))


def _locale_languages(addon_path):
    """
    Return language codes with a compiled locale/<lang>/LC_MESSAGES/
    addon.mo under this addon, regardless of whether a matching
    po/<lang>-local.po source file exists.

    :param addon_path: Real path to the addon's source directory.
    :returns: set of language codes.
    """
    locale_dir = os.path.join(addon_path, 'locale')
    languages = set()
    if os.path.isdir(locale_dir):
        for entry in os.listdir(locale_dir):
            mo_path = os.path.join(locale_dir, entry, 'LC_MESSAGES',
                                    'addon.mo')
            if os.path.isfile(mo_path):
                languages.add(entry)
    return languages


def _stage_addon(source_dir, addon_path, extra_po_langs):
    """
    Populate source_dir/<addon_name> as a staging copy of addon_path
    for delegating to an upstream make.py.

    Every top-level entry is symlinked directly to the real addon
    except po/, which is rebuilt as a real directory containing
    symlinks to the addon's actual po files, plus an empty stub
    <lang>-local.po for every language in extra_po_langs that doesn't
    already have a real one.

    The stub files exist only inside this ephemeral staging directory
    -- they are never written into the real addon's po/ folder. They
    exist purely so make.py's own get_all_languages() (which only
    checks for the presence of po/<lang>-local.po, never its contents)
    also includes languages that only have a compiled
    locale/<lang>/LC_MESSAGES/addon.mo and no matching po source. The
    actual translated text in the listing still comes from that real
    .mo file via glocale.get_addon_translator(), never from the stub.

    :param source_dir: The staging cwd make.py will be run from.
    :param addon_path: Real path to the addon's source directory.
    :param extra_po_langs: Language codes to guarantee a
        <lang>-local.po stub for (typically from _locale_languages()).
    :returns: (symlinked, stub_relpaths) -- symlinked is True if
        staging used symlinks (writes land directly on the real addon;
        nothing needs copying back), False if a full copy was used as
        a fallback (caller must copy generated files back afterward,
        e.g. compiled .mo files from a 'compile' run, but must skip
        stub_relpaths -- paths relative to the staged addon directory
        -- so the synthetic po stubs never reach the real addon).
    """
    addon_name = os.path.basename(addon_path)
    staged_addon = os.path.join(source_dir, addon_name)
    real_po_dir = os.path.join(addon_path, 'po')

    def _add_stub_po_files(staged_po_dir, existing_langs):
        os.makedirs(staged_po_dir, exist_ok=True)
        stub_relpaths = []
        for lang in extra_po_langs:
            if lang in existing_langs:
                continue
            fname = f"{lang}-local.po"
            stub_path = os.path.join(staged_po_dir, fname)
            with open(stub_path, 'w', encoding='utf-8') as fh:
                fh.write(
                    "# Placeholder generated by AddonPackShip so"
                    f" '{lang}' (compiled under locale/{lang}/) is"
                    " included in this listing; the actual translated"
                    " text comes from the compiled .mo file, not this"
                    " file.\nmsgid \"\"\nmsgstr \"\"\n"
                )
            stub_relpaths.append(os.path.join('po', fname))
        return stub_relpaths

    try:
        os.makedirs(staged_addon, exist_ok=True)
        for entry in os.listdir(addon_path):
            if entry == 'po':
                continue
            src = os.path.join(addon_path, entry)
            dst = os.path.join(staged_addon, entry)
            os.symlink(os.path.abspath(src), dst,
                       target_is_directory=os.path.isdir(src))

        staged_po_dir = os.path.join(staged_addon, 'po')
        os.makedirs(staged_po_dir, exist_ok=True)
        existing_langs = set()
        if os.path.isdir(real_po_dir):
            for entry in os.listdir(real_po_dir):
                src = os.path.join(real_po_dir, entry)
                dst = os.path.join(staged_po_dir, entry)
                os.symlink(os.path.abspath(src), dst,
                           target_is_directory=os.path.isdir(src))
                if entry.endswith('-local.po'):
                    existing_langs.add(entry[: -len('-local.po')])

        stub_relpaths = _add_stub_po_files(staged_po_dir, existing_langs)
        return True, stub_relpaths
    except OSError:
        shutil.rmtree(staged_addon, ignore_errors=True)
        shutil.copytree(addon_path, staged_addon)
        staged_po_dir = os.path.join(staged_addon, 'po')
        existing_langs = set()
        if os.path.isdir(staged_po_dir):
            existing_langs = {
                fn[: -len('-local.po')]
                for fn in os.listdir(staged_po_dir)
                if fn.endswith('-local.po')
            }
        stub_relpaths = _add_stub_po_files(staged_po_dir, existing_langs)
        return False, stub_relpaths


def run_upstream_command(script_path, version_code, command, addon_path,
                          output_dir):
    """
    Delegate `command` to the real upstream make.py bundled as
    `script_path`, so this tool never has to duplicate -- and
    therefore never has to keep in sync with -- gramps-project/
    addons-source's own packaging/listing rules.

    make.py expects to run with its target addon as a subdirectory of
    the current working directory, writing results to a sibling
    '../addons/<version>/...' tree. The output tree is staged via
    symlink (a real directory + copy-back as fallback where symlinks
    aren't permitted, e.g. unprivileged Windows) so results land
    directly in this tool's existing <version>/download,
    <version>/listings folders. The addon itself is staged via
    _stage_addon(), which also ensures every language with a compiled
    locale/<lang>/LC_MESSAGES/addon.mo is included in the listing (see
    that function's docstring) even when po/*-local.po alone wouldn't
    be enough for make.py to notice it.

    :param script_path: Path to the bundled make<NN>.py.
    :param version_code: Version code such as 'gramps52', passed
        through to make.py as-is (it only uses it to build output
        paths, matching this tool's own <version>/... layout).
    :param command: 'listing' (or any other command make.py supports
        that operates on a single addon by name).
    :param addon_path: Real path to the addon's source directory.
    :param output_dir: This run's <output_parent>/<version_code> output
        directory (the parent of download/ and listings/). Not
        necessarily where this script or its make<NN>.py siblings are
        installed -- AddonPackShip.py may point output_dir at a
        different, user-chosen parent folder.
    :returns: (success, stdout, stderr).
    """
    addon_name = os.path.basename(addon_path)
    output_parent = os.path.dirname(os.path.abspath(output_dir))

    gramps_path = resolve_gramps_path()
    if not gramps_path:
        return False, "", (
            "Could not resolve GRAMPSPATH for the upstream make.py "
            "(Gramps is not importable in this subprocess)."
        )

    with tempfile.TemporaryDirectory(prefix='aps_stage_') as stage_root:
        source_dir = os.path.join(stage_root, 'source')
        os.makedirs(source_dir, exist_ok=True)
        addons_link = os.path.join(stage_root, 'addons')
        staged_addon = os.path.join(source_dir, addon_name)

        extra_po_langs = _locale_languages(addon_path)
        addon_symlinked, stub_relpaths = _stage_addon(
            source_dir, addon_path, extra_po_langs)
        copy_back_addon = not addon_symlinked

        try:
            os.symlink(os.path.abspath(output_parent), addons_link,
                       target_is_directory=True)
            output_symlinked = True
        except OSError:
            output_symlinked = False
            os.makedirs(addons_link, exist_ok=True)

        env = os.environ.copy()
        env['GRAMPSPATH'] = gramps_path

        result = subprocess.run(
            [sys.executable, os.path.abspath(script_path),
             version_code, command, addon_name],
            cwd=source_dir,
            capture_output=True,
            text=True,
            env=env,
        )

        if copy_back_addon:
            # Copy back anything make.py generated/updated inside the
            # staged copy (compiled locale/*.mo, merged po files, etc.)
            # -- but never the synthetic po stubs; those must not reach
            # the real addon directory.
            for rel in stub_relpaths:
                stub_path = os.path.join(staged_addon, rel)
                if os.path.isfile(stub_path):
                    os.remove(stub_path)
            _copy_tree_contents(staged_addon, addon_path)

        if not output_symlinked:
            # A real (empty) 'addons' dir was created instead of a
            # symlink to output_parent -- copy whatever output landed
            # in it into this run's real output tree.
            staged_output = os.path.join(addons_link, version_code)
            if os.path.isdir(staged_output):
                _copy_tree_contents(
                    staged_output,
                    os.path.join(output_parent, version_code))

        return result.returncode == 0, result.stdout, result.stderr


def create_listing(addon_path, output_dir):
    """
    Create / update the addons-<lang>.json listing entries for this
    addon, for every language requested via the ADDON_LANGUAGES
    environment variable (comma-separated, e.g. "en,fr,nl"). 'en' is
    always included as the base/fallback listing language; it is added
    automatically even if not explicitly requested.

    Uses exec() + gramps.gen.plug.make_environment() to parse the
    .gpr.py file once per requested language, with
    glocale.get_addon_translator() supplying the localized name/
    description text (falling back to English for addons that have no
    translation of their own for a given language) — the same approach
    used by make52.py's and make60.py's own "listing" command.

    Falls back to the legacy custom parser only when Gramps cannot be
    imported; in that case only English can be listed, since the
    legacy parser has no access to Gramps' translation machinery.
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

    # ── Resolve which languages to generate ───────────────────────────────────
    # 'en' is always produced; any other requested language still lists
    # every addon (falling back to English text) so the catalog for that
    # language remains a complete, usable addon list on its own.
    requested = os.environ.get('ADDON_LANGUAGES', 'en')
    target_languages = []
    for lang in requested.split(','):
        lang = lang.strip()
        if lang and lang not in target_languages:
            target_languages.append(lang)
    if 'en' not in target_languages:
        target_languages.insert(0, 'en')

    # Compile any *-local.po files to .mo so glocale.get_addon_translator()
    # can find them for the non-English languages requested above.
    compile_translations(addon_path, output_dir)

    use_gramps = True
    try:
        # Silence the PyGIWarning "Gtk was imported without specifying a
        # version first" that comes from gramps.gui transitively importing
        # Gtk. We target Gtk 3.0 because Gramps 5.2/6.0 use Gtk 3.
        try:
            import gi
            gi.require_version('Gtk', '3.0')
        except (ImportError, ValueError):
            pass  # gi not available or version already set — harmless

        from gramps.gen.plug import make_environment
        from gramps.gen.const import GRAMPS_LOCALE as glocale
    except ImportError as exc:
        print(f"  Warning: Could not import Gramps ({exc})")
        print("  Falling back to legacy gpr parser — only 'en' can be"
              " listed and help_url/some fields may be unreliable.")
        use_gramps = False

    listings_dir = os.path.join(output_dir, 'listings')
    os.makedirs(listings_dir, exist_ok=True)

    updated_any = False
    for lang in target_languages:
        if not use_gramps and lang != 'en':
            print(f"  Skipping '{lang}' listing (Gramps not importable)")
            continue

        plugins = []

        def register(ptype, **kwargs):
            kwargs['ptype'] = ptype
            plugins.append(kwargs)

        if use_gramps:
            glocale.language = [lang]
            local_gettext = glocale.get_addon_translator(
                gpr_file, languages=[lang, 'en.UTF-8']
            ).gettext

            with open(gpr_file, encoding='utf-8',
                       errors='backslashreplace') as fh:
                code = compile(fh.read(), gpr_file, 'exec')
            exec(code,
                 make_environment(_=local_gettext),
                 {'register': register, 'build_script': True})
        else:
            plugins = _parse_gpr_legacy(gpr_file, addon_name)

        if not plugins:
            print(f"  Error: register() was never called in "
                  f"{os.path.basename(gpr_file)} ('{lang}')")
            continue

        entries = []
        for p in plugins:
            if not p.get('include_in_listing', True):
                if lang == 'en':
                    print(f"  Skipping (include_in_listing=False): "
                          f"{p.get('name', '?')}")
                continue
            entry = _build_listing_entry(p, addon_name)
            entries.append(entry)
            print(f"  ✓ Listed [{lang}]: {entry['n']}")

        if not entries:
            print(f"  Nothing listed for {addon_name} ('{lang}')")
            continue

        if _write_listing_file(listings_dir, lang, entries):
            updated_any = True

    if not updated_any:
        print(f"  Nothing listed for {addon_name}")
        return False
    return True


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

    # version_code is this tool's own output-directory naming (e.g.
    # 'gramps52'), passed in via output_dir = <output_parent>/<version_code>.
    # output_dir's parent is NOT necessarily where this script (and its
    # sibling make<NN>.py copies) live -- AddonPackShip.py lets the user
    # redirect output to a different parent folder (e.g. a Git repo
    # clone) independently of where the tool itself is installed. Use
    # this script's own location to find make<NN>.py, not output_dir's.
    version_code = os.path.basename(os.path.normpath(output_dir))
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    upstream_script = find_upstream_script(scripts_dir, version_code)

    if command == 'build':
        # See module docstring: intentionally not delegated (no
        # automatic version increments).
        success = build_addon(addon_path, output_dir)
    elif command == 'compile':
        # See module docstring: intentionally not delegated (low
        # drift risk, no staging overhead needed).
        success = compile_translations(addon_path, output_dir)
    elif command == 'listing':
        addon_name = os.path.basename(addon_path)
        target_label = _version_label(_version_digits(version_code))
        if upstream_script:
            success, stdout, stderr = run_upstream_command(
                upstream_script, version_code, 'listing', addon_path,
                output_dir)
            if stdout:
                print(stdout, end='' if stdout.endswith('\n') else '\n')
            if stderr:
                print(stderr, end='' if stderr.endswith('\n') else '\n',
                      file=sys.stderr)
        else:
            print(f"  No make{_version_digits(version_code)}.py found for "
                  f"{version_code} -- using bundled English-only fallback."
                  " Use AddonPackShip's \"Update make.py Scripts\" action"
                  " to fetch it from GitHub.")
            success = create_listing(addon_path, output_dir)
        if success:
            # Correct 'g' (target version) for this addon's own entries:
            # the addon's .gpr.py computed it from whichever single
            # Gramps is actually installed, not from version_code.
            _patch_listing_target_version(output_dir, addon_name,
                                           target_label)
            listings_dir = os.path.join(output_dir, 'listings')
            if os.path.isdir(listings_dir) and any(
                    fn.startswith('addons-') and fn.endswith('.txt')
                    for fn in os.listdir(listings_dir)):
                print(f"  Note: Gramps {target_label} uses the legacy"
                      " addons-<lang>.txt listing format, not JSON --"
                      " expected for Gramps versions before 5.2, not"
                      " an error.")
    elif command == 'clean':
        # See module docstring: intentionally not delegated (preserves
        # compiled translations for local testing).
        success = clean_addon(addon_path, output_dir)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
