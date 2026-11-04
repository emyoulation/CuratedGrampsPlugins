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
from gramps.version import major_version, VERSION_TUPLE

# Prototype: Gramps 6.0 and newer only (DB-API backends).
if VERSION_TUPLE >= (6, 0, 0):
    register(
        TOOL,
        id="PrunedBranch",
        name=_("Pruned Branch"),
        description=_(
            "Limit views, filters, tools and reports to one branch of the "
            "Family Tree for an editing session (prototype)."
        ),
        version="0.1.0",  # build 20261029.1728
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="PrunedBranch.py",
        authors=["Brian McCullough"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=[""],
        category=TOOL_UTILS,
        toolclass="PrunedBranchTool",
        optionclass="PrunedBranchOptions",
        tool_modes=[TOOL_MODE_GUI],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/"
            "tree/main/gramps61/source/PrunedBranch"
        ),
    )
