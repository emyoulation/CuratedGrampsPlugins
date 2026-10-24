#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2015      Nick Hall
# Copyright (C) 2024      Paul Womack (BugBear)
# Copyright (C) 2026      Doug Blank
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
# Copyright (C) 2026      Kari Kujansuu
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
# Flat Filter gramplet (BugBear's Flat Filter, by way of Doug Blank's
# Relationship Filter)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="Flat Filter",
        name=_("Flat Filter"),
        description=_(
            "Gramplet providing a person filter on relationships, with "
            "a choice of phonetic matching systems"
        ),
        version="2.0.2",  # build 20261023.2148
        gramps_target_version=major_version,
        authors=["Paul Womack", "Doug Blank"],
        authors_email=["", "doug.blank@gmail.com"],
        maintainers=["Brian McCullough"],
        status=STABLE,
        fname="FlatFilter.py",
        height=200,
        gramplet="FlatFilter",
        gramplet_title=_("Flat Filter"),
        # Detached gramplet default window size is 400x300
        # The settings below show every row without scroll bars.
        detached_width=560,
        detached_height=700,
        navtypes=["Person"],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins"
            "/tree/main/gramps61/source/FlatFilter"
        ),
        # help_url="https://gramps.discourse.group/t/9725",
        # help_url="Addon:FlatFilter",
    )

# ------------------------------------------------------------------------
#
# Flat Filter rule: stand-in rule for searches saved with "Define filter"
#
# ------------------------------------------------------------------------
# Define filter exists only in Gramps 6.0 and later. The id must be unique
# among all plugins, and the ruleclass unique among all Person rules: a
# duplicate silently replaces the other one. The ruleclass is also saved
# by name in custom_filters.xml, so it must never be renamed (see
# DefineFilter.md).
if (6, 0, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        id="FlatFilterRule",
        name=_("Flat Filter rule"),
        description=_(
            "Rule used by custom filters saved with the Define filter "
            "button of the Flat Filter gramplet"
        ),
        version="0.0.1",
        authors=["Kari Kujansuu"],
        maintainers=["Brian McCullough"],
        gramps_target_version=major_version,
        status=STABLE,
        fname="FlatFilter.py",
        ruleclass="FlatFilterRule",  # rule class name
        namespace="Person",  # one of the primary object classes
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins"
            "/tree/main/gramps61/source/FlatFilter/DefineFilter.md"
        ),
    )
