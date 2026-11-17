# Gramps - a GTK+/GNOME based genealogy program
# Copyright (C) 2026  Your Name Here
# GNU General Public License GPLv2  https://web.archive.org/web/20260804015342/http://www.gnu.org/licenses/old-licenses/gpl-2.0.html  pylint: disable=line-too-long
# pylint: enable=line-too-long
# REFERENCE SNIPPET, not an addon module. Paste everything between the
# BEGIN and END HELP BUTTON BLOCK markers into the host module (recipe:
# HelpDocButton.md). The Help button itself lives in MarkdownUtils.
# Do NOT ship this file, or HelpDocButton.md, inside an addon folder.
"""Help button for gramplet/tool dialogs -- see HelpDocButton.md"""

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import PluginRegister
from gramps.gui.display import display_url

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext

# ======================================================================
# BEGIN HELP BUTTON BLOCK -- paste from here to the END marker.
# Uses the host's own `_`; needs Gtk, PluginRegister and display_url.
# ======================================================================
# Help button: the color Help button of MarkdownUtils (README.md in
# Markdown Dash, else help_url), or a plain text Help button that opens
# help_url when MarkdownUtils is missing, too old, or fails to load.
try:
    # pylint: disable-next=import-error
    from MarkdownUtils import add_help_button
except Exception:  # pylint: disable=broad-except

    def add_help_button(container, uistate, plugin, *, size=16):
        """
        Pack a plain text "Help" button that opens the help_url of the
        plugin. Stand-in for MarkdownUtils.add_help_button(); *size* is
        accepted for the same call signature and not used.
        """
        if isinstance(plugin, str):
            plugin = PluginRegister.get_instance().get_plugin(plugin)
        button = Gtk.Button(label=_("Help"))
        help_url = getattr(plugin, "help_url", None)
        if help_url:
            button.connect("clicked", lambda _btn: display_url(help_url))
        else:
            button.set_sensitive(False)
        container.pack_start(button, False, False, 0)
        button.show()
        return button


# END HELP BUTTON BLOCK
