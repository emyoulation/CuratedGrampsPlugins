# Developer Notes - Fuzzy Matching gramplet
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [Phonetic Filter Rules](RulesREADME.md) ● [adding Phonetic systems (for developers)](FuzzyDev.md)

This document is for anyone changing the code, not using the gramplet — see [README.md](README.md) for that. It covers how to add a new phonetic encoding system, the shape of the codebase and why a few parts of it look more careful than they might seem to need to be, and how to actually run the test suite.

## Adding an encoding system

Every encoding system other than Soundex is a self-contained `<name>rule.py` + `<name>rule.gpr.py` pair, registered as an ordinary Gramps `RULE`-type plugin - not a custom scanned folder. This isn't a stepping-stone toward "real" discovery; it's the actual mechanism, and it exists because a "Define filter" action for a new algorithm needs a real, registered Person filter rule anyway (Gramps has no way to auto-discover *those* by scanning a folder - every one needs an explicit `register(RULE, ...)` regardless), so `phonetic_codes.py` just asks Gramps' own plugin registry which `RULE` plugins came from this addon's own folder, rather than maintaining a second, parallel discovery system alongside the one Gramps already provides. See `nysiisrule.py`/`nysiisrule.gpr.py` as the template - copy that pair, rename it, and rewrite the middle. The full contract:

```python
# myalgorule.py
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

ALGORITHM_ID = "my_algorithm"
ALGORITHM_LABEL = "My Algorithm"
ALGORITHM_DESCRIPTION = "One or two sentences shown as a tooltip."  # optional

def encode(name: str) -> set[str]:
    """Return the code(s) `name` encodes to under this algorithm."""
    return {my_algorithm(name)}

class HasMyAlgorithmName(Rule):
    labels = [_("Surname:")]
    name = _("My Algorithm match of People with the <surname>")
    description = _("Matches people whose primary surname has a specified My Algorithm code")
    category = _("General filters")

    def prepare(self, _db, _user):
        self._target_codes = encode(self.list[0]) if self.list and self.list[0] else set()

    def apply_to_one(self, _db, obj) -> bool:
        if not self._target_codes:
            return False
        return bool(encode(obj.get_primary_name().get_surname()) & self._target_codes)

    def apply(self, db, obj) -> bool:
        # Required for Gramps 5.2, which calls apply(), not
        # apply_to_one() - see "How an encoding system's rule gets
        # discovered" below for why both methods must be defined.
        return self.apply_to_one(db, obj)
```

```python
# myalgorule.gpr.py
from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        # The id MUST start with "FuzzyMatchingEncoder:" - that prefix,
        # not this file's name or location, is what makes this show up
        # in the gramplet's Encoding system list. See
        # phonetic_codes._ENCODER_ID_PREFIX and "How an encoding
        # system's rule gets discovered" below.
        id="FuzzyMatchingEncoder:my_algorithm",
        name=_("My Algorithm match of People with the <surname>"),
        description=_("Matches people whose primary surname has a specified My Algorithm code"),
        version="0.1.0",
        gramps_target_version=major_version,
        status=STABLE,
        fname="myalgorule.py",
        ruleclass="HasMyAlgorithmName",
        namespace="Person",
    )
```

The encode function and the Rule class live in the same file deliberately: they always travel together (the rule delegates its actual matching to the same `encode()` the gramplet itself calls for its on-screen matches), so there is nothing to keep in sync across files and no cross-module import ordering to reason about.

`encode` must:

* Accept a single string (a surname) and return a `set[str]` of codes. A set, not a single string, because some algorithms legitimately produce more than one valid code for one spelling.
* Never raise. `nysiisrule.py`/`matchratingrule.py`/`metaphonerule.py` all catch their own failure modes and fall back to encoding an empty string rather than letting a single odd surname take down the background indexer partway through a large tree; a new algorithm should have an equivalent fallback for whatever inputs it can't handle.
* Be reasonably fast per call. It runs once per unique surname and, in the worst case, once per person in the tree (see "Two background indexing passes, not one" below) - not asymptotically expensive itself, but not a place to do anything like a database lookup either.

`ALGORITHM_DESCRIPTION` is optional; a module that omits it is still registered fine (see `phonetic_codes._resolve_discovered_entries`) - `ALGORITHM_DESCRIPTIONS` just gets an empty string for that id. The filter rule, by contrast, isn't really optional in the same sense - see "Creating a filter from a match" below for what happens if `ruleclass` in the `.gpr.py` doesn't resolve to an actual class in the module.

Add a matching test file directly under `test/` (not a subdirectory - `test/nysiisrule_test.py` is the template, not `test/encoders/...`): at minimum, agreement with a reference implementation on a handful of names, confirmation that known phonetic variants of a name (e.g. Smith/Smyth for Soundex) produce the same code, and the rule's own `prepare()`/`apply_to_one()` lifecycle exercised directly (not just `encode()` in isolation - that would not catch a mistake in the rule's own glue code). `test/matchratingrule_test.py` is a good template for validating against a real third-party library rather than trusting its documentation - a stale README example for `jellyfish.match_rating_codex` was caught exactly this way, by running the installed library directly instead of copying the documented example.

### Soundex

Soundex (4-character "Russell", aka "NARA") is the phonetic encoding system bundled with Gramps (`gramps.gen.soundex.soundex`), and it's the one exception to the pattern above: it's hardcoded directly in `phonetic_codes._hardcoded_soundex`, not discovered. It already has a built-in Gramps rule (`HasSoundexName`), registered by Gramps under an id this addon does not control and could not give a matching prefix - so it would never be found by the id-prefix scan even if we wanted it to be, and registering a duplicate "HasSoundexName"-equivalent rule purely to give it a matching id would show up as a second, redundant entry in the standard Filter Editor's "Add Rule" dialog. It's also always available regardless of what else is installed, which a hardcoded entry reflects more honestly than routing it through the same "might not be there" discovery path as everything else.

### NYSIIS, Match Rating Approach, and Metaphone

All three ported from, and validated against, mature reference implementations rather than written from a written description of the rules - see the module docstrings in `nysiisrule.py` (validated against all ~85 cases in Apache Commons Codec's `NysiisTest.java`), `matchratingrule.py` (validated against the real `jellyfish` library, which is also where the stale-documentation catch above happened), and `metaphonerule.py` (validated against all 47 direct assertions plus every name-equivalence group in Apache Commons Codec's `MetaphoneTest.java` - over 200 name comparisons total). Match Rating Approach's own docstring also has an important caveat worth reading before recommending it to a user: its real matching power comes from a similarity-threshold *comparison* step this gramplet does not implement, so under this gramplet's exact-code-equality grouping, it is more literal than its reputation suggests.

### Daitch-Mokotoff Soundex (not included - a cautionary tale)

An implementation of Daitch-Mokotoff Soundex (useful for Slavic/Yiddish surname variants, since it's designed to produce the same code for spellings that plain Soundex treats as unrelated) was written for an earlier version of this gramplet and then dropped: it failed validation against the standard reference vectors (e.g. "Peters" should encode to `{"739400", "734000"}`, both codes, since Daitch-Mokotoff allows a name to have more than one valid encoding). If you pick this back up, validate against a full published reference table before shipping it as a new `<name>rule.py`/`<name>rule.gpr.py` pair - the algorithm has enough edge cases (adjacent-letter combination rules, branching codes) that "looks right for a few test names" is not enough evidence it's correct.

## Two background indexing passes, not one

`FuzzyMatchingGramplet.main()` is a generator, run by the Gramplet framework's own `update()`/`GLib.idle_add` machinery rather than called directly, and it builds two separate lookups:

1. **code → surnames**, over the database's unique surname list (`db.get_surname_list()`).
2. **surname → person handles**, over every person in the tree (`db.get_person_handles()`), so clicking a surname in the Matches list can populate the person column from a plain dictionary lookup instead of a fresh scan.

Both stages yield periodically (`INDEX_CHUNK_SECONDS`, time-based rather than a fixed item count, since per-item cost varies) so a large tree can't freeze the interface. This two-stage split, and the chunking itself, exist because of a real, measured problem in an earlier version of this gramplet, not as precautionary engineering:

An earlier version populated the Surname field with a `Gtk.ComboBox` holding every unique surname via `gramps.gui.autocomp.fill_combo`. Attaching that many rows to a combo box's model turned out to be roughly quadratic in GTK itself:

| Unique surnames | `combo.set_model()` time |
|---|---|
| 5,000 | 0.25 s |
| 15,000 | 1.2 s |
| 30,000 | 5.3 s |
| 60,000 | 31.6 s |

...run synchronously, with no progress feedback - "Gramps freezes, with no indication anything is happening." The actual phonetic-code computation over the same 60,000 surnames takes about 0.2 seconds in pure Python; the combo box, not the indexing logic, was the bottleneck. The fix was to stop putting the full surname list into a GTK widget at all (see "Nearby surnames vs. browsing the whole tree" below), and separately, to run whatever indexing *is* needed through the Gramplet framework's background-generator hook so a future performance regression degrades gracefully instead of freezing the UI outright.

## Repopulating a `Gtk.ListStore` fires selection signals - even without `select_path()`

`cb_name_changed`, `cb_surname_selected`, and `_clear_matches` all wrap their `Gtk.ListStore.clear()`/repopulate calls in `_blocked_selection_handlers()`, which blocks the relevant `Gtk.TreeSelection`'s "changed" handler for the duration via GObject's own `handler_block`/`handler_unblock`. This isn't defensive boilerplate: clearing and refilling a `Gtk.ListStore` while its `Gtk.TreeView` has keyboard focus fires spurious `TreeSelection` "changed" signals on its own, independent of any real selection - confirmed directly against real, realized/focused GTK widgets, not assumed. Since selecting a row in the person column calls `DisplayState.set_active()` (see below), a spurious "changed" event there would silently and incorrectly change the active person as a side effect of the list merely being refreshed. If you add a new store that needs repopulating, wrap it the same way; a hand-rolled "is this a programmatic change" boolean flag checked inside the handler is not sufficient; GTK does not guarantee synchronous, single delivery in every code path, and a flag can be reset before a signal it should have suppressed actually arrives. `handler_block`/`handler_unblock` prevents the handler from being invoked at all, which does not depend on that timing.

## Active-person sync goes through Gramps' own signals, not a private tracker

`db_changed()` and `active_changed()` are the Gramplet framework's own hooks for "the database changed" / "the active person changed" - this gramplet does not poll or independently watch for either. In the other direction, `cb_person_selected` calls `DisplayState.set_active()`, Gramps' own active-object mechanism, rather than pushing state into some gramplet-local notion of "current person." Two things to know if you touch this code:

* `History.push()` (which `set_active()` calls into) re-emits Gramps' `active-changed` signal *unconditionally*, even when the handle given is already the active one. `cb_person_selected` therefore only calls `set_active()` when the clicked handle differs from `self.uistate.get_active("Person")`, to avoid a redundant emission.
* `_focus_active_person()` (called from `db_changed()`, `active_changed()`, and the end of `main()`) selects/scrolls to the active person's row purely as a *display* reaction to an already-happened change. It must never itself trigger another "active person changed" notification - that's what the handler-blocking above is protecting against specifically for this code path, and it's the direct fix for a real, reported `Signal recursion blocked... active-changed` warning from Gramps' own `gramps.gen.utils.callback.Callback.emit()`.

## Switching Family Trees needs the phonetic index discarded first, not just refreshed

`db_changed()` is the Gramplet framework's own hook for "the database changed" - reached through Gramps' real Callback/Signal system, not anything this addon wires up itself: `gramps.gen.dbstate.DbState` is a real `Callback` subclass, `gramps.gen.plug._gramplet.Gramplet.__init__` connects `self.dbstate.connect("database-changed", self._db_changed)`, and `_db_changed` sets `self.dbstate.db = db` *before* calling `self.db_changed()` - all confirmed directly in the Gramps source, not assumed. That ordering is exactly why a real bug was possible here: by the time `db_changed()` runs, `self.dbstate.db` is already the *new* database, but `_surname_index`/`_surname_to_handles` are only ever rebuilt by `main()`'s background generator, which does not run synchronously - so they still held handles from the tree that was just closed. `db_changed()` itself calls `_focus_active_person()`, which can select a row in the (still stale) left column, firing `cb_surname_selected` - which then looked up one of those stale handles in the already-current new database and raised `HandleError`, an unhandled exception.

The fix, `_reset_phonetic_index()`, discards both dicts (and the two Matches columns, via `_clear_matches()`) as the very first thing `db_changed()` does, before anything else - including `get_active_object()` - touches the database. It is deliberately a separate method from `_clear_matches()` rather than an extension of it: `cb_name_changed()`'s normal "re-query the same, still-valid index for a different typed name" path also calls `_clear_matches()`, to clear the *displayed* results, while about to re-populate them from those same dicts moments later - folding the dict-reset into `_clear_matches()` itself would wipe the very index that normal path is about to read from, breaking ordinary typing, not just database switches. If you touch either method, keep that distinction: `_clear_matches()` is display-only and safe to call while the index stays valid; `_reset_phonetic_index()` is for when the index itself is no longer valid.

`test/database_switch_test.py` is the regression test for this - and it is worth reading before changing `db_changed()`/`active_changed()`/`main()` again, since it goes out of its way not to shortcut the mechanism that is supposed to invoke `db_changed()`: it uses a real `gramps.gen.dbstate.DbState`, calls its real `signal_change()` to actually `emit()` the `"database-changed"` signal, and lets Gramps' own already-connected chain invoke `db_changed()` - not a direct call, which would leave open the possibility of a fix that works when called directly but not through the actual signal path a real database switch uses. A first attempt at this test used a database stand-in that was not a genuine `gramps.gen.db.base.DbReadBase` subclass; `Callback.emit()` type-checks its arguments and silently returns, calling no connected callback at all, if that check fails - confirmed directly by reading `gramps.gen.utils.callback.Callback.emit`, not assumed - so that version of the test passed for the wrong reason (nothing had run at all) rather than genuinely exercising the fix. The corrected version makes the stand-in a real `DbReadBase` subclass specifically so the signal actually reaches `db_changed()`.

## Nearby surnames vs. browsing the whole tree

The Surname field's dropdown (`_refresh_nearby_combo`) never holds the full surname list - see the freeze story above. Instead it walks outward from the active person in three stages, the same shape as the published `DegreesOfSeparationHome` filter rule addon (rooted at the active person instead of the Home Person):

1. Walk upward from the active person, `NEARBY_DEGREES` generations, collecting ancestors.
2. From *each* ancestor found (including the active person), walk back downward the same number of generations, collecting descendants. Doing this from every ancestor, not just the active person, is what pulls in siblings, cousins, aunts and uncles - not just the direct line.
3. Add the partners/spouses of everyone collected.

This set is bounded by family structure, not tree size, so it stays cheap on a tree of any size. It's a convenience shortlist, not a way to reach everyone in the tree - that's what the "gtk-index" button beside the field is for, which opens `gramps.gui.selectors.SelectorFactory("Person")`, the standard Person selector, unmodified.

## Creating a filter from a match

Double-clicking a row in the **left** (Surname) Matches column (`cb_surname_activated`) builds a `gramps.gen.filters.GenericFilter` and opens it in `gramps.gui.editors.EditFilter`, mirroring the Clipboard module's own "Create a filter from the selected..." feature (`gramps.gui.makefilter.make_filter`) rather than reinventing that flow. `edit_filter_save` (also reused from `makefilter.py`) is passed as the dialog's own save callback, so the filter is written only if the user clicks OK in the dialog - never automatically. It uses the *double-clicked row's* surname, not necessarily whatever is currently typed in the Surname field, since the left column can hold several phonetically-matching surnames at once.

The rule the filter is built from depends on whichever Encoding system is currently selected, looked up via `phonetic_codes.ALGORITHM_FILTER_RULES[algorithm_id]` - **not** hardcoded to `HasSoundexName`. A filter for a NYSIIS or Match Rating Approach result needs a rule that actually tests NYSIIS/Match Rating Approach codes; reusing `HasSoundexName` for those would silently build a filter that doesn't match what the gramplet's own Matches column just showed. If the currently-selected algorithm has no resolvable rule class (its `.gpr.py`'s `ruleclass` doesn't actually name a class present in the module - see `phonetic_codes._resolve_discovered_entries`), `cb_surname_activated` shows an `OkDialog` telling the user so, rather than silently doing nothing or falling back to the wrong rule.

**Known upstream issue, not caused by this code:** clicking "Edit" on the pre-filled rule (or on a rule in *any* filter, built by this gramplet or by hand) can log `Gtk-CRITICAL **: gtk_tree_model_filter_get_path: assertion 'GTK_TREE_MODEL_FILTER (model)->priv->stamp == iter->stamp' failed`. This traces to `EditRule.select_iter()` in `gramps/gui/editors/filtereditor.py`, which passes `Gtk.TreeStore` iterators to a `Gtk.TreeSelection` whose model is actually a `Gtk.TreeModelFilter` wrapping that store - a child/filter iterator mismatch, not anything specific to any one rule or to how this gramplet builds filters. Confirmed reproducible with a manually-created filter too. Worth a Mantis BT report if one doesn't already exist; not fixable from an addon.

## How an encoding system's rule gets discovered

`phonetic_codes._discover_addon_rule_modules` asks `gramps.gen.plug.PluginRegister.get_instance().type_plugins(RULE)` - Gramps' own, already-populated registry of every `RULE`-type plugin it knows about, from every source, core and addon alike - and keeps only the ones whose `PluginData.id` starts with `phonetic_codes._ENCODER_ID_PREFIX` (`"FuzzyMatchingEncoder:"`). This is deliberately *not* a check on where a plugin's files physically live (an earlier version checked `PluginData.fpath` against this addon's own directory instead, and was reverted for exactly this reason): a rule identified by shared folder location can only ever work as long as every encoding system's rule stays bundled inside this one addon's package. Identity by `id` has no such assumption - it's read directly from each plugin's own registration metadata, before anything is imported, and a rule registered from a completely separate, independently installed and independently updated Gramps addon is discovered exactly the same way, as long as it registers with that same id prefix. This was proven directly, not just reasoned about: a throwaway third rule (`metaphonerule.py`/`.gpr.py`, registered with the id prefix but placed in an entirely different directory from this addon, on a separate `sys.path` entry) was picked up by discovery correctly, with its real rule class and `encode` function both resolved.

Each matching plugin's module (`pdata.mod_name`) is imported with a plain, bare `importlib.import_module` - safe regardless of that module's own location, because Gramps' own plugin loader (`gramps.gen.plug._manager.PluginManager.import_plugin`) pushes *that specific plugin's own* directory onto `sys.path` before importing it, independent of where any other of this addon's files live.

This is why a new encoding system needs no changes anywhere else, and why it doesn't need to ship inside this same addon at all: Gramps' own startup scan finds the new `.gpr.py` the normal way it finds every plugin, and `phonetic_codes.py`'s id-prefix filter picks it out from everything else Gramps knows about purely by that declared id, with no shared folder or manual list to maintain. `test/phonetic_codes_test.py`'s `_ensure_addon_rules_are_registered` proves the real, bundled case end-to-end (not just with mocks) by triggering the same `scan_dir` call against this addon's own directory before importing `phonetic_codes`, the same way Gramps' own startup would, and confirming `nysiisrule`, `matchratingrule`, and `metaphonerule` all come back discovered.

Discovering a module and resolving its rule class is not quite the end of the story, though - see `phonetic_codes._make_rule_findable_via_import`, called right after each rule class resolves. This exists because of a real, reported bug, not as precautionary engineering: a filter built via this gramplet's "Define filter" action worked immediately after creation, but once saved and reloaded - which is exactly what happens the next time the Person View applies a saved custom filter - silently matched every person in the tree. Root cause, confirmed directly in the Gramps source: `gramps.gen.filters._filterlist.FilterList.save` writes only the bare class name (e.g. `"HasNysiisName"`) into the saved XML, and `gramps.gen.filters._filterparser.FilterParser` reloads a rule by trying to resolve that name as `gramps.gen.filters.rules.<namespace>.<ClassName>` - which only works if the class is actually an attribute of that module. Gramps' own built-in rules already are; a bare, addon-provided rule module's classes are not, unless something makes them one. Gramps' own plugin manager has an equivalent "make the new rule findable via import statements" step (confirmed directly in both `gramps.gen.plug._manager.BasePluginManager.reg_plugins` on master and the same file on `maintenance/gramps52`), but this addon does not rely on it running first or existing at all in some future Gramps version - `_make_rule_findable_via_import` performs the same `setattr` itself, the moment this addon's own discovery runs. Without it, the reload logs "Filter rule ... not found!", drops the rule from the filter, and an empty rule list is vacuously true under Gramps' own "AND every rule" logic - confirmed directly, not just reasoned about, by building a filter with one of this addon's rules, saving it with Gramps' real `FilterList`, reloading it fresh, and applying it: it matched every person handed to it. `test/filter_persistence_test.py`'s `FilterSaveReloadTest` is the permanent regression test for exactly this - it exists because none of this addon's other tests, which all call a rule's `prepare()`/`apply_to_one()` directly, would ever exercise the save/reload path where the bug actually lived.

A rule class itself follows the same shape as Gramps' own `HasSoundexName` (`gramps/gen/filters/rules/person/_hassoundexname.py`, worth reading directly rather than guessing at the interface): `prepare(self, db, user)` computes whatever's expensive once (here, encoding the target name). The per-person test method is where it gets version-specific, and this is not a minor detail - it caused a second, separate real, reported bug from the same "Fuzzy match: ..." filter: Gramps 6.0+ calls it `apply_to_one(self, db, obj)`, confirmed directly against the real `HasSoundexName` on `master`, while Gramps 5.2 calls it `apply(self, db, obj)` instead, confirmed directly against the real `gramps.gen.filters._genericfilter.GenericFilter` and `Rule` base class on the `maintenance/gramps52` branch, which call `rule.apply(...)` throughout and never mention `apply_to_one` at all. Since this addon declares support for the full `(5.2.0, 6.2.0)` range, every rule here defines **both**: `apply_to_one` as the real implementation, and a small `apply(self, db, obj): return self.apply_to_one(db, obj)` alongside it purely so Gramps 5.2 has something to call. Skipping the older name doesn't fail loudly - a rule missing the method Gramps actually calls just inherits the base `Rule` class's own default, which unconditionally returns `True`, so the filter silently matches every person in the tree instead of raising anything, the same visible symptom as the findability bug above but from an entirely different cause. This was confirmed by simulating Gramps 5.2's exact call (`rule.apply(db, obj)`, not `apply_to_one`) directly against a rule with only `apply_to_one` defined, and separately against one with both - see `test_apply_matches_apply_to_one` in each rule's own test file, and `Gramps52ApplyCompatibilityTest` in `test/filter_persistence_test.py` for the combined reload-plus-apply() scenario. The reference example `nysiisrule.gpr.py`/`matchratingrule.gpr.py`/`metaphonerule.gpr.py`'s registration shape was modeled on `gramps-project/addons-source`'s `FilterRules/hasrolerule.py`, a currently-maintained third-party addon rule - but that one only targets Gramps 6.1+, so it only needed `apply_to_one`; it isn't a template for the dual-method compatibility this addon's own broader version range requires.

## Layout position is persisted via `ConfigManager`, in the addon's own folder

The Matches panel's divider position survives restarts via `gramps.gen.utils.configmanager.ConfigManager`, not a hand-rolled config file:

```python
CONFIG = global_config.register_manager("FuzzyMatchingGramplet", use_plugins_path=False)
```

`use_plugins_path=False` with no `override` makes `ConfigManager` use *the calling file's own directory* for the `.ini` (see the "Simple.ini" example in `register_manager`'s docstring) - this addon's own folder, alongside `FuzzyMatchingGramplet.py`, rather than Gramps' general per-user config directory. Reading/writing goes through the Gramplet framework's `on_load()`/`on_save()` lifecycle hooks, so the file is written at sensible points (e.g. closing Gramps), not on every pixel of a drag.

The `.ini`'s `[meta]` block (`plugin_id`, `schema_version`) identifies which addon the file belongs to, matching the convention used by this addon's sibling gramplets. It's registered with an empty placeholder default and then explicitly `.set()`, rather than registering the real value as the default directly: `ConfigManager.save()` comments out (`;;`) any key whose current value equals its own registered default, so registering the real identifying value as the default would leave `[meta]` permanently commented-out instead of recording it as a live identifier.

If you add a new persisted setting, register it the straightforward way (real default, no placeholder dance) unless you specifically need it to always appear uncommented regardless of whether it's been changed - that's a `[meta]`-block-specific need, not a general pattern.

## Running the tests

```bash
GRAMPS_RESOURCES=. python3 -m unittest discover -p "*_test.py"
```

Run from the addon's root directory. Three non-obvious things had to be gotten right here, most stemming from the same fact: a Gramps addon like this one is not an installed Python package, so neither Gramps' own plugin loader nor `unittest discover` treat it like one.

* **`test/__init__.py` must exist**, or `unittest discover` run this way silently reports "NO TESTS RAN" instead of an error - it doesn't find `test/` at all without it.
* **`test/phonetic_codes_test.py` cannot use a relative import** (`from .. import phonetic_codes`) to reach `phonetic_codes.py`. With `test/__init__.py` present, `test` becomes the top-level package when discovered this way, so `..` goes beyond it (`ImportError: attempted relative import beyond top-level package`). It instead inserts the addon root onto `sys.path` directly and imports `phonetic_codes` by its bare name - the same pattern `FuzzyMatchingGramplet.py` itself has to use to reach `phonetic_codes.py`, since Gramps' plugin loader (`gramps.gen.plug._manager.PluginManager.import_plugin`) imports a gramplet's main module as a bare top-level module after pushing the addon's own folder onto `sys.path`, not as part of a package - a package-relative import there fails with "attempted relative import with no known parent package" even though it looks correct.
* **`test/database_switch_test.py` needs a real or virtual display** (e.g. `xvfb-run -a python3 -m unittest discover ...` on a headless machine): unlike every other test file here, it constructs the actual gramplet, not a stand-in, which means constructing its real GTK widgets too. It is also the one test file where import order matters for a reason worth knowing about: `phonetic_codes.py`'s discovery of this addon's own `RULE` plugins runs once, at import time, so whichever test file imports `FuzzyMatchingGramplet` (and, transitively, `phonetic_codes`) first needs to have already triggered Gramps' plugin-registration scan itself - `database_switch_test.py` does this the same way `filter_persistence_test.py`/`phonetic_codes_test.py` do, but discovering it the hard way (all four algorithms silently collapsing to just the hardcoded Soundex entry, in whichever test file happened to run alphabetically first) is a real trap for a new test file that imports the gramplet without copying that pattern.

If you add a new module to the addon that other modules need to import, give it the same bare-import treatment; a normal `from . import whatever` will work under some test runners and fail under Gramps' real plugin loader, or vice versa, depending on exactly how it's invoked.

### Testing against a bare source checkout of Gramps

If `PYTHONPATH` points at a plain `git clone` of Gramps master rather than an installed/packaged copy, two dependencies are easy to be missing and will surface as confusing import errors deep inside `gramps.gen.filters`/`gramps.gui.displaystate` (which these tests need, transitively, for `HasSoundexName`/`HasNysiisName`/`HasMatchRatingName`/`EditFilter`): `orjson` (used by `gramps.gen.lib.serialize`, added as a Gramps dependency in 6.0 - not present or needed on an actual Gramps 5.2 install) and `pycairo` (used by `gramps.gui.logger`). Neither is anything this addon imports or depends on itself; they only surface because a bare checkout of Gramps *master* doesn't install its own runtime dependencies for you the way a packaged install would.

Testing this way against master exercises 6.x-shaped internals, not literally 5.2's - and that distinction turned out to matter in practice, not just in theory: `gramps.gen.filters.rules.Rule`'s per-person test method is named `apply_to_one` on master but `apply` on the real `maintenance/gramps52` branch (see "How an encoding system's rule gets discovered" above for the bug this caused and how it's handled), confirmed by fetching and reading the actual 5.2 branch source directly, not by assuming API stability across versions. Where this addon's own code depends on something Gramps-version-specific, treat "confirmed against master" as exactly that, not as "confirmed across the whole declared range" - check the actual `maintenance/gramps52` branch too when it matters, the same way this one difference was found.

`GRAMPS_RESOURCES` is also stricter than it looks: `gramps.gen.utils.resourcepath.ResourcePath` only accepts it if `<GRAMPS_RESOURCES>/gramps/authors.xml` actually exists at that exact relative path - a bare checkout keeps that file at `data/authors.xml` instead, so pointing `GRAMPS_RESOURCES` at the checkout root or `.` does not satisfy it. A minimal directory built just to pass the check (`mkdir -p somewhere/gramps && touch somewhere/gramps/authors.xml`, then `GRAMPS_RESOURCES=somewhere`) is enough for these tests, which do not depend on the real resource files' contents.
