#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025      Kari Kujansuu (SuperTool script)
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
# Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
# Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
#

from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Note styling editor
#
# One registration, one class, covering every note-holding category via
# navtypes=[...]. NoteStylingEditor.py resolves which single category a
# given instance is actually in at runtime (see its
# resolve_primary_navtype()), via the page hosting it -- so one shared
# class here is correct, unlike naively checking every category's
# active object at once (which would keep reflecting a stale one; see
# NoteStylingEditor.py's module docstring for the full explanation).
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="Note Styling Editor",
        name=_("Note Styling Editor"),
        description=_(
            "View and strip StyledText markup (bold, color, links, etc.) from "
            "a selected Note, or the first Note attached to the active record "
            "in any other note-holding category (Citation, Person, Family, "
            "Event, Place, Source, Repository, Media)"
        ),
        authors=["Kari Kujansuu", "Claude AI"],
        maintainers=["Brian McCullough"],
        status=EXPERIMENTAL,
        audience=EVERYONE,
        version="0.0.2",
        gramps_target_version=major_version,
        # height=400,
        expand=True,
        gramplet="NoteStylingEditor",
        fname="NoteStylingEditor.py",
        gramplet_title=_("Note Styling Editor"),
        navtypes=[
            "Note",
            "Citation",
            "Person",
            "Family",
            "Event",
            "Place",
            "Source",
            "Repository",
            "Media",
        ],
        # help_url="Addon:Note_Styling_Editor",
        help_url="https://gramps.discourse.group/t/5396",
    )
