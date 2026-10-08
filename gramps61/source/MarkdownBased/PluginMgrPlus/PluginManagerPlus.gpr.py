#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2017      Paul Culley
# Copyright (C) 2026      Brian McCullough
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
"""Registration for the PluginManager2 prototype addon.

``fname`` points at PluginManager2Load.py, not PluginManager2.py directly:
``load_on_reg=True`` makes Gramps call that loader's ``load_on_reg()`` at
registration time, which monkey-patches
``gramps.gui.viewmanager.PluginWindows.PluginStatus`` (the class behind
the built-in Help -> Plugin Manager menu item) with this addon's enhanced
``PluginStatus`` from PluginManager2.py. This mirrors PluginManagerPlus's
own PluginManagerLoad.py mechanism exactly.

Generated-by: Claude Sonnet 5 (Anthropic, claude-sonnet-5, chat interface)
Prompts: "Revise PluginManagerPlus into PluginManager2 (skip AGENTS.md
formatting for this prototyping pass)."; corrected after the user supplied
the original PluginManagerLoad.py loader to validate the fname/load_on_reg
mechanism.
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md (deferred
  for this prototyping pass at user's request)
Co-authored-by: Claude Sonnet 5 <noreply@anthropic.com>
"""

from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Plugin Manager Plus (prototype)
#
# ------------------------------------------------------------------------
if (5, 2, 0) <= VERSION_TUPLE <= (6,2,0):
    register(
        GENERAL,
        id="PluginManagerPlus",
        name=_("Plugin Manager plus"),
        description=(
            "Prototype fork of Plugin Manager plus: fault-tolerant addon"
            " listing import, and a locally-cached wiki addon catalog"
            " (with thumbnails) shared by installed and available addons."
        ),
        version="2.1.2",
        gramps_target_version=major_version,
        status=BETA,
        fname="PluginManagerPlusLoad.py",
        authors=["Paul Culley", "Claude AI"],
        authors_email=["paulr2787@gmail.com"],
        maintainers=["Brian McCullough"],
        maintainers_email=["emyoulation@yahoo.com"],
        category=TOOL_UTILS,
        load_on_reg=True,
        #help_url="Addon:Plugin_Manager_Plus",
    )
