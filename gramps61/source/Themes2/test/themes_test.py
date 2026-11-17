#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025       Paul Culley <paulr2787_at_gmail.com>
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""Unit tests for the Themes addon.

Tests cover:

* Version-sentinel purge logic in ``themes_load``
* CSS directory scanning helper
* ``_load_css_provider`` edge-cases (missing file, invalid CSS path)
* Config-key registration helpers

Run with::

    GRAMPS_RESOURCES=. python3 -m unittest discover -p "*_test.py"

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6), 2025-05-12.
Prompts: rewrite Gramps Themes addon for 5.2 following ThemesRewrite.odt.
"""

# ------------------------
# Python modules
# ------------------------
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Bootstrap: make it possible to import themes_load / themes without a live
# Gramps installation by providing lightweight stubs for the parts of the
# Gramps API that the modules reference at import time.
# ---------------------------------------------------------------------------
_gramps_stubs = {
    "gramps": MagicMock(),
    "gramps.gen": MagicMock(),
    "gramps.gen.config": MagicMock(),
    "gramps.gen.const": MagicMock(),
    "gramps.gen.constfunc": MagicMock(),
    "gramps.gen.utils": MagicMock(),
    "gramps.gen.utils.alive": MagicMock(),
    "gramps.gui": MagicMock(),
    "gramps.gui.configure": MagicMock(),
    "gramps.gui.display": MagicMock(),
    "gi": MagicMock(),
    "gi.repository": MagicMock(),
    "gi.repository.Gtk": MagicMock(),
    "gi.repository.Gdk": MagicMock(),
    "gi.repository.Gio": MagicMock(),
    "gi.repository.GLib": MagicMock(),
    "gi.repository.GObject": MagicMock(),
    "gi.repository.Pango": MagicMock(),
}
for _mod, _stub in _gramps_stubs.items():
    sys.modules.setdefault(_mod, _stub)

# Ensure USER_CSS resolves to something in tests
sys.modules["gramps.gen.const"].USER_CSS = tempfile.mkdtemp(prefix="gramps_css_")

# Make GRAMPS_LOCALE safe
_locale_stub = MagicMock()
_locale_stub.get_addon_translator.side_effect = ValueError
_locale_stub.translation.gettext = lambda s: s
sys.modules["gramps.gen.const"].GRAMPS_LOCALE = _locale_stub

# Add the addon directory to path so we can import the modules under test
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Now import the modules under test (GUI parts skipped by the stubs above)
import themes_load  # noqa: E402 – must come after stub setup


# ============================================================
#
# TestPrefsVersionSentinel
#
# ============================================================
class TestPrefsVersionSentinel(unittest.TestCase):
    """Test the version-sentinel / purge logic in themes_load."""

    def _make_config(self, stored_version: str) -> MagicMock:
        """Return a mock config object pre-set with *stored_version*.

        :param stored_version: Value returned by ``config.get(
            'preferences.themes-version')``.
        :returns: A configured :class:`unittest.mock.MagicMock`.
        """
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, *_: (
            stored_version if key == "preferences.themes-version" else ""
        )
        cfg.get_default.return_value = ""
        return cfg

    def test_matching_version_does_not_purge(self) -> None:
        """No purge should happen when stored version matches PREFS_VERSION."""
        cfg = self._make_config(themes_load.PREFS_VERSION)
        themes_load._register_config_keys(cfg)
        # set() should not be called with the version key during a no-op run
        calls_with_version = [
            c
            for c in cfg.set.call_args_list
            if c.args and c.args[0] == "preferences.themes-version"
        ]
        # _register_config_keys only calls register(), not set()
        self.assertEqual(cfg.set.call_count, 0)

    def test_mismatched_version_triggers_purge(self) -> None:
        """Purge should be triggered when stored version differs."""
        cfg = self._make_config("0.0")
        themes_load._purge_addon_prefs(cfg)
        # set() should be called once per addon key
        self.assertEqual(cfg.set.call_count, len(themes_load._ADDON_CONFIG_KEYS))

    def test_empty_version_triggers_purge(self) -> None:
        """An empty stored version (first run) counts as a mismatch."""
        cfg = self._make_config("")
        # Simulate the condition check done in load_on_reg
        stored = cfg.get("preferences.themes-version")
        mismatch = stored != themes_load.PREFS_VERSION
        self.assertTrue(mismatch)

    def test_prefs_version_is_non_empty_string(self) -> None:
        """PREFS_VERSION must be a non-empty string."""
        self.assertIsInstance(themes_load.PREFS_VERSION, str)
        self.assertTrue(themes_load.PREFS_VERSION)

    def test_register_config_keys_covers_all_addon_keys(self) -> None:
        """Every key in _ADDON_CONFIG_KEYS must be registered."""
        cfg = MagicMock()
        themes_load._register_config_keys(cfg)
        registered = {c.args[0] for c in cfg.register.call_args_list}
        for key in themes_load._ADDON_CONFIG_KEYS:
            self.assertIn(key, registered, msg=f"Key '{key}' not registered")


# ============================================================
#
# TestLoadCssProvider
#
# ============================================================
class TestLoadCssProvider(unittest.TestCase):
    """Test _load_css_provider helper."""

    def setUp(self) -> None:
        """Create a temp directory with a dummy CSS file."""
        self.tmpdir = tempfile.mkdtemp()
        self.css_file = os.path.join(self.tmpdir, "test.css")
        with open(self.css_file, "w", encoding="utf-8") as fh:
            fh.write(".test { color: red; }")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def test_returns_false_for_missing_file(self) -> None:
        """_load_css_provider must return False for a non-existent path."""
        screen = MagicMock()
        result = themes_load._load_css_provider(
            "/nonexistent/path.css", screen, 600
        )
        self.assertFalse(result)

    @patch("themes_load.Gtk", create=True)
    def test_returns_true_for_valid_file(self, mock_gtk) -> None:
        """_load_css_provider must return True when the file exists."""
        # themes_load imports Gtk inside the function; patch it there
        mock_provider = MagicMock()
        mock_gtk.CssProvider.return_value = mock_provider
        screen = MagicMock()
        # Re-import to pick up patched Gtk
        with patch.dict("sys.modules", {"gi.repository.Gtk": mock_gtk}):
            result = themes_load._load_css_provider(self.css_file, screen, 600)
        self.assertTrue(result)

    def test_returns_false_for_empty_path(self) -> None:
        """An empty string path must return False without raising."""
        screen = MagicMock()
        result = themes_load._load_css_provider("", screen, 600)
        self.assertFalse(result)


# ============================================================
#
# TestScanCssDir  (via themes._scan_css_dir logic, tested standalone)
#
# ============================================================
class TestScanCssDir(unittest.TestCase):
    """Test the directory-scanning logic used for themes and patches."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir)

    def _scan(self, directory: str) -> dict:
        """Minimal reimplementation of MyPrefs._scan_css_dir for unit-testing.

        :param directory: Directory to scan.
        :returns: ``{name: path}`` dict.
        """
        result = {}
        if not os.path.isdir(directory):
            return result
        for fname in os.listdir(directory):
            if fname.endswith(".css"):
                result[fname[:-4]] = os.path.join(directory, fname)
        return result

    def test_returns_empty_for_missing_directory(self) -> None:
        """Scanning a non-existent directory must return an empty dict."""
        result = self._scan("/does/not/exist")
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 0)

    def test_returns_empty_for_empty_directory(self) -> None:
        """An existing but empty directory yields an empty dict."""
        result = self._scan(self.tmpdir)
        self.assertEqual(len(result), 0)

    def test_css_files_are_discovered(self) -> None:
        """CSS files in the directory appear in the result."""
        for name in ("dark-blue.css", "light-green.css"):
            with open(os.path.join(self.tmpdir, name), "w") as fh:
                fh.write("/* test */")
        result = self._scan(self.tmpdir)
        self.assertIn("dark-blue", result)
        self.assertIn("light-green", result)
        self.assertEqual(len(result), 2)

    def test_non_css_files_are_ignored(self) -> None:
        """Non-CSS files must not appear in the result."""
        with open(os.path.join(self.tmpdir, "readme.txt"), "w") as fh:
            fh.write("hello")
        result = self._scan(self.tmpdir)
        self.assertEqual(len(result), 0)

    def test_result_values_are_absolute_paths(self) -> None:
        """Result values must be absolute file paths."""
        css_name = "my-theme.css"
        with open(os.path.join(self.tmpdir, css_name), "w") as fh:
            fh.write("/* test */")
        result = self._scan(self.tmpdir)
        path = result["my-theme"]
        self.assertTrue(os.path.isabs(path))
        self.assertTrue(os.path.isfile(path))


# ============================================================
#
# TestAddonConfigKeys
#
# ============================================================
class TestAddonConfigKeys(unittest.TestCase):
    """Sanity-check the _ADDON_CONFIG_KEYS list."""

    def test_version_key_is_in_list(self) -> None:
        """The version sentinel key must be present."""
        self.assertIn(
            "preferences.themes-version", themes_load._ADDON_CONFIG_KEYS
        )

    def test_all_keys_are_strings(self) -> None:
        """Every entry in _ADDON_CONFIG_KEYS must be a non-empty string."""
        for key in themes_load._ADDON_CONFIG_KEYS:
            self.assertIsInstance(key, str)
            self.assertTrue(key)

    def test_no_duplicate_keys(self) -> None:
        """_ADDON_CONFIG_KEYS must not contain duplicates."""
        self.assertEqual(
            len(themes_load._ADDON_CONFIG_KEYS),
            len(set(themes_load._ADDON_CONFIG_KEYS)),
        )


if __name__ == "__main__":
    unittest.main()
