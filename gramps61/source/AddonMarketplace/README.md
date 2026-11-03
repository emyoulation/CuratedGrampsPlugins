# Addon Marketplace
<!-- edit=False status=True browse=False undocked=True -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

Addon Marketplace is a friendlier way to find, install and update Gramps addons. It takes the place of the Addon Manager window, so you open it from the same menu item. Everything you know from the Addon Manager is still there, with some helpful extras:
- **clickable labels** on every addon, so one click shows only addons of the same project, type, audience or status,
- clear **Update** and **Revert** buttons that tell you whether the version offered is newer or older than the one you have,
- a **warning bar** that names any addon project that could not be loaded, and says why,
- messages that **tell you what to do** when the list is empty, with a button that clears all the filters,
- a **project dialog** that tests an addon project address before you save it, and fixes common address mistakes for you.

The addon makes these changes when Gramps starts, without changing any Gramps files, so you can switch it off at any time. It is for field testing, so please report problems and ideas.

## Contents
- [Install](#install)
- [Open the Addon Marketplace](#open-the-addon-marketplace)
- [The Addons tab](#the-addons-tab)
- [The Settings tab](#the-settings-tab)
- [The Projects tab](#the-projects-tab)
- [The Help button](#the-help-button)
- [If something does not work](#if-something-does-not-work)
- [Limits](#limits)
- [Turn the addon off](#turn-the-addon-off)
- [Credits](#credits)
- [AI disclosure](#ai-disclosure)
- [Assumptions I made (draft review)](#assumptions-i-made-draft-review)

## Install
Install the addon with the Gramps Addon Manager, from the [Emyoulation curated Gramps plug-ins](https://github.com/emyoulation/CuratedGrampsPlugins/) project. If that addons project is not in your Addon Manager yet, add it as the project page describes. Restart Gramps after you install the addon.

Addon Manager projects URLs:
* `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/master/gramps52`
* `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/master/gramps60`
* `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/master/gramps61`

## Open the Addon Marketplace
Choose **Edit > Addon Marketplace...** from the menu. Before the addon is active, this menu item is named "Addon Manager...". The window has three tabs: Addons, Settings and Projects. The buttons at the bottom are **Help** (at the left), **Refresh** and **Close**. Refresh loads the addon catalogs of your projects again.

## The Addons tab
The Addons tab lists the addons of every project that is turned on in the Projects tab. Each addon shows its name, a row of labels (called lozenges), its description and its buttons.

### Search and filters
Type in the search box to show only addons whose name, description or ID contain that text. The filter menus below the search box narrow the list by installed state (All addons, Not installed, Installed, Updates), project, type, audience and status.

The broom button at the end of the filter row resets the filters to their defaults. The defaults show only addons for **Everyone** with the status **Stable**, so addons for experts or developers, and Beta or Experimental addons, are hidden until you change those filters.

### The lozenges
The first four lozenges of an addon show its project, type, audience and status. They are buttons:
- Click a green lozenge to filter the list by that value. For example, click "Gramplet" to see only gramplets. The lozenge turns gold to show that it is the active filter.
- Click a gold lozenge to clear that filter again.

The **Version** lozenge shows the version that the project offers. If the addon is installed, an **installed version** lozenge appears at the right end of the row:
- **Green**: the installed version is the same as the version offered.
- **Dark gold**: the version offered is newer. An **Update** button is shown.
- **Red**: the version offered is older than the installed version, for example after you installed a test version yourself. A **Revert** button is shown, which installs the older version offered.

A dark gold or red installed version lozenge is a button too: click it to show only addons that have a different version available.

### The addon buttons
- **Install** installs the addon, and any Python modules it needs if you allowed that on the Settings tab. Addons that the addon depends on are installed first, when their project lists that information.
- **Update** and **Revert** replace the installed addon with the version offered.
- **Wiki** opens the help page of the addon.
- **Requires** lists what the addon needs that is missing, such as a Python module or a program.

### When something is wrong
If an enabled project gave no addons, a yellow warning bar appears above the list. It names each such project, its address and the reason, for example "catalog not found (404)" or "a GitHub page, not a catalog". The **Open Projects tab** button on the bar takes you to the project, so you can fix the address. You can select and copy the text of the bar.

When no addons show in the list, a message tells you why and what to do:
- **No projects are turned on**: turn on a project on the Projects tab.
- **No addon catalogs could be loaded**: check the project addresses, then click Refresh.
- **None of the addons listed match the filters**: click **Clear all filters**. This sets every filter to "All" and empties the search box, so every addon shows. (The broom button instead goes back to the default filters, which can still hide everything, for example when a project offers only Experimental addons.)

## The Settings tab
The Settings tab is the same as in the Addon Manager, and changes here also apply to the Addon Manager:
- **Allow Gramps to install required Python modules**: lets the Install button install the Python modules an addon needs.
- **Check for addon updates** and **What to check**: how often Gramps checks for new and updated addons when it starts, and which kind.
- **Do not ask about previously notified addons**: skips addons that Gramps already told you about.
- **Check for updated addons now**: checks at once.

## The Projects tab
The Projects tab lists the addon projects (the places addons come from). The check box of a project turns it on or off. The buttons below the list add a project, remove the selected project, move it up or down, and go back to the default project list. The first project, Gramps, cannot be removed or moved.

### The project dialog
Double-click a project, or click the **+** button, to open the project dialog:
- **Project name**: any name you like. It is shown on the Project lozenge of each addon.
- **Location Type**: **Web URL** for an address on the internet, or **Local/Network Folder** for a folder on your computer or network. For a folder, the **Browse** button next to the address box lets you pick it.
- **URL/Path**: the address of the project. It is the folder that holds the `listings` folder, not the `listings` folder or a catalog file itself.

Click **Test Location** to check the address. The Validation Status box shows what was found, such as how many addons the catalog lists, and the address that will be saved. Testing is optional: **OK** saves the project even without a test, so you can add a project while you are offline.

### Addresses that are fixed for you
When you test or save a project, the dialog changes some common mistakes into the address that Gramps needs, and shows you the result:
- A **GitHub web page** address, for example `https://github.com/name/repository/blob/main/gramps60/listings/addons-en.json`, becomes the address of the files themselves: `https://raw.githubusercontent.com/name/repository/main/gramps60/`. This works for file pages, folder pages and download links. The front page of a repository becomes an address for its default branch, but you still need to add the folder for your Gramps version, such as `gramps60`.
- A **catalog file or listings folder** at the end of the address, such as `listings/addons-en.json`, is removed, because Gramps adds it itself.
- A **folder path** typed or pasted from your file manager, such as `C:\Users\Name\addons\` or `/home/name/addons`, becomes a `file:///` address.

## The Help button
The Help button at the lower left opens this document in Markdown Dash, when Markdown Dash is installed and active. Otherwise it opens the web page of this addon.

## If something does not work
- **The menu item still says "Addon Manager..."**: the new name appears the next time Gramps rebuilds its menus, for example when you change to another view or restart Gramps. The window that opens is already the Addon Marketplace.
- **A Python module will not install**: Gramps installs modules into the `lib` folder of your Gramps plugins folder. If the installation fails, the error message shows what went wrong. You can also install the module into that folder yourself.
- **A project shows in the warning bar**: test its address in the project dialog. The Validation Status box gives more detail than the warning bar.
- When you report a problem, please include the messages that Gramps shows in the terminal window, and one line about what you did just before.

## Limits
- The window size and the settings on the Settings tab are shared with the Addon Manager.
- To find the reason a project failed, the addon reads the English catalog of that project a second time, because Gramps itself only writes the error to the terminal. A project that offers only a catalog in another language can show "catalog could not be read in this language".
- Installing Python modules without pip (in the all-in-one Windows installer or a Flatpak) is possible only on Gramps 6.1 and newer, as in the Addon Manager.
- The texts of the addon are not translated yet. Texts it shares with the Addon Manager show in your language.

## Turn the addon off
To switch the addon off without removing it, open the Plugin Manager, hide "Addon Marketplace", and restart Gramps. The menu item then opens the Addon Manager again. To remove the addon, use the Addon Manager.

## Credits
- The Addon Marketplace is built on the Addon Manager of Gramps, by the Gramps developers.
- Addon by Brian McCullough.

## AI disclosure
This addon was substantially written with an AI tool, as the Gramps [AI generated code policy](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code) asks contributors to disclose.
```
Generated-by: Claude Sonnet 5 (claude-sonnet-5) and Claude Opus 5.5 (claude-opus-5-5), Anthropic, via the claude.ai chat interface, 2026
Prompted by: Brian McCullough
```
- **Prompts (summary):** first an enhanced project dialog and Update/Revert handling inside a changed copy of the Addon Manager file of Gramps 6.0; then that copy turned into a monkey-patch addon named Addon Marketplace for Gramps 5.2 to 6.1, with its own lozenge style sheet; then a Help button that opens this README, messages that tell the user what to do when the Addons tab is empty, a warning bar for projects that could not be loaded, and conversion of GitHub web page addresses.
- **Guidelines:** written in "draft mode", so the Gramps [AGENTS.md](https://github.com/gramps-project/gramps/blob/master/AGENTS.md) style rules (type hints, Black, pylint and others) were not fully applied.
- **Testing:** the AI checked the addon with the source code of Gramps 5.2 and 6.1 in a simulated display, with live addon projects on GitHub. The user interface still needs testing by a person in a running Gramps.

## Assumptions I made (draft review)
This section is for review while the addon is in draft. Remove it before release.
- The menu item is renamed "Addon Marketplace..." as well as the window. If the name should stay "Addon Manager..." in the menu, that is a small change.
- The README describes the Edit menu, which is where the menu item is in Gramps 5.2 to 6.1.
- The Settings tab and the window size stay shared with the Addon Manager, so switching the addon off loses nothing.
- There is no screenshot yet. A screenshot of the Addons tab with a gold lozenge and the warning bar would help, saved as `media/screenshot.png`.
- The lozenge colors are described by name (green, gold, dark gold, red), as they look in the default theme. A dark theme can change the red, because it comes from the theme.
- The Help button falls back to the GitHub folder of the addon, which only works after the addon is committed to the repository.
- "Report problems" has no link yet: I assumed you will start a Gramps Discourse thread, as for other field-test addons.
