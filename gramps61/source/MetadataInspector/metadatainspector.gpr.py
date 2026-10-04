# encoding:utf-8
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2009-2011 Rob G. Healey <robhealey1@gmail.com>
#               2026      Claude AI (wish coding by Brian McCullough)
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

# ------------------------------------------------------------------------
# Metadata Inspector gramplet
#
# No requires_gi / requires_mod on purpose: every reader (GExiv2, pypdf,
# mutagen) is optional and the gramplet shows a hint if one is missing.
# ------------------------------------------------------------------------
from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="Metadata Inspector",
        name=_("Metadata Inspector"),
        description=_(
            "Gramplet to view the metadata of a media object: embedded in the "
            "file (Exif, IPTC, XMP, PDF, audio/video tags), in its XMP sidecar, "
            "and recorded in the current tree"
        ),
        height=400,
        expand=True,
        gramplet="MetadataInspector",
        gramplet_title=_("Metadata Inspector"),
        detached_width=600,
        detached_height=550,
        version="0.0.1",
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        include_in_listing=True,
        fname="metadatainspector.py",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        navtypes=["Media"],
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/MetadataInspector",
    )
