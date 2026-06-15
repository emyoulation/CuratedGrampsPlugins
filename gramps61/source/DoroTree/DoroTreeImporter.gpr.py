# -*- coding: utf-8 -*-
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Brian McCullough, Gemini
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

# ------------------------
# Gramps modules
# ------------------------

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.version import major_version, VERSION_TUPLE

_ = glocale.translation.gettext

if VERSION_TUPLE >= (5, 2, 0):
    register(
        IMPORT,
        id="dorotree import",
        name=_("DoroTree Importer"),
        description=_("Imports bilingual DoroTree (.dte) backup files natively"),
        version="0.0.1",
        gramps_target_version=major_version,
        status=STABLE,
        fname="DoroTreeImporter.py",
        import_function="import_data",
        extension="dte",
        help_url="README.md",
    )
