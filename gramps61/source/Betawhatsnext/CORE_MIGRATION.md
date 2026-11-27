# What's Next? - Moving into Gramps core

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [CORE_MIGRATION.md](CORE_MIGRATION.md)

This document is for developers. It describes how the What's Next addon replaces the built-in gramplet today, how to move the addon code into Gramps core, where its settings file should go in core, and how to retire (archive) the addon when core catches up. The gramplet is likely to keep changing after that, so the last part describes how to bring the same "superseding addon" framework back for the next round.

## How the addon replaces the built-in gramplet
Gramps registers plugins in two passes (`CLIManager.do_reg_plugins()` in `gramps/cli/grampscli.py`): first the built-in plugins in `PLUGINS_DIR`, then the addons in `USER_PLUGINS`. In `PluginRegister.scan_dir()` (`gramps/gen/plug/_pluginreg.py`), a registration whose id is already known removes the earlier one. This is the same in 5.2, 6.0 and 6.1.

The addon registers with `id="What's Next"`, the id of the built-in gramplet, so it always wins. Three consequences follow:

- The version number does not decide which gramplet loads. An addon at version 0.0.1 would still replace a core gramplet at 9.0.0. The version only affects what the Addon Manager and Plugin Manager show.
- The version range `if` in `Betawhatsnext.gpr.py` is the only switch that turns the replacement off. Once core ships the improved gramplet, that range must stop short of that Gramps release, or the addon will hide the newer core code without any warning.
- Saved Dashboard and gramplet bar layouts refer to a gramplet by its id, so a layout that showed the built-in "What's Next?" shows the addon, and later shows the core version again, with no user action.

## What moves into core
The port is a replacement of one existing core file plus one registration entry. Paths are from the Gramps source tree.

| Addon file | Core destination | Notes |
|---|---|---|
| `Betawhatsnext.py` | `gramps/plugins/gramplet/whatsnext.py` | Replaces the existing file. The class is already named `WhatNextGramplet`, as in core. |
| `Betawhatsnext.gpr.py` | The "What's Next" entry in `gramps/plugins/gramplet/gramplet.gpr.py` | Update `version`, and `height` if 300 is kept. Keep `fname="whatsnext.py"`, `help_url=GRAMPLET_HELP` and `gramps_target_version=MODULE_VERSION`. Drop the version range `if`, `maintainers` and `authors_email`. |
| Settings (see the next section) | `gramps/gen/config.py` | The addon already uses these `gramps.ini` keys, registered at runtime. In core, move the `register()` calls to `gen/config.py` and drop `import_addon_ini()`. |
| `README.md` and `media/` | The What's Next section of the Gramps wiki manual (Gramplets page) | Core gramplets get their help from the wiki through `GRAMPLET_HELP`. |
| `CHANGELOG.md` | The commit message and the pull request description | Core does not keep per-plugin changelogs. |
| `po/template.pot` | None | `gramps/plugins/gramplet/whatsnext.py` is already listed in `po/POTFILES.in`, so new strings reach the core template automatically. |

Changes to make while porting:

- Remove the MarkdownUtils Help button block and the button bar. Core cannot import an addon, and core gramplets do not carry their own Help button. The detached gramplet window already has a Help button that opens `help_url`.
- Remove the hidden batch tag buttons (`SHOW_TAG_BUTTONS` and the three `cb_batch_*` callbacks), unless a better UI for them has been found by then. Reviewers will ask about dead code. The code stays available in the archived addon.
- Remove the `show_diagnostic` trace lines, or switch them to a module-level `LOG = logging.getLogger(__name__)` at debug level.
- Bring the file to the full `AGENTS.md` standard: type hints, Sphinx docstrings, Black, pylint, mypy, class header comments, the GPL header, and unit tests in `gramps/plugins/gramplet/test/whatsnext_test.py` (unittest, not pytest). The addon is in draft mode and has none of this yet.
- Raise the core version above every addon release. The addon is at 1.1.0, so core would become 1.2.0 or higher.
- Write the commit message in the Mantis format (summary line of 70 characters or less, a `fixes`/`resolves`/`references` line), with the AI disclosure that the Gramps contribution page requires (`Generated-by:` with the tool name, provider and version, and an indication of the prompts).

## Where the settings file goes
Up to version 1.1.0 (before release), the addon followed the Emyoulation pattern: a ConfigManager .ini next to the module (`register_manager("Betawhatsnext", use_plugins_path=False)`), with a `[meta]` block. That cannot work in core, because the module folder belongs to the installed program and may not be writable. Since the Stable release had not gone out yet, the addon was changed to Option B below before release, so the addon and the future core gramplet use the same keys. The addon copies an existing `Betawhatsnext.ini` into `gramps.ini` once and then renames the old file to `Betawhatsnext.ini.imported`.

The settings are small: the three chosen tag names, "Show suggested Next Steps", and "Report a missing parent family". The Search Quota and the two loop controls are not part of this file. They are saved with each placed gramplet in the Dashboard or gramplet bar .ini, which records the gramplet id with them, and that does not change.

Three places are possible.

### Option A: its own .ini beside the view .ini files
`config.register_manager("Gramplets_whatsnext", use_config_path=True)` puts the file in `VERSION_DIR`, for example `~/.config/gramps/gramps61/Gramplets_whatsnext.ini` on Linux. That folder already holds the view settings files (`pageview.py` uses `register_manager(self.ident, use_config_path=True)`, with `ident` built as `<category>_<view id>`) and the Dashboard layout, `Gramplets_dashboardview_gramplets.ini`. The `Gramplets_` prefix matches the Dashboard file.

- For: self-contained, easy to find and delete, and close to the addon code (one line changes).
- Against: no core gramplet does this today, so it sets a new precedent. The file also starts over with each new Gramps version folder, because `load_previous()` in `gramps/gen/config.py` carries only `gramps.ini` forward from an older version. The view .ini files have the same limitation.

### Option B: keys in gramps.ini (chosen, and used by the addon now)
Register the keys in `gramps/gen/config.py` beside the other settings, in a `whatsnext` section: `whatsnext.tag-complete`, `whatsnext.tag-ignore`, `whatsnext.tag-prune`, `whatsnext.show-next-steps`, and one `whatsnext.check-<test>` key for each test offered in the options (today only `whatsnext.check-parents-missing`). The gramplet reads and writes them through the shared `config` object, as other core gramplets already do (`ancestor.py`, `events.py`, `placedetails.py` and others import `gramps.gen.config.config`).

- For: the standard core pattern, carried forward on a Gramps upgrade by `load_previous()`, and ready to show in the Preferences dialog later if wanted.
- Against: one more section in `gramps.ini`, and a change to a `gen` file that reviewers will check closely. Registering at runtime from the gramplet module also works, and is what the addon does: a key loaded from `gramps.ini` before registration keeps its saved value, and core already registers keys at runtime in `gramps/plugins/sidebar/favoritessidebar.py` and `gramps/plugins/webreport/narrativeweb.py`. For core, registering in `gen/config.py` is clearer.

The `[meta]` block is gone. `gramps.ini` has no per-section metadata: the section name already identifies the gramplet, and the only checks are the version folder, `load_previous()` carrying the file forward, and a type check on load (a saved value of the wrong type is ignored with a warning). A `whatsnext.settings-version` key could be added as a hook for a future layout change, but the rule of adding new keys instead of changing old ones makes it unlikely to be needed.

### Option C: tag choices kept with each tree
The chosen tags belong to a tree, so a tag picked for one tree means nothing in another. Today (as with the old addon .ini) the setting holds tag names, not tags, and is the same for every tree: the name is looked up in whichever tree is loaded. In a tree that has no tag of that name, nothing is hidden, and the first Tag as Complete, Ignore or Prune creates a tag with that name. So the setting works as "the tag names to use in every tree". Storing the three tag names with the tree would be the most correct choice. The database has metadata storage, but only through private methods (`_get_metadata()` and `_set_metadata()` in `gramps/gen/db/generic.py`), so this would need a public API. Leave this for discussion. The two on-or-off options would stay in Option B either way.

### Moving the addon settings forward
Nothing needs to be imported by core. The addon already writes the same `gramps.ini` keys, and `load_previous()` carries `gramps.ini` forward into the new Gramps version folder, so a user moving from the addon to the core gramplet keeps the chosen tags and options. The `import_addon_ini()` step and its `.imported` rename stay in the addon only.

## Retiring the superseding addon
Do these steps before the Gramps release that contains the new core gramplet is published. Call that release X.Y.

1. Change the range in `Betawhatsnext.gpr.py` so it stops before X.Y: `if (5, 2, 0) <= VERSION_TUPLE < (X, Y, 0):`. The current range, `<= (6, 2, 0)`, includes 6.2.0 itself, so this matters if X.Y is 6.2.
2. Raise the addon version and build comment, and add a final CHANGELOG entry saying that from Gramps X.Y the gramplet is part of core, with a link to the core pull request.
3. Publish that release only in the addon listings for Gramps versions before X.Y, and leave it out of the X.Y listing.
4. Move the addon folder to an archive location in CuratedGrampsPlugins (for example `archive/Betawhatsnext/`), or tag the last commit (for example `whatsnext-addon-final`) before deleting it. Keep the full history; it is the starting point for the next round.
5. Users who stay on an older Gramps keep the addon and the improved gramplet. Users who move to X.Y get the core version and a new plugins folder, which has no copy of the addon.

## Starting the next round
When the gramplet needs to evolve again after X.Y, bring the framework back:

1. Start from the core `whatsnext.py` of X.Y, not from the archived addon, so core fixes are not lost. Copy across the parts of the archived addon that are still useful, such as the Help button block and the .ini settings code.
2. Register with `id="What's Next"` again, with a range that starts at X.Y (`(X, Y, 0) <= VERSION_TUPLE`), and a version above the core version.
3. Restart the CHANGELOG with the core version of X.Y as the new baseline for comparison, with links to the core files as in the current baseline paragraph.
4. Keep settings compatible with core: use the same `whatsnext.*` keys, and add any new settings as new keys in that section, so that going back to core, or the next core merge, finds what it expects. Never change the type or meaning of an existing key; add a new key instead.
5. Retire the addon again with the steps above when the next core release takes the changes.

## Open questions
- Whether the batch tagging buttons come back with a new design before the core merge, or are dropped from the core version.
- Which Gramps release to aim for. The master branch currently reports 6.1.0 as a development version, so X.Y is 6.1 if the merge is in before the feature freeze, and otherwise 6.2.
- Whether core reviewers accept the Prune tag (which changes the search path) as a core feature, or prefer only Complete and Ignore at first.
