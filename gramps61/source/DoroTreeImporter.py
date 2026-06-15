# -*- coding: utf-8 -*-
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Brian McCullough
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

"""DoroTree importer for Gramps.

This is still a structural importer: DoroTree/Paradox table layouts vary, so
field-name mappings are deliberately isolated in ``TABLE_SCHEMAS`` for future
adjustment against real .dte samples.
"""

import logging
import struct
import zipfile

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.lib import ChildRef, Family, Name, NameType, Person, Surname
from gramps.gen.utils.libformatting import ImportInfo

try:
    trans = glocale.get_addon_translator(__file__)
except ValueError:
    trans = glocale.translation
_ = trans.gettext

LOG = logging.getLogger(".DoroTreeImporter")

TABLE_SCHEMAS = {
    "People.db": {
        0: "ID",
        1: "FirstName",
        2: "LastName",
        3: "Gender",
    },
    "Families.db": {
        0: "ID",
        1: "HusbandID",
        2: "WifeID",
        3: "ChildrenIDs",
    },
}


def import_data(database, filename, user):
    """Import a DoroTree .dte ZIP archive into the open Gramps database."""
    database.disable_signals()
    try:
        with zipfile.ZipFile(filename, "r") as archive:
            raw_people = parse_paradox_db(
                _read_member_case_insensitive(archive, "People.db"),
                TABLE_SCHEMAS["People.db"],
            )
            raw_families = parse_paradox_db(
                _read_member_case_insensitive(archive, "Families.db"),
                TABLE_SCHEMAS["Families.db"],
            )

        with DbTxn(_("Import DoroTree Data"), database, batch=True) as trans:
            person_map = _import_people(database, trans, raw_people)
            family_count = _import_families(database, trans, raw_families, person_map)
    except (OSError, KeyError, zipfile.BadZipFile, struct.error, ValueError) as err:
        user.notify_error(_("DoroTree import failed"), str(err))
        LOG.exception("DoroTree import failed")
        return None
    finally:
        database.enable_signals()

    database.request_rebuild()
    return ImportInfo(
        {
            _("People imported"): str(len(person_map)),
            _("Families imported"): str(family_count),
        }
    )


def _import_people(database, trans, raw_people):
    """Create Gramps Person records and return a DoroTree-ID-to-handle map."""
    person_map = {}
    for record in raw_people:
        dt_id = record.get("ID")
        if dt_id in (None, ""):
            continue

        person = Person()
        person.set_primary_name(_make_name(record.get("FirstName"), record.get("LastName")))
        person.set_gender(_parse_gender(record.get("Gender")))
        handle = database.add_person(person, trans)
        person_map[str(dt_id)] = handle
    return person_map


def _import_families(database, trans, raw_families, person_map):
    """Create Gramps Family records and update reciprocal Person family links."""
    family_count = 0
    for record in raw_families:
        family = Family()
        spouse_handles = []
        father_handle = person_map.get(str(record.get("HusbandID")))
        mother_handle = person_map.get(str(record.get("WifeID")))
        if father_handle:
            family.set_father_handle(father_handle)
            spouse_handles.append(father_handle)
        if mother_handle:
            family.set_mother_handle(mother_handle)
            spouse_handles.append(mother_handle)

        child_handles = []
        for child_id in _parse_child_ids(record.get("ChildrenIDs")):
            child_handle = person_map.get(str(child_id))
            if child_handle:
                child_ref = ChildRef()
                child_ref.set_reference_handle(child_handle)
                family.add_child_ref(child_ref)
                child_handles.append(child_handle)

        family_handle = database.add_family(family, trans)
        family_count += 1
        for person_handle in spouse_handles:
            person = database.get_person_from_handle(person_handle)
            person.add_family_handle(family_handle)
            database.commit_person(person, trans)
        for person_handle in child_handles:
            person = database.get_person_from_handle(person_handle)
            person.add_parent_family_handle(family_handle)
            database.commit_person(person, trans)
    return family_count


def _make_name(first_name, last_name):
    """Build a Gramps primary Name with a Surname object for Gramps 5.2."""
    name = Name()
    name.set_type(NameType.BIRTH)
    name.set_first_name(first_name or "")
    if last_name:
        surname = Surname()
        surname.set_surname(last_name)
        name.set_surname_list([surname])
    return name


def _parse_gender(gender_raw):
    """Map DoroTree gender encodings to Gramps 5.2 Person constants."""
    if isinstance(gender_raw, str):
        normalized = gender_raw.strip().upper()
        if normalized in {"F", "FEMALE", "2", "0"}:
            return Person.FEMALE
        if normalized in {"M", "MALE", "1"}:
            return Person.MALE
    elif gender_raw == 2 or gender_raw == 0:
        return Person.FEMALE
    elif gender_raw == 1:
        return Person.MALE
    return Person.UNKNOWN


def _parse_child_ids(value):
    """Normalize child-id fields to strings usable as person-map keys."""
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _read_member_case_insensitive(archive, filename):
    """Read a ZIP member, accepting archives created with different case."""
    names = {name.lower(): name for name in archive.namelist()}
    try:
        return archive.read(names[filename.lower()])
    except KeyError as err:
        raise KeyError(_("Archive member %(name)s not found") % {"name": filename}) from err


def parse_paradox_db(db_bytes, field_names=None):
    """Parse basic Borland Paradox records into dictionaries.

    The parser extracts field specifications and fixed-width records.  It is
    intentionally conservative; unsupported field types are skipped but retain
    cursor position so later mapped fields still align.
    """
    records = []
    if len(db_bytes) < 0x78:
        return records

    record_size = struct.unpack("<H", db_bytes[0:2])[0]
    num_records = struct.unpack("<I", db_bytes[6:10])[0]
    header_size = struct.unpack("<H", db_bytes[0x0C:0x0E])[0]
    num_fields = db_bytes[0x21]
    if not record_size or header_size >= len(db_bytes):
        return records

    fields = []
    field_spec_offset = 0x78
    for idx in range(num_fields):
        offset = field_spec_offset + (idx * 2)
        if offset + 2 > len(db_bytes):
            break
        fields.append({"type": db_bytes[offset], "size": db_bytes[offset + 1]})

    current_offset = header_size
    for _recno in range(num_records):
        if current_offset + record_size > len(db_bytes):
            break
        record_data = db_bytes[current_offset : current_offset + record_size]
        parsed_record = {}
        field_cursor = 0
        for idx, field in enumerate(fields):
            f_size = field["size"]
            f_bytes = record_data[field_cursor : field_cursor + f_size]
            key = field_names.get(idx, "Field_%d" % idx) if field_names else "Field_%d" % idx
            parsed_record[key] = _parse_paradox_value(field["type"], f_size, f_bytes)
            field_cursor += f_size
        records.append(parsed_record)
        current_offset += record_size
    return records


def _parse_paradox_value(field_type, field_size, field_bytes):
    """Decode one Paradox field value."""
    if field_type == 0x01:
        return decode_bilingual_string(field_bytes)
    if field_type in (0x05, 0x06):
        if field_size == 2:
            return struct.unpack(">h", field_bytes)[0]
        if field_size == 4:
            return struct.unpack(">i", field_bytes)[0]
    return None


def decode_bilingual_string(byte_array):
    """Decode padded DoroTree text using Windows Hebrew with UTF-8 fallback."""
    stripped_bytes = byte_array.split(b"\x00")[0].strip()
    try:
        return stripped_bytes.decode("windows-1255")
    except UnicodeDecodeError:
        return stripped_bytes.decode("utf-8", errors="ignore")
