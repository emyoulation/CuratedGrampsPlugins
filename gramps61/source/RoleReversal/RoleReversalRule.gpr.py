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
Role Reversal Rule: custom filter rules to "Reverse lookup", finding
people (Primary role) and families (Family role) with shared events
where others hold a specified Role.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    for _ns, _cls, _name in (
        ("Person", "RoleReversalPerson", _("Person Role Reversal")),
        ("Family", "RoleReversalFamily", _("Family Role Reversal")),
    ):
        register(
            RULE,
            id=_cls,
            name=_name,
            description=_(
                "Filter rule: reverse lookup of shared events where others "
                "hold a specified role."
            ),
            version="1.0.0",  # build 20261029.1554
            gramps_target_version=major_version,
            status=STABLE,
            fname="RoleReversalRule.py",
            ruleclass=_cls,  # must be the rule class name
            namespace=_ns,  # one of the primary object classes
            authors=["Claude", "Brian McCullough"],
            authors_email=["", ""],
            maintainers=["Brian McCullough"],
            maintainers_email=[""],
            help_url=(
                "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
                "gramps61/source/RoleReversalRule"
            ),
        )
