# The Three make*.py Files — Differences and Integration Plan

**Document Version**: 2.0  
**Date**: February 2026  
**AddonPackShip Version**: 1.8.3

---

## Overview

AddonPackShip ships with **three Python packaging scripts**:

| File | Origin | Purpose |
|------|--------|---------|
| `make52.py` | Gramps project (verbatim copy) | Reference implementation for Gramps 5.2 addons |
| `make60.py` | Gramps project (verbatim copy) | Reference implementation for Gramps 6.0 addons, adds `aggregate-pot` and `extract-po` |
| `make_addon.py` | AddonPackShip-specific | Subprocess worker called by the GUI; implements β/Δ build modes and per-addon operations |

All three handle the same core operations (build, compile, listing, clean), but they differ significantly in interface, scope, and capabilities.

---

## make52.py and make60.py — The Standard Scripts

### What They Are

`make52.py` and `make60.py` are the **official Gramps project packaging scripts**, copied verbatim from the Gramps addons repository. They are command-line tools designed to be run from a working directory that contains all addon folders side-by-side.

### How They Work

Both scripts are invoked from the command line with a fixed argument pattern:

```bash
python3 make52.py gramps52 build MyAddon
python3 make52.py gramps52 listing all
python3 make52.py gramps52 compile MyAddon
```

Key behaviours:

- **Relative directory layout assumed**: The script expects to be run from a directory where addon folders and the `gramps52/` output folder are siblings. Paths like `../download/` are hardcoded relative to the working directory.
- **GRAMPSPATH via environment**: To import Gramps modules (needed for listing), set `GRAMPSPATH` to point to the Gramps source tree. Without it, the script falls back to `../../..` which only works in the standard Gramps addons checkout.
- **Single build mode**: No concept of β vs Δ — builds include whatever files match the MANIFEST/auto-include rules, always.
- **`build all`** iterates every subdirectory that contains a `.gpr.py` file.
- **os.system() for external commands**: Uses `os.system()` and shell strings with `%`-style interpolation throughout, which can be fragile on Windows.

### Differences Between make52.py and make60.py

`make60.py` is a superset of `make52.py`. The only additions are:

- **`aggregate-pot`** command — merges all `template.pot` files from every addon into a single `po/addons.pot`, filtering out strings already present in the core `gramps.pot`. Used for Gramps project-wide translation coordination.
- **`extract-po`** command — the reverse: distributes translations from an aggregated `po/{lang}.po` back into per-addon `{lang}-local.po` files.
- **`subprocess.Popen`** imported (used internally by make60.py for some operations).

Otherwise the two files are functionally identical.

**Which to use?** Use `make52.py` for Gramps 5.2 addon development. Use `make60.py` if you are contributing to the Gramps 6.0 addon ecosystem or need the aggregate/extract translation workflow.

---

## make_addon.py — The AddonPackShip Worker

### What It Is

`make_addon.py` is a **subprocess worker** written specifically for AddonPackShip. It is never run directly by the user — `AddonPackShip.py` (the GUI) launches it via `subprocess.run()` with arguments and environment variables.

### How It Differs from make52/make60

| Aspect | make52/make60 | make_addon.py |
|--------|--------------|---------------|
| **Invocation** | CLI by user | Subprocess called by GUI |
| **Path model** | Relative, assumes sibling layout | Absolute paths passed as arguments |
| **Gramps import** | Via GRAMPSPATH env var | Via GRAMPS_PYTHONPATH env var (injected by parent process) |
| **Build modes** | Single mode | β Beta and Δ Release via BUILD_MODE env var |
| **File selection** | MANIFEST only | Dual-mode auto-include logic + MANIFEST/MANIFEST.beta |
| **`.po` naming** | `*-local.po` pattern only | Any `*.po` pattern (flexible naming) |
| **Output dir** | Relative `../download/` | Absolute path passed as argument |
| **Error reporting** | Printed to stdout | Captured stdout/stderr returned to GUI |
| **Windows compat** | Uses `os.system()` with shell | Uses `subprocess.run()` and `sys.executable` |
| **aggregate-pot** | ✅ (make60 only) | ❌ |
| **extract-po** | ✅ (make60 only) | ❌ |
| **init / update** | ✅ | ❌ |

### Why a Separate File?

The GUI needs to call packaging operations **from within a running Gramps session**, on **absolute paths** to individually installed addons, passing **live Gramps sys.path** to the subprocess. The standard scripts' assumptions (relative paths, GRAMPSPATH, single build mode) are incompatible with this use case. Rather than monkeypatching the standard scripts, AddonPackShip uses its own focused implementation.

---

## Feature Availability Matrix

| Feature | make52/60 CLI | AddonPackShip GUI |
|---------|--------------|-------------------|
| Build package | ✅ | ✅ Build Selected |
| Build all addons | ✅ `build all` | ✅ Select All + Build |
| Compile translations | ✅ | ✅ Compile Translations |
| Generate/amend listings | ✅ | ✅ Amend Listings |
| Pack and Ship (build + listing) | Manual | ✅ One-button workflow |
| β Beta build mode | ❌ | ✅ |
| Δ Release build mode | ❌ | ✅ |
| MANIFEST editor | Manual | ✅ Per-addon 📂 button |
| Auto-generate template.pot | ❌ | ✅ |
| Flexible .po naming | ❌ | ✅ |
| Init addon structure | ✅ | ❌ Use make52.py |
| Init translation file | ✅ | ❌ Use make52.py |
| Update .po from .pot | ✅ | ❌ Use `msgmerge` |
| Build as-needed (incremental) | ✅ | ❌ |
| Manifest validation | ✅ | ❌ |
| Unlist addon | ✅ | ❌ Delete listings/ folder |
| Check addon structure | ✅ | ❌ |
| Aggregate POT files | ✅ (make60 only) | ❌ |
| Extract PO translations | ✅ (make60 only) | ❌ |

---

## Workflow Recommendations

### For Individual Addon Developers

Use **AddonPackShip** for:
- Day-to-day packaging and rebuilding
- Beta and release packaging
- Compiling translations
- Creating and editing MANIFEST files

Use **make52.py** for:
- Initial addon setup (`init`)
- Updating translation files (`update`)
- Batch/incremental builds across many addons (`as-needed`)

### For Gramps Project Maintainers

Use **AddonPackShip** for:
- Quick test builds during review
- Checking individual addons

Use **make60.py** for:
- Batch building all addons (`build all`)
- Translation aggregation (`aggregate-pot`, `extract-po`)
- Incremental builds (`as-needed`)
- Structural validation (`check`, `manifest-check`)

---

## Integration Plan: Adopting the Standard make__.py

A future enhancement would allow AddonPackShip to **call the standard make52.py/make60.py directly** for operations it currently duplicates, while using `make_addon.py` only for features incompatible with the standard scripts.

### Why Bother?

- Reduces maintenance burden (no parallel implementation of build/compile/listing)
- Automatically picks up upstream fixes and new features
- Keeps AddonPackShip aligned with the Gramps project toolchain

### Incompatibilities to Resolve

Before make52.py can be used as a drop-in backend, several incompatibilities must be addressed:

| Incompatibility | Description | Resolution |
|-----------------|-------------|-----------|
| **Relative path model** | make52.py expects to be run from a directory where addons are siblings | Pass absolute paths via env vars or a thin wrapper that `chdir`s appropriately |
| **GRAMPSPATH vs live sys.path** | make52.py uses `GRAMPSPATH` to locate Gramps; the GUI has a live Python session | Set both `GRAMPSPATH` and `PYTHONPATH` from the GUI's `sys.path` before invoking |
| **No β/Δ build modes** | make52.py has a single build mode | Implement as a pre-processing step: generate a temporary MANIFEST from β/Δ rules, then call `make52.py build` with that MANIFEST |
| **`*-local.po` naming only** | make52.py's `compile` expects `po/*-local.po` | Pre-rename or symlink flexible-named `.po` files before calling compile, then restore |
| **Output path hardcoded** | `../download/` is relative to working dir | Set working directory correctly before calling |
| **`os.system()` on Windows** | make52.py uses shell-string commands | No change needed if `subprocess` wrapping handles the `chdir`; otherwise requires patching |

### Proposed Architecture

```
AddonPackShip.py (GUI)
    │
    ├─── make_addon.py (auxiliary, for β/Δ mode logic only)
    │         Handles: β/Δ file selection, flexible .po naming,
    │                  MANIFEST.beta creation, template.pot generation
    │         Returns: a standard MANIFEST + normalized po/ directory
    │
    └─── make52.py / make60.py (standard, for build/compile/listing)
              Called via subprocess with:
              - Correct working directory (chdir to addon parent)
              - GRAMPSPATH pointing to Gramps installation
              - Standard argument format: gramps52 build AddonName
```

Under this architecture, `make_addon.py` becomes a **pre-processor** that translates AddonPackShip's richer options into inputs that the standard script understands. The actual packaging work (tarball creation, JSON generation) moves back to the authoritative implementation.

### Migration Steps

1. **Phase 1** (current): `make_addon.py` handles everything. Easiest to maintain.
2. **Phase 2**: Extract β/Δ file-selection logic into `make_addon.py`; delegate `build` (tarball creation) to make52.py via subprocess.
3. **Phase 3**: Delegate `compile` to make52.py (after normalising `.po` file names).
4. **Phase 4**: Delegate `listing` to make52.py (after confirming GRAMPSPATH injection works reliably across platforms).
5. **Phase 5**: `make_addon.py` is reduced to β/Δ pre-processing only; all build/compile/listing operations use the standard script.

---

## Summary

**make52.py** and **make60.py** are the canonical Gramps packaging tools — run them from the command line when you need operations not yet in the GUI (init, update, as-needed, aggregate-pot).

**make_addon.py** is AddonPackShip's internal worker — it provides the β/Δ modes, flexible `.po` naming, and per-addon absolute-path operations that the standard scripts don't support.

The long-term plan is for `make_addon.py` to shrink into a thin pre-processor, with the standard scripts doing the heavy lifting.

---

**Questions or suggestions?**  
Discuss on Gramps Discourse forums or open an issue on GitHub.
