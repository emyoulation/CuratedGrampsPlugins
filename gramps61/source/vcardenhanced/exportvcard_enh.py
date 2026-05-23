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
#
# License: GPL v2 or later — see <https://www.gnu.org/licenses/>.
#

"""Export Persons to vCard (RFC 6350 / RFC 2426 / vCard 2.1 / vCard 1.0)."""

# ── Standard library ──────────────────────────────────────────────────
import logging
from collections import abc
from textwrap import TextWrapper

log = logging.getLogger(".ExportVCardEnh")

# ── Gramps modules ────────────────────────────────────────────────────
from gramps.gen.const import GRAMPS_LOCALE as glocale

_ = glocale.translation.gettext

from gramps.gen.const import PROGRAM_NAME
from gramps.version import VERSION
from gramps.gen.lib import Date, Person
from gramps.gen.lib.urltype import UrlType
from gramps.gen.lib.eventtype import EventType
from gramps.gen.display.name import displayer as _nd
from gramps.gen.plug.utils import OpenFileOrStdout
from gramps.gui.plug.export import WriterOptionBox

try:
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    _GTK_OK = True
except Exception:
    _GTK_OK = False


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

        # ── Version selector ──────────────────────────────────────────
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

        # Version descriptions shown next to each radio button
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
                radio = Gtk.RadioButton.new_with_label_from_widget(
                    first_radio, label
                )
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


# ── Per-version writer helpers ────────────────────────────────────────

def _fold_line(text, line_length, continuation):
    """Fold a long vCard property line per RFC."""
    if len(text) <= line_length:
        return text + "\r\n"
    out = []
    while len(text) > line_length:
        out.append(text[:line_length])
        text = continuation + text[line_length:]
    out.append(text)
    return "\r\n".join(out) + "\r\n"


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

    def __init__(self, database, filename, option_box=None, user=None):
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
        self.filehandle.write(
            "%s\r\n" % "\r\n".join(self.txtwrp.wrap(text))
        )

    # ── Export orchestration ──────────────────────────────────────────

    def export_data(self):
        """Open output file and write one vCard per person."""
        with OpenFileOrStdout(
            self.filename, encoding="utf-8", errors="strict", newline=""
        ) as self.filehandle:
            if self.filehandle:
                self.count = 0
                self.oldval = 0
                self.total = self.db.get_number_of_people()
                for handle in sorted(self.db.iter_person_handles()):
                    self.write_person(handle)
                    self.update()
        return True

    def write_person(self, person_handle):
        """Write one vCard for the given person handle."""
        person = self.db.get_person_from_handle(person_handle)
        if not person:
            return
        self.write_header()
        prname = person.get_primary_name()
        self.write_formatted_name(prname)
        self.write_name(prname)
        self.write_sortstring(prname)
        self.write_nicknames(person, prname)
        self.write_gender(person)
        self.write_birthdate(person)
        self.write_anniversary(person)
        self.write_addresses(person)
        self.write_urls(person)
        self.write_occupation(person)
        self.write_footer()

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

    # ── FN ────────────────────────────────────────────────────────────

    def write_formatted_name(self, prname):
        regular_name = prname.get_regular_name().strip()
        title = prname.get_title()
        if title:
            regular_name = "%s %s" % (title, regular_name)
        self.writeln("FN:%s" % self.esc(regular_name))

    # ── N ─────────────────────────────────────────────────────────────

    def write_name(self, prname):
        family_name = ""
        given_name = ""
        additional_names = ""
        hon_prefix = ""
        suffix = ""

        primary_surname = prname.get_primary_surname()
        surname_list = list(prname.get_surname_list())
        if surname_list and not surname_list[0].get_primary():
            surname_list.remove(primary_surname)
            surname_list.insert(0, primary_surname)
        family_name = ",".join(
            self.esc(
                [
                    (
                        "%s %s %s" % (
                            s.get_prefix(),
                            s.get_surname(),
                            s.get_connector(),
                        )
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

    # ── SORT-STRING ───────────────────────────────────────────────────

    def write_sortstring(self, prname):
        if self.vcard_version == "4.0":
            # vCard 4.0 uses SORT-AS parameter on N/FN instead;
            # write as X-SORT-STRING extension for compatibility.
            self.writeln("X-SORT-STRING:%s" % self.esc(_nd.sort_string(prname)))
        else:
            self.writeln("SORT-STRING:%s" % self.esc(_nd.sort_string(prname)))

    # ── NICKNAME ──────────────────────────────────────────────────────

    def write_nicknames(self, person, prname):
        nicknames = [
            x.get_nick_name()
            for x in person.get_alternate_names()
            if x.get_nick_name()
        ]
        if prname.get_nick_name():
            nicknames.insert(0, prname.get_nick_name())
        if nicknames:
            self.writeln("NICKNAME:%s" % ",".join(self.esc(nicknames)))

    # ── GENDER ────────────────────────────────────────────────────────

    def write_gender(self, person):
        gender = person.get_gender()
        if gender == Person.MALE:
            code, label = "M", "Male"
        elif gender == Person.FEMALE:
            code, label = "F", "Female"
        elif gender == Person.OTHER:
            code, label = "O", "Other"
        else:
            return

        ver = self.vcard_version
        if ver == "4.0":
            # RFC 6350: GENDER:M  (sex code only)
            self.writeln("GENDER:%s" % code)
        elif ver == "3.0":
            # Extension used by Gramps built-in and many apps
            self.writeln("X-GENDER:%s" % label)
        elif ver in ("2.1", "1.0"):
            # X-GENDER as informal extension; some apps understand it
            self.writeln("X-GENDER:%s" % label)

    # ── BDAY ─────────────────────────────────────────────────────────

    def write_birthdate(self, person):
        birth_ref = person.get_birth_ref()
        if not birth_ref:
            return
        birth = self.db.get_event_from_handle(birth_ref.ref)
        if not birth:
            return
        b_date = birth.get_date_object()
        mod = b_date.get_modifier()
        if (
            mod == Date.MOD_TEXTONLY
            or b_date.is_empty()
            or mod in (Date.MOD_SPAN, Date.MOD_FROM, Date.MOD_TO, Date.MOD_RANGE)
        ):
            return
        day, month, year, slash = b_date.get_start_date()
        if not (day > 0 and month > 0 and year > 0):
            return
        date_str = "%04d-%02d-%02d" % (year, month, day)
        if self.vcard_version in ("2.1", "1.0"):
            # 2.1 / 1.0 traditionally use YYYYMMDD without hyphens
            date_str_nodash = "%04d%02d%02d" % (year, month, day)
            self.writeln("BDAY:%s" % date_str_nodash)
        else:
            self.writeln("BDAY:%s" % date_str)

    # ── ANNIVERSARY (vCard 4.0) ───────────────────────────────────────

    def write_anniversary(self, person):
        """Write ANNIVERSARY for vCard 4.0 from marriage events."""
        if self.vcard_version != "4.0":
            return
        event_refs = person.get_primary_event_ref_list()
        for ref in event_refs:
            event = self.db.get_event_from_handle(ref.ref)
            if not event:
                continue
            if event.get_type() != EventType(EventType.MARRIAGE):
                continue
            b_date = event.get_date_object()
            mod = b_date.get_modifier()
            if (
                mod == Date.MOD_TEXTONLY
                or b_date.is_empty()
                or mod in (Date.MOD_SPAN, Date.MOD_FROM, Date.MOD_TO, Date.MOD_RANGE)
            ):
                continue
            day, month, year, slash = b_date.get_start_date()
            if day > 0 and month > 0 and year > 0:
                self.writeln(
                    "ANNIVERSARY:%04d-%02d-%02d" % (year, month, day)
                )
            break  # write only first marriage anniversary

    # ── ADR / TEL ─────────────────────────────────────────────────────

    def write_addresses(self, person):
        for address in person.get_address_list():
            postbox = ""
            ext = ""
            street = address.get_street()
            city = address.get_city()
            state = address.get_state()
            zipcode = address.get_postal_code()
            country = address.get_country()
            if street or city or state or zipcode or country:
                self.writeln(
                    "ADR:%s;%s;%s;%s;%s;%s;%s"
                    % self.esc((postbox, ext, street, city, state, zipcode, country))
                )
            phone = address.get_phone()
            if phone:
                self.writeln("TEL:%s" % phone)

    # ── URL / EMAIL ───────────────────────────────────────────────────

    def write_urls(self, person):
        for url in person.get_url_list():
            href = url.get_path()
            if not href:
                continue
            if url.get_type() == UrlType(UrlType.EMAIL):
                if href.startswith("mailto:"):
                    href = href[len("mailto:"):]
                self.writeln("EMAIL:%s" % self.esc(href))
            else:
                self.writeln("URL:%s" % self.esc(href))

    # ── ROLE / TITLE ──────────────────────────────────────────────────

    def write_occupation(self, person):
        """Write ROLE (v1–3.0) or TITLE (v4.0) from the most recent occupation."""
        event_refs = person.get_primary_event_ref_list()
        events = [
            e
            for e in [
                self.db.get_event_from_handle(r.ref) for r in event_refs
            ]
            if e and e.get_type() == EventType(EventType.OCCUPATION)
        ]
        if not events:
            return
        events.sort(key=lambda x: x.get_date_object())
        occupation = events[-1].get_description()
        if not occupation:
            return
        if self.vcard_version == "4.0":
            self.writeln("TITLE:%s" % self.esc(occupation))
        else:
            self.writeln("ROLE:%s" % self.esc(occupation))
