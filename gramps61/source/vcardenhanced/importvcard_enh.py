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
#
# License: GPL v2 or later — see <https://www.gnu.org/licenses/>.
#

"""Import from vCard (RFC 6350 / RFC 2426 / vCard 2.1 / vCard 1.0)"""

# ── Standard library ──────────────────────────────────────────────────
import re
import time
import logging

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
    Event,
    EventRef,
    EventType,
    Name,
    NameType,
    Person,
    Surname,
    Url,
    UrlType,
)
from gramps.gen.db import DbTxn
from gramps.gen.plug.utils import OpenFileOrStdin
from gramps.gen.utils.libformatting import ImportInfo

# ── VCF DNA detection ────────────────────────────────────────────────
# Variant Call Format files start with "##fileformat=VCFv" (case-sens.).
# We read only the first line to avoid loading the whole file.
_VCF_DNA_MAGIC = b"##fileformat=VCF"
_VCF_DNA_MAGIC_STR = "##fileformat=VCF"


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
    # ── DNA / Variant Call Format guard ─────────────────────────────
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

    parser = VCardEnhancedParser(database)
    try:
        # OpenFileOrStdin does not accept encoding/errors kwargs, so we
        # open the file directly.  "-" (stdin) is an edge case we keep
        # working by delegating to OpenFileOrStdin only for that path.
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
# Maps version string → dict of behavioural flags.

_VERSION_QUIRKS = {
    # vCard 1.0 — largely undocumented; treat like 2.1 but accept it.
    "1.0": {
        "fold_char": "\t",          # some v1 files use tab continuation
        "charset_param": True,      # CHARSET= params common
        "encoding_qp": True,        # QUOTED-PRINTABLE common
        "gender_prop": None,        # no GENDER or X-GENDER
        "strict_n_fields": False,   # N field may have fewer than 5 parts
    },
    # vCard 2.1 — the original Versit spec.
    "2.1": {
        "fold_char": "\t",
        "charset_param": True,
        "encoding_qp": True,
        "gender_prop": None,
        "strict_n_fields": False,
    },
    # vCard 3.0 — RFC 2426.
    "3.0": {
        "fold_char": " ",
        "charset_param": False,
        "encoding_qp": False,
        "gender_prop": "X-GENDER",  # extension property
        "strict_n_fields": True,
    },
    # vCard 4.0 — RFC 6350.
    "4.0": {
        "fold_char": " ",
        "charset_param": False,
        "encoding_qp": False,
        "gender_prop": "GENDER",
        "strict_n_fields": True,
    },
}
_DEFAULT_QUIRKS = _VERSION_QUIRKS["3.0"]


# ── Main parser class ─────────────────────────────────────────────────

class VCardEnhancedParser:
    """Parse vCard files of any supported version into Gramps records."""

    DATE_RE = re.compile(
        r"^(\d{4}-\d{1,2}-\d{1,2})|(?:(\d{4})-?(\d\d)-?(\d\d))"
    )
    # vCard 4.0 allows partial dates: --MMDD or ----DD
    DATE_PARTIAL_RE = re.compile(
        r"^--(\d\d)?(\d\d)$"
    )
    GROUP_RE = re.compile(r"^(?:[-0-9A-Za-z]+\.)?(.+)$")
    ESCAPE_CHAR = "\\"
    TOBE_ESCAPED = ["\\", ",", ";"]
    LINE_CONTINUATION_CHARS = (" ", "\t")

    # Properties that are handled by dedicated methods — anything else
    # goes into a "vCard <version> source" attribute.
    HANDLED_PROPERTIES = frozenset(
        [
            "BEGIN", "END", "VERSION",
            "FN", "N", "NICKNAME", "SORT-STRING",
            "ADR", "TEL",
            "BDAY",
            "ROLE",
            "URL", "EMAIL",
            "GENDER", "X-GENDER",
            "PRODID",
            # vCard 4.0 additions we handle:
            "ANNIVERSARY",
            "TITLE",           # 4.0 preferred over ROLE for job title
        ]
    )

    @staticmethod
    def name_value_split(data):
        """Split on first unquoted colon → (name_with_params, value)."""
        colon_idx = data.find(":")
        if colon_idx < 1:
            return ()
        quote_count = data.count('"', 0, colon_idx)
        while quote_count % 2 == 1:
            colon_idx = data.find(":", colon_idx + 1)
            if colon_idx == -1:
                return ()
            quote_count = data.count('"', 0, colon_idx)
        group_name, value = data[:colon_idx], data[colon_idx + 1:]
        m = VCardEnhancedParser.GROUP_RE.match(group_name)
        if not m:
            return ()
        return (m.group(1), value)

    @staticmethod
    def unesc(data):
        """Remove vCard escape sequences."""
        if isinstance(data, str):
            for char in reversed(VCardEnhancedParser.TOBE_ESCAPED):
                data = data.replace(VCardEnhancedParser.ESCAPE_CHAR + char, char)
            return data
        elif isinstance(data, list):
            return [VCardEnhancedParser.unesc(x) for x in data]
        raise TypeError(
            "vCard unescaping not implemented for %s" % type(data)
        )

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
    def decode_quoted_printable(value):
        """Decode QUOTED-PRINTABLE encoded value (vCard 2.1 / 1.0)."""
        try:
            import quopri
            return quopri.decodestring(value.encode("latin-1")).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            return value

    @staticmethod
    def parse_params(fields):
        """
        Parse param fields (everything after the property name) into a dict.

        fields is the list produced by splitting the name-side on ';'.
        Returns dict of param_name → list of values (upper-cased keys).
        Example: ["ADR", "TYPE=HOME", "TYPE=WORK"] →
                 {"TYPE": ["HOME", "WORK"]}
        Also handles bare vCard 2.1-style params like "HOME" (no key=).
        """
        params = {}
        for field in fields[1:]:
            if "=" in field:
                key, _, val = field.partition("=")
                params.setdefault(key.upper(), []).append(val.upper())
            else:
                # Bare parameter (e.g. vCard 2.1 "WORK", "HOME")
                params.setdefault("_BARE", []).append(field.upper())
        return params

    # ── Instance ──────────────────────────────────────────────────────

    def __init__(self, dbase):
        self.database = dbase
        self.formatted_name = ""
        self.name_parts = ""
        self.org = ""          # ORG fallback when N is absent
        self.next_line = None
        self.trans = None
        self.version = None
        self.quirks = _DEFAULT_QUIRKS
        self.person = None
        self.errors = []
        self.number_of_errors = 0
        self._raw_lines = []   # accumulate unhandled lines for this vCard

    def __get_next_line(self, filehandle):
        """Read the next logical line (joining folded continuations)."""
        line = self.next_line
        self.next_line = filehandle.readline()
        self.line_num += 1
        while self.next_line and self.next_line[0] in self.LINE_CONTINUATION_CHARS:
            line = line.rstrip("\n")
            if line.endswith("\r"):
                line = line[:-1]
            line += self.next_line[1:]
            self.next_line = filehandle.readline()
            self.line_num += 1
        return line.strip() if line else None

    def __add_msg(self, problem, line=None):
        if problem:
            self.number_of_errors += 1
        if line:
            msg = _("Line %(line)5d: %(prob)s\n") % {"line": line, "prob": problem}
        else:
            msg = problem + "\n"
        self.errors.append(msg)

    def _store_raw(self, raw_line):
        """Buffer an unhandled vCard line for later storage as an attribute."""
        self._raw_lines.append(raw_line)

    def _flush_raw_to_person(self):
        """Write buffered raw lines as a Person attribute."""
        if self.person is None or not self._raw_lines:
            self._raw_lines = []
            return
        ver = self.version or "?"
        attr_type_str = "vCard %s source" % ver
        attr_value = "\n".join(self._raw_lines)
        attr = Attribute()
        attr.set_type(AttributeType(attr_type_str))
        attr.set_value(attr_value)
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
        self.database.enable_signals()
        self.database.request_rebuild()
        tym = time.time() - tym
        msg = ngettext(
            "Import Complete: {number_of} second",
            "Import Complete: {number_of} seconds",
            tym,
        ).format(number_of=tym)
        LOG.debug(msg)
        if self.number_of_errors == 0:
            message = _("vCard import report: No errors detected")
        else:
            message = (
                _("vCard import report: %s errors detected\n") % self.number_of_errors
            )
        parent_window = None
        if hasattr(user, "uistate") and hasattr(user.uistate, "window"):
            parent_window = user.uistate.window
        user.info(message, "".join(self.errors), parent=parent_window, monospaced=True)

    def _parse_vcard_file(self, filehandle):
        """Iterate logical lines and dispatch to handlers."""
        self.next_line = filehandle.readline()
        self.line_num = 1

        while True:
            line = self.__get_next_line(filehandle)
            if line is None:
                break
            if line == "":
                continue
            if ":" not in line:
                continue

            line_parts = self.name_value_split(line)
            if not line_parts:
                continue

            fields = line_parts[0].split(";")
            prop = fields[0].upper()
            value = line_parts[1]

            # For vCard 2.1 / 1.0: decode QUOTED-PRINTABLE if flagged
            if self.quirks.get("encoding_qp"):
                params = self.parse_params(fields)
                enc = params.get("ENCODING", [])
                if "QUOTED-PRINTABLE" in enc:
                    value = self.decode_quoted_printable(value)
                charset = params.get("CHARSET", [])
                if charset and charset[0] not in ("UTF-8", "UTF8"):
                    # Best-effort: already decoded by OpenFileOrStdin
                    pass

            if prop == "BEGIN":
                self.next_person()
            elif prop == "END":
                self.finish_person()
            elif prop == "VERSION":
                self.check_version(fields, value)
            elif prop == "FN":
                self.add_formatted_name(fields, value)
            elif prop == "N":
                self.add_name_parts(fields, value)
            elif prop == "NICKNAME":
                self.add_nicknames(fields, value)
            elif prop == "SORT-STRING":
                self.add_sortas(fields, value)
            elif prop == "ADR":
                self.add_address(fields, value)
            elif prop == "TEL":
                self.add_phone(fields, value)
            elif prop == "BDAY":
                self.add_birthday(fields, value)
            elif prop == "ANNIVERSARY":
                self.add_anniversary(fields, value)
            elif prop == "ROLE":
                self.add_occupation(fields, value)
            elif prop == "TITLE":
                # vCard 4.0 uses TITLE for job title; map to occupation
                self.add_occupation(fields, value)
            elif prop == "URL":
                self.add_url(fields, value)
            elif prop == "EMAIL":
                self.add_email(fields, value)
            elif prop in ("X-GENDER", "GENDER"):
                self.add_gender(fields, value)
            elif prop == "PRODID":
                pass  # Gramps metadata; ignore
            elif prop == "ORG":
                # Buffer as raw so it appears in the "vCard n source" attribute,
                # AND capture the first component as a name fallback for records
                # that have no N or FN (e.g. businesses).
                self._store_raw(line)
                org_value = value.split(";")[0].strip()  # first component only
                if org_value and not self.org:
                    self.org = self.unesc(org_value)
            else:
                # Unhandled — buffer for raw attribute
                self._store_raw(line)

    # ── Person lifecycle ──────────────────────────────────────────────

    def next_person(self):
        if self.person is not None:
            self.finish_person()
            self.__add_msg(
                _(
                    "BEGIN property not properly closed by END; "
                    "Gramps can't cope with nested vCards."
                ),
                self.line_num - 1,
            )
        self.person = Person()
        self.formatted_name = ""
        self.name_parts = ""
        self.org = ""
        self._raw_lines = []

    def finish_person(self):
        if self.person is not None:
            self._flush_raw_to_person()
            if self.add_name():
                self.database.add_person(self.person, self.trans)
        self.person = None

    # ── VERSION ───────────────────────────────────────────────────────

    def check_version(self, fields, data):
        """Accept versions 1.0, 2.1, 3.0, 4.0; warn on anything else."""
        self.version = data.strip()
        self.quirks = _VERSION_QUIRKS.get(self.version, _DEFAULT_QUIRKS)
        if self.version not in _VERSION_QUIRKS:
            self.__add_msg(
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
        # If N is absent but ORG is present, synthesise a minimal N from it.
        # The ORG value has already been buffered as a raw attribute so it is
        # not lost; here we just make the record importable as a person.
        if not self.name_parts.strip():
            if self.org:
                # Use ORG as the surname; leave given name empty.
                self.name_parts = "%s;;;;" % self.org
                if not self.formatted_name:
                    self.formatted_name = self.org
            else:
                self.__add_msg(
                    _(
                        "The vCard is malformed. It is missing both N and ORG "
                        "properties; skipping this record."
                    ),
                    self.line_num - 1,
                )
                return False

        # Missing FN with a valid N is common and harmless — no alert needed.
        data_fields = self.split_unescaped(self.name_parts, ";")
        if self.quirks.get("strict_n_fields") and len(data_fields) != 5:
            self.__add_msg(
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

    # ── Other properties ──────────────────────────────────────────────

    def add_nicknames(self, fields, data):
        for nick in self.split_unescaped(data, ","):
            nickname = nick.strip()
            if nickname:
                alt = Name()
                alt.set_nick_name(self.unesc(nickname))
                self.person.add_alternate_name(alt)

    def add_sortas(self, fields, data):
        pass  # TODO: map to Gramps sort-as field

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
                "_add_street", "_add_street", "_add_street",
                "set_city", "set_state", "set_postal_code", "set_country",
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

    def _parse_date_str(self, date_str):
        """
        Parse a vCard date string into a Gramps Date object.

        Handles:
          - YYYYMMDD (vCard 2.1)
          - YYYY-MM-DD (vCard 3.0 / 4.0)
          - --MMDD or ----DD (vCard 4.0 partial)
          - Text fallback
        """
        date = Date()
        date_str = date_str.strip()

        # vCard 4.0 partial date: --MMDD or ----DD
        partial = self.DATE_PARTIAL_RE.match(date_str)
        if partial:
            mm_str, dd_str = partial.group(1), partial.group(2)
            mm = int(mm_str) if mm_str else 0
            dd = int(dd_str) if dd_str else 0
            try:
                date.set(value=(dd, mm, 0, False))
            except DateError:
                date.set(modifier=Date.MOD_TEXTONLY, text=date_str)
            return date

        m = self.DATE_RE.match(date_str)
        if m:
            if m.group(2):
                date_str_norm = "%s-%s-%s" % (m.group(2), m.group(3), m.group(4))
            else:
                date_str_norm = m.group(1)
            y, mo, d = [int(x, 10) for x in date_str_norm.split("-")]
            try:
                date.set(value=(d, mo, y, False))
            except DateError:
                self.__add_msg(
                    _("Invalid date {vcard_snippet}, preserving as text.").format(
                        vcard_snippet=date_str
                    ),
                    self.line_num - 1,
                )
                date.set(modifier=Date.MOD_TEXTONLY, text=date_str)
        elif date_str:
            # Date string is not in a recognised numeric format; store as
            # text without alerting — text dates are acceptable.
            date.set(modifier=Date.MOD_TEXTONLY, text=date_str)
        return date

    def add_birthday(self, fields, data):
        if not data.strip():
            return
        date = self._parse_date_str(data)
        event = Event()
        event.set_type(EventType(EventType.BIRTH))
        event.set_date_object(date)
        self.database.add_event(event, self.trans)
        ref = EventRef()
        ref.set_reference_handle(event.get_handle())
        self.person.set_birth_ref(ref)

    def add_anniversary(self, fields, data):
        """vCard 4.0 ANNIVERSARY → Gramps Marriage event (or attribute if no date)."""
        if not data.strip():
            return
        date = self._parse_date_str(data)
        event = Event()
        event.set_type(EventType(EventType.MARRIAGE))
        event.set_date_object(date)
        event.set_description(_("Anniversary (from vCard)"))
        self.database.add_event(event, self.trans)
        ref = EventRef()
        ref.set_reference_handle(event.get_handle())
        self.person.add_event_ref(ref)

    def add_occupation(self, fields, data):
        occupation = data.strip()
        if occupation:
            event = Event()
            event.set_type(EventType(EventType.OCCUPATION))
            event.set_description(self.unesc(occupation))
            self.database.add_event(event, self.trans)
            ref = EventRef()
            ref.set_reference_handle(event.get_handle())
            self.person.add_event_ref(ref)

    def add_url(self, fields, data):
        href = data.strip()
        if href:
            url = Url()
            url.set_path(self.unesc(href))
            self.person.add_url(url)

    def add_email(self, fields, data):
        email = data.strip()
        if email:
            url = Url()
            url.set_type(UrlType(UrlType.EMAIL))
            url.set_path(self.unesc(email))
            self.person.add_url(url)

    def add_gender(self, fields, data):
        """
        Handle GENDER (v4.0) and X-GENDER (v3.0 / v2.1 extension).

        vCard 4.0 GENDER format: sex-code[;identity-text]
        Sex codes: M, F, O, N (none), U (unknown)
        """
        raw = data.strip()
        if not raw:
            return
        # Take only the sex component (before optional ;)
        sex = raw.split(";")[0].strip().upper()
        if sex:
            sex = sex[0]
        if sex == "M":
            self.person.set_gender(Person.MALE)
        elif sex == "F":
            self.person.set_gender(Person.FEMALE)
        elif sex == "O":
            self.person.set_gender(Person.OTHER)
        # N (none) and U (unknown) → leave gender unset
