# Change Log - Fuzzy Matching gramplet
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [Phonetic Filter Rules](RulesREADME.md) ● [adding Phonetic systems (for developers)](FuzzyDev.md)

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
