#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2007-2009  Douglas S. Blank <doug.blank@gmail.com>
# Copyright (C) 2011       Gary Burton
# Copyright (C) 2026       Claude AI (prompted by Brian McCullough)
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

from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Register Complete Biography addon Quick Report for Person categories
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(QUICKREPORT,
            id    = 'completebiographyquickview',
            name  = _("Biography - Complete"),
            description= _("Display a more extensive biography, combining "
                            "the events, families, and other details of the "
                            "Complete Individual Report with the narrative "
                            "style of the Biography quick view"),
            version = '0.0.3',
            gramps_target_version = major_version,
            status = EXPERIMENTAL,
            fname = 'CompleteBiographyQuickview.py',
            authors = ["A Guinane", "Claude AI"],
            maintainers = ["Brian McCullough"],
            category = CATEGORY_QR_PERSON,
            runfunc = 'run',
            help_url = "Addon:Biography_Quickview#Complete_Biography",
    )
