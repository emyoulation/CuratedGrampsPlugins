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
Environment Inspector - Locale Settings tab.

The language is only one of the settings that make up the locale Gramps
uses. This tab lists the others (date, number and sorting locales, spell
checking, text direction, the locale-related Gramps preferences and the
environment variables Gramps reads at startup). Hovering over a row shows
where that setting is normally set.
"""

import locale
import logging
import os

from gi.repository import Gdk, Gtk, Pango

from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui.utils import is_right_click

import envinsp_catalog as catalog

LOG = logging.getLogger(__name__)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

COL_SETTING, COL_VALUE, COL_TIP, COL_WEIGHT = range(4)


# ------------------------------------------------------------
# Reading the settings
# ------------------------------------------------------------
def _guarded(func):
    """func() as text; a failure is shown, never raised."""
    try:
        value = func()
    except Exception as exc:  # report, never break the tab
        LOG.debug("EnvironmentInspector: %s", exc)
        return _("unavailable")
    if value is None or value == "":
        return _("(not set)")
    return str(value)


def _safe_flag(func):
    """func() as a bool; False if it fails."""
    try:
        return bool(func())
    except Exception:
        return False


def _category(name):
    """The locale of one category (LC_TIME, ...), or "" if not on this system."""
    cat = getattr(locale, name, None)
    if cat is None:
        return _("not used on this system")
    return ".".join(part for part in locale.getlocale(cat) if part)


def _yes_no(flag):
    return _("Yes") if flag else _("No")


def _date_format():
    from gramps.gen.datehandler import get_date_formats

    formats = get_date_formats()
    index = config.get("preferences.date-format")
    label = formats[index] if 0 <= index < len(formats) else index
    return str(label).split("\x04")[-1]


def _calendar(key):
    from gramps.gen.lib.date import Date

    names = Date.ui_calendar_names
    index = config.get(key)
    return names[index] if 0 <= index < len(names) else index


def _name_format():
    from gramps.gen.display.name import displayer

    default = displayer.get_default_format()
    for number, name, _fmt, _act in displayer.get_name_format(
        also_default=True, only_active=False
    ):
        if number == default:
            return name
    return default


def _place_format():
    from gramps.gen.display.place import displayer

    formats = displayer.get_formats()
    index = config.get("preferences.place-format")
    return formats[index].name if 0 <= index < len(formats) else index


def _surname_guessing():
    from gramps.gui.configure import _surname_styles

    index = config.get("behavior.surname-guessing")
    return _surname_styles[index] if 0 <= index < len(_surname_styles) else index


def _paper():
    units = _("Metric") if config.get("preferences.paper-metric") else _("Inches")
    return "%s, %s" % (config.get("preferences.paper-preference"), units)


def _pyicu_version():
    try:
        import icu
    except ImportError:
        return _("not installed")
    return getattr(icu, "VERSION", _("installed"))


def _icu_version():
    try:
        import icu
    except ImportError:
        return _("not installed")
    return getattr(icu, "ICU_VERSION", _("unknown"))


def _gspell():
    """The Gspell module, or None (Gramps' own check: gramps.gui.spell)."""
    try:
        from gramps.gui.spell import HAVE_GSPELL
    except ImportError:
        return None
    if not HAVE_GSPELL:
        return None
    from gi.repository import Gspell

    return Gspell


def _dictionary():
    """The dictionary Gramps picks for a new editor, as gramps.gui.spell does."""
    gspell = _gspell()
    if gspell is None:
        return _("none (Gspell missing)")
    code = glocale.locale_code() or ""
    language = gspell.language_lookup(code[:5]) or gspell.language_lookup(code[:2])
    if language is None:
        language = gspell.language_get_default()
        if language is None:
            return _("none found")
        return "%s (%s) - %s" % (
            language.get_name(), language.get_code(), _("Gspell default")
        )
    return "%s (%s)" % (language.get_name(), language.get_code())


def _dictionary_mismatch():
    """True if the dictionary Gramps picks is not in the interface language."""
    gspell = _gspell()
    if gspell is None:
        return False
    code = glocale.locale_code() or ""
    language = gspell.language_lookup(code[:5]) or gspell.language_lookup(code[:2])
    if language is None:
        return False
    interface = catalog.session_language(glocale).split("_")[0]
    return language.get_code().split("_")[0] != interface


def _dictionaries():
    gspell = _gspell()
    if gspell is None:
        return _("none (Gspell missing)")
    codes = sorted(lang.get_code() for lang in gspell.language_get_available())
    return "%d: %s" % (len(codes), ", ".join(codes)) if codes else _("none")


def _gtk_direction():
    if Gtk.Widget.get_default_direction() == Gtk.TextDirection.RTL:
        return _("Right to left")
    return _("Left to right")


def _gramps_rtl():
    return _("Right to left") if getattr(glocale, "rtl_locale", False) else _("Left to right")


_ENV_TIPS = {
    "LANGUAGE": _(
        "A colon-separated list of interface languages, tried in order, for "
        "example LANGUAGE=de:en. It overrides LANG and LC_MESSAGES for the "
        "interface language. Set it in a terminal (LANGUAGE=de gramps) or in "
        "the Exec line of the Gramps desktop launcher."
    ),
    "LANG": _(
        "The default locale for every category that is not set on its own. "
        "Normally set by the desktop from its language and region settings."
    ),
    "LC_ALL": _(
        "Overrides LANG and every LC_ variable at once. Usually left unset; "
        "set it only for testing, for example LC_ALL=fr_FR.UTF-8 gramps."
    ),
    "LC_MESSAGES": _("The locale for interface text, when LANGUAGE is not set."),
    "LC_TIME": _("The locale for dates and times (month and day names)."),
    "LC_COLLATE": _("The locale for sorting."),
    "LC_NUMERIC": _("The locale for numbers (decimal separator)."),
    "LC_MONETARY": _("The locale for currency amounts."),
    "COLLATION": _(
        "Read by Gramps itself, only with PyICU installed: an ICU locale "
        "for sorting that overrides LC_COLLATE, for example COLLATION=sv. "
        "It can also choose a special sort order, such as the German phone "
        "book order: COLLATION=de_DE@collation=phonebook."
    ),
}
_ENV_WHERE = _(
    "Environment variables are read once, when Gramps starts. Set them in a "
    "terminal before the gramps command, in the desktop launcher, or (on "
    "Windows) in the system environment variables."
)


def settings_groups():
    """Return [(group title, [(setting, value, where it is set)])]."""
    desktop = _(
        "Normally set by the desktop region or formats settings. Overridden "
        "by the %(var)s environment variable, or by LC_ALL; when neither is "
        "set, LANG decides."
    )
    prefs = _("Edit > Preferences > %(tab)s > %(label)s.")
    sorting = glocale.get_collation()
    sorting += " (ICU)" if catalog.have_icu() else " " + _("(system, no PyICU)")
    return [
        (_("Language and Translation"), [
            (_("Translation Order"), _guarded(lambda: ":".join(glocale.language)),
             _("Chosen at startup: the LANGUAGE environment variable if it is "
               "set, else LC_MESSAGES or LANG, which follow the language of the "
               "desktop. The Language tab of this gramplet can choose a language "
               "for the next start.")),
            (_("Messages (LC_MESSAGES)"), _guarded(lambda: _category("LC_MESSAGES")),
             desktop % {"var": "LC_MESSAGES"}),
            (_("Encoding"), _guarded(lambda: glocale.encoding),
             _("The part of the locale after the dot, as in en_US.UTF-8. Comes "
               "from LANG or LC_ALL; Gramps expects UTF-8.")),
        ]),
        (_("Formats"), [
            (_("Dates (LC_TIME)"), _guarded(lambda: glocale.calendar),
             desktop % {"var": "LC_TIME"}
             + " " + _("A LANGUAGE override also changes it.")),
            (_("Date Handler"), _guarded(lambda: type(glocale.date_displayer).__name__),
             _("Chosen by Gramps from the Dates locale: it decides month names "
               "and how typed dates are read. Not set directly.")),
            (_("Numbers (LC_NUMERIC)"), _guarded(lambda: _category("LC_NUMERIC")),
             desktop % {"var": "LC_NUMERIC"}),
            (_("Currency (LC_MONETARY)"), _guarded(lambda: _category("LC_MONETARY")),
             desktop % {"var": "LC_MONETARY"}),
        ]),
        (_("Sorting"), [
            (_("Sorting (LC_COLLATE)"), sorting,
             desktop % {"var": "LC_COLLATE"}
             + " " + _("With PyICU, the COLLATION variable overrides it and can "
                       "choose a special sort order, for example "
                       "COLLATION=de_DE@collation=phonebook.")),
            (_("PyICU"), _guarded(_pyicu_version),
             _("Optional Python package (python3-pyicu on Fedora). Without it "
               "Gramps sorts with the system rules and warns at startup.")),
            (_("ICU"), _guarded(_icu_version),
             _("The ICU library that PyICU was built with.")),
        ]),
        (_("Spelling"), [
            (_("Spell Checker"), _guarded(lambda: _yes_no(config.get("behavior.spellcheck"))),
             prefs % {"tab": _("General"), "label": _("Enable spell checker")}),
            (_("Gspell"), _yes_no(_gspell() is not None),
             _("Optional library (gspell and its GObject introspection files). "
               "Without it the spell checker setting has no effect.")),
            (_("Dictionary"),
             _guarded(_dictionary)
             + ("  \u26a0 " + _("not the interface language")
                if _safe_flag(_dictionary_mismatch) else ""),
             _("Chosen when a note editor opens, from the system locale code "
               "(LANG: first en_US, then en), not from the interface language "
               "(LANGUAGE), so starting Gramps in another language does not "
               "change it. For one text box, choose another from the "
               "Language item of the right-click menu; Gramps does not "
               "remember that choice.")),
            (_("Installed Dictionaries"), _guarded(_dictionaries),
             _("Come from Hunspell or Aspell dictionary packages (on Fedora, "
               "hunspell-xx). Install one to add a language.")),
        ]),
        (_("Text Direction"), [
            (_("Interface (GTK)"), _guarded(_gtk_direction),
             _("Set by GTK from its own translation for the interface "
               "language. It follows the language; there is no separate "
               "setting.")),
            (_("Gramps"), _guarded(_gramps_rtl),
             _("Set by Gramps from a fixed list of right-to-left languages "
               "(Arabic and Hebrew). It follows the language; there is no "
               "separate setting.")),
        ]),
        (_("Gramps Preferences"), [
            (_("Date Format"), _guarded(_date_format),
             prefs % {"tab": _("Data"), "label": _("Date format")}
             + " " + _("A change takes effect after Gramps restarts.")),
            (_("Calendar on Input"),
             _guarded(lambda: _calendar("preferences.calendar-format-input")),
             prefs % {"tab": _("Data"), "label": _("Calendar on input")}),
            (_("Calendar on Reports"),
             _guarded(lambda: _calendar("preferences.calendar-format-report")),
             prefs % {"tab": _("Data"), "label": _("Calendar on reports")}),
            (_("Name Format"), _guarded(_name_format),
             prefs % {"tab": _("Data"), "label": _("Name format")}),
            (_("Place Format"), _guarded(_place_format),
             prefs % {"tab": _("Data"), "label": _("Place format")}),
            (_("Surname Guessing"), _guarded(_surname_guessing),
             prefs % {"tab": _("Data"), "label": _("Surname guessing")}),
            (_("Paper"), _guarded(_paper),
             _("The Paper Options tab of any report dialog; the last choice "
               "is remembered for the next report.")),
        ]),
        (_("Environment Variables"), [
            ("$" + var, os.environ.get(var) or _("(not set)"),
             _ENV_TIPS[var] + " " + _ENV_WHERE)
            for var in _ENV_TIPS
        ]),
    ]


# ------------------------------------------------------------
# LocaleSettings
# ------------------------------------------------------------
class LocaleSettings(Gtk.Box):
    """The Locale Settings tab."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_border_width(6)
        hint = Gtk.Label(
            label=_("Hover over a setting to see where it is set."), xalign=0.0
        )
        self.pack_start(hint, False, False, 0)

        self.store = Gtk.TreeStore(str, str, str, int)
        view = Gtk.TreeView(model=self.store)
        self.view = view
        for title, index in ((_("Setting"), COL_SETTING), (_("Value"), COL_VALUE)):
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=index, weight=COL_WEIGHT)
            column.set_resizable(True)
            if index == COL_VALUE:
                renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
                column.set_expand(True)
            view.append_column(column)
        view.set_tooltip_column(COL_TIP)
        view.set_enable_search(False)
        view.connect("button-press-event", self.cb_button_press)

        # Right-click menu. The labels are the ones of the Grouped People
        # view, so the Gramps translation is used and translators have
        # nothing new to translate.
        self.menu = Gtk.Menu()
        for label, callback in (
            (_("Expand all Nodes"), lambda *_a: self.view.expand_all()),
            (_("Collapse all Nodes"), lambda *_a: self.view.collapse_all()),
        ):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", callback)
            self.menu.append(item)
        self.menu.show_all()
        self.menu.attach_to_widget(view, None)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.set_vexpand(True)
        scroll.add(view)
        self.pack_start(scroll, True, True, 0)

        copy = Gtk.Button(label=_("Copy table"))
        copy.connect("clicked", self.cb_copy)
        self.pack_start(copy, False, False, 0)
        # Preferences can change while Gramps runs: re-read when shown.
        self.connect("map", self.cb_refresh)

    def cb_button_press(self, _view, event):
        if is_right_click(event):
            self.menu.popup_at_pointer(event)
            return True
        return False

    def cb_refresh(self, *obj):
        # Keep groups the user collapsed collapsed when values are re-read.
        collapsed = {
            row[COL_SETTING] for row in self.store
            if not self.view.row_expanded(row.path)
        }
        self.store.clear()
        for title, rows in settings_groups():
            parent = self.store.append(None, [title, "", "", Pango.Weight.BOLD])
            for setting, value, tip in rows:
                # Tooltips are Pango markup: escape the text.
                tip = tip.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                self.store.append(parent, [setting, value, tip, Pango.Weight.NORMAL])
        for row in self.store:
            if row[COL_SETTING] not in collapsed:
                self.view.expand_row(row.path, False)

    def cb_copy(self, *obj):
        lines = []
        for group in self.store:
            lines.append("[%s]" % group[COL_SETTING])
            for row in group.iterchildren():
                lines.append("%s: %s" % (row[COL_SETTING], row[COL_VALUE]))
            lines.append("")
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("\n".join(lines).strip(), -1)
        clipboard.store()
