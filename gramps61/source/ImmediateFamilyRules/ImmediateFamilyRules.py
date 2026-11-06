#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Claude Sonnet 4.5, Anthropic
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""
Immediate Family filter rules: people or families in the immediate families
of an anchor (a Person ID, Person filter, Family ID, Family filter or
the Home Person).
"""

# ------------------------
# Python modules
# ------------------------
import logging

# ------------------------
# Gramps modules
# ------------------------
import gramps.gen.filters
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule

try:  # gramps.gen.types is new in Gramps 6.0
    from gramps.gen.types import FamilyHandle, PersonHandle
except ImportError:
    FamilyHandle = PersonHandle = str

# The editor widgets are only needed inside the Filter Editor. Importing
# them lazily-guarded keeps the rules usable from the CLI and in tests.
try:
    from gi.repository import Gtk
    from gramps.gen.display.name import displayer as _nd
    from gramps.gen.utils.db import family_name
    from gramps.gui.editors.filtereditor import MyBoolean, MyList

    _HAVE_GUI = True
except (ImportError, ValueError):
    _HAVE_GUI = False

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

_n_ = _trans.ngettext

# ---------------------------------------------------------------------------
# Anchor type keys (saved in the filter XML, locale independent)
# ---------------------------------------------------------------------------
_ANCHOR_KEYS = [
    "person_id",
    "person_filter",
    "family_id",
    "family_filter",
    "home_person",
]
_ANCHOR_LABELS = [
    _("Person ID"),
    _("Person filter"),
    _("Family ID"),
    _("Family filter"),
    _("Home Person"),  # existing Gramps string
]

# ---------------------------------------------------------------------------
# Relatives, grouped by degrees of separation from the anchor person.
# One step = one parent, child or spouse link. Associations are a direct
# link too, so they sit with the first degree.
# Keys are saved in the filter XML; labels are reused Gramps strings
# where Gramps already has them.
# ---------------------------------------------------------------------------
_DEGREE_1 = [
    ("parents", _("Parents")),
    ("spouses", _("Spouses")),
    ("children", _("Children")),
    ("associations", _("Associations")),
]
_DEGREE_2 = [
    ("siblings", _("Siblings")),
    ("parents_in_law", _("Parents-in-law")),
    ("children_in_law", _("Children-in-law")),
]
_DEGREE_3 = [
    ("siblings_in_law", _("Siblings-in-law")),
]
_ALL_KEYS = {key for row in (_DEGREE_1, _DEGREE_2, _DEGREE_3) for key, _l in row}

# Parameter indices into Rule.list
_P_ANCHOR_TYPE = 0
_P_ANCHOR_VAL = 1
_P_INCLUSIVE = 2
_P_DEGREES = 3  # first of the degree rows


def _degree_label(degree: int) -> str:
    """Row label such as '1 degree:' or '2 degrees:'."""
    return _n_("%d degree:", "%d degrees:", degree) % degree


def _parse_keys(value: str) -> set[str]:
    """Turn a saved 'parents,spouses' string into a set of keys."""
    return {key.strip() for key in (value or "").split(",") if key.strip()}


# ---------------------------------------------------------------------------
# Editor widgets
#
# EditRule (gramps/gui/editors/filtereditor.py, 5.2 through 6.1) builds a
# custom widget only when the labels entry is a tuple (label_text, factory);
# it calls factory(db). See ADVANCED.md.
# ---------------------------------------------------------------------------
def _custom_filter_names(namespace: str) -> list[str]:
    """Return sorted names of the custom filters of one namespace."""
    filters = _get_custom_filters()
    if filters is None:
        return []
    names = {f.get_name() for f in filters.get_filters(namespace)}
    return sorted(names, key=str.lower)


def _make_inclusive(_db):
    """
    The usual Gramps "Include selected Gramps ID" checkbox, but checked
    by default. Label and text are existing Gramps strings.
    """
    box = MyBoolean(_("Include selected Gramps ID"))
    box.set_active(True)
    return box


# EditRule builds the widgets of one rule in label order, so the value
# widget can find the anchor type widget built just before it and follow
# its choice. This is the only link between two rule widgets.
_LAST_ANCHOR_TYPE = None


def _make_anchor_type(_db):
    """Combo box for the anchor types."""
    global _LAST_ANCHOR_TYPE  # pylint: disable=global-statement
    _LAST_ANCHOR_TYPE = MyList(_ANCHOR_KEYS, _ANCHOR_LABELS, default=0)
    return _LAST_ANCHOR_TYPE


def _degree_row(choices: list):
    """Return a factory that builds one row of relative checkboxes."""

    def factory(_db):
        return _DegreeRow(choices)

    return factory


if _HAVE_GUI:

    class _AnchorValue(Gtk.ComboBoxText):
        """
        The value for the chosen anchor type.

        Follows the Anchor type combo built just before it:
        - Person ID / Family ID: type a Gramps ID; the drop-down is empty.
        - Person filter / Family filter: pick (or type) a filter name; the
          drop-down lists only the custom filters of that kind.
        - Home Person: not needed, so the field is grayed out.
        A warning icon appears when the ID or filter name is not found,
        and the tooltip names the person or family when it is.
        """

        def __init__(self, db):
            Gtk.ComboBoxText.__init__(self, has_entry=True)
            self._db = db
            self._type = _LAST_ANCHOR_TYPE
            self._names: list[str] = []
            self._entry = self.get_child()
            self._entry.connect("changed", self._cb_validate)
            if self._type is not None:
                self._type.connect("changed", self._cb_type_changed)
            self._refresh()
            self.show()

        def _key(self) -> str:
            return self._type.get_text() if self._type is not None else "person_id"

        def _cb_type_changed(self, _combo) -> None:
            self._entry.set_text("")  # a value for another type is meaningless
            self._refresh()

        def _refresh(self) -> None:
            key = self._key()
            self.remove_all()
            self._names = []
            if key == "person_filter":
                self._names = _custom_filter_names("Person")
            elif key == "family_filter":
                self._names = _custom_filter_names("Family")
            for name in self._names:
                self.append_text(name)
            hints = {
                "person_id": _("Type the Gramps ID of a person"),
                "family_id": _("Type the Gramps ID of a family"),
                "person_filter": _("Pick a custom Person filter"),
                "family_filter": _("Pick a custom Family filter"),
                "home_person": _("Not needed for the Home Person"),
            }
            self._entry.set_placeholder_text(hints.get(key, ""))
            self.set_sensitive(key != "home_person")
            self._cb_validate(self._entry)

        def _problem(self, key: str, text: str) -> tuple[str | None, str]:
            """Return (warning or None, tooltip) for the current value."""
            if key == "home_person" or not text:
                return None, ""
            if key in ("person_filter", "family_filter"):
                if text in self._names:
                    return None, text
                return _("No custom filter with this name"), ""
            if self._db is None:
                return None, ""
            if key == "person_id":
                person = self._db.get_person_from_gramps_id(text)
                if person is None:
                    return _("No person with this ID"), ""
                return None, _nd.display(person)
            if key == "family_id":
                family = self._db.get_family_from_gramps_id(text)
                if family is None:
                    return _("No family with this ID"), ""
                return None, family_name(family, self._db)
            return None, ""

        def _cb_validate(self, _entry) -> None:
            warning, tip = self._problem(self._key(), self.get_text())
            pos = Gtk.EntryIconPosition.SECONDARY
            self._entry.set_icon_from_icon_name(
                pos, "dialog-warning" if warning else None
            )
            self._entry.set_icon_tooltip_text(pos, warning)
            self._entry.set_tooltip_text(warning or tip or None)

        def get_text(self) -> str:
            """Return the ID or filter name as saved in the rule."""
            return self._entry.get_text().strip()

        def set_text(self, val: str) -> None:
            """Show a saved value."""
            self._entry.set_text(val)

    class _DegreeRow(Gtk.FlowBox):
        """
        One row of checkboxes for relatives at the same degree.

        A FlowBox wraps the checkboxes onto a second line when the dialog
        is narrow. A plain horizontal Box does not: the Add Rule dialog
        puts the values in a scrolled window, so a wide row ran off the
        right edge and hid its last checkboxes (the in-laws).

        Saves the checked keys as a comma-separated string, for example
        "parents,children". All boxes start out checked.
        """

        def __init__(self, choices: list):
            Gtk.FlowBox.__init__(self)
            self.set_selection_mode(Gtk.SelectionMode.NONE)
            self.set_homogeneous(False)
            self.set_min_children_per_line(1)
            self.set_max_children_per_line(len(choices))
            self.set_column_spacing(12)
            self.set_row_spacing(0)
            self._boxes = {}
            for key, label in choices:
                box = Gtk.CheckButton(label=label)
                box.set_active(True)
                self.insert(box, -1)
                # Tab should land on the checkbox, not on its FlowBox cell.
                box.get_parent().set_can_focus(False)
                self._boxes[key] = box
            self.show_all()

        def get_text(self) -> str:
            """Return the checked keys."""
            return ",".join(k for k, box in self._boxes.items() if box.get_active())

        def set_text(self, val: str) -> None:
            """Check the boxes named in a saved value."""
            keys = _parse_keys(val)
            for key, box in self._boxes.items():
                box.set_active(key in keys)

else:
    _AnchorValue = _DegreeRow = None  # never called without a GUI


_PERSON_LABELS = [
    (_("Anchor type:"), _make_anchor_type),
    (_("ID or filter name:"), _AnchorValue),
    (_("Inclusive:"), _make_inclusive),
    (_degree_label(1), _degree_row(_DEGREE_1)),
    (_degree_label(2), _degree_row(_DEGREE_2)),
    (_degree_label(3), _degree_row(_DEGREE_3)),
]
# Families rule: families are counted in steps between families. Two
# families are one step apart when one person belongs to both (as a
# partner or as a child).
_FAMILY_DEGREE_1 = [  # the families of the anchor person
    ("as_child", _("As child")),
    ("as_parent", _("As parent")),
]
_FAMILY_DEGREE_2 = [  # all families of the people in those families
    ("of_parents", _("Parents")),
    ("of_siblings", _("Siblings")),
    ("of_spouses", _("Spouses")),
    ("of_parents_in_law", _("Parents-in-law")),
    ("of_children", _("Children")),
]
_FAMILY_DEGREE_3 = [  # all families of the in-laws, one step further out
    ("of_siblings_in_law", _("Siblings-in-law")),
    ("of_children_in_law", _("Children-in-law")),
]
_FAMILY_ROWS = (_FAMILY_DEGREE_1, _FAMILY_DEGREE_2, _FAMILY_DEGREE_3)
_FAMILY_KEYS = {key for row in _FAMILY_ROWS for key, _l in row}
_FAMILY_DEGREE_OF = {key: n for n, row in enumerate(_FAMILY_ROWS, 1) for key, _l in row}

_FAMILY_LABELS = [
    (_("Anchor type:"), _make_anchor_type),
    (_("ID or filter name:"), _AnchorValue),
    (_("Inclusive:"), _make_inclusive),
    (_degree_label(1), _degree_row(_FAMILY_DEGREE_1)),
    (_degree_label(2), _degree_row(_FAMILY_DEGREE_2)),
    (_degree_label(3), _degree_row(_FAMILY_DEGREE_3)),
]


def _wanted(params: list[str]) -> tuple[bool, set[str]]:
    """Return (inclusive, set of relative keys) from Rule.list."""
    inclusive = len(params) > _P_INCLUSIVE and params[_P_INCLUSIVE] == "1"
    keys = set()
    for value in params[_P_DEGREES:]:
        keys |= _parse_keys(value)
    return inclusive, keys


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _partners(family) -> list:
    """Return the non-empty partner handles of a family."""
    return [h for h in (family.get_father_handle(), family.get_mother_handle()) if h]


def _get_custom_filters():
    """Return the shared custom filter list, loading it if needed."""
    if gramps.gen.filters.CustomFilters is None:
        try:
            gramps.gen.filters.reload_custom_filters()
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Could not load custom filters", exc_info=True)
            return None
    return gramps.gen.filters.CustomFilters


_ACTIVE_FILTERS: set[str] = set()  # guards against self-referencing filters


def _run_named_filter(db, namespace: str, name: str, user, rule_name: str) -> list:
    """Run a custom filter by name and return the matching handles."""
    filters = _get_custom_filters()
    named = filters.get_filters_dict(namespace).get(name) if filters else None
    if named is None:
        LOG.warning("%s: %s filter '%s' not found", rule_name, namespace, name)
        return []
    key = namespace + ":" + name
    if key in _ACTIVE_FILTERS:
        LOG.warning("%s: filter '%s' refers to itself", rule_name, name)
        return []
    _ACTIVE_FILTERS.add(key)
    try:
        return list(named.apply(db, user=user))
    finally:
        _ACTIVE_FILTERS.discard(key)


def _resolve_anchors(db, anchor_type: str, value: str, user, rule_name: str):
    """
    Turn the anchor selection into anchor people and anchor families.

    :returns: (list of Person objects, list of Family objects). A family
        anchor contributes the family itself and both of its partners.
    """
    value = (value or "").strip()
    people, families = [], []

    if anchor_type == "person_id":
        person = db.get_person_from_gramps_id(value)
        if person is None:
            LOG.warning("%s: Person ID '%s' not found", rule_name, value)
        else:
            people.append(person)

    elif anchor_type == "home_person":  # the ID or filter name is ignored
        person = db.get_default_person()
        if person is None:
            LOG.warning("%s: no Home Person is set", rule_name)
        else:
            people.append(person)

    elif anchor_type == "person_filter":
        for handle in _run_named_filter(db, "Person", value, user, rule_name):
            person = db.get_person_from_handle(handle)
            if person is not None:
                people.append(person)

    elif anchor_type in ("family_id", "family_filter"):
        if anchor_type == "family_id":
            family = db.get_family_from_gramps_id(value)
            if family is None:
                LOG.warning("%s: Family ID '%s' not found", rule_name, value)
            else:
                families.append(family)
        else:
            for handle in _run_named_filter(db, "Family", value, user, rule_name):
                family = db.get_family_from_handle(handle)
                if family is not None:
                    families.append(family)
        for family in families:
            for handle in _partners(family):
                person = db.get_person_from_handle(handle)
                if person is not None:
                    people.append(person)

    else:
        LOG.warning("%s: unknown anchor type '%s'", rule_name, anchor_type)

    return people, families


# ---------------------------------------------------------------------------
# Family-graph helpers
# ---------------------------------------------------------------------------
def _families(db, handles) -> list:
    """Return the Family objects for a list of handles, skipping missing ones."""
    result = []
    for handle in handles:
        family = db.get_family_from_handle(handle)
        if family is not None:
            result.append(family)
    return result


def _children(family) -> list:
    """Return the child handles of a family."""
    return [ref.ref for ref in family.get_child_ref_list()]


def _spouses_of(db, person_handle) -> list:
    """Return (spouse handle, family handle) pairs for one person."""
    person = db.get_person_from_handle(person_handle)
    if person is None:
        return []
    pairs = []
    for family in _families(db, person.get_family_handle_list()):
        for handle in _partners(family):
            if handle != person_handle:
                pairs.append((handle, family.get_handle()))
    return pairs


def _origin_family_handles(db, person_handle) -> list:
    """Return the child-of family handles of one person."""
    person = db.get_person_from_handle(person_handle)
    return list(person.get_parent_family_handle_list()) if person is not None else []


def _relatives(db, anchor) -> dict:
    """Map each relative key to the set of Person handles it covers."""
    me = anchor.get_handle()
    rel = {key: set() for key in _ALL_KEYS}

    siblings = set()
    for family in _families(db, anchor.get_parent_family_handle_list()):
        rel["parents"].update(_partners(family))
        siblings.update(h for h in _children(family) if h != me)
    rel["siblings"] = siblings

    spouses = set()
    kids = set()
    for family in _families(db, anchor.get_family_handle_list()):
        spouses.update(h for h in _partners(family) if h != me)
        kids.update(_children(family))
    rel["spouses"] = spouses
    rel["children"] = kids

    for spouse in spouses:
        for family in _families(db, _origin_family_handles(db, spouse)):
            rel["parents_in_law"].update(h for h in _partners(family) if h != me)
            rel["siblings_in_law"].update(
                h for h in _children(family) if h not in (me, spouse)
            )
    for sibling in siblings:  # spouses of siblings are siblings-in-law too
        rel["siblings_in_law"].update(s for s, _f in _spouses_of(db, sibling))
    for kid in kids:
        rel["children_in_law"].update(s for s, _f in _spouses_of(db, kid) if s != me)

    rel["associations"] = {ref.ref for ref in anchor.get_person_ref_list()}
    return rel


def _all_family_handles(db, person_handle) -> set:
    """Return every family of one person, as child or as partner."""
    person = db.get_person_from_handle(person_handle)
    if person is None:
        return set()
    return set(person.get_parent_family_handle_list()) | set(
        person.get_family_handle_list()
    )


def _family_steps(db, anchor) -> dict:
    """
    Map each Families-rule key to a set of Family handles.

    1 degree: the families of the anchor person, as child or as parent.
    2 degrees: the families of the other people in those families.
    3 degrees: the families of the siblings-in-law and children-in-law.
    The caller removes families that are already closer.
    """
    me = anchor.get_handle()
    origin = _families(db, anchor.get_parent_family_handle_list())
    own = _families(db, anchor.get_family_handle_list())
    parents = {h for f in origin for h in _partners(f)}
    siblings = {h for f in origin for h in _children(f) if h != me}
    spouses = {h for f in own for h in _partners(f) if h != me}
    children = {h for f in own for h in _children(f)}

    def families_of(people) -> set:
        result = set()
        for handle in people:
            result |= _all_family_handles(db, handle)
        return result

    spouse_origins = {h for s in spouses for h in _origin_family_handles(db, s)}
    spouse_own = {
        h for s in spouses for h in _all_family_handles(db, s) - spouse_origins
    }
    spouse_siblings = {
        h
        for f in _families(db, spouse_origins)
        for h in _children(f)
        if h not in spouses and h != me
    }
    sibling_spouses = {s for sib in siblings for s, _f in _spouses_of(db, sib)}
    child_spouses = {s for kid in children for s, _f in _spouses_of(db, kid) if s != me}

    return {
        "as_child": {f.get_handle() for f in origin},
        "as_parent": {f.get_handle() for f in own},
        "of_parents": families_of(parents),
        "of_siblings": families_of(siblings),
        "of_spouses": spouse_own,
        "of_parents_in_law": spouse_origins,
        "of_children": families_of(children),
        "of_siblings_in_law": families_of(spouse_siblings | sibling_spouses),
        "of_children_in_law": families_of(child_spouses),
    }


# ------------------------------------------------------------
#
# ImmediateFamilyPeople
#
# ------------------------------------------------------------
class ImmediateFamilyPeople(Rule):
    """People in the immediate families of an anchor."""

    labels = _PERSON_LABELS
    name = _("People in the immediate families of <anchor>")
    description = _(
        "Matches the members of the immediate families of a person or family: "
        "parents, siblings, spouses, children, in-laws and associations"
    )
    category = _("Family filters")
    allow_regex = False

    def prepare(self, db, user) -> None:
        """Build the set of matching Person handles once per filter run."""
        # "selected_handles" also lets the Gramps 6 filter optimizer skip
        # everyone else; older versions simply ignore it.
        self.selected_handles: set[PersonHandle] = set()
        inclusive, keys = _wanted(self.list)
        people, _families_ = _resolve_anchors(
            db, self.list[_P_ANCHOR_TYPE], self.list[_P_ANCHOR_VAL], user, self.name
        )
        anchors = {person.get_handle() for person in people}
        for person in people:
            rel = _relatives(db, person)
            for key in keys & _ALL_KEYS:
                self.selected_handles.update(rel[key])
        if inclusive:
            self.selected_handles.update(anchors)
        else:
            # With a Family anchor, one partner is the spouse of the other.
            self.selected_handles -= anchors

    def reset(self) -> None:
        """Drop the cached handles after the filter run."""
        self.selected_handles = set()

    def apply_to_one(self, db, person) -> bool:
        """Return True when the person is in the prepared set."""
        return person.get_handle() in self.selected_handles

    # Gramps 6.0 and newer call apply_to_one(); Gramps 5.2 calls apply().
    apply = apply_to_one


# ------------------------------------------------------------
#
# ImmediateFamilyFamilies
#
# ------------------------------------------------------------
class ImmediateFamilyFamilies(Rule):
    """Families of an anchor, and the families of the people in them."""

    labels = _FAMILY_LABELS
    name = _("Families in the immediate families of <anchor>")
    description = _(
        "Matches the families of a person or family, as child or as parent, "
        "and the families of the people in those families"
    )
    category = _("Family filters")
    allow_regex = False

    def prepare(self, db, user) -> None:
        """Build the set of matching Family handles once per filter run."""
        self.selected_handles: set[FamilyHandle] = set()
        inclusive, keys = _wanted(self.list)
        people, families = _resolve_anchors(
            db, self.list[_P_ANCHOR_TYPE], self.list[_P_ANCHOR_VAL], user, self.name
        )
        anchor_families = {family.get_handle() for family in families}
        # A family belongs to the closest degree at which any anchor person
        # reaches it (with a Family anchor, the family one partner grew up
        # in is 1 degree from that partner and 2 from the other).
        found = {1: set(), 2: set(), 3: set()}  # every family, by degree
        chosen = {1: set(), 2: set(), 3: set()}  # checked families, by degree
        for person in people:
            for key, handles in _family_steps(db, person).items():
                degree = _FAMILY_DEGREE_OF[key]
                found[degree] |= handles
                if key in keys:
                    chosen[degree] |= handles
        self.selected_handles |= chosen[1]
        self.selected_handles |= chosen[2] - found[1]
        self.selected_handles |= chosen[3] - found[1] - found[2]
        if inclusive:
            self.selected_handles.update(anchor_families)
        else:
            self.selected_handles -= anchor_families

    def reset(self) -> None:
        """Drop the cached handles after the filter run."""
        self.selected_handles = set()

    def apply_to_one(self, db, family) -> bool:
        """Return True when the family is in the prepared set."""
        return family.get_handle() in self.selected_handles

    # Gramps 6.0 and newer call apply_to_one(); Gramps 5.2 calls apply().
    apply = apply_to_one
