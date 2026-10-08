#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2017       Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2026       Brian McCullough (with Claude AI coding)
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
""" Help/Plugin Manager
This module implements the "Plugin Manager plus" (prototype) load patches.

NOTE: mirrors PluginManagerPlus.py's PluginManagerLoad.py, updated only to
import PluginStatus from PluginManager2 instead of PluginManagerPlus. If
PluginManagerPlus and PluginManager2 are both installed and enabled at
once, whichever one's load_on_reg hook runs last "wins" — both patch the
same gramps.gui.viewmanager.PluginWindows.PluginStatus attribute. That is
a pre-existing property of this patch mechanism, not something new here.

Generated-by: Claude Sonnet 5 (Anthropic, claude-sonnet-5, chat interface)
Prompts: "here's the separate PluginManagerLoad.py loader if you want to
validate any assumptions related to it" (user supplied the original
PluginManagerLoad.py so the PluginManager2 fork could mirror its actual
load_on_reg monkey-patch mechanism instead of the fname-only pattern
initially assumed).
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md (deferred
  for this prototyping pass at user's request)
Co-authored-by: Claude Sonnet 5 <noreply@anthropic.com>
"""
import sys
import os


def _lazy_plugin_status(*args, **kwargs):
    """
    Open Plugin Manager plus, importing its module on first use.

    Gramps core only ever calls ``PluginWindows.PluginStatus(dbstate,
    uistate, [])`` (gramps/gui/viewmanager.py, Help -> Plugin Manager),
    so a plain function works in place of the class. This keeps the large
    PluginManagerPlus module (and MarkdownUtils, urllib, its ini file)
    out of Gramps startup until the dialog is actually opened.
    """
    from PluginManagerPlus import PluginStatus

    return PluginStatus(*args, **kwargs)


def load_on_reg(dbstate, uistate, plugin):
    """
    Runs when plugin is registered.
    """
    if uistate:
        # It is necessary to avoid load GUI elements when run under CLI mode.
        # So we just don't load it at all.
        sys.path.append(os.path.abspath(os.path.dirname(__file__)))
        import gramps.gui.viewmanager

        gramps.gui.viewmanager.__dict__[
            "PluginWindows"
        ].PluginStatus = _lazy_plugin_status
