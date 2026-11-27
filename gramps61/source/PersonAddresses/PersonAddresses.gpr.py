#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Brian McCullough
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

if VERSION_TUPLE >= (5, 2, 0):
    register(
        GRAMPLET,
        id="PersonAddresses",
        name=_("Person Addresses"),
        description=_("Gramplet showing a sortable table of the Addresses of the active Person"),
        version="0.1.0",  # build 20261127.2306
        gramps_target_version=major_version,
        status=STABLE,
        fname="PersonAddresses.py",
        height=200,
        gramplet="PersonAddresses",
        gramplet_title=_("Addresses"),
        navtypes=["Person"],
        authors=["Brian McCullough"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/PersonAddresses",
    )
