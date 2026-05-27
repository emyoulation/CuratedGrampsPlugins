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
"""Help/Plugin Manager

This module implements the enhanced Plugin manager.  The upper information
panel is rendered via :mod:`MarkdownUtils` into a two-column layout:
left column carries the MarkdownUtils-rendered plugin detail text; right
column shows a preview thumbnail.  The lower panel holds the plugin list
with action buttons and filter checkboxes.

Layout toggle
-------------
The bottom-bar **Help** button (label changes to **Details** when README is
showing) swaps the info panel content between:

* **Details mode** — plugin registration Markdown + placeholder icon.
  Button label: *Help*.
* **README mode** — ``README(PluginMgrPlus).md`` + screenshot
  ``media/PluginMgr_capture.png``.  Button label: *Details*.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "swap layout so info pane is top and plugin list is bottom; add
Help/Details toggle button that swaps README+screenshot vs plugin
details+icon; hotlink fname/fpath, help_url, author/maintainer emails;
render boolean flags as icons; remove Edit/Wiki buttons."
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
"""



from gramps.version import major_version, VERSION_TUPLE

#------------------------------------------------------------------------
#
# Plugin Manager plus
#
#------------------------------------------------------------------------
if VERSION_TUPLE >= (5, 2, 0):
    register(
        GENERAL,
        id = "PluginManager",
        name = _("Plugin Manager plus"),
        description = "An Addon/Plugin Manager with several additional "
                 "capabilities",
        version = '1.3.0',
        gramps_target_version = major_version,
        status = EXPERIMENTAL,
        fname = "PluginManagerLoad.py",
        authors = ["Paul Culley","Claude AI"],
        authors_email = ["paulr2787@gmail.com",],
        maintainers = ["Brian McCullough"],
        maintainers_email = ["emyoulation@yahoo.com"],
        category = TOOL_UTILS,
        load_on_reg = True,
        help_url = 'Addon:Plugin_Manager_plus',
    )
