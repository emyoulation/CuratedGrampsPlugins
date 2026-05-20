#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Gramps - a GTK+/GNOME based genealogy program
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

"""
Gramps plugin registration for Markdown Dash gramplet

Author: Brian McCullough
Development: AI-assisted using Claude (Anthropic)
Date: February 2026
"""
from gramps.version import major_version, VERSION_TUPLE

#------------------------------------------------------------------------
# requires_gi declares GObject-Introspection namespaces this plugin needs.
# Plugin Manager will warn the user if they are absent.
#------------------------------------------------------------------------
if VERSION_TUPLE >= (5, 2, 0):
    register(
        GRAMPLET,
        id = "markdowndash",
        name = _("Markdown Dash"),
        description = "Dashboard gramplet to view formatted Markdown (.md) files",
        version = '1.0.0',
        gramps_target_version = major_version,
        status = BETA,
        fname = "MarkdownDash.py",
        height = 400,
        gramplet = 'MarkdownDash',
        gramplet_title = _("Markdown Dash"),
        help_url = "https://gramps.discourse.group/t/9158",
        authors = ["Claude AI"],
        authors_email = [""],
        maintainers = ["Brian McCullough"],
        maintainers_email = ["emyoulation@yahoo.com"],
        navtypes    = ["Dashboard"],
        requires_gi = [("Gtk",      "3.0"),
                    ("Gdk",      "3.0"),
                    ("GdkPixbuf","2.0"),
                    ("Pango",    "1.0")],
    )
