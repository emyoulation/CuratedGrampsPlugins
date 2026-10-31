# Based on Genealogy Capsule, Copyright (c) 2026 the Genealogy Capsule authors
# (mjlawless), MIT License:
# https://github.com/mjlawless/capsule-genealogy/blob/main/LICENSE
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
#
# GPL-2.0-or-later.
#

from gramps.version import major_version, VERSION_TUPLE

if VERSION_TUPLE >= (5, 2, 0):
    register(
        TOOL,
        id="CapsuleSources",
        name=_("Capsule Sources"),
        description=_(
            "Imports record captures saved by the Genealogy Capsule browser "
            "extension as Sources, Citations and Media, and links each one to "
            "the person you choose"
        ),
        version="0.2.0",  # build 20261031.1937
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="CapsuleSources.py",
        authors=["Genealogy Capsule authors", "mjlawless"],
        # authors_email=["", ""],
        maintainers=["Claude AI", "Brian McCullough"],
        # maintainers_email=["", ""],
        category=TOOL_DBPROC,
        toolclass="CapsuleSources",
        optionclass="CapsuleSourcesOptions",
        tool_modes=[TOOL_MODE_GUI],
        help_url=(
            "https://github.com/emyoulation/CuratedGrampsPlugins/"
            "tree/main/gramps61/source/CapsuleSources"
        ),
    )
