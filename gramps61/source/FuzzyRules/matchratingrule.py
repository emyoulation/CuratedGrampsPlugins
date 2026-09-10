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

This adds "Match Rating Approach match of People with the <surname>" to the
standard Filter Editor's "Add Rule" dialog for Person filters, under
General filters. Give it a surname and it matches every person whose
primary surname has the same Match Rating Approach codex - no
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

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger(__name__)

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
    Rule that checks for a Match Rating Approach codex match of a
    person's primary surname.

    Unlike Gramps' built-in ``HasSoundexName``, which matches across
    first name, surname, call name, and nickname in both primary and
    alternate names, this deliberately checks the primary name's
    surname only, matching what the Fuzzy Matching Gramplet's own
    "Surname" field and Matches columns actually search.
    """

    labels = [_("Surname:")]
    name = _("Match Rating Approach match of People with the <surname>")
    description = _(
        "Matches people whose primary surname has a specified Match"
        " Rating Approach codex"
    )
    category = _("General filters")
    allow_regex = False

    def __init__(self, arg, use_regex=False, use_case=False):
        super().__init__(arg, use_regex, use_case)
        self._target_codes = None

    def prepare(self, _db, _user):
        """
        Prepare the rule. Things we only want to do once.

        :param _db: The active database. Unused: the target codes only
            depend on the typed name, not on any database content.
        :param _user: The active :class:`gramps.gen.user.User`. Unused.
        """
        self._target_codes = (
            encode(self.list[0]) if self.list and self.list[0] else set()
        )

    def apply_to_one(self, _db, obj) -> bool:
        """
        Apply the rule. Return True on a match.

        :param _db: The active database. Unused.
        :param obj: The :class:`gramps.gen.lib.Person` being tested.
        :returns: True if ``obj``'s primary surname's Match Rating
            Approach codex intersects the target codes.
        """
        if not self._target_codes:
            return False
        surname = obj.get_primary_name().get_surname()
        return bool(encode(surname) & self._target_codes)

    def apply(self, db, obj) -> bool:
        """
        Alias for :meth:`apply_to_one`, needed for Gramps 5.2
        compatibility: Gramps 5.2's own filter-execution code
        (``gramps.gen.filters._genericfilter.GenericFilter``) calls
        ``rule.apply(db, obj)`` throughout - confirmed directly in the
        Gramps 5.2 source (``maintenance/gramps52`` branch), not
        assumed - whereas Gramps 6.0+ renamed this to
        ``apply_to_one`` and calls that instead (also confirmed
        directly, against the real ``gramps.gen.filters.rules.person``
        ``HasSoundexName`` on each branch). Defining both, rather than
        picking one, is what lets this one rule class work correctly
        across the whole ``(5.2.0, 6.2.0)`` Gramps range this addon's
        own ``.gpr.py`` declares, without needing separate per-version
        rule files.

        :param db: The active database. Unused; forwarded as-is.
        :param obj: The :class:`gramps.gen.lib.Person` being tested.
        :returns: See :meth:`apply_to_one`.
        """
        return self.apply_to_one(db, obj)
