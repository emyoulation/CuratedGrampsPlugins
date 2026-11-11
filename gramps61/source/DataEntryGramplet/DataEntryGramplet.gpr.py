#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2007-2009  Douglas S. Blank <doug.blank@gmail.com>
# Copyright (C) 2011       Gary Burton
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

from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Register the Data Entry gramplet for the People category views
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        # Identity
        id="Data Entry Gramplet",
        name=_("Data Entry Gramplet"),
        description=_(
            "Key in a relative of the active person, with their birth, death "
            "and other events and sources, on one form instead of working "
            "through a dozen editing dialogs"
        ),
        version="1.1.1",  # build 20261111.2017
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        audience=EXPERT,
        authors=["Douglas S. Blank", "Gary Burton"],
        maintainers=["Brian McCullough"],
        # Code
        fname="DataEntryGramplet.py",
        gramplet="DataEntryGramplet",
        # Placement and size
        navtypes=["Person"],
        gramplet_title=_("Data Entry"),
        height=375,
        expand=False,
        detached_width=510,
        detached_height=480,
        # Documentation
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
            "gramps61/source/DataEntryGramplet/CHANGELOG.md"
        ),
    )
