#
# Gramps - a GTK+/GNOME based genealogy program
#
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
The "Surname, Given" name parser shared by the Fuzzy Matching gramplet
and the Fuzzy Match Lookup window (via fuzzy_match_panel.py).

The rules are the same ones the Data Entry gramplet's "Surname, Given"
field (``split_name``) already uses, so text copied between those
fields means the same thing everywhere:

* A comma is the only thing that marks a given name: ``"Smith, John"``.
* Without a comma the whole text is a surname, so a multi-word surname
  such as ``"Van Der Berg"`` keeps working as one surname.

The Photo Tagging gramplet reads metadata in "Given Surname" order
(``split_placeholder_name``); it turns that into this "Surname, Given"
form before handing it to the lookup window (see
:func:`format_name_query`).

No GTK and no database here, so it is unit-testable on its own.
"""

# ------------------------
# Python modules
# ------------------------
from typing import List, Tuple


def parse_name_query(text: str) -> Tuple[str, str]:
    """
    Split "Surname, Given" text into its two parts.

    :param text: The field text; without a comma it is all surname.
    :returns: ``(surname, given)``, both stripped; ``given`` is ``""``
        when there is no comma.
    """
    if "," in text:
        surname, _sep, given = text.partition(",")
        return surname.strip(), given.strip()
    return text.strip(), ""


def format_name_query(surname: str, given: str = "") -> str:
    """
    Join a surname and a given name into "Surname, Given" text, the
    inverse of :func:`parse_name_query`. A blank given name gives just
    the surname (no trailing comma); a blank surname with a given name
    gives ``", Given"`` so the given name is not mistaken for a surname.

    :param surname: The surname.
    :param given: The given name, possibly blank.
    :returns: The joined text.
    """
    surname = (surname or "").strip()
    given = (given or "").strip()
    if not given:
        return surname
    return "{}, {}".format(surname, given)


def surname_words(surname: str) -> List[str]:
    """
    The individual words of a typed surname, for matching a compound
    surname ("Thompson McCullough") that Gramps files as separate
    pieces. A single-word surname gives a one-item list.

    :param surname: The surname text.
    :returns: Its whitespace-separated words, in order.
    """
    return surname.split()


def given_name_matches(typed: str, recorded: str) -> bool:
    """
    Whether a recorded given name passes the typed given-name filter.

    Plain text, not phonetic, and forgiving in two ways: the typed text
    may appear anywhere in the recorded name ("ann" finds "Joanne"),
    and a recorded word may be the start of the typed text ("Billy"
    typed still finds a recorded "Bill"). Case is ignored.

    :param typed: The given part of the query, possibly blank.
    :param recorded: A person's recorded given name(s).
    :returns: True if ``recorded`` passes (always True for blank
        ``typed``).
    """
    wanted = typed.strip().casefold()
    if not wanted:
        return True
    have = recorded.casefold()
    if wanted in have:
        return True
    return any(word and wanted.startswith(word) for word in have.split())
