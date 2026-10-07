#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
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

"""
Unit tests for the pure-Python path-resolution utilities in MarkdownDash.

Covers:
  - :class:`PathResolution` data class
  - :data:`_LANG_SUFFIX_RE` regex
  - :func:`resolve_localized_path` — all four resolution branches
  - CWD-independence (HOME collision regression test)
  - :meth:`MarkdownDash._resolve_path` asset-base logic (via a lightweight stub)

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Bootstrap: inject lightweight stubs for GTK / Gramps imports so the module
# can be imported without a running Gramps / GTK session.
# ---------------------------------------------------------------------------

_STUB_MODULES = [
    "gi",
    "gi.repository",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.GLib",
    "gi.repository.Gio",
    "gi.repository.GdkPixbuf",
    "gi.repository.Pango",
    "gramps",
    "gramps.version",
    "gramps.gen",
    "gramps.gen.plug",
    "gramps.gen.const",
]

for _mod_name in _STUB_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = types.ModuleType(_mod_name)

# Minimal attribute stubs needed to survive the module-level gi.require_version
# calls and the glocale / Gramplet references.
_gi = sys.modules["gi"]
_gi.require_version = lambda *a, **kw: None  # type: ignore[attr-defined]


def _make_catch_all_module(name: str) -> types.ModuleType:
    """Return a stub module whose attribute access always succeeds.

    Returned attributes are real Python ``type`` objects (not instances) so
    that runtime ``X | None`` union expressions in function signatures of the
    modules under test do not raise ``TypeError``.
    """
    mod = types.ModuleType(name)
    _cache: dict = {}

    def _getattr(attr: str) -> type:
        if attr not in _cache:
            # Create a genuine new type; supports X | None at runtime
            _cache[attr] = type(attr, (), {"__call__": lambda s, *a, **k: s})
        return _cache[attr]

    mod.__getattr__ = _getattr  # type: ignore[attr-defined]
    return mod


for _gi_mod in (
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.GLib",
    "gi.repository.Gio",
    "gi.repository.GdkPixbuf",
    "gi.repository.Pango",
):
    sys.modules[_gi_mod] = _make_catch_all_module(_gi_mod)

# A few constants _on_key_press checks need concrete integer values
_gdk = sys.modules["gi.repository.Gdk"]
_gdk.KEY_Left = 0xFF51  # type: ignore[attr-defined]
_gdk.KEY_Right = 0xFF53  # type: ignore[attr-defined]

# GLib.Error is caught by name in _open_uri; must be a real exception class
sys.modules["gi.repository.GLib"].Error = Exception  # type: ignore[attr-defined]

_gramps_version = sys.modules["gramps.version"]
_gramps_version.major_version = "5.2"  # type: ignore[attr-defined]
_gramps_version.VERSION_TUPLE = (5, 2, 0)  # type: ignore[attr-defined]

_gramps_gen_plug = sys.modules["gramps.gen.plug"]


class _FakeGramplet:
    """Minimal Gramplet stub so MarkdownDash can subclass it."""


_gramps_gen_plug.Gramplet = _FakeGramplet  # type: ignore[attr-defined]

_gramps_gen_const = sys.modules["gramps.gen.const"]


class _FakeLocale:
    """Stub for GRAMPS_LOCALE matching the real GrampsLocale attribute API.

    Real attributes used by ``_locale_lang()``:

    - ``glocale.lang``      — POSIX string e.g. ``"fi_FI.UTF-8"``
    - ``glocale.language``  — list e.g. ``["fi"]``
    - ``glocale.translation.gettext`` — callable returning its argument
    """

    lang: str = "en_US.UTF-8"
    language: list[str] = ["en"]

    class translation:  # noqa: N801 — matches Gramps API attribute name
        """Stub for glocale.translation."""

        @staticmethod
        def gettext(s: str) -> str:
            """Return the string unchanged (no-op translation)."""
            return s


_gramps_gen_const.GRAMPS_LOCALE = _FakeLocale()  # type: ignore[attr-defined]

# Now we can safely import the module-level symbols we want to test.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pylint: disable=wrong-import-position
from MarkdownDash import (  # noqa: E402
    PathResolution,
    _LANG_SUFFIX_RE,
    _locale_lang,
    resolve_localized_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _touch(path: str) -> None:
    """Create *path* (and any missing parent directories) as an empty file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").close()


def _plugin_tree(
    tmp: str,
    *,
    readme: bool = True,
    locales: tuple[str, ...] = (),
    labelled: tuple[str, ...] = (),
    images: tuple[str, ...] = (),
) -> str:
    """Build a fake plugin directory under *tmp* and return its path.

    :param tmp:      Root temporary directory.
    :param readme:   Whether to create ``README.md`` (English baseline).
    :param locales:  Language codes to create under ``locale/<lang>/README.md``.
    :param labelled: Language codes for ``README_<lang>.md`` source-lang files.
    :param images:   Relative image paths to create alongside ``README.md``.
    :returns:        Absolute path to the plugin directory.
    """
    plugin_dir = os.path.join(tmp, "MyAddon")
    os.makedirs(plugin_dir, exist_ok=True)
    if readme:
        _touch(os.path.join(plugin_dir, "README.md"))
    for lang in locales:
        _touch(os.path.join(plugin_dir, "locale", lang, "README.md"))
    for lang in labelled:
        _touch(os.path.join(plugin_dir, f"README_{lang}.md"))
    for img in images:
        _touch(os.path.join(plugin_dir, img))
    return plugin_dir


# ---------------------------------------------------------------------------
# _locale_lang tests
# ---------------------------------------------------------------------------


class TestLocaleLang(unittest.TestCase):
    """Tests for :func:`_locale_lang` using the real GrampsLocale attribute API.

    Each test patches ``MarkdownDash.glocale`` with a minimal stub that only
    sets the two attributes ``_locale_lang`` actually reads: ``.lang`` and
    ``.language``.
    """

    def _run(self, lang: str, language: list[str]) -> tuple[str, str]:
        """Run ``_locale_lang()`` with a patched glocale stub."""
        stub = types.SimpleNamespace(lang=lang, language=language)
        with patch("MarkdownDash.glocale", stub):
            return _md_module._locale_lang()  # pylint: disable=protected-access

    def test_finnish(self) -> None:
        """Finnish locale produces (fi_FI, fi)."""
        full, short = self._run("fi_FI.UTF-8", ["fi"])
        self.assertEqual(full, "fi_FI")
        self.assertEqual(short, "fi")

    def test_french_full(self) -> None:
        """French (France) locale produces (fr_FR, fr)."""
        full, short = self._run("fr_FR.UTF-8", ["fr"])
        self.assertEqual(full, "fr_FR")
        self.assertEqual(short, "fr")

    def test_english_us(self) -> None:
        """English (US) locale produces (en_US, en)."""
        full, short = self._run("en_US.UTF-8", ["en"])
        self.assertEqual(full, "en_US")
        self.assertEqual(short, "en")

    def test_c_locale_falls_back(self) -> None:
        """The POSIX 'C' locale is normalised to (en_US, en)."""
        full, short = self._run("C", ["en"])
        self.assertEqual(full, "en_US")
        self.assertEqual(short, "en")

    def test_codeset_stripped(self) -> None:
        """Codeset suffix (.UTF-8) must be stripped from lang_full."""
        full, _ = self._run("de_DE.UTF-8", ["de"])
        self.assertNotIn(".", full)
        self.assertEqual(full, "de_DE")

    def test_modifier_stripped(self) -> None:
        """Modifier suffix (@euro) must be stripped from lang_full."""
        full, _ = self._run("de_DE@euro", ["de"])
        self.assertNotIn("@", full)
        self.assertEqual(full, "de_DE")

    def test_language_list_first_element_used(self) -> None:
        """Only the first element of glocale.language is used for lang_short."""
        _, short = self._run("fi_FI.UTF-8", ["fi", "en"])
        self.assertEqual(short, "fi")

    def test_empty_language_list_falls_back(self) -> None:
        """An empty language list falls back to 'en' for lang_short."""
        _, short = self._run("en_US.UTF-8", [])
        self.assertEqual(short, "en")

    def test_exception_returns_defaults(self) -> None:
        """An AttributeError on glocale must return the safe default."""
        stub = types.SimpleNamespace()  # no .lang or .language
        with patch("MarkdownDash.glocale", stub):
            full, short = _md_module._locale_lang()  # pylint: disable=protected-access
        self.assertEqual(full, "en_US")
        self.assertEqual(short, "en")


# ---------------------------------------------------------------------------
# PathResolution tests
# ---------------------------------------------------------------------------


class TestPathResolution(unittest.TestCase):
    """Tests for the :class:`PathResolution` data class."""

    def test_defaults(self) -> None:
        """Default values should be non-fallback, no source_lang, English."""
        r = PathResolution("/some/path/README.md")
        self.assertEqual(r.path, "/some/path/README.md")
        self.assertFalse(r.is_fallback)
        self.assertIsNone(r.source_lang)
        self.assertEqual(r.user_lang, "en")

    def test_explicit_fields(self) -> None:
        """All fields should be settable explicitly."""
        r = PathResolution(
            "/p/README_fi.md", is_fallback=True, source_lang="fi", user_lang="en"
        )
        self.assertTrue(r.is_fallback)
        self.assertEqual(r.source_lang, "fi")
        self.assertEqual(r.user_lang, "en")

    def test_slots_reject_arbitrary_attrs(self) -> None:
        """``__slots__`` should prevent adding undefined attributes."""
        r = PathResolution("/p/README.md")
        with self.assertRaises(AttributeError):
            r.nonexistent = "x"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# _LANG_SUFFIX_RE tests
# ---------------------------------------------------------------------------


class TestLangSuffixRe(unittest.TestCase):
    """Tests for the :data:`_LANG_SUFFIX_RE` filename regex."""

    def _match(self, name: str) -> dict | None:
        m = _LANG_SUFFIX_RE.match(name)
        return m.groupdict() if m else None

    def test_simple_two_letter(self) -> None:
        g = self._match("README_fi.md")
        self.assertIsNotNone(g)
        self.assertEqual(g["stem"], "README")
        self.assertEqual(g["lang"], "fi")
        self.assertEqual(g["ext"], ".md")

    def test_full_locale(self) -> None:
        g = self._match("README_fr_FR.md")
        self.assertIsNotNone(g)
        self.assertEqual(g["lang"], "fr_FR")

    def test_compound_stem(self) -> None:
        g = self._match("MyAddon_help_de.md")
        self.assertIsNotNone(g)
        self.assertEqual(g["stem"], "MyAddon_help")
        self.assertEqual(g["lang"], "de")

    def test_no_match_plain_readme(self) -> None:
        self.assertIsNone(self._match("README.md"))

    def test_no_match_uppercase_lang(self) -> None:
        """Language code must be lower-case per the regex."""
        self.assertIsNone(self._match("README_FI.md"))

    def test_no_match_three_letter_lang(self) -> None:
        self.assertIsNone(self._match("README_fin.md"))


# ---------------------------------------------------------------------------
# resolve_localized_path tests
# ---------------------------------------------------------------------------


class TestResolveLocalizedPath(unittest.TestCase):
    """Tests for :func:`resolve_localized_path`."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── empty / missing input ────────────────────────────────────────────

    def test_empty_string(self) -> None:
        """Empty path should return a PathResolution with empty path."""
        r = resolve_localized_path("")
        self.assertEqual(r.path, "")

    def test_nonexistent_path_no_variants(self) -> None:
        """A path pointing nowhere with no variants returns itself (absolute)."""
        target = os.path.join(self._tmpdir, "MyAddon", "README.md")
        r = resolve_localized_path(target)
        self.assertEqual(r.path, target)
        self.assertFalse(r.is_fallback)

    # ── branch 1/2: locale sub-directory variant ─────────────────────────

    def test_locale_full_variant_preferred(self) -> None:
        """``locale/fr_FR/README.md`` should be returned for a ``fr_FR`` user."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True, locales=("fr_FR", "fr"))
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("fr_FR", "fr")):
            r = resolve_localized_path(target)
        expected = os.path.join(plugin_dir, "locale", "fr_FR", "README.md")
        self.assertEqual(r.path, expected)
        self.assertFalse(r.is_fallback)
        self.assertIsNone(r.source_lang)

    def test_locale_short_variant_fallback(self) -> None:
        """``locale/fr/README.md`` used when full ``fr_FR`` variant absent."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True, locales=("fr",))
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("fr_FR", "fr")):
            r = resolve_localized_path(target)
        expected = os.path.join(plugin_dir, "locale", "fr", "README.md")
        self.assertEqual(r.path, expected)
        self.assertFalse(r.is_fallback)

    # ── branch 3: unlabelled English baseline ────────────────────────────

    def test_english_user_no_fallback(self) -> None:
        """English user with only ``README.md`` — not a fallback."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True)
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            r = resolve_localized_path(target)
        self.assertEqual(r.path, target)
        self.assertFalse(r.is_fallback)

    def test_non_english_user_is_fallback(self) -> None:
        """Finnish user with only ``README.md`` — is_fallback should be True."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True)
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("fi_FI", "fi")):
            r = resolve_localized_path(target)
        self.assertEqual(r.path, target)
        self.assertTrue(r.is_fallback)
        self.assertIsNone(r.source_lang)

    # ── branch 4: source-language-labelled baseline ──────────────────────

    def test_labelled_source_lang_shown_to_english_user(self) -> None:
        """English user finds ``README_fi.md`` — is_fallback True, source_lang fi."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=False, labelled=("fi",))
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            r = resolve_localized_path(target)
        expected = os.path.join(plugin_dir, "README_fi.md")
        self.assertEqual(r.path, expected)
        self.assertTrue(r.is_fallback)
        self.assertEqual(r.source_lang, "fi")

    def test_labelled_source_lang_matches_user(self) -> None:
        """Finnish user finds ``README_fi.md`` — is_fallback False (correct lang)."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=False, labelled=("fi",))
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("fi_FI", "fi")):
            r = resolve_localized_path(target)
        expected = os.path.join(plugin_dir, "README_fi.md")
        self.assertEqual(r.path, expected)
        self.assertFalse(r.is_fallback)
        self.assertEqual(r.source_lang, "fi")

    def test_labelled_locale_variant_beats_labelled_baseline(self) -> None:
        """``locale/fi/README.md`` should win over ``README_fi.md``."""
        plugin_dir = _plugin_tree(
            self._tmpdir, readme=False, locales=("fi",), labelled=("fi",)
        )
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("fi_FI", "fi")):
            r = resolve_localized_path(target)
        expected = os.path.join(plugin_dir, "locale", "fi", "README.md")
        self.assertEqual(r.path, expected)

    # ── path absoluteness / CWD-independence (HOME collision regression) ──

    def test_returned_path_is_always_absolute(self) -> None:
        """All returned paths must be absolute regardless of process CWD."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True, locales=("fr",))
        target = os.path.join(plugin_dir, "README.md")
        # Force CWD to home to expose the regression
        orig_cwd = os.getcwd()
        try:
            os.chdir(os.path.expanduser("~"))
            with patch("MarkdownDash._locale_lang", return_value=("fr_FR", "fr")):
                r = resolve_localized_path(target)
        finally:
            os.chdir(orig_cwd)
        self.assertTrue(
            os.path.isabs(r.path),
            f"Expected absolute path, got: {r.path!r}",
        )

    def test_asset_base_not_home_when_cwd_is_home(self) -> None:
        """The asset base derived from a locale variant must not be HOME.

        Regression: when Gramps launches from ``~``, a relative path through
        ``_get_localized_filepath`` previously caused ``os.path.abspath`` to
        anchor to ``~`` instead of the plugin directory.
        """
        plugin_dir = _plugin_tree(self._tmpdir, readme=True, locales=("fi",))
        target = os.path.join(plugin_dir, "README.md")
        orig_cwd = os.getcwd()
        try:
            os.chdir(os.path.expanduser("~"))
            with patch("MarkdownDash._locale_lang", return_value=("fi_FI", "fi")):
                r = resolve_localized_path(target)
        finally:
            os.chdir(orig_cwd)
        home = os.path.expanduser("~")
        self.assertNotEqual(
            os.path.dirname(r.path),
            home,
            "asset base resolved to HOME — CWD anchor regression",
        )
        self.assertIn(
            plugin_dir,
            r.path,
            f"Resolved path {r.path!r} does not contain plugin_dir {plugin_dir!r}",
        )

    def test_tilde_path_resolved(self) -> None:
        """A ``~``-prefixed path should be fully resolved."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True)
        readme = os.path.join(plugin_dir, "README.md")
        # Manufacture a tilde path that points to the same file
        home = os.path.expanduser("~")
        if not readme.startswith(home):
            self.skipTest("tmpdir is not under HOME; cannot manufacture tilde path")
        tilde_path = "~" + readme[len(home) :]
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            r = resolve_localized_path(tilde_path)
        self.assertTrue(os.path.isabs(r.path))
        self.assertEqual(r.path, readme)

    # ── resolution priority chain ─────────────────────────────────────────

    def test_locale_variant_beats_english_baseline(self) -> None:
        """A locale variant must take precedence over the English baseline."""
        plugin_dir = _plugin_tree(self._tmpdir, readme=True, locales=("de",))
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("de_DE", "de")):
            r = resolve_localized_path(target)
        self.assertIn("locale", r.path)
        self.assertIn("de", r.path)

    def test_english_baseline_beats_foreign_labelled(self) -> None:
        """An unlabelled ``README.md`` beats a ``README_fi.md`` even for Finnish users.

        If the addon ships both ``README.md`` (English) and ``README_fi.md``
        (Finnish), the ``locale/fi/`` sub-directory variant is checked first
        (not found here), then ``README.md`` is returned as the next match —
        the ``README_fi.md`` scan in branch 4 is only reached when the
        canonical basename doesn't exist.
        """
        plugin_dir = _plugin_tree(self._tmpdir, readme=True, labelled=("fi",))
        target = os.path.join(plugin_dir, "README.md")
        with patch("MarkdownDash._locale_lang", return_value=("fi_FI", "fi")):
            r = resolve_localized_path(target)
        # No locale/fi/ variant → falls through to README.md (branch 3)
        self.assertEqual(r.path, target)
        self.assertTrue(r.is_fallback)


# ---------------------------------------------------------------------------
# _resolve_path asset-base logic (stub-based)
# ---------------------------------------------------------------------------


import MarkdownDash as _md_module  # noqa: E402 — after sys.path manipulation


class _StubViewer:
    """Minimal stand-in for MarkdownDash / _MarkdownViewer with _resolve_path."""

    current_file: str | None = None
    _asset_base: str | None = None

    def _resolve_path(self, path: str) -> str:
        """Copy of MarkdownDash._resolve_path for isolated testing.

        Calls ``_md_module._locale_lang`` so ``unittest.mock.patch`` on
        ``"MarkdownDash._locale_lang"`` correctly intercepts the lookup.
        """
        if os.path.isabs(path):
            return path

        base = self._asset_base
        if not base and self.current_file:
            base = os.path.dirname(self.current_file)
            locale_marker = os.sep + "locale" + os.sep
            if locale_marker in base:
                base = base.split(locale_marker)[0]

        if not base:
            return path

        lang_full, lang_short = (
            _md_module._locale_lang()
        )  # pylint: disable=protected-access
        for lang_code in (lang_full, lang_short):
            locale_asset = os.path.join(base, "locale", lang_code, path)
            if os.path.isfile(locale_asset):
                return locale_asset

        candidate = os.path.join(base, path)
        if os.path.isfile(candidate):
            return candidate

        return path


class TestResolvePath(unittest.TestCase):
    """Tests for the asset-resolution logic in ``_resolve_path``."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._plugin_dir = _plugin_tree(
            self._tmpdir,
            readme=True,
            locales=("fi",),
            images=("images/diagram.png",),
        )
        # Also create a locale-specific image
        _touch(
            os.path.join(self._plugin_dir, "locale", "fi", "images", "diagram_fi.png")
        )

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _viewer(
        self,
        current_file: str | None = None,
        asset_base: str | None = None,
    ) -> _StubViewer:
        v = _StubViewer()
        v.current_file = current_file
        v._asset_base = asset_base
        return v

    def test_absolute_path_returned_unchanged(self) -> None:
        """Absolute image paths must pass through unmodified."""
        v = self._viewer(asset_base=self._plugin_dir)
        abs_path = os.path.join(self._plugin_dir, "images", "diagram.png")
        self.assertEqual(v._resolve_path(abs_path), abs_path)

    def test_relative_image_found_via_asset_base(self) -> None:
        """Relative image resolves against ``_asset_base``, not CWD."""
        fi_readme = os.path.join(self._plugin_dir, "locale", "fi", "README.md")
        v = self._viewer(
            current_file=fi_readme,
            asset_base=self._plugin_dir,  # correctly set by _load()
        )
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            result = v._resolve_path("images/diagram.png")
        expected = os.path.join(self._plugin_dir, "images", "diagram.png")
        self.assertEqual(result, expected)

    def test_relative_image_fails_without_asset_base(self) -> None:
        """Without ``_asset_base``, a locale-subdir ``current_file`` should
        still resolve correctly via the belt-and-braces locale strip."""
        fi_readme = os.path.join(self._plugin_dir, "locale", "fi", "README.md")
        v = self._viewer(current_file=fi_readme, asset_base=None)
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            result = v._resolve_path("images/diagram.png")
        expected = os.path.join(self._plugin_dir, "images", "diagram.png")
        self.assertEqual(result, expected)

    def test_locale_asset_preferred_over_canonical(self) -> None:
        """A locale-specific asset variant beats the canonical one."""
        v = self._viewer(asset_base=self._plugin_dir)
        with patch("MarkdownDash._locale_lang", return_value=("fi_FI", "fi")):
            result = v._resolve_path("images/diagram_fi.png")
        expected = os.path.join(
            self._plugin_dir, "locale", "fi", "images", "diagram_fi.png"
        )
        self.assertEqual(result, expected)

    def test_missing_asset_returns_relative_path(self) -> None:
        """A relative path for a non-existent asset is returned as-is."""
        v = self._viewer(asset_base=self._plugin_dir)
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            result = v._resolve_path("images/missing.png")
        self.assertEqual(result, "images/missing.png")
        """A relative path for a non-existent asset is returned as-is."""
        v = self._viewer(asset_base=self._plugin_dir)
        with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
            result = v._resolve_path("images/missing.png")
        self.assertEqual(result, "images/missing.png")

    def test_no_base_no_current_file_returns_path(self) -> None:
        """With neither ``_asset_base`` nor ``current_file`` set, return input."""
        v = self._viewer()
        result = v._resolve_path("images/diagram.png")
        self.assertEqual(result, "images/diagram.png")

    def test_cwd_home_does_not_corrupt_asset_base(self) -> None:
        """The HOME-collision regression: asset resolution must ignore CWD."""
        fi_readme = os.path.join(self._plugin_dir, "locale", "fi", "README.md")
        v = self._viewer(
            current_file=fi_readme,
            asset_base=self._plugin_dir,
        )
        orig_cwd = os.getcwd()
        try:
            os.chdir(os.path.expanduser("~"))
            with patch("MarkdownDash._locale_lang", return_value=("en_US", "en")):
                result = v._resolve_path("images/diagram.png")
        finally:
            os.chdir(orig_cwd)
        home = os.path.expanduser("~")
        self.assertFalse(
            result.startswith(home + os.sep + "images"),
            f"Asset resolved under HOME — CWD anchor regression: {result!r}",
        )
        expected = os.path.join(self._plugin_dir, "images", "diagram.png")
        self.assertEqual(result, expected)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
