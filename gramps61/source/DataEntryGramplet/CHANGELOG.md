# Change Log - Data Entry Gramplet
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

Portions of this addon were generated with AI assistance; release entries note the AI tool used where a release was substantially AI-generated.

## v1.1.0
Supports Gramps 5.2 through 6.2 from one package. Includes the rework submitted to addons-source as a pull request (its `.gpr.py` reads 1.0.53), plus new features built on it. Generated with Claude Sonnet 5 (the rework) and Claude Opus 5.5 (the new features), Anthropic, from wish-coding by Brian McCullough.

* New: the New person area can be **linked to a person who is already in the tree**, so Add updates that person instead of creating a duplicate. Link by double-clicking a person in the Fuzzy Match Lookup window, by dropping a person on the area, or from the right-click menu. While linked, the title reads "Update person:" with the name, and a link symbol appears in the name field.
* New: Add **never duplicates a relationship or double-links a person in a family**. If the linked person is already in the family that Add would change (in any role), the family link is skipped, the events, sources and citation are still added, and the status bar says so.
* New: while linked, **Gender and Add relation are checked against the tree**. Both are filled in from the linked person; a choice that disagrees with what the tree records turns the error color, and its list offers the recorded value as a "Recorded as: ..." first line. Unlinking resets the title, colors and menus.
* New: **Fuzzy Match Lookup button** (magnifying glass) to the right of the New person "Surname, Given" field, shown while the Fuzzy Matching addon is installed and enabled. It opens the lookup window seeded with the surname (or, when the field is empty, the surname of the active person) and the given name as a filter, and selects the best match.
* New: **Add an Association** relation. It opens the Gramps Person Reference Editor (the active person is the default associated person) and adds the association to the new or linked person on Add, without a family link and never twice. The last association is remembered per family tree in `DataEntryGramplet.ini`, keyed by the database ID of the tree.
* New: **Update self** relation, for when both areas show the same person: Add then adds events, sources and citation to that person without changing any family.
* New: **Person drag and drop**. Drop a person on the Active person area to make them active (after confirming if there are unsaved edits), or on the New person area to link them. Text fields still accept text drops.
* New: **right-click menus** for both areas. An area that shows a person starts with the People view commands (Back, Forward, Home, Set Home Person, Add, Edit, Delete, Merge, Quick View, Web Connection); each area then adds its own commands (Save and Abandon; Fuzzy Match Lookup, Unlink, Add, Copy Active Data and Clear).
* New: **Citation menu** on the source radio button line and the citation line (Add, Edit, Quick View for the chosen citation). A citation added there becomes the chosen citation.
* New: **four configurable event rows** in the New person area, each with an event type menu (defaults Birth, Residence, Death, Burial); the choices are remembered in `DataEntryGramplet.ini` next to the addon. The first Birth and Death rows become the birth and death of the person.
* New: **Enter Sources / Select Citation / None** choice replaces the "Sources?" check box. Select Citation attaches one existing citation to the records you tick; Copy Active Data then also fills the Residence date from the citation.
* Changed: a refused Add (missing gender, same-gender spouse and so on) now **saves nothing**; the whole Add is rolled back and the reason is shown, so no partial person is left behind.
* Changed: **unsaved edits are visible**. Abandon turns red while the Active person area has unsaved changes, and its tooltip lists them; the area stops following the active person until you Save or Abandon.
* Changed: a linked person keeps a birth or death they already have; a new Birth or Death row is added as an ordinary event.
* Changed: the form is one aligned grid that scrolls, with the buttons pinned to the bottom; it fits down to about 315 pixels wide.
* New: **Help button** at the far left of the bottom line, opening this README in Markdown Dash (or the wiki page when Markdown Dash or MarkdownUtils is not available). It is hidden while the gramplet is undocked, since the undocked window has its own Help button.
* Changed: the Save, Abandon, Add, Copy Active Data and Clear buttons have icons to the left of their labels, and the name field has a clear (eraser) icon.
* Fixed: dropping a person no longer causes GTK critical warnings in the terminal; drops are handled after the drag has finished.

## v1.0.56 (8 Sep 2026)
Gramps 6.1.

* Translations: template regenerated and translation files remade as needed. No code changes.

## v1.0.55 (2 Jun 2026)
Gramps 6.1.

* Translations: updated from Weblate (including new Turkish and Traditional Chinese). No code changes.

## v1.0.54 (21 Apr 2026)
Gramps 6.1.

* Fixed: a crash when pressing Add, or editing the active person, with no family tree open (bug 0012691). The gramplet now shows "No Family Tree is open." instead. The same fix was released for Gramps 6.0 as v1.0.53.

## v1.0.53 (17 Apr 2026)
* Gramps 6.1: first build for Gramps 6.1. No code changes.
* Gramps 6.0 (released 21 Apr 2026 under the same number): includes the bug 0012691 fix described under v1.0.54.

## v1.0.50 to v1.0.52 (Jan - Feb 2025)
Gramps 6.0.

* Builds for Gramps 6.0, a help link to the wiki page, and translation updates from Weblate. No code changes.

## v1.0.49 (24 Oct 2024)
Baseline for this change log is **v1.0.49**, the Gramps 5.2 release of the addon in `gramps-project/addons-source` ([maintenance/gramps52](https://github.com/gramps-project/addons-source/blob/maintenance/gramps52/DataEntryGramplet/DataEntryGramplet.py)). Newest releases are at the top, and the entries within each release are listed from most to least significant.

* Translations: Danish and Ukrainian added.
* The form at this release: an Active person block (name, gender, birth, death, with Save and Abandon) and a New person block (relation, name, gender, birth, death, with Add, Copy Active Data and Clear), with an optional source title for each field behind a "Sources?" check box.

## Outstanding issues
### Planned / NYI
* Custom (user-defined) event types are not offered in the event row menus.
* Move the "hide the Help button while undocked" behavior into MarkdownUtils `add_help_button()`, so every gramplet gets it (it lives in this addon for now).

### Needs discussion
* Version numbering: the queued addons-source pull request labels itself 1.0.53, the same number as the released Gramps 6.0 and 6.1 builds. This release uses 1.1.0 to supersede both.
* Should Add refuse, rather than only warn, when Gender or Add relation disagree with what the tree records for a linked person?
* Associations are stored on the New person and point at the associated person. Confirm this matches how users read the Associations tab (for example, which side of a godparent link holds the description).

### Beyond scope
* Same-gender spouses: use the Gramps Edit Family dialog.
