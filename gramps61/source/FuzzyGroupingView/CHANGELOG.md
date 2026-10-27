# Fuzzy Grouping — Changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 0.1.0
First version: a People category view that groups people by phonetically similar surnames.

### Forked from
- Source view: the Gramps core **Grouped People** view (`personview`), [gramps/plugins/view/persontreeview.py](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/plugins/view/persontreeview.py) on `maintenance/gramps61`, at commit `5cebb2c55fdbb0a92428625d409918216409db70`, forked on 2026-10-27.
- Source registration: [view.gpr.py lines 196–213](https://github.com/gramps-project/gramps/blob/5cebb2c55fdbb0a92428625d409918216409db70/gramps/plugins/view/view.gpr.py#L196-L213) at the same commit.
- The view code in `maintenance/gramps60` is identical to the source, and `maintenance/gramps52` differs only in the license header wording and one cosmetic tuple unpacking, so the addon targets Gramps 5.2 through 6.1.
- Renamed so that the addon installs beside the core view: module `fuzzygroupingview.py`, class `FuzzyGroupingView`, plugin id `fuzzygroupingview`, view name and title "Fuzzy Grouping".
- The registration drops `order=START`, so the addon does not replace Grouped People as the default view of the People category.

### Added
- Phonetic grouping: people are grouped by a phonetic code of the core group name, so "Group as" overrides and the surname group mapping table still apply.
- Built-in Gramps Soundex is the default system and the fallback. The other systems come from the Phonetic Filter Rules addon (any RULE plugin with an id that starts with `FuzzyMatchingEncoder:`). Systems that return several codes for one name use the lowest code, so each person is in one group.
- Group rows show the spellings in the group (most used first, up to four, then "+N") followed by the code in brackets.
- Toolbar menu button to choose the phonetic system. It shows the view icon and the name of the current system.
- Toolbar Help icon. Its tooltip says whether a click shows the README in Markdown Dash or opens the Help URL in a browser.
- Configure, Columns tab: a "Grouping:" choice between "Fuzzy grouping ID" (the default) and "Sample Surname" (alphabetical by the most used spelling in each group) replaces the "first column cannot be changed" label. The first column is now labeled "Grouping".
- Configure, Subsorting tab: a Name format used only for sorting, which never changes the application Name format preference. The "Default" format is the current Display name format without its surname parts. The edit icon opens the Display Name Editor, and closing the editor selects the format that was last selected in it.
- Configure, Subsorting tab: a numbered subsort order, changed by drag and drop or by typing a number. The initial order is Name format, Birth Date, Death Date, Spouse, Last Changed, then the other columns in their Display list order.
- Configure opens by itself the first time the view is shown, when no `FuzzyGrouping.ini` exists yet.
- Settings are kept in `FuzzyGrouping.ini` in the addon folder, with a `[meta]` block.
- After a change in Configure, the view refreshes 5 seconds after the last change, or at once when Configure is closed.
- A progress dialog appears when building the grouping index takes more than 1 second.
- Custom view icon `media/fuzzy-grouping.svg`, with the core `gramps-tree-group` icon as the fallback.
- Encoder plugins hidden in the Plugin Manager leave the phonetic system menu the next time the view opens. If the view was using one, it goes back to Soundex until the plugin is shown again; the saved choice is kept.
- The phonetic system is shared both ways with the Flat Filter and Fuzzy Matching gramplets when they are in this view. A change made in a gramplet regroups the view 5 seconds later, or with the next Find.

### Known issues
- Subsorting needs PyICU. With only the system locale sorting, the subsort fields can run together.
- When the Display Name Editor is open from this view, clicking "Edit..." for Name format in Preferences fails with an error. This is a bug in Gramps core, which does not check for an editor that is already open.
- The Help URL `Addon:Fuzzy_Grouping` points to a wiki page that has not been written yet.
