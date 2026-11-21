"""
Translation Updater tool.

Pick languages, then download newer Gramps and addon translations from the
published translation packs. Addons keep their version numbers; only the
translations change. The startup half lives in TranslationUpdaterLib.py.
"""

import os
import re
import threading

from gi.repository import Gdk, GLib, Gtk

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.errors import WindowActiveError
from gramps.gen.plug import PluginRegister
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

PLUGIN_ID = "TranslationUpdater"

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

TITLE = _("Translation Updater")
(
    COL_SELECTED,
    COL_REGION,
    COL_CODE,
    COL_NAME,
    COL_ENDONYM,
    COL_ADDONS,
    COL_STATUS,
    COL_TOOLTIP,
    COL_ADDONS_N,
    COL_SORTKEY,
) = range(10)


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
        self.store = Gtk.ListStore(bool, str, str, str, str, str, str, str, int, str)
        # Default order: chosen languages first, then by name. The key is a
        # column of its own, so ticking a language moves it at once.
        self.store.set_sort_column_id(COL_SORTKEY, Gtk.SortType.ASCENDING)
        self.window.add(self._build())
        self._fill_languages(lib.cached_index())
        self._update_launcher_status()
        self.show()

    def build_menu_names(self, obj):
        # A submenu label makes this window a "branch" in Gramps' window
        # manager, so it can own child windows such as the Verify window.
        return (TITLE, TITLE)

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
        view.set_tooltip_column(COL_TOOLTIP)
        self.view = view
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self.cb_language_toggled)
        chosen_column = Gtk.TreeViewColumn("", toggle, active=COL_SELECTED)
        chosen_column.set_sort_column_id(COL_SORTKEY)
        view.append_column(chosen_column)
        # Same columns, in the same order, as Environment Inspector's
        # language table, then the columns only this tool has.
        for title, col, sort_col, tip in (
            (
                _("Region"),
                COL_REGION,
                COL_REGION,
                _(
                    "The region named in the translation code, or else the "
                    "region Gramps pairs with the language"
                ),
            ),
            (_("Code"), COL_CODE, COL_CODE, None),
            (_("Name"), COL_NAME, COL_NAME, None),
            (_("Endonym"), COL_ENDONYM, COL_ENDONYM, None),
            (
                _("Addons"),
                COL_ADDONS,
                COL_ADDONS_N,
                _("How many addons have a published translation"),
            ),
            (_("Status"), COL_STATUS, COL_STATUS, None),
        ):
            column = Gtk.TreeViewColumn(None, Gtk.CellRendererText(), text=col)
            header = Gtk.Label(label=title)
            if tip:
                header.set_tooltip_text(tip)
            header.show()
            column.set_widget(header)
            column.set_sort_column_id(sort_col)
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
        # Smart Help button, leftmost, without a button outline.
        help_button = add_help_button(buttons, self.uistate, PLUGIN_ID)
        help_button.set_relief(Gtk.ReliefStyle.NONE)
        self.verify_button = Gtk.Button(label=_("Verify"))
        self.verify_button.set_tooltip_text(
            _(
                "Show which strings changed for the highlighted language, and "
                "whether Gramps now uses the downloaded text"
            )
        )
        self.verify_button.connect("clicked", self.cb_verify)
        buttons.pack_start(self.verify_button, False, False, 0)
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

    def _tooltip_text(self, code, titles):
        """Markup listing what the last real update for code brought."""
        entry = lib.state()["langs"].get(code, {}).get("last_update")
        if not entry:
            return None
        names = lib.item_names(entry.get("core"), entry.get("addons", []), titles)
        lines = [_("Last updated %s:") % entry.get("date", "")[:10]] + [
            "  " + name for name in names
        ]
        return GLib.markup_escape_text("\n".join(lines))

    def _fill_languages(self, index):
        selected = set(lib.selected_languages())
        published = index.get("languages", {}) if index else {}
        codes = set(published) | selected
        info = {code: lib.language_info(code) for code in codes}
        titles = lib.addon_titles()
        self.store.clear()
        # Chosen languages first, then the rest by name.
        for code in sorted(
            codes, key=lambda c: (c not in selected, info[c]["name"].lower())
        ):
            count = published.get(code, {}).get("addons", -1)
            self.store.append(
                [
                    code in selected,
                    info[code]["region"],
                    code,
                    info[code]["name"],
                    info[code]["endonym"],
                    "%d" % count if count >= 0 else "\u2014",
                    self._status_text(code),
                    self._tooltip_text(code, titles),
                    count,
                    self._sort_key(code in selected, info[code]["name"]),
                ]
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
    @staticmethod
    def _sort_key(chosen, name):
        return ("0" if chosen else "1") + name.lower()

    def cb_language_toggled(self, _renderer, path):
        row = self.store[path]
        row[COL_SELECTED] = not row[COL_SELECTED]
        row[COL_SORTKEY] = self._sort_key(row[COL_SELECTED], row[COL_NAME])
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
        for widget in (
            self.check_button,
            self.refresh_button,
            self.verify_button,
            self.view,
        ):
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
        lang_names = {row[COL_CODE]: row[COL_NAME] for row in self.store}
        lines = [_("Translations checked")] + lib.summarize(results, lang_names)
        if any(r["core"] or r["addons"] for r in results):
            lines.append(_("Restart Gramps so every window uses the new translations."))
            lines.append(_("Point at a language to see what its last update brought."))
        self.status.set_text("\n".join(lines))

    def cb_verify(self, _button):
        model, treeiter = self.view.get_selection().get_selected()
        if treeiter is not None:
            code, name = model[treeiter][COL_CODE], model[treeiter][COL_NAME]
        else:
            chosen = [row for row in self.store if row[COL_SELECTED]]
            if not chosen:
                self.status.set_text(_("Choose at least one language first."))
                return
            code, name = chosen[0][COL_CODE], chosen[0][COL_NAME]
        try:
            result = lib.verify(code)
        except Exception as err:  # pylint: disable=broad-except
            self.status.set_text("%s: %s" % (name, err))
            return
        # Replace an open window for the same language with fresh results.
        old = self.uistate.gwm.get_item_from_id(VerifyWindow.key(code))
        if old is not None:
            old.close()
        try:
            VerifyWindow(self.uistate, self.track, name, result)
        except WindowActiveError:
            pass

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


# ------------------------------------------------------------------------
#
# VerifyWindow
#
# ------------------------------------------------------------------------
V_ITEM, V_ENGLISH, V_INSTALLED, V_DOWNLOADED, V_LIVE, V_MARK = range(6)
I_NAME, I_CHANGED, I_SHOWN, I_MARK, I_INDEX, I_CHANGED_N = range(6)


class VerifyWindow(ManagedWindow):
    """
    Side-by-side proof that downloads reach Gramps: English, the installed
    translation, the downloaded one and what Gramps returns now. No language
    skills needed: the last two should match and differ from the installed.
    """

    def __init__(self, uistate, track, name, result):
        self.result = result
        self.title = _("Verify translations: %s") % name
        ManagedWindow.__init__(self, uistate, track, self.key(result["lang"]))
        self.set_window(Gtk.Window(), None, self.title)
        self.window.set_resizable(True)
        self.window.set_default_size(1000, self._screen_height(0.8, 720))

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        vbox.set_border_width(12)
        explain = Gtk.Label(
            label=_(
                "Each row is a phrase that the download changed. "
                "Installed: the translation that came with Gramps %(version)s "
                "or with the addon. Downloaded: the translation that "
                "Translation Updater downloaded. Gramps now: the text Gramps "
                "shows today. When Gramps now matches Downloaded, the "
                "download is working."
            )
            % {"version": lib.VERSION},
            xalign=0,
            wrap=True,
        )
        explain.set_max_width_chars(110)
        vbox.pack_start(explain, False, False, 0)
        summary = Gtk.Label(label=self._summary(), xalign=0, wrap=True)
        summary.set_max_width_chars(110)
        vbox.pack_start(summary, False, False, 0)

        # Items above, their phrases below; the divider can be dragged.
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.pack1(self._build_items(), resize=False, shrink=False)
        paned.pack2(self._build_strings(), resize=True, shrink=False)
        paned.set_position(170)
        vbox.pack_start(paned, True, True, 0)
        vbox.pack_start(self._build_files(), False, False, 0)

        buttons = Gtk.Box(spacing=6)
        copy = Gtk.Button(label=_("Copy report"))
        copy.set_tooltip_text(_("Copy a short text report for a post or email"))
        copy.connect("clicked", self.cb_copy)
        buttons.pack_start(copy, False, False, 0)
        close = Gtk.Button(label=_("Close"))
        close.connect("clicked", self.close)
        buttons.pack_end(close, False, False, 0)
        vbox.pack_start(buttons, False, False, 0)
        self.window.add(vbox)
        self.items_view.get_selection().select_path(Gtk.TreePath.new_first())
        self.show()

    @staticmethod
    def key(code):
        """
        Window manager key: one Verify window per language. Gramps uses the
        key in a GTK action name ("win.wm-<key>"), which allows only letters,
        digits, "-" and ".", so anything else becomes "-" (pt_BR -> pt-BR).
        """
        return "TranslationUpdaterVerify-" + re.sub(r"[^A-Za-z0-9.-]", "-", code)

    def build_window_key(self, obj):
        return obj

    def build_menu_names(self, obj):
        return (self.title, None)

    @staticmethod
    def _screen_height(share, most):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor is None:
            return most
        return min(most, int(monitor.get_workarea().height * share))

    def _summary(self):
        total = sum(sec["differ"] for sec in self.result["sections"])
        good = sum(sec["ok"] for sec in self.result["sections"])
        if not total:
            text = _("The download changed no phrases compared with what is installed.")
        elif good == total:
            text = _(
                "The download changed %(total)d phrases. Gramps now shows the "
                "downloaded text for all of them."
            ) % {"total": total}
        else:
            text = _(
                "The download changed %(total)d phrases. Gramps now shows the "
                "downloaded text for %(good)d of them; the %(bad)d that do not "
                "match are listed first."
            ) % {"total": total, "good": good, "bad": total - good}
        return "\n".join([text] + self.result["notes"])

    def _build_items(self):
        store = Gtk.ListStore(str, str, str, str, int, int)
        sections = self.result["sections"]
        total = sum(sec["differ"] for sec in sections)
        good = sum(sec["ok"] for sec in sections)
        store.append(
            [_("All"), "%d" % total, "%d" % good, self._mark(good, total), -1, total]
        )
        for number, sec in enumerate(sections):
            store.append(
                [
                    sec["name"],
                    "%d" % sec["differ"],
                    "%d" % sec["ok"],
                    self._mark(sec["ok"], sec["differ"]),
                    number,
                    sec["differ"],
                ]
            )
        view = Gtk.TreeView(model=store)
        for title, col, sort_col, tip in (
            ("", I_MARK, I_MARK, None),
            (_("Item"), I_NAME, I_NAME, None),
            (_("Changed"), I_CHANGED, I_CHANGED_N, _("Phrases the download changed")),
            (
                _("Shown"),
                I_SHOWN,
                I_SHOWN,
                _("Phrases for which Gramps now shows the downloaded text"),
            ),
        ):
            self._add_column(view, title, col, sort_col, tip)
        view.get_selection().connect("changed", self.cb_item_changed)
        self.items_view = view
        return self._scrolled(view, 120)

    def _build_strings(self):
        self.strings = Gtk.ListStore(str, str, str, str, str, str)
        view = Gtk.TreeView(model=self.strings)
        for title, col in (
            (_("Item"), V_ITEM),
            (_("English"), V_ENGLISH),
            (_("Installed"), V_INSTALLED),
            (_("Downloaded"), V_DOWNLOADED),
            (_("Gramps now"), V_LIVE),
            ("", V_MARK),
        ):
            self._add_column(
                view, title, col, col, None, expand=col in (1, 2, 3, 4), ellipsize=True
            )
        view.set_tooltip_column(V_ENGLISH)
        self.item_column = view.get_column(V_ITEM)
        return self._scrolled(view, 160)

    def _build_files(self):
        frame = Gtk.Frame(label=_("Files"))
        grid = Gtk.Grid(column_spacing=6, row_spacing=4)
        grid.set_border_width(6)
        self.installed_label = Gtk.Label(xalign=0, selectable=True)
        self.downloaded_label = Gtk.Label(xalign=0, selectable=True)
        for label in (self.installed_label, self.downloaded_label):
            label.set_ellipsize(1)  # Pango.EllipsizeMode.START
            label.set_hexpand(True)
        grid.attach(Gtk.Label(label=_("Installed:"), xalign=1), 0, 0, 1, 1)
        grid.attach(self.installed_label, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label=_("Downloaded:"), xalign=1), 0, 1, 1, 1)
        grid.attach(self.downloaded_label, 1, 1, 1, 1)
        self.open_button = Gtk.Button(label=_("Open folder"))
        self.open_button.set_tooltip_text(_("Show the downloaded file in its folder"))
        self.open_button.connect("clicked", self.cb_open_folder)
        grid.attach(self.open_button, 2, 1, 1, 1)
        note = Gtk.Label(
            label=_(
                "Both are .mo files: compiled translation catalogs that Gramps "
                "reads with Python gettext. They are binary, not compressed. "
                "To read one as text, run: msgunfmt FILE"
            ),
            xalign=0,
            wrap=True,
        )
        note.set_max_width_chars(110)
        grid.attach(note, 0, 2, 3, 1)
        frame.add(grid)
        return frame

    @staticmethod
    def _one_line(text):
        """Keep every row one line tall: show line breaks as a return sign."""
        return " \u23ce ".join(part.strip() for part in text.splitlines())

    @staticmethod
    def _mark(good, total):
        return "\u2714" if good == total else "\u2718"

    @staticmethod
    def _scrolled(view, min_height):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(min_height)
        scroll.add(view)
        return scroll

    @staticmethod
    def _add_column(view, title, col, sort_col, tip, expand=False, ellipsize=False):
        cell = Gtk.CellRendererText()
        if ellipsize:
            cell.set_property("ellipsize", 3)  # Pango.EllipsizeMode.END
        column = Gtk.TreeViewColumn(None, cell, text=col)
        header = Gtk.Label(label=title)
        if tip:
            header.set_tooltip_text(tip)
        header.show()
        column.set_widget(header)
        column.set_resizable(True)
        column.set_sort_column_id(sort_col)
        column.set_min_width(60 if title else 24)
        if expand:
            column.set_expand(True)
            column.set_min_width(110)
        view.append_column(column)

    def cb_item_changed(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is None:
            return
        number = model[treeiter][I_INDEX]
        sections = self.result["sections"]
        chosen = sections if number < 0 else [sections[number]]
        self.item_column.set_visible(number < 0)  # only useful for "All"
        self.strings.clear()
        for sec in chosen:
            for english, installed, downloaded, live, okay in sec["rows"]:
                self.strings.append(
                    [
                        sec["name"],
                        self._one_line(english),
                        self._one_line(installed) or _("(none)"),
                        self._one_line(downloaded),
                        self._one_line(live),
                        "\u2714" if okay else "\u2718",
                    ]
                )
        if number < 0:
            self.installed_label.set_text(_("(choose an item above)"))
            self.downloaded_label.set_text(_("(choose an item above)"))
            self.folder = lib.branch_root()
        else:
            sec = sections[number]
            self.installed_label.set_text(
                sec["installed_path"]
                or _("(none: this addon has no translation of its own)")
            )
            self.downloaded_label.set_text(sec["downloaded_path"])
            self.folder = os.path.dirname(sec["downloaded_path"]) or lib.branch_root()
        for label in (self.installed_label, self.downloaded_label):
            label.set_tooltip_text(label.get_text())

    def cb_open_folder(self, _button):
        display_url("file://" + getattr(self, "folder", lib.branch_root()))

    def cb_copy(self, _button):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(lib.verify_report(self.result), -1)


class TranslationUpdaterOptions(tool.ToolOptions):
    """No command-line options."""

    def __init__(self, name, person_id=None):
        tool.ToolOptions.__init__(self, name, person_id)
