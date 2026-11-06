
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025  Custom Soundex Implementation
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
Custom Soundex encoder with specific consonant mappings.

Consonant mappings:
B,P,V,F -> B
C,K,Q,G,J -> C
S,Z,X -> S
D,T -> D
L -> L
M,N -> M
R -> R

Special combinations:
PH -> F
KN -> N
GH -> removed
WR -> R
"""

# Compatible with Python 3.6
from typing import Set

LOG = None  # Will be set by the importing module

#: Registry key
ALGORITHM_ID = "soundex_custom"

#: Display label
ALGORITHM_LABEL = "Soundex Custom"

# Consonant mapping rules
_CONSONANT_MAP = {
    'B': 'B', 'P': 'B', 'V': 'B', 'F': 'B',
    'C': 'C', 'K': 'C', 'Q': 'C', 'G': 'C', 'J': 'C',
    'S': 'S', 'Z': 'S', 'X': 'S',
    'D': 'D', 'T': 'D',
    'L': 'L',
    'M': 'M', 'N': 'M',
    'R': 'R'
}

# Special combinations (applied first)
_SPECIAL_COMBINATIONS = [
    ('PH', 'F'),
    ('KN', 'N'),
    ('GH', ''),  # removed
    ('WR', 'R')
]

def _clean_and_upper(name: str) -> str:
    """Keep only letters, convert to uppercase."""
    return ''.join(c for c in name if c.isalpha()).upper()

def _apply_special_combinations(name: str) -> str:
    """Apply special multi-character combinations first."""
    for old, new in _SPECIAL_COMBINATIONS:
        name = name.replace(old, new)
    return name

def _map_consonants(name: str) -> str:
    """Map individual consonants according to the rules."""
    return ''.join(_CONSONANT_MAP.get(c, c) for c in name)

def _remove_duplicates(name: str) -> str:
    """Remove consecutive duplicate letters."""
    if not name:
        return name
    result = [name[0]]
    for c in name[1:]:
        if c != result[-1]:
            result.append(c)
    return ''.join(result)

def _pad_to_four(code: str) -> str:
    """Pad code with zeros to 4 characters."""
    return (code + '000')[:4]


def _soundex_custom(name: str) -> str:
    """
    Compute custom Soundex code.

    Steps:
    1. Keep first letter
    2. Apply special combinations
    3. Map consonants
    4. Remove duplicates
    5. Remove vowels (except first)
    6. Pad to 4 characters
    """
    if not name:
        return '0000'

    cleaned = _clean_and_upper(name)
    if not cleaned:
        return '0000'

    # Keep first letter
    first_letter = cleaned[0]
    rest = cleaned[1:]

    # Apply special combinations to the rest
    rest = _apply_special_combinations(rest)

    # Map consonants
    rest = _map_consonants(rest)

    # Remove vowels from rest
    rest = ''.join(c for c in rest if c not in 'AEIOUY')

    # Remove duplicates
    rest = _remove_duplicates(rest)

    # Combine and pad
    code = first_letter + rest
    return _pad_to_four(code)

def encode(name: str) -> Set[str]:
    """
    Return the Soundex code as a set (for compatibility with phonetic_codes.py).

    :param name: The surname to encode.
    :returns: A one-element set containing the 4-character Soundex code.
    """
    try:
        code = _soundex_custom(name)
        return {code}
    except Exception:
        if LOG:
            LOG.debug("Soundex custom encoding failed for %r", name)
        return {'0000'}

# Test cases
if __name__ == "__main__":
    # Test the examples
    tests = [
        ("STEPHEN", "SDBM"),  # S-T[D]-[e]-PH[F->B]-[e]-N[M]
        ("ASHCRAFT", "ASCR"),  # A-S[S]-H-C[C]-R[R]-A-F[B]-T[D]
        ("KNIGHT", "NCD"),    # KN[N]-I-GH-T[D]
    ]

    for name, expected in tests:
        result = _soundex_custom(name)
        print(f"{name} -> {result} (expected: {expected}) {'✓' if result == expected else '✗'}")

