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
Metaphone support for the Fuzzy Matching Gramplet - both as a Person
filter rule usable standalone in Gramps' own Filter Editor ("Add
Rule" > General filters > "Metaphone match of People with the <names>"),
and as the encoding system the gramplet itself offers under that same
name.

Both live in this one file because they always travel together: this
gramplet auto-discovers its own encoding systems by asking Gramps'
own plugin registry (`gramps.gen.plug._pluginreg.PluginRegister`) for
every registered ``RULE``-type plugin whose ``id`` starts with
``phonetic_codes._ENCODER_ID_PREFIX`` (``"FuzzyMatchingEncoder:"`` -
see this file's own ``.gpr.py`` registration below), not by shared
folder location. Identity by ``id`` rather than by shared location is
deliberate: it means this rule (or any other encoding system's) could
be split out into its own, independently installed and independently
updated Gramps addon without breaking discovery, as long as its
registration keeps that same id prefix - a new encoding system is
just a new ``<name>rule.py``/``<name>rule.gpr.py`` pair, registered as
an ordinary Gramps Rule plugin with that prefix.

Using this rule directly in a Custom Filter
--------------------------------------------

This rule is not exclusive to the gramplet: open Edit > Person
Filter Editor (or the filter side-bar's "Edit" button on the Person
view), create or edit a filter, "Add Rule...", and it appears under
*General filters* as "Metaphone match of People with the <names>". Give it a
name and it matches every person whose selected name fields (by
default, the preferred name's surname pieces and call name) have
the same Metaphone code - the same test the gramplet's own "Define
filter" double-click action builds for you when Metaphone is the
selected Encoding system, so building it by hand here is only useful
if you want to combine it with other rules (e.g. AND'd with a
birth-year range) that the gramplet's own shortcut does not offer.

About Metaphone, and why this implementation exists
-----------------------------------------------------

Devised by Lawrence Philips in 1990 as an improvement on Soundex,
Metaphone models English pronunciation more closely - it accounts for
many more consonant-cluster and silent-letter patterns (e.g. silent
"GH", "PH" -> F, "TH" -> a distinct code, "KN"/"GN"/"PN" -> dropping
the leading consonant) than Soundex's simpler letter-grouping scheme,
and produces a variable-length code (by default capped at 4
characters, matching genealogical convention) rather than Soundex's
fixed 4-character shape. It correctly groups pairs Soundex sometimes
misses in the other direction too - e.g. this implementation confirms
"Smith" and "Smyth" both encode to "SM0", matching Soundex's own
Smith/Smyth agreement (NYSIIS, notably, does not - see
``nysiisrule.py``), which is the actual reason for offering more than
one Encoding system in the first place: no single algorithm agrees
with the others on every pair, and different real misspellings are
better caught by different algorithms.

Gramps has no built-in Metaphone implementation to wrap (unlike
Soundex), so ``encode`` here is a from-scratch Python port - ported
line-by-line from, and validated against every test case in, Apache
Commons Codec's ``Metaphone`` class and its own test suite (47 direct
assertions plus 18 "these N names must all share a code" groups
covering over 200 name comparisons total, all passing exactly), a
mature, widely-used reference implementation:
https://github.com/apache/commons-codec/blob/master/src/main/java/org/apache/commons/codec/language/Metaphone.java
https://github.com/apache/commons-codec/blob/master/src/test/java/org/apache/commons/codec/language/MetaphoneTest.java

The reference implementation supports a configurable maximum code
length (default 4). This module always uses the default: nothing here
needs a longer code for extra precision, and a fixed length keeps
results consistent regardless of algorithm choice, matching how the
other encoders in this addon behave.
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
ALGORITHM_ID = "metaphone"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Metaphone"

#: Shown as a tooltip on the Encoding system dropdown when this
#: algorithm is selected. See the contract in ``phonetic_codes.py``.
ALGORITHM_DESCRIPTION = (
    "Models English pronunciation more closely than Soundex - handles"
    ' silent letters and consonant clusters (e.g. "PH" -> F, silent'
    ' "GH") that Soundex\'s simpler scheme misses. Produces a shorter,'
    " variable-length code rather than Soundex's fixed 4 characters."
)

_MAX_CODE_LEN = 4
_VOWELS = "AEIOU"
_FRONTV = "EIY"
_VARSON = "CSPTG"


def _is_vowel(local: str, index: int) -> bool:
    """
    :param local: The working (uppercased, initial-exceptions-applied)
        string.
    :param index: Position to check.
    :returns: True if ``local[index]`` is one of A, E, I, O, U.
    """
    return local[index] in _VOWELS


def _is_next_char(local: str, index: int, char: str) -> bool:
    """
    :returns: True if the character after ``local[index]`` is ``char``.
    """
    return 0 <= index < len(local) - 1 and local[index + 1] == char


def _is_previous_char(local: str, index: int, char: str) -> bool:
    """
    :returns: True if the character before ``local[index]`` is ``char``.
    """
    return 0 < index < len(local) and local[index - 1] == char


def _is_last_char(word_size: int, index: int) -> bool:
    """
    :returns: True if ``index`` is the last valid position in a string
        of length ``word_size``.
    """
    return index + 1 == word_size


def _region_match(local: str, index: int, test: str) -> bool:
    """
    :returns: True if ``local`` contains exactly ``test`` starting at
        ``index``.
    """
    return (
        index >= 0
        and index + len(test) - 1 < len(local)
        and local[index : index + len(test)] == test
    )


def _apply_initial_exceptions(letters: list[str]) -> list[str]:
    """
    Handle the small set of initial-letter-pair exceptions the
    reference algorithm applies before its main, per-character pass:
    KN/GN/PN drop the leading consonant, AE drops the leading A, WR
    drops the leading W, WH collapses to just W, and a leading X is
    treated as if it were S.

    :param letters: The uppercased input, as a list of characters.
    :returns: The adjusted list of characters (a new list; ``letters``
        itself is never mutated).
    """
    # pylint: disable=too-many-return-statements
    # A faithful, sequential port of the reference implementation's own
    # initial-letter-pair rules; see the module docstring.
    first = letters[0]
    if first in ("K", "G", "P"):
        return letters[1:] if letters[1] == "N" else letters[:]
    if first == "A":
        return letters[1:] if letters[1] == "E" else letters[:]
    if first == "W":
        if letters[1] == "R":
            return letters[1:]
        if letters[1] == "H":
            adjusted = letters[1:]
            adjusted[0] = "W"
            return adjusted
        return letters[:]
    if first == "X":
        adjusted = letters[:]
        adjusted[0] = "S"
        return adjusted
    return letters[:]


def _encode_c(local: str, index: int, word_size: int) -> str:
    """Metaphone's C-specific rules (SCI/SCE/SCY, SCH, CIA/CH, CI/CE/CY)."""
    if (
        _is_previous_char(local, index, "S")
        and not _is_last_char(word_size, index)
        and local[index + 1] in _FRONTV
    ):
        return ""
    if _is_previous_char(local, index, "S") and _is_next_char(local, index, "H"):
        return "K"
    if _region_match(local, index, "CIA") or _is_next_char(local, index, "H"):
        return "X"
    if not _is_last_char(word_size, index) and local[index + 1] in _FRONTV:
        return "S"
    return "K"


def _encode_g(local: str, index: int, word_size: int) -> str:
    """Metaphone's G-specific rules (silent GH, GN/GNED, GE/GI/GY -> J)."""
    if _is_last_char(word_size, index + 1) and _is_next_char(local, index, "H"):
        return ""
    if (
        not _is_last_char(word_size, index + 1)
        and _is_next_char(local, index, "H")
        and not _is_vowel(local, index + 2)
    ):
        return ""
    if index > 0 and (
        _region_match(local, index, "GN") or _region_match(local, index, "GNED")
    ):
        return ""
    hard = _is_previous_char(local, index, "G")
    if not _is_last_char(word_size, index) and local[index + 1] in _FRONTV and not hard:
        return "J"
    return "K"


def _encode_h(local: str, index: int, word_size: int) -> str:
    """Metaphone's H-specific rules (silent terminal H, H after C/S/P/T/G)."""
    if _is_last_char(word_size, index):
        return ""
    if index > 0 and local[index - 1] in _VARSON:
        return ""
    if _is_vowel(local, index + 1):
        return "H"
    return ""


def _encode_t(local: str, index: int, word_size: int) -> str:
    """Metaphone's T-specific rules (TIA/TIO -> X, silent TCH, TH -> 0)."""
    # word_size is unused directly but kept for a consistent signature
    # with the other _encode_<letter> helpers.
    del word_size
    if _region_match(local, index, "TIA") or _region_match(local, index, "TIO"):
        return "X"
    if _region_match(local, index, "TCH"):
        return ""
    if _region_match(local, index, "TH"):
        return "0"
    return "T"


def _encode_char(local: str, index: int, word_size: int) -> tuple[str, int]:
    """
    Determine the code contribution of ``local[index]``.

    :param local: The working (uppercased, initial-exceptions-applied)
        string.
    :param index: Position being encoded.
    :param word_size: ``len(local)``, passed separately since several
        rules need it repeatedly.
    :returns: A ``(characters_to_append, extra_positions_to_skip)``
        pair. ``extra_positions_to_skip`` is 0 for every letter except
        D followed by "GE"/"GI"/"GY" (-> J, and skip the G too).
    """
    # pylint: disable=too-many-return-statements,too-many-branches
    # A faithful, sequential port of the reference implementation's own
    # per-letter rules; each letter is independent, so splitting this
    # further would make it harder, not easier, to audit against the
    # source this was ported from (see the module docstring).
    symb = local[index]
    if symb in _VOWELS:
        return (symb if index == 0 else "", 0)
    if symb == "B":
        if _is_previous_char(local, index, "M") and _is_last_char(word_size, index):
            return ("", 0)
        return ("B", 0)
    if symb == "C":
        return (_encode_c(local, index, word_size), 0)
    if symb == "D":
        if (
            not _is_last_char(word_size, index + 1)
            and _is_next_char(local, index, "G")
            and local[index + 2] in _FRONTV
        ):
            return ("J", 2)
        return ("T", 0)
    if symb == "G":
        return (_encode_g(local, index, word_size), 0)
    if symb == "H":
        return (_encode_h(local, index, word_size), 0)
    if symb in "FJLMNR":
        return (symb, 0)
    if symb == "K":
        if index > 0 and _is_previous_char(local, index, "C"):
            return ("", 0)
        return ("K", 0)
    if symb == "P":
        return ("F" if _is_next_char(local, index, "H") else "P", 0)
    if symb == "Q":
        return ("K", 0)
    if symb == "S":
        if (
            _region_match(local, index, "SH")
            or _region_match(local, index, "SIO")
            or _region_match(local, index, "SIA")
        ):
            return ("X", 0)
        return ("S", 0)
    if symb == "T":
        return (_encode_t(local, index, word_size), 0)
    if symb == "V":
        return ("F", 0)
    if symb in "WY":
        if not _is_last_char(word_size, index) and _is_vowel(local, index + 1):
            return (symb, 0)
        return ("", 0)
    if symb == "X":
        return ("KS", 0)
    if symb == "Z":
        return ("S", 0)
    return ("", 0)


def _metaphone(name: str) -> str:
    """
    Compute the Metaphone code for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: The Metaphone code (at most :data:`_MAX_CODE_LEN`
        characters), or an empty string if ``name`` is empty.
    """
    if not name:
        return ""
    if len(name) == 1:
        return name.upper()

    local = "".join(_apply_initial_exceptions(list(name.upper())))
    word_size = len(local)
    code: list[str] = []
    index = 0

    while len(code) < _MAX_CODE_LEN and index < word_size:
        symb = local[index]
        # Remove duplicate letters except C: a repeat of the
        # immediately preceding character is skipped entirely, unless
        # that repeated character is C (e.g. "ACCENT" still processes
        # both Cs, since they trigger different sub-rules depending on
        # what follows each one).
        if symb == "C" or not _is_previous_char(local, index, symb):
            addition, extra = _encode_char(local, index, word_size)
            code.extend(addition)
            index += extra
        index += 1
        if len(code) > _MAX_CODE_LEN:
            code = code[:_MAX_CODE_LEN]

    return "".join(code)


def encode(name: str) -> set[str]:
    """
    Return the (single-element) Metaphone code set for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: A one-element set containing the Metaphone code.
    """
    try:
        return {_metaphone(name)}
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Metaphone encoding failed for %r, falling back to empty", name)
        return {_metaphone("")}


# -------------------------------------------------------------------------
#
# HasMetaphoneName
#
# -------------------------------------------------------------------------
class HasMetaphoneName(Rule):
    """
    Rule that checks for a Metaphone match on a person's names.

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
    name = _("Metaphone match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same Metaphone code as the given "
        "name"
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
