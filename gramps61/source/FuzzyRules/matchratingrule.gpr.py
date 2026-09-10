#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025  Phonetic Matching Gramplet contributors
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
# Match Rating Approach person filter rule (standalone, and used by the
# Fuzzy Matching Gramplet's "Define filter" action when Match Rating
# Approach is selected)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        # The "FuzzyMatchingEncoder:" prefix is what the Fuzzy Matching
        # Gramplet's Encoding system list actually looks for (see
        # phonetic_codes._ENCODER_ID_PREFIX) - not this file's location.
        # Any independently packaged/updated addon can use the same
        # prefix to show up there too; nothing about this id needs to
        # match a folder or filename.
        id="FuzzyMatchingEncoder:match_rating",
        name=_("Match Rating Approach match of People with the <surname>"),
        description=_(
            "Matches people whose primary surname has a specified Match"
            " Rating Approach codex"
        ),
        version="0.2.0",
        authors=["Claude"],
        maintainers=["Brian McCullough"],
        gramps_target_version=major_version,
        status=STABLE,
        fname="matchratingrule.py",
        ruleclass="HasMatchRatingName",  # must be rule class name
        namespace="Person",  # one of the primary object classes
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/FuzzyRules/README.md",
        #help_url="https://gramps.discourse.group/t/9951/14",
        #help_url="Fuzzy_Matching_Gramplet",
    )
