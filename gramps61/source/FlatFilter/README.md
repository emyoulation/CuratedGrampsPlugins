# Flat Filter

[Read Me](README.md) ● [Change Log](CHANGELOG.md)

A Gramps gramplet that adds a sidebar filter to the **People** view. It finds people by the names of their relatives (father, mother, spouse, siblings and children), by their own name, by an optional "probably alive" date, and with several text-matching modes.

## Installation
1. Install the gramplet with the Addon Manager.
2. Restart Gramps (or use **Help → Reload Plugins**).
3. Open the **People** view.
4. In the sidebar, choose **Gramplets → Add a Gramplet → Flat Filter**, or add it from the gramplet selector of the sidebar.

If an older copy named "Relationship Filter" is installed, remove it. Settings saved by that copy are not carried over.

## Compatibility
Works on Gramps 5.2 and Gramps 6.0 and later. Gramps 6.0 renamed the internal `Rule.apply()` method, which every filter rule must implement, to `apply_to_one()`. The rule classes in this addon implement both names (one calls the other), so the same file runs on either version.

## What it does
The gramplet places a set of name-search rows in the sidebar. Most rows have two text boxes, a given-name box and a surname box, which are combined into one filter when you click **Find**. The **Person** row is the exception: its given-name and surname boxes are on separate lines, each followed by its own row of **Include:** checkboxes (see below).

![undocked Flat Filter gramplet](media/screenshot.png)

| Row | Matches people who... |
|-------------------------|---------------------------------------------------------------------|
| Person | ...have this given name / surname themselves |
| Father | ...have a father with this given name / surname |
| Mother | ...have a mother with this given name / surname |
| Spouse | ...have a spouse with this given name / surname |
| Sibling 1, Sibling 2 | ...have a sibling with this given name / surname |
| Child 1, Child 2 | ...have a child with this given name / surname |

Any row you leave blank is skipped. Filling in more than one row combines them with an implicit **AND**. For example, a surname in *Person* and a given name in *Father* finds people with that surname whose father has that given name.

The **Probably Alive** field accepts a date (for example `before 1900`, or a date range). It uses the standard Gramps `ProbablyAlive` rule to keep only people who were plausibly alive around that time.

## Include: checkboxes (Person row only)
A Gramps name record stores several parts: a title, a call name, a nickname, a surname prefix, a suffix, a family nickname (labeled "Clan" here because it is short), and more, in addition to the given name and surname. By default, matching a name tests **all** of these parts. That can give surprising results: a search for an *empty* given name (`^$`, see below) also matches anyone with an empty *title*, which is nearly everyone.

The two checkbox rows of the **Person** row narrow the search to the parts you mean, for that row only. Every other row (Father, Mother, Spouse, and so on) still searches all parts.

- Below the given-name line: **Title**, **Given**, **Call**, **Nick**, **Alternatives**
- Below the surname line: **Prefix**, **Surname**, **Suffix**, **Clan**, **Alternatives**

Only the checked parts are tested against the text you typed. **Alternatives** (in both rows, set separately) decides whether *alternate* names are searched as well as the primary name. For example, you might search alternate names for a surname but not for a given name.

**Defaults:** Given + Alternatives, and Surname + Alternatives, are checked. Everything else starts unchecked. This is deliberately narrow, so a pattern like `^$` behaves as expected (see the Regular expression examples below) instead of matching almost everyone through a blank title or suffix.

### Saving your own checkbox settings
Right-click **any** checkbox in the gramplet (either Include: row, or the **Use pattern matching (Regular expressions)** / **Use fuzzy matching** checkboxes below), or its label, to open a small context menu with **Save settings**.
![Checkbox context menu](media/menu.png)

**Save settings** writes the state of all twelve checkboxes (five personal, five surname, and the two matching-mode checkboxes) to `FlatFilter.ini`, in the folder of the gramplet. It uses the Gramps configuration system, the same one other Gramps addons use. The gramplet reloads these settings the next time it starts, and the **Reset** button restores them too.

The phonetic system chosen in the **Use fuzzy matching** popup menu does not need **Save settings**. It is remembered as soon as you change it.

## Help button
The **Help** button next to **Find** / **Reset** opens this README. It opens in a Markdown Dash window if that addon is installed and enabled, or in your web browser otherwise. If a translation of this README exists for your Gramps language, that translation opens instead.

## Matching modes
Two checkboxes control how the text you type is interpreted. They are mutually exclusive: checking one unchecks the other.

- **Use pattern matching (Regular expressions)** treats the text as a Python [Regular expression](https://gramps-project.org/wiki/index.php/Gramps_Glossary#regex) instead of a plain substring.
- **Use fuzzy matching** treats the text phonetically, so names that *sound* alike match even when they are spelled differently (for example `Smith` and `Smyth`). The popup menu after the checkbox chooses the phonetic system. Soundex is the default.

If neither box is checked, the text is matched as a plain, case-insensitive substring anywhere in the field (the normal Gramps default).

Like the Include: checkboxes, these two checkboxes are covered by **Save settings** and **Reset** (see above).

## Phonetic systems
The **Use fuzzy matching** popup menu lists the phonetic systems that are available:

- Without the Fuzzy Matching addon, only **Soundex** (built into Gramps) is listed.
- With the Fuzzy Matching addon installed and enabled, every system that addon provides is listed, for example Soundex, NYSIIS, Match Rating Approach and Metaphone. Hover over the menu to see a description of the selected system.

If a remembered system is no longer installed, the menu shows Soundex until you choose another system.

## Regular expression examples
When **Use pattern matching (Regular expressions)** is checked, the text in a given-name or surname box is matched against that field with the Python `re` module. Some practical examples:

| Pattern | Finds people whose... | Typical use |
|---------|-------------------------------|---|
| `^$` | given name (or surname) field is **empty** | A "Null" pattern |
| `.+` | given name (or surname) field is **not empty** | A "not-Null" pattern |
| `^Mc` | surname starts with `Mc` (e.g. `McDonald`, `McKay`) | Prefix search |
| `sen$` | surname ends in `sen` (e.g. `Jensen`, `Andersen`) | Suffix search, useful for Scandinavian patronymics |
| `^(John\|Jon\|Jonathan)$` | given name is exactly `John`, `Jon`, or `Jonathan` | Exact match against a small set of name variants |
| `[aeiou]{3,}` | field contains three or more vowels in a row | Catching unusual spellings or OCR/transcription errors |
| `(?i)^o'` | surname starts with `O'` in any letter case (e.g. `O'Brien`, `o'brien`) | Case-insensitive prefix match |

* **A "Null" pattern** finds records missing that piece of data. For example, put `^$` in the *Person* surname box to find everyone with no surname recorded. On the **Person** row, this only works as expected when the Include: checkboxes are narrowed to the one field you mean (the defaults already do this). With every part checked, `^$` also matches anyone with a blank title, suffix, and so on.
* **A "not-Null" pattern** is the opposite. Put `.+` in the *Father* given-name box to find everyone whose father has a recorded given name.
* **Case-insensitive prefix match**: the substring mode is already case-insensitive, but this shows how to force it inside a pattern.

## Fuzzy matching example
With **Use fuzzy matching** checked and **Soundex** chosen, typing `Smith` in a surname box also matches `Smyth`, `Smithe`, and other names with the same Soundex code. This helps when a family name was spelled differently across historical records.

Each word of a name is encoded separately, so `John` in a given-name box also finds `John Henry`.

**Note:** a phonetic code covers the *whole* word. It is not a prefix search. Typing `Thom` matches `Thom`, but not `Thomas` (the Soundex codes are `T500` and `T520`). Type the full name you expect, not a shortened form.

## Notes for developers
- The rule classes (`RegExpPersonal`, `RegExpFamily`, `HasNamedFather`, `HasNamedMother`, `HasNamedSpouse`, `IsSiblingofNamedSibling`, `HasNamedChild`, `HasName`) are ordinary Gramps `Rule` subclasses and can be reused or combined in custom filters.
- `RegExpPersonal` and `RegExpFamily` accept optional `personal_fields` / `surname_fields` (a subset of `PERSONAL_FIELDS` / `SURNAME_FIELDS`) and `include_alternates` arguments, which restrict the name parts tested and whether alternate names are tested. Only the "Person" row of the sidebar passes these (from its Include: checkboxes). Every other row omits them and searches everything.
- Phonetic matching is selected with an `encoder` argument: a function that takes one word and returns a `set` of codes, or `None` for no phonetic matching. A field matches when any word in it shares a code with any word of the search text.
- The phonetic systems come from the `phonetic_codes` registry of the Fuzzy Matching addon, reached through its "Fuzzy Match API" GENERAL plugin (`BasePluginManager.get_plugin()` then `import_plugin()`), as described in `FuzzyMatchAPI.md` of that addon. If that plugin is missing or fails to load, only the built-in `gramps.gen.soundex` is offered.
- The sidebar UI is built on the Gramps `SidebarFilter` base class (`gramps.gui.filters.sidebar.SidebarFilter`). The matching-mode checkboxes, the phonetic system popup menu and both Include: rows are attached directly to `self.grid`.
- Matching a `HasName`-derived rule against a `RegExpFamily` field for a female person also searches the surnames of her spouses, since married women in many record-keeping traditions took the surname of their spouse.
- Settings are stored with the Gramps configuration system (`gramps.gen.config.config.register_manager`) as `FlatFilter.ini` in the addon folder: the Include: checkboxes, the two matching-mode checkboxes (`[matching]` `regex`, `fuzzy`) and the phonetic system (`[matching]` `algorithm`). The file also stores the plugin id and a config schema version under `[meta]`. If either does not match what the running code expects, all saved settings are reset to their defaults rather than risk misreading a value from an incompatible revision.
- Every rule class implements both `apply_to_one()` (called by Gramps 6.0) and `apply()` (a one-line alias for Gramps 5.2). See Compatibility above.
- **Do not use `db.get_raw_person_data()` / `db.get_raw_family_data()` for anything beyond a bare lookup.** They look like a good Gramps 6.0 speed-up, but the result depends on backend and version: on the Gramps 5.2 dbapi backend they return a plain pickled tuple with no attribute access, while the Gramps 6.0 JSON-backed database returns a dict-like wrapper that supports attribute access. Code that assumes the latter raises `AttributeError` on the former. This was tried, failed in the field, and was reverted to `get_person_from_handle()` / `get_family_from_handle()`, verified against real `gramps==5.2.4` and `gramps==6.0.8` installs.
- The Help button code is pasted into `FlatFilter.py` from the reference `help_doc_button.py` kept with MarkdownUtils (see `HelpDocButton.md` there), between `BEGIN HELP BUTTON BLOCK` and `END HELP BUTTON BLOCK` markers. No separate module ships with this addon. If the button row cannot be found, the gramplet simply has no Help button.
- `SidebarFilter` wraps each button row in a 12 px border; `Filter._tighten_button_rows()` replaces it with smaller margins. The undocked window size is set by `detached_width` / `detached_height` in `FlatFilter.gpr.py`.

## License
GNU General Public License v2.0 or later, consistent with Gramps itself.
