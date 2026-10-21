# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2010  Doug Blank <doug.blank@gmail.com>
# Copyright (C) 2011  Nick Hall
# Copyright (C) 2011  Tim G L Lyons
# Copyright (C) 2024  Paul Womack (BugBear)
# Copyright (C) 2026  Claude AI (wish coding by Brian McCullough)
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

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------

import logging
import os
from typing import Callable
from urllib.parse import quote

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------

from gi.repository import Gdk, Gio, GLib, Gtk

from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import displayer
from gramps.gen.filters import GenericFilter
from gramps.gen.filters.rules import Rule
from gramps.gen.filters.rules.person import ProbablyAlive
from gramps.gen.lib import Date
from gramps.gen.lib.person import Person
from gramps.gen.plug import BasePluginManager, Gramplet, PluginRegister
from gramps.gen.plug._pluginreg import PluginData
from gramps.gen.soundex import soundex
from gramps.gen.utils.configmanager import ConfigManager
from gramps.gui import widgets
from gramps.gui.dialog import OkDialog
from gramps.gui.filters.sidebar import SidebarFilter
from gramps.gui.pluginmanager import GuiPluginManager

# -------------------------------------------------------------------------
#
# Gramps specific
#
# -------------------------------------------------------------------------

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)

# ======================================================================
# BEGIN HELP BUTTON BLOCK -- pasted from the MarkdownBased reference
# help_doc_button.py (recipe: HelpDocButton.md), using this module's
# own _ and LOG.
# ======================================================================
_MARKDOWNDASH_ID = "markdowndash"
_HELP_ICON_NAME = "help-browser"


def resolve_help_icon(size: int = 16) -> Gtk.Image:
    """
    Return a Gtk.Image of the full-color help-browser icon.

    :param size: icon size in pixels (square).
    :returns: the image; empty (with a logged warning) if the theme has
        no such icon at that size.
    """
    theme = Gtk.IconTheme.get_default()
    flags = (
        Gtk.IconLookupFlags.FORCE_REGULAR  # color, not the symbolic variant
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE  # exactly `size`, not nearest
    )
    info = theme.lookup_icon(_HELP_ICON_NAME, size, flags)
    image = Gtk.Image()
    if info is not None:
        image.set_from_pixbuf(info.load_icon())
    else:
        # Deliberately no new_from_icon_name() fallback: that is the
        # unreliable variant/size lookup this function exists to avoid.
        LOG.warning(
            "resolve_help_icon: theme has no '%s' icon at size %d",
            _HELP_ICON_NAME,
            size,
        )
    return image


def find_local_readme(pdata: PluginData | None) -> str | None:
    """
    Return the canonical README.md path of the plugin, or None if the
    plugin has no README of any kind.

    "Any kind" is decided by ``MarkdownUtils.resolve_localized_path()``:
    ``README.md``, a source-language ``README_<lang>.md``, or a
    ``locale/<lang>/README.md`` translation. The returned path need not
    exist on disk; Markdown Dash resolves it to the best variant for the
    user's language, falling back to the English baseline. If
    MarkdownUtils cannot be imported, only a literal ``README.md`` counts.

    :param pdata: the plugin's PluginData; None is tolerated.
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # Imported here, not at module level, so a missing MarkdownUtils
        # never stops the host module from loading. Since MarkdownUtils
        # 0.2.1 (load_on_reg=True), Gramps imports it at startup, so this
        # normally succeeds; cb_show_help() also loads Markdown Dash
        # first, which imports it too, as a fallback for older installs.
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener() -> Callable[..., Gtk.Dialog] | None:
    """
    Return Markdown Dash's open_markdown_file(), or None.

    None means Markdown Dash is deactivated, not registered, fails to
    load, or lacks that function -- callers treat all four the same way
    (fall back to help_url). Each case logs a warning naming itself, so
    a Help button that unexpectedly opens the browser can be diagnosed
    from the terminal; they only appear when Help is clicked.
    """
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        LOG.warning("help button: Markdown Dash is deactivated")
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        LOG.warning("help button: no plugin registered as '%s'", _MARKDOWNDASH_ID)
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        LOG.warning(
            "help button: Markdown Dash at %s failed to load (see the "
            "'Plugin error' above, often a missing MarkdownUtils)",
            pdata.fpath,
        )
        return None
    opener = getattr(mod, "open_markdown_file", None)
    if opener is None:
        LOG.warning(
            "help button: Markdown Dash at %s has no open_markdown_file()",
            pdata.fpath,
        )
    return opener


def open_help_url(pdata: PluginData | None, parent: Gtk.Window | None) -> None:
    """
    Open the plugin's registered help_url in the default browser.

    A bare wiki page title is resolved against gramps-project.org; a full
    http(s) URL is used as-is.

    :param pdata: the plugin's PluginData.
    :param parent: transient parent for the "no documentation" notice.
    """
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered help_url."),
            parent=parent,
        )
        return
    full_url = (
        help_url
        if help_url.startswith(("http://", "https://"))
        else "https://gramps-project.org/wiki/index.php?title="
        + quote(help_url, safe=":")
    )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("help button: could not open help_url: %s", full_url)


def cb_show_help(_button: Gtk.Button, uistate, pdata: PluginData | None) -> None:
    """
    Show the best documentation available: the plugin's own README.md in
    a Markdown Dash window if possible, else its help_url in a browser.

    :param uistate: the Gramps UiState (its main window parents the reader).
    :param pdata: the calling plugin's own PluginData.
    """
    # Load Markdown Dash first. MarkdownUtils is normally already loaded at
    # startup (load_on_reg in MarkdownUtils 0.2.1), but loading Markdown
    # Dash also imports it, so find_local_readme() can recognize
    # translated READMEs even with an older MarkdownUtils installed.
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None:
            open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            return
    open_help_url(pdata, uistate.window)


def add_help_button(
    container: Gtk.Box,
    uistate,
    plugin: PluginData | str | None,
    *,
    size: int = 16,
) -> Gtk.Button:
    """
    Pack a color "Help" button (icon plus visible label) into container.

    :param container: the Gtk.Box to pack into -- a gramplet's button row,
        or a dialog's action area.
    :param uistate: the Gramps UiState.
    :param plugin: the calling plugin's own registered id (the id= in its
        .gpr.py), or its PluginData.
    :param size: icon size in pixels; the default suits a row of ordinary
        text buttons.
    :returns: the created, already-packed button.
    """
    if isinstance(plugin, str):
        plugin_id = plugin
        plugin = PluginRegister.get_instance().get_plugin(plugin_id)
        if plugin is None:
            LOG.warning("add_help_button: no registered plugin '%s'", plugin_id)
    button = Gtk.Button()
    button.set_image(resolve_help_icon(size))
    button.set_always_show_image(True)  # else some themes hide the icon
    button.set_label(_("Help"))
    # Tooltip on the button: a Gtk.Image inside a button never shows its own.
    button.set_tooltip_text(_("Show documentation for this plugin"))
    button.connect("clicked", cb_show_help, uistate, plugin)
    container.pack_start(button, False, False, 0)
    button.show_all()
    return button


# END HELP BUTTON BLOCK

# This addon's own registered id (see FlatFilter.gpr.py), also
# saved into FlatFilter.ini as an identity check (see _get_config_manager).
_PLUGIN_ID: str = "Flat Filter"

# Bumped whenever a change to the saved keys below would make an older
# FlatFilter.ini misleading rather than merely out of date (e.g. a renamed
# or repurposed key) -- see _get_config_manager's identity/schema check.
_CONFIG_SCHEMA_VERSION: str = "1"

# Name used to register this addon's own settings with Gramps' core
# configuration-management feature (gramps.gen.config). No ".ini"
# suffix -- Gramps adds that itself.
_CONFIG_MANAGER_NAME = "FlatFilter"

# Default states for the Person row's "Include:" checkboxes, used both
# to register each setting's type/default and as the effective state
# the very first time this addon runs, before anything has been saved.
_PERSONAL_DEFAULTS: dict[str, bool] = {
    "title": False,
    "given": True,
    "call": False,
    "nick": False,
    "alternatives": True,
}
_SURNAME_DEFAULTS: dict[str, bool] = {
    "prefix": False,
    "surname": True,
    "suffix": False,
    "clan": False,
    "alternatives": True,
}

# Default states for the "Use pattern matching (Regular expressions)"
# and "Use fuzzy matching" checkboxes -- neither checked, matching this
# addon's original (pre-settings) behaviour.
_MATCHING_DEFAULTS: dict[str, bool] = {
    "regex": False,
    "fuzzy": False,
}

# Phonetic system used by "Use fuzzy matching" until the person picks
# another one from its popup menu. Same id the Fuzzy Matching addon's
# phonetic_codes registry uses for Soundex, so a saved choice means the
# same thing whether or not that addon is installed.
_DEFAULT_ALGORITHM: str = "soundex"

# GENERAL plugin registered by the Fuzzy Matching addon, exposing its
# phonetic_codes registry (Soundex, NYSIIS, Match Rating, Metaphone,
# ...). See FuzzyMatchAPI.md in that addon's folder.
_FUZZY_MATCH_API_ID = "Fuzzy Match API"

# A phonetic encoder takes one word and returns the set of codes it
# encodes to (a set, since some systems give more than one code).
Encoder = Callable[[str], set[str]]

# Cached result of _load_phonetic_systems().
PhoneticSystems = tuple[dict[str, Encoder], dict[str, str], dict[str, str]]
_PHONETIC_SYSTEMS: PhoneticSystems | None = None


def _soundex_codes(word: str) -> set[str]:
    """
    Encode one word with Gramps' own built-in Soundex.

    :param word: The word to encode.
    :returns: A one-element set holding its Soundex code.
    """
    return {soundex(word)}


def _load_phonetic_systems() -> PhoneticSystems:
    """
    Return the phonetic systems offered in the "Use fuzzy matching" menu.

    Reuses the Fuzzy Matching addon's own phonetic_codes registry when
    that addon is installed and enabled, reached through its "Fuzzy
    Match API" GENERAL plugin (a bare import from here would not work
    reliably -- see FuzzyMatchAPI.md). Without it, only Gramps' built-in
    Soundex is offered, so the gramplet never loses its fuzzy matching.

    :returns: ``(encoders, labels, descriptions)``, each keyed by
        algorithm id, Soundex always first.
    """
    global _PHONETIC_SYSTEMS  # pylint: disable=global-statement
    if _PHONETIC_SYSTEMS is not None:
        return _PHONETIC_SYSTEMS

    encoders: dict[str, Encoder] = {_DEFAULT_ALGORITHM: _soundex_codes}
    labels: dict[str, str] = {_DEFAULT_ALGORITHM: _("Soundex")}
    descriptions: dict[str, str] = {
        _DEFAULT_ALGORITHM: _(
            "Gramps' built-in Soundex. Install the Fuzzy Matching addon "
            "to choose other phonetic systems."
        )
    }

    try:
        pmgr = BasePluginManager.get_instance()
        pdata = pmgr.get_plugin(_FUZZY_MATCH_API_ID)
        module = pmgr.import_plugin(pdata) if pdata is not None else None
        codes = getattr(module, "phonetic_codes", None) if module else None
        if codes is not None:
            encoders = dict(codes.ALGORITHMS)
            labels = dict(codes.ALGORITHM_LABELS)
            descriptions = dict(getattr(codes, "ALGORITHM_DESCRIPTIONS", {}))
    except Exception:  # pylint: disable=broad-exception-caught
        # Optional addon: anything going wrong here just means "only
        # Soundex", never a gramplet that fails to load.
        LOG.exception("Fuzzy Match API unavailable; offering Soundex only.")

    _PHONETIC_SYSTEMS = (encoders, labels, descriptions)
    return _PHONETIC_SYSTEMS


# Cached ConfigManager, set on first use by _get_config_manager().
_CONFIG_MANAGER: ConfigManager | None = None


def _get_config_manager() -> ConfigManager:
    """
    Return this addon's own :class:`ConfigManager`, registering it once.

    Uses Gramps' own configuration-management feature
    (``gramps.gen.config.config.register_manager``) rather than a
    hand-rolled file reader/writer, so settings are stored the same way
    every other Gramps addon's own settings are. Passing this module's
    own directory plus :data:`_CONFIG_MANAGER_NAME` (no ``.ini`` suffix
    -- Gramps adds that) as the manager name places the resulting
    ``FlatFilter.ini`` alongside ``FlatFilter.py``,
    regardless of ``register_manager``'s own path-resolution defaults.

    The file also stores this addon's plugin id and a schema version
    under ``[meta]``. Both are registered with a default that can never
    match a real saved value (an empty string), so they are always
    written out rather than omitted when they happen to equal their
    default -- see the equivalent comment in Kaj Mikkelsen's LocalTerm
    gramplet, which this pattern is taken from. If either does not
    match what this revision of the code expects, every saved setting
    is reset to its default rather than risking a misinterpreted value
    from an incompatible future revision.

    :returns: The (possibly already-registered) ``ConfigManager``, with
        every Include: checkbox key registered and loaded from disk.
    """
    global _CONFIG_MANAGER  # pylint: disable=global-statement
    if _CONFIG_MANAGER is not None:
        return _CONFIG_MANAGER

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(plugin_dir, _CONFIG_MANAGER_NAME)
    manager = configman.register_manager(config_path)

    manager.register("meta.plugin_id", "")
    manager.register("meta.schema_version", "")
    for key, default in _PERSONAL_DEFAULTS.items():
        manager.register(f"personal.{key}", default)
    for key, default in _SURNAME_DEFAULTS.items():
        manager.register(f"surname.{key}", default)
    for key, default in _MATCHING_DEFAULTS.items():
        manager.register(f"matching.{key}", default)
    manager.register("matching.algorithm", _DEFAULT_ALGORITHM)
    manager.load()

    if (
        manager.get("meta.plugin_id") != _PLUGIN_ID
        or manager.get("meta.schema_version") != _CONFIG_SCHEMA_VERSION
    ):
        LOG.info(
            "Flat Filter settings are missing or from an "
            "incompatible version; resetting to defaults."
        )
        manager.reset()
        manager.set("meta.plugin_id", _PLUGIN_ID)
        manager.set("meta.schema_version", _CONFIG_SCHEMA_VERSION)
        manager.save()

    _CONFIG_MANAGER = manager
    return _CONFIG_MANAGER


def _load_checkbox_settings() -> dict[str, dict[str, bool]]:
    """
    Load saved checkbox states via the Gramps config manager.

    :returns: ``{"personal": {...}, "surname": {...}, "matching": {...}}``,
        with every key from :data:`_PERSONAL_DEFAULTS` /
        :data:`_SURNAME_DEFAULTS` / :data:`_MATCHING_DEFAULTS` present --
        each already resolved by ``ConfigManager.get()`` to either its
        saved value or its registered default.
    """
    manager = _get_config_manager()
    personal = {key: manager.get(f"personal.{key}") for key in _PERSONAL_DEFAULTS}
    surname = {key: manager.get(f"surname.{key}") for key in _SURNAME_DEFAULTS}
    matching = {key: manager.get(f"matching.{key}") for key in _MATCHING_DEFAULTS}
    return {"personal": personal, "surname": surname, "matching": matching}


def _load_algorithm_setting() -> str:
    """
    Return the saved phonetic system id (Soundex if never changed).

    :returns: An algorithm id, which may not be installed any more --
        the caller falls back to Soundex in that case.
    """
    return _get_config_manager().get("matching.algorithm")


def _save_algorithm_setting(algorithm_id: str) -> None:
    """
    Remember the phonetic system chosen in the "Use fuzzy matching" menu.

    Saved immediately on every change, unlike the checkboxes (which
    wait for "Save settings"), so the choice is simply remembered.
    Only this one key changes; every other key keeps its last saved
    value, since the manager holds saved state, not on-screen state.

    :param algorithm_id: The chosen algorithm id.
    """
    manager = _get_config_manager()
    manager.set("matching.algorithm", algorithm_id)
    try:
        manager.save()
    except OSError:
        LOG.exception("Could not save Flat Filter phonetic system choice.")


def _save_checkbox_settings(
    personal_checks: dict[str, Gtk.CheckButton],
    surname_checks: dict[str, Gtk.CheckButton],
    matching_checks: dict[str, Gtk.CheckButton],
) -> bool:
    """
    Save the current checkbox states via the Gramps config manager.

    :param personal_checks: The Person row's given-name checkboxes.
    :param surname_checks: The Person row's surname checkboxes.
    :param matching_checks: The "Use pattern matching (Regular
        expressions)" / "Use fuzzy matching" checkboxes, keyed
        ``"regex"`` / ``"fuzzy"``.
    :returns: ``True`` if the settings were written successfully,
        ``False`` if the file could not be written (e.g. a read-only
        install folder).
    """
    manager = _get_config_manager()
    for key, checkbox in personal_checks.items():
        manager.set(f"personal.{key}", checkbox.get_active())
    for key, checkbox in surname_checks.items():
        manager.set(f"surname.{key}", checkbox.get_active())
    for key, checkbox in matching_checks.items():
        manager.set(f"matching.{key}", checkbox.get_active())
    try:
        manager.save()
    except OSError:
        LOG.exception("Could not save Flat Filter settings.")
        return False
    return True


class _RegExpNameList(Rule):
    """Rule that checks for full or partial name matches, using a
    substring, a regular expression, or a phonetic code."""

    labels = [_("Text:")]
    name = _("People with a name matching <text>")
    description = _(
        "Matches people's names containing a substring, matching a "
        "regular expression, or matching a phonetic code"
    )
    category = _("General filters")
    allow_regex = True

    def __init__(
        self,
        arg: list[str],
        use_regex: bool = False,
        use_case: bool = False,
        encoder: Encoder | None = None,
        include_alternates: bool = True,
    ) -> None:
        """
        Create the rule.

        :param arg: The rule arguments (the text to search for).
        :param use_regex: Whether ``arg`` should be treated as a
            regular expression.
        :param use_case: Whether matching should be case sensitive.
        :param encoder: Phonetic encoder to match ``arg`` with instead
            of substring or regular-expression matching, or ``None`` for
            no phonetic matching. Mutually exclusive with ``use_regex``.
        :param include_alternates: Whether a person's alternate names
            should be tested in addition to their primary name.
        """
        super().__init__(arg, use_regex, use_case)
        self.encoder = encoder
        self.include_alternates = include_alternates
        self.target_codes: set[str] = set()

    def prepare(self, db, user) -> None:
        """
        Prepare the rule. Pre-compute the phonetic codes once, if needed.

        :param db: The database the filter will run against.
        :param user: The user object used for progress reporting.
        """
        self.target_codes = set()
        if self.encoder is not None and self.list[0]:
            for word in self.list[0].split():
                self.target_codes |= self.encoder(word)

    def field_list(self, name):
        raise NotImplementedError

    def _is_match(self, field: str) -> bool:
        """
        Return whether a single field matches the search criteria.

        :param field: The name field to test.
        :returns: ``True`` if ``field`` matches, ``False`` otherwise.
        """
        if self.encoder is not None:
            # Each word is encoded on its own, so "John" finds
            # "John Henry" -- the same rule the Fuzzy Matching addon's
            # own phonetic filter rules follow.
            if not self.target_codes:
                return False
            return any(
                self.encoder(word) & self.target_codes for word in str(field).split()
            )
        return self.match_substring(0, field)

    def apply_to_one(self, db, person) -> bool:
        """
        Test a single person against this rule.

        Named ``apply_to_one`` to match Gramps 6.0, which renamed
        ``Rule.apply`` (see
        https://github.com/gramps-project/gramps/pull/2055). ``apply``
        below is kept as a thin alias so this rule also still works
        correctly under Gramps 5.2, which calls the pre-rename name --
        both names always run the same logic, so it makes no difference
        which one a given Gramps version's filter engine calls.
        """
        names = [person.primary_name]
        if self.include_alternates:
            names += person.alternate_names
        for name in names:
            for field in self.field_list(name):
                if self._is_match(field):
                    return True
        return False

    def apply(self, db, person) -> bool:
        """
        Gramps 5.2 compatibility alias for :meth:`apply_to_one`.

        :param db: The database the filter is running against.
        :param person: The person to test.
        :returns: Whatever :meth:`apply_to_one` returns.
        """
        return self.apply_to_one(db, person)


# Personal-name fields that the "Include:" checkboxes on the Person row
# can individually enable or disable.
PERSONAL_FIELDS: tuple[str, ...] = ("title", "given", "call", "nick")

# Surname-side fields that a second "Include:" row on the Person row's
# dedicated Surname line can individually enable or disable.
SURNAME_FIELDS: tuple[str, ...] = ("prefix", "surname", "suffix", "clan")


class RegExpPersonal(_RegExpNameList):
    """
    Match a person's given-name-side name fields.

    :param personal_fields: Which of :data:`PERSONAL_FIELDS` to test.
        ``None`` (the default) tests all of them, preserving the
        historical behaviour for every row except the sidebar's own
        "Person" row, which passes an explicit, checkbox-derived subset.
    """

    def __init__(
        self,
        arg: list[str],
        use_regex: bool = False,
        use_case: bool = False,
        encoder: Encoder | None = None,
        include_alternates: bool = True,
        personal_fields: frozenset[str] | None = None,
    ) -> None:
        super().__init__(arg, use_regex, use_case, encoder, include_alternates)
        self.personal_fields = (
            frozenset(PERSONAL_FIELDS) if personal_fields is None else personal_fields
        )

    def field_list(self, name):
        field_map = {
            "title": name.title,
            "given": name.first_name,
            "call": name.call,
            "nick": name.nick,
        }
        return [field_map[key] for key in self.personal_fields]


class RegExpFamily(_RegExpNameList):
    """
    Match a person's surname-side name fields.

    :param surname_fields: Which of :data:`SURNAME_FIELDS` to test.
        ``None`` (the default) tests all of them, preserving the
        historical behaviour for every row except the sidebar's own
        "Person" row, which passes an explicit, checkbox-derived subset.
    """

    def __init__(
        self,
        arg: list[str],
        use_regex: bool = False,
        use_case: bool = False,
        encoder: Encoder | None = None,
        include_alternates: bool = True,
        surname_fields: frozenset[str] | None = None,
    ) -> None:
        super().__init__(arg, use_regex, use_case, encoder, include_alternates)
        self.surname_fields = (
            frozenset(SURNAME_FIELDS) if surname_fields is None else surname_fields
        )

    def field_list(self, name):
        primary_surname = name.get_primary_surname()
        field_map = {
            "prefix": primary_surname.get_prefix(),
            "surname": primary_surname.get_surname(),
            "suffix": name.suffix,
            "clan": name.famnick,
        }
        return [field_map[key] for key in self.surname_fields]


class _HasNamedRelation(Rule):
    labels = [_("Filter name:")]
    name = _("Children of name match")
    category = _("Family filters")
    description = _("Matches children of anybody with a given name")

    def __init__(
        self,
        arg: list[str],
        name_matcher: type,
        use_regex: bool = False,
        encoder: Encoder | None = None,
        include_alternates: bool = True,
        personal_fields: frozenset[str] | None = None,
        surname_fields: frozenset[str] | None = None,
    ) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
        """
        Create the rule.

        :param arg: The rule arguments (the text to search for).
        :param name_matcher: The ``_RegExpNameList`` subclass used to
            test names for a match.
        :param use_regex: Whether ``arg`` should be treated as a
            regular expression.
        :param encoder: Phonetic encoder, or ``None``; forwarded to
            ``name_matcher``. Mutually exclusive with ``use_regex``.
        :param include_alternates: Whether alternate names should also
            be tested, forwarded to ``name_matcher``.
        :param personal_fields: Forwarded to ``name_matcher`` when it is
            :class:`RegExpPersonal`; ignored otherwise.
        :param surname_fields: Forwarded to ``name_matcher`` when it is
            :class:`RegExpFamily`; ignored otherwise.
        """
        super().__init__(arg, use_regex)
        matcher_kwargs: dict[str, object] = {
            "encoder": encoder,
            "include_alternates": include_alternates,
        }
        if name_matcher is RegExpPersonal and personal_fields is not None:
            matcher_kwargs["personal_fields"] = personal_fields
        if name_matcher is RegExpFamily and surname_fields is not None:
            matcher_kwargs["surname_fields"] = surname_fields
        self.name_matcher = name_matcher(arg, use_regex, **matcher_kwargs)

    def prepare(self, db, user):
        self.name_matcher.requestprepare(db, user)

    def reset(self):
        self.name_matcher.requestreset()

    def get_rel_list(self, db, person):
        raise NotImplementedError

    def get_spouse_list(self, db, person):
        handles = []
        for fam_id in person.family_list:
            fam = db.get_family_from_handle(fam_id)
            if fam:
                for spouse_id in [fam.father_handle, fam.mother_handle]:
                    if not spouse_id:
                        continue
                    if spouse_id == person.handle:
                        continue
                    handles.append(spouse_id)
        return handles

    def apply_to_one(self, db, person) -> bool:
        """
        Test whether any of this person's relevant relatives match.

        Named ``apply_to_one`` to match Gramps 6.0 (see the equivalent
        note on ``_RegExpNameList.apply_to_one``); ``apply`` below is
        the Gramps 5.2 compatibility alias.

        Each candidate relative is fetched with the standard
        ``db.get_person_from_handle()`` rather than
        ``db.get_raw_person_data()``. The latter looked like a
        promising Gramps 6.0 performance win (a real 6.0 rewrite of
        this same gramplet's rules used it), but it returns a plain
        pickled tuple on Gramps 5.2 -- and possibly other backends --
        with no attribute access at all, rather than a usable object;
        confirmed by testing directly against real Gramps 5.2 and 6.0
        packages, where it raised exactly the
        ``AttributeError: 'tuple' object has no attribute
        'primary_name'`` seen in the field. Since ``get_person_from_
        handle()`` is stable and consistent on both versions, this
        file uses that everywhere rather than risk further
        version/backend-specific surprises for a speed-up that cannot
        be relied on.
        """
        for rel_id in self.get_rel_list(db, person):
            if rel_id:
                rel = db.get_person_from_handle(rel_id)
                if self.name_matcher.apply_to_one(db, rel):
                    return True
        return False

    def apply(self, db, person) -> bool:
        """
        Gramps 5.2 compatibility alias for :meth:`apply_to_one`.

        :param db: The database the filter is running against.
        :param person: The person to test.
        :returns: Whatever :meth:`apply_to_one` returns.
        """
        return self.apply_to_one(db, person)


class _HasNamedParent(_HasNamedRelation):
    def get_parent_families(self, db, person):
        families = []
        for fam_id in person.parent_family_list:
            fam = db.get_family_from_handle(fam_id)
            if fam:
                families.append(fam)
        return families


class HasNamedFather(_HasNamedParent):
    def get_rel_list(self, db, person):
        return map(
            lambda fam: fam.get_father_handle(), self.get_parent_families(db, person)
        )


class HasNamedMother(_HasNamedParent):
    def get_rel_list(self, db, person):
        return map(
            lambda fam: fam.get_mother_handle(), self.get_parent_families(db, person)
        )


class IsSiblingofNamedSibling(_HasNamedRelation):
    def get_rel_list(self, db, person):
        handles = []
        fam_id = person.get_main_parents_family_handle()  # or all families, per above?
        fam = db.get_family_from_handle(fam_id) if fam_id else None
        if fam:
            for child_ref in fam.get_child_ref_list():
                if child_ref and child_ref.ref != person.handle:
                    handles.append(child_ref.ref)
        return handles


class HasNamedChild(_HasNamedRelation):
    def get_rel_list(self, db, person):
        handles = []
        for fam_id in person.family_list:
            fam = db.get_family_from_handle(fam_id)
            if fam:
                for child_ref in fam.get_child_ref_list():
                    if child_ref:
                        handles.append(child_ref.ref)
        return handles


class HasNamedSpouse(_HasNamedRelation):
    def get_rel_list(self, db, person):
        return self.get_spouse_list(db, person)


class HasName(_HasNamedRelation):
    def get_rel_list(self, db, person):
        if person.gender == Person.FEMALE and isinstance(
            self.name_matcher, RegExpFamily
        ):
            # for female surnames, we want to trawl the spouses surnames
            handles = self.get_spouse_list(db, person)
            handles.append(person.handle)
            return handles
        return [person.handle]


def extract_text(entry_widget):
    """
    Extract the text from the entry widget, strips off any extra spaces.
    """
    return str(entry_widget.get_text().strip())


def trim_entry(entry: Gtk.Entry) -> None:
    """
    Remove leading and trailing white space from an entry, in place.

    Matching already ignores that white space (see :func:`extract_text`);
    trimming the entry itself shows the person exactly what is searched.
    The text is only replaced when it changes, so the cursor is not
    disturbed in an entry that has nothing to trim.

    :param entry: The text entry to trim.
    """
    text = entry.get_text()
    trimmed = text.strip()
    if trimmed != text:
        entry.set_text(trimmed)


# leverage to split the name into fore and aft
class SearchableNamePair:
    """
    A given-name/surname search row in the sidebar.

    :param label: The row's display label (e.g. ``"Person"``).
    :param rule_class: The ``_HasNamedRelation`` subclass used to locate
        the relative(s) whose name is tested.
    :param personal_checkboxes: Optional per-field "Include:" checkboxes
        (see :data:`PERSONAL_FIELDS`, plus an ``"alternatives"`` entry)
        that limit this row's given-name search. Only the sidebar's
        "Person" row is given these; every other row searches all
        fields and alternate names, as before.
    :param surname_checkboxes: Optional per-field "Include:" checkboxes
        (see :data:`SURNAME_FIELDS`, plus an ``"alternatives"`` entry)
        that limit this row's surname search. Only the sidebar's
        "Person" row is given these.
    """

    def __init__(
        self,
        label: str,
        rule_class: type,
        personal_checkboxes: dict[str, Gtk.CheckButton] | None = None,
        surname_checkboxes: dict[str, Gtk.CheckButton] | None = None,
    ) -> None:
        self.widget_personal = widgets.BasicEntry()
        self.widget_personal.set_placeholder_text(_("given"))
        self.widget_family = widgets.BasicEntry()
        self.widget_family.set_placeholder_text(_("surname"))
        self.label = label
        self.rule_class = rule_class
        self.personal_checkboxes = personal_checkboxes
        self.surname_checkboxes = surname_checkboxes

    def place(self, sidebar) -> None:
        """
        Place this row's label, given-name entry, and surname entry.

        Used for every row except the sidebar's "Person" row, which is
        instead laid out across two lines by
        :meth:`place_personal_only` and :meth:`place_surname_only` (see
        ``PersonSidebarFilter._place_person_rows``).

        :param sidebar: The ``PersonSidebarFilter`` supplying the grid.
        """
        sidebar.grid.attach(widgets.BasicLabel(self.label), 1, sidebar.position, 1, 1)

        self.widget_personal.set_hexpand(True)
        sidebar.grid.attach(self.widget_personal, 2, sidebar.position, 1, 1)
        self.widget_personal.connect("key-press-event", sidebar.key_press)

        self.widget_family.set_hexpand(True)
        sidebar.grid.attach(self.widget_family, 3, sidebar.position, 1, 1)
        self.widget_family.connect("key-press-event", sidebar.key_press)
        sidebar.position += 1

    def place_personal_only(self, sidebar) -> None:
        """
        Place only this row's label and given-name entry.

        The entry spans both the given-name and surname columns (2-3)
        since this row has no second entry beside it, giving it the
        same full width used by the two entries together on every
        other row.

        :param sidebar: The ``PersonSidebarFilter`` supplying the grid.
        """
        sidebar.grid.attach(widgets.BasicLabel(self.label), 1, sidebar.position, 1, 1)

        self.widget_personal.set_hexpand(True)
        sidebar.grid.attach(self.widget_personal, 2, sidebar.position, 2, 1)
        self.widget_personal.connect("key-press-event", sidebar.key_press)
        sidebar.position += 1

    def place_surname_only(self, sidebar, label: str) -> None:
        """
        Place a standalone label and this row's surname entry.

        The entry starts at the same grid column (2) as the given-name
        entry on the line above it, so both of the Person row's two
        entries share the same left edge -- rather than the column (3)
        used by every other row's surname entry -- and spans both
        columns (2-3) for the same full width as
        :meth:`place_personal_only`.

        :param sidebar: The ``PersonSidebarFilter`` supplying the grid.
        :param label: Label text for this dedicated line (e.g.
            ``_("Surname")``), distinct from ``self.label``.
        """
        sidebar.grid.attach(widgets.BasicLabel(label), 1, sidebar.position, 1, 1)

        self.widget_family.set_hexpand(True)
        sidebar.grid.attach(self.widget_family, 2, sidebar.position, 2, 1)
        self.widget_family.connect("key-press-event", sidebar.key_press)
        sidebar.position += 1

    def clear(self):
        self.widget_personal.set_text("")
        self.widget_family.set_text("")

    def _personal_fields(self) -> frozenset[str] | None:
        """
        Return which personal-name fields to search, or ``None`` for all.

        :returns: A field-name subset of :data:`PERSONAL_FIELDS` for the
            "Person" row (built from its checkboxes), or ``None`` for
            every other row, which searches all fields as before.
        """
        if self.personal_checkboxes is None:
            return None
        return frozenset(
            key for key in PERSONAL_FIELDS if self.personal_checkboxes[key].get_active()
        )

    def _surname_fields(self) -> frozenset[str] | None:
        """
        Return which surname-side fields to search, or ``None`` for all.

        :returns: A field-name subset of :data:`SURNAME_FIELDS` for the
            "Person" row (built from its checkboxes), or ``None`` for
            every other row, which searches all fields as before.
        """
        if self.surname_checkboxes is None:
            return None
        return frozenset(
            key for key in SURNAME_FIELDS if self.surname_checkboxes[key].get_active()
        )

    @staticmethod
    def _checkbox_active(
        checkboxes: dict[str, Gtk.CheckButton] | None, key: str
    ) -> bool:
        """
        Return a named checkbox's state, or ``True`` if there is none.

        :param checkboxes: A field-checkbox dict (personal or surname),
            or ``None`` for rows other than "Person" that have none.
        :param key: The checkbox to read (e.g. ``"alternatives"``).
        :returns: The checkbox's active state, or ``True`` when
            ``checkboxes`` is ``None`` -- preserving the historical
            "search everything" behaviour for every row except Person.
        """
        if checkboxes is None:
            return True
        return checkboxes[key].get_active()

    def _add_to_filter(
        self,
        generic_filter: GenericFilter,
        regex: bool,
        encoder: Encoder | None,
        widget: Gtk.Entry,
        search_class: type,
    ) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments
        v = extract_text(widget)
        if not v:
            return
        kwargs: dict[str, object] = {"use_regex": regex, "encoder": encoder}
        if search_class is RegExpPersonal:
            kwargs["personal_fields"] = self._personal_fields()
            kwargs["include_alternates"] = self._checkbox_active(
                self.personal_checkboxes, "alternatives"
            )
        elif search_class is RegExpFamily:
            kwargs["surname_fields"] = self._surname_fields()
            kwargs["include_alternates"] = self._checkbox_active(
                self.surname_checkboxes, "alternatives"
            )
        rule = self.rule_class([v], search_class, **kwargs)
        generic_filter.add_rule(rule)

    def add_to_filter(
        self,
        generic_filter: GenericFilter,
        regex: bool,
        encoder: Encoder | None,
    ) -> None:
        """
        Add the rules for this name pair's non-empty fields to the filter.

        :param generic_filter: The filter to add the rules to.
        :param regex: Whether the entered text should be treated as a
            regular expression.
        :param encoder: Phonetic encoder to match the entered text
            with, or ``None``. Mutually exclusive with ``regex``.
        """
        self._add_to_filter(
            generic_filter, regex, encoder, self.widget_personal, RegExpPersonal
        )
        self._add_to_filter(
            generic_filter, regex, encoder, self.widget_family, RegExpFamily
        )


# -------------------------------------------------------------------------
#
# PersonSidebarFilter class
#
# -------------------------------------------------------------------------
class PersonSidebarFilter(
    SidebarFilter
):  # pylint: disable=too-many-instance-attributes

    def __init__(self, dbstate, uistate, clicked):
        self.clicked_func = clicked
        self.sensitive_regex = False

        # Per-field "Include:" checkboxes that limit the "Person" row's
        # own search only; every other row keeps searching all fields.
        self.person_field_checks: dict[str, Gtk.CheckButton] = {
            "title": Gtk.CheckButton(label=_("Title")),
            "given": Gtk.CheckButton(label=_("Given")),
            "call": Gtk.CheckButton(label=_("Call")),
            "nick": Gtk.CheckButton(label=_("Nick")),
            "alternatives": Gtk.CheckButton(label=_("Alternatives")),
        }

        # Per-field "Include:" checkboxes for the Person row's separate
        # Surname line, below the personal-field checkboxes.
        self.person_surname_checks: dict[str, Gtk.CheckButton] = {
            "prefix": Gtk.CheckButton(label=_("Prefix")),
            "surname": Gtk.CheckButton(label=_("Surname")),
            "suffix": Gtk.CheckButton(label=_("Suffix")),
            "clan": Gtk.CheckButton(label=_("Clan")),
            "alternatives": Gtk.CheckButton(label=_("Alternatives")),
        }

        self.filter_regex = Gtk.CheckButton(
            label=_("Use pattern matching (Regular expressions)")
        )
        self.filter_fuzzy = Gtk.CheckButton(label=_("Use fuzzy matching"))
        self.filter_regex.connect("toggled", self.cb_regex_toggled)
        self.filter_fuzzy.connect("toggled", self.cb_fuzzy_toggled)
        self.matching_checks: dict[str, Gtk.CheckButton] = {
            "regex": self.filter_regex,
            "fuzzy": self.filter_fuzzy,
        }

        # Popup menu choosing the phonetic system "Use fuzzy matching"
        # uses, in place of the old fixed "(SoundEx)" label text.
        self.encoders, labels, self.algorithm_descriptions = _load_phonetic_systems()
        self.algorithm_combo = Gtk.ComboBoxText()
        for algorithm_id, label in labels.items():
            self.algorithm_combo.append(algorithm_id, label)
        self._set_algorithm(_load_algorithm_setting())
        self.algorithm_handler = self.algorithm_combo.connect(
            "changed", self.cb_algorithm_changed
        )

        # Load this addon's own saved checkbox settings via the Gramps
        # config manager, falling back to the hardcoded defaults if
        # nothing has been saved yet.
        self._apply_checkbox_settings(_load_checkbox_settings())

        self.names = [
            SearchableNamePair(
                _("Person"),
                HasName,
                personal_checkboxes=self.person_field_checks,
                surname_checkboxes=self.person_surname_checks,
            ),
            SearchableNamePair(_("Father"), HasNamedFather),
            SearchableNamePair(_("Mother"), HasNamedMother),
            SearchableNamePair(_("Spouse"), HasNamedSpouse),
            SearchableNamePair(_("Sibling 1"), IsSiblingofNamedSibling),
            SearchableNamePair(_("Sibling 2"), IsSiblingofNamedSibling),
            SearchableNamePair(_("Child 1"), HasNamedChild),
            SearchableNamePair(_("Child 2"), HasNamedChild),
        ]
        self.filter_alive = widgets.DateEntry(uistate, [])

        # Trim white space when focus leaves an entry; get_filter() trims
        # them all too, which covers Enter and the Find button.
        self.text_entries: list[Gtk.Entry] = [
            entry
            for pair in self.names
            for entry in (pair.widget_personal, pair.widget_family)
        ]
        self.text_entries.append(self.filter_alive.entry)
        for entry in self.text_entries:
            entry.connect("focus-out-event", self.cb_trim_entry)

        SidebarFilter.__init__(self, dbstate, uistate, "Person")

    def cb_regex_toggled(self, obj: Gtk.CheckButton) -> None:
        """
        Keep regex and fuzzy matching mutually exclusive.

        :param obj: The regular-expressions check button.
        """
        if obj.get_active():
            self.filter_fuzzy.set_active(False)

    def cb_fuzzy_toggled(self, obj: Gtk.CheckButton) -> None:
        """
        Keep regex and fuzzy matching mutually exclusive.

        :param obj: The fuzzy-matching check button.
        """
        if obj.get_active():
            self.filter_regex.set_active(False)

    def cb_algorithm_changed(self, combo: Gtk.ComboBoxText) -> None:
        """
        Remember the newly chosen phonetic system and update its tooltip.

        :param combo: The phonetic system popup menu.
        """
        algorithm_id = combo.get_active_id()
        self._update_algorithm_tooltip()
        if algorithm_id:
            _save_algorithm_setting(algorithm_id)

    def _set_algorithm(self, algorithm_id: str) -> None:
        """
        Select a phonetic system in the popup menu, falling back to Soundex.

        A saved choice can name a system that is no longer installed
        (e.g. the Fuzzy Matching addon was removed); Soundex is shown
        then, but the saved choice is left alone until the person picks
        something else.

        :param algorithm_id: The algorithm id to select.
        """
        if not self.algorithm_combo.set_active_id(algorithm_id):
            self.algorithm_combo.set_active_id(_DEFAULT_ALGORITHM)
        self._update_algorithm_tooltip()

    def _update_algorithm_tooltip(self) -> None:
        """
        Show the selected phonetic system's description as its tooltip.
        """
        description = self.algorithm_descriptions.get(
            self.algorithm_combo.get_active_id() or "", ""
        )
        self.algorithm_combo.set_tooltip_text(description or None)

    def _current_encoder(self) -> Encoder:
        """
        Return the encoder for the phonetic system selected in the menu.

        :returns: The selected system's encoder, or Soundex's.
        """
        algorithm_id = self.algorithm_combo.get_active_id() or _DEFAULT_ALGORITHM
        return self.encoders.get(algorithm_id, _soundex_codes)

    def create_widget(self):
        exdate1 = Date()
        exdate2 = Date()
        exdate1.set(
            Date.QUAL_NONE,
            Date.MOD_RANGE,
            Date.CAL_GREGORIAN,
            (0, 0, 1800, False, 0, 0, 1900, False),
        )
        exdate2.set(
            Date.QUAL_NONE, Date.MOD_BEFORE, Date.CAL_GREGORIAN, (0, 0, 1850, False)
        )

        msg1 = displayer.display(exdate1)
        msg2 = displayer.display(exdate2)

        for index, w in enumerate(self.names):
            if index == 0:
                # The "Person" row is laid out specially: given-name and
                # surname get their own lines, each followed by its own
                # "Include:" checkboxes.
                self._place_person_rows(w)
            else:
                w.place(self)

        self.add_text_entry(
            _("Probably Alive"),
            self.filter_alive,
            _("example: '%(msg1)s' or '%(msg2)s'") % {"msg1": msg1, "msg2": msg2},
        )
        # Place both matching-option checkboxes in their own row, but at
        # the same grid column and span so their left edges line up
        # exactly (no left/right label column, hence no pixel offset).
        self.grid.attach(self.filter_regex, 1, self.position, 3, 1)
        self.position += 1
        fuzzy_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        fuzzy_row.pack_start(self.filter_fuzzy, False, False, 0)
        fuzzy_row.pack_start(self.algorithm_combo, False, False, 0)
        self.grid.attach(fuzzy_row, 1, self.position, 3, 1)
        self.position += 1

        # Right-clicking anywhere in the grid (e.g. blank space between
        # rows) offers to save the current "Include:" checkbox states.
        self.grid.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.grid.connect("button-press-event", self.cb_context_menu)

    def cb_context_menu(self, _widget: Gtk.Widget, event: Gdk.EventButton) -> bool:
        """
        Show a right-click context menu offering to save current settings.

        A click that lands on an interactive child (an entry, a
        checkbox, the Find/Reset buttons) is handled by that child
        directly and never reaches this handler; this only fires for
        clicks on blank grid space.

        :param _widget: The grid the click occurred in (unused).
        :param event: The GDK button event.
        :returns: ``True`` for a right-click, once the menu has been
            shown, so the event is not processed further; ``False``
            for any other button, letting it propagate normally.
        """
        if event.button != 3:
            return False
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label=_("Save settings"))
        item.connect("activate", lambda _item: self.save_settings())
        menu.append(item)
        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def save_settings(self) -> bool:
        """
        Persist the current checkbox states to FlatFilter.ini.

        Saves the Person row's "Include:" checkboxes and the "Use
        pattern matching (Regular expressions)" / "Use fuzzy matching"
        checkboxes. The phonetic system choice is saved on its own,
        the moment it changes (see :meth:`cb_algorithm_changed`).

        :returns: ``True`` if the settings were written successfully.
        """
        saved = _save_checkbox_settings(
            self.person_field_checks, self.person_surname_checks, self.matching_checks
        )
        if not saved:
            LOG.warning("Could not save Flat Filter settings.")
        return saved

    def _apply_checkbox_settings(self, settings: dict[str, dict[str, bool]]) -> None:
        """
        Apply loaded (or default) states to the checkboxes.

        :param settings: A ``{"personal": {...}, "surname": {...},
            "matching": {...}}`` mapping as returned by
            :func:`_load_checkbox_settings`.
        """
        for key, checkbox in self.person_field_checks.items():
            checkbox.set_active(settings["personal"].get(key, _PERSONAL_DEFAULTS[key]))
        for key, checkbox in self.person_surname_checks.items():
            checkbox.set_active(settings["surname"].get(key, _SURNAME_DEFAULTS[key]))
        for key, checkbox in self.matching_checks.items():
            checkbox.set_active(settings["matching"].get(key, _MATCHING_DEFAULTS[key]))

    def _reload_algorithm(self) -> None:
        """
        Re-select the saved phonetic system without re-saving it.

        Blocks the "changed" handler so a fallback to Soundex (saved
        system not installed) does not overwrite the saved choice.
        """
        self.algorithm_combo.handler_block(self.algorithm_handler)
        try:
            self._set_algorithm(_load_algorithm_setting())
        finally:
            self.algorithm_combo.handler_unblock(self.algorithm_handler)

    def _place_person_rows(self, person_pair: SearchableNamePair) -> None:
        """
        Lay out the "Person" row's given-name and surname entries.

        Unlike every other row, the Person row's given-name and surname
        entries are placed on separate lines, each immediately followed
        by its own row of unlabeled "Include:" checkboxes limiting that
        entry's own search -- with a single separator below both,
        showing that all of it belongs only to the Person row.

        :param person_pair: The "Person" entry from ``self.names``.
        """
        person_pair.place_personal_only(self)
        self._add_include_row(self.person_field_checks, start_column=2)

        person_pair.place_surname_only(self, _("Surname"))
        self._add_include_row(self.person_surname_checks, start_column=2)

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.grid.attach(separator, 1, self.position, 3, 1)
        self.position += 1

    def _add_include_row(
        self, checkboxes: dict[str, Gtk.CheckButton], start_column: int
    ) -> None:
        """
        Add an unlabeled row of checkboxes, aligned under a text entry.

        :param checkboxes: The field checkboxes to display, in order.
        :param start_column: The grid column the first checkbox's left
            edge should align with -- the same column used by the text
            entry immediately above this row (2 for the given-name
            entry, 3 for the surname entry). The row is given a
            generous column span so it can grow past the grid's normal
            3 columns without being cramped or wrapping.
        """
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for checkbox in checkboxes.values():
            row.pack_start(checkbox, False, False, 0)
        self.grid.attach(row, start_column, self.position, 5, 1)
        self.position += 1

    def clear(self, obj):
        for w in self.names:
            w.clear()
        self._apply_checkbox_settings(_load_checkbox_settings())
        self._reload_algorithm()
        self.filter_alive.set_text("")

    def cb_trim_entry(self, entry: Gtk.Entry, _event: Gdk.EventFocus) -> bool:
        """
        Trim an entry when keyboard focus leaves it.

        :param entry: The entry losing focus.
        :param _event: The focus-out event (unused).
        :returns: ``False``, so GTK continues its own focus handling.
        """
        trim_entry(entry)
        return False

    def get_filter(self):
        """
        Extracts the text strings from the sidebar, and uses them to build up
        a new filter.

        :returns: The filter, or ``None`` when every field is blank. Like
            the core person sidebar filter, ``None`` makes the view show
            everyone without running a filter at all; a filter with no
            rules would test every person only to match them all.
        """

        # Enter and Find both arrive here, possibly without focus having
        # left the entry being typed in.
        for entry in self.text_entries:
            trim_entry(entry)

        regex = self.filter_regex.get_active()
        encoder = self._current_encoder() if self.filter_fuzzy.get_active() else None

        # build a GenericFilter
        generic_filter = GenericFilter()
        for w in self.names:
            w.add_to_filter(generic_filter, regex, encoder)

        alive = extract_text(self.filter_alive)
        if alive:
            rule = ProbablyAlive([alive])
            generic_filter.add_rule(rule)

        if not generic_filter.get_rules():
            return None
        return generic_filter


# -------------------------------------------------------------------------
#
# Helper for locating the Find/Reset button row
#
# -------------------------------------------------------------------------
def _find_button_row(widget: Gtk.Widget, target_labels: set[str]) -> Gtk.Box | None:
    """
    Find the ``Gtk.Box`` that directly contains a labeled button.

    Walks the widget tree looking for a ``Gtk.Button`` whose label
    (stripped of any mnemonic underscore) case-insensitively matches one
    of ``target_labels``, and returns that button's parent container.
    Used to add the Help button to the same row as ``SidebarFilter``'s
    own Find/Reset buttons without depending on that class's private
    attribute names.

    :param widget: The root widget to search from.
    :param target_labels: Normalised (no underscore, casefolded) button
        labels to match against.
    :returns: The ``Gtk.Box`` containing a matching button, or ``None``
        if no matching button was found.
    """
    if isinstance(widget, Gtk.Button):
        label = widget.get_label()
        if label and label.replace("_", "").strip().casefold() in target_labels:
            parent = widget.get_parent()
            if isinstance(parent, Gtk.Box):
                return parent
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = _find_button_row(child, target_labels)
            if found is not None:
                return found
    return None


# -------------------------------------------------------------------------
#
# Filter class
#
# -------------------------------------------------------------------------
class Filter(Gramplet):
    """
    The base class for all filter gramplets.
    """

    FILTER_CLASS: type[SidebarFilter] | None = None
    PLUGIN_ID: str = ""

    def init(self) -> None:
        """
        Build the sidebar filter widget and attach it to the gramplet.
        """
        self.filter = self.FILTER_CLASS(
            self.dbstate, self.uistate, self.__filter_clicked
        )
        self.widget = self.filter.get_widget()
        self._add_help_button()
        self._tighten_button_rows()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.widget)
        self.widget.show_all()

    def _tighten_button_rows(self) -> None:
        """
        Trim the padding around the Find/Reset and Define filter rows.

        ``SidebarFilter`` gives each of its button rows a 12 px border on
        every side, so the two rows sit inside 48 px of blank space.
        Replace that with small margins: 6 px at the sides, which lines
        the buttons up with the row labels (the grid border is 6 px),
        and 6 px below each row.
        """
        for child in self.widget.get_children():
            if isinstance(child, Gtk.ButtonBox):
                child.set_border_width(0)
                child.set_margin_start(6)
                child.set_margin_end(6)
                child.set_margin_bottom(6)

    def _add_help_button(self) -> None:
        """
        Pack a Help button into the same row as the Find/Reset buttons.

        This is a nice-to-have, not a core feature of the gramplet: if
        the Find/Reset row cannot be located (e.g. a future
        ``SidebarFilter`` redesign), or anything else about adding the
        button goes wrong, the gramplet simply has no Help button rather
        than failing to load at all.
        """
        try:
            target_labels = {
                _("Find").casefold(),
                _("_Find").replace("_", "").casefold(),
                _("Reset").casefold(),
                _("_Reset").replace("_", "").casefold(),
                _("Clear").casefold(),
                _("_Clear").replace("_", "").casefold(),
            }
            button_row = _find_button_row(self.widget, target_labels)
            if button_row is None:
                LOG.warning(
                    "Could not locate the Find/Reset button row; "
                    "no Help button was added."
                )
                return
            add_help_button(button_row, self.uistate, self.PLUGIN_ID)
        except Exception:  # pylint: disable=broad-exception-caught
            LOG.exception("Failed to add the Help button; continuing without it.")

    def __filter_clicked(self):
        """
        Called when the filter apply button is clicked.
        """
        self.gui.view.generic_filter = self.filter.get_filter()
        self.gui.view.build_tree()


# -------------------------------------------------------------------------
#
# FlatFilter class
#
# -------------------------------------------------------------------------
class FlatFilter(Filter):
    """
    A gramplet providing a Person Filter.
    """

    FILTER_CLASS = PersonSidebarFilter
    PLUGIN_ID = _PLUGIN_ID
