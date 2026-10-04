# Change Log - Fuzzy Matching gramplet
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [Phonetic Filter Rules](RulesREADME.md) ● [adding Phonetic systems (for developers)](FuzzyDev.md) ● [Fuzzy Match API](FuzzyMatchAPI.md)

## Origin

`FuzzyMatchingGramplet.py` was forked on **6 Sep 2026** from Gramps' own
built-in **SoundEx** gramplet,
[`gramps/plugins/gramplet/soundgen.py`](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/plugins/gramplet/soundgen.py)
(`maintenance/gramps61` branch), which this addon's own file header
still carries forward the copyright of:

* Copyright (C) 2000-2006 Donald N. Allingham
* Copyright (C) 2008 Brian G. Matherly
* Copyright (C) 2010 Jakim Friant

Everything from the "matching people, not just a code" workflow
onward - the surname-match search, the cached per-tree phonetic index,
background indexing, active-person sync, filter creation, and the
features below - is new work built on top of that original gramplet,
not present in `soundgen.py` itself.

Portions of this addon were generated with AI assistance; see
[README.md](README.md#ai-assisted-contribution-disclosure) for the
project's AI-generated-code disclosure. Version entries below note the
AI tool used where a version was substantially AI-generated.

## v0.5.1 (15 Sep 2026)

* Fixed: a person with a compound/double surname (e.g. "Thompson
  McCullough", stored as two separate `Surname` pieces on one `Name`)
  was invisible to phonetic search entirely - findable under neither
  piece - because indexing used `Name.get_surname()`'s single,
  connector-joined string ("Thompson McCullough" as one piece)
  instead of each piece separately. That joined string is never one
  of the entries `DbReadBase.get_surname_list()` enumerates, so such a
  person's handle was filed under a key the phonetic-code index could
  never actually reach, and their total was silently missing from
  every matching surname's count - the specific gap between this
  gramplet's own count and the same search run as a custom People
  filter (which checks each surname piece independently, the way
  Gramps' built-in `HasSoundexName` rule already does). Fixed by
  indexing (and re-indexing on every add/update/delete) each surname
  piece separately via the new `fuzzy_match_index.person_surnames`
  helper, shared by both the gramplet and `FuzzyMatchLookupWindow.py`.
* Fixed: selecting/centering the active person's own row in both
  Matches columns failed for the same reason whenever the active
  person had a compound surname - the row lookup compared against
  their single joined surname string, which likewise never appears in
  the left column. Now checks every surname piece the active person
  carries.
* Changed: seeding the Surname field from a person (the active
  person, a browsed person, or one dropped onto the field) now uses
  their primary surname piece alone, not the fully-formatted joined
  string - encoding a whole joined compound surname under NYSIIS,
  Metaphone, or Match Rating Approach (each of which, unlike Soundex,
  processes the entire input as one continuous run rather than a
  fixed-length code) produced a code for the run-on string as a
  whole, matching neither surname piece on its own.
* Changed: the nearby-surname dropdown now suggests every surname
  piece a nearby relative carries, not just one representative string
  per relative, for the same reason.
* Generated-by: Claude Sonnet 5 (Anthropic), from a bug report that
  the active person was not being found/selected in the Matches
  columns, and that a compound-surname person ("Thompson McCullough")
  was undercounted (726 matches from this gramplet vs. 1384 from the
  equivalent custom People filter) and not found by a search for
  either of her two surnames, under this project's
  [Gramps coding/AGENTS guidelines](https://github.com/gramps-project/gramps/blob/master/AGENTS.md).

## v0.5.0 (15 Sep 2026)

* Added: the gramplet's Matches columns now stay live while it's open
  - a person being created, edited, or deleted, or their birth/death
  event's date or place being changed, updates the display without
  needing to retype the Surname field or reopen the gramplet. Person
  changes are patched into the existing index using the handle list
  each database signal already provides, not a full rescan; an event
  date/place edit (which commits only the `Event` object, not the
  `Person`) is handled separately since it never fires `person-update`
  at all.
* Added: `fuzzy_match_index.py` and `fuzzy_match_display.py`, two new
  GTK-free sibling modules holding the phonetic index and the
  person-display formatting that used to live only inside
  `FuzzyMatchingGramplet.py`. The gramplet is now a thin GTK layer over
  both, with no logic duplicated between them.
* Added: `FuzzyMatchLookupWindow.py`, a small standalone "does someone
  like this already exist" popup and its `show_fuzzy_lookup()` entry
  point, for other addons to call directly - for example, a Photo
  Tagging-style gramplet that parsed a Surname/Given Name out of image
  metadata. Built the same way this addon suite's own
  `PluginManagerPlus.PluginStatus` window is (`ManagedWindow` plus a
  `build_menu_names` override), not by trying to detach the gramplet's
  own widget tree from a docked pane, since that machinery is private
  and has shifted across the 5.2-6.2 range this addon targets.
* Added: `FuzzyMatchAPI.md`, a companion document for another addon's
  developer (or their AI coding assistant) covering how to call into
  `fuzzy_match_index`/`fuzzy_match_display`/`FuzzyMatchLookupWindow`
  from outside this addon, including the bare-import requirement and
  what isn't implemented (there is no phonetic given-name matching or
  shared/global index today).
* Added: `test/fuzzy_match_index_test.py` and
  `test/fuzzy_match_display_test.py`, `unittest`-based tests for the
  two new GTK-free modules, using lightweight fake `Db`/`Person`
  objects (and, for the display module, mock-patched Gramps
  birth/death/name-display calls) rather than a real Family Tree.
* Generated-by: Claude Sonnet 5 (Anthropic), from prompts to (1) make
  the Matches columns refresh live on person/event database signals
  instead of only on gramplet reopen, (2) expose that same matching
  logic so another addon can do a quick "does this person already
  exist" lookup, including an undocked popup if the gramplet isn't
  open in any view, and (3) reduce the resulting duplication across
  the gramplet and the new popup down to one shared implementation
  each for indexing and display formatting, then bring the whole set
  to this project's distribution-ready bar (Black, pylint, mypy, and
  new tests) with an API document for other addons' developers, under
  this project's [Gramps coding/AGENTS guidelines](https://github.com/gramps-project/gramps/blob/master/AGENTS.md).

## v0.4.0 (10 Sep 2026)

* Added: rows in the right-hand Matches column (people) can now be
  dragged out as a standard Gramps "person-link", the same drag type
  Gramps itself uses in the Relationships view, People view, and
  Person editor reference lists - so a match found here can be
  dropped onto any other Gramps view, gramplet, or editor field that
  already accepts a dragged person.
* Added: the Surname field now accepts a person dropped onto it (from
  this gramplet's own person list or from elsewhere in Gramps) and
  fills itself with that person's surname, the same as typing it.
* Added: the left-hand Matches column now shows a count of how many
  people share each matching surname, e.g. `Smith (12)`, instead of
  the surname alone.
* Generated-by: Claude Sonnet 5 (Anthropic), from prompts to add
  drag-and-drop of a Person object out of the Matches list, accept a
  dropped Person on the Surname field to set its value, and show a
  per-surname person count in the Matches list, under this project's
  [Gramps coding/AGENTS guidelines](https://github.com/gramps-project/gramps/blob/master/AGENTS.md).

## v0.3.1

* Fixed: `db_changed` now discards the previous Family Tree's cached
  phonetic index and person-lookup table before anything else runs,
  rather than after, closing a window where switching Family Trees
  could raise `HandleError` against handles from the tree that was
  just closed.
* Added: the Matches paned's column split is now remembered between
  sessions (`FuzzyMatchingGramplet.ini`) instead of always reopening
  at the default 1/3-2/3 split.

## v0.3.0

Convert extensible Phonetic systems to Rule plugins - Soundex, NYSIIS,
Match Rating Approach, and Metaphone are each also usable directly as
a standalone Gramps filter rule from the Filter Editor's "Add Rule"
dialog, not just from inside this gramplet. See
[RulesREADME.md](RulesREADME.md).

## v0.2.0

* Added: double-clicking a surname in the left Matches column opens a
  pre-filled "Define filter" dialog for that surname, mirroring the
  Clipboard module's "Create a filter from the selected..." feature.
* Added: the gramplet now stays in sync with the active person set
  elsewhere in Gramps - its surname and row are selected and scrolled
  into view in both Matches columns whenever the active person
  changes, from any source.
* Changed: replaced the O(n^2) "scan every person, dedupe with an
  `in` test" surname list from the original SoundEx gramplet with
  `DbReadBase.get_surname_list()` plus a code -> surnames index built
  once per database load (or algorithm change) and cached, so typing
  in the Surname field is an O(1) lookup instead of a fresh scan. See
  the `FuzzyMatchingGramplet.py` module docstring for the measurements
  that motivated this.
* Changed: that indexing work now runs as a background generator
  driven by the Gramplet framework's own idle-time scheduling, with a
  spinner and running count, instead of blocking the GTK main loop
  synchronously.
* Removed: the name field's `Gtk.ComboBox` populated with every unique
  surname in the tree via `gramps.gui.autocomp.fill_combo`, replaced
  with a plain entry plus a small "nearby relatives" dropdown and a
  standard Person-selector browse button - `set_model()` on that combo
  was the dominant cost on large trees, not the gramplet's own
  indexing logic.

## v0.1.0 (6 Sep 2026)

Initial fork of `soundgen.py` under the new name "Fuzzy Matching".
Turned the original single-code lookup into a match-finding workflow:
typing a surname shows every surname in the Family Tree that
phonetically matches it, and every person who carries each matching
surname, rather than only the phonetic code for one typed name.

* Generated-by: Claude Sonnet 5 (Anthropic), from prompts to fork
  `soundgen.py` into a surname phonetic-match finder while keeping the
  original gramplet's name-entry-to-code behavior working, under this
  project's
  [Gramps coding/AGENTS guidelines](https://github.com/gramps-project/gramps/blob/master/AGENTS.md)
  and
  [AI-generated code guidelines](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code).
