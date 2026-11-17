# What's Next? - Changelog

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable differences between Beta What's Next and the built-in "What's Next" gramplet in Gramps.

Baseline for comparison: "What's Next" version 1.0.0, as registered in [gramplet.gpr.py](https://github.com/gramps-project/gramps/blob/5cebb2c55fdbb0a92428625d409918216409db70/gramps/plugins/gramplet/gramplet.gpr.py#L445), using the source file [whatsnext.py on maintenance/gramps61](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/plugins/gramplet/whatsnext.py) (fetched October 2026). The `maintenance/gramps52` copy, also registered as 1.0.0, has the same behavior; it differs only in the license header wording and one tuple-unpacking style change.

## [0.2.0]
### Added
- Three tags that shape the list, each applied to a Person or a Family. Complete and Ignore hide the object from the list, while the search still travels through it to reach relatives. Prune hides the object and the search does not travel through it, so nothing reached only through it is examined.
- A row of buttons along the bottom of the gramplet. The batch buttons "Complete", "Ignore" and "Prune" tag every Person and Family currently shown, in one step, and leave out the Home Person. The list refreshes at once. A Help button sits on the far left.
- A menu on a right-click over any shown Person or Family: "Review" opens the editor, three items tag that one object as Complete, Ignore or Prune, and "Organize Tags" opens the tag organizer. A right-click anywhere else keeps the usual Copy and Select All menu, with "Organize Tags" added at the bottom.
- Default tags, created at the top of the tag list the first time one is needed if none has been chosen in the options: "Completed" (grey), "Ignored" (pale grey) and "Pruned" (dark amber). The created tag is then remembered as the chosen tag for that purpose.
- A background search. The list is built a little at a time, so a large tree no longer freezes the window, and a new refresh replaces a search that has not finished.
- Settings of the gramplet are stored in the folder of the gramplet, next to the module, with a `[meta]` block that records the plugin and a schema version. An old settings file from an incompatible version is ignored rather than misread.
- A short tooltip for every option, shown over both the label and the control.
- The list refreshes when a tag is added, changed or deleted, so deleting the Ignore or Prune tag brings the objects back at once.
- A "Show suggested Next Steps" option, on by default, that turns the guidance steps and the 👣 suggestions off for a shorter list.
- A "Report a missing parent family" option, on by default.

### Changed
- A finished Person or Family that carries the completion tag is now hidden from the list, instead of being listed with a "not complete" note. The list holds the research findings and the Home Person line, and nothing else.
- The tag that stops the search is now named "Prune". A tag chosen as the "Ignore" tag in an earlier version is carried forward as the Prune tag.
- Each of the three tags must be a different tag. When two are set to the same tag, the later one in the order Complete, Ignore, Prune is treated as not chosen, so Prune can never act as Complete.
- The three chosen tags are stored in the settings file of the gramplet, and a tag created by a batch button is saved there at once and appears in the options. Tags saved by an earlier version are carried forward once.
- The two completion tags of earlier versions, one for People and one for Families, are now a single "Complete" tag that applies to either.
- The search reads the preferred Birth and Death events of a Person, rather than every event of every Person, so it does less database work on a large tree.
- Each refresh clears the clickable links of the previous list, so moving the mouse over the list no longer grows slower over the life of the session.
- The guidance text (no tree loaded, empty tree, no Home Person) and the 👣 suggestions are governed by the new "Show suggested Next Steps" option, in place of the earlier fixed module switch.

### Removed
- The lines that listed every Person or Family without a completion tag. A completion tag now hides the object rather than listing it.
- Two debugging numbers that reached user-visible messages in the earlier beta ("591 family not complete" and a numbered "person not complete").

### Fixed
- The missing-parent report, which the earlier beta built but never displayed, is shown again. People with no parent family are listed once more, and the new "Report a missing parent family" option can turn the report off.

## [0.1.11]
### Added
- Separate registration (`id="Beta What's Next"`, class `BetaWhatNextGramplet`) so the beta can run beside the built-in gramplet. Registers on Gramps 5.2.0 through 6.2.0 only, using `VERSION_TUPLE` and `major_version` from `gramps.version`.
- Guidance when no Family Tree is loaded, with steps for creating, loading or importing a tree. The built-in gramplet showed only "No Family Tree loaded."
- Guidance when the tree contains no people, with steps for adding a family or importing people. The built-in gramplet gave no message for an empty tree and showed "No Home Person set." instead.
- Guidance when no Home Person is set, with steps for setting one. The built-in gramplet showed only "No Home Person set."
- A first line naming the Home Person, so the starting point of the search is visible.
- A 👣 next-step suggestion for a missing Birth event.
- A refresh when an event is added, changed or deleted, so fixing a birth date or place removes the old problem from the list.

### Changed
- Several option labels were shortened, for example "Minimum number of items to display" to "Search Quota", and "Descendant generations per ancestor generation" to "Depth per loop".
- The default "Depth per loop" was lowered from 2 to 1, and the default "Pause search expansion" was raised from 1 to 5, so the search stays closer to direct ancestors for longer.
- Several problem descriptions were reworded to read as complete sentences.
- The help link points to the beta repository rather than the Gramps wiki manual.

## Outstanding issues
### Planned, not yet implemented
- The 👣 suggestions for a missing spouse, father, mother, parent family and marriage event are written in the source but not yet shown.
- The individual tests (name, birth, death, dates, places, marriage, relationship type) are to become separate options, through the same registry that already carries the "Report a missing parent family" option.
- The data integrity tests from the [Verify the Data](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/plugins/tool/verify.py) tool are to be offered as further options, so one gramplet can report the same concerns.

### Needs discussion
- Whether a batch "Complete" should tag every shown object, or only the shown objects that have no remaining finding, since marking an object Complete is a claim that its gaps will never be filled.

### Beyond scope
- Moving the Search Quota and the two loop controls into the settings file of the gramplet. For now they stay in the gramplet bar, as in the built-in gramplet, while the tags and the newer options are kept in the folder of the gramplet.
