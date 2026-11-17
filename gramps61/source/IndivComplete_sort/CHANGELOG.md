# Complete Individual Report (Sorted) — Changelog
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [GenealogicalNumberingAPI.md](GenealogicalNumberingAPI.md)

## 1.1.0
First version of the fork, as the addon "Complete Individual Report (Sorted)" (IndivComplete_sort).
- **Sort the people.** New "Sort by" option: surname, given name and birth date (default); surname, given name and Gramps ID; birth date; Gramps ID; kinship from the Filter Person; or numbering system. The order is the same on every run (the built-in report in Gramps 6.0 lists people in an unpredictable order).
- **Better birth date sorting.** Uses the Gramps date sort value, so qualified dates ("about", "before", ranges), dates before the year 1000 and other calendars sort correctly. Falls back to a baptism or christening date. New option "List people without a birth date first".
- **Kinship order.** Adapted from the KinSorter by Matthias Basler (MantisBT 0010362): each family together, children by birth date. Unrelated people are listed at the end instead of being dropped, a couple who both had earlier families is no longer skipped, and very deep trees no longer risk a recursion limit.
- **Genealogical numbering.** New Ancestor and Descendant numbering options for a chosen Center Person: Sosa-Stradonitz (Kekulé), Ahnentafel, Simple, Henry, Modified Henry, d'Aboville, de Villiers/Pama, Meurgey de Tupigny and Record (Modified Register), or a person attribute. Each menu item shows a short example.
- **Identifiers replace the Gramps ID after names.** The bracket after each name shows the ancestor number, else the descendant number, else the Person label. People who appear more than once in the tree show every number.
- **Person label and Family label.** "Include Gramps ID" becomes "Person label": Do not include, Gramps ID, or an attribute value (falling back to the Gramps ID). Saved settings and Books from the built-in report carry over. New "Family label" line in the Families section.
- **Attribute submenus.** The Attribute item in each identifier menu opens a list of attribute types and shows the type used last, which is remembered in `IndivComplete_sort.ini`.
- **Center Person list.** Offers the Home Person, the active person, and bookmarked and recently viewed people, with a button to choose anyone else.
- **Clearer tabs.** Options regrouped into People, Display, Include, Identifiers and Sections, replacing "Report Options (2)" and "Include (2)".
- **Reusable module.** The numbering and identifier options are in `genealogical_numbering.py`, for use by other reports. See [GenealogicalNumberingAPI.md](GenealogicalNumberingAPI.md).

## 1.0.0
The Complete Individual Report built into Gramps 6.1 (`gramps/plugins/textreport/indivcomplete.py`), used as the base of this fork.

## Outstanding issues
Known limitations and ideas for later versions.

### Planned / NYI
- Settings did not come back between runs on one test system. Saving and loading work in tests with the real report dialog; the cause is being investigated.
- Translations for the new strings ("Person label", "Family label", "Ancestor numbering system", "Descendant numbering system", "Ahnentafel numbering", "Identifiers" and help texts).

### Needs discussion
- Whether `genealogical_numbering.py` should become a shared library addon, or be proposed for Gramps core, so other reports can use the same identifier options.
- The active person is not known when a Book runs later; the Home Person is used instead.

### Beyond scope
- The "Complete Individual Report 2" layout, the "Complete Kinship report" and the enhanced ODF exporter from [MantisBT 0010362](https://gramps-project.org/bugs/view.php?id=10362).
- On the command line, person-based filters (such as "Descendants of") give "Empty report"; the built-in report does the same.
- In the built-in Detailed Descendant Report, Modified Henry numbering uses plain Henry numbers from the third generation.
