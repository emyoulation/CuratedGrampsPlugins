# Auto Active and Home Person
This addon is for developers. It has no user interface: it is a "monkey patch" that changes how Gramps behaves while Gramps is running, without changing any Gramps files. It is a field test for a small Gramps core change, described in [Proposed core change](#proposed-core-change).

## The problem
A new user creates a Family Tree and adds the first person. Gramps sets neither an Active Person nor a Home Person, so the Relationships view stays blank, the Home button does nothing, and many gramplets show nothing. The same happens after the first import into an empty tree. New users take this as a bug. It is one of the problems listed in the Friendlier First Hour review of novice reports.

Gramps already chooses an Active Person in one place: `History.clear()` in `gramps/gui/displaystate.py` pushes `db.find_initial_person()` for the Person history. `clear()` runs when a tree is opened and again on every `person-rebuild` signal (through `History.history_changed()`), which is how an import ends. `find_initial_person()` returns the Home Person, or else whichever row `SELECT handle FROM person` returns first, which depends on the database engine. It never sets a Home Person.

So there are three gaps:
- Adding the first person to a tree that was empty when it was opened sets neither person, because `person-add` does not reach `History`.
- After an import into an empty tree, the Active Person is an arbitrary person, and no Home Person is set.
- A tree that has people but no Home Person never gets one.

## What the addon does
- When a tree is opened, it is checked once. If the tree already has a Home Person, the addon connects nothing and does nothing more for that tree. Established trees see no overhead.
- Otherwise the addon listens to the database signals `person-add`, `person-update` and `person-rebuild`. The rebuild signal is needed because imports do not send per-person signals (Gramps XML and CSV import in a batch transaction, GEDCOM disables signals); all three importers end with `request_rebuild()`.
- The work is deferred with `GLib.idle_add`, so it runs after the transaction commit and after the other signal handlers, and a burst of signals costs one pass.
- When there is at least one Person:
  - If there is no Active Person, the last created Person becomes the Active Person (`uistate.set_active()`).
  - If there is no Home Person, or the Home Person handle points at a Person that no longer exists, the first created Person becomes the Home Person (`db.set_default_person_handle()`).
- After a `person-rebuild` in a tree without a Home Person, core has already pushed the arbitrary pick of `find_initial_person()` (core connects its handler first, so it runs first). The addon treats that Active Person as missing and replaces it.
- When both are set, the addon disconnects its handlers for that tree.

### Creation order
Gramps creates handles with `create_id()` in `gramps/gen/utils/id.py`, which starts each handle with a time stamp. Sorting the handles therefore sorts the people by creation time: the smallest handle is the first Person created, the largest is the last one created (after an import, the final imported Person). Because handles are unique, the Active Person and the Home Person are the same Person only when the tree has exactly one Person.

Change times are not used. Imports keep the change times of the source program (the GEDCOM `CHAN` tag, the Gramps XML `change` attribute), so the "last modified" Person after an import can be anyone in the file.

### A detail that is easy to miss
`uistate.get_active("Person")` returns an empty string, not `None`, when the Person history is empty (`History.present()`). A test for `is None` never sees a missing Active Person.

## Limits
- A Gramps XML (.gramps) or .gpkg import keeps the handles from the tree where the file was made. "First" and "last" then follow the creation order in that tree, not the order of the import.
- In a tree that has people but no Home Person, the first Person change in the session sets the Home Person to the oldest Person.
- Setting the Home Person cannot be undone with Edit > Undo, the same as the core Set Home Person command.
- `person-delete` is not watched. If the Home Person is deleted later, no new Home Person is chosen (core clears the handle in `delete_person_from_database()`).
- Only Gramps 5.2, 6.0 and 6.1 are registered.

## Proposed core change
In core, the fix belongs where Gramps already chooses the initial Active Person: `History.clear()`. The addon keeps established trees free of overhead by disconnecting; in core, the same result costs one cheap test per `person-add` signal.

**1. `gramps/gen/db/base.py`, `gramps/gen/db/generic.py` and `gramps/plugins/db/dbapi/dbapi.py`.** Add two small queries, so the GUI does not need to load every handle:

```python
def find_first_created_person_handle(self):
    """Return the handle of the oldest Person, or None."""
    self.dbapi.execute("SELECT handle FROM person ORDER BY handle ASC LIMIT 1")
    row = self.dbapi.fetchone()
    return row[0] if row else None


def find_last_created_person_handle(self):
    """Return the handle of the newest Person, or None."""
    self.dbapi.execute("SELECT handle FROM person ORDER BY handle DESC LIMIT 1")
    row = self.dbapi.fetchone()
    return row[0] if row else None
```

`find_initial_person()` should use the first query for its fallback, so the Person chosen no longer depends on the database engine.

**2. `gramps/gui/displaystate.py`, class `History`.** Move the Person part of `clear()` into its own method, extend it, and call it from `clear()` and from a new `person-add` handler:

```python
def clear(self):
    self.history = []
    self.mru = []
    self.index = -1
    self.lock = False
    if self.nav_type == "Person":
        self.choose_initial_person()


def choose_initial_person(self):
    """
    Choose an Active Person, and a Home Person if the tree has none.
    The Home Person is the first created Person; with no Home Person
    the Active Person is the last created one.
    """
    if not self.dbstate.is_open():
        return
    db = self.dbstate.db
    home = db.get_default_handle()
    if home and db.has_person_handle(home):
        self.push(home)
        return
    first = db.find_first_created_person_handle()
    if first is None:
        return  # empty tree
    db.set_default_person_handle(first)
    self.push(db.find_last_created_person_handle())


def cb_person_added(self, handle_list):
    """Fill an empty Person history when the first people are added."""
    if not self.history:
        self.choose_initial_person()
```

and in `__init__`, for the Person history only:

```python
if nav_type == "Person":
    self.signal_map["person-add"] = self.cb_person_added
```

`person-rebuild` needs no change: `history_changed()` already calls `clear()`. In an established tree the new handler costs one list test per `person-add`.

When a tree with people but no Home Person is opened, this sets the Home Person at load instead of at the first Person change of the session (as the addon does). That writes one metadata value when the tree opens.

**3. Placement in the gen layer was considered and rejected.** Setting the Home Person inside `add_person()` or `transaction_commit()` would also cover the command line, but it would write metadata in the middle of a transaction and would run during batch imports. Choosing an Active Person is a GUI concept in any case, and `History` already owns that choice.

**4. Related work.** [Import with No Tree Loaded](https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/ImportWithoutTree/README.md), and its planned core version, sets the Home Person and Active Person itself after it creates a tree for an import. With the change above, that code could be dropped.

## Testing
1. Create a new Family Tree and load it. Add one Person. That Person becomes both the Active Person and the Home Person.
2. Add a second Person. Nothing changes.
3. Create another new tree and import a GEDCOM file. The first imported Person becomes the Home Person and the last imported Person becomes the Active Person.
4. Open a tree that already has a Home Person and work normally. The addon connects nothing (run Gramps with `--debug=.AutoActiveHome` to see the log lines).

## Assumptions I made
- "First created" and "last created" by handle order are good enough stand-ins for creation time, including after GEDCOM and CSV imports.
- A missing Home Person should be filled in automatically even in an older tree that never had one, at the first Person change of the session.
- The proposed core change belongs in the GUI `History` class, not in the database layer.
