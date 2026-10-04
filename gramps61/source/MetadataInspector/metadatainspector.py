#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2009-2011 Rob G. Healey <robhealey1@gmail.com>
#               2019      Paul Culley <paulr2787@gmail.com>
#               2026      Claude AI (wish coding by Brian McCullough)
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
Metadata Inspector, a read-only gramplet that shows the metadata of the active
Media object, with one notebook tab for each place where the metadata lives:

* File: the file information, how the image was made, and the Exif, IPTC and
  XMP tags, PDF information and audio/video tags embedded in the file.
* Sidecar: the XMP sidecar of the file, if there is one.
* Current Tree: the media record, everything that references it (with the
  region of the image that each reference selects), and its Attributes,
  Notes, Tags and Citations.

Where the sources disagree, the Current Tree outranks the sidecar, which
outranks the file (for the pixel size, the file wins).  The value in use is
shown in bold with ``*``; the values it overrides are red with a dagger.

Metadata Inspector is a fork of the Edit Image Exif Metadata gramplet by Rob G.
Healey, generalized to cover the most common kinds of metadata.  Every reader
is optional: GExiv2 for images and sidecars, pypdf for PDF files and mutagen
for audio and video files.
"""

# Deferred evaluation of annotations (PEP 563).  The handle types come from
# gramps.gen.types, which does not exist in Gramps 5.2, so they are imported
# only for type checking.  It also allows the Python 3.10 annotation syntax on
# older Python versions.
from __future__ import annotations

# -------------------------------------------------------------------------
#
# Standard Python modules
#
# -------------------------------------------------------------------------
import datetime
import hashlib
import importlib
import logging
import os
import re
import zlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

# -------------------------------------------------------------------------
#
# GTK/Gnome modules
#
# -------------------------------------------------------------------------
import gi
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk

try:
    # Use whichever GExiv2 typelib is installed (0.10, 0.12, 0.14, 0.16, ...)
    # rather than insisting on 0.10, which newer systems no longer ship.
    _GEXIV2_VERSIONS = gi.Repository.get_default().enumerate_versions("GExiv2")
    if not _GEXIV2_VERSIONS:
        raise ValueError("GExiv2 is not installed")
    gi.require_version("GExiv2", _GEXIV2_VERSIONS[-1])
    from gi.repository import GExiv2
except (ImportError, ValueError):
    GExiv2 = None

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import displayer as _dd
from gramps.gen.db.exceptions import DbException
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.display.place import displayer as place_displayer
from gramps.gen.errors import DateError, HandleError, WindowActiveError
from gramps.gen.lib import Date
from gramps.gen.mime import get_description
from gramps.gen.plug import Gramplet
from gramps.gen.utils.db import family_name
from gramps.gen.utils.file import media_path_full
from gramps.gen.utils.place import conv_lat_lon
from gramps.gui.managedwindow import ManagedWindow

if TYPE_CHECKING:
    from gramps.gen.db.base import DbReadBase
    from gramps.gen.lib import Media
    from gramps.gen.types import MediaHandle
    from gramps.gui.displaystate import DisplayState

    Key = tuple[Any, ...]
    Mark = tuple[str, str, str, str]

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext
# Strings that already exist in the catalog of Gramps (the context menu of the
# Grouped People view, ...) are looked up with the translator of Gramps itself,
# so that they pick up its translations.
_gramps_gettext = glocale.translation.gettext

LOG = logging.getLogger(__name__)


# -------------------------------------------------------------------------
#
# Optional readers: each one works without the others
#
# -------------------------------------------------------------------------
def _optional_module(*names: str) -> Any:
    """
    Return the first of the named modules that can be imported, or None.
    """
    for name in names:
        try:
            return importlib.import_module(name)
        except ImportError:
            LOG.debug("Optional module %s is not available", name)
    return None


def _error_classes(module: Any, *names: str) -> tuple[type[Exception], ...]:
    """
    Return the exception classes of *module* with the given dotted names.
    """
    classes = []
    for dotted in names:
        found = module
        for part in dotted.split("."):
            found = getattr(found, part, None)
        if isinstance(found, type) and issubclass(found, Exception):
            classes.append(found)
    return tuple(classes)


_PDF_LIBRARY = _optional_module("pypdf", "PyPDF2")
PdfReader: Any = getattr(_PDF_LIBRARY, "PdfReader", None)
mutagen: Any = _optional_module("mutagen")

# What the readers and the database raise for a damaged, unsupported or
# missing thing; anything else is a programming error and is not caught.
_DB_ERRORS = (HandleError, DbException, AttributeError, KeyError, TypeError, ValueError)
_PDF_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    RuntimeError,
    NotImplementedError,
    zlib.error,
) + _error_classes(_PDF_LIBRARY, "errors.PyPdfError")
_AV_ERRORS = (
    OSError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
) + _error_classes(mutagen, "MutagenError")
_GEXIV2_ERRORS = (TypeError, AttributeError, OSError, ValueError)

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
# (section id, display name) in display order (within a tab)
_SECTIONS = (
    ("gramps", _("Gramps media record")),
    ("refs", _("Gramps references")),
    ("attrs", _gramps_gettext("Attributes")),
    ("notes", _gramps_gettext("Notes")),
    ("tags", _gramps_gettext("Tags")),
    ("cites", _gramps_gettext("Citations")),
    ("fileinfo", _("File information")),
    ("capture", _("Technical & Capture")),
    ("exif", "Exif"),
    ("iptc", "IPTC"),
    ("xmp", "XMP"),
    ("pdf", _("PDF document")),
    ("av", _("Audio/Video tags")),
    ("sidecar_file", _("Sidecar file")),
    ("xmp_sidecar", _("XMP - sidecar")),
)

# Notebook tabs: id, title, icon, sections shown.  Same convention as Gramps'
# own tabs: the icon is shown and the title is bold only while the tab has data.
# File and Sidecar share the theme's list icon; the Current Tree tab (what the
# database holds about the media object) uses Gramps' own "view media" icon.
_ICON_LIST = "view-list-bullet-symbolic"
_TABS = (
    (
        "file",
        _("File"),
        _ICON_LIST,
        ("fileinfo", "capture", "exif", "iptc", "xmp", "pdf", "av"),
    ),
    ("sidecar", _("Sidecar"), _ICON_LIST, ("sidecar_file", "xmp_sidecar")),
    (
        "gramps",
        _("Current Tree"),
        "gramps-viewmedia",
        ("gramps", "refs", "attrs", "notes", "tags", "cites"),
    ),
)
_TAB_SECTIONS = {tab_id: sections for tab_id, _title, _icon, sections in _TABS}

# sections that hold real metadata (embedded in the file, or in its XMP
# sidecar); they drive the "has data" highlight of the gramplet's own tab
_EMBEDDED = ("capture", "exif", "iptc", "xmp", "xmp_sidecar", "pdf", "av")
# what makes the Current Tree tab "have data" (besides a date or a real Title)
_GRAMPS_DATA = ("refs", "attrs", "notes", "tags", "cites")

# Where a value can come from, and who wins when they disagree
# (first in the tuple wins).
_SOURCE_NAMES = {
    "gramps": _("Gramps media record"),
    "sidecar": _("XMP sidecar"),
    "file": _("File"),
}
_PRECEDENCE = ("gramps", "sidecar", "file")
# Pixel size is a fact about the file: the file wins over a sidecar's claim.
_LABEL_DIMENSIONS = _("Dimensions")
_FIELD_PRECEDENCE = {_LABEL_DIMENSIONS: ("file", "sidecar")}
_LABEL_TITLE = _("Title")
_LABEL_DATE_ORIGINAL = _("Date/Time Original")
_LABEL_DATE_DIGITIZED = _("Date/Time Digitized")
_DATE_LABELS = (_LABEL_DATE_ORIGINAL, _LABEL_DATE_DIGITIZED)
# markers (the colour/weight styling is applied in the tree)
_MARK_PREFERRED = "*"
_MARK_OVERRIDDEN = "\u2020"  # dagger

# XMP Metadata Working Group "applied to dimensions" of a sidecar
_DIM_W = "Xmp.mwg-rs.Regions/mwg-rs:AppliedToDimensions/stDim:w"
_DIM_H = "Xmp.mwg-rs.Regions/mwg-rs:AppliedToDimensions/stDim:h"
_DIM_UNIT = "Xmp.mwg-rs.Regions/mwg-rs:AppliedToDimensions/stDim:unit"


# ------------------------------------------------------------
#
# Row
#
# ------------------------------------------------------------
class Row(NamedTuple):
    """
    One display line of a tab.

    The status is "", "preferred" or "overridden" (see the precedence of the
    sources) and the note explains it.  The value is the single line shown in
    the tree; the full value is what the dialog shows.
    """

    section: str
    group: str
    label: str
    value: str
    tag: str
    desc: str
    full: str
    status: str = ""
    note: str = ""


# The items that sources are compared on: the generic label of each (the first
# name the common metadata vocabularies give it), and the tags that carry it in
# order of preference.  Only items with a counterpart in another source can
# disagree (see _judge).  The label is also the row name of each of its tags.
_FIELD_TAGS = (
    (_("Title"), ("Xmp.dc.title", "Iptc.Application2.ObjectName")),
    (_("Headline"), ("Xmp.photoshop.Headline", "Iptc.Application2.Headline")),
    (
        _("Description"),
        (
            "Exif.Image.ImageDescription",
            "Xmp.dc.description",
            "Iptc.Application2.Caption",
        ),
    ),
    (_("Keywords"), ("Iptc.Application2.Keywords", "Xmp.dc.subject")),
    (_("Alt Text"), ("Xmp.iptc.AltTextAccessibility",)),
    (_("People in Image"), ("Xmp.iptcExt.PersonInImage",)),
    (
        _("Date/Time Digitized"),
        # Provenance: when the *digital copy* was made.  xmp:CreateDate is the
        # creation of the digital resource, so it belongs here, not under
        # "Original" (a scanner stamps it with the scan time).
        (
            "Exif.Photo.DateTimeDigitized",
            "Xmp.exif.DateTimeDigitized",
            "Iptc.Application2.DigitizationDate",
            "Xmp.xmp.CreateDate",
        ),
    ),
    (
        _("Date/Time Original"),
        # The date of the *content* (the original physical item), which is
        # what the Gramps media Date records.  IPTC "Date Created" and
        # photoshop:DateCreated are defined as exactly that, so they lead; an
        # Exif DateTimeOriginal may just be the scan time, so it comes after.
        (
            "Iptc.Application2.DateCreated",
            "Xmp.photoshop.DateCreated",
            "Exif.Photo.DateTimeOriginal",
            "Xmp.exif.DateTimeOriginal",
        ),
    ),
    (_("Software"), ("Exif.Image.Software", "Xmp.xmp.CreatorTool")),
    (
        _("Creator"),
        ("Exif.Image.Artist", "Xmp.dc.creator", "Iptc.Application2.Byline"),
    ),
    (
        _("Copyright Notice"),
        ("Exif.Image.Copyright", "Xmp.dc.rights", "Iptc.Application2.Copyright"),
    ),
    (_("Rights Usage Terms"), ("Xmp.xmpRights.UsageTerms",)),
    (
        _("Credit Line"),
        ("Iptc.Application2.Credit", "Xmp.photoshop.Credit"),
    ),
    (_("Digital Source Type"), ("Xmp.iptcExt.DigitalSourceType",)),
)

# Exif tags combined into the "Technical & Capture" rows
_EXPOSURE_TAGS = (
    "Exif.Photo.FNumber",
    "Exif.Photo.ExposureTime",
    "Exif.Photo.ISOSpeedRatings",
)
_LENS_TAGS = ("Exif.Photo.LensModel", "Exif.Photo.FocalLength")

# Each tag of the items above is named by the item's generic label in the File
# and Sidecar tabs (the raw tag name is in the Tag column).
_GENERIC_LABELS = {tag: label for label, keys in _FIELD_TAGS for tag in keys}

# Gramps objects that can hold a media reference (and so a region of the
# image): (class name, DbRead getter).  Order = display order.
_REF_CLASSES = (
    ("Person", "get_person_from_handle"),
    ("Family", "get_family_from_handle"),
    ("Event", "get_event_from_handle"),
    ("Place", "get_place_from_handle"),
    ("Source", "get_source_from_handle"),
    ("Citation", "get_citation_from_handle"),
)

# "2019:05:04 12:30:59", "2019-05-04T12:30:59", ...
# date without a time, possibly partial: "1931-06-01", "1931-06", "1931"
_DATE_ONLY_RE = re.compile(r"^(\d{4})(?:[:\-](\d{2})(?:[:\-](\d{2}))?)?$")
_DATETIME_RE = re.compile(
    r"^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})"
)
# PDF dates: D:YYYYMMDDHHmmSS+hh'mm'  (everything after the year is optional)
_PDF_DATE_RE = re.compile(r"^(?:D:)?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?")
# XMP "LangAlt" values come back as: lang="x-default" The text
_LANG_RE = re.compile(r'^lang="[^"]*"\s*')
# Exiv2 writes a LangAlt as:  lang="x-default" Text, lang="de" Text, ...
_LANG_SPLIT_RE = re.compile(r'(?:^|,\s*)lang="([^"]*)"\s*')
# XMP value types that really hold several values (see _tag_values)
_XMP_ARRAY_TYPES = ("XmpBag", "XmpSeq", "XmpAlt")

# Name / Value / Tag column widths as a share of the tree's width
_COLUMN_SHARES = (0.4, 0.4, 0.2)

_MAX_NAME_CHARS = 40  # Media name shown in the dialog's button row
_MAX_VALUE_LEN = 300  # shown in the tree
_MAX_FULL_LEN = 20000  # kept for the dialog (MakerNote etc. can be huge)


# -----------------------------------------------------------------------------
# Formatting helpers (no GTK / no file access, easy to test)
# -----------------------------------------------------------------------------
def _clean(text: object, limit: int = _MAX_VALUE_LEN) -> str:
    """
    Return *text* on one line, shortened to *limit* characters.
    """
    if text is None:
        return ""
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[:limit] + "\u2026"
    return text


def _row(
    section: str,
    group: str,
    label: str,
    full: object,
    tag: str = "",
    desc: str = "",
    status: str = "",
    note: str = "",
) -> Row:
    """
    Return a Row whose display value is the shortened *full* value.
    """
    full = "" if full is None else str(full)
    if len(full) > _MAX_FULL_LEN:
        full = full[:_MAX_FULL_LEN] + "\u2026"
    return Row(section, group, label, _clean(full), tag, desc, full, status, note)


def _format_ymd_hms(
    year: int,
    month: int = 0,
    day: int = 0,
    hour: int | None = None,
    minute: int | None = None,
    second: int | None = None,
) -> str:
    """
    Format a possibly partial date, and an optional time, in the Gramps date format.

    Return an empty string if the date cannot be shown.
    """
    if not year:
        return ""
    try:
        text = _dd.display(Date(year, month or 0, day or 0))
    except (DateError, ValueError, TypeError):
        return ""
    if hour is not None:
        text = f"{text} {hour:02d}:{minute or 0:02d}:{second or 0:02d}"
    return text


def _format_datetime_text(text: str) -> str:
    """
    Show an Exif, IPTC or XMP date or date-time in the Gramps date format.

    Text that is not a date is returned unchanged.
    """
    match = _DATETIME_RE.match(text or "")
    if match:
        values = [int(group) for group in match.groups()]
        return _format_ymd_hms(*values) or text
    match = _DATE_ONLY_RE.match(text or "")
    if match:
        year, month, day = (int(group) if group else 0 for group in match.groups())
        return _format_ymd_hms(year, month, day) or text
    return text


def _format_pdf_date(text: str) -> str:
    """
    Show a PDF date string in the Gramps date format, or return it unchanged.
    """
    match = _PDF_DATE_RE.match(text or "")
    if not match:
        return text
    year = int(match.group(1))
    month, day, hour, minute, second = (
        int(group) if group else None for group in match.groups()[1:]
    )
    if hour is None:
        return _format_ymd_hms(year, month or 0, day or 0) or text
    return _format_ymd_hms(year, month or 0, day or 0, hour, minute, second) or text


def _rational_to_float(text: str) -> float | None:
    """
    Convert an Exif rational such as "200558/1000" to a float, or None.
    """
    num, sep, den = (text or "").partition("/")
    try:
        return float(num) / (float(den) if sep else 1.0)
    except (ValueError, ZeroDivisionError):
        return None


def _dms_to_decimal(text: str, ref: str) -> float | None:
    """
    Convert Exif degrees, minutes and seconds and a hemisphere letter to signed decimal
    degrees.
    """
    parts = [_rational_to_float(part) for part in (text or "").split()[:3]]
    numbers = [part for part in parts if part is not None]
    if not numbers or len(numbers) != len(parts):
        return None
    numbers += [0.0] * (3 - len(numbers))
    decimal = numbers[0] + numbers[1] / 60.0 + numbers[2] / 3600.0
    if (ref or "").strip().upper() in ("S", "W"):
        decimal = -decimal
    return decimal


def _format_duration(seconds: float) -> str:
    """
    Format seconds as H:MM:SS, or M:SS when under an hour.
    """
    seconds = int(round(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# -----------------------------------------------------------------------------
# GExiv2 (Exif / IPTC / XMP) reader
# -----------------------------------------------------------------------------
def _raw(meta: Any, key: str) -> str:
    """
    Return the raw string of a tag, or "" if it is missing or unreadable.
    """
    try:
        if meta.has_tag(key):
            return meta.get_tag_string(key) or ""
    except GLib.Error:
        pass
    return ""


def _lang_alt_text(raw: str) -> str:
    """
    Return the text of an XMP language alternative.

    The default language comes first, then each other language as "text (lang)".
    """
    parts = _LANG_SPLIT_RE.split(raw or "")
    if len(parts) < 3:
        return (raw or "").strip()
    alternatives = list(zip(parts[1::2], (text.strip() for text in parts[2::2])))
    texts = [text for lang, text in alternatives if lang == "x-default"][:1]
    texts += [f"{text} ({lang})" for lang, text in alternatives if lang != "x-default"]
    return "; ".join(text for text in texts if text)


def _tag_values(meta: Any, key: str) -> list[str] | None:
    """
    Return the values of an IPTC or XMP tag, or None if it holds one plain value.
    """
    # GExiv2 get_tag_multiple() cannot be used on every XMP tag.  Older
    # releases answer for a plain (non-array) XMP value, including every field of
    # an XMP structure, by repeating the value once for each character in it:
    # "514" comes back as ["514", "514", "514"].  So it is used only where the
    # value really is a list (XMP bags and sequences, IPTC datasets), where every
    # release is correct.  Language alternatives are parsed from the string form,
    # which older releases get wrong too.
    if key.startswith("Xmp."):
        try:
            kind = meta.get_tag_type(key) or ""
        except GLib.Error:
            kind = ""
        if kind == "LangAlt":
            return [_lang_alt_text(meta.get_tag_string(key))]
        if kind not in _XMP_ARRAY_TYPES:
            return None
    return [str(value) for value in (meta.get_tag_multiple(key) or [])]


def _tag_full(meta: Any, key: str) -> str:
    """
    Return the complete readable value of a tag, or "" if it is missing.

    Several values are joined with "; " and line breaks are kept.
    """
    text = ""
    try:
        if not meta.has_tag(key):
            return ""
        if key.startswith(("Iptc.", "Xmp.")):
            values = [
                _LANG_RE.sub("", value) for value in (_tag_values(meta, key) or [])
            ]
            text = "; ".join(value for value in values if value)
        if not text:
            text = meta.get_tag_interpreted_string(key) or meta.get_tag_string(key)
            text = _LANG_RE.sub("", text or "")
    except GLib.Error:
        return ""
    text = text.strip()
    if "date" in key.lower() or "time" in key.lower():
        text = _format_datetime_text(text)
    return text


def _describe(meta: Any, key: str) -> str:
    """
    Return the description of a tag from the Exiv2 tables, or "".
    """
    if not key:
        return ""
    try:
        return _clean(meta.get_tag_description(key) or "", 500)
    except GLib.Error:
        return ""


def _first_tag(meta: Any, keys: tuple[str, ...]) -> tuple[str, str]:
    """
    Return the key and value of the first tag in *keys* that has a value, else ("", "").
    """
    for key in keys:
        text = _tag_full(meta, key)
        if text:
            return key, text
    return "", ""


def _joined_tags(
    meta: Any, keys: tuple[str, ...], sep: str = " \u00b7 "
) -> tuple[str, str]:
    """
    Join the values of the tags in *keys* that have one.

    Return the keys used, separated by commas, and the joined text.
    """
    used, parts = [], []
    for key in keys:
        text = _clean(_tag_full(meta, key))
        if text:
            used.append(key)
            parts.append(text)
    return ", ".join(used), sep.join(parts)


def _gps_rows(meta: Any) -> list[Row]:
    """
    Return the GPS and Altitude rows decoded from the Exif GPS tags.
    """
    rows = []
    lat = _dms_to_decimal(
        _raw(meta, "Exif.GPSInfo.GPSLatitude"),
        _raw(meta, "Exif.GPSInfo.GPSLatitudeRef"),
    )
    lon = _dms_to_decimal(
        _raw(meta, "Exif.GPSInfo.GPSLongitude"),
        _raw(meta, "Exif.GPSInfo.GPSLongitudeRef"),
    )
    if lat is not None and lon is not None:
        converted = conv_lat_lon(f"{lat:.6f}", f"{lon:.6f}", "DEG")
        lat_text, lon_text = converted if isinstance(converted, tuple) else (None, None)
        if lat_text and lon_text:
            text = f"{lat_text}, {lon_text}"
        else:
            text = f"{lat:.6f}, {lon:.6f}"
        rows.append(
            _row(
                "capture",
                "",
                _("GPS"),
                text,
                "Exif.GPSInfo.GPSLatitude, Exif.GPSInfo.GPSLongitude",
                _describe(meta, "Exif.GPSInfo.GPSLatitude"),
            )
        )
    altitude = _rational_to_float(_raw(meta, "Exif.GPSInfo.GPSAltitude"))
    if altitude is not None:
        if _raw(meta, "Exif.GPSInfo.GPSAltitudeRef").strip() == "1":
            altitude = -altitude
        rows.append(
            _row(
                "capture",
                "",
                _("Altitude"),
                f"{altitude:.1f} m",
                "Exif.GPSInfo.GPSAltitude",
                _describe(meta, "Exif.GPSInfo.GPSAltitude"),
            )
        )
    return rows


def _capture_rows(meta: Any) -> list[Row]:
    """
    Return the Technical & Capture rows decoded from the Exif of the file.

    They show the camera, exposure, lens and GPS position; the raw tags are also listed
    in the Exif section.
    """
    rows = []
    make = _tag_full(meta, "Exif.Image.Make")
    model = _tag_full(meta, "Exif.Image.Model")
    camera = model if model.startswith(make) else f"{make} {model}".strip()
    if camera:
        rows.append(
            _row(
                "capture",
                "",
                _("Make & Model"),
                camera,
                "Exif.Image.Make, Exif.Image.Model",
                _describe(meta, "Exif.Image.Model"),
            )
        )
    for label, keys in (
        (_("Exposure Settings"), _EXPOSURE_TAGS),
        (_("Lens Specifications"), _LENS_TAGS),
    ):
        used, text = _joined_tags(meta, keys)
        if text:
            rows.append(
                _row("capture", "", label, text, used, _describe(meta, keys[0]))
            )
    rows += _gps_rows(meta)
    return rows


def _open_metadata(path: str) -> Any:
    """
    Open an image or an XMP sidecar with GExiv2, or return None if that is not possible.
    """
    # Metadata() followed by open_path() works whether or not the optional
    # GExiv2 Python override is present.
    if GExiv2 is None or not path:
        return None
    try:
        meta = GExiv2.Metadata()
        meta.open_path(path)
        return meta
    except GLib.Error as err:
        LOG.debug("GExiv2 could not open %s: %s", path, err)
    except _GEXIV2_ERRORS:
        LOG.exception("MetadataInspector: could not read metadata from %s", path)
    return None


def _sidecar_candidates(media_path: str) -> list[str]:
    """
    Return every path where an XMP sidecar of *media_path* is looked for.

    The name of the file with its extension replaced ("photo.xmp"), as the Photo Tagging
    gramplet does, comes first, then the name with ".xmp" added ("photo.jpg.xmp"); each
    also in capitals.  The lower case forms are at even positions.
    """
    base = os.path.splitext(media_path)[0]
    return [
        candidate
        for candidate in (
            base + ".xmp",
            base + ".XMP",
            media_path + ".xmp",
            media_path + ".XMP",
        )
        if candidate != media_path
    ]


def _find_sidecar(media_path: str) -> str:
    """
    Return the first XMP sidecar of the file that exists, or "".
    """
    for candidate in _sidecar_candidates(media_path):
        if os.path.isfile(candidate):
            return candidate
    return ""


def _struct_label(tag: str) -> str:
    """
    Return a readable name for an XMP structure path, e.g. "Regions > RegionList[1] >
    Name".
    """
    path = tag.split(".", 2)[-1]
    return " > ".join(segment.split(":", 1)[-1] for segment in path.split("/"))


def _tag_rows(meta: Any, section: str, getter: Callable[[], list[str]]) -> list[Row]:
    """
    Return one Row for each tag that *getter* lists; empty XMP structure containers are
    left out.
    """
    rows: list[Row] = []
    try:
        tags = getter()
    except GLib.Error:
        return rows
    for tag in tags:
        parts = tag.split(".")
        group = parts[1] if len(parts) > 2 else ""
        full = _tag_full(meta, tag)
        if not full and section.startswith("xmp"):
            continue
        if "/" in tag:
            label = _struct_label(tag)
        elif tag in _GENERIC_LABELS:
            label = _GENERIC_LABELS[tag]
        else:
            try:
                label = meta.get_tag_label(tag) or parts[-1]
            except GLib.Error:
                label = parts[-1]
        rows.append(_row(section, group, label, full, tag, _describe(meta, tag)))
    return rows


# ------------------------------------------------------------
#
# Candidate
#
# ------------------------------------------------------------
class Candidate(NamedTuple):
    """
    A value that one source offers for one compared item.

    The *cmp* key is what is compared between sources; *rowkeys* are the
    (section, tag or label) of the rows that carry the value, so that they can
    be marked.
    """

    source: str
    value: str
    cmp: Key
    rowkeys: tuple[tuple[str, str], ...]


_SECTION_OF_PREFIX = {"Exif": "exif", "Iptc": "iptc", "Xmp": "xmp"}
_DATE_PARTS_RE = re.compile(r"^(\d{4})(?:[:\-](\d{2})(?:[:\-](\d{2}))?)?")


def _norm_text(text: str) -> str:
    """
    Normalize text for comparison: whitespace and case are not differences.
    """
    return " ".join((text or "").split()).casefold()


def _date_key_from_text(text: str) -> Key | None:
    """
    Return a ("gdate", Date) comparison key for an Exif, IPTC or XMP date string, or
    None.
    """
    match = _DATE_PARTS_RE.match(text or "")
    if not match or int(match.group(1)) == 0:
        return None
    year, month, day = (int(group) if group else 0 for group in match.groups())
    try:
        return ("gdate", Date(year, month, day))
    except (DateError, ValueError, TypeError):
        return None


def _gramps_date_key(date: Date | None) -> Key | None:
    """
    Return a comparison key for the Gramps media Date, or None if it cannot be compared.

    Empty and text-only dates cannot be compared; ranges, approximate dates and other
    calendars can.
    """
    try:
        if (
            date is None
            or date.is_empty()
            or date.get_modifier() == Date.MOD_TEXTONLY
            or not date.get_sort_value()
        ):
            return None
    except AttributeError:
        return None
    return ("gdate", date)


def _specificity(cmp: Key) -> int:
    """
    Return how precise a date key is: 1 for a year to 3 for a full date, else 0.
    """
    if cmp[0] != "gdate":
        return 0
    date = cmp[1]
    if date.get_modifier() != Date.MOD_NONE or date.get_quality() != Date.QUAL_NONE:
        return 0
    return sum(
        1 for part in (date.get_year(), date.get_month(), date.get_day()) if part
    )


def _same(first: Key, second: Key) -> bool:
    """
    Return True if two comparison keys do not disagree.

    Dates agree when the spans of time they stand for overlap, as Date.match() decides.
    That handles partial dates, the ranges set in the Gramps preferences for approximate
    dates, date ranges and other calendars.
    """
    if first[0] == "gdate" and second[0] == "gdate":
        return first[1].match(second[1])
    return first == second


def _resolve(
    label: str, candidates: list[Candidate]
) -> tuple[Candidate, list[Candidate]]:
    """
    Return the candidate in use and the candidates that disagree with the one of highest
    precedence.

    Of the candidates that agree, the most precise one (for example the fuller date) is
    the one in use.
    """
    order = _FIELD_PRECEDENCE.get(label, _PRECEDENCE)
    ranked = sorted(
        candidates,
        key=lambda cand: (
            order.index(cand.source) if cand.source in order else len(order)
        ),
    )
    winner = ranked[0]
    agreeing = [cand for cand in ranked if _same(winner.cmp, cand.cmp)]
    losers = [cand for cand in ranked if not _same(winner.cmp, cand.cmp)]
    shown = max(agreeing, key=lambda cand: _specificity(cand.cmp))
    return shown, losers


def _tag_candidate(
    meta: Any, source: str, label: str, key: str, text: str
) -> Candidate:
    """
    Return the Candidate for the first tag of an item that *meta* has.
    """
    if source == "sidecar":
        section = "xmp_sidecar"
    else:
        section = _SECTION_OF_PREFIX.get(key.split(".")[0], "xmp")
    cmp = None
    if label in _DATE_LABELS:
        cmp = _date_key_from_text(_raw(meta, key))
    if cmp is None:
        cmp = ("text", _norm_text(text))
    return Candidate(source, text, cmp, ((section, key),))


def _gramps_candidates(media: Media, path: str) -> dict[str, Candidate]:
    """
    Return what the Gramps media record offers for the items it overlaps: the Title and
    the date of the content.

    The Gramps record is the arbiter, so it outranks the sidecar and the file.  A Title
    that is only the file name, which is the Gramps default, is not offered.
    """
    found = {}
    title = _custom_title(media, path)
    if title:
        found[_LABEL_TITLE] = Candidate(
            "gramps",
            title,
            ("text", _norm_text(title)),
            (("gramps", _("Title")),),
        )
    date = media.get_date_object()
    key = _gramps_date_key(date)
    if key:
        found[_LABEL_DATE_ORIGINAL] = Candidate(
            "gramps",
            _dd.display(date),
            key,
            (("gramps", _("Date")),),
        )
    return found


def _custom_title(media: Media, path: str) -> str:
    """
    Return the media Title, or "" if it is empty or only the file name without
    extension.
    """
    title = (media.get_description() or "").strip()
    default = os.path.splitext(os.path.basename(path or media.get_path()))[0]
    return "" if title == default else title


def _dimension_row(size: tuple[int, int]) -> Row:
    """
    Return the File information row for the pixel size of the image.
    """
    return _row(
        "fileinfo",
        "",
        _LABEL_DIMENSIONS,
        _("%(w)d x %(h)d pixels") % {"w": size[0], "h": size[1]},
    )


def _dimension_candidates(
    size: tuple[int, int] | None, side_meta: Any
) -> list[Candidate]:
    """
    Return the pixel size of the file and the size that a sidecar says its regions apply
    to.

    Nothing is returned if the size of the file is unknown.
    """
    if not size:
        return []
    text = _("%(w)d x %(h)d pixels")
    found = [
        Candidate(
            "file",
            text % {"w": size[0], "h": size[1]},
            ("dims", size[0], size[1]),
            (("fileinfo", _LABEL_DIMENSIONS),),
        )
    ]
    if side_meta is not None:
        try:
            side_w, side_h = int(_raw(side_meta, _DIM_W)), int(_raw(side_meta, _DIM_H))
        except ValueError:
            return found
        if _raw(side_meta, _DIM_UNIT).strip().lower() in ("", "pixel"):
            found.append(
                Candidate(
                    "sidecar",
                    text % {"w": side_w, "h": side_h},
                    ("dims", side_w, side_h),
                    (("xmp_sidecar", _DIM_W), ("xmp_sidecar", _DIM_H)),
                )
            )
    return found


def _judge(marks: list[Mark], label: str, candidates: list[Candidate]) -> None:
    """
    Add marks for the rows of one item when its sources disagree.

    The value in use is "preferred" and the values it overrides are "overridden".
    """
    shown, losers = _resolve(label, candidates)
    if not losers:
        return
    note = _("Preferred value. Other sources differ:") + "".join(
        f"\n  {_SOURCE_NAMES[cand.source]}: {cand.value}" for cand in losers
    )
    for section, matcher in shown.rowkeys:
        marks.append((section, matcher, "preferred", note))
    lost = _("Overridden by %(source)s: %(value)s") % {
        "source": _SOURCE_NAMES[shown.source],
        "value": shown.value,
    }
    for cand in losers:
        for section, matcher in cand.rowkeys:
            marks.append((section, matcher, "overridden", lost))


def _apply_marks(rows: list[Row], marks: list[Mark]) -> list[Row]:
    """
    Return *rows* with the status and note of every matching mark applied.
    """
    result = []
    for row in rows:
        for section, matcher, status, note in marks:
            if row.section == section and matcher in (row.tag, row.label):
                row = row._replace(status=status, note=note)
        result.append(row)
    return result


def _conflict_marks(
    file_meta: Any,
    side_meta: Any,
    gramps: dict[str, Candidate],
    dimensions: list[Candidate],
) -> list[Mark]:
    """
    Return the marks for rows whose sources disagree.

    The Gramps record outranks the sidecar, which outranks the file.
    """
    marks: list[Mark] = []
    for label, keys in _FIELD_TAGS:
        candidates = []
        for meta, source in ((file_meta, "file"), (side_meta, "sidecar")):
            if meta is None:
                continue
            key, text = _first_tag(meta, keys)
            if text:
                candidates.append(_tag_candidate(meta, source, label, key, text))
        if label in gramps:
            candidates.append(gramps[label])
        if len(candidates) > 1:
            _judge(marks, label, candidates)
    if len(dimensions) > 1:
        _judge(marks, _LABEL_DIMENSIONS, dimensions)
    return marks


def _read_gexiv2(
    path: str,
    sidecar_path: str = "",
    read_file: bool = True,
    gramps: dict[str, Candidate] | None = None,
    size: tuple[int, int] | None = None,
) -> tuple[list[Row], list[Mark]] | None:
    """
    Read Exif, IPTC and XMP from the file and XMP from its sidecar.

    :param read_file: False to read only the sidecar.
    :param size: The pixel size if already known, else GExiv2 is asked.
    :returns: The rows and the marks, or None if nothing could be opened.
    """
    file_meta = _open_metadata(path) if read_file else None
    side_meta = _open_metadata(sidecar_path)
    if file_meta is None and side_meta is None:
        return None

    rows = []
    if size is None and file_meta is not None:
        width, height = file_meta.get_pixel_width(), file_meta.get_pixel_height()
        if width > 0 and height > 0:
            size = (width, height)
            rows.append(_dimension_row(size))
    marks = _conflict_marks(
        file_meta, side_meta, gramps or {}, _dimension_candidates(size, side_meta)
    )
    if file_meta is not None:
        rows += _capture_rows(file_meta)
        rows += _tag_rows(file_meta, "exif", file_meta.get_exif_tags)
        rows += _tag_rows(file_meta, "iptc", file_meta.get_iptc_tags)
        rows += _tag_rows(file_meta, "xmp", file_meta.get_xmp_tags)
    if side_meta is not None:
        rows += _tag_rows(side_meta, "xmp_sidecar", side_meta.get_xmp_tags)
    return rows, marks


# -----------------------------------------------------------------------------
# PDF reader (optional: pypdf / PyPDF2)
# -----------------------------------------------------------------------------
def _read_pdf(path: str) -> tuple[list[Row], str]:
    """
    Read the PDF information; return the rows and a note for the user, if any.
    """
    if PdfReader is None:
        return [], _("Install the 'pypdf' Python module to view PDF metadata.")
    try:
        reader = PdfReader(path)
        if getattr(reader, "is_encrypted", False):
            reader.decrypt("")
        info = reader.metadata
        pages = len(reader.pages)
    except _PDF_ERRORS as err:
        # a damaged or encrypted PDF raises one of these
        LOG.debug("PDF read failed for %s: %s", path, err)
        return [], _("This PDF could not be read (damaged or encrypted?).")

    rows = [_row("pdf", "", _("Pages"), str(pages))]
    for key, value in (info or {}).items():
        name = str(key).lstrip("/")
        text = str(value)
        if name.endswith("Date"):
            text = _format_pdf_date(text.replace("'", ""))
        if not text.strip():
            continue
        rows.append(_row("pdf", "", name, text, str(key)))
    return rows, ""


# -----------------------------------------------------------------------------
# Audio / video reader (optional: mutagen)
# -----------------------------------------------------------------------------
def _read_av(path: str) -> tuple[list[Row], str]:
    """
    Read the stream information and tags of an audio or video file; return the rows and
    a note.
    """
    if mutagen is None:
        return [], _("Install the 'mutagen' Python module to view audio tags.")
    try:
        audio = mutagen.File(path, easy=True)
    except _AV_ERRORS as err:
        LOG.debug("mutagen failed for %s: %s", path, err)
        audio = None
    if audio is None:
        return [], ""

    rows = []
    info = getattr(audio, "info", None)
    stream = (
        ("length", _("Duration"), _format_duration),
        ("bitrate", _("Bit rate"), lambda v: f"{int(v) // 1000} kbps"),
        ("sample_rate", _("Sample rate"), lambda v: f"{int(v)} Hz"),
        ("channels", _("Channels"), str),
    )
    for attr, label, fmt in stream:
        value = getattr(info, attr, None)
        if value:
            rows.append(_row("av", _("Stream"), label, fmt(value)))

    for key, values in (audio.tags or {}).items():
        if not isinstance(values, (list, tuple)):
            values = [values]
        text = "; ".join(str(value) for value in values)
        if text.strip():
            rows.append(_row("av", _("Tags"), key, text, key))
    return rows, ""


# -----------------------------------------------------------------------------
# Gramps references (who uses this media object, and which part of it)
# -----------------------------------------------------------------------------
def _image_size(path: str) -> tuple[int, int] | None:
    """
    Return the (width, height) of an image from its header, or None.
    """
    try:
        info = GdkPixbuf.Pixbuf.get_file_info(path)
    except (GLib.Error, TypeError, ValueError):
        return None
    width, height = info[1], info[2]
    return (width, height) if width > 0 and height > 0 else None


def _object_name(db: DbReadBase, class_name: str, obj: Any) -> str:
    """
    Return the display name of a Person, Family, Event, Place, Source or Citation.
    """
    name = ""
    try:
        if class_name == "Person":
            name = name_displayer.display(obj)
        elif class_name == "Family":
            name = family_name(obj, db)
        elif class_name == "Event":
            name = obj.get_description() or str(obj.get_type())
        elif class_name == "Place":
            name = place_displayer.display(db, obj)
        elif class_name == "Source":
            name = obj.get_title()
        elif class_name == "Citation":
            name = obj.get_page()
    except _DB_ERRORS:
        # a name that cannot be built must not hide the reference itself
        LOG.debug("No display name for %s %s", class_name, obj.get_gramps_id())
    return name


def _region_texts(
    rect: tuple[int, int, int, int] | None, size: tuple[int, int] | None
) -> tuple[str, str]:
    """
    Return the short text for the tree and the full text for the dialog of a media
    reference region.

    :param rect: (left, top, right, bottom) in percent of the image, from its top-left
        corner, or None for the whole image. :param size: The pixel size of the image,
        or None.
    """
    if not rect or not any(rect):
        whole = _("Whole image (no region selected)")
        return whole, whole
    left, top, right, bottom = rect
    short = f"{left}%, {top}% \u2013 {right}%, {bottom}%"
    full = _(
        "Region (percent of the image, from its top-left corner):\n"
        "Left %(l)d%%, Top %(t)d%%, Right %(r)d%%, Bottom %(b)d%%"
    ) % {"l": left, "t": top, "r": right, "b": bottom}
    if size:
        width, height = size
        full += "\n" + _(
            "About %(x1)d,%(y1)d to %(x2)d,%(y2)d pixels in a %(w)d x %(h)d pixel image"
        ) % {
            "x1": round(left * width / 100.0),
            "y1": round(top * height / 100.0),
            "x2": round(right * width / 100.0),
            "y2": round(bottom * height / 100.0),
            "w": width,
            "h": height,
        }
    return short, full


def _reference_holder(db: DbReadBase, class_name: str, handle: str) -> Any:
    """
    Return the object of that class and handle that can hold a media reference.
    """
    getter = getattr(db, dict(_REF_CLASSES).get(class_name, ""), None)
    return getter(handle) if getter else None


def _reference_rows(
    db: DbReadBase, media: Media, size: tuple[int, int] | None
) -> list[Row]:
    """
    Return one Row for each media reference to *media*, with the region of the image
    that it selects.
    """
    find = getattr(db, "find_backlink_handles", None)
    if find is None:
        return []
    handle = media.get_handle()
    order = [name for name, _getter in _REF_CLASSES]
    found = []
    try:
        backlinks = list(find(handle, order))
    except _DB_ERRORS:
        LOG.debug("Could not look up references to %s", handle, exc_info=True)
        return []
    for class_name, ref_handle in backlinks:
        obj = _reference_holder(db, class_name, ref_handle)
        if obj is None:
            continue
        label = (
            f"{_object_name(db, class_name, obj) or _('(no name)')} "
            f"[{obj.get_gramps_id()}]"
        )
        for ref in obj.get_media_list():
            if ref.get_reference_handle() != handle:
                continue
            short, full = _region_texts(ref.get_rectangle(), size)
            found.append(
                (
                    order.index(class_name),
                    glocale.sort_key(label),
                    Row(
                        "refs",
                        _gramps_gettext(class_name),
                        label,
                        short,
                        "",
                        _("The part of the image selected on this media reference."),
                        full,
                    ),
                )
            )
    found.sort(key=lambda item: item[:2])
    return [item[2] for item in found]


# -----------------------------------------------------------------------------
# Collect everything for one Media object
# -----------------------------------------------------------------------------
# ------------------------------------------------------------
#
# Collected
#
# ------------------------------------------------------------
class Collected(NamedTuple):
    """
    Everything that collect_metadata() found.

    The rows, the messages for the user, which tabs have data (tab id to
    bool), and the sidecar names that were looked for.
    """

    rows: list[Row]
    notes: list[str]
    has_data: dict[str, bool]
    sidecar_names: tuple[str, ...]


def _safe_get(db: DbReadBase, getter_name: str, handle: str) -> Any:
    """
    Return db.<getter_name>(handle), or None if the database cannot supply it.
    """
    getter = getattr(db, getter_name, None)
    if getter is None:
        return None
    try:
        return getter(handle)
    except _DB_ERRORS:
        # e.g. a handle that no longer exists
        LOG.debug("Could not get %s for %s", getter_name, handle, exc_info=True)
        return None


def _media_object_rows(db: DbReadBase, media: Media) -> list[Row]:
    """
    Return Rows for the Attributes, Notes, Tags and Citations of the Media object.
    """
    rows = []
    for attr in media.get_attribute_list():
        rows.append(_row("attrs", "", str(attr.get_type()), attr.get_value()))
    for handle in media.get_note_list():
        note = _safe_get(db, "get_note_from_handle", handle)
        if note is not None:
            label = f"{note.get_type()} [{note.get_gramps_id()}]"
            rows.append(_row("notes", "", label, note.get()))
    for handle in media.get_tag_list():
        tag = _safe_get(db, "get_tag_from_handle", handle)
        if tag is not None:
            rows.append(_row("tags", "", tag.get_name(), ""))
    for handle in media.get_citation_list():
        citation = _safe_get(db, "get_citation_from_handle", handle)
        if citation is not None:
            source = _safe_get(
                db, "get_source_from_handle", citation.get_reference_handle()
            )
            title = source.get_title() if source is not None else ""
            label = f"{title or _('(no title)')} [{citation.get_gramps_id()}]"
            rows.append(_row("cites", "", label, citation.get_page()))
    return rows


def _created_time(path: str, stat: os.stat_result) -> datetime.datetime | None:
    """
    Return when the file was created, or None if the system does not record it.
    """
    # os.stat() cannot tell on Linux: there st_ctime is the last change of the
    # inode, not the creation.  So use st_birthtime where Python has it (macOS,
    # BSD, Windows), else the birth time from GIO ("time::created"), which Linux
    # file systems provide where they record it.
    birth = getattr(stat, "st_birthtime", None)
    try:
        if birth:
            return datetime.datetime.fromtimestamp(birth)
        info = Gio.File.new_for_path(path).query_info(
            "time::created", Gio.FileQueryInfoFlags.NONE, None
        )
        if info.has_attribute("time::created"):
            created = info.get_attribute_uint64("time::created")
            if created > 0:
                return datetime.datetime.fromtimestamp(created)
    except (GLib.Error, OverflowError, OSError, ValueError):
        LOG.debug("No creation time for %s", path, exc_info=True)
    return None


def _format_timestamp(moment: datetime.datetime) -> str:
    """
    Format a datetime, with its time, in the Gramps date format.
    """
    return _format_ymd_hms(
        moment.year,
        moment.month,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second,
    )


def _file_info_rows(section: str, path: str, mime: str = "") -> list[Row]:
    """
    Return Rows for the name, folder, size, created and modified time of a file, and its
    type if *mime* is given.
    """
    stat = os.stat(path)
    created = _created_time(path, stat)
    rows = [
        _row(section, "", _("Name"), os.path.basename(path)),
        _row(section, "", _("Folder"), os.path.dirname(path)),
        _row(section, "", _("Size"), GLib.format_size(stat.st_size)),
        _row(
            section,
            "",
            _("Created"),
            _format_timestamp(created) if created else _("Not available"),
        ),
        _row(
            section,
            "",
            _("Modified"),
            _format_timestamp(datetime.datetime.fromtimestamp(stat.st_mtime)),
        ),
    ]
    if mime:
        rows.append(_row(section, "", _("Type"), f"{get_description(mime)} ({mime})"))
    return rows


def _finish(
    rows: list[Row],
    notes: list[str],
    marks: list[Mark],
    media: Media,
    path: str,
    sidecar_names: tuple[str, ...],
) -> Collected:
    """
    Apply the marks to the rows and work out which tabs have data.
    """
    # The File and Sidecar tabs have data whenever they have anything to list.
    # The Current Tree tab always lists the ID and path of the media record, so
    # it only has data for what somebody recorded: references, attributes,
    # notes, tags, citations, a date, or a Title other than the default file name.
    rows = _apply_marks(rows, marks)
    sections = {row.section for row in rows}
    has_data = {
        "file": bool(sections & set(_TAB_SECTIONS["file"])),
        "sidecar": bool(sections & set(_TAB_SECTIONS["sidecar"])),
        "gramps": bool(sections & set(_GRAMPS_DATA))
        or bool(_custom_title(media, path))
        or any(row.section == "gramps" and row.label == _("Date") for row in rows),
    }
    return Collected(rows, notes, has_data, sidecar_names)


def _gramps_rows(
    db: DbReadBase, media: Media, size: tuple[int, int] | None
) -> list[Row]:
    """
    Return the Rows of the media record, its own objects and its references.

    All of it is in the database, so it is listed even if the file is missing.
    """
    rows = [
        _row("gramps", "", _("Gramps ID"), media.get_gramps_id()),
        _row("gramps", "", _("Title"), media.get_description()),
    ]
    media_date = _dd.display(media.get_date_object())
    if media_date:
        rows.append(_row("gramps", "", _("Date"), media_date))
    rows.append(_row("gramps", "", _("Stored path"), media.get_path()))
    return rows + _media_object_rows(db, media) + _reference_rows(db, media, size)


def _embedded_metadata(
    path: str,
    mime: str,
    sidecar: str,
    gramps: dict[str, Candidate],
    size: tuple[int, int] | None,
) -> tuple[list[Row], list[Mark], list[str]]:
    """
    Read what is embedded in the file and in its sidecar.

    :returns: The rows, the marks, and the messages for the user.
    """
    rows: list[Row] = []
    marks: list[Mark] = []
    notes: list[str] = []
    is_image = mime.startswith("image/")
    reads_file = is_image or mime.startswith("video/")
    if reads_file or sidecar:
        found = _read_gexiv2(
            path, sidecar, read_file=reads_file, gramps=gramps, size=size
        )
        if found is not None:
            rows += found[0]
            marks += found[1]
        if GExiv2 is None:
            notes.append(
                _(
                    "Install the GExiv2 library (gir1.2-gexiv2-*) to view image "
                    "metadata and XMP sidecars."
                )
            )
        elif found is None and is_image:
            notes.append(_("No readable Exif/IPTC/XMP metadata in this image."))
        elif sidecar and not any(
            row.section in ("exif", "iptc", "xmp") for row in rows
        ):
            if any(row.section == "xmp_sidecar" for row in rows):
                notes.append(
                    _(
                        "The file itself carries no Exif/IPTC/XMP metadata; the "
                        "details come from its XMP sidecar (%s)."
                    )
                    % os.path.basename(sidecar)
                )
    if mime == "application/pdf":
        part_rows, note = _read_pdf(path)
        rows += part_rows
        if note:
            notes.append(note)
    if mime.startswith("audio/") or mime.startswith("video/"):
        part_rows, note = _read_av(path)
        rows += part_rows
        if note:
            notes.append(note)
    if not any(row.section in _EMBEDDED for row in rows) and not notes:
        notes.append(_("No embedded metadata found in this file."))
    return rows, marks, notes


def collect_metadata(db: DbReadBase, media: Media) -> Collected:
    """
    Gather all the metadata for a Media object.
    """
    path = media_path_full(db, media.get_path())
    mime = media.get_mime_type() or ""
    sidecar_names = tuple(
        os.path.basename(cand) for cand in _sidecar_candidates(path)[::2]
    )
    size = _image_size(path) if mime.startswith("image/") else None
    rows = _gramps_rows(db, media, size)
    notes: list[str] = []
    marks: list[Mark] = []
    if not os.path.isfile(path):
        notes.append(_("File not found: %s") % path)
    elif not os.access(path, os.R_OK):
        notes.append(_("File is not readable: %s") % path)
    else:
        rows += _file_info_rows("fileinfo", path, mime)
        if size:
            rows.append(_dimension_row(size))
        sidecar = _find_sidecar(path)
        if sidecar:
            rows += _file_info_rows("sidecar_file", sidecar)
        more_rows, marks, more_notes = _embedded_metadata(
            path, mime, sidecar, _gramps_candidates(media, path), size
        )
        rows += more_rows
        notes += more_notes
    return _finish(rows, notes, marks, media, path, sidecar_names)


# ------------------------------------------------------------
#
# MetadataDialog
#
# ------------------------------------------------------------
class MetadataDialog(ManagedWindow):
    """
    Read-only dialog for one metadata item, listed in the Windows menu of Gramps.

    Opening the same item again raises the dialog that is already open.
    """

    def __init__(
        self,
        uistate: DisplayState,
        track: list[Any],
        key: str,
        label: str,
        value: str,
        location: str,
        tag: str,
        description: str,
        media_name: str = "",
        note: str = "",
    ) -> None:
        """
        Build and show the dialog.

        :param track: The parent windows; an empty list for the main window.
        :param key: Identifies the item, so that it is opened only once.
        :param location: Where the item sits in the tree, e.g. File > Exif > Image.
        :param media_name: The name of the Media object, shown beside the Close button.
        :param note: Which source is in use, or what overrides the value.
        :raises WindowActiveError: If the dialog for the item is already open.
        """
        # build_menu_names() is called from ManagedWindow.__init__
        self.item_label = label
        self.media_name = media_name
        ManagedWindow.__init__(self, uistate, track, key)

        title = _gramps_gettext("%(str1)s: %(str2)s") % {
            "str1": _("Metadata"),
            "str2": label,
        }
        dialog = Gtk.Dialog()
        self.set_window(dialog, None, title)
        dialog.set_default_size(600, 350)
        dialog.add_button(_gramps_gettext("_Close"), Gtk.ResponseType.CLOSE)
        dialog.set_default_response(Gtk.ResponseType.CLOSE)
        # Only the Close button is handled here: closing with the window
        # manager (or Escape) goes through the "delete-event" handler that
        # set_window() connected to ManagedWindow.close().
        dialog.connect("response", self.cb_response)

        self._add_media_name(dialog)
        self._build_content(dialog, label, value, location, tag, description, note)
        self.show()

    def build_menu_names(self, obj: str) -> tuple[str, str | None]:
        """
        Return the label of this window in the Windows menu; it has no submenu.
        """
        label = _gramps_gettext("%(str1)s: %(str2)s") % {
            "str1": _("Metadata"),
            "str2": self.item_label,
        }
        if self.media_name:
            label = f"{label} ({_clean(self.media_name, 40)})"
        return (label, None)

    def build_window_key(self, obj: str) -> str:
        """
        Return the key as given; the default, id(obj), would never match a new string.
        """
        return obj

    def cb_response(self, _dialog: Gtk.Dialog, response: int) -> None:
        """
        Close the window when the Close button is pressed.
        """
        if response == Gtk.ResponseType.CLOSE:
            self.close()

    def _add_media_name(self, dialog: Gtk.Dialog) -> None:
        """
        Show the name of the Media object at the left of the Close button.
        """
        # In a GtkButtonBox a "secondary" child goes to the end opposite the
        # buttons, and a non-homogeneous child keeps its own width so that the
        # Close button is not stretched.
        if not self.media_name:
            return
        action_area = dialog.get_action_area()
        name_label = Gtk.Label(label=self.media_name, xalign=0)
        # A GtkButtonBox gives each child only its *minimum* width, and an
        # ellipsizable label's minimum is just "...".  So request a real
        # minimum (width_chars) and ellipsize only names too long to fit.
        chars = min(len(self.media_name), _MAX_NAME_CHARS)
        name_label.set_width_chars(chars)
        name_label.set_max_width_chars(_MAX_NAME_CHARS)
        if len(self.media_name) > _MAX_NAME_CHARS:
            name_label.set_ellipsize(3)  # Pango.EllipsizeMode.END
        name_label.set_tooltip_text(self.media_name)
        name_label.set_margin_start(6)
        action_area.pack_start(name_label, False, False, 0)
        action_area.set_child_secondary(name_label, True)
        action_area.set_child_non_homogeneous(name_label, True)

    @staticmethod
    def _build_content(
        dialog: Gtk.Dialog,
        label: str,
        value: str,
        location: str,
        tag: str,
        description: str,
        note: str = "",
    ) -> None:
        """
        Build the Name and Value area and the Details notebook.
        """
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.set_wide_handle(True)
        dialog.get_content_area().pack_start(paned, True, True, 0)
        paned.pack1(
            MetadataDialog._build_name_value(label, value), resize=True, shrink=False
        )
        paned.pack2(
            MetadataDialog._build_details(location, tag, description, note),
            resize=True,
            shrink=True,
        )

    @staticmethod
    def _build_name_value(label: str, value: str) -> Gtk.Box:
        """
        Return the top pane: the Name and the Value of the item.
        """
        top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        top_box.set_size_request(-1, 130)
        grid = Gtk.Grid(row_spacing=6, column_spacing=12, border_width=12)

        name_label = Gtk.Label.new_with_mnemonic(_gramps_gettext("_Name:"))
        name_label.set_halign(Gtk.Align.START)
        name_entry = Gtk.Entry(hexpand=True, editable=False)
        name_entry.set_text(label)
        name_label.set_mnemonic_widget(name_entry)
        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(name_entry, 1, 0, 1, 1)

        value_label = Gtk.Label.new_with_mnemonic(_gramps_gettext("_Value:"))
        value_label.set_halign(Gtk.Align.START)
        value_label.set_valign(Gtk.Align.START)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        value_view = Gtk.TextView(editable=False, accepts_tab=False)
        value_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        value_view.get_buffer().set_text(value)
        scroll.add(value_view)
        value_label.set_mnemonic_widget(value_view)
        grid.attach(value_label, 0, 1, 1, 1)
        grid.attach(scroll, 1, 1, 1, 1)

        top_box.pack_start(grid, True, True, 0)
        return top_box

    @staticmethod
    def _build_details(
        location: str, tag: str, description: str, note: str
    ) -> Gtk.Notebook:
        """
        Return the bottom pane: a notebook with the Details page.
        """
        notebook = Gtk.Notebook()
        details = Gtk.Grid(row_spacing=6, column_spacing=12, border_width=12)
        items = [
            (_("Section:"), location),
            (_("Tag:"), tag),
            (_("Description:"), description),
            (_("Sources:"), note),
        ]
        row_no = 0
        for caption, item_text in items:
            if not item_text:
                continue
            caption_label = Gtk.Label(label=caption, xalign=0, yalign=0)
            text_label = Gtk.Label(label=item_text, xalign=0, yalign=0, hexpand=True)
            text_label.set_line_wrap(True)
            text_label.set_selectable(True)
            details.attach(caption_label, 0, row_no, 1, 1)
            details.attach(text_label, 1, row_no, 1, 1)
            row_no += 1
        details_scroll = Gtk.ScrolledWindow()
        details_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        details_scroll.add(details)
        notebook.append_page(details_scroll, Gtk.Label(label=_("Details")))
        return notebook


# ------------------------------------------------------------
#
# _Page
#
# ------------------------------------------------------------
class _Page:
    """
    One notebook tab: its tree store and tree, and the widgets of its label.
    """

    def __init__(
        self, tab_id: str, name: str, icon: str, sections: tuple[str, ...]
    ) -> None:
        """
        Remember what the tab shows; the widgets are created when the page is built.
        """
        self.tab_id = tab_id
        self.name = name
        self.icon = icon
        self.sections = sections
        self.store: Any = None
        self.tree: Any = None
        self.scroll: Any = None
        self.message: Any = None
        self.box: Any = None
        self.tab_widget: Any = None
        self.tab_image: Any = None
        self.tab_label: Any = None


# ------------------------------------------------------------
#
# MetadataInspector
#
# ------------------------------------------------------------
class MetadataInspector(Gramplet):
    """
    Read-only inspector for the metadata of the active Media object.

    There is one tab for each place the metadata lives: File, Sidecar and Current Tree.
    """

    # TreeStore columns: the name as displayed (with its marker), value, raw
    # tag, tooltip (markup), full value, tag description, status, note, and the
    # plain name (used for the dialog and the headings path)
    (
        COL_LABEL,
        COL_VALUE,
        COL_TAG,
        COL_TIP,
        COL_FULL,
        COL_DESC,
        COL_STATUS,
        COL_NOTE,
        COL_NAME,
    ) = range(9)

    def init(self) -> None:
        """
        Build the display.
        """
        self.pages: dict[str, _Page] = {}
        self.notebook: Any = None
        self.note_label: Any = None
        self.count_label: Any = None
        self.legend_label: Any = None
        self._media_name = ""
        self._media_handle: MediaHandle | None = None
        # tree -> [width the columns were set for, width pending]
        self._widths: dict[Any, list[int]] = {}
        self._error_rgba: Any = None
        vbox = self._build_gui()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(vbox)
        vbox.show_all()
        for page in self.pages.values():  # show_all() un-hid the icons
            self._set_tab_state(page, False)

    def db_changed(self) -> None:
        """
        Connect the signals that refresh the display.
        """
        self.connect(self.dbstate.db, "media-add", self.update)
        self.connect(self.dbstate.db, "media-update", self.update)
        self.connect(self.dbstate.db, "media-delete", self.update)
        self.connect(self.dbstate.db, "media-rebuild", self.update)
        self.connect_signal("Media", self.update)

    def active_changed(self, handle: MediaHandle) -> None:
        """
        Refresh the display when the active media object changes.
        """
        self.update()

    # -- building -------------------------------------------------------------
    def _build_gui(self) -> Gtk.Box:
        """
        Build the note line, the notebook of tabs, and the count and legend lines.
        """
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        vbox.set_border_width(6)

        self.note_label = Gtk.Label(xalign=0)
        self.note_label.set_line_wrap(True)
        vbox.pack_start(self.note_label, False, False, 0)

        self.notebook = Gtk.Notebook()
        self.notebook.set_scrollable(True)
        for tab_id, name, icon, sections in _TABS:
            page = self._build_page(_Page(tab_id, name, icon, sections))
            self.pages[tab_id] = page
            self.notebook.append_page(page.box, page.tab_widget)
        vbox.pack_start(self.notebook, True, True, 0)

        self.count_label = Gtk.Label(xalign=0)
        vbox.pack_start(self.count_label, False, False, 0)
        self.legend_label = Gtk.Label(xalign=0)
        self.legend_label.set_line_wrap(True)
        vbox.pack_start(self.legend_label, False, False, 0)
        return vbox

    def _build_page(self, page: _Page) -> _Page:
        """
        Create the tab label, the message line and the tree of a page.
        """
        # tab label, as GrampsTab.build_label_widget(): icon, then the title
        hbox = Gtk.Box()
        page.tab_image = Gtk.Image.new_from_icon_name(page.icon, Gtk.IconSize.MENU)
        page.tab_label = Gtk.Label(label=page.name)
        hbox.pack_start(page.tab_image, True, True, 0)
        hbox.set_spacing(6)
        hbox.add(page.tab_label)
        hbox.show_all()
        page.tab_widget = hbox

        page.store = Gtk.TreeStore(*([str] * 9))
        page.tree = self._build_tree(page.store)
        page.scroll = Gtk.ScrolledWindow()
        page.scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        page.scroll.set_min_content_height(260)
        page.scroll.set_shadow_type(Gtk.ShadowType.IN)
        page.scroll.add(page.tree)

        page.message = Gtk.Label(xalign=0)
        page.message.set_line_wrap(True)
        page.message.set_margin_top(6)
        page.message.set_margin_start(6)
        page.message.set_no_show_all(True)

        page.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        page.box.pack_start(page.message, False, False, 0)
        page.box.pack_start(page.scroll, True, True, 0)
        return page

    def _build_tree(self, store: Gtk.TreeStore) -> Gtk.TreeView:
        """
        Return a Name, Value and Tag tree for *store*.
        """
        tree = Gtk.TreeView(model=store)
        tree.set_tooltip_column(self.COL_TIP)
        tree.set_enable_search(True)
        tree.set_search_column(self.COL_VALUE)
        tree.connect("button-press-event", self.cb_button_press)
        tree.connect("row-activated", self.cb_row_activated)
        tree.connect("size-allocate", self.cb_tree_size_allocate)
        for index, title in (
            (self.COL_LABEL, _("Name")),
            (self.COL_VALUE, _("Value")),
            (self.COL_TAG, _("Tag")),
        ):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
            column = Gtk.TreeViewColumn(title, renderer, text=index)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_resizable(True)
            column.set_min_width(30)
            if index != self.COL_TAG:
                column.set_cell_data_func(renderer, self.cb_cell_style)
            tree.append_column(column)
        return tree

    def _set_tab_state(self, page: _Page, has_data: bool) -> None:
        """
        Show the icon and a bold title on a tab that has data, as the tabs of Gramps do.
        """
        if has_data:
            page.tab_image.show()
            page.tab_label.set_markup(f"<b>{GLib.markup_escape_text(page.name)}</b>")
        else:
            page.tab_image.hide()
            page.tab_label.set_text(page.name)

    # -- callbacks ------------------------------------------------------------
    def cb_tree_size_allocate(
        self, tree: Gtk.TreeView, allocation: Gdk.Rectangle
    ) -> None:
        """
        Keep the columns at 40%, 40% and 20% of the width of the tree.
        """
        # The widths are set from an idle handler, not inside the allocation, and
        # only when the width of the tree changed, so that a column border dragged
        # by the user stays until the gramplet is resized.
        state = self._widths.setdefault(tree, [0, 0])
        width = allocation.width
        if width < 100 or width in state:
            return
        state[1] = width
        GLib.idle_add(self.cb_apply_column_widths, tree)

    def cb_apply_column_widths(self, tree: Gtk.TreeView) -> bool:
        """
        Set the column widths of *tree*; return False so that the idle handler runs
        once.
        """
        state = self._widths.setdefault(tree, [0, 0])
        width, state[1] = state[1], 0
        if not width or width == state[0]:
            return False
        state[0] = width
        columns = tree.get_columns()
        used = 0
        for column, share in zip(columns[:-1], _COLUMN_SHARES[:-1]):
            column_width = int(width * share)
            column.set_fixed_width(column_width)
            used += column_width
        columns[-1].set_fixed_width(max(width - used, 1))
        return False

    def _get_error_rgba(self, tree: Gtk.TreeView) -> Gdk.RGBA:
        """
        Return the error color of the theme, used for overridden values.
        """
        if self._error_rgba is None:
            found, rgba = tree.get_style_context().lookup_color("error_color")
            self._error_rgba = (
                rgba if found else Gdk.RGBA(red=0.8, green=0.0, blue=0.0, alpha=1.0)
            )
        return self._error_rgba

    def cb_cell_style(
        self,
        column: Gtk.TreeViewColumn,
        renderer: Gtk.CellRendererText,
        model: Gtk.TreeStore,
        tree_iter: Gtk.TreeIter,
        _data: None,
    ) -> None:
        """
        Show headings and preferred values in bold, and overridden values in the error
        color.
        """
        status = model.get_value(tree_iter, self.COL_STATUS)
        bold = model.iter_has_child(tree_iter) or status == "preferred"
        renderer.set_property("weight", 700 if bold else 400)
        if status == "overridden":
            renderer.set_property(
                "foreground-rgba", self._get_error_rgba(column.get_tree_view())
            )
        else:
            renderer.set_property("foreground-set", False)

    def cb_row_activated(
        self, tree: Gtk.TreeView, path: Gtk.TreePath, _column: Gtk.TreeViewColumn
    ) -> None:
        """
        Expand or collapse a heading, or open the detail dialog of an item.
        """
        store = tree.get_model()
        tree_iter = store.get_iter(path)
        if store.iter_has_child(tree_iter):
            if tree.row_expanded(path):
                tree.collapse_row(path)
            else:
                tree.expand_row(path, False)
            return

        crumbs: list[str] = []
        parent = store.iter_parent(tree_iter)
        while parent:
            crumbs.insert(0, store[parent][self.COL_NAME])
            parent = store.iter_parent(parent)

        row = store[path]
        location = " > ".join(crumbs)
        # one dialog per media object + item; asking again raises the open one
        digest = hashlib.md5(
            f"{location}|{row[self.COL_NAME]}".encode("utf-8")
        ).hexdigest()[:12]
        key = f"metadatainspector-{self._media_handle}-{digest}"
        try:
            MetadataDialog(
                self.uistate,
                [],
                key,
                row[self.COL_NAME],
                row[self.COL_FULL],
                location,
                row[self.COL_TAG],
                row[self.COL_DESC],
                media_name=self._media_name,
                note=row[self.COL_NOTE],
            )
        except WindowActiveError:
            pass  # already open; ManagedWindow has brought it to the front

    def cb_open_all_nodes(self, _item: Gtk.MenuItem, tree: Gtk.TreeView) -> None:
        """
        Expand every section and group of the tab.
        """
        tree.expand_all()

    def cb_close_all_nodes(self, _item: Gtk.MenuItem, tree: Gtk.TreeView) -> None:
        """
        Collapse every section and group of the tab.
        """
        tree.collapse_all()

    def cb_button_press(self, tree: Gtk.TreeView, event: Gdk.EventButton) -> bool:
        """
        Show the context menu on a right click.

        It offers to copy the value or the tag of an item, and to expand or collapse all
        nodes.
        """
        if event.button != 3:
            return False
        menu = Gtk.Menu()

        hit = tree.get_path_at_pos(int(event.x), int(event.y))
        if hit:
            tree.get_selection().select_path(hit[0])
            row = tree.get_model()[hit[0]]
            for label, text in (
                (_("Copy value"), row[self.COL_FULL]),
                (_("Copy tag name"), row[self.COL_TAG]),
            ):
                if text:
                    item = Gtk.MenuItem(label=label)
                    item.connect("activate", self.cb_copy, text)
                    menu.append(item)
            if menu.get_children():
                menu.append(Gtk.SeparatorMenuItem())

        for label, callback in (
            (_gramps_gettext("Expand all Nodes"), self.cb_open_all_nodes),
            (_gramps_gettext("Collapse all Nodes"), self.cb_close_all_nodes),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", callback, tree)
            menu.append(item)

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def cb_copy(self, _item: Gtk.MenuItem, text: str) -> None:
        """
        Put *text* on the clipboard.
        """
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)

    # -- display --------------------------------------------------------------
    def _populate(self, page: _Page, rows: list[Row]) -> list[str]:
        """
        Fill the tree of a tab with sections, groups and rows.

        :returns: The count text of each section that reports one.
        """
        page.store.clear()
        by_section: dict[str, list[Row]] = {}
        for row in rows:
            if row.section in page.sections:
                by_section.setdefault(row.section, []).append(row)
        counts = []
        marks = {"preferred": _MARK_PREFERRED, "overridden": _MARK_OVERRIDDEN}
        for section_id, section_name in _SECTIONS:
            section_rows = by_section.get(section_id)
            if not section_rows:
                continue
            section_iter = page.store.append(None, self._heading(section_name))
            groups = {}
            for row in section_rows:
                parent = section_iter
                if row.group:
                    if row.group not in groups:
                        groups[row.group] = page.store.append(
                            section_iter, self._heading(row.group)
                        )
                    parent = groups[row.group]
                mark = marks.get(row.status, "")
                tip = "\n".join(
                    GLib.markup_escape_text(part)
                    for part in (row.tag, row.desc, row.note)
                    if part
                )
                page.store.append(
                    parent,
                    [
                        f"{row.label} {mark}" if mark else row.label,
                        row.value,
                        row.tag,
                        tip,
                        row.full,
                        row.desc,
                        row.status,
                        row.note,
                        row.label,
                    ],
                )
            if section_id in _EMBEDDED or section_id == "refs":
                counts.append(f"{section_name}: {len(section_rows)}")
        # all section and group headings start expanded
        page.tree.expand_all()
        return counts

    @staticmethod
    def _heading(name: str) -> list[str]:
        """
        Return the store row for a section or group heading.
        """
        return [name, "", "", "", "", "", "", "", name]

    @staticmethod
    def _empty_message(page: _Page, result: Collected) -> str:
        """
        Return the text for a tab with nothing to list, or "".
        """
        sections = {row.section for row in result.rows}
        if page.tab_id == "sidecar":
            if "xmp_sidecar" in sections:
                return ""
            if "sidecar_file" in sections:
                return _("The XMP sidecar has no readable metadata.")
            return _("No XMP sidecar found. Looked for: %s") % ", ".join(
                result.sidecar_names
            )
        if any(section in sections for section in page.sections):
            return ""
        return {
            "file": _("The file is not available."),
            "gramps": _(
                "Nothing is recorded in the current tree for this media object."
            ),
        }.get(page.tab_id, "")

    def _show_result(self, result: Collected) -> None:
        """
        Fill every tab from the collected metadata.
        """
        counts = []
        for tab_id, page in self.pages.items():
            counts += self._populate(page, result.rows)
            self._set_tab_state(page, result.has_data[tab_id])
            message = self._empty_message(page, result)
            page.message.set_text(message)
            page.message.set_visible(bool(message))
            page.scroll.set_visible(not message or bool(page.store.get_iter_first()))
        self.count_label.set_text("   ".join(counts))
        if any(row.status for row in result.rows):
            self.legend_label.set_text(
                f"{_MARK_PREFERRED} {_('value in use where sources differ')}     "
                f"{_MARK_OVERRIDDEN} {_('overridden by another source')}"
            )
        else:
            self.legend_label.set_text("")
        self.note_label.set_text("\n".join(result.notes))

    def _clear(self) -> None:
        """
        Empty every tab.
        """
        for page in self.pages.values():
            page.store.clear()
            page.message.set_visible(False)
            page.scroll.set_visible(True)
            self._set_tab_state(page, False)
        self.note_label.set_text("")
        self.count_label.set_text("")
        self.legend_label.set_text("")

    def main(self) -> None:
        """
        Show the metadata of the active media object.
        """
        self._clear()
        self.set_has_data(False)
        self._media_name = ""
        self._media_handle = None

        handle = self.get_active("Media")
        if not handle:
            self.note_label.set_text(_("Select a media object to view its metadata."))
            return
        media = self.dbstate.db.get_media_from_handle(handle)
        if media is None:
            return
        # the Media object's name is its Title; fall back to the file name
        self._media_name = media.get_description() or os.path.basename(media.get_path())
        self._media_handle = handle

        result = collect_metadata(self.dbstate.db, media)
        self._show_result(result)
        # the gramplet's own tab in the bar is highlighted for real metadata
        # (embedded or in a sidecar), not merely because there is a file
        self.set_has_data(any(row.section in _EMBEDDED for row in result.rows))

    def update_has_data(self) -> None:
        """
        Keep the highlight of the gramplet tab correct while the gramplet is hidden.
        """
        handle = self.get_active("Media")
        if handle:
            media = self.dbstate.db.get_media_from_handle(handle)
            self.set_has_data(self.get_has_data(media))
        else:
            self.set_has_data(False)

    def get_has_data(self, media: Media | None) -> bool:
        """
        Return True if the media file or its sidecar contains metadata.
        """
        if media is None:
            return False
        result = collect_metadata(self.dbstate.db, media)
        return any(row.section in _EMBEDDED for row in result.rows)
