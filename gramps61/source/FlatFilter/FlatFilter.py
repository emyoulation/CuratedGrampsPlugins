#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2024  Paul Womack (BugBear)
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
# Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, 2025)
# Prompts used:
#   1. "Create a .gpr.py for FlatFilter.py gramplet code (for all categories)
#       following Gramps developer guidelines"
#   2. "Running a filtering under 5.2 fails. Adapting the .gpr.py to 6.0 gives
#       AttributeError: 'HasNamedFather' object has no attribute 'apply_to_one'"
# Constraints:
#   https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
#   https://github.com/gramps-project/gramps/blob/master/AGENTS.md
#
# Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
#
# Changelog:
#   1.0.0  Initial release (Paul Womack / BugBear)
#   1.1.0  Port to Gramps 6.0 API:
#          - Rule.apply(db, person) renamed to Rule.apply_to_one(db, person)
#          - Rule.requestprepare(db, user) replaced by Rule.prepare(db, user)
#          - Rule.requestreset() replaced by Rule.reset()
#          - gramps_target_version bumped to "6.0" in FlatFilter.gpr.py
#

# ------------------------
# Python modules
# ------------------------
import logging

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gtk
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import displayer
from gramps.gen.filters import GenericFilter
from gramps.gen.filters.rules import Rule
from gramps.gen.filters.rules.person import RegExpName, ProbablyAlive
from gramps.gen.lib import Date
from gramps.gen.lib.person import Person
from gramps.gen.plug import Gramplet
from gramps.gui import widgets
from gramps.gui.filters import build_filter_model
from gramps.gui.filters.sidebar import SidebarFilter

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)


# ------------------------------------------------------------
#
# _RegExpNameList
#
# ------------------------------------------------------------
class _RegExpNameList(Rule):
    """Rule that checks for full or partial name matches."""

    labels = [_("Text:")]
    name = _("People with a name matching <text>")
    description = _(
        "Matches people's names containing a substring or "
        "matching a regular expression"
    )
    category = _("General filters")
    allow_regex = True

    def field_list(self, name: object) -> list[str]:
        """
        Return the list of name fields to test for this rule.

        :param name: A Gramps Name object.
        :returns: List of string fields to test against the search value.
        """
        raise NotImplementedError

    def apply_to_one(self, db: object, person: object) -> bool:
        """
        Apply the rule to a single Person object.

        :param db: The Gramps database.
        :param person: The Person object to test.
        :returns: True if the person matches, False otherwise.
        """
        for name in [person.get_primary_name()] + person.get_alternate_names():
            for field in self.field_list(name):
                if self.match_substring(0, field):
                    return True
        return False


# ------------------------------------------------------------
#
# RegExpPersonal
#
# ------------------------------------------------------------
class RegExpPersonal(_RegExpNameList):
    """Matches given name, title, or nickname against a pattern."""

    def field_list(self, name: object) -> list[str]:
        """
        Return given-name fields for this name object.

        :param name: A Gramps Name object.
        :returns: List of personal name string fields.
        """
        return [name.first_name, name.title, name.nick]


# ------------------------------------------------------------
#
# RegExpFamily
#
# ------------------------------------------------------------
class RegExpFamily(_RegExpNameList):
    """Matches surname, suffix, title, family nickname, or call name."""

    def field_list(self, name: object) -> list[str]:
        """
        Return family-name fields for this name object.

        :param name: A Gramps Name object.
        :returns: List of family name string fields.
        """
        return [name.get_surname(), name.suffix, name.title, name.famnick, name.call]


# ------------------------------------------------------------
#
# _HasNamedRelation
#
# ------------------------------------------------------------
class _HasNamedRelation(Rule):
    """
    Base rule that matches a person based on a named relative.

    Subclasses define which relatives to inspect via get_rel_list().
    The name_matcher constructor argument selects the name-matching
    rule class (RegExpPersonal or RegExpFamily).
    """

    labels = [_("Filter name:")]
    name = _("Children of name match")
    category = _("Family filters")
    description = _("Matches children of anybody with a given name")

    def __init__(self, arg: list, name_matcher: type, use_regex: bool = False) -> None:
        """
        Initialise the relation rule.

        :param arg: Rule argument list (search text at index 0).
        :param name_matcher: Class of name-matching rule to apply to relatives.
        :param use_regex: Whether to treat the search text as a regex.
        """
        super().__init__(arg, use_regex)
        self.name_matcher = name_matcher(arg, use_regex)

    def prepare(self, db: object, user: object) -> None:
        """
        Prepare the rule and the nested name matcher for use.

        :param db: The Gramps database.
        :param user: The User object for progress reporting.
        """
        self.name_matcher.prepare(db, user)

    def reset(self) -> None:
        """Reset the rule and the nested name matcher after use."""
        self.name_matcher.reset()

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return a list of handles for the relatives to test.

        :param db: The Gramps database.
        :param person: The Person whose relatives are returned.
        :returns: List of person handles.
        """
        raise NotImplementedError

    def get_spouse_list(self, db: object, person: object) -> list:
        """
        Return handles of all spouses of the given person.

        :param db: The Gramps database.
        :param person: The Person whose spouses are returned.
        :returns: List of spouse person handles.
        """
        result = []
        for fam_id in person.get_family_handle_list():
            fam = db.get_family_from_handle(fam_id)
            if fam:
                for spouse_id in [
                    fam.get_father_handle(),
                    fam.get_mother_handle(),
                ]:
                    if not spouse_id:
                        continue
                    if spouse_id == person.handle:
                        continue
                    result.append(spouse_id)
        return result

    def apply_to_one(self, db: object, person: object) -> bool:
        """
        Apply the rule to a single Person object.

        :param db: The Gramps database.
        :param person: The Person object to test.
        :returns: True if any relative matches the name rule.
        """
        for rel_id in self.get_rel_list(db, person):
            if rel_id:
                rel = db.get_person_from_handle(rel_id)
                if rel and self.name_matcher.apply_to_one(db, rel):
                    return True
        return False


# ------------------------------------------------------------
#
# _HasNamedParent
#
# ------------------------------------------------------------
class _HasNamedParent(_HasNamedRelation):
    """Base rule for matching by a named parent."""

    def get_parent_familys(self, db: object, person: object) -> list:
        """
        Return all parent Family objects for the given person.

        :param db: The Gramps database.
        :param person: The Person whose parent families are returned.
        :returns: List of Family objects.
        """
        result = []
        for fam_id in person.get_parent_family_handle_list():
            fam = db.get_family_from_handle(fam_id)
            if fam:
                result.append(fam)
        return result


# ------------------------------------------------------------
#
# HasNamedFather
#
# ------------------------------------------------------------
class HasNamedFather(_HasNamedParent):
    """Rule that matches if the person's father's name matches."""

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return the father handle from each parent family.

        :param db: The Gramps database.
        :param person: The Person to inspect.
        :returns: List of father handles (may contain None values).
        """
        return [fam.get_father_handle() for fam in self.get_parent_familys(db, person)]


# ------------------------------------------------------------
#
# HasNamedMother
#
# ------------------------------------------------------------
class HasNamedMother(_HasNamedParent):
    """Rule that matches if the person's mother's name matches."""

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return the mother handle from each parent family.

        :param db: The Gramps database.
        :param person: The Person to inspect.
        :returns: List of mother handles (may contain None values).
        """
        return [fam.get_mother_handle() for fam in self.get_parent_familys(db, person)]


# ------------------------------------------------------------
#
# IsSiblingofNamedSibling
#
# ------------------------------------------------------------
class IsSiblingofNamedSibling(_HasNamedRelation):
    """Rule that matches if any sibling (via main parent family) name matches."""

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return handles of all siblings in the main parent family.

        :param db: The Gramps database.
        :param person: The Person whose siblings are returned.
        :returns: List of sibling person handles.
        """
        result = []
        fam_id = person.get_main_parents_family_handle()
        if fam_id:
            fam = db.get_family_from_handle(fam_id)
            if fam:
                for child_ref in fam.get_child_ref_list():
                    if child_ref and child_ref.ref != person.handle:
                        result.append(child_ref.ref)
        return result


# ------------------------------------------------------------
#
# HasNamedChild
#
# ------------------------------------------------------------
class HasNamedChild(_HasNamedRelation):
    """Rule that matches if any child's name matches."""

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return handles of all children across all families.

        :param db: The Gramps database.
        :param person: The Person whose children are returned.
        :returns: List of child person handles.
        """
        result = []
        for fam_id in person.get_family_handle_list():
            fam = db.get_family_from_handle(fam_id)
            if fam:
                for child_ref in fam.get_child_ref_list():
                    if child_ref:
                        result.append(child_ref.ref)
        return result


# ------------------------------------------------------------
#
# HasNamedSpouse
#
# ------------------------------------------------------------
class HasNamedSpouse(_HasNamedRelation):
    """Rule that matches if any spouse's name matches."""

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return handles of all spouses.

        :param db: The Gramps database.
        :param person: The Person whose spouses are returned.
        :returns: List of spouse person handles.
        """
        return self.get_spouse_list(db, person)


# ------------------------------------------------------------
#
# HasName
#
# ------------------------------------------------------------
class HasName(_HasNamedRelation):
    """
    Rule that matches on the person's own name.

    For female persons matched against a RegExpFamily rule, the
    surnames of all spouses are also searched (reflecting the common
    genealogical practice of recording married surnames).
    """

    def get_rel_list(self, db: object, person: object) -> list:
        """
        Return handle(s) to test for name matching.

        For female persons with a family-name matcher, also include
        spouse handles so married surnames are searched.

        :param db: The Gramps database.
        :param person: The Person to inspect.
        :returns: List of person handles to test.
        """
        if person.gender == Person.FEMALE and isinstance(
            self.name_matcher, RegExpFamily
        ):
            result = self.get_spouse_list(db, person)
            result.append(person.handle)
            return result
        return [person.handle]


# ------------------------------------------------------------
#
# SearchableNamePair
#
# ------------------------------------------------------------
class SearchableNamePair:
    """
    A pair of entry widgets for given-name and family-name searching.

    Places two BasicEntry boxes side-by-side in the sidebar grid,
    one for personal (given) names and one for family (surname) names.
    """

    def __init__(self, label: str, rule_class: type) -> None:
        """
        Initialise the name pair.

        :param label: Row label text shown in the sidebar.
        :param rule_class: The _HasNamedRelation subclass to instantiate.
        """
        self.widget_personal = widgets.BasicEntry()
        self.widget_family = widgets.BasicEntry()
        self.label = label
        self.rule_class = rule_class

    def place(self, sidebar: object) -> None:
        """
        Attach this name pair's widgets to the sidebar grid.

        :param sidebar: The SidebarFilter instance that owns the grid.
        """
        sidebar.grid.attach(widgets.BasicLabel(self.label), 1, sidebar.position, 1, 1)
        self.widget_personal.set_hexpand(True)
        self.widget_personal.set_placeholder_text(_("given"))
        sidebar.grid.attach(self.widget_personal, 2, sidebar.position, 1, 1)
        self.widget_personal.connect("key-press-event", sidebar.key_press)

        self.widget_family.set_hexpand(True)
        self.widget_family.set_placeholder_text(_("surname"))
        sidebar.grid.attach(self.widget_family, 3, sidebar.position, 1, 1)
        self.widget_family.connect("key-press-event", sidebar.key_press)
        sidebar.position += 1

    def clear(self) -> None:
        """Clear both entry widgets."""
        self.widget_personal.set_text("")
        self.widget_family.set_text("")

    def _add_to_filter(
        self,
        generic_filter: object,
        regex: bool,
        widget: object,
        search_class: type,
    ) -> None:
        """
        Add a rule to the filter if the widget has non-empty text.

        :param generic_filter: The GenericFilter being built.
        :param regex: Whether to enable regex matching.
        :param widget: The entry widget whose text to read.
        :param search_class: RegExpPersonal or RegExpFamily.
        """
        v = str(widget.get_text().strip())
        if v:
            rule = self.rule_class([v], search_class, use_regex=regex)
            generic_filter.add_rule(rule)

    def add_to_filter(self, generic_filter: object, regex: bool) -> None:
        """
        Add personal-name and family-name rules to the filter.

        :param generic_filter: The GenericFilter being built.
        :param regex: Whether to enable regex matching.
        """
        self._add_to_filter(generic_filter, regex, self.widget_personal, RegExpPersonal)
        self._add_to_filter(generic_filter, regex, self.widget_family, RegExpFamily)


# ------------------------------------------------------------
#
# PersonSidebarFilter2
#
# ------------------------------------------------------------
class PersonSidebarFilter2(SidebarFilter):
    """Extended person filter sidebar with relationship-aware name rows."""

    def __init__(self, dbstate: object, uistate: object, clicked: object) -> None:
        """
        Initialise the filter sidebar.

        :param dbstate: The Gramps database state.
        :param uistate: The Gramps UI state.
        :param clicked: Callback invoked when the filter is applied.
        """
        self.clicked_func = clicked

        self.names = [
            SearchableNamePair(_("Father"), HasNamedFather),
            SearchableNamePair(_("Mother"), HasNamedMother),
            SearchableNamePair(_("Name"), HasName),
            SearchableNamePair(_("Spouse"), HasNamedSpouse),
            SearchableNamePair(_("Sibling"), IsSiblingofNamedSibling),
            SearchableNamePair(_("2nd Sibling"), IsSiblingofNamedSibling),
            SearchableNamePair(_("Child"), HasNamedChild),
            SearchableNamePair(_("2nd Child"), HasNamedChild),
        ]
        self.filter_alive = widgets.DateEntry(uistate, [])
        self.filter_regex = Gtk.CheckButton(label=_("Use regular expressions"))

        SidebarFilter.__init__(self, dbstate, uistate, "Person")

    def create_widget(self) -> None:
        """Build and lay out all filter widgets inside the sidebar grid."""
        exdate1 = Date()
        exdate2 = Date()
        exdate1.set(
            Date.QUAL_NONE,
            Date.MOD_RANGE,
            Date.CAL_GREGORIAN,
            (0, 0, 1800, False, 0, 0, 1900, False),
        )
        exdate2.set(
            Date.QUAL_NONE,
            Date.MOD_BEFORE,
            Date.CAL_GREGORIAN,
            (0, 0, 1850, False),
        )

        msg1 = displayer.display(exdate1)
        msg2 = displayer.display(exdate2)

        for w in self.names:
            w.place(self)

        self.add_text_entry(
            _("Probably Alive"),
            self.filter_alive,
            _('example: "%(msg1)s" or "%(msg2)s"') % {"msg1": msg1, "msg2": msg2},
        )
        self.add_regex_entry(self.filter_regex)

    def clear(self, obj: object) -> None:
        """
        Clear all filter entry widgets.

        :param obj: GTK widget that triggered the clear (unused).
        """
        for w in self.names:
            w.clear()
        self.filter_alive.set_text("")

    def get_filter(self) -> GenericFilter:
        """
        Build and return a GenericFilter from the current widget values.

        :returns: A GenericFilter combining all active rule entries with AND.
        """
        regex = self.filter_regex.get_active()
        generic_filter = GenericFilter()

        for w in self.names:
            w.add_to_filter(generic_filter, regex)

        alive = str(self.filter_alive.get_text().strip())
        if alive:
            rule = ProbablyAlive([alive])
            generic_filter.add_rule(rule)

        return generic_filter


# ------------------------------------------------------------
#
# Filter2
#
# ------------------------------------------------------------
class Filter2(Gramplet):
    """Base class for filter gramplets that embed a SidebarFilter."""

    FILTER_CLASS = None

    def init(self) -> None:
        """Initialise the gramplet, replacing the default textview with the filter widget."""
        self.filter = self.FILTER_CLASS(
            self.dbstate, self.uistate, self.__filter_clicked
        )
        self.widget = self.filter.get_widget()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.widget)
        self.widget.show_all()

    def __filter_clicked(self) -> None:
        """
        Apply the current filter to the active view.

        Called when the user presses Enter or clicks Apply in the sidebar.
        """
        self.gui.view.generic_filter = self.filter.get_filter()
        self.gui.view.build_tree()


# ------------------------------------------------------------
#
# FlatFilter
#
# ------------------------------------------------------------
class FlatFilter(Filter2):
    """
    Gramplet providing an extended Person Filter sidebar.

    Adds separate given-name and family-name entry boxes for:
    father, mother, the person themselves, spouse, sibling, and child,
    plus a Probably-Alive date range field and regex toggle.
    """

    FILTER_CLASS = PersonSidebarFilter2
