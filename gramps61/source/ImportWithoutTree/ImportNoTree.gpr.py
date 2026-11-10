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

# Monkey patch for Gramps 5.2 through 6.1 (Mantis 0012185).
if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        GENERAL,
        id="ImportNoTree",
        category="ImportNoTree",
        name=_("Import with No Tree Loaded"),
        description=_(
            "Makes Family Trees > Import... work when no Family Tree is "
            "loaded. A new Family Tree is created, named after the imported "
            "file, and the file is imported into it."
        ),
        version="0.1.0",  # build 20261110.0013
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="ImportNoTree.py",
        load_on_reg=True,
        authors=["Claude AI"],
        maintainers=["Brian McCullough"],
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/ImportNoTree/README.md",
    )
