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
"""Registration for the PR2296 Live Preferences monkey patch addon."""

from gramps.version import major_version, VERSION_TUPLE

# Gramps 5.2 up to (not including) 6.2, where core could adopt the fix.
if (5, 2) <= VERSION_TUPLE[:2] < (6, 2):
    register(
        GENERAL,
        id="PR2296_LivePreferences",
        name=_("PR2296 Live Preferences"),
        description=_(
            "Monkey patch: applies the Date format, Age display precision, "
            "Display ages for events after death, and Navigator text label "
            "Preferences without restarting Gramps. Also shows date format "
            "examples in Preferences (Gramps PR 2296)."
        ),
        version="0.1.0",  # build 20261122.1820
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        fname="PR2296_LivePreferences.py",
        load_on_reg=True,
        authors=["Brian McCullough", "Doug Blank", "Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        help_url="https://github.com/gramps-project/gramps/pull/2296",
    )
