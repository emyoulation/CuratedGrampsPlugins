#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2019       Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2025       Paul Culley <paulr2787_at_gmail.com>
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
"""Themes addon – startup loader.

Runs when the plugin is registered (``load_on_reg = True``).  Responsible for:

* Monkey-patching :class:`gramps.gui.configure.GrampsPreferences` so that the
  Preferences dialog gains a **Theme** panel.
* Persisting / restoring GTK theme, font, dark-variant, and fixed-scrollbar
  preferences.
* Loading the three-layer CSS cascade at startup:

  1. User-selected CSS theme     (``PRIORITY_APPLICATION``)
  2. Enabled CSS patches         (``PRIORITY_APPLICATION``, in sorted order)
  3. Personal ``gramps_user.css``(``PRIORITY_USER`` – highest precedence)

* Version-guarding saved preferences: if the stored
  ``preferences.themes-version`` string does not match :data:`PREFS_VERSION`,
  all theme-related config keys are purged and recreated so that settings
  written by an older release cannot silently corrupt the new layout.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6), 2025-05-12.
Prompts: rewrite Gramps Themes addon for 5.2 following ThemesRewrite.odt,
add versioning to saved prefs, provide complete replacement source files.
Constraints: https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
"""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import logging

LOG = logging.getLogger(__name__)

# Minimal i18n at module level; full translation loaded in load_on_reg via
# glocale, but _() must be defined before any top-level code uses it.
try:
    from gramps.gen.const import GRAMPS_LOCALE as _glocale  # type: ignore[import]

    try:
        _ = _glocale.get_addon_translator(__file__).gettext
    except (ValueError, AttributeError):
        _ = _glocale.translation.gettext
except Exception:  # pylint: disable=broad-except
    _ = lambda s: s  # noqa: E731 – fallback when Gramps is not installed

# ---------------------------------------------------------------------------
# Version sentinel for saved-preferences compatibility.
# Increment this string whenever the set of config keys registered by this
# addon changes in a way that is not backward-compatible with older saves.
# ---------------------------------------------------------------------------
PREFS_VERSION: str = "1.0"

# Keys managed exclusively by this addon (used for version-mismatch purge).
_ADDON_CONFIG_KEYS: list[str] = [
    "preferences.themes-version",
    "preferences.theme",
    "preferences.theme-dark-variant",
    "preferences.font",
    "preferences.css-theme",
    "preferences.css-patches",
    "interface.toolbar-text",
    "interface.fixed-scrollbar",
]


# -------------------------------------------------------------------------
#
# _purge_addon_prefs
#
# -------------------------------------------------------------------------
def _purge_addon_prefs(config) -> None:  # type: ignore[type-arg]
    """Remove all addon-owned config keys from the live config store.

    :param config: The Gramps :class:`gramps.gen.config.Configuration` object.
    """
    for key in _ADDON_CONFIG_KEYS:
        try:
            config.set(key, config.get_default(key))
        except Exception:  # pylint: disable=broad-except
            # Key may not be registered yet on a first-ever run; ignore.
            pass


# -------------------------------------------------------------------------
#
# _register_config_keys
#
# -------------------------------------------------------------------------
def _register_config_keys(config) -> None:  # type: ignore[type-arg]
    """Register all addon config keys with their default values.

    Safe to call multiple times (Gramps ignores re-registration of an already
    known key).

    :param config: The Gramps :class:`gramps.gen.config.Configuration` object.
    """
    config.register("preferences.themes-version", "")
    config.register("preferences.theme", "")
    config.register("preferences.theme-dark-variant", "")
    config.register("preferences.font", "")
    config.register("preferences.css-theme", "")
    config.register("preferences.css-patches", "")
    config.register("interface.toolbar-text", False)
    config.register("interface.fixed-scrollbar", "")


# -------------------------------------------------------------------------
#
# _load_css_provider
#
# -------------------------------------------------------------------------
def _load_css_provider(path: str, screen, priority: int) -> bool:
    """Load a CSS file and attach it to *screen* at *priority*.

    :param path: Absolute path to a ``.css`` file.
    :param screen: A :class:`Gdk.Screen` object.
    :param priority: GTK style-provider priority constant.
    :returns: ``True`` if the file was loaded successfully, ``False``
        otherwise.
    """
    from gi.repository import Gtk  # pylint: disable=import-outside-toplevel

    if not os.path.isfile(path):
        LOG.warning(_("CSS file not found: %s"), path)
        return False
    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(path)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, priority)
        LOG.debug(_("Loaded CSS: %s (priority %d)"), path, priority)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warning(_("Failed to load CSS '%s': %s"), path, exc)
        return False


# -------------------------------------------------------------------------
#
# load_on_reg
#
# -------------------------------------------------------------------------
def load_on_reg(dbstate, uistate, plugin) -> None:
    """Run when the plugin is registered.

    :param dbstate: The Gramps database-state object (may be ``None``).
    :param uistate: The Gramps UI-state object; ``None`` under CLI.
    :param plugin: The plugin descriptor object (unused).
    """
    if not uistate:
        # Do not import any GUI elements when running under CLI.
        return

    # ------------------------------------------------------------------ imports
    from gi.repository import Gtk  # pylint: disable=import-outside-toplevel
    from gi.repository.Gdk import Screen  # pylint: disable=import-outside-toplevel
    from gramps.gen.config import config  # pylint: disable=import-outside-toplevel
    from gramps.gen.const import USER_CSS  # pylint: disable=import-outside-toplevel
    from gramps.gui.configure import GrampsPreferences  # pylint: disable=import-outside-toplevel

    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    from themes import MyPrefs  # pylint: disable=import-outside-toplevel,import-error

    # -------------------------------------------------------- version sentinel
    _register_config_keys(config)
    stored_version = config.get("preferences.themes-version")
    if stored_version != PREFS_VERSION:
        LOG.info(
            _(
                "Themes addon: prefs version mismatch "
                "(stored '%s', expected '%s') – purging old settings."
            ),
            stored_version,
            PREFS_VERSION,
        )
        _purge_addon_prefs(config)
        _register_config_keys(config)
        config.set("preferences.themes-version", PREFS_VERSION)

    # --------------------------------------------------- monkey-patch Prefs UI
    GrampsPreferences.__init__ = MyPrefs.__init__

    # ------------------------------------------ save GTK defaults for 'Reset'
    gtksettings = Gtk.Settings.get_default()
    if not hasattr(GrampsPreferences, "def_dark"):
        GrampsPreferences.def_dark = gtksettings.get_property(
            "gtk-application-prefer-dark-theme"
        )
        GrampsPreferences.def_theme = gtksettings.get_property("gtk-theme-name")
        GrampsPreferences.def_font = gtksettings.get_property("gtk-font-name")

    # --------------------------------------------- restore GTK theme prefs
    value = config.get("preferences.theme-dark-variant")
    if value:
        gtksettings.set_property(
            "gtk-application-prefer-dark-theme", value == "True"
        )

    value = config.get("preferences.theme")
    if value:
        gtksettings.set_property("gtk-theme-name", value)

    value = config.get("preferences.font")
    if value:
        gtksettings.set_property("gtk-font-name", value)

    # ----------------------------------------- restore toolbar-text pref
    value = config.get("interface.toolbar-text")
    toolbar = uistate.uimanager.get_widget("ToolBar")
    if toolbar is not None:
        toolbar.set_style(
            Gtk.ToolbarStyle.BOTH if value else Gtk.ToolbarStyle.ICONS
        )

    # ----------------------------------------- restore fixed-scrollbar pref
    value = config.get("interface.fixed-scrollbar")
    if value and value not in ("", "False", "0"):
        from gi.repository.Gdk import Screen as _Screen  # pylint: disable=import-outside-toplevel

        gtksettings.set_property("gtk-primary-button-warps-slider", False)
        MyPrefs.provider = Gtk.CssProvider()
        css = (
            "* { -GtkScrollbar-has-backward-stepper: 1; "
            "-GtkScrollbar-has-forward-stepper: 1; }"
        )
        MyPrefs.provider.load_from_data(css.encode("utf8"))
        Gtk.StyleContext.add_provider_for_screen(
            _Screen.get_default(),
            MyPrefs.provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # ----------------------------------------------- load CSS cascade layer 1
    # CSS Theme (single selection, APPLICATION priority)
    screen = Screen.get_default()
    active_css_theme = config.get("preferences.css-theme")
    if active_css_theme:
        theme_path = os.path.join(USER_CSS, "themes", active_css_theme + ".css")
        _load_css_provider(theme_path, screen, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ----------------------------------------------- load CSS cascade layer 2
    # CSS Patches (multiple, sorted, APPLICATION priority)
    patches_str = config.get("preferences.css-patches")
    if patches_str:
        for patch_name in [p.strip() for p in patches_str.split(",") if p.strip()]:
            patch_path = os.path.join(USER_CSS, "patches", patch_name + ".css")
            _load_css_provider(
                patch_path, screen, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    # ----------------------------------------------- load CSS cascade layer 3
    # gramps_user.css personal override (USER priority – always wins)
    user_css = os.path.join(USER_CSS, "gramps_user.css")
    if os.path.isfile(user_css):
        _load_css_provider(user_css, screen, Gtk.STYLE_PROVIDER_PRIORITY_USER)
