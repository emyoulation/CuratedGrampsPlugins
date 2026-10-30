# AddonPackShip vs. upstream make.py — comparison & roadmap

**Supersedes:** `COMPARE_make_APS_original.md` (Document Version 2.0,
February 2026). That draft's architecture description and Integration
Plan predate the in-process refactor and the discovery of two real
behavioral hazards described below; this revision corrects both while
keeping the parts of the original's structure that still hold up well
(the audience-facing "which tool for which task" guidance and feature
matrix in particular).
**Status:** current as of the `make_addon.py` in-process refactor,
session-logging feature, and upstream `make.py` patch proposal.

---

## 1. Overview

AddonPackShip (APS) ships with **three Python packaging scripts**:

| File | Origin | Purpose |
|------|--------|---------|
| `make52.py` | Gramps project (verbatim copy, refreshed via "Update make.py Scripts") | Reference implementation for Gramps 5.2 addons |
| `make60.py` | Gramps project (verbatim copy) | Reference implementation for Gramps 6.0 addons; adds `aggregate-pot` and `extract-po` |
| `make61.py` | Gramps project (verbatim copy) | Reference implementation for Gramps 6.1 addons |
| `make_addon.py` | AddonPackShip-specific | Packaging engine used by both the GUI (in-process) and standalone from a terminal |

All four handle overlapping operations, but differ in interface, scope,
and — for three of the four core commands — real behavior.

---

## 2. make52.py / make60.py / make61.py — the standard scripts

### What they are

The official Gramps project packaging scripts, fetched verbatim from
`gramps-project/addons-source` (one `make.py` per maintenance branch;
APS renames each locally so multiple versions can sit side by side).
Command-line tools designed to run from a working directory where
addon folders and the version's output folder are siblings.

### How they work

```bash
python3 make61.py gramps61 build MyAddon
python3 make61.py gramps61 listing all
python3 make61.py gramps61 compile MyAddon
```

- **Relative directory layout assumed**: addon folders and
  `../addons/<version>/` are expected as siblings of the working
  directory.
- **`GRAMPSPATH` via environment**: needed to import Gramps modules
  (for `listing`/`init`/`update`/`as-needed`/`check`). Falls back to
  `../../..`, which only works from inside a standard Gramps addons
  checkout.
- **Single build mode**: no beta/release distinction — `build`
  includes whatever matches the fixed file patterns plus `MANIFEST`,
  always, and always bumps the addon's version (see §4).
- **`os.system()`/shell strings** throughout for external commands
  (`msgfmt`, `xgettext`, `msgmerge`, `msginit`).

### Differences between the three

Verified directly against the current `maintenance/gramps52`,
`gramps60`, and `gramps61` branches: **`do_tar()`, `cleanup()`, and
`increment_target()` — the functions this document's hazard analysis
in §4 is about — are byte-for-byte identical across all three.**
`make60.py`/`make61.py` add `aggregate-pot` and `extract-po` (not in
`make52.py`) and have been refactored to call shared
`build_addon()`/`compile_addon()` functions from their command
dispatch, where `make52.py` still inlines the same logic. That's a
code-organization difference only — behavior is the same either way,
since both paths call the same `do_tar()`/`cleanup()`.

**Which to use?** Whichever matches the Gramps version you're
targeting. Use `make60.py`/`make61.py` if you need the
`aggregate-pot`/`extract-po` translation-coordination workflow.

---

## 3. make_addon.py — APS's packaging engine

### What it is

`make_addon.py` is bundled and distributed with AddonPackShip, and is
a **fully supported, independently tested tool in its own right** (33
unit tests as of this writing) — not a subprocess-only internal
worker. It's used two ways:

- **In-process**, imported directly by `AddonPackShip.py` and called
  via its `run_command()` function — no subprocess involved for
  `build`/`compile`/`clean`, and no subprocess at all unless `listing`
  delegates to a bundled `make<NN>.py` (see §3.2).
- **Standalone from a terminal**: `python3 make_addon.py <command>
  <addon_path> <output_dir>`, with `BUILD_MODE`/`ADDON_LANGUAGES`
  environment variables — fully independent of the GUI.

### How it differs from make52/60/61

| Aspect | make52/60/61 | make_addon.py |
|---|---|---|
| Invocation | CLI only | In-process import (GUI) *or* CLI (standalone) |
| Path model | Relative, assumes sibling layout | Absolute paths, explicit arguments |
| Gramps import | `GRAMPSPATH` env var | Already running inside the same process as Gramps when called from the GUI — no import mechanism needed. (`GRAMPS_PYTHONPATH` still exists but is now vestigial, kept only for standalone-CLI use.) |
| Build modes | Single mode | β Beta and Δ Release, via `build_mode` parameter (CLI: `BUILD_MODE` env var) |
| File selection | `MANIFEST` only | Dual-mode auto-include logic + `MANIFEST`/`MANIFEST.beta` |
| `.po` naming | `*-local.po` pattern only | **`*-local.po` pattern only** — same convention, not more flexible |
| Version bump on build | **Always** (`increment_target()`) | Never |
| Locale wipe on clean | **Always** (`shutil.rmtree(locale/)`) | Never |
| Subprocess/interpreter use | N/A (this *is* the subprocess target) | None at all for `build`/`compile`/`clean`; for `listing`'s upstream delegation, a validated interpreter check (rejects the Windows Store's non-functional `python` alias) plus after-the-fact artifact verification, rather than trusting `sys.executable`/exit-code alone |
| `init` / `update` | ✅ | ✅ in the GUI, as **Edit translation…** (`prepare_template()` + `prepare_local_po()`: msginit for a new `<lang>-local.po`, msgmerge for an existing one); no CLI command |
| `aggregate-pot` / `extract-po` | ✅ (make60/61 only) | ❌ (see §7) |

### Why a separate file — the real reason

The original rationale for this split (absolute paths vs. relative,
live `sys.path` vs. `GRAMPSPATH`) no longer holds: those were solved
by running in-process, not by maintaining a parallel implementation.
The reason `build`/`compile`/`clean` are still not delegated is two
concrete, verified behavioral hazards, not a path/environment
mismatch — see §4.

---

## 4. Why build/compile/clean aren't delegated — verified hazards

Traced directly against the real `make.py` source, not assumed:

### `build`

| | Upstream `make.py` | `make_addon.py` |
|---|---|---|
| Version bump | **Always bumps** patch version in `.gpr.py` (`increment_target()`, called from `do_tar()`, on *every* run) | Never touches version |
| `setup.py` (compiled extensions) | Delegates to `python3 setup.py --build` | **Not supported** — a compiled-extension addon is silently missed |
| Root `*.txt` files | Always included | Not included unless caught by a `MANIFEST` entry |
| Beta/release modes | No such concept | Two modes; extra `MANIFEST.beta`/po/`template.pot`/subdirectory logic |
| tar entry ownership | Normalized to `uname=gname='gramps'` | OS default (cosmetic) |
| `MANIFEST` semantics | One flat pattern list, always additive | `MANIFEST.beta` *replaces* auto-extras in beta mode; `MANIFEST` additive in both — more flexible, but different |

### `compile`

Functionally close — both run `msgfmt <po> -o
locale/<lang>/LC_MESSAGES/addon.mo` per translation file. The real
difference: `make_addon.py` also auto-creates `po/` and generates
`template.pot` via `xgettext` if missing (upstream keeps that in
`init`). Convenience, not a hazard — this is the one command where
full delegation was always safe, and its lack of delegation is really
just about avoiding subprocess/staging overhead for something simple.

### `clean`

Deliberately narrower by design:

- Upstream's `cleanup()` **wipes `locale/` entirely** (every compiled
  translation, every language) plus removes legacy po-file patterns
  (`*-global.po`, `*-temp.po`, `??.po`, `?????.po`) `make_addon.py`
  doesn't touch.
- `make_addon.py` only removes `__pycache__/`, `.pyc`/`.pyo`, and
  backup files — **never `locale/`** — so translations survive
  between test runs.

### `listing`

Genuinely delegated when a `make<NN>.py` is bundled — no divergence
to document there, since that command actually executes the upstream
code. Bundled English-only fallback (`create_listing()`) otherwise.

---

## 5. Feature availability matrix

| Feature | make52/60/61 CLI | AddonPackShip GUI | `make_addon.py` CLI |
|---|---|---|---|
| Build package | ✅ | ✅ | ✅ |
| Compile translations | ✅ | ✅ | ✅ |
| Generate/amend listings | ✅ | ✅ | ✅ (delegates when possible) |
| Pack and Ship (build + listing) | Manual, two commands | ✅ one-button | — |
| β Beta / Δ Release build modes | ❌ | ✅ | ✅ |
| MANIFEST editor | Manual | ✅ per-addon | — |
| Auto-generate `template.pot` | ❌ (separate `init` step) | ✅ (part of `compile`) | ✅ |
| Init translation bootstrap (`template.pot` + first `<lang>-local.po`) | ✅ `init` | ✅ **Edit translation…** | ❌ |
| Update `.po` from `.pot` | ✅ `update` | ✅ **Edit translation…** | ❌ |
| Build as-needed (whole-repo incremental) | ✅ `as-needed` | ❌ | ❌ |
| Manifest content validation | ✅ `manifest-check` | ❌ | ❌ |
| Unlist an addon | ✅ `unlist` (removes just that addon from every listing) | ❌ — **no safe equivalent**; deleting `listings/` would remove every addon's listing, not just one | ❌ |
| Version-vs-listing consistency check | ✅ `check` | ❌ | ❌ |
| Aggregate POT files | ✅ `aggregate-pot` (make60/61 only) | ❌ | ❌ |
| Extract PO translations | ✅ `extract-po` (make60/61 only) | ❌ | ❌ |
| Run the unit tests of the repository | ✅ `test` (make60 only) | ❌ | ❌ |
| Create a brand-new addon's initial skeleton (`.gpr.py`, source stub) | ❌ — **no tool does this today**, including `init` (which only bootstraps translations for an addon that already exists) | ❌ | ❌ |

---

### Coverage summary
`make60.py`, the build script in the Gramps 6.0 branch of `addons-source`, has 13 commands. AddonPackShip covers 6 of them, a little under half (46%): `build`, `compile`, `listing`, `clean`, `init` and `update` (the last two as **Edit translation…**). These are all of the commands used to package and translate one addon. Within them, the known gaps are compiled-extension addons (`setup.py`) and root `*.txt` files, which `build` includes by default; both are rare. The version bump of `build` and the `locale/` wipe of `clean` are left out on purpose (see §4).

The 7 commands not covered are `as-needed`, `manifest-check`, `unlist`, `check`, `aggregate-pot`, `extract-po` and `test`. Except for `unlist`, they are maintenance tasks for the whole `addons-source` repository rather than for one addon.

Other branches have slightly different command sets. `make61.py` has 12 (no `test`), so the same 6 are 50%. `make52.py` has 9: `compile` is part of its `build`, and it has no `aggregate-pot`, `extract-po` or `test`; AddonPackShip covers 5 of those 9, about 56%.

## 6. Workflow recommendations

### For individual addon developers

Use **AddonPackShip** for day-to-day packaging, beta/release builds,
compiling translations, and MANIFEST editing.

Use the standard **make.py** for `as-needed`, `unlist` and `check`
until §7's planned tabs cover them. (`init` and `update` are now
covered by **Edit translation…**.)

### For Gramps project maintainers

Use **AddonPackShip** for quick test builds and reviewing individual
addons.

Use the standard **make60.py**/**make61.py** for whole-repo `build
all`, translation aggregation (`aggregate-pot`/`extract-po`),
incremental builds (`as-needed`), and structural validation
(`check`/`manifest-check`).

---

## 7. Roadmap: planned tabs and what they'd build on

### 7.1 Locale / translator tab

`init` and `update` are now covered in-process by **Edit
translation…** (see §5). `aggregate-pot` and `extract-po` remain;
they are the translator workflow of the whole repository, and none carry §4's hazards — they don't touch version
numbers or delete compiled artifacts. Good candidates for **direct
delegation** to `make<NN>.py` from day one, the same way `listing`
already works, rather than needing in-process reimplementation first
— though each should get the same "trace the real source before
trusting it" treatment §4 gave `build`/`clean`.

### 7.2 Addon lifecycle tab (spawning / sunsetting)

- **Sunsetting**: `unlist` directly covers the listing half in one
  step. Full sunsetting (archiving source, marking deprecated status)
  goes beyond any current tool and needs new design.
- **Spawning**: genuinely new territory — see the last row of §5.
  Neither `init` nor anything else creates an addon's initial
  `.gpr.py`/source skeleton.

### 7.3 Limited Python shell for CLI-only features

Natural home for `as-needed`, `manifest-check`, `check` — batch/
maintenance commands that don't map onto a single-addon GUI workflow.
Two design notes carried forward from this project's own history:

1. **Run it in-process, not as a subprocess.** `eval.py` and
   `PythonGramplet.py` (core Gramps) and the `GrampyScript` addon all
   implement "run Python from a Gramps GUI" via `exec()`/`eval()`
   directly in the running interpreter — no subprocess, no
   interpreter-discovery problem. `make_addon.py`'s own refactor took
   the same direction for the same reasons (see §3's Windows
   `cx_Freeze`/Store-alias history). A shell tab should follow that
   precedent.
2. **`as-needed` and `check` are `sys.argv`-shaped, not
   function-call-shaped** — they run as top-level script code driven
   by positional arguments, not cleanly callable functions. Wrapping
   them safely means either an upstream patch (same category as §8)
   or a scoped subprocess call with the same interpreter-validation
   and artifact-verification safeguards already built for `listing`.

---

## 8. Upstream patch proposal status

Two opt-in environment-variable flags — `MAKE_PY_NO_VERSION_BUMP`
(skip `build`'s version bump) and `MAKE_PY_KEEP_LOCALE` (skip
`clean`'s locale wipe) — drafted and functionally verified against
fresh copies of the current `make.py` from all three maintenance
branches (one patch covers all three; the affected functions are
identical across them). Handed off for submission by a contributor
experienced with the project's review process.

**Assume roughly a year before this lands**, per typical Gramps
project review lead time. Until then, `make_addon.py` remains the
supported implementation for `build`/`compile`/`clean` — this is the
correction to the original document's Integration Plan, which assumed
a phased migration to the standard scripts was straightforwardly safe
without having traced `do_tar()`/`cleanup()` against the real source.
It wasn't: delegating `build` today would silently bump every test
build's version number, and delegating `clean` today would silently
delete every compiled translation. Once (if) the patch lands,
re-evaluate delegating `build`/`clean` using the new flags for
iterative use, leaving them unset for actual release builds — the
same split `listing` already demonstrates works.

See `PR_DESCRIPTION.md` and the accompanying `.patch` files for the
full proposal.

---

## 9. Session log ("teaching" transcript)

Every GUI action writes to `logs/<session_id>.log`, stored next to
`make_addon.py` itself — a fixed, discoverable location regardless of
where a given run's output is redirected. `session_id` is a timestamp
set once when the tool window opens. As of 1.9.7, a 📁 icon next to
**Pack and Ship** opens this folder directly in the OS file browser —
shown only once this session has actually written its own log entry,
not merely because logs exist from an earlier day.

**Design principle:** the primary, copy-pasteable line is always the
command that actually ran — the `make_addon.py` form for
`build`/`compile`/`clean` (accurate, and stable for as long as §8 is
pending), whichever of the real `make<NN>.py` or the bundled fallback
genuinely executed for `listing`. When a `make<NN>.py` happens to be
bundled for `build`/`compile`/`clean` too, its rough equivalent is
shown as a secondary "FYI" note, explicitly flagged as not a drop-in
substitute, with the specific difference (version bump, locale wipe,
or missing auto-`template.pot`) spelled out — never presented as
interchangeable.

Non-English listing generation is currently disabled (pruned as a
final step, not removed from the underlying code) while an unrelated
Windows-specific listing bug was tracked down; re-enabling it is a
one-line flag flip (`ENABLE_NON_ENGLISH_LISTINGS` in `make_addon.py`).

---

*Consolidates `COMPARE_make_APS_original.md` (February 2026) with
analysis from this project's development conversation. Drafted by
Claude (Anthropic; model: Claude Sonnet 5) at the AddonPackShip
maintainer's request and reviewed by the maintainer before use.*
*Generated-by: Claude Sonnet 5, Anthropic, via claude.ai*
