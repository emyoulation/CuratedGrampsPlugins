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
Environment Inspector - translation catalog matching (no GTK).

Looks up interface text that is already on screen in the translation
catalog of another Gramps language. Kept free of GTK so it can be tested
on its own.
"""

import re

from gramps.gen.datehandler import LANG_TO_DISPLAY
from gramps.gen.display.name import NameDisplay
from gramps.gen.lib import Date, Name, Surname
from gramps.gen.utils import grampslocale as _grampslocale
from gramps.gen.utils.grampslocale import GrampsLocale

# printf-style placeholders as used in Gramps msgids: %s, %d, %(name)s ...
_PLACEHOLDER = re.compile(r"%(?:\((\w+)\))?[-#0 +]?\d*(?:\.\d+)?[sdifrxX]")
_PERCENT = "\x00PCT\x00"

STATUS_TRANSLATED = "translated"
STATUS_SAME = "same"
STATUS_PATTERN = "pattern"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_MISSING = "not in catalog"


def norm(text):
    """Normalize UI text for matching: no mnemonic underscores, tidy spaces."""
    if not text:
        return ""
    return " ".join(text.replace("_", "").split())


def _base_msgid(key):
    """Strip gettext (\\x04) and Gramps sgettext ('|') contexts from a msgid."""
    if "\x04" in key:
        key = key.split("\x04", 1)[1]
    if "|" in key:
        key = key.rsplit("|", 1)[1]
    return key


def _iter_catalog(translation):
    """Yield (msgid, msgstr) pairs from a translation and its fallbacks."""
    trans = translation
    while trans is not None:
        for key, value in (getattr(trans, "_catalog", None) or {}).items():
            if isinstance(key, tuple):  # plural forms: (msgid, index)
                if key[1] != 0:
                    continue
                key = key[0]
            if isinstance(key, str) and key and isinstance(value, str):
                yield key, value
        trans = getattr(trans, "_fallback", None)


def is_english(locale):
    lang = (locale.lang or "")[:2]
    return lang == "en" or lang == "C" or not lang


# ------------------------------------------------------------
# Matcher
# ------------------------------------------------------------
class CatalogMatcher:
    """
    Map text shown in the current session language to the preview language.

    target index: normalized msgid -> list of normalized translations
    current map:  normalized on-screen text -> normalized msgid
    patterns:     regexes for msgids with placeholders, in on-screen form
    """

    def __init__(self, current_locale, target_locale):
        self.target = {}
        for key, value in _iter_catalog(target_locale.translation):
            msgid = norm(_base_msgid(key))
            self.target.setdefault(msgid, []).append(norm(value))

        self.current = {}
        current_english = is_english(current_locale)
        display_forms = {}
        if not current_english:
            for key, value in _iter_catalog(current_locale.translation):
                msgid = norm(_base_msgid(key))
                self.current.setdefault(norm(value), msgid)
                display_forms.setdefault(msgid, norm(value))

        self.patterns = []
        for msgid in self.target:
            if "%" not in msgid:
                continue
            shown = msgid if current_english else display_forms.get(msgid, msgid)
            compiled = self._compile(shown)
            if compiled:
                self.patterns.append((compiled[0], compiled[1], msgid))
        # Longer patterns first, so specific text wins over generic text.
        self.patterns.sort(key=lambda item: -len(item[0].pattern))

    @staticmethod
    def _compile(shown):
        text = shown.replace("%%", _PERCENT)
        keys = []
        parts = []
        pos = 0
        literal_len = 0
        for match in _PLACEHOLDER.finditer(text):
            literal = text[pos : match.start()]
            literal_len += sum(ch.isalpha() for ch in literal)
            parts.append(re.escape(literal.replace(_PERCENT, "%")))
            parts.append("(.+?)")
            keys.append(match.group(1) or len(keys))
            pos = match.end()
        tail = text[pos:]
        literal_len += sum(ch.isalpha() for ch in tail)
        parts.append(re.escape(tail.replace(_PERCENT, "%")))
        # Skip "%s", "%s: %s" and similar: they would match almost anything.
        if not keys or len(keys) > 4 or literal_len < 4:
            return None
        return re.compile("^" + "".join(parts) + "$", re.S), keys

    @staticmethod
    def _fill(template, keys, values):
        named = {k: v for k, v in zip(keys, values) if isinstance(k, str)}
        positional = [v for k, v in zip(keys, values) if not isinstance(k, str)]
        counter = iter(positional)

        def repl(match):
            name = match.group(1)
            if name:
                return named.get(name, match.group(0))
            return next(counter, match.group(0))

        text = template.replace("%%", _PERCENT)
        return _PLACEHOLDER.sub(repl, text).replace(_PERCENT, "%")

    def lookup(self, shown):
        """
        Return (preview text, status, original) for text shown on screen.

        original is the untranslated (English) source text, or "" when the
        text is not in the catalog.
        """
        text = norm(shown)
        if not text:
            return "", STATUS_MISSING, ""
        msgid = self.current.get(text, text)
        values = self.target.get(msgid)
        if values:
            preview = values[0]
            if len(set(values)) > 1:
                return preview, STATUS_AMBIGUOUS, msgid
            status = STATUS_SAME if preview == text else STATUS_TRANSLATED
            return preview, status, msgid
        for regex, keys, pattern_msgid in self.patterns:
            match = regex.match(text)
            if match:
                values = match.groups()
                template = self.target[pattern_msgid][0]
                return (
                    self._fill(template, keys, values),
                    STATUS_PATTERN,
                    self._fill(pattern_msgid, keys, values),
                )
        return "", STATUS_MISSING, ""


# ------------------------------------------------------------
# Samples (dates, names, sorting, common words)
# ------------------------------------------------------------
COMMON_MSGIDS = [
    "Person", "Family", "Event", "Place", "Source", "Citation",
    "Repository", "Media", "Note", "Birth", "Death", "Marriage",
    "Burial", "Baptism", "Father", "Mother", "Child", "Children",
    "Spouse", "Name", "Date", "Description", "Edit", "Remove", "Add",
    "Help", "Close", "Cancel",
]

SORT_SAMPLE = [
    "Zeller", "Ångström", "Æbelø", "Øster", "Åberg", "Ärger", "Ober",
    "Çelik", "Öberg", "Čapek", "Lindqvist", "Ñúñez", "Ábel", "Aaron",
]


def make_locale(lang):
    """A separate GrampsLocale for lang; the session locale is unchanged."""
    return GrampsLocale(lang=lang)


def have_icu():
    return bool(getattr(_grampslocale, "HAVE_ICU", False))


def date_displayer(locale, fmt):
    """A date displayer for locale and format index, translated for locale."""
    cal = locale.calendar or locale.lang or "C"
    cls = (
        LANG_TO_DISPLAY.get(cal)
        or LANG_TO_DISPLAY.get(cal[:2])
        or LANG_TO_DISPLAY["C"]
    )
    return cls(format=fmt, blocale=locale)


def _sample_dates():
    exact = Date()
    exact.set_yr_mon_day(1890, 3, 14)
    about = Date()
    about.set(Date.QUAL_NONE, Date.MOD_ABOUT, Date.CAL_GREGORIAN, (0, 0, 1850, False))
    before = Date()
    before.set(Date.QUAL_NONE, Date.MOD_BEFORE, Date.CAL_GREGORIAN, (0, 6, 1900, False))
    span = Date()
    span.set(
        Date.QUAL_NONE,
        Date.MOD_RANGE,
        Date.CAL_GREGORIAN,
        (0, 0, 1800, False, 0, 0, 1810, False),
    )
    return exact, [("about", about), ("before", before), ("between", span)]


_ENGLISH = []


def english_locale():
    """A US English GrampsLocale (untranslated), made once."""
    if not _ENGLISH:
        _ENGLISH.append(make_locale("en"))
    return _ENGLISH[0]


def sample_rows(current_locale, target_locale):
    """
    Return rows (kind, original, current, preview, status) for the Samples
    list; original is the untranslated (English) form.
    """
    rows = []
    english = english_locale()
    cur_t = current_locale.translation
    tgt_t = target_locale.translation
    for msgid in COMMON_MSGIDS:
        cur = cur_t.sgettext(msgid)
        tgt = tgt_t.sgettext(msgid)
        status = STATUS_TRANSLATED if tgt != msgid else STATUS_SAME
        rows.append(("Word", msgid, cur, tgt, status))

    exact, modified = _sample_dates()
    cur_disp = date_displayer(current_locale, 0)
    for index, label in enumerate(cur_disp.formats):
        try:
            orig = date_displayer(english, index).display(exact)
            cur = date_displayer(current_locale, index).display(exact)
            tgt = date_displayer(target_locale, index).display(exact)
        except Exception as exc:  # a format a displayer cannot render
            orig, cur, tgt = "", str(exc), ""
        label = str(label).split("\x04")[-1]  # drop a gettext context
        rows.append((f"Date format {index}: {label}", orig, cur, tgt, ""))
    for label, date in modified:
        orig = date_displayer(english, 0).display(date)
        cur = date_displayer(current_locale, 0).display(date)
        tgt = date_displayer(target_locale, 0).display(date)
        rows.append((f"Date ({label})", orig, cur, tgt, ""))

    name = Name()
    name.set_first_name("Johann Sebastian")
    surname = Surname()
    surname.set_surname("Bach")
    name.add_surname(surname)
    rows.append(
        (
            "Name",
            NameDisplay(xlocale=english).display_name(name),
            NameDisplay(xlocale=current_locale).display_name(name),
            NameDisplay(xlocale=target_locale).display_name(name),
            "",
        )
    )

    orig_sorted = sorted(SORT_SAMPLE, key=english.sort_key)
    cur_sorted = sorted(SORT_SAMPLE, key=current_locale.sort_key)
    tgt_sorted = sorted(SORT_SAMPLE, key=target_locale.sort_key)
    note = "" if have_icu() else "PyICU missing: system sorting"
    for index, (orig, cur, tgt) in enumerate(
        zip(orig_sorted, cur_sorted, tgt_sorted), start=1
    ):
        rows.append((f"Sort order {index}", orig, cur, tgt, note))
    return rows


# ------------------------------------------------------------
# Gramps Translations table (Language tab)
# ------------------------------------------------------------
# Gramps pairs each language with a Windows locale "Language_Country" in
# win32locale._LOCALE_NAMES. These are the countries used there; the flag
# shows that region. A translation whose own code names a region
# (pt_BR, zh_TW, de_AT ...) uses that region instead.
_COUNTRY_ISO = {
    "Albania": "AL", "Austria": "AT", "Brazil": "BR", "Bulgaria": "BG",
    "China": "CN", "Croatia": "HR", "Czech Republic": "CZ", "Denmark": "DK",
    "Finland": "FI", "France": "FR", "Germany": "DE", "Greece": "GR",
    "Hong Kong": "HK", "Hungary": "HU", "Iran": "IR", "Israel": "IL",
    "Italy": "IT", "Japan": "JP", "Korea": "KR", "Lithuania": "LT",
    "Netherlands": "NL", "Norway": "NO", "Poland": "PL", "Portugal": "PT",
    "Romania": "RO", "Russia": "RU", "Saudi Arabia": "SA",
    "Serbia and Montenegro": "RS", "Slovakia": "SK", "Slovenia": "SI",
    "Spain": "ES", "Sweden": "SE", "Taiwan": "TW", "Turkey": "TR",
    "Ukraine": "UA", "United Kingdom": "GB", "United States": "US",
    "Vietnam": "VN",
}


def flag_emoji(iso):
    """Regional-indicator flag emoji for a two-letter region code."""
    if len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in iso.upper())


def _locale_names():
    try:
        from gramps.gen.utils.win32locale import _LOCALE_NAMES
    except ImportError:
        return {}
    return _LOCALE_NAMES


def _icu_endonym(code):
    try:
        from icu import Locale
    except ImportError:
        return ""
    loc = Locale(code)
    return str(loc.getDisplayName(loc))


def _catalog_size(translation):
    return sum(1 for key, _value in _iter_catalog(translation) if key)


def language_rows(current_locale, locale_cache=None):
    """
    Return one dict per installed Gramps translation:
    code, name (in the session language), endonym, region (ISO code),
    region_source ("code" or "Gramps"), flag, strings (catalog size or -1).
    """
    names = {code: name for name, code in current_locale.get_language_dict().items()}
    table = _locale_names()
    cache = locale_cache if locale_cache is not None else {}
    rows = []
    for code in current_locale.get_available_translations():
        entry = table.get(code) or table.get(code[:2])
        english = entry[2] if entry else code
        region, source = "", ""
        parts = code.split("_")
        if len(parts) > 1 and len(parts[1]) == 2:
            region, source = parts[1].upper(), "code"
        elif entry and entry[0] and "_" in entry[0]:
            region = _COUNTRY_ISO.get(entry[0].split("_", 1)[1], "")
            source = "Gramps" if region else ""
        endonym, strings = english, -1
        if code != "en":
            try:
                if code not in cache:
                    cache[code] = make_locale(code)
                translation = cache[code].translation
                endonym = translation.gettext(english)
                strings = _catalog_size(translation)
            except Exception:  # a broken catalog must not break the table
                endonym = ""
            if endonym == english and not code.startswith("en"):
                endonym = _icu_endonym(code) or endonym
        rows.append(
            {
                "code": code,
                "name": names.get(code, english),
                "endonym": endonym,
                "region": region,
                "region_source": source,
                "flag": flag_emoji(region),
                "strings": strings,
            }
        )
    return rows


def session_language(locale):
    """The translation code the session uses (for example "en" or "pt_BR")."""
    languages = getattr(locale, "language", None) or []
    if languages:
        return languages[0]
    return (locale.lang or "en").split(".")[0].split("_")[0]


def endonym(code, current_locale, locale_cache=None):
    """The name of a language in that language, from its own catalog."""
    table = _locale_names()
    entry = table.get(code) or table.get(code[:2])
    english = entry[2] if entry else code
    if code == "en" or code == session_language(current_locale):
        return current_locale.translation.gettext(english)
    cache = locale_cache if locale_cache is not None else {}
    try:
        if code not in cache:
            cache[code] = make_locale(code)
        name = cache[code].translation.gettext(english)
    except Exception:
        name = english
    if name == english and not code.startswith("en"):
        name = _icu_endonym(code) or name
    return name


def english_name(code):
    """The English name of a language (the exonym), from the Gramps table."""
    table = _locale_names()
    entry = table.get(code) or table.get(code[:2])
    return entry[2] if entry else ""
