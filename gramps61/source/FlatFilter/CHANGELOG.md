# Changelog — Flat Filter

[Read Me](README.md) ● [Change Log](CHANGELOG.md)

All notable changes to this gramplet. Newest first.

## 2.0.0
This release gathers everything since Doug Blank renamed the gramplet "Relationship Filter", including an earlier revision that was never publicly released.

### Changed
- Renamed back to **Flat Filter**, the name Paul Womack (BugBear) gave the original. The plugin id, folder, file names, gramplet class and settings file all use the new name: `Flat Filter`, `FlatFilter/`, `FlatFilter.py`, `FlatFilter.gpr.py`, `FlatFilter.ini`. The new name also brings the gramplet back up near the top of the long gramplet list in the Add a Gramplet menu.
- The **Use fuzzy matching (SoundEx)** checkbox is now **Use fuzzy matching**, followed by a popup menu that chooses the phonetic system. Soundex is the default. The menu remembers the choice as soon as it changes, without needing **Save settings**.
- Phonetic matching now encodes each word of a name on its own, so `John` finds `John Henry`. Before, the whole field was encoded as one word.
- The Help button is now labeled **Help**, with a small icon, and opens a translated README when one exists for the Gramps language. Its code is built into `FlatFilter.py`; the separate `help_doc_button.py` file is no longer shipped.
- The undocked window now opens large enough (560 × 700) to show every row without scroll bars, instead of the Gramps default of 400 × 300.
- Less blank space around the Find / Reset and Define filter button rows.
- Spaces at the start or end of a text box are removed when you move to another box, press Enter, or click **Find**. Matching already ignored them; now the box shows exactly what is searched.
- **Find** with every field blank now shows everyone without running a filter, as the core Filter sidebar does. Before, it ran a filter with no rules, which checked every person (with a progress window when the Filter Progress addon is installed) only to match them all.

### Added
- When the Fuzzy Matching addon is installed and enabled, the popup menu offers every phonetic system that addon provides (Soundex, NYSIIS, Match Rating Approach, Metaphone, and any system added to it later), through its "Fuzzy Match API" plugin. Each system has a tooltip describing it. Without that addon, the menu offers the Soundex built into Gramps.

### Notes
- Settings saved by "Relationship Filter" (`RelationshipFilter.ini`) are not carried over, because the plugin id changed. Remove the old `RelationshipFilter` folder so the two gramplets do not appear side by side.
- The rule classes take an `encoder` argument (a function returning a set of phonetic codes) instead of `use_soundex`.

## Unreleased revision (1.0.1 in its .gpr.py)
Announced as available, but never publicly released.

### Added
- Gramps 5.2 support alongside Gramps 6.0 and later, from one file. Every rule class implements both `apply_to_one()` (Gramps 6.0) and `apply()` (Gramps 5.2).
- The **Person** row splits the given name and the surname onto separate lines, each with its own row of **Include:** checkboxes for the name parts to search: Title, Given, Call, Nick and Alternatives; Prefix, Surname, Suffix, Clan and Alternatives. This makes null (`^$`) and not-null (`.+`) regular expression searches usable.
- **Use fuzzy matching (SoundEx)** checkbox, mutually exclusive with regular expression matching.
- Right-click **Save settings** for the checkbox states, stored with the Gramps configuration system next to the gramplet. **Reset** restores the saved states.
- Help button beside **Find** and **Reset**, opening the README in Markdown Dash when available, or the help page in a web browser.

### Fixed
- Replaced `get_raw_person_data()` with `get_person_from_handle()`, which raised `AttributeError` on Gramps 5.2.

## Relationship Filter (Doug Blank)
- Reworked Flat Filter and renamed it "Relationship Filter". Supported Gramps 6.0 only.

## Flat Filter (Paul Womack, BugBear)
- Original gramplet: a People view sidebar filter that finds people by the names of their father, mother, spouse, siblings and children.
