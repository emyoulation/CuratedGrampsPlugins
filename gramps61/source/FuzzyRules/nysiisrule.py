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
NYSIIS (New York State Identification and Intelligence System) support
for the Fuzzy Matching Gramplet - both as a Person filter rule usable
standalone in Gramps' own Filter Editor ("Add Rule" > General filters
> "NYSIIS match of People with the <names>"), and as the encoding system
the gramplet itself offers under that same name.

Both live in this one file because they always travel together: this
gramplet auto-discovers its own encoding systems by asking Gramps'
own plugin registry (`gramps.gen.plug._pluginreg.PluginRegister`) for
every registered ``RULE``-type plugin whose ``id`` starts with
``phonetic_codes._ENCODER_ID_PREFIX`` (``"FuzzyMatchingEncoder:"`` -
see this file's own ``.gpr.py`` registration below), not by scanning a
folder of its own. Identity by ``id`` rather than by shared location
is deliberate: it means this rule (or any other encoding system's)
could be split out into its own, independently installed and
independently updated Gramps addon without breaking discovery, as
long as its registration keeps that same id prefix - a new encoding
system is just a new ``<name>rule.py``/``<name>rule.gpr.py`` pair,
registered as an ordinary Gramps Rule plugin with that prefix, using
the machinery Gramps already has for exactly this rather than a
second, parallel discovery system.

Adding a new encoding system means writing a file shaped like this
one, satisfying the small contract documented in ``phonetic_codes.py``
(``ALGORITHM_ID``, ``ALGORITHM_LABEL``, ``encode``, and optionally
``ALGORITHM_DESCRIPTION``), plus registering it as a ``RULE`` plugin
the normal Gramps way (see ``nysiisrule.gpr.py`` alongside this file)
so it also has a rule for the gramplet's "Define filter" action to
use - see ``FuzzyMatchingGramplet.cb_surname_activated``.

Using this rule directly in a Custom Filter
--------------------------------------------

This rule is not exclusive to the gramplet: open Edit > Person
Filter Editor (or the filter side-bar's "Edit" button on the Person
view), create or edit a filter, "Add Rule...", and it appears under
*General filters* as "NYSIIS match of People with the <names>". Give it a
name and it matches every person whose selected name fields (by
default, the preferred name's surname pieces and call name) have the
same NYSIIS code - the same test the gramplet's own "Define filter"
double-click action builds for you when NYSIIS is the selected
Encoding system, so building it by hand here is only useful if you
want to combine it with other rules (e.g. AND'd with a birth-year
range) that the gramplet's own shortcut does not offer.

About NYSIIS, and why this implementation exists
--------------------------------------------------

Devised in 1970, NYSIIS keeps more information about vowel position
and sequence than Soundex does, at the cost of being a longer code.
It does not treat "Y" as a vowel (except in the specific suffix rules
below), so it will not consider some pairs a match that Soundex does -
e.g. "Smith" and "Smyth" get different NYSIIS codes. This is a real,
deliberate characteristic of the algorithm, not a bug, and not a sign
that Soundex is somehow more "correct" - they simply group surnames
differently, which is the actual reason for offering more than one
Encoding system in the first place.

Gramps has no built-in NYSIIS implementation to wrap (unlike Soundex),
so ``encode`` here is a from-scratch Python port - ported line-by-line
from, and validated against every one of the roughly 85 test cases in,
Apache Commons Codec's ``Nysiis`` class and its own test suite, a
mature, widely-used reference implementation:
https://github.com/apache/commons-codec/blob/master/src/main/java/org/apache/commons/codec/language/Nysiis.java
https://github.com/apache/commons-codec/blob/master/src/test/java/org/apache/commons/codec/language/NysiisTest.java

Unlike that library's default ("strict") mode, ``encode`` returns the
full, untruncated code rather than truncating to 6 characters: NYSIIS'
own advantage over Soundex is retaining more information, and nothing
here needs the fixed-width-database-field constraint that motivated
the original 6-character limit in 1970. ``test/nysiisrule_test.py``
covers both the full code this module returns and the truncated
6-character form, so a future contributor who wants strict-mode
truncation back has a validated starting point.
"""

# Deferred annotation evaluation (PEP 563), required for Python 3.8/3.9
# compatibility: this module's type hints use `list[X]`, `tuple[X, Y]`,
# `set[str]`, etc. (PEP 585 syntax), which those Python versions cannot
# evaluate at runtime even though they parse it fine - Gramps 5.2's own
# official minimum is Python 3.8. This import makes every annotation in
# this file a deferred string, never evaluated at runtime at all,
# restoring compatibility with the full (5.2.0, 6.2.0) Gramps range
# this addon's own .gpr.py declares, without giving up the modern
# annotation syntax itself.
from __future__ import annotations

# ------------------------
# Python modules
# ------------------------
import logging
from collections.abc import Callable
from typing import Any

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule
from gramps.gen.lib import Person

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext


LOG = logging.getLogger(__name__)

# ------------------------
# Gramps specific
# ------------------------
# "Match in:" option, from phonetic_name_parts.py in this folder. The
# import is guarded because Gramps does not survive a rule addon that
# fails to import: if the file is missing, this rule still loads and
# compares the preferred surname only, without the option.
try:
    # pylint: disable-next=wrong-import-position
    from phonetic_name_parts import (
        OPTION_LABEL,
        name_parts_widget,
        pad_args,
        parse_parts,
        person_matches,
    )

    _HAVE_NAME_PARTS = True
except ImportError:
    _HAVE_NAME_PARTS = False
    LOG.warning(
        "phonetic_name_parts.py not found next to %s; the Match in: option "
        "is unavailable and only the preferred surname is compared",
        __file__,
    )

    def pad_args(arg: list[str] | None) -> list[str]:
        """
        Fallback: return the rule arguments unchanged.

        :param arg: The rule's argument list as given.
        :returns: The same arguments, as a list.
        """
        return list(arg or [])

    def parse_parts(text: str | None) -> frozenset[str]:
        """
        Fallback: no "Match in:" option, so no part keys.

        :param text: Ignored.
        :returns: An empty set.
        """
        del text
        return frozenset()

    def person_matches(
        person: Person,
        keys: frozenset[str],
        target_codes: set[str],
        encoder: Callable[[str], set[str]],
    ) -> bool:
        """
        Fallback: compare each surname piece of the preferred name.

        :param person: A :class:`gramps.gen.lib.Person`.
        :param keys: Ignored.
        :param target_codes: Codes of the name the rule was given.
        :param encoder: The module's ``encode`` function.
        :returns: True on a match.
        """
        del keys
        if not target_codes:
            return False
        surnames = person.get_primary_name().get_surname_list()
        words = [piece.get_surname() for piece in surnames]
        return any(encoder(w) & target_codes for w in words if w and w.strip())


#: Registry key. See the contract in ``phonetic_codes.py`` for why
#: this should be treated as stable once shipped.
ALGORITHM_ID = "nysiis"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "NYSIIS"

#: Shown as a tooltip on the Encoding system dropdown when this
#: algorithm is selected. See the contract in ``phonetic_codes.py``.
ALGORITHM_DESCRIPTION = (
    "Keeps more information about vowel position than Soundex, at the"
    ' cost of a longer code. Does not treat "Y" as a vowel, so it will'
    ' not match some pairs Soundex does (e.g. "Smith"/"Smyth").'
)

_VOWELS = "AEIOU"


def _is_vowel(char: str) -> bool:
    """
    :param char: A single character.
    :returns: True if ``char`` is one of A, E, I, O, U.
    """
    return char in _VOWELS


def _clean(name: str) -> str:
    """
    Keep only letters from ``name``, uppercased, matching the input
    normalization Apache Commons Codec's ``SoundexUtils.clean`` uses
    ahead of its own NYSIIS implementation.

    :param name: The raw input.
    :returns: ``name`` with every non-letter character removed,
        uppercased.
    """
    return "".join(char for char in name if char.isalpha()).upper()


def _transcode_remaining(prev: str, curr: str, nxt: str, after_next: str) -> str:
    """
    Transcode one character of the "remaining characters" pass (rule 4
    in the class docstring), given a 4-character sliding window
    ``[i-1, i, i+1, i+2]`` centered on the character being transcoded.

    :param prev: The character before ``curr`` (already transcoded, if
        an earlier step changed it).
    :param curr: The character being transcoded.
    :param nxt: The character after ``curr``, or a space if ``curr``
        is the last character.
    :param after_next: The character after ``nxt``, or a space if
        unavailable.
    :returns: The one-or-more-character replacement for ``curr``.
    """
    # pylint: disable=too-many-return-statements
    # A faithful, sequential port of the reference implementation's own
    # rule list; each rule is independent, so splitting this further
    # would make it harder, not easier, to audit against the source
    # this was ported from (see the module docstring).
    if curr == "E" and nxt == "V":
        return "AF"
    if _is_vowel(curr):
        return "A"
    if curr == "Q":
        return "G"
    if curr == "Z":
        return "S"
    if curr == "M":
        return "N"
    if curr == "K":
        return "NN" if nxt == "N" else "C"
    if curr == "S" and nxt == "C" and after_next == "H":
        return "SSS"
    if curr == "P" and nxt == "H":
        return "FF"
    if curr == "H" and (not _is_vowel(prev) or not _is_vowel(nxt)):
        return prev
    if curr == "W" and _is_vowel(prev):
        return prev
    return curr


def _transcode_prefix_and_suffix(cleaned: str) -> str:
    """
    Apply NYSIIS rules 1 and 2: transcode the first and last characters
    of the name before the main, per-character pass.

    :param cleaned: The already-cleaned (letters only, uppercased) name.
    :returns: ``cleaned`` with its first/last characters transcoded.
    """
    # 1. Transcode first characters of name.
    if cleaned.startswith("MAC"):
        cleaned = "MCC" + cleaned[3:]
    if cleaned.startswith("KN"):
        cleaned = "NN" + cleaned[2:]
    elif cleaned.startswith("K"):
        cleaned = "C" + cleaned[1:]
    if cleaned.startswith("PH") or cleaned.startswith("PF"):
        cleaned = "FF" + cleaned[2:]
    if cleaned.startswith("SCH"):
        cleaned = "SSS" + cleaned[3:]

    # 2. Transcode last characters of name.
    if cleaned.endswith("EE") or cleaned.endswith("IE"):
        cleaned = cleaned[:-2] + "Y"
    if cleaned.endswith(("DT", "RT", "RD", "NT", "ND")):
        cleaned = cleaned[:-2] + "D"

    return cleaned


def _build_key(cleaned: str) -> str:
    """
    Apply NYSIIS rules 3 and 4: build the key from ``cleaned``'s first
    character, followed by the transcoded remaining characters.

    :param cleaned: The name after :func:`_transcode_prefix_and_suffix`.
    :returns: The key before the trailing cleanup in rules 5-7.
    """
    # 3. First character of key = first character of name.
    chars = list(cleaned)
    length = len(chars)
    key_chars = [chars[0]]

    # 4. Transcode remaining characters, incrementing by one character
    # each time. This mutates `chars` in place (matching the reference
    # implementation exactly), so later iterations see already
    # transcoded characters as their "previous"/"next" context, not
    # the original ones.
    i = 1
    while i < length:
        prev = chars[i - 1]
        curr = chars[i]
        nxt = chars[i + 1] if i < length - 1 else " "
        after_next = chars[i + 2] if i < length - 2 else " "
        transcoded = _transcode_remaining(prev, curr, nxt, after_next)
        chars[i : i + len(transcoded)] = list(transcoded)
        if chars[i] != chars[i - 1]:
            key_chars.append(chars[i])
        i += 1

    return "".join(key_chars)


def _strip_trailing(key: str) -> str:
    """
    Apply NYSIIS rules 5-7: clean up the trailing characters of an
    already-built key.

    :param key: The key from :func:`_build_key`.
    :returns: ``key`` with its trailing S/AY/A handled per rules 5-7.
    """
    if len(key) <= 1:
        return key

    # 5. If last character is S, remove it.
    last_char = key[-1]
    if last_char == "S":
        key = key[:-1]
        last_char = key[-1]

    # 6. If last characters are AY, replace with Y.
    if len(key) > 2 and key[-2] == "A" and last_char == "Y":
        key = key[:-2] + last_char

    # 7. If last character is A, remove it.
    if last_char == "A":
        key = key[:-1]

    return key


def _nysiis(name: str) -> str:
    """
    Compute the full (untruncated) NYSIIS code for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: The NYSIIS code, or an empty string if ``name`` contains
        no letters at all.
    """
    cleaned = _clean(name)
    if not cleaned:
        return ""

    cleaned = _transcode_prefix_and_suffix(cleaned)
    key = _build_key(cleaned)
    return _strip_trailing(key)


def encode(name: str) -> set[str]:
    """
    Return the (single-element) NYSIIS code set for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: A one-element set containing the full NYSIIS code.
    """
    try:
        return {_nysiis(name)}
    except Exception:  # pylint: disable=broad-except
        LOG.debug("NYSIIS encoding failed for %r, falling back to empty", name)
        return {_nysiis("")}


# -------------------------------------------------------------------------
#
# HasNysiisName
#
# -------------------------------------------------------------------------
class HasNysiisName(Rule):
    """
    Rule that checks for a NYSIIS match on a person's names.

    Which name fields are compared is the rule's second option, "Match
    in:" (see ``phonetic_name_parts.py``). By default the preferred
    name's surname pieces (each piece separately) and its call name are
    compared. Ticking more boxes widens it towards what Gramps' built-in
    ``HasSoundexName`` always searches (given, call and nick names,
    alternate names), but only where the user asks for it - so a search
    for "Johnson" need not also return every John.
    """

    # Second option: which name parts to match (see
    # phonetic_name_parts.py). Missing/empty = preferred surname + call name.
    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("NYSIIS match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same NYSIIS (New York State "
        "Identification and Intelligence System) code as the given name"
    )
    category = _("General filters")
    allow_regex = False

    def __init__(
        self, arg: list[str], use_regex: bool = False, use_case: bool = False
    ) -> None:
        """
        Create the rule.

        :param arg: ``[name, match_in]``; ``match_in`` may be omitted.
        :param use_regex: Unused; this rule does not support regexes.
        :param use_case: Unused.
        """
        super().__init__(arg, use_regex, use_case)
        self._target_codes: set[str] = set()
        self._parts: frozenset[str] | None = None

    def set_list(self, arg: list[str]) -> None:
        """
        Store the rule values, filling in the "Match in:" option for
        one-argument filters saved by earlier versions (and callers
        that pass only the name), which then get the default: the
        preferred name's surname and call name.

        :param arg: The rule's argument list.
        """
        super().set_list(pad_args(arg))

    def prepare(self, db: Any, user: Any) -> None:
        """
        Encode the target name and read the "Match in:" option once.

        :param db: The active database. Unused.
        :param user: The active :class:`gramps.gen.user.User`. Unused.
        """
        del db, user
        self._target_codes = (
            encode(self.list[0]) if self.list and self.list[0] else set()
        )
        self._parts = parse_parts(self.list[1] if len(self.list) > 1 else "")

    def apply_to_one(self, db: Any, obj: Person) -> bool:
        """
        Apply the rule. Return True on a match.

        :param db: The active database. Unused.
        :param obj: The :class:`gramps.gen.lib.Person` being tested.
        :returns: True if any selected name field of ``obj`` encodes to
            one of the target codes.
        """
        if self._parts is None:  # applied without prepare()
            self.prepare(db, None)
        return person_matches(
            obj, self._parts or frozenset(), self._target_codes, encode
        )

    def apply(self, db: Any, obj: Person) -> bool:
        """
        Alias for :meth:`apply_to_one`, for Gramps 5.2, whose filters
        call ``apply``; Gramps 6.0+ calls ``apply_to_one``.

        :param db: The active database. Unused.
        :param obj: The :class:`gramps.gen.lib.Person` being tested.
        :returns: See :meth:`apply_to_one`.
        """
        return self.apply_to_one(db, obj)
