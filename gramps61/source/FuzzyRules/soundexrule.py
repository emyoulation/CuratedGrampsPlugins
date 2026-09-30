#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Phonetic Matching Gramplet contributors
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
Soundex person filter rule with name-field granularity, standalone or
as the Fuzzy Matching Gramplet's Soundex encoding system.

Why a second Soundex rule
-------------------------

Gramps' built-in ``HasSoundexName`` ("Soundex match of People with the
<name>") always compares every name field - given, surname, call and
nick names, in the primary and every alternate name - with no way to
narrow it. A search for the surname "Thomas" therefore also returns
everyone whose *given* name is Thomas, and a filter made from the
Fuzzy Matching Gramplet's Soundex results could return more people
than the gramplet itself shows.

This rule uses the same Soundex code (``gramps.gen.soundex.soundex``)
but adds the "Match in:" option shared with the NYSIIS, MRA and
Metaphone rules (see ``phonetic_name_parts.py``). Its default is the
preferred name's surname pieces and call name; also ticking
Given, Nick and Alternatives reproduces the built-in rule's reach.

It registers with the ``FuzzyMatchingEncoder:`` id prefix, so when it
is installed the gramplet uses it for Soundex (encoding and "Define
filter") in place of its hardcoded fallback to the built-in rule. See
``phonetic_codes._load_encoders``.

The class is named ``HasSoundexNames``, not ``HasSoundexName``: rule
classes are made findable as ``gramps.gen.filters.rules.person.<Class>``
so saved filters reload, and reusing the built-in class name would
replace Gramps' own rule there.
"""

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
from gramps.gen.soundex import soundex as _core_soundex

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


#: Registry key - the same id the gramplet's hardcoded Soundex entry
#: uses, so a saved "Encoding system: Soundex" choice keeps working
#: whether or not this rule is installed.
ALGORITHM_ID = "soundex"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Soundex"

#: Tooltip for the Encoding system dropdown.
ALGORITHM_DESCRIPTION = (
    "The classic 4-character genealogy code (e.g. Gramps' own"
    " SoundEx gramplet). Groups names that sound alike when"
    ' spoken, such as "Smith" and "Smyth".'
)


def encode(name: str) -> set[str]:
    """
    Return the (single-element) Soundex code set for ``name``.

    :param name: The name (or any word) to encode.
    :returns: A one-element set with the four-character code that
        :func:`gramps.gen.soundex.soundex` returns.
    """
    try:
        return {_core_soundex(name)}
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Soundex encoding failed for %r, falling back to empty", name)
        return {_core_soundex("")}


# -------------------------------------------------------------------------
#
# HasSoundexNames
#
# -------------------------------------------------------------------------
class HasSoundexNames(Rule):
    """
    Rule that checks for a Soundex match on a person's names, in the
    name fields selected by the "Match in:" option (the preferred name's
    surname pieces and call name by default).
    """

    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("Soundex match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same Soundex code as the given name"
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
