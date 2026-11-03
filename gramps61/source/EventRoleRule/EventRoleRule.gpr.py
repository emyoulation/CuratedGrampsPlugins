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

"""Registration for the Event Role Rule (Event filter rule)."""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        RULE,
        id="EventRoleRule",
        name=_("Events with participants in the <role>"),
        description=_(
            "Matches events in which a person or family takes part "
            "in the selected role."
        ),
        version="0.0.0",  # build 20261102.2028
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="EventRoleRule.py",
        ruleclass="EventRoleRule",
        namespace="Event",
        authors=["Brian McCullough"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/"
            "tree/main/gramps61/source/EventRoleRule"
        ),
    )
