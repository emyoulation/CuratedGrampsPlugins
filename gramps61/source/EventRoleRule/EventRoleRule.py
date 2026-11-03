#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
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
Event filter rule: events in which a person or family takes part in a
selected role (Primary, Witness, Godparent, a custom role, ...).
"""

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule
from gramps.gen.lib import EventRoleType

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

# Stored in the filter XML, so these keys must never be translated.
PARTICIPANT_KEYS = ["any", "person", "family"]
PARTICIPANT_LABELS = [_("Person or family"), _("Person"), _("Family")]


def _role_widget(db):
    """Role selector: standard roles plus this tree's custom roles."""
    # Imported here so the rule still loads without a GUI (CLI filters).
    from gramps.gui.editors.filtereditor import MySelect

    return MySelect(EventRoleType, db.get_event_roles())


def _participant_widget(db):
    """Participant selector: person, family, or either."""
    from gramps.gui.editors.filtereditor import MyList

    return MyList(PARTICIPANT_KEYS, PARTICIPANT_LABELS)


class EventRoleRule(Rule):
    """Match events where a participant has the selected role."""

    labels = [
        (_("Role:"), _role_widget),
        (_("Participant:"), _participant_widget),
    ]
    name = _("Events with participants in the <role>")
    description = _(
        "Matches events in which a person or family takes part "
        "in the selected role."
    )
    category = _("General filters")

    def __init__(self, arg, use_regex=False, use_case=False):
        super().__init__(arg, use_regex, use_case)
        self.matches = set()

    def prepare(self, db, user):
        """Collect the matching event handles once, from the event refs."""
        self.matches = set()
        role_key = self.list[0]
        if not role_key:
            return
        participant = self.list[1] or "any"
        if participant in ("any", "person"):
            for person in db.iter_people():
                self._collect(person, role_key)
        if participant in ("any", "family"):
            for family in db.iter_families():
                self._collect(family, role_key)

    def _collect(self, obj, role_key):
        """Add events that obj takes part in with the selected role."""
        for event_ref in obj.get_event_ref_list():
            if event_ref.get_role().xml_str() == role_key:
                self.matches.add(event_ref.ref)

    def reset(self):
        """Release the collected handles."""
        self.matches = set()

    def apply_to_one(self, db, event):
        """Return True if the event has a participant in the role."""
        return event.handle in self.matches

    # Gramps 5.2 calls apply(); 6.0 and newer call apply_to_one().
    apply = apply_to_one

    def display_values(self):
        """Show translated values in the filter editor rule list."""
        role = EventRoleType()
        role.set_from_xml_str(self.list[0])
        participant = dict(zip(PARTICIPANT_KEYS, PARTICIPANT_LABELS)).get(
            self.list[1], self.list[1]
        )
        return '%s="%s";%s="%s"' % (
            _("Role:"),
            str(role),
            _("Participant:"),
            participant,
        )
