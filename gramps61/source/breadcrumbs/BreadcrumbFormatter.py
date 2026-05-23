#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough <emyoulation@yahoo.com>
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
# Generated-by: Claude Sonnet 4.6 (Anthropic) via claude.ai
# Prompts: Standalone formatting module for PedigreeBreadcrumbs gramplet.
#   Accepts ordered PedigreeEntry namedtuples (youngest to oldest) and returns
#   plain-text and tagged FormattedText for breadcrumb and generation-list
#   formats. Tags carry superscript ranges and gramps:// hyperlink ranges for
#   Family (breadcrumb given-name) and Person (list GrampsID) targets.

"""BreadcrumbFormatter — standalone formatting module for PedigreeBreadcrumbs.

Accepts an ordered list of ``PedigreeEntry`` named-tuples (youngest → oldest)
and produces two formatted representations of the pedigree:

1. **Breadcrumb** — a single line::

       Given⁶ SURNAME; Given⁵ SURNAME; …

   Surnames are suppressed when identical to the previous entry, except the
   rightmost (oldest) person always shows their surname.  The generation label
   appears *after* the given name, *before* the surname.

2. **Generation list** — one line per person::

       label: Full Name  YYYY–YYYY; GrampsID

Each format is returned in two flavours:

* **Plain text** — suitable for clipboard copy.
* **``FormattedText``** — a named-tuple containing the plain string plus
  lists of character ranges for superscripts and hyperlinks, exactly matching
  the styling structure used in Gramps Note N0039 (the reference note):

  - Breadcrumb links: ``gramps://Family/handle/{parent_family_handle}``
    covering the *given name only* (before the superscript label).
    Persons with no known parent family receive no link.
  - List links: ``gramps://Person/handle/{person_handle}``
    covering the *GrampsID* at the end of each line.
  - Superscript: the label character(s) in both breadcrumb and list.

The caller (``PedigreeBreadcrumbs.py``) assembles ``StyledTextTag`` objects
from the ranges and passes them to ``StyledText``, keeping this module
free of all Gramps imports.

``PedigreeEntry`` fields
------------------------
handle          str   Gramps internal person handle
family_handle   str   handle of the person's first parent family, or ""
gramps_id       str   e.g. "I0042"
label           str   generation marker — any string: "1", "A", "★" …
given           str   first / given name(s), including any name suffix
surname         str   primary surname
name_full       str   full name via Gramps Name Display preference
birth_year      str   4-digit birth year, or ""
death_year      str   4-digit death year, or ""

``FormattedText`` fields
------------------------
plain           str                 plain Unicode text (no markup)
sup_ranges      list[(int,int)]     character spans to mark as superscript
link_ranges     list[(str,int,int)] (gramps_url, start, end) for each link
"""

from collections import namedtuple

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------

PedigreeEntry = namedtuple(
    "PedigreeEntry",
    ["handle", "family_handle", "gramps_id", "label",
     "given", "surname", "name_full", "birth_year", "death_year"],
)

FormattedText = namedtuple(
    "FormattedText",
    ["plain", "sup_ranges", "link_ranges"],
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _life_span(entry):
    """Return "YYYY–YYYY", "YYYY–", "–YYYY", or "" for the entry."""
    if entry.birth_year or entry.death_year:
        return f"{entry.birth_year}\u2013{entry.death_year}"
    return ""


# ===========================================================================
# Plain-text formatters
# ===========================================================================

def format_breadcrumb_plain(entries):
    """
    Return the breadcrumb as a plain Unicode string.

    Format per token: ``{given}{label}[ {SURNAME}]``
    Tokens separated by ``"; "``.
    Surname suppressed when matching the previous entry's surname, except the
    last (oldest) entry always shows its surname.

    Parameters
    ----------
    entries : list of PedigreeEntry   (youngest → oldest)

    Returns
    -------
    str
    """
    if not entries:
        return ""

    parts    = []
    prev_sn  = ""
    last_idx = len(entries) - 1

    for idx, e in enumerate(entries):
        show_sn = (idx == last_idx) or (e.surname != prev_sn)
        prev_sn = e.surname
        token = e.given + e.label
        if show_sn and e.surname:
            token += " " + e.surname
        parts.append(token)

    return "; ".join(parts)


def format_list_plain(entries):
    """
    Return the generation list as a plain multi-line string.

    Each line: ``label: Full Name  YYYY–YYYY; GrampsID``

    Parameters
    ----------
    entries : list of PedigreeEntry   (youngest → oldest)

    Returns
    -------
    str
    """
    if not entries:
        return ""

    lines = []
    for e in entries:
        span = _life_span(e)
        line = e.label + ": " + e.name_full
        if span:
            line += "  " + span
        line += "; " + e.gramps_id
        lines.append(line)
    return "\n".join(lines)


# ===========================================================================
# FormattedText builders  (caller assembles into StyledText)
# ===========================================================================
#
# These return FormattedText(plain, sup_ranges, link_ranges).
#
# sup_ranges  — list of (start, end)  covering each label character run
#
# link_ranges — list of (url, start, end) where:
#   breadcrumb: url = gramps://Family/handle/{family_handle}
#               range covers the given name only (before the label)
#               omitted when family_handle is empty
#   list:       url = gramps://Person/handle/{person_handle}
#               range covers the GrampsID string at line end
#
# The caller builds:
#   StyledTextTag("superscript", "", sup_ranges)
#   StyledTextTag("link", url, [(start, end)])   — one per link_range entry
# ---------------------------------------------------------------------------


def format_breadcrumb_tagged(entries):
    """
    Return breadcrumb ``FormattedText`` with superscript and Family link ranges.

    Token layout in the plain string::

        {given}{label}[ {SURNAME}]

    Superscript covers ``{label}``.
    Family link covers ``{given}`` only (before the label).

    Parameters
    ----------
    entries : list of PedigreeEntry

    Returns
    -------
    FormattedText
    """
    if not entries:
        return FormattedText("", [], [])

    separator = "; "
    sep_len   = len(separator)
    last_idx  = len(entries) - 1

    plain_parts = []
    sup_ranges  = []   # (start, end) for each label
    link_ranges = []   # (url, start, end) for each person with a family handle

    pos     = 0
    prev_sn = ""

    for idx, e in enumerate(entries):
        show_sn = (idx == last_idx) or (e.surname != prev_sn)
        prev_sn = e.surname

        # Family link: given name only, before the label
        given_start = pos
        given_end   = pos + len(e.given)
        if e.family_handle:
            link_ranges.append((
                f"gramps://Family/handle/{e.family_handle}",
                given_start,
                given_end,
            ))

        # Superscript: label immediately after given name
        label_start = given_end
        label_end   = label_start + len(e.label)
        sup_ranges.append((label_start, label_end))

        seg = e.given + e.label
        if show_sn and e.surname:
            seg += " " + e.surname

        plain_parts.append(seg)
        pos += len(seg)
        if idx < last_idx:
            pos += sep_len

    plain_string = separator.join(plain_parts)
    return FormattedText(plain_string, sup_ranges, link_ranges)


def format_list_tagged(entries):
    """
    Return generation list ``FormattedText`` with superscript and Person link ranges.

    Line layout::

        {label}: {Full Name}[  {YYYY–YYYY}]; {GrampsID}

    Superscript covers ``{label}`` at line start.
    Person link covers ``{GrampsID}`` at line end.

    Parameters
    ----------
    entries : list of PedigreeEntry

    Returns
    -------
    FormattedText
    """
    if not entries:
        return FormattedText("", [], [])

    newline    = "\n"
    sup_ranges  = []
    link_ranges = []
    lines       = []
    pos         = 0

    for idx, e in enumerate(entries):
        span = _life_span(e)

        # Label at line start → superscript
        label_start = pos
        label_end   = pos + len(e.label)
        sup_ranges.append((label_start, label_end))

        # Build line text
        line = e.label + ": " + e.name_full
        if span:
            line += "  " + span
        line += "; " + e.gramps_id

        # GrampsID at end of line → Person link
        id_end   = pos + len(line)
        id_start = id_end - len(e.gramps_id)
        link_ranges.append((
            f"gramps://Person/handle/{e.handle}",
            id_start,
            id_end,
        ))

        lines.append(line)
        pos += len(line)
        if idx < len(entries) - 1:
            pos += len(newline)

    plain_string = newline.join(lines)
    return FormattedText(plain_string, sup_ranges, link_ranges)


# ===========================================================================
# Combined helper
# ===========================================================================

def format_all(entries):
    """
    Return all four representations in a dict.

    Keys
    ----
    ``"breadcrumb_plain"``   : str
    ``"breadcrumb_tagged"``  : FormattedText
    ``"list_plain"``         : str
    ``"list_tagged"``        : FormattedText
    """
    return {
        "breadcrumb_plain":  format_breadcrumb_plain(entries),
        "breadcrumb_tagged": format_breadcrumb_tagged(entries),
        "list_plain":        format_list_plain(entries),
        "list_tagged":       format_list_tagged(entries),
    }
