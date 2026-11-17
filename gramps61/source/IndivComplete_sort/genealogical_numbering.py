#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Genealogical numbering systems and identifier options, reusable by any
report, gramplet or tool.

One registry holds every numbering system. Each system is either an
ancestor system (numbers the forebears of a focal person, e.g.
Sosa-Stradonitz/Kekule) or a descendant system (numbers the offspring of a
focal person, e.g. Henry, d'Aboville). A plugin picks one of each,
independently, for one focal person (the Center Person).

The tree is walked once per direction; a system only formats the numbers
and decides their sort order, so a new system is a small class::

    class MySystem(DescendantSystem):
        system_id = "my_system"
        label = N_("My numbering")       # deferred translation
        example = "1, 1-1, 1-2"           # shown in menus

        def format(self, rec):
            return "-".join(str(i) for i in (1,) + rec.path)

    register_system(MySystem())

Pedigree collapse and cousin marriages give one person several numbers;
all of them are kept (up to ``max_numbers``), smallest/first found first.

Every identifier choice is one drop-down list whose "Attribute: <type>"
item shows the attribute type last used in that choice; in the GUI the
item has a submenu with every attribute type (center_person_gui.py).

See GenealogicalNumberingAPI.md for a usage guide.

The ancestor system follows the Sosa numbering in core reports
(ancestorreport.py, detancestralreport.py, gvhourglass.py); the descendant
systems match descendreport.py and detdescendantreport.py, which each
carry their own copies of this logic.
"""

# pylint: disable=too-many-lines
# (one shared module is easier for other addons to copy than several)

# ------------------------
# Python modules
# ------------------------
from __future__ import annotations

import heapq
import importlib.util
import logging
import os
import sys
from collections import deque
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Iterator, NamedTuple

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.lib import AttributeType, Family, Person
from gramps.gen.plug.menu import EnumeratedListOption, Menu
from gramps.gen.plug.report.utils import roman

if TYPE_CHECKING:  # gramps.gen.types is not in Gramps 5.2
    from gramps.gen.db import DbReadBase
    from gramps.gen.types import PersonHandle

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext


def N_(value: str) -> str:  # pylint: disable=invalid-name
    """
    Mark a string for translation without translating it now (the deferred
    translation keyword that make.py passes to xgettext).

    :param value: The untranslated string.
    :returns: The same string.
    """
    return value


Translator = Callable[[str], str]

ANCESTOR = "ancestor"
DESCENDANT = "descendant"
NONE_ID = "none"
GRAMPS_ID = "gramps_id"
ATTR_PREFIX = "attr:"  # option value "attr:<attribute type name>"

# Menu option names used by the helpers below
OPT_FOCAL = "num_focal"
OPT_ANCESTOR = "num_ancestor"
OPT_DESCENDANT = "num_descendant"
# "inc_id" is the name of the core "Include Gramps ID" option, which the
# Person label replaces: saved settings and books carry over (0 = Do not
# include, 1 or 2 = Gramps ID).
OPT_PERSON_LABEL = "inc_id"
OPT_FAMILY_LABEL = "family_label"

# Attribute offered first when none has been used yet
DEFAULT_ATTRIBUTE = AttributeType().xml_str()  # "Identification Number"

PERSON = "person"
FAMILY = "family"

# Center Person choices besides Gramps IDs, resolved when the report runs
HOME_PERSON = "home"
ACTIVE_PERSON = "active"

GUI_MODULE = "center_person_gui"


# ------------------------------------------------------------
#
# NumberRecord
#
# ------------------------------------------------------------
class NumberRecord(NamedTuple):
    """
    One number of one person.

    :param handle: The person handle.
    :param generation: 1 for the focal person.
    :param number: The Sosa number (ancestor systems only).
    :param path: Child positions below the focal person, e.g. (2, 1) is the
        first child of the second child (descendant systems only).
    :param seq: Order found, generation by generation (1 is the focal person).
    :param gen_seq: Order found within its generation.
    """

    handle: PersonHandle
    generation: int
    number: int
    path: tuple[int, ...]
    seq: int
    gen_seq: int


# ------------------------------------------------------------
#
# NumberingSystem
#
# ------------------------------------------------------------
class NumberingSystem:
    """
    Base class of all numbering systems.

    :cvar system_id: Stable identifier, saved in report options and books.
    :cvar direction: ANCESTOR or DESCENDANT.
    :cvar label: Untranslated label (translated when shown).
    :cvar example: Short sample shown in menus, e.g. "1, 11, 1A".
    :cvar unique: True when a person can only have one number.
    :cvar uses_attribute: True for the Attribute systems.
    """

    system_id = ""
    direction = ""
    label = ""
    example = ""
    unique = False
    uses_attribute = False

    def format(self, rec: NumberRecord) -> str:
        """
        Return the display text of one number.

        :param rec: The number to format.
        :returns: The display text.
        """
        raise NotImplementedError

    def display(self, rec: NumberRecord, numbering: Numbering) -> str:
        """
        Return the display text of one number for a Numbering. Systems that
        need the database or the chosen attribute override this; the others
        only implement format().

        :param rec: The number to show.
        :param numbering: The Numbering the number belongs to.
        :returns: The display text.
        """
        del numbering  # only used by the Attribute systems
        return self.format(rec)

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Return a sort key putting numbered people in this system's order.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return (rec.seq,)

    def get_label(self, translate: Translator | None = None) -> str:
        """
        Return the label.

        :param translate: Translation function (default: the GUI language).
        :returns: The translated label.
        """
        return (translate or _)(self.label)

    def get_menu_label(self, translate: Translator | None = None) -> str:
        """
        Return the label with its example, e.g. "Henry numbering (1, 11, 1A)".

        :param translate: Translation function (default: the GUI language).
        :returns: The menu text.
        """
        label = self.get_label(translate)
        return f"{label} ({self.example})" if self.example else label


# ------------------------------------------------------------
#
# AncestorSystem
#
# ------------------------------------------------------------
class AncestorSystem(NumberingSystem):
    """Base for systems numbering the ancestors of the focal person."""

    direction = ANCESTOR

    def format(self, rec: NumberRecord) -> str:
        """
        Return the Sosa number.

        :param rec: The number to format.
        :returns: The display text.
        """
        return str(rec.number)

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort by Sosa number.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return (rec.number,)


# ------------------------------------------------------------
#
# DescendantSystem
#
# ------------------------------------------------------------
class DescendantSystem(NumberingSystem):
    """Base for systems numbering the descendants of the focal person."""

    direction = DESCENDANT

    def format(self, rec: NumberRecord) -> str:
        """
        Return the running number.

        :param rec: The number to format.
        :returns: The display text.
        """
        return str(rec.seq)


# ------------------------------------------------------------
#
# SosaStradonitz
#
# ------------------------------------------------------------
class SosaStradonitz(AncestorSystem):
    """Sosa-Stradonitz (Ahnentafel, Kekule): father 2n, mother 2n+1."""

    system_id = "sosa"
    label = N_("Sosa-Stradonitz number")
    example = "1, 2, 3, 4"


# ------------------------------------------------------------
#
# AhnentafelNumbering
#
# ------------------------------------------------------------
class AhnentafelNumbering(SosaStradonitz):
    """
    Ahnentafel: the same numbers as Sosa-Stradonitz (father 2n, mother
    2n+1), offered under the name many genealogists know it by.
    """

    system_id = "ahnentafel"
    label = N_("Ahnentafel numbering")
    example = "1, 2, 3, 4"


def attribute_value(obj: Person | Family, attribute: str) -> str:
    """
    Return the value of the first attribute of a type.

    :param obj: The Person or Family.
    :param attribute: XML type name such as "Identification Number", or a
        custom type name.
    :returns: The value, or "" when there is none.
    """
    if attribute:
        for attr in obj.get_attribute_list():
            if attr.get_type().xml_str() == attribute and attr.get_value().strip():
                return str(attr.get_value()).strip()
    return ""


def attribute_or_gramps_id(obj: Person | Family, attribute: str) -> str:
    """
    Return an attribute value, or the Gramps ID when there is none.

    :param obj: The Person or Family.
    :param attribute: The attribute type name.
    :returns: The attribute value or the Gramps ID.
    """
    return attribute_value(obj, attribute) or str(obj.get_gramps_id())


def attribute_label(attribute: str, translate: Translator | None = None) -> str:
    """
    Return the display name of an attribute type name.

    :param attribute: The attribute type name.
    :param translate: Translation function (default: the GUI language).
    :returns: The translated label of a standard type, or a custom type
        name unchanged.
    """
    for (
        dummy_value,
        label,
        xml,
    ) in AttributeType._BASEMAP:  # pylint: disable=protected-access
        if xml == attribute:
            return (translate or _)(label)
    return attribute or ""


# ------------------------------------------------------------
#
# AncestorAttribute
#
# ------------------------------------------------------------
class AncestorAttribute(AncestorSystem):
    """
    Ancestors of the focal person, shown by a Person Attribute; without a
    value, by the Numbering fallback (the Person label), else the Gramps ID.
    """

    system_id = "ancestor_attribute"
    label = N_("Attribute")
    unique = True
    uses_attribute = True

    def display(self, rec: NumberRecord, numbering: Numbering) -> str:
        """
        Return the attribute value, the fallback label or the Gramps ID.

        :param rec: The number to show.
        :param numbering: The Numbering, with the attribute and fallback.
        :returns: The display text.
        """
        return _attribute_display(rec, numbering)


# ------------------------------------------------------------
#
# DescendantAttribute
#
# ------------------------------------------------------------
class DescendantAttribute(DescendantSystem):
    """
    Descendants of the focal person, shown by a Person Attribute; without a
    value, by the Numbering fallback (the Person label), else the Gramps ID.
    """

    system_id = "descendant_attribute"
    label = N_("Attribute")
    unique = True
    uses_attribute = True

    def display(self, rec: NumberRecord, numbering: Numbering) -> str:
        """
        Return the attribute value, the fallback label or the Gramps ID.

        :param rec: The number to show.
        :param numbering: The Numbering, with the attribute and fallback.
        :returns: The display text.
        """
        return _attribute_display(rec, numbering)

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort family branch by family branch.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return rec.path


def _attribute_display(rec: NumberRecord, numbering: Numbering) -> str:
    """
    Return the text of an Attribute system number.

    :param rec: The number to show.
    :param numbering: The Numbering, with the attribute and fallback.
    :returns: The attribute value, else the fallback, else the Gramps ID.
    """
    person = numbering.db.get_person_from_handle(rec.handle)
    if person is None:
        return ""
    value = attribute_value(person, numbering.attribute or "")
    if not value and numbering.fallback is not None:
        value = numbering.fallback(person)
    return value or str(person.get_gramps_id())


# ------------------------------------------------------------
#
# SimpleNumbering
#
# ------------------------------------------------------------
class SimpleNumbering(DescendantSystem):
    """Generation number only, as in the Descendant Report."""

    system_id = "simple"
    label = N_("Simple numbering")
    example = "1, 2, 2, 3"
    unique = True

    def format(self, rec: NumberRecord) -> str:
        """
        Return the generation.

        :param rec: The number to format.
        :returns: The display text.
        """
        return str(rec.generation)

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort generation by generation.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return (rec.generation, rec.gen_seq)


HENRY = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# ------------------------------------------------------------
#
# HenryNumbering
#
# ------------------------------------------------------------
class HenryNumbering(DescendantSystem):
    """Henry: one character per generation, 1-9 then A-Z, then (n)."""

    system_id = "henry"
    label = N_("Henry numbering")
    example = "1, 11, 1A"

    def format(self, rec: NumberRecord) -> str:
        """
        Return the Henry number.

        :param rec: The number to format.
        :returns: The display text.
        """
        return "1" + "".join(
            HENRY[i - 1] if i <= len(HENRY) else f"({i})" for i in rec.path
        )

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort family branch by family branch.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return rec.path


# ------------------------------------------------------------
#
# ModifiedHenryNumbering
#
# ------------------------------------------------------------
class ModifiedHenryNumbering(DescendantSystem):
    """Modified Henry: digits 1-9, then (10), (11), ..."""

    system_id = "modified_henry"
    label = N_("Modified Henry numbering")
    example = "1, 11, 1(10)"

    def format(self, rec: NumberRecord) -> str:
        """
        Return the Modified Henry number.

        :param rec: The number to format.
        :returns: The display text.
        """
        return "1" + "".join(str(i) if i < 10 else f"({i})" for i in rec.path)

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort family branch by family branch.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return rec.path


# ------------------------------------------------------------
#
# DAbovilleNumbering
#
# ------------------------------------------------------------
class DAbovilleNumbering(DescendantSystem):
    """d'Aboville: child positions separated by dots, e.g. 1.3.2."""

    system_id = "daboville"
    label = N_("d'Aboville numbering")
    example = "1, 1.1, 1.2.3"

    def format(self, rec: NumberRecord) -> str:
        """
        Return the d'Aboville number.

        :param rec: The number to format.
        :returns: The display text.
        """
        return ".".join(str(i) for i in (1,) + rec.path)

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort family branch by family branch.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return rec.path


PAMA = "abcdefghijklmnopqrstuvwxyz"


# ------------------------------------------------------------
#
# VilliersPamaNumbering
#
# ------------------------------------------------------------
class VilliersPamaNumbering(DescendantSystem):
    """de Villiers/Pama: generation letter plus child position, a1b3c2."""

    system_id = "villiers_pama"
    label = N_("de Villiers/Pama numbering")
    example = "a1, a1b1, a1b2c3"

    @staticmethod
    def _letter(generation: int) -> str:
        """
        Return the letter of a generation.

        :param generation: 1 for the focal person.
        :returns: "a" to "z", then "[27]" and so on.
        """
        if generation <= len(PAMA):
            return PAMA[generation - 1]
        return f"[{generation}]"

    def format(self, rec: NumberRecord) -> str:
        """
        Return the de Villiers/Pama number.

        :param rec: The number to format.
        :returns: The display text.
        """
        return "a1" + "".join(
            self._letter(gen) + str(i) for gen, i in enumerate(rec.path, start=2)
        )

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort family branch by family branch.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return rec.path


# ------------------------------------------------------------
#
# MeurgeyNumbering
#
# ------------------------------------------------------------
class MeurgeyNumbering(DescendantSystem):
    """Meurgey de Tupigny: Roman generation, then order in generation."""

    system_id = "meurgey"
    label = N_("Meurgey de Tupigny numbering")
    example = "I, II-1, III-1"
    unique = True

    def format(self, rec: NumberRecord) -> str:
        """
        Return the Meurgey de Tupigny number.

        :param rec: The number to format.
        :returns: The display text.
        """
        if rec.generation == 1:
            return str(roman(1))
        return f"{roman(rec.generation)}-{rec.gen_seq}"

    def sort_key(self, rec: NumberRecord) -> tuple[int, ...]:
        """
        Sort generation by generation.

        :param rec: The number to sort.
        :returns: The sort key.
        """
        return (rec.generation, rec.gen_seq)


# ------------------------------------------------------------
#
# RecordNumbering
#
# ------------------------------------------------------------
class RecordNumbering(DescendantSystem):
    """Record (Modified Register): one running number, generation order."""

    system_id = "record"
    label = N_("Record (Modified Register) numbering")
    example = "1, 2, 3, 4"
    unique = True


# ------------------------------------------------------------
#
# Registry
#
# ------------------------------------------------------------
_SYSTEMS: dict[str, NumberingSystem] = {}


def register_system(system: NumberingSystem) -> None:
    """
    Add (or replace) a numbering system in the registry.

    :param system: Instance of an AncestorSystem or DescendantSystem subclass.
    :raises ValueError: When the system has no direction or system_id.
    """
    if system.direction not in (ANCESTOR, DESCENDANT) or not system.system_id:
        raise ValueError(_("A numbering system needs a direction and an id."))
    _SYSTEMS[system.system_id] = system


def get_system(system_id: str) -> NumberingSystem | None:
    """
    Return a registered system.

    :param system_id: The system id.
    :returns: The system, or ``None`` when there is none with this id.
    """
    return _SYSTEMS.get(system_id)


def get_systems(
    direction: str, include_attribute: bool = False
) -> list[NumberingSystem]:
    """
    Return the registered systems of one direction, in registry order.

    :param direction: ANCESTOR or DESCENDANT.
    :param include_attribute: Include the Attribute system, which menus
        offer once per attribute type ("Attribute: <type>").
    :returns: The systems.
    """
    return [
        system
        for system in _SYSTEMS.values()
        if system.direction == direction
        and (include_attribute or not system.uses_attribute)
    ]


def attribute_system(direction: str) -> NumberingSystem | None:
    """
    Return the registered Attribute system of one direction.

    :param direction: ANCESTOR or DESCENDANT.
    :returns: The system, or ``None``.
    """
    for system in _SYSTEMS.values():
        if system.direction == direction and system.uses_attribute:
            return system
    return None


for _system in (
    SosaStradonitz(),
    AhnentafelNumbering(),
    AncestorAttribute(),
    SimpleNumbering(),
    HenryNumbering(),
    ModifiedHenryNumbering(),
    DAbovilleNumbering(),
    VilliersPamaNumbering(),
    MeurgeyNumbering(),
    RecordNumbering(),
    DescendantAttribute(),
):
    register_system(_system)


# ------------------------------------------------------------
#
# Tree walking
#
# ------------------------------------------------------------
def _walk_ancestors(
    db: DbReadBase,
    focal_handle: PersonHandle,
    max_generations: int | None,
    max_numbers: int,
) -> Iterator[NumberRecord]:
    """
    Yield ancestor numbers in increasing Sosa number. A priority queue
    keeps the numbers in order, so each person gets their ``max_numbers``
    smallest numbers even with pedigree collapse or loops.

    :param db: The database.
    :param focal_handle: The focal person (number 1).
    :param max_generations: Generations to number, ``None`` for all.
    :param max_numbers: Most numbers kept per person.
    :returns: The numbers.
    """
    heap: list[tuple[int, PersonHandle]] = [(1, focal_handle)]
    counts: dict[PersonHandle, int] = {}
    seq = 0
    while heap:
        number, handle = heapq.heappop(heap)
        if counts.get(handle, 0) >= max_numbers:
            continue
        counts[handle] = counts.get(handle, 0) + 1
        generation = number.bit_length()
        seq += 1
        yield NumberRecord(handle, generation, number, (), seq, 0)
        if max_generations and generation >= max_generations:
            continue
        person = db.get_person_from_handle(handle)
        family_handle = person.get_main_parents_family_handle() if person else None
        family = db.get_family_from_handle(family_handle) if family_handle else None
        if family is None:
            continue
        if family.get_father_handle():
            heapq.heappush(heap, (number * 2, family.get_father_handle()))
        if family.get_mother_handle():
            heapq.heappush(heap, (number * 2 + 1, family.get_mother_handle()))


def _walk_descendants(  # pylint: disable=too-many-locals
    db: DbReadBase,
    focal_handle: PersonHandle,
    max_generations: int | None,
    max_numbers: int,
) -> Iterator[NumberRecord]:
    """
    Yield descendant numbers generation by generation. Children are taken
    family by family, in the order of the person's family list and each
    family's child list (as the core reports do).

    :param db: The database.
    :param focal_handle: The focal person (number 1).
    :param max_generations: Generations to number, ``None`` for all.
    :param max_numbers: Most numbers kept per person.
    :returns: The numbers.
    """
    empty_path: tuple[int, ...] = ()
    queue = deque([(focal_handle, empty_path)])
    counts: dict[PersonHandle, int] = {}
    gen_seq: dict[int, int] = {}
    seq = 0
    while queue:
        handle, path = queue.popleft()
        if counts.get(handle, 0) >= max_numbers:
            continue
        counts[handle] = counts.get(handle, 0) + 1
        generation = len(path) + 1
        seq += 1
        gen_seq[generation] = gen_seq.get(generation, 0) + 1
        yield NumberRecord(handle, generation, 0, path, seq, gen_seq[generation])
        if max_generations and generation >= max_generations:
            continue
        person = db.get_person_from_handle(handle)
        if person is None:
            continue
        index = 0
        for family_handle in person.get_family_handle_list():
            family = db.get_family_from_handle(family_handle)
            if family is None:
                continue
            for child_ref in family.get_child_ref_list():
                index += 1
                queue.append((child_ref.ref, path + (index,)))


# ------------------------------------------------------------
#
# Numbering
#
# ------------------------------------------------------------
class Numbering:
    """
    The numbers one system gives the relatives of one focal person.

    :param db: The database (or proxy).
    :param focal_handle: The focal person (number 1).
    :param system: A registered NumberingSystem, or its system_id.
    :param max_generations: Generations to number, ``None`` for all.
    :param max_numbers: Most numbers kept per person (pedigree collapse).
    :param attribute: Attribute type name, for the Attribute systems.
    :param fallback: Function giving the text the Attribute systems show
        when a person has no value (e.g. a Label).
    :raises ValueError: When the system is unknown.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        db: DbReadBase,
        focal_handle: PersonHandle,
        system: NumberingSystem | str | None,
        max_generations: int | None = None,
        max_numbers: int = 10,
        attribute: str | None = None,
        fallback: Callable[[Person], str] | None = None,
    ) -> None:
        if isinstance(system, str):
            system = get_system(system)
        if system is None:
            raise ValueError(_("Unknown numbering system."))
        self.db = db
        self.system = system
        self.attribute = attribute
        self.fallback = fallback
        self.focal_handle = focal_handle
        limit = 1 if system.unique else max(1, max_numbers)
        walk = _walk_ancestors if system.direction == ANCESTOR else _walk_descendants
        self._records: dict[PersonHandle, list[NumberRecord]] = {}
        for rec in walk(db, focal_handle, max_generations, limit):
            self._records.setdefault(rec.handle, []).append(rec)

    def __contains__(self, handle: object) -> bool:
        """
        Return whether a person is numbered.

        :param handle: The person handle.
        :returns: ``True`` when numbered.
        """
        return handle in self._records

    def __len__(self) -> int:
        """
        Return the number of numbered people.

        :returns: The count.
        """
        return len(self._records)

    def handles(self) -> list[PersonHandle]:
        """
        Return the numbered people, in this system's order.

        :returns: The person handles.
        """
        return sorted(self._records, key=self._sort_key_of)

    def records(self, handle: PersonHandle) -> list[NumberRecord]:
        """
        Return the numbers of a person.

        :param handle: The person handle.
        :returns: The NumberRecords (empty when not numbered).
        """
        return list(self._records.get(handle, []))

    def numbers(self, handle: PersonHandle) -> list[str]:
        """
        Return the display numbers of a person.

        :param handle: The person handle.
        :returns: The display numbers (empty when not numbered).
        """
        return [self.system.display(rec, self) for rec in self._records.get(handle, [])]

    def primary(self, handle: PersonHandle) -> str | None:
        """
        Return the first (smallest) number of a person.

        :param handle: The person handle.
        :returns: The display number, or ``None``.
        """
        recs = self._records.get(handle)
        return self.system.display(recs[0], self) if recs else None

    def generation(self, handle: PersonHandle) -> int | None:
        """
        Return the generation of a person's first number.

        :param handle: The person handle.
        :returns: 1 for the focal person, or ``None``.
        """
        recs = self._records.get(handle)
        return recs[0].generation if recs else None

    def sort_key(self, handle: PersonHandle) -> tuple[int, ...] | None:
        """
        Return the sort key of a person's first number.

        :param handle: The person handle.
        :returns: The sort key, or ``None``.
        """
        recs = self._records.get(handle)
        return self.system.sort_key(recs[0]) if recs else None

    def _sort_key_of(self, handle: PersonHandle) -> tuple[int, ...]:
        """
        Return the sort key of a numbered person.

        :param handle: A numbered person handle.
        :returns: The sort key.
        """
        return self.system.sort_key(self._records[handle][0])


# ------------------------------------------------------------
#
# Label
#
# ------------------------------------------------------------
class Label:
    """
    The label shown for a Person or Family: nothing, its Gramps ID, or an
    attribute value (falling back to the Gramps ID).

    :param choice: NONE_ID, GRAMPS_ID or "attr:<attribute type name>".
    """

    def __init__(self, choice: str = NONE_ID) -> None:
        self.choice = choice or NONE_ID
        self.attribute = split_attribute(self.choice)

    def __bool__(self) -> bool:
        """
        Return whether a label is shown.

        :returns: ``False`` for "Do not include".
        """
        return self.choice != NONE_ID

    def __call__(self, obj: Person | Family | None) -> str:
        """
        Return the label of a Person or Family.

        :param obj: The Person or Family.
        :returns: The label, or "" for "Do not include".
        """
        if obj is None or self.choice == NONE_ID:
            return ""
        if self.attribute:
            return attribute_or_gramps_id(obj, self.attribute)
        return str(obj.get_gramps_id())


# ------------------------------------------------------------
#
# AttributeMemory
#
# ------------------------------------------------------------
SCHEMA_VERSION = "3"


class AttributeMemory:
    """
    Remember the attribute type last used in each attribute choice (keyed
    by option name), in an .ini next to the plugin (Gramps ConfigManager,
    with a [meta] block). An .ini written by another plugin id or another
    schema is replaced.

    :param plugin_id: The plugin id, also the .ini file name.
    :param folder: The plugin folder.
    """

    KEYS = (OPT_PERSON_LABEL, OPT_ANCESTOR, OPT_DESCENDANT, OPT_FAMILY_LABEL)

    def __init__(self, plugin_id: str, folder: str) -> None:
        self.config = configman.register_manager(
            plugin_id,
            os.path.join(folder, plugin_id + ".ini"),
            use_plugins_path=False,
        )
        # Empty defaults, so the real values are written (not commented
        # out as defaults) and a missing or foreign [meta] block shows.
        self.config.register("meta.plugin_id", "")
        self.config.register("meta.schema_version", "")
        for key in self.KEYS:
            self.config.register(f"attributes.{key}", "")
        self.config.load()
        found = (
            self.config.get("meta.plugin_id"),
            self.config.get("meta.schema_version"),
        )
        if found != (plugin_id, SCHEMA_VERSION):
            if found != ("", ""):
                # written by another plugin or an older schema: start over
                self.config.reset()
                self._drop_unknown_keys()
            self.config.set("meta.plugin_id", plugin_id)
            self.config.set("meta.schema_version", SCHEMA_VERSION)
            self.save()

    def _drop_unknown_keys(self) -> None:
        """Forget settings of an older schema that are no longer used."""
        for section, settings in self.config.data.items():
            known = self.config.default.get(section, {})
            for setting in list(settings):
                if setting not in known:
                    del settings[setting]

    def get(self, key: str) -> str:
        """
        Return the attribute type last used in one choice.

        :param key: The option name.
        :returns: The attribute type name, or "".
        """
        if key not in self.KEYS:
            return ""
        return str(self.config.get(f"attributes.{key}"))

    def set(self, key: str, attribute: str) -> None:
        """
        Remember the attribute type used in one choice.

        :param key: The option name.
        :param attribute: The attribute type name.
        """
        if key in self.KEYS and attribute and attribute != self.get(key):
            self.config.set(f"attributes.{key}", attribute)
            self.save()

    def save(self) -> None:
        """Write the .ini, ignoring a read-only plugin folder."""
        try:
            self.config.save()
        except OSError as err:
            LOG.debug("Could not save %s: %s", self.config.filename, err)


_MEMORY: dict[str, AttributeMemory] = {}


def use_attribute_memory(plugin_id: str, folder: str) -> AttributeMemory:
    """
    Remember the attribute types last used in ``folder``/``plugin_id``.ini.
    Call once, from the plugin using these helpers, before building menus.

    :param plugin_id: The plugin id, also the .ini file name.
    :param folder: The plugin folder.
    :returns: The AttributeMemory.
    """
    if "memory" not in _MEMORY:
        _MEMORY["memory"] = AttributeMemory(plugin_id, folder)
    return _MEMORY["memory"]


def _remembered(key: str) -> str:
    """
    Return the attribute type last used in one choice.

    :param key: The option name.
    :returns: The attribute type name, or "".
    """
    memory = _MEMORY.get("memory")
    return memory.get(key) if memory is not None else ""


def _remember(key: str, choice: str) -> None:
    """
    Remember the attribute type of a choice, if it is an attribute.

    :param key: The option name.
    :param choice: The option value.
    """
    attribute = split_attribute(choice)
    memory = _MEMORY.get("memory")
    if attribute and memory is not None:
        memory.set(key, attribute)


# ------------------------------------------------------------
#
# Menu helpers
#
# ------------------------------------------------------------
def split_attribute(choice: Any) -> str:
    """
    Return the attribute type of an "attr:<type>" choice.

    :param choice: The option value.
    :returns: The attribute type name, or "".
    """
    if isinstance(choice, str) and choice.startswith(ATTR_PREFIX):
        return choice[len(ATTR_PREFIX) :]
    return ""


def attribute_items(db: DbReadBase | None, kind: str = PERSON) -> list[tuple[str, str]]:
    """
    Return the Person (or Family) attribute types: the custom types used in
    the tree (sorted), then the standard types.

    :param db: The database, for the custom types (may be ``None``).
    :param kind: PERSON or FAMILY.
    :returns: (attribute type name, display name) pairs.
    """
    standard = [
        (xml, label)
        for value, label, xml in AttributeType._DATAMAP  # pylint: disable=protected-access
        if value not in (AttributeType.UNKNOWN, AttributeType.CUSTOM)
    ]
    custom: list[tuple[str, str]] = []
    if db is not None:
        names = (
            db.get_family_attribute_types()
            if kind == FAMILY
            else db.get_person_attribute_types()
        )
        known = {xml for xml, dummy_label in standard}
        custom = [
            (name, name)
            for name in sorted(set(names), key=glocale.sort_key)
            if name and name not in known
        ]
    return custom + standard


def attribute_choice_text(attribute: str, translate: Translator | None = None) -> str:
    """
    Return "Attribute: <display name>" for an attribute type name.

    :param attribute: The attribute type name.
    :param translate: Translation function (default: the GUI language).
    :returns: The menu text.
    """
    translate = translate or _
    return translate("%(str1)s: %(str2)s") % {
        "str1": translate("Attribute"),
        "str2": attribute_label(attribute, translate),
    }


# ------------------------------------------------------------
#
# AttributeChoiceOption
#
# ------------------------------------------------------------
class AttributeChoiceOption(EnumeratedListOption):
    """
    A drop-down list whose last top-level item is "Attribute: <type>".

    In the GUI (center_person_gui.GuiAttributeChoiceOption) that item has a
    submenu with every attribute type; picking one makes it the shown type.
    The attribute type last used in this choice is remembered. Elsewhere
    (command line, books) the list is flat: the top-level items, then one
    "attr:<type>" item per attribute type, so any type is valid.

    :param label: The option label.
    :param value: The default value.
    :param top_items: (value, text) pairs shown before the Attribute item.
    :param db: The database, for the custom attribute types.
    :param kind: PERSON or FAMILY attribute types.
    :param memory_key: Key of the remembered attribute type (option name).
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        label: str,
        value: str,
        top_items: list[tuple[str, str]],
        db: DbReadBase | None,
        kind: str,
        memory_key: str,
    ) -> None:
        self.db = db
        self.kind = kind
        self._top = list(top_items)
        self._default = value
        self.attribute = _remembered(memory_key) or DEFAULT_ATTRIBUTE
        EnumeratedListOption.__init__(self, label, value)
        self._rebuild()

    def _attribute_types(self) -> list[tuple[str, str]]:
        """
        Return the attribute types, including the shown one.

        :returns: (attribute type name, display name) pairs.
        """
        types = attribute_items(self.db, self.kind)
        if self.attribute not in (name for name, dummy_text in types):
            types.insert(0, (self.attribute, self.attribute))
        return types

    def _rebuild(self) -> None:
        """Rebuild the flat list of items and tell the GUI."""
        items = list(self._top)
        items.append(
            (ATTR_PREFIX + self.attribute, attribute_choice_text(self.attribute))
        )
        for name, dummy_text in self._attribute_types():
            if name != self.attribute:
                items.append((ATTR_PREFIX + name, attribute_choice_text(name)))
        self.set_items(items)
        self.emit("options-changed")

    def get_tree(self) -> list[tuple[str, str, list[tuple[str, str]] | None]]:
        """
        Return the GUI layout. Only the Attribute item has children.

        :returns: (value, text, children) for each top-level item, where
            children are (value, attribute display name) pairs.
        """
        tree: list[tuple[str, str, list[tuple[str, str]] | None]] = [
            (value, text, None) for value, text in self._top
        ]
        children = [
            (ATTR_PREFIX + name, text) for name, text in self._attribute_types()
        ]
        tree.append(
            (
                ATTR_PREFIX + self.attribute,
                attribute_choice_text(self.attribute),
                children,
            )
        )
        return tree

    def set_value(self, value: Any) -> None:
        """
        Set the value; any "attr:<type>" is accepted and becomes the shown
        attribute type. An unknown value gives the default.

        :param value: The new value. A saved "Include Gramps ID" value
            (0, 1 or 2) is converted.
        """
        if not isinstance(value, str) or value in ("0", "1", "2"):
            value = GRAMPS_ID if value not in (0, "0", False) else NONE_ID
        attribute = split_attribute(value)
        if attribute:
            if attribute != self.attribute:
                self.attribute = attribute
                self._rebuild()
        elif value not in (top_value for top_value, dummy_text in self._top):
            value = self._default
        EnumeratedListOption.set_value(self, value)


def add_label_option(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    menu: Menu,
    category_name: str,
    name: str,
    label: str,
    db: DbReadBase | None = None,
    kind: str = PERSON,
    default: str = GRAMPS_ID,
) -> AttributeChoiceOption:
    """
    Add a Label choice: "Do not include", "Gramps ID" and
    "Attribute: <last used type>" (with every type in its GUI submenu).

    :param menu: The menu.
    :param category_name: The tab.
    :param name: The option name.
    :param label: The option label.
    :param db: The database, for the custom attribute types.
    :param kind: PERSON or FAMILY.
    :param default: NONE_ID, GRAMPS_ID or "attr:<type>".
    :returns: The created option.
    """
    _register_gui_options()
    top = [(NONE_ID, _("Do not include")), (GRAMPS_ID, _("Gramps ID"))]
    opt = AttributeChoiceOption(label, default, top, db, kind, name)
    opt.set_help(
        _("An attribute is replaced by the Gramps ID when the attribute has no value.")
    )
    menu.add_option(category_name, name, opt)
    return opt


def add_person_label_option(
    menu: Menu,
    category_name: str,
    db: DbReadBase | None = None,
    default: str = GRAMPS_ID,
) -> AttributeChoiceOption:
    """
    Add the "Person label" choice (option name OPT_PERSON_LABEL).

    :param menu: The menu.
    :param category_name: The tab.
    :param db: The database, for the custom attribute types.
    :param default: NONE_ID, GRAMPS_ID or "attr:<type>".
    :returns: The created option.
    """
    return add_label_option(
        menu, category_name, OPT_PERSON_LABEL, _("Person label"), db, PERSON, default
    )


def add_family_label_option(
    menu: Menu,
    category_name: str,
    db: DbReadBase | None = None,
    default: str = GRAMPS_ID,
) -> AttributeChoiceOption:
    """
    Add the "Family label" choice (option name OPT_FAMILY_LABEL).

    :param menu: The menu.
    :param category_name: The tab.
    :param db: The database, for the custom attribute types.
    :param default: NONE_ID, GRAMPS_ID or "attr:<type>".
    :returns: The created option.
    """
    return add_label_option(
        menu, category_name, OPT_FAMILY_LABEL, _("Family label"), db, FAMILY, default
    )


# ------------------------------------------------------------
#
# CenterPersonOption
#
# ------------------------------------------------------------
class CenterPersonOption(EnumeratedListOption):
    """
    A Center Person drop-down: "Home Person: <name> (<id>)" and
    "Active person: <name> (<id>)" on top, then the bookmarked and recent
    people (each once, sorted by name).

    The value is HOME_PERSON, ACTIVE_PERSON or a Gramps ID; any Gramps ID of
    the tree is accepted (from saved options, books or the command line) and
    added to the list. The GUI widget (center_person_gui.py) adds the active
    and recent people and a "Select a different person" button.

    :param label: The option label.
    :param db: The database.
    """

    def __init__(self, label: str, db: DbReadBase | None) -> None:
        self.db = db
        self.active_handle: PersonHandle | None = None
        self._recent: list[PersonHandle] = []
        self._extra: list[PersonHandle] = []
        EnumeratedListOption.__init__(self, label, HOME_PERSON)
        self.refresh()

    @staticmethod
    def _describe(person: Person | None) -> str:
        """
        Return "<name> (<id>)".

        :param person: The person.
        :returns: The text, or "None".
        """
        if person is None:
            return str(_("None"))
        return f"{name_displayer.display(person)} ({person.get_gramps_id()})"

    def _person(self, handle: PersonHandle | None) -> Person | None:
        """
        Return a person, or ``None`` when the handle is no longer valid.

        :param handle: The person handle.
        :returns: The person.
        """
        if not handle or self.db is None:
            return None
        try:
            return self.db.get_person_from_handle(handle)
        except Exception:  # pylint: disable=broad-exception-caught
            return None  # the handle is no longer in the tree

    def refresh(
        self,
        active_handle: PersonHandle | None = None,
        recent_handles: list[PersonHandle] | None = None,
    ) -> None:
        """
        Rebuild the list. The GUI passes the active person and the recently
        viewed people, which the database does not know.

        :param active_handle: The active person.
        :param recent_handles: The recently viewed people.
        """
        if active_handle is not None:
            self.active_handle = active_handle
        if recent_handles is not None:
            self._recent = list(recent_handles)
        home = self.db.get_default_person() if self.db is not None else None
        items = [
            (
                HOME_PERSON,
                _("%(str1)s: %(str2)s")
                % {"str1": _("Home Person"), "str2": self._describe(home)},
            ),
            (
                ACTIVE_PERSON,
                _("Active person: %s")
                % self._describe(self._person(self.active_handle)),
            ),
        ]
        handles: list[PersonHandle] = []
        if self.db is not None:
            handles.extend(self.db.get_bookmarks().get())
        handles.extend(self._recent)
        handles.extend(self._extra)
        people: dict[str, Person] = {}
        for handle in handles:
            person = self._person(handle)
            if person is not None:
                people[person.get_gramps_id()] = person
        for gid, person in sorted(
            people.items(),
            key=lambda item: glocale.sort_key(name_displayer.sorted(item[1])),
        ):
            items.append((gid, self._describe(person)))
        self.set_items(items)
        self.emit("options-changed")

    def add_person(self, handle: PersonHandle) -> None:
        """
        Add a person to the list and make them the Center Person.

        :param handle: The person handle.
        """
        person = self._person(handle)
        if person is None:
            return
        if handle not in self._extra:
            self._extra.append(handle)
        self.refresh()
        self.set_value(person.get_gramps_id())

    def set_value(self, value: Any) -> None:
        """
        Set the value; a Gramps ID of the tree is added to the list, an
        unknown value gives the Home Person.

        :param value: HOME_PERSON, ACTIVE_PERSON or a Gramps ID.
        """
        if value not in (item_value for item_value, dummy_text in self.get_items()):
            person = None
            if (
                value
                and self.db is not None
                and value
                not in (
                    HOME_PERSON,
                    ACTIVE_PERSON,
                )
            ):
                person = self.db.get_person_from_gramps_id(value)
            if person is not None:
                self._extra.append(person.get_handle())
                self.refresh()
            else:
                value = HOME_PERSON
        EnumeratedListOption.set_value(self, value)

    def get_center_person(self, db: DbReadBase) -> Person | None:
        """
        Return the chosen person: the Home Person, the active person (known
        only while the report dialog is open; else the Home Person), or the
        person with the chosen Gramps ID.

        :param db: The database (or proxy) the report uses.
        :returns: The person, or ``None`` when there is no Home Person.
        """
        value = self.get_value()
        person = None
        if value == ACTIVE_PERSON and self.active_handle:
            person = db.get_person_from_handle(self.active_handle)
        elif value not in (HOME_PERSON, ACTIVE_PERSON):
            person = db.get_person_from_gramps_id(value)
        return person or db.get_default_person()


def _load_gui_module() -> ModuleType:
    """
    Load center_person_gui.py from this module's folder. Gramps removes a
    plugin folder from sys.path once the plugin is imported, so a plain
    import would fail when the report dialog is opened later.

    :returns: The module.
    :raises ImportError: When the module cannot be loaded.
    """
    if GUI_MODULE in sys.modules:
        return sys.modules[GUI_MODULE]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), GUI_MODULE + ".py")
    spec = importlib.util.spec_from_file_location(GUI_MODULE, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[GUI_MODULE] = module
    return module


def _register_gui_options() -> None:
    """Use this module's widgets when the Gramps GUI is running."""
    if "gramps.gui.plug._guioptions" not in sys.modules:
        return
    # pylint: disable=import-outside-toplevel
    from gramps.gen.plug import BasePluginManager

    try:
        gui = _load_gui_module()
    except (ImportError, OSError) as err:
        LOG.warning("Center Person and Attribute menus unavailable: %s", err)
        return
    pmgr = BasePluginManager.get_instance()
    pmgr.register_option(CenterPersonOption, gui.GuiCenterPersonOption)
    pmgr.register_option(AttributeChoiceOption, gui.GuiAttributeChoiceOption)


def add_numbering_options(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    menu: Menu,
    category_name: str,
    db: DbReadBase | None = None,
    ancestor: bool = True,
    descendant: bool = True,
    default_ancestor: str = NONE_ID,
) -> dict[str, EnumeratedListOption]:
    """
    Add Center Person, ancestor and descendant numbering choices to a menu.
    Each choice lists "Do not include", the numbering systems and
    "Attribute: <last used type>", with every attribute type in its submenu
    (in the GUI). The saved values are system ids or "attr:<type>", so books
    and saved report options keep working when systems are added.

    :param menu: The menu.
    :param category_name: The tab.
    :param db: The database, for the custom attribute types.
    :param ancestor: Add the ancestor numbering choice.
    :param descendant: Add the descendant numbering choice.
    :param default_ancestor: Default ancestor system id.
    :returns: The created options, keyed by option name.
    """
    options: dict[str, EnumeratedListOption] = {}
    _register_gui_options()
    focal = CenterPersonOption(_("Center Person"), db)
    focal.set_help(_("The center person for the report"))
    menu.add_option(category_name, OPT_FOCAL, focal)
    options[OPT_FOCAL] = focal

    for wanted, direction, name, label in (
        (ancestor, ANCESTOR, OPT_ANCESTOR, _("Ancestor numbering system")),
        (descendant, DESCENDANT, OPT_DESCENDANT, _("Descendant numbering system")),
    ):
        if not wanted:
            continue
        default = default_ancestor if direction == ANCESTOR else NONE_ID
        top = [(NONE_ID, _("Do not include"))]
        top.extend(
            (system.system_id, system.get_menu_label())
            for system in get_systems(direction)
        )
        opt: EnumeratedListOption
        if attribute_system(direction) is not None:
            opt = AttributeChoiceOption(label, default, top, db, PERSON, name)
        else:
            opt = EnumeratedListOption(label, default)
            opt.set_items(top)
        opt.set_help(
            _(
                "The numbering system to be used. An attribute is replaced "
                "by the Person label when the attribute has no value."
            )
        )
        menu.add_option(category_name, name, opt)
        options[name] = opt
    return options


def _menu_value(menu: Menu, name: str, default: Any = None) -> Any:
    """
    Return the value of a menu option.

    :param menu: The menu.
    :param name: The option name.
    :param default: Value when the menu has no such option.
    :returns: The value.
    """
    option = menu.get_option_by_name(name)
    return option.get_value() if option is not None else default


def resolve_numbering_choice(
    choice: str, direction: str
) -> tuple[NumberingSystem | None, str | None]:
    """
    Return the system and attribute of a numbering choice.

    :param choice: A system id, or "attr:<type>".
    :param direction: ANCESTOR or DESCENDANT.
    :returns: (system or ``None``, attribute type name or ``None``).
    """
    attribute = split_attribute(choice)
    if attribute:
        return attribute_system(direction), attribute
    return get_system(choice), None


def person_label_from_menu(menu: Menu) -> Label:
    """
    Build the Person Label chosen with add_person_label_option().

    :param menu: The menu.
    :returns: The Label.
    """
    choice = _menu_value(menu, OPT_PERSON_LABEL, NONE_ID)
    _remember(OPT_PERSON_LABEL, choice)
    return Label(choice)


def family_label_from_menu(menu: Menu) -> Label:
    """
    Build the Family Label chosen with add_family_label_option().

    :param menu: The menu.
    :returns: The Label.
    """
    choice = _menu_value(menu, OPT_FAMILY_LABEL, NONE_ID)
    _remember(OPT_FAMILY_LABEL, choice)
    return Label(choice)


def numbering_from_menu(
    db: DbReadBase,
    menu: Menu,
    person_label: Label | None = None,
    max_generations: int | None = None,
    max_numbers: int = 10,
) -> tuple[Numbering | None, Numbering | None]:
    """
    Build the numberings chosen with add_numbering_options(). Falls back to
    the Home Person when no Center Person is set.

    :param db: The database (or proxy) the report uses.
    :param menu: The menu.
    :param person_label: Label used when an Attribute numbering has no value.
    :param max_generations: Generations to number, ``None`` for all.
    :param max_numbers: Most numbers kept per person.
    :returns: (ancestor Numbering or ``None``, descendant Numbering or ``None``).
    """
    option = menu.get_option_by_name(OPT_FOCAL)
    if isinstance(option, CenterPersonOption):
        focal = option.get_center_person(db)
    else:
        gid = option.get_value() if option is not None else ""
        focal = db.get_person_from_gramps_id(gid) if gid else None
        focal = focal or db.get_default_person()
    if focal is None:
        return None, None
    result: list[Numbering | None] = []
    for name, direction in ((OPT_ANCESTOR, ANCESTOR), (OPT_DESCENDANT, DESCENDANT)):
        choice = _menu_value(menu, name, NONE_ID)
        _remember(name, choice)
        system, attribute = resolve_numbering_choice(choice, direction)
        result.append(
            Numbering(
                db,
                focal.get_handle(),
                system,
                max_generations,
                max_numbers,
                attribute=attribute,
                fallback=person_label if person_label else None,
            )
            if system
            else None
        )
    return result[0], result[1]
