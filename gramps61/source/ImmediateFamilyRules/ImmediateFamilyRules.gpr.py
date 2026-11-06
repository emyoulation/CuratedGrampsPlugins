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

from gramps.version import major_version, VERSION_TUPLE

_HELP_URL = (
    "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
    "gramps61/source/ImmediateFamilyRules"
)

if VERSION_TUPLE >= (5, 2, 0):
    register(
        RULE,
        id="ImmediateFamilyRules_ImmediateFamilyPeople",
        name=_("People in the immediate families of <anchor>"),
        description=_(
            "Matches the members of the immediate families of a person or "
            "family: parents, siblings, spouses, children, in-laws and "
            "associations"
        ),
        version="0.1.1",  # build 20261106.0439
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="ImmediateFamilyRules.py",
        ruleclass="ImmediateFamilyPeople",
        namespace="Person",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        help_url=_HELP_URL,
    )

    register(
        RULE,
        id="ImmediateFamilyRules_ImmediateFamilyFamilies",
        name=_("Families in the immediate families of <anchor>"),
        description=_(
            "Matches the families of a person or family, as child or as "
            "parent, and the families of the people in those families"
        ),
        version="0.1.1",  # build 20261106.0439
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="ImmediateFamilyRules.py",
        ruleclass="ImmediateFamilyFamilies",
        namespace="Family",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        help_url=_HELP_URL,
    )
