#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2011       Paul Franklin
# Copyright (C) 2023       Nick Hall
# Copyright (C) 2026       Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Addon Marketplace: a monkey-patch replacement for the Gramps Addon Manager.

Forked from gramps/gui/plug/_windows.py (maintenance/gramps60) with the
enhanced project dialog, clickable filter lozenges and Update/Downgrade
handling, per-project language codes, "Include English" catalogs, SSL
diagnostics and a filtered/total count (merged from a later revision of
that file), plus the Gramps 6.1 install improvements (PyPI name resolution,
depends_on, clearer failure messages). At registration it replaces
``gramps.gui.plug._windows.AddonManager``, so the existing menu item opens
this window instead. Works on Gramps 5.2 through 6.1.

Generated-by: Claude Opus 5.5 (Anthropic, claude-opus-5-5, claude.ai chat)
Prompt: "Can this variation of the Addon Manager be made into a monkey
patch addon? One renamed as Addon Marketplace and compatible with 5.2 to
6.1 versions of Gramps. And using the CSS (renamed media/lozenges.CSS and
stripped of CSS unrelated to the addon.)"
"""

from __future__ import annotations  # "str | None" hints on Python < 3.10

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------
import os
import datetime
import sys
import json
import re
import ssl
import threading
import subprocess
import importlib
import shutil
import logging
from html import escape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, url2pathname, urlopen

# -------------------------------------------------------------------------
#
# GTK modules
#
# -------------------------------------------------------------------------

from gi.repository import Gtk, Gdk, GdkPixbuf, Gio, GLib, Pango

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import COLON, USER_PLUGINS, LIB_PATH
from gramps.gen.config import config
from gramps.gen.utils.configmanager import ConfigManager
from gramps.gen.constfunc import win
from gramps.gen.plug import PluginRegister, PTYPE_STR, load_addon_file
from gramps.gen.plug import AUDIENCETEXT, STATUSTEXT
from gramps.gen.plug.utils import urlopen_maybe_no_check_cert
from gramps.gen.plug.utils import version_str_to_tup
from gramps.gen.utils.requirements import Requirements
from gramps.version import major_version
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.glade import Glade
from gramps.gui.listmodel import ListModel, NOSORT, TOGGLE
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.dialog import InfoDialog, OkDialog, QuestionDialog2
from gramps.gui.display import display_help, display_url
from gramps.gui.widgets import BasicLabel, SimpleButton, WarnButton
from gramps.gui.plug import _windows as PluginWindows

# Gramps 6.1 added a PyPI installer that works without pip (AIO, Flatpak)
# and maps import names to PyPI names ("PIL" -> "Pillow"). Older versions
# fall back to running pip directly.
try:
    from gramps.gen.utils.pypi import (
        PyPIInstallError,
        _pip_available,
        install_package,
        is_frozen,
        resolve_pypi_name,
    )

    HAVE_PYPI = True
except ImportError:
    HAVE_PYPI = False

    class PyPIInstallError(Exception):
        """Placeholder so the except clauses work before Gramps 6.1."""


try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext
ngettext = _trans.ngettext

LOG = logging.getLogger(".AddonMarketplace")

RELOAD = 777  # A custom Gtk response_type for the Reload button
PLUGIN_ID = "AddonMarketplace"  # the id= in AddonMarketplace.gpr.py

MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
CSS_FILE = os.path.join(MEDIA_DIR, "lozenges.css")
# Projects file: a [behavior] addons-projects list that offers extra
# projects (the gtk-index button on the Projects tab). A gramps.ini that a
# user drops into the media folder (their own, or one from another user)
# wins, unedited; the addon ships only addons-projects.ini, so an update
# of the addon never overwrites the dropped-in file.
PROJECTS_INI_NAMES = ("gramps.ini", "addons-projects.ini")


def _projects_ini_path():
    """
    The projects file in use: media/gramps.ini when it exists, else
    media/addons-projects.ini, else None.
    """
    for name in PROJECTS_INI_NAMES:
        path = os.path.join(MEDIA_DIR, name)
        if os.path.isfile(path):
            return path
    return None


# Gramps Discourse list of curated third-party addon collections
CURATED_COLLECTIONS_URL = (
    "https://gramps.discourse.group/t/" "curated-third-party-addon-collections/7170/18"
)


_SETTINGS = None
_SETTINGS_SCHEMA = "1"


def _settings():
    """
    The settings of the Addon Marketplace, kept with the Gramps
    ConfigManager in AddonMarketplace.ini next to this module: the
    language code of each project (by address, since gramps.ini stores
    only name, address and on/off) and the "Include English" option.
    """
    global _SETTINGS  # pylint: disable=global-statement
    if _SETTINGS is not None:
        return _SETTINGS
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), PLUGIN_ID)
    manager = config.register_manager(path)
    # defaults that can never match a saved value, so they are always written
    manager.register("meta.plugin_id", "")
    manager.register("meta.schema_version", "")
    manager.register("projects.languages", {})
    manager.register("projects.include-english", False)
    # {addon id: catalog version} of offers already installed, so an
    # offer that installing did not satisfy is not repeated each start
    manager.register("updates.installed-offers", {})
    manager.load()
    if (
        manager.get("meta.plugin_id") != PLUGIN_ID
        or manager.get("meta.schema_version") != _SETTINGS_SCHEMA
    ):
        manager.reset()
        manager.set("meta.plugin_id", PLUGIN_ID)
        manager.set("meta.schema_version", _SETTINGS_SCHEMA)
        manager.save()
    _SETTINGS = manager
    return manager


def _project_language(url):
    """
    The saved language code of the project at *url*, or "".
    """
    return _settings().get("projects.languages").get(_url_key(url), "")


def _save_project_languages(projects):
    """
    Save the language codes of *projects* ([name, url, enabled, code]),
    dropping codes of projects that are no longer in the list.
    """
    languages = {
        _url_key(project[1]): project[3]
        for project in projects
        if len(project) > 3 and project[3]
    }
    manager = _settings()
    if manager.get("projects.languages") != languages:
        manager.set("projects.languages", languages)
        manager.save()


def _read_ini_projects(path):
    """
    Return the addons-projects list of a projects file (gramps.ini
    format), read with the
    Gramps ConfigManager, as [[name, url, enabled], ...]. Malformed
    entries are skipped; a missing or unreadable file gives [].
    """
    if not os.path.isfile(path):
        return []
    ini = ConfigManager(path)
    ini.register("behavior.addons-projects", [])
    try:
        ini.load()
        projects = ini.get("behavior.addons-projects") or []
    except Exception:  # a broken file should not stop the window
        LOG.warning("Addon Marketplace: cannot read projects from %s", path)
        return []
    good = []
    for entry in projects:
        if (
            isinstance(entry, (list, tuple))
            and len(entry) >= 2
            and isinstance(entry[0], str)
            and isinstance(entry[1], str)
            and entry[1].strip()
        ):
            enabled = bool(entry[2]) if len(entry) > 2 else False
            good.append([entry[0].strip(), entry[1].strip(), enabled])
    return good


_RAW_GITHUB_RE = re.compile(
    r"^https?://raw\.githubusercontent\.com/([^/?#]+)/([^/?#]+)", re.IGNORECASE
)


def _project_home_url(url):
    """
    Where the name of a project links to in the project picker.

    A raw.githubusercontent.com address links to the GitHub repository
    (``https://github.com/<owner>/<repo>``); any other address links to
    the folder one level above the project folder, on the same path.
    """
    match = _RAW_GITHUB_RE.match(url)
    if match:
        return "https://github.com/%s/%s" % match.groups()
    parsed = urlparse(url)
    parent = parsed.path.rstrip("/").rsplit("/", 1)[0] + "/"
    return parsed._replace(path=parent, params="", query="", fragment="").geturl()


def _open_uri(uri):
    """
    Open a project home in the web browser or file manager.
    """
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        LOG.warning("Addon Marketplace: cannot open %s", uri)


def _cb_folder_button_press(eventbox, event):
    """
    Open the home of the project on a double-click of its folder icon.
    Every click on the icon is consumed, so it never edits the project.
    """
    if event.type == Gdk.EventType._2BUTTON_PRESS and event.button == 1:
        if eventbox.project_home:
            _open_uri(eventbox.project_home)
    return True


def _project_folder_icon():
    """
    A folder icon that opens the home of a project on a double-click.
    """
    eventbox = Gtk.EventBox()
    eventbox.set_visible_window(False)
    eventbox.add(Gtk.Image.new_from_icon_name("folder", Gtk.IconSize.BUTTON))
    eventbox.project_home = None
    eventbox.connect("button-press-event", _cb_folder_button_press)
    return eventbox


def _set_project_location(icon, url):
    """
    Point a project folder icon at the home of the project (see
    _project_home_url). Without an address the icon is dimmed.
    """
    if url.strip():
        icon.project_home = _project_home_url(url)
        icon.get_child().set_sensitive(True)
        icon.set_tooltip_text(_("Double-click to open %s") % icon.project_home)
    else:
        icon.project_home = None
        icon.get_child().set_sensitive(False)
        icon.set_tooltip_text(None)


def _project_name_label():
    """
    A plain label for a project name.
    """
    label = Gtk.Label()
    label.set_xalign(0)
    return label


_GPR_ID_PATTERN = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")


def _addon_folder_index():
    """
    Map each plugin id found in the .gpr.py files of the user plugins
    folder to the list of folders that register it. More than one folder
    means duplicate copies, of which Gramps registers whichever it
    happens to scan last.

    :returns: {plugin id: [folder, ...]}
    """
    index = {}
    try:
        entries = sorted(os.listdir(USER_PLUGINS))
    except OSError:
        return index
    for entry in entries:
        folder = os.path.join(USER_PLUGINS, entry)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith(".gpr.py"):
                continue
            try:
                with open(os.path.join(folder, name), encoding="utf-8") as fp:
                    ids = set(_GPR_ID_PATTERN.findall(fp.read()))
            except OSError:
                continue
            for addon_id in ids:
                index.setdefault(addon_id, []).append(folder)
    return index


def _find_addon_folder(addon_id):
    """
    The folder in the user plugins folder whose .gpr.py registers
    *addon_id*, or None.
    """
    folders = _addon_folder_index().get(addon_id)
    return folders[0] if folders else None


def _url_key(url):
    """
    Comparison form of a project address: normalized like the project
    dialog does it, without the trailing slash, lower-case.
    """
    return _normalize_location_text(url).rstrip("/").lower()


# ----------------------------------------------------------------------
# Help button: the color Help button of MarkdownUtils (README.md in
# Markdown Dash, else help_url), or a plain text Help button that opens
# help_url when MarkdownUtils is missing, too old, or fails to load.
# Recipe: HelpDocButton.md in the MarkdownBased folder.
# ----------------------------------------------------------------------
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


# Import names whose PyPI distribution has another name. The first part is
# a copy of _IMPORT_TO_PYPI in gramps/gen/utils/pypi.py of Gramps 6.1, for
# Gramps 5.2 and 6.0, which do not have it.
_IMPORT_TO_PYPI_FALLBACK = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "bs4": "beautifulsoup4",
    "serial": "pyserial",
    "usb": "pyusb",
    "nacl": "PyNaCl",
    "Crypto": "pycryptodome",
    "OpenSSL": "pyOpenSSL",
    "wx": "wxPython",
}
# Modules published as source code only (which needs build tools to
# install), with a ready-made "binary" distribution that provides the
# same import name. Used on every Gramps version.
_BINARY_ALTERNATIVES = {
    "psycopg2": ["psycopg2-binary"],
    "psycopg": ["psycopg", "psycopg-binary"],  # -binary brings libpq along
}


def _pypi_names(package):
    """
    The PyPI distributions that provide the import name *package*.
    """
    if package in _BINARY_ALTERNATIVES:
        return list(_BINARY_ALTERNATIVES[package])
    if HAVE_PYPI:
        return [resolve_pypi_name(package)]
    return [_IMPORT_TO_PYPI_FALLBACK.get(package, package)]


def _pip_command(package):
    """
    How to install one Python module into the Gramps plugin lib folder.

    :returns: (command, pypi_names); command is None when the Gramps 6.1
        PyPI installer must be used instead of pip (frozen Gramps, or no
        pip available).
    """
    names = _pypi_names(package)
    if HAVE_PYPI:
        if is_frozen() or not _pip_available():
            return None, names
        cmd = [sys.executable, "-m", "pip"]
    else:
        # Same choice the 5.2/6.0 Addon Manager makes on Windows (AIO);
        # elsewhere "python -m pip" finds the pip that matches Gramps.
        cmd = ["pip.exe"] if win() else [sys.executable, "-m", "pip"]
    return cmd + ["install", "--target", LIB_PATH] + names, names


class _PipProgress:
    """
    Install Python modules in a background thread, behind a small modal
    progress dialog, so Gramps keeps drawing its windows. Large modules
    (litellm, for one) can take minutes, and on a new Python version pip
    may have to build parts of them from source. Cancel stops pip; the
    Gramps 6.1 PyPI installer cannot be interrupted, so Cancel is dimmed
    while it runs.
    """

    def __init__(self, parent):
        self.cancelled = False
        self._proc = None
        self.dialog = Gtk.Dialog(
            title=_("Installing Python modules"), transient_for=parent, modal=True
        )
        self.dialog.set_deletable(False)
        self.dialog.set_resizable(False)  # fit the content, no empty space
        area = self.dialog.get_content_area()
        area.set_spacing(12)
        area.set_border_width(12)
        row = Gtk.Box(spacing=12)
        spinner = Gtk.Spinner()
        spinner.start()
        row.pack_start(spinner, False, False, 0)
        self.label = Gtk.Label(xalign=0)
        self.label.set_line_wrap(True)
        self.label.set_max_width_chars(50)
        row.pack_start(self.label, True, True, 0)
        area.pack_start(row, False, False, 0)
        note = Gtk.Label(
            label=_(
                "Large modules can take several minutes, especially when "
                "parts of them must be built on this computer."
            ),
            xalign=0,
        )
        note.set_line_wrap(True)
        note.set_max_width_chars(50)
        area.pack_start(note, False, False, 0)
        self.cancel_button = self.dialog.add_button(
            _("Cancel"), Gtk.ResponseType.CANCEL
        )
        self.dialog.connect("response", self._cb_response)
        self.dialog.show_all()

    def _cb_response(self, _dialog, _response_id):
        self.cancelled = True
        self.cancel_button.set_sensitive(False)
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def install(self, package):
        """
        Install one module, keeping the GTK main loop running meanwhile.

        :returns: None on success, else the error text ("" when the user
            cancelled).
        """
        cmd, pypi_names = _pip_command(package)
        self.label.set_markup(
            _("Installing <b>%s</b>...") % escape(", ".join(pypi_names))
        )
        self.cancel_button.set_sensitive(cmd is not None and not self.cancelled)
        result = {}

        def work():
            try:
                if cmd is None:
                    for name in pypi_names:
                        install_package(name, LIB_PATH)
                    return
                self._proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                )
                output, _err = self._proc.communicate()
                if self._proc.returncode:
                    result["error"] = output.decode("utf-8", "replace")
            except (PyPIInstallError, OSError) as err:
                result["error"] = str(err)

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        while thread.is_alive():
            while Gtk.events_pending():
                Gtk.main_iteration()
            thread.join(0.05)
        if self.cancelled:
            return ""
        return result.get("error")

    def close(self):
        """Close the progress dialog."""
        self.dialog.destroy()


# A typed or pasted Windows drive path, e.g. "C:\Users\Name\addons\"
def _ssl_contexts() -> list:
    """
    The SSL contexts to try for HTTPS requests, in order.

    First the system certificate store, which is also what Gramps uses
    when it loads the catalogs, and which holds any company or proxy
    certificates; then the ``certifi`` bundle, when installed, which helps
    on macOS where a Python.org Python may have no certificates until
    "Install Certificates.command" is run.

    :returns: a list of :class:`ssl.SSLContext` (None stands for the
        urllib default when no context could be made).
    """
    contexts = []
    try:
        contexts.append(ssl.create_default_context())
    except Exception as exc:  # pragma: no cover
        LOG.warning("SSL context: system default failed (%s)", exc)
    try:
        import certifi  # type: ignore[import-untyped]

        contexts.append(ssl.create_default_context(cafile=certifi.where()))
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover
        LOG.warning("SSL context: certifi available but failed (%s)", exc)
    return contexts or [None]


def _is_ssl_error(err) -> bool:
    """
    Whether a URLError is a certificate verification problem.
    """
    reason = getattr(err, "reason", err)
    return isinstance(reason, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(
        reason
    )


_SSL_TROUBLESHOOTING_URL = (
    "https://dev.to/mochafreddo/solving-ssl-certificate-"
    "verification-issues-with-pip-on-macos-4ahp"
)


def _ssl_remediation_text() -> str:
    """
    Return a short explanation of why SSL certificate verification may
    fail for HTTPS addon-repository requests, tailored to whether Gramps
    is currently running on macOS.

    macOS Python builds do not use the system Keychain to verify
    certificates, so a freshly installed Python may have no CA bundle to
    check against — unlike Linux/Windows, where the system's own
    certificate store is normally used. There is no ``pip`` command on a
    stock macOS system, so this deliberately does not suggest
    ``pip3 install certifi``.

    Shared by :meth:`EnhancedProjectDialog._validate_web_url` (the Test
    Location validator) and the warning bar of :class:`AddonMarketplace`
    (when loading a catalog fails with a certificate error).

    :returns: The remediation text, without a leading or trailing newline.
    """
    if sys.platform == "darwin":
        return _(
            "This is common on macOS: Python does not use the system "
            "Keychain to verify certificates, so a freshly installed "
            "Python may have no certificate bundle to check against.\n\n"
            "To fix it, run this once in a Terminal (adjust the "
            "version to match your Python install):\n"
            "  /Applications/Python\\ 3.x/Install Certificates.command\n\n"
            "For other ways to resolve this, see:\n  {}"
        ).format(_SSL_TROUBLESHOOTING_URL)
    return _(
        "This usually means the certificate store used by Python on "
        "this system is missing or out of date.\n\n"
        "For background on this class of issue and how to resolve it, "
        "see:\n  {}"
    ).format(_SSL_TROUBLESHOOTING_URL)


def _find_warn_button(widget: Gtk.Widget | None) -> Gtk.Widget | None:
    """
    Recursively search *widget*'s tree for Gramps' status-bar warning
    button -- the lightbulb icon that already opens the native "Gramps
    Warnings" dialog with the buffered log messages for this session.

    Rather than depend on a specific, version-fragile attribute path
    (e.g. ``uistate.viewmanager.statusbar``) to reach the button, this
    walks the widget hierarchy looking for a :class:`WarnButton`
    instance, which is stable regardless of how the status bar is wired
    up internally.

    :param widget: The widget to search, normally the main Gramps window
        (:attr:`DisplayState.window`).
    :returns: The :class:`WarnButton` widget, or ``None`` if it could not
        be found (e.g. an unexpected Gramps GUI layout).
    """
    if widget is None:
        return None
    if isinstance(widget, WarnButton):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = _find_warn_button(child)
            if found is not None:
                return found
    return None


_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")

# A GitHub web page address: github.com/<owner>/<repo>[/<view>/<rest>]
_GITHUB_PAGE_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([^/?#]+)/([^/?#]+?)(?:\.git)?"
    r"(?:/(blob|tree|raw)/([^?#]+))?/?(?:[?#].*)?$",
    re.IGNORECASE,
)
# A catalog file or listings folder pasted at the end of an address;
# Gramps adds "listings/addons-<lang>.json" itself
_LISTINGS_TAIL_RE = re.compile(
    r"/listings(?:/(?:addons-[A-Za-z_]+\.json)?)?/?$", re.IGNORECASE
)


def _github_raw_url(url: str) -> str:
    """
    Convert a github.com web page address to the raw.githubusercontent.com
    address that serves the files themselves. Any other text is returned
    unchanged.

    - github.com/<owner>/<repo>/blob/<branch>/<path> (a file page)
    - github.com/<owner>/<repo>/tree/<branch>/<path> (a folder page)
    - github.com/<owner>/<repo>/raw/<branch>/<path> (a download link)
    - github.com/<owner>/<repo> (the repository page; HEAD stands for
      the default branch)

    :param url: An address typed or pasted by the user.
    :returns: The raw.githubusercontent.com address, or *url*.
    """
    match = _GITHUB_PAGE_RE.match(url)
    if not match:
        return url
    owner, repo, _view, rest = match.groups()
    return "https://raw.githubusercontent.com/%s/%s/%s" % (
        owner,
        repo,
        rest.strip("/") if rest else "HEAD",
    )


def _normalize_location_text(text: str) -> str:
    """
    Normalize a user-typed repository location to the canonical form
    Gramps expects.

    A github.com web page address (a file, folder or repository page) is
    converted to its raw.githubusercontent.com address, and a pasted
    ``listings/addons-xx.json`` ending is removed, since Gramps adds it
    itself. Other web URLs are returned unchanged. Any local or network
    location --
    whether already a ``file://`` URI, a Windows path typed or pasted
    from File Explorer (e.g. ``C:\\Users\\Name\\addons\\``), or a POSIX
    path -- is converted to a ``file:///...`` URI. Text that cannot be
    confidently recognized as a local location is returned unchanged so
    it can be validated as a web URL instead.

    :param text: The raw text typed or pasted by the user.
    :returns: The normalized location.
    """
    text = text.strip()
    if text.startswith(("http://", "https://", "file://")):
        text = _github_raw_url(text)
        # drop a pasted "listings/addons-xx.json" (Gramps adds it), but
        # keep the trailing slash this dialog saves addresses with
        trimmed = _LISTINGS_TAIL_RE.sub("", text)
        if trimmed != text:
            text = trimmed + "/"
        return text
    if not text:
        return text

    if _WINDOWS_DRIVE_RE.match(text):
        # Build the URI directly so a Windows path converts correctly
        # even when Gramps itself is not running on Windows.
        posix_style = text.replace("\\", "/")
        if not posix_style.startswith("/"):
            posix_style = "/" + posix_style
        return "file://" + quote(posix_style, safe="/:")

    if text.startswith("\\\\") or text.startswith("/") or os.path.exists(text):
        try:
            return Path(text).resolve().as_uri()
        except (OSError, ValueError):
            return text

    return text


class EnhancedProjectDialog:
    """
    Enhanced dialog for creating/editing addon repository projects.

    Features:

    - Multi-line URL field with wrapping (handles long URLs).
    - Web URL vs Local/Network Folder selection.
    - Typed or pasted local paths (including Windows paths such as
      ``C:\\Users\\Name\\addons\\``) are normalized to the ``file://``
      URI form Gramps expects.
    - Comprehensive validation with detailed feedback.
    - Test URL button for optional validation.
    - OK button always enabled (allows offline placeholder creation).

    Originally implemented as a standalone module (``_projectdialog.py``)
    and merged into ``_windows.py``; the Validation Status links, the
    language code, the SSL handling and the focus fix came from a later
    revision of that file (Claude Sonnet 4.6, July 2026).
    """

    def __init__(self, parent, title, project_name="", project_url="", project_lang=""):
        """
        Initialize the enhanced project dialog.

        :param parent: Parent window (transient_for).
        :param title: Dialog title (e.g., "New Project" or "Edit Project").
        :param project_name: Initial project name.
        :param project_url: Initial project URL/path.
        :param project_lang: Language-code override for this project (e.g. ``"fi"``).
            When set, this code is used in preference to the running Gramps
            locale when selecting which ``addons-XX.json`` file to fetch.
            An empty string means "use Gramps locale".
        """
        self.parent = parent
        self.result = None
        self._project_lang = project_lang  # current language override

        # Create dialog - 50% wider for long URLs
        self.dialog = Gtk.Dialog(
            title=title,
            transient_for=parent,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        )
        self.dialog.set_default_size(900, 560)
        self.dialog.set_border_width(12)

        # Build the interface
        self._build_interface(project_name, project_url, project_lang)

        # Connect signals
        self._connect_signals()

    def _build_interface(self, project_name, project_url, project_lang=""):
        """
        Build the dialog interface.

        :param project_name: Initial project name.
        :param project_url: Initial project URL/path.
        :param project_lang: Initial language-code override (may be empty).
        """
        # Content area
        vbox = self.dialog.get_content_area()
        vbox.set_spacing(12)

        # Grid for input fields
        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_column_spacing(12)
        grid.set_column_homogeneous(False)

        # Project name
        label = Gtk.Label(label=_("%s: ") % _("Project name"))
        label.set_halign(Gtk.Align.END)
        label.set_width_chars(15)
        grid.attach(label, 0, 0, 1, 1)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_hexpand(True)
        self.name_entry.set_text(project_name)
        self.name_entry.set_activates_default(True)
        self.name_entry.set_placeholder_text(_("e.g., My Addons Repository"))
        grid.attach(self.name_entry, 1, 0, 2, 1)

        # Location type selector
        label = Gtk.Label(label=_("%s: ") % _("Location Type"))
        label.set_halign(Gtk.Align.END)
        label.set_width_chars(15)
        grid.attach(label, 0, 1, 1, 1)

        type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.url_radio = Gtk.RadioButton.new_with_label_from_widget(None, _("Web URL"))
        self.folder_radio = Gtk.RadioButton.new_with_label_from_widget(
            self.url_radio, _("Local/Network Folder")
        )
        type_box.pack_start(self.url_radio, False, False, 0)
        type_box.pack_start(self.folder_radio, False, False, 0)
        grid.attach(type_box, 1, 1, 2, 1)

        # URL/Path label
        url_label = Gtk.Label(label=_("%s: ") % _("URL/Path"))
        url_label.set_halign(Gtk.Align.END)
        url_label.set_valign(Gtk.Align.START)
        url_label.set_width_chars(15)
        grid.attach(url_label, 0, 2, 1, 1)

        # URL/Path field - multi-line with wrapping
        url_scroll = Gtk.ScrolledWindow()
        url_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        url_scroll.set_min_content_height(100)
        url_scroll.set_hexpand(True)

        self.url_text = Gtk.TextView()
        self.url_text.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.url_text.set_accepts_tab(False)
        self.url_buffer = self.url_text.get_buffer()
        self.url_buffer.set_text(project_url)

        # Add helpful placeholder if empty
        if not project_url:
            help_text = _(
                "Enter URL or use Browse button.\n"
                "Examples:\n"
                "  https://example.com/addons/\n"
                "  file:///C:/Users/Name/addons/\n"
                "  C:\\Users\\Name\\addons\\  (pasted paths are converted)"
            )
            self.url_text.set_tooltip_text(help_text)

        url_scroll.add(self.url_text)
        # URL field spans only the middle column; the browse button is beside it.
        # The language selector (row 3) will occupy the remaining right portion.
        grid.attach(url_scroll, 1, 2, 1, 1)

        # Folder selection button (icon only, like Preferences)
        self.browse_button = Gtk.Button()
        self.browse_button.set_tooltip_text(_("Select folder"))
        browse_image = Gtk.Image()
        browse_image.set_from_icon_name("document-open", Gtk.IconSize.BUTTON)
        browse_image.show()
        self.browse_button.add(browse_image)
        self.browse_button.set_valign(Gtk.Align.START)
        self.browse_button.set_sensitive(False)
        grid.attach(self.browse_button, 2, 2, 1, 1)

        # ── Language code row (row 3) ──────────────────────────────────────
        # A plain Gtk.Entry.  The user types an ISO 639-1 or locale code
        # (e.g. "en", "fi", "zh_CN").  On Test Location / OK the value is
        # stripped of whitespace and used to look for addons-XX.json.
        # Leaving it blank means "use the running Gramps locale".
        lang_label = Gtk.Label(label=_("%s: ") % _("Language code"))
        lang_label.set_halign(Gtk.Align.END)
        lang_label.set_width_chars(15)
        lang_label.set_tooltip_text(
            _(
                'Enter an ISO 639-1 or locale code (e.g. "en", "fi", '
                '"zh_CN") to override which addons-XX.json listing file is '
                "fetched for this project.  Leave blank to use the running "
                "Gramps locale."
            )
        )
        grid.attach(lang_label, 0, 3, 1, 1)

        self._lang_entry = Gtk.Entry()
        self._lang_entry.set_text(project_lang or "")
        self._lang_entry.set_placeholder_text(
            _("e.g. en, fi, zh_CN  (blank = Gramps locale)")
        )
        self._lang_entry.set_max_width_chars(12)
        self._lang_entry.set_width_chars(12)
        self._lang_entry.set_tooltip_text(
            _(
                "ISO 639-1 or locale code for the addons listing to use, "
                'e.g. "en", "fi", "zh_CN".  Leave blank to follow '
                "the running Gramps locale."
            )
        )
        self._lang_entry.set_activates_default(True)
        grid.attach(self._lang_entry, 1, 3, 2, 1)

        vbox.pack_start(grid, False, False, 0)

        # Validation status frame
        status_frame = Gtk.Frame(label=_("Validation Status"))
        status_frame.set_margin_top(6)

        status_scroll = Gtk.ScrolledWindow()
        status_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        status_scroll.set_min_content_height(150)

        self.status_text = Gtk.TextView()
        self.status_text.set_editable(False)
        self.status_text.set_wrap_mode(Gtk.WrapMode.WORD)
        self.status_text.set_left_margin(6)
        self.status_text.set_right_margin(6)
        self.status_buffer = self.status_text.get_buffer()

        # Tag for clickable hyperlinks in the status view
        self._link_tag = self.status_buffer.create_tag(
            "hyperlink",
            foreground="blue",
            underline=Pango.Underline.SINGLE,
        )
        # Map from tag object → URL/path string for click handling
        self._link_map: dict = {}

        self.status_text.connect("button-release-event", self._on_status_click)
        self.status_text.connect("motion-notify-event", self._on_status_motion)

        self._set_status_text(
            _(
                "Click 'Test Location' to validate the repository.\n\n"
                "Validation is optional - you can save without testing "
                "(useful for creating placeholders offline)."
            )
        )

        status_scroll.add(self.status_text)
        status_frame.add(status_scroll)
        vbox.pack_start(status_frame, True, True, 0)

        # Dialog buttons
        self.dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        self.test_button = self.dialog.add_button(
            _("Test Location"), Gtk.ResponseType.HELP
        )
        self.ok_button = self.dialog.add_button(_("_OK"), Gtk.ResponseType.OK)
        self.dialog.set_default_response(Gtk.ResponseType.OK)

        # Set initial mode based on current URL
        if project_url and (
            project_url.startswith("http://") or project_url.startswith("https://")
        ):
            self.url_radio.set_active(True)
        elif project_url:
            self.folder_radio.set_active(True)

        # Update button state based on initial selection
        self._on_type_changed(None)

        self.dialog.show_all()

    def _connect_signals(self):
        """Connect signal handlers."""
        self.url_radio.connect("toggled", self._on_type_changed)
        self.folder_radio.connect("toggled", self._on_type_changed)
        self.browse_button.connect("clicked", self._on_browse_clicked)
        self.dialog.connect("response", self._on_response)

    def _get_active_lang(self) -> str:
        """
        Return the language-code override from the entry widget.

        Strips leading/trailing whitespace from whatever the user typed.
        An empty string means "use the running Gramps locale".

        :returns: A stripped language-code string such as ``"fi"`` or
            ``"zh_CN"``, or ``""`` if the entry is blank.
        """
        return self._lang_entry.get_text().strip()

    def _get_url_text(self) -> str:
        """
        Get the raw URL/path text from the text view.

        :returns: The text currently entered, stripped of leading and
            trailing whitespace.
        """
        start = self.url_buffer.get_start_iter()
        end = self.url_buffer.get_end_iter()
        return self.url_buffer.get_text(start, end, False).strip()

    def _on_type_changed(self, widget):
        """Handle location type change"""
        is_folder = self.folder_radio.get_active()
        self.browse_button.set_sensitive(is_folder)
        self._set_status_text(
            _(
                "Click 'Test Location' to validate the repository.\n\n"
                "Validation is optional - you can save without testing."
            )
        )

    def _on_browse_clicked(self, widget):
        """Open folder chooser dialog using Gtk.FileChooserDialog"""
        chooser = Gtk.FileChooserDialog(
            title=_("Select Listings Folder"),
            parent=self.dialog,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        chooser.add_buttons(
            _("_Cancel"),
            Gtk.ResponseType.CANCEL,
            _("_Select"),
            Gtk.ResponseType.OK,
        )

        # Set initial folder from the current URI/path if possible
        current_text = _normalize_location_text(self._get_url_text())
        if current_text.startswith("file://"):
            path = url2pathname(urlparse(current_text).path)
            if os.path.exists(path):
                chooser.set_current_folder(path)

        response = chooser.run()
        if response == Gtk.ResponseType.OK:
            folder_path = chooser.get_filename()

            # Remove a trailing "listings" segment; Gramps adds it itself.
            if folder_path.endswith(os.sep + "listings"):
                folder_path = folder_path.rsplit(os.sep + "listings", 1)[0]

            # Build the file:// URI with pathlib so it is correct on
            # both POSIX and Windows.
            file_uri = Path(folder_path).as_uri()
            if not file_uri.endswith("/"):
                file_uri += "/"

            # Set the URI in the text field (not the OS path)
            self.url_buffer.set_text(file_uri)

        chooser.destroy()

    def _validate_local_folder(
        self, folder_path: str, lang_override: str = ""
    ) -> tuple:
        """
        Validate a local or network folder path.

        Accepts both OS paths and ``file://`` URIs.

        Returns a ``(success, segments)`` tuple where *segments* is a list
        of ``(text, is_link)`` pairs suitable for
        :meth:`_set_status_segments`.

        :param folder_path: The folder path or ``file://`` URI to check.
        :param lang_override: When non-empty, use this language code instead
            of the running Gramps locale when selecting the JSON file to check.
        :returns: A ``(success, segments)`` tuple.
        """
        if folder_path.startswith("file://"):
            # Use urlparse + url2pathname so both POSIX
            # (file:///home/name/x) and Windows (file:///C:/Users/x) URIs
            # convert to a correct OS path. A manual string slice loses
            # the POSIX leading slash and mishandles percent-encoding.
            folder_path = url2pathname(urlparse(folder_path).path)
            folder_path = folder_path.rstrip("/\\")

        # Check if path exists
        if not os.path.exists(folder_path):
            return False, [
                (
                    _("❌ Error: Path does not exist:\n"),
                    False,
                ),
                (folder_path, True),
                (_("\n\nPlease check the path and try again."), False),
            ]

        if not os.path.isdir(folder_path):
            return False, [
                (_("❌ Error: Path is not a directory:\n"), False),
                (folder_path, True),
            ]

        # Check for listings folder
        listings_path = folder_path
        if not folder_path.endswith("listings"):
            test_listings = os.path.join(folder_path, "listings")
            if os.path.isdir(test_listings):
                listings_path = test_listings
            else:
                return False, [
                    (
                        _(
                            "❌ Error: Not a listings folder.\n\n"
                            "The selected folder should be named 'listings' or "
                            "contain a 'listings' subfolder.\n\nPath: "
                        ),
                        False,
                    ),
                    (folder_path, True),
                ]

        # Look for JSON files
        try:
            json_files = [f for f in os.listdir(listings_path) if f.endswith(".json")]
        except PermissionError:
            return False, [
                (_("❌ Error: Permission denied reading folder:\n"), False),
                (listings_path, True),
            ]

        if not json_files:
            return False, [
                (
                    _(
                        "⚠️  Warning: Listings folder found but no JSON files present.\n\nPath: "
                    ),
                    False,
                ),
                (listings_path, True),
                (
                    _(
                        "\n\nThe listings folder should contain files like:\n"
                        "  • addons-en.json\n"
                        "  • addons-fr.json\n"
                        "  • etc."
                    ),
                    False,
                ),
            ]

        # Check for language-specific file.
        # Honour the per-project language override when set; otherwise fall
        # back to the running Gramps locale.
        if lang_override:
            locale = lang_override
        else:
            locale = glocale.language[0] if glocale.language else "en"
        native_file = "addons-{}.json".format(locale)
        native_path = os.path.join(listings_path, native_file)
        fallback_path = os.path.join(listings_path, "addons-en.json")

        # Build segments list: (text, is_link)
        segs: list = []
        segs.append((_("✅ Success: Valid listings folder found!\n\nPath: "), False))
        segs.append((listings_path, True))  # clickable path → open folder
        segs.append((_("\n\nFound {} JSON file(s):\n").format(len(json_files)), False))
        for jf in sorted(json_files):
            jf_path = os.path.join(listings_path, jf)
            jf_uri = Path(jf_path).resolve().as_uri()
            segs.append(("  • ", False))
            segs.append((jf, True, jf_uri))  # clickable JSON filename
            segs.append(("\n", False))

        # Check native language file
        if os.path.exists(native_path):
            segs.append(
                (
                    _("\n✅ Native language file found: {}").format(native_file),
                    False,
                )
            )
            try:
                with open(native_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        segs.append(
                            (_("\n   Contains {} addon(s)").format(len(data)), False)
                        )
                    else:
                        segs.append(
                            (
                                _(
                                    "\n   ⚠️  Warning: Unexpected JSON format (not an array)"
                                ),
                                False,
                            )
                        )
            except json.JSONDecodeError as err:
                segs.append(
                    (_("\n   ⚠️  Warning: Invalid JSON: {}").format(str(err)), False)
                )
            except OSError as err:
                segs.append(
                    (
                        _("\n   ⚠️  Warning: Could not read file: {}").format(str(err)),
                        False,
                    )
                )

        elif os.path.exists(fallback_path):
            segs.append(
                (
                    _("\n⚠️  Native language file not found: {}").format(native_file),
                    False,
                )
            )
            segs.append((_("\n   Will fallback to: addons-en.json"), False))
            try:
                with open(fallback_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        segs.append(
                            (_("\n   Contains {} addon(s)").format(len(data)), False)
                        )
            except (OSError, json.JSONDecodeError) as err:
                segs.append(
                    (
                        _("\n   ⚠️  Warning: Could not read: {}").format(str(err)),
                        False,
                    )
                )
        else:
            segs.append(
                (
                    _("\n⚠️  Warning: Neither {} nor addons-en.json found").format(
                        native_file
                    ),
                    False,
                )
            )

        # Show what will be saved: the parent of the listings folder,
        # since Gramps appends "listings/addons-XX.json" itself.
        parent_path = Path(listings_path).resolve().parent
        save_uri = parent_path.as_uri().rstrip("/")
        segs.append((_("\n\n💾 Will be saved as: "), False))
        segs.append((save_uri, True))
        segs.append((_("\n   (Gramps will append '/listings/addons-XX.json')"), False))

        return True, segs

    @staticmethod
    def _browseable_url(raw_url: str) -> str:
        """
        Return a human-browseable URL for *raw_url*.

        Raw content hosts (e.g. ``raw.githubusercontent.com``) serve
        individual files correctly but return 404 for directory paths
        because there is no directory-listing endpoint.  This helper
        maps such hosts to the corresponding web UI URL so that directory
        links open in a browser rather than producing a 404.

        Currently handled mappings:

        * ``raw.githubusercontent.com/USER/REPO/BRANCH/PATH``
          → ``github.com/USER/REPO/tree/BRANCH/PATH``
        * ``gitlab.com/USER/REPO/-/raw/BRANCH/PATH``
          → ``gitlab.com/USER/REPO/-/tree/BRANCH/PATH``

        All other URLs are returned unchanged.

        :param raw_url: The URL to convert (may or may not end with ``/``).
        :returns: A browser-friendly URL suitable for :func:`display_url`.
        """
        parsed = urlparse(raw_url)
        host = parsed.netloc.lower()

        # raw.githubusercontent.com  →  github.com /tree/ view
        if host == "raw.githubusercontent.com":
            # path: /USER/REPO/BRANCH/...
            parts = parsed.path.lstrip("/").split("/", 3)
            if len(parts) >= 3:
                user, repo, branch = parts[0], parts[1], parts[2]
                remainder = parts[3].rstrip("/") if len(parts) == 4 else ""
                tree_path = (
                    "/{}/{}/tree/{}/{}".format(user, repo, branch, remainder)
                    if remainder
                    else "/{}/{}/tree/{}".format(user, repo, branch)
                )
                return "https://github.com" + tree_path
            return raw_url

        # gitlab.com /-/raw/  →  /-/tree/ view
        if host == "gitlab.com" and "/-/raw/" in parsed.path:
            return raw_url.replace("/-/raw/", "/-/tree/", 1).rstrip("/")

        return raw_url

    @staticmethod
    def _fetch_json(file_url: str) -> tuple:
        """Fetch and parse a JSON file from *file_url*.

        Tries the SSL contexts of :func:`_ssl_contexts` in order, moving
        to the next only after a certificate verification failure.

        :param file_url: The raw URL of the JSON file to retrieve.
        :returns: ``(data, err_text, is_ssl_error)`` where *data* is the
            parsed object on success and ``None`` on failure, *err_text*
            is a short translatable status string (empty on success), and
            *is_ssl_error* flags a certificate-verification failure so the
            caller can show one consolidated remediation message instead
            of repeating it for every file checked.
        """
        contexts = _ssl_contexts()
        try:
            req = Request(file_url, headers={"User-Agent": "Gramps"})
            for index, ctx in enumerate(contexts):
                try:
                    with urlopen(req, timeout=10, context=ctx) as response:
                        data = json.loads(response.read().decode("utf-8"))
                    return data, "", False
                except URLError as err:
                    if not _is_ssl_error(err) or index == len(contexts) - 1:
                        raise
        except HTTPError as err:
            if err.code == 404:
                return None, _("\n⚠️  Not found (404): {}").format(file_url), False
            return None, _("\n⚠️  HTTP Error {}: {}").format(err.code, file_url), False
        except URLError as err:
            reason = str(err.reason)
            # Detect SSL certificate errors specifically — common on macOS,
            # where Python does not use the system Keychain for certificate
            # verification. The full remediation text is shown once by the
            # caller rather than repeated here for each file checked.
            if "CERTIFICATE_VERIFY_FAILED" in reason or "SSL" in reason.upper():
                return (
                    None,
                    _("\n⚠️  SSL certificate verification failed: {}").format(reason),
                    True,
                )
            return (
                None,
                _(
                    "\n❌ Network Error: {}"
                    "\n\nPossible causes:"
                    "\n  • No internet connection"
                    "\n  • URL is incorrect"
                    "\n  • Server is down"
                    "\n  • Firewall blocking access"
                ).format(reason),
                False,
            )
        except json.JSONDecodeError as err:
            return (
                None,
                _("\n❌ Invalid JSON in {}\n   {}").format(file_url, str(err)),
                False,
            )

    def _validate_web_url(self, url: str, lang_override: str = "") -> tuple:
        """Validate a web URL by fetching its listings JSON files.

        Returns a ``(success, segments)`` tuple where *segments* is a list
        of ``(text, is_link[, href])`` tuples for :meth:`_set_status_segments`.
        Directory links use :meth:`_browseable_url` to avoid raw-host 404s.

        :param url: The base URL of the addon repository.
        :param lang_override: When non-empty, use this language code instead
            of the running Gramps locale when selecting the JSON file to check.
        """
        # Basic URL format check
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ["http", "https"]:
                return False, [
                    (
                        _(
                            "❌ Error: Invalid URL scheme.\n\nURL must start with "
                            "http:// or https://\n\nGiven: "
                        ),
                        False,
                    ),
                    (url, True),
                ]
            if not parsed.netloc:
                return False, [
                    (
                        _(
                            "❌ Error: Invalid URL format.\n\nURL must include a "
                            "domain name.\n\nExample: https://github.com/user/repo/raw/main/"
                        ),
                        False,
                    ),
                ]
        except ValueError as err:
            return False, [
                (_("❌ Error: Malformed URL.\n\n{}\n\nURL: ").format(str(err)), False),
                (url, True),
            ]

        # urljoin needs a trailing slash; the saved/displayed value must not have one.
        url_for_join = url if url.endswith("/") else url + "/"
        url_saved = url_for_join.rstrip("/")

        listings_url = urljoin(url_for_join, "listings/")
        listings_browse_url = self._browseable_url(listings_url)
        url_browse = self._browseable_url(url_for_join)

        # Honour the per-project language override when set.
        if lang_override:
            locale = lang_override
        else:
            locale = glocale.language[0] if glocale.language else "en"
        native_file = "addons-{}.json".format(locale)
        native_url = urljoin(listings_url, native_file)
        fallback_url = urljoin(listings_url, "addons-en.json")

        segs: list = [
            (_("Testing URL: "), False),
            (url_saved, True, url_browse),
            (_("\nListings folder: "), False),
            (listings_browse_url, True),
        ]
        if listings_browse_url != listings_url:
            segs.append((_("\n   (raw URL: {})").format(listings_url), False))

        _SAVE_SEGS = [
            (_("\n\n💾 Will be saved as: "), False),
            (url_saved, True, url_browse),
            (_("\n   (Gramps will append '/listings/addons-XX.json')"), False),
        ]

        # Try native language file first
        segs.append((_("\n\nChecking for: "), False))
        segs.append((native_file, True, native_url))
        native_data, native_err, native_ssl = self._fetch_json(native_url)

        if native_data is not None:
            segs.append((_("\n✅ Found: {}").format(native_file), False))
            if isinstance(native_data, list):
                segs.append(
                    (_("   Contains {} addon(s)").format(len(native_data)), False)
                )
            else:
                segs.append((_("   ⚠️  Warning: Unexpected JSON format"), False))
            segs = [(_("✅ Success: Repository validated\n\n"), False)] + segs
            segs.extend(_SAVE_SEGS)
            return True, segs

        # Native file not found — report and try English fallback
        segs.append((native_err, False))
        segs.append((_("\n\nChecking fallback: "), False))
        segs.append(("addons-en.json", True, fallback_url))
        fallback_data, fallback_err, fallback_ssl = self._fetch_json(fallback_url)

        if fallback_data is not None:
            segs.append((_("\n✅ Found: addons-en.json (fallback)"), False))
            if isinstance(fallback_data, list):
                segs.append(
                    (_("   Contains {} addon(s)").format(len(fallback_data)), False)
                )
            segs = [
                (_("✅ Success: Repository validated (using fallback)\n\n"), False)
            ] + segs
            segs.extend(_SAVE_SEGS)
            return True, segs

        # Distinguish error types so we can return the right success flag.
        # SSL errors mean the URL structure is likely correct but the local
        # Python installation cannot verify the certificate.  We treat this
        # as a soft pass (True) so the user can save the project; Gramps
        # itself uses a separate download path that may work.
        is_ssl_error = native_ssl or fallback_ssl

        if "404" in fallback_err:
            segs.append(
                (
                    _(
                        "\n❌ Not found: addons-en.json (404)"
                        "\n\nError: No listings found."
                        "\nThe URL should point to a folder containing:"
                        "\n  • listings/addons-en.json (required)"
                        "\n  • listings/addons-{}.json (optional)"
                    ).format(locale),
                    False,
                )
            )
            return False, segs

        # SSL certificate error — URL is probably valid; warn but allow
        # saving. The remediation text is shown once here rather than once
        # per file checked (native_err/fallback_err are already the short
        # single-line versions), and only mentions the macOS-specific fix
        # when actually running on macOS.
        if is_ssl_error:
            segs.append((fallback_err, False))
            segs = [
                (_("⚠️  SSL Warning: Certificate verification failed\n"), False),
                (
                    _(
                        "(URL structure appears valid — you may save and use "
                        "this repository)\n\n"
                    ),
                    False,
                ),
                (_ssl_remediation_text(), False),
                (_("\n\n"), False),
            ] + segs
            segs.extend(_SAVE_SEGS)
            return True, segs

        # Generic network or parse error
        segs.append((fallback_err, False))
        return False, segs

    def _set_status_text(self, text: str) -> None:
        """
        Set the status view to a plain text message (no links).

        :param text: The plain text to display.
        """
        self._link_map.clear()
        self.status_buffer.set_text(text)

    def _set_status_segments(self, segments) -> None:
        """
        Populate the status view from a list of ``(text, is_link[, href])``
        tuples.

        When *is_link* is ``True`` the segment is rendered as a clickable
        hyperlink.  An optional third element *href* overrides the link
        target; if omitted the segment text itself is used as the target
        (suitable for URLs and ``file://`` URIs inserted verbatim).

        :param segments: Iterable of 2- or 3-element tuples describing
            each piece of text.
        """
        if isinstance(segments, str):
            # Fallback: caller passed a plain string
            self._set_status_text(segments)
            return

        self._link_map.clear()
        self.status_buffer.set_text("")
        end_iter = self.status_buffer.get_end_iter()

        for item in segments:
            if len(item) == 3:
                text, is_link, href = item
            else:
                text, is_link = item
                href = text  # the text itself is the target

            if is_link and text.strip():
                # Create a unique anonymous tag for this link so we can
                # map it back to the URL on click.
                tag = self.status_buffer.create_tag(
                    None,
                    foreground="blue",
                    underline=Pango.Underline.SINGLE,
                )
                self._link_map[tag] = href
                self.status_buffer.insert_with_tags(end_iter, text, tag)
            else:
                self.status_buffer.insert(end_iter, text)

    def _open_link(self, target: str) -> None:
        """
        Open *target* in the appropriate viewer.

        Folders and ``file://`` URIs open in the file manager (or the
        program for that file type); http/https opens in the web browser.

        :param target: The URI or URL to open.
        """
        if not target.startswith(("http://", "https://", "file://")):
            target = Path(target).resolve().as_uri()  # an OS path
        _open_uri(target)

    def _on_status_click(self, widget, event) -> bool:
        """
        Handle button-release events on the status view.

        Detects whether the click landed on a hyperlink tag and opens
        the associated URL/path.

        :param widget: The :class:`Gtk.TextView` that received the event.
        :param event: The :class:`Gdk.EventButton`.
        :returns: ``False`` so the event propagates normally.
        """
        if event.button != 1:
            return False
        buf_x, buf_y = widget.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(event.x), int(event.y)
        )
        text_iter = widget.get_iter_at_location(buf_x, buf_y)
        if text_iter is None:
            return False
        # get_iter_at_location returns (bool, iter) in newer PyGObject
        if isinstance(text_iter, tuple):
            _hit, text_iter = text_iter
        for tag in text_iter.get_tags():
            if tag in self._link_map:
                self._open_link(self._link_map[tag])
                return True
        return False

    def _on_status_motion(self, widget, event) -> bool:
        """
        Change the cursor to a hand pointer when hovering over a link.

        :param widget: The :class:`Gtk.TextView`.
        :param event: The :class:`Gdk.EventMotion`.
        :returns: ``False`` so the event propagates normally.
        """
        buf_x, buf_y = widget.window_to_buffer_coords(
            Gtk.TextWindowType.WIDGET, int(event.x), int(event.y)
        )
        text_iter = widget.get_iter_at_location(buf_x, buf_y)
        if isinstance(text_iter, tuple):
            _hit, text_iter = text_iter
        over_link = False
        if text_iter is not None:
            for tag in text_iter.get_tags():
                if tag in self._link_map:
                    over_link = True
                    break
        gdk_window = widget.get_window(Gtk.TextWindowType.TEXT)
        if gdk_window:
            cursor = (
                Gdk.Cursor.new_for_display(
                    gdk_window.get_display(), Gdk.CursorType.HAND2
                )
                if over_link
                else None
            )
            gdk_window.set_cursor(cursor)
        return False

    def _on_response(self, dialog, response_id):
        """
        Handle dialog response.

        Gramps Addon Manager expects URLs in specific formats:

        - Web: ``http://example.com/path/to/repo`` (no trailing slash)
        - Local: ``file:///C:/path/to/repo`` (Windows, no trailing slash)
        - Local: ``file:///path/to/repo`` (Unix, no trailing slash)

        Gramps appends ``/listings/addons-XX.json`` itself.
        Local paths, including Windows paths typed or pasted from File
        Explorer, are converted to ``file://`` URIs automatically.
        """
        if response_id == Gtk.ResponseType.HELP:
            # Test button clicked - validate
            self._test_url()
            dialog.stop_emission_by_name("response")  # Don't close dialog

        elif response_id == Gtk.ResponseType.OK:
            # OK button - save result
            url_text = _normalize_location_text(self._get_url_text())
            is_folder = self.folder_radio.get_active()

            # For web URLs: strip any /listings suffix (Gramps appends it
            # itself) and remove any trailing slash.  The stored URL must
            # NOT end with "/" because download paths are built by simple
            # string concatenation: addon["_u"] + "/download/" + filename.
            if not is_folder and url_text:
                url_text = url_text.rstrip("/")
                if url_text.endswith("/listings"):
                    url_text = url_text[:-9]  # Remove trailing '/listings'
                url_text = url_text.rstrip("/")

            # For file:// URIs, normalization already produced the correct
            # format.  Strip any trailing slash for consistency.
            if is_folder and url_text:
                url_text = url_text.rstrip("/")

            self.result = {
                "name": self.name_entry.get_text().strip(),
                "url": url_text,
                "is_folder": is_folder,
                "lang": self._get_active_lang(),
            }

    def _test_url(self):
        """
        Validate the current URL/Path and update the status area.

        When a language override is selected the validation uses that
        language code to probe the matching ``addons-XX.json`` file.
        After a successful local-folder probe the language combo is
        repopulated with the codes discovered in that folder.
        """
        self._set_status_text(_("Validating...\n\nPlease wait..."))

        # Force UI update
        while Gtk.events_pending():
            Gtk.main_iteration()

        raw_text = self._get_url_text()
        if not raw_text:
            self._set_status_text(_("❌ Error: URL/Path cannot be empty."))
            return

        url_text = _normalize_location_text(raw_text)
        lang_override = self._get_active_lang()

        # Auto-detect type: file:// URIs are folders, http/https are web.
        # Anything else is treated as a web URL for validation purposes.
        if url_text.startswith("file://"):
            _success, segments = self._validate_local_folder(
                url_text, lang_override=lang_override
            )
        else:
            _success, segments = self._validate_web_url(
                url_text, lang_override=lang_override
            )

        if url_text != raw_text:
            # Reflect the normalized form back to the user so they can
            # see their typed path was recognized and converted.
            self.url_buffer.set_text(url_text)
            prefix_seg = [
                (_("ℹ️  Converted to: "), False),
                (url_text, True),
                ("\n\n", False),
            ]
            if isinstance(segments, str):
                segments = prefix_seg + [(segments, False)]
            else:
                segments = prefix_seg + segments

        self._set_status_segments(segments)

    def run(self):
        """
        Run the dialog and return the result.

        Schedules :meth:`_focus_after_map` via :func:`GLib.idle_add` before
        blocking in :meth:`Gtk.Dialog.run`, so the window-manager focus
        request happens *after* the dialog window has actually been
        mapped rather than immediately before ``run()`` is called.

        ``show_all()`` (called earlier, while the interface was being
        built) only *requests* that the window be mapped -- it does not
        block until the window manager has finished creating it. Calling
        ``present_with_time`` right there, before ``run()``, could still
        run before that mapping completes, which is why doing so did not
        reliably fix the "needs two clicks" symptom. Queuing it with
        :func:`GLib.idle_add` lets the main loop process the pending map
        first, since idle callbacks only run once no higher-priority
        events (including that mapping) are left pending.

        :returns: A dictionary with ``name``, ``url``, and ``is_folder``
            keys, or ``None`` if the dialog was cancelled.
        """
        timestamp = Gtk.get_current_event_time()
        GLib.idle_add(self._focus_after_map, timestamp)
        self.dialog.run()
        self.dialog.destroy()
        return self.result

    def _focus_after_map(self, timestamp: int) -> bool:
        """
        Give the dialog window-manager focus once it has been mapped.

        A plain ``present()`` is not enough here: it passes a timestamp of
        ``0`` (``GDK_CURRENT_TIME``), which focus-stealing-prevention in
        many window managers treats as "no timestamp" and ignores, so the
        window is raised but not focused -- leaving the first click on any
        widget, such as "Test Location", to only focus/activate the window
        instead of the widget. Using the real timestamp of the event that
        opened this dialog avoids that.

        :param timestamp: The timestamp captured synchronously in
            :meth:`run`, before this callback was scheduled -- an idle
            callback runs with no event of its own, so it cannot obtain a
            valid timestamp itself.
        :returns: ``False`` so :func:`GLib.idle_add` runs this only once.
        """
        self.dialog.present_with_time(timestamp)
        return False


# -------------------------------------------------------------------------
#
# GetAddons
#
# -------------------------------------------------------------------------


# -------------------------------------------------------------------------
#
# GetAddons
#
# -------------------------------------------------------------------------
class GetAddons(threading.Thread):
    """
    Retrieve the addon listings of all enabled projects as a background
    task, keeping a reason for each enabled project that gave no addons.

    Per-project language codes (``project[3]``) and the "Include English"
    option are honoured; see :func:`_load_projects`.
    """

    def __init__(self, callback, projects, include_english=False, cache=None):
        threading.Thread.__init__(self)
        self.callback = callback
        self.projects = [list(project) for project in projects]
        self.include_english = include_english
        self.cache = dict(cache or {})  # a snapshot; the window owns the cache
        self.addon_list = []
        self.problems = []  # [(project name, url, reason, is_ssl), ...]
        self.enabled = 0
        self.fetched = {}

    def emit_signal(self):
        self.callback(self.addon_list, self.problems, self.enabled, self.fetched)

    def run(self):
        # Never let an exception escape here: emit_signal would then never
        # run and the list would show "Loading..." forever.
        try:
            (
                self.addon_list,
                self.problems,
                self.enabled,
                self.fetched,
            ) = _load_projects(self.projects, self.include_english, self.cache)
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Addon Marketplace: loading the catalogs failed", exc_info=True)
            self.enabled = sum(1 for project in self.projects if project[2])
            self.problems = [
                (project[0], project[1], _("the catalog could not be loaded"), False)
                for project in self.projects
                if project[2]
            ]
        GLib.idle_add(self.emit_signal)


def _effective_language(lang_override):
    """
    The language a project catalog is read in: its language code, or the
    first language of Gramps.
    """
    if lang_override:
        return lang_override.strip()
    langs = glocale.get_language_list()
    return langs[0] if langs else "en"


def _project_needs_english(lang_override):
    """
    Whether a project read in *lang_override* (or the Gramps language, when
    empty) would get anything new from an extra English catalog.
    """
    return not _effective_language(lang_override).lower().startswith("en")


def _should_offer_include_english(projects):
    """
    Whether the "Include English" option is relevant: the Gramps language
    is not English, or an enabled project has a non-English language code.
    """
    if _project_needs_english(""):
        return True
    return any(
        project[2] and _project_needs_english(project[3] if len(project) > 3 else "")
        for project in projects
    )


def _as_str_list(value):
    """
    A catalog list of names: a list of strings; a single string becomes a
    one-item list; anything else becomes an empty list.
    """
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _as_int(value, default):
    """
    A catalog number: an int (not a bool), or an int written as text;
    else *default*.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return default


# The register() field name of each short catalog key. Catalogs written by
# Gramps' make.py use only the short keys, and Gramps 5.2 to 6.1 read only
# those; a catalog may also carry any register() field under its own name
# (preferred when both are present). The rest of this module reads the
# short keys, so _normalize_catalog_entry() fills both.
_REGISTER_TO_SHORT = {
    "id": "i",
    "name": "n",
    "version": "v",
    "description": "d",
    "ptype": "t",
    "status": "s",
    "audience": "a",
    "help_url": "h",
    "gramps_target_version": "g",
    "requires_mod": "rm",
    "requires_gi": "rg",
    "requires_exe": "re",
    "depends_on": "do",
}
# register() fields that are lists of names
_NAME_LIST_FIELDS = (
    "authors",
    "authors_email",
    "maintainers",
    "maintainers_email",
)


def _normalize_catalog_entry(entry):
    """
    One addon of a catalog (listings/addons-xx.json), made safe for the
    rest of this module, which then reads its keys directly.

    Catalogs are written by many projects and change over time, so every
    key is checked here, once. Unknown keys are kept as they are. An
    entry without a usable id ("i") or download file ("z") is useless and
    gives None. Unknown type, audience or status numbers are kept; the
    lozenges show them through _catalog_label().

    :returns: a new dict, or None to skip the entry.
    """
    if not isinstance(entry, dict):
        return None
    entry = dict(entry)
    for long_key, short_key in _REGISTER_TO_SHORT.items():
        if entry.get(long_key) is not None:  # register() name wins
            entry[short_key] = entry[long_key]
    addon_id = entry.get("i")
    download = entry.get("z")
    if not isinstance(addon_id, str) or not addon_id.strip():
        return None
    if not isinstance(download, str) or not download.strip():
        return None
    addon = dict(entry)  # unknown keys pass through
    addon["i"] = addon_id.strip()
    addon["z"] = download.strip()
    name = entry.get("n")
    addon["n"] = name if isinstance(name, str) and name.strip() else addon["i"]
    version = entry.get("v")
    if isinstance(version, (int, float)) and not isinstance(version, bool):
        version = str(version)
    addon["v"] = version.strip() if isinstance(version, str) else ""
    for key in ("d", "h"):
        addon[key] = entry.get(key) if isinstance(entry.get(key), str) else ""
    addon["t"] = _as_int(entry.get("t"), -1)  # -1: no type given
    addon["a"] = _as_int(entry.get("a"), 0)
    addon["s"] = _as_int(entry.get("s"), 0)
    for key in ("rm", "re", "do"):
        if key in entry:
            addon[key] = _as_str_list(entry.get(key))
    for key in _NAME_LIST_FIELDS:
        if key in entry:
            addon[key] = _as_str_list(entry.get(key))
    # keep the register() names equal to the checked short keys
    for long_key, short_key in _REGISTER_TO_SHORT.items():
        if long_key in entry and short_key in addon:
            addon[long_key] = addon[short_key]
    if "rg" in entry:
        specs = entry.get("rg")
        addon["rg"] = [
            [spec[0], spec[1]]
            for spec in (specs if isinstance(specs, (list, tuple)) else [])
            if isinstance(spec, (list, tuple))
            and len(spec) >= 2
            and isinstance(spec[0], str)
            and isinstance(spec[1], str)
        ]
        if "requires_gi" in entry:
            addon["requires_gi"] = addon["rg"]
    return addon


def _normalize_catalog(entries, source=""):
    """
    All usable addons of a loaded catalog (see _normalize_catalog_entry).
    A catalog that is not a list gives []. Skipped entries are logged.
    """
    if not isinstance(entries, list):
        LOG.warning("Addon Marketplace: the catalog %s is not a list", source)
        return []
    addons = [_normalize_catalog_entry(entry) for entry in entries]
    skipped = addons.count(None)
    if skipped:
        LOG.warning(
            "Addon Marketplace: skipped %d unusable entries (no id or no "
            "download file) in the catalog %s",
            skipped,
            source,
        )
    return [addon for addon in addons if addon is not None]


def _catalog_label(table, value):
    """
    The text for a catalog type, audience or status number; an unknown
    number (for example a type added in a newer Gramps) gets a plain
    "Unknown" text instead of an error.
    """
    if value in table:
        return table[value]
    if value == -1:
        return _("Unknown")
    return _("Unknown (%s)") % value


def _get_addons_in(project, url, langs):
    """
    Like gramps.gen.plug.utils.get_addons(), but trying the catalogs of
    *langs* (then English) instead of the Gramps languages, without
    changing the language of Gramps itself, which other threads use.

    :returns: the addon dicts, or [] when no catalog could be read.
    """
    if not url.startswith(("http://", "https://", "file://")):
        return []
    fptr = None
    for lang in list(langs) + ["en"]:
        for code in dict.fromkeys((lang, lang[:2])):
            try:
                fptr = urlopen_maybe_no_check_cert(
                    "%s/listings/addons-%s.json" % (url, code)
                )
                break
            except Exception:  # same broad catch as get_addons()
                fptr = None
        if fptr is not None:
            break
    if fptr is None:
        return []
    with fptr:
        addon_list = _normalize_catalog(json.load(fptr), "%s (%s)" % (project, url))
    pmgr = GuiPluginManager.get_instance()
    for plugin_dict in addon_list:
        plugin_dict["_p"] = project
        plugin_dict["_u"] = url
        plugin = pmgr.get_plugin(plugin_dict["i"])
        if plugin:
            plugin_dict["_v"] = plugin.version
    return addon_list


def _catalog_key(name, url, lang):
    """
    The cache key of one catalog: project name (it is written into each
    addon), comparison form of the address and language ("+en" for the
    extra English catalog).
    """
    return (name, _url_key(url), lang)


def _project_keys(projects, include_english):
    """
    The catalog keys that the enabled *projects* need.
    """
    keys = []
    for project in projects:
        if not project[2]:
            continue
        lang = project[3].strip() if len(project) > 3 and project[3] else ""
        keys.append(_catalog_key(project[0], project[1], lang))
        if include_english and _project_needs_english(lang):
            keys.append(_catalog_key(project[0], project[1], "+en"))
    return keys


def _fetch_catalog(name, url, lang):
    """
    Download one catalog. *lang* is a language code, "" for the Gramps
    languages, or "+en" for the extra English catalog.

    :returns: (addons, problem); *problem* is None or (reason, is_ssl).
    """
    if lang == "+en":
        try:
            english = _get_addons_in(name, url, ["en"])
        except Exception:  # pylint: disable=broad-except
            english = []
        for addon in english:
            addon["_p"] = "%s + en" % name
        return english, None  # its main catalog reports any problem
    try:
        if lang:
            langs = [lang] + [
                code for code in glocale.get_language_list() if code != lang
            ]
            addons = _get_addons_in(name, url, langs)
        else:
            # not Gramps' get_addons(): one bad entry there loses the
            # whole catalog; _get_addons_in() normalizes each entry
            addons = _get_addons_in(name, url, glocale.get_language_list())
    except Exception:  # e.g. a listing that is not valid JSON
        LOG.warning("Addon Marketplace: the %s catalog failed to load", name)
        addons = []
    if not addons:
        return [], _probe_listing(url)
    return addons, None


def _load_projects(projects, include_english=False, cache=None):
    """
    Load the catalogs of the enabled *projects* ([name, url, enabled,
    language code]).

    A project with a language code reads that catalog first. With
    *include_english*, a project read in another language also gets its
    English catalog, listed as the project "<name> + en".

    :param cache: {catalog key: (addons, problem)} of catalogs already
        downloaded; only the others are downloaded.
    :returns: (addon_list, problems, enabled count, fetched); *problems*
        has a (name, url, reason, is_ssl) entry for each enabled project
        that gave no addons, *fetched* the newly downloaded catalogs.
    """
    cache = cache or {}
    fetched = {}
    addon_list, problems, enabled = [], [], 0
    for project in projects:
        name, url, active = project[0], project[1], project[2]
        lang = project[3].strip() if len(project) > 3 and project[3] else ""
        if not active:
            continue
        enabled += 1
        wanted = [lang]
        if include_english and _project_needs_english(lang):
            wanted.append("+en")
        for code in wanted:
            key = _catalog_key(name, url, code)
            if key in cache:
                addons, problem = cache[key]
            else:
                addons, problem = fetched[key] = _fetch_catalog(name, url, code)
            if problem:
                problems.append((name, url) + tuple(problem))
                break  # no English catalog for a project that failed
            addon_list.extend(addons)
    return addon_list, problems, enabled, fetched


def _available_updates_for(projects):
    """
    Like gramps.gen.plug.utils.available_updates(), but reading the
    catalogs with the language codes of *projects*.

    :returns: [(label, download url, addon dict), ...]
    """
    whattypes = config.get("behavior.check-for-addon-update-types")
    skip_seen = config.get("behavior.do-not-show-previously-seen-addon-updates")
    seen = config.get("behavior.previously-seen-addon-updates")
    updates = []
    addon_list, _problems, _enabled, _fetched = _load_projects(projects)
    for plugin_dict in addon_list:
        if skip_seen and plugin_dict["i"] in seen:
            continue
        url = "%s/download/%s" % (plugin_dict["_u"].rstrip("/"), plugin_dict["z"])
        if "_v" in plugin_dict:
            if "update" in whattypes and version_str_to_tup(
                plugin_dict["v"], 3
            ) > version_str_to_tup(plugin_dict["_v"], 3):
                updates.append((_("Updated"), url, plugin_dict))
        elif "new" in whattypes:
            updates.append((_("New", "updates"), url, plugin_dict))
    config.set(
        "behavior.last-check-for-addon-updates",
        datetime.date.today().strftime("%Y/%m/%d"),
    )
    return updates


def _probe_listing(url):
    """
    Explain why a project gave no addons. Gramps' get_addons() only logs
    its errors, so open the English listing once more to find the reason.

    :returns: (reason, is_ssl); *is_ssl* flags a certificate problem.
    """
    if not url.startswith(("http://", "https://", "file://")):
        return _("not a web (https://) or folder (file://) location"), False
    raw_url = _github_raw_url(url)
    if raw_url != url:
        return (
            _("a GitHub page, not a catalog; use this address instead: %s") % raw_url,
            False,
        )
    listing = url.rstrip("/") + "/listings/addons-en.json"
    try:
        with urlopen_maybe_no_check_cert(listing) as fptr:
            raw = fptr.read()
        if raw.lstrip()[:1] == b"<":
            return _("the address returns a web page, not a catalog"), False
        data = json.loads(raw.decode("utf-8"))
    except HTTPError as err:
        if err.code == 404:
            return _("catalog not found (404)"), False
        return _("web server error %d") % err.code, False
    except URLError as err:
        if isinstance(err.reason, FileNotFoundError):
            return _("catalog file not found"), False
        reason = str(err.reason)
        if (
            isinstance(err.reason, ssl.SSLError)
            or "CERTIFICATE_VERIFY_FAILED" in reason
        ):
            return _("the security certificate could not be verified"), True
        return _("cannot connect: %s") % reason, False
    except ValueError:
        return _("catalog is not valid JSON"), False
    except OSError as err:
        return _("cannot read the catalog: %s") % err, False
    if not data:
        return _("catalog lists no addons"), False
    return _("catalog could not be read in this language"), False


# -------------------------------------------------------------------------
#
# ProjectPickerDialog
#
# -------------------------------------------------------------------------
class ProjectPickerDialog:
    """
    A list of addon projects, each with a check box, from which the user
    picks the ones to add.
    """

    def __init__(self, parent, projects):
        self.projects = projects
        self.result = []
        self.dialog = Gtk.Dialog(
            title=_("Add projects"),
            transient_for=parent,
            modal=True,
            destroy_with_parent=True,
        )
        self.dialog.set_default_size(460, 640)
        # so any lozenges.css rules apply here too
        self.dialog.get_style_context().add_class("addon-marketplace")
        self.dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        self.add_button = self.dialog.add_button(_("_Add"), Gtk.ResponseType.OK)
        self.add_button.set_sensitive(False)
        self.dialog.set_default_response(Gtk.ResponseType.OK)

        area = self.dialog.get_content_area()
        area.set_spacing(6)
        area.set_border_width(12)
        # %s is the linked phrase, kept as one string for translators
        link_text = _("known curated addon collections")
        intro = Gtk.Label()
        intro.set_markup(
            escape(_("Select from published list of %s."))
            % (
                '<a href="%s">%s</a>'
                % (escape(CURATED_COLLECTIONS_URL, quote=True), escape(link_text))
            )
        )
        intro.set_track_visited_links(False)
        intro.set_tooltip_text(CURATED_COLLECTIONS_URL)
        intro.connect("activate-link", lambda _label, uri: _open_uri(uri) or True)
        intro.set_line_wrap(True)
        intro.set_xalign(0)
        area.pack_start(intro, False, False, 0)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.checks = []
        for name, url, enabled in projects:
            row = Gtk.Box(spacing=12)
            row.set_margin_top(3)
            row.set_margin_bottom(3)
            check = Gtk.CheckButton()
            check.connect("toggled", self.__check_toggled)
            self.checks.append(check)
            # double-click the folder icon to open the home of the project:
            # the GitHub repository, or the folder one level above
            folder = _project_folder_icon()
            _set_project_location(folder, url)
            title = _project_name_label()
            title.set_text(name)
            row.pack_start(check, False, False, 0)
            row.pack_start(folder, False, False, 0)
            row.pack_start(title, True, True, 0)
            listbox.add(row)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(listbox)
        area.pack_start(scroll, True, True, 0)

        self.dialog.show_all()

    def __check_toggled(self, _check):
        self.add_button.set_sensitive(any(c.get_active() for c in self.checks))

    def run(self):
        """
        Run the dialog.

        :returns: the checked projects, or [] when cancelled.
        """
        if self.dialog.run() == Gtk.ResponseType.OK:
            self.result = [
                project
                for project, check in zip(self.projects, self.checks)
                if check.get_active()
            ]
        self.dialog.destroy()
        return self.result


# -------------------------------------------------------------------------
#
# ProjectRow
#
# -------------------------------------------------------------------------
class ProjectRow(Gtk.ListBoxRow):
    """
    A class to display an external addons repository.
    """

    def __init__(self, manager, project):
        Gtk.ListBoxRow.__init__(self)
        self.manager = manager
        self.project = project

        hbox = Gtk.Box()
        hbox.set_spacing(12)
        hbox.set_margin_top(3)
        hbox.set_margin_bottom(3)

        self.check = Gtk.CheckButton()
        hbox.pack_start(self.check, False, False, 0)

        # double-click the folder icon to open the home of the project;
        # double-click the name or the rest of the row to edit the project
        self.folder = _project_folder_icon()
        hbox.pack_start(self.folder, False, False, 0)
        self.name = _project_name_label()
        hbox.pack_start(self.name, True, True, 0)

        self.add(hbox)
        self.show_all()

        self.update()
        self.check.connect("toggled", self.__check_toggled)

    def __check_toggled(self, check):
        self.project[2] = check.get_active()
        # gramps.ini keeps [name, url, enabled]; the language code is in
        # AddonMarketplace.ini
        projects = [row.project[:3] for row in self.manager.project_list]
        config.set("behavior.addons-projects", projects)
        self.manager.update_project_list()
        self.manager.schedule_refresh()

    def update(self):
        """
        Update the row when the project data has been updated.
        """
        _set_project_location(self.folder, self.project[1])
        self.name.set_text(self.project[0])
        self.check.set_active(self.project[2])


def _update_status_lozenge(label: Gtk.Label, combo: Gtk.ComboBoxText) -> None:
    """
    Refresh a leftmost status-filter lozenge's text and highlight state.

    Unlike the other filter lozenges, this one is not tied to a fixed
    per-addon value: it always mirrors whichever entry is currently
    selected in *combo* (:attr:`AddonMarketplace.addon_combo`), and is
    highlighted whenever that selection is not "All addons" (index 0).

    Shared by :class:`AddonRow` (initial creation and click handling) and
    :class:`AddonManager` (bulk refresh on any filter change) so the two
    call sites cannot drift out of sync.

    :param label: The lozenge's inner label widget.
    :param combo: The addon-status filter combo, whose index 0 entry is
        always "All addons".
    """
    label.set_text(combo.get_active_text())
    ctx = label.get_style_context()
    if combo.get_active() != 0:
        ctx.add_class("lozenge-active")
        label.set_tooltip_text(_("Click to clear this filter"))
    else:
        ctx.remove_class("lozenge-active")
        label.set_tooltip_text(_("Addons are not filtered by status"))


def _download_url(addon):
    """
    The download address of an addon: its project address (without a
    trailing slash, since a double slash gives a 404 on some servers),
    "/download/" and its file name.
    """
    return "%s/download/%s" % (addon["_u"].rstrip("/"), addon["z"])


# -------------------------------------------------------------------------
#
# AddonRow
#
# -------------------------------------------------------------------------
class AddonRow(Gtk.ListBoxRow):
    """
    A class representing an addon in the Addon Marketplace.
    """

    def __init__(self, manager, addon, req, window):
        Gtk.ListBoxRow.__init__(self)
        self.manager = manager
        self.addon = addon
        self.req = req
        self.window = window

        context = self.get_style_context()
        context.add_class("addon-row")

        # the installed version, from the live plugin registry: the catalog
        # may have been read before an install or update
        pdata = GuiPluginManager.get_instance().get_plugin(addon["i"])
        if pdata is not None:
            addon["_v"] = pdata.version
        else:
            addon.pop("_v", None)

        self.vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.vbox.set_spacing(6)
        self.__build_gui(self.vbox, self.addon, self.req)
        self.add(self.vbox)
        self.show_all()

    def __build_gui(self, vbox, addon, req):
        """
        Build the GUI for this addon row.
        """
        for child in vbox.get_children():
            vbox.remove(child)

        text = escape(addon["n"])
        title = Gtk.Label()
        title.set_text('<span size="larger" weight="bold">%s</span>' % text)
        title.set_use_markup(True)
        title.set_halign(Gtk.Align.CENTER)
        vbox.pack_start(title, False, False, 0)

        hbox = Gtk.Box()
        hbox.set_spacing(3)
        lozenge = self.__create_status_lozenge()
        hbox.pack_start(lozenge, False, False, 0)
        lozenge = self.__create_lozenge_button(
            _("Project"), addon["_p"], self.manager.project_combo
        )
        hbox.pack_start(lozenge, False, False, 0)
        lozenge = self.__create_lozenge_button(
            _("Type"), _catalog_label(PTYPE_STR, addon["t"]), self.manager.type_combo
        )
        hbox.pack_start(lozenge, False, False, 0)
        lozenge = self.__create_lozenge_button(
            _("Audience"),
            _catalog_label(AUDIENCETEXT, addon["a"]),
            self.manager.audience_combo,
        )
        hbox.pack_start(lozenge, False, False, 0)
        lozenge = self.__create_lozenge_button(
            _("Status"),
            _catalog_label(STATUSTEXT, addon["s"]),
            self.manager.status_combo,
        )
        hbox.pack_start(lozenge, False, False, 0)
        # version_status is None when the installed and repository versions
        # match (or nothing is installed), "update" when the repository
        # version is newer than what is installed, and "downgrade" when the
        # repository version is older than what is installed.
        version_status = None
        if "_v" in addon and addon["_v"] != addon["v"]:
            repo_version = version_str_to_tup(addon["v"], 3)
            installed_version = version_str_to_tup(addon["_v"], 3)
            if repo_version > installed_version:
                version_status = "update"
            elif repo_version < installed_version:
                version_status = "downgrade"

        lozenge = self.__create_lozenge(_("Repository version"), addon["v"])
        hbox.pack_start(lozenge, False, False, 0)
        if "_v" in addon:
            if version_status == "downgrade":
                extra_class = "lozenge-warn"
            elif version_status == "update":
                extra_class = "lozenge-caution"
            else:
                extra_class = None

            if extra_class:
                # Flag the installed-version lozenge and let it double as
                # a shortcut to the "Updates" filter, just like the
                # Project/Type/Audience/Status lozenges above.
                lozenge = self.__create_lozenge_button(
                    _("Installed version"),
                    addon["_v"],
                    self.manager.addon_combo,
                    filter_text=_("Updates"),
                    extra_class=extra_class,
                )
            else:
                lozenge = self.__create_lozenge(_("Installed version"), addon["_v"])
            hbox.pack_end(lozenge, False, False, 0)

        vbox.pack_start(hbox, False, False, 0)

        text = addon["d"]
        descr = Gtk.Label()
        descr.set_text(text)
        descr.set_halign(Gtk.Align.START)
        descr.set_hexpand(False)
        descr.set_line_wrap(True)
        descr.set_line_wrap_mode(Pango.WrapMode.WORD)
        vbox.pack_start(descr, False, False, 0)

        bb = Gtk.Box()
        bb.set_spacing(6)

        if "_v" not in addon and req.check_addon(addon, install=True):
            b1 = Gtk.Button(label=_("Install"))
            b1.set_label(_("Install"))
            b1.connect("clicked", self.__on_install_clicked, addon)
            bb.pack_end(b1, False, False, 0)

        if addon["h"]:
            b2 = Gtk.Button(label=_("Wiki"))
            b2.connect("clicked", self.__on_wiki_clicked, addon["h"])
            bb.pack_start(b2, False, False, 0)

        if not req.check_addon(addon) or addon.get("rm"):
            b3 = Gtk.Button(label=_("Requires"))
            b3.connect("clicked", self.__on_requires_clicked, addon)
            bb.pack_start(b3, False, False, 0)

        if version_status == "update":
            b4 = Gtk.Button(label=_("Update"))
            b4.connect("clicked", self.__on_update_clicked, addon)
            bb.pack_end(b4, False, False, 0)
        elif version_status == "downgrade":
            b4 = Gtk.Button(label=_("Downgrade"))
            b4.connect("clicked", self.__on_update_clicked, addon)
            bb.pack_end(b4, False, False, 0)

        vbox.pack_start(bb, False, False, 0)
        vbox.show_all()

    def _install_python_deps(self, button, addon):
        """
        Install the Python modules an addon requires.

        Uses the Gramps 6.1 PyPI helpers when present; otherwise falls
        back to pip. Returns True on success. On failure, disables
        *button*, shows an error dialog and returns False.
        """
        packages = self.req.install(addon)
        if not packages:
            return True
        progress = _PipProgress(self.window)
        try:
            for package in packages:
                error = progress.install(package)
                if error is None:
                    continue
                if error:  # failed, not cancelled
                    button.set_sensitive(False)
                    InfoDialog(
                        _("Module installation failed"), error, parent=self.window
                    )
                return False
        finally:
            progress.close()
        return True

    def __on_install_clicked(self, button, addon):
        """
        Install the addon and possibly some required python modules.
        """
        if not self._install_python_deps(button, addon):
            return

        # Invalidate the caches to ensure that the new modules will be found.
        importlib.invalidate_caches()

        if not self.req.check_addon(addon):
            InfoDialog(
                _("Module installation failed"),
                _("Gramps was unable to install the required modules"),
                parent=self.window,
            )
            return

        # Install addons this one depends on ("do" = depends_on, Gramps 6.1
        # listings). Older listings have no "do" key, so this is skipped.
        pmgr = GuiPluginManager.get_instance()
        for dep_id in addon.get("do", []):
            if pmgr.get_plugin(dep_id) is None:
                dep = self.manager.find_addon(dep_id)
                if dep is not None:
                    if not self._install_python_deps(button, dep):
                        return
                    importlib.invalidate_caches()
                    dep_path = _download_url(dep)
                    if load_addon_file(dep_path):
                        self.manager.install_addon(dep_id)

        # Install addon
        path = _download_url(addon)
        if not load_addon_file(path, callback=LOG.debug):
            InfoDialog(
                _("Addon installation failed"),
                _("Gramps was unable to install '%s'.") % addon["n"],
                parent=self.window,
            )
            return
        _remember_installed_offers({addon["i"]: addon["v"]})
        self.manager.install_addon(addon["i"])
        self.manager.refresh()

    def __on_wiki_clicked(self, button, url):
        """
        Display the wiki page for the addon.
        """
        if url.startswith(("http://", "https://")):
            display_url(url)
        else:
            display_help(url)

    def __on_requires_clicked(self, button, addon):
        """
        Display the requirements for the addon.
        """
        _show_requirements_checklist(self.window, addon)

    def __on_update_clicked(self, button, addon):
        """
        Install the repository's current version of the addon.

        Shared by both the "Update" and "Downgrade" buttons: in either case
        the addon is re-downloaded and replaced with whatever version the
        repository currently offers.
        """
        path = _download_url(addon)
        if not load_addon_file(path, callback=LOG.debug):
            InfoDialog(
                _("Addon download failed"),
                _(
                    "Could not download or install '{name}'.\n\n"
                    "URL tried:\n{url}\n\n"
                    "Check that the project URL is correct and that "
                    "you have a working internet connection."
                ).format(name=addon.get("n", addon["i"]), url=path),
                parent=self.window,
            )
            return
        _remember_installed_offers({addon["i"]: addon["v"]})
        self.manager.update_addon(addon["i"])
        self.manager.refresh()

    def __create_status_lozenge(self):
        """
        The first lozenge: it shows the installed-state filter (for example
        "New or Updated") and is gold while that filter is set; a click
        then sets it back to "All addons".
        """
        combo = self.manager.addon_combo
        label = Gtk.Label()
        label.get_style_context().add_class("lozenge")
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_focus_on_click(False)
        button.add(label)
        button.get_style_context().add_class("lozenge-button")
        # found by AddonMarketplace.__refresh_lozenge_colours
        button._status_lozenge_data = (label, combo)
        _update_status_lozenge(label, combo)
        button.connect("clicked", self.__on_status_lozenge_clicked, label, combo)
        return button

    def __on_status_lozenge_clicked(self, _button, label, combo):
        """
        Set the installed-state filter back to "All addons".
        """
        if combo.get_active() != 0:
            combo.set_active(0)
        _update_status_lozenge(label, combo)

    def __create_lozenge(
        self, description: str, text: str, extra_class: str | None = None
    ) -> Gtk.Label:
        """
        Create a passive lozenge shaped label to display addon information.
        Used for non-filterable fields (Version, Installed version).

        :param description: Tooltip text describing the lozenge.
        :param text: Text displayed within the lozenge.
        :param extra_class: Optional additional CSS class to apply, for
            example ``"lozenge-warn"`` to flag a version downgrade.
        :returns: The configured lozenge label.
        """
        label = Gtk.Label()
        label.set_tooltip_text(description)
        context = label.get_style_context()
        context.add_class("lozenge")
        if extra_class:
            context.add_class(extra_class)
        label.set_text(text)
        return label

    def __create_lozenge_button(
        self,
        description: str,
        text: str,
        combo,
        filter_text: str | None = None,
        extra_class: str | None = None,
    ) -> Gtk.Button:
        """
        Create an interactive two-state lozenge button linked to a filter combo.

        Blue  = the combo is at its "All..." position  → click sets the filter.
        Orange = the combo is filtered to this value   → click resets the filter.

        :param description: Tooltip text describing the lozenge.
        :param text: Text displayed within the lozenge.
        :param combo: The filter combo this lozenge controls.
        :param filter_text: The combo entry text this lozenge filters by,
            if different from *text* -- for example, an "Installed
            version" lozenge displays a version number but filters the
            addon-status combo by "Updates". Defaults to *text*.
        :param extra_class: Optional additional CSS class to apply
            alongside "lozenge", such as ``"lozenge-warn"`` or
            ``"lozenge-caution"``, independent of the active-filter
            highlighting.
        :returns: The configured lozenge button.
        """
        filter_text = text if filter_text is None else filter_text

        label = Gtk.Label()
        label.set_text(text)
        context = label.get_style_context()
        context.add_class("lozenge")
        if extra_class:
            context.add_class(extra_class)

        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_focus_on_click(False)
        button.add(label)
        button.get_style_context().add_class("lozenge-button")

        # Store data for external colour refresh (used by AddonMarketplace.__refresh_lozenge_colours)
        button._lozenge_data = (label, combo, filter_text)

        # Initialise colour state
        self.__update_lozenge_colour(label, combo, filter_text)

        button.connect("clicked", self.__on_lozenge_clicked, label, combo, filter_text)
        return button

    def __update_lozenge_colour(self, label, combo, text):
        """
        Apply or remove the lozenge-active CSS class based on the current
        state of *combo*.  Orange when the filter matches *text*, blue otherwise.
        """
        ctx = label.get_style_context()
        if self.manager.is_filter_active(combo, text):
            ctx.add_class("lozenge-active")
            label.set_tooltip_text(_("Click to clear this filter"))
        else:
            ctx.remove_class("lozenge-active")
            label.set_tooltip_text(_('Click to filter by "%s"') % text)

    def __on_lozenge_clicked(self, button, label, combo, text):
        """
        Toggle the filter combo between "active for this value" and "All".
        """
        if self.manager.is_filter_active(combo, text):
            # Currently orange → reset to "All"
            combo.set_active(0)
        else:
            # Currently blue → set to matching entry
            self.manager.set_combo_to_text(combo, text)
        # Colour update will propagate via __combo_changed → invalidate_filter
        # but we also flip immediately for instant visual feedback.
        self.__update_lozenge_colour(label, combo, text)


# -------------------------------------------------------------------------
#
# AddonMarketplace
#
# -------------------------------------------------------------------------
class AddonMarketplace(ManagedWindow):
    """
    A class to allow the user to easily select addons to install.
    """

    def __init__(self, dbstate, uistate, track):
        self.dbstate = dbstate
        self.title = _("Addon Marketplace")
        # The class (not the instance) is the window key, so a second
        # "Addon Marketplace..." brings the open window to the front and
        # raises WindowActiveError, which the menu handler of Gramps catches.
        ManagedWindow.__init__(self, uistate, [], self.__class__)

        self.__pmgr = GuiPluginManager.get_instance()
        self.__preg = PluginRegister.get_instance()
        dialog = Gtk.Dialog(
            title="", transient_for=uistate.window, destroy_with_parent=True
        )
        # "N of M addons" count, at the left of the Refresh button
        self._count_label = Gtk.Label(label="")
        self._count_label.set_margin_start(6)
        self._count_label.set_margin_end(6)
        action_area = dialog.get_action_area()
        action_area.pack_start(self._count_label, False, False, 0)
        action_area.reorder_child(self._count_label, 0)
        dialog.add_button(_("Refresh"), RELOAD)
        dialog.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        self.set_window(dialog, None, self.title)
        # lozenges.css rules are scoped to this class so other windows
        # (and other addons) that use .lozenge keep their own look
        self.window.get_style_context().add_class("addon-marketplace")
        # Help button lower left: opens README.md in Markdown Dash, or
        # else the help_url registered in AddonMarketplace.gpr.py
        area = self.window.get_action_area()
        help_button = add_help_button(area, uistate, PLUGIN_ID)
        if isinstance(area, Gtk.ButtonBox):
            area.set_child_secondary(help_button, True)

        self.req = Requirements()
        self._catalogs = {}  # downloaded catalogs, see refresh()
        self._load_generation = 0
        self._refresh_source = 0
        # projects-file projects: read when the Projects tab is shown and
        # again when the gtk-index button is clicked (see __reread_ini)
        self._ini_projects = []

        self.setup_configs("interface.addonmanager", 750, 400)
        self.window.connect("response", self.__on_dialog_button)

        book = Gtk.Notebook()

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_spacing(6)
        vbox.set_margin_start(6)
        vbox.set_margin_end(6)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)

        self.search = Gtk.Entry()
        self.search.set_icon_from_icon_name(
            Gtk.EntryIconPosition.SECONDARY, "system-search"
        )
        self.search.connect("changed", self.__combo_changed)
        vbox.pack_start(self.search, False, False, 0)

        hbox = Gtk.Box()
        hbox.set_spacing(6)
        self.lb = Gtk.ListBox()
        self.lb.set_activate_on_single_click(False)

        label = Gtk.Label(label=_("Filters") + COLON)
        label.set_margin_end(12)
        hbox.pack_start(label, False, False, 0)

        self.addon_combo = Gtk.ComboBoxText()
        self.addon_combo.set_entry_text_column(0)
        self.addon_combo.append_text(_("All addons"))  # index 0
        self.addon_combo.append_text(_("Not installed"))  # index 1
        self.addon_combo.append_text(_("Installed"))  # index 2
        self.addon_combo.append_text(_("Updates"))  # index 3
        self.addon_combo.append_text(_("New or Updated"))  # index 4
        self.addon_combo.set_active(4)
        self.addon_combo.connect("changed", self.__combo_changed)
        hbox.pack_start(self.addon_combo, False, False, 0)

        # [name, url, enabled] from gramps.ini, plus the language code
        # saved in AddonMarketplace.ini
        self.projects = [
            list(project[:3]) + [_project_language(project[1])]
            for project in config.get("behavior.addons-projects")
        ]
        self.project_combo = Gtk.ComboBoxText()
        self.project_combo.set_entry_text_column(0)
        self._project_combo_handler = self.project_combo.connect(
            "changed", self.__combo_changed
        )
        hbox.pack_start(self.project_combo, False, False, 0)

        type_store = Gtk.ListStore(int, str)
        type_store.append([-1, _("All types")])
        entries = list(PTYPE_STR.items())
        for entry in sorted(entries, key=lambda item: item[1]):
            type_store.append(entry)
        self.type_combo = self.__create_filter_combo(type_store, 0)
        hbox.pack_start(self.type_combo, False, False, 0)

        audience_store = Gtk.ListStore(int, str)
        audience_store.append([-1, _("All audiences")])
        for key, value in AUDIENCETEXT.items():
            audience_store.append([key, value])
        self.audience_combo = self.__create_filter_combo(audience_store, 1)
        hbox.pack_start(self.audience_combo, False, False, 0)

        status_store = Gtk.ListStore(int, str)
        status_store.append([-1, _("All statuses")])
        entries = list(STATUSTEXT.items())
        for entry in sorted(entries, reverse=True):
            status_store.append(entry)
        self.status_combo = self.__create_filter_combo(status_store, 1)
        hbox.pack_start(self.status_combo, False, False, 0)

        clear = Gtk.Button.new_from_icon_name("edit-clear", Gtk.IconSize.BUTTON)
        clear.set_tooltip_text(_("Reset addon filters to defaults"))
        clear.connect("clicked", self.__clear_filters)
        hbox.pack_start(clear, False, False, 0)

        vbox.pack_start(hbox, False, False, 0)

        # Shown only when an enabled project gave no addons
        self.problem_bar = Gtk.InfoBar()
        self.problem_bar.set_message_type(Gtk.MessageType.WARNING)
        self.problem_label = Gtk.Label()
        self.problem_label.set_line_wrap(True)
        self.problem_label.set_xalign(0)
        self.problem_label.set_selectable(True)
        self.problem_bar.get_content_area().pack_start(
            self.problem_label, True, True, 0
        )
        # Gramps' own lightbulb: opens the Gramps Warnings dialog with the
        # logged details (module, line, the urlopen error ...)
        warn_btn = WarnButton()
        warn_btn.set_tooltip_text(_("Show the warnings that Gramps logged"))
        warn_btn.connect("clicked", self.__on_open_warnings_clicked)
        self.problem_bar.get_content_area().pack_start(warn_btn, False, False, 0)
        self.problem_bar.get_content_area().reorder_child(warn_btn, 0)
        self.ssl_button = self.problem_bar.add_button(
            _("Certificate help"), Gtk.ResponseType.HELP
        )
        self.ssl_button.set_tooltip_text(_ssl_remediation_text())
        self.problem_bar.add_button(_("Open Projects tab"), Gtk.ResponseType.APPLY)
        self.problem_bar.connect("response", self.__on_problem_bar_response)
        self.problem_bar.set_no_show_all(True)
        vbox.pack_start(self.problem_bar, False, False, 0)

        self.addon_sw = Gtk.ScrolledWindow()
        self.addon_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.addon_sw.add(self.lb)
        vbox.pack_start(self.addon_sw, True, True, 0)

        self.book = book
        book.append_page(vbox, Gtk.Label(label=_("Addons")))

        grid = self.create_settings_panel()
        book.append_page(grid, Gtk.Label(label=_("Settings")))

        grid = self.create_projects_panel()
        book.append_page(grid, Gtk.Label(label=_("Projects")))
        # after the pages are added: adding them emits switch-page too
        book.connect("switch-page", self.__on_switch_page)

        for project in self.projects:
            self.project_list.add(ProjectRow(self, project))
        self.update_project_list()

        self.window.get_content_area().pack_start(book, True, True, 0)

        self.lb.set_sort_func(self.__sort_func)
        self.lb.set_filter_func(self.__filter_func)

        self.show()

        self.refresh()

    def __create_filter_combo(self, store, default):
        """
        Create a ComboBox for filters.
        """
        combo = Gtk.ComboBox()
        combo.set_model(store)
        combo.set_entry_text_column(1)
        combo.connect("changed", self.__combo_changed)
        combo.set_active(default)
        renderer_text = Gtk.CellRendererText()
        combo.pack_start(renderer_text, True)
        combo.add_attribute(renderer_text, "text", 1)
        return combo

    def update_project_list(self):
        """
        Update the project list after it has been changed.
        """
        self.projects = [row.project for row in self.project_list]
        config.set("behavior.addons-projects", [p[:3] for p in self.projects])
        _save_project_languages(self.projects)
        self.__update_include_english_visibility()
        self.__rebuild_project_combo()
        self.__update_ini_button()

    def __update_include_english_visibility(self):
        """
        Show the "Include English" check box only while it is relevant
        (see _should_offer_include_english); hidden, it is also turned off.
        """
        if _should_offer_include_english(self.projects):
            self.include_english_check.show()
        elif self.include_english_check.get_active():
            self.include_english_check.hide()
            self.include_english_check.set_active(False)
        else:
            self.include_english_check.hide()

    def __rebuild_project_combo(self):
        """
        Fill the Project filter, with a "<name> + en" entry for each project
        that gets an extra English catalog while "Include English" is on.
        """
        # keep the chosen project if it is still in the list, and filter
        # only once, after the rebuild
        current = self.project_combo.get_active_text()
        entries = [_("All projects")]
        include_english = self.include_english_check.get_active()
        for project in self.projects:
            entries.append(project[0])
            if (
                include_english
                and project[2]
                and _project_needs_english(project[3] if len(project) > 3 else "")
            ):
                entries.append("%s + en" % project[0])
        old_entries = [row[0] for row in self.project_combo.get_model()]
        if entries == old_entries:
            return
        self.project_combo.handler_block(self._project_combo_handler)
        self.project_combo.remove_all()
        for text in entries:
            self.project_combo.append_text(text)
        index = entries.index(current) if current in entries else 0
        self.project_combo.set_active(index)
        self.project_combo.handler_unblock(self._project_combo_handler)
        if hasattr(self, "lb") and current != entries[index]:
            self.__combo_changed(self.project_combo)

    def __on_include_english_toggled(self, check):
        """
        "Include English" changes what is downloaded, so save it, rebuild
        the Project filter and load the catalogs again.
        """
        manager = _settings()
        if manager.get("projects.include-english") != check.get_active():
            manager.set("projects.include-english", check.get_active())
            manager.save()
        if hasattr(self, "lb"):
            self.__rebuild_project_combo()
            self.schedule_refresh()

    def __on_switch_page(self, _book, _page, page_num):
        """
        Read the projects file again each time the Projects tab is shown,
        so the gtk-index button there is up to date.
        """
        if page_num == 2:
            self.__reread_ini()

    def __reread_ini(self):
        """
        Read the projects of the projects file (see _projects_ini_path)
        and update the gtk-index button.
        """
        if getattr(self, "ini_btn", None) is None:
            return  # no projects file when the window opened
        path = _projects_ini_path()
        self._ini_file = os.path.basename(path) if path else ""
        self._ini_projects = _read_ini_projects(path) if path else []
        self.__update_ini_button()

    def __new_ini_projects(self):
        """
        Projects in the projects file whose address is not already used by
        a project in the list.
        """
        known = {_url_key(project[1]) for project in self.projects}
        new, seen = [], set()
        for project in [list(p) for p in self._ini_projects]:
            # offer (and add) the fixed address, e.g. raw instead of a
            # GitHub web page
            project[1] = _normalize_location_text(project[1])
            key = _url_key(project[1])
            if key not in known and key not in seen:
                seen.add(key)
                new.append(project)
        return new

    def __update_ini_button(self):
        """
        Make the gtk-index button available only while the projects file
        offers projects that are not in the list yet.
        """
        if getattr(self, "ini_btn", None) is None:
            return
        count = len(self.__new_ini_projects())
        filename = getattr(self, "_ini_file", "") or PROJECTS_INI_NAMES[-1]
        self.ini_btn.set_sensitive(count > 0)
        if count:
            self.ini_btn.set_tooltip_text(
                ngettext(
                    "Add projects from the %(file)s file of the Addon "
                    "Marketplace (%(count)d project not in your list yet)",
                    "Add projects from the %(file)s file of the Addon "
                    "Marketplace (%(count)d projects not in your list yet)",
                    count,
                )
                % {"file": filename, "count": count}
            )
        else:
            self.ini_btn.set_tooltip_text(
                _(
                    "Every project in the %s file of the Addon "
                    "Marketplace is in your list"
                )
                % filename
            )

    def __add_ini_projects(self, button):
        """
        Show the projects of the projects file that are not in the list yet,
        each with a check box, and add the checked ones.
        """
        self.__reread_ini()  # pick up any edit to the file
        candidates = self.__new_ini_projects()
        if not candidates:
            self.__update_ini_button()
            return
        chosen = ProjectPickerDialog(self.window, candidates).run()
        if not chosen:
            return
        for project in chosen:
            # Only name and address come from the projects file; its on/off
            # flags are ignored. A project picked here is wanted, so it is
            # added turned on.
            self.project_list.add(ProjectRow(self, [project[0], project[1], True, ""]))
        self.update_project_list()
        self.refresh()

    def refresh(self, reload=False):
        """
        Show the addons of the enabled projects.

        Catalogs are downloaded once per window and kept; turning a project
        on or off, or "Include English", only downloads catalogs that are
        not kept yet, and shows the list at once when none are missing.

        :param reload: download every catalog again (the Refresh button).
        """
        if self._refresh_source:
            GLib.source_remove(self._refresh_source)
            self._refresh_source = 0
        if reload:
            self._catalogs.clear()
        # A newer refresh makes the results of older threads stale
        self._load_generation += 1
        generation = self._load_generation
        include_english = self.include_english_check.get_active()
        keys = _project_keys(self.projects, include_english)
        if all(key in self._catalogs for key in keys):
            addons, problems, enabled, fetched = _load_projects(
                self.projects, include_english, self._catalogs
            )
            self.load_addons(addons, problems, enabled, generation, fetched)
            return
        for child in self.lb.get_children():
            self.lb.remove(child)
        self.__placeholder(_("Loading..."))
        self.problem_bar.hide()
        self.__update_count_label()
        thread = GetAddons(
            lambda addons, problems, enabled, fetched: self.load_addons(
                addons, problems, enabled, generation, fetched
            ),
            self.projects,
            include_english,
            self._catalogs,
        )
        thread.start()

    def schedule_refresh(self):
        """
        Refresh a moment later, so several quick check box clicks give one
        refresh instead of one each.
        """
        if self._refresh_source:
            GLib.source_remove(self._refresh_source)
        self._refresh_source = GLib.timeout_add(400, self.__scheduled_refresh)

    def __scheduled_refresh(self):
        self._refresh_source = 0
        # the window may have been closed while the refresh was waiting
        if self.uistate.gwm.get_item_from_id(self.window_id) is self:
            self.refresh()
        return False

    def update_addon(self, addon_id):
        """
        Register and load the freshly downloaded version of an addon.
        """
        pdata = self.__preg.get_plugin(addon_id)
        if pdata is not None:
            self.__pmgr.reg_plugin_dir(
                pdata.directory, self.dbstate, self.uistate, load_on_reg=True
            )
            pdata = self.__preg.get_plugin(addon_id)
        if pdata is None:
            pdata = self.__rescan_addon_folder(addon_id)
        if pdata is None:
            self.__registration_failed(addon_id)
            return
        self.__pmgr.load_plugin(pdata)
        self.__pmgr.emit("plugins-reloaded")

    def install_addon(self, addon_id):
        """
        Register and load a freshly downloaded addon.
        """
        self.__pmgr.reg_plugins(
            USER_PLUGINS, self.dbstate, self.uistate, load_on_reg=True
        )
        pdata = self.__preg.get_plugin(addon_id)
        if pdata is None:
            pdata = self.__rescan_addon_folder(addon_id)
        if pdata is None:
            self.__registration_failed(addon_id)
            return
        self.__pmgr.load_plugin(pdata)
        self.__pmgr.emit("plugins-reloaded")

    def __rescan_addon_folder(self, addon_id):
        """
        Scan the folder of a freshly installed addon again. Gramps scans
        each plugin folder once and skips it afterwards, so an addon whose
        folder was scanned at startup (and dropped then, for example for a
        missing Python module that is installed now) is never registered
        by reg_plugins(); reg_plugin_dir() forgets the folder and scans it
        again.

        :returns: the PluginData, or None.
        """
        folder = _find_addon_folder(addon_id)
        if folder is None:
            return None
        try:
            self.__pmgr.reg_plugin_dir(
                folder, self.dbstate, self.uistate, load_on_reg=True
            )
        except ValueError:
            pass  # not scanned before, so reg_plugins() already tried it
        return self.__preg.get_plugin(addon_id)

    def __registration_failed(self, addon_id):
        """
        A downloaded addon that Gramps will not register. When something
        it requires is missing, say so; otherwise it was almost always
        made for another Gramps version. Offer to keep its files, or to
        remove them.
        """
        folder = _find_addon_folder(addon_id)
        addon = self.find_addon(addon_id)
        missing = _missing_requirements(Requirements(), addon) if addon else []
        if missing:
            title = _("Addon Requirements Missing")
            text = _(
                "The addon '%(addon_id)s' was installed, but Gramps cannot "
                "use it until these are installed: %(missing)s.\n\n"
                "Keep its files, so that it works after you install them and "
                "restart Gramps, or remove them?"
            ) % {"addon_id": addon_id, "missing": ", ".join(missing)}
        else:
            title = _("Addon Version Mismatch")
            text = _(
                "The addon '%(addon_id)s' was downloaded, but Gramps "
                "%(major_version)s cannot use it. It was probably made for "
                "another Gramps version, or its project (on the Projects tab "
                "of this window) is for another Gramps version.\n\n"
                "Keep its files to adapt its .gpr.py registration file "
                "yourself, or remove them?"
            ) % {"addon_id": addon_id, "major_version": major_version}
        keep = QuestionDialog2(
            title,
            text,
            _("Keep the files"),
            _("Remove the files"),
            parent=self.window,
        ).run()
        if keep or folder is None:
            if keep and folder:
                LOG.info("Addon Marketplace: kept %s", folder)
            return
        try:
            shutil.rmtree(folder)
        except OSError as err:
            OkDialog(
                _("Addon files not removed"),
                _("Could not remove %(folder)s: %(error)s")
                % {"folder": folder, "error": err},
                parent=self.window,
            )

    def build_menu_names(self, obj):
        return (self.title, self.title)

    def __placeholder(self, text, detail=None, button_text=None, callback=None):
        """
        Show what the list box displays when no addon rows are visible:
        a bold message, an optional explanation and an optional button.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        label = Gtk.Label()
        label.set_markup('<span size="larger" weight="bold">%s</span>' % escape(text))
        label.set_line_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        box.pack_start(label, False, False, 0)
        if detail:
            info = Gtk.Label(label=detail)
            info.set_line_wrap(True)
            info.set_justify(Gtk.Justification.CENTER)
            box.pack_start(info, False, False, 0)
        if button_text:
            button = Gtk.Button(label=button_text)
            button.set_halign(Gtk.Align.CENTER)
            button.connect("clicked", callback)
            box.pack_start(button, False, False, 0)
        box.show_all()
        self.lb.set_placeholder(box)

    def load_addons(
        self, addon_list, problems=(), enabled=1, generation=None, fetched=None
    ):
        """
        Populate the list box, report projects that gave no addons, and
        set an actionable message for when no rows are visible.
        """
        if fetched:
            self._catalogs.update(fetched)  # keep them, even from an old load
        if generation is not None and generation != self._load_generation:
            return  # a newer refresh is on its way
        selected = self.lb.get_selected_row()
        selected_key = (selected.addon["i"], selected.addon["_p"]) if selected else None
        for child in self.lb.get_children():
            self.lb.remove(child)
        self._addon_list = addon_list
        for addon in addon_list:
            row = AddonRow(self, addon, self.req, self.window)
            self.lb.add(row)
            if selected_key == (addon["i"], addon["_p"]):
                self.lb.select_row(row)  # keep the selected addon selected

        if problems:
            lines = [
                _("%(bad)d of %(all)d enabled projects gave no addons:")
                % {"bad": len(problems), "all": enabled}
            ]
            for project, url, reason, _is_ssl in problems:
                lines.append("\u2022 %s: %s\n   %s" % (project, reason, url))
            self.problem_label.set_text("\n".join(lines))
            any_ssl = any(problem[3] for problem in problems)
            # show_all() skips widgets marked no_show_all, so lift it briefly
            self.problem_bar.set_no_show_all(False)
            self.problem_bar.show_all()
            self.problem_bar.set_no_show_all(True)
            # the certificate guide only helps with certificate problems
            self.ssl_button.set_visible(any_ssl)
        else:
            self.problem_bar.hide()

        if enabled == 0:
            self.__placeholder(
                _("No projects are turned on."),
                _("Turn on at least one project on the Projects tab."),
                _("Open Projects tab"),
                self.__show_projects_tab,
            )
        elif not addon_list:
            self.__placeholder(
                _("No addon catalogs could be loaded."),
                _(
                    "Check the project addresses on the Projects tab, "
                    "then click Refresh."
                ),
                _("Open Projects tab"),
                self.__show_projects_tab,
            )
        else:
            count = len(addon_list)
            self.__placeholder(
                ngettext(
                    "The %d addon listed does not match the filters.",
                    "None of the %d addons listed match the filters.",
                    count,
                )
                % count,
                None,
                _("Clear all filters"),
                self.__clear_all_filters,
            )
        self.__update_count_label()
        GLib.idle_add(self.__recenter_selection)

    def __on_problem_bar_response(self, _bar, response_id):
        """
        Buttons of the warning bar: certificate help or the Projects tab.
        """
        if response_id == Gtk.ResponseType.HELP:
            _open_uri(_SSL_TROUBLESHOOTING_URL)
        else:
            self.__show_projects_tab()

    def __on_open_warnings_clicked(self, _button):
        """
        Open Gramps' own Gramps Warnings dialog, by clicking the lightbulb
        button of the status bar of the main window.
        """
        # The warning handler of the status bar shows that dialog. Its
        # button opens it from a button-press handler (WarnButton.on_clicked),
        # not the "clicked" signal, so clicked() on the button does nothing.
        rhandler = getattr(self.uistate, "rhandler", None)
        if rhandler is not None and hasattr(rhandler, "display"):
            rhandler.display(None)
            return
        warn_button = _find_warn_button(self.uistate.window)
        handler = getattr(warn_button, "func", None)
        if handler is not None:
            handler(warn_button)
        else:
            InfoDialog(
                _("Warnings Not Available"),
                _(
                    "Could not find the warning button of the status bar, "
                    "so the Gramps Warnings dialog could not be opened."
                ),
                parent=self.window,
            )

    def __update_count_label(self):
        """
        Show "N of M addons" at the left of the Refresh button.
        """
        rows = [r for r in self.lb.get_children() if isinstance(r, AddonRow)]
        visible = sum(1 for r in rows if r.get_child_visible())
        self._count_label.set_text(
            ngettext(
                "{filtered} of {total} addon",
                "{filtered} of {total} addons",
                len(rows),
            ).format(filtered=visible, total=len(rows))
        )
        self._count_label.show()

    def __recenter_selection(self):
        """
        Keep the selected addon in view after a filter change, scrolled to
        the middle of the list. The selection itself is never changed.
        Runs once from idle_add.
        """
        target = self.lb.get_selected_row()
        if target is None or not target.get_child_visible():
            return False
        adj = self.addon_sw.get_vadjustment()
        alloc = target.get_allocation()
        middle = alloc.y + alloc.height / 2 - self.addon_sw.get_allocation().height / 2
        adj.set_value(
            max(adj.get_lower(), min(middle, adj.get_upper() - adj.get_page_size()))
        )
        return False

    def __show_projects_tab(self, *_args):
        """
        Switch to the Projects tab.
        """
        self.book.set_current_page(2)

    def find_addon(self, addon_id):
        """
        Return the addon dict for the given plugin ID, or None if not found.
        """
        for addon in getattr(self, "_addon_list", []):
            if addon["i"] == addon_id:
                return addon
        return None

    def __clear_all_filters(self, *_args):
        """
        Set every filter to "All" and empty the search text, so every
        listed addon shows (the Reset button restores the defaults
        instead, which hide some audiences and statuses).
        """
        self.search.set_text("")
        for combo in (
            self.addon_combo,
            self.project_combo,
            self.type_combo,
            self.audience_combo,
            self.status_combo,
        ):
            combo.set_active(0)

    def __clear_filters(self, combo):
        """
        Reset the filters back to their defaults.
        """
        self.search.set_text("")
        self.type_combo.set_active(0)
        self.addon_combo.set_active(0)
        self.project_combo.set_active(0)
        self.audience_combo.set_active(1)
        self.status_combo.set_active(1)

    def is_filter_active(self, combo, text):
        """
        Return True when *combo* is currently filtering on *text*
        (i.e. not at its "All..." position).

        addon_combo and project_combo are ComboBoxText → compare active
        text directly. type/audience/status combos are ComboBox with a
        ListStore(int, str) → active when the active row's integer key is
        not -1 AND the display text in column 1 matches *text*.
        """
        if combo in (self.addon_combo, self.project_combo):
            return combo.get_active_text() == text
        active_iter = combo.get_active_iter()
        if active_iter is None:
            return False
        model = combo.get_model()
        key = model.get_value(active_iter, 0)
        label = model.get_value(active_iter, 1)
        return key != -1 and label == text

    def set_combo_to_text(self, combo, text):
        """
        Set *combo* to the entry whose display text equals *text*.
        For addon_combo and project_combo (ComboBoxText) iterate by index.
        For model-based combos iterate the ListStore.
        Does nothing if no matching entry is found.
        """
        if combo in (self.addon_combo, self.project_combo):
            model = combo.get_model()
            for i, row in enumerate(model):
                if row[0] == text:
                    combo.set_active(i)
                    return
        else:
            model = combo.get_model()
            row_iter = model.get_iter_first()
            while row_iter:
                if model.get_value(row_iter, 1) == text:
                    combo.set_active_iter(row_iter)
                    return
                row_iter = model.iter_next(row_iter)

    def __combo_changed(self, combo):
        """
        Called when a filter is changed.
        Invalidates the filter and refreshes lozenge colours on all rows.
        """
        self.lb.invalidate_filter()
        self.__refresh_lozenge_colours()
        self.__update_count_label()
        # after the list box has filtered again
        GLib.idle_add(self.__recenter_selection)

    def __refresh_lozenge_colours(self):
        """
        Set the colours of the filter lozenges of every addon to match the
        filters. (Version lozenges are right already: each row reads the
        installed version when it is built, and rows are rebuilt after an
        install or update.)
        """
        for row in self.lb.get_children():
            if not isinstance(row, AddonRow):
                continue
            # The lozenge hbox is the second child of vbox (index 1)
            vbox = row.vbox
            children = vbox.get_children()
            if len(children) < 2:
                continue
            hbox = children[1]
            for widget in hbox.get_children():
                if not isinstance(widget, Gtk.Button):
                    continue
                # Retrieve the label, combo, and text stored on the button
                inner = widget.get_child()
                if not isinstance(inner, Gtk.Label):
                    continue
                status_data = getattr(widget, "_status_lozenge_data", None)
                if status_data is not None:
                    _update_status_lozenge(*status_data)
                    continue
                data = getattr(widget, "_lozenge_data", None)
                if data is None:
                    continue
                lbl, cb, txt = data
                ctx = inner.get_style_context()
                if self.is_filter_active(cb, txt):
                    ctx.add_class("lozenge-active")
                    inner.set_tooltip_text(_("Click to clear this filter"))
                else:
                    ctx.remove_class("lozenge-active")
                    inner.set_tooltip_text(_('Click to filter by "%s"') % txt)

    def __sort_func(self, row1, row2):
        """
        Sort the addons by ID, then by name (the same addon can come from
        two projects, or in English from an "Include English" project).
        """
        value1 = (row1.addon["i"], row1.addon["n"])
        value2 = (row2.addon["i"], row2.addon["n"])
        if value1 > value2:
            return 1
        elif value1 < value2:
            return -1
        else:
            return 0

    def __filter_func(self, row):
        """
        Filter the addons list according to the user selection.
        """
        search_text = self.search.get_text()
        addon_text = self.addon_combo.get_active_text()
        project_text = self.project_combo.get_active_text()
        type_iter = self.type_combo.get_active_iter()
        audience_iter = self.audience_combo.get_active_iter()
        status_iter = self.status_combo.get_active_iter()

        if addon_text == _("Not installed"):
            if "_v" in row.addon:
                return False
        if addon_text == _("Installed"):
            if "_v" not in row.addon:
                return False
        if addon_text == _("Updates"):
            if "_v" not in row.addon:
                return False
            # compare as numbers, so "1.0" and "1.0.0" are the same version
            if version_str_to_tup(row.addon["v"], 3) == version_str_to_tup(
                row.addon["_v"], 3
            ):
                return False
        if addon_text == _("New or Updated"):
            if "_v" in row.addon and version_str_to_tup(
                row.addon["v"], 3
            ) == version_str_to_tup(row.addon["_v"], 3):
                return False
        if project_text != _("All projects"):
            if row.addon["_p"] != project_text:
                return False
        model = self.type_combo.get_model()
        value = model.get_value(type_iter, 0)
        if value != -1 and row.addon["t"] != value:
            return False
        model = self.audience_combo.get_model()
        value = model.get_value(audience_iter, 0)
        if value != -1 and row.addon["a"] != value:
            return False
        model = self.status_combo.get_model()
        value = model.get_value(status_iter, 0)
        if value != -1 and row.addon["s"] != value:
            return False
        if search_text:
            # name, description, ID, authors, maintainers, their e-mail
            # addresses and the help address
            addon = row.addon
            parts = [addon.get(key, "") for key in ("n", "d", "i", "h")]
            for key in _NAME_LIST_FIELDS:  # lists after normalization
                parts.extend(addon.get(key, []))
            searchable = " ".join(parts).lower()
            if search_text.lower() not in searchable:
                return False
        return True

    def __on_dialog_button(self, dialog, response_id):
        """
        Handle a main dialog button click.
        """
        if response_id == Gtk.ResponseType.CLOSE:
            self.close(dialog)
        elif response_id == RELOAD:
            self.refresh(reload=True)

    def create_projects_panel(self):
        """
        Configuration tab with addons projects.
        """
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_spacing(6)
        vbox.set_margin_start(6)
        vbox.set_margin_end(6)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)

        # Built from two existing Gramps words, so it is already translated
        self.include_english_check = Gtk.CheckButton(
            label=_("Include") + " " + _("English")
        )
        self.include_english_check.set_tooltip_text(
            _(
                "For each project below that is read in another language "
                "(its own language code, or the language of Gramps), also "
                "load its English catalog, so English names and descriptions "
                "can be searched too. These addons show the project name "
                'followed by "+ en".'
            )
        )
        self.include_english_check.set_active(
            _settings().get("projects.include-english")
        )
        # shown and hidden by __update_include_english_visibility only
        self.include_english_check.set_no_show_all(True)
        self.include_english_check.connect("toggled", self.__on_include_english_toggled)
        vbox.pack_start(self.include_english_check, False, False, 0)

        self.project_list = Gtk.ListBox()
        self.project_list.set_activate_on_single_click(False)
        self.project_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.project_list.connect("row-activated", self.__edit_project)
        self.project_list.connect("row-selected", self.__project_selected)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.add(self.project_list)
        vbox.pack_start(sw, True, True, 0)

        hbox = Gtk.Box()
        # Offer projects from the projects file; only when one exists
        self.ini_btn = None
        if _projects_ini_path() is not None:
            self.ini_btn = SimpleButton("gtk-index", self.__add_ini_projects)
            hbox.pack_start(self.ini_btn, False, False, 0)
        add_btn = SimpleButton("list-add", self.__add_project)
        add_btn.set_tooltip_text(_("Insert a project"))
        del_btn = SimpleButton("list-remove", self.__remove_project)
        del_btn.set_tooltip_text(_("Remove the selected project"))
        up_btn = SimpleButton("go-up", self.__move_up)
        up_btn.set_tooltip_text(_("Move project upwards in the list"))
        down_btn = SimpleButton("go-down", self.__move_down)
        down_btn.set_tooltip_text(_("Move project downwards in the list"))
        restore_btn = SimpleButton("document-revert", self.__restore_defaults)
        restore_btn.set_tooltip_text(_("Revert to the project defaults"))
        self.buttons = [add_btn, del_btn, up_btn, down_btn, restore_btn]
        for button in self.buttons:
            hbox.pack_start(button, False, False, 0)
        self.buttons[1].set_sensitive(False)
        self.buttons[2].set_sensitive(False)
        self.buttons[3].set_sensitive(False)
        vbox.pack_start(hbox, False, False, 0)

        return vbox

    def create_settings_panel(self):
        """
        Configuration tab with addons settings.
        """
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        vbox.set_spacing(6)
        vbox.set_margin_start(6)
        vbox.set_margin_end(6)
        vbox.set_margin_top(6)
        vbox.set_margin_bottom(6)

        heading1 = Gtk.Label()
        text = _("General")
        heading1.set_text('<span weight="bold">%s</span>' % text)
        heading1.set_use_markup(True)
        heading1.set_halign(Gtk.Align.START)
        vbox.pack_start(heading1, False, False, 0)

        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_margin_start(6)
        grid.set_margin_bottom(12)
        vbox.pack_start(grid, False, False, 0)

        row = 1
        install = Gtk.CheckButton()
        install.set_label(_("Allow Gramps to install required Python modules"))
        install.set_tooltip_text(
            _("Where possible, try to install any missing prerequisite Python modules")
        )
        active = config.get("behavior.addons-allow-install")
        install.set_active(active)
        install.connect("toggled", self.install_changed)
        grid.attach(install, 1, row, 1, 1)

        heading2 = Gtk.Label()
        text = _("Scheduled update checks")
        heading2.set_text('<span weight="bold">%s</span>' % text)
        heading2.set_use_markup(True)
        heading2.set_halign(Gtk.Align.START)
        vbox.pack_start(heading2, False, False, 0)

        grid = Gtk.Grid()
        grid.set_row_spacing(6)
        grid.set_margin_start(6)
        vbox.pack_start(grid, False, False, 0)

        # Check for addon updates:
        row = 1
        obox = Gtk.ComboBoxText()
        formats = [
            _("Never"),
            _("Once a month"),
            _("Once a week"),
            _("Once a day"),
            _("Always"),
        ]
        list(map(obox.append_text, formats))
        active = config.get("behavior.check-for-addon-updates")
        obox.set_active(active)
        obox.connect("changed", self.check_for_updates_changed)
        lwidget = BasicLabel(_("%s: ") % _("Check for addon updates"))
        grid.attach(lwidget, 1, row, 1, 1)
        grid.attach(obox, 2, row, 1, 1)

        row += 1
        self.whattype_box = Gtk.ComboBoxText()
        formats = [
            _("Updated addons only"),
            _("New addons only"),
            _("New and updated addons"),
        ]
        list(map(self.whattype_box.append_text, formats))
        whattype = config.get("behavior.check-for-addon-update-types")
        if "new" in whattype and "update" in whattype:
            self.whattype_box.set_active(2)
        elif "new" in whattype:
            self.whattype_box.set_active(1)
        elif "update" in whattype:
            self.whattype_box.set_active(0)
        self.whattype_box.connect("changed", self.check_for_type_changed)
        lwidget = BasicLabel(_("%s: ") % _("What to check"))
        grid.attach(lwidget, 1, row, 1, 1)
        grid.attach(self.whattype_box, 2, row, 1, 1)

        row += 1
        previous = Gtk.CheckButton()
        previous.set_label(_("Do not ask about previously notified addons"))
        active = config.get("behavior.do-not-show-previously-seen-addon-updates")
        previous.set_active(active)
        previous.connect("toggled", self.previous_changed)
        grid.attach(previous, 1, row, 1, 1)

        row += 1
        button = Gtk.Button(label=_("Check for updated addons now"))
        button.connect("clicked", self.check_for_updates)
        button.set_hexpand(False)
        button.set_halign(Gtk.Align.CENTER)
        grid.attach(button, 1, row, 2, 1)

        return vbox

    def edit_project(self, row):
        """
        Add or edit a project using enhanced dialog with URL validation.
        """
        if row.project[0] == "":
            title = _("New Project")
        else:
            title = _("Edit Project")

        project_lang = row.project[3] if len(row.project) > 3 else ""
        dialog = EnhancedProjectDialog(
            self.window, title, row.project[0], row.project[1], project_lang
        )
        result = dialog.run()

        if result:
            if row.project[0] == "":
                self.project_list.add(row)
            row.project[0] = result["name"]
            row.project[1] = result["url"]
            if len(row.project) > 3:
                row.project[3] = result["lang"]
            else:
                row.project.append(result["lang"])
            row.update()
            self.update_project_list()
            self.refresh()

    def __add_project(self, button):
        """
        Add a project
        """
        self.edit_project(ProjectRow(self, ["", "", False, ""]))

    def __remove_project(self, button):
        """
        Remove a project
        """
        row = self.project_list.get_selected_row()
        if row:
            self.project_list.remove(row)
            self.update_project_list()
            self.refresh()

    def __move_up(self, button):
        row = self.project_list.get_selected_row()
        index = row.get_index()
        if index > 1:
            self.project_list.unselect_row(row)
            self.project_list.remove(row)
            self.project_list.insert(row, index - 1)
            self.project_list.select_row(row)
            self.update_project_list()

    def __move_down(self, button):
        row = self.project_list.get_selected_row()
        index = row.get_index()
        if index > 0 and index < len(self.project_list) - 1:
            self.project_list.unselect_row(row)
            self.project_list.remove(row)
            self.project_list.insert(row, index + 1)
            self.project_list.select_row(row)
            self.update_project_list()

    def __project_selected(self, listbox, row):
        if row:
            index = row.get_index()
            if index == 0:
                self.buttons[1].set_sensitive(False)
                self.buttons[2].set_sensitive(False)
                self.buttons[3].set_sensitive(False)
            elif index == 1:
                self.buttons[1].set_sensitive(True)
                self.buttons[2].set_sensitive(False)
                self.buttons[3].set_sensitive(True)
            elif index < len(self.project_list) - 1:
                self.buttons[1].set_sensitive(True)
                self.buttons[2].set_sensitive(True)
                self.buttons[3].set_sensitive(True)
            else:
                self.buttons[1].set_sensitive(True)
                self.buttons[2].set_sensitive(True)
                self.buttons[3].set_sensitive(False)
        else:
            self.buttons[1].set_sensitive(False)
            self.buttons[2].set_sensitive(False)
            self.buttons[3].set_sensitive(False)

    def __restore_defaults(self, button):
        """
        Restore project defaults.
        """
        dlg = QuestionDialog2(
            _("Restore project defaults"),
            _("Are you sure?"),
            _("Yes"),
            _("No"),
            parent=self.window,
        )
        if dlg.run():
            for row in self.project_list.get_children():
                self.project_list.remove(row)
            projects = [["Gramps", config.get("behavior.addons-url"), True, ""]]
            self.project_list.add(ProjectRow(self, projects[0]))
            self.update_project_list()
            self.refresh()

    def __edit_project(self, listbox, row):
        """
        Edit a project
        """
        self.edit_project(row)

    def check_for_updates(self, button):
        try:
            addon_update_list = _filter_update_offers(
                _available_updates_for(self.projects), show_inactive=True
            )
        except:
            OkDialog(
                _("Checking Addons Failed"),
                _(
                    "The addon repository appears to be unavailable. "
                    "Please try again later."
                ),
                parent=self.window,
            )
            return

        if len(addon_update_list) > 0:
            rescan = PluginWindows.UpdateAddons(
                self.uistate, self.track, addon_update_list, show_inactive=True
            ).rescan
            self.uistate.viewmanager.do_reg_plugins(
                self.dbstate, self.uistate, rescan=rescan
            )
        else:
            check_types = config.get("behavior.check-for-addon-update-types")
            OkDialog(
                _("There are no available addons of this type"),
                _("Checked for '%s'") % _("' and '").join([_(t) for t in check_types]),
                parent=self.window,
            )

        # List of translated strings used here
        # Dead code for l10n
        _("new"), _("update")

    def check_for_type_changed(self, obj):
        active = obj.get_active()
        if active == 0:  # update
            config.set("behavior.check-for-addon-update-types", ["update"])
        elif active == 1:  # update
            config.set("behavior.check-for-addon-update-types", ["new"])
        elif active == 2:  # update
            config.set("behavior.check-for-addon-update-types", ["update", "new"])

    def check_for_updates_changed(self, obj):
        """
        Save "Check for addon updates" option.
        """
        active = obj.get_active()
        config.set("behavior.check-for-addon-updates", active)

    def previous_changed(self, obj):
        active = obj.get_active()
        config.set("behavior.do-not-show-previously-seen-addon-updates", active)

    def install_changed(self, obj):
        active = obj.get_active()
        config.set("behavior.addons-allow-install", active)


# -------------------------------------------------------------------------
#
# PluginStatus: overview of all plugins
#


# -------------------------------------------------------------------------
#
# Update offers that installing does not satisfy
#
# -------------------------------------------------------------------------
def _remember_installed_offers(offers):
    """
    Record that these offers were installed.

    :param offers: {addon id: catalog version that was installed}
    """
    if not offers:
        return
    settings = _settings()
    saved = dict(settings.get("updates.installed-offers"))
    saved.update(offers)
    settings.set("updates.installed-offers", saved)
    settings.save()


def _filter_update_offers(addon_update_list, show_inactive=False):
    """
    Drop the offers that installing again would not satisfy, so they do
    not come back at every start of Gramps:

    * "New" addons that are already installed but that Gramps does not
      register (nearly always a Python module or GObject library it
      requires is missing), so Gramps never sees them as installed;
    * offers whose catalog version was already installed, but Gramps
      still has an older version: the download holds another version
      than its catalog says, or duplicate copies of the addon (with the
      same id in two folders) hide the new one.

    An offer comes back when its catalog version changes, or when the
    addon is no longer on disk. The reason for each dropped offer is
    logged at info level.

    :param addon_update_list: [(status, download url, addon dict), ...]
        as made by Gramps' available_updates().
    :param show_inactive: keep the installed addons that Gramps does not
        register (for an explicit check, which shows what they miss).
    :returns: the offers to show, in the same form.
    """
    if not addon_update_list:
        return addon_update_list
    # Gramps' own startup check passes its catalog entries unchecked
    normalized = []
    for entry in addon_update_list:
        plugin_dict = _normalize_catalog_entry(entry[2]) if len(entry) > 2 else None
        if plugin_dict is not None:
            normalized.append((entry[0], entry[1], plugin_dict))
    addon_update_list = normalized
    folders = _addon_folder_index()
    preg = PluginRegister.get_instance()
    installed = dict(_settings().get("updates.installed-offers"))
    changed = False
    kept = []
    for entry in addon_update_list:
        plugin_dict = entry[2]
        addon_id, version = plugin_dict["i"], plugin_dict["v"]
        on_disk = folders.get(addon_id, [])
        if not on_disk or installed.get(addon_id, version) != version:
            # gone from disk, or a new catalog version: offer it again
            changed |= installed.pop(addon_id, None) is not None
            kept.append(entry)
            continue
        pdata = preg.get_plugin(addon_id)
        if pdata is None and show_inactive:
            kept.append(entry)
            continue
        if pdata is None:
            reason = (
                "it is installed in %s but Gramps does not register it "
                "(check its requirements)" % ", ".join(on_disk)
            )
        elif addon_id in installed:
            if len(on_disk) > 1:
                reason = "%d copies are installed (%s); Gramps uses version %s" % (
                    len(on_disk),
                    ", ".join(on_disk),
                    pdata.version,
                )
            else:
                reason = (
                    "version %s was installed, but its download contains version %s"
                    % (version, pdata.version)
                )
        else:
            kept.append(entry)  # an ordinary offer
            continue
        LOG.info(
            "Addon Marketplace: not offering '%s' (%s) again: %s",
            plugin_dict.get("n", addon_id),
            version,
            reason,
        )
    if changed:
        _settings().set("updates.installed-offers", installed)
        _settings().save()
    return kept


_WARN_ICON_NAME = "dialog-warning"
_WARN_ICON_FILE = os.path.join(MEDIA_DIR, "warning.png")
# green check for "installed"; bundled only, since the theme icons with
# that look ("emblem-default" and the like) mean different things in
# different themes
_INSTALLED_ICON_FILE = os.path.join(MEDIA_DIR, "installed.svg")


def _file_pixbuf(path, size=16):
    """
    A bundled icon file at *size* pixels, or None (logged).
    """
    try:
        return GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
    except GLib.Error:
        LOG.warning("Addon Marketplace: cannot load %s", path)
        return None


def _warning_pixbuf(size=16):
    """
    The full-color warning icon: from the icon theme, else the bundled
    media/warning.png. Never the symbolic (monochrome) variant.

    :returns: a GdkPixbuf.Pixbuf, or None.
    """
    info = Gtk.IconTheme.get_default().lookup_icon(
        _WARN_ICON_NAME,
        size,
        Gtk.IconLookupFlags.FORCE_REGULAR
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE,
    )
    if info is not None:
        try:
            return info.load_icon()
        except GLib.Error:
            pass
    return _file_pixbuf(_WARN_ICON_FILE, size)


def _add_leading_icon(column, pixbuf, show_column):
    """
    Put *pixbuf* before the text of a tree column, on the rows where
    the boolean model column *show_column* is true.
    """
    renderer = Gtk.CellRendererPixbuf()
    renderer.set_property("pixbuf", pixbuf)
    column.pack_start(renderer, False)
    column.reorder(renderer, 0)
    column.add_attribute(renderer, "visible", show_column)


def _add_requires_column(tree, model_column, warn_column):
    """
    Insert a "Requires" text column after Name (the third column), with
    a warning icon before the text where *warn_column* is true.
    """
    renderer = Gtk.CellRendererText()
    renderer.set_fixed_height_from_font(True)
    renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
    column = Gtk.TreeViewColumn(_("Requires"), renderer, text=model_column)
    _add_leading_icon(column, _warning_pixbuf(), warn_column)
    # the tree is in fixed-height mode, which needs fixed-size columns
    column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
    column.set_fixed_width(180)
    column.set_resizable(True)
    column.set_sort_column_id(model_column)
    tree.insert_column(column, 3)
    return column


def _missing_requirements(req, plugin_dict):
    """
    What an addon of a catalog requires that is not installed.

    :param req: a gramps.gen.utils.requirements.Requirements (it caches
        what it found, so one is shared by all addons of a list).
    :param plugin_dict: the addon dict of a catalog ("rm" Python modules,
        "rg" GObject introspection modules, "re" executables).
    :returns: display names of the missing items; empty if none.
    """
    missing = [
        module for module in plugin_dict.get("rm", []) if not req.check_mod(module)
    ]
    missing += [
        " ".join(spec) for spec in plugin_dict.get("rg", []) if not req.check_gi(spec)
    ]
    missing += [exe for exe in plugin_dict.get("re", []) if not req.check_exe(exe)]
    return missing


def _package_manager():
    """
    "dnf" on Fedora and its relatives, "apt" on Debian and Ubuntu and
    their relatives, else None (other Linux, Windows, macOS).
    """
    if win() or sys.platform == "darwin":
        return None
    try:
        with open("/etc/os-release", encoding="utf-8") as fp:
            text = fp.read().lower()
    except OSError:
        return None
    ids = set()
    for line in text.splitlines():
        if line.startswith(("id=", "id_like=")):
            ids.update(line.split("=", 1)[1].strip().strip('"').split())
    if ids & {"fedora", "rhel", "centos"}:
        return "dnf"
    if ids & {"debian", "ubuntu"}:
        return "apt"
    return None


def _requirement_steps(plugin_dict, req):
    """
    What an addon is missing, and how to get each item.

    :returns: [(title, explanation, [command, ...]), ...]
    """
    manager = _package_manager()
    allowed = config.get("behavior.addons-allow-install")
    frozen = HAVE_PYPI and is_frozen()
    steps = []
    for module in plugin_dict.get("rm", []):
        if req.check_mod(module):
            continue
        names = _pypi_names(module)
        if allowed:
            text = _(
                "Gramps can try to install this module: check the addon in "
                "the list of new and updated addons and click Install "
                "Selected Addons, or click Install on the Addons tab. If that "
                "fails, install it yourself with one of these commands:"
            )
        else:
            text = _(
                "Turn on \u201cAllow Gramps to install required Python "
                "modules\u201d on the Settings tab, so that Gramps can install "
                "it. You can also install it yourself:"
            )
        commands = []
        if not frozen:
            commands.append(
                "%s -m pip install --target '%s' %s"
                % (sys.executable, LIB_PATH, " ".join(names))
            )
        if manager == "dnf":
            # a system package carries the original name (python3-psycopg2),
            # not the name of a binary substitute from PyPI
            dist = module if module in _BINARY_ALTERNATIVES else names[0]
            commands.append("dnf provides 'python3dist(%s)'" % dist.lower())
        elif manager == "apt":
            commands.append(
                "apt-cache search --names-only '^python3-%s$'" % module.lower()
            )
        steps.append((_("%s (Python module)") % module, text, commands))
    for spec in plugin_dict.get("rg", []):
        if req.check_gi(spec):
            continue
        name, versions = spec[0], [v.strip() for v in spec[1].split(",")]
        commands = []
        if manager == "dnf":
            commands.append(
                "dnf provides "
                + " ".join(
                    "'*/girepository-1.0/%s-%s.typelib'" % (name, v) for v in versions
                )
            )
        elif manager == "apt":
            commands.append("apt-file search %s-%s.typelib" % (name, versions[0]))
        steps.append(
            (
                _("%s (GObject library)") % " ".join(spec),
                _(
                    "Install it with the package manager of your system. "
                    "Gramps cannot install it."
                ),
                commands,
            )
        )
    for exe in plugin_dict.get("re", []):
        if req.check_exe(exe):
            continue
        commands = []
        if manager == "dnf":
            commands.append("dnf provides '*/bin/%s'" % exe)
        elif manager == "apt":
            commands.append("apt-file search --regexp 'bin/%s$'" % exe)
        steps.append(
            (
                _("%s (program)") % exe,
                _(
                    "Install it with the package manager of your system. "
                    "Gramps cannot install it."
                ),
                commands,
            )
        )
    return steps


def _show_requirements_checklist(parent, plugin_dict):
    """
    Show what an addon needs that is missing, with copyable commands.
    """
    steps = _requirement_steps(plugin_dict, Requirements())
    name = plugin_dict.get("n", plugin_dict.get("i", ""))
    dialog = Gtk.Dialog(title=_("What %s needs") % name, transient_for=parent)
    dialog.add_button(_("Close"), Gtk.ResponseType.CLOSE)
    dialog.set_default_size(620, -1)
    dialog.set_resizable(False)  # fit the content, no empty space
    area = dialog.get_content_area()
    area.set_spacing(10)
    area.set_border_width(12)

    def label(markup):
        widget = Gtk.Label(xalign=0)
        widget.set_markup(markup)
        widget.set_line_wrap(True)
        widget.set_max_width_chars(70)
        return widget

    if not steps:
        area.pack_start(
            label(escape(_("Everything this addon requires is installed."))),
            False,
            False,
            0,
        )
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    for title, text, commands in steps:
        area.pack_start(label("<b>%s</b>" % escape(title)), False, False, 0)
        area.pack_start(label(escape(text)), False, False, 0)
        for command in commands:
            row = Gtk.Box(spacing=6)
            cmd_label = label("<tt>%s</tt>" % escape(command))
            cmd_label.set_selectable(True)
            row.pack_start(cmd_label, True, True, 0)
            copy = Gtk.Button(label=_("Copy"))
            copy.set_valign(Gtk.Align.START)
            copy.connect("clicked", lambda _b, c=command: clipboard.set_text(c, -1))
            row.pack_start(copy, False, False, 0)
            area.pack_start(row, False, False, 0)
    if steps:
        manager = _package_manager()
        if manager == "dnf":
            hint = _(
                "A dnf provides command shows the name of the package that "
                "has the file; install that package with "
                "sudo dnf install <package name>."
            )
        elif manager == "apt":
            hint = _(
                "An apt command shows the name of the package that has the "
                "file; install that package with sudo apt install <package "
                "name>. apt-file may need to be installed and updated first."
            )
        else:
            hint = ""
        footer = (hint + " " if hint else "") + _(
            "Restart Gramps after installing system packages."
        )
        area.pack_start(label("<i>%s</i>" % escape(footer)), False, False, 0)
    dialog.show_all()
    dialog.run()
    dialog.destroy()


_CORE_UPDATE_ADDONS = getattr(
    PluginWindows, "_core_UpdateAddons", PluginWindows.UpdateAddons
)
PluginWindows._core_UpdateAddons = _CORE_UPDATE_ADDONS


class _UpdateAddons(_CORE_UPDATE_ADDONS):
    """
    Gramps' "Available Gramps Updates for Addons" window, without the
    offers that installing would not satisfy, and remembering what was
    installed from it. Opens nothing when no offer is left.
    """

    # pylint: disable-next=super-init-not-called
    def __init__(self, uistate, track, addon_update_list, show_inactive=False):
        """
        Like Gramps' own window, with a Requires column after Name. An
        offer whose requirements are missing keeps its checkbox (Select
        All checks it too); a warning icon and tooltip say what it lacks.

        :param show_inactive: also list installed addons that Gramps does
            not register (the explicit "Check for updated addons now").
        """
        self.rescan = False  # read by callers even when nothing opens
        addon_update_list = _filter_update_offers(addon_update_list, show_inactive)
        if not addon_update_list:
            return
        self._offer_dicts = {
            plugin_dict["i"]: plugin_dict
            for _status, _url, plugin_dict in addon_update_list
        }
        self._offer_versions = {
            plugin_dict["i"]: plugin_dict["v"]
            for _status, _url, plugin_dict in addon_update_list
        }
        preg = PluginRegister.get_instance()
        folders = _addon_folder_index()

        # Gramps' UpdateAddons.__init__ builds and runs the window in one
        # go, so it is rebuilt here; model columns 0-6 are unchanged
        # because the inherited install_addons() reads them by number.
        self.title = _("Available Gramps Updates for Addons")
        ManagedWindow.__init__(self, uistate, track, self, modal=True)
        glade = Glade("updateaddons.glade")
        self.set_window(glade.toplevel, None, None)
        self.window.set_title(self.title)
        self.setup_configs("interface.updateaddons", 750, 400)
        glade.get_object("select_all").connect("clicked", self.select_all_clicked)
        glade.get_object("select_none").connect("clicked", self.select_none_clicked)
        glade.get_object("apply").connect("clicked", self.install_addons)
        glade.get_object("cancel").connect("clicked", self.close)

        tree = glade.get_object("list")
        self.list = ListModel(
            tree,
            [
                {
                    "name": _("Select"),
                    "width": 60,
                    "type": TOGGLE,
                    "visible_col": 6,
                    "editable": True,
                },  # 0 selected?
                (_("Type"), 1, 180),  # 1 new gramplet
                (_("Name"), 2, 200),  # 2 name (version)
                (_("Description"), 3, 200),  # 3 description
                ("", NOSORT, 0),  # 4 url
                ("", NOSORT, 0),  # 5 id
                {"name": "", "type": TOGGLE},  # 6 checkbox visible?
                ("", NOSORT, 0),  # 7 Requires text
                ("", NOSORT, 0),  # 8 tooltip (markup)
                {"name": "", "type": TOGGLE},  # 9 requirements missing?
                {"name": "", "type": TOGGLE},  # 10 installed (on disk)?
            ],
            list_mode="tree",
        )
        # ListModel numbers only the columns it shows, so a column it
        # builds after the hidden ones would show the wrong model
        # column; Requires and the warning icon are added here instead.
        self._requires_column = _add_requires_column(tree, 7, 9)
        tree.connect("button-press-event", self.__cb_tree_click)
        _add_leading_icon(
            tree.get_columns()[2], _file_pixbuf(_INSTALLED_ICON_FILE), 10
        )  # Name
        tree.set_tooltip_column(8)
        # ListModel turns on fixed-height mode, which sizes each cell from
        # the first row only: a category row, where the icons are hidden,
        # so the icons got zero width on every row. This list is short.
        tree.set_fixed_height_mode(False)

        req = Requirements()
        pos = None
        addon_update_list.sort(key=lambda x: "%s %s" % (x[0], x[2]["t"]))
        last_category = None
        node = None
        for status, plugin_url, plugin_dict in addon_update_list:
            category = _("%(str1)s: %(str2)s") % {
                "str1": status,
                "str2": _catalog_label(PTYPE_STR, plugin_dict["t"]),
            }
            if last_category != category:
                last_category = category
                node = self.list.add(
                    [False, category, "", "", "", "", False, "", "", False, False]
                )
            missing = _missing_requirements(req, plugin_dict)
            feedback = _("Missing: %s") % ", ".join(missing) if missing else ""
            addon_id = plugin_dict["i"]
            installed = bool(folders.get(addon_id))
            tips = []
            if installed and preg.get_plugin(addon_id) is None:
                # on disk, but Gramps does not register it
                tips.append(_("Installed, not active."))
            elif installed:
                tips.append(_("Installed."))
            if missing:
                tips.append(feedback)
                tips.append(
                    _(
                        "Gramps cannot use this addon until what it requires "
                        "is installed. Click the warning icon for what to do."
                    )
                )
            tooltip = escape("\n".join(tips))
            child = self.list.add(
                [
                    False,
                    "%s %s" % (status, _catalog_label(PTYPE_STR, plugin_dict["t"])),
                    "%s (%s)" % (plugin_dict["n"], plugin_dict["v"]),
                    plugin_dict["d"],
                    plugin_url,
                    addon_id,
                    True,  # every addon row has a checkbox
                    feedback,
                    tooltip,
                    bool(missing),
                    installed,
                ],
                node=node,
            )
            if pos is None:
                pos = child
        if pos:
            self.list.selection.select_iter(pos)

        self.show()
        self.window.run()

    def __cb_tree_click(self, tree, event):
        """
        A click in the Requires cell of an addon with missing requirements
        opens the checklist of what it needs.
        """
        if event.button != 1 or event.type != Gdk.EventType.BUTTON_PRESS:
            return False
        hit = tree.get_path_at_pos(int(event.x), int(event.y))
        if not hit or hit[1] is not self._requires_column:
            return False
        model = tree.get_model()
        row = model.get_iter(hit[0])
        if not model.get_value(row, 9):  # no missing requirements
            return False
        plugin_dict = self._offer_dicts.get(model.get_value(row, 5))
        if plugin_dict:
            _show_requirements_checklist(self.window, plugin_dict)
        return False

    def install_addons(self, obj):
        """
        Record the checked offers, then let Gramps install them.
        """
        model = self.list.model
        chosen = {}
        category = model.get_iter_first()
        while category:
            for row in range(model.iter_n_children(category)):
                child = model.iter_nth_child(category, row)
                addon_id = model.get_value(child, 5)
                if model.get_value(child, 0) and addon_id in self._offer_versions:
                    chosen[addon_id] = self._offer_versions[addon_id]
            category = model.iter_next(category)
        _remember_installed_offers(chosen)
        self.__install_modules_of(chosen)
        super().install_addons(obj)

    def __install_modules_of(self, addon_ids):
        """
        Before the checked addons download, install the Python modules
        they require that are missing, when the Settings tab allows it.
        Gramps' own window only downloads the addons, so an addon whose
        modules are missing would install but never be active. Failures
        are shown together afterwards; Cancel stops the module installs,
        and the addons still download.
        """
        if not config.get("behavior.addons-allow-install"):
            return
        req = Requirements()
        modules = []
        for addon_id in addon_ids:
            for module in req.install(self._offer_dicts.get(addon_id, {})):
                if module not in modules:
                    modules.append(module)
        if not modules:
            return
        progress = _PipProgress(self.window)
        failed = []
        try:
            for module in modules:
                error = progress.install(module)
                if progress.cancelled:
                    break
                if error is not None:
                    failed.append((module, error))
        finally:
            progress.close()
        importlib.invalidate_caches()  # so Gramps finds the new modules
        if failed:
            details = "\n\n".join(
                "%s:\n%s" % (module, "\n".join(error.strip().splitlines()[-6:]))
                for module, error in failed
            )
            InfoDialog(
                _("Some Python modules could not be installed"),
                _(
                    "The addons are installed anyway, but stay inactive until "
                    "these modules are installed. Click the warning icon of an "
                    "addon in this list, or its Requires button in the Addon "
                    "Marketplace, for what to do."
                )
                + "\n\n"
                + details,
                parent=self.window,
            )


# -------------------------------------------------------------------------
#
# Monkey patch
#
# -------------------------------------------------------------------------
_CSS_PROVIDER = None


def _load_css():
    """
    Load media/lozenges.css once for the whole screen. The rules are
    scoped to the .addon-marketplace window class.
    """
    global _CSS_PROVIDER
    if _CSS_PROVIDER is not None:
        return
    screen = Gdk.Screen.get_default()
    if screen is None or not os.path.isfile(CSS_FILE):
        LOG.warning("Addon Marketplace: cannot load %s", CSS_FILE)
        return
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(CSS_FILE)
    except GLib.Error as err:
        LOG.warning("Addon Marketplace: CSS error in %s: %s", CSS_FILE, err)
        return
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _CSS_PROVIDER = provider


def _relabel_menu(uistate):
    """
    Rename the Edit menu item from "Addon Manager..." to
    "Addon Marketplace...". Only the stored menu XML is changed; Gramps
    rebuilds the menu from it shortly after startup (and on view changes).
    """
    uimanager = getattr(uistate, "uimanager", None)
    et_xml = getattr(uimanager, "et_xml", None)
    if et_xml is None:
        return
    for item in et_xml.iter("item"):
        action = item.find("attribute[@name='action']")
        if action is None or action.text != "win.AddonManager":
            continue
        label = item.find("attribute[@name='label']")
        if label is not None:
            label.text = _("_Addon Marketplace...")
            # already translated here, so stop Gtk.Builder looking it up
            label.attrib.pop("translatable", None)


def load_on_reg(dbstate, uistate, plugin):
    """
    Called by the Gramps plugin manager at registration. The command line
    has no uistate and no Addon Manager, so nothing is patched there.
    """
    if uistate is None:
        return []
    PluginWindows.AddonManager = AddonMarketplace
    # also used by the startup check for addon updates (viewmanager)
    PluginWindows.UpdateAddons = _UpdateAddons
    _load_css()
    _relabel_menu(uistate)
    return []
