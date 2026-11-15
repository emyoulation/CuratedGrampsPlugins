#
# Gramps - a GTK+/GNOME based genealogy program
#
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
# Clipboard Ref and Place context Menus
#
# ------------------------------------------------------------------------
if VERSION_TUPLE[:2] >= (5, 2):
    register(
        GENERAL,
        id="ClipboardRefMenu",
        name=_("Clipboard Ref Menu"),
        description=_(
            "Adds Clip items to the clipboard right-click menu: the object a "
            "reference row points to, and all the places enclosing a place."
        ),
        version="0.1.0",  # build 20261115.1540
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="ClipboardRefMenu.py",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        category=TOOL_UTILS,
        load_on_reg=True,
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/"
            "gramps61/source/ClipboardRefMenu/README.md"
        ),
    )
