# Gramps - a GTK+/GNOME based genealogy program
# Copyright (C) 2026  Your Name Here
# GNU General Public License GPLv2  https://web.archive.org/web/20260804015342/http://www.gnu.org/licenses/old-licenses/gpl-2.0.html  pylint: disable=line-too-long
# pylint: enable=line-too-long
# REFERENCE SNIPPET, not an addon module. Paste everything between the
# BEGIN and END HELP BUTTON BLOCK markers into the host module (recipe:
# HelpDocButton.md).
# Do NOT ship this file, or HelpDocButton.md, inside an addon folder.
"""Color "Help" button for gramplet/tool dialogs -- see HelpDocButton.md"""

# ------------------------
# Python modules
# ------------------------
import logging
import os
from collections.abc import Callable
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

# ======================================================================
# BEGIN HELP BUTTON BLOCK -- paste from here to the END marker.
# If the host module already defines `_` and LOG, delete the translator
# and LOG lines just below and use the host's.
# ======================================================================
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext

LOG = logging.getLogger(".gui.plug")

_MARKDOWNDASH_ID = "markdowndash"
_HELP_ICON_NAME = "help-browser"


def resolve_help_icon(size: int = 16) -> Gtk.Image:
    """
    Return a Gtk.Image of the full-color help-browser icon.

    :param size: icon size in pixels (square).
    :returns: the image; empty (with a logged warning) if the theme has
        no such icon at that size.
    """
    theme = Gtk.IconTheme.get_default()
    flags = (
        Gtk.IconLookupFlags.FORCE_REGULAR  # color, not the symbolic variant
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE  # exactly `size`, not nearest
    )
    info = theme.lookup_icon(_HELP_ICON_NAME, size, flags)
    image = Gtk.Image()
    if info is not None:
        image.set_from_pixbuf(info.load_icon())
    else:
        # Deliberately no new_from_icon_name() fallback: that is the
        # unreliable variant/size lookup this function exists to avoid.
        LOG.warning(
            "resolve_help_icon: theme has no '%s' icon at size %d",
            _HELP_ICON_NAME,
            size,
        )
    return image


def find_local_readme(pdata: PluginData | None) -> str | None:
    """
    Return the canonical README.md path of the plugin, or None if the
    plugin has no README of any kind.

    "Any kind" is decided by ``MarkdownUtils.resolve_localized_path()``:
    ``README.md``, a source-language ``README_<lang>.md``, or a
    ``locale/<lang>/README.md`` translation. The returned path need not
    exist on disk; Markdown Dash resolves it to the best variant for the
    user's language, falling back to the English baseline. If
    MarkdownUtils cannot be imported, only a literal ``README.md`` counts.

    :param pdata: the plugin's PluginData; None is tolerated.
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # Imported here, not at module level: MarkdownUtils belongs to the
        # optional Markdown Dash add-on and is only importable once that
        # add-on has been loaded (see cb_show_help()).
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener() -> Callable[..., Gtk.Dialog] | None:
    """
    Return Markdown Dash's open_markdown_file(), or None.

    None means Markdown Dash is deactivated, not registered, fails to
    load, or lacks that function -- callers treat all four the same way
    (fall back to help_url).
    """
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


def open_help_url(pdata: PluginData | None, parent: Gtk.Window | None) -> None:
    """
    Open the plugin's registered help_url in the default browser.

    A bare wiki page title is resolved against gramps-project.org; a full
    http(s) URL is used as-is.

    :param pdata: the plugin's PluginData.
    :param parent: transient parent for the "no documentation" notice.
    """
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
        LOG.exception("help button: could not open help_url: %s", full_url)


def cb_show_help(_button: Gtk.Button, uistate, pdata: PluginData | None) -> None:
    """
    Show the best documentation available: the plugin's own README.md in
    a Markdown Dash window if possible, else its help_url in a browser.

    :param uistate: the Gramps UiState (its main window parents the reader).
    :param pdata: the calling plugin's own PluginData.
    """
    # Load Markdown Dash first: that makes its MarkdownUtils importable,
    # which find_local_readme() then uses to recognize translated READMEs.
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None:
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
    plugin: PluginData | str | None,
    *,
    size: int = 16,
) -> Gtk.Button:
    """
    Pack a color "Help" button (icon plus visible label) into container.

    :param container: the Gtk.Box to pack into -- a gramplet's button row,
        or a dialog's action area.
    :param uistate: the Gramps UiState.
    :param plugin: the calling plugin's own registered id (the id= in its
        .gpr.py), or its PluginData.
    :param size: icon size in pixels; the default suits a row of ordinary
        text buttons.
    :returns: the created, already-packed button.
    """
    if isinstance(plugin, str):
        plugin_id = plugin
        plugin = PluginRegister.get_instance().get_plugin(plugin_id)
        if plugin is None:
            LOG.warning("add_help_button: no registered plugin '%s'", plugin_id)
    button = Gtk.Button()
    button.set_image(resolve_help_icon(size))
    button.set_always_show_image(True)  # else some themes hide the icon
    button.set_label(_("Help"))
    # Tooltip on the button: a Gtk.Image inside a button never shows its own.
    button.set_tooltip_text(_("Show documentation for this plugin"))
    button.connect("clicked", cb_show_help, uistate, plugin)
    container.pack_start(button, False, False, 0)
    button.show_all()
    return button


# END HELP BUTTON BLOCK
