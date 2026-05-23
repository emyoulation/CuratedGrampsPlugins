#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough <emyoulation@yahoo.com>
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
# Generated-by: Claude Sonnet 4.6 (Anthropic) via claude.ai

register(GRAMPLET,
    id                    = "PedigreeBreadcrumbs",
    name                  = _("Pedigree Breadcrumbs"),
    description           = _("Shows the relationship 'breadcrumb' path between"
                              " people in different generations."),
    status                = BETA,
    fname                 = "PedigreeBreadcrumbs.py",
    height                = 200,
    expand                = True,
    gramplet              = "PedigreeBreadcrumbs",
    gramplet_title        = _("Pedigree Breadcrumbs"),
    detached_width        = 620,
    detached_height       = 320,
    version               = "0.1.0",
    gramps_target_version = "5.2",
    include_in_listing    = True,
    authors               = ["Claude Sonnet 4.6 (Anthropic)"],
    authors_email         = ["claude.ai"],
    maintainers           = ["Brian McCullough"],
    maintainers_email     = ["emyoulation@yahoo.com"],
    help_url              = "https://gramps.discourse.group/t/3367/3",
)
