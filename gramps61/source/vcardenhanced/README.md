# vcardenhanced — Multi-version vCard Import/Export for Gramps

**Addon type:** Fork-and-Hide workaround (GEPS 048, Workaround A)
**vCard versions supported:** 1.0, 2.1, 3.0, 4.0
**Status:** Experimental / proof-of-concept

---

## What this addon does

Replaces the built-in Gramps vCard importer and exporter with dialect-aware versions that handle vCard versions 1.0, 2.1, 3.0, and 4.0. Unhandled vCard properties are preserved (not silently dropped) as Person attributes of type `vCard <version> source`. A Variant Call Format (VCF) DNA file is detected on the first line and rejected with a clear alert rather than a confusing parse error. ORG vCards without Names are imported as Surnames.

The exporter adds a version selector to the export wizard (default: 3.0).

---

## Installation

1. Copy the four files into a single addon directory inside your Gramps user data folder, e.g.:
   `~/.gramps/gramps60/plugins/vcardenhanced/`

   Files:
   - `vcardenhanced.gpr.py`
   - `importvcard_enh.py`
   - `exportvcard_enh.py`
   - `README.md`

2. Restart Gramps.

3. The addon attempts to automatically hide the built-in vCard plugins on startup (see Hurdle 4 below). The automatic hide does not work yet in your Gramps version:
   - Open **Help → Plugin Manager** Enhanced
   - Search `vCard` (the built-in import) and `vCard` (the built-in export) and set them to **Hidden**
   - The addon versions are named **vCard (Enhanced — v1/2.1/3.0/4.0)**

---

## Fork/Hide Workaround — Hurdles Encountered

This addon is a structured experiment in the GEPS 048 "Workaround A:Fork-and-Hide" approach. The following problems were discovered during development and are documented here as input to the full GEPS 048 implementation.

### Hurdle 1 — Duplicate plugin IDs cause silent failures

**Problem:** The built-in vCard plugins use the IDs `im_vcard` and `ex_vcard`. Reusing these IDs in an addon causes Gramps to raise a duplicate-plugin registration error. This error is **not clearly reported to the user** — depending on the Gramps version, the startup log either silently drops one of the registrations or produces a traceback that doesn't identify which plugin caused it.

**Workaround:** This addon uses distinct IDs: `im_vcard_f` ('f' for "fork") and `ex_vcard_f`. This means both the built-in and the enhanced versions are registered simultaneously, creating a duplicate-entry problem in the import/export dialog (see Hurdle 4).

**GEPS 048 implication:** The framework needs a first-class "supersedes" or "replaces" registration field so addon authors can explicitly declare that their plugin replaces a built-in, and the framework can handle deduplication automatically.

---

### Hurdle 2 — Built-in .gpr.py is amalgamated; no standalone file to copy

**Problem:** The built-in importer and exporter plugins are registered in a shared `gramps/plugins/lib/...gpr.py` file (or similar amalgamated file) alongside many other plugins. There is no standalone `vcard.gpr.py` to simply copy and modify. An addon author who doesn't know where to look has no obvious path to find the registration parameters needed to construct a fork.

**Additional problem:** If `fname=` in a `.gpr.py` points to a file that doesn't exist, Gramps silently skips the plugin at startup with no user-visible error and no log message at the default log level. This makes typos in `fname=` very hard to diagnose.

**Workaround:** The addon's `.gpr.py` was written from scratch, using the built-in plugin's parameters as reference. The `fname=` values were verified by confirming that both `.py` files exist in the addon directory before testing.

**GEPS 048 implication:** The framework should emit a warning (at least
at DEBUG level) when a registered `fname=` cannot be found. Ideally,
the Plugin Manager UI would show "file missing" next to the plugin name.

---

### Hurdle 3 — Import paths differ between core plugins and addons

**Problem:** Core Gramps plugins import from relative paths or from `gramps.plugins.lib` directly. Addon plugins live in the user data directory, outside the Gramps package tree, and must use fully qualified `gramps.*` import paths. Copying a core plugin file and adjusting only the registration is not sufficient — imports also need updating.

Additionally, the built-in `importvcard.py` uses `OpenFileOrStdin` without specifying `encoding=`, which works for core because it falls back to the system default. In the enhanced version, explicit `encoding="utf-8", errors="replace"` is necessary to handle multi-version input gracefully.

**Workaround:** This addon is self-contained — no shared modules from core are monkey-patched or subclassed. All imports use fully qualified Gramps package paths.

**GEPS 048 implication:** The fork-and-hide workaround guide (in GEPS 048's Workaround A section) should include a checklist of import path differences as a known friction point.

---

### Hurdle 4 — Hiding the built-in has no stable API

**Problem:** To eliminate the duplicate-entry problem in the import/export dialog (both built-in and enhanced showing up for `.vcf` files), the built-in plugins must be hidden. The `.gpr.py` includes a best-effort automatic hide using `PluginRegister`. However:

- The API for reading and writing the hidden-plugin set   (`get_hidden_plugin_ids` / `save_hidden_plugin_ids`) is not part of   the documented Gramps plugin API and may not exist in all versions.
- The hidden-plugin list is managed by Plugin Manager Enhanced, which   stores it in a user config file. The attribute names on `PluginRegister` differ between Gramps versions.
- If the automatic hide fails, it fails **silently** — there is no   feedback to the user that manual hiding is required.

**Workaround:** The `_auto_hide_upstream()` function in `.gpr.py` tries two known attribute names (`get_hidden_plugin_ids` and `_hidden`) and swallows all exceptions. The README instructs users to hide manually if the automatic hide does not work.

**GEPS 048 implication:** A stable, version-independent API for hiding a plugin by ID is essential for any fork-and-hide approach to be reliable. This should be part of the core plugin registration system, not a side-effect dependency on Plugin Manager Enhanced.

---

### Hurdle 5 — No "toggle active fork" UI in core

**Problem:** Once both the built-in and the enhanced plugin are registered, and one is hidden, there is no built-in Gramps UI for the user to toggle which one is active. This requires either Plugin Manager Enhanced (a separate addon) or manual config-file editing.

**Workaround:** The README documents the manual procedure. A future version of the exporter option box could include a "Restore built-in" button that calls the toggle pattern described in GEPS 048.

---

## vCard Version Notes

| Version | Standard | Notes |
|---------|----------|-------|
| 1.0 | Versit 1995 | Rarely encountered; tab-folding; QUOTED-PRINTABLE common |
| 2.1 | Versit 1996 | Widely supported; used by Outlook, older phones; QP encoding |
| 3.0 | RFC 2426 (1998) | Gramps default; space-folding; UTF-8 |
| 4.0 | RFC 6350 (2011) | Modern standard; GENDER, ANNIVERSARY, CLIENTPIDMAP |

Properties not handled by the importer are stored as a `vCard <n> source` Person attribute (where `<n>` is the detected version), so data is preserved for manual review or future processing.

---

## Variant Call Format (DNA) Detection

`.vcf` is shared between vCard (contact data) and Variant Call Format (genomic/DNA data). VCF DNA files begin with `##fileformat=VCFv`. This addon reads the first 32 bytes of any `.vcf` file before attempting to parse it as a vCard. If the DNA magic bytes are detected, import is aborted and an alert is shown.

---

## Credits

- Original vCard import/export: Martin Hawlisch, Donald N. Allingham, Brian G. Matherly, Jakim Friant, Michiel D. Nauta (Gramps project)
- Export option box pattern: Kari Kujansuu (isotammiexportxml)
- Enhanced multi-version fork: Claude (Anthropic, claude-sonnet-4-6),   GEPS 048 experiment, 2026-03-21
- Human author / tester: Brian McCullough (emyoulation), Gramps project
