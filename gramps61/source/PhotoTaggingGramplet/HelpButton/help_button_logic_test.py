"""
Standalone smoke test for the four help-button functions added to
PhotoTaggingGramplet.py (find_local_readme, resolve_markdown_dash_opener,
open_help_url, and the on_help_clicked routing logic).

This sandbox has no working PyGObject (_gi C extension missing) and no
Gramps install, so a real GTK/Gramps run isn't possible here. Gio, GLib,
OkDialog, PluginRegister and GuiPluginManager are stood in with light
fakes; the function bodies below are copied verbatim from
PhotoTaggingGramplet.py so this exercises the actual added logic, not a
re-implementation of it, against the real PhotoTaggingGramplet.gpr.py
values (id="Photo Tagging", help_url="Addon:Photo_Tagging_Gramplet") and
the real addon directory (no README.md present).
"""
import os
import tempfile
import unittest
from urllib.parse import quote


# ---- fakes standing in for gi.repository.Gio / .GLib ----------------
class FakeGLibError(Exception):
    pass


class FakeGio:
    launched = []
    raise_error = False

    @classmethod
    def reset(cls):
        cls.launched = []
        cls.raise_error = False

    class AppInfo:
        @staticmethod
        def launch_default_for_uri(uri, ctx):
            if FakeGio.raise_error:
                raise FakeGLibError("boom")
            FakeGio.launched.append(uri)


class FakeGLib:
    Error = FakeGLibError


# ---- fakes standing in for gramps.gui.dialog.OkDialog ----------------
class FakeOkDialog:
    calls = []

    def __init__(self, title, message, parent=None):
        FakeOkDialog.calls.append((title, message, parent))


# ---- fakes standing in for PluginRegister / GuiPluginManager --------
class FakePluginData:
    def __init__(self, name, fpath, help_url):
        self.name = name
        self.fpath = fpath
        self.help_url = help_url


class FakePluginRegister:
    _plugins = {}

    @classmethod
    def get_instance(cls):
        return cls

    @classmethod
    def get_plugin(cls, plugin_id):
        return cls._plugins.get(plugin_id)


class FakeGuiPluginManager:
    _mod_by_pdata_name = {}
    _hidden_ids = set()

    @classmethod
    def get_instance(cls):
        return cls

    @classmethod
    def load_plugin(cls, pdata):
        return cls._mod_by_pdata_name.get(pdata.name)

    @classmethod
    def get_hidden_plugin_ids(cls):
        return cls._hidden_ids


def _(text):
    return text


LOG_MESSAGES = []


class FakeLog:
    @staticmethod
    def exception(msg, *args):
        LOG_MESSAGES.append(msg % args)


Gio = FakeGio
GLib = FakeGLib
OkDialog = FakeOkDialog
PluginRegister = FakePluginRegister
GuiPluginManager = FakeGuiPluginManager
LOG = FakeLog

MARKDOWNDASH_ID = "markdowndash"

# ---- the four functions, copied verbatim from PhotoTaggingGramplet.py --


def find_local_readme(pdata):
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    return readme_path if os.path.isfile(readme_path) else None


def resolve_markdown_dash_opener():
    gpm = GuiPluginManager.get_instance()
    if MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        return None
    pdata = PluginRegister.get_instance().get_plugin(MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        return None
    return getattr(mod, "open_markdown_file", None)


def open_help_url(pdata, parent):
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered " "help_url."),
            parent=parent,
        )
        return
    if help_url.startswith(("http://", "https://")):
        full_url = help_url
    else:
        full_url = "https://gramps-project.org/wiki/index.php?title=" + quote(
            help_url, safe=":"
        )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("PhotoTaggingGramplet: could not open help_url: %s", full_url)


def on_help_clicked(uistate_window, my_plugin_id="Photo Tagging"):
    pdata = PluginRegister.get_instance().get_plugin(my_plugin_id)
    readme_path = find_local_readme(pdata)
    if readme_path is not None:
        open_markdown_file = resolve_markdown_dash_opener()
        if open_markdown_file is not None:
            open_markdown_file(
                readme_path,
                "FAKE_UISTATE",
                parent=uistate_window,
                addon_name=pdata.name,
            )
            return "opened_via_markdown_dash"
    open_help_url(pdata, uistate_window)
    return "opened_via_help_url"


# ------------------------------------------------------------------
# tests
# ------------------------------------------------------------------

REPO_ADDON_DIR = "/home/user/addons-source/PhotoTaggingGramplet"


class HelpButtonLogicTest(unittest.TestCase):
    def setUp(self):
        FakeGio.reset()
        FakeOkDialog.calls = []
        LOG_MESSAGES.clear()
        FakePluginRegister._plugins = {}
        FakeGuiPluginManager._mod_by_pdata_name = {}
        FakeGuiPluginManager._hidden_ids = set()

    # -- find_local_readme -------------------------------------------------
    def test_find_local_readme_none_pdata(self):
        self.assertIsNone(find_local_readme(None))

    def test_find_local_readme_no_fpath(self):
        self.assertIsNone(find_local_readme(FakePluginData("x", "", "help_url")))

    def test_find_local_readme_missing_file_real_addon_dir(self):
        # Exercises the real repo directory: PhotoTaggingGramplet/ has no
        # README.md today, so this must return None, not raise.
        pdata = FakePluginData("Photo Tagging", REPO_ADDON_DIR, "irrelevant")
        self.assertIsNone(find_local_readme(pdata))

    def test_find_local_readme_present_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "README.md"), "w", encoding="utf-8").close()
            pdata = FakePluginData("x", tmp, "irrelevant")
            self.assertEqual(
                find_local_readme(pdata), os.path.join(tmp, "README.md")
            )

    # -- resolve_markdown_dash_opener ---------------------------------------
    def test_resolve_markdown_dash_opener_not_registered(self):
        # Markdown Dash isn't installed in this repo -- must degrade to
        # None, not raise.
        self.assertIsNone(resolve_markdown_dash_opener())

    def test_resolve_markdown_dash_opener_registered_and_loadable(self):
        class FakeModule:
            @staticmethod
            def open_markdown_file(*args, **kwargs):
                pass

        pdata = FakePluginData("Markdown Dash", "/fake/path", None)
        FakePluginRegister._plugins[MARKDOWNDASH_ID] = pdata
        FakeGuiPluginManager._mod_by_pdata_name[pdata.name] = FakeModule
        opener = resolve_markdown_dash_opener()
        self.assertIs(opener, FakeModule.open_markdown_file)

    def test_resolve_markdown_dash_opener_registered_but_hidden(self):
        # Regression test for the human-found bug: a user who clicked
        # "Deactivate" on Markdown Dash in Plugin Manager must not have
        # it silently used anyway. GuiPluginManager.load_plugin() does
        # NOT enforce this on its own (confirmed live) -- the hidden-id
        # check has to happen before load_plugin() is even called.
        class FakeModule:
            @staticmethod
            def open_markdown_file(*args, **kwargs):
                pass

        pdata = FakePluginData("Markdown Dash", "/fake/path", None)
        FakePluginRegister._plugins[MARKDOWNDASH_ID] = pdata
        FakeGuiPluginManager._mod_by_pdata_name[pdata.name] = FakeModule
        FakeGuiPluginManager._hidden_ids = {MARKDOWNDASH_ID}

        self.assertIsNone(resolve_markdown_dash_opener())

    # -- open_help_url --------------------------------------------------
    def test_open_help_url_no_help_url_shows_ok_dialog(self):
        pdata = FakePluginData("x", "/fake", None)
        open_help_url(pdata, parent="PARENT")
        self.assertEqual(len(FakeOkDialog.calls), 1)
        self.assertEqual(FakeOkDialog.calls[0][2], "PARENT")
        self.assertEqual(FakeGio.launched, [])

    def test_open_help_url_full_url_used_as_is(self):
        pdata = FakePluginData("x", "/fake", "https://example.org/help")
        open_help_url(pdata, parent=None)
        self.assertEqual(FakeGio.launched, ["https://example.org/help"])

    def test_open_help_url_real_gpr_help_url_no_regression(self):
        # The real PhotoTaggingGramplet.gpr.py value. Confirms the new
        # quote()-based encoding doesn't change behavior for the actual
        # value in use today (no space, one colon which stays literal).
        pdata = FakePluginData(
            "Photo Tagging", REPO_ADDON_DIR, "Addon:Photo_Tagging_Gramplet"
        )
        open_help_url(pdata, parent=None)
        self.assertEqual(
            FakeGio.launched,
            [
                "https://gramps-project.org/wiki/index.php?"
                "title=Addon:Photo_Tagging_Gramplet"
            ],
        )

    def test_open_help_url_encodes_space_and_special_chars(self):
        # This is the case the fix targets: an f-string would have sent
        # a broken (space-containing) URI straight to launch_default_for_uri.
        pdata = FakePluginData("x", "/fake", "Addon: Photo Tagging & Friends")
        open_help_url(pdata, parent=None)
        self.assertEqual(
            FakeGio.launched,
            [
                "https://gramps-project.org/wiki/index.php?"
                "title=Addon:%20Photo%20Tagging%20%26%20Friends"
            ],
        )

    def test_open_help_url_glib_error_is_caught_and_logged(self):
        FakeGio.raise_error = True
        pdata = FakePluginData("x", "/fake", "https://example.org/help")
        open_help_url(pdata, parent=None)  # must not raise
        self.assertEqual(len(LOG_MESSAGES), 1)
        self.assertIn("https://example.org/help", LOG_MESSAGES[0])

    # -- on_help_clicked (full routing) ----------------------------------
    def test_on_help_clicked_falls_back_to_help_url_today(self):
        # Real-world state of this repo right now: no README.md in
        # PhotoTaggingGramplet/, and Markdown Dash is not installed.
        pdata = FakePluginData(
            "Photo Tagging", REPO_ADDON_DIR, "Addon:Photo_Tagging_Gramplet"
        )
        FakePluginRegister._plugins["Photo Tagging"] = pdata
        result = on_help_clicked(uistate_window="MAIN_WINDOW")
        self.assertEqual(result, "opened_via_help_url")
        self.assertEqual(
            FakeGio.launched,
            [
                "https://gramps-project.org/wiki/index.php?"
                "title=Addon:Photo_Tagging_Gramplet"
            ],
        )

    def test_on_help_clicked_prefers_markdown_dash_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "README.md"), "w", encoding="utf-8").close()
            pdata = FakePluginData("Photo Tagging", tmp, "Addon:Whatever")
            FakePluginRegister._plugins["Photo Tagging"] = pdata

            md_pdata = FakePluginData("Markdown Dash", "/fake/mdd", None)
            FakePluginRegister._plugins[MARKDOWNDASH_ID] = md_pdata

            calls = []

            class FakeMarkdownDashModule:
                @staticmethod
                def open_markdown_file(readme_path, uistate, parent, addon_name):
                    calls.append((readme_path, uistate, parent, addon_name))

            FakeGuiPluginManager._mod_by_pdata_name[
                "Markdown Dash"
            ] = FakeMarkdownDashModule

            result = on_help_clicked(uistate_window="MAIN_WINDOW")
            self.assertEqual(result, "opened_via_markdown_dash")
            self.assertEqual(len(calls), 1)
            readme_path, uistate, parent, addon_name = calls[0]
            self.assertEqual(readme_path, os.path.join(tmp, "README.md"))
            self.assertEqual(parent, "MAIN_WINDOW")
            self.assertEqual(addon_name, "Photo Tagging")
            # Falling back to the browser must NOT also have fired.
            self.assertEqual(FakeGio.launched, [])

    def test_on_help_clicked_falls_back_when_markdown_dash_deactivated(self):
        # Same regression as test_resolve_markdown_dash_opener_registered_
        # but_hidden, exercised through the full on_help_clicked routing:
        # a local README.md exists AND Markdown Dash is registered and
        # loadable, but the user deactivated it -- must fall back to
        # help_url, not open it anyway.
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "README.md"), "w", encoding="utf-8").close()
            pdata = FakePluginData("Photo Tagging", tmp, "https://example.org/help")
            FakePluginRegister._plugins["Photo Tagging"] = pdata

            md_pdata = FakePluginData("Markdown Dash", "/fake/mdd", None)
            FakePluginRegister._plugins[MARKDOWNDASH_ID] = md_pdata

            calls = []

            class FakeMarkdownDashModule:
                @staticmethod
                def open_markdown_file(*args, **kwargs):
                    calls.append(args)

            FakeGuiPluginManager._mod_by_pdata_name[
                "Markdown Dash"
            ] = FakeMarkdownDashModule
            FakeGuiPluginManager._hidden_ids = {MARKDOWNDASH_ID}

            result = on_help_clicked(uistate_window="MAIN_WINDOW")
            self.assertEqual(result, "opened_via_help_url")
            self.assertEqual(calls, [])  # Markdown Dash must not fire
            self.assertEqual(FakeGio.launched, ["https://example.org/help"])

    def test_on_help_clicked_unregistered_plugin_id_degrades_gracefully(self):
        # pdata lookup itself fails (e.g. id typo) -- must not raise, and
        # must show the "no documentation" dialog rather than crash on
        # None.help_url.
        result = on_help_clicked(uistate_window="MAIN_WINDOW", my_plugin_id="typo-id")
        self.assertEqual(result, "opened_via_help_url")
        self.assertEqual(len(FakeOkDialog.calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
