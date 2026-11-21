"""
Translation Updater engine (no GTK).

Registered as a GENERAL plugin with load_on_reg=True, so load_on_reg() runs at
startup and applies previously downloaded translation packs:

* Addon packs take precedence over the .mo shipped inside each addon
  (GrampsLocale.get_addon_translator is wrapped: pack -> Gramps -> shipped).
* The core pack is merged into the running Gramps translator in place, so
  every later _() call returns the updated text (Option A).
* Optionally, a merged gramps.mo is bound for Glade dialogs, and a launcher
  that sets GRAMPS_RESOURCES gives full coverage from startup (Option B).

A pack is only applied on top of the exact files it was downloaded against.
If the distro updates gramps.mo, or an addon update ships a new .mo, that
pack pauses until the next check, so older downloads never mask newer
translations.

The Translation Updater tool imports this module for downloads and settings.
"""

import datetime
import gettext
import hashlib
import json
import locale
import logging
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import zipfile
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from gi.repository import GLib

from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import USER_DATA, USER_PLUGINS
from gramps.gen.utils.grampslocale import GrampsLocale
from gramps.gen.utils.grampstranslation import GrampsTranslations
from gramps.gen.utils.resourcepath import ResourcePath
from gramps.version import VERSION, VERSION_TUPLE

LOG = logging.getLogger(".TranslationUpdater")
try:
    _TRANS = glocale.get_addon_translator(__file__)
except ValueError:  # stock Gramps when this addon lacks the user's language
    _TRANS = glocale.translation
_ = _TRANS.gettext
ngettext = _TRANS.ngettext

PLUGIN_ID = "TranslationUpdater"
PACK_FORMAT = 1
DEFAULT_URL = (
    "https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/"
    "translation-packs"
)
PACKS_HOME = os.path.join(USER_DATA, "translation-packs")
RESOURCES = os.path.join(PACKS_HOME, "resources")
DESKTOP_FILE = os.path.join(
    GLib.get_user_data_dir(), "applications", "gramps-updated-translations.desktop"
)
CORE_DOMAIN = "gramps"
ADDON_DOMAIN = "addon"

# ------------------------------------------------------------------------
# Settings (TranslationUpdater.ini next to this module)
# ------------------------------------------------------------------------
CONFIG = configman.register_manager(PLUGIN_ID, __file__, use_plugins_path=False)
# [meta] defaults are blank so ConfigManager writes them uncommented.
CONFIG.register("meta.plugin_id", "")
CONFIG.register("meta.schema_version", "")
CONFIG.register("source.base_url", DEFAULT_URL)
CONFIG.register("source.branch", "")
CONFIG.register("packs.languages", [])
CONFIG.register("packs.core", True)
CONFIG.register("packs.addons", True)
CONFIG.register("packs.glade", True)
CONFIG.register("packs.check_at_startup", False)
CONFIG.register("packs.last_check", "")
CONFIG.register("window.width", 820)
CONFIG.register("window.height", 720)
CONFIG.load()
CONFIG.set("meta.plugin_id", PLUGIN_ID)
CONFIG.set("meta.schema_version", "1")
CONFIG.save()


def branch():
    """Pack branch for this Gramps, e.g. 'gramps60'."""
    return CONFIG.get("source.branch") or "gramps%d%d" % tuple(VERSION_TUPLE[:2])


def branch_root():
    """Folder holding this branch's downloaded packs and state."""
    return os.path.join(PACKS_HOME, branch())


def core_pack_root():
    return os.path.join(branch_root(), "core")


def addon_pack_root(name):
    return os.path.join(branch_root(), "addons", name)


def merged_root():
    return os.path.join(branch_root(), "merged")


def mo_path(root, code, domain):
    return os.path.join(root, code, "LC_MESSAGES", domain + ".mo")


# ------------------------------------------------------------------------
# Small helpers
# ------------------------------------------------------------------------
_SHA_CACHE = {}


def file_sha(path):
    """sha256 of a file ('' if missing), cached by mtime and size."""
    if not path or not os.path.isfile(path):
        return ""
    stat = os.stat(path)
    key = (os.path.realpath(path), stat.st_mtime_ns, stat.st_size)
    if key not in _SHA_CACHE:
        digest = hashlib.sha256()
        with open(path, "rb") as fp:
            for block in iter(lambda: fp.read(65536), b""):
                digest.update(block)
        _SHA_CACHE[key] = digest.hexdigest()
    return _SHA_CACHE[key]


def write_atomic(path, data):
    """Write bytes to path via a temporary file in the same folder."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def find_mo(domain, root, lang):
    """
    Locate domain.mo for lang under root using gettext's own language
    expansion (de_DE -> de, etc.). Returns (code, path) or (None, None).
    """
    if not lang or not root or not os.path.isdir(root):
        return None, None
    path = gettext.find(domain, root, [lang])
    if not path:
        return None, None
    code = os.path.basename(os.path.dirname(os.path.dirname(path)))
    return code, path


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------------
# State (what each pack was downloaded against)
# ------------------------------------------------------------------------
def state_path():
    return os.path.join(branch_root(), "state.json")


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as fp:
            state = json.load(fp)
    except (OSError, ValueError):
        state = {}
    state.setdefault("langs", {})
    state.setdefault("merged", {})
    return state


def save_state(state):
    write_atomic(state_path(), json.dumps(state, indent=1, sort_keys=True).encode())


_STATE = None


def state():
    global _STATE  # pylint: disable=global-statement
    if _STATE is None:
        _STATE = load_state()
    return _STATE


def reload_state():
    global _STATE  # pylint: disable=global-statement
    _STATE = load_state()
    return _STATE


# ------------------------------------------------------------------------
# Where the real (distro/installer) translations live
# ------------------------------------------------------------------------
def using_resources():
    """True when Gramps was started by the full-coverage launcher."""
    env = os.environ.get("GRAMPS_RESOURCES")
    return bool(env) and os.path.realpath(env) == os.path.realpath(RESOURCES)


def system_locale_dir():
    """The installed Gramps locale folder, even when running via the launcher."""
    rpath = ResourcePath()
    if using_resources():
        return os.path.join(os.path.dirname(os.path.realpath(rpath.data_dir)), "locale")
    return rpath.locale_dir


def system_core_mo(code):
    return find_mo(CORE_DOMAIN, system_locale_dir(), code)[1]


def installed_addons():
    """{folder name: path} for addons in the user plugin folder."""
    found = {}
    try:
        names = os.listdir(USER_PLUGINS)
    except OSError:
        return found
    for name in names:
        path = os.path.join(USER_PLUGINS, name)
        if os.path.isdir(path) and any(
            fname.endswith(".gpr.py") for fname in os.listdir(path)
        ):
            found[name] = path
    return found


def shipped_addon_mo(addon_path, code):
    return find_mo(ADDON_DOMAIN, os.path.join(addon_path, "locale"), code)[1]


# ------------------------------------------------------------------------
# Pack validity
# ------------------------------------------------------------------------
def valid_core_pack(lang):
    """(code, path) of the core pack for lang if it may be applied."""
    code, path = find_mo(CORE_DOMAIN, core_pack_root(), lang)
    if not path:
        return None, None
    entry = state()["langs"].get(code, {}).get("core")
    if not entry or entry.get("sha256") != file_sha(path):
        return None, None
    if entry.get("system_sha256", "") != file_sha(system_core_mo(code)):
        LOG.info("Core pack '%s' paused: installed gramps.mo changed", code)
        return None, None
    return code, path


def valid_addon_pack(name, addon_path, lang):
    """(code, path) of an addon pack for lang if it may be applied."""
    code, path = find_mo(ADDON_DOMAIN, addon_pack_root(name), lang)
    if not path:
        return None, None
    entry = state()["langs"].get(code, {}).get("addons", {}).get(name)
    if not entry or entry.get("sha256") != file_sha(path):
        return None, None
    if entry.get("shipped_sha256", "") != file_sha(shipped_addon_mo(addon_path, code)):
        LOG.info("Addon pack '%s/%s' paused: addon was updated", code, name)
        return None, None
    return code, path


# ------------------------------------------------------------------------
# Raw .mo reading/writing (keeps plural and context keys intact)
# ------------------------------------------------------------------------
def read_mo_raw(path):
    """Return {msgid bytes: msgstr bytes} exactly as stored in a .mo."""
    with open(path, "rb") as fp:
        data = fp.read()
    magic = struct.unpack("<I", data[:4])[0]
    if magic == 0x950412DE:
        order = "<"
    elif magic == 0xDE120495:
        order = ">"
    else:
        raise ValueError("not a .mo file: %s" % path)
    count, orig_off, trans_off = struct.unpack(order + "3I", data[8:20])
    entries = {}
    for i in range(count):
        olen, ooff = struct.unpack(
            order + "2I", data[orig_off + 8 * i : orig_off + 8 * i + 8]
        )
        tlen, toff = struct.unpack(
            order + "2I", data[trans_off + 8 * i : trans_off + 8 * i + 8]
        )
        entries[data[ooff : ooff + olen]] = data[toff : toff + tlen]
    return entries


def write_mo_raw(entries, path):
    """Write {msgid: msgstr} bytes as a little-endian .mo (no hash table)."""
    keys = sorted(entries)
    ids = bytearray()
    strs = bytearray()
    spans = []
    for key in keys:
        value = entries[key]
        spans.append((len(ids), len(key), len(strs), len(value)))
        ids += key + b"\0"
        strs += value + b"\0"
    count = len(keys)
    header_size = 7 * 4
    ids_start = header_size + 16 * count
    strs_start = ids_start + len(ids)
    out = bytearray(
        struct.pack(
            "<7I", 0x950412DE, 0, count, header_size, header_size + 8 * count, 0, 0
        )
    )
    for ioff, ilen, _soff, _slen in spans:
        out += struct.pack("<2I", ilen, ids_start + ioff)
    for _ioff, _ilen, soff, slen in spans:
        out += struct.pack("<2I", slen, strs_start + soff)
    out += ids + strs
    write_atomic(path, bytes(out))


def merge_mo(base_path, pack_path, out_path):
    """
    Write base .mo with pack entries layered on top (pack wins, base header
    kept). Entries are matched on the singular msgid (with context), so a
    plural entry in the pack replaces the base one even if the plural text
    changed.
    """
    base = read_mo_raw(base_path) if base_path else {}
    pack = read_mo_raw(pack_path)
    pack_singulars = {key.split(b"\0", 1)[0] for key in pack if key}
    merged = {
        key: value
        for key, value in base.items()
        if not key or key.split(b"\0", 1)[0] not in pack_singulars
    }
    for key, value in pack.items():
        if key or b"" not in merged:
            merged[key] = value
    write_mo_raw(merged, out_path)


# ------------------------------------------------------------------------
# Option A: merge the core pack into running translators
# ------------------------------------------------------------------------
_MARK = "_translation_updater_overlaid"


def overlay_translation(trans, force=False):
    """Layer the core pack over a Gramps translator, in place."""
    if not CONFIG.get("packs.core") or not isinstance(trans, GrampsTranslations):
        return False
    catalog = getattr(trans, "_catalog", None)
    # Marked on the translator itself: Python reuses object ids, so a set of
    # ids could wrongly skip a translator created later.
    if catalog is None or (getattr(trans, _MARK, False) and not force):
        return False
    _code, path = valid_core_pack(getattr(trans, "lang", None))
    if not path:
        return False
    with open(path, "rb") as fp:
        fresh = gettext.GNUTranslations(fp)
    fresh._catalog.pop("", None)  # pylint: disable=protected-access
    catalog.update(fresh._catalog)  # pylint: disable=protected-access
    setattr(trans, _MARK, True)
    return True


# ------------------------------------------------------------------------
# Patches on GrampsLocale
# ------------------------------------------------------------------------
_ORIGINALS = {}


def _patched_get_translation(self, domain=None, localedir=None, languages=None):
    trans = _ORIGINALS["_get_translation"](self, domain, localedir, languages)
    if domain in (None, self.localedomain) and localedir in (None, self.localedir):
        try:
            overlay_translation(trans)
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Core translation overlay failed", exc_info=True)
    return trans


def _addon_pack_translator(self, name, addon_path, lang, domain, fallback):
    """Pack translator for one addon, falling back to fallback; or None."""
    _code, path = valid_addon_pack(name, addon_path, lang)
    if not path:
        return None
    pack = gettext.translation(
        domain,
        localedir=addon_pack_root(name),
        languages=[lang],
        class_=GrampsTranslations,
    )
    pack.lang = lang
    if fallback is not None:
        pack.add_fallback(fallback)
    return pack


def _patched_get_addon_translator(self, filename=None, domain="addon", languages=None):
    # Call through __wrapped__ (not a captured reference) so that a later
    # patch such as Addon Locale Fix can slot in underneath this one.
    try:
        result = _patched_get_addon_translator.__wrapped__(
            self, filename, domain, languages
        )
    except ValueError:
        # Stock Gramps raises when the addon ships no translation for the
        # language. A downloaded pack can still supply one.
        rescued = _rescue_addon_translator(self, filename, domain, languages)
        if rescued is None:
            raise
        return rescued
    if not filename or not CONFIG.get("packs.addons"):
        return result
    try:
        lang = getattr(result, "lang", None)
        if not lang or not isinstance(result, GrampsTranslations):
            return result  # English: nothing to layer
        addon_path = os.path.dirname(os.path.abspath(filename))
        name = os.path.basename(addon_path)
        pack = _addon_pack_translator(self, name, addon_path, lang, domain, result)
        return pack or result
    except Exception:  # pylint: disable=broad-except
        LOG.warning("Addon translation pack failed for %s", filename, exc_info=True)
        return result


def _rescue_addon_translator(self, filename, domain, languages):
    """Pack translator (with Gramps as fallback) when stock lookup failed."""
    if not filename or not CONFIG.get("packs.addons"):
        return None
    addon_path = os.path.dirname(os.path.abspath(filename))
    name = os.path.basename(addon_path)
    for lang in languages or self.language or []:
        try:
            fallback = self._get_translation(languages=[lang])
        except ValueError:
            fallback = None
        try:
            pack = _addon_pack_translator(
                self, name, addon_path, lang, domain, fallback
            )
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Addon translation pack failed for %s", filename, exc_info=True)
            pack = None
        if pack is not None:
            return pack
    return None


def install_patches():
    """Wrap GrampsLocale translator lookups (idempotent)."""
    if _ORIGINALS:
        return
    _ORIGINALS["_get_translation"] = GrampsLocale._get_translation
    _patched_get_addon_translator.__wrapped__ = GrampsLocale.get_addon_translator
    GrampsLocale._get_translation = _patched_get_translation
    GrampsLocale.get_addon_translator = _patched_get_addon_translator


# ------------------------------------------------------------------------
# Merged gramps.mo and the resources folder (Glade binding and Option B)
# ------------------------------------------------------------------------
def ensure_merged(code):
    """Merged gramps.mo for code (system + valid pack), or None."""
    out = mo_path(merged_root(), code, CORE_DOMAIN)
    _pcode, pack = valid_core_pack(code)
    if not pack:
        if os.path.exists(out):
            os.remove(out)
        state()["merged"].pop(code, None)
        return None
    system = system_core_mo(code)
    key = {"pack": file_sha(pack), "system": file_sha(system)}
    if state()["merged"].get(code) == key and os.path.isfile(out):
        return out
    merge_mo(system, pack, out)
    state()["merged"][code] = key
    save_state(state())
    return out


def _ensure_link(link, target):
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.islink(link):
        if os.readlink(link) == target:
            return
        os.remove(link)
    elif os.path.exists(link):
        if os.path.isdir(link):
            shutil.rmtree(link)
        else:
            os.remove(link)
    os.symlink(target, link)


def launcher_supported():
    """Option B needs symlinks, an installed layout and a Linux desktop."""
    if not sys.platform.startswith("linux"):
        return False
    data_dir = os.path.realpath(ResourcePath().data_dir)
    return os.path.basename(data_dir) == "gramps" and os.path.isfile(
        os.path.join(data_dir, "authors.xml")
    )


def build_locale_tree():
    """
    (Re)build RESOURCES: links to the installed gramps data and docs, and
    locale/<code>/LC_MESSAGES/gramps.mo for every installed language (merged
    file where a valid pack exists, otherwise a link to the installed file).
    """
    if sys.platform == "win32":
        return False
    sys_dir = system_locale_dir()
    if not sys_dir or not os.path.isdir(sys_dir):
        return False
    data_dir = os.path.realpath(ResourcePath().data_dir)
    _ensure_link(os.path.join(RESOURCES, "gramps"), data_dir)
    doc_dir = os.path.join(os.path.dirname(data_dir), "doc")
    if os.path.isdir(doc_dir):
        _ensure_link(os.path.join(RESOURCES, "doc"), doc_dir)

    wanted = {}
    for code in os.listdir(sys_dir):
        installed = mo_path(sys_dir, code, CORE_DOMAIN)
        if os.path.isfile(installed):
            wanted[code] = os.path.realpath(installed)
    if os.path.isdir(core_pack_root()):
        for code in os.listdir(core_pack_root()):
            merged = ensure_merged(code)
            if merged:
                wanted[code] = merged

    loc_root = os.path.join(RESOURCES, "locale")
    for code, target in wanted.items():
        _ensure_link(mo_path(loc_root, code, CORE_DOMAIN), target)
    if os.path.isdir(loc_root):
        for code in os.listdir(loc_root):
            if code not in wanted:
                shutil.rmtree(os.path.join(loc_root, code), ignore_errors=True)
    return True


def needs_locale_tree():
    lang = getattr(glocale.translation, "lang", None)
    glade = CONFIG.get("packs.glade") and valid_core_pack(lang)[1]
    return bool(glade) or os.path.exists(DESKTOP_FILE) or using_resources()


def bind_glade():
    """Point Glade (C gettext) at the merged translations for the UI language."""
    if sys.platform == "win32" or using_resources() or not CONFIG.get("packs.glade"):
        return False
    lang = getattr(glocale.translation, "lang", None)
    code, _path = valid_core_pack(lang)
    if not code or not os.path.isfile(
        mo_path(os.path.join(RESOURCES, "locale"), code, CORE_DOMAIN)
    ):
        return False
    try:
        locale.bindtextdomain(glocale.localedomain, os.path.join(RESOURCES, "locale"))
    except (AttributeError, OSError):
        return False
    return True


# ------------------------------------------------------------------------
# Option B: full-coverage launcher
# ------------------------------------------------------------------------
def gramps_command():
    found = shutil.which("gramps")
    if found:
        return found
    arg0 = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    return arg0 if os.path.isfile(arg0) else "gramps"


def launcher_command():
    return 'env GRAMPS_RESOURCES="%s" %s' % (RESOURCES, gramps_command())


def create_launcher():
    if not launcher_supported():
        return False
    build_locale_tree()
    text = "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=%s" % _("Gramps (updated translations)"),
            "Comment=%s" % _("Gramps using translations from Translation Updater"),
            "Exec=%s %%U" % launcher_command(),
            "Icon=org.gramps_project.Gramps",
            "Terminal=false",
            "Categories=Office;Database;",
            "StartupNotify=true",
            "",
        ]
    )
    write_atomic(DESKTOP_FILE, text.encode("utf-8"))
    return True


def remove_launcher():
    if os.path.exists(DESKTOP_FILE):
        os.remove(DESKTOP_FILE)


# ------------------------------------------------------------------------
# Downloading
# ------------------------------------------------------------------------
def _url(*parts):
    return "/".join([CONFIG.get("source.base_url").rstrip("/")] + list(parts))


RETRY_CODES = (429, 500, 502, 503, 504)


def fetch(url, timeout=30, tries=5):
    """
    Download url. When the server says "too many requests" or is briefly
    unavailable, wait (as long as it asks, or 2, 4, 8 ... seconds) and retry.
    Only called from background threads, so waiting does not freeze Gramps.
    """
    request = Request(
        url, headers={"User-Agent": "Gramps/%s TranslationUpdater" % VERSION}
    )
    for attempt in range(tries):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as err:
            if err.code not in RETRY_CODES or attempt == tries - 1:
                raise
            try:
                wait = float(err.headers.get("Retry-After", ""))
            except ValueError:
                wait = 2.0 ** (attempt + 1)
            wait = min(max(wait, 1.0), 60.0)
        except URLError:
            if attempt == tries - 1:
                raise
            wait = 2.0 ** (attempt + 1)
        LOG.info("Retrying %s in %.0f s", url, wait)
        time.sleep(wait)
    raise RuntimeError("unreachable")


def fetch_json(url):
    data = json.loads(fetch(url).decode("utf-8"))
    if data.get("format", 0) > PACK_FORMAT:
        raise ValueError(_("This pack format is newer than Translation Updater"))
    return data


def index_cache_path():
    return os.path.join(branch_root(), "index.json")


def fetch_index():
    """Download and cache this branch's index of available languages."""
    index = fetch_json(_url(branch(), "index.json"))
    write_atomic(index_cache_path(), json.dumps(index, indent=1).encode())
    return index


def cached_index():
    try:
        with open(index_cache_path(), encoding="utf-8") as fp:
            return json.load(fp)
    except (OSError, ValueError):
        return None


def default_code(available):
    """Best pack code for the current interface language."""
    lang = getattr(glocale.translation, "lang", None) or "en"
    base = lang.split(".")[0].split("@")[0]
    for candidate in (base, base.split("_")[0]):
        if candidate in available:
            return candidate
    return None


def selected_languages():
    chosen = list(CONFIG.get("packs.languages"))
    if chosen:
        return chosen
    index = cached_index()
    code = default_code(index.get("languages", {}) if index else {})
    return [code] if code else []


class _Bundle:
    """
    The language's pack.zip, downloaded at most once and only when some
    wanted file has changed. Falls back to single files for packs built
    before bundles existed.
    """

    def __init__(self, lang, manifest):
        self.lang = lang
        self.entry = manifest.get("bundle")
        self.zip = None

    def read(self, path):
        if not self.entry:
            return None
        if self.zip is None:
            data = fetch(_url(branch(), self.lang, self.entry["path"]))
            if hashlib.sha256(data).hexdigest() != self.entry["sha256"]:
                raise ValueError(_("Checksum mismatch for %s") % self.entry["path"])
            self.zip = zipfile.ZipFile(BytesIO(data))
        try:
            return self.zip.read(path)
        except KeyError:
            return None


def _download_entry(lang, entry, dest, bundle=None):
    """Download one pack file if its hash differs. Returns True if replaced."""
    if file_sha(dest) == entry["sha256"]:
        return False
    data = bundle.read(entry["path"]) if bundle else None
    if data is None:
        data = fetch(_url(branch(), lang, entry["path"]))
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise ValueError(_("Checksum mismatch for %s") % entry["path"])
    write_atomic(dest, data)
    return True


def _remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.exists(path):
        os.remove(path)


def prune(selected):
    """Delete packs for languages that are no longer selected."""
    st = state()
    for code in list(st["langs"]):
        if code in selected:
            continue
        _remove(os.path.join(core_pack_root(), code))
        _remove(os.path.join(merged_root(), code))
        addons_root = os.path.join(branch_root(), "addons")
        if os.path.isdir(addons_root):
            for name in os.listdir(addons_root):
                _remove(os.path.join(addons_root, name, code))
        st["langs"].pop(code, None)
        st["merged"].pop(code, None)


def update_packs(languages=None, progress=None):
    """
    Check the server and download changed packs for the given pack codes.

    :param progress: optional callable(fraction, text)
    :returns: list of dicts with keys lang, core, addons, removed, error
    """
    languages = list(languages if languages is not None else selected_languages())
    st = reload_state()
    results = []
    index = fetch_index()
    available = index.get("languages", {})
    installed = installed_addons()
    want_core = CONFIG.get("packs.core")
    want_addons = CONFIG.get("packs.addons")

    total = max(len(languages), 1)
    for number, code in enumerate(languages):
        result = {
            "lang": code,
            "core": False,
            "addons": 0,
            "updated": [],
            "removed": 0,
            "error": "",
        }
        results.append(result)
        if progress:
            progress(number / total, code)
        if code not in available:
            result["error"] = _("No translations published for this language")
            continue
        try:
            manifest = fetch_json(_url(branch(), code, "manifest.json"))
            bundle = _Bundle(code, manifest)
            lang_state = st["langs"].setdefault(code, {})
            lang_state["checked"] = now_iso()

            core_dest = mo_path(core_pack_root(), code, CORE_DOMAIN)
            if want_core and manifest.get("core"):
                result["core"] = _download_entry(
                    code, manifest["core"], core_dest, bundle
                )
                lang_state["core"] = {
                    "sha256": manifest["core"]["sha256"],
                    "system_sha256": file_sha(system_core_mo(code)),
                    "date": manifest.get("sources", {})
                    .get("gramps", {})
                    .get("date", ""),
                }
            else:
                _remove(os.path.join(core_pack_root(), code))
                lang_state.pop("core", None)

            addon_state = {}
            published = manifest.get("addons", {}) if want_addons else {}
            names = sorted(installed.items())
            for step, (name, addon_path) in enumerate(names):
                if progress:
                    progress(
                        (number + (step + 1) / (len(names) + 1)) / total,
                        "%s: %s" % (code, name),
                    )
                dest = mo_path(addon_pack_root(name), code, ADDON_DOMAIN)
                entry = published.get(name)
                if not entry:
                    if os.path.exists(dest):
                        _remove(os.path.join(addon_pack_root(name), code))
                        result["removed"] += 1
                    continue
                if _download_entry(code, entry, dest, bundle):
                    result["addons"] += 1
                    result["updated"].append(name)
                addon_state[name] = {
                    "sha256": entry["sha256"],
                    "shipped_sha256": file_sha(shipped_addon_mo(addon_path, code)),
                }
            lang_state["addons"] = addon_state
            if result["core"] or result["updated"]:
                # Remembered so the tool can show what the last update brought.
                lang_state["last_update"] = {
                    "date": lang_state["checked"],
                    "core": result["core"],
                    "addons": list(result["updated"]),
                }
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Translation pack update failed for %s", code, exc_info=True)
            result["error"] = str(err)

    prune(languages)
    save_state(st)
    CONFIG.set("packs.last_check", now_iso())
    CONFIG.save()
    if progress:
        progress(1.0, "")
    return results


def apply_now():
    """Apply freshly downloaded packs to the running session where possible."""
    reload_state()
    install_patches()
    overlay_translation(glocale.translation, force=True)
    if needs_locale_tree():
        build_locale_tree()
        bind_glade()


def addon_titles():
    """
    {addon folder: display name} from the plugin registry.

    A folder can register several plugins; a listed one (such as the tool)
    is preferred over a hidden helper. Falls back to the folder name.
    """
    found = {}
    try:
        from gramps.gen.plug import (  # pylint: disable=import-outside-toplevel
            PTYPE_STR,
            PluginRegister,
        )

        preg = PluginRegister.get_instance()
        for ptype in PTYPE_STR:
            for pdata in preg.type_plugins(ptype):
                folder = os.path.basename(os.path.normpath(pdata.fpath or ""))
                if not folder or not pdata.name:
                    continue
                listed = getattr(pdata, "include_in_listing", True)
                if folder not in found or (listed and not found[folder][1]):
                    found[folder] = (pdata.name, listed)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Could not read addon names", exc_info=True)
    return {folder: name for folder, (name, _listed) in found.items()}


def item_names(core, addons, titles=None):
    """Sorted display names for an update: Gramps first, then addons."""
    titles = addon_titles() if titles is None else titles
    names = sorted((titles.get(name, name) for name in addons), key=str.lower)
    return ([_("Gramps")] if core else []) + names


def summarize(results, lang_names=None, limit=6):
    """
    One line per language for the user, naming what was updated.

    :param lang_names: optional {code: display name}
    :param limit: how many item names to show before "and N more"
    """
    lang_names = lang_names or {}
    titles = addon_titles()
    lines = []
    for res in results:
        label = lang_names.get(res["lang"], res["lang"])
        if res["error"]:
            lines.append("%s: %s" % (label, res["error"]))
            continue
        names = item_names(res["core"], res.get("updated", []), titles)
        if len(names) > limit + 1:  # never "and 1 more"
            more = len(names) - limit
            names = names[:limit] + [_("and %d more") % more]
        parts = []
        if names:
            parts.append(", ".join(names))
        if res["removed"]:
            parts.append(_("%d removed") % res["removed"])
        lines.append("%s: %s" % (label, "; ".join(parts) or _("up to date")))
    return lines


# ------------------------------------------------------------------------
# Language details for the table (same rules as Environment Inspector)
# ------------------------------------------------------------------------
# Region names in Gramps' Windows locale table -> ISO codes. A copy of the
# table in Environment Inspector (envinsp_catalog.py); keep the two in step.
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
}  # fmt: skip
_LANG_CACHE = {}


def _flag(iso):
    if len(iso) != 2 or not iso.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in iso.upper())


def _locale_table():
    try:
        from gramps.gen.utils.win32locale import (  # pylint: disable=import-outside-toplevel
            _LOCALE_NAMES,
        )
    except ImportError:
        return {}
    return _LOCALE_NAMES


def language_info(code):
    """
    {region, name, endonym} for a pack code, as Environment Inspector shows
    them: region is flag plus ISO code (from the code itself, else the region
    Gramps pairs with the language), name is in the session language, endonym
    is the language's name in itself (from its installed Gramps catalog).
    """
    if code in _LANG_CACHE:
        return _LANG_CACHE[code]
    table = _locale_table()
    entry = table.get(code) or table.get(code[:2])
    english = entry[2] if entry else code
    region = ""
    parts = code.split("_")
    if len(parts) > 1 and len(parts[1]) == 2:
        region = parts[1].upper()
    elif entry and entry[0] and "_" in entry[0]:
        region = _COUNTRY_ISO.get(entry[0].split("_", 1)[1], "")
    try:
        names = {c: n for n, c in glocale.get_language_dict().items()}
    except Exception:  # pylint: disable=broad-except
        names = {}
    endonym = ""
    if not code.startswith("en"):
        installed = system_core_mo(code)
        if installed:
            try:
                with open(installed, "rb") as fp:
                    endonym = gettext.GNUTranslations(fp).gettext(english)
            except (OSError, ValueError):
                endonym = ""
            if endonym == english:
                endonym = ""
    else:
        endonym = english
    info = {
        "region": ("%s %s" % (_flag(region), region)).strip(),
        "name": names.get(code, english),
        "endonym": endonym,
    }
    _LANG_CACHE[code] = info
    return info


# ------------------------------------------------------------------------
# Verification: prove that Gramps really uses the downloaded translations
# ------------------------------------------------------------------------
def _split_key(key):
    """(context or None, msgid, is_plural) from a raw .mo key."""
    text = key.decode("utf-8", "replace")
    context = None
    if "\x04" in text:
        context, text = text.split("\x04", 1)
    return context, text.split("\x00", 1)[0], "\x00" in text


def _live(trans, context, msgid):
    """What Gramps' own translator returns for a string right now."""
    if context is not None:
        return trans.pgettext(context, msgid)
    return trans.gettext(msgid)


def _compare(name, base, pack, trans, paths=("", "")):
    """
    Section dict comparing installed (base) and downloaded (pack) entries,
    and what trans returns. Plural entries are left out: which plural form
    a test number selects differs by language.
    """
    rows = []
    for key, value in pack.items():
        if not key or base.get(key) == value:
            continue
        context, msgid, plural = _split_key(key)
        if plural:
            continue
        downloaded = value.decode("utf-8", "replace")
        installed = base.get(key, b"").decode("utf-8", "replace")
        live = _live(trans, context, msgid)
        english = msgid if context is None else "%s  [%s]" % (msgid, context)
        rows.append((english, installed, downloaded, live, live == downloaded))
    rows.sort(key=lambda row: (row[4], row[0].lower()))  # problems first
    return {
        "name": name,
        "differ": len(rows),
        "ok": sum(1 for row in rows if row[4]),
        "rows": rows,
        "installed_path": paths[0] or "",
        "downloaded_path": paths[1] or "",
    }


def verify(code):
    """
    Compare installed and downloaded translations for one language, and ask
    Gramps' own translators (the same calls Gramps and addons make) which
    text they return now.

    :returns: dict with lang, sections (list) and notes (list of str)
    """
    reload_state()
    install_patches()
    result = {"lang": code, "sections": [], "notes": []}

    _pcode, pack = valid_core_pack(code)
    if not pack:
        result["notes"].append(
            _("No Gramps translation is downloaded for this language, or it is paused.")
        )
    else:
        system = system_core_mo(code)
        try:
            # New translator through the patched lookup, as Gramps makes one.
            trans = glocale._get_translation(  # pylint: disable=protected-access
                languages=[code]
            )
        except ValueError:
            trans = None
            result["notes"].append(
                _(
                    "Gramps has no installed translation for this language, so "
                    "the downloaded Gramps translation cannot be layered on it."
                )
            )
        if trans is not None:
            result["sections"].append(
                _compare(
                    _("Gramps"),
                    read_mo_raw(system) if system else {},
                    read_mo_raw(pack),
                    trans,
                    (system, pack),
                )
            )

    titles = addon_titles()
    for name, addon_path in sorted(installed_addons().items()):
        _acode, apack = valid_addon_pack(name, addon_path, code)
        if not apack:
            continue
        shipped = shipped_addon_mo(addon_path, code)
        try:
            trans = glocale.get_addon_translator(
                os.path.join(addon_path, "__init__.py"), languages=[code]
            )
        except ValueError as err:
            result["notes"].append("%s: %s" % (titles.get(name, name), err))
            continue
        section = _compare(
            titles.get(name, name),
            read_mo_raw(shipped) if shipped else {},
            read_mo_raw(apack),
            trans,
            (shipped, apack),
        )
        if section["differ"]:
            result["sections"].append(section)
    return result


def verify_report(result, samples=3):
    """Plain-text report of a verify() result, for pasting into a post."""
    index = cached_index() or {}
    lines = [
        "Translation Updater check: %s" % result["lang"],
        "Gramps %s, packs for %s, checked %s"
        % (VERSION, branch(), now_iso()[:16].replace("T", " ")),
    ]
    for key, source in sorted(index.get("sources", {}).items()):
        lines.append(
            "  %s: %s (%s)"
            % (key, source.get("commit", "")[:10], source.get("date", "")[:10])
        )
    total = sum(sec["differ"] for sec in result["sections"])
    good = sum(sec["ok"] for sec in result["sections"])
    lines.append(
        "Strings that differ from the installed translation: %d; "
        "Gramps now returns the downloaded text for %d of them." % (total, good)
    )
    for note in result["notes"]:
        lines.append("Note: " + note)
    for sec in result["sections"]:
        lines.append("")
        lines.append("%s: %d of %d" % (sec["name"], sec["ok"], sec["differ"]))
        for english, installed, downloaded, live, okay in sec["rows"][:samples]:
            lines.append("  English:    " + english)
            lines.append("  Installed:  " + (installed or "(none)"))
            lines.append("  Downloaded: " + downloaded)
            lines.append("  Gramps now: %s  %s" % (live, "OK" if okay else "MISMATCH"))
    return "\n".join(lines)


# ------------------------------------------------------------------------
# Startup
# ------------------------------------------------------------------------
def _due_for_check():
    last = CONFIG.get("packs.last_check")
    if not last:
        return True
    try:
        then = datetime.datetime.fromisoformat(last)
    except ValueError:
        return True
    return datetime.datetime.now(datetime.timezone.utc) - then > datetime.timedelta(
        hours=20
    )


def _background_check(dbstate, uistate):
    try:
        results = update_packs()
    except Exception:  # pylint: disable=broad-except
        LOG.info("Startup translation check failed", exc_info=True)
        return

    def finish():
        apply_now()
        changed = any(r["core"] or r["addons"] for r in results)
        if changed and uistate is not None:
            try:
                uistate.push_message(
                    dbstate,
                    _(
                        "Translation updates downloaded; restart Gramps to see them all."
                    ),
                )
            except Exception:  # pylint: disable=broad-except
                pass
        return False

    GLib.idle_add(finish)


def load_on_reg(dbstate, uistate, plugin):  # pylint: disable=unused-argument
    """Called by Gramps at startup: apply packs, optionally check for updates."""
    try:
        install_patches()
        overlay_translation(glocale.translation)
        if needs_locale_tree():
            build_locale_tree()
            bind_glade()
        if (
            uistate is not None
            and CONFIG.get("packs.check_at_startup")
            and _due_for_check()
        ):
            threading.Thread(
                target=_background_check, args=(dbstate, uistate), daemon=True
            ).start()
    except Exception:  # pylint: disable=broad-except
        LOG.warning("Translation Updater startup failed", exc_info=True)
    return []
