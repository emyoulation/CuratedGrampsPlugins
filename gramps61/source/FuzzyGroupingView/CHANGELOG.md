# Fuzzy Grouping — Changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 0.2.0
Changes since the 0.1.2 release.

### Added
- Right-click menu: a "Grouping (Phonetic encoding)" submenu chooses the phonetic system at once, with None and every available system. Its mark follows changes made in Configure and in the Flat Filter and Fuzzy Matching gramplets.
- Expand all Nodes opens the groups one at a time: the groups on screen first, then the ones below, then the ones above. After 2 seconds a progress window with a Cancel button appears, and afterward the group that was at the top of the view goes back to the top.
- Configure, Subsorting tab: a "Use the whole list" check box. When it is off, only number 1 of the subsort order is used, which is the fastest.
- Cancel in the progress window stops the subsorting and turns "Use the whole list" off. An index build that did not finish (a crash or a forced quit) also turns it off at the next start. The status bar says so after the next build.
- Diagnostics: start Gramps with `gramps -d fuzzygroupingview` to log the time of each step of every index build, of phonetic system changes and of Expand all Nodes.

### Changed
- Expand all Nodes is much faster in large trees: the row positions are kept in a table instead of being searched again for each group (before this change, Expand all took about 40 seconds for 61,052 people in 8,654 groups).
- Subsorting is faster: a build sorts on the first subsort field only, then adds the next fields only for people who are still tied.
- The progress window has a second phase, "Subsorting people with equal sort values", and its Cancel button stays responsive during slow phases.
- The "Default" sort Name format now removes the surname parts from the built-in name formats too. In 0.1.2 only formats written with keywords lost their surnames. The Default line shows the cleaned format.
- The Help URL points to the addon folder on GitHub.
- Code brought to the Gramps AGENTS.md guidelines (type hints, docstrings, Black, pylint, mypy), with unit tests in the `test` folder.

### Fixed
- The Configure dialog now opens the first time the view is shown, also when Gramps was restarted after the install before the view was opened.

### Known issues
- Subsorting needs PyICU. With only the system locale sorting, the subsort fields can run together.
- When the Display Name Editor is open from this view, clicking "Edit..." for Name format in Preferences fails with an error. This is a bug in Gramps core, which does not check for an editor that is already open.
- A person added or edited after a build gets the full subsort key, and can sit beside a tied person in the wrong order until the next build.

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
- A "None" choice turns phonetic matching off and groups on an exact match of the preferred surname (or its "Group as" value), as in the Grouped People view.
- Built-in Gramps Soundex is the default system and the fallback. The other systems come from the Phonetic Filter Rules addon (any RULE plugin with an id that starts with `FuzzyMatchingEncoder:`). Systems that return several codes for one name use the lowest code, so each person is in one group.
- Group rows show the spellings in the group (most used first, up to four, then "+N") followed by the code in brackets.
- Toolbar Help icon. Its tooltip says whether a click shows the README in Markdown Dash or opens the Help URL in a browser.
- Configure, Columns tab: a "Grouping:" choice between "Sample Surname" (the default; alphabetical by the most used spelling in each group, in locale order) and "Fuzzy grouping ID" replaces the "first column cannot be changed" label. The first column is now labeled "Grouping".
- Configure, Columns tab: a "Fuzzy (Phonetic encoding) system:" list below the Grouping choice chooses the phonetic system.
- Configure, Subsorting tab: a Name format used only for sorting, which never changes the application Name format preference. The "Default" format is the current Display name format without its surname parts. The edit icon opens the Display Name Editor, and closing the editor selects the format that was last selected in it.
- Configure, Subsorting tab: a numbered subsort order, changed by drag and drop or by typing a number. The initial order is Name format, Birth Date, Death Date, Spouse, Last Changed, then the other columns in their Display list order.
- Configure opens by itself the first time the view is shown, when no `FuzzyGrouping.ini` exists yet.
- Settings are kept in `FuzzyGrouping.ini` in the addon folder, with a `[meta]` block.
- After a change in Configure, the view refreshes 2 seconds after the last change, or at once when Configure is closed.
- A progress dialog appears when building the grouping index takes more than 1 second.
- Default sidebar gramplets: Flat Filter first and Fuzzy Matching second (each only when installed and not hidden), then the Gramps Person Filter. "Restore default gramplets" in the sidebar uses the same order, checked when it is chosen.
- Custom view icon `media/fuzzy-grouping.svg`, with the core `gramps-tree-group` icon as the fallback.
- Encoder plugins hidden in the Plugin Manager leave the phonetic system list the next time the view opens. If the view was using one, it goes back to Soundex until the plugin is shown again; the saved choice is kept.
- The phonetic system is shared both ways with the Flat Filter and Fuzzy Matching gramplets when they are in this view. A change made in a gramplet regroups the view 2 seconds later, or with the next Find.

### Known issues
- Subsorting needs PyICU. With only the system locale sorting, the subsort fields can run together.
- When the Display Name Editor is open from this view, clicking "Edit..." for Name format in Preferences fails with an error. This is a bug in Gramps core, which does not check for an editor that is already open.
- The Help URL `Addon:Fuzzy_Grouping` pointed to a wiki page that had not been written yet (fixed in 0.2.0).
