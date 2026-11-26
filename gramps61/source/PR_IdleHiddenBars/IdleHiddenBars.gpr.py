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

if (5, 2, 0) <= VERSION_TUPLE < (6, 3, 0):
    register(
        GENERAL,
        id="IdleHiddenBars",
        name=_("Idle Hidden Bars"),
        description=_(
            "A monkey patch so that a hidden sidebar or bottombar does no "
            "work: its gramplet stops updating while the bar is hidden and "
            "catches up when the bar is shown again. Undocked gramplets keep "
            "updating."
        ),
        version="0.1.0",  # build 20261126.1914
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="IdleHiddenBars.py",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        load_on_reg=True,
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/IdleHiddenBars",
    )
