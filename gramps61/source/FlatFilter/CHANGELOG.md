# Changelog — Flat Filter

[Read Me](README.md) ● [Change Log](CHANGELOG.md) ● [Define Filter](DefineFilter.md)

All notable changes to this gramplet. Newest first.

## 2.0.2
- A filter rule named "Flat Filter rule" (class `FlatFilterRule`), registered in `FlatFilter.gpr.py` for Gramps 6.0 and later. Saved Flat Filter searches use it to stand in for each Flat Filter rule. It also appears in the Filter Editor, but it is not meant to be added by hand.

## 2.0.1
Kari Kujansuu made the **Define filter** button work with Flat Filter, so a Flat Filter search can be saved as a custom filter. How it works, and what is still missing, is documented in [DefineFilter.md](DefineFilter.md).

### Added
- **Define filter** (Gramps 6.0 and later) now saves Flat Filter searches. It opens the Define Filter dialog with one rule for each box that is filled in, including **Probably Alive**, and the comment "Created by the Flat Filter gramplet on" followed by the date. After you click OK, the filter is in the custom filter list, so it can be chosen in the Filter sidebar, in reports, and anywhere else Gramps offers custom filters. Before, the dialog opened, but the saved filter lost its Flat Filter rules the next time Gramps started, because Gramps could not find those rule classes by name.
- A Generic filter rule added

### Known limitations
- **Use fuzzy matching** cannot be saved yet, so **Define filter** is dimmed while it is checked, with a tooltip saying so.
- Changes to the **Include:** checkboxes of the Person row are not saved. The saved filter then searches every name part, so it can match more people than **Find**.
- Saved Flat Filter searches need Flat Filter to be installed and active.

### Notes
- Filters saved from this version record the class names `FlatFilterRule`, `HasNamedFather`, `RegExpPersonal` and so on in `custom_filters.xml`. Renaming any of these classes in a later version would break filters that people have already saved.

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

## 1.0.1
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

## Flat Filter 1.0.0 (Paul Womack, BugBear)
Initial release.
- A People view sidebar filter that finds people by the names of their father, mother, spouse, siblings and children, and by their own name.
- Each relationship row has separate boxes for the given name and the surname.
- **Probably Alive** date field, using the standard Gramps `ProbablyAlive` rule.
- One **Use regular expressions** checkbox switching every box to regular expression matching.
- For a female person, the own-name surname box also searches the surnames of her spouses.
