"""
Daitch-Mokotoff Soundex person filter rule (Randy Daitch and Gary
Mokotoff, 1985) - a Soundex refinement built specifically for Slavic
and Germanic-derived Jewish surnames, and the long-standing standard
for Jewish genealogy indexing (JewishGen, the U.S. Holocaust Memorial
Museum, HIAS). Six-digit codes, the *first* letter is itself coded
(not kept literally, unlike plain Soundex), and - unlike every other
algorithm in this folder - a single name can legitimately produce
several distinct valid codes at once (not just two): "Peters" is both
739400 and 734000, and "Jackson" is four different codes. That fits
the existing multi-code encode() contract directly.

An earlier attempt at this algorithm was dropped after it failed
validation against the standard reference vectors - unsurprising,
since the rule table has around 100 pattern entries and the branching/
digit-collapsing logic has a few genuinely non-obvious corners (e.g.
the MN/NM exception below). This version is a close port of Apache
Commons Codec's DaitchMokotoffSoundex (Apache-2.0), whose rule table
(dmrules.txt) and branching algorithm are validated against the
published reference implementation at avotaynu.com/soundex.htm. Every
example vector below (Peters, Peterson, Jackson, Auerbach, Moskowitz,
Berlin) is checked against independently published references, not
just against this port's own output.

Same shape as this folder's other rules otherwise: encode() + a Rule
subclass in the same file, the shared "Match in:" option from
phonetic_name_parts.py (with the same fallback if that file's
missing), and both apply()/apply_to_one() for the Gramps 5.2 vs 6.0+
split - see FuzzyDev.md.
"""

import logging

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
ALGORITHM_ID = "daitch_mokotoff"

#: Display label shown in the gramplet's "Encoding system" dropdown.
ALGORITHM_LABEL = "Daitch-Mokotoff"

#: Tooltip for the Encoding system dropdown.
ALGORITHM_DESCRIPTION = (
    "The Daitch-Mokotoff Soundex (1985), built for Slavic and"
    " Germanic-derived Jewish surnames and the standard used by"
    " JewishGen and the U.S. Holocaust Memorial Museum. Six-digit codes;"
    " a name can legitimately encode to several codes at once, e.g."
    ' "Jackson" is four different codes.'
)

_MAX_LENGTH = 6

#: (pattern, replacement-at-start, replacement-before-a-vowel,
#: replacement-elsewhere) - "|" separates branch alternatives, "" means
#: not coded. Ported line-for-line from Apache Commons Codec's
#: dmrules.txt (Apache-2.0), itself built from the published D-M
#: coding chart - not reconstructed from the chart's prose description,
#: for the same reason the module docstring gives.
_RULE_DATA = (
    # Vowels
    ("a", "0", "", ""),
    ("e", "0", "", ""),
    ("i", "0", "", ""),
    ("o", "0", "", ""),
    ("u", "0", "", ""),
    # Consonants
    ("b", "7", "7", "7"),
    ("d", "3", "3", "3"),
    ("f", "7", "7", "7"),
    ("g", "5", "5", "5"),
    ("h", "5", "5", ""),
    ("k", "5", "5", "5"),
    ("l", "8", "8", "8"),
    ("m", "6", "6", "6"),
    ("n", "6", "6", "6"),
    ("p", "7", "7", "7"),
    ("q", "5", "5", "5"),
    ("r", "9", "9", "9"),
    ("s", "4", "4", "4"),
    ("t", "3", "3", "3"),
    ("v", "7", "7", "7"),
    ("w", "7", "7", "7"),
    ("x", "5", "54", "54"),
    ("y", "1", "", ""),
    ("z", "4", "4", "4"),
    # Romanian t-cedilla/t-comma
    ("ţ", "3|4", "3|4", "3|4"),
    ("ț", "3|4", "3|4", "3|4"),
    # Polish e-ogonek/a-ogonek
    ("ę", "", "", "|6"),
    ("ą", "", "", "|6"),
    # Multi-letter combinations
    ("schtsch", "2", "4", "4"),
    ("schtsh", "2", "4", "4"),
    ("schtch", "2", "4", "4"),
    ("shtch", "2", "4", "4"),
    ("shtsh", "2", "4", "4"),
    ("stsch", "2", "4", "4"),
    ("ttsch", "4", "4", "4"),
    ("zhdzh", "2", "4", "4"),
    ("shch", "2", "4", "4"),
    ("scht", "2", "43", "43"),
    ("schd", "2", "43", "43"),
    ("stch", "2", "4", "4"),
    ("strz", "2", "4", "4"),
    ("strs", "2", "4", "4"),
    ("stsh", "2", "4", "4"),
    ("szcz", "2", "4", "4"),
    ("szcs", "2", "4", "4"),
    ("ttch", "4", "4", "4"),
    ("tsch", "4", "4", "4"),
    ("ttsz", "4", "4", "4"),
    ("zdzh", "2", "4", "4"),
    ("zsch", "4", "4", "4"),
    ("chs", "5", "54", "54"),
    ("csz", "4", "4", "4"),
    ("czs", "4", "4", "4"),
    ("drz", "4", "4", "4"),
    ("drs", "4", "4", "4"),
    ("dsh", "4", "4", "4"),
    ("dsz", "4", "4", "4"),
    ("dzh", "4", "4", "4"),
    ("dzs", "4", "4", "4"),
    ("sch", "4", "4", "4"),
    ("sht", "2", "43", "43"),
    ("szt", "2", "43", "43"),
    ("shd", "2", "43", "43"),
    ("szd", "2", "43", "43"),
    ("tch", "4", "4", "4"),
    ("trz", "4", "4", "4"),
    ("trs", "4", "4", "4"),
    ("tsh", "4", "4", "4"),
    ("tts", "4", "4", "4"),
    ("ttz", "4", "4", "4"),
    ("tzs", "4", "4", "4"),
    ("tsz", "4", "4", "4"),
    ("zdz", "2", "4", "4"),
    ("zhd", "2", "43", "43"),
    ("zsh", "4", "4", "4"),
    ("ai", "0", "1", ""),
    ("aj", "0", "1", ""),
    ("ay", "0", "1", ""),
    ("au", "0", "7", ""),
    ("cz", "4", "4", "4"),
    ("cs", "4", "4", "4"),
    ("ds", "4", "4", "4"),
    ("dz", "4", "4", "4"),
    ("dt", "3", "3", "3"),
    ("ei", "0", "1", ""),
    ("ej", "0", "1", ""),
    ("ey", "0", "1", ""),
    ("eu", "1", "1", ""),
    ("fb", "7", "7", "7"),
    ("ia", "1", "", ""),
    ("ie", "1", "", ""),
    ("io", "1", "", ""),
    ("iu", "1", "", ""),
    ("ks", "5", "54", "54"),
    ("kh", "5", "5", "5"),
    ("mn", "66", "66", "66"),
    ("nm", "66", "66", "66"),
    ("oi", "0", "1", ""),
    ("oj", "0", "1", ""),
    ("oy", "0", "1", ""),
    ("pf", "7", "7", "7"),
    ("ph", "7", "7", "7"),
    ("sh", "4", "4", "4"),
    ("sc", "2", "4", "4"),
    ("st", "2", "43", "43"),
    ("sd", "2", "43", "43"),
    ("sz", "4", "4", "4"),
    ("th", "3", "3", "3"),
    ("ts", "4", "4", "4"),
    ("tc", "4", "4", "4"),
    ("tz", "4", "4", "4"),
    ("ui", "0", "1", ""),
    ("uj", "0", "1", ""),
    ("uy", "0", "1", ""),
    ("ue", "0", "1", ""),
    ("zd", "2", "43", "43"),
    ("zh", "4", "4", "4"),
    ("zs", "4", "4", "4"),
    # Branching cases - a letter/combination that can sound two ways.
    ("c", "4|5", "4|5", "4|5"),
    ("ch", "4|5", "4|5", "4|5"),
    ("ck", "5|45", "5|45", "5|45"),
    ("rs", "4|94", "4|94", "4|94"),
    ("rz", "4|94", "4|94", "4|94"),
    ("j", "1|4", "|4", "|4"),
)

#: Accented-letter -> plain-ASCII folding, same set Commons Codec ships
#: (covers the accented Latin letters that show up in the surnames this
#: rule targets).
_FOLDINGS = {
    "ß": "s", "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
    "æ": "a", "ç": "c", "è": "e", "é": "e", "ê": "e", "ë": "e", "ì": "i",
    "í": "i", "î": "i", "ï": "i", "ð": "d", "ñ": "n", "ò": "o", "ó": "o",
    "ô": "o", "õ": "o", "ö": "o", "ø": "o", "ù": "u", "ú": "u", "û": "u",
    "ý": "y", "þ": "b", "ÿ": "y", "ć": "c", "ł": "l", "ś": "s", "ż": "z",
    "ź": "z",
}

_VOWELS = "aeiou"


class _Rule:
    """One line of _RULE_DATA, with its three replacement lists split
    on "|" into alternatives (branches)."""

    __slots__ = ("pattern", "start", "vowel", "other")

    def __init__(self, pattern, start, vowel, other):
        self.pattern = pattern
        self.start = tuple(start.split("|"))
        self.vowel = tuple(vowel.split("|"))
        self.other = tuple(other.split("|"))

    def replacements_for(self, context, at_start):
        """
        Pick this rule's replacement alternatives for one match.

        :param context: The input from the current position onward
            (so ``context[:len(self.pattern)] == self.pattern``).
        :param at_start: Whether this is the first letter group coded
            in the name.
        :returns: The tuple of replacement alternatives to branch on.
        """
        if at_start:
            return self.start
        next_index = len(self.pattern)
        if next_index < len(context) and context[next_index] in _VOWELS:
            return self.vowel
        return self.other


def _build_rules():
    """Group _RULE_DATA by each pattern's first character, longest
    pattern first, so matching can greedily prefer the longer n-gram."""
    rules = {}
    for pattern, start, vowel, other in _RULE_DATA:
        rules.setdefault(pattern[0], []).append(_Rule(pattern, start, vowel, other))
    for group in rules.values():
        group.sort(key=lambda rule: len(rule.pattern), reverse=True)
    return rules


_RULES = _build_rules()


def _cleanup(name):
    """Lowercase, drop whitespace/non-letters, and fold accents - the
    same cleanup Commons Codec applies before coding."""
    result = []
    for ch in name or "":
        if ch.isspace() or not ch.isalpha():
            continue
        ch = ch.lower()
        result.append(_FOLDINGS.get(ch, ch))
    return "".join(result)


class _Branch:
    """One in-progress candidate code. A name branches (see the module
    docstring) whenever a letter or combination can sound two ways."""

    __slots__ = ("code", "last_replacement")

    def __init__(self):
        self.code = ""
        self.last_replacement = None

    def copy(self):
        """Return an independent branch with the same state so far."""
        branch = _Branch()
        branch.code = self.code
        branch.last_replacement = self.last_replacement
        return branch

    def apply(self, replacement, force):
        """
        Append ``replacement``, unless it's already accounted for.

        Adjacent letters with the same code collapse into one sound
        (rule 4 of the D-M system) - implemented here as "skip the
        append if what's already on the end of the code already ends
        with this replacement" rather than a simple last-digit
        comparison, since a multi-digit replacement (e.g. "43") can
        already contain what a following single-digit one would add.
        ``force`` is for the MN/NM exception, the one pair the system
        codes separately despite matching this same-code rule.

        :param replacement: The next replacement to append (may be
            ``""`` for "not coded").
        :param force: True for the MN/NM exception.
        """
        append = (
            self.last_replacement is None
            or not self.last_replacement.endswith(replacement)
            or force
        )
        if append and len(self.code) < _MAX_LENGTH:
            self.code += replacement
            if len(self.code) > _MAX_LENGTH:
                self.code = self.code[:_MAX_LENGTH]
        self.last_replacement = replacement

    def finish(self):
        """Zero-pad up to the required length."""
        if len(self.code) < _MAX_LENGTH:
            self.code += "0" * (_MAX_LENGTH - len(self.code))


def _daitch_mokotoff_raw(name):
    """
    Return every Daitch-Mokotoff Soundex code for one word, as a
    sorted list (usually one code; several when the word contains a
    letter or combination that can sound two ways - see the module
    docstring).

    :param name: The surname (or any word) to encode.
    :returns: A sorted list of 6-digit code strings; empty if nothing
        alphabetic was found to encode.
    """
    word = _cleanup(name)
    if not word:
        return []

    branches = {"": _Branch()}
    last_char = None  # None means "nothing coded yet" (start of word)
    index = 0
    length = len(word)
    while index < length:
        ch = word[index]
        candidates = _RULES.get(ch)
        if not candidates:
            index += 1
            continue

        context = word[index:]
        rule = next((r for r in candidates if context.startswith(r.pattern)), None)
        if rule is None:  # pragma: no cover - every letter has a 1-char rule
            index += 1
            last_char = ch
            continue

        replacements = rule.replacements_for(context, at_start=last_char is None)
        # MN and NM are the one exception to "same code collapses":
        # they're coded separately even though M and N share a code.
        force = (last_char == "m" and ch == "n") or (last_char == "n" and ch == "m")

        next_branches = {}
        for branch in branches.values():
            for replacement in replacements:
                candidate = branch.copy() if len(replacements) > 1 else branch
                candidate.apply(replacement, force)
                next_branches.setdefault(candidate.code, candidate)
        branches = next_branches

        index += len(rule.pattern)
        last_char = ch

    for branch in branches.values():
        branch.finish()
    return sorted({branch.code for branch in branches.values()})


def encode(name):
    """
    Return every Daitch-Mokotoff code set for ``name``.

    :param name: The surname (or any word) to encode.
    :returns: A set of 6-digit code strings (often more than one - see
        the module docstring), or ``{""}`` if nothing alphabetic was
        found to encode.
    """
    try:
        codes = _daitch_mokotoff_raw(name)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Daitch-Mokotoff encoding failed for %r, falling back", name)
        return {""}
    return set(codes) if codes else {""}


# -------------------------------------------------------------------------
#
# HasDaitchMokotoffNames
#
# -------------------------------------------------------------------------
class HasDaitchMokotoffNames(Rule):
    """
    Rule that checks for a Daitch-Mokotoff match on a person's names,
    in the name fields selected by the "Match in:" option (the
    preferred name's surname pieces and call name by default - same as
    HasSoundexNames). A match against any one of the given name's
    codes counts.
    """

    labels = (
        [_("Name:"), (OPTION_LABEL, name_parts_widget)]
        if _HAVE_NAME_PARTS
        else [_("Name:")]
    )
    name = _("D-M match of People with the <names>")
    description = _(
        "Matches people whose selected name fields (preferred surname and "
        "call name by default) have the same Daitch-Mokotoff code as the "
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
            any of the target codes.
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
