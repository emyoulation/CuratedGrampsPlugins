"""
Phonex person filter rule - a Soundex variant tuned for English/British
surnames (A.J. Lait and B. Randell, "An Assessment of Name Matching
Algorithms", 1996). Ported from the peer-reviewed R `phonics` package's
implementation (Howard, JSS 2020), not reconstructed from memory, since
the ordering of the letter-folding rules below is easy to get subtly
wrong (e.g. R/L only turn into a digit when *not* followed by a vowel
or at the end of the word).

Same shape as soundexrule.py: encode() + a Rule subclass in the same
file, the shared "Match in:" option from phonetic_name_parts.py (with
the same fallback if that file's missing), and both apply()/
apply_to_one() for the Gramps 5.2 vs 6.0+ split - see FuzzyDev.md.
"""

import logging
import re

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.filters.rules import Rule

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.gettext

LOG = logging.getLogger(__name__)

# "Match in:" option, shared with the other phonetic rules - see
# soundexrule.py for the reasoning behind this guarded import and its
# fallback.
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

    def pad_args(arg):
        """Fallback: return the rule arguments unchanged."""
        return list(arg or [])

    def parse_parts(text):
        """Fallback: no "Match in:" option, so no part keys."""
        del text
        return frozenset()

    def person_matches(person, keys, target_codes, encoder):
        """Fallback: compare each surname piece of the preferred name."""
        del keys
        if not target_codes:
            return False
        surnames = person.get_primary_name().get_surname_list()
        words = [piece.get_surname() for piece in surnames]
        return any(encoder(w) & target_codes for w in words if w and w.strip())


#: Registry key - see phonetic_codes._ENCODER_ID_PREFIX.
ALGORITHM_ID = "phonex"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Phonex"

#: Tooltip for the Encoding system dropdown.
ALGORITHM_DESCRIPTION = (
    "An improved Soundex variant (Lait & Randell, 1996) tuned for"
    " English/British surnames - folds together a few extra leading"
    ' patterns plain Soundex treats as different, e.g. "Kn-", "Wr-"'
    ' and "Ph-".'
)

#: Codes are letter + up to 3 digits, zero-padded, the same shape as
#: Gramps' own Soundex codes.
_MAX_CODE_LEN = 4

#: Letters this algorithm drops or treats as vowels when deciding
#: whether R/L are followed by "a vowel" - matches the reference R
#: implementation's own character class exactly (it includes H and W
#: alongside the true vowels and Y).
_VOWELISH = "AEHIOUWY"


def _phonex_raw(name, max_code_len=_MAX_CODE_LEN):
    """
    Compute the raw Phonex code for one word.

    Steps (see the module docstring for the reference this was ported
    from): normalise to uppercase A-Z only; strip a trailing run of
    S's; fold a handful of leading letters/pairs (Kn-, Wr-, Ph-, a
    leading H, a leading vowel, and single-letter P/V/K/Q/J/Z); keep
    the first letter as-is; then fold the rest of the word to digits
    (R and L only when not followed by a vowel-ish letter or at the
    end of the word; M/N absorbing a following D/G; B/F/P/V; D/T
    unless followed by C; C/G/J/K/Q/S/X/Z); collapse repeated digits;
    and zero-pad/truncate to ``max_code_len``.

    :param name: The surname (or any word) to encode.
    :param max_code_len: Length to zero-pad/truncate the code to.
    :returns: The Phonex code, or ``""`` if nothing alphabetic was
        found to encode.
    """
    word = (name or "").upper()
    # A handful of accented Latin letters this algorithm is defined
    # over (see the R phonics package's own docs); anything else is
    # simply not alphabetic as far as this algorithm is concerned.
    word = word.replace("Ä", "A").replace("Ü", "U").replace("Ö", "O")
    word = word.replace("ß", "S")
    word = re.sub(r"[^A-Z]", "", word)
    if not word:
        return ""

    word = re.sub(r"S+$", "", word)
    word = re.sub(r"^KN", "N", word)
    word = re.sub(r"^WR", "R", word)
    word = re.sub(r"^PH", "F", word)
    word = re.sub(r"^H", "", word)
    word = re.sub(r"^[EIOUY]", "A", word)
    word = re.sub(r"^P", "B", word)
    word = re.sub(r"^V", "F", word)
    word = re.sub(r"^[KQ]", "C", word)
    word = re.sub(r"^J", "G", word)
    word = re.sub(r"^Z", "S", word)
    if not word:
        return ""

    first, rest = word[0], word[1:]

    # R -> 6, unless followed by a vowel-ish letter or at the end
    # (in which case it's dropped, along with any other stray R's).
    rest = re.sub(rf"R[{_VOWELISH}]|R$", "6", rest)
    rest = rest.replace("R", "")

    # L -> 4, same "not before a vowel, not at the end" rule as R.
    rest = re.sub(rf"L[{_VOWELISH}]|L$", "4", rest)
    rest = rest.replace("L", "")

    # Whatever vowel-ish letters are left (not already consumed above)
    # are simply dropped.
    rest = re.sub(f"[{_VOWELISH}]", "", rest)

    rest = re.sub(r"[MN][DG]*", "5", rest)
    rest = re.sub(r"[BFPV]", "1", rest)

    rest = re.sub(r"[DT]C", "C", rest)  # DC/TC -> C: silent before C
    rest = re.sub(r"[DT]", "3", rest)

    rest = re.sub(r"[CGJKQSXZ]", "2", rest)

    rest = re.sub(r"([0-6])\1+", r"\1", rest)  # collapse repeats

    code = first + rest
    zeros = "0" * max_code_len
    code = (code + zeros)[:max_code_len]
    return "" if code == zeros else code


def encode(name):
    """
    Return the (single-element) Phonex code set for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: A one-element set with the Phonex code.
    """
    try:
        return {_phonex_raw(name)}
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Phonex encoding failed for %r, falling back to empty", name)
        return {""}


# -------------------------------------------------------------------------
#
# HasPhonexNames
#
# -------------------------------------------------------------------------
class HasPhonexNames(Rule):
    """
    Rule that checks for a Phonex match on a person's names, in the
    name fields selected by the "Match in:" option (the preferred
    name's surname pieces and call name by default - same as
    HasSoundexNames).
    """

    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("Phonex match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same Phonex code as the given name"
    )
    category = _("General filters")
    allow_regex = False

    def __init__(self, arg, use_regex=False, use_case=False):
        """
        Create the rule.

        :param arg: ``[name, match_in]``; ``match_in`` may be omitted.
        :param use_regex: Unused; this rule does not support regexes.
        :param use_case: Unused.
        """
        super().__init__(arg, use_regex, use_case)
        self._target_codes = set()
        self._parts = None

    def set_list(self, arg):
        """
        Store the rule values, filling in the "Match in:" option for
        one-argument filters (or callers passing only the name), which
        then get the default: the preferred name's surname and call
        name.

        :param arg: The rule's argument list.
        """
        super().set_list(pad_args(arg))

    def prepare(self, db, user):
        """
        Encode the target name and read the "Match in:" option once.

        :param db: The active database. Unused.
        :param user: The active gramps.gen.user.User. Unused.
        """
        del db, user
        self._target_codes = (
            encode(self.list[0]) if self.list and self.list[0] else set()
        )
        self._parts = parse_parts(self.list[1] if len(self.list) > 1 else "")

    def apply_to_one(self, db, obj):
        """
        Apply the rule. Return True on a match.

        :param db: The active database. Unused.
        :param obj: The gramps.gen.lib.Person being tested.
        :returns: True if any selected name field of ``obj`` encodes to
            the target code.
        """
        if self._parts is None:  # applied without prepare()
            self.prepare(db, None)
        return person_matches(
            obj, self._parts or frozenset(), self._target_codes, encode
        )

    def apply(self, db, obj):
        """
        Alias for apply_to_one(), for Gramps 5.2, whose filters call
        ``apply``; Gramps 6.0+ calls ``apply_to_one``.

        :param db: The active database. Unused.
        :param obj: The gramps.gen.lib.Person being tested.
        :returns: See apply_to_one().
        """
        return self.apply_to_one(db, obj)
