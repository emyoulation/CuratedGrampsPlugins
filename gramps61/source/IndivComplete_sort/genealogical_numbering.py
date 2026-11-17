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
Genealogical numbering systems, reusable by any report, gramplet or tool.

One registry holds every system. Each system is either an ancestor system
(numbers the forebears of a focal person, e.g. Sosa-Stradonitz/Kekule) or
a descendant system (numbers the offspring of a focal person, e.g. Henry,
d'Aboville). A plugin picks one of each, independently, for one focal
person.

The tree is walked once per direction; a system only formats the numbers
and decides their sort order, so a new system is a small class:

    class MySystem(DescendantSystem):
        system_id = "my_system"
        label = _T_("My numbering")       # deferred translation
        def format(self, rec):
            return "-".join(str(i) for i in (1,) + rec.path)

    register_system(MySystem())

Pedigree collapse and cousin marriages give one person several numbers;
all of them are kept (up to ``max_numbers``), smallest/first found first.

Every identifier choice is one drop-down list that folds in the
attribute types, so a menu needs no separate attribute selectors:

* Person label / Family label: "Do not include", "Gramps ID",
  "Attribute: <type>" (the value of that attribute, else the Gramps ID)
* Ancestor / Descendant numbering: "Do not include", the numbering
  systems, "Attribute: <type>" (numbers the same relatives, shows the
  attribute, else the Person label, else the Gramps ID)

Only "Attribute: <type>" shows at the top level, with the type last used
in that choice (remembered, see use_attribute_memory()); in the GUI its
submenu lists every attribute type, custom types first.

Typical use in a report::

    import genealogical_numbering as gn

    gn.use_attribute_memory("<plugin id>", os.path.dirname(__file__))

    # in add_menu_options():
    gn.add_person_label_option(menu, category_name, dbase)
    gn.add_numbering_options(menu, category_name, dbase)
    gn.add_family_label_option(menu, category_name, dbase)

    # in the report:
    person_label = gn.person_label_from_menu(menu)
    family_label = gn.family_label_from_menu(menu)
    anc, desc = gn.numbering_from_menu(self._db, menu, person_label)
    if anc:
        anc.numbers(person_handle)   # -> ["4", "18"]

The ancestor system adapted from the Sosa numbering in core reports
(ancestorreport.py, detancestralreport.py, gvhourglass.py); the descendant
systems match descendreport.py and detdescendantreport.py, which each
carry their own, slightly different, copies of this logic.
"""

# ------------------------
# Python modules
# ------------------------
import heapq
import importlib.util
import logging
import os
import sys
from collections import deque, namedtuple

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.lib import AttributeType
from gramps.gen.plug.menu import EnumeratedListOption
from gramps.gen.plug.report.utils import roman

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext


def _T_(value):  # enable deferred translations (see po/genpot.sh)
    return value


ANCESTOR = "ancestor"
DESCENDANT = "descendant"
NONE_ID = "none"

GRAMPS_ID = "gramps_id"
ATTR_PREFIX = "attr:"  # option value "attr:<attribute type name>"

# Menu option names used by the helpers below
OPT_FOCAL = "num_focal"
OPT_ANCESTOR = "num_ancestor"
OPT_DESCENDANT = "num_descendant"
# "inc_id" is the name of Gramps' own "Include Gramps ID" option, which the
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

# One number of one person.
#   ancestor systems:   number = Sosa number (1 = focal person)
#   descendant systems: path = child positions below the focal person,
#                       e.g. (2, 1) = first child of the second child;
#                       seq = order found, generation by generation (1 = focal)
#                       gen_seq = order found within its generation
#   both:               generation (1 = focal person)
NumberRecord = namedtuple(
    "NumberRecord", ["handle", "generation", "number", "path", "seq", "gen_seq"]
)


# ------------------------------------------------------------
#
# NumberingSystem
#
# ------------------------------------------------------------
class NumberingSystem:
    """
    Base class of all numbering systems.

    :cvar system_id: stable identifier, saved in report options and books
    :cvar direction: ANCESTOR or DESCENDANT
    :cvar label: untranslated label (translated when shown)
    :cvar unique: True when a person can only have one number
    """

    system_id = ""
    direction = ""
    label = ""
    example = ""  # short sample shown in menus, e.g. "1, 11, 1A"
    unique = False
    uses_attribute = False

    def format(self, rec):
        """Return the display text of one NumberRecord."""
        raise NotImplementedError

    def display(self, rec, numbering):
        """
        Return the display text of one NumberRecord for a Numbering.
        Systems that need the database or the chosen attribute override
        this; the others only implement format().
        """
        return self.format(rec)

    def sort_key(self, rec):
        """Return a sort key putting numbered people in this system's order."""
        return (rec.seq,)

    def get_label(self, translate=None):
        """Return the label, translated by ``translate`` (default: GUI)."""
        return (translate or _)(self.label)

    def get_menu_label(self, translate=None):
        """Return the label with its example, e.g. "Henry numbering (1, 11, 1A)"."""
        label = self.get_label(translate)
        return "%s (%s)" % (label, self.example) if self.example else label


# ------------------------------------------------------------
#
# AncestorSystem / DescendantSystem
#
# ------------------------------------------------------------
class AncestorSystem(NumberingSystem):
    """Base for systems numbering the ancestors of the focal person."""

    direction = ANCESTOR

    def sort_key(self, rec):
        return (rec.number,)


class DescendantSystem(NumberingSystem):
    """Base for systems numbering the descendants of the focal person."""

    direction = DESCENDANT


# ------------------------------------------------------------
#
# Built-in systems
#
# ------------------------------------------------------------
class SosaStradonitz(AncestorSystem):
    """Sosa-Stradonitz (Ahnentafel, Kekule): father 2n, mother 2n+1."""

    system_id = "sosa"
    label = _T_("Sosa-Stradonitz number")
    example = "1, 2, 3, 4"

    def format(self, rec):
        return str(rec.number)


class AhnentafelNumbering(SosaStradonitz):
    """
    Ahnentafel: the same numbers as Sosa-Stradonitz (father 2n,
    mother 2n+1), offered under the name many genealogists know it by.
    """

    system_id = "ahnentafel"
    label = _T_("Ahnentafel numbering")
    example = "1, 2, 3, 4"


def attribute_value(obj, attribute):
    """
    Return the value of the first attribute of type ``attribute`` (an XML
    type name such as "Identification Number", or a custom type name) of
    a Person or Family, or "" when it has no such value.
    """
    if attribute:
        for attr in obj.get_attribute_list():
            if attr.get_type().xml_str() == attribute and attr.get_value().strip():
                return attr.get_value().strip()
    return ""


def attribute_or_gramps_id(obj, attribute):
    """Return the attribute value, or the Gramps ID when it has none."""
    return attribute_value(obj, attribute) or obj.get_gramps_id()


def attribute_label(attribute, translate=None):
    """
    Return the display name of an attribute type name: the translated
    label of a standard type, or a custom type name unchanged.
    """
    for value, label, xml in AttributeType._BASEMAP:
        if xml == attribute:
            return (translate or _)(label)
    return attribute or ""


class _AttributeMixin:
    """
    Show a Person Attribute instead of a number; when the person has no
    value, show the Numbering's fallback label (the Person label), and
    when that is empty too, the Gramps ID.
    """

    label = _T_("Attribute")
    unique = True
    uses_attribute = True

    def format(self, rec):
        return ""

    def display(self, rec, numbering):
        person = numbering.db.get_person_from_handle(rec.handle)
        if person is None:
            return ""
        value = attribute_value(person, numbering.attribute)
        if not value and numbering.fallback is not None:
            value = numbering.fallback(person)
        return value or person.get_gramps_id()


class AncestorAttribute(_AttributeMixin, AncestorSystem):
    """Ancestors of the focal person, shown by a Person Attribute."""

    system_id = "ancestor_attribute"


class DescendantAttribute(_AttributeMixin, DescendantSystem):
    """Descendants of the focal person, shown by a Person Attribute."""

    system_id = "descendant_attribute"

    def sort_key(self, rec):
        return rec.path


class SimpleNumbering(DescendantSystem):
    """Generation number only, as in the Descendant Report."""

    system_id = "simple"
    label = _T_("Simple numbering")
    example = "1, 2, 2, 3"
    unique = True

    def format(self, rec):
        return str(rec.generation)

    def sort_key(self, rec):
        return (rec.generation, rec.gen_seq)


HENRY = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class HenryNumbering(DescendantSystem):
    """Henry: one character per generation, 1-9 then A-Z, then (n)."""

    system_id = "henry"
    label = _T_("Henry numbering")
    example = "1, 11, 1A"

    def format(self, rec):
        return "1" + "".join(
            HENRY[i - 1] if i <= len(HENRY) else "(%d)" % i for i in rec.path
        )

    def sort_key(self, rec):
        return rec.path


class ModifiedHenryNumbering(DescendantSystem):
    """Modified Henry: digits 1-9, then (10), (11), ..."""

    system_id = "modified_henry"
    label = _T_("Modified Henry numbering")
    example = "1, 11, 1(10)"

    def format(self, rec):
        return "1" + "".join(str(i) if i < 10 else "(%d)" % i for i in rec.path)

    def sort_key(self, rec):
        return rec.path


class DAbovilleNumbering(DescendantSystem):
    """d'Aboville: child positions separated by dots, e.g. 1.3.2."""

    system_id = "daboville"
    label = _T_("d'Aboville numbering")
    example = "1, 1.1, 1.2.3"

    def format(self, rec):
        return ".".join(str(i) for i in (1,) + rec.path)

    def sort_key(self, rec):
        return rec.path


PAMA = "abcdefghijklmnopqrstuvwxyz"


class VilliersPamaNumbering(DescendantSystem):
    """de Villiers/Pama: generation letter plus child position, a1b3c2."""

    system_id = "villiers_pama"
    label = _T_("de Villiers/Pama numbering")
    example = "a1, a1b1, a1b2c3"

    @staticmethod
    def _letter(generation):
        if generation <= len(PAMA):
            return PAMA[generation - 1]
        return "[%d]" % generation

    def format(self, rec):
        return "a1" + "".join(
            self._letter(gen) + str(i) for gen, i in enumerate(rec.path, start=2)
        )

    def sort_key(self, rec):
        return rec.path


class MeurgeyNumbering(DescendantSystem):
    """Meurgey de Tupigny: Roman generation, then order in generation."""

    system_id = "meurgey"
    label = _T_("Meurgey de Tupigny numbering")
    example = "I, II-1, III-1"
    unique = True

    def format(self, rec):
        if rec.generation == 1:
            return roman(1)
        return "%s-%d" % (roman(rec.generation), rec.gen_seq)

    def sort_key(self, rec):
        return (rec.generation, rec.gen_seq)


class RecordNumbering(DescendantSystem):
    """Record (Modified Register): one running number, generation order."""

    system_id = "record"
    label = _T_("Record (Modified Register) numbering")
    example = "1, 2, 3, 4"
    unique = True

    def format(self, rec):
        return str(rec.seq)


# ------------------------------------------------------------
#
# Registry
#
# ------------------------------------------------------------
_SYSTEMS = {}


def register_system(system):
    """
    Add (or replace) a numbering system in the registry.

    :param system: instance of an AncestorSystem or DescendantSystem subclass
    """
    if system.direction not in (ANCESTOR, DESCENDANT) or not system.system_id:
        raise ValueError("numbering system needs a direction and a system_id")
    _SYSTEMS[system.system_id] = system


def get_system(system_id):
    """Return the registered system with this id, or None."""
    return _SYSTEMS.get(system_id)


def get_systems(direction, include_attribute=False):
    """
    Return the registered systems of one direction, in registry order.
    The Attribute systems are left out unless asked for, because menus
    offer them once per attribute type ("Attribute: <type>").
    """
    return [
        system
        for system in _SYSTEMS.values()
        if system.direction == direction
        and (include_attribute or not system.uses_attribute)
    ]


def attribute_system(direction):
    """Return the registered Attribute system of one direction."""
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
def _walk_ancestors(db, focal_handle, max_generations, max_numbers):
    """
    Yield ancestor NumberRecords in increasing Sosa number.

    A priority queue keeps the numbers in order, so each person gets their
    ``max_numbers`` smallest numbers even with pedigree collapse or loops.
    """
    heap = [(1, focal_handle)]
    counts = {}
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
        if person is None:
            continue
        family_handle = person.get_main_parents_family_handle()
        family = db.get_family_from_handle(family_handle) if family_handle else None
        if family is None:
            continue
        if family.get_father_handle():
            heapq.heappush(heap, (number * 2, family.get_father_handle()))
        if family.get_mother_handle():
            heapq.heappush(heap, (number * 2 + 1, family.get_mother_handle()))


def _walk_descendants(db, focal_handle, max_generations, max_numbers):
    """
    Yield descendant NumberRecords generation by generation.

    Children are taken family by family, in the order of the person's
    family list and each family's child list (as the core reports do).
    """
    queue = deque([(focal_handle, ())])
    counts = {}
    seq = 0
    gen_seq = {}
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

    :param db: database (or proxy)
    :param focal_handle: handle of the focal person (number 1)
    :param system: a registered NumberingSystem (or its system_id)
    :param max_generations: generations to number, None for all
    :param max_numbers: most numbers kept per person (pedigree collapse)
    :param attribute: attribute type name, for the Attribute systems
    :param fallback: function(person) giving the text the Attribute systems
                     show when the person has no value (e.g. a Label)
    """

    def __init__(
        self,
        db,
        focal_handle,
        system,
        max_generations=None,
        max_numbers=10,
        attribute=None,
        fallback=None,
    ):
        if isinstance(system, str):
            system = get_system(system)
        if system is None:
            raise ValueError("unknown numbering system")
        self.db = db
        self.system = system
        self.attribute = attribute
        self.fallback = fallback
        self.focal_handle = focal_handle
        limit = 1 if system.unique else max(1, max_numbers)
        walk = _walk_ancestors if system.direction == ANCESTOR else _walk_descendants
        self._records = {}
        for rec in walk(db, focal_handle, max_generations, limit):
            self._records.setdefault(rec.handle, []).append(rec)

    def __contains__(self, handle):
        return handle in self._records

    def __len__(self):
        return len(self._records)

    def handles(self):
        """Return the numbered handles, in this system's order."""
        return sorted(self._records, key=self.sort_key)

    def records(self, handle):
        """Return the NumberRecords of a person (empty list if none)."""
        return list(self._records.get(handle, []))

    def numbers(self, handle):
        """Return the display numbers of a person (empty list if none)."""
        return [self.system.display(rec, self) for rec in self._records.get(handle, [])]

    def primary(self, handle):
        """Return the first (smallest) number of a person, or None."""
        recs = self._records.get(handle)
        return self.system.display(recs[0], self) if recs else None

    def generation(self, handle):
        """Return the generation of the first number (1 = focal), or None."""
        recs = self._records.get(handle)
        return recs[0].generation if recs else None

    def sort_key(self, handle):
        """Return the sort key of a person's first number, or None."""
        recs = self._records.get(handle)
        return self.system.sort_key(recs[0]) if recs else None


# ------------------------------------------------------------
#
# Label
#
# ------------------------------------------------------------
class Label:
    """
    The label shown for a Person or Family: nothing, its Gramps ID, or an
    attribute value (falling back to the Gramps ID).

    :param choice: NONE_ID, GRAMPS_ID or "attr:<attribute type name>"
    """

    def __init__(self, choice=NONE_ID):
        self.choice = choice or NONE_ID
        self.attribute = split_attribute(self.choice)

    def __bool__(self):
        return self.choice != NONE_ID

    def __call__(self, obj):
        """Return the label text of a Person or Family ("" when none)."""
        if obj is None or self.choice == NONE_ID:
            return ""
        if self.attribute:
            return attribute_or_gramps_id(obj, self.attribute)
        return obj.get_gramps_id()


# ------------------------------------------------------------
#
# AttributeMemory
#
# ------------------------------------------------------------
SCHEMA_VERSION = "3"
_MEMORY = None


class AttributeMemory:
    """
    Remember the attribute type last used in each attribute choice (keyed
    by option name), in an .ini next to the plugin (Gramps ConfigManager,
    with a [meta] block). An .ini written by another plugin id or another
    schema is replaced.
    """

    KEYS = (OPT_PERSON_LABEL, OPT_ANCESTOR, OPT_DESCENDANT, OPT_FAMILY_LABEL)

    def __init__(self, plugin_id, folder):
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
            self.config.register("attributes.%s" % key, "")
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

    def _drop_unknown_keys(self):
        """Forget settings of an older schema that are no longer used."""
        for section, settings in self.config.data.items():
            known = self.config.default.get(section, {})
            for setting in list(settings):
                if setting not in known:
                    del settings[setting]

    def get(self, key):
        """Return the attribute type last used in one choice, or ""."""
        if key not in self.KEYS:
            return ""
        return self.config.get("attributes.%s" % key)

    def set(self, key, attribute):
        """Remember the attribute type used in one choice."""
        if key in self.KEYS and attribute and attribute != self.get(key):
            self.config.set("attributes.%s" % key, attribute)
            self.save()

    def save(self):
        """Write the .ini, ignoring a read-only plugin folder."""
        try:
            self.config.save()
        except OSError:
            pass


def use_attribute_memory(plugin_id, folder):
    """
    Remember the attribute types last used in ``folder``/``plugin_id``.ini.
    Call once, from the plugin using these helpers, before building menus.
    """
    global _MEMORY
    if _MEMORY is None:
        _MEMORY = AttributeMemory(plugin_id, folder)
    return _MEMORY


def _remembered(key):
    return _MEMORY.get(key) if _MEMORY is not None else ""


def _remember(key, choice):
    attribute = split_attribute(choice)
    if attribute and _MEMORY is not None:
        _MEMORY.set(key, attribute)


# ------------------------------------------------------------
#
# Menu helpers
#
# ------------------------------------------------------------
def split_attribute(choice):
    """Return the attribute type of an "attr:<type>" choice, else ""."""
    if choice and choice.startswith(ATTR_PREFIX):
        return choice[len(ATTR_PREFIX) :]
    return ""


def attribute_items(db, kind=PERSON):
    """
    Return (attribute type name, display name) pairs of Person (or Family)
    attribute types: the custom types used in the tree (sorted), then the
    standard types.
    """
    standard = []
    for value, label, xml in AttributeType._DATAMAP:
        if value not in (AttributeType.UNKNOWN, AttributeType.CUSTOM):
            standard.append((xml, label))
    custom = []
    if db is not None:
        names = (
            db.get_family_attribute_types()
            if kind == FAMILY
            else db.get_person_attribute_types()
        )
        known = {xml for xml, label in standard}
        custom = [
            (name, name)
            for name in sorted(set(names), key=glocale.sort_key)
            if name and name not in known
        ]
    return custom + standard


def attribute_choice_text(attribute, translate=None):
    """Return "Attribute: <display name>" for an attribute type name."""
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

    In the GUI (center_person_gui.GuiAttributeChoiceOption) that item has
    a submenu with every attribute type; picking one makes it the shown
    type. The attribute type last used in this choice is remembered.
    Elsewhere (command line, books) the list is flat: the top-level items,
    then one "attr:<type>" item per attribute type, so any type is valid.

    :param top_items: (value, text) pairs shown before the Attribute item
    :param kind: PERSON or FAMILY attribute types
    :param memory_key: key of the remembered attribute type (option name)
    """

    def __init__(self, label, value, top_items, db, kind, memory_key):
        self.db = db
        self.kind = kind
        self._top = list(top_items)
        self._default = value
        self.attribute = _remembered(memory_key) or DEFAULT_ATTRIBUTE
        EnumeratedListOption.__init__(self, label, value)
        self._rebuild()

    def _attribute_types(self):
        types = attribute_items(self.db, self.kind)
        if self.attribute not in (name for name, text in types):
            types.insert(0, (self.attribute, self.attribute))
        return types

    def _rebuild(self):
        items = list(self._top)
        items.append(
            (ATTR_PREFIX + self.attribute, attribute_choice_text(self.attribute))
        )
        for name, dummy_text in self._attribute_types():
            if name != self.attribute:
                items.append((ATTR_PREFIX + name, attribute_choice_text(name)))
        self.set_items(items)
        self.emit("options-changed")

    def get_tree(self):
        """
        Return the GUI layout: [(value, text, children)], where only the
        Attribute item has children: [(value, attribute display name)].
        """
        tree = [(value, text, None) for value, text in self._top]
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

    def set_value(self, value):
        if not isinstance(value, str) or value in ("0", "1", "2"):
            # a saved "Include Gramps ID" value: 0 = no, 1 or 2 = yes
            value = GRAMPS_ID if value not in (0, "0", False) else NONE_ID
        attribute = split_attribute(value)
        if attribute:
            if attribute != self.attribute:
                self.attribute = attribute
                self._rebuild()
        elif value not in (v for v, d in self._top):
            value = self._default
        EnumeratedListOption.set_value(self, value)


def add_label_option(
    menu, category_name, name, label, db=None, kind=PERSON, default=GRAMPS_ID
):
    """
    Add a Label choice: "Do not include", "Gramps ID" and
    "Attribute: <last used type>" (with every type in its GUI submenu).

    :param default: NONE_ID, GRAMPS_ID or "attr:<type>"
    :returns: the created option
    """
    _register_gui_options()
    top = [(NONE_ID, _("Do not include")), (GRAMPS_ID, _("Gramps ID"))]
    opt = AttributeChoiceOption(label, default, top, db, kind, name)
    opt.set_help(
        _(
            "An attribute is replaced by the Gramps ID when the "
            "attribute has no value."
        )
    )
    menu.add_option(category_name, name, opt)
    return opt


def add_person_label_option(menu, category_name, db=None, default=GRAMPS_ID):
    """Add the "Person label" choice (option name OPT_PERSON_LABEL)."""
    return add_label_option(
        menu, category_name, OPT_PERSON_LABEL, _("Person label"), db, PERSON, default
    )


def add_family_label_option(menu, category_name, db=None, default=GRAMPS_ID):
    """Add the "Family label" choice (option name OPT_FAMILY_LABEL)."""
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

    The value is HOME_PERSON, ACTIVE_PERSON or a Gramps ID; any Gramps ID
    of the tree is accepted (from saved options, books or the command
    line) and added to the list. The GUI widget (center_person_gui.py)
    adds the active and recent people and a "Select a different person"
    button.
    """

    def __init__(self, label, db):
        self.db = db
        self.active_handle = None
        self._recent = []
        self._extra = []
        EnumeratedListOption.__init__(self, label, HOME_PERSON)
        self.refresh()

    def _describe(self, person):
        if person is None:
            return _("None")
        return "%s (%s)" % (name_displayer.display(person), person.get_gramps_id())

    def _person(self, handle):
        if not handle or self.db is None:
            return None
        try:
            return self.db.get_person_from_handle(handle)
        except Exception:  # handle no longer in the tree
            return None

    def refresh(self, active_handle=None, recent_handles=None):
        """
        Rebuild the list. The GUI passes the active person and the
        recently viewed people, which the database does not know.
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
        handles = []
        if self.db is not None:
            handles.extend(self.db.get_bookmarks().get())
        handles.extend(self._recent)
        handles.extend(self._extra)
        people = {}
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

    def add_person(self, handle):
        """Add a person to the list and make them the Center Person."""
        person = self._person(handle)
        if person is None:
            return
        if handle not in self._extra:
            self._extra.append(handle)
        self.refresh()
        self.set_value(person.get_gramps_id())

    def set_value(self, value):
        if value not in (v for v, d in self.get_items()):
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

    def get_center_person(self, db):
        """
        Return the chosen person: the Home Person, the active person (known
        only while the report dialog is open; else the Home Person), or the
        person with the chosen Gramps ID.
        """
        value = self.get_value()
        person = None
        if value == ACTIVE_PERSON and self.active_handle:
            person = db.get_person_from_handle(self.active_handle)
        elif value not in (HOME_PERSON, ACTIVE_PERSON):
            person = db.get_person_from_gramps_id(value)
        return person or db.get_default_person()


GUI_MODULE = "center_person_gui"


def _load_gui_module():
    """
    Load center_person_gui.py from this module's folder. Gramps removes a
    plugin's folder from sys.path once the plugin is imported, so a plain
    import would fail when the report dialog is opened later.
    """
    if GUI_MODULE in sys.modules:
        return sys.modules[GUI_MODULE]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), GUI_MODULE + ".py")
    spec = importlib.util.spec_from_file_location(GUI_MODULE, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[GUI_MODULE] = module
    return module


def _register_gui_options():
    """Use this module's widgets when the Gramps GUI is running."""
    if "gramps.gui.plug._guioptions" not in sys.modules:
        return
    try:
        # pylint: disable=import-outside-toplevel
        from gramps.gen.plug import BasePluginManager

        gui = _load_gui_module()
    except (ImportError, OSError) as err:
        LOG.warning("Center Person and Attribute menus unavailable: %s", err)
        return
    pmgr = BasePluginManager.get_instance()
    pmgr.register_option(CenterPersonOption, gui.GuiCenterPersonOption)
    pmgr.register_option(AttributeChoiceOption, gui.GuiAttributeChoiceOption)


def add_numbering_options(
    menu,
    category_name,
    db=None,
    ancestor=True,
    descendant=True,
    default_ancestor=NONE_ID,
):
    """
    Add Center Person, ancestor and descendant numbering choices to a menu.
    Each choice lists "Do not include", the numbering systems and
    "Attribute: <last used type>", with every attribute type in its
    submenu (in the GUI).

    The saved values are system ids or "attr:<type>", so books and saved
    report options keep working when systems are added.

    :param db: database, to offer the custom attribute types it uses
    :returns: dict with the created options, keyed by option name
    """
    options = {}
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


def _menu_value(menu, name, default=None):
    option = menu.get_option_by_name(name)
    return option.get_value() if option is not None else default


def resolve_numbering_choice(choice, direction):
    """
    Return (system, attribute) for a numbering choice: a system id, or
    "attr:<type>" for the Attribute system of ``direction``.
    """
    attribute = split_attribute(choice)
    if attribute:
        return attribute_system(direction), attribute
    return get_system(choice), None


def person_label_from_menu(menu):
    """Build the Person Label chosen with add_person_label_option()."""
    choice = _menu_value(menu, OPT_PERSON_LABEL, NONE_ID)
    _remember(OPT_PERSON_LABEL, choice)
    return Label(choice)


def family_label_from_menu(menu):
    """Build the Family Label chosen with add_family_label_option()."""
    choice = _menu_value(menu, OPT_FAMILY_LABEL, NONE_ID)
    _remember(OPT_FAMILY_LABEL, choice)
    return Label(choice)


def numbering_from_menu(
    db, menu, person_label=None, max_generations=None, max_numbers=10
):
    """
    Build the numberings chosen with add_numbering_options().

    Falls back to the Home Person when no Center Person is set.

    :param person_label: Label used when an Attribute numbering has no value
    :returns: (ancestor Numbering or None, descendant Numbering or None)
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
    fallback = person_label if person_label else None
    result = []
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
                fallback=fallback,
            )
            if system
            else None
        )
    return tuple(result)
