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
"""Registration for Translation Updater (startup engine + tool)."""

from gramps.version import major_version, VERSION_TUPLE

HELP_URL = "https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/TranslationUpdater/README.md"

if (5, 2) <= VERSION_TUPLE[:2] < (7, 0):
    # Startup half: applies downloaded packs before most windows open.
    register(
        GENERAL,
        id="TranslationUpdaterStartup",
        name=_("Translation Updater startup"),
        description=_(
            "Applies translation packs downloaded by the Translation Updater tool."
        ),
        version="0.1.0",  # build 20261121.0005
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="TranslationUpdaterLib.py",
        authors=["Brian McCullough"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        category=TOOL_UTILS,
        load_on_reg=True,
        include_in_listing=False,
        help_url=HELP_URL,
    )

    # Tool: choose languages and download.
    register(
        TOOL,
        id="TranslationUpdater",
        name=_("Translation Updater"),
        description=_(
            "Downloads newer Gramps and addon translations for chosen languages, "
            "without changing addon versions."
        ),
        version="0.1.0",  # build 20261121.0005
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="TranslationUpdater.py",
        authors=["Brian McCullough"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        category=TOOL_UTILS,
        toolclass="TranslationUpdater",
        optionclass="TranslationUpdaterOptions",
        tool_modes=[TOOL_MODE_GUI],
        help_url=HELP_URL,
    )
