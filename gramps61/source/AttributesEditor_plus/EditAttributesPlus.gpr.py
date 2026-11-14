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

"""
Registration for the Edit Attributes Plus monkey-patch addon.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2) <= VERSION_TUPLE[:2] < (6, 2):
    register(
        GENERAL,
        id="EditAttributesPlus",
        name=_("Edit Attributes Plus"),
        description=_(
            "Resizable Attribute Editor with a multi-line Value field, "
            "plus multi-column type popups and 'Add a gramplet' menus "
            "(sidebar, bottombar and Dashboard monkey patch)."
        ),
        version="0.1.0",  # build 20261113.2327
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="EditAttributesPlus.py",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        load_on_reg=True,
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/EditAttributesPlus/README.md",
    )
