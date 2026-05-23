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
# $Id$

#------------------------------------------------------------------------
#
# Plugin Manager Enhanced
#
#------------------------------------------------------------------------
from gramps.version import major_version, VERSION_TUPLE

"""
Plugin registration for the Plugin Manager plus Help menu option.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "create a new Dashboard gramplet that inventories the icons available
in the current GTK/Gramps theme, using the freedesktop Icon Theme Specification
and the existing Themes addon cascade; clicking an icon name shows the full size
family and the MarkdownDash markdown source; refresh on theme change."
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
Date: May 2026
"""

if VERSION_TUPLE >= (5, 2, 0):
    register(GENERAL,
    id    = 'PluginManager',
    name  = _("Plugin Manager plus"),
    description =  _("Plugin Manager with expanded feedback"),
    version = '1.3.0',
    gramps_target_version = major_version,
    fname = "PluginManagerLoad.py",
    authors = ["Paul Culley"],
    authors_email = ["paulr2787@gmail.com"],
    maintainers = ["Brian McCullough"],
    maintainers_email = ["emyoulation@yahoo.com"],
    category = TOOL_UTILS,
    load_on_reg = True,
    help_url = 'README(PluginMgrPlus).md',
    # help_url = 'Addon:Plugin_ManagerV2',
    status = STABLE
    )
