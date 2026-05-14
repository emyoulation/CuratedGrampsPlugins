#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2019       Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2026       Claude AI
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
# Themes
#
# ------------------------------------------------------------------------
if VERSION_TUPLE >= (5, 2, 0):
    register(
        GENERAL,
        id="ThemesPrefs",
        name=_("Theme preferences"),
        description=_(
            "An addition to Preferences for simple Theme and Font"
            " adjustment.  Especially useful for Windows users."
            " Also supports a layered CSS theming system with"
            " CSS Themes, CSS Patches, and a personal user override."
        ),
        version="1.0.0",
        gramps_target_version=major_version,
        fname="themes_load.py",
        authors=["Paul Culley"],
        authors_email=["paulr2787@gmail.com"],
        maintainers=["Brian McCullough"],
        maintainers_email=["emyoulation@yahoo.com"],
        category=TOOL_UTILS,
        load_on_reg=True,
        status=EXPERIMENTAL,
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/gramps61/source/Theme2/README.md",
        # help_url="Addon:Theme2",
    )
