# Fuzzy Match API — for AI coding assistants integrating another addon
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [Phonetic Filter Rules](RulesREADME.md) ● [adding Phonetic systems (for developers)](FuzzyDev.md) ● [Fuzzy Match API](FuzzyMatchAPI.md)

**Audience:** this document is written for an AI assistant (or a developer) working on a *different* Gramps addon that wants to reuse this addon's surname-matching logic — for example, a Photo Tagging gramplet that parsed a Surname/Given Name out of image metadata and wants to check whether that person might already exist before creating a new one. If that's not your situation, see [README.md](README.md) instead.

**Do not import `FuzzyMatchingGramplet.py`** for this. That file is the gramplet's own GTK widget tree and Gramplet-framework wiring — it has no public API meant for other addons to call, and instantiating it outside the Gramplet framework will not work. The three modules below are the actual integration points.

## TL;DR — three integration points

| You want... | Use | Needs GTK? |
|---|---|---|
| A visible popup the user can interact with (type a surname, see matches, double-click to edit) | `FuzzyMatchLookupWindow.show_fuzzy_lookup()` | Yes |
| Raw `{surname: [handle, ...]}` data, no UI at all | `fuzzy_match_index.FuzzyMatchIndex` | No |
| To format a `Person` the same way this addon's own UIs do | `fuzzy_match_display.format_person()` | No |

All three live in this addon's own installed folder, but **do not import any of them with a bare `import fuzzy_match_index`-style statement from your own addon's code — that does not work reliably.** See "How to actually import this addon's modules" below for why, and for the one correct way to reach any of them.

Since this is a separate, optional addon, always guard the lookup: if Fuzzy Matching isn't installed, isn't enabled, or is an older version that doesn't register this API yet, the lookup returns `None`, and your addon should degrade gracefully (skip the check) rather than fail.

```python
from gramps.gen.plug import BasePluginManager

def _get_fuzzy_match_module():
    """Return the Fuzzy Matching addon's API module, or None if unavailable."""
    pmgr = BasePluginManager.get_instance()
    pdata = pmgr.get_plugin("Fuzzy Match API")
    if pdata is None:
        return None
    try:
        return pmgr.import_plugin(pdata)
    except ImportError:
        return None
```


## Pattern 1 — quick visible popup (most common case)

Call this when the user does something that makes "check for a duplicate" relevant — most typically right before your own addon is about to create a new `Person`.

```python
from gramps.gen.plug import BasePluginManager

def _get_fuzzy_match_module():
    pmgr = BasePluginManager.get_instance()
    pdata = pmgr.get_plugin("Fuzzy Match API")
    if pdata is None:
        return None
    try:
        return pmgr.import_plugin(pdata)
    except ImportError:
        return None

# ... later, e.g. after parsing a name out of photo metadata:
module = _get_fuzzy_match_module()
if module is not None:
    module.show_fuzzy_lookup(
        dbstate, uistate, track,
        surname=parsed_surname,
        given_name=parsed_given_name,  # optional
    )
```

**What this does:**
- Opens a small standalone window (title "Fuzzy Match Lookup") showing every surname in the tree that phonetically matches `surname`, under whichever Encoding system the person last chose in this window this session (Soundex by default) - the window has its own Encoding system selector, independent of `FuzzyMatchingGramplet.py`'s own choice.
- If `surname` is an exact match among the results, that row is selected automatically — populating the right column with every person carrying it — and the right column is scrolled/selected to whichever person's given name sorts closest to `given_name`. This is deliberately *not* a filter: the right column shows everyone with the surname, not just people whose given name contains `given_name`, specifically so a nickname, initial, or transcription difference between your parsed given name and what's actually recorded doesn't hide the person you're looking for. The Given Name field itself is left blank, not filled in with `given_name` — an earlier version of this did fill it in "for reference", but that left it sitting there as an active filter for whatever the person clicked next, silently emptying the right column again on an ordinary manual surname click. A selection or edit the person actually makes in that field, from that point on, does filter normally.
- If a Fuzzy Match Lookup window is already open, this re-seeds *that* window's fields/selection and raises it, rather than opening a second one. Calling `show_fuzzy_lookup` again with a new surname is the correct way to update an already-open window — there is no separate "update" method to call.
- The window builds its own index in the background (with a spinner) the first time it opens; a few hundred thousand people takes at most a second or two, not a freeze.
- The window shows up under Gramps' **Windows** menu as "Fuzzy Match Lookup".
- This call is fire-and-forget: it does not block, and it does not return a result to inspect. If your addon needs the actual match data programmatically (e.g., to decide whether to even ask the user), use Pattern 2 instead, possibly *in addition to* showing the window.

**Function signature:**

```python
def show_fuzzy_lookup(dbstate, uistate, track=None, surname="", given_name=""):
    """
    :param dbstate: The current gramps.gen.dbstate.DbState.
    :param uistate: The current gramps.gui.displaystate.DisplayState.
    :param track: ManagedWindow track list from your own window, or
        None/[] if you have no window of your own to nest this under.
    :param surname: Surname to look up and, if there's an exact
        match, select in the left column.
    :param given_name: Given name to scroll/select the closest match
        to in the right column, once populated - not a filter (see
        above).
    :returns: The (now open) FuzzyMatchLookupWindow instance. You
        normally don't need this return value for anything.
    """
```

## Pattern 2 — raw match data, no UI

Use this when you want to *decide something in code* based on whether a match exists — e.g., only prompt the user at all if there's actually a plausible duplicate — rather than always popping a window open.

```python
module = _get_fuzzy_match_module()  # see the helper above
if module is not None:
    index = module.FuzzyMatchIndex(dbstate.db)
    index.build_sync()  # blocks briefly; fine for an occasional, one-off check
    matches = index.find_matches(parsed_surname)  # {surname: [handle, ...]}
    if matches:
        total_people = sum(len(handles) for handles in matches.values())
        # ... decide what to do, e.g. show_fuzzy_lookup() only now
```

`module.FuzzyMatchIndex` works even though `fuzzy_match_index.py` isn't itself registered as a GENERAL plugin: `FuzzyMatchLookupWindow.py` (the one that is) already does `from fuzzy_match_index import FuzzyMatchIndex` at its own top level, so once it's been imported via the plugin registry, `FuzzyMatchIndex` is sitting right there as one of its attributes — no second registry entry needed. Same reasoning covers `module.format_person` in Pattern 3 below.

**Important: build your own instance, don't try to reuse the gramplet's or the lookup window's index.** There is currently no shared/global index — the gramplet, the lookup window, and any `FuzzyMatchIndex` you construct yourself are each independent. `FuzzyMatchIndex(dbstate.db)` is cheap to construct; the cost is in `build()`/`build_sync()`, so construct one and reuse it across multiple lookups in the same operation (e.g., checking every row of an import file) rather than rebuilding per name.

**`build_sync()` vs `build()`:** `build_sync()` blocks until finished — fine for a single occasional check. If you're calling this from your own GTK code and want to stay responsive on a large tree, drive `build()` (a generator) via `GLib.idle_add` yourself, the same way `FuzzyMatchingGramplet.main()` does — see that file for the exact pattern, or `FuzzyMatchLookupWindow._start_build`/`_cb_build_step` for a smaller example.

**Core `FuzzyMatchIndex` methods:**

| Method | Returns | Notes |
|---|---|---|
| `FuzzyMatchIndex(db, algorithm_id=None)` | — | `algorithm_id` defaults to `phonetic_codes.DEFAULT_ALGORITHM` (Soundex) if omitted |
| `build_sync()` | `None` | Blocks until the index is built |
| `build(progress_callback=None)` | generator | For driving in the background; see above |
| `find_surnames(name)` | `list[str]` | Surnames phonetically matching `name` |
| `find_people(surname)` | `list[str]` | Person handles carrying this surname as one of their surname pieces - see "Compound surnames" below |
| `find_matches(name)` | `dict[str, list[str]]` | Both combined — usually what you want |
| `.ready` | `bool` | `False` until the first `build()`/`build_sync()` completes |

**What the index covers:** surname pieces of each person's *primary* name only - not given, call or nick names, and not alternate names. This is the same default the Phonetic Filter Rules use (see "Building a filter from these rules in code" below), so a filter built with only a name argument returns the same people as `find_matches`. The index has no equivalent of the rules' "Match in:" option.

**Compound surnames:** a person with a double/compound surname (e.g. "Thompson McCullough", stored as two separate `Surname` pieces on one `Name`) is indexed under *each* piece separately — `find_people("Thompson")` and `find_people("McCullough")` both return their handle. This is deliberate, and matches how Gramps' own `HasSoundexName` filter rule treats a multi-part surname: it does not use `Name.get_surname()`'s single, connector-joined string ("Thompson McCullough" as one piece), since that joined string is neither what `db.get_surname_list()` enumerates nor, for any algorithm other than Soundex, phonetically equivalent to either surname alone. If you're formatting or comparing surnames yourself rather than going through `find_people`/`find_matches`, use `fuzzy_match_index.person_surnames(person)` (returns the set of individual pieces) rather than `person.get_primary_name().get_surname()` for the same reason.

**Keeping an index current:** if you build one `FuzzyMatchIndex` and hold onto it across multiple person edits (rather than building fresh each time), connect it to the database's own signals the same way `FuzzyMatchingGramplet.py` does, so it doesn't go stale:

```python
db.connect("person-add", lambda handles: index.on_person_changed(handles))
db.connect("person-update", lambda handles: index.on_person_changed(handles))
db.connect("person-delete", lambda handles: index.on_person_deleted(handles))
db.connect("person-rebuild", lambda: index.on_rebuild())
```

`on_person_changed`/`on_person_deleted` return the `set` of surnames touched by that change, in case you want to react to specifically those; `on_rebuild()` just clears `.ready` — you're responsible for calling `build()`/`build_sync()` again afterward, the same as `FuzzyMatchingGramplet.cb_person_rebuild` does. If you're doing a single one-off check and discarding the index immediately afterward, none of this is necessary — just `build_sync()` and read the result once.

## Pattern 3 — formatting a person the same way this addon does

If you're building your own display of candidate matches (rather than using `show_fuzzy_lookup`'s window) and want the same "Display Name (birth-death) [Gramps ID]" format this addon uses everywhere:

```python
module = _get_fuzzy_match_module()  # see the helper above
if module is not None:
    text = module.format_person(dbstate.db, person)  # "Jane Smith (1900-1980) [I0001]"
```

`format_person(db, person) -> str` takes the real database and a real `gramps.gen.lib.Person` object — not handles, not the fakes this addon's own tests use.

## Building a filter from these rules in code

The Phonetic Filter Rules addon (a separate folder, `FuzzyRules/`) provides one Person filter rule per encoding system. Unlike `FuzzyMatchIndex`, these rules can compare more than the primary surname, through a second argument. Use them when your addon builds a `GenericFilter`, rather than the index, when you need given names, alternate names, or the other name fields.

Get the rule class for an encoding system from the same registry the gramplet uses, via the API module:

```python
module = _get_fuzzy_match_module()  # see the helper above
rules = module.phonetic_codes.ALGORITHM_FILTER_RULES if module else {}
rule_class = rules.get("metaphone")  # None if that system has no rule installed
```

`module.phonetic_codes` (added in this version) also lists what is installed: `ALGORITHM_LABELS` maps each algorithm id to its display label, for building your own Encoding system choice, and `DEFAULT_ALGORITHM` is the id to preselect.

| Algorithm id | Rule class | Name in the Add Rule dialog |
|---|---|---|
| `soundex` | `HasSoundexNames` | Soundex match of People with the \<names\> |
| `nysiis` | `HasNysiisName` | NYSIIS match of People with the \<names\> |
| `match_rating` | `HasMatchRatingName` | MRA match of People with the \<names\> |
| `metaphone` | `HasMetaphoneName` | Metaphone match of People with the \<names\> |

Arguments are `[name, match_in]`:

* `name` - the name to encode and compare against.
* `match_in` - comma-separated keys choosing the name fields, in any order: `title`, `given`, `call`, `nick`, `given_alt` (given-name fields of alternate names), `prefix`, `surname`, `suffix`, `clan` (family nickname), `surname_alt` (surname fields of alternate names). Omitted or empty means `surname`: the primary name's surname pieces only, the same scope as `FuzzyMatchIndex`.

```python
from gramps.gen.filters import GenericFilterFactory

person_filter = GenericFilterFactory("Person")()
person_filter.add_rule(rule_class(["Johnson", "surname,surname_alt"]))
```

Each surname piece of a compound surname, and each word of a multi-word given name, is compared separately. So `["John", "given"]` matches "John Henry", and `["Johnson"]` (surname only) never matches someone named John.

Soundex without the Phonetic Filter Rules installed: `ALGORITHM_FILTER_RULES["soundex"]` is then Gramps' built-in `HasSoundexName`, which takes only one argument and always compares every name field. Check `rule_class.__name__` if your code depends on the second argument.

## How to actually import this addon's modules

**An earlier version of this document said every registered addon's folder is on `sys.path` for the whole Gramps session, so a bare `import fuzzy_match_index` from another addon's code would just work. That was wrong, and real-world testing against a running Gramps caught it: the bare import failed silently, even with Fuzzy Matching installed and working.** The actual behavior: Gramps adds an addon's own folder to `sys.path` only *while it is itself importing that addon's registered module*, then removes it again immediately after (`BasePluginManager.import_plugin(pdata)`'s own docstring: "this will add the pdata.fpath to sys.path first (if needed), import, and then reset path"). By the time your addon's code runs — even at actual click/use time, well after Gramps has finished starting up — Fuzzy Matching's folder is not on `sys.path` unless something is actively importing it right then.

The fix, and the only supported way to reach any of this: Fuzzy Matching registers a `GENERAL` plugin, `id="Fuzzy Match API"` (see `FuzzyMatchingGramplet.gpr.py`), whose `fname` is `FuzzyMatchLookupWindow.py`. Look it up and import it through Gramps' own plugin registry, which handles `sys.path` correctly for that one call:

```python
from gramps.gen.plug import BasePluginManager

pmgr = BasePluginManager.get_instance()
pdata = pmgr.get_plugin("Fuzzy Match API")   # None if not installed/enabled/new enough
module = pmgr.import_plugin(pdata)            # the FuzzyMatchLookupWindow module itself
```

`fuzzy_match_index.py` and `fuzzy_match_display.py` aren't separately registered — they don't need to be, since `FuzzyMatchLookupWindow.py` already imports both of them (bare, same-folder, which works fine for it since it's the file actually being imported) and so has `FuzzyMatchIndex`, `format_person`, etc. sitting on it as ordinary attributes once loaded this way. `PhotoTaggingGramplet.py`'s own `_get_fuzzy_match_lookup()` is a real, in-production example of this exact pattern, if you want to see it end to end.

`load_on_reg` on that registration is `False`: nothing imports it automatically at Gramps startup, regardless of whether any other installed addon ever calls it. It's only ever imported on demand, by whatever addon actually calls `import_plugin` — which is also why guarding for `pdata is None` (not installed, not enabled, or an older version predating this registration) and for `ImportError` from `import_plugin` itself both matter; neither is exotic, both are the normal "this optional addon isn't there" case.

## What isn't implemented (don't assume it exists)

- **No phonetic given-name matching in the index or the lookup window.** (The filter rules can match given names - see "Building a filter from these rules in code".) `given_name` in `show_fuzzy_lookup` selects/scrolls to the closest match by plain locale-aware sort order (see Pattern 1), and a manual filter afterward is a plain case-insensitive substring match — neither is a phonetic comparison. Reusing `phonetic_codes.ALGORITHMS` against the given name too would be a reasonable addition, but it doesn't exist today — don't write integration code that assumes it does.
- **No shared/global index.** Each `FuzzyMatchIndex` you construct is independent of the gramplet's own and of any `FuzzyMatchLookupWindow`'s own. There's no registry or singleton to fetch an already-built one from.
- **No return value carrying match results from `show_fuzzy_lookup`.** It opens a window; it doesn't hand back data. Use Pattern 2 if you need data.
- **No CLI/headless entry point.** `fuzzy_match_index.py` and `fuzzy_match_display.py` have no `gi.repository` import and work fine outside a GUI, but nothing in this addon currently exposes a command-line tool built on them.

## Version and compatibility notes

- This API (the three modules above) was introduced in Fuzzy Matching v0.5.0 — see [CHANGELOG.md](CHANGELOG.md). **The "Fuzzy Match API" GENERAL plugin registration — the only reliable way to actually reach it from another addon — was added in v0.5.1**, correcting the bare-import guidance v0.5.0's version of this document gave, which didn't work. If you're integrating against an installed copy of Fuzzy Matching, guard for `pdata is None` regardless (per "How to actually import this addon's modules" above), since that also covers "installed but older than v0.5.1".
- Like the rest of this addon, these modules must import successfully on Python 3.6 (Gramps 5.2.5 field reports) as well as current Python — see the "Field reports" comment near the top of `FuzzyMatchingGramplet.py` for what that constrains about type-hint syntax. If you're generating code that imports these modules from your own addon, this doesn't affect you (you're calling into already-compatible code), but it's worth knowing if you're proposing changes to these modules themselves.
- Targets Gramps 5.2 through 6.2 (see `FuzzyMatchingGramplet.gpr.py`'s version guard). Nothing in these three modules is GTK-version-specific beyond what `FuzzyMatchLookupWindow.py` itself needs.

## Files covered by this document

| File | What it is |
|---|---|
| `fuzzy_match_index.py` | The phonetic index itself — build, incremental update, lookup. No GTK. |
| `fuzzy_match_display.py` | `format_person()` and the event-driven row-refresh helper. No GTK. |
| `FuzzyMatchLookupWindow.py` | The standalone popup and `show_fuzzy_lookup()`. Needs GTK. |

`FuzzyMatchingGramplet.py` itself is *not* part of this API — it's the gramplet, not a library, and is out of scope for this document. See [README.md](README.md) for what it does.
