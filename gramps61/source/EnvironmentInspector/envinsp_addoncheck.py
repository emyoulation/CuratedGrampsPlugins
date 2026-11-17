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
Environment Inspector - addon translation check (no GTK).

glocale.get_addon_translator() raises ValueError when an addon has no
translation for any language of the session ("No usable translations in
da for addon"). A module that calls it without catching that error does
not load at all, so the addon is missing in that language, and Gramps only
writes a "Plugin error" warning (or nothing, for some plugin types).
English sessions never fail, because Gramps accepts English without a
translation, so developers rarely see this.

It runs for the language of the current session (shown on the Language
tab) and again after a restart in another language.

check_addons() looks at every addon folder in the user plugin folder:
whether it has a translation (locale/<lang>/LC_MESSAGES/addon.mo) for the
session languages, and which of its modules call get_addon_translator()
without a try/except that catches ValueError. The result is written as a
plain-text report.
"""

import ast
import gettext
import os
import time

DOMAIN = "addon"


def _usable(localedir, languages):
    """The language get_addon_translator() would use, or "" if it fails."""
    for lang in languages:
        if os.path.isdir(localedir) and gettext.find(DOMAIN, localedir, [lang]):
            return lang
        if lang.startswith(("en", "C")):
            return "en"
    return ""


def english_session(languages):
    """True when the session uses English, where every addon loads."""
    return _usable("", list(languages)) == "en"


def _catches_value_error(handler):
    """True if an except clause catches ValueError (or everything)."""
    if handler.type is None:
        return True
    names = []
    types = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in types:
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
    return any(name in ("ValueError", "Exception", "BaseException") for name in names)


def unguarded_calls(path):
    """
    Line numbers of get_addon_translator() calls in a Python file that no
    enclosing try/except catches ValueError for.

    :returns: (lines, error): error is a message if the file cannot be read.
    """
    try:
        with open(path, encoding="utf-8-sig") as handle:  # some files start with a BOM
            tree = ast.parse(handle.read(), filename=path)
    except (OSError, SyntaxError, UnicodeDecodeError, ValueError) as err:
        return [], str(err)
    lines = []

    def visit(node, guarded):
        if isinstance(node, ast.Try) or type(node).__name__ == "TryStar":
            body_guarded = guarded or any(_catches_value_error(h) for h in node.handlers)
            for child in node.body:
                visit(child, body_guarded)
            for child in node.handlers + node.orelse + node.finalbody:
                visit(child, guarded)
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_addon_translator"
            and not guarded
        ):
            lines.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(tree, False)
    return sorted(lines), ""


def _addon_roots(plugins_dir):
    """
    Every folder holding a .gpr.py file, at any depth, as Gramps finds
    addons (it walks the plugin folder recursively). A folder such as a
    stray copy "6.1/" is not an addon itself; the addons inside it are.
    """
    roots = []
    for root, dirs, files in os.walk(plugins_dir):
        dirs[:] = sorted(
            d for d in dirs if d not in ("__pycache__", "locale", "po") and not d.startswith(".")
        )
        if any(name.endswith(".gpr.py") for name in files):
            roots.append(root)
    return roots


def _addon_modules(root, roots):
    """The .py files of one addon, without those of addons nested in it."""
    nested = {r for r in roots if r != root and r.startswith(root + os.sep)}
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d
            for d in dirs
            if d not in ("__pycache__", "locale", "po")
            and os.path.join(current, d) not in nested
        )
        for fname in sorted(files):
            if fname.endswith(".py") and not fname.endswith(".gpr.py"):
                yield os.path.join(current, fname)


def registered_dirs():
    """
    The folders of every plugin this Gramps registered. Gramps also scans
    folders meant for another Gramps version (such as a "6.1" copy inside
    the 6.0 plugin folder), but it does not register a plugin whose
    gramps_target_version is for another version, so those never load.
    :returns: a set of real paths, or None if the registry is unavailable.
    """
    try:
        from gramps.gen.plug._pluginreg import PTYPE, PluginRegister
    except ImportError:
        return None
    pgr = PluginRegister.get_instance()
    found = set()
    for ptype in PTYPE:
        for pdata in pgr.type_plugins(ptype):
            folder = getattr(pdata, "fpath", None) or getattr(pdata, "directory", None)
            if folder:
                found.add(os.path.realpath(folder))
    return found


def check_addons(plugins_dir, languages, registered=None):
    """
    :param plugins_dir: the user plugin folder (gramps.gen.const.USER_PLUGINS).
    :param languages: the session languages (glocale.language).
    :param registered: folders of registered plugins (registered_dirs()),
        or None to check every addon folder on disk. A folder that is not
        in it is listed with "registered": False and not checked.
    :returns: one dict per addon folder: name (path relative to
        plugins_dir), path, language (the translation used, or ""),
        risky ([(file, [lines])]), errors.
    """
    results = []
    roots = _addon_roots(plugins_dir)
    for folder in roots:
        if registered is not None and os.path.realpath(folder) not in registered:
            results.append(
                {
                    "name": os.path.relpath(folder, plugins_dir),
                    "path": folder,
                    "registered": False,
                    "language": "",
                    "risky": [],
                    "errors": [],
                }
            )
            continue
        risky, errors, calls = [], [], False
        for path in _addon_modules(folder, roots):
            try:
                with open(path, encoding="utf-8", errors="replace") as handle:
                    if "get_addon_translator" not in handle.read():
                        continue
            except OSError as err:
                errors.append("%s: %s" % (os.path.relpath(path, folder), err))
                continue
            calls = True
            lines, error = unguarded_calls(path)
            if error:
                errors.append("%s: %s" % (os.path.relpath(path, folder), error))
            if lines:
                risky.append((os.path.relpath(path, folder), lines))
        if not calls:
            continue  # uses only Gramps' own translations
        results.append(
            {
                "name": os.path.relpath(folder, plugins_dir),
                "path": folder,
                "registered": True,
                "language": _usable(os.path.join(folder, "locale"), languages),
                "risky": risky,
                "errors": errors,
            }
        )
    results.sort(key=lambda item: item["name"].casefold())
    return results


WEBLATE_URL = "https://hosted.weblate.org/projects/gramps-project/addons/"

DISCUSSION_URL = (
    "https://gramps.discourse.group/t/get-addon-translator-makes-addons-fail-"
    "to-load-in-languages-where-they-are-not-translated/10230"
)


def core_has_fallback():
    """
    True if get_addon_translator() in this Gramps falls back to the Gramps
    translation instead of raising ValueError (the proposed core fix, or
    an addon that patches it in). Tested by asking for the translation of
    an empty folder, which has none.
    :returns: True, False, or None when the session language is English
        (English never fails, so it cannot be tested).
    """
    import tempfile

    from gramps.gen.const import GRAMPS_LOCALE as glocale

    if english_session(glocale.language):
        return None
    with tempfile.TemporaryDirectory(prefix="envinsp-") as folder:
        try:
            glocale.get_addon_translator(os.path.join(folder, "probe.py"))
        except ValueError:
            return False
        except Exception:  # pylint: disable=broad-except
            return None
    return True


def _lines(item):
    return "; ".join(
        "%s line %s" % (fname, ", ".join(str(n) for n in lines))
        for fname, lines in item["risky"]
    )


def report(results, languages, plugins_dir, fallback=None):
    """
    The plain-text report, and the number of addons that fail to load.

    :param fallback: core_has_fallback(): with the core fallback, an
        untranslated addon loads (in English) even if it does not catch the
        error, so nothing fails.
    """
    lang_str = ":".join(languages) or "(none)"
    skipped = [r for r in results if not r["registered"]]
    results = [r for r in results if r["registered"]]
    untranslated = [r for r in results if not r["language"]]
    failing = [] if fallback else [r for r in untranslated if r["risky"]]
    safe = [r for r in untranslated if r not in failing]
    translated = [r for r in results if r["language"]]
    at_risk = [r for r in translated if r["risky"]]
    fallback_text = {
        True: "applied (untranslated addons load, in English)",
        False: "not applied",
        None: "not tested (English session)",
    }[fallback]
    out = [
        "Environment Inspector addon translation check, %s UTC"
        % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "Session languages: %s" % lang_str,
        "Addon folder: %s" % plugins_dir,
        "Gramps fallback for untranslated addons: %s" % fallback_text,
        "",
    ]
    if failing:
        out += [
            "=" * 72,
            "ADDONS THAT DO NOT LOAD IN THIS LANGUAGE: %d" % len(failing),
            "=" * 72,
        ]
        out += ["  ** %s  (%s)" % (item["name"], _lines(item)) for item in failing]
        out += [
            "",
            "These failures are unnecessary. Each addon has no translation for",
            "this language, and Gramps raises an error instead of showing the",
            "addon in English. Fix it in Gramps (see the discussion), or in each",
            "addon by catching the error (see the end of this file):",
            "  " + DISCUSSION_URL,
            "=" * 72,
        ]
    else:
        out.append("All registered addons load in this language.")
    out += [
        "",
        "No translation, shown in English: %d" % len(safe),
    ]
    out += ["  %s" % item["name"] for item in safe]
    if safe:
        out += [
            "These addons need a translation for this language. Addons from the",
            "Gramps addons collection are translated on Weblate:",
            "  " + WEBLATE_URL,
        ]
    out += ["", "Translated: %d" % len(translated)]
    out += ["  %s (%s)" % (item["name"], item["language"]) for item in translated]
    if at_risk and not fallback:
        out += [
            "",
            "Translated here, but would not load in a language they lack: %d"
            % len(at_risk),
        ]
        out += ["  %s  (%s)" % (item["name"], _lines(item)) for item in at_risk]
    if skipped:
        out += [
            "",
            "Not checked, because this Gramps did not register them (made for another "
            "Gramps version, or hidden by a requirement): %d" % len(skipped),
        ]
        out += ["  %s" % item["name"] for item in skipped]
    problems = [r for r in results if r["errors"]]
    if problems:
        out += ["", "Files that could not be checked:"]
        for item in problems:
            out += ["  %s: %s" % (item["name"], err) for err in item["errors"]]
    if failing or (at_risk and not fallback):
        out += [
            "",
            "Fix in an addon module:",
            "    try:",
            "        _trans = glocale.get_addon_translator(__file__)",
            "    except ValueError:",
            "        _trans = glocale.translation",
            "    _ = _trans.gettext",
        ]
    return "\n".join(out) + "\n", len(failing)


def write_summary(log_path, plugins_dir, languages, registered=None):
    """
    Check the addons, write the report and count the results.
    :returns: dict with failing (addons that do not load in this language),
        english (no translation, shown in English), translated, and
        fallback (core_has_fallback()).
    """
    fallback = core_has_fallback()
    results = check_addons(plugins_dir, languages, registered)
    text, failing = report(results, languages, plugins_dir, fallback)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    checked = [r for r in results if r["registered"]]
    untranslated = sum(1 for r in checked if not r["language"])
    return {
        "failing": failing,
        "english": untranslated - failing,
        "translated": len(checked) - untranslated,
        "fallback": fallback,
    }


def write_report(log_path, plugins_dir, languages, registered=None):
    """
    Check the addons and write the report.
    :returns: the number of addons that do not load in this language.
    """
    return write_summary(log_path, plugins_dir, languages, registered)["failing"]
