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
Phonex (French) person filter rule with name-field granularity,
standalone or as the Fuzzy Matching Gramplet's Phonex (French)
encoding system.

The encoder
-----------

Phonex is the French phonetic algorithm published by Frederic Brouard
on 31 March 1999, with Florence Marquis, speech therapist. See
https://sqlpro.developpez.com/cours/soundex/ for the sixteen rewriting
steps and the reference implementation.

Note that an unrelated algorithm by Lait and Randell, built for
English names, also goes by the name Phonex. This one is the French
algorithm, and the two share nothing but the word.

French spelling writes one sound many ways: the nasal of "Martin" is
also written "-ein", "-aim" and "-in"; "Dupont" and "Dupond" sound
alike; "Guillaume" starts with the sound of "K". A code built for
English, such as Soundex, keeps those spellings apart. Phonex rewrites
a name through a chain of French spelling-to-sound rules and returns
what is left, so that names pronounced alike share one code.

It is a letter code of no fixed length, not a Soundex-style
four-character code, and the digits 1 to 5 in a code stand for sounds
rather than for letter groups: 1 is the nasal of "an / on / en", 2 the
sound of "oi", 3 the sound of "ou", 4 the nasal of "in / ain / ein",
and 5 the sound of "ch".

Brouard adds two further steps that turn the finished code into a
base-22 floating point number. They are left out here, because they
only pack the same code into a number, and the code itself is what a
match compares.

Accents are folded away before the chain runs, as Brouard's own
``prepare`` function folds them, so "Emile" and "Émile" encode alike -
which matters where a tree mixes accented and unaccented spellings of
one name. The cedilla is the exception and is read as "S" first, again
following ``prepare``: "Garcon" and "Garçon" are the same name, but a
bare "C" there would read as the sound of "K".

Two places depart from the published step order, both marked in
``encode`` below: a "C" that sounds like "S" is read before the nasal
step rather than after it, and a nasal digit is not accepted to the
left of the intervocalic "S" rule. Without the first, "Vincent" takes
a "K" sound; without the second, "Vincent" and "Vinsant" do not meet.

Name fields
-----------

The rule adds the "Match in:" option shared with the rules of the
FuzzyRules addon (see ``phonetic_name_parts.py``). Its default is the
preferred name's surname pieces and call name.

It registers with the ``FuzzyMatchingEncoder:`` id prefix, so when it
is installed the Fuzzy Matching Gramplet offers Phonex (French) as an
encoding system and uses this rule for "Define filter". See
``phonetic_codes._load_encoders``.
"""

from __future__ import annotations

# ------------------------
# Python modules
# ------------------------
import logging
import re
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
ALGORITHM_ID = "phonex_french"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Phonex (French)"

#: Tooltip for the Encoding system dropdown.
ALGORITHM_DESCRIPTION = (
    "The French Phonex algorithm of Frederic Brouard (1999), a chain of"
    " French spelling-to-sound rules. Groups spellings that sound alike"
    ' in French, such as "Dupont" and "Dupond", or "Martin" and "Martain".'
)

#: Placeholder standing for a "C" that sounds like "S", held apart
#: from a written "S" until the intervocalic rule has run. It never
#: reaches a finished code.
_SOFT_C = "6"

#: Nasal vowel groups and the digit each one encodes to, applied only
#: where no vowel (or earlier sound digit) follows.
_NASALS = (
    ("AN", "1"),
    ("ON", "1"),
    ("AM", "1"),
    ("EN", "1"),
    ("EM", "1"),
    ("IN", "4"),
)

#: Single letters folded onto the consonant they sound like, applied
#: after every group rule has run.
_FINAL_LETTERS = (
    ("A", "O"),
    ("D", "T"),
    ("P", "T"),
    ("J", "G"),
    ("B", "F"),
    ("V", "F"),
    ("M", "N"),
)


def _fold_accents(name: str) -> str:
    """
    Return ``name`` upper-cased and reduced to plain ASCII letters.

    The cedilla is read before the fold: "Ç" sounds like "S", while the
    fold would leave a bare "C", which later reads as the sound of "K".

    :param name: The name (or any word) to fold.
    :returns: The upper-case ASCII form of the name.
    """
    text = str(name).upper().strip().replace("Ç", "S")
    return unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")


def _collapse_repeats(code: str) -> str:
    """
    Return ``code`` with runs of one repeated character reduced to one.

    :param code: A partly encoded name.
    :returns: The same text with no character repeated side by side.
    """
    out: list[str] = []
    for char in code:
        if not out or out[-1] != char:
            out.append(char)
    return "".join(out)


def encode(name: str) -> set[str]:
    """
    Return the (single-element) French Phonex code set for ``name``.

    :param name: The name (or any word) to encode.
    :returns: A one-element set holding the code, or an empty set for a
        name with no letters in it.
    """
    try:
        code = _fold_accents(name)
        if not code:
            return set()

        # "Y" is written for the sound of "I"; the chain below writes a
        # "Y" of its own for the sound of a closed "E", so this runs first.
        code = code.replace("Y", "I")

        # An "H" is silent unless it belongs to "CH", "SH" or "PH".
        code = re.sub(r"(?<![CSP])H", "", code)
        code = code.replace("PH", "F")

        # "G" before "a", "ai", "ain" or "aim" sounds like "K".
        code = re.sub(r"G(AI?[NM])", r"K\1", code)

        # A nasal group followed by a vowel is not nasal at all.
        code = re.sub(r"[AE]I[NM](?=[AEIOU])", "YN", code)

        # "C" before "e" or "i" sounds like "S". It is read here, while
        # that "e" or "i" is still written, but held as a placeholder:
        # the "S" of "Vincent" is not the "Z" of "Lisa", so it must not
        # reach the intervocalic rule below.
        code = re.sub(r"C(?=[EI])", _SOFT_C, code)

        # Vowel groups that stand for one sound.
        code = code.replace("EAU", "O").replace("OUA", "2")
        for group in ("EIN", "AIN", "EIM", "AIM"):
            code = code.replace(group, "4")

        # Groups that sound like a closed "E".
        code = code.replace("AI", "Y").replace("EI", "Y")
        code = code.replace("ER", "YR").replace("ESS", "YS")
        code = code.replace("ET", "YT").replace("EZ", "YZ")

        # Nasal vowels, where no vowel or earlier sound digit follows.
        for group, digit in _NASALS:
            code = re.sub(group + r"(?![AEIOU1234])", digit, code)

        # An "S" between two vowels sounds like "Z". A nasal digit may
        # stand to the right, since it began with a vowel, but never to
        # the left, where it ends in the "n" of "pensee" - a letter,
        # not a vowel, so the "s" there keeps its own sound.
        code = re.sub(r"(?<=[AEIOUY])S(?=[AEIOUY1234])", "Z", code)
        code = code.replace(_SOFT_C, "S")

        # The remaining vowel groups.
        code = code.replace("OE", "E").replace("EU", "E").replace("AU", "O")
        code = code.replace("OI", "2").replace("OU", "3")

        # The sound of "ch". "SCH" runs first, or "CH" would claim it.
        code = code.replace("SCH", "5").replace("CH", "5").replace("SH", "5")
        code = code.replace("SS", "S").replace("SC", "S")

        # Any "C" still written sounds like "K". "QU" and "GU" run
        # before the bare "Q", which would otherwise leave a "U".
        code = code.replace("QU", "K").replace("GU", "K").replace("Q", "K")
        code = code.replace("GA", "KA").replace("GO", "KO").replace("GY", "KY")
        code = code.replace("C", "K")

        for old, new in _FINAL_LETTERS:
            code = code.replace(old, new)

        code = _collapse_repeats(code)

        # A final "t" or "x" is not spoken.
        code = re.sub(r"[TX]$", "", code)

        return {code} if code else set()
    except Exception:  # pylint: disable=broad-except
        LOG.debug("French Phonex encoding failed for %r, returning no code", name)
        return set()


# -------------------------------------------------------------------------
#
# HasPhonexFrenchNames
#
# -------------------------------------------------------------------------
class HasPhonexFrenchNames(Rule):
    """
    Rule that checks for a French Phonex match on a person's names, in
    the name fields selected by the "Match in:" option (the preferred
    name's surname pieces and call name by default).
    """

    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("Phonex (French) match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same French Phonex code as the "
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
