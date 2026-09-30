#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Phonetic Matching Gramplet contributors
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
# Phonex person filter rule with name-field options (the Fuzzy Matching
# Gramplet's Phonex encoding system when installed)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        # "FuzzyMatchingEncoder:" prefix: see phonetic_codes._ENCODER_ID_PREFIX.
        id="FuzzyMatchingEncoder:phonex",
        name=_("Phonex match of People with the <names>"),
        description=_(
            "Matches people with a name field having the same Phonex "
            "phonetic encoding as a test name."
        ),
        version="0.3.2",
        authors=["Claude"],
        maintainers=["Brian McCullough"],
        gramps_target_version=major_version,
        status=STABLE,
        fname="phonexrule.py",
        ruleclass="HasPhonexNames",  # must be rule class name
        namespace="Person",  # one of the primary object classes
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/FuzzyRules/README.md",
    )
