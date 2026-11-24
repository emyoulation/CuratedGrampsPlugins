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
Registration for the Auto Active and Home Person monkey-patch addon.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2) <= VERSION_TUPLE < (6, 2):
    register(
        GENERAL,
        id="AutoActiveHome",
        name=_("Auto Active and Home Person"),
        description=_(
            "Monkey patch for new Family Trees: when the first people are "
            "added or imported, makes the last created Person the Active "
            "Person and the first created Person the Home Person, if they "
            "are not set yet."
        ),
        version="0.1.0",  # build 20261122.2215
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="AutoActiveHome.py",
        load_on_reg=True,
        authors=["Claude AI"],
        maintainers=["Brian McCullough"],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
            "gramps61/source/AutoActiveHome"
        ),
    )
