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
Match Rating Approach (MRA) person filter rule, standalone or as part
of the Fuzzy Matching Gramplet.

Using this rule on its own
--------------------------

This adds "MRA match of People with the <names>" to the
standard Filter Editor's "Add Rule" dialog for Person filters, under
General filters. Give it a name and it matches every person whose selected
name fields (by default, the preferred name's surname pieces
and call name) have the same Match Rating Approach codex - no
gramplet required for this part; it works anywhere a Person filter
rule can be used (Filter Gramplet, Filter sidebar, reports, etc.).

**Important limitation, worth knowing before using this rule**: MRA's
real matching power comes from its own *comparison* algorithm, which
tolerates codexes that are similar but not identical (within a
length- and sum-dependent threshold - see the `Match rating approach
<https://en.wikipedia.org/wiki/Match_rating_approach>`_ article for
the exact rules). This rule, like the Fuzzy Matching Gramplet's own
on-screen matching, groups by exact codex equality - it does not
implement that threshold comparison. Under plain equality, MRA's
codex is comparatively literal: for example, "SMITH" and "SMYTH"
encode to different codexes here (``SMTH`` vs ``SMYTH``) and so would
not match, even though MRA's own comparison algorithm is often cited
as successfully matching that exact pair.

The Fuzzy Matching Gramplet also uses this rule for its own "Define
filter" action when Match Rating Approach is the selected Encoding
system, and calls this module's :func:`encode` directly for its own
on-screen matching - both uses share the exact same encoding logic in
this one file, so they can never quietly disagree with each other.
See ``phonetic_codes.py`` for how the gramplet discovers this module:
it asks Gramps' own plugin registry for every ``RULE``-type plugin
whose ``id`` starts with ``phonetic_codes._ENCODER_ID_PREFIX`` (see
this file's own ``.gpr.py`` registration) - identity by id, not by
shared folder location, so this rule could move to its own
independently distributed addon without breaking discovery, as long
as its registration keeps that same id prefix.

About Match Rating Approach
----------------------------

MRA is a Western Airlines-developed algorithm (hence its other name,
"Personal Numeric Identifier"/PNI) commonly used for genealogical
name matching. Its encoding step ("codex") is simple: drop every
vowel except one that begins the word, collapse repeated consonants,
and keep only the first and last three characters if that leaves more
than six.

This is a from-scratch Python implementation, ported from - and
validated against 48 names run through - the real
``match_rating_codex`` function in the
`jellyfish <https://github.com/jamesturk/jellyfish>`_ library
(version 0.8.9), a mature, widely-used reference:
https://github.com/jamesturk/jellyfish/blob/v0.8.9/jellyfish/_jellyfish.py

Unlike ``jellyfish.match_rating_codex``, :func:`encode` strips
non-letter characters before encoding instead of raising on them -
real surnames routinely contain apostrophes, hyphens, and accented
letters, and this must never raise. A stale documented example was
caught exactly this way while validating this port: jellyfish's own
README claims ``match_rating_codex('Jellyfish') == 'JLLFSH'``; the
actual installed 0.8.9 library returns ``'JLYFSH'``, confirmed by
running it directly rather than trusting the documentation. See
``test/matchratingrule_test.py``, whose reference vectors were
produced the same way - by running the real library, not copied from
its docs.
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


#: Registry key used by phonetic_codes.py and the gramplet's own saved
#: Encoding system setting. Treat as stable once shipped: renaming it
#: is the same as removing this algorithm and adding a new one.
ALGORITHM_ID = "match_rating"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Match Rating Approach"

#: Shown as a tooltip on the Encoding system dropdown when this
#: algorithm is selected.
ALGORITHM_DESCRIPTION = (
    "A compact code (drop non-leading vowels, collapse repeated"
    " consonants). This gramplet groups results by exact code"
    " equality, like the other Encoding systems - it does not use"
    " Match Rating Approach's own similarity-threshold comparison, so"
    " it is more literal here than its reputation for matching names"
    ' like "Smith"/"Smyth" might suggest.'
)

_VOWELS = "AEIOU"


def _clean(name: str) -> str:
    """
    Keep only letters from ``name``, uppercased.

    :param name: The raw input.
    :returns: ``name`` with every non-letter character removed,
        uppercased.
    """
    return "".join(char for char in name if char.isalpha()).upper()


def _match_rating_codex(name: str) -> str:
    """
    Compute the Match Rating Approach codex for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: The codex: every consonant, with immediate repeats
        collapsed to one, plus a leading vowel if the word starts with
        one, reduced to the first and last three characters if that
        would otherwise be longer than six.
    """
    cleaned = _clean(name)
    if not cleaned:
        return ""

    codex_chars = []
    prev = None
    for index, char in enumerate(cleaned):
        is_vowel = char in _VOWELS
        keep_as_leading_vowel = index == 0 and is_vowel
        keep_as_new_consonant = (not is_vowel) and char != prev
        if keep_as_leading_vowel or keep_as_new_consonant:
            codex_chars.append(char)
        prev = char

    if len(codex_chars) > 6:
        return "".join(codex_chars[:3] + codex_chars[-3:])
    return "".join(codex_chars)


def encode(name: str) -> set[str]:
    """
    Return the (single-element) Match Rating Approach codex set for
    ``name``.

    :param name: The surname (or any word) to encode.
    :returns: A one-element set containing the codex.
    """
    try:
        return {_match_rating_codex(name)}
    except Exception:  # pylint: disable=broad-except
        LOG.debug(
            "Match Rating Approach encoding failed for %r, falling back to empty",
            name,
        )
        return {_match_rating_codex("")}


# -------------------------------------------------------------------------
#
# HasMatchRatingName
#
# -------------------------------------------------------------------------
class HasMatchRatingName(Rule):
    """
    Rule that checks for a Match Rating Approach match on a person's
    names.

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
    name = _("MRA match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same Match Rating Approach (MRA) "
        "codex as the given name"
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
