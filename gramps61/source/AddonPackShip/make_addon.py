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
import io
import re
import sys
import ast
import glob
import logging
import datetime
import contextlib
import subprocess
import shutil
import tarfile
import tempfile
import time
import json

LOG = logging.getLogger(__name__)

# ── Bootstrap: inject Gramps into sys.path when run standalone ───────────────
# AddonPackShip.py now imports this module directly and calls
# run_command() in-process, so it already shares AddonPackShip's own
# sys.path and this bootstrap is not needed for that path. It remains
# here only for backward compatibility with running this file
# standalone from the command line / CI (main(), below), where
# GRAMPS_PYTHONPATH can still be set manually to make `import gramps`
# work without a separate GRAMPSPATH configuration -- the same
# technique make52.py/make60.py use, just delivered via env rather
# than a CLI arg.
_gramps_pythonpath = os.environ.get('GRAMPS_PYTHONPATH', '')
if _gramps_pythonpath:
    for _p in _gramps_pythonpath.split(os.pathsep):
        if _p and _p not in sys.path:
            sys.path.insert(0, _p)

# ── Default when no explicit choice is given (2026-08) ────────────────────
# Non-English addon listings were disabled by default while a
# Windows-specific 'listing' bug was tracked down. AddonPackShip's GUI
# now overrides this per-run via run_command()'s own `multilingual`
# parameter (see its "Multilingual" checkbox, deselected by default to
# match this same value) -- this constant now only matters for
# standalone CLI use of this module, where nothing else specifies a
# preference. It does NOT remove any of the multi-language machinery
# below (_stage_addon()'s po stub generation, create_listing()'s
# per-language loop, the upstream make<NN>.py delegation's own
# language detection all still run exactly as before) -- it only
# prunes non-English listing files as a final step in run_command()
# when neither the GUI nor a CLI caller has said otherwise.
ENABLE_NON_ENGLISH_LISTINGS = False

# Set by run_command() for the duration of one command, from its
# wait_callback argument: called about ten times a second while
# _run_subprocess() waits on a child process, so a GUI caller
# (AddonPackShip.py) can keep its window responsive and avoid the
# desktop's "not responding" warning during long steps. None for the
# command-line main(), which has no window to keep alive.
_WAIT_CALLBACK = None

# Validated standalone Python interpreter per GRAMPSPATH (see
# _find_real_python_executable()), so the probe -- a separate Python
# importing Gramps, a second or more each time -- runs once per Gramps
# session instead of once per addon per version.
_PYTHON_EXE_CACHE = {}


def _run_subprocess(cmd, timeout=None, **kwargs):
    """
    subprocess.run(cmd, capture_output=True, text=True, ...) that,
    while a _WAIT_CALLBACK is set, waits in short slices and calls it
    between them instead of blocking until the child exits.

    :param cmd: The command list.
    :param timeout: Seconds before the child is killed and
        subprocess.TimeoutExpired raised, or None for no limit.
    :param kwargs: Passed to subprocess.Popen (e.g. cwd, env).
    :returns: A subprocess.CompletedProcess.
    """
    callback = _WAIT_CALLBACK
    if callback is None:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, **kwargs)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, **kwargs)
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=0.1)
            break
        except subprocess.TimeoutExpired:
            if deadline is not None and time.monotonic() > deadline:
                proc.kill()
                proc.communicate()
                raise
            try:
                callback()
            except Exception:  # pylint: disable=broad-except
                LOG.exception("wait callback failed")
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

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
            result = _run_subprocess(['msgfmt', po_file, '-o', mo_file])
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

def build_addon(addon_path: str, output_dir: str,
                 build_mode: str = 'beta') -> bool:
    """
    Build .addon.tgz file.

    :param addon_path: Path to the addon's source directory.
    :param output_dir: This run's ``<output_parent>/<version_code>``
        output directory.
    :param build_mode: 'beta' (default) includes everything for
        testers and translators; 'release' produces a clean end-user
        package, intentionally lossy.
    :returns: ``True`` on success, ``False`` on failure.

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
    build_mode = (build_mode or 'beta').lower()
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


def _prune_non_english_listings(listings_dir):
    """
    Delete every ``addons-<lang>.json``/``.txt`` in ``listings_dir``
    except the English one.

    Callers decide whether English-only is actually wanted for this
    run (see run_command()'s ``multilingual`` parameter and
    ``effective_multilingual``) and only call this when it is -- this
    function itself no longer re-checks the module-level
    ``ENABLE_NON_ENGLISH_LISTINGS`` default, so a caller's explicit
    per-call choice is never silently overridden by it.

    :param listings_dir: The ``listings/`` directory to prune.
    """
    if not os.path.isdir(listings_dir):
        return
    for fname in os.listdir(listings_dir):
        if fname in ('addons-en.json', 'addons-en.txt'):
            continue
        if fname.startswith('addons-') and (
                fname.endswith('.json') or fname.endswith('.txt')):
            try:
                os.remove(os.path.join(listings_dir, fname))
                print(f"  (non-English listings disabled for now -- "
                      f"removed {fname})")
            except OSError as exc:
                print(f"  Warning: could not remove {fname}: {exc}")


def _log_session_command(session_id, command_line, note=None):
    """
    Append one CLI-equivalent command line to this session's teaching
    log at ``<this plugin's own install directory>/logs/<session_id>.log``.

    This exists purely to teach: it lets a developer see, and
    directly reuse, exactly what they could type at a terminal to
    reproduce -- by hand, using the real make.py tools -- each action
    the AddonPackShip GUI just performed for them. It has no effect
    on packaging itself; a failure to write the log is a warning, not
    an error.

    The log lives next to make_addon.py itself (the AddonPackShip
    plugin's own folder) rather than under the (user-redirectable)
    output location, so it sits in one fixed, easy-to-find place
    regardless of where a given run's output was sent -- and so one
    file can span several addons and versions in the same session.

    :param session_id: Identifies one GUI tool session (typically a
        timestamp of when the AddonPackShip window was opened).
        Logging is skipped entirely when this is falsy -- e.g. when
        make_addon.py's own CLI ``main()`` calls run_command()
        directly, there is no GUI session to teach an equivalent for.
    :param command_line: The command a developer could type verbatim.
    :param note: Optional extra context line(s) (e.g. required
        working-directory layout), written immediately above the
        command.
    """
    if not session_id:
        return
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(scripts_dir, 'logs')
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, f"{session_id}.log")
        with open(log_path, 'a', encoding='utf-8') as fh:
            # Blank line before every entry (including the first) so
            # each command stands out as its own block when reading
            # the file back -- readability over a compact log.
            fh.write("\n")
            if note:
                for line in note.splitlines():
                    fh.write(f"# {line}\n")
            fh.write(f"[{timestamp}] {command_line}\n")
    except OSError as exc:
        print(f"  Warning: could not write session log: {exc}")


def _log_build_style_command(command, upstream_script, version_code,
                              addon_name, addon_path, output_dir,
                              build_mode, success, session_id):
    """
    Log the CLI-equivalent for a 'build', 'compile', or 'clean' call.

    make_addon.py is bundled and distributed alongside AddonPackShip
    and is fully supported standalone from the command line (see
    main(), below) -- for at least as long as AddonPackShip continues
    reimplementing 'build'/'compile'/'clean' itself rather than
    delegating them to the upstream make<NN>.py (to avoid its
    automatic version increment on 'build' and its locale/ wipe on
    'clean' -- see this module's docstring). So the logged line is
    always the make_addon.py command that actually ran: accurate,
    and something a developer can copy and reuse with confidence.

    When a make<NN>.py is also bundled for this version, a secondary
    "FYI" note points at the real, standard tool's rough equivalent
    too -- since that is the wider ecosystem's tool and worth knowing
    about -- but is explicit that it is not a drop-in substitute, and
    says exactly how it differs, rather than presenting it as
    interchangeable.

    :param command: 'build', 'compile', or 'clean'.
    :param upstream_script: Path to the bundled make<NN>.py for this
        version, or ``None`` if none is bundled.
    :param version_code: Version code such as 'gramps61'.
    :param addon_name: The addon's directory name.
    :param addon_path: Path to the addon's source directory.
    :param output_dir: This run's ``<output_parent>/<version_code>``
        output directory.
    :param build_mode: 'beta' or 'release' -- only relevant to
        'build'; the upstream tool has no equivalent distinction.
    :param success: Whether this command reported success, recorded
        in the log as a trailing ``# succeeded``/``# failed`` comment.
    :param session_id: Forwarded to _log_session_command(); logging
        is a no-op when this is falsy.
    """
    cli_cmd = (f'python3 make_addon.py {command} "{addon_path}"'
               f' "{output_dir}"')
    note_lines = []
    if command == 'build' and build_mode != 'beta':
        note_lines.append(
            f"set BUILD_MODE={build_mode} in the environment first"
            f" (bash: BUILD_MODE={build_mode} <command>; cmd.exe:"
            f" set BUILD_MODE={build_mode} && <command>)")

    if upstream_script:
        script_name = os.path.basename(upstream_script)
        upstream_cmd = (f'python3 {script_name} {version_code} {command}'
                        f' {addon_name}')
        note_lines.append(
            "FYI: the standard make.py tool's rough equivalent would"
            " be:")
        note_lines.append(f"  {upstream_cmd}")
        note_lines.append("but it is NOT a drop-in substitute:")
        if command == 'build':
            note_lines.append(
                f"  - it also bumps the version in {addon_name}"
                "/*.gpr.py every time it runs")
            note_lines.append(
                "  - it has no beta/release distinction (always"
                " builds the minimal, release-style file set: no"
                " po/*.po, template.pot, or MANIFEST.beta)")
        elif command == 'compile':
            note_lines.append(
                "  - it does not auto-create po/ or generate"
                " template.pot the way this tool's 'compile' does"
                " for convenience -- it only compiles po files that"
                " already exist")
        elif command == 'clean':
            note_lines.append(
                f"  - it also deletes {addon_name}/locale/ entirely"
                " (every compiled translation), which this tool's"
                " own 'clean' preserves for local testing")
        note_lines.append(
            f"  - requires {addon_name}/ as a subdirectory of the"
            f" current directory, with ../addons/{version_code}/ as"
            " the sibling output tree (see make.py's own"
            " conventions)")

    outcome = "succeeded" if success else "failed"
    _log_session_command(session_id, f'{cli_cmd}  # {outcome}',
                         note="\n".join(note_lines) or None)


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


def _copy_tree_contents(src_dir, dst_dir, lenient=False):
    """
    Copy every file under src_dir into the matching relative location
    under dst_dir, creating directories as needed. Used only by the
    copy-based staging fallback (real directory symlinks unavailable,
    e.g. an unprivileged Windows account -- the common case, since
    creating symlinks there requires either admin rights or Developer
    Mode).

    :param src_dir: Directory tree to copy from.
    :param dst_dir: Directory tree to copy into.
    :param lenient: If ``False`` (default), a copy failure (e.g. a
        locked or read-only destination file) raises immediately, as
        before. If ``True``, each file is copied independently and a
        failure on one file is recorded as a warning and skipped
        rather than aborting the rest of the copy -- appropriate when
        the destination tree may contain files this tool does not
        own and should not insist on overwriting (see
        run_upstream_command(), which additionally scopes *which*
        files it ever attempts to copy back for exactly this reason).
    :returns: A list of warning strings, one per file that could not
        be copied. Always empty when ``lenient`` is ``False`` (any
        failure raises instead).
    """
    warnings = []
    for root, _dirs, filenames in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        dest_root = dst_dir if rel == '.' else os.path.join(dst_dir, rel)
        os.makedirs(dest_root, exist_ok=True)
        for fname in filenames:
            src_file = os.path.join(root, fname)
            dst_file = os.path.join(dest_root, fname)
            if lenient:
                try:
                    shutil.copy2(src_file, dst_file)
                except OSError as exc:
                    warnings.append(
                        f"could not update {os.path.relpath(dst_file, dst_dir)}"
                        f" ({exc})")
            else:
                shutil.copy2(src_file, dst_file)
    return warnings


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


def _find_real_python_executable(gramps_path=None):
    """
    Return a *validated* Python interpreter for running make<NN>.py's
    ``listing`` command, or ``None`` if none could be found.

    This script may itself be running inside a frozen copy of Gramps
    -- in which case ``sys.executable`` is the Gramps application
    itself, not a usable interpreter (see the module docstring
    history). ``sys.executable`` is validated the same way as any
    other candidate rather than trusted whenever ``sys.frozen`` is
    unset: that flag reliably marks cx_Freeze builds (e.g. the
    Windows AIO installer) but is not set by every frozen packaging
    -- notably not by the macOS .app bundle, where ``sys.executable``
    can still resolve to the app bundle path itself even though
    ``sys.frozen`` is absent.

    Candidates found via ``shutil.which()`` are not trusted blindly:
    each is actually run with a trivial ``-c`` script and a short
    timeout before being accepted. This matters most on Windows,
    where ``python``/``python3`` on PATH can resolve to the Microsoft
    Store's "App Execution Alias" stub rather than a real interpreter,
    on a machine that only has Gramps installed (e.g. via the AIO
    installer) and no separately-installed system Python. That stub
    typically exits having produced no output at all, which is
    exactly what made an earlier version of this function look like
    it was working (a path was found) while actually running nothing
    -- silently producing no listing output with no error at all.

    :param gramps_path: If given, forwarded to
        _validate_python_executable() so a candidate must actually be
        able to import Gramps from this path, not just run Python --
        and a version-specific candidate name (e.g. ``python3.13``,
        parsed from a ``.../python3.13/site-packages`` -style path
        segment) is tried ahead of the generic ``python3``/``python``
        names. This directly targets the case observed in practice: a
        system ``python3`` of a different, incompatible major/minor
        version than the one this Gramps tree was actually built for,
        which can run Python fine but can't import this particular
        ``gramps`` package -- and which the old plain "does it run"
        check had no way to notice.
    :returns: Path to a working Python interpreter, or ``None``.
    """
    cached = _PYTHON_EXE_CACHE.get(gramps_path)
    if cached is not None:
        return cached

    candidates = []
    if gramps_path:
        version_match = re.search(r'python(\d+\.\d+)', gramps_path)
        if version_match:
            candidates.append(f'python{version_match.group(1)}')
    candidates.extend(("python3", "python"))

    found_exe = None
    if _validate_python_executable(sys.executable, gramps_path=gramps_path):
        found_exe = sys.executable
    else:
        for candidate in candidates:
            found = shutil.which(candidate)
            if found and _validate_python_executable(
                    found, gramps_path=gramps_path):
                found_exe = found
                break
    if found_exe is not None:
        # Only a success is cached, so a missing interpreter is looked
        # for again next time (e.g. after the user installs one).
        _PYTHON_EXE_CACHE[gramps_path] = found_exe
    return found_exe


def _validate_python_executable(candidate, gramps_path=None, timeout=5):
    """
    Confirm ``candidate`` is an actually-runnable Python interpreter,
    not merely a name that ``shutil.which()`` happened to resolve.

    :param candidate: Path to the candidate interpreter.
    :param gramps_path: If given, the probe also does exactly what
        upstream make.py's own ``listing`` command does --
        ``sys.path.insert(0, gramps_path)`` then import the two
        ``gramps.gen`` names it actually needs -- so a candidate that
        can run Python but can't import Gramps from this path (e.g. a
        system Python with a different major/minor version than the
        one this Gramps tree was built for) is rejected here instead
        of being handed to make.py, which would otherwise report
        success (exit 0) while having silently done nothing.
    :param timeout: Seconds to wait before giving up on a candidate
        that hangs (e.g. an interactive alias stub waiting on stdin).
    :returns: ``True`` if running ``candidate -c "..."`` produced the
        expected marker text; ``False`` on any failure, non-zero exit,
        timeout, or unexpected output.
    """
    probe = 'print("APS_PYTHON_OK")'
    if gramps_path:
        probe = (
            f'import sys; sys.path.insert(0, {gramps_path!r})\n'
            'from gramps.gen.const import GRAMPS_LOCALE\n'
            'from gramps.gen.plug import make_environment\n'
            'print("APS_PYTHON_OK")'
        )
    try:
        result = _run_subprocess([candidate, '-c', probe], timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "APS_PYTHON_OK" in result.stdout


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
    :returns: (success, stdout, stderr), where success is ``True``
        (ran and the expected output was verified on disk), ``False``
        (ran and failed, or ran but did not produce the expected
        output), or ``None`` (could not even be attempted -- no
        working standalone Python interpreter was found; the caller
        should fall back to the in-process, subprocess-free
        create_listing() instead of treating this as a hard failure).
    """
    addon_name = os.path.basename(addon_path)
    output_parent = os.path.dirname(os.path.abspath(output_dir))

    gramps_path = resolve_gramps_path()
    if not gramps_path:
        # None: could not even be attempted (see the tri-state note
        # in the docstring) -- let the caller fall back to
        # create_listing() instead of reporting a hard failure.
        return None, "", (
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

        python_exe = _find_real_python_executable(gramps_path=gramps_path)
        if python_exe is None:
            # None (not False) is a deliberate third state here,
            # distinct from "ran and failed": it means delegation
            # could not even be attempted. run_command() treats this
            # as a signal to fall back to the bundled English-only
            # create_listing() -- which needs no subprocess at all --
            # rather than reporting a hard failure that produces
            # nothing on a machine with no working standalone Python
            # (e.g. a Gramps AIO install with no separate Python, on
            # a Windows PATH where 'python'/'python3' only resolve to
            # the Microsoft Store's non-functional alias stub) or none
            # that can actually import Gramps from gramps_path (e.g. a
            # system Python of a different major/minor version than
            # this Gramps tree was built for -- observed in practice
            # on a frozen macOS build).
            return None, "", (
                "No standalone Python 3 interpreter capable of"
                f" importing Gramps from {gramps_path!r} could be"
                " found on PATH to run the upstream make.py script."
            )

        cmd = [python_exe, os.path.abspath(script_path),
               version_code, command, addon_name]
        try:
            result = _run_subprocess(cmd, cwd=source_dir, env=env)
        except OSError as exc:
            # _find_real_python_executable() validates each candidate
            # before returning it, but that check can still miss a
            # packaging-specific quirk (as happened in practice on a
            # macOS .app build). Treat that the same as "no working
            # interpreter found" -- None, not False -- so the caller
            # falls back to the bundled create_listing() rather than
            # taking down the whole Gramps session.
            return None, "", (
                f"Could not run the upstream make.py with interpreter "
                f"{python_exe!r}: {exc}"
            )

        if copy_back_addon:
            # Copy back anything make.py generated/updated inside the
            # staged copy -- compiled locale/*.mo and merged po files.
            # 'listing' can only ever produce/modify those two
            # subtrees, so only they are copied back, rather than the
            # whole staged_addon tree: staged_addon is a full copy of
            # the *entire* addon (see _stage_addon()'s copy fallback),
            # which can include files this delegation has no business
            # touching -- e.g. the addon's own .gpr.py/.py source, or
            # (as happened in practice) another file that happened to
            # be locked because it was a live, currently-running
            # Gramps plugin file. Copying those back unnecessarily
            # both risks a permission failure on files that were never
            # actually changed, and risks silently propagating a
            # make.py bug into the addon's real source tree.
            #
            # The synthetic po stubs must never reach the real addon,
            # so they are removed from the staged copy first.
            for rel in stub_relpaths:
                stub_path = os.path.join(staged_addon, rel)
                if os.path.isfile(stub_path):
                    os.remove(stub_path)

            copy_warnings = []
            for subdir in ('locale', 'po'):
                staged_subdir = os.path.join(staged_addon, subdir)
                if os.path.isdir(staged_subdir):
                    copy_warnings.extend(_copy_tree_contents(
                        staged_subdir, os.path.join(addon_path, subdir),
                        lenient=True))
            for warning in copy_warnings:
                # Non-fatal: by this point the listing itself has
                # already been written to output_dir by the
                # subprocess above. These are just local-tree
                # translation-file conveniences (e.g. for offline
                # testing), so a locked/read-only file here should
                # not turn a successful listing into a reported
                # failure.
                print(f"  Warning: {warning}")

        if not output_symlinked:
            # A real (empty) 'addons' dir was created instead of a
            # symlink to output_parent -- copy whatever output landed
            # in it into this run's real output tree. Lenient here
            # too: a single locked file (e.g. a listing JSON open in
            # another program) should produce a warning, not abort a
            # run that otherwise completed.
            staged_output = os.path.join(addons_link, version_code)
            if os.path.isdir(staged_output):
                for warning in _copy_tree_contents(
                        staged_output,
                        os.path.join(output_parent, version_code),
                        lenient=True):
                    print(f"  Warning: {warning}")

        if command == 'listing' and result.returncode == 0:
            # Do not trust returncode == 0 alone as proof that
            # anything was actually produced. A subprocess that
            # silently ran nothing useful (e.g. python_exe resolved
            # to a non-functional stub that validation didn't catch,
            # or make.py itself changed its output layout) can still
            # exit 0 -- as happened in practice, with no console
            # output of any kind to hint at the problem. Verify the
            # one file this call must have produced actually exists.
            expected_json = os.path.join(output_dir, 'listings',
                                          'addons-en.json')
            if not os.path.isfile(expected_json):
                diag_stdout = result.stdout or '(no output captured)'
                diag_stderr = result.stderr or '(no output captured)'
                # None, not False: a script that exits 0 having
                # silently done nothing (see this function's own
                # preflight-probe comment above, and the ImportError
                # case that motivated it) is functionally identical to
                # "delegation could not be attempted" -- the
                # environment cannot make this upstream script do its
                # job, whatever the reason. Reporting a hard failure
                # here left the caller with no working listing at all
                # even though create_listing() (the existing fallback
                # for a genuinely unusable interpreter) runs in-process
                # against the same live Gramps and doesn't share
                # whatever problem just prevented a *separate*
                # interpreter from importing it.
                return None, "", (
                    f"make.py reported success (exit 0) but did not "
                    f"produce {expected_json}.\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"Working directory: {source_dir}\n"
                    f"--- stdout ---\n{diag_stdout}\n"
                    f"--- stderr ---\n{diag_stderr}"
                )

        return result.returncode == 0, result.stdout, result.stderr


def _find_gpr_file(addon_path: str) -> str | None:
    """
    Find this addon's .gpr.py registration file.

    Tries the two conventional names first (matching / lowercased
    addon directory name), then falls back to the first .gpr.py found
    in the directory.

    :param addon_path: Path to the addon's source directory.
    :returns: Path to the .gpr.py file, or ``None`` if none was found.
    """
    addon_name = os.path.basename(addon_path)
    for candidate in [
        os.path.join(addon_path, f"{addon_name}.gpr.py"),
        os.path.join(addon_path, f"{addon_name.lower()}.gpr.py"),
    ]:
        if os.path.exists(candidate):
            return candidate
    for fn in os.listdir(addon_path):
        if fn.endswith('.gpr.py'):
            return os.path.join(addon_path, fn)
    return None


def _canonical_version_tuple(version_code):
    """
    Return a representative (major, minor, 0) VERSION_TUPLE for a
    version code like 'gramps61', e.g. (6, 1, 0).

    This is used only to evaluate a .gpr.py's own version-range gate
    (e.g. ``if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):``) for a
    *different* version than whichever Gramps is actually running --
    the patch digit is irrelevant to that comparison, so 0 is always
    safe to use.

    :returns: A 3-tuple, or ``None`` if version_code isn't in the
        expected 'grampsNN' form.
    """
    digits = _version_digits(version_code)
    if len(digits) < 2 or not digits.isdigit():
        return None
    return (int(digits[0]), int(digits[1:]), 0)


def _extract_literal_target_version(source):
    """
    Statically find a single, literal (hardcoded string)
    ``gramps_target_version=`` value across every ``register()`` call
    in a .gpr.py's source, without executing any of it.

    Many real .gpr.py files -- including ones with no version-range
    gate at all -- hand-write a single fixed version string here
    rather than computing it from ``major_version``. That's a genuine,
    precise compatibility declaration (this addon supports exactly
    this one version), just not expressed as a range. Detecting it
    statically lets check_gpr_version_coverage() give a real
    True/False verdict for that case instead of falling back to a
    generic "unverified".

    :param source: The .gpr.py file's source text.
    :returns: The literal string (e.g. ``'6.1'``) if every
        ``register()`` call that specifies ``gramps_target_version``
        with a plain string literal agrees on the same value, and at
        least one does. ``None`` if no call specifies one as a
        literal (it may be a computed expression like
        ``major_version``, or omitted), or if different calls
        disagree -- either way there's no single value to check
        against.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    literals = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'register'):
            continue
        for kw in node.keywords:
            if (kw.arg == 'gramps_target_version'
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)):
                literals.add(kw.value.value)

    return literals.pop() if len(literals) == 1 else None


def check_gpr_version_coverage(addon_path: str,
                                version_codes: list[str]) -> dict:
    """
    Check whether this addon's own .gpr.py would actually register
    itself under each of ``version_codes``, by re-exec'ing the file
    once per version with ``gramps.version.VERSION_TUPLE`` and
    ``major_version`` temporarily patched to that version's values.

    This exists because a multi-version build duplicates one built
    .addon.tgz into every selected version's download/ folder (see
    AddonPackShip.build_for_versions()) on the assumption that the
    addon's own code and .gpr.py are already compatible with all of
    them. That assumption can be wrong -- a .gpr.py written or
    updated while only a newer Gramps was installed may use syntax or
    values that a genuinely older target version's gate does not
    expect -- and the previous behaviour was to duplicate unchecked
    either way.

    Never rewrites the .gpr.py itself, even when it disagrees with a
    target version -- only reports the mismatch so the caller can
    refuse to duplicate into it. Silently rewriting version-related
    metadata during packaging is exactly the upstream make.py behavior
    (always bumping the version on every build) that motivated keeping
    this tool's own packaging engine in the first place.

    Most .gpr.py files have no explicit version-range gate at all
    (they just register unconditionally). A sentinel probe with an
    implausible version tells a genuine gate apart from this common
    case -- if register() fires even for that, there's no real gate.
    When there isn't one, this also checks for a hardcoded, literal
    ``gramps_target_version=`` string (see
    _extract_literal_target_version()): many real addons declare
    compatibility with exactly one version this way rather than a
    range, and that's a precise, checkable claim even without a gate.
    Only when neither a gate nor a literal value can be found is a
    version reported as genuinely unverified.

    :param addon_path: Path to the addon's source directory.
    :param version_codes: Version codes to check, e.g.
        ``['gramps52', 'gramps60', 'gramps61']``.
    :returns: ``{version_code: True/False/None}``. ``True`` means
        either a version-range gate registered under that version, or
        a hardcoded literal ``gramps_target_version`` matches it
        exactly. ``False`` means a gate excluded it (or raised while
        evaluating it), or a hardcoded literal names a different
        version. ``None`` means this could not be verified at all --
        no .gpr.py found, Gramps/the version module unavailable, or
        (the common case) no gate and no literal value either.
        Callers should treat ``None`` as "unverified", not as a
        failure, and should not treat it as equivalent to a confirmed
        ``True``.
    """
    gpr_file = _find_gpr_file(addon_path)
    if not gpr_file:
        return {code: None for code in version_codes}

    try:
        import gramps.version as gramps_version_module
        from gramps.gen.plug import make_environment
    except ImportError:
        return {code: None for code in version_codes}

    with open(gpr_file, encoding='utf-8', errors='backslashreplace') as fh:
        source = fh.read()
    code_obj = compile(source, gpr_file, 'exec')

    original_tuple = gramps_version_module.VERSION_TUPLE
    original_major = gramps_version_module.major_version
    results = {}

    def _registers_under(target_tuple, version_label):
        """Exec the .gpr.py under a patched VERSION_TUPLE/major_version
        and report whether register() actually fired. Returns None on
        an exception during exec (ambiguous, not a clean signal either
        way), rather than False, so the sentinel probe below doesn't
        misread a genuinely gate-related crash as "no gate"."""
        registered = []

        def register(*_args, **_kwargs):
            registered.append(True)

        gramps_version_module.VERSION_TUPLE = target_tuple
        gramps_version_module.major_version = version_label
        try:
            exec(code_obj,
                 make_environment(_=lambda s: s),
                 {'register': register, 'build_script': True})
        except Exception:  # pylint: disable=broad-except
            return None
        return bool(registered)

    try:
        # Sentinel: an absurd version no real addon should legitimately
        # claim to support. If register() fires even under this, the
        # .gpr.py has no genuine version-range gate at all -- it's
        # registering unconditionally, and a True result below for any
        # real version_code would be a false positive (the developer
        # made no compatibility claim, positive or negative, not
        # confirmation the code actually works there). In that case
        # every result for this addon is reported as unverified rather
        # than falsely "covered", so callers know to warn rather than
        # duplicate silently.
        has_real_gate = _registers_under((0, 0, 0), '0.0') is not True
        literal_target_version = (
            None if has_real_gate else _extract_literal_target_version(source))

        for version_code in version_codes:
            target_tuple = _canonical_version_tuple(version_code)
            if target_tuple is None:
                results[version_code] = None
                continue
            target_label = _version_label(_version_digits(version_code))
            if not has_real_gate:
                if literal_target_version is not None:
                    results[version_code] = (
                        literal_target_version == target_label)
                else:
                    results[version_code] = None
                continue
            results[version_code] = _registers_under(
                target_tuple, target_label)
    finally:
        gramps_version_module.VERSION_TUPLE = original_tuple
        gramps_version_module.major_version = original_major

    return results


def create_listing(addon_path: str, output_dir: str,
                    target_languages: list[str] | None = None) -> bool:
    """
    Create / update the addons-<lang>.json listing entries for this
    addon, for every language in ``target_languages``. 'en' is always
    included as the base/fallback listing language; it is added
    automatically even if not requested.

    :param addon_path: Path to the addon's source directory.
    :param output_dir: This run's ``<output_parent>/<version_code>``
        output directory.
    :param target_languages: Languages to generate listing entries
        for (e.g. ``['en', 'fr', 'nl']``). Defaults to English only
        when not given.
    :returns: ``True`` on success, ``False`` on failure.

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

    gpr_file = _find_gpr_file(addon_path)
    if not gpr_file:
        print(f"  Error: No .gpr.py file found for {addon_name}")
        return False

    # ── Check .tgz exists ────────────────────────────────────────────────────
    tgz_file = os.path.join(output_dir, 'download', f"{addon_name}.addon.tgz")
    if not os.path.exists(tgz_file):
        # Return True (not an error) so the UI shows ✓ with a warning
        # rather than ✗ with "Error:". A missing .tgz is a workflow
        # reminder ("Build first"), not a fault. This must be a plain
        # return, not sys.exit(): this function is called in-process
        # (see run_command()), and sys.exit() here would tear down the
        # whole calling Gramps application rather than just this step.
        print(f"  ⚠  {addon_name}.addon.tgz not found — run Build first.")
        print(f"  Skipping listing for {addon_name}.")
        return True

    # ── Resolve which languages to generate ───────────────────────────────────
    # 'en' is always produced; any other requested language still lists
    # every addon (falling back to English text) so the catalog for that
    # language remains a complete, usable addon list on its own.
    resolved_languages = []
    for lang in (target_languages or ['en']):
        lang = lang.strip()
        if lang and lang not in resolved_languages:
            resolved_languages.append(lang)
    if 'en' not in resolved_languages:
        resolved_languages.insert(0, 'en')
    target_languages = resolved_languages

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


def _listing_sort_key(entry):
    """
    Sort key for addons-<lang>.json entries: by 'n' (the name shown
    in the Addon Manager), case-insensitively, so a person reading the
    file finds an addon where the GUI lists it. Then 'i' and 't' as
    tiebreakers, so plugins sharing a name (e.g. a CSV importer and
    exporter) always come out in the same order.

    This is a reading order only. make52.py's single-addon merge
    assumes (type, id) order, but _reconcile_listing_with_gpr()
    repairs whatever that merge leaves, so file order no longer
    affects correctness.

    :param entry: One listing entry dict.
    :returns: A sortable tuple.
    """
    try:
        ptype = int(entry.get('t', 0))
    except (TypeError, ValueError):
        ptype = 0
    return (
        str(entry.get('n', '')).casefold(),
        str(entry.get('i', '')).casefold(),
        ptype,
    )


def _fresh_listing_entries(gpr_file, addon_name, lang):
    """
    Return the listing entries this addon's .gpr.py produces right now
    for `lang` -- the same exec() + make_environment() approach as
    create_listing() -- or None if Gramps can't be imported here.

    :param gpr_file: Path to the addon's .gpr.py.
    :param addon_name: The addon's directory name.
    :param lang: Listing language code, e.g. 'en'.
    :returns: A list of entry dicts, or None.
    """
    try:
        from gramps.gen.plug import make_environment
        from gramps.gen.const import GRAMPS_LOCALE as glocale
    except ImportError:
        return None

    plugins = []

    def register(ptype, **kwargs):
        kwargs['ptype'] = ptype
        plugins.append(kwargs)

    glocale.language = [lang]
    local_gettext = glocale.get_addon_translator(
        gpr_file, languages=[lang, 'en.UTF-8']).gettext
    with open(gpr_file, encoding='utf-8', errors='backslashreplace') as fh:
        code = compile(fh.read(), gpr_file, 'exec')
    exec(code,  # pylint: disable=exec-used
         make_environment(_=local_gettext),
         {'register': register, 'build_script': True})
    return [_build_listing_entry(p, addon_name) for p in plugins
            if p.get('include_in_listing', True)]


def _listing_entries_match(current, fresh):
    """
    Whether the entries already in a listing file for one addon
    (`current`) are exactly the ones its .gpr.py produces now
    (`fresh`): same count, one entry per plugin id, and every field
    _build_listing_entry() produces equal -- except 'g', which
    _patch_listing_target_version() sets separately. Extra fields an
    upstream make<NN>.py adds (e.g. make61.py's 'do') are ignored.
    """
    if len(current) != len(fresh):
        return False
    by_id = {}
    for entry in current:
        if entry.get('i') in by_id:
            return False  # duplicate entry for one plugin
        by_id[entry.get('i')] = entry
    for entry in fresh:
        existing = by_id.get(entry['i'])
        if existing is None:
            return False
        for key, value in entry.items():
            if key != 'g' and existing.get(key) != value:
                return False
    return True


def _reconcile_listing_with_gpr(addon_path, output_dir):
    """
    Make sure every addons-<lang>.json under output_dir/listings/
    lists this addon exactly as its .gpr.py does now -- run after the
    'listing' command, whichever generator produced it.

    Needed because make52.py still has the old upstream single-addon
    merge: it inserts the new entry before the first existing line
    whose (type, id) sorts after it, and KEEPS the addon's old line
    wherever that sits. On a file not sorted by (type, id) this leaves
    a stale duplicate (e.g. Photo Tagging 1.2.4 *and* 1.1.3), and a
    later dedupe that keeps the last occurrence then kept the stale
    one. make60.py/make61.py replace the addon's entries instead, so
    they were not affected. Reported success was based only on
    addons-en.json existing, so nothing flagged it.

    When a file's entries for this addon differ from the .gpr.py
    (missing, stale, duplicated), all of this addon's entries are
    removed and the fresh ones inserted, and the file is written in
    name order (see _listing_sort_key()). Fields an upstream script added that this
    module does not produce (e.g. 'do') are carried over from the
    old entry for the same plugin id. Files that already match are
    left byte-for-byte untouched.

    :param addon_path: Path to the addon's source directory.
    :param output_dir: This run's <output_parent>/<version_code>.
    """
    addon_name = os.path.basename(addon_path)
    tgz_name = f"{addon_name}.addon.tgz"
    listings_dir = os.path.join(output_dir, 'listings')
    gpr_file = _find_gpr_file(addon_path)
    if not gpr_file or not os.path.isdir(listings_dir):
        return

    for path in sorted(glob.glob(os.path.join(listings_dir, 'addons-*.json'))):
        fname = os.path.basename(path)
        lang = fname[len('addons-'):-len('.json')]
        try:
            fresh = _fresh_listing_entries(gpr_file, addon_name, lang)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  Warning: could not check {fname} against the"
                  f" .gpr.py: {exc}")
            continue
        if fresh is None:
            print("  Warning: Gramps not importable -- listings were not"
                  " checked against the .gpr.py.")
            return
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                existing = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(existing, list):
            continue

        current = [e for e in existing
                   if isinstance(e, dict) and e.get('z') == tgz_name]
        if _listing_entries_match(current, fresh):
            continue

        known = set(_build_listing_entry({}, addon_name)) | {
            'rm', 'rg', 're', 'h', 'a'}
        extras_by_id = {}
        for entry in current:
            extras = {k: v for k, v in entry.items() if k not in known}
            if extras:
                extras_by_id.setdefault(entry.get('i'), {}).update(extras)
        repaired = []
        for entry in fresh:
            merged = dict(extras_by_id.get(entry['i'], {}))
            merged.update(entry)
            repaired.append(merged)

        fresh_keys = {(e['t'], e['i']) for e in repaired}
        kept = [e for e in existing
                if not (isinstance(e, dict) and e.get('z') == tgz_name)
                and not (isinstance(e, dict)
                         and (e.get('t'), e.get('i')) in fresh_keys)]
        result = sorted(kept + repaired, key=_listing_sort_key)
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                json.dump(result, fh, indent=2, ensure_ascii=False)
                fh.write('\n')
        except OSError as exc:
            print(f"  Warning: could not repair {fname}: {exc}")
            continue
        old_versions = ", ".join(
            f"{e.get('i')} {e.get('v')}" for e in current) or "none"
        new_versions = ", ".join(f"{e['i']} {e['v']}" for e in repaired)
        print(f"  Repaired {fname}: was [{old_versions}],"
              f" now [{new_versions}]")


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

def run_command(
        command: str, addon_path: str, output_dir: str,
        build_mode: str = 'beta',
        target_languages: list[str] | None = None,
        session_id: str | None = None,
        multilingual: bool | None = None,
        wait_callback=None
) -> tuple[bool, str, str]:
    """
    Run one packaging command and return its outcome.

    This is the single entry point for the packaging engine: it holds
    the command dispatch logic previously duplicated between main()
    and AddonPackShip.py's own subprocess-launching code, now that
    AddonPackShip.py imports this module directly and calls this
    function in-process instead of shelling out to
    ``sys.executable`` (which, under a frozen/cx_Freeze build of
    Gramps, is the Gramps application itself rather than a usable
    Python interpreter -- see the module docstring history).

    Because this runs in-process, nothing it calls may call
    ``sys.exit()`` -- doing so would terminate the calling
    application, not just this packaging step. Any such calls have
    been converted to plain ``return`` statements in the functions
    this dispatches to. Any unexpected exception is caught here and
    reported as a failure rather than propagating into the caller.

    All of the functions this dispatches to communicate progress via
    ``print()``; that output is captured here so callers get the same
    ``(success, stdout, stderr)`` shape that used to come from
    ``subprocess.run(..., capture_output=True, text=True)``, without
    needing any changes on the caller's side.

    :param command: One of ``'build'``, ``'compile'``, ``'listing'``,
        ``'clean'``.
    :param addon_path: Path to the addon's source directory.
    :param output_dir: This run's ``<output_parent>/<version_code>``
        output directory.
    :param build_mode: ``'beta'`` or ``'release'`` -- only used by
        ``'build'``.
    :param target_languages: Languages to generate listing entries
        for -- only used by ``'listing'`` (English-only fallback
        path). Defaults to English only.
    :param session_id: When given (by AddonPackShip.py, once per GUI
        tool session), the CLI-equivalent of whatever this call ends
        up doing is appended to this plugin's own
        ``logs/<session_id>.log`` -- a teaching transcript a
        developer can read to learn how to drive make.py by hand.
        ``None`` (the default, used by this module's own CLI
        ``main()``) skips logging entirely.
    :param multilingual: Only used by ``'listing'``. ``True``
        generates/keeps ``addons-<lang>.json`` for every language the
        addon has a ``po/<lang>-local.po`` for; ``False`` restricts
        the result to English only, regardless of how many
        translations the addon actually has. ``None`` (the default,
        used by this module's own CLI ``main()``) falls back to the
        module-level ``ENABLE_NON_ENGLISH_LISTINGS`` constant.
        AddonPackShip.py's GUI always passes an explicit value here,
        from its "Multilingual" checkbox.
    :param wait_callback: Optional function with no arguments, called
        about ten times a second while this command waits on a child
        process (msgfmt, the interpreter probe, an upstream
        make<NN>.py) -- lets a GUI caller keep its window responsive.
        ``None`` (the default, used by this module's own CLI
        ``main()``) waits normally.
    :returns: ``(success, stdout, stderr)``.
    """
    global _WAIT_CALLBACK  # pylint: disable=global-statement
    previous_wait_callback = _WAIT_CALLBACK
    _WAIT_CALLBACK = wait_callback
    try:
        return _run_command(command, addon_path, output_dir, build_mode,
                            target_languages, session_id, multilingual)
    finally:
        _WAIT_CALLBACK = previous_wait_callback


def _run_command(command, addon_path, output_dir, build_mode,
                 target_languages, session_id, multilingual):
    """
    The body of run_command(), separated so run_command() can set and
    reliably reset _WAIT_CALLBACK around it. See run_command() for the
    parameters and return value.
    """
    effective_multilingual = (
        ENABLE_NON_ENGLISH_LISTINGS if multilingual is None else multilingual)

    if not os.path.isdir(addon_path):
        return False, "", f"Error: Addon path does not exist: {addon_path}"

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
    addon_name = os.path.basename(addon_path)

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    success = False

    try:
        with (contextlib.redirect_stdout(stdout_buffer),
              contextlib.redirect_stderr(stderr_buffer)):
            if command == 'build':
                # See module docstring: intentionally not delegated (no
                # automatic version increments).
                success = build_addon(addon_path, output_dir,
                                       build_mode=build_mode)
                _log_build_style_command(
                    'build', upstream_script, version_code, addon_name,
                    addon_path, output_dir, build_mode, success, session_id)
            elif command == 'compile':
                # See module docstring: intentionally not delegated (low
                # drift risk, no staging overhead needed).
                success = compile_translations(addon_path, output_dir)
                _log_build_style_command(
                    'compile', upstream_script, version_code, addon_name,
                    addon_path, output_dir, build_mode, success, session_id)
            elif command == 'listing':
                target_label = _version_label(_version_digits(version_code))
                upstream_result = None
                upstream_failure_detail = None
                if upstream_script:
                    # Delegating to the upstream make<NN>.py: kept as a
                    # subprocess call (inside run_upstream_command())
                    # rather than imported, because that script is
                    # fetched as-is from gramps-project/addons-source
                    # (see "Update make.py Scripts") and so is treated
                    # as untrusted, unmodified third-party code that
                    # should stay process-isolated.
                    upstream_result, up_stdout, up_stderr = (
                        run_upstream_command(upstream_script, version_code,
                                              'listing', addon_path,
                                              output_dir))
                    success = bool(upstream_result)
                    if up_stdout:
                        print(up_stdout,
                              end='' if up_stdout.endswith('\n') else '\n')
                    if up_stderr:
                        print(up_stderr,
                              end='' if up_stderr.endswith('\n') else '\n',
                              file=sys.stderr)
                    if upstream_result is not None:
                        # A real attempt was made (whether it
                        # succeeded or failed) -- log the actual
                        # make<NN>.py invocation, since that is the
                        # real upstream CLI tool this is teaching.
                        outcome = "succeeded" if success else "failed"
                        script_name = os.path.basename(upstream_script)
                        note = (
                            f"requires {addon_name}/ as a subdirectory"
                            " of the current directory, with"
                            f" ../addons/{version_code}/ as the"
                            " sibling output tree (see make.py's own"
                            " conventions)"
                        )
                        if not success:
                            # The explanatory note above is always the
                            # same text regardless of *why* this run
                            # failed -- on its own it gave no way to
                            # tell a real make.py error apart from
                            # this delegation's own layout assumptions
                            # not holding. Include whatever the
                            # subprocess actually said, so the log is
                            # useful for diagnosing this after the
                            # fact, not just for learning the
                            # equivalent CLI form.
                            failure_detail = (up_stderr or up_stdout
                                               or '(no output captured)')
                            # No truncation here (unlike the GUI
                            # dialog's 200-char cap in
                            # _collect_command_result()) -- this is a
                            # plain text log file with no size
                            # constraint to justify one, and a short
                            # cap has already once cut off the single
                            # most diagnostic detail (the actual
                            # resolved GRAMPSPATH value) in practice.
                            note += f"\n  Command output: {failure_detail}"
                        _log_session_command(
                            session_id,
                            f'python3 {script_name} {version_code} listing'
                            f' {addon_name}  # {outcome}',
                            note=note)
                    else:
                        # Could not really be attempted (e.g. no
                        # working standalone Python interpreter on
                        # this machine, or -- as observed in practice
                        # -- a version-mismatched interpreter that
                        # can't import the gramps tree at GRAMPSPATH;
                        # see run_upstream_command()'s docstring and
                        # its artifact-verification comment). Fall
                        # back below to the bundled, subprocess-free
                        # English-only generator rather than reporting
                        # a hard failure that produces nothing at all.
                        # Keep the real diagnostic (if any) so it's
                        # still logged rather than silently lost the
                        # moment recovery succeeds.
                        upstream_failure_detail = (
                            up_stderr or up_stdout or None)
                        print("  Falling back to bundled English-only "
                              "listing generator (any other languages "
                              "this addon has will not be included).")

                if not upstream_script or upstream_result is None:
                    if not upstream_script:
                        print(f"  No make{_version_digits(version_code)}.py"
                              f" found for {version_code} -- using bundled"
                              " English-only fallback. Use AddonPackShip's"
                              " \"Update make.py Scripts\" action to fetch"
                              " it from GitHub.")
                    if not effective_multilingual:
                        # Cheap early narrowing for this path only (we
                        # control it entirely, unlike the upstream
                        # script): avoids compiling/exec'ing languages
                        # that _prune_non_english_listings() would
                        # just delete again below. create_listing()
                        # itself is untouched and still accepts
                        # target_languages normally.
                        target_languages = ['en']
                    success = create_listing(addon_path, output_dir,
                                              target_languages)
                    fallback_note = None
                    if upstream_failure_detail:
                        fallback_note = (
                            "upstream make.py delegation was attempted"
                            " but could not actually produce a listing"
                            " -- falling back to this bundled"
                            " generator instead. What make.py reported:"
                            f"\n  {upstream_failure_detail}")
                    _log_session_command(
                        session_id,
                        f'python3 make_addon.py listing "{addon_path}"'
                        f' "{output_dir}"'
                        f'  # {"succeeded" if success else "failed"}',
                        note=fallback_note)
                if success:
                    # First make sure the listing really holds this
                    # addon's current .gpr.py entries -- make52.py can
                    # leave a stale duplicate behind (see
                    # _reconcile_listing_with_gpr()). Done before the
                    # 'g' correction below, since the repaired entries
                    # carry the running Gramps version in 'g'.
                    _reconcile_listing_with_gpr(addon_path, output_dir)
                    # Correct 'g' (target version) for this addon's own
                    # entries: the addon's .gpr.py computed it from
                    # whichever single Gramps is actually installed,
                    # not from version_code.
                    _patch_listing_target_version(output_dir, addon_name,
                                                   target_label)
                    listings_dir = os.path.join(output_dir, 'listings')
                    if not effective_multilingual:
                        _prune_non_english_listings(listings_dir)
                    if os.path.isdir(listings_dir) and any(
                            fn.startswith('addons-') and fn.endswith('.txt')
                            for fn in os.listdir(listings_dir)):
                        print(f"  Note: Gramps {target_label} uses the "
                              "legacy addons-<lang>.txt listing format, "
                              "not JSON -- expected for Gramps versions "
                              "before 5.2, not an error.")
            elif command == 'clean':
                # See module docstring: intentionally not delegated
                # (preserves compiled translations for local testing).
                success = clean_addon(addon_path, output_dir)
                _log_build_style_command(
                    'clean', upstream_script, version_code, addon_name,
                    addon_path, output_dir, build_mode, success, session_id)
            else:
                print(f"Unknown command: {command}", file=sys.stderr)
                success = False
    except Exception as exc:  # pylint: disable=broad-except
        # Mirrors the previous subprocess boundary: a failure inside
        # the packaging engine must never propagate into (and
        # potentially crash) the process that called run_command().
        LOG.exception("run_command(%s) failed", command)
        print(str(exc), file=stderr_buffer)
        success = False

    return success, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def main() -> None:
    """
    Command-line entry point.

    Kept for standalone/CI use (``python3 make_addon.py <command>
    <addon_path> <output_dir>``); AddonPackShip.py itself no longer
    goes through this -- it imports this module and calls
    run_command() directly. BUILD_MODE and ADDON_LANGUAGES environment
    variables are only read here, at the CLI boundary, and passed into
    run_command() as plain arguments.
    """
    if len(sys.argv) < 4:
        print("Usage: make_addon.py <command> <addon_path> <output_dir>")
        print("Commands: build, compile, listing, clean")
        sys.exit(1)

    command = sys.argv[1]
    addon_path = sys.argv[2]
    output_dir = sys.argv[3]
    build_mode = os.environ.get('BUILD_MODE', 'beta')
    requested = os.environ.get('ADDON_LANGUAGES', 'en')
    target_languages = [lang.strip() for lang in requested.split(',')
                         if lang.strip()]

    success, stdout, stderr = run_command(
        command, addon_path, output_dir, build_mode=build_mode,
        target_languages=target_languages)

    if stdout:
        print(stdout, end='' if stdout.endswith('\n') else '\n')
    if stderr:
        print(stderr, end='' if stderr.endswith('\n') else '\n',
              file=sys.stderr)

    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
