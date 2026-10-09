# Changelog: Plugin Manager plus
## 2.1.3 - 2026-10-08
### Changed
- The plugin list view is detached while its rows are filled, so it does not redraw for each of several hundred rows.
- On open, the selected row is centered directly. The old workaround (sort by Name descending, then ascending) can be restored by setting `_CENTER_ON_OPEN_VIA_SORT_TOGGLE = True` near the top of `PluginManagerPlus.py`.
- The modules `difflib`, `urllib.request`, `urllib.parse` and `http.client` are imported only inside the functions that use them.
- Button icons use the same icon resolver as every other icon in the dialog (MarkdownUtils when it is installed).
- Two helpers now build the list columns: `_add_text_column` (Status, Name, Description) and `_add_indicator_column` (README and help). Column order, widths, saved widths and the live text wrapping of Description are unchanged.

### Fixed
- Without MarkdownUtils, moving the mouse over the information pane raised a `NameError` on every movement.

### Removed
- A second import of `gi` and `Gio` inside `_launch_uri`.

## 2.1.2 - 2026-10-08
### Added
- When a plugin registers its own icon (`stock_icon` for a View, otherwise the first entry of `icons`), the Preview pane shows that icon at 128 px on the same line as the thumbnail. The thumbnail is narrowed so both fit. When there is no thumbnail, the icon is shown beside the placeholder icon.

### Changed
- The placeholder icon in the Preview pane is centered, the same as thumbnails, so the pane does not jump left and right while scrolling.
- When MarkdownUtils is installed, it is the only code that resolves icons, in every pane. This needs the MarkdownUtils fix from 2026-10-08.
- The registration file uses a temporary `help_url` that points to the plugin folder on GitHub, for systems without MarkdownUtils.

### Fixed
- Wiki thumbnails with spaces in the file name (for example, "SQLite Export addon 51.png") failed with a traceback in the console. File names are now URL-encoded, with spaces as underscores, and HTTP errors are caught.
- While scrolling, the same wiki image could be downloaded again and again. An image that is downloading, or that failed in this Gramps session, is not requested again.

### Removed
- The **Category:** line in the Details pane. The **Interface:** line shows the same submenu or view category under exactly the same conditions.

## 2.1.1 - 2026-10-08
### Changed
- Icons and composite icon strips in the list are loaded once per Gramps session and then reused.
- The wiki catalog match for each plugin is computed once and reused for later selections.
- The search text for each row is built once and reused until the list is filled again.
- Built-in plugins are detected with `PLUGINS_DIR` from Gramps (a path prefix test on real paths) instead of a search for the text "gramps/plugins".
- Four small helpers replace repeated code: `_is_builtin_path`, `_readme_path`, `_status_text` and `_view_category_label`.

### Removed
- Unused code: `UPDATE_RES`, `IGNORE_RES`, `static.panel`, five unused attributes of `PluginStatus`, `_MdInfoPane._tags`, and `restart_needed` (it was set but never read).

## 2.1.0 - 2026-10-08
### Changed
- `PluginManagerPlusLoad.py` no longer imports the dialog when Gramps starts. The module, MarkdownUtils and the settings file are loaded the first time **Help → Plugin Manager** is opened.

### Fixed
- **Update** downloaded the listing of every enabled repository once for each enabled repository, and wrote every entry that many times to `new_addons.txt`. Each repository is now downloaded once, with `get_addons()` from Gramps. The list no longer applies the Gramps update-type and "previously seen" filters, and this dialog no longer sets the date of the last update check.
- Opening the dialog could stall until some unrelated event arrived (for example, a mouse movement), while the dialog waited for its final window size.
- When `media/Template_Addons5.2.txt` was missing and the computer was offline, every open could freeze for up to 10 seconds. The table is now downloaded in the background, at most once per Gramps session.

## 2.0.4 - 2026-10-08
### Added
- The Preview pane uses `screenshots/1.png` (or `screenshots/1.webp`) in the plugin folder, in preference to `media/screenshot.png` and `media/screenshot.webp`.
- An image larger than 5 MB is not loaded in the Preview pane. A warning with the file size is shown instead.
- An **Interface:** line under **Type:** in the Details pane shows where the plugin appears in Gramps. Examples: "Tools ▶ Isotammi tools ▼ SuperTool...", "Reports ▶ Text Reports ▼ Double Cousins...", "Charts ▶ Quilt Chart", or the list of views for a Gramplet.

### Fixed
- The search box did not search all registration fields. It now also matches status (for example, EXPERIMENTAL), version, target Gramps version, audience, type, category, file name, folder and help link.
- Search fields are kept separate, so a search with several words cannot match across the boundary of two fields.
- A plugin with no folder was searched for a screenshot relative to the current working folder.
