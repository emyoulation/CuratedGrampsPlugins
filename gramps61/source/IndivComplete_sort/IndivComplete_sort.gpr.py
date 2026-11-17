#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2009      Benny Malengier
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

"""Registration of the Complete Individual Report (Sorted) addon."""

from gramps.version import major_version, VERSION_TUPLE

if VERSION_TUPLE >= (5, 2, 0):
    register(
        REPORT,
        id="IndivComplete_sort",
        name=_("Complete Individual Report (Sorted)"),
        description=_(
            "Produces a complete report on the selected people, "
            "sorted by surname, given name and birth date"
        ),
        version="1.1.0",  # build 20261117.1845
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="IndivComplete_sort.py",
        authors=["Donald N. Allingham", "Brian McCullough"],
        authors_email=["don@gramps-project.org", ""],
        maintainers=["Brian McCullough"],
        category=CATEGORY_TEXT,
        reportclass="IndivCompleteSortReport",
        optionclass="IndivCompleteSortOptions",
        report_modes=[REPORT_MODE_GUI, REPORT_MODE_BKI, REPORT_MODE_CLI],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
            "gramps61/source/IndivComplete_sort"
        ),
    )
