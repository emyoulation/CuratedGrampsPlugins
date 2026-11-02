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

if (5, 2, 0) <= VERSION_TUPLE < (6, 1, 0):
    register(
        GENERAL,
        id="StrictPyGObjectCompat",
        name=_("Strict PyGObject Compatibility"),
        description=_(
            "On systems with PyGObject 3.56 or newer, prevents crashes such as "
            "the Place Details gramplet 'Must be string' error, and stops a "
            "small memory leak when editing table cells in editors. Does "
            "nothing on older systems."
        ),
        version="0.1.0",  # build 20261102.0302
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="StrictPyGObjectCompat.py",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=["https://gramps.discourse.group/t/10178"],
        load_on_reg=True,
        help_url=("https://gramps.discourse.group/t/10178"),
        # help_url=(
        #     "https://github.com/emyoulation/CuratedGrampsPlugins/"
        #     "tree/main/gramps61/source/StrictPyGObjectCompat"
        # ),
    )
