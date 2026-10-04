#
# Gramps - a GTK+/GNOME based genealogy program
# http://gramps-project.org
# Gramplet registration - plug-in/add-on to extend Gramps
#
# Copyright (C) 2013    Artem Glebov <artem.glebov@gmail.com>
# Copyright (C) 2014    Nick Hall
# Copyright (C) 2021    Paul Culley
# Copyright (C) 2021    Bruce Jackson
# Copyright (C) 2026    Brian McCullough
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

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="Photo Tagging",
        name=_("Photo Tagging"),
        description=_("Gramplet for tagging people in photos"),
        authors=["Artem Glebov", "Nick Hall", "Paul Culley", "Bruce Jackson"],
        maintainers=["Brian McCullough"],
        version = '1.2.2',
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="PhotoTaggingGramplet.py",
        height=400,
        gramplet="PhotoTaggingGramplet",
        gramplet_title=_("Photo Tagging"),
        navtypes=["Media"],
        help_url="https://gramps.discourse.group/t/1889/14",
        include_in_listing=True,
        #requires_gi=[("GExiv2", "0.10,0.12,0.14,0.16")],
    )
