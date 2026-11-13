# PR2485 Edit Person Tweaks changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 0.1.0
- Fixed column widths saved as 2 for tables that were never drawn ([Mantis 0014379](https://gramps-project.org/bugs/view.php?id=14379)). `PersistentTreeView.get_columns_size()` no longer rounds a width of 0 up to 2, so its zero check skips the save, and `restore_column_size()` ignores saved values of 2 or less for text columns, which repairs widths already stored in gramps.ini. Applies to every editor tab and list; skipped if Gramps core already has the fix.
- Added Gramps [PR #2485](https://github.com/gramps-project/gramps/pull/2485) (Doug Blank, Mantis 0013365): the Multiple Surnames table restores the saved width of all five columns, the Origin column uses FIXED sizing so it resizes like the others, and the Prefix, Connector and Origin defaults are wider. Skipped if Gramps core already has the PR.
- Switching to Multiple Surnames (button or Ctrl+A) adds a surname row and starts editing its Prefix cell; an existing completely empty row is reused instead.
- In Multiple Surnames mode, Ctrl+A runs "Create and add a new surname"; text being typed in a cell is committed first.
- Added a Fuzzy Match Lookup button right of the Surname field, shown only when the Fuzzy Matching addon ("Fuzzy Match API") is registered and not hidden, and hidden in Multiple Surnames mode.
- Added a "surname" field tip (placeholder) to the Surname field, matching the Prefix and Suffix tips.
- At startup, resets `person_editor_surnames` in gramps.ini to the default when its 1st, 3rd and 4th values are all 2.

## Outstanding issues
### Planned/NYI
- Remove the startup reset of `person_editor_surnames`; the restore fix for Mantis 0014379 now covers it.
- Decide what to do with a surname row that was added but left empty (currently kept on save).

### Needs discussion
- The global `PersistentTreeView` fix is broader than the Person editor; it could move to its own addon or ship with a PR field-test addon.
- Section schema versions in Gramps `ConfigManager`, so an update can discard a stale section such as `[spacing]` instead of adding a one-off fix for each key. `load_previous()` in `gramps/gen/config.py` copies gramps.ini forward on every version upgrade, so bad values survive upgrades.
- Fuzzy Match Lookup double-click currently opens the found person in their own editor; an alternative is to fill the dialog name fields.

### Beyond scope
- Merging the `persistenttreeview.py` fix and PR #2485 into Gramps core.
- `FuzzyMatchLookupWindow` calls `self.window.show_all()` instead of `ManagedWindow.show()`, so it has no `opened` attribute and crashes if opened with a parent track (fix belongs in the Fuzzy Matching addon).
