#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2008       Gary Burton
# Copyright (C) 2009       Nick Hall
# Copyright (C) 2010       Benny Malengier
# Copyright (C) 2026       Claude AI (wish coding by Brian McCullough)
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
Registration of the Fuzzy Grouping person view.

Forked from the core "personview" (Grouped People) entry in
gramps/plugins/view/view.gpr.py at commit
5cebb2c55fdbb0a92428625d409918216409db70 (maintenance/gramps61).
Differences: new id/name/class/file, no order=START (does not take over
as the default People view), addon status/version/maintainer fields.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2) <= VERSION_TUPLE[:2] < (6, 2):
    register(
        VIEW,
        id="fuzzygroupingview",
        name=_("Fuzzy Grouping"),
        description=_(
            "The view showing all people in the Family Tree grouped by "
            "phonetically similar family names"
        ),
        version="0.2.0",  # build 20261029.0510
        gramps_target_version=major_version,
        status=STABLE,
        fname="fuzzygroupingview.py",
        authors=["Claude", "Brian McCullough"],
        maintainers=["Brian McCullough"],
        category=("People", _("People")),
        viewclass="FuzzyGroupingView",
        stock_icon="fuzzy-grouping",  # media/fuzzy-grouping.svg, see view module
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main"
            "/gramps61/source/FuzzyGroupingView"
        ),
    )
