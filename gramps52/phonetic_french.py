#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2025  Custom French Phonetic Encoder
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
Custom French phonetic encoder for the Fuzzy Matching Gramplet.

Implements a 16-step French phonetic transformation algorithm.
"""

# Compatible with Python 3.6
import re
import unicodedata
from typing import Set

LOG = None  # Will be set by the importing module

#: Registry key
ALGORITHM_ID = "phonetic_french"

#: Display label
ALGORITHM_LABEL = "French Phonetic"

def encode(name: str) -> Set[str]:
    """
    Apply the 16-step French phonetic transformation.

    :param name: The surname to encode.
    :returns: A one-element set containing the phonetic code.
    """
    try:
        # Step 0: Convert to string and normalize
        strval = str(name)
        r = unicodedata.normalize('NFKD', strval.upper().strip()).encode('ASCII', 'ignore').decode('ASCII')

        # Step 1: Replace Y by I
        r = r.replace('Y', 'I')

        # Step 2: Replace accented E by Y
        r = r.replace(u'É', 'Y')
        r = r.replace(u'È', 'Y')
        r = r.replace(u'Ê', 'Y')

        # Step 3: Remove H not preceded by C, S, or P
        r = re.sub(r'([^CSP])H', r'\1', r)

        # Step 4: Replace PH by F
        r = r.replace('PH', 'F')

        # Step 5: Replace G followed by A, AI, AM, AN by K
        r = re.sub(r'G(AI?[N|M])', r'K\1', r)

        # Step 6: Replace vowel+I+N/M followed by vowel
        r = re.sub(r'([A|E]I[N|M])([A|E|I|O|U])', r'YN\2', r)

        # Step 7: Replace specific groups (water sounds)
        r = r.replace('EAU', 'O')
        r = r.replace('OUA', '2')
        r = r.replace('EIN', '4')
        r = r.replace('AIN', '4')
        r = r.replace('EIM', '4')
        r = r.replace('AIM', '4')

        # Step 8: Replace AI, EI, ER, ESS, ET, EZ
        r = r.replace('AI', 'Y')
        r = r.replace('EI', 'Y')
        r = r.replace('ER', 'YR')
        r = r.replace('ESS', 'YS')
        r = r.replace('ET', 'YT')
        r = r.replace('EZ', 'YZ')

        # Step 9: Replace AN, ON, AM, EN, EM, IN (not followed by vowel or sound 1-4)
        r = re.sub(r'AN([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
        r = re.sub(r'ON([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
        r = re.sub(r'AM([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
        r = re.sub(r'EN([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
        r = re.sub(r'EM([^A|E|I|O|U|1|2|3|4])', r'1\1', r)
        r = re.sub(r'IN([^A|E|I|O|U|1|2|3|4])', r'4\1', r)

        # Step 10: Replace S by Z (between vowels or sounds 1-4)
        r = re.sub(r'([A|E|I|O|U|Y|1|2|3|4])S([A|E|I|O|U|Y|1|2|3|4])', r'\1Z\2', r)

        # Step 11: Replace specific groups
        r = r.replace('OE', 'E')
        r = r.replace('EU', 'E')
        r = r.replace('AU', 'O')
        r = r.replace('OI', '2')
        r = r.replace('OY', '2')
        r = r.replace('OU', '3')

        # Step 12: Replace CH, SCH, SH, SS, SC
        r = r.replace('CH', '5')
        r = r.replace('SCH', '5')
        r = r.replace('SH', '5')
        r = r.replace('SS', 'S')
        r = r.replace('SC', 'S')

        # Step 13: Replace C by S (before E or I)
        r = re.sub(r'C([E|I])', r'S\1', r)

        # Step 14: Replace letters
        r = r.replace('C', 'K')
        r = r.replace('Q', 'K')
        r = r.replace('QU', 'K')
        r = r.replace('GU', 'K')
        r = r.replace('GA', 'KA')
        r = r.replace('GO', 'KO')
        r = r.replace('GY', 'KY')

        # Step 15: Replace remaining letters
        r = r.replace('A', 'O')
        r = r.replace('D', 'T')
        r = r.replace('P', 'T')
        r = r.replace('J', 'G')
        r = r.replace('B', 'F')
        r = r.replace('V', 'F')
        r = r.replace('M', 'N')

        # Step 16: Remove duplicate letters
        oldc = '#'
        newr = ''
        for c in r:
            if oldc != c:
                newr = newr + c
            oldc = c
        r = newr

        # Step 17: Remove ending T or X
        r = re.sub(r'(.*)[T|X]$', r'\1', r)

        return {r}

    except Exception:
        if LOG:
            LOG.debug("French phonetic encoding failed for %r", name)
        return {'0'}
