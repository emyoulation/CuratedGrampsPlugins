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
        id="capsulesources",
        name=_("Capsule Sources"),
        description=_(
            "Imports record captures saved by the Genealogy Capsule browser "
            "extension as Sources, Citations and Media, without creating people"
        ),
        version="0.1.0",  # build 20261030.1949
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="capsule_sources.py",
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
            "tree/main/CapsuleSources"
        ),
    )
