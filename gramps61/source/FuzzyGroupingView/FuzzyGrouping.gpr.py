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

# Registration forked from the core "personview" (Grouped People) entry in
# gramps/plugins/view/view.gpr.py at commit
# 5cebb2c55fdbb0a92428625d409918216409db70 (maintenance/gramps61).
# Differences: new id/name/class/file, no order=START (does not take over
# as the default People view), addon status/version/maintainer fields.

from gramps.version import major_version, VERSION_TUPLE

if (5, 2) <= VERSION_TUPLE[:2] < (6, 2):
    register(
        VIEW,
        id="fuzzygroupingview",
        name=_("Fuzzy Grouping"),
        description=_(
            "The view showing all people in the Family Tree grouped by"
            " phonetically similar family names"
        ),
        version="0.1.1",  # build 20261027.1431
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="fuzzygroupingview.py",
        authors=["The Gramps project", "Brian McCullough"],
        authors_email=["https://gramps-project.org", ""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        category=("People", _("People")),
        viewclass="FuzzyGroupingView",
        stock_icon="fuzzy-grouping",  # media/fuzzy-grouping.svg, see view module
        help_url="Addon:Fuzzy_Grouping",  # wiki page not written yet
    )
