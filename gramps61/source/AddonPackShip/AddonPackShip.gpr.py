#!/usr/bin/python
# -*- coding: utf-8 -*-

#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough <emyoulation@yahoo.com>
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
# along with this program; if not, see <https://www.gnu.org/licenses/>.

"""
Gramps registration file for Addon Pack and Ship Tool

Author: Brian McCullough
Development: AI-assisted using Claude (Anthropic)
Date: February 2026
🤖 Generated with Claude Code https://claude.com/claude-code
"""

from gramps.gen.const import GRAMPS_LOCALE as glocale
_ = glocale.translation.gettext

#------------------------------------------------------------------------
#
# Register the Tool
#
#------------------------------------------------------------------------

register(
    TOOL,
    id = 'addonpackship',
    name = _("Addon Pack and Ship"),
    description = _(
        "Packaging and distribution tool - create release-ready "
        "Gramps addon plugin packages and listings for GitHub publishing"
    ),
    version = '1.8.11',
    gramps_target_version = '5.2',
    status = STABLE,
    audience = EXPERT,
    fname = 'AddonPackShip.py',
    authors = ["Claude (Anthropic AI)"],
    authors_email = [""],
    maintainers = ["Brian McCullough"],
    maintainers_email = ["emyoulation@yahoo.com"],
    category = TOOL_UTILS,
    toolclass = 'AddonPackShip',
    tool_modes = [TOOL_MODE_GUI],
    help_url = ("https://github.com/emyoulation/CuratedGrampsPlugins/"
        "blob/main/ COMPARE_make_APS.md"),
    optionclass = 'AddonPackShipOptions',
)
