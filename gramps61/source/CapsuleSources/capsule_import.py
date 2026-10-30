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

No people, events or facts are created here; that is Phase 2, behind a review
step, because Capsule never merges people without the researcher deciding.
This module uses gramps.gen only (no GTK), so it can run headless in tests.
"""

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.lib import (
    Attribute,
    Citation,
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
        self.sources = {s.get_title(): s.get_handle() for s in db.iter_sources()}
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


def import_captures(db, captures):
    """Add each capture to the tree in one transaction. Returns ImportResult."""
    result = ImportResult()
    index = TreeIndex(db)
    with DbTxn(_("Import Capsule captures"), db) as trans:
        for cap in captures:
            if cap.capture_id in index.captures:
                result.skipped.append(cap.capture_id)
                continue
            for text in cap.problems:
                result.problems.append((cap.capture_id, text))
            _import_one(db, trans, index, cap, result)
    return result


def _import_one(db, trans, index, cap, result):
    private = cap.is_private

    # --- Repository: one per site ----------------------------------------
    repo_name = cap.site_name or cap.host or _("Unknown web site")
    repo_handle = index.repos.get(repo_name)
    if repo_handle is None:
        repo = Repository()
        repo.set_name(repo_name)
        repo.set_type(RepositoryType.WEBSITE)
        if cap.site_root_url:
            url = Url()
            url.set_path(cap.site_root_url)
            url.set_type(UrlType.WEB_HOME)
            repo.add_url(url)
        repo_handle = db.add_repository(repo, trans)
        index.repos[repo_name] = repo_handle
        result.repositories += 1

    # --- Source: keyed on the Evidence Explained source-list entry --------
    src_title = cap.source_list_entry or cap.title or cap.url or cap.capture_id
    src_handle = index.sources.get(src_title)
    if src_handle is None:
        source = Source()
        source.set_title(src_title)
        if cap.site_name:
            source.set_abbreviation(cap.site_name)
        reporef = RepoRef()
        reporef.set_reference_handle(repo_handle)
        reporef.set_media_type(SourceMediaType.ELECTRONIC)
        source.add_repo_reference(reporef)
        src_handle = db.add_source(source, trans)
        index.sources[src_title] = src_handle
        result.sources += 1

    # --- Citation: one per capture ----------------------------------------
    citation = Citation()
    citation.set_reference_handle(src_handle)
    citation.set_page(cap.reference_note or cap.display_title)
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


def _add_note(db, trans, text, note_type, private):
    note = Note(text)
    note.set_type(note_type)
    note.set_privacy(private)
    return db.add_note(note, trans)
