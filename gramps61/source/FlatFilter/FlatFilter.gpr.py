#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2024-2026  Paul Womack (BugBear)
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

# ------------------------------------------------------------------------
#
# FlatFilter Gramplet registration
#
# FlatFilter extends the built-in Person Filter sidebar with additional
# relationship-aware name matching rules:
#   - Father / Mother name match
#   - Person's own name (given and family separately)
#   - Spouse name match
#   - Sibling name match (× 2 rows, reserved for future variants)
#   - Child name match   (× 2 rows, reserved for future variants)
#   - Probably-Alive date range filter
#
# Each name field is split into two entry boxes: one for given/personal
# names and one for family/surname names, so partial or regex searches
# can target each part independently.
#
# Registered for the "Person" navtype only, because all filter rules and
# the sidebar class (PersonSidebarFilter2) are written specifically around
# Person records and person-relative relationships.
#
# Author    : Paul Womack (BugBear)
# Maintainer: <maintainer name and contact>
#
# Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, 2025)
# Prompts used:
#   1. "Create a .gpr.py for FlatFilter.py gramplet code (for all categories)
#       following Gramps developer guidelines"
#   2. "Running a filtering under 5.2 fails. Adapting the .gpr.py to 6.0 gives
#       AttributeError: 'HasNamedFather' object has no attribute 'apply_to_one'"
# Constraints:
#   https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
#   https://github.com/gramps-project/gramps/blob/master/AGENTS.md
#
# Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
#
# ------------------------------------------------------------------------

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
_ = glocale.translation.gettext

# ------------------------------------------------------------------------
#
# FlatFilter Gramplet — Person view
#
# ------------------------------------------------------------------------
register(
    GRAMPLET,
    id="Person Flat Filter",
    name=_("Person Flat Filter"),
    description=_(
        "Extended person filter gramplet with split given/family name "
        "entry boxes and relationship-aware name-matching rules for "
        "father, mother, spouse, sibling, and child."
    ),
    authors="Paul Womack",
    version="1.0.02",
    gramps_target_version="6.0",
    status=STABLE,
    fname="FlatFilter.py",
    gramplet="FlatFilter",
    gramplet_title=_("Flat Filter"),
    navtypes=["Person"],
    help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/FlatFilter/README.md",
)
