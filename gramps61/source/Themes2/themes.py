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
"""Themes addon - Preferences panel.

Defines :class:`MyPrefs`, which is monkey-patched over
:class:`gramps.gui.configure.GrampsPreferences` by ``themes_load.py`` so that
the Preferences dialog gains a **Theme** tab.

The tab provides:

* GTK theme selector (combo)
* Dark-variant toggle
* Font selector
* CSS Theme selector (single ``~/.local/share/gramps/css/themes/*.css``)
* CSS Patches (multiple ``~/.local/share/gramps/css/patches/*.css``)
* User override management (``gramps_user.css``) with Edit / Open Folder
* Toolbar-text toggle
* Fixed-scrollbar toggle (Windows only)
* Restore-to-defaults button

CSS cascade order (lowest to highest priority):

1. ``gramps.css``      (loaded by ViewManager, APPLICATION priority)
2. CSS Theme           (APPLICATION priority)
3. CSS Patches         (APPLICATION priority, sorted order)
4. ``gramps_user.css`` (USER priority - always wins)

Bug fixes applied in this revision
-----------------------------------
* **Status label refresh** - ``self._user_css_status`` is now a stored
  attribute so :meth:`cb_open_user_css` can update it live after creating
  ``gramps_user.css``.  Previously the label was a local variable evaluated
  once at panel-build time, so it always reflected the state *before* the
  user clicked Edit.
* **Dark-variant string/bool** - ``preferences.theme-dark-variant`` is now
  stored as ``"True"`` (dark explicitly enabled) or ``""`` (empty = use OS
  default, do nothing on restore).  The previous code stored ``"False"`` which
  is a non-empty truthy string, so ``if value:`` in ``load_on_reg`` was
  ``True`` even for a disabled dark variant, causing the flag to be forced off
  on every startup and -- worse -- leaving a stale value in ``gramps.ini``
  that persisted after the addon was uninstalled.
* **GTK theme name leak** - Only an explicitly *changed* (non-default) GTK
  theme name is persisted.  If the user selects the same theme that GTK
  already uses, ``""`` is stored so that ``gramps.ini`` is left clean and
  Gramps falls back to the OS/GTK default when the addon is absent.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6), 2025-05-12.
Prompts: rewrite Gramps Themes addon for 5.2 following ThemesRewrite.odt,
add versioning to saved prefs, provide complete replacement source files,
fix status-label refresh bug and dark-variant boolean/string bug.
Constraints: https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
"""

# ------------------------
# Python modules
# ------------------------
import glob
import logging
import os
import subprocess
import types

# ------------------------
# GNOME / GTK modules
# ------------------------
from gi.repository import Gio, GLib, Gtk, Pango
from gi.repository.Gdk import Screen
from gi.repository.GObject import BindingFlags

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import USER_CSS
from gramps.gen.constfunc import win
from gramps.gen.utils.alive import update_constants
from gramps.gui.configure import (
    WIKI_HELP_PAGE,
    WIKI_HELP_SEC,
    ConfigureDialog,
    GrampsPreferences,
)
from gramps.gui.display import display_help

# ------------------------
# Gramps specific
# ------------------------
try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_USER_CSS_TEMPLATE = """\
/* Gramps User CSS Override
 *
 * This file is loaded LAST at PRIORITY_USER (800), which is higher than any
 * APPLICATION priority style.  Your rules here always win.
 *
 * CSS Cascade (lowest -> highest priority):
 *   1. gramps.css          (core - loaded by ViewManager)
 *   2. CSS Theme           (if selected in Preferences)
 *   3. CSS Patches         (enabled in Preferences, sorted order)
 *   4. THIS FILE           (your personal overrides)
 *
 * Example:
 *   .lozenge {
 *     background-color: #ff6600;
 *     color: white;
 *   }
 */

"""


# -------------------------------------------------------------------------
#
# _load_css_provider  (module-level helper)
#
# -------------------------------------------------------------------------
def _load_css_provider(path: str, screen, priority: int) -> bool:
    """Load *path* as a CSS provider and attach it to *screen* at *priority*.

    :param path: Absolute path to a ``.css`` file.
    :param screen: A :class:`Gdk.Screen` instance.
    :param priority: GTK style-provider priority constant.
    :returns: ``True`` on success, ``False`` on failure.
    """
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


# ============================================================
#
# MyPrefs
#
# ============================================================
class MyPrefs(GrampsPreferences):
    """Enhanced Preferences dialog with GTK-theme and CSS-theming controls.

    The class is monkey-patched over :class:`GrampsPreferences.__init__` by
    ``themes_load.py`` so that the Preferences dialog gains a **Theme** tab
    without modifying core Gramps source.
    """

    # ------------------------------------------------------------------
    # __init__
    # ------------------------------------------------------------------
    def __init__(self, uistate, dbstate) -> None:
        """Initialise the enhanced Preferences dialog.

        Replaces :meth:`GrampsPreferences.__init__`.  Monkey-patches all addon
        methods onto ``self`` before delegating to
        :meth:`ConfigureDialog.__init__` so that the standard panel list is
        extended with our Theme panel.

        :param uistate: The Gramps UI-state object.
        :param dbstate: The Gramps database-state object.
        """
        # ---- patch addon methods onto self --------------------------------
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
            "_scan_css_dir",
            "_reload_css_cascade",
            "_refresh_user_css_status",
        ):
            setattr(self, name, types.MethodType(getattr(MyPrefs, name), self))

        # ---- build page-function list -------------------------------------
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

        on_close = self._close if hasattr(self, "_close") else update_constants
        ConfigureDialog.__init__(
            self,
            uistate,
            dbstate,
            page_funcs,
            GrampsPreferences,
            config,
            on_close=on_close,
        )

        help_btn = self.window.add_button(_("_Help"), Gtk.ResponseType.HELP)
        help_btn.connect(
            "clicked", lambda x: display_help(WIKI_HELP_PAGE, WIKI_HELP_SEC)
        )
        self.setup_configs("interface.grampspreferences", 700, 500)

    # ------------------------------------------------------------------
    # add_themes_panel
    # ------------------------------------------------------------------
    def add_themes_panel(self, configdialog) -> tuple[str, Gtk.Grid]:
        """Build and return the Theme preferences panel.

        Called by :class:`ConfigureDialog` when building the list of tabs.

        :param configdialog: The parent :class:`ConfigureDialog` (unused but
            required by the protocol).
        :returns: A ``(label_string, widget)`` tuple.
        """
        grid = Gtk.Grid()
        grid.set_border_width(12)
        grid.set_column_spacing(6)
        grid.set_row_spacing(6)
        row = 0

        # ================================================================
        # Section: GTK Theme
        # ================================================================
        lbl = Gtk.Label()
        lbl.set_markup("<b>{}</b>".format(_("GTK Theme")))
        lbl.set_halign(Gtk.Align.START)
        grid.attach(lbl, 0, row, 3, 1)
        row += 1

        # --- Theme combo -----------------------------------------------
        self.theme = Gtk.ComboBoxText()
        self.t_names: set[str] = set()

        # Built-in GTK themes
        try:
            themes = Gio.resources_enumerate_children("/org/gtk/libgtk/theme", 0)
            for theme in themes:
                if theme.endswith("/"):
                    self.t_names.add(theme[:-1])
                elif theme.startswith(("HighContrast", "Raleigh", "gtk-win32")):
                    self.t_names.add(theme.replace(".css", ""))
        except Exception:  # pylint: disable=broad-except
            pass

        # User / system themes from filesystem
        self.gtk_css(os.path.join(GLib.get_home_dir(), ".themes"))
        self.gtk_css(os.path.join(GLib.get_user_data_dir(), "themes"))
        for sysdir in GLib.get_system_data_dirs():
            self.gtk_css(os.path.join(sysdir, "themes"))

        self.gtksettings = Gtk.Settings.get_default()

        # Record the GTK-default theme at dialog-open time.  cb_theme_combo_changed
        # uses this to detect when the user returns to the default so it can
        # store "" rather than the default name, keeping gramps.ini clean.
        self._default_gtk_theme: str = self.gtksettings.get_property(
            "gtk-theme-name"
        )
        c_theme = self._default_gtk_theme

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

        # --- Dark variant ----------------------------------------------
        self.dark = Gtk.CheckButton(label=_("Dark Variant"))
        # Reflect the *current live* GTK state, not the stored config value.
        # The stored value may be "" meaning "use OS default".
        dark_val = self.gtksettings.get_property(
            "gtk-application-prefer-dark-theme"
        )
        self.dark.set_active(dark_val)
        self.dark.connect("toggled", self.cb_dark_variant_changed)
        if os.environ.get("GTK_THEME"):
            self.dark.set_sensitive(False)
            self.dark.set_tooltip_text(_("Theme is hardcoded by GTK_THEME"))
        grid.attach(self.dark, 1, row, 2, 1)
        row += 1

        # --- Font ------------------------------------------------------
        font_button = Gtk.FontButton(show_style=False)
        font_button.set_filter_func(self.font_filter, None)
        self.gtksettings.bind_property(
            "gtk-font-name",
            font_button,
            "font-name",
            BindingFlags.BIDIRECTIONAL | BindingFlags.SYNC_CREATE,
        )
        font_button.connect("font-set", self.cb_font_changed)
        lwidget = Gtk.Label(label=_("%s: ") % _("Font"))
        lwidget.set_halign(Gtk.Align.END)
        grid.attach(lwidget, 0, row, 1, 1)
        grid.attach(font_button, 1, row, 2, 1)
        row += 1

        # --- Toolbar text ----------------------------------------------
        t_text = Gtk.CheckButton.new_with_mnemonic(
            _("_Toolbar") + " " + _("Text")
        )
        t_text.set_active(config.get("interface.toolbar-text"))
        t_text.connect("toggled", self.cb_toolbar_text_changed)
        grid.attach(t_text, 1, row, 2, 1)
        row += 1

        # --- Fixed scrollbar (Windows only) ---------------------------
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

        row += 1  # spacer

        # ================================================================
        # Section: CSS Theming cascade
        # ================================================================
        lbl2 = Gtk.Label()
        lbl2.set_markup("<b>{}</b>".format(_("CSS Theming")))
        lbl2.set_halign(Gtk.Align.START)
        grid.attach(lbl2, 0, row, 3, 1)
        row += 1

        hint = Gtk.Label(
            label=_(
                "CSS cascade order (lowest to highest priority):\n"
                "  1. gramps.css (core)   2. CSS Theme   "
                "3. CSS Patches   4. gramps_user.css"
            )
        )
        hint.set_halign(Gtk.Align.START)
        hint.set_line_wrap(True)
        grid.attach(hint, 0, row, 3, 1)
        row += 1

        # --- CSS Theme combo ------------------------------------------
        self.css_combo = Gtk.ComboBoxText()
        self.css_combo.append("", _("None (use Gramps default)"))
        self.css_themes: dict[str, str] = self._scan_css_dir(
            os.path.join(USER_CSS, "themes")
        )
        for name in sorted(self.css_themes):
            self.css_combo.append(name, name)
        active_css = config.get("preferences.css-theme")
        if active_css and active_css in self.css_themes:
            self.css_combo.set_active_id(active_css)
        else:
            self.css_combo.set_active(0)
        self.css_combo.connect("changed", self.cb_css_theme_changed)

        lwidget = Gtk.Label(label=_("%s: ") % _("CSS Theme"))
        lwidget.set_halign(Gtk.Align.END)
        grid.attach(lwidget, 0, row, 1, 1)
        grid.attach(self.css_combo, 1, row, 2, 1)
        row += 1

        # --- CSS Patches ----------------------------------------------
        lbl3 = Gtk.Label(label=_("CSS Patches:"))
        lbl3.set_halign(Gtk.Align.END)
        lbl3.set_valign(Gtk.Align.START)
        grid.attach(lbl3, 0, row, 1, 1)

        self.css_patches: dict[str, str] = self._scan_css_dir(
            os.path.join(USER_CSS, "patches")
        )
        self.patch_checks: dict[str, Gtk.CheckButton] = {}

        patches_str = config.get("preferences.css-patches")
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
        grid.attach(frame, 1, row, 2, 1)
        row += 1

        # --- gramps_user.css user override ----------------------------
        lbl4 = Gtk.Label()
        lbl4.set_markup("<b>{}</b>".format(_("User CSS Override")))
        lbl4.set_halign(Gtk.Align.START)
        grid.attach(lbl4, 0, row, 3, 1)
        row += 1

        user_css_path = os.path.join(USER_CSS, "gramps_user.css")
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        path_entry = Gtk.Entry()
        path_entry.set_text(user_css_path)
        path_entry.set_editable(False)
        path_box.pack_start(path_entry, True, True, 0)

        # Edit button - pencil/editor icon; tooltip carries the description so
        # no translated button label is needed (reduces translation workload).
        edit_img = Gtk.Image.new_from_icon_name(
            "text-editor", Gtk.IconSize.SMALL_TOOLBAR
        )
        edit_btn = Gtk.Button()
        edit_btn.set_image(edit_img)
        edit_btn.set_relief(Gtk.ReliefStyle.NONE)
        edit_btn.set_tooltip_text(_("Edit gramps_user.css in default text editor"))
        edit_btn.connect("clicked", self.cb_open_user_css)
        path_box.pack_start(edit_btn, False, False, 0)

        # Open-folder button - document-open icon; tooltip carries description.
        folder_img = Gtk.Image.new_from_icon_name(
            "document-open", Gtk.IconSize.SMALL_TOOLBAR
        )
        folder_btn = Gtk.Button()
        folder_btn.set_image(folder_img)
        folder_btn.set_relief(Gtk.ReliefStyle.NONE)
        folder_btn.set_tooltip_text(_("Open CSS folder in file manager"))
        folder_btn.connect("clicked", self.cb_open_css_folder)
        path_box.pack_start(folder_btn, False, False, 0)

        grid.attach(path_box, 0, row, 3, 1)
        row += 1

        # Status label stored as an instance attribute so cb_open_user_css can
        # call _refresh_user_css_status() to update it live after file creation.
        self._user_css_status = Gtk.Label()
        self._user_css_status.set_halign(Gtk.Align.START)
        self._refresh_user_css_status()
        grid.attach(self._user_css_status, 0, row, 3, 1)
        row += 1

        row += 1  # spacer

        # --- Restore defaults -----------------------------------------
        button = Gtk.Button(label=_("Restore to defaults"))
        button.connect("clicked", self.cb_default_clicked)
        grid.attach(button, 0, row, 2, 1)

        return _("Theme"), grid

    # ------------------------------------------------------------------
    # _refresh_user_css_status
    # ------------------------------------------------------------------
    def _refresh_user_css_status(self) -> None:
        """Update ``self._user_css_status`` to reflect whether the file exists.

        Safe to call at any time after the panel has been constructed.  The
        label is updated in-place so GTK reflows the panel without rebuilding.
        """
        user_css_path = os.path.join(USER_CSS, "gramps_user.css")
        if os.path.isfile(user_css_path):
            self._user_css_status.set_markup(
                "<span foreground='green'>{}</span>".format(
                    _("\u2713 gramps_user.css is present and active")
                )
            )
        else:
            self._user_css_status.set_text(
                _("(gramps_user.css not yet created)")
            )

    # ------------------------------------------------------------------
    # _scan_css_dir
    # ------------------------------------------------------------------
    def _scan_css_dir(self, directory: str) -> dict[str, str]:
        """Return ``{name: path}`` for every ``.css`` file in *directory*.

        :param directory: Absolute path of the directory to scan.
        :returns: Dictionary mapping bare name (without ``.css``) to full path.
        """
        result: dict[str, str] = {}
        if not os.path.isdir(directory):
            return result
        for fname in os.listdir(directory):
            if fname.endswith(".css"):
                result[fname[:-4]] = os.path.join(directory, fname)
        return result

    # ------------------------------------------------------------------
    # gtk_css
    # ------------------------------------------------------------------
    def gtk_css(self, directory: str) -> None:
        """Scan *directory* for GTK 3.x themes and add names to :attr:`t_names`.

        :param directory: Path of a ``themes/`` parent directory to scan.
        """
        if not os.path.isdir(directory):
            return
        for entry in glob.glob(
            os.path.join(directory, "*", "gtk-3.*", "gtk.css")
        ):
            self.t_names.add(entry.replace("\\", "/").split("/")[-3])

    # ------------------------------------------------------------------
    # _reload_css_cascade
    # ------------------------------------------------------------------
    def _reload_css_cascade(self) -> None:
        """Re-apply the complete CSS cascade from current config state.

        GTK does not support unloading providers, so this is additive; the
        standard cascade semantics (later rule wins) produce correct results.
        """
        screen = Screen.get_default()
        if screen is None:
            return

        active = config.get("preferences.css-theme")
        if active and active in self.css_themes:
            _load_css_provider(
                self.css_themes[active],
                screen,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

        patches_str = config.get("preferences.css-patches")
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

    # ==================================================================
    # Callbacks - all prefixed with cb_ per AGENTS.md convention
    # ==================================================================

    def cb_theme_combo_changed(self, obj: Gtk.ComboBoxText) -> None:
        """Handle GTK theme combo change.

        Stores the chosen theme name, or ``""`` when the selection returns to
        the OS-default theme so that ``gramps.ini`` stays clean.

        :param obj: The :class:`Gtk.ComboBoxText` that fired the signal.
        """
        value = obj.get_active_text()
        if value:
            self.gtksettings.set_property("gtk-theme-name", value)
            # Persist only non-default choices.  Storing "" means "use whatever
            # GTK's default is", preventing gramps.ini from forcing a specific
            # theme when this addon is absent.
            if value == self._default_gtk_theme:
                config.set("preferences.theme", "")
            else:
                config.set("preferences.theme", value)

    # Keep the old name alias so external code that may reference it still works.
    def theme_changed(self, obj: Gtk.ComboBoxText) -> None:
        """Alias for :meth:`cb_theme_combo_changed` (backward-compat).

        :param obj: The combo box that changed.
        """
        self.cb_theme_combo_changed(obj)

    def cb_dark_variant_changed(self, obj: Gtk.CheckButton) -> None:
        """Handle dark-variant checkbox toggle.

        Stores ``"True"`` when dark mode is explicitly enabled, or ``""``
        (empty) when it is turned off.  An empty value means "do nothing on
        startup", so the OS/GTK default is respected both while the addon is
        installed and after it is removed.

        :param obj: The :class:`Gtk.CheckButton` that was toggled.
        """
        value = obj.get_active()
        self.gtksettings.set_property("gtk-application-prefer-dark-theme", value)
        # Only store "True"; store "" (not "False") for off so that gramps.ini
        # does not carry a stale value that would be truthy on the next read.
        config.set("preferences.theme-dark-variant", "True" if value else "")

    def cb_css_theme_changed(self, obj: Gtk.ComboBoxText) -> None:
        """Handle CSS theme combo change.

        :param obj: The :class:`Gtk.ComboBoxText` for CSS theme selection.
        """
        active_id = obj.get_active_id() or ""
        config.set("preferences.css-theme", active_id)
        self._reload_css_cascade()

    def cb_patch_toggled(self, patch_name: str, widget: Gtk.CheckButton) -> None:
        """Handle a CSS patch checkbox toggle.

        Re-saves the ordered enabled-patch list and reloads the cascade.

        :param patch_name: Name of the patch whose checkbox changed.
        :param widget: The :class:`Gtk.CheckButton` that was toggled.
        """
        enabled = [
            name
            for name in sorted(self.css_patches)
            if self.patch_checks[name].get_active()
        ]
        config.set("preferences.css-patches", ",".join(enabled))
        self._reload_css_cascade()

    def cb_font_changed(self, obj: Gtk.FontButton) -> None:
        """Handle font selection change.

        :param obj: The :class:`Gtk.FontButton` that fired the signal.
        """
        config.set("preferences.font", obj.get_font())

    def font_filter(self, family, face, *_obj) -> bool:
        """Filter font chooser to show only regular-weight, upright faces.

        :param family: :class:`Pango.FontFamily` (unused).
        :param face: :class:`Pango.FontFace` being evaluated.
        :returns: ``True`` if the face should be shown.
        """
        desc = face.describe()
        return (
            desc.get_style() == Pango.Style.NORMAL
            and desc.get_weight() == Pango.Weight.NORMAL
        )

    def cb_toolbar_text_changed(self, obj: Gtk.CheckButton) -> None:
        """Handle toolbar-text checkbox toggle.

        :param obj: The :class:`Gtk.CheckButton` that was toggled.
        """
        value = obj.get_active()
        config.set("interface.toolbar-text", value)
        toolbar = self.uistate.uimanager.get_widget("ToolBar")
        if toolbar is not None:
            toolbar.set_style(
                Gtk.ToolbarStyle.BOTH if value else Gtk.ToolbarStyle.ICONS
            )

    # Keep old name for compatibility
    def t_text_changed(self, obj: Gtk.CheckButton) -> None:
        """Alias for :meth:`cb_toolbar_text_changed` (backward-compat).

        :param obj: The checkbox that changed.
        """
        self.cb_toolbar_text_changed(obj)

    def cb_scroll_changed(self, obj: Gtk.CheckButton) -> None:
        """Handle fixed-scrollbar checkbox toggle (Windows only).

        :param obj: The :class:`Gtk.CheckButton` that was toggled.
        """
        value = obj.get_active()
        config.set("interface.fixed-scrollbar", str(value))
        self.gtksettings.set_property(
            "gtk-primary-button-warps-slider", not value
        )
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
                subprocess.check_output(
                    "setx GTK_OVERLAY_SCROLLING 0", shell=True
                )
            else:
                subprocess.check_output(
                    r"reg delete HKCU\Environment"
                    r" /v GTK_OVERLAY_SCROLLING /f",
                    shell=True,
                )
        except subprocess.CalledProcessError:
            LOG.warning(
                _("Cannot set environment variable GTK_OVERLAY_SCROLLING")
            )

    def cb_default_clicked(self, obj: Gtk.Button) -> None:
        """Restore all theme settings to their original GTK defaults.

        :param obj: The clicked :class:`Gtk.Button` (unused).
        """
        # GTK settings
        self.gtksettings.set_property("gtk-font-name", self.def_font)
        self.gtksettings.set_property("gtk-theme-name", self.def_theme)
        self.gtksettings.set_property(
            "gtk-application-prefer-dark-theme", self.def_dark
        )

        # Config keys - all cleared to empty so gramps.ini is left clean
        config.set("preferences.font", "")
        config.set("preferences.theme", "")
        config.set("preferences.theme-dark-variant", "")
        config.set("preferences.css-theme", "")
        config.set("preferences.css-patches", "")

        # Reset GTK theme combo
        self.theme.remove_all()
        for indx, theme in enumerate(sorted(self.t_names)):
            self.theme.append_text(theme)
            if theme == self.def_theme:
                self.theme.set_active(indx)
        self.dark.set_active(self.def_dark)

        # Reset CSS combo & patches
        self.css_combo.set_active(0)
        for chk in self.patch_checks.values():
            chk.set_active(False)

        # Windows-only scrollbar reset
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
        """Open ``gramps_user.css`` in the system default text editor.

        Creates the file with a template header if it does not yet exist, then
        refreshes the status label so the UI reflects the new state immediately.
        Also loads the new file into the running CSS cascade right away.

        :param obj: The clicked :class:`Gtk.Button` (unused).
        """
        user_css_path = os.path.join(USER_CSS, "gramps_user.css")
        if not os.path.isfile(user_css_path):
            os.makedirs(USER_CSS, exist_ok=True)
            with open(user_css_path, "w", encoding="utf-8") as fh:
                fh.write(_USER_CSS_TEMPLATE)
            # Update status label immediately (fix for "not yet created" bug).
            self._refresh_user_css_status()
            # Load into the running session so the user sees the effect now.
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
                LOG.warning(
                    _("No default text editor found for gramps_user.css")
                )
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warning(_("Could not open gramps_user.css: %s"), exc)

    def cb_open_css_folder(self, obj: Gtk.Button) -> None:
        """Open the Gramps user CSS folder in the system file manager.

        :param obj: The clicked :class:`Gtk.Button` (unused).
        """
        os.makedirs(USER_CSS, exist_ok=True)
        try:
            app = Gio.app_info_get_default_for_type("inode/directory", False)
            if app:
                app.launch_uris(["file://" + USER_CSS])
            else:
                LOG.warning(_("No default file manager found"))
        except Exception as exc:  # pylint: disable=broad-except
            LOG.warning(_("Could not open CSS folder: %s"), exc)
