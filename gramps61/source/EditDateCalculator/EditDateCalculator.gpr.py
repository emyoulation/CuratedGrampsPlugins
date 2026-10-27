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
Edit Date Calculator: adds a slide-out Date Calculator to the Edit Date dialog.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        GENERAL,
        id="editdatecalculator",
        name=_("Edit Date Calculator"),
        description=_(
            "Adds a slide-out Date Calculator panel to the Edit Date dialog. "
            "Open it with the triangle tab on the right edge of the dialog. "
            "To switch it off, hide this plugin and restart Gramps."
        ),
        version="0.0.2",  # build 20261026.1854
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="editdatecalculator.py",
        load_on_reg=True,
        authors=["Claude","Brian McCullough"],
        authors_email=["",""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        help_url="https://gramps.discourse.group/t/10127/8",
    )
