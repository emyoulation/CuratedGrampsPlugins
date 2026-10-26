#
# Gramps - a GTK+/GNOME based genealogy program
# http://gramps-project.org
# Gramplet registration - plug-in/add-on to extend Gramps
#
# Copyright (C) 2026    Brian McCullough (Claude wish coding)
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
        id="PDFFieldMapper",
        name=_("PDF Field Mapper"),
        description=_(
            "Map the form fields of a PDF media object to GEDCOM-style names, "
            "reorder the tab sequence, and embed the mapping in the PDF"
        ),
        version="0.0.2",
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="pdffieldmapper.py",
        height=350,
        gramplet="PDFFieldMapper",
        gramplet_title=_("PDF Field Mapper"),
        navtypes=["Media"],
        requires_mod=["pypdf"],
        include_in_listing=True,
        help_url="https://claude.ai/share/5499326c-cb83-453f-aa82-7f8248f94ca6",
    )

