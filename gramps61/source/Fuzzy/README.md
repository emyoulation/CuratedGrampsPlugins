# Fuzzy Matching Gramplet
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [Phonetic Filter Rules](RulesREADME.md) ● [adding Phonetic systems (for developers)](FuzzyDev.md)

Type a surname and find every person in the Family Tree whose surname phonetically matches it — spelling variants, transcription differences, the "Smith vs. Smyth" problem — instead of just being told a code. It grew out of the core Gramps **SoundEx** gramplet (`gramps/plugins/gramplet/soundgen.py`), which only ever computed a single Soundex code for one typed name and rebuilt its surname list in a way that visibly slowed down on large trees; this gramplet keeps the same starting idea and turns it into an actual search tool.

## Features
* [Matching people, not just a code](#matching-people-not-just-a-code) — see every surname and every person that phonetically matches what you type
* [Working with a match](#working-with-a-match) — click a person to make them active, double-click to edit them
* [Staying in sync](#staying-in-sync) — the gramplet follows along as you navigate the tree elsewhere
* [Creating a filter from a match](#creating-a-filter-from-a-match) — turn a code into a reusable People filter
* [Finding a surname to search](#finding-a-surname-to-search) — nearby-relative suggestions, or browse anyone in the tree
* [Staying fast on large trees](#staying-fast-on-large-trees) — indexes in the background with visible progress
* [Adjusting the layout](#adjusting-the-layout) — resizable results panel that remembers your layout
* [Help](#help) — one click to this document, or to the online guide
* [Encoding systems](#encoding-systems) — Soundex, NYSIIS, Match Rating Approach, and Metaphone, each catching different spelling variants
* [What's inherited from the original gramplet](#whats-inherited-from-the-original-gramplet) — the name field and code display still work the way they always did

## Matching people, not just a code
Type a surname into the **Surname** field and pick an **Encoding system** (see [Encoding systems](#encoding-systems)). The **Code(s)** list shows the phonetic code(s) for what you typed, and **Matches** shows the results in two columns: every surname in the tree sharing that code on the left, and every person who has whichever surname you select on the right, as `Display Name (birth year–death year) [Gramps ID]`. The number next to the **Matches:** heading is the total across every matching surname combined, not just whichever one is currently selected — handy for confirming a Custom Filter built from [a match](#creating-a-filter-from-a-match) or [directly](RulesREADME.md) returns the same count.

## Working with a match
Click a person in the right-hand column to make them the active person elsewhere in Gramps. Double-click (or press Enter on) a row to open that person directly in the standard Person editor.

## Staying in sync
The gramplet isn't just a one-way search box: when the active person changes — from this gramplet, the Home button, another view, or another gramplet — their surname and their own row are automatically selected and scrolled into view in both columns, so you can always see where the active person sits among their phonetic namesakes.

## Creating a filter from a match
Double-click a surname in the left Matches column to open a "Define filter" dialog, pre-filled with a People filter matching that surname under whichever Encoding system is currently selected, named `Fuzzy match: <surname> (<encoding system>)` with a dated comment. Nothing is saved automatically — the dialog opens exactly as if you had built it by hand, and it's saved only if you click OK. To build a filter combining one of these rules with other conditions, or to use one without the gramplet open at all, see [RulesREADME.md](RulesREADME.md).

## Finding a surname to search
The Surname field's dropdown suggests surnames from people closely related to the active person, as a shortcut. To search for anyone in the whole tree instead, use the index button (▤) beside the field, which opens the standard Person selector.

## Staying fast on large trees
Opening the gramplet or changing the encoding system rebuilds its lookups in the background rather than freezing the interface, with a spinner and a running count while it works. On a very large tree you may briefly see this indexing step; typing and browsing results otherwise stay instant.

## Adjusting the layout
Drag the divider between the two Matches columns to resize them; your chosen split is remembered the next time you open the gramplet.

## Help
The Help button (lower-left) opens this document — in the Markdown Dash gramplet if it's installed, otherwise in your browser — or the online guide if this file isn't available.

## Encoding systems
Soundex, NYSIIS, Match Rating Approach, and Metaphone all ship today as an addon bundle, each catching different kinds of spelling variation — see [Matching people, not just a code](#matching-people-not-just-a-code) for an example of how differently they can group the same names. Every Encoding system other than Soundex is also a standalone Gramps filter rule, usable directly from the Filter Editor's "Add Rule" dialog — see [RulesREADME.md](RulesREADME.md) for how to use them that way, or [FuzzyDev.md](FuzzyDev.md) if you want to add another Encoding system of your own.

## What's inherited from the original gramplet
Typing a surname and seeing its phonetic code, and having the field pre-filled from the active person when a tree loads, both come from the original SoundEx gramplet and still work the same way — they're just no longer the whole feature.

## Files
| File | Purpose |
|---|---|
| `FuzzyMatchingGramplet.gpr.py` | Plugin registration |
| `FuzzyMatchingGramplet.py` | Gtk gramplet UI, background indexing, and active-person sync |
| `FuzzyMatchingGramplet.ini` | Generated on first use to remember your layout choices; not shipped |
| `phonetic_codes.py` | Discovers available Encoding systems via Gramps' own plugin registry (no Gtk/db dependency, unit-testable) |
| `test/__init__.py` | Empty; required so `unittest discover` (see below) actually finds `test/` |
| `test/phonetic_codes_test.py` | `unittest` tests for `phonetic_codes.py` |

## Running the tests
```bash
GRAMPS_RESOURCES=. python3 -m unittest discover -p "*_test.py"
```

Run this from the addon's root directory. See [FuzzyDev.md](FuzzyDev.md) if this reports "NO TESTS RAN" or an import error — there are a couple of non-obvious setup requirements specific to testing a Gramps addon this way.

## AI-assisted contribution disclosure
Portions of this addon were generated with AI assistance, per the Gramps project's [AI-generated code guidelines](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code). Suggested commit-message trailers for whoever lands this as a real commit:

#### Generated-by: Clause Sonnet 5 medium

