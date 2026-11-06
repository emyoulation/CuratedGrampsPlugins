# Addon Marketplace changelog
<!-- edit=False status=True browse=False undocked=True -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable changes to the Addon Marketplace addon are listed here, newest first. Changes are compared with the Addon Manager of Gramps.

## 0.1.2 - 2026-11-06
Shows what is missing in the list of new and updated addons, copes with changes in the catalogs of projects, and stops update offers that came back at every start of Gramps.

### Fixed
- A catalog with changes the Addon Marketplace does not expect no longer breaks it. Each addon in a catalog is checked when the catalog loads: missing values get defaults, values of the wrong kind are corrected, new keys are kept, and an addon of a type, audience or status that this Gramps does not know (for example from a newer Gramps) shows as "Unknown". Only an entry without an addon ID or download file is skipped, and the terminal says how many. Before, one unusable entry lost every addon of that project, and one unknown type stopped the Addons tab with an error.
- The same new and updated addons are no longer offered at every start of Gramps, even after you install them. Gramps offered again, as "New", every installed addon that it cannot use because a module or program it requires is missing, and offered again every addon whose download contains another version than its catalog says, or that is installed twice in two folders. The check at startup now skips these offers until the project publishes a new version, and writes the reason to the log at info level.
- Gramps no longer stops responding while the Install button installs the Python modules an addon requires. A small window shows which module is being installed, and its **Cancel** button stops the installation. Large modules, such as the `litellm` module of the Chat With Tree addons, can take several minutes. On Gramps 6.1 without pip, the installation cannot be stopped, so Cancel is dimmed.
- An addon that was installed once before, and that Gramps could not use then (for example because a module it requires was missing), now works at once when you install it again after its requirements are installed. Before, Gramps did not look at its folder again until it was restarted.
- When Gramps cannot use a downloaded addon because something it requires is missing, the message names what is missing, instead of saying that the addon was probably made for another Gramps version.
- The Help button now comes from MarkdownUtils, which shows a color icon also on themes without one (such as current Adwaita), and names the addon in its tooltip. The warning about a missing help icon is no longer written to the terminal. Without MarkdownUtils, the Help button is a plain text button that opens the web page of this addon.
- The description of the addon in the Plugin Manager names the **Downgrade** button, instead of a "Revert" button that does not exist.

### Added
- The list of new and updated addons (at startup, and from **Check for updated addons now** on the Settings tab) has a **Requires** column. A warning icon and the missing Python modules, GObject libraries or programs show there, and a tooltip on the row explains what to do. The warning icon comes from the icon theme when it has a color one, otherwise from the new `media/warning.png`.
- **Check for updated addons now** also lists installed addons that Gramps cannot use, so you can see what they miss. Every addon in the list has a check box, and **Select All** checks every addon.
- A green check mark (the new `media/installed.svg`) before the addon name shows that the addon is already installed.
- A click on the warning icon of an addon in that list, or on the **Requires** button of an addon on the Addons tab, opens a checklist of what the addon needs: each missing Python module, GObject library or program, whether Gramps can install it, and commands to copy. On Fedora and Debian or Ubuntu, the commands find the system package that has each missing item.
- A catalog may also list each addon with the field names of its `.gpr.py` registration (`name`, `version`, `authors`, `maintainers` and every other field), next to or instead of the short keys of today; a field name wins over its short key. The search box finds addons by the names and e-mail addresses of their authors and maintainers when a catalog lists them. This prepares the Addon Marketplace for a fuller catalog that lists every field of each addon.
- When **Allow Gramps to install required Python modules** is on, the list of new and updated addons installs the missing Python modules of the checked addons before it downloads them, in the same small window as the Install button. Before, it only downloaded the addons, which then stayed inactive. Modules that are published only as source code get their ready-made "binary" version, such as `psycopg2-binary` for `psycopg2`.

### Changed
- The list of known addon collections now ships as `media/addons-projects.ini` instead of `media/gramps.ini`. A `gramps.ini` file put in the `media` folder (your own from your Gramps user folder, or one shared by another user) is used instead, without editing, and an update of the addon no longer overwrites it. The tooltip of the index card button names the file in use.

## 0.1.1 - 2026-11-03
Fixes the project check boxes, and brings the documentation up to date.

### Fixed
- Turning a project or "Include English" on or off no longer downloads the catalogs of every project again, resets the Project filter, moves the selection to another addon, or rebuilds every addon in the list. Catalogs are now downloaded once when the window opens and kept until it closes, so a change only downloads catalogs that are not kept yet, and several quick clicks give one update of the list. **Refresh** still downloads every catalog again.
- Changing a filter keeps the selected addon selected and in view, and only recolors the lozenges, instead of rebuilding every addon in the list.

### Changed
- Projects added from the "Add projects" dialog are turned on. The on/off flags in `media/gramps.ini` are ignored; only the main `gramps.ini` of Gramps decides which projects are on.
- `media/gramps.ini` is read each time the Projects tab opens and each time the index card button is clicked, so a changed list of addon collections shows at once. Before, it was read once when the window opened.
- The README describes every feature of the addon, with screenshots of the Addons tab, the Settings tab, the Add projects dialog and the Edit Project dialog, and this changelog lists the changes of each release.

## 0.1.0 - 2026-11-03
First field-test release. The addon replaces the Addon Manager window of Gramps 5.2, 6.0 and 6.1 when Gramps starts, without replacing any Gramps files.

### Added
- The Addon Marketplace window opens from the menu item of the Addon Manager, which is renamed "Addon Marketplace...". Only one window opens at a time: the menu item brings an open window to the front. Hiding the addon in the Plugin Manager and restarting Gramps brings back the Addon Manager.
- The Project, Type, Audience and Status lozenges of each addon are buttons: a click filters the list by that value and turns the lozenge gold; a second click clears that filter. A new first lozenge shows the installed state filter, and a click sets it back to "All addons".
- A "New or Updated" installed state filter, which shows the addons you do not have yet and the addons with a different version available. It is the filter when the window opens.
- The installed version lozenge shows whether the version offered is newer (dark gold, with an **Update** button) or older (red, with a **Downgrade** button). Before, every different version showed an Update button, and "1.0" and "1.0.0" counted as different versions. A dark gold or red installed version lozenge filters the list to addons with a different version available.
- A warning bar above the addon list names each enabled project that gave no addons, with its address and the reason (catalog not found, file not found, a GitHub web page instead of a catalog, a web page, invalid JSON, certificate, connection or server errors). It has a light bulb button that opens the Gramps Warnings dialog, a **Certificate help** button for certificate problems, and an **Open Projects tab** button. For a GitHub web page address, the bar shows the address to use instead.
- When no addons show, the list explains why and what to do: no projects turned on, no catalogs loaded (with an **Open Projects tab** button), or none of the listed addons match the filters (with a **Clear all filters** button that sets every filter to "All" and empties the search box). Before, the list only said "No matching addons found."
- An "Add projects" dialog, opened with a new index card button on the Projects tab, lists the known curated addon collections from the `media/gramps.ini` file of the addon that are not in your project list yet. A link opens the published list of known curated addon collections on the Gramps Discourse forum.
- A language code for each project, set in the project dialog. The catalog in that language is read first, for loading the addons and for "Check for updated addons now". The codes are kept in `AddonMarketplace.ini` next to the addon.
- An "Include English" check box on the Projects tab, shown when Gramps or a project uses another language than English. It also loads the English catalog of each such project, listed as the project "<name> + en", with its own Project filter entry.
- A new project dialog, with a choice of Web URL or Local/Network Folder, a folder Browse button, a large address box for long addresses, and a **Test Location** button that checks the catalog and shows the address that will be saved. Addresses, folders and file names in its Validation Status box are links. Certificate problems get a warning with advice, and the project can still be saved. OK saves without a test, so projects can be added offline.
- The project dialog converts GitHub web page addresses (file pages, folder pages, download links and repository front pages) to raw.githubusercontent.com addresses, removes a pasted `listings/addons-xx.json` ending and a trailing slash, and converts typed or pasted folder paths, including Windows paths, to `file:///` addresses.
- Each project on the Projects tab, and in the Add projects dialog, has a folder icon: a double-click opens the GitHub repository of the project, or the folder one level above the project folder. A double-click on the name or the rest of the row edits the project. The project addresses are no longer shown in the list.
- A count of the addons shown, such as "149 of 209 addons", at the left of the Refresh button.
- The Help button, at the lower left, opens the README of this addon in Markdown Dash when it is installed and active, otherwise the web page of this addon. Before, it opened the Gramps manual.
- When Gramps cannot use a downloaded addon, almost always one made for another Gramps version, a message offers to keep its files (to adapt its `.gpr.py` file) or to remove them.
- The search box also searches the help address, and the names and e-mail addresses of authors and maintainers when a catalog lists them.
- On Gramps 5.2 and 6.0, the Install button uses the improvements of Gramps 6.1: addons that an addon depends on are installed first, and a message names an addon that failed to install. On Gramps 6.1, its own PyPI installer is used for modules, as in the Addon Manager.
- A failed Update or Downgrade shows a message with the address that was tried.
- A style sheet of its own (`media/lozenges.css`) for the lozenges and addon rows, limited to this window so that other windows and addons keep their look.

### Changed
- The addon list is sorted by addon ID, then by name.
- Project addresses are saved without a trailing slash, and download addresses no longer get a double slash, which gave a 404 error on some servers.
- On Linux and macOS, Python modules are installed with the pip of the Python that runs Gramps, so a pip that belongs to another Python is not used by mistake.
- Test Location checks certificates with the certificate store of the system first, as Gramps does, and only then with the `certifi` bundle when it is installed.

### Fixed
- Turning several projects on or off quickly no longer shows the same addons more than once.
- Update no longer stops with an error when the new version of an addon cannot be registered.
- A project name that contains `&` or `<` is shown correctly on the Projects tab.

## Outstanding issues
### Planned or not yet implemented
- Translations of the new texts of the addon.
- The color Help button needs the next release of [MarkdownUtils](https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/MarkdownBased). With MarkdownUtils 0.2.2 or older, the Help button is the plain text button.

### Needs discussion
- Whether the menu item should keep the name "Addon Manager...".
- Whether projects that were saved earlier with a GitHub web page address should be converted automatically when the catalogs load, instead of being reported in the warning bar.
- Whether the window should remember its own size instead of sharing it with the Addon Manager.
- After installing the addon in a running Gramps, the menu item keeps its old name until Gramps rebuilds its menus (for example, on a change of view).

### Beyond scope
- The reason a project failed is found by reading its English catalog a second time, because `get_addons()` in Gramps only writes errors to the terminal. A change in Gramps itself to return the error would remove the second request.
- A catalog that lists another version than its download contains (in November 2026, the PostgreSQL addon of the Gramps project lists 1.0.23, but its download contains 1.0.22) must be fixed by that project. The Addon Marketplace only stops offering the same version again.
- The catalogs published today list no authors or maintainers, so searching for a person finds nothing until the catalog generator of Gramps adds them.
- Installing Python modules without pip (all-in-one Windows installer, Flatpak) on Gramps 5.2 and 6.0: the PyPI installer exists only in Gramps 6.1 and newer.

### Wishlist
Ideas for making shopping for addons more pleasant, and for helping people follow through on what they installed. Roughly in the suggested order of work.
- **A receipt of each install session.** After installing or updating, keep a list in `AddonMarketplace.ini` of each addon: name, type, old version and new version (or "new"), date, and whether Gramps can use it. People remember to try one to three new addons, but lose track of more than that.
- **Where to find each addon** in the receipt, from its type: a gramplet is added from the right-click menu of a gramplet bar or the Dashboard, a view appears in its category after a restart of Gramps, a tool or report in its menu and category, a filter rule in the filter editor, a quick view in the right-click menu of its object type.
- **Links in the receipt**, shown only when they exist: the local README (through Markdown Dash), the local CHANGELOG for updates (opened at the heading of the new version), and the web help (`help_url`).
- **"Explored" check boxes** in the receipt, with a count of the addons still to explore on a lozenge or tab, and in the menu item ("Addon Marketplace (4 new)") after Gramps restarts, instead of a popup.
- **A changelog excerpt for updates:** only the part of the CHANGELOG between the old and the new version headings, to show what is different from what you had.
- **"New since your last visit":** keep a snapshot of the catalog ids and versions when the window closes, and offer a lozenge that shows only the addons that are new or changed since then. The catalogs have no dates, so this is the only way to see what is recent.
- **A duplicate-id warning:** before installing, warn when another installed folder already registers the same plugin id (as with the Themes and Themes2 folders), and offer to replace that folder instead of adding a second copy.
- **The cost before buying:** show the requirements of an addon in its row before it is installed, with a "Works now" badge or the warning icon and checklist, and a note for very large modules (such as `litellm`).
- **A wish list:** a star on an addon puts it on an "Install later" list, for example while a system package that it needs is installed first.
- **A project trust badge:** mark the addons of the Gramps project differently from those of other collections, and always show the project name.
- **A catalog and download mismatch report:** when Gramps registers another version than the catalog promised (as with the PostgreSQL addon, 1.0.23 in the catalog and 1.0.22 in its download), say so, and offer to open the issue page of the project with the details filled in.
- **Preview before installing:** download the `.tgz` of an addon to a cache without installing it, and show its README and screenshots in Markdown Dash.
- **Undo an update:** keep the previous folder of an addon as a backup before an update replaces it, and offer **Undo update** in the receipt. The Downgrade button only works while the project still offers the older version.
