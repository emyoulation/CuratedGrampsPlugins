#
# importvcard_enh.py — Enhanced vCard importer for Gramps
#
# Supports vCard versions 1, 2.1, 3.0, 4.0.
# Unhandled properties are stored as Person attributes of type
# "vCard <version> source" so no data is silently lost.
# Variant Call Format (.vcf DNA) files are detected early and rejected
# with a clear alert rather than a confusing parse error.
#
# Based on the Gramps built-in importvcard.py (RFC 2426).
# Original authors: Martin Hawlisch, Donald N. Allingham,
#                   Brian G. Matherly, Michiel D. Nauta.
# Enhanced by: Claude (Anthropic, claude-sonnet-4-6) for GEPS 048.
# 2026 revision: Claude (Anthropic, Claude Opus 5.5) — embedded media
#   to Media objects, RELATED to Associations, mapping of every vCard
#   property that has a Gramps database destination.
#
# License: GPL v2 or later — see <https://www.gnu.org/licenses/>.
#

"""Import from vCard (RFC 6350 / RFC 6474 / RFC 2426 / vCard 2.1 / 1.0)"""

# ── Standard library ──────────────────────────────────────────────────
import base64
import hashlib
import logging
import mimetypes
import os
import re
import time
from functools import partial
from urllib.parse import unquote_to_bytes, urlparse
from urllib.request import url2pathname

LOG = logging.getLogger(".ImportvCardEnh")

# ── Gramps modules ────────────────────────────────────────────────────
from gramps.gen.const import GRAMPS_LOCALE as glocale

_ = glocale.translation.gettext
ngettext = glocale.translation.ngettext

from gramps.gen.errors import GrampsImportError
from gramps.gen.lib import (
    Address,
    Attribute,
    AttributeType,
    Date,
    DateError,
    ChildRef,
    Event,
    EventRef,
    EventRoleType,
    EventType,
    Family,
    FamilyRelType,
    Media,
    MediaRef,
    Name,
    NameType,
    Note,
    NoteType,
    Person,
    PersonRef,
    Place,
    PlaceName,
    PlaceType,
    Surname,
    Tag,
    Url,
    UrlType,
)
from gramps.gen.db import DbTxn
from gramps.gen.display.name import displayer as _nd
from gramps.gen.display.place import displayer as _pd
from gramps.gen.mime import get_type
from gramps.gen.plug.utils import OpenFileOrStdin
from gramps.gen.utils.file import create_checksum, media_path, relative_path
from gramps.gen.utils.libformatting import ImportInfo

# ── VCF DNA detection ────────────────────────────────────────────────
# Variant Call Format files start with "##fileformat=VCFv" (case-sens.).
_VCF_DNA_MAGIC = b"##fileformat=VCF"

# Name of the folder (created beside the imported .vcf) that receives
# images and sounds embedded in the vCards.
MEDIA_SUBFOLDER = "media"

# Name given to vCards that have no N, FN or ORG property.
PLACEHOLDER_GIVEN = _("unidentified")
PLACEHOLDER_SURNAME = _("vCard Import")

# Properties that carry no person data; a vCard holding only these is empty.
_NO_DATA_PROPS = ("BEGIN", "END", "VERSION", "PRODID")

# Lines longer than this are shortened when a vCard is quoted in the report
# (embedded photos would otherwise flood it).
_CHUNK_LINE_MAX = 100


def _is_vcf_dna(filename):
    """Return True if the file looks like a Variant Call Format DNA file."""
    try:
        with open(filename, "rb") as fh:
            header = fh.read(32)
        return header.startswith(_VCF_DNA_MAGIC)
    except OSError:
        return False


# ── Public entry point ────────────────────────────────────────────────


def importData(database, filename, user):
    """Function called by Gramps to import data on persons in vCard format."""
    if _is_vcf_dna(filename):
        user.notify_error(
            _("Cannot import this .vcf file"),
            _(
                "This file appears to be a Variant Call Format (VCF) file "
                "used for DNA / genomic data, not a vCard contact file.\n\n"
                "Gramps cannot import DNA VCF files. Please use a "
                "bioinformatics tool to process this file."
            ),
        )
        return

    parser = VCardEnhancedParser(database, filename)
    try:
        if filename == "-":
            with OpenFileOrStdin(filename) as fh:
                parser.parse(fh, user)
        else:
            with open(filename, encoding="utf-8", errors="replace") as fh:
                parser.parse(fh, user)
    except EnvironmentError as msg:
        user.notify_error(_("%s could not be opened\n") % filename, str(msg))
        return
    except GrampsImportError as msg:
        user.notify_error(_("%s could not be opened\n") % filename, str(msg))
        return
    return ImportInfo({_("Results"): _("done")})


# ── Helper functions (unchanged from built-in) ────────────────────────


def splitof_nameprefix(name):
    """Return (prefix, Surname) by splitting on first uppercase char."""
    look_for_capital = False
    for i, char in enumerate(name):
        if look_for_capital:
            if char.isupper():
                return (name[:i].rstrip(), name[i:])
            else:
                look_for_capital = False
        if not char.isalpha():
            look_for_capital = True
    return ("", name)


def fitin(prototype, receiver, element):
    """Return index in receiver where element should be inserted to match prototype."""
    receiver_idx = 0
    receiver_chunks = receiver.split()
    element_idx = prototype.index(element)
    i = 0
    idx = prototype.find(receiver_chunks[i])
    while idx < element_idx:
        if idx == -1:
            return -1
        receiver_idx += len(receiver_chunks[i]) + 1
        i += 1
        idx = prototype.find(receiver_chunks[i])
    return receiver_idx


# ── Per-version quirks registry ───────────────────────────────────────

_VERSION_QUIRKS = {
    "1.0": {"strict_n_fields": False},
    "2.1": {"strict_n_fields": False},
    "3.0": {"strict_n_fields": True},
    "4.0": {"strict_n_fields": True},
}
_DEFAULT_QUIRKS = _VERSION_QUIRKS["3.0"]


# ── Property → destination tables ─────────────────────────────────────

# Binary-capable properties that become Media objects.
_MEDIA_PROPS = {
    "PHOTO": _("photo"),
    "LOGO": _("logo"),
    "SOUND": _("sound"),
}

# TYPE hints (vCard 2.1/3.0) → MIME type.
_TYPE_HINT_MIME = {
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "GIF": "image/gif",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "TIF": "image/tiff",
    "WEBP": "image/webp",
    "WAVE": "audio/wav",
    "WAV": "audio/wav",
    "MP3": "audio/mpeg",
    "MPEG": "audio/mpeg",
    "OGG": "audio/ogg",
    "AIFF": "audio/aiff",
}

# Magic bytes → file extension (more reliable than TYPE= claims).
_MAGIC_EXT = [
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"BM", ".bmp"),
    (b"II*\x00", ".tif"),
    (b"MM\x00*", ".tif"),
    (b"ID3", ".mp3"),
    (b"OggS", ".ogg"),
]

# Instant-messaging properties → Url (custom type "Instant Messaging").
# Value is the protocol label used as the Url description.
_IM_PROPS = {
    "IMPP": "",
    "X-AIM": "AIM",
    "X-ICQ": "ICQ",
    "X-JABBER": "Jabber",
    "X-MSN": "MSN",
    "X-YAHOO": "Yahoo",
    "X-SKYPE": "Skype",
    "X-SKYPE-USERNAME": "Skype",
    "X-GOOGLE-TALK": "Google Talk",
    "X-GTALK": "Google Talk",
    "X-QQ": "QQ",
    "X-GADUGADU": "Gadu-Gadu",
}

# Other URI properties → Url with a custom type label.
_URL_PROPS = {
    "FBURL": _("Free/Busy"),
    "CALURI": _("Calendar"),
    "CALADRURI": _("Calendar address"),
    "SOCIALPROFILE": _("Social Profile"),
    "X-SOCIALPROFILE": _("Social Profile"),
    "X-TWITTER": _("Social Profile"),
}

# Vendor extensions that express a relationship → RELATED TYPE.
_RELATED_ALIASES = {
    "AGENT": "agent",
    "X-SPOUSE": "spouse",
    "X-EVOLUTION-SPOUSE": "spouse",
    "X-KADDRESSBOOK-X-SPOUSESNAME": "spouse",
    "X-ASSISTANT": "assistant",
    "X-EVOLUTION-ASSISTANT": "assistant",
    "X-KADDRESSBOOK-X-ASSISTANTSNAME": "assistant",
    "X-MANAGER": "manager",
    "X-EVOLUTION-MANAGER": "manager",
    "X-KADDRESSBOOK-X-MANAGERSNAME": "manager",
}

# RELATED TYPE values (RFC 6350 + Apple labels) → Association label.
_RELATION_LABELS = {
    "spouse": _("Spouse"),
    "partner": _("Partner"),
    "child": _("Child"),
    "parent": _("Parent"),
    "father": _("Father"),
    "mother": _("Mother"),
    "sibling": _("Sibling"),
    "brother": _("Brother"),
    "sister": _("Sister"),
    "kin": _("Kin"),
    "muse": _("Muse"),
    "crush": _("Crush"),
    "date": _("Date"),
    "sweetheart": _("Sweetheart"),
    "colleague": _("Colleague"),
    "co-worker": _("Coworker"),
    "coworker": _("Coworker"),
    "agent": _("Agent"),
    "assistant": _("Assistant"),
    "manager": _("Manager"),
    "friend": _("Friend"),
    "acquaintance": _("Acquaintance"),
    "met": _("Met"),
    "contact": _("Contact"),
    "neighbor": _("Neighbor"),
    "co-resident": _("Co-resident"),
    "coresident": _("Co-resident"),
    "emergency": _("Emergency contact"),
    "me": _("Same person"),
    "other": _("Related"),
    "husband": _("Husband"),
    "wife": _("Wife"),
    "son": _("Son"),
    "daughter": _("Daughter"),
}

# RELATED types that build Families instead of Associations
_SPOUSE_TYPES = {"spouse", "partner", "husband", "wife"}
_PARENT_TYPES = {"parent", "father", "mother"}
_CHILD_TYPES = {"child", "son", "daughter"}
_SIBLING_TYPES = {"sibling", "brother", "sister"}
_FAMILY_TYPES = _SPOUSE_TYPES | _PARENT_TYPES | _CHILD_TYPES | _SIBLING_TYPES

# Last-resort hint for the father / mother slot when no gender is known
_MALE_TITLES = {"king", "prince", "duke", "earl", "lord", "sir", "mr", "baron", "count"}
_FEMALE_TITLES = {
    "queen",
    "princess",
    "duchess",
    "countess",
    "lady",
    "dame",
    "mrs",
    "ms",
    "miss",
    "baroness",
}

_URI_RE = re.compile(r"^(urn|mailto|https?|tel|sip|xmpp|cid|data|ftp):", re.I)
_PROP_LINE_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)?[;:]")
_APPLE_LABEL_RE = re.compile(r"^_\$!<(.+)>!\$_$")
_GEO_RE = re.compile(r"^geo:\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)", re.I)


# ── Main parser class ─────────────────────────────────────────────────


class VCardEnhancedParser:
    """Parse vCard files of any supported version into Gramps records."""

    # (regex, which fields the groups hold) — tried in order.
    DATE_PATTERNS = [
        (re.compile(r"^(\d{4})-?(\d\d)-?(\d\d)$"), "ymd"),
        (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "ymd"),
        (re.compile(r"^(\d{4})-(\d\d)$"), "ym"),
        (re.compile(r"^(\d{4})$"), "y"),
        (re.compile(r"^--(\d\d)(\d\d)$"), "md"),
        (re.compile(r"^--(\d\d)$"), "m"),
        (re.compile(r"^---(\d\d)$"), "d"),
    ]
    GROUP_RE = re.compile(r"^(?:([-0-9A-Za-z]+)\.)?(.+)$")
    ESCAPE_CHAR = "\\"
    TOBE_ESCAPED = ["\\", ",", ";"]
    LINE_CONTINUATION_CHARS = (" ", "\t")

    @staticmethod
    def name_value_split(data):
        """Split on first unquoted colon → (name_with_params, value, group)."""
        colon_idx = data.find(":")
        if colon_idx < 1:
            return ()
        quote_count = data.count('"', 0, colon_idx)
        while quote_count % 2 == 1:
            colon_idx = data.find(":", colon_idx + 1)
            if colon_idx == -1:
                return ()
            quote_count = data.count('"', 0, colon_idx)
        group_name, value = data[:colon_idx], data[colon_idx + 1 :]
        m = VCardEnhancedParser.GROUP_RE.match(group_name)
        if not m:
            return ()
        return (m.group(2), value, m.group(1))

    @staticmethod
    def unesc(data):
        """Remove vCard escape sequences for \\ , ;"""
        if isinstance(data, str):
            for char in reversed(VCardEnhancedParser.TOBE_ESCAPED):
                data = data.replace(VCardEnhancedParser.ESCAPE_CHAR + char, char)
            return data
        elif isinstance(data, list):
            return [VCardEnhancedParser.unesc(x) for x in data]
        raise TypeError("vCard unescaping not implemented for %s" % type(data))

    @staticmethod
    def unesc_text(data):
        """Full TEXT unescape, including \\n / \\N → newline (NOTE etc.)."""
        out = []
        i = 0
        while i < len(data):
            char = data[i]
            if char == "\\" and i + 1 < len(data):
                nxt = data[i + 1]
                out.append("\n" if nxt in "nN" else nxt)
                i += 2
            else:
                out.append(char)
                i += 1
        return "".join(out)

    @staticmethod
    def count_escapes(strng):
        count = 0
        for char in reversed(strng):
            if char != VCardEnhancedParser.ESCAPE_CHAR:
                return count
            count += 1
        return count

    @staticmethod
    def split_unescaped(strng, sep):
        parts = strng.split(sep)
        for i in reversed(range(len(parts))):
            if VCardEnhancedParser.count_escapes(parts[i]) % 2 == 1:
                appendix = parts.pop(i + 1)
                parts[i] += sep + appendix
        return parts

    @staticmethod
    def decode_quoted_printable(value, charset="utf-8"):
        """Decode QUOTED-PRINTABLE encoded value (vCard 2.1 / 1.0)."""
        import quopri

        raw = quopri.decodestring(value.encode("utf-8"))
        try:
            return raw.decode(charset or "utf-8", errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")

    @staticmethod
    def parse_params(fields):
        """
        Parse param fields into a dict of upper-cased name → list of values.

        ["ADR", "TYPE=HOME,WORK", "PREF"] → {"TYPE": ["HOME,WORK"],
                                             "_BARE": ["PREF"]}
        """
        params = {}
        for field in fields[1:]:
            if "=" in field:
                key, sep, val = field.partition("=")
                params.setdefault(key.upper(), []).append(val.strip('"').upper())
            else:
                params.setdefault("_BARE", []).append(field.upper())
        return params

    @staticmethod
    def _param_list(params, *keys):
        """Flatten comma-separated param values for the given keys."""
        out = []
        for key in keys:
            for val in params.get(key, []):
                out.extend(v.strip() for v in val.split(",") if v.strip())
        return out

    @staticmethod
    def _is_base64(params):
        enc = VCardEnhancedParser._param_list(params, "ENCODING", "_BARE")
        return "B" in enc or "BASE64" in enc

    @staticmethod
    def _is_qp(params):
        enc = VCardEnhancedParser._param_list(params, "ENCODING", "_BARE")
        return "QUOTED-PRINTABLE" in enc

    # ── Instance ──────────────────────────────────────────────────────

    def __init__(self, dbase, filename=None):
        self.database = dbase
        if filename and filename != "-":
            base_dir = os.path.dirname(os.path.abspath(filename))
        else:
            base_dir = os.getcwd()
        self.media_dir = os.path.join(base_dir, MEDIA_SUBFOLDER)

        self.next_line = None
        self.line_num = 0
        self.trans = None
        self.version = None
        self.quirks = _DEFAULT_QUIRKS
        self.person = None
        self.errors = []
        self.number_of_errors = 0

        # Context of the line being dispatched
        self._cur_line = ""
        self._cur_line_num = 0
        self._cur_params = {}
        self._cur_group = None

        # Cross-vCard state
        self._pending_relations = []
        self._pending_anniversaries = []  # (person handle, Event, chunk)
        self._name_tokens = []  # (handle, set of name words)
        self._by_uid = {}
        self._by_email = {}
        self._by_name = {}
        self._stubs = {}
        self._place_cache = None
        self._media_cache = None
        self._tag_cache = {}
        self.stats = dict.fromkeys(
            (
                "people",
                "events",
                "places",
                "media",
                "files",
                "notes",
                "tags",
                "associations",
                "stubs",
                "placeholders",
                "families",
            ),
            0,
        )

        self._reset_person_state()
        self._handlers = self._build_handlers()

    def _build_handlers(self):
        """Map vCard property names to handler(fields, value)."""
        handlers = {
            "BEGIN": lambda f, v: self.next_person(),
            "END": lambda f, v: self.finish_person(),
            "VERSION": self.check_version,
            "FN": self.add_formatted_name,
            "N": self.add_name_parts,
            "NICKNAME": self.add_nicknames,
            "SORT-STRING": self.add_sortas,
            "X-SORT-STRING": self.add_sortas,
            "ADR": self.add_address,
            "TEL": self.add_phone,
            "BDAY": partial(self.add_vital_date, EventType.BIRTH),
            "DEATHDATE": partial(self.add_vital_date, EventType.DEATH),
            "BIRTHPLACE": partial(self.add_vital_place, EventType.BIRTH),
            "DEATHPLACE": partial(self.add_vital_place, EventType.DEATH),
            "ANNIVERSARY": self.add_anniversary,
            "X-ANNIVERSARY": self.add_anniversary,
            "X-EVOLUTION-ANNIVERSARY": self.add_anniversary,
            "ROLE": self.add_role,
            "TITLE": self.add_title,
            "ORG": self.add_org,
            "URL": self.add_url,
            "EMAIL": self.add_email,
            "GENDER": self.add_gender,
            "X-GENDER": self.add_gender,
            "NOTE": self.add_note,
            "CATEGORIES": self.add_categories,
            "UID": self.add_uid,
            "RELATED": self.add_related,
            "X-ABRELATEDNAMES": self.add_apple_grouped,
            "X-ABDATE": self.add_apple_grouped,
            "X-ABLABEL": self.add_apple_grouped,
            "PRODID": lambda f, v: None,  # producing program; not person data
        }
        for prop in _MEDIA_PROPS:
            handlers[prop] = partial(self.add_media, prop)
        for prop, label in _IM_PROPS.items():
            handlers[prop] = partial(self.add_im, label)
        for prop, label in _URL_PROPS.items():
            handlers[prop] = partial(self.add_labeled_url, label)
        for prop, rel in _RELATED_ALIASES.items():
            handlers[prop] = partial(self.add_related_alias, rel)
        return handlers

    def _reset_person_state(self):
        self._card_lines = []  # logical lines of this vCard, for the report
        self._card_flagged = False  # a message was reported for this vCard
        self._card_has_data = False
        self.formatted_name = ""
        self.name_parts = ""
        self.org = ""
        self.org_full = ""
        self._org_line = None
        self._org_as_name = False
        self._title = ""
        self._role = ""
        self._raw_lines = []
        self._vital = {}  # EventType value → Event
        self._vital_place = {}  # EventType value → (text, geo|None)
        self._events = []
        self._notes = []
        self._tags = []
        self._media = []
        self._relations = []
        self._anniversaries = []
        self._groups = {}
        self._uids = []
        self._emails = []
        self._sort_string = None
        self._sort_line = None

    # ── Low-level line reading ────────────────────────────────────────

    def _advance(self, filehandle):
        self.next_line = filehandle.readline()
        self.line_num += 1

    def _get_next_line(self, filehandle):
        """Read the next logical line (joining folded continuations)."""
        line = self.next_line
        self._advance(filehandle)
        while self.next_line and self.next_line[0] in self.LINE_CONTINUATION_CHARS:
            line = line.rstrip("\n")
            if line.endswith("\r"):
                line = line[:-1]
            line += self.next_line[1:]
            self._advance(filehandle)
        return line.strip() if line else None

    def _slurp_bare_continuations(self, filehandle, value):
        """
        Some vCard 2.1 writers put BASE64 data on following lines with no
        leading whitespace, ended by a blank line. Join those lines.
        """
        while (
            self.next_line
            and self.next_line.strip()
            and not _PROP_LINE_RE.match(self.next_line)
        ):
            value += self.next_line.strip()
            self._advance(filehandle)
        return value

    def _join_qp_soft_breaks(self, filehandle, value):
        """QUOTED-PRINTABLE soft line break: a trailing '=' continues."""
        while value.endswith("=") and self.next_line:
            value = value[:-1] + self.next_line.rstrip("\r\n")
            self._advance(filehandle)
        return value

    # ── Messages ──────────────────────────────────────────────────────

    def _add_msg(self, problem, line=None, chunk=None):
        """
        Report a problem. Inside a vCard the whole vCard is quoted once,
        after its messages, when the vCard is finished. Pass chunk to quote
        a vCard explicitly (used after the vCard has been finished).
        """
        if problem:
            self.number_of_errors += 1
        if line:
            msg = _("Line %(line)5d: %(prob)s\n") % {"line": line, "prob": problem}
        else:
            msg = problem + "\n"
        self.errors.append(msg)
        if chunk:
            self.errors.append(chunk)
        elif self.person is not None:
            self._card_flagged = True

    @staticmethod
    def _format_chunk(lines):
        """Indent a vCard for the report, shortening very long lines."""
        out = []
        for line in lines:
            if len(line) > _CHUNK_LINE_MAX:
                line = _("%(start)s… [%(count)d more characters]") % {
                    "start": line[:_CHUNK_LINE_MAX],
                    "count": len(line) - _CHUNK_LINE_MAX,
                }
            out.append("        " + line)
        return "\n".join(out) + "\n\n"

    def _store_raw(self, raw_line):
        """Buffer an unhandled vCard line for later storage as an attribute."""
        if raw_line:
            self._raw_lines.append(raw_line)

    def _flush_raw_to_person(self):
        """Write buffered raw lines as a Person attribute."""
        if self.person is None or not self._raw_lines:
            self._raw_lines = []
            return
        attr = Attribute()
        attr.set_type(AttributeType("vCard %s source" % (self.version or "?")))
        attr.set_value("\n".join(self._raw_lines))
        self.person.add_attribute(attr)
        self._raw_lines = []

    # ── Top-level parse ───────────────────────────────────────────────

    def parse(self, filehandle, user):
        """Parse the vCard file into the Gramps database."""
        tym = time.time()
        self.person = None
        self.database.disable_signals()
        with DbTxn(_("vCard import"), self.database, batch=True) as self.trans:
            self._parse_vcard_file(filehandle)
            self._resolve_relations()
        self.database.enable_signals()
        self.database.request_rebuild()
        tym = time.time() - tym
        LOG.debug("vCard import complete: %.2f seconds", tym)

        if self.number_of_errors == 0:
            message = _("vCard import report: No errors detected")
        else:
            message = (
                _("vCard import report: %s errors detected\n") % self.number_of_errors
            )
        details = self._summary() + "\n" + "".join(self.errors)
        parent_window = None
        if hasattr(user, "uistate") and hasattr(user.uistate, "window"):
            parent_window = user.uistate.window
        user.info(message, details, parent=parent_window, monospaced=True)

    def _summary(self):
        labels = [
            ("people", _("People imported")),
            ("events", _("Events created")),
            ("places", _("Places created")),
            ("media", _("Media objects created")),
            ("files", _("Media files written")),
            ("notes", _("Notes created")),
            ("tags", _("Tags created")),
            ("associations", _("Associations created")),
            ("stubs", _("People created from RELATED names")),
            ("placeholders", _("Placeholder people (no name)")),
            ("families", _("Families created")),
        ]
        lines = ["%-36s %d" % (lbl + ":", self.stats[key]) for key, lbl in labels]
        if self.stats["files"]:
            lines.append(_("Media folder: %s") % self.media_dir)
        return "\n".join(lines) + "\n"

    def _parse_vcard_file(self, filehandle):
        """Iterate logical lines and dispatch to handlers."""
        self.next_line = filehandle.readline()
        self.line_num = 1

        while True:
            line = self._get_next_line(filehandle)
            if line is None:
                break
            if not line or ":" not in line:
                continue
            line_parts = self.name_value_split(line)
            if not line_parts:
                continue
            name_part, value, group = line_parts
            fields = name_part.split(";")
            prop = fields[0].upper()
            params = self.parse_params(fields)

            if self._is_base64(params) or value[:5].lower() == "data:":
                value = self._slurp_bare_continuations(filehandle, value)
                line = line + value[len(line_parts[1]) :]
            elif self._is_qp(params):
                value = self._join_qp_soft_breaks(filehandle, value)
                charset = (params.get("CHARSET") or ["UTF-8"])[0]
                value = self.decode_quoted_printable(value, charset)

            self._cur_line = line
            self._cur_line_num = self.line_num - 1
            self._cur_params = params
            self._cur_group = group.lower() if group else None

            if self.person is None and prop not in ("BEGIN", "END", "VERSION"):
                continue  # junk outside BEGIN/END
            if self._cur_group and self.person is not None:
                self._groups.setdefault(self._cur_group, {})[prop] = (
                    value,
                    line,
                    self._cur_line_num,
                )

            if prop != "BEGIN":
                self._card_lines.append(line)
                if prop not in _NO_DATA_PROPS:
                    self._card_has_data = True

            handler = self._handlers.get(prop)
            if handler is None:
                self._store_raw(line)
            else:
                handler(fields, value)

            if prop == "BEGIN":
                self._card_lines.append(line)  # state was reset by BEGIN

        if self.person is not None:
            self._add_msg(_("File ended inside a vCard (missing END)."), self.line_num)
            self.finish_person()

    # ── Person lifecycle ──────────────────────────────────────────────

    def next_person(self):
        if self.person is not None:
            self._add_msg(
                _(
                    "BEGIN property not properly closed by END; "
                    "Gramps can't cope with nested vCards."
                ),
                self.line_num - 1,
            )
            self.finish_person()
        self.person = Person()
        self._reset_person_state()

    def finish_person(self):
        """Commit the buffered vCard as a Person plus its secondary objects."""
        if self.person is None:
            return
        if not self._card_has_data:
            self._add_msg(
                _("The vCard contains no data; skipping this record."),
                self.line_num - 1,
            )
            self._end_card()
            return
        self._process_groups()
        if not self.add_name():
            self._end_card()  # nothing was written to the database
            return
        self._check_sort_string()
        self._build_occupation()
        self._commit_events()
        self._commit_notes()
        self._commit_tags()
        self._commit_media()
        self._flush_raw_to_person()

        self.database.add_person(self.person, self.trans)
        handle = self.person.get_handle()
        self.stats["people"] += 1
        self._register_lookup(handle)
        src_name = _nd.display(self.person)
        chunk = self._format_chunk(self._card_lines)
        for rel in self._relations:
            self._pending_relations.append((handle, src_name) + rel + (chunk,))
        for event in self._anniversaries:
            self._pending_anniversaries.append((handle, event, chunk))
        self._end_card()

    def _end_card(self):
        """Quote the vCard after its messages (if any) and drop the person."""
        if self._card_flagged:
            self.errors.append(self._format_chunk(self._card_lines))
        self.person = None

    # ── VERSION ───────────────────────────────────────────────────────

    def check_version(self, fields, data):
        """Accept versions 1.0, 2.1, 3.0, 4.0; warn on anything else."""
        self.version = data.strip()
        self.quirks = _VERSION_QUIRKS.get(self.version, _DEFAULT_QUIRKS)
        if self.version not in _VERSION_QUIRKS:
            self._add_msg(
                _(
                    "vCard version %(ver)s is not explicitly supported; "
                    "attempting import using vCard 3.0 rules."
                )
                % {"ver": self.version},
                self.line_num - 1,
            )

    # ── Name properties ───────────────────────────────────────────────

    def add_formatted_name(self, fields, data):
        if not self.formatted_name:
            self.formatted_name = self.unesc(str(data)).strip()

    def add_name_parts(self, fields, data):
        if not self.name_parts:
            self.name_parts = data.strip()

    def add_name(self):
        """Build and attach the primary Name from buffered N, FN, and ORG data."""
        if not self.name_parts.strip():
            if self.org:
                # Business card: ORG becomes the surname. Keep the original
                # ORG line (with any departments) in the source attribute.
                self.name_parts = "%s;;;;" % self.org.replace(";", "\\;")
                if not self.formatted_name:
                    self.formatted_name = self.org
                self._org_as_name = True
                self._store_raw(self._org_line)
            elif self.formatted_name:
                # FN only (common in vCard 4.0 where N is optional).
                self.name_parts = self._n_from_text(self.formatted_name)
            else:
                self._add_msg(
                    _(
                        "The vCard has no N, FN or ORG property; imported as "
                        "placeholder person '%(given)s %(surname)s'."
                    )
                    % {"given": PLACEHOLDER_GIVEN, "surname": PLACEHOLDER_SURNAME},
                    self.line_num - 1,
                )
                self.stats["placeholders"] += 1
                name = Name()
                name.set_type(NameType(NameType.BIRTH))
                name.set_first_name(PLACEHOLDER_GIVEN)
                surname = Surname()
                surname.set_surname(PLACEHOLDER_SURNAME)  # no prefix split
                name.add_surname(surname)
                name.set_primary_surname()
                self.person.set_primary_name(name)
                return True

        data_fields = self.split_unescaped(self.name_parts, ";")
        if self.quirks.get("strict_n_fields") and len(data_fields) != 5:
            self._add_msg(
                _("The vCard N field has wrong component count."),
                self.line_num - 1,
            )

        name = Name()
        name.set_type(NameType(NameType.BIRTH))

        if data_fields[0].strip():
            for surname_str in self.split_unescaped(data_fields[0], ","):
                surname = Surname()
                prefix, sname = splitof_nameprefix(self.unesc(surname_str))
                surname.set_surname(sname.strip())
                surname.set_prefix(prefix.strip())
                name.add_surname(surname)
            name.set_primary_surname()

        given_name = ""
        if len(data_fields) > 1 and data_fields[1].strip():
            given_name = " ".join(self.unesc(self.split_unescaped(data_fields[1], ",")))
        additional_names = ""
        if len(data_fields) > 2 and data_fields[2].strip():
            additional_names = " ".join(
                self.unesc(self.split_unescaped(data_fields[2], ","))
            )
        self._add_firstname(given_name.strip(), additional_names.strip(), name)

        if len(data_fields) > 3 and data_fields[3].strip():
            name.set_title(
                " ".join(self.unesc(self.split_unescaped(data_fields[3], ",")))
            )
        if len(data_fields) > 4 and data_fields[4].strip():
            name.set_suffix(
                " ".join(self.unesc(self.split_unescaped(data_fields[4], ",")))
            )

        self.person.set_primary_name(name)
        return True

    @staticmethod
    def _n_from_text(text):
        """'First Middle Last' or 'Last, First' → an N value."""
        text = text.strip()
        if "," in text:
            last, sep, first = text.partition(",")
            return "%s;%s;;;" % (last.strip(), first.strip())
        tokens = text.split()
        if len(tokens) == 1:
            return ";%s;;;" % tokens[0]
        return "%s;%s;;;" % (tokens[-1], " ".join(tokens[:-1]))

    def _add_firstname(self, given_name, additional_names, name):
        """Combine given and additional names, inferring call name from FN."""
        default = "%s %s" % (given_name, additional_names)
        if self.formatted_name:
            if given_name:
                if additional_names:
                    gpos = self.formatted_name.find(given_name)
                    apos = self.formatted_name.find(additional_names)
                    if gpos != -1 and apos != -1:
                        if gpos <= apos:
                            firstname = default
                        else:
                            firstname = "%s %s" % (additional_names, given_name)
                            name.set_call_name(given_name)
                    else:
                        idx = fitin(self.formatted_name, additional_names, given_name)
                        if idx == -1:
                            firstname = default
                        else:
                            firstname = "%s%s %s" % (
                                additional_names[:idx],
                                given_name,
                                additional_names[idx:],
                            )
                            name.set_call_name(given_name)
                else:
                    firstname = given_name
            else:
                firstname = additional_names
        else:
            firstname = default
        name.set_first_name(firstname.strip())

    def add_nicknames(self, fields, data):
        for nick in self.split_unescaped(data, ","):
            nickname = nick.strip()
            if nickname:
                alt = Name()
                alt.set_nick_name(self.unesc(nickname))
                self.person.add_alternate_name(alt)

    def add_sortas(self, fields, data):
        """Kept only when it differs from what Gramps would compute."""
        if self._sort_string is None:
            self._sort_string = self.unesc(data).strip()
            self._sort_line = self._cur_line

    def _check_sort_string(self):
        if not self._sort_string:
            return
        computed = _nd.sort_string(self.person.get_primary_name())
        if self._sort_string.split() != computed.split():  # padding differs
            self._store_raw(self._sort_line)

    # ── Address / phone ───────────────────────────────────────────────

    def add_address(self, fields, data):
        data_fields = [x.strip() for x in self.unesc(self.split_unescaped(data, ";"))]
        if "".join(data_fields):
            addr = Address()

            def add_street(s):
                if s:
                    already = addr.get_street()
                    addr.set_street(("%s %s" % (already, s)).strip() if already else s)

            addr._add_street = add_street
            setters = [
                "_add_street",
                "_add_street",
                "_add_street",
                "set_city",
                "set_state",
                "set_postal_code",
                "set_country",
            ]
            for i, df in enumerate(data_fields):
                if i >= len(setters):
                    break
                getattr(addr, setters[i])(df)
            self.person.add_address(addr)

    def add_phone(self, fields, data):
        tel = data.strip()
        if tel:
            addr = Address()
            addr.set_phone(self.unesc(tel))
            self.person.add_address(addr)

    # ── Dates and events ──────────────────────────────────────────────

    def _parse_date_str(self, date_str):
        """
        Parse a vCard date into a Gramps Date.

        Handles YYYYMMDD, YYYY-MM-DD, YYYY-MM, YYYY, --MMDD, --MM, ---DD,
        an optional trailing Thhmmss time (dropped), and text fallback.
        """
        date = Date()
        text = date_str.strip()
        if "TEXT" in self._cur_params.get("VALUE", []):
            date.set(modifier=Date.MOD_TEXTONLY, text=self.unesc_text(text))
            return date
        datepart = text
        if text[:1].isdigit() or text[:1] == "-":
            datepart = text.split("T")[0]

        for regex, layout in self.DATE_PATTERNS:
            m = regex.match(datepart)
            if not m:
                continue
            vals = dict(zip(layout, (int(g) for g in m.groups())))
            try:
                date.set(
                    value=(vals.get("d", 0), vals.get("m", 0), vals.get("y", 0), False)
                )
            except DateError:
                self._add_msg(
                    _("Invalid date {vcard_snippet}, preserving as text.").format(
                        vcard_snippet=text
                    ),
                    self._cur_line_num,
                )
                date.set(modifier=Date.MOD_TEXTONLY, text=text)
            return date

        if text:
            date.set(modifier=Date.MOD_TEXTONLY, text=self.unesc_text(text))
        return date

    def _vital_event(self, etype):
        if etype not in self._vital:
            event = Event()
            event.set_type(EventType(etype))
            self._vital[etype] = event
        return self._vital[etype]

    def add_vital_date(self, etype, fields, data):
        """BDAY / DEATHDATE → Birth / Death event date."""
        if data.strip():
            self._vital_event(etype).set_date_object(self._parse_date_str(data))

    def add_vital_place(self, etype, fields, data):
        """BIRTHPLACE / DEATHPLACE (RFC 6474) → place of Birth / Death event."""
        value = data.strip()
        if not value:
            return
        geo = None
        m = _GEO_RE.match(value)
        if m:
            geo = (m.group(1), m.group(2))
            text = "%s, %s" % geo
        else:
            text = self.unesc_text(value)
        self._vital_event(etype)
        self._vital_place[etype] = (text, geo)

    def add_anniversary(self, fields, data):
        """ANNIVERSARY → Marriage event (attached to a Family at end of file)."""
        if not data.strip():
            return
        event = Event()
        event.set_type(EventType(EventType.MARRIAGE))
        event.set_date_object(self._parse_date_str(data))
        event.set_description(_("Anniversary (from vCard)"))
        self._anniversaries.append(event)  # placed on a Family at end of file

    def add_role(self, fields, data):
        if not self._role:
            self._role = self.unesc(data).strip()

    def add_title(self, fields, data):
        if not self._title:
            self._title = self.unesc(data).strip()

    def add_org(self, fields, data):
        parts = [p.strip() for p in self.unesc(self.split_unescaped(data, ";"))]
        parts = [p for p in parts if p]
        if parts and not self.org:
            self.org = parts[0]
            self.org_full = "; ".join(parts)  # ";" so the exporter can split it back
            self._org_line = self._cur_line

    def _build_occupation(self):
        """TITLE / ROLE / ORG → one Occupation event (ORG as Agency)."""
        org = "" if self._org_as_name else self.org_full
        if not (self._title or self._role or org):
            return
        event = Event()
        event.set_type(EventType(EventType.OCCUPATION))
        event.set_description(self._title or self._role)
        if self._title and self._role and self._role != self._title:
            attr = Attribute()
            attr.set_type(AttributeType(_("Role")))
            attr.set_value(self._role)
            event.add_attribute(attr)
        if org:
            attr = Attribute()
            attr.set_type(AttributeType(AttributeType.AGENCY))
            attr.set_value(org)
            event.add_attribute(attr)
        self._events.append(event)

    def _commit_events(self):
        for etype, event in self._vital.items():
            place = self._vital_place.get(etype)
            if place:
                event.set_place_handle(self._place_handle(*place))
            self.database.add_event(event, self.trans)
            self.stats["events"] += 1
            ref = EventRef()
            ref.set_reference_handle(event.get_handle())
            if etype == EventType.BIRTH:
                self.person.set_birth_ref(ref)
            else:
                self.person.set_death_ref(ref)
        for event in self._events:
            self.database.add_event(event, self.trans)
            self.stats["events"] += 1
            ref = EventRef()
            ref.set_reference_handle(event.get_handle())
            self.person.add_event_ref(ref)

    def _place_handle(self, text, geo):
        """Reuse a Place whose full title matches, else create one."""
        if self._place_cache is None:
            self._place_cache = {}
            for place in self.database.iter_places():
                title = _pd.display(self.database, place).strip().lower()
                self._place_cache.setdefault(title, place.get_handle())
        key = text.strip().lower()
        if key in self._place_cache:
            return self._place_cache[key]
        place = Place()
        pname = PlaceName()
        pname.set_value(text.strip())
        place.set_name(pname)
        place.set_type(PlaceType(PlaceType.UNKNOWN))
        if geo:
            place.set_latitude(geo[0])
            place.set_longitude(geo[1])
        self.database.add_place(place, self.trans)
        self.stats["places"] += 1
        self._place_cache[key] = place.get_handle()
        return place.get_handle()

    # ── Url-type properties ───────────────────────────────────────────

    def _type_desc(self, ignore=("INTERNET", "PREF", "X400", "VOICE")):
        types = self._param_list(self._cur_params, "TYPE", "_BARE")
        types = [t for t in types if t not in ignore and not t.startswith("PREF")]
        return ", ".join(t.title() for t in types)

    def _add_url(self, path, utype, desc=""):
        url = Url()
        url.set_path(path)
        url.set_type(utype)
        if desc:
            url.set_description(desc)
        self.person.add_url(url)

    def add_url(self, fields, data):
        href = data.strip()
        if href:
            self._add_url(
                self.unesc(href), UrlType(UrlType.WEB_HOME), self._type_desc()
            )

    def add_email(self, fields, data):
        email = self.unesc(data.strip())
        if email:
            self._add_url(email, UrlType(UrlType.EMAIL), self._type_desc())
            self._emails.append(email.lower().replace("mailto:", ""))

    def add_im(self, protocol, fields, data):
        value = self.unesc(data.strip())
        if not value:
            return
        if not protocol and ":" in value:
            protocol = value.split(":", 1)[0].upper()
        desc = ", ".join(x for x in (protocol, self._type_desc()) if x)
        self._add_url(value, UrlType(_("Instant Messaging")), desc)

    def add_labeled_url(self, label, fields, data):
        value = self.unesc(data.strip())
        if value:
            self._add_url(value, UrlType(label), self._type_desc())

    # ── Gender ────────────────────────────────────────────────────────

    def add_gender(self, fields, data):
        """
        GENDER (4.0): sex[;identity]; X-GENDER (2.1/3.0): Male/Female/...
        The identity text, if any, becomes a "Gender identity" attribute.
        """
        raw = data.strip()
        if not raw:
            return
        sex, sep, identity = raw.partition(";")
        sex = sex.strip().upper()[:1]
        if sex == "M":
            self.person.set_gender(Person.MALE)
        elif sex == "F":
            self.person.set_gender(Person.FEMALE)
        elif sex == "O":
            self.person.set_gender(Person.OTHER)
        identity = self.unesc_text(identity).strip()
        if identity:
            attr = Attribute()
            attr.set_type(AttributeType(_("Gender identity")))
            attr.set_value(identity)
            self.person.add_attribute(attr)

    # ── Notes, tags, UID ──────────────────────────────────────────────

    def add_note(self, fields, data):
        text = self.unesc_text(data).replace("\r\n", "\n").strip()
        if text:
            self._notes.append(text)

    def _commit_notes(self):
        for text in self._notes:
            note = Note(text)
            note.set_type(NoteType(NoteType.PERSON))
            self.database.add_note(note, self.trans)
            self.stats["notes"] += 1
            self.person.add_note(note.get_handle())

    def add_categories(self, fields, data):
        for cat in self.split_unescaped(data, ","):
            name = self.unesc(cat).strip()
            if name and name not in self._tags:
                self._tags.append(name)

    def _commit_tags(self):
        for name in self._tags:
            handle = self._tag_cache.get(name)
            if handle is None:
                tag = self.database.get_tag_from_name(name)
                if tag is None:
                    tag = Tag()
                    tag.set_name(name)
                    self.database.add_tag(tag, self.trans)
                    self.stats["tags"] += 1
                handle = tag.get_handle()
                self._tag_cache[name] = handle
            self.person.add_tag(handle)

    def add_uid(self, fields, data):
        """No Gramps field for UID; keep it raw but use it to resolve RELATED."""
        if data.strip():
            self._uids.append(data.strip())
        self._store_raw(self._cur_line)

    # ── Media (PHOTO / LOGO / SOUND) ──────────────────────────────────

    def _media_mime_hint(self):
        for val in self._param_list(self._cur_params, "TYPE", "MEDIATYPE", "_BARE"):
            if "/" in val:
                return val.lower()
            if val in _TYPE_HINT_MIME:
                return _TYPE_HINT_MIME[val]
        return ""

    def add_media(self, prop, fields, data):
        """Buffer an embedded or linked media item; written in finish_person."""
        value = data.strip()
        if not value:
            return
        item = {
            "kind": prop,
            "data": None,
            "path": None,
            "mime": self._media_mime_hint(),
            "raw": self._cur_line,
            "line": self._cur_line_num,
        }
        lowered = value.lower()
        try:
            if lowered.startswith("data:"):
                header, sep, payload = value.partition(",")
                mime = header[5:].split(";")[0].strip().lower()
                if mime:
                    item["mime"] = mime
                if ";base64" in header.lower():
                    item["data"] = base64.b64decode("".join(payload.split()))
                else:
                    item["data"] = unquote_to_bytes(payload)
            elif self._is_base64(self._cur_params):
                item["data"] = base64.b64decode("".join(value.split()))
            elif lowered.startswith("file:"):
                item["path"] = url2pathname(urlparse(value).path)
            elif lowered.startswith(("http://", "https://")):
                # Remote media is linked, not downloaded.
                self._add_url(
                    value,
                    UrlType(_MEDIA_PROPS[prop].title()),
                    _("vCard %s link") % _MEDIA_PROPS[prop],
                )
                return
            else:
                self._store_raw(self._cur_line)  # e.g. CID: references
                return
        except ValueError as err:
            self._add_msg(
                _("Could not decode %(kind)s data (%(err)s); kept as text.")
                % {"kind": _MEDIA_PROPS[prop], "err": err},
                self._cur_line_num,
            )
            self._store_raw(self._cur_line)
            return
        if item["data"] is not None and not item["data"]:
            return
        self._media.append(item)

    @staticmethod
    def _guess_ext(data, mime):
        for magic, ext in _MAGIC_EXT:
            if data.startswith(magic):
                return ext
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            return ".wav"
        return (mimetypes.guess_extension(mime) if mime else None) or ".bin"

    @staticmethod
    def _safe_name(text):
        cleaned = re.sub(r"[^\w-]+", "_", text).strip("_")
        return cleaned[:40] or "vcard"

    def _existing_media(self):
        """checksum → Media handle for everything already in the database."""
        if self._media_cache is None:
            self._media_cache = {}
            for media in self.database.iter_media():
                if media.get_checksum():
                    self._media_cache.setdefault(
                        media.get_checksum(), media.get_handle()
                    )
        return self._media_cache

    def _db_path(self, full):
        """Path relative to the tree's base media folder when inside it."""
        full = os.path.abspath(full)
        base = os.path.abspath(media_path(self.database))
        try:
            if os.path.commonpath([full, base]) == base:
                return relative_path(full, base)
        except ValueError:
            pass
        return full

    def _media_handle(self, item, person_name):
        kind_label = _MEDIA_PROPS[item["kind"]]
        if item["data"] is not None:
            data = item["data"]
            checksum = hashlib.md5(data).hexdigest()
            handle = self._existing_media().get(checksum)
            if handle:
                return handle  # identical image already in the tree
            fname = "%s_%s_%s%s" % (
                self._safe_name(person_name),
                item["kind"].lower(),
                checksum[:8],
                self._guess_ext(data, item["mime"]),
            )
            full = os.path.join(self.media_dir, fname)
            if not os.path.exists(full):
                os.makedirs(self.media_dir, exist_ok=True)
                with open(full, "wb") as fh:
                    fh.write(data)
                self.stats["files"] += 1
        else:
            full = item["path"]
            if not os.path.isfile(full):
                self._add_msg(
                    _("Linked %(kind)s file not found: %(path)s")
                    % {"kind": kind_label, "path": full},
                    item["line"],
                )
                self._store_raw(item["raw"])
                return None
            checksum = create_checksum(full)

        handle = self._existing_media().get(checksum)
        if handle:
            return handle
        media = Media()
        media.set_path(self._db_path(full))
        media.set_mime_type(get_type(full))
        media.set_description(
            _("%(name)s (vCard %(kind)s)") % {"name": person_name, "kind": kind_label}
        )
        media.set_checksum(checksum)
        self.database.add_media(media, self.trans)
        self.stats["media"] += 1
        self._media_cache[checksum] = media.get_handle()
        return media.get_handle()

    def _commit_media(self):
        if not self._media:
            return
        person_name = _nd.display(self.person) or self.formatted_name
        order = {"PHOTO": 0, "LOGO": 1, "SOUND": 2}  # PHOTO first = preview
        for item in sorted(self._media, key=lambda m: order.get(m["kind"], 9)):
            try:
                handle = self._media_handle(item, person_name)
            except OSError as err:
                self._add_msg(
                    _("Could not save %(kind)s to %(dir)s: %(err)s")
                    % {
                        "kind": _MEDIA_PROPS[item["kind"]],
                        "dir": self.media_dir,
                        "err": err,
                    },
                    item["line"],
                )
                self._store_raw(item["raw"])
                continue
            if handle:
                ref = MediaRef()
                ref.set_reference_handle(handle)
                self.person.add_media_reference(ref)

    # ── Relationships ─────────────────────────────────────────────────
    #
    # Spouse, parent and child relations build Families; sibling relations
    # are dropped when the two people share a parent; everything else
    # becomes an Association.

    @staticmethod
    def _relation_label(types):
        labels = [
            _RELATION_LABELS.get(t.lower(), t.title())
            for t in types
            if t.lower() not in ("pref", "")
        ]
        return ", ".join(labels) or _("Related")

    @staticmethod
    def _types_from_label(label):
        """'_$!<Spouse>!$_', 'Friend, Coworker', 'Ehepartner' → type keys."""
        reverse = {v.lower(): k for k, v in _RELATION_LABELS.items()}
        types = []
        for part in VCardEnhancedParser.unesc_text(label).split(","):
            part = part.strip()
            m = _APPLE_LABEL_RE.match(part)
            part = (m.group(1) if m else part).strip().lower()
            if part:
                types.append(
                    part if part in _RELATION_LABELS else reverse.get(part, part)
                )
        return types

    def _buffer_relation(self, types, kind, value, raw, line_num):
        types = [t.lower() for t in types if t and t.lower() != "pref"]
        self._relations.append((types, kind, value, raw, line_num))

    def add_related(self, fields, data):
        value = data.strip()
        if not value:
            return
        types = self._param_list(self._cur_params, "TYPE")
        vtype = (self._cur_params.get("VALUE") or [""])[0]
        if vtype == "TEXT" or (vtype != "URI" and not _URI_RE.match(value)):
            kind, value = "text", self.unesc_text(value).strip()
        else:
            kind = "uri"
        self._buffer_relation(types, kind, value, self._cur_line, self._cur_line_num)

    def add_related_alias(self, rel_type, fields, data):
        """X-SPOUSE, X-MANAGER, AGENT ... → RELATED of the matching type."""
        value = data.strip()
        if not value:
            return
        if "BEGIN:VCARD" in value.upper():
            self._store_raw(self._cur_line)  # embedded AGENT vCard
            return
        vtype = (self._cur_params.get("VALUE") or [""])[0]
        kind = "uri" if vtype in ("URI", "URL") or _URI_RE.match(value) else "text"
        if kind == "text":
            value = self.unesc_text(value).strip()
        self._buffer_relation(
            [rel_type], kind, value, self._cur_line, self._cur_line_num
        )

    def add_apple_grouped(self, fields, data):
        """
        Apple X-ABRELATEDNAMES / X-ABDATE are labelled by an X-ABLabel in
        the same group (item1.X-ABLabel:_$!<Spouse>!$_); the group data
        is collected in _parse_vcard_file and handled in _process_groups.
        Ungrouped occurrences are handled here, using TYPE= if present
        (X-ABRELATEDNAMES;TYPE=spouse:Henry VIII).
        """
        if self._cur_group:
            return
        prop = fields[0].upper()
        if prop == "X-ABRELATEDNAMES" and data.strip():
            self._buffer_relation(
                self._param_list(self._cur_params, "TYPE"),
                "text",
                self.unesc_text(data).strip(),
                self._cur_line,
                self._cur_line_num,
            )
        else:
            self._store_raw(self._cur_line)

    def _process_groups(self):
        for props in self._groups.values():
            label_item = props.get("X-ABLABEL")
            used = False
            if "X-ABRELATEDNAMES" in props:
                value, line, line_num = props["X-ABRELATEDNAMES"]
                if value.strip():
                    self._buffer_relation(
                        self._types_from_label(label_item[0]) if label_item else [],
                        "text",
                        self.unesc_text(value).strip(),
                        line,
                        line_num,
                    )
                used = True
            if "X-ABDATE" in props:
                value, line, line_num = props["X-ABDATE"]
                if label_item and "anniversary" in label_item[0].lower():
                    self._cur_params = {}
                    self.add_anniversary(None, value)
                    used = True
                else:
                    self._store_raw(line)
            if label_item and not used:
                self._store_raw(label_item[1])

    # ── Resolution of buffered relations (end of file) ────────────────

    @staticmethod
    def _norm_uid(uid):
        uid = uid.strip().lower()
        return uid[9:] if uid.startswith("urn:uuid:") else uid

    @staticmethod
    def _words(text):
        return set(re.findall(r"\w+", text.lower()))

    def _register_lookup(self, handle):
        for uid in self._uids:
            self._by_uid.setdefault(self._norm_uid(uid), set()).add(handle)
        for email in self._emails:
            self._by_email.setdefault(email, set()).add(handle)
        name = self.person.get_primary_name()
        texts = [self.formatted_name, _nd.display(self.person), name.get_regular_name()]
        for text in texts:
            if text and text.strip():
                self._by_name.setdefault(text.strip().lower(), set()).add(handle)
        # All name words (title, given, surnames, suffix, FN, nicknames) so
        # that "Henry VIII" finds "King Henry VIII" (N:Tudor;Henry;;King;VIII)
        words = set()
        for text in (
            texts
            + [
                name.get_title(),
                name.get_suffix(),
                name.get_first_name(),
                name.get_surname(),
            ]
            + [alt.get_nick_name() for alt in self.person.get_alternate_names()]
        ):
            words |= self._words(text or "")
        self._name_tokens.append((handle, words))

    def _find_by_name(self, text):
        """Exact name first; else people whose name words include all words."""
        exact = self._by_name.get(text.lower())
        if exact:
            return set(exact)
        wanted = self._words(text)
        if not wanted:
            return set()
        return {h for h, words in self._name_tokens if wanted <= words}

    def _get_stub(self, text, src_name):
        """Create (once per name) a minimal Person for an unmatched RELATED name."""
        key = text.lower()
        if key in self._stubs:
            return self._stubs[key]
        saved = (self.person, self.formatted_name, self.name_parts)
        self.person = Person()
        self.formatted_name = text
        self.name_parts = self._n_from_text(text)
        self.add_name()
        attr = Attribute()
        attr.set_type(AttributeType(_("vCard RELATED")))
        attr.set_value(
            _("Created from a RELATED property in the vCard of %s") % src_name
        )
        self.person.add_attribute(attr)
        self.database.add_person(self.person, self.trans)
        handle = self.person.get_handle()
        self.person, self.formatted_name, self.name_parts = saved
        self._stubs[key] = handle
        self.stats["stubs"] += 1
        return handle

    def _resolve_target(self, src, src_name, kind, value, line_num, chunk):
        """Return (target handle or None, problem shown) for one relation."""
        if kind == "text":
            found = self._find_by_name(value)
        elif value.lower().startswith("mailto:"):
            found = self._by_email.get(value[7:].lower(), set())
        else:
            found = self._by_uid.get(self._norm_uid(value), set())
        if found == {src}:
            return src, False  # points back at the same person (e.g. TYPE=me)
        candidates = found - {src}
        if len(candidates) == 1:
            return next(iter(candidates)), False
        if not candidates and kind == "text" and value:
            return self._get_stub(value, src_name), False
        if candidates:
            problem = _("RELATED value %s matches several people; not linked.")
        else:
            problem = _("RELATED value %s matches nobody in this file; not linked.")
        self._add_msg(problem % value, line_num, chunk)
        return None, True

    def _resolve_relations(self):
        """
        Turn buffered relations into Families (spouse / parent / child) and
        Associations (all other types), and place ANNIVERSARY events.
        """
        people = {}  # handle → Person, committed once at the end

        def person(handle):
            if handle not in people:
                people[handle] = self.database.get_person_from_handle(handle)
            return people[handle]

        spouse_pairs = {}  # frozenset(a, b) → married?
        parents_of = {}  # child → set of parents
        sibling_pairs = []  # (a, b, sibling types, label)
        assoc = []  # (src, target, label)

        for (
            src,
            src_name,
            types,
            kind,
            value,
            raw,
            line_num,
            chunk,
        ) in self._pending_relations:
            target, failed = self._resolve_target(
                src, src_name, kind, value, line_num, chunk
            )
            if failed:
                attr = Attribute()
                attr.set_type(AttributeType(_("vCard RELATED")))
                attr.set_value(raw)
                person(src).add_attribute(attr)
                continue
            if target == src:
                continue
            tset = set(types)
            if tset & _SPOUSE_TYPES:
                pair = frozenset((src, target))
                married = bool(tset & (_SPOUSE_TYPES - {"partner"}))
                spouse_pairs[pair] = spouse_pairs.get(pair, False) or married
            if tset & _CHILD_TYPES:
                parents_of.setdefault(target, set()).add(src)
            if tset & _PARENT_TYPES:
                parents_of.setdefault(src, set()).add(target)
            if tset & _SIBLING_TYPES:
                stypes = [t for t in types if t in _SIBLING_TYPES]
                sibling_pairs.append(
                    (src, target, stypes, self._relation_label(stypes))
                )
            others = [t for t in types if t not in _FAMILY_TYPES]
            if others or not tset & _FAMILY_TYPES:
                assoc.append((src, target, self._relation_label(others)))

        # ── Families: key = frozenset of the parents (1 or 2 people) ─────
        families = {}  # key → {"married": bool, "children": [], "events": []}

        def family(key, married=False):
            entry = families.setdefault(
                key, {"married": False, "children": [], "events": []}
            )
            entry["married"] = entry["married"] or married
            return entry

        for pair, married in spouse_pairs.items():
            family(pair, married)
        for child, parents in parents_of.items():
            parents = parents - {child}
            if len(parents) > 2:
                names = ", ".join(_nd.display(person(h)) for h in parents)
                self._add_msg(
                    _(
                        "%(child)s has more than two parents (%(names)s); "
                        "linked as Associations instead."
                    )
                    % {"child": _nd.display(person(child)), "names": names}
                )
                assoc.extend((child, p, _RELATION_LABELS["parent"]) for p in parents)
                continue
            if parents:
                entry = family(frozenset(parents))
                if child not in entry["children"]:
                    entry["children"].append(child)

        for handle, event, chunk in self._pending_anniversaries:
            couples = [k for k in families if handle in k and len(k) == 2]
            if len(couples) > 1:
                # Several spouses: the vCard does not say which marriage.
                self._add_msg(
                    _(
                        "%s has an ANNIVERSARY but several spouses; the Marriage "
                        "event is kept on the person."
                    )
                    % _nd.display(person(handle)),
                    None,
                    chunk,
                )
                self.database.add_event(event, self.trans)
                self.stats["events"] += 1
                ref = EventRef()
                ref.set_reference_handle(event.get_handle())
                person(handle).add_event_ref(ref)
                continue
            key = couples[0] if couples else frozenset((handle,))
            entry = family(key, married=True)
            new_date = event.get_date_object()
            if not any(e.get_date_object().is_equal(new_date) for e in entry["events"]):
                entry["events"].append(event)  # both spouses may list the date

        for key, entry in families.items():
            self._create_family(key, entry, person)

        # Siblings: not stored only when the Family already says exactly the
        # same thing (both are children of one Family, and "brother" /
        # "sister" agree with the recorded gender), because the exporter
        # writes that relation back from the Family. Every other sibling
        # relation (half-siblings, no known parents, gender not recorded)
        # is kept as an Association, so no vCard data is lost.
        child_family = {}
        for key, entry in families.items():
            for child in entry["children"]:
                child_family[child] = key
        for a, b, stypes, label in sibling_pairs:
            same_family = a in child_family and child_family[a] == child_family.get(b)
            gender = person(b).get_gender()
            implied = all(
                t == "sibling"
                or (t == "brother" and gender == Person.MALE)
                or (t == "sister" and gender == Person.FEMALE)
                for t in stypes
            )
            if same_family and implied:
                continue
            assoc.append((a, b, label))

        for src, target, label in assoc:
            pref = PersonRef()
            pref.set_reference_handle(target)
            pref.set_relation(label)
            person(src).add_person_ref(pref)
            self.stats["associations"] += 1

        for obj in people.values():
            self.database.commit_person(obj, self.trans)

    def _role_gender(self, person_obj):
        """
        Gender used only to choose the father / mother slot (the Person
        gender is not changed): the recorded gender, else the Gramps
        given-name statistics of this tree, else an English title
        (N prefix / FN start) such as King or Queen.
        """
        gender = person_obj.get_gender()
        if gender in (Person.MALE, Person.FEMALE):
            return gender
        name = person_obj.get_primary_name()
        stats = getattr(self.database, "genderStats", None)
        if stats is not None and name.get_first_name():
            guess = stats.guess_gender(name.get_first_name().split()[0])
            if guess in (Person.MALE, Person.FEMALE):
                return guess
        words = self._words(name.get_title())
        if words & _MALE_TITLES:
            return Person.MALE
        if words & _FEMALE_TITLES:
            return Person.FEMALE
        return Person.UNKNOWN

    def _create_family(self, key, entry, person):
        """Write one Family; father/mother chosen by (guessed) gender."""
        fam = Family()
        members = list(key)
        roles = {h: self._role_gender(person(h)) for h in members}
        if len(members) == 2:
            father, mother = members
            if roles[father] == Person.FEMALE or roles[mother] == Person.MALE:
                father, mother = mother, father
            fam.set_father_handle(father)
            fam.set_mother_handle(mother)
        elif roles[members[0]] == Person.FEMALE:
            fam.set_mother_handle(members[0])
        else:
            fam.set_father_handle(members[0])
        fam.set_relationship(
            FamilyRelType(
                FamilyRelType.MARRIED if entry["married"] else FamilyRelType.UNKNOWN
            )
        )
        for child in entry["children"]:
            cref = ChildRef()
            cref.set_reference_handle(child)
            fam.add_child_ref(cref)
        for event in entry["events"]:
            self.database.add_event(event, self.trans)
            self.stats["events"] += 1
            eref = EventRef()
            eref.set_reference_handle(event.get_handle())
            eref.set_role(EventRoleType(EventRoleType.FAMILY))
            fam.add_event_ref(eref)
        self.database.add_family(fam, self.trans)
        self.stats["families"] += 1
        handle = fam.get_handle()
        for parent in members:
            person(parent).add_family_handle(handle)
        for child in entry["children"]:
            person(child).add_parent_family_handle(handle)
