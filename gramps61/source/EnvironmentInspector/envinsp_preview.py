#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
"""
Environment Inspector - Translation Preview tab.

Shows how Gramps text looks in another installed Gramps translation,
without changing the running session:

- Samples: common words, every date format, date modifiers, a name and a
  sort order, side by side for the session language and the preview
  language.
- Windows: the interface text of an open window (Windows menu), the
  visible sidebar or bottombar gramplet of the active view, an open
  Dashboard gramplet, or the main window, looked up in the catalog of the
  preview language. Only interface text is read; text-entry contents
  (genealogy data) are never read or changed.
"""

import logging

from gi.repository import Gdk, GLib, Gtk, Pango

from gramps.gen.const import GRAMPS_LOCALE as glocale

import envinsp_catalog as catalog

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

COL_KIND, COL_ORIGINAL, COL_CURRENT, COL_PREVIEW, COL_STATUS = range(5)
_WRAP_COLUMNS = (COL_ORIGINAL, COL_CURRENT, COL_PREVIEW)
_WRAP_MAX_LINES = 5
_CELL_MARGIN = 12  # cell padding plus a little slack, in pixels
_MAX_STRINGS = 3000
# Never read text the user typed: entries (incl. spin buttons and search
# entries) and text views hold genealogy data, not interface text.
_DATA_WIDGETS = (Gtk.Entry, Gtk.TextView)


def _table_titles():
    return (_("Kind"), _("Original (English)"), _("Current"), _("Preview"), _("Status"))


def _same_text_language(code):
    """
    A key that is equal for languages that show the same text: the
    untranslated source text is US English, so "en", "en_US" and "C" are
    the Original column; other English variants (en_GB...) are translations.
    """
    code = (code or "en").split(".")[0]
    if code in ("C", "POSIX", "en", "en_US"):
        return "en"
    return code


# ------------------------------------------------------------
# Collecting interface text from a widget tree
# ------------------------------------------------------------
def collect_strings(root, title=None):
    """Return [(kind, text)] for the interface text under root."""
    rows = []
    seen = set()

    def add(kind, text):
        if not text or len(rows) >= _MAX_STRINGS:
            return
        text = " ".join(text.split())
        if not text or not any(ch.isalpha() for ch in text) or text in seen:
            return
        seen.add(text)
        rows.append((kind, text))

    def walk(widget):
        if len(rows) >= _MAX_STRINGS:
            return
        try:
            if not widget.get_visible():
                return
            add(_("Tooltip"), widget.get_tooltip_text())
        except Exception:  # widget already destroyed
            return
        if isinstance(widget, _DATA_WIDGETS):
            return
        if isinstance(widget, Gtk.Window):
            add(_("Title"), widget.get_title())
        if isinstance(widget, Gtk.Label):
            add(_("Label"), widget.get_text())
        if isinstance(widget, Gtk.TreeView):
            for column in widget.get_columns():
                if column.get_visible():
                    add(_("Column"), column.get_title())
        # Labels that are not ordinary children.
        if isinstance(widget, Gtk.Notebook):
            for index in range(widget.get_n_pages()):
                tab = widget.get_tab_label(widget.get_nth_page(index))
                if tab is not None:
                    walk(tab)
        elif isinstance(widget, (Gtk.Frame, Gtk.Expander)):
            label = widget.get_label_widget()
            if label is not None:
                walk(label)
        # Only public children: Gtk.Container.forall() would also hand
        # internal children (such as the scroll bars of a scrolled window)
        # to Python, and PyGObject can release them while GTK still uses
        # them, which causes Gtk-CRITICAL warnings.
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                walk(child)

    if title:
        add(_("Title"), title)
    if root is not None:
        walk(root)
    return rows


# ------------------------------------------------------------
# Finding the windows and gramplets to preview
# ------------------------------------------------------------
def _visible_tab(bar):
    """The visible gramplet tab of a sidebar/bottombar, or None."""
    if bar is None or not bar.is_visible():
        return None
    index = bar.get_current_page()
    return bar.get_nth_page(index) if index >= 0 else None


def _active_page(uistate):
    viewmanager = getattr(uistate, "viewmanager", None)
    return getattr(viewmanager, "active_page", None)


def list_sources(uistate):
    """Return [(label, descriptor)] for everything that can be previewed."""
    sources = [(_("Main window"), ("main",))]
    page = _active_page(uistate)
    if page is not None:
        for attr, label in (("sidebar", _("Sidebar")), ("bottombar", _("Bottombar"))):
            tab = _visible_tab(getattr(page, attr, None))
            if tab is not None:
                sources.append(("%s: %s" % (label, getattr(tab, "title", "?")), (attr,)))
        gramplets = getattr(getattr(page, "widget", None), "gramplet_map", None)
        if isinstance(gramplets, dict):
            for title in sorted(gramplets):
                gramplet = gramplets[title]
                if gramplet is not None and getattr(gramplet, "gstate", "") == "maximized":
                    sources.append((_("Dashboard: %s") % title, ("dashboard", title)))
    gwm = getattr(uistate, "gwm", None)
    for window_id, item in list(getattr(gwm, "id2item", {}).items()):
        window = getattr(item, "window", None)
        if isinstance(window, Gtk.Window):
            sources.append(
                (_("Window: %s") % (window.get_title() or "?"), ("managed", window_id))
            )
    return sources


def resolve_source(uistate, descriptor):
    """Return (root widget, extra title) for a descriptor, looked up now."""
    kind = descriptor[0]
    if kind == "main":
        return uistate.window, None
    page = _active_page(uistate)
    if kind in ("sidebar", "bottombar"):
        tab = _visible_tab(getattr(page, kind, None))
        return tab, getattr(tab, "title", None)
    if kind == "dashboard":
        gramplets = getattr(getattr(page, "widget", None), "gramplet_map", {}) or {}
        gramplet = gramplets.get(descriptor[1])
        return getattr(gramplet, "mainframe", None), descriptor[1]
    if kind == "managed":
        gwm = getattr(uistate, "gwm", None)
        item = gwm.get_item_from_id(descriptor[1]) if gwm else None
        return getattr(item, "window", None), None
    return None, None


# ------------------------------------------------------------
# TranslationPreview
# ------------------------------------------------------------
class TranslationPreview(Gtk.Box):
    """The Translation Preview tab."""

    def __init__(self, uistate, config=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)
        self.uistate = uistate
        self._config = config  # EnvironmentInspector.ini, or None
        self.status_checks = {}
        self._matchers = {}
        self._locales = {}
        self._sources = []
        self._shown = False
        # Language each table was last built for: a table is rebuilt when it
        # is shown and the preview language has changed since.
        self._samples_lang = None
        self._window_key = None

        row = Gtk.Box(spacing=6)
        row.pack_start(Gtk.Label(label=_("Preview language:")), False, False, 0)
        self.lang_combo = Gtk.ComboBoxText()
        row.pack_start(self.lang_combo, False, False, 0)
        self.wrap_check = Gtk.CheckButton(label=_("Wrap long text (up to 5 lines)"))
        self.wrap_check.set_active(True)
        self.wrap_check.connect("toggled", self.cb_wrap_toggled)
        row.pack_end(self.wrap_check, False, False, 0)
        self._views = []
        self._lang_columns = []  # (Current column, Preview column) per table
        self._lang_names = {
            code: name for name, code in glocale.get_language_dict().items()
        }
        self._wrap_cache = {}
        self._last_width = {}
        self._remeasure_pending = set()
        self.pack_start(row, False, False, 0)

        notebook = Gtk.Notebook()
        self._notebook = notebook
        self.samples_store, samples_view = self._make_table()
        samples_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        samples_box.pack_start(self._scrolled(samples_view), True, True, 0)
        samples_copy = Gtk.Button(label=_("Copy table"))
        samples_copy.connect("clicked", self.cb_copy, self.samples_store)
        samples_box.pack_start(samples_copy, False, False, 0)
        notebook.append_page(samples_box, Gtk.Label(label=_("Samples")))

        windows_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        top = Gtk.Box(spacing=6)
        self.source_combo = Gtk.ComboBoxText()
        self.source_combo.set_hexpand(True)
        top.pack_start(self.source_combo, True, True, 0)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text(_("Refresh the list of windows and gramplets"))
        refresh.connect("clicked", self.cb_refresh_sources)
        top.pack_start(refresh, False, False, 0)
        windows_box.pack_start(top, False, False, 0)

        options = Gtk.Box(spacing=6)
        options.pack_start(Gtk.Label(label=_("Show catalog text:")), False, False, 0)
        hidden = self._hidden_statuses()
        # One check box per status; the label is translated, the key is not.
        for status, label, tip in (
            (catalog.STATUS_TRANSLATED, _("translated"),
             _("The text is in the catalog, and the preview language "
               "translates it into different text.")),
            (catalog.STATUS_SAME, _("same"),
             _("The text is in the catalog, but the preview language shows "
               "the same text: it is not translated yet, or it is the same "
               "word in both languages (such as an abbreviation or a name).")),
            (catalog.STATUS_PATTERN, _("pattern"),
             _("Text built while Gramps runs, such as \"Edit Person (Smith, "
               "John)\", that matches a catalog entry with placeholders. The "
               "preview fills the placeholders in.")),
            (catalog.STATUS_AMBIGUOUS, _("ambiguous"),
             _("The text matches a catalog entry that the preview language "
               "translates in more than one way (for example by context). "
               "The preview shows the first translation.")),
            (catalog.STATUS_MISSING, _("not in catalog"),
             _("The text is not in the Gramps catalog: usually genealogy "
               "data, text from an addon with its own catalog, or text from "
               "GTK or the system.")),
        ):
            check = Gtk.CheckButton(label=label)
            check.set_tooltip_text(tip)
            check.set_active(status not in hidden)
            check.connect("toggled", self.cb_status_toggled)
            self.status_checks[status] = check
            options.pack_start(check, False, False, 0)
        windows_copy = Gtk.Button(label=_("Copy table"))
        options.pack_end(windows_copy, False, False, 0)
        windows_box.pack_start(options, False, False, 0)

        self.summary = Gtk.Label(xalign=0.0)
        windows_box.pack_start(self.summary, False, False, 0)
        self.windows_store, windows_view = self._make_table()
        windows_copy.connect("clicked", self.cb_copy, self.windows_store)
        windows_box.pack_start(self._scrolled(windows_view), True, True, 0)
        notebook.append_page(windows_box, Gtk.Label(label=_("Windows")))
        notebook.connect("switch-page", self.cb_switch_page)
        self.pack_start(notebook, True, True, 0)

        self._fill_languages()
        self._update_language_columns()
        self.lang_combo.connect("changed", self.cb_language_changed)
        self.source_combo.connect("changed", self.cb_source_changed)
        # Build locales and catalogs only when the tab is first shown.
        self.connect("map", self.cb_first_map)

    # --- layout helpers ------------------------------------------------
    @staticmethod
    def _scrolled(child):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.add(child)
        return scroll

    def _make_table(self):
        store = Gtk.ListStore(str, str, str, str, str)
        view = Gtk.TreeView(model=store)
        for index, title in enumerate(_table_titles()):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer)
            if index in _WRAP_COLUMNS:
                # Ellipsizing keeps the column able to shrink; the text is
                # wrapped by inserting line breaks at the column width.
                renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
                column.set_cell_data_func(renderer, self._cell_text, (view, index))
                column.connect("notify::width", self._cb_column_width, view)
                column.set_expand(True)
            else:
                column.add_attribute(renderer, "text", index)
            column.set_resizable(True)
            column.set_sort_column_id(index)
            view.append_column(column)
        view.set_tooltip_column(COL_PREVIEW)
        self._views.append(view)
        self._lang_columns.append((view.get_column(COL_CURRENT), view.get_column(COL_PREVIEW)))
        return store, view

    # --- language column titles ------------------------------------------
    def _language_name(self, code):
        if not code:
            return "?"
        return (
            self._lang_names.get(code)
            or self._lang_names.get(code.split("_")[0])
            or catalog.english_name(code)
            or code
        )

    def _update_language_columns(self):
        """
        Title the Current and Preview columns with their language, and hide
        a column that repeats the language of a column to its left
        (Original is US English).
        """
        current = catalog.session_language(glocale)
        preview = self.lang_combo.get_active_id() or current
        show_current = _same_text_language(current) != "en"
        show_preview = _same_text_language(preview) not in (
            "en",
            _same_text_language(current),
        )
        current_title = "%s (%s)" % (_("Current"), self._language_name(current))
        preview_title = "%s (%s)" % (_("Preview"), self._language_name(preview))
        for current_col, preview_col in self._lang_columns:
            current_col.set_title(current_title)
            preview_col.set_title(preview_title)
            current_col.set_visible(show_current)
            preview_col.set_visible(show_preview)
        for view in self._views:
            self._queue_remeasure(view)

    # --- wrapping ------------------------------------------------------------
    def _wrapped(self, view, text, width):
        """text broken into lines that fit width pixels, at most 5 lines."""
        key = (text, width)
        if key in self._wrap_cache:
            return self._wrap_cache[key]
        layout = view.create_pango_layout(text)
        layout.set_width(width * Pango.SCALE)
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        data = text.encode("utf-8")
        lines = []
        for line in layout.get_lines_readonly():
            chunk = data[line.start_index : line.start_index + line.length]
            lines.append(chunk.decode("utf-8", "ignore").rstrip("\n"))
        if len(lines) > _WRAP_MAX_LINES:
            lines = lines[:_WRAP_MAX_LINES]
            lines[-1] = lines[-1].rstrip() + "\u2026"
        result = "\n".join(lines)
        if len(self._wrap_cache) > 20000:
            self._wrap_cache.clear()
        self._wrap_cache[key] = result
        return result

    def _cell_text(self, column, cell, model, tree_iter, data):
        view, index = data
        text = model.get_value(tree_iter, index) or ""
        width = column.get_width() - _CELL_MARGIN
        if text and self.wrap_check.get_active() and width > 40:
            text = self._wrapped(view, text, width)
        cell.set_property("text", text)

    def _cb_column_width(self, column, _pspec, view):
        width = column.get_width()
        last = self._last_width.get(column)
        # Ignore tiny changes so a scroll bar appearing cannot start a loop.
        if last is not None and abs(width - last) <= 4:
            return
        self._last_width[column] = width
        self._queue_remeasure(view)

    def _queue_remeasure(self, view):
        if view in self._remeasure_pending:
            return
        self._remeasure_pending.add(view)
        GLib.idle_add(self._remeasure, view)

    def _remeasure(self, view):
        """Make the view recompute every row height."""
        self._remeasure_pending.discard(view)
        model = view.get_model()
        for row in model:
            model.row_changed(row.path, row.iter)
        return False

    def cb_wrap_toggled(self, *obj):
        for view in self._views:
            self._queue_remeasure(view)

    def _fill_languages(self):
        names = {code: name for name, code in glocale.get_language_dict().items()}
        current = catalog.session_language(glocale)
        codes = glocale.get_available_translations()
        for code in codes:
            self.lang_combo.append(code, "%s: %s" % (code, names.get(code, code)))
        # Start on the current language, the row selected on the Language tab.
        if current in codes:
            self.lang_combo.set_active_id(current)
        elif codes:
            self.lang_combo.set_active(0)

    # --- data --------------------------------------------------------------
    def _target(self):
        code = self.lang_combo.get_active_id()
        if not code:
            return None, None
        if code not in self._locales:
            self._locales[code] = catalog.make_locale(code)
            self._matchers[code] = catalog.CatalogMatcher(glocale, self._locales[code])
        return self._locales[code], self._matchers[code]

    def _busy(self, state):
        if self.uistate is not None:
            self.uistate.set_busy_cursor(state)

    def _refresh_samples(self):
        self.samples_store.clear()
        self._samples_lang = self.lang_combo.get_active_id()
        try:
            locale, _matcher = self._target()
            if locale is None:
                return
            rows = catalog.sample_rows(glocale, locale)
        except Exception as exc:
            LOG.warning("Translation Preview samples failed: %s", exc, exc_info=True)
            rows = [(_("Error"), "", str(exc), "", "")]
        for row in rows:
            self.samples_store.append(list(row))

    def _refresh_window(self):
        self.windows_store.clear()
        self.summary.set_text("")
        index = self.source_combo.get_active()
        self._window_key = (self.lang_combo.get_active_id(), index)
        try:
            _locale, matcher = self._target()
        except Exception as exc:
            LOG.warning("Translation Preview catalog failed: %s", exc, exc_info=True)
            self.summary.set_text(str(exc))
            return
        if index < 0 or index >= len(self._sources) or matcher is None:
            return
        label, descriptor = self._sources[index]
        root, title = resolve_source(self.uistate, descriptor)
        if root is None:
            self.summary.set_text(_("Not available any more; click Refresh."))
            return
        counts = {}
        shown = {s for s, check in self.status_checks.items() if check.get_active()}
        for kind, text in collect_strings(root, title):
            preview, status, original = matcher.lookup(text)
            counts[status] = counts.get(status, 0) + 1
            if status in self.status_checks and status not in shown:
                continue
            if not original and _same_text_language(catalog.session_language(glocale)) == "en":
                # The Current column is hidden in a US English session:
                # keep text that is not in the catalog visible in Original.
                original = text
            self.windows_store.append([kind, original, text, preview, status])
        total = sum(counts.values())
        detail = ", ".join("%s %d" % (status, n) for status, n in sorted(counts.items()))
        self.summary.set_text(_("%(total)d strings: %(detail)s") % {"total": total, "detail": detail})

    # --- callbacks ---------------------------------------------------------
    def cb_first_map(self, *obj):
        if self._shown:
            return
        self._shown = True
        self._busy(True)
        try:
            self._refresh_samples()
            self.cb_refresh_sources()
        finally:
            self._busy(False)

    def _refresh_visible(self, page_num=None):
        """Rebuild the visible table if the preview language changed."""
        if page_num is None:
            page_num = self._notebook.get_current_page()
        code = self.lang_combo.get_active_id()
        self._busy(True)
        try:
            if page_num == 0 and self._samples_lang != code:
                self._refresh_samples()
            elif page_num == 1 and self._window_key != (code, self.source_combo.get_active()):
                self._refresh_window()
        finally:
            self._busy(False)

    def cb_language_changed(self, *obj):
        self._update_language_columns()
        if self._shown:
            self._refresh_visible()

    def cb_switch_page(self, notebook, page, page_num):
        if not self._shown:
            return
        if page_num == 1:
            self.cb_refresh_sources()  # rebuilds the window table
        else:
            self._refresh_visible(page_num)

    def cb_refresh_sources(self, *obj):
        previous = self.source_combo.get_active_text()
        self._sources = list_sources(self.uistate)
        self.source_combo.handler_block_by_func(self.cb_source_changed)
        self.source_combo.remove_all()
        active = 0
        for index, (label, _descriptor) in enumerate(self._sources):
            self.source_combo.append_text(label)
            if label == previous:
                active = index
        self.source_combo.handler_unblock_by_func(self.cb_source_changed)
        if self._sources:
            self.source_combo.set_active(active)  # emits "changed"
        else:
            self.cb_source_changed()

    def cb_source_changed(self, *obj):
        if not self._shown:
            return
        self._busy(True)
        try:
            self._refresh_window()
        finally:
            self._busy(False)

    def _hidden_statuses(self):
        if self._config is None:
            return set()
        try:
            return set(self._config.get("preview.hidden-statuses") or [])
        except Exception:  # missing or damaged setting: show everything
            return set()

    def cb_status_toggled(self, *obj):
        if self._config is not None:
            hidden = [s for s, check in self.status_checks.items() if not check.get_active()]
            self._config.set("preview.hidden-statuses", hidden)
            self._config.save()
        self.cb_source_changed()

    def cb_copy(self, _button, store):
        # The visible columns only, with their titles as shown.
        view = self._views[0] if store is self.samples_store else self._views[1]
        shown = [i for i, col in enumerate(view.get_columns()) if col.get_visible()]
        lines = ["\t".join(view.get_column(i).get_title() for i in shown)]
        for row in store:
            lines.append("\t".join(row[i] or "" for i in shown))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("\n".join(lines), -1)
        clipboard.store()
