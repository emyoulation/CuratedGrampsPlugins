"""
Translation Updater tool.

Pick languages, then download newer Gramps and addon translations from the
published translation packs. Addons keep their version numbers; only the
translations change. The startup half lives in TranslationUpdaterLib.py.
"""

import os
import threading

from gi.repository import GLib, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui.display import display_url
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.plug import tool

import TranslationUpdaterLib as lib

try:
    _TRANS = glocale.get_addon_translator(__file__)
except ValueError:  # stock Gramps when this addon lacks the user's language
    _TRANS = glocale.translation
_ = _TRANS.gettext
ngettext = _TRANS.ngettext

HELP_URL = (
    "https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/"
    "gramps61/source/TranslationUpdater/README.md"
)
TITLE = _("Translation Updater")
COL_SELECTED, COL_NAME, COL_CODE, COL_STATUS = range(4)


class TranslationUpdater(tool.Tool, ManagedWindow):
    """Tool window for choosing languages and downloading packs."""

    def __init__(self, dbstate, user, options_class, name, callback=None):
        self.uistate = user.uistate
        self._busy = False
        self._closed = False
        tool.Tool.__init__(self, dbstate, options_class, name)
        ManagedWindow.__init__(self, self.uistate, [], self.__class__)
        self.set_window(Gtk.Window(), None, TITLE)
        self.window.set_default_size(
            lib.CONFIG.get("window.width"), lib.CONFIG.get("window.height")
        )
        self.store = Gtk.ListStore(bool, str, str, str)
        self.window.add(self._build())
        self._fill_languages(lib.cached_index())
        self._update_launcher_status()
        self.show()

    def build_menu_names(self, obj):
        return (TITLE, None)

    # --------------------------------------------------------------------
    # Layout
    # --------------------------------------------------------------------
    def _build(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(12)

        intro = Gtk.Label(
            label=_(
                "Download newer translations for Gramps and for your installed "
                "addons, in the languages you choose. Addons keep their version "
                "numbers; only the translations change."
            ),
            wrap=True,
            xalign=0,
        )
        vbox.pack_start(intro, False, False, 0)

        # Languages
        frame = Gtk.Frame(label=_("Languages"))
        fbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        fbox.set_border_width(6)
        view = Gtk.TreeView(model=self.store)
        self.view = view
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.cb_language_toggled)
        view.append_column(Gtk.TreeViewColumn("", toggle, active=COL_SELECTED))
        for title, col in (
            (_("Language"), COL_NAME),
            (_("Code"), COL_CODE),
            (_("Status"), COL_STATUS),
        ):
            column = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=col)
            column.set_sort_column_id(col)
            column.set_resizable(True)
            view.append_column(column)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(view)
        fbox.pack_start(scroll, True, True, 0)
        self.refresh_button = Gtk.Button(label=_("Refresh list"))
        self.refresh_button.set_tooltip_text(_("Get the list of published languages"))
        self.refresh_button.connect("clicked", self.cb_refresh)
        rbox = Gtk.Box()
        rbox.pack_start(self.refresh_button, False, False, 0)
        fbox.pack_start(rbox, False, False, 0)
        frame.add(fbox)
        vbox.pack_start(frame, True, True, 0)

        # What to update
        for key, label, tip in (
            ("packs.core", _("Gramps translations"), None),
            ("packs.addons", _("Addon translations"), None),
            (
                "packs.glade",
                _("Also use updated Gramps translations in Glade-built dialogs"),
                _("Takes effect when Gramps restarts"),
            ),
            (
                "packs.check_at_startup",
                _("Check for updates when Gramps starts (at most once a day)"),
                None,
            ),
        ):
            check = Gtk.CheckButton(label=label)
            check.set_active(lib.CONFIG.get(key))
            if tip:
                check.set_tooltip_text(tip)
            check.connect("toggled", self.cb_option_toggled, key)
            vbox.pack_start(check, False, False, 0)

        # Advanced
        expander = Gtk.Expander(label=_("Advanced"))
        grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        grid.set_border_width(6)
        grid.attach(Gtk.Label(label=_("Source:"), xalign=1), 0, 0, 1, 1)
        self.url_entry = Gtk.Entry()
        self.url_entry.set_text(lib.CONFIG.get("source.base_url"))
        self.url_entry.set_hexpand(True)
        self.url_entry.connect("changed", self.cb_url_changed)
        grid.attach(self.url_entry, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=_("Branch:"), xalign=1), 0, 1, 1, 1)
        grid.attach(Gtk.Label(label=lib.branch(), xalign=0), 1, 1, 1, 1)
        grid.attach(Gtk.Label(label=_("Packs folder:"), xalign=1), 0, 2, 1, 1)
        grid.attach(
            Gtk.Label(label=lib.branch_root(), xalign=0, selectable=True), 1, 2, 1, 1
        )
        expander.add(grid)
        vbox.pack_start(expander, False, False, 0)

        # Full-coverage launcher (Option B)
        if lib.launcher_supported():
            lframe = Gtk.Frame(label=_("Full-coverage launcher"))
            lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            lbox.set_border_width(6)
            lbox.pack_start(
                Gtk.Label(
                    label=_(
                        "Some text, such as menu labels, is translated before "
                        "addons load. A separate launcher starts Gramps with the "
                        "updated translations from the very beginning."
                    ),
                    wrap=True,
                    xalign=0,
                ),
                False,
                False,
                0,
            )
            command = Gtk.Label(
                label=lib.launcher_command(), selectable=True, xalign=0, wrap=True
            )
            command.set_tooltip_text(_("Command line equivalent"))
            lbox.pack_start(command, False, False, 0)
            bbox = Gtk.Box(spacing=6)
            self.create_button = Gtk.Button(label=_("Create launcher"))
            self.create_button.connect("clicked", self.cb_create_launcher)
            self.remove_button = Gtk.Button(label=_("Remove launcher"))
            self.remove_button.connect("clicked", self.cb_remove_launcher)
            self.launcher_status = Gtk.Label(xalign=0)
            bbox.pack_start(self.create_button, False, False, 0)
            bbox.pack_start(self.remove_button, False, False, 0)
            bbox.pack_start(self.launcher_status, True, True, 0)
            lbox.pack_start(bbox, False, False, 0)
            lframe.add(lbox)
            vbox.pack_start(lframe, False, False, 0)
        else:
            self.create_button = self.remove_button = self.launcher_status = None

        # Progress and results stay inside this window, so no dialog ever
        # covers another (GNOME centers modal dialogs and pins them there).
        self.progress = Gtk.ProgressBar(show_text=True)
        self.progress.set_no_show_all(True)
        vbox.pack_start(self.progress, False, False, 0)
        self.status = Gtk.Label(xalign=0, wrap=True, selectable=True)
        vbox.pack_start(self.status, False, False, 0)

        buttons = Gtk.Box(spacing=6)
        help_button = Gtk.Button(label=_("Help"))
        help_button.connect("clicked", lambda _btn: display_url(HELP_URL))
        buttons.pack_start(help_button, False, False, 0)
        close = Gtk.Button(label=_("Close"))
        close.connect("clicked", self.close)
        buttons.pack_end(close, False, False, 0)
        self.check_button = Gtk.Button(label=_("Check for updates"))
        self.check_button.connect("clicked", self.cb_check)
        buttons.pack_end(self.check_button, False, False, 0)
        vbox.pack_start(buttons, False, False, 0)
        return vbox

    # --------------------------------------------------------------------
    # Language list
    # --------------------------------------------------------------------
    def _language_name(self, code):
        """Display name for a pack code, even if Gramps lacks that language."""
        try:
            return (
                glocale._get_language_string(code) or code
            )  # pylint: disable=protected-access
        except Exception:  # pylint: disable=broad-except
            return code

    def _status_text(self, code):
        entry = lib.state()["langs"].get(code)
        if not entry:
            return ""
        parts = []
        if entry.get("core"):
            if lib.valid_core_pack(code)[1]:
                parts.append(_("Gramps"))
            else:
                parts.append(_("Gramps paused (installed translation changed)"))
        count = len(entry.get("addons", {}))
        if count:
            parts.append(ngettext("%d addon", "%d addons", count) % count)
        checked = entry.get("checked", "")[:10]
        if checked:
            parts.append(_("checked %s") % checked)
        return ", ".join(parts)

    def _fill_languages(self, index):
        selected = set(lib.selected_languages())
        codes = set(index.get("languages", {})) if index else set()
        codes |= selected
        names = {code: self._language_name(code) for code in codes}
        self.store.clear()
        # Chosen languages first, then the rest alphabetically.
        for code in sorted(codes, key=lambda c: (c not in selected, names[c].lower())):
            self.store.append(
                [code in selected, names[code], code, self._status_text(code)]
            )
        if not index:
            self.status.set_text(
                _("Press Refresh list to see which languages are published.")
            )

    def _chosen(self):
        return [row[COL_CODE] for row in self.store if row[COL_SELECTED]]

    # --------------------------------------------------------------------
    # Callbacks
    # --------------------------------------------------------------------
    def cb_language_toggled(self, _renderer, path):
        row = self.store[path]
        row[COL_SELECTED] = not row[COL_SELECTED]
        lib.CONFIG.set("packs.languages", self._chosen())
        lib.CONFIG.save()

    def cb_option_toggled(self, button, key):
        lib.CONFIG.set(key, button.get_active())
        lib.CONFIG.save()

    def cb_url_changed(self, entry):
        lib.CONFIG.set("source.base_url", entry.get_text().strip() or lib.DEFAULT_URL)
        lib.CONFIG.save()

    # --------------------------------------------------------------------
    # Background work (keeps Gramps responsive during downloads)
    # --------------------------------------------------------------------
    def _set_busy(self, busy, text=""):
        self._busy = busy
        for widget in (self.check_button, self.refresh_button, self.view):
            widget.set_sensitive(not busy)
        if busy:
            self.progress.set_fraction(0.0)
            self.progress.set_text(text)
            self.progress.show()
            self.status.set_text("")
        else:
            self.progress.hide()

    def _cb_progress(self, fraction, text):
        if not self._closed:
            self.progress.set_fraction(min(max(fraction, 0.0), 1.0))
            if text:
                self.progress.set_text(text)
        return False

    def _run_in_background(self, work, done, text):
        """
        Run work(progress) in a thread, then done(result, error) in the GTK
        main loop. progress(fraction, text) may be called from the thread.
        """
        self._set_busy(True, text)

        def progress(fraction, label):
            GLib.idle_add(self._cb_progress, fraction, label)

        def finish(result, error):
            if not self._closed:
                self._set_busy(False)
            done(result, error)
            return False

        def runner():
            try:
                result, error = work(progress), None
            except Exception as err:  # pylint: disable=broad-except
                result, error = None, err
            GLib.idle_add(finish, result, error)

        threading.Thread(target=runner, daemon=True).start()

    # --------------------------------------------------------------------
    # Refresh and check
    # --------------------------------------------------------------------
    def cb_refresh(self, _button):
        if self._busy:
            return
        self._run_in_background(
            lambda _progress: lib.fetch_index(),
            self._refresh_done,
            _("Getting the list of published languages"),
        )

    def _refresh_done(self, index, error):
        if self._closed:
            return
        if error:
            self.status.set_text(_("Could not get the language list: %s") % error)
            return
        self._fill_languages(index)
        self.status.set_text(
            _("%d languages published for %s.")
            % (len(index.get("languages", {})), lib.branch())
        )

    def cb_check(self, _button):
        if self._busy:
            return
        languages = self._chosen()
        if not languages:
            self.status.set_text(_("Choose at least one language first."))
            return
        lib.CONFIG.set("packs.languages", languages)
        lib.CONFIG.save()
        self._run_in_background(
            lambda progress: lib.update_packs(languages, progress),
            self._check_done,
            _("Checking translations"),
        )

    def _check_done(self, results, error):
        if error:
            if not self._closed:
                self.status.set_text(_("Could not check for translations: %s") % error)
            return
        # Patching the running translators belongs in the main loop.
        lib.apply_now()
        if self._closed:
            return
        self._fill_languages(lib.cached_index())
        self._update_launcher_status()
        lines = [_("Translations checked")] + lib.summarize(results)
        if any(r["core"] or r["addons"] for r in results):
            lines.append(_("Restart Gramps so every window uses the new translations."))
        self.status.set_text("\n".join(lines))

    def cb_create_launcher(self, _button):
        try:
            lib.create_launcher()
        except OSError as err:
            self.status.set_text(_("Could not create the launcher: %s") % err)
        self._update_launcher_status()

    def cb_remove_launcher(self, _button):
        lib.remove_launcher()
        self._update_launcher_status()

    def _update_launcher_status(self):
        if self.launcher_status is None:
            return
        exists = os.path.exists(lib.DESKTOP_FILE)
        self.create_button.set_sensitive(not exists)
        self.remove_button.set_sensitive(exists)
        if lib.using_resources():
            text = _("Gramps is running from the launcher now.")
        elif exists:
            text = _('Look for "Gramps (updated translations)" in your menu.')
        else:
            text = ""
        self.launcher_status.set_text(text)

    def close(self, *obj):
        self._closed = True
        width, height = self.window.get_size()
        lib.CONFIG.set("window.width", width)
        lib.CONFIG.set("window.height", height)
        lib.CONFIG.save()
        ManagedWindow.close(self, *obj)


class TranslationUpdaterOptions(tool.ToolOptions):
    """No command-line options."""

    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
