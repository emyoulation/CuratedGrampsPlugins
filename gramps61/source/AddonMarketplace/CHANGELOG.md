# Addon Marketplace changelog
<!-- edit=False status=True browse=False undocked=True -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable changes to the Addon Marketplace addon are listed here, newest first. Changes are compared with the Addon Manager of Gramps.

## 0.1.0 - 2026-11-02
First field-test release. The addon replaces the Addon Manager window of Gramps 5.2, 6.0 and 6.1 when Gramps starts, without replacing any Gramps files.

### Added
- The Addon Marketplace window opens from the menu item of the Addon Manager, which is renamed "Addon Marketplace...". Hiding the addon in the Plugin Manager and restarting Gramps brings back the Addon Manager.
- The Project, Type, Audience and Status lozenges of each addon are buttons: a click filters the list by that value and turns the lozenge gold; a second click clears that filter.
- The installed version lozenge shows whether the version offered is newer (dark gold, with an **Update** button) or older (red, with a **Revert** button). Before, every different version showed an Update button. A dark gold or red installed version lozenge filters the list to addons with a different version available.
- A warning bar above the addon list names each enabled project that gave no addons, with its address and the reason (catalog not found, file not found, a GitHub web page instead of a catalog, a web page, invalid JSON, connection or server errors), and an **Open Projects tab** button. For a GitHub web page address, the bar shows the address to use instead.
- When no addons show, the list explains why and what to do: no projects turned on, no catalogs loaded (with an **Open Projects tab** button), or none of the listed addons match the filters (with a **Clear all filters** button that sets every filter to "All" and empties the search box). Before, the list only said "No matching addons found."
- A new project dialog, with a choice of Web URL or Local/Network Folder, a folder Browse button, a large address box for long addresses, and a **Test Location** button that checks the catalog and shows the address that will be saved. OK saves without a test, so projects can be added offline.
- The project dialog converts GitHub web page addresses (file pages, folder pages, download links and repository front pages) to raw.githubusercontent.com addresses, removes a pasted `listings/addons-xx.json` ending, and converts typed or pasted folder paths, including Windows paths, to `file:///` addresses.
- The Help button, at the lower left, opens the README of this addon in Markdown Dash when it is installed and active, otherwise the web page of this addon. Before, it opened the Gramps manual.
- On Gramps 5.2 and 6.0, the Install button uses the improvements of Gramps 6.1: addons that an addon depends on are installed first, a message names an addon that failed to install, and the message for an addon that failed to register points to the Projects tab. On Gramps 6.1, its own PyPI installer is used for modules, as in the Addon Manager.
- On Linux and macOS, Python modules are installed with the pip of the Python that runs Gramps, so a pip that belongs to another Python is not used by mistake.
- A style sheet of its own (`media/lozenges.css`) for the lozenges and addon rows, limited to this window so that other windows and addons keep their look.

### Fixed
- Turning several projects on or off quickly no longer shows the same addons more than once.

## Outstanding issues
### Planned or not yet implemented
- A screenshot of the Addons tab for the README.
- Translations of the new texts of the addon.
- The Help button shows no icon on themes without a color help icon. A bundled color icon, and a tooltip that names the addon, wait for the shared Help button code in [MarkdownUtils](https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/MarkdownBased) to get them, so that every addon gets the same fix.

### Needs discussion
- Whether the menu item should keep the name "Addon Manager...".
- Whether projects that were saved earlier with a GitHub web page address should be converted automatically when the catalogs load, instead of being reported in the warning bar.
- Whether the window should remember its own size instead of sharing it with the Addon Manager.
- After installing the addon in a running Gramps, the menu item keeps its old name until Gramps rebuilds its menus (for example, on a change of view).

### Beyond scope
- The reason a project failed is found by reading its English catalog a second time, because `get_addons()` in Gramps only writes errors to the terminal. A change in Gramps itself to return the error would remove the second request.
- Installing Python modules without pip (all-in-one Windows installer, Flatpak) on Gramps 5.2 and 6.0: the PyPI installer exists only in Gramps 6.1 and newer.
