# Notes on preparing the French encoders for release

These notes record what had to change between the two modules as submitted and the two rules in this folder. They are written for the next person who writes an encoder for the Fuzzy Matching framework, so the same ground does not have to be covered again.

The modules were contributed by Jerome Rapinat through the Gramps Discourse thread on international fuzzy name matching, as two Python files with no registration files.

## Registration

A phonetic encoder reaches Gramps only through a registration file. Each module needs a matching `.gpr.py` that calls `register(RULE, ...)` with `fname` naming the module, `ruleclass` naming the rule class exactly, and `namespace="Person"`.

The plugin `id` must carry the `FuzzyMatchingEncoder:` prefix. That prefix is how the Fuzzy Matching Gramplet discovers encoding systems: it scans the plugin registry for RULE plugins whose id starts with it, rather than keeping a list of known systems. Without the prefix a rule still works in the Person Filter Editor, but the gramplet never offers it in the Encoding system dropdown.

Wrap `register(...)` in a version test against `VERSION_TUPLE` so the addon declines to register on a Gramps release it was never tried on, and set `gramps_target_version=major_version` so one source folder serves several Gramps versions.

## Naming

The file name should lead with the phonetic system and follow with the dialect or variant, so that every dialect of one system sorts together in a folder listing. The module file, its registration file, any settings file and the registered plugin id should all share that name.

The submitted file called `phonetic_french` names a language rather than a system. The algorithm is Phonex, published by Frederic Brouard on 31 March 1999, so the file is now `phonexfrenchrule.py` with the id `FuzzyMatchingEncoder:phonex_french`. Be aware that an unrelated English algorithm by Lait and Randell also goes by the name Phonex, which is why the label reads "Phonex (French)".

The second file, called `soundex_french`, turned out not to be French at all. Its letter pairs PH, KN, WR and GH are English spellings, and its consonant groups match no published system that could be traced, including the French Soundex2 that Brouard published alongside Phonex. It is registered as `soundex_custom` until its origin is settled.

Rule class names should not collide with a class that Gramps already ships. Rule classes are made findable under `gramps.gen.filters.rules.person`, so reusing a core class name would displace the core rule there and break saved filters. The plural form, as in `HasPhonexFrenchNames`, keeps the two apart.

## What the framework expects of an encoder module

Each module exposes three constants and one function.

- `ALGORITHM_ID` is the registry key. Treat it as fixed once the addon has been published, because saved "Encoding system" choices refer to it.
- `ALGORITHM_LABEL` is what the dropdown shows.
- `ALGORITHM_DESCRIPTION` is the tooltip for the dropdown.
- `encode(name)` returns a **set** of codes, not a single code. A one-element set is normal; systems such as Daitch-Mokotoff return several. Return an empty set for a name with no letters in it, so that blank name fields never match each other.

## Name-field granularity

Both submitted rules compared the primary surname and nothing else. Every rule in the FuzzyRules addon instead offers the "Match in:" option from `phonetic_name_parts.py`, which lets the person choose among surname pieces, given name, call name, nick name and the alternate names. Without it, a search for the surname "Thomas" also returns everyone whose given name is Thomas.

Adopting the option means four changes: add the option to `labels`, override `set_list` to call `pad_args` so filters saved with one argument still load, read the option in `prepare` with `parse_parts`, and test the person with `person_matches` instead of reading the surname directly.

Because this folder ships separately from FuzzyRules, it carries its own copy of `phonetic_name_parts.py`. Importing it from the FuzzyRules folder would depend on load order and on that addon being installed. The copy must be kept in step with the original; treat the FuzzyRules copy as the source. The import stays inside a `try` block, because Gramps does not survive a rule addon that fails to import, and the fallback keeps the rule loadable with surname matching only.

## Gramps 5.2 and 6.0 and later

Gramps 6.0 renamed the per-object hook on `Rule` from `apply` to `apply_to_one`. A rule that defines only one of the two works on one side of that line and raises on the other.

The rules here define `apply_to_one` with the real work in it, and keep a one-line `apply` that forwards to it. Both hooks were exercised against a 5.2-shaped base class and a 6.0-shaped base class, with a matching and a non-matching person, and both paths return the same answer.

Two further points that are easy to miss.

- `prepare` takes two arguments, `(db, user)`, on both sides of the 6.0 line. A rule written with the older one-argument signature fails at filter time rather than at load time.
- Gramps 6 asks a rule that narrows the search in `prepare` to publish the result as `selected_handles`, so the optimizer can skip the per-person loop. A phonetic rule has to encode every person, so it has nothing to publish and correctly forces the full loop.

## Defects found in the submitted encoders

The Phonex port reproduced the published algorithm closely, including one branch that is dead in Brouard's own reference implementation. Several steps, however, could never run as ordered, and the effects were not visible without testing pairs of names.

- Accents were stripped before the rule that reads accented E, so that rule never fired, and the strip turned the cedilla into a plain C that later read as the sound of K. "Garcon" and "Garçon" did not meet.
- Silent H was only removed when another letter preceded it, so a leading H survived and "Hugo" did not meet "Ugo".
- The nasal rules consumed the following character, so a nasal at the end of a word was never encoded. This affects a large share of French surnames: "Simon" and "Simond" did not meet, and "Martin" kept its letters.
- The same consume-the-next-character pattern broke overlapping cases of the rule that reads S as Z between vowels.
- Rules were listed after rules that eat them, so SCH never reached its own line and QU never reached its own line. "Quentin" and "Kentin" did not meet.

The custom Soundex variant had no Unicode handling at all, so accented letters landed in the finished code. Its letter pairs were applied only after the first letter had been split off, so any pair starting at position one never matched and "Philippe" did not meet "Filipe". H and W were neither coded nor dropped and appeared literally in codes.

The lesson worth passing on is that a phonetic encoder cannot be reviewed by reading. Every rule in a chain of string replacements can be shadowed by an earlier one, and the result still looks like a plausible code. Test pairs of names that ought to meet, and pairs that ought not to.

## Attribution

Gramps asks that the use of an AI tool be disclosed in the commit message, with the fully qualified name of the tool, the provider and the version, using the `Generated-by:` tag for code substantially written by the tool and `Co-authored-by:` where it assisted. The repair and packaging of these two modules falls under that rule.

The copyright headers name Jerome Rapinat for the original work. Brouard holds the copyright in the Phonex algorithm itself, and the module docstring points at the published description.

## Still to settle

- The two places where the Phonex port now departs from the published step order, both marked in `encode`. Without them "Vincent" takes a K sound and does not meet "Vinsant". Reverting to the published order is a two-line change.
- Two rules the submitted port added that are not in the published tables, `ez` read as `yz` and `on` read as the nasal 1. The second looks like an omission in the published table, since the article names the "on" sound in its own prose.
- The origin of the custom Soundex variant, and whether it was meant to be French.
- A README for this folder, which the Help button of each rule expects to find.
