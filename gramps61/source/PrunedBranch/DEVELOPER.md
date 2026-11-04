# Pruned Branch — Developer Notes
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [DEVELOPER.md](DEVELOPER.md)

## Files
| File | Purpose |
|------|---------|
| `PrunedBranch.gpr.py` | Tool registration (Gramps 6.0 or newer, TOOL_UTILS, EXPERIMENTAL). |
| `PrunedBranch.py` | Tool dialog, `BranchSession` (start, end, signal handlers, colors), settings, open-editor guard, monkey-patches. |
| `prunedbranch_db.py` | `BranchDb` wrapper, keep-set computation, SQLite TEMP keep-tables, callback helpers. |
| `prunedbranch_bench.py` | Benchmark report. |
| `PrunedBranch.ini` | Settings, created beside the module on first use (recent tags per tree). |
| `media/pruned_branch.css` | Session stylesheet (the only one during beta). |
| `media/screenshot.png`, `media/tool_dialog.png` | README images. |

Sibling modules are imported at module level only: Gramps adds the plugin folder to `sys.path` during import and removes it afterward.

## Design
How the session limits listings without touching the tree file.

### Wrapper, not patched database
`BranchDb` wraps `dbstate.db`. It overrides only the listing calls for the nine primary object types: `get_X_handles`, `iter_X_handles`, `iter_<plural>`, `get_X_cursor`, `get_number_of_<plural>`, `_iter_raw_X_data`, plus `get_place_tree_cursor` and `_iter_raw_place_tree_data`. Everything else is forwarded by `__getattr__`; attribute writes are forwarded by `__setattr__` (except `_pb_*` names).

Instance-patching the real database was rejected. Database-internal code calls `self.get_person_cursor()` and similar (for example `dbapi.reindex_reference_map`), and `DbGeneric.__init__` captures bound listing methods in its table-function map. Patching would make Rebuild Reference Maps cover only the branch. With a wrapper, `self` inside those methods is still the real database.

`BranchDb.__class__` is a property that returns the class of the real database. `DbState` declares `database-changed` for `DbReadBase` or `ProxyDbBase`, and `Callback.emit()` silently drops (after printing "Signal emitted with wrong arg types") a signal whose argument fails `isinstance()`. `isinstance()` consults `__class__`, as `unittest.mock` spec objects do. Inheriting from `DbReadBase` is not possible: its stub methods would be found before `__getattr__`. `type(wrapper)` is still `BranchDb`.

### Switching the database
`BranchSession.prepare()` builds the branch (keep sets, keep-tables, wrapper) without switching; `start()` calls it, then switches. Start: `dbstate.change_database_noclose(wrapper)`, then `dbstate.signal_change()`. This is the same pattern as `DbState.apply_proxy()`. A temporary listener checks that the signal really delivered the wrapper; if not, the session switches back, empties the keep-tables and reports an error instead of showing a red window over the full tree.

Side effects of `database-changed` that matter:
- `EditPrimary` closes on it without saving, hence the open-editor guard below.
- Navigation history is cleared; the Active Person is restored afterward.
- `DisplayState.db_changed` (`long-op-start`) and the clipboard reconnect to the database without disconnecting first. Harmless after a real tree change (the old database is closed), but Pruned Branch keeps the same real database. `drop_duplicate_callbacks()` snapshots the callback keys before the switch and afterward disconnects any new callback that repeats one already connected (equal callables, or lambdas with the same code and closure values).

`Callback.emit()` only calls plain functions and bound methods (`types.FunctionType`, `types.MethodType`). `functools.partial` objects are skipped with "Badly formed entry in callback map", so the per-table handlers are closures made by `_make_handler()`.

`Callback.emit()` iterates its callback list directly, and `disconnect()` removes from that list. A handler that disconnects itself during the emission makes Gramps skip the next callback. The session therefore ends through `GLib.idle_add` when another tree is opened, not inside the `database-changed` handler.

`end()` clears `SESSION` first, then runs the switch in `_end_switch()` inside `try`/`finally`, so the window class, status bar button, stylesheet and title are always restored, even after an error.

### Keep sets
`compute_keep_sets()` feeds a seed object (real database, but `iter_person_handles()` returns the chosen people) to `ReferencedBySelectionProxyDb(all_people=True)`, the engine class behind the Export Assistant reference filter. The proxy is used read-only and discarded; its `referenced` sets become the keep sets. FilterProxyDb is never used, because it strips references to filtered-out records.

`_FastReferencedBySelection` changes three things:
- The engine stores the allowed people as a list, so each membership test is O(n). The subclass converts it to a set on first use.
- `process_family()` keeps a family only when its father, mother or a child is in the branch. Without this, a family reached through a Note link (`process_note` queues `gramps://Family/handle/...`) or an LDS ordinance joins with all its events, places, citations and media.
- `process_object()` ignores `Event`. Events reached through event references go through `process_event_ref()`, which calls `process_event()` directly; `process_object("Event")` is only reached from Note links.

Note links to other object types are still followed. These method names are the same in 5.2, 6.0 and 6.1.

Known engine quirk (not fixed): `process_place()` reuses the variable `place` in its loop, so `process_tags()` runs on the last enclosing place instead of the original place. Tags are not limited by the session, so this has no effect here.

### SQL keep-table join (the "cookie cutter")
On SQLite, `KeepTables` keeps `temp.pb_keep_<table>` (one column, `handle` PRIMARY KEY) on the real connection, filled with `executemany`. Raw iteration becomes:

`SELECT t.handle, t.<data_field> FROM temp.pb_keep_<table> AS k CROSS JOIN main.<table> AS t ON t.handle = k.handle`

- `CROSS JOIN` forces SQLite to walk the small keep-table and probe the big table by its primary key.
- Each read uses its own cursor (`dbapi.cursor()`), fetches all rows and closes the query before yielding the first record. Gramplets and view models pause between records; a query left open would hold the keep-table.
- `data_field` comes from `serializer.data_field` (`json_data` on 6.x).
- TEMP tables live in SQLite temporary storage, never in the tree file, and vanish when the connection closes.
- Counts and handle iteration come from the Python sets; sorted lists filter the real sorted query by the set.

The keep-tables are never dropped. SQLite refuses `DROP TABLE` while any query on the connection is open ("database table is locked"), even a query on another table, and after a switch the views and gramplets keep full-tree queries open while they reload. `create()` uses `CREATE TEMP TABLE IF NOT EXISTS`, then `DELETE`, then inserts; `clear()` empties the tables at session end. Neither is affected by open queries.

Transaction pitfall: Gramps uses Python sqlite3 implicit transactions, and `transaction_commit` emits `*-add` signals after it commits. An INSERT in a signal handler would leave an implicit transaction open, and the next `BEGIN TRANSACTION;` from Gramps would fail. `KeepTables._commit()` therefore commits right away when `db.transaction is None`.

Rejected: TEMP views named like the real tables. SQLite searches the `temp` schema first, so they would limit every query, including writes (which would fail), `XmlWriter` backups, `reindex_reference_map` and Gramps ID uniqueness checks.

Fallback: on DB-API backends other than SQLite, the wrapper uses per-handle `get_raw_X_data()` reads (the "python" strategy).

### Monkey-patches (installed on first session start, then pass-through)
| Target | Behavior during a session |
|--------|---------------------------|
| `ViewManager._ViewManager__backup` | Autobackup and backup on exit: `dbstate.db` swapped to the real database for the call. |
| `QuickBackup.__init__` | Make Backup (the dialog runs inside `__init__`): same swap. |
| `ExportAssistant.save` | Every export uses the full tree; the export person filter still works. |
| `gramps.gui.plug.tool.gui_tool` | Asks before any tool runs. TOOL_DBFIX: end session or cancel. Other categories: run on branch, end session first, or cancel. The Pruned Branch tool itself is exempt. |
| `ManagedWindow.set_window` | A gramplet detached during a session gets the `pruned-branch` class on its window. |

### Open-editor guard
`open_editor_titles()` walks `uistate.gwm` (`window_tree` and `id2item`) for `EditPrimary`, `EditSecondary` and `EditReference` instances. Start, the status bar button, End branch and "End branch, then run" refuse while any are open and list their titles. `end(switch_back=False)` (another tree opened, or the tree closed) skips the guard: Gramps has already closed the editors. `end()` returns True only when the session ended.

### Keeping the branch current
Handlers on the real database: `<table>-add` and `<table>-delete` for all nine types, `person-update` (adds own and parent families of branch people), `family-update` (adds father, mother and children of branch families). A dbstate `database-changed` handler ends the session without switching back when another tree is loaded or the tree is closed.

### Benchmark without a session
With no session active, **Run benchmark** applies the People choice, makes a trial `BranchSession`, calls `prepare()` and passes it to `run_benchmark(..., trial=True)`. Gramps is never switched, so no view, gramplet or signal sees the trial wrapper. The keep-tables are emptied afterward (only when no real session has started meanwhile). The report marks the branch as a trial and says that switching times were not measured.

### Settings
`PrunedBranch.ini` is a core `ConfigManager` registered with `register_manager(PLUGIN_ID, override=__file__, use_plugins_path=False)`, so it sits beside the module. `[meta]` holds `plugin_id='PrunedBranch'` and `schema_version='1'`; a file with another plugin id, another schema or no `[meta]` block is reset and replaced on the next save. The meta defaults are empty strings on purpose: `ConfigManager.save()` comments out values equal to their default, and the real values must be written for the check to work.

`tags.recent` is `{tree id: {"tree": tree name, "tags": [tag handle, ...]}}`, newest first, up to 10 per tree. The tree id is `db.get_dbid()`; the tree name is only there to make the file readable. A tag is recorded only when a session actually starts from it.

### Colors
`load_session_css()` loads `media/pruned_branch.css` from the addon folder; **Customize colors** opens that same file. During beta there is no user copy (an earlier build copied it to `<USER_CSS>/pruned-branch/`; that subfolder was chosen because `webstuff.py` offers every `.css` file directly in `USER_CSS` as a Narrated Web Site stylesheet, which matters if user copies return). Priority is `STYLE_PROVIDER_PRIORITY_APPLICATION + 10`: above `gramps.css` and the Themes addon CSS themes and patches, below the Themes addon `gramps_user.css` (USER priority).

The provider is added only while a session is active. Most rules are scoped to `.pruned-branch` (the main window and detached gramplet windows during a session) or `.pruned-branch-alert` (status bar button). Pop-up menus cannot be scoped: each menu is its own top-level window, outside the main window. They inherit the text color of the item that opened them, so the menu rules set every color. Menu rules use the child combinator (`menu > menuitem:hover`): GTK treats an open submenu as part of the item that opened it, so a descendant selector would highlight a whole open submenu.

Buttons are drawn lighter than the window, as GTK themes do. Flat buttons keep their borderless look and only change on hover or when checked. The toolbar selectors repeat the `:not()` parts so they outrank the framed-button rule.

The first line of the stylesheet, `/* pruned-branch-css-version: N */`, is reserved for user copies: when they return, a copy older than the default can be detected and reported.

## Verified against the Gramps source
Checked in the `maintenance/gramps52`, `maintenance/gramps60` and `maintenance/gramps61` branches (and master for `select_from_*`):
- No `select_from_*` methods exist in any branch.
- The listing method names are identical in 6.0 and 6.1.
- `GenericFilter.apply()` and the list view models (`peoplemodel.py` uses `db.get_person_cursor` as `gen_cursor`) only use the wrapped listing calls.
- The core Dashboard gramplets (Surname Cloud, Top Surnames, Given Name Cloud, Age Stats, Statistics, Records, To Do) and the Calendar and Age on Date quick reports only use wrapped listing calls.
- Backup and export hooks, `GrampletWindow` and `DetachedWindow` have the same names in 5.2, 6.0 and 6.1.

## Headless tests
Synthetic SQLite tree, 10,000 people: both strategies return the same subset; enclosing places are included and the place tree is complete; a filter on the branch matches the tagged people; an edit through the wrapper keeps family links outside the branch; new Gramps IDs are unique in the whole tree; a keep-table INSERT followed by a Gramps transaction works; undo through the wrapper works; Rebuild Reference Maps through the wrapper covers the whole tree.

Gramps 6.0 `example.gramps` (SQLite): a 3-person branch lists 3 people and one surname through `iter_people()` with both strategies; `DbState` delivers `database-changed` with the wrapper; paused branch readers do not block clearing the keep-tables; clearing works with a full-tree reader open, and a second session reuses the tables with the right rows; the settings file saves, reloads and rejects an older schema.

## Open questions for the 65,000-person test
- Real speed-up per record type, SQL join against per-handle reads (benchmark report).
- Time to build the session (filter, closure, keep-tables) and to switch views.
- Memory use of the fetch-all reads on a large branch.
- Whether the CSS selectors cover the toolbar, menus and gramplets of other themes.
- Whether existing people who join the branch through an edit appear in list views without a restart.
