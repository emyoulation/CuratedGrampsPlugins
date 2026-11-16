"""
Addon Locale Fix: a monkey patch for GrampsLocale.get_addon_translator().

Fixes three long-standing problems (Gramps 4.0 through 6.1 and master):

1. Crash. When an addon has no .mo for any language in the user's list and
   the list holds no "en" (e.g. a plain LANG=de_DE.UTF-8 session), Gramps
   raises ValueError("No usable translations in de for addon") and the
   addon fails to load.  Most addons wrap the call in try/except; this makes
   the guard unnecessary.

2. Priority. Gramps consults its own translation first and the addon's .mo
   only as a fallback, so an addon cannot translate a string that Gramps
   core also translates.  Now the addon's .mo comes first, then Gramps.
   Priority is only changed when both are in the same language; otherwise
   the stock order (Gramps first) is kept, so languages are never mixed
   within one phrase.

3. Before Gramps 5.2 the `languages` argument (used by reports written in
   another language) was ignored for the Gramps part of the translator.

Cooperates with other wrappers that follow the __wrapped__ convention (such
as Translation Updater): they keep working whichever loads first.

Addons that load at startup and were imported before this fix ran are
retried once Gramps finishes starting (GUI only).

Python 2.7 compatible on purpose: Gramps 4.0 and 4.1 supported it.
"""

import gettext
import logging
import os
import sys

from gramps.gen.utils.grampslocale import GrampsLocale

LOG = logging.getLogger(".AddonLocaleFix")

_MARK = "_addon_locale_fix"
_TRANSLATIONS = getattr(sys.modules[GrampsLocale.__module__], "GrampsTranslations")


# ------------------------------------------------------------------------
# Helpers that work with every Gramps version
# ------------------------------------------------------------------------
def _func(obj):
    """Plain function behind a (Python 2 unbound) method."""
    return getattr(obj, "__func__", getattr(obj, "im_func", obj))


def _lang_of(trans):
    """Language code of a Gramps translator ('en' for the null one)."""
    try:
        return trans.language() or "en"
    except Exception:  # pylint: disable=broad-except
        return getattr(trans, "lang", None) or getattr(trans, "_language", None) or "en"


def _set_lang(trans, lang):
    """5.2+ uses .lang, earlier versions ._language; set both."""
    trans.lang = lang
    trans._language = lang  # pylint: disable=protected-access


def _core_translator(locale_obj, languages):
    """Gramps translator for the requested languages, never raising."""
    try:
        return locale_obj._get_translation(  # pylint: disable=protected-access
            languages=languages or None
        )
    except ValueError:
        pass
    try:
        return locale_obj._get_translation()  # pylint: disable=protected-access
    except ValueError:
        return locale_obj.translation


def _addon_translation(domain, path, languages):
    """First addon .mo for the language list, stopping at English."""
    if not path or not os.path.isdir(path):
        return None
    for lang in languages:
        if not lang or lang.startswith(("en", "C")):
            return None  # English wins from here: msgids are English
        if gettext.find(domain, path, [lang]):
            trans = gettext.translation(
                domain, localedir=path, languages=[lang], class_=_TRANSLATIONS
            )
            _set_lang(trans, lang)
            return trans
    return None


# ------------------------------------------------------------------------
# The fixed method
# ------------------------------------------------------------------------
def fixed_get_addon_translator(self, filename=None, domain="addon", languages=None):
    """
    Translator for an addon: the addon's own .mo first, then Gramps.

    Same signature and return type as the stock method, but never raises
    for a missing addon translation.
    """
    langs = list(languages or self.language or ["en"])
    core = _core_translator(self, langs)
    path = self.localedir
    if filename:
        path = os.path.join(os.path.dirname(os.path.abspath(filename)), "locale")
    addon = _addon_translation(domain, path, langs)
    if addon is None:
        return core
    if _lang_of(addon) == _lang_of(core):
        addon.add_fallback(core)
        return addon
    # Different languages: keep the stock order so phrases stay in one language.
    core.add_fallback(addon)
    return core


setattr(fixed_get_addon_translator, _MARK, True)


# ------------------------------------------------------------------------
# Installing the patch
# ------------------------------------------------------------------------
def install():
    """
    Put the fixed method in place (idempotent).

    * Nothing patched yet: replace the method.
    * Cooperative wrappers (expose __wrapped__ and call through it): point
      the innermost wrapper at the fix, so the wrappers keep working.
    * Unknown wrapper: wrap it once more, falling back to the fix when it
      raises ValueError.
    """
    current = _func(GrampsLocale.__dict__["get_addon_translator"])
    parent, node = None, current
    seen = set()
    while getattr(node, "__wrapped__", None) is not None and id(node) not in seen:
        seen.add(id(node))
        parent, node = node, _func(node.__wrapped__)
    if getattr(node, _MARK, False):
        return "already installed"
    if parent is not None:
        parent.__wrapped__ = fixed_get_addon_translator
        return "under %s" % getattr(parent, "__name__", "a wrapper")
    if node.__module__ == GrampsLocale.__module__:
        GrampsLocale.get_addon_translator = fixed_get_addon_translator
        return "replaced"

    def safety_net(self, filename=None, domain="addon", languages=None):
        try:
            return current(self, filename, domain, languages)
        except ValueError:
            return fixed_get_addon_translator(self, filename, domain, languages)

    setattr(safety_net, _MARK, True)
    GrampsLocale.get_addon_translator = safety_net
    return "safety net around %s" % getattr(current, "__module__", "?")


def probe():
    """
    True when get_addon_translator survives a language nobody has.

    The stock method raises ValueError for this in every Gramps version, so
    this proves the fix is reachable through any wrappers in front of it.
    """
    from gramps.gen.const import GRAMPS_LOCALE as glocale

    missing = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no-such-addon")
    try:
        glocale.get_addon_translator(
            os.path.join(missing, "probe.py"), languages=["zz_ZZ"]
        )
    except ValueError:
        return False
    return True


def install_checked():
    """install(), then fall back to a safety net if the probe still fails."""
    how = install()
    if probe():
        return how
    current = _func(GrampsLocale.__dict__["get_addon_translator"])

    def safety_net(self, filename=None, domain="addon", languages=None):
        try:
            return current(self, filename, domain, languages)
        except ValueError:
            return fixed_get_addon_translator(self, filename, domain, languages)

    setattr(safety_net, _MARK, True)
    GrampsLocale.get_addon_translator = safety_net
    return "%s; probe failed, safety net added" % how


# ------------------------------------------------------------------------
# Retry startup addons that crashed before the fix was installed
# ------------------------------------------------------------------------
def _uses_addon_translator(pdata):
    try:
        with open(os.path.join(pdata.fpath, pdata.fname)) as fp:
            return "get_addon_translator" in fp.read()
    except (IOError, OSError, UnicodeDecodeError, TypeError):
        return False


def retry_failed_startup_addons(dbstate, uistate):
    """Load startup (load_on_reg) addons that are still not loaded."""
    try:
        from gramps.gen.config import config
        from gramps.gen.plug import BasePluginManager
        from gramps.gen.plug._pluginreg import PluginRegister
    except ImportError:
        return False
    pmgr = BasePluginManager.get_instance()
    try:
        hidden = config.get("plugin.hiddenplugins")
    except Exception:  # pylint: disable=broad-except
        hidden = []
    for pdata in PluginRegister.get_instance().filter_load_on_reg():
        if pdata.id in hidden or pmgr.is_loaded(pdata.id):
            continue
        if not _uses_addon_translator(pdata):
            continue
        module = pmgr.load_plugin(pdata)
        if not module:
            continue
        LOG.info("Loaded '%s' after fixing its translator", pdata.id)
        if hasattr(module, "load_on_reg"):
            try:
                results = module.load_on_reg(dbstate, uistate, pdata)
            except Exception:  # pylint: disable=broad-except
                LOG.warning("Retry of '%s' failed", pdata.id, exc_info=True)
                continue
            try:
                iter(results)
                pdata.data = (pdata.data or []) + list(results)
            except TypeError:
                pdata.data = results
    return False  # one-shot GLib idle callback


def load_on_reg(dbstate, uistate, plugin):  # pylint: disable=unused-argument
    """Called by Gramps at startup."""
    try:
        LOG.debug("get_addon_translator fix: %s", install_checked())
    except Exception:  # pylint: disable=broad-except
        LOG.warning("Could not install the get_addon_translator fix", exc_info=True)
        return []
    if uistate is not None:
        try:
            from gi.repository import GLib

            GLib.idle_add(retry_failed_startup_addons, dbstate, uistate)
        except ImportError:
            pass
    return []
