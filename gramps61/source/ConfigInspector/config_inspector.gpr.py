# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Claude Sonnet 5
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
from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Config Inspector (Tools > Debug)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        TOOL,
        id="Config Inspector",
        name=_("Config Inspector"),
        description=_(
            "Lists every gramplet entry cached in this profile's saved "
            "dashboard, sidebar, and bottombar layout .ini files "
            "(identifying which view/splitbar each came from), and can "
            "flush all of them at once so every view rebuilds its "
            "gramplet layout fresh from the currently registered plugin "
            "data."
        ),
        status=EXPERIMENTAL,
        audience=DEVELOPER,
        version="0.0.2",
        gramps_target_version=major_version,
        fname="config_inspector.py",
        authors=["Claude"],
        category=TOOL_DEBUG,
        toolclass="ConfigInspector",
        optionclass="ConfigInspectorOptions",
        tool_modes=[TOOL_MODE_GUI],
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/ConfigInspector",
    )
