#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Jerome Rapinat
# Copyright (C) 2026  Claude AI (wish coding by Brian McCullough)
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
# Custom Soundex person filter rule with name-field options (standalone,
# and the Fuzzy Matching Gramplet's Soundex Custom encoding system when
# installed)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        # "FuzzyMatchingEncoder:" prefix: see phonetic_codes._ENCODER_ID_PREFIX.
        id="FuzzyMatchingEncoder:soundex_custom",
        name=_("Soundex Custom match of People with the <names>"),
        description=_(
            "Matches people with a name field having the same custom"
            " Soundex phonetic encoding as a test name."
        ),
        version="0.1.0",  # build 20261106.1730
        authors=["Jerome Rapinat", "Claude"],
        maintainers=["Jerome Rapinat"],
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="soundexcustomrule.py",
        ruleclass="HasSoundexCustomNames",  # must be rule class name
        namespace="Person",  # one of the primary object classes
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins"
            "/blob/main/gramps61/source/FussyRules_romjerome"
        ),
    )
