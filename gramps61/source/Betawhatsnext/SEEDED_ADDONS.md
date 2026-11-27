# What's Next? - Seeded addons

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [SEEDED_ADDONS.md](SEEDED_ADDONS.md)

This document is for developers. It describes a way to ship most of the plugins that come with Gramps as addons, placed in the user plugins folder (for example `gramps62/plugins`), instead of as built-in plugins in the protected program folder. A user can then update, replace, or change them like any other addon. The What's Next gramplet is the first trial. It replaces CORE_MIGRATION.md, which planned to merge the gramplet back into the built-ins; that plan was dropped.

## Decisions so far
- **Most plugins become seeded addons.** Only the plugins that are needed for the basic operation of Gramps stay built in (see "Plugins that stay built in").
- **Addon translations use their own catalog.** The strings of seeded addons live in the consolidated translation catalog for the addons, separate from the core catalog.
- **Translation Updater is the first step** toward keeping those translations current between releases.
- **Settings go in gramps.ini.** A seeded addon keeps its settings as keys in `gramps.ini`, not in an .ini file in its own folder (see "Settings").

## How seeding works
An installer or package manager cannot write into the home folder of each user, and it often runs before that folder exists. So Gramps itself does the seeding, when a Gramps version starts and finds addons to seed.

- **Bundle folder.** The program ships a folder of ordinary addon packages in its protected space, for example `share/gramps/bundled-addons/*.addon.tgz`, with a small index that lists each package, its plugin ids, and its version.
- **Same install code as the Addon Manager.** Seeding an addon is installing it: Gramps unpacks each package into `USER_PLUGINS` with the existing `load_addon_file()` in `gramps/gen/plug/utils.py`. There is no second mechanism to maintain, and no network is needed.
- **When it runs.** At startup, before the user plugins are registered (`CLIManager.do_reg_plugins()` in `gramps/cli/grampscli.py` scans `PLUGINS_DIR`, then `USER_PLUGINS`). A first start of a new Gramps version seeds everything that has not been declined.
- **Manifest.** Gramps records what it seeded: the plugin id, the version, and a checksum of each file it unpacked. This is what tells Gramps later whether a copy is still the one it installed.

## Updates and changed copies
- **Updates come through the addon listing.** Each seeded addon must be listed in the official addon listing for its Gramps version, or the Addon Manager finds no updates for it.
- **A newer bundle re-seeds.** When a Gramps point release ships a newer bundled version, Gramps replaces the installed copy, but only if every file still matches the manifest.
- **A changed copy is left alone.** If the user (or a tinkerer) edited the files, Gramps does not overwrite them. It reports that a newer bundled version is available and offers "Restore bundled version" instead.

## Removing a seeded addon
If a user uninstalls a seeded addon, it must not return at the next start. Gramps keeps a "declined" list in `gramps.ini`, in the same way it already keeps `behavior.previously-seen-addon-updates` for update notices. "Restore bundled version" removes the plugin from that list again.

## Plugins that stay built in
The test for the list: Gramps started with the user plugins folder empty, or with seeding turned off, must still open, edit, and save a tree, and must be able to install or restore addons. A starting list:

- the database backends
- Gramps XML import and export, and GEDCOM import and export
- the core views needed to edit a tree (People, Families, Events, Places, Sources, Citations, Repositories, Media, Notes)
- the Preferences dialog
- the Addon Manager and the Plugin Manager, because they are the tools that install, repair, and restore the seeded addons; if they were addons themselves, a broken plugins folder would have no way back

Everything else (most gramplets, reports, tools, quick views, and the other views) is a candidate for seeding.

## Translations
- **Consolidated addon catalog.** Seeded addons are translated in the consolidated catalog for the addons, not in the core catalog.
- **Translation lookup order.** A seeded addon uses `glocale.get_addon_translator(__file__)`. In `gramps/gen/utils/grampslocale.py` that translator checks the core catalog first and falls back to the addon catalog. A string that core already translates keeps its core translation, and a new string comes from the addon catalog.
- **Carry translations over, do not redo them.** When a plugin moves out of core, its existing core translations should be copied into the addon catalog by matching identical source strings, for example by running `msgmerge` with the core `.po` file of each language as a compendium. Translators then see only the strings that are truly new.
- **Remove the core entries afterwards.** The file of the plugin comes out of `po/POTFILES.in`, so the two catalogs do not both carry it. Its strings stay in the core catalog only where other core code still uses them.
- **Translation Updater.** It updates translations without a new version of the addon. It needs the manifest of seeded addons, so it fetches their translations even though the user never installed them through the Addon Manager.

## Settings
A seeded addon keeps its settings as keys in `gramps.ini`, in a section named for the plugin (What's Next uses `whatsnext`), registered at runtime with `config.register()`. Core already does this in `gramps/plugins/sidebar/favoritessidebar.py` and `gramps/plugins/webreport/narrativeweb.py`.

- An update or a re-seed unpacks the addon folder again, but `gramps.ini` is untouched.
- A Gramps upgrade carries `gramps.ini` forward (`load_previous()` in `gramps/gen/config.py`), but not the plugins folder or the other .ini files of the version folder.
- `gramps.ini` has no metadata for each section. Add new settings as new keys, and never change the type or meaning of an existing key.

## Version folders
Each Gramps version has its own user plugins folder (`gramps61/plugins`, `gramps62/plugins` and so on), so seeding runs again for each new version. That is wanted: an old copy never runs on a newer Gramps. Hand changes in the old version folder stay behind, and the user can copy them across on purpose.

## Locked-down and shared computers
- **Off switch.** A `gramps.ini` key or an environment variable turns seeding off, for administrators who manage plugins themselves.
- **Shared folder (later).** An option to seed into a shared plugins folder for all users of one computer.

## Source, tests, and packaging
- The source of a seeded plugin can stay in the Gramps repository, with its unit tests. Only where it is installed changes.
- The build packs each seeded plugin into an `.addon.tgz` and writes the bundle index, instead of copying the plugin into `gramps/plugins`.
- Distribution packages ship the bundle folder like any other data files.

## Until seeding exists
Before Gramps can seed, an addon can still take the place of a built-in plugin: Gramps registers the built-ins first and the user plugins second, and a registration with an id that is already known replaces the earlier one (`PluginRegister.scan_dir()` in `gramps/gen/plug/_pluginreg.py`, the same in 5.2, 6.0 and 6.1). This is how the What's Next addon works today.

- The version number does not decide which one loads; the addon always wins.
- The version range `if` in the `.gpr.py` is therefore the only switch that turns the replacement off. If a later Gramps release ships a newer built-in (or seeded) copy, the range must stop short of that release, or the old addon hides the newer code without a warning.
- Once Gramps seeds What's Next itself, the addon and the seeded copy are the same addon, and the "bundled version is newer" rule above takes over from the version range.

## What's Next as the first trial
Current state of the addon:

- registers with the same id as the built-in (`What's Next`), so it replaces it on Gramps 5.2 to 6.2
- settings in `gramps.ini`, section `whatsnext` (`tag-complete`, `tag-ignore`, `tag-prune`, `show-next-steps`, `check-parents-missing`), with a one-time import of the old `Betawhatsnext.ini`
- translations through `glocale.get_addon_translator(__file__)`, so the strings it shares with the built-in keep their core translations

Steps to make it a seedable addon:

1. Add it to the consolidated addon catalog, carrying over the core translations of its 42 existing strings.
2. List it in the official addon listing for each supported Gramps version.
3. Decide the folder and file name (today `Betawhatsnext`), since seeding and the listing will fix it in place.
4. Add it to the bundle and to the manifest that Translation Updater reads.
5. Test: a new version folder with no plugins seeds it; an edited copy is left alone; an uninstalled copy stays uninstalled; "Restore bundled version" brings it back.

## Open questions
- Where the seeding code lives: in core startup, or first as an addon that proves the idea (with the known limit that an addon cannot seed the folder it is itself installed in until it is installed).
- The format and place of the bundle index and of the seed manifest.
- Whether "Restore bundled version" belongs in the Plugin Manager, the Addon Manager, or both.
- Which views, if any, beyond those needed to edit a tree, must stay built in.
- How a GEPS proposal should present this to the Gramps developers.
