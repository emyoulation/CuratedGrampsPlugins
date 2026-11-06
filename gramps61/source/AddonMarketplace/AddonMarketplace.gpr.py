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
Addon Marketplace: replaces the window behind Edit > Addon Manager.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        GENERAL,
        id="AddonMarketplace",
        name=_("Addon Marketplace"),
        description=_(
            "Replaces the Addon Manager with the Addon Marketplace: clickable "
            "filter lozenges, Update and Downgrade buttons, and a project dialog "
            "that tests web and local addon repositories. "
            "To switch it off, hide this plugin and restart Gramps."
        ),
        version="0.1.2",  # build 20261106.1640
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="AddonMarketplace.py",
        load_on_reg=True,
        authors=["Claude AI", "Brian McCullough"],
        authors_email=["", ""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
            "gramps61/source/AddonMarketplace"
        ),
    )
