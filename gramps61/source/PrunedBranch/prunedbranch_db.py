"""
Pruned Branch - database side (draft prototype, Gramps 6.0+).

BranchDb wraps the open database. Only LISTING calls (handle lists,
iterators, cursors, counts, raw iterators) are limited to the branch.
Everything else (single-record reads, commits, undo, signals, backlinks,
Gramps ID checks, reindex/rebuild) is forwarded to the real database,
where ``self`` is still the real database and sees the whole tree.
"""

import logging

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db.generic import Cursor
from gramps.gen.lib import (
    Citation,
    Event,
    Family,
    Media,
    Note,
    Person,
    Place,
    Repository,
    Source,
)
from gramps.gen.proxy import ReferencedBySelectionProxyDb

LOG = logging.getLogger(".PrunedBranch")

# table name: (object class, singular method stem, plural method stem)
TABLES = {
    "person": (Person, "person", "people"),
    "family": (Family, "family", "families"),
    "event": (Event, "event", "events"),
    "place": (Place, "place", "places"),
    "source": (Source, "source", "sources"),
    "citation": (Citation, "citation", "citations"),
    "repository": (Repository, "repository", "repositories"),
    "media": (Media, "media", "media"),
    "note": (Note, "note", "notes"),
}
# These real get_X_handles() methods accept (sort_handles, locale).
SORTABLE = {"person", "family", "place", "source", "citation", "media"}

STRATEGY_SQL = "sql"
STRATEGY_PYTHON = "python"


def is_sqlite(db):
    """True when db is a DB-API database on the SQLite backend."""
    dbapi = getattr(db, "dbapi", None)
    return dbapi is not None and type(dbapi).__module__.endswith("sqlite")


def callback_keys(db):
    """Keys of every callback currently connected to the real db."""
    cmap = getattr(db, "_Callback__callback_map", {})
    return {key for entries in cmap.values() for key, _fn in entries}


def _same_callback(one, two):
    """True for equal callables, or lambdas with the same code and values."""
    if one == two:
        return True
    code = getattr(one, "__code__", None)
    if code is None or code is not getattr(two, "__code__", None):
        return False
    try:
        cells_one = [cell.cell_contents for cell in one.__closure__ or ()]
        cells_two = [cell.cell_contents for cell in two.__closure__ or ()]
    except ValueError:  # an empty cell
        return False
    return cells_one == cells_two


def drop_duplicate_callbacks(db, before):
    """
    Disconnect callbacks connected since the snapshot "before" (from
    callback_keys) that repeat a callback which was already connected.

    A database switch makes every "database-changed" listener connect to
    the new database. Most listeners disconnect from the old one first.
    A few core ones do not (DisplayState.db_changed connects
    "long-op-start"; the clipboard connects its update and delete
    handlers), which is harmless after a real tree change, because the
    old database is closed. Pruned Branch keeps the same real database,
    so those connections would pile up with every start and end.

    :returns: the number of callbacks disconnected
    """
    cmap = getattr(db, "_Callback__callback_map", {})
    doomed = []
    for entries in cmap.values():
        old = [fn for key, fn in entries if key in before]
        for key, fn in entries:
            if key not in before and any(_same_callback(fn, o) for o in old):
                doomed.append(key)
    for key in doomed:
        db.disconnect(key)
    return len(doomed)


def count_callbacks(db, signal=None):
    """Diagnostic: number of callbacks connected to the real db."""
    cmap = getattr(db, "_Callback__callback_map", {})
    if signal:
        return len(cmap.get(signal, []))
    return sum(len(v) for v in cmap.values())


# ------------------------------------------------------------
# Subset computation (engine code: ReferencedBySelectionProxyDb)
# ------------------------------------------------------------
class _PeopleSeed:
    """Real db, except iter_person_handles() returns the chosen people."""

    def __init__(self, real, people):
        self._real = real
        self._people = people

    def iter_person_handles(self):
        return iter(self._people)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _FastReferencedBySelection(ReferencedBySelectionProxyDb):
    """
    Same traversal as the export dialog's reference filter, with three
    changes:

    - The engine keeps the allowed people in a list, which makes every
      membership test O(n); turn it into a set on first use.
    - A Family is kept only when its father, mother or one of its
      children is in the branch. Without this, a family linked from a
      Note (or from an LDS ordinance) joins the branch with all of its
      events, places, citations and media, even when nobody in it is in
      the branch.
    - An Event is kept only when a kept person or kept family refers to
      it. The engine reaches events in two ways: through event
      references (process_event_ref calls process_event directly), and
      through links inside Notes (queued, then process_object). Only the
      second way is dropped, so every event of the branch is still kept.
    """

    def _pb_allowed_people(self):
        allowed = self.restricted_to.get("Person")
        if allowed is not None and not isinstance(allowed, (set, frozenset)):
            allowed = set(allowed)
            self.restricted_to["Person"] = allowed
        return allowed

    def process_person(self, person, reference=True):
        self._pb_allowed_people()
        return super().process_person(person, reference)

    def process_family(self, family):
        if family is None or family.handle in self.referenced["Family"]:
            return
        allowed = self._pb_allowed_people()
        if allowed is not None:
            members = [family.get_father_handle(), family.get_mother_handle()]
            members.extend(ref.ref for ref in family.get_child_ref_list())
            if not any(handle in allowed for handle in members if handle):
                return
        super().process_family(family)

    def process_object(self, class_name, handle, reference=True):
        # Events only arrive here from links inside Notes.
        if class_name == "Event":
            return
        super().process_object(class_name, handle, reference)


def compute_keep_sets(real, people_handles):
    """
    Return {table: set(handles)} for the people plus everything they
    reference (families, events, places incl. enclosing places,
    citations, sources, repositories, media, notes).
    """
    proxy = _FastReferencedBySelection(
        _PeopleSeed(real, list(people_handles)), all_people=True
    )
    keep = {table: set() for table in TABLES}
    for class_name, handles in proxy.referenced.items():
        table = class_name.lower()
        if table in keep:
            keep[table] = set(handles)
    return keep


# ------------------------------------------------------------
# The "cookie cutter": TEMP keep-tables on the real connection
# ------------------------------------------------------------
class KeepTables:
    """
    One TEMP table per object type (temp.pb_keep_<table>). TEMP tables
    live in SQLite temporary storage, never in the tree file, and vanish
    when the connection closes.
    """

    def __init__(self, real):
        self.real = real
        self.dbapi = real.dbapi

    def _commit(self):
        # Gramps uses implicit transactions; an INSERT outside a Gramps
        # transaction leaves one open, and the next "BEGIN TRANSACTION;"
        # would fail. Commit our own writes right away.
        if getattr(self.real, "transaction", None) is None:
            self.dbapi.commit()

    def _executemany(self, sql, handles):
        conn = getattr(self.dbapi, "_Connection__connection", None)
        if conn is not None:
            conn.executemany(sql, ((h,) for h in handles))
        else:
            for handle in handles:
                self.dbapi.execute(sql, [handle])

    def create(self, keep):
        """
        Create the keep-tables if needed, empty them and fill them.

        Tables are created once per connection and then reused: SQLite
        refuses DROP TABLE while ANY query on the connection is still open
        ("database table is locked"), and after a session switch the views
        and gramplets keep full-tree queries open while they reload.
        CREATE ... IF NOT EXISTS and DELETE have no such limit.
        """
        for table in TABLES:
            self.dbapi.execute(
                f"CREATE TEMP TABLE IF NOT EXISTS pb_keep_{table} "
                "(handle VARCHAR(50) PRIMARY KEY NOT NULL)"
            )
            self.dbapi.execute(f"DELETE FROM temp.pb_keep_{table}")
            self._executemany(
                f"INSERT OR IGNORE INTO temp.pb_keep_{table} (handle) VALUES (?)",
                keep[table],
            )
        self._commit()

    def add(self, table, handles):
        self._executemany(
            f"INSERT OR IGNORE INTO temp.pb_keep_{table} (handle) VALUES (?)",
            handles,
        )
        self._commit()

    def remove(self, table, handles):
        self._executemany(
            f"DELETE FROM temp.pb_keep_{table} WHERE handle = ?", handles
        )
        self._commit()

    def clear(self):
        """
        Empty the keep-tables at session end (see create() for why they
        are not dropped). The empty tables vanish with the connection.
        """
        for table in TABLES:
            try:
                self.dbapi.execute(f"DELETE FROM temp.pb_keep_{table}")
            except Exception:
                LOG.debug("Pruned Branch: cannot empty pb_keep_%s", table, exc_info=True)
        try:
            self._commit()
        except Exception:
            LOG.debug("Pruned Branch: commit after clear failed", exc_info=True)


# ------------------------------------------------------------
# BranchDb wrapper
# ------------------------------------------------------------
class BranchDb:
    """Listing calls limited to the branch; everything else forwarded."""

    def __init__(self, real, keep, strategy):
        dct = self.__dict__
        dct["_pb_real"] = real
        dct["_pb_keep"] = keep
        dct["_pb_strategy"] = strategy
        for table, (cls, one, many) in TABLES.items():
            self._pb_install(table, cls, one, many)
        dct["_iter_raw_place_tree_data"] = self._pb_iter_place_tree
        dct["get_place_tree_cursor"] = lambda: Cursor(self._pb_iter_place_tree)

    # --- forwarding -------------------------------------------------
    def __getattr__(self, name):
        # Only called for names not found on the wrapper itself.
        return getattr(self.__dict__["_pb_real"], name)

    def __setattr__(self, name, value):
        if name.startswith("_pb_"):
            self.__dict__[name] = value
        else:
            setattr(self._pb_real, name, value)

    @property
    def real_db(self):
        return self._pb_real

    # isinstance() also consults __class__. DbState declares the
    # "database-changed" signal for DbReadBase or ProxyDbBase, and
    # Callback.emit() drops a signal whose argument fails that check (it
    # only prints a warning). Reporting the real database class lets the
    # signal through. type(wrapper) is still BranchDb.
    @property
    def __class__(self):
        return type(self.__dict__["_pb_real"])

    # --- generated listing methods ------------------------------------
    def _pb_install(self, table, cls, one, many):
        real = self._pb_real
        keep = self._pb_keep[table]
        dct = self.__dict__

        def iter_raw():
            return self._pb_iter_raw(table, one)

        def get_handles(sort_handles=False, locale=glocale):
            if sort_handles and table in SORTABLE:
                full = getattr(real, f"get_{one}_handles")(True, locale)
                return [h for h in full if h in keep]
            return list(keep)

        def iter_objects():
            for _handle, data in iter_raw():
                yield real.serializer.data_to_object(data, cls)

        dct[f"_iter_raw_{one}_data"] = iter_raw
        dct[f"get_{one}_cursor"] = lambda: Cursor(iter_raw)
        dct[f"get_{one}_handles"] = get_handles
        dct[f"iter_{one}_handles"] = lambda: iter(list(keep))
        dct[f"iter_{many}"] = iter_objects
        dct[f"get_number_of_{many}"] = lambda: len(keep)

    def _pb_iter_raw(self, table, one):
        if self._pb_strategy == STRATEGY_SQL:
            yield from self._pb_iter_raw_sql(table)
        else:
            get_raw = getattr(self._pb_real, f"get_raw_{one}_data")
            for handle in list(self._pb_keep[table]):
                data = get_raw(handle)
                if data is not None:
                    yield (handle, data)

    def _pb_iter_raw_sql(self, table):
        real = self._pb_real
        field = real.serializer.data_field
        # CROSS JOIN makes SQLite walk the small keep-table and probe the
        # big table by its PRIMARY KEY.
        sql = (
            f"SELECT t.handle, t.{field} FROM temp.pb_keep_{table} AS k "
            f"CROSS JOIN main.{table} AS t ON t.handle = k.handle"
        )
        # Read every row and close the query BEFORE yielding anything.
        # Callers (gramplets, view models) often pause between records; a
        # query left open on the keep-table locks it, and the DROP at
        # session end then fails with "database table is locked".
        rows = []
        with real.dbapi.cursor() as cur:
            cur.execute(sql)
            batch = cur.fetchmany()
            while batch:
                rows.extend(batch)
                batch = cur.fetchmany()
        for row in rows:
            yield (row[0], real.serializer.string_to_data(row[1]))

    def _pb_iter_place_tree(self):
        real = self._pb_real
        keep = self._pb_keep["place"]
        if self._pb_strategy != STRATEGY_SQL:
            for handle, data in real._iter_raw_place_tree_data():
                if handle in keep:
                    yield (handle, data)
            return
        field = real.serializer.data_field
        sql = (
            f"SELECT t.handle, t.{field} FROM main.place AS t "
            "JOIN temp.pb_keep_place AS k ON k.handle = t.handle "
            "WHERE t.enclosed_by = ?"
        )
        to_do = [""]
        while to_do:
            parent = to_do.pop()
            with real.dbapi.cursor() as cur:
                cur.execute(sql, [parent])
                rows = []
                batch = cur.fetchmany()
                while batch:
                    rows.extend(batch)
                    batch = cur.fetchmany()
            for row in rows:
                to_do.append(row[0])
                yield (row[0], real.serializer.string_to_data(row[1]))
