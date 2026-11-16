#
# Gramps - a GTK+/GNOME based genealogy program
#
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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""
Registration for Addon Locale Fix.

Works on every Gramps version with addon support and a GrampsLocale
(4.0 and newer), so this file deliberately keeps pre-5.2 branches:
before 5.2 there is no EXPERIMENTAL status, no maintainers attribute,
help_url is accepted for gramplets only, and register() rejects unknown
keywords.
"""

from gramps.version import major_version, VERSION_TUPLE

HELP_URL = "https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/AddonLocaleFix/README.md"

if (4, 0) <= VERSION_TUPLE[:2] < (7, 0):
    _KWARGS = dict(
        id="AddonLocaleFix",
        name=_("Addon Locale Fix"),
        description=_(
            "Monkey patch that helps addons work in more languages. Addons "
            "load even without a translation for your language, and their "
            "own translations come first."
        ),
        version="0.1.0",  # build 20261116.1701
        gramps_target_version=major_version,
        status=STABLE,
        fname="AddonLocaleFix.py",
        authors=["Brian McCullough"],
        authors_email=[""],
        load_on_reg=True,
    )
    if VERSION_TUPLE[:2] >= (5, 2):
        _KWARGS["maintainers"] = ["Brian McCullough"]
        _KWARGS["help_url"] = HELP_URL

    register(GENERAL, **_KWARGS)
