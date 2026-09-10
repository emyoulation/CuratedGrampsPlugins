#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025  Phonetic Matching Gramplet contributors
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

"""
Phonetic algorithm registry used by the Fuzzy Matching Gramplet.

This module deliberately has no dependency on Gtk or on the Gramps
database layer, so the encoding logic can be unit tested in isolation
and reused independently of the GUI.

Every encoding system other than Soundex is discovered through
Gramps' own plugin registry rather than a custom folder scan: each one
ships as an ordinary ``RULE``-type Gramps plugin (a ``<name>.py`` +
``<name>.gpr.py`` pair, e.g. ``nysiisrule.py``/``nysiisrule.gpr.py``),
because a "Define filter" action for that algorithm needs a real,
registered Person filter rule anyway - Gramps has no mechanism to
auto-discover *those* by scanning a folder, so every encoding system
needs an explicit ``register(RULE, ...)`` call regardless. Once that
registration exists, this module asks
:class:`gramps.gen.plug.PluginRegister` for every ``RULE``-type plugin
it already knows about, and keeps the ones whose
:attr:`PluginData.id` starts with :data:`_ENCODER_ID_PREFIX` - a
plugin's own choice, made when it registers, not anything this module
infers from where the plugin happens to live on disk.

That choice matters. An earlier version filtered by
:attr:`PluginData.fpath` (the directory a ``.gpr.py`` was found in)
matching this addon's own folder instead. That only works as long as
every encoding system's rule ships bundled inside this same addon
package - it would silently stop finding a rule the moment someone
distributed a phonetic-encoding rule as its own, independently
installed and independently updated Gramps addon, since it would then
live in a different folder by design, not by accident. The ``id``
prefix has no such assumption: it is read directly from each plugin's
own registration metadata, before anything is imported, and says
nothing about where that plugin's files live. Any Gramps addon,
bundled with this gramplet or not, can opt into showing up in this
gramplet's Encoding system list purely by choosing a
:data:`_ENCODER_ID_PREFIX`-prefixed ``id`` when it registers and
satisfying the small module contract below - see
``nysiisrule.py``/``matchratingrule.py`` for the contract a new
encoding system's module must satisfy, and ``FuzzyDev.md`` for the
full walkthrough.

Soundex is the one exception, hardcoded below rather than discovered:
it already has a built-in Gramps rule (``HasSoundexName``), registered
by Gramps under an ``id`` this addon does not control and could not
prefix, and re-registering a duplicate "HasSoundexName"-equivalent
rule purely to give it a matching id would show up as a second,
redundant entry in the standard Filter Editor's "Add Rule" dialog.
Soundex is also always available regardless of what else is
installed, which a hardcoded entry reflects more honestly than
routing it through the same "might not be there" discovery path as
everything else.

Discovering a rule module is not quite enough on its own, though - see
:func:`_make_rule_findable_via_import` for the second half of the
picture: Gramps' own saved-filter persistence needs the rule class to
also be reachable as ``gramps.gen.filters.rules.<namespace>.<ClassName>``,
independent of anything this module does.

See ``nysiisrule.py``/``matchratingrule.py`` for the contract a new
encoding system's module must satisfy, and for the reasoning behind an
earlier Daitch-Mokotoff Soundex attempt being dropped rather than
shipped after it failed validation against the standard reference
vectors (e.g. "Peters" should encode to {"739400", "734000"}).
"""

# Deferred annotation evaluation (PEP 563), required for Python 3.8/3.9
# compatibility: this module's type hints use `list[X]`, `dict[K, V]`,
# `X | None`, etc. (PEP 585/604 syntax), which those Python versions
# cannot evaluate at runtime even though they parse it fine - Gramps
# 5.2's own official minimum is Python 3.8, which predates both PEPs
# (585 needs 3.9+, 604 needs 3.10+). This import makes every
# annotation in this file a deferred string, never evaluated at
# runtime at all, restoring compatibility with the full (5.2.0,
# 6.2.0) Gramps range this addon's own .gpr.py declares, without
# giving up the modern annotation syntax itself.
from __future__ import annotations

# ------------------------
# Python modules
# ------------------------
import importlib
import logging
from types import ModuleType
from typing import Callable, Iterable

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.filters.rules.person import HasSoundexName
from gramps.gen.plug import PluginRegister
from gramps.gen.plug._pluginreg import RULE
from gramps.gen.soundex import soundex as _core_soundex

LOG = logging.getLogger(__name__)

#: Every Person filter rule this addon (or any independently
#: distributed addon) wants included in the Encoding system list must
#: register with a Gramps plugin ``id`` starting with this prefix -
#: see the module docstring above for why this, rather than shared
#: physical location, is what identifies an encoding system's rule.
#: ``nysiisrule.gpr.py``/``matchratingrule.gpr.py`` both do this.
_ENCODER_ID_PREFIX = "FuzzyMatchingEncoder:"


def _soundex_encode(name: str) -> set[str]:
    """
    Return the (single-element) Soundex code set for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: A one-element set containing the four-character Soundex
        code, matching the value that
        :func:`gramps.gen.soundex.soundex` would return.
    """
    try:
        return {_core_soundex(name)}
    except UnicodeEncodeError:
        LOG.debug("Soundex encoding failed for %r, falling back to empty", name)
        return {_core_soundex("")}


def _hardcoded_soundex() -> tuple[str, Callable[[str], set[str]], str, str, type]:
    """
    Build the hardcoded Soundex registry entry - see the module
    docstring for why Soundex specifically is not discovered the way
    every other encoding system is.

    :returns: A ``(algorithm_id, encode, label, description,
        rule_class)`` tuple, in the shape :func:`_load_encoders`
        assembles its four registries from.
    """
    description = (
        "The classic 4-character genealogy code (e.g. Gramps' own"
        " SoundEx gramplet). Groups names that sound alike when"
        ' spoken, such as "Smith" and "Smyth".'
    )
    return ("soundex", _soundex_encode, "Soundex", description, HasSoundexName)


def _discover_addon_rule_modules() -> list[tuple[ModuleType, str, str]]:
    """
    Ask Gramps' own plugin registry for every ``RULE``-type plugin
    whose ``id`` starts with :data:`_ENCODER_ID_PREFIX`, and import
    each one.

    :returns: A list of ``(module, ruleclass_name, namespace)`` tuples
        for every such plugin that imported successfully. A plugin
        whose module fails to import is logged and omitted rather than
        aborting discovery of the rest. ``ruleclass_name``/``namespace``
        are Gramps' own record (from the ``.gpr.py`` registration, not
        this module) of which class in the module is the actual filter
        rule, and which primary-object namespace (``"Person"`` for
        every rule this addon ships) it belongs to.
    """
    modules_and_ruleclasses = []
    registry = PluginRegister.get_instance()
    for pdata in registry.type_plugins(RULE):
        if not (pdata.id or "").startswith(_ENCODER_ID_PREFIX):
            continue
        try:
            module = importlib.import_module(pdata.mod_name)
        except Exception:  # pylint: disable=broad-except
            LOG.exception(
                "Fuzzy Matching: could not import rule module %r for "
                "plugin %r, skipping",
                pdata.mod_name,
                pdata.id,
            )
            continue
        modules_and_ruleclasses.append((module, pdata.ruleclass, pdata.namespace))
    return modules_and_ruleclasses


def _make_rule_findable_via_import(
    rule_class: type, ruleclass_name: str, namespace: str
) -> None:
    """
    Make a discovered rule class resolvable as
    ``gramps.gen.filters.rules.<namespace>.<ruleclass_name>``, the same
    way Gramps' own built-in rules already are and the same way
    Gramps' own plugin manager makes *other* addon rules found this
    way (``gramps.gen.plug._manager.BasePluginManager.reg_plugins``
    has an equivalent "Get the addon rules and import them and make
    them findable" step, confirmed directly in the Gramps source).

    This matters for a very concrete reason, not just tidiness:
    Gramps saves a filter's rule to XML as only the bare class name
    (``rule.__class__.__name__``, confirmed directly in
    ``gramps.gen.filters._filterlist.FilterList.save``), and reloads
    it by trying, among other things, ``rules.<namespace>.<ClassName>``
    (confirmed directly in ``gramps.gen.filters._filterparser``). If
    the class was never made an attribute of that module - which a
    plain ``importlib.import_module`` of this addon's own rule module,
    on its own, does not do - that lookup fails, Gramps logs "Filter
    rule ... not found!", and drops the rule from the filter entirely.
    A filter with zero rules is not an error: ``all(())`` and the
    equivalent "AND every rule" logic are vacuously true for an empty
    rule list, so the filter silently matches *every* person in the
    tree instead of raising anything - confirmed directly, not just
    reasoned about, by building a filter with one of this addon's
    rules, saving it, reloading it fresh, and applying it: the reload
    logged the "not found" warning, produced a filter with an empty
    rule list, and matched every person handed to it.

    Calling this every time a rule is discovered (rather than relying
    on Gramps' own equivalent step, which is not guaranteed to exist or
    run before this addon's own discovery does, depending on Gramps
    version and load order) means a filter built from this addon's
    "Define filter" action keeps working correctly the next time it is
    applied, including after being saved, reloaded, or used from a
    different view than the gramplet itself.

    :param rule_class: The already-resolved rule class.
    :param ruleclass_name: Its class name, matching the ``.gpr.py``
        registration's own ``ruleclass``.
    :param namespace: The primary-object namespace it belongs to
        (``"Person"`` for every rule this addon ships), matching the
        ``.gpr.py`` registration's own ``namespace``.
    """
    try:
        rules_namespace_module = importlib.import_module(
            "gramps.gen.filters.rules." + namespace.lower()
        )
    except ImportError:
        LOG.warning(
            "Fuzzy Matching: no gramps.gen.filters.rules.%s to register "
            "%r into; filters using it may not survive being saved "
            "and reloaded",
            namespace.lower(),
            ruleclass_name,
        )
        return

    setattr(rules_namespace_module, ruleclass_name, rule_class)

    editor_rule_list = getattr(rules_namespace_module, "editor_rule_list", None)
    if editor_rule_list is not None and rule_class not in editor_rule_list:
        editor_rule_list.append(rule_class)


def _register_encoders(
    entries: Iterable[tuple[str, Callable[[str], set[str]], str, str, type | None]],
) -> tuple[
    dict[str, Callable[[str], set[str]]],
    dict[str, str],
    dict[str, str],
    dict[str, type | None],
]:
    """
    Register each already-resolved ``(algorithm_id, encode, label,
    description, rule_class)`` entry.

    Split out from the discovery functions above so the
    duplicate-handling logic can be unit tested directly with
    in-memory fake entries, without needing a real Gramps plugin
    registry - see ``test/phonetic_codes_test.py``.

    :param entries: Already-resolved
        ``(algorithm_id, encode, label, description, rule_class)``
        tuples.
    :returns: An ``(algorithms, labels, descriptions, filter_rules)``
        tuple, each dict keyed by algorithm id, matching
        :data:`ALGORITHMS`/:data:`ALGORITHM_LABELS`/
        :data:`ALGORITHM_DESCRIPTIONS`/:data:`ALGORITHM_FILTER_RULES`.
        An entry reusing an id an earlier entry already claimed is
        logged and skipped - the rest are still registered.
    """
    algorithms: dict[str, Callable[[str], set[str]]] = {}
    labels: dict[str, str] = {}
    descriptions: dict[str, str] = {}
    filter_rules: dict[str, type | None] = {}

    for algorithm_id, encode, label, description, rule_class in entries:
        if algorithm_id in algorithms:
            LOG.warning(
                "Fuzzy Matching: duplicate encoder id %r, keeping the "
                "first one found",
                algorithm_id,
            )
            continue
        algorithms[algorithm_id] = encode
        labels[algorithm_id] = label
        descriptions[algorithm_id] = description
        filter_rules[algorithm_id] = rule_class

    return algorithms, labels, descriptions, filter_rules


def _resolve_discovered_entries() -> (
    list[tuple[str, Callable[[str], set[str]], str, str, type | None]]
):
    """
    Turn every discovered addon rule module into a
    ``(algorithm_id, encode, label, description, rule_class)`` entry,
    validating each against the encoder contract.

    :returns: One entry per module that satisfies the contract
        (``ALGORITHM_ID``, ``ALGORITHM_LABEL``, and a callable
        ``encode`` are required; ``ALGORITHM_DESCRIPTION`` defaults to
        ``""`` if absent). A module missing a required attribute, or
        whose ``encode`` is not callable, is logged and skipped.
    """
    entries = []
    for module, ruleclass_name, namespace in _discover_addon_rule_modules():
        module_name = getattr(module, "__name__", repr(module))
        try:
            algorithm_id = module.ALGORITHM_ID
            algorithm_label = module.ALGORITHM_LABEL
            encode = module.encode
        except AttributeError as err:
            LOG.warning(
                "Fuzzy Matching: rule module %r is missing %s, skipping",
                module_name,
                err,
            )
            continue

        if not callable(encode):
            LOG.warning(
                "Fuzzy Matching: rule module %r has a non-callable encode, skipping",
                module_name,
            )
            continue

        description = getattr(module, "ALGORITHM_DESCRIPTION", "")
        rule_class = getattr(module, ruleclass_name, None)
        if rule_class is not None:
            _make_rule_findable_via_import(rule_class, ruleclass_name, namespace)
        entries.append((algorithm_id, encode, algorithm_label, description, rule_class))

    return entries


def _load_encoders() -> tuple[
    dict[str, Callable[[str], set[str]]],
    dict[str, str],
    dict[str, str],
    dict[str, type | None],
]:
    """
    Assemble the full encoder registry: the hardcoded Soundex entry
    plus every discovered addon rule module.

    :returns: See :func:`_register_encoders`.
    """
    entries = [_hardcoded_soundex()] + _resolve_discovered_entries()
    return _register_encoders(entries)


def _choose_default(algorithms: dict[str, Callable[[str], set[str]]]) -> str | None:
    """
    Pick the default algorithm id from whatever :func:`_load_encoders`
    found.

    :param algorithms: The discovered ``{id: encode}`` mapping.
    :returns: ``"soundex"`` if it was found (it always should be,
        being hardcoded), otherwise the first id found (sorted, for a
        stable choice across runs), or ``None`` if no encoders were
        found at all.
    """
    if "soundex" in algorithms:
        return "soundex"
    if algorithms:
        return sorted(algorithms)[0]
    return None


#: Registry of available algorithms, keyed by the identifier stored in
#: the gramplet's UI, auto-populated as described in the module
#: docstring above. Each entry maps to a function that takes a name
#: and returns a set of codes (a set, rather than a single code,
#: because some phonetic algorithms legitimately produce more than one
#: valid code for a single spelling). Adding a future algorithm needs
#: no change here: add a new <name>.py/<name>.gpr.py RULE plugin pair
#: to this addon's own folder instead.
ALGORITHMS: dict[str, Callable[[str], set[str]]]

#: Display labels for :data:`ALGORITHMS`, keyed the same way, kept
#: separate so callers can build UI without importing translation
#: machinery into this module.
ALGORITHM_LABELS: dict[str, str]

#: Help/description text for :data:`ALGORITHMS`, keyed the same way
#: (an empty string for a module that does not provide one). Intended
#: for display as a tooltip on the gramplet's Encoding system dropdown
#: - see :meth:`FuzzyMatchingGramplet.cb_algorithm_changed`.
ALGORITHM_DESCRIPTIONS: dict[str, str]

#: The Person filter rule class to use for each algorithm's "Define
#: filter" action, keyed the same way (``None`` if not resolvable).
#: See :meth:`FuzzyMatchingGramplet.cb_surname_activated`, which tells
#: the user that action is unavailable rather than silently doing
#: nothing, or incorrectly reusing a different algorithm's rule, when
#: this is ``None`` for the currently-selected algorithm.
ALGORITHM_FILTER_RULES: dict[str, type | None]

ALGORITHMS, ALGORITHM_LABELS, ALGORITHM_DESCRIPTIONS, ALGORITHM_FILTER_RULES = (
    _load_encoders()
)

#: The algorithm id the gramplet selects by default. See
#: :func:`_choose_default`.
DEFAULT_ALGORITHM = _choose_default(ALGORITHMS)

if not ALGORITHMS:
    LOG.error(
        "Fuzzy Matching: no phonetic encoders could be loaded "
        "(not even the hardcoded Soundex entry); the gramplet's "
        "Encoding system list will be empty"
    )
