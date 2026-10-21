# Change log (AddonPackShip — Gramps Addon Packaging Tool)
[**QuickStart.md**](QuickStart.md) ● [**README.md**](README.md) ● [**Change Log**](CHANGELOG.md)

## 1.9.16 (in progress)

- **Fixed stale entries in the Gramps 5.2 listing.** The bundled `make52.py` still has the old upstream single-addon `listing` merge: it inserts the new entry before the first existing line whose `(t, i)` sorts after it, and keeps the addon's old line. AddonPackShip's dedupe then kept the *last* duplicate — the old one — so an addon could be listed at its previous version in `gramps52/listings/addons-en.json` (e.g. Photo Tagging 1.1.3 instead of 1.2.4) while 5.2's `.addon.tgz` and the 6.0/6.1 listings were correct. Success was judged only by `addons-en.json` existing, so nothing reported it. `make60.py`/`make61.py` were not affected.
- New listing check and repair (`_reconcile_listing_with_gpr()` in `make_addon.py`): after every listing run, whichever generator produced it, each `addons-<lang>.json` is compared with what the addon's `.gpr.py` registers now. Missing, stale or duplicated entries for that addon are replaced with the current ones, and a `Repaired addons-en.json: was [...], now [...]` line appears in the results. Files that already match are not rewritten. Extra fields an upstream script adds (e.g. `make61.py`'s `do`) are kept. The bundled `make52.py` is left matching upstream, so **Update Scripts…** never overwrites a local patch.
- When a listing file still contains duplicates of one plugin, the dedupe now keeps the entry with the highest version, not the last one in the file.
- Listing files are now sorted by `n` — the name the Addon Manager shows — case-insensitively, so a listing can be read in the same order as the GUI. They were previously sorted by `z` (package file name). Expect a one-time reordering diff in each `addons-<lang>.json` the next time it is listed.
- **Progress window for long operations.** **Pack and Ship**, **Build Selected**, **Compile Translations**, **Amend Listings** and **Clean** now show Gramps' standard progress window, naming each step (e.g. "Listing PhotoTaggingGramplet for gramps52") with a bar that advances per build and per listing. Previously the window froze until the whole run finished, long enough for the desktop to offer to force-quit Gramps as "not responding".
- The window also keeps redrawing *during* each step: `make_addon.run_command()` accepts a new optional `wait_callback`, and every child process (`msgfmt`, the interpreter check, `make<NN>.py`) is now waited on in short slices that call it. The command-line `make_addon.py` is unchanged.
- The standalone Python interpreter used for upstream `make<NN>.py` listings is now found and checked once per Gramps session, instead of on every listing for every version — roughly halving the number of slow child processes in a multi-version Pack and Ship.

## 1.9.14 (2026-09)

- `check_gpr_version_coverage()` now tells a genuine version-range gate in an addon's `.gpr.py` apart from no gate at all (the common case): a sentinel probe with an implausible version checks whether `register()` fires unconditionally. When it does, every version's coverage now reports as unverified rather than falsely "confirmed compatible" — an addon with no gate never actually claimed compatibility with anything, positive or negative.
- Multi-version builds now show an explicit note when a target version's compatibility was never verified this way, instead of duplicating the package as silently as a confirmed-compatible one.

## 1.9.12 (2026-09)

- `run_upstream_command()`'s interpreter check now actually validates that a candidate Python can import Gramps from the resolved `GRAMPSPATH` (the same imports upstream `make.py`'s own `listing` command needs), instead of only checking that it can run Python at all — catching a version-mismatched system interpreter (e.g. a system `python3` different from the Python version a given Gramps installation's own tree was built for) before wasting a subprocess call on it.
- A version-specific interpreter name (e.g. `python3.13`, parsed from the resolved `GRAMPSPATH`) is now tried ahead of the generic `python3`/`python` on `PATH`, in case a matching interpreter happens to be available.
- When upstream `make.py` reports success (exit 0) but never actually produces a listing — the same silent-failure class the interpreter check above targets — this is now treated as "delegation could not be attempted" and falls back to the bundled English-only listing generator, instead of reporting a hard failure that produces nothing. The real diagnostic is preserved as a note on the fallback's own log entry rather than being lost.

## 1.9.11 (2026-09)

- Removed the 500-character truncation on the session log's failure-detail note for a failed `listing` delegation — a short cap had already once cut off the single most diagnostic detail (the actual resolved `GRAMPSPATH` value) in practice.

## 1.9.10 (2026-09)

- No functional changes. Version number incremented by AddonPackShip's own opt-in per-addon version-bump flag firing during a Pack and Ship run, rather than by a deliberate release.

## 1.9.9 (2026-09)

- Fixed "Pack and Ship" silently discarding build/listing failure details: `show_combined_results()` only ever showed ✓/✗, unlike the standalone Build/Listing buttons, which already showed a truncated error line. It now shows the same detail.
- The session log now includes the actual subprocess output when the upstream `listing` delegation fails, instead of only ever logging the fixed "not a drop-in substitute" explanatory note regardless of the real cause.

## 1.9.7 (2026-09)

- Session log folder icon added next to **📦 Pack and Ship** — opens `logs/` in the OS file browser. Shown only once this session's own log file exists, not merely because logs exist from an earlier day.

## 1.9.6 (2026-09)

- Fixed a crash in `listing`'s upstream delegation when no valid standalone Python interpreter could be found (frozen macOS `.app` / Windows AIO builds) — now caught and treated as "delegation unavailable," falling back to the bundled listing generator instead of taking down the whole Gramps session.
- `_find_real_python_executable()` now validates `sys.executable` directly instead of trusting it whenever `sys.frozen` is unset, since not every frozen packaging sets that flag.
- Removed the redundant `from gramps.gen.const import GRAMPS_LOCALE as glocale; _ = glocale.translation.gettext` from this tool's own `.gpr.py` — `_` is already provided by Gramps' plugin-loader exec namespace (per the `addons-source` project's registration-file convention).
- Added a version-compatibility guard for multi-version builds: before duplicating a built `.addon.tgz` into every checked Gramps Version's folder, checks whether the addon's own `.gpr.py` actually registers under each target version (re-evaluating its own version-range gate, if any) and skips — rather than silently shipping — versions it excludes. An override is available for confirmed-safe exceptions.

# Not Yet Implemented:

> From Claude 20260823 05:17 CT
> 
> Glad it's landing well — this has been a fun one to iterate on, and the design's ended up in a pretty good place: real delegation to upstream `make.py` for the parts that actually drift, your own bundled logic kept deliberately for the parts where you wanted manual control (versioning, translation cleanup), and now a proper settings story via `APS.ini` instead of leaning on Gramps' global config for something that's really per-tool state.
> 
> A few loose threads worth keeping in mind as you keep testing:
> 
> - The `git status`/`git diff` check from a few rounds back, if you haven't already confirmed it — worth double-checking once more now that the version-bump control exists, since that's the mechanism that actually produces a real content diff for GitHub Desktop to pick up.
> - The `gramps-preferences` and `folder-publicshare`/`color-select-symbolic` icon names are all assumptions about what's registered in your icon theme — if any of them render blank, that's a one-line fix, just let me know which.
> - The Markdown Dash / undocked README viewer is still just a documented `TODO` in `on_help_icon_clicked()` — (Claude continues: "happy to wire that up for real whenever that gramplet's API is something you can point me at.")

