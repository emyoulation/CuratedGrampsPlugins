# Pruned Branch — Changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [DEVELOPER.md](DEVELOPER.md)

## 0.1.0
First public release (experimental prototype, Gramps 6.0 and newer).
- Working-subset sessions: choose a tag or a Person custom filter, and the list views, place tree, sidebar and custom filters, Dashboard gramplets, reports and most tools see only that branch, while every edit is saved to the full tree.
- The branch is the chosen people plus every record they use (families, events, places with their enclosing places, citations, sources, repositories, media, notes), built with the same engine as the Export Assistant reference filter.
- Families and events that only reach the branch through a link inside a Note (or an LDS ordinance) are left out: a family needs a parent or child in the branch, an event needs a person or family of the branch that uses it.
- Fast listing on SQLite: TEMP keep-tables joined to the real tables in SQL, with a per-record fallback for other database backends.
- Backups, Make Backup, backup on exit and every export always use the full tree; Family Tree Repair tools can only run after the session ends, and other tools ask whether to run on the branch.
- Starting or ending a session is refused while record editors are open, because Gramps closes them without saving when the views reload; the open editors are listed.
- Records added during a session join the branch, and deleted records leave it.
- Impossible-to-miss session display: a light rose tint on the main window, its menus and detached gramplet windows, a ⛔ PRUNED BRANCH window title, and a red status bar button in the middle of the status bar that ends the session with one click.
- The tags used most recently are remembered per Family Tree (up to 10) and listed first, newest selected, in `PrunedBranch.ini` beside the addon; a settings file from another plugin or schema version is ignored.
- Customizable colors: **Customize colors** opens `media/pruned_branch.css` in the default text editor.
- Opening another Family Tree or closing the tree ends the session cleanly, and ending always restores the normal window, even after an error.
- Benchmark report comparing the full tree with the branch for every record type, sorted lists, the place tree and a person filter, including signal-connection counts across sessions; it also runs before a session starts, on a trial branch that Gramps never switches to.

## Outstanding issues
Known gaps and ideas, grouped by status.

### Planned/NYI
- Remember the last custom filter and the listing method, not only the last tags.
- Note links to Places, Sources, Citations, Media and other Notes still add those records to the branch; treat them like note links to Families and Events.
- An option for a stricter family rule that leaves out the parent family of a branch person when neither parent is in the branch.
- A small helper so other addons (for example a branch-aware What's Next) can ask whether a record is in the active branch.
- People who join the branch through an edit can be missing from the list views until the next session start; confirm and refresh them.
- Results of the 65,000-person benchmark: real speed-up per record type and session build time.
- A personal copy of the stylesheet that survives addon updates (for example in the Gramps CSS folder), with a warning when it is older than the default; the version line at the top of `media/pruned_branch.css` is reserved for this.

### Needs discussion
- Starting from a Tools menu entry, compared with a gramplet or a Family Trees menu item.
- Choosing the branch from one tag or one custom filter, compared with a new selection dialog.
- Every export uses the full tree, because Gramps cannot tell an export made as a backup from any other export.
- Reports run on the branch without a warning.
- One click on the status bar button ends the session without a confirmation question.
- Tinting editors and other dialogs during a session, not only the main window and detached gramplets.
- The working name "Pruned Branch" can suggest that records were deleted.
- Gramps 5.2 support (BSDDB and the 5.2 database API); see the [Gramps 5.2 database code](https://github.com/gramps-project/gramps/tree/maintenance/gramps52/gramps/gen/db).

### Beyond scope
- Third-party addons that run their own SQL queries see the whole tree.
- Title bars drawn by the window manager (not by GTK) cannot be colored.
- Gramps core changes, such as a branch-aware database layer; reference: [ReferencedBySelectionProxyDb](https://github.com/gramps-project/gramps/blob/maintenance/gramps60/gramps/gen/proxy/referencedbyselection.py).
