# Phonetic Filter Rules
This addon bundles three Person filter rules — **NYSIIS**, **Match Rating Approach**, and **Metaphone** — that work anywhere Gramps filters do. Developed for use with the Fuzzy Matching gramplet but not limited to use only inside it. If you just want the gramplet's own Matches panel, you do not need this document at all; it is for building your *own* filters with these rules directly, the same way you would use Gramps' built-in Soundex rule.

## Features
* [Finding the rules](#finding-the-rules) — where they show up in the Filter Editor
* [NYSIIS](#nysiis) — catches more spelling drift than Soundex, in exchange for a longer code
* [Match Rating Approach](#match-rating-approach) — a compact code, best for near-identical spellings
* [Metaphone](#metaphone) — models English pronunciation more closely than Soundex
* [Building a filter with one of these rules](#building-a-filter-with-one-of-these-rules) — a worked example
* [Combining a rule with other conditions](#combining-a-rule-with-other-conditions) — why you would do this instead of using the gramplet's own shortcut

## Finding the rules
Open **Edit ▸ Person Filter Editor** (or the "Edit" button next to the filter dropdown on the People view), create or edit a filter, and click **Add Rule...**. All three rules listed here appear under **General filters**, alongside Gramps' own built-in rules, as:

* "NYSIIS match of People with the \<surname\>"
* "Match Rating Approach match of People with the \<surname\>"
* "Metaphone match of People with the \<surname\>"

Each takes a single surname as its parameter and matches every person whose *primary* surname produces the same phonetic code — not first names, nicknames, or alternate names, unlike Gramps' own Soundex rule, which checks all of those.

## NYSIIS
NYSIIS (New York State Identification and Intelligence System) keeps more information about vowel position than Soundex does, which is both its strength and its one real quirk: it does not treat "Y" as a vowel, so some pairs Soundex considers a match — "Smith" and "Smythe" is the classic example — come out as different NYSIIS codes. That is not a bug to work around; it is simply a different, and often complementary, way of grouping spelling variants. If Soundex is not catching a variant you expect, NYSIIS sometimes will, and vice versa.

## Match Rating Approach
Match Rating Approach produces a shorter, more literal code: it drops non-leading vowels and collapses repeated consonants, without Soundex's or NYSIIS's broader letter-grouping rules. Worth knowing before you reach for it: Match Rating Approach's reputation for catching loose spelling variants comes from its own *comparison* algorithm, which tolerates codes that are similar but not identical — this rule does not implement that comparison, only the plain code. Used as an exact-match filter rule (the only kind Gramps supports), it will group truly identical spellings and very close variants, but is the most literal of the three rules here — it wo not catch as much drift as NYSIIS or Metaphone will.

## Metaphone
Metaphone models English pronunciation more closely than Soundex: it accounts for silent letters and consonant clusters Soundex's simpler scheme misses — "PH" becoming an F sound, a silent "GH", and others — and produces a shorter, variable-length code rather than Soundex's fixed four characters. It agrees with Soundex on more pairs than NYSIIS does (both correctly group "Smith" and "Smyth", for example), while still catching some variants Soundex's cruder letter-grouping misses.

## Building a filter with one of these rules
As a worked example, here is building a filter that finds everyone with a NYSIIS-equivalent surname to "Boucher":

1. **Edit ▸ Person Filter Editor**, then **Add** to create a new filter (or pick an existing one to edit).
2. **Add Rule...**, find "NYSIIS match of People with the \<surname\>" under *General filters*, and select it.
3. Type `Boucher` into the Name field the rule asks for, and click **Add**.
4. Give the filter a name (e.g. "NYSIIS: Boucher") and click **OK**.
5. The new filter is now available anywhere Gramps lets you pick a Person filter — the filter side-bar on the People view, reports, and more.

Swap in "Match Rating Approach match..." or "Metaphone match..." for either of the other two rules; everything else about the steps is identical.

## Combining a rule with other conditions
The Fuzzy Matching gramplet's own "Define filter" double-click action (see [README.md](README.md)) builds exactly this kind of single-rule filter for you automatically, pre-filled with whichever surname you double-click and whichever Encoding system is currently selected — for a quick, one-off check, that is almost always faster than building one by hand here. Building a filter yourself is worth it when you want to combine one of these rules with something the gramplet's shortcut does not offer: AND'd with a birth-year range, OR'd with a second surname, restricted to a specific tag, and so on — anything the Filter Editor's own rule list and "All rules must apply"/"At least one rule must apply" options support.

## AI-assisted contribution disclosure
Portions of this addon were generated with AI assistance, per the Gramps project [AI-generated code guidelines](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code). Suggested commit-message trailers for whoever lands this as a real commit:

#### Generated-by: Clause Sonnet 5 medium

