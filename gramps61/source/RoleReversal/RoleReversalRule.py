#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
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
Role Reversal rules: a "Reverse lookup" of shared events.
  People   - Primary role in a shared event where others hold the role
  Families - Family role in a shared event where others hold the role
The role selector sets the role of the OTHER participants (for example
Godparent).  Empty = any role.

The role is stored as the Gramps XML string of the role ("Witness", or the
text of a custom role), so saved filters do not depend on the language.
"""

import logging

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule
from gramps.gen.lib import EventRoleType

try:
    _ = glocale.get_addon_translator(__file__).sgettext
except ValueError:
    _ = glocale.translation.sgettext

LOG = logging.getLogger(".RoleReversalRule")

ROLE_LABEL = _("Shared with role:")


# -------------------------------------------------------------------------
#
# RoleSelector - text combo box of event roles (GUI only)
#
# Like the type selectors of the filter editor (MySelect), but for event
# roles, which the filter editor has no selector for.  Standard roles plus
# the custom roles used in the tree; any text can be typed.
#
# -------------------------------------------------------------------------
try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    from gramps.gui.autocomp import StandardCustomSelector

    class RoleSelector(Gtk.ComboBox):
        """Editable combo box of event roles; empty means any role."""

        def __init__(self, db=None):
            Gtk.ComboBox.__init__(self, has_entry=True)
            custom_roles = []
            if db is not None:
                try:
                    custom_roles = db.get_event_roles()
                except AttributeError:
                    pass
            self.sel = StandardCustomSelector(
                EventRoleType._I2SMAP,
                self,
                EventRoleType._CUSTOM,
                EventRoleType._DEFAULT,
                custom_roles,
            )
            self.get_child().set_placeholder_text(_("any role"))
            self.set_tooltip_text(
                _(
                    "The role of the other person or family in the shared "
                    "event. Leave empty to match any role."
                )
            )
            self.set_text("")
            self.show()

        def get_text(self):
            """Return the role to save: its XML string, or '' for any."""
            value, text = self.sel.get_values()
            if value == EventRoleType._CUSTOM and not text.strip():
                return ""
            return EventRoleType((value, text)).xml_str()

        def set_text(self, val):
            """Show a saved role ('' shows the empty entry)."""
            if not val:
                self.sel.set_values((EventRoleType._CUSTOM, ""))
                return
            role = EventRoleType()
            role.set_from_xml_str(val)
            self.sel.set_values((int(role), str(role)))

    RULE_LABELS = [(ROLE_LABEL, RoleSelector)]

except (ImportError, ValueError):
    RULE_LABELS = [ROLE_LABEL]


# -------------------------------------------------------------------------
#
# RoleReversalBase - the shared rule logic
#
# -------------------------------------------------------------------------
class RoleReversalBase(Rule):
    """Match objects whose own-role events are shared with someone else."""

    labels = RULE_LABELS
    category = _("Event filters")
    own_class = ""  # "Person" or "Family"

    def __init__(self, arg, use_regex=False, use_case=False):
        super().__init__(arg, use_regex, use_case)
        self.role = None
        self.cache = {}

    def prepare(self, db, user):
        """Read the role once per filter run."""
        self.role = None
        if self.list and self.list[0]:
            self.role = EventRoleType()
            self.role.set_from_xml_str(self.list[0])
        self.cache = {}

    def reset(self):
        """Free the cache after the filter run."""
        self.cache = {}

    def is_own_role(self, role):
        """True for the role this object must have in the event."""
        raise NotImplementedError

    def participants(self, db, event_handle):
        """
        Return [(class_name, handle, role), ...] for every person and
        family that references the event.  Cached per filter run.
        """
        if event_handle in self.cache:
            return self.cache[event_handle]
        found = []
        for class_name, handle in db.find_backlink_handles(
            event_handle, ["Person", "Family"]
        ):
            if class_name == "Person":
                obj = db.get_person_from_handle(handle)
            else:
                obj = db.get_family_from_handle(handle)
            if obj is None:
                continue
            for ref in obj.get_event_ref_list():
                if ref.ref == event_handle:
                    found.append((class_name, handle, ref.get_role()))
        self.cache[event_handle] = found
        return found

    def is_shared(self, db, event_handle, own_handle):
        """True when someone else references the event with the role."""
        for class_name, handle, role in self.participants(db, event_handle):
            if class_name == self.own_class and handle == own_handle:
                continue  # this object itself
            if self.role is None or role == self.role:
                return True
        return False

    def apply_to_one(self, db, obj):
        """Return True on a match."""
        for ref in obj.get_event_ref_list():
            if self.is_own_role(ref.get_role()) and self.is_shared(
                db, ref.ref, obj.get_handle()
            ):
                return True
        return False

    apply = apply_to_one  # Gramps 5.2 calls apply()


# -------------------------------------------------------------------------
#
# RoleReversalPerson
#
# -------------------------------------------------------------------------
class RoleReversalPerson(RoleReversalBase):
    """People who are Primary in an event that is shared."""

    name = _("Role Reversal")
    description = _(
        "Reverse lookup: matches people with the Primary role in shared "
        "events where others hold the specified role (for example, people "
        "with a Godparent at their baptism). Empty role: any role"
    )
    own_class = "Person"

    def is_own_role(self, role):
        return role.is_primary()


# -------------------------------------------------------------------------
#
# RoleReversalFamily
#
# -------------------------------------------------------------------------
class RoleReversalFamily(RoleReversalBase):
    """Families with the Family role in an event that is shared."""

    name = _("Role Reversal")
    description = _(
        "Reverse lookup: matches families with the Family role in shared "
        "events where others hold the specified role (for example, families "
        "with a Witness at their marriage). Empty role: any role"
    )
    own_class = "Family"

    def is_own_role(self, role):
        return role.is_family()
