#
# Gramps - a GTK+/GNOME based genealogy program
#
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    register(
        GENERAL,
        id="PR2485",
        name=_("PR2485 Edit Person Tweaks"),
        description=_(
            "Improves the New/Edit Person dialogs: Multiple Surnames column "
            "widths are remembered (Gramps PR 2485), switching to Multiple "
            "Surnames adds a row ready for typing, a Fuzzy Match Lookup "
            "button appears beside the Surname field when Fuzzy Matching is "
            "installed, and the Surname field shows a 'surname' tip."
        ),
        version="0.1.0",  # build 20261113.2223
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="PR2485.py",
        authors=["Douglas S. Blank", "Claude AI"],
        authors_email=["",""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        load_on_reg=True,
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/PR2485/CHANGELOG.md",
    )
