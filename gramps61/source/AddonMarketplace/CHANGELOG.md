# Addon Marketplace changelog
<!-- edit=False status=True browse=False undocked=True -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable changes to the Addon Marketplace addon are listed here, newest first. Changes are compared with the Addon Manager of Gramps.

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
- The Help button shows no icon on themes without a color help icon. A bundled color icon, and a tooltip that names the addon, wait for the shared Help button code in [MarkdownUtils](https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/MarkdownBased) to get them, so that every addon gets the same fix.

### Needs discussion
- Whether the menu item should keep the name "Addon Manager...".
- Whether projects that were saved earlier with a GitHub web page address should be converted automatically when the catalogs load, instead of being reported in the warning bar.
- Whether the window should remember its own size instead of sharing it with the Addon Manager.
- After installing the addon in a running Gramps, the menu item keeps its old name until Gramps rebuilds its menus (for example, on a change of view).

### Beyond scope
- The reason a project failed is found by reading its English catalog a second time, because `get_addons()` in Gramps only writes errors to the terminal. A change in Gramps itself to return the error would remove the second request.
- The catalogs published today list no authors or maintainers, so searching for a person finds nothing until the catalog generator of Gramps adds them.
- Installing Python modules without pip (all-in-one Windows installer, Flatpak) on Gramps 5.2 and 6.0: the PyPI installer exists only in Gramps 6.1 and newer.
