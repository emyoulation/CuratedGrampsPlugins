# Based on Genealogy Capsule, Copyright (c) 2026 the Genealogy Capsule authors
# (mjlawless), MIT License:
# https://github.com/mjlawless/capsule-genealogy/blob/main/LICENSE
#
# Capsule Sources - write captures into a Gramps tree
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
#
# GPL-2.0-or-later.
#
# DRAFT MODE: working and readable first; not yet commit-ready.

"""Phase 1 importer: Repository, Source, Citation, Media and Notes only.

Structure (revision 2): the Genealogy Capsule captures archive is the
Repository, each web site is a Source held by that Repository, and each
capture (one memorial, one census page...) is a Citation of that Source,
dated with the day it was captured.

No people, events or facts are created here; that is Phase 2, behind a review
step, because Capsule never merges people without the researcher deciding.
This module uses gramps.gen only (no GTK), so it can run headless in tests.
"""

import re
from pathlib import Path

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.errors import HandleError
from gramps.gen.lib import (
    Attribute,
    Citation,
    Date,
    Media,
    MediaRef,
    Note,
    NoteType,
    RepoRef,
    Repository,
    RepositoryType,
    Source,
    SourceMediaType,
    SrcAttribute,
    Url,
    UrlType,
)
from gramps.gen.mime import get_type
from gramps.gen.utils.file import create_checksum

try:
    _ = glocale.get_addon_translator(__file__).gettext
except ValueError:
    _ = glocale.translation.gettext

# Custom attribute names. Not translated on purpose: they are lookup keys,
# and a tree shared between languages must still find its own captures.
ATTR_CAPTURE_ID = "Capsule capture id"
ATTR_SOURCE_ID = "Capsule source id"
ATTR_URL = "URL"
ATTR_ACCESSED = "Accessed"
ATTR_ARCHIVED_URL = "Archived URL"
ATTR_SHA256 = "SHA-256"
ATTR_CAPSULE_FILE = "Capsule file"
ATTR_SITE = "Capsule site"  # on a Source: which web site it stands for

# The one Repository: the Capsule captures archive. A proper name plus the
# folder name, so it is not translated (it is also the lookup key).
REPO_NAME = "Genealogy Capsule captures"
CAPSULE_HOME = "https://github.com/mjlawless/capsule-genealogy"
URL_TYPE_ARCHIVE = "Capsule archive folder"


def _attr_value(obj, name):
    for attr in obj.get_attribute_list():
        if str(attr.get_type()) == name:
            return attr.get_value()
    return None


def _src_attr(name, value):
    attr = SrcAttribute()
    attr.set_type(name)
    attr.set_value(value)
    return attr


def _attr(name, value):
    attr = Attribute()
    attr.set_type(name)
    attr.set_value(value)
    return attr


# ------------------------------------------------------------
# lookups into the existing tree
# ------------------------------------------------------------
def imported_capture_ids(db):
    """Map capture_id -> citation handle for captures already in the tree."""
    found = {}
    for citation in db.iter_citations():
        cap_id = _attr_value(citation, ATTR_CAPTURE_ID)
        if cap_id:
            found[cap_id] = citation.get_handle()
    return found


class TreeIndex:
    """Name/path lookups built once per import run, kept current as we add."""

    def __init__(self, db):
        self.repos = {r.get_name(): r.get_handle() for r in db.iter_repositories()}
        # Sources are found by their "Capsule site" attribute, not their title,
        # so the user may retitle them ("Find a Grave") and never collide
        # with a Source of their own that happens to share the name.
        self.sources = {}
        for source in db.iter_sources():
            site = _attr_value(source, ATTR_SITE)
            if site:
                self.sources[site] = source.get_handle()
        self.media = {m.get_path(): m.get_handle() for m in db.iter_media()}
        self.captures = imported_capture_ids(db)


# ------------------------------------------------------------
# the import
# ------------------------------------------------------------
class ImportResult:
    def __init__(self):
        self.repositories = 0
        self.sources = 0
        self.citations = 0
        self.media = 0
        self.notes = 0
        self.skipped = []  # capture ids already in the tree
        self.problems = []  # (capture_id, text)

    def summary(self):
        return _(
            "Added {cit} citations, {src} sources, {repo} repositories, "
            "{med} media objects and {note} notes."
        ).format(
            cit=self.citations,
            src=self.sources,
            repo=self.repositories,
            med=self.media,
            note=self.notes,
        )


def import_captures(db, captures, root="", links=None):
    """Add each capture to the tree in one transaction. Returns ImportResult.

    root is the captures folder (recorded on the Repository); links maps
    capture_id -> the handle of the primary Person linked in the tool, who
    then cites the new Citation.
    """
    links = links or {}
    result = ImportResult()
    index = TreeIndex(db)
    with DbTxn(_("Import Capsule captures"), db) as trans:
        for cap in captures:
            if cap.capture_id in index.captures:
                result.skipped.append(cap.capture_id)
                continue
            for text in cap.problems:
                result.problems.append((cap.capture_id, text))
            _import_one(db, trans, index, cap, result, root, links.get(cap.capture_id))
    return result


def _capture_date(cap):
    """The day of the capture (UTC, as Capsule writes it) as a Gramps Date."""
    for text in (cap.captured_at, cap.access_date):
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text or "")
        if match:
            date = Date()
            date.set_yr_mon_day(*(int(part) for part in match.groups()))
            return date
    return None


def _archive_repository(db, trans, index, root, result):
    """The Repository standing for the Capsule captures archive."""
    handle = index.repos.get(REPO_NAME)
    if handle is not None:
        return handle
    repo = Repository()
    repo.set_name(REPO_NAME)
    repo.set_type(RepositoryType.COLLECTION)
    home = Url()
    home.set_path(CAPSULE_HOME)
    home.set_type(UrlType.WEB_HOME)
    home.set_description("Genealogy Capsule")
    repo.add_url(home)
    if root:
        folder = Url()
        folder.set_path(Path(root).as_uri())
        folder.set_type((UrlType.CUSTOM, URL_TYPE_ARCHIVE))
        repo.add_url(folder)
    handle = db.add_repository(repo, trans)
    index.repos[REPO_NAME] = handle
    result.repositories += 1
    return handle


def _site_source(db, trans, index, cap, repo_handle, result):
    """The Source standing for the web site the capture came from."""
    site = cap.site_label
    handle = index.sources.get(site)
    if handle is not None:
        return handle
    source = Source()
    source.set_title(site)
    if cap.site_root_url:
        source.set_publication_info(cap.site_root_url)
    source.add_attribute(_src_attr(ATTR_SITE, site))
    reporef = RepoRef()
    reporef.set_reference_handle(repo_handle)
    reporef.set_media_type(SourceMediaType.ELECTRONIC)
    source.add_repo_reference(reporef)
    handle = db.add_source(source, trans)
    index.sources[site] = handle
    result.sources += 1
    return handle


def _import_one(db, trans, index, cap, result, root, person_handle):
    private = cap.is_private

    # --- Repository: the Capsule archive; Source: the web site -----------
    repo_handle = _archive_repository(db, trans, index, root, result)
    src_handle = _site_source(db, trans, index, cap, repo_handle, result)

    # --- Citation: one per capture ----------------------------------------
    citation = Citation()
    citation.set_reference_handle(src_handle)
    citation.set_page(cap.display_title)
    date = _capture_date(cap)
    if date is not None:
        citation.set_date_object(date)
    citation.set_privacy(private)
    citation.add_attribute(_src_attr(ATTR_CAPTURE_ID, cap.capture_id))
    if cap.source_id:
        citation.add_attribute(_src_attr(ATTR_SOURCE_ID, cap.source_id))
    if cap.url:
        citation.add_attribute(_src_attr(ATTR_URL, cap.url))
    if cap.access_date:
        citation.add_attribute(_src_attr(ATTR_ACCESSED, cap.access_date))
    if cap.archived_url and cap.archived_url != cap.url:
        citation.add_attribute(_src_attr(ATTR_ARCHIVED_URL, cap.archived_url))

    # the layered Evidence Explained citation, kept whole in one note
    lines = []
    if cap.reference_note:
        lines.append(_("Reference note:") + "\n" + cap.reference_note)
    if cap.short_note:
        lines.append(_("Short note:") + "\n" + cap.short_note)
    if cap.source_list_entry:
        lines.append(_("Source list entry:") + "\n" + cap.source_list_entry)
    if lines:
        citation.add_note(
            _add_note(db, trans, "\n\n".join(lines), NoteType.CITATION, private)
        )
        result.notes += 1

    # the researcher's own notes from notes.json
    for text in cap.notes:
        citation.add_note(_add_note(db, trans, text, NoteType.RESEARCH, private))
        result.notes += 1

    # --- Media: linked in place, never copied out of the Capsule archive --
    for cfile in cap.files:
        if not cfile.exists:
            continue
        path = str(cfile.abs_path)
        media_handle = index.media.get(path)
        if media_handle is None:
            media = Media()
            media.set_path(path)
            media.set_mime_type(cfile.mime or get_type(path))
            media.set_description(f"{cap.display_title} ({_(cfile.label)})")
            media.set_checksum(create_checksum(path))
            media.set_privacy(private)
            media.add_attribute(_attr(ATTR_CAPSULE_FILE, cfile.rel_path))
            if cfile.sha256:
                media.add_attribute(_attr(ATTR_SHA256, cfile.sha256))
            if cfile.source_url:
                media.add_attribute(_attr(ATTR_URL, cfile.source_url))
            media_handle = db.add_media(media, trans)
            index.media[path] = media_handle
            result.media += 1
        mref = MediaRef()
        mref.set_reference_handle(media_handle)
        citation.add_media_reference(mref)

    db.add_citation(citation, trans)
    index.captures[cap.capture_id] = citation.get_handle()
    result.citations += 1
    if person_handle:
        _cite(db, trans, person_handle, citation.get_handle())


def get_person(db, handle):
    """The Person for handle, or None when it is gone from this tree."""
    if not handle:
        return None
    try:
        return db.get_person_from_handle(handle)
    except HandleError:
        return None


def _cite(db, trans, person_handle, citation_handle):
    person = get_person(db, person_handle)
    # the Person's own citation list only, not those on its names, events...
    if person is not None and citation_handle not in person.get_citation_list():
        person.add_citation(citation_handle)
        db.commit_person(person, trans)


def cite_person(db, person_handle, citation_handle):
    """The linked primary Person cites the capture's Citation (shown on
    the Source Citations tab of the Person editor)."""
    with DbTxn(_("Link Capsule capture to a person"), db) as trans:
        _cite(db, trans, person_handle, citation_handle)


def uncite_person(db, person_handle, citation_handle):
    """Undo cite_person(): the Person no longer cites the Citation."""
    person = get_person(db, person_handle)
    if person is None or citation_handle not in person.get_citation_list():
        return
    # own list only: a citation the user put on a Name or Event stays
    person.set_citation_list(
        [h for h in person.get_citation_list() if h != citation_handle]
    )
    with DbTxn(_("Unlink Capsule capture from a person"), db) as trans:
        db.commit_person(person, trans)


def _add_note(db, trans, text, note_type, private):
    note = Note(text)
    note.set_type(note_type)
    note.set_privacy(private)
    return db.add_note(note, trans)
