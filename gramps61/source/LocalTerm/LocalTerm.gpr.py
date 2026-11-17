#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C)           Kaj Mikkelsen
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
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
Gramps registration file for the Localized Glossary Index gramplet.
"""

from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Register the Gramplet
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="LocalTerm Gramplet",
        name=_("Localized Gramps Glossary Terminology"),
        description=_("Localized index to Gramps Glossary terminology"),
        version="0.3.7",  # build 20261028.1545
        gramps_target_version=major_version,
        status=BETA,
        audience=EXPERT,
        fname="LocalTerm.py",
        authors=["Kaj Mikkelsen", "Claude AI"],
        authors_email=["kmi@vgdata.dk", ""],
        maintainers=["Brian McCullough"],
        maintainers_email=["emyoulation@yahoo.com"],
        height=20,
        detached_width=510,
        detached_height=480,
        expand=True,
        gramplet="LocalTerm",
        gramplet_title=_("Localized Glossary Index"),
        navtypes=["Person", "Dashboard", "Note"],
        help_url="https://github.com/emyoulation/LocalTerm",
    )
