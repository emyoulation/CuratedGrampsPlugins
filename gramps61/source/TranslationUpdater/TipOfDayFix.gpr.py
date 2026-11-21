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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""Registration for Tip of the Day Fix (monkey patch)."""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2) <= VERSION_TUPLE[:2] < (7, 0):
    register(
        GENERAL,
        id="TipOfDayFix",
        name=_("Tip of the Day Fix"),
        description=_(
            "Monkey patch for Tip of the Day: shows the paragraph breaks in "
            "tips correctly when they are written in an unexpected form, and "
            "stops the GTK markup warnings this causes."
        ),
        version="0.1.0",  # build 20261121.0556
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="TipOfDayFix.py",
        authors=["Brian McCullough"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        load_on_reg=True,
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
            "gramps61/source/TipOfDayFix"
        ),
    )
