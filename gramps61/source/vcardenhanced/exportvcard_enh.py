#
# exportvcard_enh.py — Enhanced vCard exporter for Gramps
#
# Supports vCard versions 1.0, 2.1, 3.0 (default), and 4.0.
# Version is selectable in the export wizard via VCardVersionOptionBox.
#
# Based on the Gramps built-in exportvcard.py (RFC 2426 / RFC 6350).
# Original authors: Martin Hawlisch, Donald N. Allingham,
#                   Brian G. Matherly, Jakim Friant, Michiel D. Nauta.
# Enhanced by: Claude (Anthropic, claude-sonnet-4-6) for GEPS 048.
# 2026 revision: Claude (Anthropic, Claude Opus 5.5) — round-trip with
#   importvcard_enh.py: PHOTO/LOGO (large thumbnail of the first gallery
#   image), SOUND, RELATED from Associations, NOTE, CATEGORIES, death and
#   place properties, ORG, IM/social Urls, and replay of preserved
#   "vCard <n> source" lines.
#
# License: GPL v2 or later — see <https://www.gnu.org/licenses/>.
#

"""Export Persons to vCard (RFC 6350 / RFC 2426 / vCard 2.1 / vCard 1.0)."""

# ── Standard library ──────────────────────────────────────────────────
import base64
import logging
import os
import re
from collections import abc
from textwrap import TextWrapper

log = logging.getLogger(".ExportVCardEnh")

# ── Gramps modules ────────────────────────────────────────────────────
from gramps.gen.const import GRAMPS_LOCALE as glocale

_ = glocale.translation.gettext

from gramps.gen.const import IMAGE_DIR, PROGRAM_NAME, THUMB_LARGE
from gramps.version import VERSION
from gramps.gen.lib import AttributeType, Date, EventRoleType, FamilyRelType, Person
from gramps.gen.lib.urltype import UrlType
from gramps.gen.lib.eventtype import EventType
from gramps.gen.display.name import displayer as _nd
from gramps.gen.display.place import displayer as _pd
from gramps.gen.plug.utils import OpenFileOrStdout
from gramps.gen.utils.file import media_path_full
from gramps.gui.plug.export import WriterOptionBox

try:
    from gramps.gen.utils.thumbnails import SIZE_LARGE, get_thumbnail_path

    _THUMBS_OK = True
except Exception:  # GdkPixbuf missing (e.g. headless CLI)
    _THUMBS_OK = False

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    _GTK_OK = True
except Exception:
    _GTK_OK = False


# ── Strings shared with importvcard_enh.py (must stay identical) ──────
PLACEHOLDER_GIVEN = _("unidentified")
PLACEHOLDER_SURNAME = _("vCard Import")
_IM_TYPE = _("Instant Messaging")
_MEDIA_KINDS = {"PHOTO": _("photo"), "LOGO": _("logo"), "SOUND": _("sound")}
_GENDER_IDENTITY = _("Gender identity")
_ROLE_ATTR = _("Role")
_RELATED_ATTR = _("vCard RELATED")

# Url custom type → vCard property
_URL_PROPS = {
    _("Free/Busy"): "FBURL",
    _("Calendar"): "CALURI",
    _("Calendar address"): "CALADRURI",
}
_SOCIAL_TYPE = _("Social Profile")

# IM protocol label (Url description) → legacy property
_IM_LEGACY = {
    "AIM": "X-AIM",
    "ICQ": "X-ICQ",
    "Jabber": "X-JABBER",
    "MSN": "X-MSN",
    "Yahoo": "X-YAHOO",
    "Skype": "X-SKYPE",
    "Google Talk": "X-GOOGLE-TALK",
    "QQ": "X-QQ",
    "Gadu-Gadu": "X-GADUGADU",
}

# Association label → RELATED TYPE (reverse of the importer table)
_RELATION_TYPES = {
    _("Spouse"): "spouse",
    _("Partner"): "partner",
    _("Child"): "child",
    _("Parent"): "parent",
    _("Father"): "father",
    _("Mother"): "mother",
    _("Sibling"): "sibling",
    _("Brother"): "brother",
    _("Sister"): "sister",
    _("Kin"): "kin",
    _("Muse"): "muse",
    _("Crush"): "crush",
    _("Date"): "date",
    _("Sweetheart"): "sweetheart",
    _("Colleague"): "colleague",
    _("Coworker"): "co-worker",
    _("Agent"): "agent",
    _("Assistant"): "assistant",
    _("Manager"): "manager",
    _("Friend"): "friend",
    _("Acquaintance"): "acquaintance",
    _("Met"): "met",
    _("Contact"): "contact",
    _("Neighbor"): "neighbor",
    _("Co-resident"): "co-resident",
    _("Emergency contact"): "emergency",
    _("Same person"): "me",
    _("Related"): "",
    _("Husband"): "husband",
    _("Wife"): "wife",
    _("Son"): "son",
    _("Daughter"): "daughter",
}
# Labels Apple writes as _$!<Label>!$_ (always English)
_APPLE_STD = {
    "father": "Father",
    "mother": "Mother",
    "parent": "Parent",
    "brother": "Brother",
    "sister": "Sister",
    "child": "Child",
    "friend": "Friend",
    "spouse": "Spouse",
    "partner": "Partner",
    "assistant": "Assistant",
    "manager": "Manager",
}

_PROP_LINE_RE = re.compile(r"^(?:[-0-9A-Za-z]+\.)?([-0-9A-Za-z]+)[;:]")
_SOURCE_ATTR_RE = re.compile(r"^vCard \S+ source$")
_GEO_NAME_RE = re.compile(r"^(-?[\d.]+), (-?[\d.]+)$")

_MIME_TYPE_HINT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/gif": "GIF",
    "image/bmp": "BMP",
    "image/tiff": "TIFF",
    "audio/wav": "WAVE",
    "audio/x-wav": "WAVE",
    "audio/mpeg": "MP3",
    "audio/ogg": "OGG",
}


# ── Public entry point ────────────────────────────────────────────────


def exportData(database, filename, user, option_box=None):
    """Function called by Gramps to export persons in vCard format."""
    writer = VCardEnhancedWriter(database, filename, option_box, user)
    try:
        writer.export_data()
    except EnvironmentError as msg:
        user.notify_error(_("Could not create %s") % filename, str(msg))
        return False
    except Exception:
        log.exception("vCard export failed")
        user.notify_error(_("Could not create %s") % filename)
        return False
    return True


# ── Version option box ────────────────────────────────────────────────

VCARD_VERSIONS = ["1.0", "2.1", "3.0", "4.0"]
VCARD_VERSION_DEFAULT = "3.0"


class VCardVersionOptionBox(WriterOptionBox):
    """
    Extends WriterOptionBox with a vCard version selector.

    Pattern adapted from isotammiexportxml.py (Kari Kujansuu).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.vcard_version = VCARD_VERSION_DEFAULT
        self._version_radios = {}

    def get_vcard_version(self):
        return self.vcard_version

    def get_option_box(self):
        option_box = super().get_option_box()

        if not _GTK_OK:
            return option_box

        frame = Gtk.Frame(label=_("vCard version to export"))
        frame.set_margin_top(8)
        frame.set_margin_bottom(4)
        frame.set_margin_start(4)
        frame.set_margin_end(4)

        vbox = Gtk.VBox(spacing=4)
        vbox.set_margin_top(4)
        vbox.set_margin_bottom(4)
        vbox.set_margin_start(8)
        vbox.set_margin_end(8)
        frame.add(vbox)

        _VERSION_LABELS = {
            "1.0": _("1.0  — original Versit spec (rarely needed)"),
            "2.1": _("2.1  — widely supported; used by older phones and apps"),
            "3.0": _("3.0  — RFC 2426; Gramps default; broadest compatibility"),
            "4.0": _("4.0  — RFC 6350; modern standard; richer data types"),
        }

        first_radio = None
        for ver in VCARD_VERSIONS:
            label = _VERSION_LABELS.get(ver, ver)
            if first_radio is None:
                radio = Gtk.RadioButton.new_with_label(None, label)
                first_radio = radio
            else:
                radio = Gtk.RadioButton.new_with_label_from_widget(first_radio, label)
            if ver == VCARD_VERSION_DEFAULT:
                radio.set_active(True)
            self._version_radios[ver] = radio
            vbox.pack_start(radio, False, False, 0)

        option_box.pack_start(frame, False, True, 4)
        option_box.show_all()
        return option_box

    def parse_options(self):
        super().parse_options()
        for ver, radio in self._version_radios.items():
            if radio.get_active():
                self.vcard_version = ver
                break


# ── Main writer class ─────────────────────────────────────────────────


class VCardEnhancedWriter:
    """Write vCard files of a specified version from a Gramps database."""

    LINELENGTH = 73
    ESCAPE_CHAR = "\\"
    TOBE_ESCAPED = ["\\", ",", ";"]

    @staticmethod
    def esc(data):
        """Escape special vCard chars."""
        if isinstance(data, str):
            for char in VCardEnhancedWriter.TOBE_ESCAPED:
                data = data.replace(char, VCardEnhancedWriter.ESCAPE_CHAR + char)
            return data
        elif isinstance(data, list):
            return [VCardEnhancedWriter.esc(x) for x in data]
        elif isinstance(data, tuple):
            return tuple(VCardEnhancedWriter.esc(x) for x in data)
        raise TypeError("VCard escaping not implemented for %s" % type(data))

    @staticmethod
    def esc_text(text):
        """TEXT escape including newlines (NOTE, places, RELATED names)."""
        text = VCardEnhancedWriter.esc(text.replace("\r\n", "\n"))
        return text.replace("\n", "\\n")

    @staticmethod
    def qp_encode(text):
        """QUOTED-PRINTABLE without soft line breaks (vCard 2.1 NOTE)."""
        out = []
        for byte in text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"):
            if 33 <= byte <= 126 and byte != 61 or byte == 32:
                out.append(chr(byte))
            else:
                out.append("=%02X" % byte)
        return "".join(out)

    def __init__(self, database, filename, option_box=None, user=None):
        self.base_db = database
        self.db = database
        self.filename = filename
        self.user = user
        self.filehandle = None
        self.option_box = option_box
        self.vcard_version = VCARD_VERSION_DEFAULT

        if isinstance(getattr(self.user, "callback", None), abc.Callable):
            self.update = self._update_real
        else:
            self.update = self._update_empty

        if option_box:
            option_box.parse_options()
            self.db = option_box.get_filtered_database(self.db)
            if hasattr(option_box, "get_vcard_version"):
                self.vcard_version = option_box.get_vcard_version()

        log.info("Exporting as vCard %s", self.vcard_version)

        self.txtwrp = TextWrapper(
            width=self.LINELENGTH,
            expand_tabs=False,
            replace_whitespace=False,
            drop_whitespace=False,
            subsequent_indent=" ",
        )
        self.count = 0
        self.total = 0
        self.oldval = 0
        self._item = 0  # Apple group counter, per vCard

    @property
    def old_style(self):
        """True for vCard 1.0 / 2.1 parameter and encoding conventions."""
        return self.vcard_version in ("1.0", "2.1")

    def _update_empty(self):
        pass

    def _update_real(self):
        self.count += 1
        newval = int(100 * self.count / self.total)
        if newval != self.oldval:
            self.user.callback(newval)
            self.oldval = newval

    def writeln(self, text):
        """Write a folded vCard line to the output file."""
        self.filehandle.write("%s\r\n" % "\r\n".join(self.txtwrp.wrap(text)))

    # ── Helpers ───────────────────────────────────────────────────────

    def _type_params(self, types):
        """TYPE parameter text: ';HOME;WORK' (2.1) or ';TYPE=home,work'."""
        types = [t.strip().replace(" ", "-") for t in types if t and t.strip()]
        if not types:
            return ""
        if self.old_style:
            return "".join(";" + t.upper() for t in types)
        return ";TYPE=" + ",".join(t.lower() for t in types)

    @staticmethod
    def _desc_types(desc):
        return [d.strip() for d in desc.split(",") if d.strip()] if desc else []

    @staticmethod
    def _attr_values(obj, type_string):
        return [
            a.get_value()
            for a in obj.get_attribute_list()
            if str(a.get_type()) == type_string
        ]

    def _source_lines(self, person):
        """Lines preserved by the importer in 'vCard <n> source' attributes."""
        lines = []
        for attr in person.get_attribute_list():
            if _SOURCE_ATTR_RE.match(str(attr.get_type())):
                lines.extend(l for l in attr.get_value().split("\n") if l.strip())
        return lines

    @staticmethod
    def _line_prop(line):
        m = _PROP_LINE_RE.match(line)
        return m.group(1).upper() if m else ""

    def _uid_of(self, person):
        for line in self._source_lines(person):
            if self._line_prop(line) == "UID":
                return line.split(":", 1)[1].strip()
        return ""

    def _is_stub(self, person):
        """People the importer created for unmatched RELATED names."""
        return any(
            not _PROP_LINE_RE.match(v) for v in self._attr_values(person, _RELATED_ATTR)
        )

    @staticmethod
    def _is_placeholder(name):
        return (
            name.get_first_name() == PLACEHOLDER_GIVEN
            and name.get_surname() == PLACEHOLDER_SURNAME
        )

    def _date_value(self, date):
        """Return (params, value) for a date, or None if not expressible."""
        if date is None or date.is_empty() and not date.get_text():
            return None
        mod = date.get_modifier()
        if mod == Date.MOD_TEXTONLY:
            text = date.get_text().strip()
            if not text:
                return None
            params = ";VALUE=text" if self.vcard_version == "4.0" else ""
            return params, self.esc_text(text)
        if mod in (Date.MOD_SPAN, Date.MOD_RANGE, Date.MOD_FROM, Date.MOD_TO):
            return None
        day, month, year = date.get_start_date()[:3]
        if year and month and day:
            fmt = "%04d%02d%02d" if self.old_style else "%04d-%02d-%02d"
            return "", fmt % (year, month, day)
        if year and month:
            return "", "%04d-%02d" % (year, month)
        if year:
            return "", "%04d" % year
        if month and day:
            return "", "--%02d%02d" % (month, day)
        if month:
            return "", "--%02d" % month
        if day:
            return "", "---%02d" % day
        return None

    def _place_value(self, place_handle):
        """Return (params, value) for BIRTHPLACE / DEATHPLACE."""
        place = self.base_db.get_place_from_handle(place_handle)
        if not place:
            return None
        name = place.get_name().get_value()
        lat, lon = place.get_latitude(), place.get_longitude()
        if lat and lon and _GEO_NAME_RE.match(name or ""):
            return ";VALUE=uri", "geo:%s,%s" % (lat, lon)
        title = _pd.display(self.base_db, place)
        return ("", self.esc_text(title)) if title else None

    # ── Export orchestration ──────────────────────────────────────────

    def export_data(self):
        """Open output file and write one vCard per person."""
        with OpenFileOrStdout(
            self.filename, encoding="utf-8", errors="strict", newline=""
        ) as self.filehandle:
            if self.filehandle:
                self.count = 0
                self.oldval = 0
                self.total = self.db.get_number_of_people() or 1
                for handle in sorted(self.db.iter_person_handles()):
                    self.write_person(handle)
                    self.update()
        return True

    def write_person(self, person_handle):
        """Write one vCard for the given person handle."""
        person = self.db.get_person_from_handle(person_handle)
        if not person or self._is_stub(person):
            return
        self._item = 0
        source = self._source_lines(person)
        source_props = {self._line_prop(l) for l in source}
        prname = person.get_primary_name()

        self.write_header()
        if self._is_placeholder(prname):
            pass  # the original vCard had no N / FN / ORG
        elif self._org_as_name(person, prname, source):
            self.write_formatted_name(prname)  # FN only; ORG is replayed
        else:
            self.write_formatted_name(prname)
            self.write_name(prname)
            if not source_props & {"SORT-STRING", "X-SORT-STRING"}:
                self.write_sortstring(prname)
        self.write_nicknames(person, prname)
        self.write_gender(person)
        self.write_vitals(person)
        self.write_anniversary(person)
        self.write_addresses(person)
        self.write_urls(person)
        self.write_occupation(person)
        self.write_notes(person)
        self.write_categories(person)
        self.write_media(person)
        self.write_related(person)
        self.write_source_lines(person, source)
        self.write_footer()

    def _org_as_name(self, person, prname, source):
        """Business card imported with ORG as surname (and no N)."""
        if prname.get_first_name() or len(prname.get_surname_list()) != 1:
            return False
        for line in source:
            if self._line_prop(line) == "ORG":
                first = line.split(":", 1)[1].split(";")[0].replace("\\", "")
                return first.strip() == prname.get_surname()
        return False

    # ── Header / footer ───────────────────────────────────────────────

    def write_header(self):
        self.writeln("BEGIN:VCARD")
        self.writeln("VERSION:%s" % self.vcard_version)
        if self.vcard_version in ("3.0", "4.0"):
            self.writeln(
                "PRODID:-//Gramps//NONSGML %s %s//EN" % (PROGRAM_NAME, VERSION)
            )

    def write_footer(self):
        self.writeln("END:VCARD")
        self.writeln("")

    # ── FN / N / SORT-STRING / NICKNAME ───────────────────────────────

    def write_formatted_name(self, prname):
        regular_name = prname.get_regular_name().strip()
        title = prname.get_title()
        if title:
            regular_name = "%s %s" % (title, regular_name)
        self.writeln("FN:%s" % self.esc(regular_name))

    def write_name(self, prname):
        given_name = ""
        additional_names = ""

        primary_surname = prname.get_primary_surname()
        surname_list = list(prname.get_surname_list())
        if surname_list and not surname_list[0].get_primary():
            surname_list.remove(primary_surname)
            surname_list.insert(0, primary_surname)
        family_name = ",".join(
            self.esc(
                [
                    (
                        "%s %s %s"
                        % (s.get_prefix(), s.get_surname(), s.get_connector())
                    ).strip()
                    for s in surname_list
                ]
            )
        )

        call_name = prname.get_call_name()
        if call_name:
            given_name = self.esc(call_name)
            additional_list = prname.get_first_name().split()
            if call_name in additional_list:
                additional_list.remove(call_name)
            additional_names = ",".join(self.esc(additional_list))
        else:
            name_list = prname.get_first_name().split()
            if name_list:
                given_name = self.esc(name_list[0])
                if len(name_list) > 1:
                    additional_names = ",".join(self.esc(name_list[1:]))

        hon_prefix = ",".join(self.esc(prname.get_title().split()))
        suffix = ",".join(self.esc(prname.get_suffix().split()))

        self.writeln(
            "N:%s;%s;%s;%s;%s"
            % (family_name, given_name, additional_names, hon_prefix, suffix)
        )

    def write_sortstring(self, prname):
        prop = "X-SORT-STRING" if self.vcard_version == "4.0" else "SORT-STRING"
        self.writeln("%s:%s" % (prop, self.esc(_nd.sort_string(prname))))

    def write_nicknames(self, person, prname):
        nicknames = [
            x.get_nick_name() for x in person.get_alternate_names() if x.get_nick_name()
        ]
        if prname.get_nick_name():
            nicknames.insert(0, prname.get_nick_name())
        if nicknames:
            self.writeln("NICKNAME:%s" % ",".join(self.esc(nicknames)))

    # ── GENDER ────────────────────────────────────────────────────────

    def write_gender(self, person):
        gender = person.get_gender()
        codes = {
            Person.MALE: ("M", "Male"),
            Person.FEMALE: ("F", "Female"),
            Person.OTHER: ("O", "Other"),
        }
        code, label = codes.get(gender, ("", ""))
        identity = (self._attr_values(person, _GENDER_IDENTITY) or [""])[0]
        if self.vcard_version == "4.0":
            if code or identity:
                value = code + (";" + self.esc_text(identity) if identity else "")
                self.writeln("GENDER:%s" % value)
        else:
            if label:
                self.writeln("X-GENDER:%s" % label)
            if identity:  # X-GENDER cannot carry it; use the 4.0 property
                self.writeln("GENDER:%s;%s" % (code, self.esc_text(identity)))

    # ── BDAY / BIRTHPLACE / DEATHDATE / DEATHPLACE ────────────────────

    def write_vitals(self, person):
        for ref, date_prop, place_prop in (
            (person.get_birth_ref(), "BDAY", "BIRTHPLACE"),
            (person.get_death_ref(), "DEATHDATE", "DEATHPLACE"),
        ):
            if not ref:
                continue
            event = self.base_db.get_event_from_handle(ref.ref)
            if not event:
                continue
            value = self._date_value(event.get_date_object())
            if value:
                self.writeln("%s%s:%s" % (date_prop, value[0], value[1]))
            if event.get_place_handle():
                value = self._place_value(event.get_place_handle())
                if value:
                    self.writeln("%s%s:%s" % (place_prop, value[0], value[1]))

    # ── ANNIVERSARY ───────────────────────────────────────────────────

    def write_anniversary(self, person):
        """First Marriage event on the person, else on their first family."""
        events = [
            self.base_db.get_event_from_handle(r.ref)
            for r in person.get_event_ref_list()
        ]
        for fam_handle in person.get_family_handle_list():
            family = self.base_db.get_family_from_handle(fam_handle)
            if family:
                events.extend(
                    self.base_db.get_event_from_handle(r.ref)
                    for r in family.get_event_ref_list()
                    if r.get_role() == EventRoleType.FAMILY
                )
        for event in events:
            if event and event.get_type() == EventType.MARRIAGE:
                value = self._date_value(event.get_date_object())
                if value:
                    prop = (
                        "ANNIVERSARY"
                        if self.vcard_version == "4.0"
                        else "X-ANNIVERSARY"
                    )
                    self.writeln("%s%s:%s" % (prop, value[0], value[1]))
                    return

    # ── ADR / TEL ─────────────────────────────────────────────────────

    def write_addresses(self, person):
        for address in person.get_address_list():
            street = address.get_street()
            city = address.get_city()
            state = address.get_state()
            zipcode = address.get_postal_code()
            country = address.get_country()
            if street or city or state or zipcode or country:
                self.writeln(
                    "ADR:%s;%s;%s;%s;%s;%s;%s"
                    % self.esc(("", "", street, city, state, zipcode, country))
                )
            phone = address.get_phone()
            if phone:
                self.writeln("TEL:%s" % phone)

    # ── URL / EMAIL / IMPP / SOCIALPROFILE / media links ──────────────

    def write_urls(self, person):
        for url in person.get_url_list():
            href = url.get_path()
            if not href:
                continue
            utype = url.get_type()
            label = str(utype)
            types = self._desc_types(url.get_description())

            if utype == UrlType(UrlType.EMAIL):
                if href.startswith("mailto:"):
                    href = href[len("mailto:") :]
                self.writeln("EMAIL%s:%s" % (self._type_params(types), self.esc(href)))
            elif label == _IM_TYPE:
                self._write_im(href, types)
            elif label == _SOCIAL_TYPE:
                prop = (
                    "SOCIALPROFILE"
                    if self.vcard_version == "4.0"
                    else "X-SOCIALPROFILE"
                )
                self.writeln("%s%s:%s" % (prop, self._type_params(types), href))
            elif label in _URL_PROPS:
                self.writeln(
                    "%s%s:%s" % (_URL_PROPS[label], self._type_params(types), href)
                )
            elif label.lower() in _MEDIA_KINDS.values():
                prop = [k for k, v in _MEDIA_KINDS.items() if v == label.lower()][0]
                if self.vcard_version == "4.0":
                    self.writeln("%s:%s" % (prop, href))
                else:
                    value_kw = "URL" if self.old_style else "uri"
                    self.writeln("%s;VALUE=%s:%s" % (prop, value_kw, href))
            else:
                self.writeln("URL%s:%s" % (self._type_params(types), self.esc(href)))

    def _write_im(self, href, types):
        protocol = types[0] if types else ""
        if protocol in _IM_LEGACY and ":" not in href:
            self.writeln(
                "%s%s:%s" % (_IM_LEGACY[protocol], self._type_params(types[1:]), href)
            )
            return
        if protocol and protocol.upper() == href.split(":", 1)[0].upper():
            types = types[1:]  # protocol was derived from the URI scheme
        self.writeln("IMPP%s:%s" % (self._type_params(types), href))

    # ── TITLE / ROLE / ORG ────────────────────────────────────────────

    def write_occupation(self, person):
        """Most recent Occupation: description, Role and Agency attributes."""
        events = [
            e
            for e in [
                self.base_db.get_event_from_handle(r.ref)
                for r in person.get_primary_event_ref_list()
            ]
            if e and e.get_type() == EventType(EventType.OCCUPATION)
        ]
        if not events:
            return
        events.sort(key=lambda x: x.get_date_object())
        event = events[-1]
        occupation = event.get_description()
        role = (self._attr_values(event, _ROLE_ATTR) or [""])[0]
        agency = [
            a.get_value()
            for a in event.get_attribute_list()
            if a.get_type() == AttributeType.AGENCY
        ]
        if occupation:
            if self.vcard_version == "4.0" or role:
                self.writeln("TITLE:%s" % self.esc(occupation))
            else:
                self.writeln("ROLE:%s" % self.esc(occupation))  # built-in style
        if role:
            self.writeln("ROLE:%s" % self.esc(role))
        if agency and agency[0]:
            units = [u.strip() for u in agency[0].split(";")]
            self.writeln("ORG:%s" % ";".join(self.esc(units)))

    # ── NOTE / CATEGORIES ─────────────────────────────────────────────

    def write_notes(self, person):
        for handle in person.get_note_list():
            note = self.base_db.get_note_from_handle(handle)
            text = note.get() if note else ""
            if not text.strip():
                continue
            if self.old_style and ("\n" in text or not text.isascii()):
                self.writeln(
                    "NOTE;ENCODING=QUOTED-PRINTABLE;CHARSET=UTF-8:%s"
                    % self.qp_encode(text)
                )
            else:
                self.writeln("NOTE:%s" % self.esc_text(text))

    def write_categories(self, person):
        names = []
        for handle in person.get_tag_list():
            tag = self.base_db.get_tag_from_handle(handle)
            if tag:
                names.append(self.esc(tag.get_name()))
        if names:
            self.writeln("CATEGORIES:%s" % ",".join(names))

    # ── PHOTO / LOGO / SOUND ──────────────────────────────────────────

    def _media_kind(self, media):
        """Kind marked by the importer in the description, else by MIME."""
        desc = media.get_description()
        for kind, label in _MEDIA_KINDS.items():
            if desc.endswith("(vCard %s)" % label):
                return kind
        mime = media.get_mime_type() or ""
        if mime.startswith("image/"):
            return "PHOTO"
        if mime.startswith("audio/"):
            return "SOUND"
        return None

    def _thumbnail_bytes(self, media, media_ref):
        """PNG bytes of the large Gramps thumbnail (honoring the ref region)."""
        if not _THUMBS_OK:
            log.warning("Thumbnails unavailable; PHOTO/LOGO not exported")
            return None
        full = media_path_full(self.base_db, media.get_path())
        rect = media_ref.get_rectangle()
        if not rect or tuple(rect) == (0, 0, 100, 100):
            rect = None
        os.makedirs(THUMB_LARGE, exist_ok=True)  # absent before first GUI run
        path = get_thumbnail_path(full, media.get_mime_type(), rect, SIZE_LARGE)
        if not path or os.path.dirname(os.path.abspath(path)) == os.path.abspath(
            IMAGE_DIR
        ):
            return None  # Gramps returned a "missing" / generic icon
        with open(path, "rb") as fh:
            return fh.read()

    def write_media(self, person):
        """
        PHOTO = large thumbnail of the first gallery image; LOGO likewise
        from the first image the importer marked as a logo; SOUND embeds
        the first audio file as-is.
        """
        done = set()
        for media_ref in person.get_media_list():
            media = self.base_db.get_media_from_handle(media_ref.ref)
            if not media:
                continue
            kind = self._media_kind(media)
            if not kind or kind in done:
                continue
            try:
                if kind == "SOUND":
                    full = media_path_full(self.base_db, media.get_path())
                    with open(full, "rb") as fh:
                        data = fh.read()
                    mime = media.get_mime_type() or "audio/wav"
                else:
                    data = self._thumbnail_bytes(media, media_ref)
                    mime = "image/png"
            except OSError as err:
                log.warning("Could not read media %s: %s", media.get_path(), err)
                continue
            if not data:
                continue
            done.add(kind)
            self._write_binary(kind, data, mime)

    def _write_binary(self, prop, data, mime):
        b64 = base64.b64encode(data).decode("ascii")
        hint = _MIME_TYPE_HINT.get(mime, mime.split("/")[-1].upper())
        if self.vcard_version == "4.0":
            self.writeln("%s:data:%s;base64,%s" % (prop, mime, b64))
        elif self.vcard_version == "3.0":
            self.writeln("%s;ENCODING=b;TYPE=%s:%s" % (prop, hint, b64))
        else:
            self.writeln("%s;ENCODING=BASE64;TYPE=%s:%s" % (prop, hint, b64))
            self.writeln("")  # 2.1 convention: blank line ends BASE64 data

    # ── RELATED (Associations) ────────────────────────────────────────

    def _relations(self, person):
        """
        (types, label, target handle) for every relation of the person:
        Associations, plus spouses and children from the Families where
        the person is a parent, plus parents and siblings from the
        Families where the person is a child.
        """
        out = []
        seen = set()

        def add(types, label, handle):
            key = (handle, tuple(types))
            if handle and handle != person.get_handle() and key not in seen:
                seen.add(key)
                out.append((types, label, handle))

        for fam_handle in person.get_family_handle_list():
            fam = self.base_db.get_family_from_handle(fam_handle)
            if not fam:
                continue
            other = (
                fam.get_mother_handle()
                if fam.get_father_handle() == person.get_handle()
                else fam.get_father_handle()
            )
            if fam.get_relationship() == FamilyRelType.MARRIED:
                add(["spouse"], _("Spouse"), other)
            else:
                add(["partner"], _("Partner"), other)
            for cref in fam.get_child_ref_list():
                add(["child"], _("Child"), cref.ref)
        for fam_handle in person.get_parent_family_handle_list():
            fam = self.base_db.get_family_from_handle(fam_handle)
            if not fam:
                continue
            for parent in (fam.get_father_handle(), fam.get_mother_handle()):
                add(["parent"], _("Parent"), parent)
            for cref in fam.get_child_ref_list():
                sib = self.base_db.get_person_from_handle(cref.ref)
                gender = sib.get_gender() if sib else Person.UNKNOWN
                if gender == Person.MALE:
                    add(["brother"], _("Brother"), cref.ref)
                elif gender == Person.FEMALE:
                    add(["sister"], _("Sister"), cref.ref)
                else:
                    add(["sibling"], _("Sibling"), cref.ref)
        for pref in person.get_person_ref_list():
            label = pref.get_relation() or _("Related")
            parts = [p.strip() for p in label.split(",") if p.strip()]
            types = [t for t in (_RELATION_TYPES.get(p, p.lower()) for p in parts) if t]
            add(types, label, pref.ref)
        return out

    def write_related(self, person):
        for types, label, handle in self._relations(person):
            target = self.base_db.get_person_from_handle(handle)
            if not target:
                continue
            # A target that is exported as its own vCard and has a UID is
            # linked by URI; otherwise by name, which the importer matches
            # (or recreates as a stub person).
            exported = self.db.get_person_from_handle(
                handle
            ) is not None and not self._is_stub(target)
            uid = self._uid_of(target) if exported else ""
            name = target.get_primary_name().get_regular_name().strip()
            if not (uid or name):
                continue

            if self.vcard_version == "4.0":
                params = ";TYPE=" + ",".join(types) if types else ""
                if uid:
                    self.writeln("RELATED%s:%s" % (params, uid))
                else:
                    self.writeln(
                        "RELATED;VALUE=text%s:%s" % (params, self.esc_text(name))
                    )
            else:
                # Apple grouped form, read by Apple, Android and our importer
                self._item += 1
                if len(types) == 1 and types[0] in _APPLE_STD:
                    ab_label = "_$!<%s>!$_" % _APPLE_STD[types[0]]
                else:
                    ab_label = self.esc_text(label)
                self.writeln(
                    "item%d.X-ABRELATEDNAMES:%s" % (self._item, self.esc_text(name))
                )
                self.writeln("item%d.X-ABLabel:%s" % (self._item, ab_label))

    # ── Preserved source lines ────────────────────────────────────────

    def write_source_lines(self, person, source):
        """Replay lines the importer could not map, plus unresolved RELATED."""
        for line in source:
            if self._line_prop(line) not in ("BEGIN", "END", "VERSION"):
                self.writeln(line)
        for value in self._attr_values(person, _RELATED_ATTR):
            if _PROP_LINE_RE.match(value):
                self.writeln(value)
