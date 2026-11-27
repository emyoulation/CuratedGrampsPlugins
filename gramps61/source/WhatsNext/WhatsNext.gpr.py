# encoding:utf-8
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2009 Benny Malengier
# Copyright (C) 2011 Nick Hall
# Copyright (C) 2011 Tim G L Lyons
# Copyright (C) 2023-2024 Brian McCullough
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

# ------------------------------------------------------------------------
#
# Gramps modules
#
# ------------------------------------------------------------------------

# register, GRAMPLET, STABLE, EVERYONE and _ are provided by the Gramps
# plugin registration environment.
from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Register What's Next Gramplet
#
# This addon uses the same id as the built-in "What's Next" gramplet. Gramps
# registers its built-in plugins first and the addons in the user plugins
# folder second, and a later registration with the same id replaces the
# earlier one, so this gramplet supersedes the built-in one. The name,
# description and title reuse the strings Gramps already translates.
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="What's Next",
        name=_("What's Next"),
        description=_("Gramplet suggesting items to research"),
        version="1.1.0",  # build 20261127.0132
        gramps_target_version=major_version,
        status=STABLE,
        audience=EVERYONE,
        authors=["Reinhard Mueller"],
        authors_email=[""],
        maintainers=["Jakim Friant", "Brian McCullough"],
        maintainers_email=["jmodule@friant.org", "emyoulation@yahoo.com"],
        fname="WhatsNext.py",
        height=300,
        expand=True,
        gramplet="WhatNextGramplet",
        gramplet_title=_("What's Next?"),
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
            "gramps61/source/WhatsNext"
        ),
    )
