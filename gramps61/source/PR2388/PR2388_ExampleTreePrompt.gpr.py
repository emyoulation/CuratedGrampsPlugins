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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""
Registration for the Example Tree Prompt monkey-patch addon
(field-test port of Gramps PR 2388).
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2) <= VERSION_TUPLE < (6, 2):
    register(
        GENERAL,
        id="PR2388_ExampleTreePrompt",
        name=_("PR2388 Example Tree Prompt"),
        description=_(
            "On startup, offers to import a practice Family Tree from the "
            "sample data included with Gramps. Afterwards it shows the "
            "Dashboard with a To Do note to get started. Field-test port of "
            "Gramps PR 2388."
        ),
        version="0.1.0",  # build 20261109.1950
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="PR2388_ExampleTreePrompt.py",
        load_on_reg=True,
        authors=["Claude AI", "Doug Blank (PR 2388)"],
        maintainers=["Brian McCullough"],
        help_url="https://github.com/gramps-project/gramps/pull/2388",
    )
