# Feature Comparison: make.py vs AddonPackShip

**Document Version**: 1.0  
**Date**: February 2026  
**AddonPackShip Version**: 1.7.3
**Author**: Claude (Anthropic AI)
---

## Overview

**make.py** is the original command-line tool for Gramps addon packaging, used by addon maintainers and the Gramps project itself.
https://github.com/gramps-project/addons-source/tree/maintenance/gramps52/make.py

**AddonPackShip** is a GUI tool that provides a user-friendly interface for the most common addon packaging workflows.

This document explains which `make.py` features are available in AddonPackShip and which require using the command-line tool.

---

## Feature Availability Matrix

| Feature | make.py Command | AddonPackShip GUI | Status | Notes |
|---------|----------------|-------------------|--------|-------|
| **Build addon package** | `build AddonName` | ✅ Build Selected | Full | Creates `.addon.tgz` files |
| **Build all addons** | `build all` | ✅ Select All + Build | Full | Multi-select support |
| **Compile translations** | `compile AddonName` | ✅ Compile Translations | Full | Compiles `.po` → `.mo` |
| **Compile all translations** | `compile all` | ✅ Select All + Compile | Full | Multi-select support |
| **Generate listings** | `listing AddonName` | ✅ Create Listings | Full | Creates JSON metadata |
| **Generate all listings** | `listing all` | ✅ Select All + Listing | Full | Multi-select support |
| **Pack and Ship workflow** | `build` + `listing` | ✅ Pack and Ship | Enhanced | One-button workflow with β/Δ modes |
| **Clean cache files** | `clean` | ❌ Removed | N/A | Feature disabled pending safety review |
| **Create MANIFEST** | Manual editing | ✅ Edit MANIFEST | Enhanced | GUI editor with directory preview |
| **Generate template.pot** | `xgettext` (manual) | ✅ Auto-generated | Enhanced | Created during Compile if missing |
| **Initialize addon structure** | `init AddonDirectory` | ❌ Not Available | Use make.py | Creates directory structure |
| **Initialize translation file** | `init AddonDirectory fr` | ❌ Not Available | Use make.py | Creates empty `.po` files |
| **Update translations** | `update AddonDirectory fr` | ❌ Not Available | Use make.py | Updates `.po` from `.pot` |
| **Build as-needed** | `as-needed` | ❌ Not Available | Use make.py | Builds only changed addons |
| **Manifest validation** | `manifest-check` | ❌ Not Available | Use make.py | Validates MANIFEST syntax |
| **Unlist addon** | `unlist AddonName` | ❌ Not Available | Use make.py | Removes from listings |
| **Check addon** | `check AddonName` | ❌ Not Available | Use make.py | Validates addon structure |
| **Aggregate POT files** | `aggregate-pot` | ❌ Not Available | Use make.py | Combines all `.pot` files |
| **Extract PO translations** | `extract-po` | ❌ Not Available | Use make.py | Splits aggregated translations |

---

## ✅ Features Available in AddonPackShip

### 1. Build Addon Packages
**make.py**: `python3 make.py gramps52 build AddonName`  
**AddonPackShip**: Select addon(s) → **Build Selected**

**Advantages in GUI**:
- Visual selection interface
- Multi-select support
- Real-time feedback
- Shows which MANIFEST file was used
- Dual build modes (β Beta / Δ Release)

### 2. Compile Translations
**make.py**: `python3 make.py gramps52 compile AddonName`  
**AddonPackShip**: Select addon(s) → **Compile Translations**

**Advantages in GUI**:
- Auto-generates `template.pot` if missing
- Visual selection of multiple addons
- Progress feedback
- Flexible `.po` file naming (handles `-local`, `_FR`, etc.)

### 3. Generate Listings
**make.py**: `python3 make.py gramps52 listing AddonName`  
**AddonPackShip**: Select addon(s) → **Create Listings**

**Advantages in GUI**:
- Uses actual plugin registration data (more accurate)
- Multi-select support
- Shows metadata extraction
- Validates `.gpr.py` syntax

### 4. Pack and Ship (Enhanced Workflow)
**make.py**: Multiple commands required  
**AddonPackShip**: **📦 Pack and Ship (Build + Listing)**

**GUI Exclusive Features**:
- **β Beta mode**: Auto-includes translation sources, docs, all files
- **Δ Release mode**: Clean end-user package
- Warning dialog before lossy Release builds
- One-click complete workflow
- Visual confirmation of output location

### 5. MANIFEST Editor (GUI Exclusive)
**make.py**: Manual file editing  
**AddonPackShip**: **✏️ Edit MANIFEST** button

**Features**:
- Creates `MANIFEST` or `MANIFEST.beta` based on mode
- Seeds from existing MANIFEST when creating `.beta`
- Appends filtered directory listing
- Opens in system default editor
- Smart filtering (omits auto-included files)

---

## ❌ Features NOT Available in AddonPackShip

These features require using the command-line `make.py` tool:

### 1. Initialize New Addon Structure
**Command**: `python3 make.py gramps52 init AddonDirectory`

**What it does**:
- Creates addon directory
- Creates `po/` subdirectory
- Sets up basic structure

**Why not in GUI**: This is a one-time setup task better suited to command-line or IDE.

### 2. Initialize Translation Files
**Command**: `python3 make.py gramps52 init AddonDirectory fr`

**What it does**:
- Creates empty `po/fr-local.po` file
- Sets up translation file headers

**Why not in GUI**: Rare operation; translators typically receive `.po` files from developers.

### 3. Update Existing Translations
**Command**: `python3 make.py gramps52 update AddonDirectory fr`

**What it does**:
- Runs `msgmerge` to update `.po` files from new `.pot`
- Preserves existing translations
- Adds new strings, marks obsolete ones

**Workaround**: Use standalone `msgmerge`:
```bash
msgmerge -U po/fr-local.po po/template.pot
```

### 4. Build As-Needed (Incremental)
**Command**: `python3 make.py gramps52 as-needed`

**What it does**:
- Checks modification times
- Rebuilds only changed addons
- Regenerates listings
- Runs cleanup

**Why not in GUI**: Optimization for batch operations; GUI is for explicit user actions.

### 5. Manifest Validation
**Command**: `python3 make.py gramps52 manifest-check`

**What it does**:
- Validates MANIFEST syntax
- Checks for non-existent files
- Reports errors

**Workaround**: AddonPackShip validates during build and reports errors.

### 6. Unlist Addon
**Command**: `python3 make.py gramps52 unlist AddonName`

**What it does**:
- Removes addon from listing JSON
- Keeps `.addon.tgz` file

**Workaround**: Manually edit JSON file or don't build listing for that addon.

### 7. Check Addon Structure
**Command**: `python3 make.py gramps52 check AddonName`

**What it does**:
- Validates `.gpr.py` syntax
- Checks required files exist
- Reports structural issues

**Workaround**: AddonPackShip validates during build and reports malformed `.gpr.py` files.

### 8. Aggregate POT Files
**Command**: `python3 make.py gramps60 aggregate-pot`

**What it does**:
- Combines all `template.pot` files
- Creates single `po/addons.pot`
- Excludes strings already in `gramps.pot`

**Purpose**: For Gramps project translation coordination.

**Why not in GUI**: Project-level operation, not needed by individual addon developers.

### 9. Extract PO Translations
**Command**: `python3 make.py gramps60 extract-po`

**What it does**:
- Extracts translations from aggregated `po/{lang}.po`
- Distributes to individual addon `{lang}-local.po` files

**Purpose**: For Gramps project translation distribution.

**Why not in GUI**: Project-level operation, reverse of aggregation.

---

## Clean Feature (Temporarily Disabled)

**Command**: `python3 make.py gramps52 clean [AddonDirectory]`  
**AddonPackShip**: ❌ Removed (pending safety review)

**What it does**:
- Removes `__pycache__` directories
- Deletes `.pyc`, `.pyo` bytecode files
- Cleans editor backup files (`*~`)

**Status**: Disabled in v1.7.0 due to safety concerns about inadvertent file deletion during development.

**Workaround**: Manually delete `__pycache__/` directories when needed.

---

## Workflow Recommendations

### For Individual Addon Developers

**Use AddonPackShip for**:
- Day-to-day packaging
- Creating beta releases
- Generating final releases
- Compiling translations
- Creating/editing MANIFEST files

**Use make.py for**:
- Initial addon setup (`init`)
- Updating translation files (`update`)
- Batch operations on many addons

### For Gramps Project Maintainers

**Use AddonPackShip for**:
- Testing individual addons
- Quick rebuilds during review

**Use make.py for**:
- Batch building all addons (`build all`)
- Translation aggregation (`aggregate-pot`)
- Translation distribution (`extract-po`)
- Incremental builds (`as-needed`)
- Structural validation (`check`, `manifest-check`)

### For Translators

**Use AddonPackShip for**:
- Compiling translations to test
- Generating `template.pot` from source

**Use make.py for**:
- Updating `.po` files from new `.pot` (`update`)

---

## Migration Notes

If you're currently using `make.py` and want to switch to AddonPackShip:

### What You Can Replace

✅ **Daily packaging workflow**  
Replace: `python3 make.py gramps52 build MyAddon && python3 make.py gramps52 listing MyAddon`  
With: Select addon → **Pack and Ship**

✅ **Translation compilation**  
Replace: `python3 make.py gramps52 compile MyAddon`  
With: Select addon → **Compile Translations**

✅ **MANIFEST management**  
Replace: Text editor  
With: **Edit MANIFEST** button

### What You Must Keep make.py For

❌ **New addon initialization** (`init`)  
❌ **Translation file updates** (`update`)  
❌ **Project-wide aggregation** (`aggregate-pot`, `extract-po`)

---

## Summary

**AddonPackShip** covers **~70% of common use cases** with a much easier interface:
- Building packages (single or batch)
- Compiling translations
- Creating listings
- MANIFEST editing
- Dual build modes (β/Δ)

**make.py** remains necessary for:
- Initial setup operations
- Advanced translation workflows
- Project-level coordination
- Batch optimization features

**Best Practice**: Use AddonPackShip for regular addon packaging, keep `make.py` available for specialized operations.

---

## Additional Resources

- **AddonPackShip README.md** — Complete GUI tool documentation
- **AddonPackShip QuickStart.md** — 5-minute getting started guide
- **make.py source** — Command-line reference implementation
- **Gramps Wiki** — Developer documentation

---

**Questions or Suggestions?**

If you need a `make.py` feature in the GUI, please discuss on Gramps Discourse forums!
