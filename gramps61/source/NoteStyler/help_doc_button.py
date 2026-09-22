# Gramps - a GTK+/GNOME based genealogy program
# Copyright (C) 2026  Your Name Here
# GNU General Public License GPLv2  https://web.archive.org/web/20260804015342/http://www.gnu.org/licenses/old-licenses/gpl-2.0.html  pylint: disable=line-too-long
# pylint: enable=line-too-long
# BEFORE MERGING into a host module: read HelpDocButton.md#integration-checklist
# TEMPLATE SHORTCUT: the short header above and the pointer-only docstrings
# below are NOT the normal Gramps convention (see AGENTS.md) -- they are
# deliberate, one-off exceptions for this snippet only. Do not copy this
# header/docstring style into a new standalone module; see the checklist.
"""Color "Help" button for gramplet/report/tool dialogs -- see HelpDocButton.md"""

# ------------------------
# Python modules
# ------------------------
import logging
import os
from typing import Callable
from urllib.parse import quote

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gio, GLib, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import PluginRegister
from gramps.gen.plug._pluginreg import PluginData
from gramps.gui.dialog import OkDialog
from gramps.gui.pluginmanager import GuiPluginManager

# ------------------------
# Gramps specific
# ------------------------
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext

LOG = logging.getLogger(".gui.plug")

# see HelpDocButton.md#constants -- also see HelpDocButton.md's note on
# Markdown Dash potentially merging into Gramps core (6.2/7.0)
_MARKDOWNDASH_ID = "markdowndash"
_HELP_ICON_NAME = "help-browser"


def resolve_help_icon(size: int = 48) -> Gtk.Image:
    """resolve_help_icon -- see HelpDocButton.md#resolve_help_icon-parameters"""
    theme = Gtk.IconTheme.get_default()
    flags = (
        Gtk.IconLookupFlags.FORCE_REGULAR
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE
    )
    info = theme.lookup_icon(_HELP_ICON_NAME, size, flags)
    image = Gtk.Image()
    if info is not None:
        image.set_from_pixbuf(info.load_icon())
    else:
        # No fallback via new_from_icon_name()/set_from_icon_name() here --
        # that is exactly the unreliable color/symbolic-variant lookup this
        # function exists to avoid (see HelpDocButton.md), and it would also
        # ignore `size`. An icon-less Gtk.Image is a visibly missing icon,
        # which is easier to notice and fix (install/complete the icon
        # theme) than a silently wrong-variant or wrong-size one.
        LOG.warning(
            "resolve_help_icon: theme has no '%s' icon at size %d",
            _HELP_ICON_NAME,
            size,
        )
    return image


def find_local_readme(pdata: PluginData | None) -> str | None:
    """find_local_readme -- see HelpDocButton.md#find_local_readme-parameters"""
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    return readme_path if os.path.isfile(readme_path) else None


def resolve_markdown_dash_opener() -> Callable[..., Gtk.Dialog] | None:
    """resolve_markdown_dash_opener --
    see HelpDocButton.md#resolve_markdown_dash_opener-parameters"""
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        return None
    return getattr(mod, "open_markdown_file", None)


def open_help_url(pdata: PluginData, parent: Gtk.Window | None) -> None:
    """open_help_url -- see HelpDocButton.md#open_help_url-parameters"""
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered help_url."),
            parent=parent,
        )
        return
    full_url = (
        help_url
        if help_url.startswith(("http://", "https://"))
        else "https://gramps-project.org/wiki/index.php?title="
        + quote(help_url, safe=":")
    )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("help_doc_button: could not open help_url: %s", full_url)


def cb_show_help(_button: Gtk.Button, uistate, pdata: PluginData) -> None:
    """cb_show_help -- see HelpDocButton.md#cb_show_help-parameters"""
    readme_path = find_local_readme(pdata)
    if readme_path is not None:
        open_markdown_file = resolve_markdown_dash_opener()
        if open_markdown_file is not None:
            open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            return
    open_help_url(pdata, uistate.window)


def add_help_button(
    container: Gtk.Box,
    uistate,
    pdata: PluginData,
    *,
    size: int = 48,
) -> Gtk.Button:
    """add_help_button -- see HelpDocButton.md#add_help_button-parameters"""
    button = Gtk.Button()
    button.set_image(resolve_help_icon(size))
    button.set_always_show_image(True)
    button.set_label(_("Help"))
    button.set_tooltip_text(_("Show documentation for this plugin"))
    button.connect("clicked", cb_show_help, uistate, pdata)
    container.pack_start(button, False, False, 0)
    button.show_all()
    return button
