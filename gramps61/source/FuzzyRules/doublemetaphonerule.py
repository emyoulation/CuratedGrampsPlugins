"""
Double Metaphone person filter rule (Lawrence Philips, 2000) - the
second-generation Metaphone, distinct from the single-code Metaphone
this addon's metaphonerule.py already provides. It returns a primary
and (sometimes) a secondary code for the same word - e.g. "Smith"
yields SM0/XMT and "Schmidt" yields XMT/SMT, so the two share XMT -
which maps directly onto encode()'s existing "a word can legitimately
have more than one valid code" contract; no new plumbing needed.

_double_metaphone_raw() below is a close port of Andrew Collins' 2007
Python translation of the original C++ algorithm (itself translated
from Kevin Atkinson's C source), including Matthew Somerville's 2009
bug fixes against the reference implementation - the version long
distributed as dracos/double-metaphone and packaged on PyPI as
`Metaphone`. Its author states the work is public domain. Ported
rather than reconstructed from a description of the algorithm: it
special-cases roughly 100 different contexts for the letter C alone,
exactly the kind of detail a from-memory reimplementation gets subtly
wrong.

Same shape as this folder's other rules otherwise: encode() + a Rule
subclass in the same file, the shared "Match in:" option from
phonetic_name_parts.py (with the same fallback if that file's
missing), and both apply()/apply_to_one() for the Gramps 5.2 vs 6.0+
split - see FuzzyDev.md.
"""

import logging
import re
import unicodedata

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
ALGORITHM_ID = "double_metaphone"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Double Metaphone"

#: Tooltip for the Encoding system dropdown.
ALGORITHM_DESCRIPTION = (
    "The second-generation Metaphone (Lawrence Philips, 2000). Returns"
    " up to two codes per name (e.g. both codes for a German-derived and"
    " an English-derived pronunciation), so it can catch cross-language"
    ' spelling variants plain Metaphone/Soundex miss, e.g. "Smith" vs.'
    ' "Schmidt".'
)

_VOWELS = ("A", "E", "I", "O", "U", "Y")


def _double_metaphone_raw(name):
    """
    Return the ``(primary, secondary)`` Double Metaphone codes for one
    word - ``secondary`` is ``""`` when the word has only one code.

    See the module docstring for where this was ported from.

    :param name: The surname (or any word) to encode.
    :returns: A ``(primary, secondary)`` tuple of code strings.
    """
    # Strip diacritics (NFD-decompose, then drop combining marks), then
    # keep only A-Z - this addon's other rules do the same, and it
    # keeps the indexing below well-defined for any input.
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", name or "")
        if unicodedata.category(c) != "Mn"
    )
    word = re.sub(r"[^A-Za-z]", "", stripped).upper()
    if not word:
        return ("", "")

    is_slavo_germanic = bool(
        re.search(r"W|K|CZ|WITZ", word)
    )

    length = len(word)
    first = 2
    # Pad with dashes so the algorithm's lookahead/lookbehind indexing
    # can run off either end of the real word without special-casing
    # every access.
    padded = "-" * first + word + "------"
    last = first + length - 1
    pos = first
    pri = sec = ""

    if padded[first : first + 2] in ("GN", "KN", "PN", "WR", "PS"):
        pos += 1

    if padded[first] == "X":
        pri = sec = "S"
        pos += 1

    while pos <= last:
        ch = padded[pos]
        nxt = (None, 1)

        if ch in _VOWELS:
            nxt = ("A", 1) if pos == first else (None, 1)

        elif ch == "B":
            nxt = ("P", 2) if padded[pos + 1] == "B" else ("P", 1)

        elif ch == "C":
            if (
                pos > first + 1
                and padded[pos - 2] not in _VOWELS
                and padded[pos - 1 : pos + 2] == "ACH"
                and padded[pos + 2] != "I"
                and (
                    padded[pos + 2] != "E"
                    or padded[pos - 2 : pos + 4] in ("BACHER", "MACHER")
                )
            ):
                nxt = ("K", 2)
            elif pos == first and padded[first : first + 6] == "CAESAR":
                nxt = ("S", 2)
            elif padded[pos : pos + 4] == "CHIA":
                nxt = ("K", 2)
            elif padded[pos : pos + 2] == "CH":
                if pos > first and padded[pos : pos + 4] == "CHAE":
                    nxt = ("K", "X", 2)
                elif (
                    pos == first
                    and (
                        padded[pos + 1 : pos + 6] in ("HARAC", "HARIS")
                        or padded[pos + 1 : pos + 4] in ("HOR", "HYM", "HIA", "HEM")
                    )
                    and padded[first : first + 5] != "CHORE"
                ):
                    nxt = ("K", 2)
                elif (
                    padded[first : first + 4] in ("VAN ", "VON ")
                    or padded[first : first + 3] == "SCH"
                    or padded[pos - 2 : pos + 4] in ("ORCHES", "ARCHIT", "ORCHID")
                    or padded[pos + 2] in ("T", "S")
                    or (
                        (padded[pos - 1] in ("A", "O", "U", "E") or pos == first)
                        and padded[pos + 2]
                        in ("L", "R", "N", "M", "B", "H", "F", "V", "W")
                    )
                ):
                    nxt = ("K", 2)
                else:
                    if pos > first:
                        if padded[first : first + 2] == "MC":
                            nxt = ("K", 2)
                        else:
                            nxt = ("X", "K", 2)
                    else:
                        nxt = ("X", 2)
            elif padded[pos : pos + 2] == "CZ" and padded[pos - 2 : pos + 2] != "WICZ":
                nxt = ("S", "X", 2)
            elif padded[pos + 1 : pos + 4] == "CIA":
                nxt = ("X", 3)
            elif padded[pos : pos + 2] == "CC" and not (
                pos == first + 1 and padded[first] == "M"
            ):
                if padded[pos + 2] in ("I", "E", "H") and padded[pos + 2 : pos + 4] != "HU":
                    if (pos == first + 1 and padded[first] == "A") or padded[
                        pos - 1 : pos + 4
                    ] in ("UCCEE", "UCCES"):
                        nxt = ("KS", 3)
                    else:
                        nxt = ("X", 3)
                else:
                    nxt = ("K", 2)
            elif padded[pos : pos + 2] in ("CK", "CG", "CQ"):
                nxt = ("K", 2)
            elif padded[pos : pos + 2] in ("CI", "CE", "CY"):
                if padded[pos : pos + 3] in ("CIO", "CIE", "CIA"):
                    nxt = ("S", "X", 2)
                else:
                    nxt = ("S", 2)
            else:
                if padded[pos + 1 : pos + 3] in (" C", " Q", " G"):
                    nxt = ("K", 3)
                elif (
                    padded[pos + 1] in ("C", "K", "Q")
                    and padded[pos + 1 : pos + 3] not in ("CE", "CI")
                ):
                    nxt = ("K", 2)
                else:
                    nxt = ("K", 1)

        elif ch == "D":
            if padded[pos : pos + 2] == "DG":
                if padded[pos + 2] in ("I", "E", "Y"):
                    nxt = ("J", 3)
                else:
                    nxt = ("TK", 2)
            elif padded[pos : pos + 2] in ("DT", "DD"):
                nxt = ("T", 2)
            else:
                nxt = ("T", 1)

        elif ch == "F":
            nxt = ("F", 2) if padded[pos + 1] == "F" else ("F", 1)

        elif ch == "G":
            if padded[pos + 1] == "H":
                if pos > first and padded[pos - 1] not in _VOWELS:
                    nxt = ("K", 2)
                elif pos < first + 3:
                    if pos == first:
                        nxt = ("J", 2) if padded[pos + 2] == "I" else ("K", 2)
                    elif (
                        (pos > first + 1 and padded[pos - 2] in ("B", "H", "D"))
                        or (pos > first + 2 and padded[pos - 3] in ("B", "H", "D"))
                        or (pos > first + 3 and padded[pos - 3] in ("B", "H"))
                    ):
                        nxt = (None, 2)
                    elif (
                        pos > first + 2
                        and padded[pos - 1] == "U"
                        and padded[pos - 3] in ("C", "G", "L", "R", "T")
                    ):
                        nxt = ("F", 2)
                    elif pos > first and padded[pos - 1] != "I":
                        nxt = ("K", 2)
                    else:
                        nxt = (None, 2)
                else:
                    if (
                        pos > first + 2
                        and padded[pos - 1] == "U"
                        and padded[pos - 3] in ("C", "G", "L", "R", "T")
                    ):
                        nxt = ("F", 2)
                    elif pos > first and padded[pos - 1] != "I":
                        nxt = ("K", 2)
                    else:
                        nxt = (None, 2)
            elif padded[pos + 1] == "N":
                if pos == first + 1 and padded[first] in _VOWELS and not is_slavo_germanic:
                    nxt = ("KN", "N", 2)
                elif (
                    padded[pos + 2 : pos + 4] != "EY"
                    and padded[pos + 1] != "Y"
                    and not is_slavo_germanic
                ):
                    nxt = ("N", "KN", 2)
                else:
                    nxt = ("KN", 2)
            elif padded[pos + 1 : pos + 3] == "LI" and not is_slavo_germanic:
                nxt = ("KL", "L", 2)
            elif pos == first and (
                padded[pos + 1] == "Y"
                or padded[pos + 1 : pos + 3]
                in ("ES", "EP", "EB", "EL", "EY", "IB", "IL", "IN", "IE", "EI", "ER")
            ):
                nxt = ("K", "J", 2)
            elif (
                (padded[pos + 1 : pos + 3] == "ER" or padded[pos + 1] == "Y")
                and padded[first : first + 6] not in ("DANGER", "RANGER", "MANGER")
                and padded[pos - 1] not in ("E", "I")
                and padded[pos - 1 : pos + 2] not in ("RGY", "OGY")
            ):
                nxt = ("K", "J", 2)
            elif padded[pos + 1] in ("E", "I", "Y") or padded[pos - 1 : pos + 3] in (
                "AGGI",
                "OGGI",
            ):
                if (
                    padded[first : first + 4] in ("VON ", "VAN ")
                    or padded[first : first + 3] == "SCH"
                    or padded[pos + 1 : pos + 3] == "ET"
                ):
                    nxt = ("K", 2)
                else:
                    nxt = ("J", 2) if padded[pos + 1 : pos + 5] == "IER " else ("J", "K", 2)
            elif padded[pos + 1] == "G":
                nxt = ("K", 2)
            else:
                nxt = ("K", 1)

        elif ch == "H":
            if (pos == first or padded[pos - 1] in _VOWELS) and padded[pos + 1] in _VOWELS:
                nxt = ("H", 2)
            else:
                nxt = (None, 1)

        elif ch == "J":
            if padded[pos : pos + 4] == "JOSE" or padded[first : first + 4] == "SAN ":
                if (pos == first and padded[pos + 4] == " ") or padded[
                    first : first + 4
                ] == "SAN ":
                    nxt = ("H",)
                else:
                    nxt = ("J", "H")
            elif pos == first and padded[pos : pos + 4] != "JOSE":
                nxt = ("J", "A")
            else:
                if padded[pos - 1] in _VOWELS and not is_slavo_germanic and padded[
                    pos + 1
                ] in ("A", "O"):
                    nxt = ("J", "H")
                elif pos == last:
                    nxt = ("J", " ")
                elif padded[pos + 1] not in (
                    "L",
                    "T",
                    "K",
                    "S",
                    "N",
                    "M",
                    "B",
                    "Z",
                ) and padded[pos - 1] not in ("S", "K", "L"):
                    nxt = ("J",)
                else:
                    nxt = (None,)
            nxt = nxt + (2 if padded[pos + 1] == "J" else 1,)

        elif ch == "K":
            nxt = ("K", 2) if padded[pos + 1] == "K" else ("K", 1)

        elif ch == "L":
            if padded[pos + 1] == "L":
                if (
                    pos == last - 2
                    and padded[pos - 1 : pos + 3] in ("ILLO", "ILLA", "ALLE")
                ) or (
                    (
                        padded[last - 1 : last + 1] in ("AS", "OS")
                        or padded[last] in ("A", "O")
                    )
                    and padded[pos - 1 : pos + 3] == "ALLE"
                ):
                    nxt = ("L", " ", 2)
                else:
                    nxt = ("L", 2)
            else:
                nxt = ("L", 1)

        elif ch == "M":
            if (
                padded[pos + 1 : pos + 4] == "UMB"
                and (pos + 1 == last or padded[pos + 2 : pos + 4] == "ER")
            ) or padded[pos + 1] == "M":
                nxt = ("M", 2)
            else:
                nxt = ("M", 1)

        elif ch == "N":
            nxt = ("N", 2) if padded[pos + 1] == "N" else ("N", 1)

        elif ch == "P":
            if padded[pos + 1] == "H":
                nxt = ("F", 2)
            elif padded[pos + 1] in ("P", "B"):
                nxt = ("P", 2)
            else:
                nxt = ("P", 1)

        elif ch == "Q":
            nxt = ("K", 2) if padded[pos + 1] == "Q" else ("K", 1)

        elif ch == "R":
            if (
                pos == last
                and not is_slavo_germanic
                and padded[pos - 2 : pos] == "IE"
                and padded[pos - 4 : pos - 2] not in ("ME", "MA")
            ):
                nxt = ("", "R")
            else:
                nxt = ("R",)
            nxt = nxt + (2 if padded[pos + 1] == "R" else 1,)

        elif ch == "S":
            if padded[pos - 1 : pos + 2] in ("ISL", "YSL"):
                nxt = (None, 1)
            elif pos == first and padded[first : first + 5] == "SUGAR":
                nxt = ("X", "S", 1)
            elif padded[pos : pos + 2] == "SH":
                if padded[pos + 1 : pos + 5] in ("HEIM", "HOEK", "HOLM", "HOLZ"):
                    nxt = ("S", 2)
                else:
                    nxt = ("X", 2)
            elif padded[pos : pos + 3] in ("SIO", "SIA") or padded[pos : pos + 4] == "SIAN":
                nxt = ("S", "X", 3) if not is_slavo_germanic else ("S", 3)
            elif (
                pos == first and padded[pos + 1] in ("M", "N", "L", "W")
            ) or padded[pos + 1] == "Z":
                nxt = ("S", "X")
                nxt = nxt + (2 if padded[pos + 1] == "Z" else 1,)
            elif padded[pos : pos + 2] == "SC":
                if padded[pos + 2] == "H":
                    if padded[pos + 3 : pos + 5] in ("OO", "ER", "EN", "UY", "ED", "EM"):
                        if padded[pos + 3 : pos + 5] in ("ER", "EN"):
                            nxt = ("X", "SK", 3)
                        else:
                            nxt = ("SK", 3)
                    elif (
                        pos == first
                        and padded[first + 3] not in _VOWELS
                        and padded[first + 3] != "W"
                    ):
                        nxt = ("X", "S", 3)
                    else:
                        nxt = ("X", 3)
                elif padded[pos + 2] in ("I", "E", "Y"):
                    nxt = ("S", 3)
                else:
                    nxt = ("SK", 3)
            elif pos == last and padded[pos - 2 : pos] in ("AI", "OI"):
                nxt = ("", "S", 1)
            else:
                nxt = ("S",)
                nxt = nxt + (2 if padded[pos + 1] in ("S", "Z") else 1,)

        elif ch == "T":
            if padded[pos : pos + 4] == "TION":
                nxt = ("X", 3)
            elif padded[pos : pos + 3] in ("TIA", "TCH"):
                nxt = ("X", 3)
            elif padded[pos : pos + 2] == "TH" or padded[pos : pos + 3] == "TTH":
                if padded[pos + 2 : pos + 4] in ("OM", "AM") or padded[
                    first : first + 4
                ] in ("VON ", "VAN ") or padded[first : first + 3] == "SCH":
                    nxt = ("T", 2)
                else:
                    nxt = ("0", "T", 2)
            elif padded[pos + 1] in ("T", "D"):
                nxt = ("T", 2)
            else:
                nxt = ("T", 1)

        elif ch == "V":
            nxt = ("F", 2) if padded[pos + 1] == "V" else ("F", 1)

        elif ch == "W":
            if padded[pos : pos + 2] == "WR":
                nxt = ("R", 2)
            elif pos == first and (padded[pos + 1] in _VOWELS or padded[pos : pos + 2] == "WH"):
                nxt = ("A", "F", 1) if padded[pos + 1] in _VOWELS else ("A", 1)
            elif (
                (pos == last and padded[pos - 1] in _VOWELS)
                or padded[pos - 1 : pos + 4] in ("EWSKI", "EWSKY", "OWSKI", "OWSKY")
                or padded[first : first + 3] == "SCH"
            ):
                nxt = ("", "F", 1)
            elif padded[pos : pos + 4] in ("WICZ", "WITZ"):
                nxt = ("TS", "FX", 4)
            else:
                nxt = (None, 1)

        elif ch == "X":
            if pos == last and (
                padded[pos - 3 : pos] in ("IAU", "EAU") or padded[pos - 2 : pos] in ("AU", "OU")
            ):
                nxt = (None,)
            else:
                nxt = ("KS",)
            nxt = nxt + (2 if padded[pos + 1] in ("C", "X") else 1,)

        elif ch == "Z":
            if padded[pos + 1] == "H":
                nxt = ("J",)
            elif padded[pos + 1 : pos + 3] in ("ZO", "ZI", "ZA") or (
                is_slavo_germanic and pos > first and padded[pos - 1] != "T"
            ):
                nxt = ("S", "TS")
            else:
                nxt = ("S",)
            nxt = nxt + (2 if padded[pos + 1] in ("Z", "H") else 1,)

        if len(nxt) == 2:
            if nxt[0]:
                pri += nxt[0]
                sec += nxt[0]
            pos += nxt[1]
        elif len(nxt) == 3:
            if nxt[0]:
                pri += nxt[0]
            if nxt[1]:
                sec += nxt[1]
            pos += nxt[2]
        else:
            pos += 1

    return (pri, "") if pri == sec else (pri, sec)


def encode(name):
    """
    Return the Double Metaphone code set for ``name`` - one element if
    the primary and secondary codes match or the secondary is empty,
    otherwise both.

    :param name: The surname (or any word) to encode.
    :returns: A one- or two-element set of code strings.
    """
    try:
        primary, secondary = _double_metaphone_raw(name)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Double Metaphone encoding failed for %r, falling back", name)
        return {""}
    codes = {primary, secondary} if secondary else {primary}
    return codes or {""}


# -------------------------------------------------------------------------
#
# HasDoubleMetaphoneNames
#
# -------------------------------------------------------------------------
class HasDoubleMetaphoneNames(Rule):
    """
    Rule that checks for a Double Metaphone match on a person's names,
    in the name fields selected by the "Match in:" option (the
    preferred name's surname pieces and call name by default - same as
    HasSoundexNames). A match against either the primary or the
    secondary code of the given name counts.
    """

    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("Double Metaphone match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same Double Metaphone code as the "
        "given name"
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
            either target code.
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
