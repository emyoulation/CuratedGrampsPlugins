# Based on Genealogy Capsule, Copyright (c) 2026 the Genealogy Capsule authors
# (mjlawless), MIT License:
# https://github.com/mjlawless/capsule-genealogy/blob/main/LICENSE
#
# Capsule Sources - read Genealogy Capsule capture folders
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
#
# GPL-2.0-or-later. The tolerant-reading approach follows
# capsule/collection/read.py from Genealogy Capsule, rewritten here with the
# Python standard library only, so the addon needs no extra modules.
#
# DRAFT MODE: working and readable first; not yet commit-ready.

"""Read Capsule capture folders (capture-folder/v1 and v2) into plain objects.

Nothing in this module imports Gramps or GTK, so it can be tested on its own.
Every read is tolerant: a missing or malformed file gives empty values and a
note in Capture.problems, never an exception (except a missing manifest, which
means the folder is not a capture at all).
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

CAPTURE_ID_SHAPE = re.compile(r"^\d{8}-[a-z0-9-]+-[0-9a-f]{8}$")

IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp", "tif", "tiff")

# Record categories, in the order and wording of the Capsule Captures Index
# (capsule/collection/record_types.py). First match wins.
UNCLASSIFIED = "Unclassified"
_CATEGORY_RULES = (
    ("Reference lists", r"coverage|holdings"),
    ("Church registers", r"church register|kirchenbuch"),
    ("Probate & wills", r"probate|\bwills?\b|letters of administration|administration records|testament"),
    ("Military", r"military|draft|pension|soldier|\bwar\b|regiment|enlist"),
    ("Immigration & naturalization", r"passenger|naturali[sz]|immigra|emigra|ship manifest|border crossing"),
    ("Census & household", r"census|household|husförhör|house interrogation|clerical survey"),
    ("Land & property", r"valuation|tithe|\bland\b|property|deed|estate map"),
    ("Marriage", r"marri|wedding|banns|trau"),
    ("Birth & baptism", r"baptis|birth|christening|taufe"),
    ("Death & burial", r"death|burial|obituar|grave|memorial|cemetery|funeral|beerdigung"),
    ("Directories & books", r"directory|book|almanac|yearbook"),
    ("Public records", r"social security|public records|voter|court"),
)
_CATEGORY_COMPILED = tuple((n, re.compile(p, re.IGNORECASE)) for n, p in _CATEGORY_RULES)
_EMPTY_TYPES = {"", "none", "unknown", "unclassified", "n/a"}


def record_category(record_type):
    """The common category for a free-text record type, or "Unclassified"."""
    text = (record_type or "").strip()
    if text.lower() in _EMPTY_TYPES:
        return UNCLASSIFIED
    for name, pattern in _CATEGORY_COMPILED:
        if pattern.search(text):
            return name
    return UNCLASSIFIED


def _ext_type(rel):
    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else "file"
    return "image" if ext in IMAGE_EXTS else ext


# Labels for media the Capsule tool rendered itself (manifest media[].provenance)
RENDERED_LABELS = {
    "render:page-pdf": "page PDF",
    "render:page-mhtml": "saved page",
}


@dataclass
class CaptureFile:
    """One archived file we may attach to Gramps as a Media object."""

    rel_path: str  # relative to the capture folder, forward slashes
    abs_path: Path
    mime: str | None
    sha256: str | None
    label: str  # "record image", "page PDF", "saved page", "document"
    source_url: str | None = None

    @property
    def exists(self):
        return self.abs_path.is_file()


@dataclass
class Capture:
    """Everything Phase 1 needs from one capture folder."""

    folder: Path
    capture_id: str
    source_id: str | None = None  # canonical UUIDv7 from the manifest
    spec_version: str | None = None
    url: str = ""
    title: str | None = None
    site_name: str | None = None
    record_type: str | None = None
    gating: str = "public"
    copyright_flag: bool = False
    captured_at: str | None = None
    is_document: bool = False
    extraction_pending: bool = False
    # citation.json
    reference_note: str | None = None
    short_note: str | None = None
    source_list_entry: str | None = None
    access_date: str | None = None
    archived_url: str | None = None
    # sidecars
    notes: list = field(default_factory=list)  # list of note text strings
    superseded: bool = False
    superseded_by: str | None = None
    ever_superseded: bool = False
    # extraction.json
    personas: list = field(default_factory=list)  # list of (label, role)
    assertion_count: int = 0
    external_refs: list = field(default_factory=list)  # identifier or URL text
    extraction_notes: str | None = None
    # result.json and transcript/
    verify_ok: bool | None = None
    verify_shortfall: list = field(default_factory=list)
    transcribed_at: str | None = None
    file_types: list = field(default_factory=list)  # "html", "pdf", "image" ...
    files: list = field(default_factory=list)  # list of CaptureFile
    problems: list = field(default_factory=list)

    @property
    def is_private(self):
        """Subscription (gated) or copyright-flagged captures stay private."""
        return self.gating == "gated" or self.copyright_flag

    @property
    def host(self):
        try:
            return urlparse(self.url).netloc or None
        except ValueError:
            return None

    @property
    def site_root_url(self):
        try:
            parts = urlparse(self.url)
        except ValueError:
            return None
        if parts.scheme and parts.netloc:
            return f"{parts.scheme}://{parts.netloc}/"
        return None

    @property
    def status(self):
        """Lifecycle status as the Captures Index shows it."""
        return "extracted" if self.assertion_count else "captured"

    @property
    def awaiting_reading(self):
        """Archived without a key and not read yet."""
        return self.extraction_pending and not self.superseded and not self.ever_superseded

    @property
    def category(self):
        return record_category(self.record_type)

    @property
    def primary_persona(self):
        return self.personas[0][0] if self.personas else None

    @property
    def external_ref_count(self):
        return len(self.external_refs)

    @property
    def reading(self):
        """The "Read or not" facet of the Captures Index."""
        if self.awaiting_reading:
            return "not read yet"
        if self.is_document:
            return "file, not read"
        return "read"

    @property
    def site_label(self):
        return self.site_name or self.host or "unknown"

    @property
    def search_blob(self):
        """Lowercased text the filter box matches, as in the Captures Index."""
        parts = [
            self.record_type,
            self.category,
            self.primary_persona,
            self.site_name,
            self.status,
            self.short_note,
            self.capture_id,
            self.url,
            self.title,
            *self.external_refs,
            *self.notes,
        ]
        return " ".join(p for p in parts if p).lower()

    @property
    def media_count(self):
        return sum(1 for f in self.files if f.rel_path.startswith("media/"))

    @property
    def display_title(self):
        return self.title or self.short_note or self.url or self.capture_id


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------
def _load_json(path, problems, want=dict):
    """Load a JSON file; return an empty value of type `want` on any trouble."""
    if not path.is_file():
        return want()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as err:
        problems.append(f"{path.name}: {err}")
        return want()
    if not isinstance(data, want):
        problems.append(f"{path.name}: unexpected JSON shape")
        return want()
    return data


def _str_or_none(value):
    return value if isinstance(value, str) and value.strip() else None


def default_captures_root():
    """Where Capsule keeps its captures on this computer.

    Mirrors capsule/config.py: CAPSULE_DATA_DIR wins, otherwise the
    platform's user data folder for "Capsule".
    """
    explicit = os.environ.get("CAPSULE_DATA_DIR")
    if explicit:
        return Path(explicit) / "captures"
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "Capsule"
    elif sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or str(home / "AppData" / "Local")
        base = Path(local) / "Capsule"
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or str(home / ".local" / "share")
        base = Path(xdg) / "Capsule"
    return base / "captures"


# ------------------------------------------------------------
# reading one capture
# ------------------------------------------------------------
def read_capture(folder):
    """Read one capture folder. Raises FileNotFoundError if not a capture."""
    folder = Path(folder)
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no manifest.json in {folder}")

    problems = []
    manifest = _load_json(manifest_path, problems)
    citation = _load_json(folder / "citation.json", problems)
    source = manifest.get("source") or {}
    archive = manifest.get("archive") or {}
    hashes = (manifest.get("hashes") or {}).get("files") or {}

    cap = Capture(
        folder=folder,
        # the directory name wins over the manifest claim, like Capsule does
        capture_id=folder.name,
        source_id=_str_or_none(source.get("id")),
        spec_version=_str_or_none(manifest.get("spec_version")),
        url=str(source.get("url") or ""),
        title=_str_or_none(source.get("title")),
        site_name=_str_or_none(source.get("site_name")),
        record_type=_str_or_none(source.get("record_type")),
        gating=str(source.get("gating_status") or "public"),
        copyright_flag=bool(source.get("copyright_flag", False)),
        captured_at=_str_or_none(archive.get("captured_at")),
        is_document=archive.get("kind") == "document",
        extraction_pending=manifest.get("extraction") == "pending",
        reference_note=_str_or_none(citation.get("reference_note")),
        short_note=_str_or_none(citation.get("short_note")),
        source_list_entry=_str_or_none(citation.get("source_list_entry")),
        access_date=_str_or_none(citation.get("access_date")),
        archived_url=_str_or_none(citation.get("archived_url")),
        problems=problems,
    )
    # --- extraction.json -------------------------------------------------
    extraction = _load_json(folder / "extraction.json", problems)
    for persona in extraction.get("personas") or []:
        if isinstance(persona, dict):
            label = str(persona.get("label") or "").strip() or "(unlabeled)"
            cap.personas.append((label, str(persona.get("role") or "")))
    cap.assertion_count = sum(
        1 for a in extraction.get("assertions") or [] if isinstance(a, dict)
    )
    for ref in extraction.get("external_refs") or []:
        if isinstance(ref, dict):
            text = " ".join(
                str(ref.get(k) or "") for k in ("authority", "identifier", "url", "label")
            ).strip()
            cap.external_refs.append(text)
    cap.extraction_notes = _str_or_none(extraction.get("notes"))

    # --- result.json (Capsule's own verdict) and transcripts --------------
    result = _load_json(folder / "result.json", problems)
    if isinstance(result.get("verify_ok"), bool):
        cap.verify_ok = result["verify_ok"]
    if isinstance(result.get("verify_shortfall"), list):
        cap.verify_shortfall = [str(x) for x in result["verify_shortfall"]]
    for tpath in (folder / "transcript").glob("*/transcript.json"):
        created = (_load_json(tpath, problems).get("transcription") or {}).get("created_at")
        if isinstance(created, str) and (cap.transcribed_at is None or created > cap.transcribed_at):
            cap.transcribed_at = created

    # --- file types, like the Files column of the Captures Index ----------
    primary = _str_or_none(archive.get("local_snapshot"))
    types = set()
    for rel in hashes:
        if ".." in rel.split("/"):
            continue
        if primary and rel == primary:
            types.add("html" if rel.endswith(".html") else _ext_type(rel))
        elif rel.startswith("media/"):
            types.add(_ext_type(rel))
        elif rel.endswith(".html"):
            types.add("html")
    cap.file_types = sorted(types)

    if manifest.get("capture_id") and manifest.get("capture_id") != folder.name:
        problems.append("manifest capture_id differs from folder name")

    # --- files to attach -------------------------------------------------
    if cap.is_document:
        rel = _str_or_none(archive.get("local_snapshot"))
        if rel:
            cap.files.append(
                CaptureFile(
                    rel_path=rel,
                    abs_path=folder / rel,
                    mime=_str_or_none(archive.get("media_type")),
                    sha256=_str_or_none(hashes.get(rel))
                    or _str_or_none(archive.get("sha256")),
                    label="document",
                )
            )
    listed = set()
    for entry in manifest.get("media") or []:
        if not isinstance(entry, dict):
            continue
        rel = _str_or_none(entry.get("path"))
        if not rel:
            continue
        listed.add(rel)
        provenance = str(entry.get("provenance") or "")
        cap.files.append(
            CaptureFile(
                rel_path=rel,
                abs_path=folder / rel,
                mime=_str_or_none(entry.get("mime")),
                sha256=_str_or_none(hashes.get(rel)),
                label=RENDERED_LABELS.get(provenance, "record image"),
                source_url=_str_or_none(entry.get("source_url")),
            )
        )
    # hashed media files without a media[] entry (older captures)
    for rel in sorted(hashes):
        if rel.startswith("media/") and rel not in listed:
            cap.files.append(
                CaptureFile(
                    rel_path=rel,
                    abs_path=folder / rel,
                    mime=None,
                    sha256=_str_or_none(hashes.get(rel)),
                    label="record image",
                )
            )
    for cfile in cap.files:
        if not cfile.exists:
            problems.append(f"missing file: {cfile.rel_path}")

    # --- notes.json (append-only; a revision is a new note) --------------
    for note in _load_json(folder / "notes.json", problems, want=list):
        if isinstance(note, dict) and _str_or_none(note.get("text")):
            stamp = _str_or_none(note.get("created_at"))
            text = note["text"].strip()
            cap.notes.append(f"{text}\n\n({stamp})" if stamp else text)

    # --- lifecycle.json: the latest event is the state -------------------
    events = _load_json(folder / "lifecycle.json", problems, want=list)
    latest = events[-1] if events and isinstance(events[-1], dict) else None
    cap.ever_superseded = any(
        isinstance(e, dict) and e.get("event") == "superseded" for e in events
    )
    if latest and latest.get("event") == "superseded":
        cap.superseded = True
        other = latest.get("superseded_by_capture_id")
        if isinstance(other, str) and CAPTURE_ID_SHAPE.match(other):
            cap.superseded_by = other

    return cap


def read_all(captures_root):
    """Read every capture under captures_root, newest first."""
    root = Path(captures_root)
    if not root.is_dir():
        return []
    captures = []
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        try:
            captures.append(read_capture(child))
        except FileNotFoundError:
            continue
    captures.sort(key=lambda c: (c.captured_at or "", c.capture_id), reverse=True)
    return captures
