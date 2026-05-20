# ------------------------------------------------------------------------
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
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

"""
Plugin registration for the Icon Browser gramplet.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "create a new Dashboard gramplet that inventories the icons available
in the current GTK/Gramps theme, using the freedesktop Icon Theme Specification
and the existing Themes addon cascade; clicking an icon name shows the full size
family and the MarkdownDash markdown source; refresh on theme change."
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
Revised Development: AI-assisted using Gemini (Google)
Date: May 2026
"""

if VERSION_TUPLE >= (5, 2, 0):
  register(
      GRAMPLET,
      id="IconBrowserGramplet",
      name=_("Icon Browser"),
      description=_(
          "Browse the icons available in the current GTK/Gramps theme. "
          "Click any icon name to see all available sizes and the "
          "MarkdownDash syntax for embedding that icon."
      ),
      status=STABLE,
      version="1.1.0",
      gramps_target_version=major_version,
      fname="IconBrowserGramplet.py",
      gramplet="IconBrowserGramplet",
      height=400,
      expand=True,
      gramplet_title=_("Icon Browser"),
      detached_width=900,
      detached_height=650,
      navtypes= ["Dashboard"],
      include_in_listing=True,
      help_url = "https://gramps.discourse.group/t/2884/9",
  )
