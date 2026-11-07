#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Jerome Rapinat
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

"""
Custom Soundex person filter rule with name-field granularity,
standalone or as the Fuzzy Matching Gramplet's Soundex Custom
encoding system.

The encoder
-----------

This is a Soundex variant. It keeps the shape of classic Soundex - the
first letter, then a four-character code - but it groups the consonants
differently and reads four letter pairs as one sound before coding
begins:

* "PH" is read as "F", "KN" as "N", "WR" as "R", and "GH" is dropped.
* B, P, V and F share a group, as do C, K, Q, G and J; S, Z and X;
  D and T; and M and N. L and R keep groups of their own.

Where classic Soundex writes digits, this variant writes the letter
that stands for the group, so a code looks like "SMD0" rather than
"S530". Vowels separate groups and are then dropped, and H and W are
dropped with them, as in classic Soundex.

The pairs it reads are English rather than French ones, so despite the
name under which it was submitted it is a general-purpose variant, not
a French encoder. For French-language names, see
``phonexfrenchrule.py`` in this folder.

Name fields
-----------

The rule adds the "Match in:" option shared with the rules of the
FuzzyRules addon (see ``phonetic_name_parts.py``). Its default is the
preferred name's surname pieces and call name.

It registers with the ``FuzzyMatchingEncoder:`` id prefix, so when it
is installed the Fuzzy Matching Gramplet offers Soundex Custom as an
encoding system and uses this rule for "Define filter". See
``phonetic_codes._load_encoders``.
"""

from __future__ import annotations

# ------------------------
# Python modules
# ------------------------
import logging
import unicodedata
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
# "Match in:" option, from the copy of phonetic_name_parts.py shipped
# in this folder. The import is guarded because Gramps does not
# survive a rule addon that fails to import: if the file is missing,
# this rule still loads and compares the preferred surname only,
# without the option.
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


#: Registry key - see the contract in ``phonetic_codes.py`` for why
#: this is treated as stable once shipped.
ALGORITHM_ID = "soundex_custom"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Soundex Custom"

#: Tooltip for the Encoding system dropdown.
ALGORITHM_DESCRIPTION = (
    "A Soundex variant with wider consonant groups (B,P,V,F; C,K,Q,G,J;"
    " S,Z,X; D,T; M,N) that also reads PH, KN, WR and GH as one sound."
    " Groups more spellings together than classic Soundex does."
)

#: Letter pairs read as one sound, applied to the whole name before the
#: first letter is taken.
_SPECIAL_COMBINATIONS = (
    ("PH", "F"),
    ("KN", "N"),
    ("GH", ""),
    ("WR", "R"),
)

#: Consonant groups. Each letter is written as the letter that stands
#: for its group. Letters absent from the map (H and W) are dropped.
_CONSONANT_MAP = {
    "B": "B",
    "P": "B",
    "V": "B",
    "F": "B",
    "C": "C",
    "K": "C",
    "Q": "C",
    "G": "C",
    "J": "C",
    "S": "S",
    "Z": "S",
    "X": "S",
    "D": "D",
    "T": "D",
    "L": "L",
    "M": "M",
    "N": "M",
    "R": "R",
}

#: Letters that separate groups and are then dropped from the code.
_VOWELS = "AEIOUY"

#: Letters that are neither coded nor kept.
_SILENT = "HW"

#: Length of a finished code, counting the first letter.
_CODE_LENGTH = 4


def _clean_and_upper(name: str) -> str:
    """
    Return ``name`` upper-cased, folded to ASCII and stripped of
    anything that is not a letter.

    The fold matters for names recorded with accents: without it, "é"
    and "ç" reach the code unchanged and an accented spelling of a name
    cannot match a plain one.

    :param name: The name (or any word) to clean.
    :returns: The letters of the name, upper-case ASCII.
    """
    folded = (
        unicodedata.normalize("NFKD", str(name).upper())
        .encode("ASCII", "ignore")
        .decode("ASCII")
    )
    return "".join(char for char in folded if char.isalpha())


def _apply_special_combinations(name: str) -> str:
    """
    Read the letter pairs that stand for one sound.

    :param name: A cleaned, upper-case name.
    :returns: The name with each pair replaced.
    """
    for old, new in _SPECIAL_COMBINATIONS:
        name = name.replace(old, new)
    return name


def _map_consonants(name: str) -> str:
    """
    Write each consonant as the letter standing for its group.

    :param name: A cleaned, upper-case name.
    :returns: The name with consonants mapped; vowels pass through.
    """
    return "".join(_CONSONANT_MAP.get(char, char) for char in name)


def _collapse_repeats(name: str) -> str:
    """
    Return ``name`` with runs of one repeated character reduced to one.

    :param name: A mapped name.
    :returns: The same text with no character repeated side by side.
    """
    out: list[str] = []
    for char in name:
        if not out or out[-1] != char:
            out.append(char)
    return "".join(out)


def _soundex_custom(name: str) -> str:
    """
    Return the custom Soundex code for ``name``.

    The first letter is kept as written; the rest is read for its
    special pairs, mapped to consonant groups, collapsed where a group
    repeats, and stripped of the vowels that separated the groups. The
    result is cut or padded to four characters.

    :param name: The name (or any word) to encode.
    :returns: The four-character code, or an empty string for a name
        with no letters in it.
    """
    cleaned = _clean_and_upper(name)
    if not cleaned:
        return ""

    # The pairs are read across the whole name, so that a name starting
    # with one of them ("Philippe", "Knight") is read like a name that
    # merely contains it.
    cleaned = _apply_special_combinations(cleaned)
    cleaned = "".join(char for char in cleaned if char not in _SILENT)
    if not cleaned:
        return ""

    first_letter = cleaned[0]
    rest = _map_consonants(cleaned[1:])
    rest = _collapse_repeats(rest)
    rest = "".join(char for char in rest if char not in _VOWELS)

    return (first_letter + rest + "000")[:_CODE_LENGTH]


def encode(name: str) -> set[str]:
    """
    Return the (single-element) custom Soundex code set for ``name``.

    :param name: The name (or any word) to encode.
    :returns: A one-element set holding the code, or an empty set for a
        name with no letters in it.
    """
    try:
        code = _soundex_custom(name)
        return {code} if code else set()
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Soundex Custom encoding failed for %r, returning no code", name)
        return set()


# -------------------------------------------------------------------------
#
# HasSoundexCustomNames
#
# -------------------------------------------------------------------------
class HasSoundexCustomNames(Rule):
    """
    Rule that checks for a custom Soundex match on a person's names, in
    the name fields selected by the "Match in:" option (the preferred
    name's surname pieces and call name by default).
    """

    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("Soundex Custom match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same custom Soundex code as the "
        "given name"
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
