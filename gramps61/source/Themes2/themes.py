#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2019, 2025 Paul Culley <paulr2787_at_gmail.com>
# Copyright (C) 2026       Brian McCullough (Gemini AI coding) <emyoulation_at_yahoo.com>
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
"""Themes addon - Preferences panel.

Defines :class:`MyPrefs`, which is monkey-patched over
:class:`gramps.gui.configure.GrampsPreferences` by ``themes_load.py`` so that
the Preferences dialog gains a **Theme** tab.

The tab provides:

* GTK theme selector (combo)
* Dark-variant toggle
* Font selector
* Collapsible CSS section (CSS Theme selector, Patches, User override)
* Toolbar-text toggle
* Fixed-scrollbar toggle (Windows only)
* Restore-to-defaults button (resets GTK Theme, Dark Variant, Font, and CSS)

CSS cascade order (lowest to highest priority):

1. ``gramps.css``      (loaded by ViewManager, APPLICATION priority)
2. CSS Theme           (APPLICATION priority)
3. CSS Patches         (APPLICATION priority, sorted order)
4. ``gramps_user.css`` (USER priority - always wins)

Bug fixes applied in this revision
-----------------------------------
* **Status label refresh** - ``self._user_css_status`` is now a stored
  attribute so :meth:`cb_open_user_css` can update it live after creating
  ``gramps_user.css``.
* **Dark-variant string/bool** - ``preferences.theme-dark-variant`` is stored
  as ``"True"`` or ``"False"``.
* **Live GTK Theme Switching** - Instant application of GTK themes via active
  ``Gtk.Settings`` without requiring a Gramps restart.
* **OS Font Restoration** - Restores systemic OS default font family and size
  upon clicking "Restore to defaults" and immediately updates the FontButton widget.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6), 2025-05-12.
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
Modified-by: Gemini 2.5 (Google), 2026-08-14.
Prompts: Restore OS default font family and size on "Restore to defaults" with live FontButton synchronization.
Co-authored-by: Gemini 2.5 <gemini@google.com>
"""

# ------------------------------------------------------------------------
# Python modules
# ------------------------------------------------------------------------
import configparser
import glob
import logging
import os
import subprocess
import types

# ------------------------------------------------------------------------
# GNOME / GTK modules
# ------------------------------------------------------------------------
from gi.repository import Gio, GLib, Gtk, Pango
from gi.repository.Gdk import Screen
from gi.repository.GObject import BindingFlags

# ------------------------------------------------------------------------
# Gramps modules
# ------------------------------------------------------------------------
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import USER_CSS, DATA_DIR
from gramps.gen.constfunc import win
from gramps.gen.utils.alive import update_constants
from gramps.gui.configure import (
    WIKI_HELP_PAGE,
    WIKI_HELP_SEC,
    ConfigureDialog,
    GrampsPreferences,
)
from gramps.gui.display import display_help

# ------------------------------------------------------------------------
# Gramps specific
# ------------------------------------------------------------------------
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger(__name__)

# Path to isolated themes.ini file inside the addon directory
INI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes.ini")


class ThemeConfig:
    """Helper to read and write key/value pairs to themes.ini."""

    def __init__(self, ini_path: str) -> None:
        self.path = ini_path
        self.parser = configparser.ConfigParser()
        self.load()

    def load(self) -> None:
        """Load the ini file if it exists, ensuring [theme] section present."""
        if os.path.exists(self.path):
            try:
                self.parser.read(self.path, encoding="utf-8")
            except Exception as exc:
                LOG.warning(_("Failed to read themes.ini: %s"), exc)

        if not self.parser.has_section("theme"):
            self.parser.add_section("theme")

    def get(self, key: str, default: str = "") -> str:
        """Get a value from the [theme] section."""
        return self.parser.get("theme", key, fallback=default)

    def set(self, key: str, value: str) -> None:
        """Set a value in the [theme] section and save immediately."""
        self.parser.set("theme", key, str(value))
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                self.parser.write(fh)
        except Exception as exc:
            LOG.warning(_("Failed to write themes.ini: %s"), exc)


theme_config = ThemeConfig(INI_PATH)

_USER_CSS_TEMPLATE = """\
/* Gramps User CSS Override
 *
 * This file is loaded LAST at PRIORITY_USER (800), which is higher than any
 * APPLICATION priority style. Your rules here always win.
 */

"""

def _load_css_provider(path: str, screen: Screen, priority: int) -> bool:
    """Load *path* as a CSS provider and attach it to *screen* at *priority*."""
    if not os.path.isfile(path):
        LOG.warning(_("CSS file not found: %s"), path)
        return False
    try:
        provider = Gtk.CssProvider()
        provider.load_from_path(path)
        Gtk.StyleContext.add_provider_for_screen(screen, provider, priority)
        LOG.debug(_("Loaded CSS '%s' at priority %d"), path, priority)
        return True
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warning(_("Failed to load CSS '%s': %s"), path, exc)
        return False


class MyPrefs(GrampsPreferences):
    """Enhanced Preferences dialog with GTK-theme and CSS-theming controls."""

    def __init__(self, uistate, dbstate) -> None:
        """Initialize the preferences window and bind theme methods."""
        for name in (
            "add_themes_panel",
            "gtk_css",
            "theme_changed",
            "cb_dark_variant_changed",
            "cb_theme_combo_changed",
            "cb_css_theme_changed",
            "cb_patch_toggled",
            "cb_font_changed",
            "font_filter",
            "cb_default_clicked",
            "cb_scroll_changed",
            "cb_toolbar_text_changed",
            "cb_open_user_css",
            "cb_open_css_folder",
            "cb_cascade_link_activated",
            "_scan_css_dir",
            "_reload_css_cascade",
            "_refresh_user_css_status",
        ):
            setattr(self, name, types.MethodType(getattr(MyPrefs, name), self))

        base_panels = [
            self.add_data_panel,
            self.add_general_panel,
            self.add_famtree_panel,
            self.add_import_panel,
            self.add_limits_panel,
            self.add_color_panel,
            self.add_symbols_panel,
            self.add_idformats_panel,
            self.add_text_panel,
            self.add_warnings_panel,
            self.add_researcher_panel,
        ]
        if hasattr(self, "add_ptypes_panel"):
            base_panels.append(self.add_ptypes_panel)
        base_panels.append(self.add_themes_panel)
        page_funcs = tuple(base_panels)

        base_on_close = self._close if hasattr(self, "_close") else update_constants

        ConfigureDialog.__init__(
            self,
            uistate,
            dbstate,
            page_funcs,
            GrampsPreferences,
            config,
            on_close=base_on_close,
        )

        help_btn = self.window.add_button(_("_Help"), Gtk.ResponseType.HELP)
        help_btn.connect(
            "clicked", lambda x: display_help(WIKI_HELP_PAGE, WIKI_HELP_SEC)
        )
        self.setup_configs("interface.grampspreferences", 700, 500)

    def add_themes_panel(self, configdialog) -> tuple[str, Gtk.Grid]:
        """Build and populate the **Theme** tab layout in Preferences."""
        grid = Gtk.Grid()
        grid.set_border_width(12)
        grid.set_column_spacing(6)
        grid.set_row_spacing(6)
        row = 0

        self.gtksettings = Gtk.Settings.get_default()

        # Capture systemic OS default GTK properties
        self.def_theme = "Adwaita"
        self.def_dark = False
        self.def_font = self.gtksettings.get_property("gtk-font-name") if self.gtksettings else ""
        self.font_binding = None

        lbl = Gtk.Label()
        lbl.set_markup("<b>{}</b>".format(_("GTK Theme")))
        lbl.set_halign(Gtk.Align.START)
        grid.attach(lbl, 0, row, 3, 1)
        row += 1

        self.theme = Gtk.ComboBoxText()
        self.t_names: set[str] = set()

        try:
            themes = Gio.resources_enumerate_children("/org/gtk/libgtk/theme", 0)
            for theme in themes:
                if theme.endswith("/"):
                    self.t_names.add(theme[:-1])
                elif theme.startswith(("HighContrast", "Raleigh", "gtk-win32")):
                    self.t_names.add(theme.replace(".css", ""))
        except Exception:
            pass

        self.gtk_css(os.path.join(GLib.get_home_dir(), ".themes"))
        self.gtk_css(os.path.join(GLib.get_user_data_dir(), "themes"))
        for sysdir in GLib.get_system_data_dirs():
            self.gtk_css(os.path.join(sysdir, "themes"))

        c_theme = theme_config.get("theme", self.def_theme)

        for indx, theme in enumerate(sorted(self.t_names)):
            self.theme.append_text(theme)
            if theme == c_theme:
                self.theme.set_active(indx)

        if os.environ.get("GTK_THEME"):
            self.theme.set_sensitive(False)
            self.theme.set_tooltip_text(_("Theme is hardcoded by GTK_THEME"))
        else:
            self.theme.connect("changed", self.cb_theme_combo_changed)

        lwidget = Gtk.Label(label=(_("%s: ") % _("Theme")))
        lwidget.set_halign(Gtk.Align.END)
        grid.attach(lwidget, 0, row, 1, 1)
        grid.attach(self.theme, 1, row, 1, 1)
        row += 1

        self.dark = Gtk.CheckButton(label=_("Dark Variant"))
        dark_val = theme_config.get("dark-variant", "False") == "True"
        self.dark.set_active(dark_val)
        self.dark.connect("toggled", self.cb_dark_variant_changed)
        if os.environ.get("GTK_THEME"):
            self.dark.set_sensitive(False)
            self.dark.set_tooltip_text(_("Theme is hardcoded by GTK_THEME"))
        grid.attach(self.dark, 1, row, 2, 1)
        row += 1

        self.font_button = Gtk.FontButton(show_style=False)
        self.font_button.set_filter_func(self.font_filter, None)
        saved_font = theme_config.get("font", "")
        if saved_font:
            self.font_button.set_font_name(saved_font)
        else:
            self.font_binding = self.gtksettings.bind_property(
                "gtk-font-name",
                self.font_button,
                "font-name",
                BindingFlags.BIDIRECTIONAL | BindingFlags.SYNC_CREATE,
            )
        self.font_button.connect("font-set", self.cb_font_changed)
        lwidget = Gtk.Label(label=_("%s: ") % _("Font"))
        lwidget.set_halign(Gtk.Align.END)
        grid.attach(lwidget, 0, row, 1, 1)
        grid.attach(self.font_button, 1, row, 2, 1)
        row += 1

        t_text = Gtk.CheckButton.new_with_mnemonic(
            _("_Toolbar") + " " + _("Text")
        )
        t_text.set_active(config.get("interface.toolbar-text"))
        t_text.connect("toggled", self.cb_toolbar_text_changed)
        grid.attach(t_text, 1, row, 2, 1)
        row += 1

        if win():
            self.sc_text = Gtk.CheckButton.new_with_mnemonic(
                _("Fixed Scrollbar (requires restart)")
            )
            sc_val = config.get("interface.fixed-scrollbar")
            self.sc_text.set_active(
                bool(sc_val) and sc_val not in ("False", "0", "")
            )
            self.sc_text.connect("toggled", self.cb_scroll_changed)
            grid.attach(self.sc_text, 1, row, 2, 1)
            row += 1

        row += 1

        css_expander = Gtk.Expander()
        css_expander.set_use_markup(True)
        css_expander.set_label("<b>{}</b>".format(_("CSS Theming")))
        css_expander.set_expanded(False)

        css_grid = Gtk.Grid()
        css_grid.set_column_spacing(6)
        css_grid.set_row_spacing(6)
        css_grid.set_margin_top(6)
        css_row = 0

        hint = Gtk.Label()
        hint.set_markup(
            _(
                "CSS cascade order (lowest to highest priority):\n"
                '  1. <a href="{path1}">gramps.css</a> (core)   '
                '2. <a href="{path2}">CSS Theme</a>   '
                '3. <a href="{path3}">CSS Patches</a>   '
                '4. <a href="{path4}">gramps_user.css</a>'
            ).format(
                path1=DATA_DIR,
                path2=os.path.join(USER_CSS, "themes"),
                path3=os.path.join(USER_CSS, "patches"),
                path4=USER_CSS,
            )
        )
        hint.set_halign(Gtk.Align.START)
        hint.set_line_wrap(True)
        hint.connect("activate-link", self.cb_cascade_link_activated)
        css_grid.attach(hint, 0, css_row, 3, 1)
        css_row += 1

        self.css_combo = Gtk.ComboBoxText()
        self.css_combo.append("", _("None (use Gramps default)"))
        self.css_themes: dict[str, str] = self._scan_css_dir(
            os.path.join(USER_CSS, "themes")
        )
        for name in sorted(self.css_themes):
            self.css_combo.append(name, name)
        active_css = theme_config.get("css-theme", "")
        if active_css and active_css in self.css_themes:
            self.css_combo.set_active_id(active_css)
        else:
            self.css_combo.set_active(0)
        self.css_combo.connect("changed", self.cb_css_theme_changed)

        lwidget = Gtk.Label(label=_("%s: ") % _("CSS Theme"))
        lwidget.set_halign(Gtk.Align.END)
        css_grid.attach(lwidget, 0, css_row, 1, 1)
        css_grid.attach(self.css_combo, 1, css_row, 2, 1)
        css_row += 1

        lbl3 = Gtk.Label(label=_("CSS Patches:"))
        lbl3.set_halign(Gtk.Align.END)
        lbl3.set_valign(Gtk.Align.START)
        css_grid.attach(lbl3, 0, css_row, 1, 1)

        self.css_patches: dict[str, str] = self._scan_css_dir(
            os.path.join(USER_CSS, "patches")
        )
        self.patch_checks: dict[str, Gtk.CheckButton] = {}

        patches_str = theme_config.get("css-patches", "")
        enabled_set: set[str] = (
            {p.strip() for p in patches_str.split(",") if p.strip()}
            if patches_str
            else set()
        )

        patches_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        if self.css_patches:
            for patch_name in sorted(self.css_patches):
                chk = Gtk.CheckButton(label=patch_name)
                chk.set_active(patch_name in enabled_set)
                chk.connect(
                    "toggled",
                    lambda w, pn=patch_name: self.cb_patch_toggled(pn, w),
                )
                self.patch_checks[patch_name] = chk
                patches_box.pack_start(chk, False, False, 0)
        else:
            no_patch_lbl = Gtk.Label(
                label=(
                    _("No patches found.\nPlace .css files in:\n%s")
                    % os.path.join(USER_CSS, "patches")
                )
            )
            no_patch_lbl.set_halign(Gtk.Align.START)
            no_patch_lbl.set_line_wrap(True)
            patches_box.pack_start(no_patch_lbl, False, False, 0)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(90)
        sw.add(patches_box)
        frame = Gtk.Frame()
        frame.add(sw)
        css_grid.attach(frame, 1, css_row, 2, 1)
        css_row += 1

        lbl4 = Gtk.Label()
        lbl4.set_markup("<b>{}</b>".format(_("User CSS Override")))
        lbl4.set_halign(Gtk.Align.START)
        css_grid.attach(lbl4, 0, css_row, 3, 1)
        css_row += 1

        user_css_path = os.path.join(USER_CSS, "gramps_user.css")
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        path_entry = Gtk.Entry()
        path_entry.set_text(user_css_path)
        path_entry.set_editable(False)
        path_box.pack_start(path_entry, True, True, 0)

        edit_btn = Gtk.Button()
        edit_btn.set_image(
            Gtk.Image.new_from_icon_name("text-editor", Gtk.IconSize.SMALL_TOOLBAR)
        )
        edit_btn.set_relief(Gtk.ReliefStyle.NONE)
        edit_btn.set_tooltip_text(_("Edit gramps_user.css in default text editor"))
        edit_btn.connect("clicked", self.cb_open_user_css)
        path_box.pack_start(edit_btn, False, False, 0)

        folder_btn = Gtk.Button()
        folder_btn.set_image(
            Gtk.Image.new_from_icon_name("document-open", Gtk.IconSize.SMALL_TOOLBAR)
        )
        folder_btn.set_relief(Gtk.ReliefStyle.NONE)
        folder_btn.set_tooltip_text(_("Open CSS folder in file manager"))
        folder_btn.connect("clicked", self.cb_open_css_folder)
        path_box.pack_start(folder_btn, False, False, 0)

        css_grid.attach(path_box, 0, css_row, 3, 1)
        css_row += 1

        self._user_css_status = Gtk.Label()
        self._user_css_status.set_halign(Gtk.Align.START)
        self._refresh_user_css_status()
        css_grid.attach(self._user_css_status, 0, css_row, 3, 1)

        css_expander.add(css_grid)
        grid.attach(css_expander, 0, row, 3, 1)
        row += 1

        row += 1

        button = Gtk.Button(label=_("Restore to defaults"))
        button.connect("clicked", self.cb_default_clicked)
        grid.attach(button, 0, row, 2, 1)

        return _("Theme"), grid

    def _refresh_user_css_status(self) -> None:
        """Update the label showing whether ``gramps_user.css`` exists."""
        user_css_path = os.path.join(USER_CSS, "gramps_user.css")
        if os.path.isfile(user_css_path):
            self._user_css_status.set_markup(
                "<span foreground='green'>{}</span>".format(
                    _("\u2713 gramps_user.css is present and active")
                )
            )
        else:
            self._user_css_status.set_text(_("(gramps_user.css not yet created)"))

    def _scan_css_dir(self, directory: str) -> dict[str, str]:
        """Scan *directory* for ``.css`` files and return ``{stem: path}``."""
        result: dict[str, str] = {}
        if not os.path.isdir(directory):
            return result
        for fname in os.listdir(directory):
            if fname.endswith(".css"):
                result[fname[:-4]] = os.path.join(directory, fname)
        return result

    def gtk_css(self, directory: str) -> None:
        """Scan a directory tree for GTK themes and add them to ``t_names``."""
        if not os.path.isdir(directory):
            return
        for entry in glob.glob(os.path.join(directory, "*", "gtk-3.*", "gtk.css")):
            self.t_names.add(entry.replace("\\", "/").split("/")[-3])

    def _reload_css_cascade(self) -> None:
        """Re-apply active CSS provider layers to the default screen."""
        screen = Screen.get_default()
        if screen is None:
            return

        active = theme_config.get("css-theme", "")
        if active and active in self.css_themes:
            _load_css_provider(
                self.css_themes[active], screen, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        patches_str = theme_config.get("css-patches", "")
        if patches_str:
            for pname in [p.strip() for p in patches_str.split(",") if p.strip()]:
                if pname in self.css_patches:
                    _load_css_provider(
                        self.css_patches[pname],
                        screen,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                    )

        user_css = os.path.join(USER_CSS, "gramps_user.css")
        if os.path.isfile(user_css):
            _load_css_provider(user_css, screen, Gtk.STYLE_PROVIDER_PRIORITY_USER)

    def cb_cascade_link_activated(self, label: Gtk.Label, uri: str) -> bool:
        """Handle link clicks in the cascade hint label by opening the folder."""
        os.makedirs(uri, exist_ok=True)
        try:
            app = Gio.app_info_get_default_for_type("inode/directory", False)
            if app:
                app.launch_uris(["file://" + uri])
            else:
                LOG.warning(_("No default file manager found"))
        except Exception as exc:
            LOG.warning(_("Could not open folder '%s': %s"), uri, exc)
        return True

    def cb_theme_combo_changed(self, obj: Gtk.ComboBoxText) -> None:
        """Apply selected GTK theme dynamically without requiring a restart."""
        value = obj.get_active_text()
        if value:
            settings = Gtk.Settings.get_default()
            if settings:
                settings.set_property("gtk-theme-name", value)
            theme_config.set("theme", value)

    def theme_changed(self, obj: Gtk.ComboBoxText) -> None:
        """Legacy alias for :meth:`cb_theme_combo_changed`."""
        self.cb_theme_combo_changed(obj)

    def cb_dark_variant_changed(self, obj: Gtk.CheckButton) -> None:
        """Apply dark-variant setting dynamically and update configuration."""
        value = obj.get_active()
        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", value)
        theme_config.set("dark-variant", "True" if value else "False")

    def cb_css_theme_changed(self, obj: Gtk.ComboBoxText) -> None:
        """Apply selected CSS theme and reload cascade."""
        active_id = obj.get_active_id() or ""
        theme_config.set("css-theme", active_id)
        self._reload_css_cascade()

    def cb_patch_toggled(self, patch_name: str, widget: Gtk.CheckButton) -> None:
        """Save enabled CSS patches and reload cascade."""
        enabled = [
            name
            for name in sorted(self.css_patches)
            if self.patch_checks[name].get_active()
        ]
        theme_config.set("css-patches", ",".join(enabled))
        self._reload_css_cascade()

    def cb_font_changed(self, obj: Gtk.FontButton) -> None:
        """Save custom font setting."""
        font_name = obj.get_font()
        theme_config.set("font", font_name)
        if self.gtksettings:
            self.gtksettings.set_property("gtk-font-name", font_name)
        self.uistate.emit('font-changed')
        # Reason for emit is for fitting columns to resized content
        # https://github.com/gramps-project/gramps/pull/1306#issuecomment-957557573
        # https://gramps.discourse.group/t/themes-addon-needs-adoption-by-a-maintainer/6231

    def font_filter(self, family, face, *_obj) -> bool:
        """Filter font selection dialog to normal style and weight."""
        desc = face.describe()
        return (
            desc.get_style() == Pango.Style.NORMAL
            and desc.get_weight() == Pango.Weight.NORMAL
        )

    def cb_toolbar_text_changed(self, obj: Gtk.CheckButton) -> None:
        """Toggle text labels on toolbar buttons."""
        value = obj.get_active()
        config.set("interface.toolbar-text", value)
        toolbar = self.uistate.uimanager.get_widget("ToolBar")
        if toolbar is not None:
            toolbar.set_style(
                Gtk.ToolbarStyle.BOTH if value else Gtk.ToolbarStyle.ICONS
            )

    def t_text_changed(self, obj: Gtk.CheckButton) -> None:
        """Legacy alias for :meth:`cb_toolbar_text_changed`."""
        self.cb_toolbar_text_changed(obj)

    def cb_scroll_changed(self, obj: Gtk.CheckButton) -> None:
        """Toggle fixed scrollbars (Windows only)."""
        value = obj.get_active()
        config.set("interface.fixed-scrollbar", str(value))
        self.gtksettings.set_property("gtk-primary-button-warps-slider", not value)
        if hasattr(MyPrefs, "provider"):
            Gtk.StyleContext.remove_provider_for_screen(
                Screen.get_default(), MyPrefs.provider
            )
        if value:
            MyPrefs.provider = Gtk.CssProvider()
            css = (
                "* { -GtkScrollbar-has-backward-stepper: 1; "
                "-GtkScrollbar-has-forward-stepper: 1; }"
            )
            MyPrefs.provider.load_from_data(css.encode("utf8"))
            Gtk.StyleContext.add_provider_for_screen(
                Screen.get_default(),
                MyPrefs.provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        try:
            if value:
                subprocess.check_output("setx GTK_OVERLAY_SCROLLING 0", shell=True)
            else:
                subprocess.check_output(
                    r"reg delete HKCU\Environment /v GTK_OVERLAY_SCROLLING /f",
                    shell=True,
                )
        except subprocess.CalledProcessError:
            LOG.warning(_("Cannot set environment variable GTK_OVERLAY_SCROLLING"))

    def cb_default_clicked(self, obj: Gtk.Button) -> None:
        """Reset theme, font, and CSS settings back to system defaults."""
        self.gtksettings.set_property("gtk-theme-name", self.def_theme)
        self.gtksettings.set_property("gtk-application-prefer-dark-theme", False)

        theme_config.set("font", "")
        theme_config.set("theme", "")
        theme_config.set("dark-variant", "False")
        theme_config.set("css-theme", "")
        theme_config.set("css-patches", "")

        if self.def_font:
            self.gtksettings.set_property("gtk-font-name", self.def_font)

        if hasattr(self, "font_binding") and self.font_binding:
            self.font_binding.unbind()

        sys_font = self.gtksettings.get_property("gtk-font-name")
        self.font_button.set_font_name(sys_font)

        self.font_binding = self.gtksettings.bind_property(
            "gtk-font-name",
            self.font_button,
            "font-name",
            BindingFlags.BIDIRECTIONAL | BindingFlags.SYNC_CREATE,
        )

        self.theme.remove_all()
        for indx, theme in enumerate(sorted(self.t_names)):
            self.theme.append_text(theme)
            if theme == self.def_theme:
                self.theme.set_active(indx)
        self.dark.set_active(False)

        self.css_combo.set_active(0)
        for chk in self.patch_checks.values():
            chk.set_active(False)

        if not win():
            return
        if hasattr(self, "sc_text"):
            self.sc_text.set_active(False)
        config.set("interface.fixed-scrollbar", "")
        self.gtksettings.set_property("gtk-primary-button-warps-slider", True)
        if hasattr(MyPrefs, "provider"):
            Gtk.StyleContext.remove_provider_for_screen(
                Screen.get_default(), MyPrefs.provider
            )
        try:
            subprocess.check_output(
                r"reg delete HKCU\Environment /v GTK_OVERLAY_SCROLLING /f",
                shell=True,
            )
        except subprocess.CalledProcessError:
            pass

    def cb_open_user_css(self, obj: Gtk.Button) -> None:
        """Open or create ``gramps_user.css`` in the default editor."""
        user_css_path = os.path.join(USER_CSS, "gramps_user.css")
        if not os.path.isfile(user_css_path):
            os.makedirs(USER_CSS, exist_ok=True)
            with open(user_css_path, "w", encoding="utf-8") as fh:
                fh.write(_USER_CSS_TEMPLATE)
            self._refresh_user_css_status()
            screen = Screen.get_default()
            if screen:
                _load_css_provider(
                    user_css_path, screen, Gtk.STYLE_PROVIDER_PRIORITY_USER
                )
        try:
            app = Gio.app_info_get_default_for_type("text/plain", False)
            if app:
                app.launch_uris(["file://" + user_css_path])
            else:
                LOG.warning(_("No default text editor found for gramps_user.css"))
        except Exception as exc:
            LOG.warning(_("Could not open gramps_user.css: %s"), exc)

    def cb_open_css_folder(self, obj: Gtk.Button) -> None:
        """Open the user CSS directory in the default file manager."""
        os.makedirs(USER_CSS, exist_ok=True)
        try:
            app = Gio.app_info_get_default_for_type("inode/directory", False)
            if app:
                app.launch_uris(["file://" + USER_CSS])
            else:
                LOG.warning(_("No default file manager found"))
        except Exception as exc:
            LOG.warning(_("Could not open CSS folder: %s"), exc)