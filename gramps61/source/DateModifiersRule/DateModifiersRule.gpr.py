#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Date Modifiers Rule: one custom filter rule (per object type) that matches
valid dates by Type and Quality, or invalid (Text only) dates by text.
Companion to the Edit Date Calculator addon.
"""

from gramps.version import major_version, VERSION_TUPLE

if (5, 2, 0) <= VERSION_TUPLE < (6, 2, 0):
    for _ns, _cls, _name in (
        ("Event", "HasDateModifiersEvent", _("Event Date Modifiers")),
        ("Citation", "HasDateModifiersCitation", _("Citation Date Modifiers")),
        ("Media", "HasDateModifiersMedia", _("Media Date Modifiers")),
    ):
        register(
            RULE,
            id=_cls,
            name=_name,
            description=_(
                "Filter rule: valid dates by Type and Quality, "
                "or invalid (Text only) dates by text."
            ),
            version="0.0.0",  # build 20261029.1440
            gramps_target_version=major_version,
            status=EXPERIMENTAL,
            fname="DateModifiersRule.py",
            ruleclass=_cls,  # must be the rule class name
            namespace=_ns,  # one of the primary object classes
            authors=["Claude", "Brian McCullough"],
            authors_email=["", ""],
            maintainers=["Brian McCullough"],
            maintainers_email=[""],
            help_url=(
                "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/"
                "gramps61/source/DateModifiersRule"
            ),
            # help_url="https://gramps.discourse.group/t/10127/8",
        )
