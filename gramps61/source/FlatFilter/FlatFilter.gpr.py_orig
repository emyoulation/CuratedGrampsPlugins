#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2015      Nick Hall
# Copyright (C) 2024      Paul Womack (BugBear)
# Copyright (C) 2026      Doug Blank
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
from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Flat Filter gramplet (BugBear's Flat Filter, by way of Doug Blank's
# Relationship Filter)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="Flat Filter",
        name=_("Flat Filter"),
        description=_(
            "Gramplet providing a person filter on relationships, with "
            "a choice of phonetic matching systems"
        ),
        version="2.0.0",  # build 20261021.1538
        gramps_target_version=major_version,
        status=STABLE,
        fname="FlatFilter.py",
        height=200,
        gramplet="FlatFilter",
        gramplet_title=_("Flat Filter"),
        # Undocked window size that shows every row without scroll bars.
        detached_width=560,
        detached_height=700,
        navtypes=["Person"],
        authors=["Paul Womack", "Doug Blank"],
        authors_email=["doug.blank@gmail.com"],
        help_url="Addon:FlatFilter",
    )
