# PR2388 Example Tree Prompt Changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

This addon is a field-test package of [Gramps pull request #2388](https://github.com/gramps-project/gramps/pull/2388) by Doug Blank ([@dsblank](https://github.com/dsblank)). Version 0.0.0 below records what the pull request itself provides, as the baseline. Later versions list what the addon changes or adds.

## 0.1.0
- Packaged as an addon for Gramps 5.2, 6.0 and 6.1, so the feature can be tested without patching Gramps core files. If a future Gramps already includes the feature, the addon does nothing.
- The dialog no longer competes with a tree opened at startup. It does not appear when Gramps starts with something to open or import (for example `gramps file.ged`, opening a file from a file manager, or the `-O`, `-C`, `-i`, `-e` or `-a` options), when a tree is chosen in the Family Trees manager, or when the last tree loads automatically. (In 0.0.0 the dialog appears anyway, and importing would close the tree the user just opened.)
- Runs on Python 3.13 and older. (In 0.0.0, `exampleimport.py` raises a `NameError` when it is imported there.)
- Only the **Do not ask again** checkbox turns the dialog off for good. **Skip**, the Esc key and the window close button skip it for this launch only. (In 0.0.0, Skip also turns it off for good, so the checkbox only matters together with Import.)
- After the import, Gramps switches to the Dashboard. If the Dashboard is empty or still shows only the default gramplets, the To Do gramplet is added.
- If the imported data has no To Do notes, one To Do note is added and attached to the Home Person. It links "Read more about this sample tree" to the addon help page, "Home Person" to the [Gramps Glossary entry](https://gramps-project.org/wiki/index.php/Gramps_Glossary#home_person), and the name to the Home Person. If the tree has no Home Person, the note says so and uses the person with the lowest Gramps ID instead.
- The imported tree is named "sample tree data" instead of "Example Family Tree". Gramps also includes the much larger `example.gramps`, and `data.gramps` has no name of its own, so the generic name avoids confusion and still fits a replacement or localized `data.gramps`.
- The Tip of the Day is skipped for any launch where the dialog appears, so two similar windows never open together. (In 0.0.0 both appear.)
- The dialog uses the Tip of the Day layout (Gramps picture on the left, text on the right) with the window title "Getting Started" instead of "Welcome to Gramps", so it does not share a name with the Welcome to Gramps gramplet. The body text was rewritten, and the button now reads **Import Practice Tree**.
- Importing adds a "Gramps example data" bookmark for the sample media folder to the file chooser sidebar, unless a bookmark for that folder already exists.
- The map pictures are kept in an optional `maps` folder inside the addon folder instead of the Gramps data folder.
- The dialog setting is kept in `PR2388_ExampleTreePrompt.ini` in the addon folder instead of `gramps.ini`, so the `--config=behavior.show-example-prompt:True` command line override does not apply.
- A warning is logged when the sample data cannot be found, instead of skipping the dialog silently.
- The button and checkbox labels have no keyboard mnemonics, and the checkbox reads **Do not ask again**, matching the wording Gramps already uses (and translates) elsewhere.

## 0.0.0
Baseline: the features of [Gramps pull request #2388](https://github.com/gramps-project/gramps/pull/2388), "Prompt new users to import the Example Family Tree on startup", by Doug Blank. The pull request notes that it was written with Claude Code.
- At startup, when no tree named "Example Family Tree" exists, a "Welcome to Gramps" dialog offers to import the sample data that comes with Gramps (`data.gramps`).
- **Import Example Tree** creates a new "Example Family Tree" with the default database backend, imports the data with the Gramps XML importer and opens it in the main window.
- `{GRAMPS_RESOURCES}` is added to the values Gramps expands in media paths, and `DOC_DIR` is exported from `const.py`, so the sample media is found in installed Gramps packages.
- After the import, 21 OpenStreetMap world map pictures (zoom levels 0 to 2), bundled in the Gramps data folder, are copied into the Geography map cache. Pictures already in the cache are not replaced.
- **Skip**, the Esc key and the window close button turn the dialog off for good. The **Don't ask again** checkbox does the same when combined with Import. Importing without the checkbox leaves the dialog on, so it appears again if that tree is deleted or renamed.
- The dialog is shown from `Gramps.__init__`, after the Family Trees manager closes and after the Tip of the Day window opens.
- The setting `behavior.show-example-prompt` is stored in `gramps.ini` and can be overridden with `--config=behavior.show-example-prompt:True`.
- The button and checkbox labels have keyboard mnemonics.

## Outstanding issues
### Planned / NYI
- The map pictures are not yet included in the addon package; testers download them with the command in the README.
- Preferences options to keep file chooser bookmarks for the current Base media path, the backup path and other useful folders.

### Needs discussion
- Which of the differences above should be proposed on [the pull request](https://github.com/gramps-project/gramps/pull/2388): the startup-file conflict, the checkbox behavior, the tree name and skipping the Tip of the Day.
- In the pull request, `gramps/gui/exampleimport.py` raises a `NameError` when it is imported on Python 3.13 and older, because the `ViewManager` type annotation is only imported for type checking.
- Some Linux packages may leave out `data.gramps`; in that case the dialog never appears (a warning is logged with the path that was checked).
- Confirm that the "Getting Started" title is visible in the window title bar on macOS and Windows.

### Beyond scope
- Offering the large `example.gramps` tree as a second choice.
- Providing localized sample data.
