#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2026       Claude Sonnet 5
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""
Standalone phonetic surname index, factored out of
``FuzzyMatchingGramplet.py`` so both it and something that isn't that
gramplet's own GTK widgets - currently :mod:`FuzzyMatchLookupWindow`,
and, via that module's ``show_fuzzy_lookup`` function, any other addon
that wants a quick "does someone like this already exist" check (see
that module's docstring for the intended calling convention from
another plugin, e.g. a Photo Tagging-style gramplet that has just
parsed a Surname out of image metadata) - share one implementation
instead of two.

Deliberately has no ``gi.repository``/GTK import of any kind, so it is
safe to import and use from a non-GUI context too (a CLI tool, a
headless import filter) - only :class:`~gramps.gen.db.base.DbReadBase`
and the plain-Python :mod:`phonetic_codes` module are required.

Note on imports: like ``FuzzyMatchingGramplet.py``, this is imported
by bare module name (``import fuzzy_match_index``), not as a package,
since Gramps puts every registered addon's own folder on ``sys.path``
- see the equivalent, longer comment in ``FuzzyMatchingGramplet.py``.
"""

# ------------------------
# Python modules
# ------------------------
import logging
import time
from typing import Dict, List, Optional, Set

# ------------------------
# Gramps specific
# ------------------------
from phonetic_codes import ALGORITHMS, DEFAULT_ALGORITHM

LOG = logging.getLogger(__name__)

#: How long (seconds) :meth:`FuzzyMatchIndex.build` processes before
#: yielding, for a caller driving it in the background (e.g. via
#: ``GLib.idle_add``) the same way ``FuzzyMatchingGramplet.py`` drives
#: its own equivalent stages. A caller that wants a single blocking
#: call instead can just use :meth:`FuzzyMatchIndex.build_sync`.
INDEX_CHUNK_SECONDS = 0.05

#: How many items :meth:`FuzzyMatchIndex.build` processes between
#: progress reports/yields, primarily - :data:`INDEX_CHUNK_SECONDS` is
#: kept as a secondary safety net (yield sooner if that much time
#: passes without reaching this count) rather than removed, in case a
#: future phase ever processes items far more expensively than today's
#: two do. On a large tree (tens of thousands of people), a strictly
#: time-based interval reports progress far more often than a person
#: actually benefits from watching, and each report has a real cost
#: (a GTK label/spinner update on the caller's side) - reporting every
#: 1,000 items instead bounds that to a fixed, small number of updates
#: regardless of tree size (60 for a 60,000-person tree) rather than
#: however many fit in 0.05 seconds each, without needing per-tree
#: tuning to keep that number reasonable.
INDEX_PROGRESS_INTERVAL = 1000


def person_surnames(person) -> Set[str]:
    """
    Return every distinct surname *piece* on ``person``'s primary
    name, as Gramps' own ``HasSoundexName`` filter rule and
    ``DbReadBase.get_surname_list()`` both work with - not
    ``Name.get_surname()``'s single, fully-formatted (and, for anyone
    with more than one :class:`~gramps.gen.lib.Surname` on their name,
    connector-joined) string.

    This distinction matters more than it looks: a person entered with
    two surnames - a double/compound surname such as "Thompson
    McCullough", stored as two separate ``Surname`` entries on one
    ``Name`` - has ``Name.get_surname_list()`` returning both
    ``Surname`` objects, but ``Name.get_surname()`` returns the one
    joined string ``"Thompson McCullough"``. That joined string is
    never one of the entries ``DbReadBase.get_surname_list()`` returns
    (which tracks each ``Surname`` piece individually, the same
    granularity this function uses), so indexing by
    ``Name.get_surname()`` instead of this function silently drops
    that person from every phonetic match - including a search for
    either surname piece on its own, and including this gramplet's own
    "select the active person's row" behavior, which looks for exactly
    this same per-piece surname among the currently-displayed matches.
    It also undercounts relative to Gramps' built-in ``HasSoundexName``
    rule (used by the "Define filter" action - see
    ``FuzzyMatchingGramplet.cb_surname_activated``), which checks each
    ``Surname`` piece independently for exactly this reason.

    A non-compound name (the overwhelmingly common case - one
    ``Surname`` entry) returns a one-element set equal to what
    ``Name.get_surname()`` would already have given, so this is a
    strict improvement, not a behavior change, for anyone without a
    multi-part surname.

    :param person: The :class:`gramps.gen.lib.Person` to read.
    :returns: The distinct, non-empty surname piece(s) on their
        primary name - usually one, more than one only for a
        multi-part/compound surname. Empty if their primary name has
        no surname at all.
    """
    return {
        surname.get_surname()
        for surname in person.get_primary_name().get_surname_list()
        if surname.get_surname()
    }


# ------------------------------------------------------------
#
# FuzzyMatchIndex
#
# ------------------------------------------------------------
class FuzzyMatchIndex:
    """
    A cached, per-database phonetic surname index: which surnames
    phonetically match a given name, and which people carry each
    surname - the same two lookups ``FuzzyMatchingGramplet.py`` keeps
    for its own Matches columns, available here without any GTK
    involved.

    :attr:`ready` is False until :meth:`build` (or
    :meth:`build_sync`) has completed at least once; every ``find_*``
    method simply returns nothing until then rather than raising, so a
    caller mid-build degrades to "no matches yet" instead of an
    exception.
    """

    def __init__(self, db, algorithm_id: Optional[str] = None) -> None:
        """
        :param db: The :class:`~gramps.gen.db.base.DbReadBase` to
            index. Must already be open.
        :param algorithm_id: One of :data:`phonetic_codes.ALGORITHMS`'s
            keys, or None for :data:`phonetic_codes.DEFAULT_ALGORITHM`.
        """
        self.db = db
        # Optional only on input (the constructor's own parameter, which
        # accepts None as shorthand for "use the default") - once stored,
        # this is always a real algorithm id, never None, which is what
        # lets ALGORITHMS[self.algorithm_id] be indexed directly
        # everywhere below without a None-check at every call site.
        # phonetic_codes.DEFAULT_ALGORITHM is itself typed Optional[str]
        # (it could theoretically be None if no algorithm registered at
        # all), so the fallback below is asserted, not just assumed -
        # see phonetic_codes._hardcoded_soundex, which exists
        # specifically so at least one algorithm is always available.
        if algorithm_id is not None:
            self.algorithm_id: str = algorithm_id
        else:
            assert DEFAULT_ALGORITHM is not None, (
                "phonetic_codes registered no algorithms at all - see "
                "phonetic_codes._hardcoded_soundex"
            )
            self.algorithm_id = DEFAULT_ALGORITHM
        self.surname_index: Dict[str, List[str]] = {}
        self.surname_to_handles: Dict[str, List[str]] = {}
        # Handle -> the *set* of individual surname pieces (see
        # person_surnames) they're currently filed under - a set, not
        # a single string, because a compound/double surname files one
        # person under more than one piece. Exists purely so a single
        # person-add/-update/-delete signal can patch
        # surname_to_handles/surname_index in O(1)-ish time - removing
        # a handle from whichever piece(s) it used to be filed under,
        # or deciding whether a piece is brand new to the tree -
        # instead of falling back to a full build() rebuild for every
        # single edit. See on_person_changed/on_person_deleted/
        # _remove_handle_from_surname.
        self.handle_to_surname: Dict[str, Set[str]] = {}
        self.known_surnames: Set[str] = set()
        self.ready = False

    def build(self, chunk_seconds: float = INDEX_CHUNK_SECONDS, progress_callback=None):
        """
        (Re)build the index from scratch, yielding periodically so a
        caller can drive this on GTK's idle loop (``GLib.idle_add``)
        instead of freezing the UI for the whole build - the same
        pattern ``FuzzyMatchingGramplet.main`` uses for its own two
        stages. A caller that doesn't care about that (a script, or a
        "just block, this is a one-off check" UI) can use
        :meth:`build_sync` instead.

        :param chunk_seconds: Safety-net seconds of work between each
            ``yield`` if :data:`INDEX_PROGRESS_INTERVAL` items haven't
            already been reached first - see that constant for why
            item count, not elapsed time, is the primary trigger.
        :param progress_callback: Optional ``callback(phase, position,
            total)``, called once at the start of each phase
            (``position=0``) and again just before every subsequent
            yield, so a caller can drive its own progress display
            (a spinner and running count, say) without needing to
            know anything about how the two phases are chunked -
            that stays entirely in this method. ``phase`` is the
            plain, untranslated string ``"surnames"`` or ``"people"``;
            translating it for display is the caller's job.
        :returns: A generator; ``yield True`` between chunks, nothing
            after the final one (implicit ``StopIteration``).
        """
        self.ready = False
        encode = ALGORITHMS[self.algorithm_id]

        surnames = self.db.get_surname_list()
        known = set(surnames)
        total = len(surnames)
        if progress_callback:
            progress_callback("surnames", 0, total)
        code_index: Dict[str, List[str]] = {}
        deadline = time.perf_counter() + chunk_seconds
        for position, surname in enumerate(surnames, start=1):
            for code in encode(surname):
                code_index.setdefault(code, []).append(surname)
            if position % INDEX_PROGRESS_INTERVAL == 0 or time.perf_counter() >= deadline:
                if progress_callback:
                    progress_callback("surnames", position, total)
                yield True
                deadline = time.perf_counter() + chunk_seconds

        person_handles = self.db.get_person_handles(sort_handles=False)
        total = len(person_handles)
        if progress_callback:
            progress_callback("people", 0, total)
        handle_index: Dict[str, List[str]] = {}
        reverse_index: Dict[str, Set[str]] = {}
        deadline = time.perf_counter() + chunk_seconds
        for position, handle in enumerate(person_handles, start=1):
            person = self.db.get_person_from_handle(handle)
            if person is not None:
                pieces = person_surnames(person)
                for piece in pieces:
                    handle_index.setdefault(piece, []).append(handle)
                    # db.get_surname_list() is trusted above as the
                    # source of every surname worth computing a code
                    # for, since it is already a ready-made, per-tree
                    # unique list - but nothing here actually
                    # guarantees it enumerates a *non-primary* piece of
                    # a compound/double surname the same way
                    # person_surnames() does (see that function's
                    # docstring). Rather than assume one way or the
                    # other, any piece this stage finds that Stage 1
                    # did not already cover gets its own code added
                    # right here - the same "brand new surname" step
                    # on_person_changed does for an incremental edit,
                    # just applied once, up front, for a full build too.
                    if piece not in known:
                        for code in encode(piece):
                            code_index.setdefault(code, []).append(piece)
                        known.add(piece)
                reverse_index[handle] = pieces
            if position % INDEX_PROGRESS_INTERVAL == 0 or time.perf_counter() >= deadline:
                if progress_callback:
                    progress_callback("people", position, total)
                yield True
                deadline = time.perf_counter() + chunk_seconds

        self.surname_index = code_index
        self.known_surnames = known
        self.surname_to_handles = handle_index
        self.handle_to_surname = reverse_index
        self.ready = True
        LOG.debug(
            "FuzzyMatchIndex: indexed %d unique surnames into %d codes and "
            "%d people using %s",
            len(known),
            len(code_index),
            len(reverse_index),
            self.algorithm_id,
        )

    def build_sync(self, chunk_seconds: float = INDEX_CHUNK_SECONDS) -> None:
        """
        Run :meth:`build` straight through to completion, for a caller
        that would rather block briefly than manage a background
        generator - reasonable for an occasional, on-demand lookup
        against a Family Tree of ordinary size.

        :param chunk_seconds: Unused for timing here (there is no idle
            loop to yield back to), but still passed through so the
            exact same generator code path runs either way.
        """
        for _ in self.build(chunk_seconds):
            pass

    def find_surnames(self, name: str) -> List[str]:
        """
        Return every surname in the tree that phonetically matches
        ``name`` under the current algorithm, unsorted.

        :param name: The surname to match against.
        :returns: Matching surnames, or ``[]`` before the first
            :meth:`build` completes.
        """
        if not self.ready:
            return []
        encode = ALGORITHMS[self.algorithm_id]
        matches: Set[str] = set()
        for code in encode(name):
            matches.update(self.surname_index.get(code, []))
        return list(matches)

    def find_surnames_for_code(self, code: str) -> List[str]:
        """
        Return every surname filed directly under phonetic ``code`` -
        the per-code counterpart to :meth:`find_surnames`, which
        merges every code a name might encode to into one flat list.
        Used by a caller (the gramplet's "All <code>" grouping) that
        wants to keep each code's surnames separate rather than
        merged together.

        :param code: One phonetic code, typically a value yielded by
            encoding a name under the current algorithm.
        :returns: Surnames filed under this code, or ``[]`` if none
            (or before the first :meth:`build` completes).
        """
        if not self.ready:
            return []
        return list(self.surname_index.get(code, []))

    def find_people(self, surname: str) -> List[str]:
        """
        Return the handles of every person carrying ``surname`` as one
        of their primary name's surname pieces (see
        :func:`person_surnames`) - not necessarily their only surname,
        for someone with a compound/double surname.

        :param surname: The exact surname piece to look up (typically
            one returned by :meth:`find_surnames`, not the originally
            typed/queried name).
        :returns: Person handles, or ``[]`` if none (or before the
            first :meth:`build` completes).
        """
        return list(self.surname_to_handles.get(surname, []))

    def find_matches(self, name: str) -> Dict[str, List[str]]:
        """
        Convenience combining :meth:`find_surnames` and
        :meth:`find_people`: every surname phonetically matching
        ``name``, each with its own list of person handles.

        :param name: The surname to match against.
        :returns: ``{surname: [handle, ...]}`` for every matching
            surname, or ``{}`` before the first :meth:`build`
            completes.
        """
        return {
            surname: self.find_people(surname) for surname in self.find_surnames(name)
        }

    def on_person_changed(self, handles: List[str]) -> Set[str]:
        """
        Patch the index in place for one or more added or edited
        people, without a full :meth:`build` rebuild - see
        ``FuzzyMatchingGramplet.cb_person_changed``, which this
        mirrors. Connect this to the database's own
        ``person-add``/``person-update`` signals.

        A no-op before the first :meth:`build` completes.

        :param handles: Handles of the people that were added or
            updated, as passed by the database's signal.
        :returns: The surnames added to, changed in, or removed from
            the index by this call - empty if nothing was touched (or
            the index isn't ready yet). A GUI caller can use this to
            decide what, if anything, needs refreshing on screen
            without re-deriving it itself.
        """
        touched: Set[str] = set()
        if not self.ready:
            return touched

        encode = ALGORITHMS[self.algorithm_id]
        for handle in handles:
            try:
                person = self.db.get_person_from_handle(handle)
            except Exception:  # pylint: disable=broad-except
                # HandleError from gramps.gen.errors, imported lazily
                # by callers that need to catch it specifically - see
                # the module docstring for why this file avoids all
                # but the plainest Gramps imports.
                continue

            new_pieces = person_surnames(person)
            old_pieces = self.handle_to_surname.get(handle, set())

            for piece in old_pieces - new_pieces:
                self._remove_handle_from_surname(handle, piece)
                touched.add(piece)

            for piece in new_pieces:
                bucket = self.surname_to_handles.setdefault(piece, [])
                if handle not in bucket:
                    bucket.append(handle)

                if piece not in self.known_surnames:
                    for code in encode(piece):
                        self.surname_index.setdefault(code, [])
                        if piece not in self.surname_index[code]:
                            self.surname_index[code].append(piece)
                    self.known_surnames.add(piece)

                touched.add(piece)

            self.handle_to_surname[handle] = new_pieces

        return touched

    def on_person_deleted(self, handles: List[str]) -> Set[str]:
        """
        Patch the index in place for one or more deleted people,
        without a full :meth:`build` rebuild - see
        ``FuzzyMatchingGramplet.cb_person_deleted``, which this
        mirrors. Connect this to the database's own ``person-delete``
        signal.

        A no-op before the first :meth:`build` completes.

        :param handles: Handles of the people that were deleted, as
            passed by the database's signal.
        :returns: The surnames touched by this call - see
            :meth:`on_person_changed`'s return value, which this
            mirrors.
        """
        touched: Set[str] = set()
        if not self.ready:
            return touched
        for handle in handles:
            pieces = self.handle_to_surname.pop(handle, None)
            if not pieces:
                continue
            for piece in pieces:
                self._remove_handle_from_surname(handle, piece)
            touched.update(pieces)
        return touched

    def on_rebuild(self) -> None:
        """
        Mark the index stale in response to the database's own
        ``person-rebuild`` signal (fired after batch operations - an
        import, or a Tool that runs in one transaction - instead of
        individual add/update/delete signals). There is no per-handle
        list to patch with here, so this just clears :attr:`ready`;
        the caller is responsible for noticing and calling
        :meth:`build`/:meth:`build_sync` again before the next lookup.
        """
        self.ready = False

    def _remove_handle_from_surname(self, handle: str, surname: str) -> None:
        """
        Remove ``handle`` from ``surname``'s bucket, and if that
        empties the bucket, drop the surname from the index entirely
        so an emptied-out surname stops appearing in a caller's
        Matches display instead of lingering there with a
        permanently-zero count.

        :param handle: The person handle to remove.
        :param surname: The surname bucket to remove it from.
        """
        bucket = self.surname_to_handles.get(surname)
        if not bucket:
            return
        if handle in bucket:
            bucket.remove(handle)
        if bucket:
            return

        del self.surname_to_handles[surname]
        self.known_surnames.discard(surname)
        for code, surnames in list(self.surname_index.items()):
            if surname in surnames:
                surnames.remove(surname)
                if not surnames:
                    del self.surname_index[code]
