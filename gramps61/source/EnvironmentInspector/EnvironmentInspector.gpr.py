# EnvironmentInspector.gpr.py
#    — Gramps plugin registration for Environment Inspector gramplet
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
# Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
# Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
from gramps.version import major_version, VERSION_TUPLE

#------------------------------------------------------------------------
#
# Environment Inspector
#
#------------------------------------------------------------------------

if VERSION_TUPLE >= (5, 2, 0):
    register(
        GRAMPLET,
        id="EnvironmentInspector",
        name=_("Environment Inspector"),
        description=_("Two-tab developer reference gramplet showing the current locale "
                      "and a searchable, sortable table of all Gramps string constants."),
        version="1.0.5",
        gramps_target_version=major_version,
        status=STABLE,
        audience=EVERYONE,
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=["emyoulation@yahoo.com"],
        fname="EnvironmentInspector.py",
        height=375,
        gramplet="EnvironmentInspector",
        gramplet_title=_("Environment Inspector"),
        navtypes=["Dashboard"],
        include_in_listing=True,
        help_url="https://github.com/emyoulation/EnvironmentInspector/blob/master/"
                 "README.md#environment-inspector-gramplet",
    )