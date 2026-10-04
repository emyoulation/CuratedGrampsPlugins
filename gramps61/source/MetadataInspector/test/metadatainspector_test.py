#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Claude AI (wish coding by Brian McCullough)
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
Unit tests for the Metadata Inspector gramplet.

They run without a display and without GExiv2.  GTK namespaces that are not
installed are replaced by mocks, the ManagedWindow of Gramps is replaced by a
small registry, and GExiv2 is faked.  The fake GExiv2 behaves like the older
releases (which repeat a plain XMP value once for each character when asked for
several values) or like the current ones, and the tests that read XMP run
against both.  The date logic runs against the real Gramps Date class and the
real Gramps preferences.
"""

from __future__ import annotations

# -------------------------------------------------------------------------
#
# Standard Python modules
#
# -------------------------------------------------------------------------
import datetime
import functools
import importlib
import os
import re
import shutil
import sys
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any
from unittest import mock

# -------------------------------------------------------------------------
#
# GTK/Gnome modules
#
# -------------------------------------------------------------------------
import gi
from gi import repository as gi_repository
from gi.repository import GLib

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.config import config
from gramps.gen.errors import WindowActiveError
from gramps.gen.lib import Date
from gramps.gen.utils.place import conv_lat_lon

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SAMPLE_XMP = os.path.join(DATA, "sample.xmp")


# -------------------------------------------------------------------------
#
# FakeManagedWindow
#
# -------------------------------------------------------------------------
class FakeManagedWindow:
    """
    Stand-in for the ManagedWindow of Gramps: a registry of open windows.
    """

    registry: dict[Any, FakeManagedWindow] = {}
    presented: int
    closed: int

    def __init__(self, uistate: Any, track: list[Any], obj: Any, modal: bool = False):
        """
        Register the window, or raise WindowActiveError if it is already open.
        """
        key = self.build_window_key(obj)
        menu_label, submenu_label = self.build_menu_names(obj)
        if key in self.registry:
            self.registry[key].presented += 1
            raise WindowActiveError("already active")
        self.window_id = key
        self.menu_label = menu_label
        self.submenu_label = submenu_label
        self.uistate = uistate
        self.track = track
        self.modal = modal
        self.presented = 0
        self.closed = 0
        self.shown = False
        self.window: Any = None
        self.title_text = ""
        self.registry[key] = self

    def set_window(self, window: Any, _title: Any, text: str) -> None:
        """
        Remember the window and its title, and connect its delete event.
        """
        self.window = window
        self.title_text = text
        window.connect("delete-event", self.close)

    def show(self) -> None:
        """
        Record that the window was shown.
        """
        self.shown = True

    def close(self, *_args: Any) -> None:
        """
        Remove the window from the registry.
        """
        self.closed += 1
        self.registry.pop(self.window_id, None)

    def build_window_key(self, obj: Any) -> Any:
        """
        Return the default key.
        """
        return id(obj)

    def build_menu_names(self, _obj: Any) -> tuple[str, str | None]:
        """
        Return the default menu labels.
        """
        return ("Undefined Menu", "Undefined Submenu")


def _prepare_environment() -> None:
    """
    Make the module importable without a display, GTK windows or a database.
    """
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for name, version in (("Gtk", "3.0"), ("Gdk", "3.0"), ("GdkPixbuf", "2.0")):
        try:
            gi.require_version(name, version)
            importlib.import_module(f"gi.repository.{name}")
        except (ImportError, ValueError):
            stub = mock.MagicMock(name=name)
            sys.modules[f"gi.repository.{name}"] = stub
            setattr(gi_repository, name, stub)
    window_module = types.ModuleType("gramps.gui.managedwindow")
    setattr(window_module, "ManagedWindow", FakeManagedWindow)
    sys.modules["gramps.gui.managedwindow"] = window_module


_prepare_environment()
mi: Any = importlib.import_module("metadatainspector")

# What the fake GExiv2 knows about the XMP properties used in the tests;
# Exiv2 answers "XmpText" for anything it has no entry for.
XMP_TYPES = {
    "Xmp.dc.title": "LangAlt",
    "Xmp.dc.description": "LangAlt",
    "Xmp.dc.rights": "LangAlt",
    "Xmp.xmpRights.UsageTerms": "LangAlt",
    "Xmp.dc.creator": "XmpSeq",
    "Xmp.digiKam.TagsList": "XmpSeq",
    "Xmp.dc.subject": "XmpBag",
    "Xmp.iptcExt.PersonInImage": "XmpBag",
    "Xmp.MicrosoftPhoto.LastKeywordXMP": "XmpBag",
}
LANG_SPLIT = re.compile(r'(?:^|,\s*)lang="([^"]*)"\s*')
ARRAY_TYPES = ("XmpBag", "XmpSeq", "XmpAlt")


def lang_alternatives(raw: str) -> list[tuple[str, str]]:
    """
    Split Exiv2's string form of a language alternative into (lang, text).
    """
    parts = LANG_SPLIT.split(raw or "")
    return list(zip(parts[1::2], [text.strip() for text in parts[2::2]]))


# -------------------------------------------------------------------------
#
# FakeExiv
#
# -------------------------------------------------------------------------
class FakeExiv:
    """
    Fake GExiv2.Metadata whose content comes from a profile for each path.
    """

    PROFILES: dict[str, dict[str, Any]] = {}
    old = True  # behave like the older GExiv2 releases

    def __init__(self) -> None:
        """
        Start with an empty profile.
        """
        self.profile: dict[str, Any] = exiv_profile()

    def open_path(self, path: str) -> None:
        """
        Load the profile of *path*; an unknown file cannot be read.
        """
        if path in self.PROFILES:
            self.profile = self.PROFILES[path]
        else:
            raise GLib.Error(f"unreadable {path}")

    def has_tag(self, key: str) -> bool:
        """
        Return True if the tag exists.
        """
        return key in self.profile["tags"] or key in self.profile["multi"]

    def get_tag_string(self, key: str) -> str:
        """
        Return the raw string of a tag.
        """
        return str(self.profile["tags"].get(key, ""))

    def get_tag_interpreted_string(self, key: str) -> str:
        """
        Return the interpreted string of a tag (the same as the raw one here).
        """
        return self.get_tag_string(key)

    def get_tag_type(self, key: str) -> str:
        """
        Return the value type that Exiv2 registers for the tag.
        """
        return XMP_TYPES.get(key, "XmpText") if key.startswith("Xmp.") else "Ascii"

    def get_tag_multiple(self, key: str) -> list[str]:
        """
        Return the values of a tag as GExiv2 does, including the older bug.
        """
        raw = self.get_tag_string(key)
        items = list(self.profile["multi"].get(key, []))
        if not key.startswith("Xmp."):
            return items or ([raw] if raw else [])
        kind = self.get_tag_type(key)
        if kind in ARRAY_TYPES:
            return items
        if kind == "LangAlt":
            alternatives = lang_alternatives(raw)
            if self.old:
                defaults = [text for lang, text in alternatives if lang == "x-default"]
                default = (defaults or [alternatives[0][1] if alternatives else ""])[0]
                return [default] * len(alternatives)
            return [f'lang="{lang}" {text}' for lang, text in alternatives]
        return [raw] * len(raw) if self.old else [raw]

    def get_tag_description(self, key: str) -> str:
        """
        Return a description of the tag.
        """
        return f"description of {key}"

    def get_tag_label(self, key: str) -> str | None:
        """
        Return the label of the tag; None for the paths into XMP structures.
        """
        return None if "/" in key else key.split(".")[-1]

    def get_pixel_width(self) -> int:
        """
        Return the width of the image.
        """
        return int(self.profile["width"])

    def get_pixel_height(self) -> int:
        """
        Return the height of the image.
        """
        return int(self.profile["height"])

    def get_exif_tags(self) -> list[str]:
        """
        Return the Exif tags.
        """
        return list(self.profile["exif"])

    def get_iptc_tags(self) -> list[str]:
        """
        Return the IPTC tags.
        """
        return list(self.profile["iptc"])

    def get_xmp_tags(self) -> list[str]:
        """
        Return the XMP tags.
        """
        return list(self.profile["xmp"])


def exiv_profile(
    tags: dict[str, str] | None = None,
    multi: dict[str, list[str]] | None = None,
    width: int = 0,
    height: int = 0,
) -> dict[str, Any]:
    """
    Return a profile for FakeExiv; the tag lists follow from the tag prefixes.
    """
    tags = dict(tags or {})
    multi = dict(multi or {})
    keys = list(tags) + [key for key in multi if key not in tags]
    return {
        "tags": tags,
        "multi": multi,
        "width": width,
        "height": height,
        "exif": [key for key in keys if key.startswith("Exif.")],
        "iptc": [key for key in keys if key.startswith("Iptc.")],
        "xmp": [key for key in keys if key.startswith("Xmp.")],
    }


def sidecar_profile(path: str) -> dict[str, Any]:
    """
    Build the profile that Exiv2 would give for an XMP sidecar file.
    """
    namespaces = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "dc": "http://purl.org/dc/elements/1.1/",
        "ext": "http://iptc.org/std/Iptc4xmpExt/2008-02-29/",
        "mwg": "http://www.metadataworkinggroup.com/schemas/regions/",
        "dim": "http://www.metadataworkinggroup.com/schemas/dim/",
        "area": "http://www.metadataworkinggroup.com/schemas/area/",
    }
    with open(path, encoding="utf-8") as handle:
        xml = handle.read()
    start = xml.index("<x:xmpmeta")
    end = xml.index("</x:xmpmeta>") + len("</x:xmpmeta>")
    desc = ET.fromstring(xml[start:end]).find(".//rdf:Description", namespaces)
    assert desc is not None
    title = desc.find("dc:title/rdf:Alt/rdf:li", namespaces)
    assert title is not None
    tags = {"Xmp.dc.title": f'lang="x-default" {title.text}'}
    multi = {
        "Xmp.dc.creator": [
            li.text or ""
            for li in desc.findall("dc:creator/rdf:Seq/rdf:li", namespaces)
        ],
        "Xmp.iptcExt.PersonInImage": [
            li.text or ""
            for li in desc.findall("ext:PersonInImage/rdf:Bag/rdf:li", namespaces)
        ],
    }
    for key, items in multi.items():
        tags[key] = items[0]
    regions = "Xmp.mwg-rs.Regions"
    for key in (
        regions,
        regions + "/mwg-rs:AppliedToDimensions",
        regions + "/mwg-rs:RegionList",
    ):
        tags[key] = ""  # containers carry no value
    applied = desc.find("mwg:Regions/mwg:AppliedToDimensions", namespaces)
    assert applied is not None
    for attr in ("w", "h", "unit"):
        tags[f"{regions}/mwg-rs:AppliedToDimensions/stDim:{attr}"] = (
            applied.get("{%s}%s" % (namespaces["dim"], attr)) or ""
        )
    for index, item in enumerate(
        desc.findall("mwg:Regions/mwg:RegionList/rdf:Bag/rdf:li", namespaces), 1
    ):
        base = f"{regions}/mwg-rs:RegionList[{index}]"
        tags[base] = ""
        tags[base + "/mwg-rs:Area"] = ""
        for field in ("Name", "Type"):
            node = item.find(f"mwg:{field}", namespaces)
            assert node is not None
            tags[f"{base}/mwg-rs:{field}"] = node.text or ""
        area = item.find("mwg:Area", namespaces)
        assert area is not None
        for attr in ("x", "y", "w", "h", "unit"):
            tags[f"{base}/mwg-rs:Area/stArea:{attr}"] = (
                area.get("{%s}%s" % (namespaces["area"], attr)) or ""
            )
    return exiv_profile(tags, multi)


# -------------------------------------------------------------------------
#
# Fakes for the media object, the database and the system
#
# -------------------------------------------------------------------------
class FakeDisplayer:
    """
    Date displayer with a fixed, locale independent format.
    """

    prefixes = {
        Date.MOD_ABOUT: "about ",
        Date.MOD_BEFORE: "before ",
        Date.MOD_AFTER: "after ",
    }

    def display(self, date: Date | None) -> str:
        """
        Show a date as year-month-day, leaving out what is zero.
        """
        if date is None or date.is_empty():
            return ""
        if date.get_modifier() == Date.MOD_TEXTONLY:
            return str(date.get_text())
        parts = (date.get_year(), date.get_month(), date.get_day())
        prefix = self.prefixes.get(date.get_modifier(), "")
        return prefix + "-".join(str(part) for part in parts if part)


def make_date(
    year: int, month: int = 0, day: int = 0, modifier: int = 0, calendar: int = 0
) -> Date:
    """
    Return a real Gramps Date.
    """
    date = Date()
    if year or month or day:
        date.set(modifier=modifier, calendar=calendar, value=(day, month, year, False))
    return date


def range_date(first: int, last: int) -> Date:
    """
    Return a Gramps date range from 1 January of *first* to 31 December of *last*.
    """
    date = Date()
    date.set(modifier=Date.MOD_RANGE, value=(1, 1, first, False, 31, 12, last, False))
    return date


def quality_date(year: int, quality: int) -> Date:
    """
    Return a year with a quality, such as estimated.
    """
    date = Date()
    date.set(quality=quality, value=(0, 0, year, False))
    return date


def text_date(text: str) -> Date:
    """
    Return a text-only date.
    """
    date = Date()
    date.set(modifier=Date.MOD_TEXTONLY, text=text)
    return date


class FakeMedia:
    """
    Stand-in for a Gramps Media object.
    """

    def __init__(
        self,
        path: str,
        mime: str = "image/jpeg",
        desc: str | None = None,
        date: Date | None = None,
        **lists: list[Any],
    ) -> None:
        """
        Create a media object; the Title defaults to the file name, as in Gramps.
        """
        self.path = path
        self.mime = mime
        self.date = date
        self.desc = (
            os.path.splitext(os.path.basename(path))[0] if desc is None else desc
        )
        self.lists = lists

    def get_path(self) -> str:
        """Return the stored path."""
        return self.path

    def get_mime_type(self) -> str:
        """Return the MIME type."""
        return self.mime

    def get_handle(self) -> str:
        """Return the handle."""
        return "HM"

    def get_gramps_id(self) -> str:
        """Return the Gramps ID."""
        return "O0001"

    def get_description(self) -> str:
        """Return the Title."""
        return self.desc

    def get_date_object(self) -> Date | None:
        """Return the date."""
        return self.date

    def get_attribute_list(self) -> list[Any]:
        """Return the attributes."""
        return self.lists.get("attrs", [])

    def get_note_list(self) -> list[Any]:
        """Return the note handles."""
        return self.lists.get("notes", [])

    def get_tag_list(self) -> list[Any]:
        """Return the tag handles."""
        return self.lists.get("tags", [])

    def get_citation_list(self) -> list[Any]:
        """Return the citation handles."""
        return self.lists.get("cites", [])


class FakeMediaRef:
    """
    A media reference with an optional region.
    """

    def __init__(self, handle: str, rect: tuple[int, int, int, int] | None) -> None:
        """Remember the media handle and the region."""
        self.handle = handle
        self.rect = rect

    def get_reference_handle(self) -> str:
        """Return the handle of the media object."""
        return self.handle

    def get_rectangle(self) -> tuple[int, int, int, int] | None:
        """Return the region."""
        return self.rect


class FakeHolder:
    """
    A person, family or event that holds media references.
    """

    def __init__(
        self, gid: str, name: str, refs: list[FakeMediaRef], desc: str = ""
    ) -> None:
        """Remember what the holder shows."""
        self.gid = gid
        self.name = name
        self.refs = refs
        self.desc = desc

    def get_gramps_id(self) -> str:
        """Return the Gramps ID."""
        return self.gid

    def get_media_list(self) -> list[FakeMediaRef]:
        """Return the media references."""
        return self.refs

    def get_description(self) -> str:
        """Return the description (events)."""
        return self.desc

    def get_type(self) -> str:
        """Return the type (events)."""
        return "Birth"


class FakeDb:
    """
    Database stand-in with back-references and a few getters.
    """

    def __init__(self, links: list[tuple[str, str]], holders: dict[str, Any]) -> None:
        """Remember the back-references and the objects."""
        self.links = links
        self.holders = holders

    def find_backlink_handles(self, handle: str, classes: list[str]) -> Any:
        """Return the back-references of the media object."""
        assert handle == "HM" and "Person" in classes
        return iter(self.links)

    def _get(self, handle: str) -> Any:
        """Return the object with that handle, or None."""
        return self.holders.get(handle)

    get_person_from_handle = _get
    get_family_from_handle = _get
    get_event_from_handle = _get
    get_place_from_handle = _get
    get_source_from_handle = _get
    get_citation_from_handle = _get
    get_note_from_handle = _get
    get_tag_from_handle = _get


class FakeGioInfo:
    """
    File information from the fake Gio.
    """

    def __init__(self, created: int | None) -> None:
        """Remember the birth time."""
        self.created = created

    def has_attribute(self, _name: str) -> bool:
        """Return True if the file system records a birth time."""
        return self.created is not None

    def get_attribute_uint64(self, _name: str) -> int | None:
        """Return the birth time in seconds."""
        return self.created


class FakeGio:
    """
    Fake of the Gio module, enough for the creation time of a file.
    """

    created: int | None = None
    raising = False
    FileQueryInfoFlags = types.SimpleNamespace(NONE=0)

    class File:
        """
        Fake Gio.File.
        """

        @staticmethod
        def new_for_path(_path: str) -> FakeGio.File:
            """Return a file object."""
            return FakeGio.File()

        def query_info(
            self, _attrs: str, _flags: int, _cancellable: Any
        ) -> FakeGioInfo:
            """Return the information, or raise like a failing file system."""
            if FakeGio.raising:
                raise GLib.Error("no time::created")
            return FakeGioInfo(FakeGio.created)


class FakeGdkPixbuf:
    """
    Fake of GdkPixbuf: the sizes come from a dictionary of paths.
    """

    sizes: dict[str, tuple[int, int] | None] = {}

    class Pixbuf:
        """
        Fake GdkPixbuf.Pixbuf.
        """

        @staticmethod
        def get_file_info(path: str) -> tuple[str, int, int]:
            """Return the format and size, or a zero size if unreadable."""
            size = FakeGdkPixbuf.sizes.get(path, (500, 347))
            return ("jpeg",) + (size if size else (0, 0))


# -------------------------------------------------------------------------
#
# InspectorTestCase
#
# -------------------------------------------------------------------------
class InspectorTestCase(unittest.TestCase):
    """
    Base class: patches the module with fakes and offers helpers.
    """

    def setUp(self) -> None:
        """
        Patch the module with fakes; everything is restored afterwards.
        """
        FakeExiv.PROFILES = {}
        FakeExiv.old = True
        FakeGio.created = None
        FakeGio.raising = False
        FakeGdkPixbuf.sizes = {}
        FakeManagedWindow.registry.clear()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        saved = {
            key: config.get(f"behavior.date-{key}-range")
            for key in ("about", "before", "after")
        }
        for key, value in saved.items():
            self.addCleanup(config.set, f"behavior.date-{key}-range", value)
        patches: dict[str, Any] = {
            "GExiv2": types.SimpleNamespace(Metadata=FakeExiv),
            "_dd": FakeDisplayer(),
            "media_path_full": lambda _db, path: path,
            "get_description": lambda mime: f"description of {mime}",
            "name_displayer": types.SimpleNamespace(display=lambda obj: obj.name),
            "place_displayer": types.SimpleNamespace(display=lambda _db, obj: obj.name),
            "family_name": lambda family, _db: family.name,
            "PdfReader": None,
            "mutagen": None,
            "GdkPixbuf": FakeGdkPixbuf,
            "Gio": FakeGio,
        }
        for name, value in patches.items():
            patcher = mock.patch.object(mi, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def make_file(self, name: str, content: bytes = b"x") -> str:
        """
        Create a file in the temporary folder and return its path.
        """
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def make_image(
        self,
        file_tags: dict[str, str] | None = None,
        side_tags: dict[str, str] | None = None,
        size: tuple[int, int] = (516, 640),
        sidecar: bool = True,
    ) -> str:
        """
        Create pic.jpg, and pic.xmp unless *sidecar* is False; return the image path.
        """
        image = self.make_file("pic.jpg")
        FakeExiv.PROFILES[image] = exiv_profile(file_tags, None, *size)
        FakeGdkPixbuf.sizes[image] = size
        if sidecar:
            side = self.make_file("pic.xmp")
            FakeExiv.PROFILES[side] = exiv_profile(side_tags)
        return image

    @staticmethod
    def sections(rows: list[Any]) -> dict[str, list[Any]]:
        """
        Group rows by section.
        """
        grouped: dict[str, list[Any]] = {}
        for row in rows:
            grouped.setdefault(row.section, []).append(row)
        return grouped

    @staticmethod
    def find(rows: list[Any], section: str, key: str) -> Any:
        """
        Return the row of *section* whose tag or label is *key*.
        """
        found = [r for r in rows if r.section == section and key in (r.tag, r.label)]
        assert found, f"no {key} row in {section}"
        return found[0]

    @staticmethod
    def statuses(rows: list[Any]) -> dict[tuple[str, str], str]:
        """
        Return the marked rows as {(section, tag or label): status}.
        """
        return {(r.section, r.tag or r.label): r.status for r in rows if r.status}


def both_gexiv2(test: Callable[[Any], None]) -> Callable[[Any], None]:
    """
    Run a test against the older and the current behavior of GExiv2.
    """

    @functools.wraps(test)
    def wrapper(self: Any) -> None:
        """Run the test once for each behavior."""
        for old in (True, False):
            with self.subTest(old_gexiv2=old):
                FakeExiv.old = old
                test(self)

    return wrapper


def collect(media: Any, db: Any = None) -> Any:
    """
    Run collect_metadata with the patched module.
    """
    return mi.collect_metadata(db, media)


# -------------------------------------------------------------------------
#
# FormattingTests
#
# -------------------------------------------------------------------------
class FormattingTests(InspectorTestCase):
    """
    Text, date and number formatting helpers.
    """

    def test_clean_makes_one_short_line(self) -> None:
        """Line breaks and runs of spaces collapse, and long text is shortened."""
        self.assertEqual(mi._clean("a\n  b"), "a b")
        self.assertEqual(mi._clean(None), "")
        self.assertEqual(len(mi._clean("x" * 1000)), mi._MAX_VALUE_LEN + 1)

    def test_row_keeps_the_full_value(self) -> None:
        """The display value is one short line; the full value is kept."""
        row = mi._row("exif", "Image", "Desc", "one\ntwo " + "x" * 400, "Exif.Tag", "d")
        self.assertTrue(row.full.startswith("one\ntwo"))
        self.assertNotIn("\n", row.value)
        self.assertLessEqual(len(row.value), mi._MAX_VALUE_LEN + 1)
        self.assertEqual((row.status, row.note), ("", ""))

    def test_row_caps_huge_values(self) -> None:
        """A huge value, such as a maker note, is capped for the dialog."""
        self.assertEqual(
            len(mi._row("exif", "", "m", "y" * 50000).full), mi._MAX_FULL_LEN + 1
        )

    def test_date_times_use_the_gramps_format(self) -> None:
        """Exif and ISO dates are shown in the Gramps date format."""
        cases = {
            "2019:05:04 12:30:59": "2019-5-4 12:30:59",
            "2005-03-02T10:00:00": "2005-3-2 10:00:00",
            "1931-06-01": "1931-6-1",
            "1897-03": "1897-3",
            "1897": "1897",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(mi._format_datetime_text(text), expected)

    def test_other_text_is_not_taken_for_a_date(self) -> None:
        """Text that is not a date, and impossible dates, are returned unchanged."""
        for text in ("hello", "1/125", "-5", "0000-00-00", "0000:00:00 00:00:00"):
            with self.subTest(text=text):
                self.assertEqual(mi._format_datetime_text(text), text)

    def test_pdf_dates(self) -> None:
        """PDF dates may be partial; the offset is ignored."""
        self.assertEqual(
            mi._format_pdf_date("D:20200102030405+0100"), "2020-1-2 03:04:05"
        )
        self.assertEqual(mi._format_pdf_date("D:1930"), "1930")
        self.assertEqual(mi._format_pdf_date("D:193006"), "1930-6")
        self.assertEqual(mi._format_pdf_date("not a date"), "not a date")

    def test_rationals(self) -> None:
        """Exif rationals become floats; bad ones become None."""
        self.assertEqual(mi._rational_to_float("200558/1000"), 200.558)
        self.assertEqual(mi._rational_to_float("5"), 5.0)
        self.assertIsNone(mi._rational_to_float("0/0"))
        self.assertIsNone(mi._rational_to_float("abc"))

    def test_degrees_minutes_seconds(self) -> None:
        """Degrees, minutes and seconds with a hemisphere become signed degrees."""
        self.assertAlmostEqual(mi._dms_to_decimal("38/1 30/1 0/1", "N"), 38.5)
        self.assertAlmostEqual(mi._dms_to_decimal("96/1 48/1 0/1", "W"), -96.8)
        self.assertAlmostEqual(
            mi._dms_to_decimal("33/1 51/1 2442/100", "S"), -33.856783, places=6
        )
        self.assertAlmostEqual(mi._dms_to_decimal("38/1", "N"), 38.0)
        self.assertIsNone(mi._dms_to_decimal("x/1 0/1 0/1", "N"))
        self.assertIsNone(mi._dms_to_decimal("", "N"))

    def test_durations(self) -> None:
        """Seconds become H:MM:SS, or M:SS under an hour."""
        self.assertEqual(mi._format_duration(3725), "1:02:05")
        self.assertEqual(mi._format_duration(65), "1:05")

    def test_language_alternatives(self) -> None:
        """The default language comes first, the others are labeled."""
        self.assertEqual(mi._lang_alt_text('lang="x-default" Hello'), "Hello")
        self.assertEqual(
            mi._lang_alt_text('lang="x-default" Hello, lang="de" Hallo'),
            "Hello; Hallo (de)",
        )
        self.assertEqual(
            mi._lang_alt_text('lang="de" Hallo, lang="x-default" Hello'),
            "Hello; Hallo (de)",
        )
        self.assertEqual(mi._lang_alt_text('lang="en" Hello'), "Hello (en)")
        self.assertEqual(
            mi._lang_alt_text('lang="x-default" Hello, world, lang="de" Hallo, Welt'),
            "Hello, world; Hallo, Welt (de)",
        )
        self.assertEqual(mi._lang_alt_text("Plain text"), "Plain text")
        self.assertEqual(mi._lang_alt_text(""), "")

    def test_structure_paths(self) -> None:
        """A path into an XMP structure becomes readable names."""
        self.assertEqual(
            mi._struct_label("Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name"),
            "Regions > RegionList[1] > Name",
        )
        self.assertEqual(
            mi._struct_label(
                "Xmp.mwg-rs.Regions/mwg-rs:RegionList[2]/mwg-rs:Area/stArea:x"
            ),
            "Regions > RegionList[2] > Area > x",
        )

    def test_comparison_text_ignores_case_and_spacing(self) -> None:
        """Whitespace and case are not differences."""
        self.assertEqual(
            mi._norm_text("  Grandpa   AT the Farm "), "grandpa at the farm"
        )


# -------------------------------------------------------------------------
#
# DateComparisonTests
#
# -------------------------------------------------------------------------
class DateComparisonTests(InspectorTestCase):
    """
    Comparison of dates with Date.match() and the Gramps preferences.
    """

    @staticmethod
    def parts(key: Any) -> Any:
        """Return (kind, year, month, day) of a ("gdate", Date) key."""
        return (
            None
            if key is None
            else (key[0], key[1].get_year(), key[1].get_month(), key[1].get_day())
        )

    @staticmethod
    def key(year: int, month: int = 0, day: int = 0) -> Any:
        """Return the key of a plain date."""
        return ("gdate", Date(year, month, day))

    def test_keys_from_text(self) -> None:
        """Exif, ISO and partial dates become keys; unusable text does not."""
        self.assertEqual(
            self.parts(mi._date_key_from_text("1931:06:01 00:00:00")),
            ("gdate", 1931, 6, 1),
        )
        self.assertEqual(
            self.parts(mi._date_key_from_text("2005-03-02T10:00:00")),
            ("gdate", 2005, 3, 2),
        )
        self.assertEqual(
            self.parts(mi._date_key_from_text("1897")), ("gdate", 1897, 0, 0)
        )
        self.assertIsNone(mi._date_key_from_text("0000:00:00 00:00:00"))
        self.assertIsNone(mi._date_key_from_text("sometime in spring"))

    def test_keys_from_gramps_dates(self) -> None:
        """Only an empty or text-only Gramps date cannot be compared."""
        comparable = [
            make_date(1897, 3, 2),
            make_date(1897),
            make_date(1897, modifier=Date.MOD_ABOUT),
            range_date(1895, 1900),
            make_date(1897, 1, 1, calendar=Date.CAL_JULIAN),
            quality_date(1897, Date.QUAL_ESTIMATED),
        ]
        for date in comparable:
            with self.subTest(date=str(date)):
                self.assertIsNotNone(mi._gramps_date_key(date))
        for other in (text_date("the spring of the flood"), make_date(0), None):
            with self.subTest(date=str(other)):
                self.assertIsNone(mi._gramps_date_key(other))

    def test_partial_dates_agree_when_they_overlap(self) -> None:
        """A year agrees with a date in that year; a month with a day in it."""
        self.assertTrue(mi._same(self.key(1897), self.key(1897, 3, 2)))
        self.assertTrue(mi._same(self.key(1897, 3, 2), self.key(1897)))
        self.assertFalse(mi._same(self.key(1897), self.key(1898, 3, 2)))
        self.assertFalse(mi._same(self.key(1897, 3), self.key(1897, 4, 2)))
        self.assertFalse(mi._same(self.key(1897, 3, 2), self.key(1897, 3, 5)))

    def test_other_keys(self) -> None:
        """Text and size keys must be equal; a date never equals text."""
        self.assertTrue(mi._same(("text", "a b"), ("text", "a b")))
        self.assertFalse(mi._same(("text", "a"), ("text", "b")))
        self.assertFalse(mi._same(("dims", 516, 640), ("dims", 514, 640)))
        self.assertFalse(mi._same(self.key(1897), ("text", "1897")))

    def test_about_dates_follow_the_preferences(self) -> None:
        """An approximate date is widened by the range set in the Gramps preferences."""
        about = ("gdate", make_date(1897, modifier=Date.MOD_ABOUT))
        config.set("behavior.date-about-range", 50)
        self.assertTrue(mi._same(about, self.key(1931, 6, 1)))
        self.assertFalse(mi._same(about, self.key(2005, 3, 2)))
        config.set("behavior.date-about-range", 10)
        self.assertFalse(mi._same(about, self.key(1931, 6, 1)))
        self.assertFalse(mi._same(self.key(1931, 6, 1), about))
        self.assertTrue(mi._same(about, self.key(1902, 1, 1)))

    def test_before_and_after_dates(self) -> None:
        """Before and after dates compare on the side they point to."""
        config.set("behavior.date-before-range", 50)
        config.set("behavior.date-after-range", 50)
        before = ("gdate", make_date(1900, modifier=Date.MOD_BEFORE))
        after = ("gdate", make_date(1900, modifier=Date.MOD_AFTER))
        self.assertTrue(mi._same(before, self.key(1880, 1, 1)))
        self.assertFalse(mi._same(before, self.key(1931, 6, 1)))
        self.assertFalse(mi._same(before, self.key(1900, 6, 1)))
        self.assertTrue(mi._same(after, self.key(1931, 6, 1)))
        self.assertFalse(mi._same(after, self.key(1850, 1, 1)))

    def test_ranges_estimates_and_calendars(self) -> None:
        """Date ranges, estimated dates and other calendars compare as Gramps does."""
        config.set("behavior.date-about-range", 50)
        span = ("gdate", range_date(1895, 1900))
        self.assertTrue(mi._same(span, self.key(1897, 3, 2)))
        self.assertFalse(mi._same(span, self.key(1931, 6, 1)))
        estimated = ("gdate", quality_date(1897, Date.QUAL_ESTIMATED))
        self.assertTrue(mi._same(estimated, self.key(1931, 1, 1)))
        self.assertFalse(mi._same(estimated, self.key(2005, 1, 1)))
        julian = ("gdate", make_date(1897, 1, 1, calendar=Date.CAL_JULIAN))
        self.assertTrue(mi._same(julian, self.key(1897, 1, 13)))
        self.assertFalse(mi._same(julian, self.key(1897, 1, 1)))

    def test_specificity(self) -> None:
        """More date parts mean more precision; approximate dates count for nothing."""
        self.assertEqual(mi._specificity(self.key(1897, 3, 2)), 3)
        self.assertEqual(mi._specificity(self.key(1897, 3)), 2)
        self.assertEqual(mi._specificity(self.key(1897)), 1)
        self.assertEqual(
            mi._specificity(("gdate", make_date(1897, modifier=Date.MOD_ABOUT))), 0
        )
        self.assertEqual(mi._specificity(("gdate", range_date(1895, 1900))), 0)
        self.assertEqual(mi._specificity(("text", "x")), 0)


# -------------------------------------------------------------------------
#
# RegionTextTests
#
# -------------------------------------------------------------------------
class RegionTextTests(InspectorTestCase):
    """
    The text shown for the region of a media reference.
    """

    def test_region_with_a_known_image_size(self) -> None:
        """The tree shows percentages; the dialog adds the pixel rectangle."""
        short, full = mi._region_texts((15, 27, 25, 43), (500, 347))
        self.assertEqual(short, "15%, 27% \u2013 25%, 43%")
        self.assertIn("Left 15%, Top 27%, Right 25%, Bottom 43%", full)
        self.assertIn("About 75,94 to 125,149 pixels in a 500 x 347 pixel image", full)

    def test_region_without_an_image_size(self) -> None:
        """Without a size there is no pixel line."""
        self.assertNotIn("pixels", mi._region_texts((15, 27, 25, 43), None)[1])

    def test_no_region_means_the_whole_image(self) -> None:
        """A missing or empty region selects the whole image."""
        for rect in (None, (0, 0, 0, 0)):
            with self.subTest(rect=rect):
                self.assertEqual(
                    mi._region_texts(rect, None),
                    ("Whole image (no region selected)",) * 2,
                )


def position_text(latitude: str, longitude: str) -> str:
    """
    Return a position as Gramps itself formats it in degrees, minutes and seconds.
    """
    converted = conv_lat_lon(latitude, longitude, "DEG")
    assert isinstance(converted, tuple)
    return f"{converted[0]}, {converted[1]}"


def record_labels(captions: list[str]) -> Callable[..., Any]:
    """
    Return a Gtk.Label replacement that records the text of each label.
    """

    def make_label(*_args: Any, **kwargs: Any) -> Any:
        """Record the label text and return a mock widget."""
        captions.append(str(kwargs.get("label")))
        return mock.MagicMock()

    return make_label


def fake_meta(
    tags: dict[str, str] | None = None, multi: dict[str, list[str]] | None = None
) -> FakeExiv:
    """
    Return a fake GExiv2.Metadata holding the given tags.
    """
    meta = FakeExiv()
    meta.profile = exiv_profile(tags, multi)
    return meta


WIDTH_TAG = "Xmp.mwg-rs.Regions/mwg-rs:AppliedToDimensions/stDim:w"
NAME_TAG = "Xmp.mwg-rs.Regions/mwg-rs:RegionList[2]/mwg-rs:Name"
RECTANGLE_TAG = "Xmp.MP.RegionInfo/MPRI:Regions[2]/MPReg:Rectangle"


# -------------------------------------------------------------------------
#
# TagReadingTests
#
# -------------------------------------------------------------------------
class TagReadingTests(InspectorTestCase):
    """
    Reading tag values: the same result on older and current GExiv2.
    """

    def test_the_fake_repeats_values_like_older_releases(self) -> None:
        """The stand-in for the older GExiv2 reproduces the repeated values."""
        meta = fake_meta({WIDTH_TAG: "514"})
        FakeExiv.old = True
        self.assertEqual(meta.get_tag_multiple(WIDTH_TAG), ["514"] * 3)
        FakeExiv.old = False
        self.assertEqual(meta.get_tag_multiple(WIDTH_TAG), ["514"])

    @both_gexiv2
    def test_plain_values_are_read_once(self) -> None:
        """Plain XMP text and the fields of XMP structures are never repeated."""
        meta = fake_meta(
            {
                WIDTH_TAG: "514",
                NAME_TAG: "Ann Example",
                "Xmp.xmp.CreatorTool": "Adobe Photoshop",
                RECTANGLE_TAG: "0.6, 0.1, 0.09, 0.24",
            }
        )
        self.assertEqual(mi._tag_full(meta, WIDTH_TAG), "514")
        self.assertEqual(mi._tag_full(meta, NAME_TAG), "Ann Example")
        self.assertEqual(mi._tag_full(meta, "Xmp.xmp.CreatorTool"), "Adobe Photoshop")
        self.assertEqual(
            mi._tag_full(meta, RECTANGLE_TAG),
            "0.6, 0.1, 0.09, 0.24",
        )
        self.assertIsNone(mi._tag_values(meta, WIDTH_TAG))
        self.assertIsNone(mi._tag_values(meta, "Xmp.xmp.CreatorTool"))

    @both_gexiv2
    def test_plain_xmp_date_is_formatted_once(self) -> None:
        """A plain XMP date is shown once, in the Gramps date format."""
        meta = fake_meta({"Xmp.photoshop.DateCreated": "1931-06-01"})
        self.assertEqual(mi._tag_full(meta, "Xmp.photoshop.DateCreated"), "1931-6-1")

    @both_gexiv2
    def test_arrays_give_every_item(self) -> None:
        """Bags, sequences and repeatable IPTC datasets give all their items."""
        meta = fake_meta(
            {
                "Xmp.dc.creator": "A",
                "Xmp.iptcExt.PersonInImage": "x",
                "Xmp.dc.subject": "x",
                "Iptc.Application2.Keywords": "family",
            },
            {
                "Xmp.dc.creator": ["A. Dana", "B. Eli"],
                "Xmp.iptcExt.PersonInImage": ["Ann", "Bob", "Cy"],
                "Xmp.dc.subject": ["family", "farm"],
                "Iptc.Application2.Keywords": ["family", "farm", "barn"],
            },
        )
        self.assertEqual(mi._tag_full(meta, "Xmp.dc.creator"), "A. Dana; B. Eli")
        self.assertEqual(
            mi._tag_full(meta, "Xmp.iptcExt.PersonInImage"), "Ann; Bob; Cy"
        )
        self.assertEqual(mi._tag_full(meta, "Xmp.dc.subject"), "family; farm")
        self.assertEqual(
            mi._tag_full(meta, "Iptc.Application2.Keywords"), "family; farm; barn"
        )
        self.assertEqual(mi._tag_values(meta, "Xmp.dc.creator"), ["A. Dana", "B. Eli"])

    @both_gexiv2
    def test_one_item_array(self) -> None:
        """An array with one item gives that item."""
        meta = fake_meta({"Xmp.dc.creator": "Solo"}, {"Xmp.dc.creator": ["Solo"]})
        self.assertEqual(mi._tag_full(meta, "Xmp.dc.creator"), "Solo")

    @both_gexiv2
    def test_language_alternatives_are_read_from_the_string(self) -> None:
        """Titles in several languages show the default first on any GExiv2."""
        one = fake_meta({"Xmp.dc.title": 'lang="x-default" Grandpa'})
        two = fake_meta({"Xmp.dc.title": 'lang="x-default" Hello, lang="de" Hallo'})
        self.assertEqual(mi._tag_full(one, "Xmp.dc.title"), "Grandpa")
        self.assertEqual(mi._tag_full(two, "Xmp.dc.title"), "Hello; Hallo (de)")
        self.assertEqual(mi._tag_values(two, "Xmp.dc.title"), ["Hello; Hallo (de)"])

    def test_missing_and_exif_tags(self) -> None:
        """A missing tag is empty; an Exif tag is read as a plain string."""
        meta = fake_meta({"Exif.Image.Artist": "  Dana  "})
        self.assertEqual(mi._tag_full(meta, "Exif.Image.Artist"), "Dana")
        self.assertEqual(mi._tag_full(meta, "Exif.Image.Make"), "")
        self.assertEqual(mi._raw(meta, "Exif.Image.Make"), "")
        self.assertEqual(
            mi._describe(meta, "Exif.Image.Artist"), "description of Exif.Image.Artist"
        )
        self.assertEqual(mi._describe(meta, ""), "")

    def test_first_tag_and_joined_tags(self) -> None:
        """The first tag with a value wins; several tags can be joined."""
        meta = fake_meta(
            {"Xmp.dc.rights": 'lang="x-default" Mine', "Exif.Photo.FNumber": "F8"}
        )
        keys = ("Exif.Image.Copyright", "Xmp.dc.rights")
        self.assertEqual(mi._first_tag(meta, keys), ("Xmp.dc.rights", "Mine"))
        self.assertEqual(mi._first_tag(meta, ("Exif.Image.Artist",)), ("", ""))
        self.assertEqual(
            mi._joined_tags(meta, ("Exif.Photo.FNumber", "Exif.Photo.ISOSpeedRatings")),
            ("Exif.Photo.FNumber", "F8"),
        )

    @both_gexiv2
    def test_rows_for_every_tag(self) -> None:
        """Every tag becomes a row named by its generic label, with its raw tag."""
        tags = {
            "Xmp.dc.title": 'lang="x-default" Grandpa at the farm',
            "Iptc.Application2.Headline": "Farm Day",
            "Exif.Image.ImageDescription": "Line1\nLine2",
            "Exif.Photo.DateTimeDigitized": "2005:03:02 10:00:00",
            "Exif.Photo.DateTimeOriginal": "1931:06:01 00:00:00",
            "Exif.Image.Make": "Canon",
            "Exif.Image.Copyright": "(c) 1931 Family",
            "Xmp.xmpRights.UsageTerms": 'lang="x-default" Family use only',
            "Xmp.iptcExt.DigitalSourceType": "digitalCapture",
            NAME_TAG: "Ann Example",
        }
        image = self.make_image(tags, sidecar=False, size=(800, 600))
        FakeExiv.PROFILES[image] = exiv_profile(
            tags, {"Iptc.Application2.Keywords": ["family", "farm"]}, 800, 600
        )
        rows, marks = mi._read_gexiv2(image)
        by_tag = {row.tag: row for row in rows if row.tag}
        self.assertEqual(marks, [])
        labels = {tag: by_tag[tag].label for tag in tags if tag != NAME_TAG}
        self.assertEqual(
            labels,
            {
                "Xmp.dc.title": "Title",
                "Iptc.Application2.Headline": "Headline",
                "Exif.Image.ImageDescription": "Description",
                "Exif.Photo.DateTimeDigitized": "Date/Time Digitized",
                "Exif.Photo.DateTimeOriginal": "Date/Time Original",
                "Exif.Image.Make": "Make",
                "Exif.Image.Copyright": "Copyright Notice",
                "Xmp.xmpRights.UsageTerms": "Rights Usage Terms",
                "Xmp.iptcExt.DigitalSourceType": "Digital Source Type",
            },
        )
        self.assertEqual(by_tag[NAME_TAG].label, "Regions > RegionList[2] > Name")
        self.assertEqual(by_tag["Xmp.dc.title"].full, "Grandpa at the farm")
        self.assertEqual(by_tag["Exif.Image.ImageDescription"].full, "Line1\nLine2")
        self.assertEqual(
            by_tag["Exif.Photo.DateTimeOriginal"].full, "1931-6-1 00:00:00"
        )
        self.assertEqual(by_tag[NAME_TAG].full, "Ann Example")
        self.assertEqual(
            by_tag["Exif.Image.Copyright"].desc, "description of Exif.Image.Copyright"
        )
        self.assertEqual(
            [(r.label, r.full) for r in rows if r.section == "fileinfo"],
            [("Dimensions", "800 x 600 pixels")],
        )

    def test_empty_xmp_containers_are_left_out(self) -> None:
        """XMP structure containers carry no value, so they are not listed."""
        image = self.make_image(
            {"Xmp.mwg-rs.Regions": "", WIDTH_TAG: "514"}, sidecar=False
        )
        rows = mi._read_gexiv2(image, size=(1, 1))[0]
        self.assertEqual([row.tag for row in rows], [WIDTH_TAG])

    def test_known_size_is_not_repeated_by_the_reader(self) -> None:
        """When the caller knows the size, the reader adds no Dimensions row."""
        image = self.make_image({"Exif.Image.Make": "Canon"}, sidecar=False)
        rows = mi._read_gexiv2(image, size=(500, 347))[0]
        self.assertEqual([row for row in rows if row.section == "fileinfo"], [])


# -------------------------------------------------------------------------
#
# CaptureTests
#
# -------------------------------------------------------------------------
class CaptureTests(InspectorTestCase):
    """
    The Technical and Capture rows decoded from the Exif of the file.
    """

    @staticmethod
    def capture(tags: dict[str, str]) -> dict[str, str]:
        """Return {label: value} of the capture rows for the tags."""
        return {row.label: row.full for row in mi._capture_rows(fake_meta(tags))}

    def test_no_data_gives_no_rows(self) -> None:
        """Nothing is listed when there are no capture tags."""
        self.assertEqual(mi._capture_rows(fake_meta({})), [])

    def test_all_rows_in_order(self) -> None:
        """Camera, exposure, lens, GPS and altitude come in that order."""
        tags = {
            "Exif.Image.Make": "Canon",
            "Exif.Image.Model": "Canon EOS 5D",
            "Exif.Photo.FNumber": "F5.6",
            "Exif.Photo.ExposureTime": "1/125 s",
            "Exif.Photo.ISOSpeedRatings": "100",
            "Exif.Photo.LensModel": "EF50mm",
            "Exif.Photo.FocalLength": "50.0 mm",
            "Exif.GPSInfo.GPSLatitude": "38/1 30/1 0/1",
            "Exif.GPSInfo.GPSLatitudeRef": "N",
            "Exif.GPSInfo.GPSLongitude": "96/1 48/1 0/1",
            "Exif.GPSInfo.GPSLongitudeRef": "W",
            "Exif.GPSInfo.GPSAltitude": "1000/10",
            "Exif.GPSInfo.GPSAltitudeRef": "1",
        }
        rows = mi._capture_rows(fake_meta(tags))
        self.assertEqual(
            [row.label for row in rows],
            [
                "Make & Model",
                "Exposure Settings",
                "Lens Specifications",
                "GPS",
                "Altitude",
            ],
        )
        values = {row.label: row.full for row in rows}
        self.assertEqual(values["Make & Model"], "Canon EOS 5D")
        self.assertEqual(values["Exposure Settings"], "F5.6 \u00b7 1/125 s \u00b7 100")
        self.assertEqual(values["Lens Specifications"], "EF50mm \u00b7 50.0 mm")
        self.assertEqual(values["GPS"], position_text("38.500000", "-96.800000"))
        self.assertEqual(values["Altitude"], "-100.0 m")
        self.assertEqual({row.status for row in rows}, {""})
        tags_by_label = {row.label: row.tag for row in rows}
        self.assertEqual(
            tags_by_label["Make & Model"], "Exif.Image.Make, Exif.Image.Model"
        )

    def test_camera_names(self) -> None:
        """The make is not repeated when the model contains it."""
        self.assertEqual(
            self.capture({"Exif.Image.Make": "Nikon", "Exif.Image.Model": "D70"})[
                "Make & Model"
            ],
            "Nikon D70",
        )
        self.assertEqual(
            self.capture({"Exif.Image.Make": "Kodak"})["Make & Model"], "Kodak"
        )
        self.assertEqual(
            self.capture({"Exif.Image.Model": "Brownie No. 2"})["Make & Model"],
            "Brownie No. 2",
        )

    def test_partial_exposure_and_lens(self) -> None:
        """Only the values that exist are shown."""
        self.assertEqual(
            self.capture({"Exif.Photo.ISOSpeedRatings": "400"})["Exposure Settings"],
            "400",
        )
        self.assertEqual(
            self.capture({"Exif.Photo.LensModel": "EF50mm"})["Lens Specifications"],
            "EF50mm",
        )

    def test_gps_hemispheres_and_altitude(self) -> None:
        """Southern and eastern positions, and altitudes above and below sea level."""
        south_east = {
            "Exif.GPSInfo.GPSLatitude": "33/1 51/1 2442/100",
            "Exif.GPSInfo.GPSLatitudeRef": "S",
            "Exif.GPSInfo.GPSLongitude": "151/1 12/1 5507/100",
            "Exif.GPSInfo.GPSLongitudeRef": "E",
        }
        self.assertEqual(
            self.capture(south_east)["GPS"], position_text("-33.856783", "151.215297")
        )
        self.assertNotIn("Altitude", self.capture(south_east))
        above = {
            "Exif.GPSInfo.GPSAltitude": "2000/10",
            "Exif.GPSInfo.GPSAltitudeRef": "0",
        }
        self.assertEqual(self.capture(above)["Altitude"], "200.0 m")
        self.assertEqual(
            self.capture({"Exif.GPSInfo.GPSAltitude": "5/1"})["Altitude"], "5.0 m"
        )

    def test_incomplete_or_impossible_gps(self) -> None:
        """A missing longitude or unreadable values give no position."""
        latitude_only = {
            "Exif.GPSInfo.GPSLatitude": "33/1 51/1 0/1",
            "Exif.GPSInfo.GPSLatitudeRef": "S",
        }
        self.assertNotIn("GPS", self.capture(latitude_only))
        unreadable = {
            "Exif.GPSInfo.GPSLatitude": "n/a",
            "Exif.GPSInfo.GPSLongitude": "n/a",
        }
        self.assertNotIn("GPS", self.capture(unreadable))

    def test_impossible_latitude_falls_back_to_numbers(self) -> None:
        """When Gramps cannot format the position it is shown as plain numbers."""
        impossible = {
            "Exif.GPSInfo.GPSLatitude": "91/1 0/1 0/1",
            "Exif.GPSInfo.GPSLatitudeRef": "N",
            "Exif.GPSInfo.GPSLongitude": "10/1 0/1 0/1",
            "Exif.GPSInfo.GPSLongitudeRef": "E",
        }
        self.assertEqual(self.capture(impossible)["GPS"], "91.000000, 10.000000")

    def test_capture_rows_come_from_the_file_only(self) -> None:
        """A sidecar never produces capture rows."""
        image = self.make_image(
            {"Exif.Image.Make": "Canon", "Exif.Image.Model": "EOS 5D"},
            {"Exif.Image.Make": "Other"},
        )
        rows = collect(FakeMedia(image)).rows
        self.assertEqual(
            [r.full for r in rows if r.section == "capture"], ["Canon EOS 5D"]
        )
        pdf = self.make_file("doc.pdf", b"%PDF")
        self.make_file("doc.xmp")
        FakeExiv.PROFILES[os.path.join(self.tmp, "doc.xmp")] = exiv_profile(
            {"Exif.Image.Make": "Canon"}
        )
        rows = collect(FakeMedia(pdf, "application/pdf")).rows
        self.assertFalse([r for r in rows if r.section == "capture"])


# -------------------------------------------------------------------------
#
# SidecarLookupTests
#
# -------------------------------------------------------------------------
class SidecarLookupTests(InspectorTestCase):
    """
    Finding the XMP sidecar of a file.
    """

    def test_candidates(self) -> None:
        """The names looked for, lower case first at even positions."""
        names = [os.path.basename(c) for c in mi._sidecar_candidates("/x/photo.jpg")]
        self.assertEqual(
            names, ["photo.xmp", "photo.XMP", "photo.jpg.xmp", "photo.jpg.XMP"]
        )

    def test_no_sidecar(self) -> None:
        """A file without a sidecar has none."""
        self.assertEqual(mi._find_sidecar(self.make_file("photo.jpg")), "")

    def test_both_conventions(self) -> None:
        """photo.xmp is preferred, photo.jpg.xmp is accepted."""
        image = self.make_file("photo.jpg")
        both = self.make_file("photo.jpg.xmp")
        self.assertEqual(mi._find_sidecar(image), both)
        first = self.make_file("photo.xmp")
        self.assertEqual(mi._find_sidecar(image), first)

    def test_an_xmp_file_is_not_its_own_sidecar(self) -> None:
        """A media file that is itself an .xmp has no sidecar."""
        self.assertEqual(mi._find_sidecar(self.make_file("x.xmp")), "")


# -------------------------------------------------------------------------
#
# ReaderTests
#
# -------------------------------------------------------------------------
class ReaderTests(InspectorTestCase):
    """
    The readers for PDF, audio and video, and the opening of files.
    """

    def test_pdf_rows(self) -> None:
        """The PDF reader lists the page count and the information entries."""

        class Reader:
            """Fake pypdf reader."""

            is_encrypted = False
            metadata = {
                "/Title": "Deed",
                "/Author": "Clerk",
                "/CreationDate": "D:19300615120000+00'00'",
                "/Subject": "",
            }
            pages = [1, 2, 3]

            def __init__(self, _path: str) -> None:
                """Accept the path."""

        with mock.patch.object(mi, "PdfReader", Reader):
            rows, note = mi._read_pdf("x.pdf")
        by_label = {row.label: row for row in rows}
        self.assertEqual({row.section for row in rows}, {"pdf"})
        self.assertEqual(by_label["Pages"].full, "3")
        self.assertEqual(
            (by_label["Title"].full, by_label["Author"].full), ("Deed", "Clerk")
        )
        self.assertEqual(by_label["CreationDate"].full, "1930-6-15 12:00:00")
        self.assertNotIn("Subject", by_label)
        self.assertEqual(note, "")

    def test_pdf_reader_missing_or_failing(self) -> None:
        """A missing library or a damaged PDF gives a note and no rows."""
        rows, note = mi._read_pdf("x.pdf")
        self.assertEqual((rows, "pypdf" in note), ([], True))

        def failing(_path: str) -> Any:
            """Raise like a damaged PDF."""
            raise ValueError("damaged")

        with mock.patch.object(mi, "PdfReader", failing):
            rows, note = mi._read_pdf("x.pdf")
        self.assertEqual(
            (rows, note), ([], "This PDF could not be read (damaged or encrypted?).")
        )

    def test_encrypted_pdf_is_opened_with_an_empty_password(self) -> None:
        """An encrypted PDF is tried with an empty password."""
        passwords: list[str] = []

        class Reader:
            """Fake pypdf reader of an encrypted file."""

            is_encrypted = True
            metadata = {"/Title": "Locked"}
            pages: list[int] = []

            def __init__(self, _path: str) -> None:
                """Accept the path."""

            def decrypt(self, password: str) -> None:
                """Record the password."""
                passwords.append(password)

        with mock.patch.object(mi, "PdfReader", Reader):
            rows = mi._read_pdf("x.pdf")[0]
        self.assertEqual(passwords, [""])
        self.assertIn("Title", [row.label for row in rows])

    def test_audio_rows(self) -> None:
        """The audio reader lists the stream information and the tags."""
        audio = types.SimpleNamespace(
            info=types.SimpleNamespace(
                length=125.0, bitrate=128000, sample_rate=44100, channels=2
            ),
            tags={"title": ["Song"], "artist": ["Band", "Guest"]},
        )
        fake = types.SimpleNamespace(File=lambda _path, easy=True: audio)
        with mock.patch.object(mi, "mutagen", fake):
            rows, note = mi._read_av("x.mp3")
        values = {(row.group, row.label): row.full for row in rows}
        self.assertEqual(
            values,
            {
                ("Stream", "Duration"): "2:05",
                ("Stream", "Bit rate"): "128 kbps",
                ("Stream", "Sample rate"): "44100 Hz",
                ("Stream", "Channels"): "2",
                ("Tags", "title"): "Song",
                ("Tags", "artist"): "Band; Guest",
            },
        )
        self.assertEqual(note, "")

    def test_audio_reader_missing_unreadable_or_unknown(self) -> None:
        """No library, a failing library and an unknown format all give no rows."""
        rows, note = mi._read_av("x.mp3")
        self.assertEqual((rows, "mutagen" in note), ([], True))

        def failing(_path: str, easy: bool = True) -> Any:
            """Raise like an unreadable file."""
            raise ValueError("unreadable")

        for reader in (failing, lambda _path, easy=True: None):
            with mock.patch.object(mi, "mutagen", types.SimpleNamespace(File=reader)):
                self.assertEqual(mi._read_av("x.mp3"), ([], ""))

    def test_opening_files(self) -> None:
        """A readable file opens; unreadable files and a missing GExiv2 give None."""
        image = self.make_image(sidecar=False)
        self.assertIsNotNone(mi._open_metadata(image))
        self.assertIsNone(mi._open_metadata(os.path.join(self.tmp, "missing.jpg")))
        self.assertIsNone(mi._open_metadata(""))
        with mock.patch.object(mi, "GExiv2", None):
            self.assertIsNone(mi._open_metadata(image))

    def test_image_size(self) -> None:
        """The size comes from the image header; unreadable images have none."""
        image = self.make_image(size=(516, 640))
        self.assertEqual(mi._image_size(image), (516, 640))
        FakeGdkPixbuf.sizes[image] = None
        self.assertIsNone(mi._image_size(image))


# -------------------------------------------------------------------------
#
# FileInformationTests
#
# -------------------------------------------------------------------------
class FileInformationTests(InspectorTestCase):
    """
    The rows with the file information, and the creation time in particular.
    """

    def test_rows_and_order(self) -> None:
        """Created sits just above Modified."""
        path = self.make_file("pic.jpg")
        labels = [
            row.label for row in mi._file_info_rows("fileinfo", path, "image/jpeg")
        ]
        self.assertEqual(
            labels, ["Name", "Folder", "Size", "Created", "Modified", "Type"]
        )
        self.assertEqual(
            [row.label for row in mi._file_info_rows("sidecar_file", path)],
            ["Name", "Folder", "Size", "Created", "Modified"],
        )

    def test_birth_time_from_python(self) -> None:
        """st_birthtime is used where Python provides it, before GIO."""
        stat = types.SimpleNamespace(st_birthtime=946684800.0)
        FakeGio.created = 1000000000
        expected = datetime.datetime.fromtimestamp(946684800.0)
        self.assertEqual(mi._created_time("x", stat), expected)

    def test_birth_time_from_gio(self) -> None:
        """Without st_birthtime (Linux) the birth time comes from GIO."""
        FakeGio.created = 1000000000
        expected = datetime.datetime.fromtimestamp(1000000000)
        self.assertEqual(mi._created_time("x", types.SimpleNamespace()), expected)

    def test_no_birth_time(self) -> None:
        """When it is not recorded, or GIO fails, there is no creation time."""
        stat = types.SimpleNamespace()
        self.assertIsNone(mi._created_time("x", stat))
        FakeGio.created = 0
        self.assertIsNone(mi._created_time("x", stat))
        FakeGio.created = 1000000000
        FakeGio.raising = True
        self.assertIsNone(mi._created_time("x", stat))
        self.assertIsNone(mi._created_time("x", types.SimpleNamespace(st_birthtime=0)))

    def test_created_is_shown_or_stated_unavailable(self) -> None:
        """Created shows the time, or says Not available instead of guessing."""
        path = self.make_file("pic.jpg")
        FakeGio.created = 1000000000
        shown = {row.label: row.full for row in mi._file_info_rows("fileinfo", path)}
        expected = mi._format_timestamp(datetime.datetime.fromtimestamp(1000000000))
        self.assertEqual(shown["Created"], expected)
        self.assertNotEqual(shown["Created"], shown["Modified"])
        FakeGio.created = None
        shown = {row.label: row.full for row in mi._file_info_rows("fileinfo", path)}
        self.assertEqual(shown["Created"], "Not available")
        self.assertNotEqual(shown["Modified"], "Not available")


# -------------------------------------------------------------------------
#
# Fakes for the objects of the database that a media object points to
#
# -------------------------------------------------------------------------
class FakeAttribute:
    """
    An attribute of the media object.
    """

    def __init__(self, kind: str, value: str) -> None:
        """Remember the type and the value."""
        self.kind = kind
        self.value = value

    def get_type(self) -> str:
        """Return the type."""
        return self.kind

    def get_value(self) -> str:
        """Return the value."""
        return self.value


class FakeNote:
    """
    A note.
    """

    def get_gramps_id(self) -> str:
        """Return the Gramps ID."""
        return "N0001"

    def get_type(self) -> str:
        """Return the type."""
        return "Media Note"

    def get(self) -> str:
        """Return the text."""
        return "line one\nline two"


class FakeTag:
    """
    A tag.
    """

    def get_name(self) -> str:
        """Return the name."""
        return "Verified"


class FakeSource:
    """
    A source.
    """

    def get_title(self) -> str:
        """Return the title."""
        return "1900 Census"


class FakeCitation:
    """
    A citation.
    """

    def get_gramps_id(self) -> str:
        """Return the Gramps ID."""
        return "C0001"

    def get_page(self) -> str:
        """Return the page."""
        return "Sheet 4, line 12"

    def get_reference_handle(self) -> str:
        """Return the handle of the source."""
        return "S1"


def reference_db() -> FakeDb:
    """
    Return a database where six objects refer to the media object (or not).
    """
    holders = {
        "p1": FakeHolder("I01", "Ann Example", [FakeMediaRef("HM", (15, 27, 25, 43))]),
        "p2": FakeHolder(
            "I02",
            "Ben Sample",
            [FakeMediaRef("OTHER", (1, 1, 2, 2)), FakeMediaRef("HM", (51, 19, 59, 33))],
        ),
        "p3": FakeHolder("I03", "Zed No Region", [FakeMediaRef("HM", None)]),
        "p4": FakeHolder(
            "I04", "Not Referencing", [FakeMediaRef("OTHER", (5, 5, 6, 6))]
        ),
        "f1": FakeHolder("F01", "Sample / Example", [FakeMediaRef("HM", (0, 0, 0, 0))]),
        "e1": FakeHolder(
            "E01", "x", [FakeMediaRef("HM", (10, 10, 20, 20))], "Birth of Ben"
        ),
    }
    links = [
        ("Person", "p3"),
        ("Event", "e1"),
        ("Person", "p1"),
        ("Family", "f1"),
        ("Person", "p2"),
    ]
    return FakeDb(links, holders)


# -------------------------------------------------------------------------
#
# PrecedenceTests
#
# -------------------------------------------------------------------------
class PrecedenceTests(InspectorTestCase):
    """
    Which source is in use when sources disagree, and how that is marked.
    """

    @staticmethod
    def candidate(source: str, text: str, *rowkeys: tuple[str, str]) -> Any:
        """Return a text Candidate."""
        return mi.Candidate(source, text, ("text", text.lower()), rowkeys)

    def test_gramps_outranks_sidecar_outranks_file(self) -> None:
        """The Current Tree wins, then the sidecar, then the file."""
        gramps = self.candidate("gramps", "G")
        sidecar = self.candidate("sidecar", "S")
        file = self.candidate("file", "F")
        shown, losers = mi._resolve("Title", [file, sidecar, gramps])
        self.assertEqual(
            (shown.source, [c.source for c in losers]), ("gramps", ["sidecar", "file"])
        )
        shown, losers = mi._resolve("Title", [file, sidecar])
        self.assertEqual(
            (shown.source, [c.source for c in losers]), ("sidecar", ["file"])
        )

    def test_the_file_wins_on_pixel_size(self) -> None:
        """The pixel size is a fact about the file, so the file outranks a sidecar."""
        sidecar = self.candidate("sidecar", "514")
        file = self.candidate("file", "516")
        shown, losers = mi._resolve("Dimensions", [sidecar, file])
        self.assertEqual(
            (shown.source, [c.source for c in losers]), ("file", ["sidecar"])
        )

    def test_agreeing_dates_show_the_more_precise_one(self) -> None:
        """A year and a date that agree are no conflict; the fuller date is shown."""
        year = mi.Candidate("gramps", "1897", ("gdate", Date(1897, 0, 0)), ())
        full = mi.Candidate("file", "1897-3-2", ("gdate", Date(1897, 3, 2)), ())
        shown, losers = mi._resolve(mi._LABEL_DATE_ORIGINAL, [full, year])
        self.assertEqual((shown.source, losers), ("file", []))

    def test_conflicting_dates_show_the_gramps_date(self) -> None:
        """When the dates disagree the Gramps date is in use."""
        year = mi.Candidate("gramps", "1897", ("gdate", Date(1897, 0, 0)), ())
        other = mi.Candidate("file", "1931-6-1", ("gdate", Date(1931, 6, 1)), ())
        shown, losers = mi._resolve(mi._LABEL_DATE_ORIGINAL, [other, year])
        self.assertEqual(
            (shown.source, [c.source for c in losers]), ("gramps", ["file"])
        )

    def test_judge_marks_the_rows(self) -> None:
        """The value in use is preferred and what it overrides is overridden."""
        file = self.candidate("file", "F", ("exif", "Exif.Image.Copyright"))
        sidecar = self.candidate("sidecar", "S", ("xmp_sidecar", "Xmp.dc.rights"))
        marks: list[Any] = []
        mi._judge(marks, "Copyright Notice", [file, sidecar])
        note = "Preferred value. Other sources differ:\n  File: F"
        self.assertEqual(
            marks,
            [
                ("xmp_sidecar", "Xmp.dc.rights", "preferred", note),
                (
                    "exif",
                    "Exif.Image.Copyright",
                    "overridden",
                    "Overridden by XMP sidecar: S",
                ),
            ],
        )

    def test_judge_marks_nothing_without_a_conflict(self) -> None:
        """Equal values leave the rows alone."""
        marks: list[Any] = []
        mi._judge(
            marks,
            "Title",
            [
                self.candidate("file", "Same", ("a", "b")),
                self.candidate("sidecar", "SAME", ("c", "d")),
            ],
        )
        self.assertEqual(marks, [])

    def test_apply_marks_by_tag_or_label(self) -> None:
        """A mark applies to the row of that section with that tag or label."""
        rows = [
            mi._row("exif", "", "Copyright Notice", "x", "Exif.Image.Copyright"),
            mi._row("gramps", "", "Title", "t"),
            mi._row("iptc", "", "Title", "t", "Iptc.Application2.ObjectName"),
        ]
        marked = mi._apply_marks(
            rows,
            [
                ("exif", "Exif.Image.Copyright", "overridden", "why"),
                ("gramps", "Title", "preferred", "n"),
            ],
        )
        self.assertEqual([r.status for r in marked], ["overridden", "preferred", ""])
        self.assertEqual(marked[0].note, "why")


# -------------------------------------------------------------------------
#
# DatabaseRowTests
#
# -------------------------------------------------------------------------
class DatabaseRowTests(InspectorTestCase):
    """
    Rows from the database: references, attributes, notes, tags and citations.
    """

    def test_references_and_regions(self) -> None:
        """One row for each reference to the media object, sorted by type and name."""
        rows = mi._reference_rows(reference_db(), FakeMedia("x.jpg"), (500, 347))
        self.assertEqual(
            [(row.group, row.label) for row in rows],
            [
                ("Person", "Ann Example [I01]"),
                ("Person", "Ben Sample [I02]"),
                ("Person", "Zed No Region [I03]"),
                ("Family", "Sample / Example [F01]"),
                ("Event", "Birth of Ben [E01]"),
            ],
        )
        by_label = {row.label: row for row in rows}
        ann = by_label["Ann Example [I01]"]
        self.assertEqual(ann.value, "15%, 27% \u2013 25%, 43%")
        self.assertIn(
            "About 75,94 to 125,149 pixels in a 500 x 347 pixel image", ann.full
        )
        self.assertEqual(by_label["Ben Sample [I02]"].value, "51%, 19% \u2013 59%, 33%")
        whole = "Whole image (no region selected)"
        self.assertEqual(by_label["Zed No Region [I03]"].value, whole)
        self.assertEqual(by_label["Sample / Example [F01]"].value, whole)
        self.assertNotIn("I04", " ".join(row.label for row in rows))
        self.assertEqual({row.section for row in rows}, {"refs"})

    def test_references_survive_a_failing_database(self) -> None:
        """A database without back-references, or one that fails, gives no rows."""
        media = FakeMedia("x.jpg")
        self.assertEqual(mi._reference_rows(None, media, None), [])

        class Failing(FakeDb):
            """Database that fails like a closed one."""

            def find_backlink_handles(self, handle: str, classes: list[str]) -> Any:
                """Raise a Gramps error."""
                raise mi.HandleError("closed")

        self.assertEqual(mi._reference_rows(Failing([], {}), media, None), [])

    def test_attributes_notes_tags_and_citations(self) -> None:
        """The media object's own attributes, notes, tags and citations are listed."""
        db = FakeDb(
            [],
            {
                "N1": FakeNote(),
                "T1": FakeTag(),
                "C1": FakeCitation(),
                "S1": FakeSource(),
            },
        )
        media = FakeMedia(
            "x.jpg",
            attrs=[FakeAttribute("Photographer", "A. Dana")],
            notes=["N1", "GONE"],
            tags=["T1"],
            cites=["C1"],
        )
        rows = mi._media_object_rows(db, media)
        by_section = self.sections(rows)
        self.assertEqual(
            [(r.label, r.value) for r in by_section["attrs"]],
            [("Photographer", "A. Dana")],
        )
        self.assertEqual(len(by_section["notes"]), 1)
        note = by_section["notes"][0]
        self.assertEqual(note.label, "Media Note [N0001]")
        self.assertEqual(note.full, "line one\nline two")
        self.assertEqual(note.value, "line one line two")
        self.assertEqual([r.label for r in by_section["tags"]], ["Verified"])
        cite = by_section["cites"][0]
        self.assertEqual(
            (cite.label, cite.value), ("1900 Census [C0001]", "Sheet 4, line 12")
        )

    def test_object_rows_without_the_getters(self) -> None:
        """A database that cannot supply the objects gives no rows."""
        media = FakeMedia("x.jpg", notes=["N1"], tags=["T1"], cites=["C1"])
        self.assertEqual(mi._media_object_rows(None, media), [])


# -------------------------------------------------------------------------
#
# CollectTests
#
# -------------------------------------------------------------------------
class CollectTests(InspectorTestCase):
    """
    collect_metadata() end to end: what is shown, what is marked, which tabs have data.
    """

    def use_sample_sidecar(self, size: tuple[int, int] = (516, 640)) -> str:
        """Create an image with the synthetic sidecar next to it."""
        image = self.make_image(sidecar=False, size=size)
        side = os.path.join(self.tmp, "pic.xmp")
        shutil.copy(SAMPLE_XMP, side)
        FakeExiv.PROFILES[side] = sidecar_profile(SAMPLE_XMP)
        return image

    @both_gexiv2
    def test_sidecar_values_are_shown_once(self) -> None:
        """Sidecar rows show each value once; only the people list has separators."""
        rows = collect(FakeMedia(self.use_sample_sidecar())).rows
        side = [row for row in rows if row.section == "xmp_sidecar"]
        self.assertEqual(len(side), 27)
        self.assertTrue(all(row.full for row in side))
        self.assertEqual(
            [row.tag for row in side if "; " in row.full], ["Xmp.iptcExt.PersonInImage"]
        )
        by_label = {row.label: row.full for row in side}
        self.assertEqual(by_label["Title"], "A Family Picnic at the Lake")
        self.assertEqual(by_label["Creator"], "Dana Photographer")
        self.assertEqual(
            by_label["People in Image"], "Ann Example; Ben Sample; Cy Placeholder"
        )
        self.assertEqual(by_label["Regions > RegionList[2] > Name"], "Ben Sample")
        self.assertEqual(by_label["Regions > RegionList[3] > Type"], "Face")
        self.assertEqual(by_label["Regions > RegionList[1] > Area > x"], "0.301")
        self.assertEqual(by_label["Regions > AppliedToDimensions > w"], "514")
        self.assertEqual(by_label["Regions > AppliedToDimensions > unit"], "pixel")
        self.assertEqual({row.group for row in side}, {"dc", "iptcExt", "mwg-rs"})

    @both_gexiv2
    def test_sidecar_tab_information_and_notes(self) -> None:
        """The sidecar file is listed, and a note says where the details come from."""
        result = collect(FakeMedia(self.use_sample_sidecar()))
        sidecar_file = {
            r.label: r.full for r in result.rows if r.section == "sidecar_file"
        }
        self.assertEqual(sidecar_file["Name"], "pic.xmp")
        self.assertEqual(sidecar_file["Folder"], self.tmp)
        self.assertIn("Created", sidecar_file)
        self.assertEqual(
            result.notes,
            [
                "The file itself carries no Exif/IPTC/XMP metadata; the details "
                "come from its XMP sidecar (pic.xmp)."
            ],
        )
        self.assertEqual(result.sidecar_names, ("pic.xmp", "pic.jpg.xmp"))
        self.assertEqual(
            result.has_data, {"file": True, "sidecar": True, "gramps": False}
        )

    @both_gexiv2
    def test_pixel_size_mismatch_in_the_sidecar(self) -> None:
        """A sidecar saying 514 pixels for a 516 pixel file has both rows marked."""
        rows = collect(FakeMedia(self.use_sample_sidecar())).rows
        dims = self.find(rows, "fileinfo", "Dimensions")
        self.assertEqual((dims.full, dims.status), ("516 x 640 pixels", "preferred"))
        self.assertIn("XMP sidecar: 514 x 640 pixels", dims.note)
        for tag in (WIDTH_TAG, WIDTH_TAG.replace(":w", ":h")):
            row = self.find(rows, "xmp_sidecar", tag)
            self.assertEqual(
                (row.status, row.note),
                ("overridden", "Overridden by File: 516 x 640 pixels"),
            )

    @both_gexiv2
    def test_matching_or_unusable_sidecar_size_marks_nothing(self) -> None:
        """Equal sizes, and sizes in another unit, are not conflicts."""
        image = self.use_sample_sidecar(size=(514, 640))
        self.assertEqual(self.statuses(collect(FakeMedia(image)).rows), {})
        image = self.use_sample_sidecar()
        FakeExiv.PROFILES[os.path.join(self.tmp, "pic.xmp")]["tags"][
            WIDTH_TAG.replace(":w", ":unit")
        ] = "normalized"
        self.assertEqual(self.statuses(collect(FakeMedia(image)).rows), {})

    @both_gexiv2
    def test_three_way_title_conflict(self) -> None:
        """The Current Tree title wins over the sidecar and the file."""
        image = self.make_image(
            {"Iptc.Application2.ObjectName": "File Title"},
            {"Xmp.dc.title": 'lang="x-default" Sidecar Title'},
        )
        rows = collect(FakeMedia(image, desc="Gramps Title")).rows
        title = self.find(rows, "gramps", "Title")
        self.assertEqual(title.status, "preferred")
        self.assertIn("XMP sidecar: Sidecar Title", title.note)
        self.assertIn("File: File Title", title.note)
        sidecar = self.find(rows, "xmp_sidecar", "Xmp.dc.title")
        self.assertEqual(
            (sidecar.status, sidecar.note),
            ("overridden", "Overridden by Gramps media record: Gramps Title"),
        )
        self.assertEqual(
            self.find(rows, "iptc", "Iptc.Application2.ObjectName").status, "overridden"
        )

    @both_gexiv2
    def test_sidecar_outranks_file_without_a_gramps_counterpart(self) -> None:
        """The sidecar beats the file for a copyright; case and spacing are ignored."""
        image = self.make_image(
            {"Exif.Image.Copyright": "(c) Family", "Exif.Image.Artist": "Same Person"},
            {"Xmp.dc.rights": "(c) Sidecar Owner", "Xmp.dc.creator": "same   PERSON"},
        )
        rows = collect(FakeMedia(image)).rows
        self.assertEqual(
            self.statuses(rows),
            {
                ("xmp_sidecar", "Xmp.dc.rights"): "preferred",
                ("exif", "Exif.Image.Copyright"): "overridden",
            },
        )
        self.assertTrue(
            self.find(rows, "xmp_sidecar", "Xmp.dc.rights").note.endswith(
                "File: (c) Family"
            )
        )

    @both_gexiv2
    def test_same_software_in_file_and_sidecar_is_no_conflict(self) -> None:
        """The same plain value in two sources must not look different."""
        image = self.make_image(
            {"Exif.Image.Software": "Adobe Photoshop"},
            {"Xmp.xmp.CreatorTool": "Adobe Photoshop"},
        )
        rows = collect(FakeMedia(image)).rows
        self.assertEqual(self.statuses(rows), {})
        self.assertEqual(
            self.find(rows, "xmp_sidecar", "Xmp.xmp.CreatorTool").full,
            "Adobe Photoshop",
        )

    @both_gexiv2
    def test_different_software_quotes_each_value_once(self) -> None:
        """When the plain values differ each one is quoted once in the notes."""
        image = self.make_image(
            {"Exif.Image.Software": "Adobe Photoshop"},
            {"Xmp.xmp.CreatorTool": "Scanner Pro 4"},
        )
        rows = collect(FakeMedia(image)).rows
        sidecar = self.find(rows, "xmp_sidecar", "Xmp.xmp.CreatorTool")
        self.assertEqual(sidecar.status, "preferred")
        self.assertEqual(sidecar.note.count("Adobe Photoshop"), 1)
        self.assertEqual(
            self.find(rows, "exif", "Exif.Image.Software").note,
            "Overridden by XMP sidecar: Scanner Pro 4",
        )

    def test_default_title_does_not_compete(self) -> None:
        """A Title that is just the file name is not a value."""
        image = self.make_image(
            {"Iptc.Application2.ObjectName": "File Title"}, sidecar=False
        )
        self.assertEqual(self.statuses(collect(FakeMedia(image)).rows), {})

    def test_gramps_data_alone_marks_nothing(self) -> None:
        """With nothing to compare against, nothing is marked."""
        pdf = self.make_file("doc.pdf", b"%PDF")
        media = FakeMedia(
            pdf, "application/pdf", desc="Deed of sale", date=make_date(1897, 3, 2)
        )
        rows = collect(media).rows
        self.assertEqual(self.statuses(rows), {})
        self.assertEqual(
            (
                self.find(rows, "gramps", "Title").full,
                self.find(rows, "gramps", "Date").full,
            ),
            ("Deed of sale", "1897-3-2"),
        )

    def test_scan_dates_the_content_date_is_the_one_compared(self) -> None:
        """A scanner stamps the scan time; the content date is in IPTC Date Created."""
        scan = {
            "Exif.Photo.DateTimeOriginal": "2005:03:02 10:00:00",
            "Exif.Photo.DateTimeDigitized": "2005:03:02 10:00:00",
            "Xmp.xmp.CreateDate": "2005-03-02T10:00:00",
            "Iptc.Application2.DateCreated": "1931-06-01",
        }
        image = self.make_image(scan, sidecar=False)
        rows = collect(FakeMedia(image, date=make_date(1931))).rows
        self.assertEqual(self.statuses(rows), {})
        self.assertEqual(
            self.find(rows, "iptc", "Iptc.Application2.DateCreated").full, "1931-6-1"
        )
        self.assertEqual(
            self.find(rows, "exif", "Exif.Photo.DateTimeDigitized").full,
            "2005-3-2 10:00:00",
        )
        rows = collect(FakeMedia(image, date=make_date(1900, 5, 5))).rows
        self.assertEqual(
            self.statuses(rows),
            {
                ("gramps", "Date"): "preferred",
                ("iptc", "Iptc.Application2.DateCreated"): "overridden",
            },
        )

    def test_sidecar_content_date_beats_a_scan_time(self) -> None:
        """photoshop:DateCreated in the sidecar overrides a scan-time Exif original."""
        image = self.make_image(
            {"Exif.Photo.DateTimeOriginal": "2005:03:02 10:00:00"},
            {"Xmp.photoshop.DateCreated": "1931-06-01"},
        )
        self.assertEqual(
            self.statuses(collect(FakeMedia(image)).rows),
            {
                ("xmp_sidecar", "Xmp.photoshop.DateCreated"): "preferred",
                ("exif", "Exif.Photo.DateTimeOriginal"): "overridden",
            },
        )

    def test_digital_copy_dates_never_conflict_with_the_gramps_date(self) -> None:
        """xmp:CreateDate is the date of the digital copy, so it is not compared."""
        image = self.make_image(
            {"Xmp.xmp.CreateDate": "2005-03-02T10:00:00"}, sidecar=False
        )
        self.assertEqual(
            self.statuses(collect(FakeMedia(image, date=make_date(1931))).rows), {}
        )

    def test_approximate_gramps_dates_end_to_end(self) -> None:
        """Approximate, ranged and other-calendar dates compare as Gramps does."""
        embedded = {"Iptc.Application2.DateCreated": "1931-06-01"}
        gramps_date, iptc = ("gramps", "Date"), (
            "iptc",
            "Iptc.Application2.DateCreated",
        )
        conflict = {gramps_date: "preferred", iptc: "overridden"}
        cases: list[tuple[str, Date, dict[str, str], int, dict[Any, str]]] = [
            (
                "about, 50 years",
                make_date(1897, modifier=Date.MOD_ABOUT),
                embedded,
                50,
                {},
            ),
            (
                "about, 10 years",
                make_date(1897, modifier=Date.MOD_ABOUT),
                embedded,
                10,
                conflict,
            ),
            (
                "range agrees",
                range_date(1895, 1900),
                {"Iptc.Application2.DateCreated": "1897-06-01"},
                50,
                {},
            ),
            ("range disagrees", range_date(1895, 1900), embedded, 50, conflict),
            (
                "before disagrees",
                make_date(1900, modifier=Date.MOD_BEFORE),
                embedded,
                50,
                conflict,
            ),
            (
                "before agrees",
                make_date(1900, modifier=Date.MOD_BEFORE),
                {"Iptc.Application2.DateCreated": "1880-01-01"},
                50,
                {},
            ),
            (
                "estimated",
                quality_date(1897, Date.QUAL_ESTIMATED),
                embedded,
                10,
                conflict,
            ),
            (
                "julian agrees",
                make_date(1897, 1, 1, calendar=Date.CAL_JULIAN),
                {"Iptc.Application2.DateCreated": "1897-01-13"},
                50,
                {},
            ),
            (
                "julian disagrees",
                make_date(1897, 1, 1, calendar=Date.CAL_JULIAN),
                {"Iptc.Application2.DateCreated": "1897-01-01"},
                50,
                conflict,
            ),
            ("text only", text_date("the spring of the flood"), embedded, 50, {}),
            ("plain date", make_date(1900, 5, 5), embedded, 50, conflict),
        ]
        for name, date, tags, about_range, expected in cases:
            with self.subTest(name):
                config.set("behavior.date-about-range", about_range)
                image = self.make_image(tags, sidecar=False)
                self.assertEqual(
                    self.statuses(collect(FakeMedia(image, date=date)).rows), expected
                )

    def test_approximate_date_is_shown_as_recorded(self) -> None:
        """The Current Tree row shows the approximate date and explains the conflict."""
        config.set("behavior.date-about-range", 10)
        image = self.make_image(
            {"Iptc.Application2.DateCreated": "1931-06-01"}, sidecar=False
        )
        media = FakeMedia(image, date=make_date(1897, modifier=Date.MOD_ABOUT))
        row = self.find(collect(media).rows, "gramps", "Date")
        self.assertEqual(row.full, "about 1897")
        self.assertIn("File: 1931-6-1", row.note)

    def test_file_information(self) -> None:
        """Dimensions are listed with the file information, even without metadata."""
        image = self.make_image(sidecar=False, size=(500, 347))
        result = collect(FakeMedia(image))
        info = {r.label: r.full for r in result.rows if r.section == "fileinfo"}
        self.assertEqual(
            set(info),
            {"Name", "Folder", "Size", "Created", "Modified", "Type", "Dimensions"},
        )
        self.assertEqual(info["Dimensions"], "500 x 347 pixels")
        self.assertEqual(result.notes, ["No embedded metadata found in this file."])
        self.assertFalse(
            [r for r in result.rows if r.section in ("xmp_sidecar", "sidecar_file")]
        )

    def test_dimensions_fall_back_to_gexiv2(self) -> None:
        """When GdkPixbuf cannot read the image, GExiv2 supplies the size once."""
        image = self.make_image(sidecar=False, size=(800, 600))
        FakeGdkPixbuf.sizes[image] = None
        rows = collect(FakeMedia(image)).rows
        self.assertEqual(
            [r.full for r in rows if r.label == "Dimensions"], ["800 x 600 pixels"]
        )
        with mock.patch.object(mi, "GExiv2", None):
            rows = collect(FakeMedia(image)).rows
        self.assertEqual([r for r in rows if r.label == "Dimensions"], [])

    def test_missing_and_unreadable_files(self) -> None:
        """The database rows are listed even when the file cannot be read."""
        result = collect(FakeMedia(os.path.join(self.tmp, "gone.jpg")), reference_db())
        self.assertEqual(
            result.notes, [f"File not found: {os.path.join(self.tmp, 'gone.jpg')}"]
        )
        self.assertEqual(len([r for r in result.rows if r.section == "refs"]), 5)
        self.assertEqual(
            result.has_data, {"file": False, "sidecar": False, "gramps": True}
        )
        image = self.make_image(sidecar=False)
        with mock.patch.object(mi.os, "access", return_value=False):
            result = collect(FakeMedia(image))
        self.assertEqual(result.notes, [f"File is not readable: {image}"])
        self.assertFalse([r for r in result.rows if r.section == "fileinfo"])

    def test_notes_for_missing_libraries_and_unreadable_images(self) -> None:
        """The user is told what to install, and when an image has nothing readable."""
        image = self.make_image(sidecar=False)
        with mock.patch.object(mi, "GExiv2", None):
            notes = collect(FakeMedia(image)).notes
        self.assertEqual(len(notes), 1)
        self.assertIn("GExiv2", notes[0])
        self.assertIn("sidecars", notes[0])
        del FakeExiv.PROFILES[image]
        self.assertEqual(
            collect(FakeMedia(image)).notes,
            ["No readable Exif/IPTC/XMP metadata in this image."],
        )

    def test_unreadable_sidecar(self) -> None:
        """A sidecar that cannot be read still has its file information listed."""
        image = self.make_image(sidecar=False)
        self.make_file("pic.xmp", b"junk")
        result = collect(FakeMedia(image))
        self.assertFalse([r for r in result.rows if r.section == "xmp_sidecar"])
        self.assertTrue([r for r in result.rows if r.section == "sidecar_file"])
        self.assertEqual(result.notes, ["No embedded metadata found in this file."])
        self.assertEqual(result.has_data["sidecar"], True)

    def test_pdf_with_a_sidecar(self) -> None:
        """For a PDF the sidecar is read, and the missing PDF library is mentioned."""
        pdf = self.make_file("doc.pdf", b"%PDF")
        side = self.make_file("doc.xmp")
        shutil.copy(SAMPLE_XMP, side)
        FakeExiv.PROFILES[side] = sidecar_profile(SAMPLE_XMP)
        result = collect(FakeMedia(pdf, "application/pdf"))
        self.assertTrue([r for r in result.rows if r.section == "xmp_sidecar"])
        self.assertFalse([r for r in result.rows if r.label == "Dimensions"])
        self.assertTrue(any("pypdf" in note for note in result.notes))

    def test_has_data_flags(self) -> None:
        """Tabs have data when they list anything; Current Tree when recorded."""
        bare = self.make_image(sidecar=False)
        self.assertEqual(
            collect(FakeMedia(bare)).has_data,
            {"file": True, "sidecar": False, "gramps": False},
        )
        self.assertTrue(collect(FakeMedia(bare), reference_db()).has_data["gramps"])
        self.assertTrue(
            collect(FakeMedia(bare, desc="A real title")).has_data["gramps"]
        )
        self.assertTrue(
            collect(FakeMedia(bare, date=make_date(1897))).has_data["gramps"]
        )
        self.assertTrue(
            collect(FakeMedia(bare, attrs=[FakeAttribute("Kind", "x")])).has_data[
                "gramps"
            ]
        )


# -------------------------------------------------------------------------
#
# FakeStore
#
# -------------------------------------------------------------------------
class FakeStore:
    """
    Minimal tree store: rows with children, no widgets.
    """

    def __init__(self) -> None:
        """Start empty."""
        self.nodes: dict[int, list[str]] = {}
        self.order: dict[int | None, list[int]] = {None: []}
        self.parent: dict[int, int | None] = {}
        self.last = 0

    def clear(self) -> None:
        """Remove every row."""
        self.nodes = {}
        self.order = {None: []}
        self.parent = {}
        self.last = 0

    def append(self, parent: int | None, row: list[str]) -> int:
        """Add a row below *parent* and return its iterator."""
        self.last += 1
        self.nodes[self.last] = row
        self.parent[self.last] = parent
        self.order.setdefault(parent, []).append(self.last)
        self.order.setdefault(self.last, [])
        return self.last

    def get_iter(self, path: int) -> int:
        """Return the iterator of a path (the same thing here)."""
        return path

    def get_iter_first(self) -> int | None:
        """Return the first top-level row."""
        return self.order[None][0] if self.order[None] else None

    def iter_has_child(self, tree_iter: int) -> bool:
        """Return True if the row has children."""
        return bool(self.order.get(tree_iter))

    def iter_parent(self, tree_iter: int) -> int | None:
        """Return the parent of a row."""
        return self.parent.get(tree_iter)

    def get_value(self, tree_iter: int, column: int) -> str:
        """Return a value of a row."""
        return self.nodes[tree_iter][column]

    def __getitem__(self, key: int) -> list[str]:
        """Return a row."""
        return self.nodes[key]


class FakeTree:
    """
    Minimal tree view: remembers what was expanded.
    """

    def __init__(self, store: FakeStore) -> None:
        """Remember the store."""
        self.store = store
        self.expanded_all = 0
        self.expanded: set[int] = set()
        self.collapsed: set[int] = set()
        self.columns: list[Any] = []

    def get_model(self) -> FakeStore:
        """Return the store."""
        return self.store

    def get_columns(self) -> list[Any]:
        """Return the columns."""
        return self.columns

    def expand_all(self) -> None:
        """Count a full expansion."""
        self.expanded_all += 1

    def collapse_all(self) -> None:
        """Record a full collapse."""
        self.expanded_all = -1

    def row_expanded(self, path: int) -> bool:
        """Return True if the row is expanded."""
        return path in self.expanded

    def expand_row(self, path: int, _all: bool) -> None:
        """Expand a row."""
        self.expanded.add(path)

    def collapse_row(self, path: int) -> None:
        """Collapse a row."""
        self.expanded.discard(path)
        self.collapsed.add(path)

    def get_style_context(self) -> Any:
        """Return a style context that knows the error color."""
        return types.SimpleNamespace(lookup_color=lambda _name: (True, "ERROR-COLOR"))


class FakeColumn:
    """
    A tree column that remembers its fixed width.
    """

    def __init__(self) -> None:
        """Start without a width."""
        self.width: int | None = None

    def set_fixed_width(self, width: int) -> None:
        """Remember the width."""
        self.width = width


# -------------------------------------------------------------------------
#
# GrampletTests
#
# -------------------------------------------------------------------------
class GrampletTests(InspectorTestCase):
    """
    The gramplet: tabs, markers, tree behavior, and what is highlighted.
    """

    def setUp(self) -> None:
        """Patch GLib so that idle callbacks run at once, and GTK with mocks."""
        super().setUp()
        glib = types.SimpleNamespace(
            idle_add=lambda func, *args: func(*args),
            markup_escape_text=GLib.markup_escape_text,
            Error=GLib.Error,
            format_size=GLib.format_size,
        )
        for name, value in (
            ("GLib", glib),
            ("Gtk", mock.MagicMock()),
            ("Gdk", mock.MagicMock()),
        ):
            patcher = mock.patch.object(mi, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def make_gramplet() -> Any:
        """Return a gramplet whose pages use fake stores and mock widgets."""
        inspector = mi.MetadataInspector.__new__(mi.MetadataInspector)
        inspector.pages = {}
        for tab_id, name, icon, sections in mi._TABS:
            page = mi._Page(tab_id, name, icon, sections)
            page.store = FakeStore()
            page.tree = FakeTree(page.store)
            for widget in ("scroll", "message", "tab_image", "tab_label"):
                setattr(page, widget, mock.MagicMock())
            inspector.pages[tab_id] = page
        for widget in ("note_label", "count_label", "legend_label"):
            setattr(inspector, widget, mock.MagicMock())
        inspector.uistate = "UISTATE"
        inspector._media_name = "Pic"
        inspector._media_handle = "HM"
        inspector._widths = {}
        inspector._error_rgba = None
        return inspector

    @staticmethod
    def tops(page: Any) -> list[str]:
        """Return the headings at the top of a page."""
        return [page.store[i][0] for i in page.store.order[None]]

    @staticmethod
    def leaf(page: Any, key: str) -> int:
        """Return the iterator of the item whose name or tag is *key*."""
        for tree_iter, row in page.store.nodes.items():
            if key in (
                row[mi.MetadataInspector.COL_NAME],
                row[mi.MetadataInspector.COL_TAG],
            ):
                if not page.store.iter_has_child(tree_iter):
                    return tree_iter
        raise AssertionError(f"no item {key}")

    def conflicting_result(self) -> Any:
        """Return a result where the title differs in all three sources."""
        image = self.make_image(
            {
                "Iptc.Application2.ObjectName": "File Title",
                "Exif.Photo.DateTimeOriginal": "1931:06:01 00:00:00",
            },
            {"Xmp.dc.title": 'lang="x-default" Sidecar Title'},
        )
        return collect(FakeMedia(image, desc="Gramps Title"), reference_db())

    def test_the_tabs(self) -> None:
        """There are three tabs with their icons, and each section is in one tab."""
        self.assertEqual(
            [(tab[0], tab[1], tab[2]) for tab in mi._TABS],
            [
                ("file", "File", "view-list-bullet-symbolic"),
                ("sidecar", "Sidecar", "view-list-bullet-symbolic"),
                ("gramps", "Current Tree", "gramps-viewmedia"),
            ],
        )
        sections = sorted(sum((list(tab[3]) for tab in mi._TABS), []))
        self.assertEqual(sections, sorted(section for section, _name in mi._SECTIONS))
        self.assertEqual(
            mi._TABS[0][3], ("fileinfo", "capture", "exif", "iptc", "xmp", "pdf", "av")
        )

    def test_tab_state_follows_the_gramps_convention(self) -> None:
        """A tab with data shows its icon and a bold title; an empty tab neither."""
        inspector = self.make_gramplet()
        page = inspector.pages["gramps"]
        inspector._set_tab_state(page, True)
        page.tab_image.show.assert_called_once()
        self.assertEqual(
            page.tab_label.set_markup.call_args[0][0], "<b>Current Tree</b>"
        )
        inspector._set_tab_state(page, False)
        page.tab_image.hide.assert_called_once()
        self.assertEqual(page.tab_label.set_text.call_args[0][0], "Current Tree")

    def test_sections_of_each_tab(self) -> None:
        """Each tab lists its own sections in the standard order, expanded."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        pages = inspector.pages
        self.assertEqual(self.tops(pages["file"]), ["File information", "Exif", "IPTC"])
        self.assertEqual(self.tops(pages["sidecar"]), ["Sidecar file", "XMP - sidecar"])
        self.assertEqual(
            self.tops(pages["gramps"])[:2], ["Gramps media record", "Gramps references"]
        )
        self.assertTrue(all(page.tree.expanded_all == 1 for page in pages.values()))
        for tab_id in ("file", "sidecar", "gramps"):
            self.assertTrue(pages[tab_id].tab_image.show.called, tab_id)

    def test_capture_section_comes_after_the_file_information(self) -> None:
        """Technical and Capture sits between File information and Exif."""
        image = self.make_image(
            {"Exif.Image.Make": "Canon", "Exif.Photo.FNumber": "F8"}, sidecar=False
        )
        inspector = self.make_gramplet()
        inspector._show_result(collect(FakeMedia(image)))
        page = inspector.pages["file"]
        self.assertEqual(
            self.tops(page), ["File information", "Technical & Capture", "Exif"]
        )
        capture = page.store.order[None][1]
        rows = [page.store[i] for i in page.store.order[capture]]
        self.assertEqual([r[0] for r in rows], ["Make & Model", "Exposure Settings"])
        self.assertEqual([r[1] for r in rows], ["Canon", "F8"])
        self.assertIn(
            "Technical & Capture: 2", inspector.count_label.set_text.call_args[0][0]
        )

    def test_markers_and_notes(self) -> None:
        """Preferred values get an asterisk and overridden ones a dagger."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        col = mi.MetadataInspector
        gramps = inspector.pages["gramps"]
        title = gramps.store[self.leaf(gramps, "Title")]
        self.assertEqual(
            (title[col.COL_LABEL], title[col.COL_NAME]), ("Title *", "Title")
        )
        self.assertEqual(title[col.COL_STATUS], "preferred")
        sidecar = inspector.pages["sidecar"]
        lost = sidecar.store[self.leaf(sidecar, "Xmp.dc.title")]
        self.assertTrue(lost[col.COL_LABEL].endswith(" \u2020"))
        self.assertIn(
            "Overridden by Gramps media record: Gramps Title", lost[col.COL_TIP]
        )
        file_page = inspector.pages["file"]
        iptc = file_page.store[self.leaf(file_page, "Iptc.Application2.ObjectName")]
        self.assertTrue(iptc[col.COL_LABEL].endswith(" \u2020"))

    def test_legend_only_when_something_is_marked(self) -> None:
        """The legend explains the markers, and is empty when nothing is marked."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        legend = inspector.legend_label.set_text.call_args[0][0]
        self.assertIn("*", legend)
        self.assertIn("\u2020", legend)
        image = self.make_image(
            {"Iptc.Application2.ObjectName": "Same"}, {"Xmp.dc.title": "Same"}
        )
        inspector = self.make_gramplet()
        inspector._show_result(collect(FakeMedia(image)))
        self.assertEqual(inspector.legend_label.set_text.call_args[0][0], "")

    def test_cell_style(self) -> None:
        """Bold for headings and preferred values; error color for overridden ones."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        gramps, sidecar = inspector.pages["gramps"], inspector.pages["sidecar"]
        column = types.SimpleNamespace(get_tree_view=lambda: gramps.tree)

        def style(page: Any, tree_iter: int) -> Any:
            """Return the renderer after styling one row."""
            renderer = mock.MagicMock()
            inspector.cb_cell_style(column, renderer, page.store, tree_iter, None)
            return renderer

        style(gramps, self.leaf(gramps, "Title")).set_property.assert_any_call(
            "weight", 700
        )
        lost = style(sidecar, self.leaf(sidecar, "Xmp.dc.title"))
        lost.set_property.assert_any_call("weight", 400)
        lost.set_property.assert_any_call("foreground-rgba", "ERROR-COLOR")
        style(gramps, self.leaf(gramps, "Gramps ID")).set_property.assert_any_call(
            "foreground-set", False
        )
        style(gramps, gramps.store.order[None][0]).set_property.assert_any_call(
            "weight", 700
        )

    def test_empty_tab_messages(self) -> None:
        """A tab with nothing to list says why, and has no icon."""
        image = self.make_image(sidecar=False)
        inspector = self.make_gramplet()
        inspector._show_result(collect(FakeMedia(image)))
        sidecar = inspector.pages["sidecar"]
        self.assertEqual(
            sidecar.message.set_text.call_args[0][0],
            "No XMP sidecar found. Looked for: pic.xmp, pic.jpg.xmp",
        )
        sidecar.scroll.set_visible.assert_called_with(False)
        sidecar.message.set_visible.assert_called_with(True)
        self.assertFalse(sidecar.tab_image.show.called)
        file_page = inspector.pages["file"]
        self.assertEqual(file_page.message.set_text.call_args[0][0], "")
        self.assertTrue(file_page.tab_image.show.called)

    def test_unreadable_sidecar_and_missing_file_messages(self) -> None:
        """The messages for an unreadable sidecar and for a missing file."""
        image = self.make_image(sidecar=False)
        self.make_file("pic.xmp", b"junk")
        inspector = self.make_gramplet()
        inspector._show_result(collect(FakeMedia(image)))
        self.assertEqual(
            inspector.pages["sidecar"].message.set_text.call_args[0][0],
            "The XMP sidecar has no readable metadata.",
        )
        self.assertEqual(self.tops(inspector.pages["sidecar"]), ["Sidecar file"])
        self.assertTrue(inspector.pages["sidecar"].tab_image.show.called)
        inspector = self.make_gramplet()
        inspector._show_result(collect(FakeMedia(os.path.join(self.tmp, "gone.jpg"))))
        self.assertEqual(
            inspector.pages["file"].message.set_text.call_args[0][0],
            "The file is not available.",
        )
        self.assertIn("File not found", inspector.note_label.set_text.call_args[0][0])
        self.assertFalse(inspector.pages["file"].tab_image.show.called)
        self.assertEqual(
            mi.MetadataInspector._empty_message(
                inspector.pages["gramps"],
                types.SimpleNamespace(rows=[], sidecar_names=()),
            ),
            "Nothing is recorded in the current tree for this media object.",
        )

    def test_double_click_opens_the_dialog(self) -> None:
        """An item opens the detail dialog with everything it needs."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        page = inspector.pages["gramps"]
        with mock.patch.object(mi, "MetadataDialog") as dialog:
            inspector.cb_row_activated(page.tree, self.leaf(page, "Title"), None)
            inspector.cb_row_activated(page.tree, self.leaf(page, "Title"), None)
        args, kwargs = dialog.call_args_list[0]
        uistate, track, key, label, value, location, tag, desc = args
        self.assertEqual((tag, desc), ("", ""))
        self.assertEqual(
            (uistate, track, label, value), ("UISTATE", [], "Title", "Gramps Title")
        )
        self.assertEqual(location, "Gramps media record")
        self.assertTrue(key.startswith("metadatainspector-HM-"))
        self.assertIn("Preferred value. Other sources differ:", kwargs["note"])
        self.assertEqual(kwargs["media_name"], "Pic")
        self.assertEqual(dialog.call_args_list[1][0][2], key)

    def test_double_click_on_a_heading_toggles_it(self) -> None:
        """A heading expands and collapses instead of opening a dialog."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        page = inspector.pages["gramps"]
        heading = page.store.order[None][0]
        with mock.patch.object(mi, "MetadataDialog") as dialog:
            inspector.cb_row_activated(page.tree, heading, None)
            self.assertIn(heading, page.tree.expanded)
            inspector.cb_row_activated(page.tree, heading, None)
        self.assertIn(heading, page.tree.collapsed)
        dialog.assert_not_called()

    def test_an_open_dialog_is_not_opened_twice(self) -> None:
        """The error for an already open dialog is not shown to the user."""
        inspector = self.make_gramplet()
        inspector._show_result(self.conflicting_result())
        page = inspector.pages["gramps"]
        with mock.patch.object(
            mi, "MetadataDialog", side_effect=WindowActiveError("open")
        ):
            inspector.cb_row_activated(page.tree, self.leaf(page, "Title"), None)

    def test_expand_and_collapse_act_on_their_own_tab(self) -> None:
        """The context menu actions use the tree they were opened on."""
        inspector = self.make_gramplet()
        sidecar, gramps = (
            inspector.pages["sidecar"].tree,
            inspector.pages["gramps"].tree,
        )
        inspector.cb_open_all_nodes(None, sidecar)
        inspector.cb_close_all_nodes(None, gramps)
        self.assertEqual((sidecar.expanded_all, gramps.expanded_all), (1, -1))

    def test_column_widths(self) -> None:
        """The columns take 40%, 40% and 20% of the width, separately for each tree."""
        inspector = self.make_gramplet()
        file_tree, gramps_tree = (
            inspector.pages["file"].tree,
            inspector.pages["gramps"].tree,
        )
        file_tree.columns = [FakeColumn() for _ in range(3)]
        gramps_tree.columns = [FakeColumn() for _ in range(3)]

        def widths(tree: Any) -> list[int | None]:
            """Return the widths of the columns of a tree."""
            return [column.width for column in tree.columns]

        inspector.cb_tree_size_allocate(file_tree, types.SimpleNamespace(width=1000))
        self.assertEqual(widths(file_tree), [400, 400, 200])
        inspector.cb_tree_size_allocate(file_tree, types.SimpleNamespace(width=777))
        self.assertEqual(sum(widths(file_tree)), 777)
        file_tree.columns[0].width = 123  # the user drags a border
        inspector.cb_tree_size_allocate(file_tree, types.SimpleNamespace(width=777))
        self.assertEqual(file_tree.columns[0].width, 123)
        inspector.cb_tree_size_allocate(file_tree, types.SimpleNamespace(width=50))
        self.assertEqual(file_tree.columns[0].width, 123)
        inspector.cb_tree_size_allocate(gramps_tree, types.SimpleNamespace(width=500))
        self.assertEqual(widths(gramps_tree), [200, 200, 100])

    def test_the_error_color_comes_from_the_theme(self) -> None:
        """The color for overridden values is read once from the theme."""
        inspector = self.make_gramplet()
        tree = inspector.pages["file"].tree
        self.assertEqual(inspector._get_error_rgba(tree), "ERROR-COLOR")
        tree.get_style_context = None  # a second lookup would fail
        self.assertEqual(inspector._get_error_rgba(tree), "ERROR-COLOR")

    def test_copy_puts_text_on_the_clipboard(self) -> None:
        """Copy value and Copy tag name use the clipboard."""
        inspector = self.make_gramplet()
        inspector.cb_copy(None, "some text")
        clipboard = mi.Gtk.Clipboard.get.return_value
        clipboard.set_text.assert_called_once_with("some text", -1)

    def run_main(self, media: Any, db: Any = None) -> Any:
        """Run main() for a media object and return the gramplet."""
        inspector = self.make_gramplet()
        inspector.dbstate = types.SimpleNamespace(
            db=types.SimpleNamespace(get_media_from_handle=lambda _handle: media)
        )
        inspector.get_active = lambda _navtype: "HM"
        inspector.set_has_data = mock.MagicMock()
        mi.MetadataInspector.main(inspector)
        return inspector

    def test_gramplet_tab_is_highlighted_only_for_real_metadata(self) -> None:
        """The gramplet tab in the Gramps bar is bold for metadata, not just a file."""
        bare = self.make_image(sidecar=False)
        inspector = self.run_main(FakeMedia(bare))
        self.assertFalse(inspector.set_has_data.call_args_list[-1][0][0])
        self.assertTrue(inspector.pages["file"].tab_image.show.called)
        self.assertFalse(inspector.get_has_data(FakeMedia(bare)))
        tagged = self.make_image({"Iptc.Application2.ObjectName": "T"}, sidecar=False)
        inspector = self.run_main(FakeMedia(tagged))
        self.assertTrue(inspector.set_has_data.call_args_list[-1][0][0])
        self.assertTrue(inspector.get_has_data(FakeMedia(tagged)))
        sidecar_only = self.make_image(None, {"Xmp.dc.title": "From the sidecar"})
        self.assertTrue(
            self.run_main(FakeMedia(sidecar_only)).set_has_data.call_args_list[-1][0][0]
        )
        self.assertFalse(inspector.get_has_data(None))

    def test_main_without_a_media_object(self) -> None:
        """Without an active media object the display says so and is empty."""
        inspector = self.make_gramplet()
        inspector.get_active = lambda _navtype: ""
        inspector.set_has_data = mock.MagicMock()
        mi.MetadataInspector.main(inspector)
        self.assertEqual(
            inspector.note_label.set_text.call_args[0][0],
            "Select a media object to view its metadata.",
        )
        inspector.set_has_data.assert_called_with(False)
        self.assertEqual(self.tops(inspector.pages["file"]), [])

    def test_update_has_data_while_hidden(self) -> None:
        """The highlight is kept right while the gramplet is not visible."""
        tagged = self.make_image({"Iptc.Application2.ObjectName": "T"}, sidecar=False)
        inspector = self.make_gramplet()
        inspector.dbstate = types.SimpleNamespace(
            db=types.SimpleNamespace(
                get_media_from_handle=lambda _handle: FakeMedia(tagged)
            )
        )
        inspector.set_has_data = mock.MagicMock()
        inspector.get_active = lambda _navtype: "HM"
        inspector.update_has_data()
        inspector.set_has_data.assert_called_with(True)
        inspector.get_active = lambda _navtype: ""
        inspector.update_has_data()
        inspector.set_has_data.assert_called_with(False)


# -------------------------------------------------------------------------
#
# DialogTests
#
# -------------------------------------------------------------------------
class DialogTests(InspectorTestCase):
    """
    The read-only dialog, which is a managed window listed in the Windows menu.
    """

    def setUp(self) -> None:
        """Patch GTK with a mock so that no widget is created."""
        super().setUp()
        patcher = mock.patch.object(mi, "Gtk", mock.MagicMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def open_dialog(
        key: str = "k1", label: str = "Copyright Notice", media: str = "Pic"
    ) -> Any:
        """Open a dialog for one item."""
        return mi.MetadataDialog(
            "UISTATE",
            [],
            key,
            label,
            "value",
            "File > Exif > Image",
            "Exif.Image.Copyright",
            "description",
            media_name=media,
            note="Overridden by File: x",
        )

    def test_it_is_listed_in_the_windows_menu(self) -> None:
        """The dialog is registered with a label naming the item and the media."""
        dialog = self.open_dialog()
        self.assertIn("k1", FakeManagedWindow.registry)
        self.assertEqual(dialog.menu_label, "Metadata: Copyright Notice (Pic)")
        self.assertIsNone(dialog.submenu_label)
        self.assertEqual(dialog.window_id, "k1")
        self.assertEqual(dialog.title_text, "Metadata: Copyright Notice")
        self.assertTrue(dialog.shown)
        self.assertEqual((dialog.uistate, dialog.track), ("UISTATE", []))

    def test_without_a_media_name(self) -> None:
        """The menu label has no name, and no name label is added to the buttons."""
        dialog = self.open_dialog("k2", "Size", media="")
        self.assertEqual(dialog.menu_label, "Metadata: Size")
        self.assertFalse(dialog.window.get_action_area.called)

    def test_the_same_item_is_not_opened_twice(self) -> None:
        """Opening an open item raises WindowActiveError and presents the dialog."""
        first = self.open_dialog()
        with self.assertRaises(WindowActiveError):
            self.open_dialog()
        self.assertEqual(first.presented, 1)
        self.assertEqual(len(FakeManagedWindow.registry), 1)
        self.open_dialog("k2", "Creator")
        self.assertEqual(sorted(FakeManagedWindow.registry), ["k1", "k2"])

    def test_closing(self) -> None:
        """The Close button removes the dialog from the menu; other responses do not."""
        first = self.open_dialog()
        second = self.open_dialog("k2", "Creator")
        first.cb_response(None, mi.Gtk.ResponseType.CLOSE)
        self.assertEqual(sorted(FakeManagedWindow.registry), ["k2"])
        self.assertEqual(first.closed, 1)
        second.cb_response(None, mi.Gtk.ResponseType.DELETE_EVENT)
        self.assertEqual(second.closed, 0)
        second.window.connect.assert_any_call("delete-event", second.close)

    def test_media_name_label_is_not_collapsed(self) -> None:
        """A short name keeps its own width and is not ellipsized; a long one is."""
        label = mock.MagicMock()
        mi.Gtk.Label.return_value = label
        self.open_dialog(media="Grandpa portrait")
        label.set_width_chars.assert_any_call(len("Grandpa portrait"))
        label.set_ellipsize.assert_not_called()
        label.reset_mock()
        FakeManagedWindow.registry.clear()
        self.open_dialog(media="A" * 90)
        label.set_width_chars.assert_any_call(40)
        label.set_max_width_chars.assert_any_call(40)
        label.set_ellipsize.assert_called()

    def test_media_name_sits_at_the_left_of_the_buttons(self) -> None:
        """The name is a secondary, non-homogeneous child of the button box."""
        dialog = self.open_dialog()
        action_area = dialog.window.get_action_area.return_value
        action_area.set_child_secondary.assert_called_once()
        action_area.set_child_non_homogeneous.assert_called_once()

    def test_details_include_the_sources(self) -> None:
        """The Details page lists the section, tag, description and sources."""
        captions: list[str] = []
        mi.Gtk.Label.side_effect = record_labels(captions)
        self.open_dialog()
        for text in (
            "Section:",
            "Tag:",
            "Description:",
            "Sources:",
            "Overridden by File: x",
        ):
            self.assertIn(text, captions)


# -------------------------------------------------------------------------
#
# BrokenExiv
#
# -------------------------------------------------------------------------
class BrokenExiv(FakeExiv):
    """
    GExiv2 stand-in whose methods named in *failing* raise GLib.Error.
    """

    failing: tuple[str, ...] = ()

    def _check(self, name: str) -> None:
        """Raise like GExiv2 does when a call fails."""
        if name in self.failing:
            raise GLib.Error(f"{name} failed")

    def has_tag(self, key: str) -> bool:
        """Return True if the tag exists, or fail."""
        self._check("has_tag")
        return super().has_tag(key)

    def get_tag_type(self, key: str) -> str:
        """Return the value type, or fail."""
        self._check("get_tag_type")
        return super().get_tag_type(key)

    def get_tag_description(self, key: str) -> str:
        """Return the description, or fail."""
        self._check("get_tag_description")
        return super().get_tag_description(key)

    def get_tag_label(self, key: str) -> str | None:
        """Return the label, or fail."""
        self._check("get_tag_label")
        return super().get_tag_label(key)

    def get_xmp_tags(self) -> list[str]:
        """Return the XMP tags, or fail."""
        self._check("get_xmp_tags")
        return super().get_xmp_tags()


# -------------------------------------------------------------------------
#
# ErrorPathTests
#
# -------------------------------------------------------------------------
class ErrorPathTests(InspectorTestCase):
    """
    Failures of the libraries and of the database give safe results, never a crash.
    """

    @staticmethod
    def broken(*failing: str, tags: dict[str, str] | None = None) -> BrokenExiv:
        """Return a fake GExiv2 that fails in the named methods."""
        meta = BrokenExiv()
        meta.profile = exiv_profile(tags or {"Exif.Image.Make": "Canon"})
        meta.failing = failing
        return meta

    def test_a_failing_tag_lookup(self) -> None:
        """A tag that cannot be read is empty."""
        meta = self.broken("has_tag")
        self.assertEqual(mi._raw(meta, "Exif.Image.Make"), "")
        self.assertEqual(mi._tag_full(meta, "Exif.Image.Make"), "")

    def test_a_failing_description_lookup(self) -> None:
        """A tag without a readable description has none."""
        self.assertEqual(
            mi._describe(self.broken("get_tag_description"), "Exif.Image.Make"), ""
        )

    def test_a_failing_type_lookup_reads_plain_text(self) -> None:
        """When the type cannot be asked, an XMP tag is read as plain text."""
        meta = self.broken("get_tag_type", tags={"Xmp.xmp.CreatorTool": "Tool"})
        self.assertIsNone(mi._tag_values(meta, "Xmp.xmp.CreatorTool"))
        self.assertEqual(mi._tag_full(meta, "Xmp.xmp.CreatorTool"), "Tool")

    def test_a_failing_tag_list(self) -> None:
        """A list of tags that cannot be read is empty."""
        meta = self.broken("get_xmp_tags")
        self.assertEqual(mi._tag_rows(meta, "xmp", meta.get_xmp_tags), [])

    def test_a_failing_label_lookup(self) -> None:
        """Without a label the last part of the tag is the name."""
        meta = self.broken("get_tag_label", tags={"Exif.Image.Make": "Canon"})
        rows = mi._tag_rows(meta, "exif", meta.get_exif_tags)
        self.assertEqual([row.label for row in rows], ["Make"])

    def test_impossible_dates(self) -> None:
        """A date that Gramps cannot represent is not shown and not compared."""
        with mock.patch.object(mi, "Date", side_effect=ValueError("impossible")):
            self.assertEqual(mi._format_ymd_hms(1931, 2, 31), "")
            self.assertIsNone(mi._date_key_from_text("1931-02-31"))

    def test_a_date_that_is_not_a_date(self) -> None:
        """Something without the methods of a Date cannot be compared."""
        self.assertIsNone(mi._gramps_date_key(object()))

    def test_gexiv2_failing_in_an_unexpected_way(self) -> None:
        """A binding problem when opening a file gives no metadata, not a crash."""

        def broken_metadata() -> Any:
            """Raise like a mismatched binding."""
            raise TypeError("binding problem")

        broken = types.SimpleNamespace(Metadata=broken_metadata)
        with mock.patch.object(mi, "GExiv2", broken):
            with self.assertLogs(mi.LOG, level="ERROR") as logs:
                result = mi._open_metadata(self.make_file("pic.jpg"))
        self.assertIsNone(result)
        self.assertIn("could not read metadata", logs.output[0])

    def test_an_unreadable_image_header(self) -> None:
        """An image whose header cannot be read has no size."""

        class Failing:
            """GdkPixbuf that cannot read the file."""

            class Pixbuf:
                """Fake GdkPixbuf.Pixbuf."""

                @staticmethod
                def get_file_info(_path: str) -> Any:
                    """Raise like an unreadable file."""
                    raise GLib.Error("unreadable")

        with mock.patch.object(mi, "GdkPixbuf", Failing):
            self.assertIsNone(mi._image_size("x.jpg"))

    def test_object_names(self) -> None:
        """Each kind of object that can hold a media reference has a display name."""
        event = types.SimpleNamespace(
            get_description=lambda: "",
            get_type=lambda: "Birth",
            get_gramps_id=lambda: "E1",
        )
        described = types.SimpleNamespace(
            get_description=lambda: "Baptism",
            get_type=lambda: "Baptism",
            get_gramps_id=lambda: "E2",
        )
        cases = [
            ("Person", types.SimpleNamespace(name="Ann Example"), "Ann Example"),
            (
                "Family",
                types.SimpleNamespace(name="Example / Sample"),
                "Example / Sample",
            ),
            ("Event", event, "Birth"),
            ("Event", described, "Baptism"),
            ("Place", types.SimpleNamespace(name="Springfield"), "Springfield"),
            ("Source", types.SimpleNamespace(get_title=lambda: "Census"), "Census"),
            ("Citation", types.SimpleNamespace(get_page=lambda: "Page 3"), "Page 3"),
            ("Note", types.SimpleNamespace(), ""),
        ]
        for class_name, obj, expected in cases:
            with self.subTest(class_name=class_name, expected=expected):
                self.assertEqual(mi._object_name(None, class_name, obj), expected)

    def test_a_name_that_cannot_be_built(self) -> None:
        """The reference is still listed, as (no name), when the name fails."""
        failing = types.SimpleNamespace(
            display=mock.Mock(side_effect=mi.HandleError("gone"))
        )
        with mock.patch.object(mi, "name_displayer", failing):
            rows = mi._reference_rows(reference_db(), FakeMedia("x.jpg"), None)
        self.assertEqual(rows[0].label, "(no name) [I01]")

    def test_a_failing_getter(self) -> None:
        """An object that the database cannot supply is None."""

        class Db:
            """Database whose getter fails."""

            @staticmethod
            def get_note_from_handle(_handle: str) -> Any:
                """Raise like a stale handle."""
                raise mi.HandleError("gone")

        self.assertIsNone(mi._safe_get(Db(), "get_note_from_handle", "N1"))
        self.assertIsNone(mi._safe_get(Db(), "get_tag_from_handle", "T1"))

    def test_a_reference_to_a_missing_object_is_skipped(self) -> None:
        """A back-reference whose object cannot be found is left out."""
        db = reference_db()
        db.links.append(("Person", "ghost"))
        rows = mi._reference_rows(db, FakeMedia("x.jpg"), None)
        self.assertEqual(len(rows), 5)

    def test_an_audio_file(self) -> None:
        """Audio tags are listed, with a note if the library is missing."""
        audio = self.make_file("song.mp3")
        self.assertTrue(
            any(
                "mutagen" in note
                for note in collect(FakeMedia(audio, "audio/mpeg")).notes
            )
        )
        reader = types.SimpleNamespace(
            File=lambda _path, easy=True: types.SimpleNamespace(
                info=types.SimpleNamespace(length=61), tags={"title": ["Song"]}
            )
        )
        with mock.patch.object(mi, "mutagen", reader):
            result = collect(FakeMedia(audio, "audio/mpeg"))
        self.assertEqual(
            {
                (row.group, row.label, row.full)
                for row in result.rows
                if row.section == "av"
            },
            {("Stream", "Duration", "1:01"), ("Tags", "title", "Song")},
        )
        self.assertEqual(result.notes, [])


# -------------------------------------------------------------------------
#
# OptionalLibraryTests
#
# -------------------------------------------------------------------------
class OptionalLibraryTests(InspectorTestCase):
    """
    The readers are optional: a missing library is not an error.
    """

    def test_first_available_module(self) -> None:
        """The first module that can be imported is used; none gives None."""
        json_module = importlib.import_module("json")
        self.assertIs(mi._optional_module("no_such_module_here", "json"), json_module)
        self.assertIsNone(mi._optional_module("no_such_module_here", "nor_this_one"))

    def test_error_classes_of_a_library(self) -> None:
        """Only real exception classes are returned; a missing library gives none."""

        class LibraryError(Exception):
            """Error of a fake library."""

        library = types.SimpleNamespace(
            errors=types.SimpleNamespace(PyPdfError=LibraryError, NotAnError="text")
        )
        self.assertEqual(
            mi._error_classes(library, "errors.PyPdfError"), (LibraryError,)
        )
        self.assertEqual(
            mi._error_classes(library, "errors.NotAnError", "errors.Missing"), ()
        )
        self.assertEqual(mi._error_classes(None, "errors.PyPdfError"), ())

    def test_a_single_audio_tag_value(self) -> None:
        """A tag whose value is a plain string rather than a list is listed too."""
        audio = types.SimpleNamespace(info=None, tags={"title": "Single"})
        reader = types.SimpleNamespace(File=lambda _path, easy=True: audio)
        with mock.patch.object(mi, "mutagen", reader):
            rows = mi._read_av("x.mp3")[0]
        self.assertEqual([(row.label, row.full) for row in rows], [("title", "Single")])


# -------------------------------------------------------------------------
#
# WidgetBuildingTests
#
# -------------------------------------------------------------------------
class WidgetBuildingTests(InspectorTestCase):
    """
    The widgets are assembled as designed (GTK is a mock, so nothing is drawn).
    """

    def setUp(self) -> None:
        """Patch GTK with a mock."""
        super().setUp()
        patcher = mock.patch.object(mi, "Gtk", mock.MagicMock())
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def blank_gramplet() -> Any:
        """Return a gramplet without pages, as it is before init()."""
        inspector = mi.MetadataInspector.__new__(mi.MetadataInspector)
        inspector.pages = {}
        return inspector

    def test_the_notebook_has_three_tabs_with_icons(self) -> None:
        """Each tab label has its icon at menu size, and the pages are in order."""
        inspector = self.blank_gramplet()
        inspector._build_gui()
        self.assertEqual(list(inspector.pages), ["file", "sidecar", "gramps"])
        icons = [call.args for call in mi.Gtk.Image.new_from_icon_name.call_args_list]
        self.assertEqual(
            icons,
            [
                ("view-list-bullet-symbolic", mi.Gtk.IconSize.MENU),
                ("view-list-bullet-symbolic", mi.Gtk.IconSize.MENU),
                ("gramps-viewmedia", mi.Gtk.IconSize.MENU),
            ],
        )
        notebook = mi.Gtk.Notebook.return_value
        self.assertEqual(notebook.append_page.call_count, 3)
        mi.Gtk.TreeStore.assert_called_with(*([str] * 9))

    def test_the_tree_columns_and_signals(self) -> None:
        """Name, Value and Tag columns; fixed width; the three signals are connected."""
        inspector = self.blank_gramplet()
        store = mock.MagicMock()
        tree = inspector._build_tree(store)
        titles = [call.args[0] for call in mi.Gtk.TreeViewColumn.call_args_list]
        self.assertEqual(titles, ["Name", "Value", "Tag"])
        column = mi.Gtk.TreeViewColumn.return_value
        column.set_sizing.assert_called_with(mi.Gtk.TreeViewColumnSizing.FIXED)
        self.assertEqual(
            column.set_cell_data_func.call_count, 2
        )  # not for the Tag column
        tree.set_tooltip_column.assert_called_with(mi.MetadataInspector.COL_TIP)
        for signal, handler in (
            ("button-press-event", inspector.cb_button_press),
            ("row-activated", inspector.cb_row_activated),
            ("size-allocate", inspector.cb_tree_size_allocate),
        ):
            tree.connect.assert_any_call(signal, handler)
        self.assertEqual(tree.append_column.call_count, 3)

    def test_init_replaces_the_text_view_and_hides_the_icons(self) -> None:
        """init() puts the notebook in the gramplet and starts with no icons."""
        inspector = self.blank_gramplet()
        container = mock.MagicMock()
        inspector.gui = types.SimpleNamespace(
            get_container_widget=lambda: container, textview="TEXTVIEW"
        )
        inspector.init()
        container.remove.assert_called_once_with("TEXTVIEW")
        container.add.assert_called_once()
        self.assertEqual(list(inspector.pages), ["file", "sidecar", "gramps"])
        for page in inspector.pages.values():
            page.tab_image.hide.assert_called()
        self.assertIsNone(inspector._media_handle)

    def test_signals_and_active_media(self) -> None:
        """The gramplet refreshes when media objects change or the selection does."""
        inspector = self.blank_gramplet()
        inspector.dbstate = types.SimpleNamespace(db="DB")
        inspector.connect = mock.MagicMock()
        inspector.connect_signal = mock.MagicMock()
        inspector.update = mock.MagicMock()
        inspector.db_changed()
        signals = [call.args[1] for call in inspector.connect.call_args_list]
        self.assertEqual(
            signals, ["media-add", "media-update", "media-delete", "media-rebuild"]
        )
        inspector.connect_signal.assert_called_once_with("Media", inspector.update)
        inspector.active_changed("H1")
        inspector.update.assert_called_once()

    def test_context_menu_over_an_item(self) -> None:
        """Right-click on an item offers the copy items, then expand and collapse."""
        inspector = self.blank_gramplet()
        store = FakeStore()
        item = store.append(
            None, ["Title", "v", "Xmp.dc.title", "", "full value", "", "", "", "Title"]
        )
        tree = mock.MagicMock()
        tree.get_model.return_value = store
        tree.get_path_at_pos.return_value = (item, None, 0, 0)
        event = types.SimpleNamespace(button=3, x=1.0, y=2.0)
        self.assertTrue(inspector.cb_button_press(tree, event))
        labels = [call.kwargs["label"] for call in mi.Gtk.MenuItem.call_args_list]
        self.assertEqual(
            labels,
            ["Copy value", "Copy tag name", "Expand all Nodes", "Collapse all Nodes"],
        )
        mi.Gtk.Menu.return_value.popup_at_pointer.assert_called_once_with(event)
        mi.Gtk.SeparatorMenuItem.assert_called_once()

    def test_context_menu_over_empty_space_and_other_buttons(self) -> None:
        """Empty space offers only expand and collapse; other buttons do nothing."""
        inspector = self.blank_gramplet()
        tree = mock.MagicMock()
        tree.get_path_at_pos.return_value = None
        self.assertTrue(
            inspector.cb_button_press(
                tree, types.SimpleNamespace(button=3, x=0.0, y=0.0)
            )
        )
        labels = [call.kwargs["label"] for call in mi.Gtk.MenuItem.call_args_list]
        self.assertEqual(labels, ["Expand all Nodes", "Collapse all Nodes"])
        self.assertFalse(
            inspector.cb_button_press(
                tree, types.SimpleNamespace(button=1, x=0.0, y=0.0)
            )
        )

    def test_context_menu_skips_what_is_empty(self) -> None:
        """An item with no tag offers only Copy value."""
        inspector = self.blank_gramplet()
        store = FakeStore()
        item = store.append(
            None, ["Name", "v", "", "", "full value", "", "", "", "Name"]
        )
        tree = mock.MagicMock()
        tree.get_model.return_value = store
        tree.get_path_at_pos.return_value = (item, None, 0, 0)
        inspector.cb_button_press(tree, types.SimpleNamespace(button=3, x=0.0, y=0.0))
        labels = [call.kwargs["label"] for call in mi.Gtk.MenuItem.call_args_list]
        self.assertEqual(labels[0], "Copy value")
        self.assertNotIn("Copy tag name", labels)

    def test_the_details_page_skips_empty_items(self) -> None:
        """Only the items that have text are listed on the Details page."""
        captions: list[str] = []
        mi.Gtk.Label.side_effect = record_labels(captions)
        mi.MetadataDialog._build_details("File > Exif", "", "", "")
        self.assertIn("Section:", captions)
        self.assertNotIn("Tag:", captions)
        self.assertNotIn("Sources:", captions)

    def test_idle_callback_without_a_pending_width(self) -> None:
        """The idle callback does nothing when there is no new width, and runs once."""
        inspector = self.blank_gramplet()
        inspector._widths = {}
        self.assertFalse(inspector.cb_apply_column_widths(mock.MagicMock()))

    def test_main_when_the_media_object_is_gone(self) -> None:
        """If the active handle has no media object the display stays empty."""
        inspector = GrampletTests.make_gramplet()
        inspector.dbstate = types.SimpleNamespace(
            db=types.SimpleNamespace(get_media_from_handle=lambda _handle: None)
        )
        inspector.get_active = lambda _navtype: "HM"
        inspector.set_has_data = mock.MagicMock()
        mi.MetadataInspector.main(inspector)
        self.assertEqual(inspector._media_name, "")
        inspector.set_has_data.assert_called_once_with(False)


if __name__ == "__main__":
    unittest.main()
