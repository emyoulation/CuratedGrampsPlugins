#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Brian McCullough
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

"""
MarkdownUtils  --  Reusable Markdown rendering library for Gramps add-ons.

Provides:
  - ``Segment``                 -- data model for a parsed text run
  - ``parse_markdown()``        -- convert Markdown text to a list of Segments
  - ``define_tags()``           -- create all Gtk.TextTag styles in a TextBuffer
  - ``inline_to_pango()``       -- convert inline Markdown to Pango markup (tables)
  - ``build_table_widget()``    -- build a Gtk.TreeView widget for a GFM table
  - ``resolve_icon_pixbuf()``   -- resolve a GTK/Gramps icon to a GdkPixbuf
  - ``list_icons_by_context()`` -- enumerate icon names from the live theme cascade
  - ``GRAMPS_ICONS``            -- short-name → GTK icon-name alias map
  - ``NAMESPACE_MAP``           -- Gramps object-type → DB getter / editor map
  - ``VIEW_NAMES``              -- lowercase category alias → canonical view name

Anchor / in-document navigation
--------------------------------
Headings carry an ``anchor`` attribute on their ``Segment``.  The anchor slug
is derived from the heading text using the same GitHub-Flavoured Markdown
algorithm:

  1. Lower-case the text.
  2. Remove everything that is not a letter, digit, space, or hyphen.
  3. Replace runs of whitespace with a single hyphen.

The caller (gramplet or other consumer) receives the anchor name via
``Segment.anchor`` and is responsible for placing a ``Gtk.TextMark`` in the
buffer at the corresponding position, then scrolling to that mark when the
user clicks an anchor link (``#anchor-slug``).

Icon-theme cascade awareness
----------------------------
:func:`resolve_icon_pixbuf` and :func:`list_icons_by_context` both call
:meth:`Gtk.IconTheme.get_default`, which returns the process-wide singleton
that GTK keeps in sync with the active theme at all times.  When the Gramps
Themes addon changes the GTK theme via
``Gtk.Settings.set_property("gtk-theme-name", …)``, GTK updates the
singleton's search paths in-place; every subsequent call to this module
automatically reflects the new cascade without any explicit cache invalidation.

:func:`resolve_icon_pixbuf` uses ``GENERIC_FALLBACK | USE_BUILTIN`` lookup
flags so it renders the identical pixel data that GTK widgets produce
internally, and never silently returns ``None`` for an icon that the GUI
itself would display.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6, release 2026-05)
Prompts: "restructure MarkdownDash gramplet — extract markdown handling into a
separate library module; add in-document anchor scroll navigation for header
links such as [label](#anchor-slug)"
Revision prompts: "update MarkdownUtils.py per MarkdownUtils_improvements.txt:
add GENERIC_FALLBACK|USE_BUILTIN lookup flags to resolve_icon_pixbuf; add
list_icons_by_context() public helper for IconBrowserGramplet enumeration."
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md
"""

# ------------------------
# Python modules
# ------------------------
import os
import re

# ------------------------
# Gramps modules
# ------------------------
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, Gtk, Pango

# ------------------------
# Gramps specific
# ------------------------
# (no local imports — this is the base library)

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
import logging

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#
# Segment
#
# ---------------------------------------------------------------------------
class Segment:
    """One run of styled text to insert into a Gtk.TextBuffer.

    :param text:        Plain Unicode string to insert into the buffer.
    :param attrs:       List of tag-name strings (keys in the dict returned by
                        :func:`define_tags`) to apply to this run.
    :param url:         URI string that makes this run a clickable link, or
                        ``None``.
    :param image_path:  Filesystem path / URL for an embedded image, or
                        ``None``.
    :param gramps_icon: ``(icon_name, size)`` tuple to embed a GTK theme icon
                        inline, or ``None``.
    :param table_data:  ``(columns, align, body_rows, sep_widths)`` tuple to
                        render a GFM table as a child widget, or ``None``.
    :param anchor:      GitHub-style anchor slug for heading segments so the
                        caller can place a ``Gtk.TextMark`` at this position.
                        ``None`` for non-heading segments.
    """

    __slots__ = (
        "text",
        "attrs",
        "url",
        "image_path",
        "gramps_icon",
        "table_data",
        "anchor",
    )

    def __init__(
        self,
        text: str,
        attrs: list | None = None,
        url: str | None = None,
        image_path: str | None = None,
        gramps_icon: tuple | None = None,
        table_data: tuple | None = None,
        anchor: str | None = None,
    ) -> None:
        """Initialise a Segment with text and optional rendering metadata."""
        self.text = text
        self.attrs = attrs or []
        self.url = url
        self.image_path = image_path
        self.gramps_icon = gramps_icon
        self.table_data = table_data
        self.anchor = anchor


# ---------------------------------------------------------------------------
#
# Inline parser helpers
#
# ---------------------------------------------------------------------------

# Inline token regex -- finds the first special construct in a string.
_INLINE_RE = re.compile(
    r"(?P<img>!\[(?P<img_alt>[^\]]*)\]\((?P<img_url>[^)]*)\))"
    r"|(?P<link>\[(?P<link_label>[^\]]+)\]\((?P<link_url>[^)]+)\))"
    r"|(?P<bold3>\*{3}(?P<bold3_t>.+?)\*{3})"
    r"|(?P<und3>_{3}(?P<und3_t>.+?)_{3})"
    r"|(?P<bold2>\*{2}(?P<bold2_t>.+?)\*{2})"
    r"|(?P<und2>_{2}(?P<und2_t>.+?)_{2})"
    r"|(?P<code>`(?P<code_t>[^`\n]+)`)"
    r"|(?P<strike>~~(?P<strike_t>.+?)~~)"
    r"|(?P<em1>(?<!\*)\*(?!\*)(?P<em1_t>[^*\n]+?)(?<!\*)\*(?!\*))"
    r"|(?P<em2>(?<!\w)_(?!_)(?P<em2_t>[^_\n]+?)(?<!_)_(?!\w))",
    re.DOTALL,
)


def _esc(text: str) -> str:
    """XML-escape *text* for use inside Pango markup.

    :param text: Raw text string.
    :returns: XML-safe string.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _heading_anchor(text: str) -> str:
    """Derive a GitHub-style anchor slug from a heading's plain text.

    Algorithm:
      1. Strip inline Markdown to plain text.
      2. Lower-case.
      3. Remove everything that is not a letter, digit, space, or hyphen.
      4. Replace runs of whitespace with a single ``-``.

    :param text: Raw heading text (may contain inline Markdown).
    :returns: Anchor slug string.
    """
    # Remove inline Markdown tokens to get display text
    plain = re.sub(r"[*_`~\[\]!]", "", text)
    plain = re.sub(r"\(([^)]*)\)", "", plain)
    plain = plain.lower()
    plain = re.sub(r"[^\w\s-]", "", plain, flags=re.UNICODE)
    plain = re.sub(r"\s+", "-", plain.strip())
    return plain


# ---------------------------------------------------------------------------
#
# _parse_inline
#
# ---------------------------------------------------------------------------
def _parse_inline(text: str, base_attrs: tuple = ()) -> list[Segment]:
    """Split *text* into Segments, detecting inline Markdown constructs.

    :param text:       Input text that may contain inline Markdown.
    :param base_attrs: Tuple of tag names already active for this block
                       (e.g. ``('heading1',)`` for a heading line).
    :returns: List of :class:`Segment` objects.
    """
    segments: list[Segment] = []
    pos = 0
    base = list(base_attrs)

    while pos < len(text):
        m = _INLINE_RE.search(text, pos)
        if not m:
            tail = text[pos:]
            if tail:
                segments.append(Segment(tail, base[:]))
            break

        before = text[pos : m.start()]
        if before:
            segments.append(Segment(before, base[:]))

        kind = m.lastgroup

        if kind == "img":
            alt = m.group("img_alt") or m.group("img_url")
            url = m.group("img_url")
            gi_m = re.match(r"^gramps:icon:([^:]+)(?::(\d+))?$", url)
            if gi_m:
                icon_name = gi_m.group(1)
                size = int(gi_m.group(2)) if gi_m.group(2) else 16
                segments.append(
                    Segment(alt or icon_name, base[:], gramps_icon=(icon_name, size))
                )
            else:
                segments.append(
                    Segment(alt or url, base + ["image_link"], image_path=url)
                )

        elif kind == "link":
            label = m.group("link_label")
            url = m.group("link_url")
            if url.startswith("#"):
                # In-document anchor link
                inner = _parse_inline(label, base + ["anchor_link"])
                for seg in inner:
                    seg.url = url
                segments.extend(inner)
            elif url.startswith("gramps:nav:") or url.startswith("gramps:edit:"):
                inner = _parse_inline(label, base + ["gramps_link"])
                for seg in inner:
                    seg.url = url
                segments.extend(inner)
            else:
                inner = _parse_inline(label, base + ["hyperlink"])
                for seg in inner:
                    seg.url = url
                segments.extend(inner)

        elif kind in ("bold3", "und3"):
            t = m.group("bold3_t") if kind == "bold3" else m.group("und3_t")
            segments.extend(_parse_inline(t, base + ["bold", "italic"]))

        elif kind in ("bold2", "und2"):
            t = m.group("bold2_t") if kind == "bold2" else m.group("und2_t")
            segments.extend(_parse_inline(t, base + ["bold"]))

        elif kind == "code":
            segments.append(Segment(m.group("code_t"), base + ["code_inline"]))

        elif kind == "strike":
            segments.extend(_parse_inline(m.group("strike_t"), base + ["strike"]))

        elif kind in ("em1", "em2"):
            t = m.group("em1_t") if kind == "em1" else m.group("em2_t")
            segments.extend(_parse_inline(t, base + ["italic"]))

        pos = m.end()

    return segments


# ---------------------------------------------------------------------------
#
# parse_markdown  (block parser)
#
# ---------------------------------------------------------------------------
def parse_markdown(md_text: str) -> list[Segment]:
    """Parse a Markdown document into a flat list of :class:`Segment` objects.

    Supported block constructs:
      - ATX headings (``# H1`` … ``###### H6``) with anchor slugs
      - Setext headings (underlined with ``=`` or ``-``)
      - Fenced code blocks (backtick or tilde)
      - GFM tables
      - Blockquotes
      - Unordered and ordered lists (with nesting)
      - Horizontal rules
      - Blank lines and paragraphs

    Heading :class:`Segment` objects carry a non-``None`` ``anchor`` attribute
    equal to the GitHub-style anchor slug so the caller can place a
    ``Gtk.TextMark`` for in-document scroll navigation.

    :param md_text: Full Markdown document text.
    :returns: List of :class:`Segment` objects.
    """
    lines = md_text.splitlines()
    segments: list[Segment] = []
    in_code = False
    code_lang = ""
    code_lines: list[str] = []

    def add(
        text: str,
        attrs: tuple = (),
        url: str | None = None,
        image_path: str | None = None,
    ) -> None:
        """Append a plain :class:`Segment` (no anchor) to *segments*."""
        if text:
            segments.append(Segment(text, list(attrs), url, image_path))

    def add_heading(raw_text: str, level: int) -> None:
        """Parse heading inline content and append Segments with anchor set.

        The *first* segment for a heading carries the anchor slug; subsequent
        segments (from inline parsing) inherit ``anchor=None`` because the mark
        only needs to be placed at the start of the heading run.

        :param raw_text: The raw heading text (without the ``#`` prefix).
        :param level:    Heading level 1–6.
        """
        tag_name = "heading{}".format(level)
        slug = _heading_anchor(raw_text)
        inline_segs = _parse_inline(raw_text.strip(), (tag_name,))
        if inline_segs:
            inline_segs[0].anchor = slug
        segments.extend(inline_segs)
        add("\n\n")

    def flush_code() -> None:
        """Emit accumulated fenced-code-block lines as Segments."""
        lang = " ({})".format(code_lang) if code_lang else ""
        add("--- code{} ---\n".format(lang), ("code_fence_marker",))
        for cl in code_lines:
            add(cl + "\n", ("code_block",))
        add("--- end code ---\n\n", ("code_fence_marker",))
        code_lines.clear()

    def is_table_separator(line: str) -> bool:
        """Return ``True`` if *line* is a GFM table separator (``|---|:---:|``)."""
        s = line.strip()
        if not s.startswith("|") and "|" not in s:
            return False
        return bool(re.match(r"^[\|\s\-:]+$", s))

    def parse_table_row(line: str) -> list[str]:
        """Split a pipe-delimited table row into cell strings.

        :param line: A raw table row line.
        :returns: List of cell content strings.
        """
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|"):
            s = s[:-1]
        return [c.strip() for c in s.split("|")]

    def flush_table(
        header_row: list[str],
        body_rows: list[list[str]],
        align: list[str],
        sep_widths: list[int],
    ) -> None:
        """Emit a single ``table_data`` Segment rendered as a GTK TreeView.

        :param header_row: List of header cell strings.
        :param body_rows:  List of rows, each a list of cell strings.
        :param align:      Per-column alignment: ``'left'``, ``'center'``, or
                           ``'right'``.
        :param sep_widths: Per-column dash count from the GFM separator row.
        """
        ncols = max(
            len(header_row),
            max((len(r) for r in body_rows), default=0),
        )
        while len(header_row) < ncols:
            header_row.append("")
        for r in body_rows:
            while len(r) < ncols:
                r.append("")
        segments.append(
            Segment("", table_data=(header_row, align, body_rows, sep_widths))
        )
        add("\n")

    i = 0
    while i < len(lines):
        raw = lines[i]

        # ── fenced code block ────────────────────────────────────────────
        fence = re.match(r"^(`{3,}|~{3,})(.*)", raw)
        if fence and not in_code:
            in_code = True
            code_lang = fence.group(2).strip()
            i += 1
            continue
        if in_code:
            if re.match(r"^(`{3,}|~{3,})\s*$", raw):
                in_code = False
                flush_code()
            else:
                code_lines.append(raw)
            i += 1
            continue

        # ── GFM table ────────────────────────────────────────────────────
        if "|" in raw and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            header_row = parse_table_row(raw)
            sep_cells = parse_table_row(lines[i + 1])
            align: list[str] = []
            sep_widths: list[int] = []
            for sc in sep_cells:
                sc = sc.strip()
                sep_widths.append(sc.count("-"))
                if sc.startswith(":") and sc.endswith(":"):
                    align.append("center")
                elif sc.endswith(":"):
                    align.append("right")
                else:
                    align.append("left")
            i += 2
            body_rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                body_rows.append(parse_table_row(lines[i]))
                i += 1
            flush_table(header_row, body_rows, align, sep_widths)
            continue

        # ── blockquote ───────────────────────────────────────────────────
        bq = re.match(r"^>\s?(.*)", raw)
        if bq:
            add("│ ", ("blockquote_bar",))
            segments.extend(_parse_inline(bq.group(1), ("blockquote", "italic")))
            add("\n")
            i += 1
            continue

        # ── setext H1 ────────────────────────────────────────────────────
        if i + 1 < len(lines) and re.match(r"^=+\s*$", lines[i + 1]) and raw.strip():
            add_heading(raw.strip(), 1)
            i += 2
            continue

        # ── setext H2 ────────────────────────────────────────────────────
        if i + 1 < len(lines) and re.match(r"^-+\s*$", lines[i + 1]) and raw.strip():
            add_heading(raw.strip(), 2)
            i += 2
            continue

        # ── ATX headings ─────────────────────────────────────────────────
        h = re.match(r"^(#{1,6})\s+(.*)", raw)
        if h:
            add_heading(h.group(2).rstrip("# ").strip(), len(h.group(1)))
            i += 1
            continue

        # ── horizontal rule ──────────────────────────────────────────────
        if re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", raw):
            add("─" * 48 + "\n\n", ("hr",))
            i += 1
            continue

        # ── unordered list ───────────────────────────────────────────────
        ul = re.match(r"^(\s*)([-*+])\s+(.*)", raw)
        if ul:
            depth = len(ul.group(1)) // 2
            add("    " * depth + "\u2022 ", ("list_bullet",))
            segments.extend(_parse_inline(ul.group(3)))
            add("\n")
            i += 1
            continue

        # ── ordered list ─────────────────────────────────────────────────
        ol = re.match(r"^(\s*)(\d+)\.\s+(.*)", raw)
        if ol:
            depth = len(ol.group(1)) // 2
            add("    " * depth + ol.group(2) + ". ", ("list_bullet",))
            segments.extend(_parse_inline(ol.group(3)))
            add("\n")
            i += 1
            continue

        # ── blank line ───────────────────────────────────────────────────
        if raw.strip() == "":
            add("\n")
            i += 1
            continue

        # ── paragraph line ───────────────────────────────────────────────
        segments.extend(_parse_inline(raw))
        add("\n")
        i += 1

    if in_code and code_lines:
        flush_code()

    return segments


# ---------------------------------------------------------------------------
#
# define_tags
#
# ---------------------------------------------------------------------------
def define_tags(buf: Gtk.TextBuffer) -> dict[str, Gtk.TextTag]:
    """Create all rendering :class:`Gtk.TextTag` objects inside *buf*.

    Tags are created via ``buf.create_tag()`` so constructor keyword arguments
    automatically activate the corresponding ``-set`` flags.  All tags are also
    stored in the buffer's tag table and returned as a name-keyed dict.

    :param buf: The :class:`Gtk.TextBuffer` that will own the tags.
    :returns: ``dict`` mapping tag-name strings to :class:`Gtk.TextTag` objects.
    """
    W_BOLD = Pango.Weight.BOLD
    S_ITALIC = Pango.Style.ITALIC
    U_SINGLE = Pango.Underline.SINGLE

    tags: dict[str, Gtk.TextTag] = {}

    def tag(name: str, **kw) -> Gtk.TextTag:
        """Create a named tag in *buf* and store it in *tags*."""
        tags[name] = buf.create_tag(name, **kw)
        return tags[name]

    # Headings
    tag("heading1", weight=W_BOLD, scale=2.0, foreground="#111111")
    tag("heading2", weight=W_BOLD, scale=1.6, foreground="#111111")
    tag("heading3", weight=W_BOLD, scale=1.3, foreground="#222222")
    tag("heading4", weight=W_BOLD, scale=1.1, foreground="#222222")
    tag("heading5", weight=W_BOLD, scale=1.0, foreground="#333333")
    tag("heading6", weight=W_BOLD, scale=0.9, foreground="#555555")

    # Block structural
    tag("hr", foreground="#bbbbbb")
    tag("blockquote", foreground="#555555", style=S_ITALIC)
    tag("blockquote_bar", foreground="#aaaaaa", weight=W_BOLD)
    tag(
        "code_block",
        family="Monospace",
        foreground="#222222",
        background="#f5f5f5",
        paragraph_background="#f5f5f5",
    )
    tag(
        "code_fence_marker",
        family="Monospace",
        foreground="#888888",
        background="#e8e8e8",
        paragraph_background="#e8e8e8",
    )
    tag("list_bullet", foreground="#555555", weight=W_BOLD)

    # Inline emphasis
    tag("bold", weight=W_BOLD)
    tag("italic", style=S_ITALIC)
    tag("strike", strikethrough=True)
    tag(
        "code_inline",
        family="Monospace",
        foreground="#333333",
        background="#f0f0f0",
    )

    # Interactive (visual only -- click handling is done by the consumer)
    tag("hyperlink", foreground="#0055cc", underline=U_SINGLE)
    tag("image_link", foreground="#0077aa", underline=U_SINGLE, background="#eef4ff")
    tag("gramps_link", foreground="#8800aa", underline=U_SINGLE, background="#f5eeff")
    # In-document anchor links rendered like regular hyperlinks but distinct
    tag("anchor_link", foreground="#006633", underline=U_SINGLE)

    return tags


# ---------------------------------------------------------------------------
#
# inline_to_pango  (used for table cell rendering)
#
# ---------------------------------------------------------------------------
def inline_to_pango(text: str) -> str:
    """Convert inline Markdown in *text* to a Pango markup string.

    Handles: ``**bold**``, ``*italic*``, ``***bold-italic***``, `` `code` ``,
    ``~~strike~~``, ``[label](url)`` links, and plain text.  Images inside
    table cells are shown as their alt text in italics.  The result is always
    XML-safe.

    :param text: Inline Markdown text.
    :returns: Pango markup string.
    """
    result: list[str] = []
    pos = 0

    while pos < len(text):
        m = _INLINE_RE.search(text, pos)
        if not m:
            result.append(_esc(text[pos:]))
            break
        if m.start() > pos:
            result.append(_esc(text[pos : m.start()]))
        kind = m.lastgroup
        if kind == "img":
            alt = m.group("img_alt") or m.group("img_url")
            result.append("<i>{}</i>".format(_esc(alt)))
        elif kind == "link":
            label = m.group("link_label")
            result.append(
                '<span foreground="#0055cc" underline="single">{}</span>'.format(
                    inline_to_pango(label)
                )
            )
        elif kind in ("bold3", "und3"):
            t = m.group("bold3_t") if kind == "bold3" else m.group("und3_t")
            result.append("<b><i>{}</i></b>".format(inline_to_pango(t)))
        elif kind in ("bold2", "und2"):
            t = m.group("bold2_t") if kind == "bold2" else m.group("und2_t")
            result.append("<b>{}</b>".format(inline_to_pango(t)))
        elif kind == "code":
            result.append("<tt>{}</tt>".format(_esc(m.group("code_t"))))
        elif kind == "strike":
            result.append("<s>{}</s>".format(inline_to_pango(m.group("strike_t"))))
        elif kind in ("em1", "em2"):
            t = m.group("em1_t") if kind == "em1" else m.group("em2_t")
            result.append("<i>{}</i>".format(inline_to_pango(t)))
        else:
            result.append(_esc(m.group(0)))
        pos = m.end()

    return "".join(result)


# ---------------------------------------------------------------------------
#
# build_table_widget
#
# ---------------------------------------------------------------------------
def build_table_widget(
    columns: list[str],
    align: list[str],
    body_rows: list[list[str]],
    sep_widths: list[int] | None = None,
) -> Gtk.Frame:
    """Return a :class:`Gtk.Frame` containing a :class:`Gtk.TreeView` for a GFM table.

    Column widths are derived from whichever is larger:

    1. Content measure — max plain-text length across header + all body cells
       for that column, multiplied by an estimated ~7 px per character.
    2. Separator hint — the number of dashes in the GFM separator row
       (``|---|:-----:|``).

    :param columns:    List of header cell strings (may contain inline Markdown).
    :param align:      Per-column alignment strings: ``'left'``, ``'center'``,
                       or ``'right'``.
    :param body_rows:  List of rows; each row is a list of cell strings.
    :param sep_widths: Per-column dash count from the GFM separator row, used
                       as a minimum-width hint.  Defaults to 5 per column.
    :returns: A :class:`Gtk.Frame` containing the styled :class:`Gtk.TreeView`.
    """
    _PX_PER_CHAR = 7
    _MIN_COL_PX = 40
    _CELL_XPAD = 12

    ncols = len(columns)
    if sep_widths is None:
        sep_widths = [5] * ncols

    def plain(markup_str: str) -> str:
        """Strip basic Pango tags to get approximate display length."""
        return re.sub(r"<[^>]+>", "", markup_str)

    col_char_widths: list[int] = []
    for ci in range(ncols):
        hdr_len = len(plain(inline_to_pango(columns[ci])))
        cell_max = max(
            (
                len(plain(inline_to_pango(str(row[ci]))))
                for row in body_rows
                if ci < len(row)
            ),
            default=0,
        )
        col_char_widths.append(max(hdr_len, cell_max))

    col_min_px: list[int] = []
    for ci in range(ncols):
        content_px = col_char_widths[ci] * _PX_PER_CHAR + _CELL_XPAD
        sep_px = sep_widths[ci] * _PX_PER_CHAR + _CELL_XPAD
        col_min_px.append(max(content_px, sep_px, _MIN_COL_PX))

    store = Gtk.ListStore(*([str] * ncols))
    for row in body_rows:
        markup_row = [
            inline_to_pango(str(row[ci]) if ci < len(row) else "")
            for ci in range(ncols)
        ]
        store.append(markup_row)

    tv = Gtk.TreeView(model=store)
    tv.set_headers_visible(True)
    tv.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
    tv.set_enable_search(False)
    tv.set_reorderable(False)
    tv.set_rubber_banding(False)

    _xalign = {"left": 0.0, "center": 0.5, "right": 1.0}

    for ci, col_title in enumerate(columns):
        col_align = align[ci] if ci < len(align) else "left"
        xalign = _xalign.get(col_align, 0.0)

        renderer = Gtk.CellRendererText()
        renderer.set_property("xalign", xalign)
        renderer.set_property("xpad", 6)
        renderer.set_property("ypad", 3)
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)

        tvc = Gtk.TreeViewColumn(col_title, renderer, markup=ci)
        tvc.set_resizable(True)
        tvc.set_expand(True)
        tvc.set_min_width(col_min_px[ci])
        tvc.set_clickable(False)
        tvc.set_alignment(xalign)

        label = Gtk.Label()
        label.set_markup(
            "<b>{}</b>".format(
                col_title.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
        )
        label.show()
        tvc.set_widget(label)

        tv.append_column(tvc)

    frame = Gtk.Frame()
    frame.set_shadow_type(Gtk.ShadowType.IN)
    frame.add(tv)
    frame.set_margin_top(4)
    frame.set_margin_bottom(4)
    frame.show_all()
    return frame


# ---------------------------------------------------------------------------
#
# GRAMPS_ICONS  -- short-name alias map
#
# ---------------------------------------------------------------------------
GRAMPS_ICONS: dict[str, list[str]] = {
    # Object types
    "person": ["gramps-person"],
    "family": ["gramps-family"],
    "event": ["gramps-event"],
    "place": ["gramps-place"],
    "source": ["gramps-source"],
    "citation": ["gramps-citation"],
    "repository": ["gramps-repository"],
    "media": ["gramps-media", "gramps-mediaobject"],
    "note": ["gramps-notes", "gramps-note"],
    "tag": ["gramps-tag"],
    # Views / Dashboard
    "dashboard": ["gramps-gramplet"],
    "gramplet": ["gramps-gramplet"],
    "pedigree": ["gramps-pedigree"],
    "fanchart": ["gramps-fanchart"],
    "fan": ["gramps-fanchart"],
    "geo": ["gramps-geo", "gramps-geography"],
    "geography": ["gramps-geo", "gramps-geography"],
    "relation": ["gramps-relation", "gramps-relationship"],
    "relationship": ["gramps-relation", "gramps-relationship"],
    "reports": ["gramps-reports"],
    "tools": ["gramps-tools"],
    "date": ["gramps-date"],
    # Actions
    "merge": ["gramps-merge"],
    "lock": ["gramps-lock"],
    "unlock": ["gramps-unlock"],
}


# ---------------------------------------------------------------------------
#
# resolve_icon_pixbuf
#
# ---------------------------------------------------------------------------
def resolve_icon_pixbuf(
    icon_name: str,
    size: int,
    icon_theme: Gtk.IconTheme | None = None,
) -> GdkPixbuf.Pixbuf | None:
    """Return a :class:`GdkPixbuf.Pixbuf` for a named GTK/Gramps icon, or ``None``.

    Uses the *live* default :class:`Gtk.IconTheme` (or a caller-supplied theme)
    so the rendered icon always matches what the running Gramps GUI displays —
    including any GTK theme change applied by the Themes addon.

    Resolution order:

    1. Exact GTK named icon via the current theme cascade at *size* pixels,
       with ``GENERIC_FALLBACK | USE_BUILTIN`` flags so the result mirrors
       what :class:`Gtk.Image` would render.
    2. All candidate names from :data:`GRAMPS_ICONS` alias list, same flags.
    3. Raster PNG at exact pixel size from Gramps ``DATA_DIR``
       (e.g. ``22x22/actions/``, ``48x48/actions/``).
    4. Scalable SVG from Gramps ``DATA_DIR`` rendered at *size*.
    5. Gramps ``IMAGE_DIR`` files.

    ``GENERIC_FALLBACK`` causes GTK to retry with progressively shorter icon
    name prefixes (e.g. ``"go-next-symbolic"`` → ``"go-next"`` → ``"go"``)
    before giving up, which matches the lookup strategy used by GTK widgets
    internally.  ``USE_BUILTIN`` ensures that compiled-in icons are reached
    before falling through to the filesystem fallback paths below.

    :param icon_name:  GTK or Gramps short icon name.
    :param size:       Desired pixel size.
    :param icon_theme: Optional :class:`Gtk.IconTheme` to query; when ``None``
                       the process-wide default theme is used.
    :returns: :class:`GdkPixbuf.Pixbuf` or ``None`` if not found anywhere.
    """
    if icon_theme is None:
        icon_theme = Gtk.IconTheme.get_default()

    _FLAGS = Gtk.IconLookupFlags.GENERIC_FALLBACK | Gtk.IconLookupFlags.USE_BUILTIN

    def _load_named(name: str, px_size: int) -> GdkPixbuf.Pixbuf | None:
        """Try to load *name* from the icon theme cascade at *px_size* pixels.

        Uses ``GENERIC_FALLBACK | USE_BUILTIN`` so the result is identical to
        what :class:`Gtk.Image` renders when given the same icon name.

        :param name:    Freedesktop icon name.
        :param px_size: Desired pixel size.
        :returns: :class:`GdkPixbuf.Pixbuf` or ``None``.
        """
        try:
            info = icon_theme.lookup_icon(name, px_size, _FLAGS)
            if info:
                pb = info.load_icon()
                if pb:
                    return pb
        except Exception:  # pylint: disable=broad-except
            pass
        return None

    pb = _load_named(icon_name, size)
    if pb:
        return pb

    candidates = GRAMPS_ICONS.get(icon_name.lower(), [])
    for cand in candidates:
        pb = _load_named(cand, size)
        if pb:
            return pb

    try:
        from gramps.gen.const import DATA_DIR, IMAGE_DIR

        icon_base = os.path.join(DATA_DIR, "icons", "hicolor")
        raster_sizes = [size, 22, 48, 16, 24, 32, 64]
        seen_sizes: list[int] = []
        for s in raster_sizes:
            if s not in seen_sizes:
                seen_sizes.append(s)
        subdirs_raster = [
            os.path.join(icon_base, "{}x{}".format(s, s), cat)
            for s in seen_sizes
            for cat in ("actions", "apps", "places", "categories", "status")
        ]
        subdirs_svg = [
            os.path.join(icon_base, "scalable", cat)
            for cat in ("actions", "apps", "places", "categories", "status")
        ]
        all_names = [icon_name] + candidates

        for d in subdirs_raster:
            for name in all_names:
                fp = os.path.join(d, name + ".png")
                if os.path.isfile(fp):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(fp, size, size)
                        if pb:
                            return pb
                    except Exception:
                        pass

        for d in subdirs_svg:
            for name in all_names:
                fp = os.path.join(d, name + ".svg")
                if os.path.isfile(fp):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(fp, size, size)
                        if pb:
                            return pb
                    except Exception:
                        pass

        for name in all_names:
            for ext in (".png", ".svg", ".jpg"):
                fp = os.path.join(IMAGE_DIR, name + ext)
                if os.path.isfile(fp):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(fp, size, size)
                        if pb:
                            return pb
                    except Exception:
                        pass
    except ImportError:
        pass

    return None


# ---------------------------------------------------------------------------
#
# list_icons_by_context
#
# ---------------------------------------------------------------------------
def list_icons_by_context(
    context: str | None = None,
    icon_theme: Gtk.IconTheme | None = None,
) -> list[str]:
    """Return a sorted list of icon names available in the current theme cascade.

    Wraps :meth:`Gtk.IconTheme.list_icons` so callers (e.g.
    :class:`IconBrowserGramplet`) do not need to import GTK directly.  The
    enumeration follows the full freedesktop inheritance chain — current theme
    → parent themes → hicolor — because :meth:`Gtk.IconTheme.get_default`
    already incorporates every layer.

    When *context* is ``None`` all icons are returned regardless of their
    freedesktop context (Actions, Apps, Devices, …).  When a context string is
    given, only icons tagged with that context in the theme's ``index.theme``
    are included.

    :param context:    Freedesktop context name (e.g. ``'Actions'``), or
                       ``None`` to return every icon in the cascade.
    :param icon_theme: Optional :class:`Gtk.IconTheme` to query; when ``None``
                       the process-wide default theme is used so the result
                       always mirrors the live Gramps GUI theme.
    :returns: Alphabetically sorted (case-insensitive) list of icon name strings.
    """
    if icon_theme is None:
        icon_theme = Gtk.IconTheme.get_default()
    names: list[str] = icon_theme.list_icons(context) or []
    return sorted(names, key=str.casefold)


# ---------------------------------------------------------------------------
# Gramps object-type maps (shared by any consumer of this library)
# ---------------------------------------------------------------------------

#: Mapping from Gramps object-type name to
#: ``(gramps_id_getter, handle_getter, editor_class_name)``.
NAMESPACE_MAP: dict[str, tuple[str, str, str]] = {
    "Person": (
        "get_person_from_gramps_id",
        "get_person_from_handle",
        "EditPerson",
    ),
    "Family": (
        "get_family_from_gramps_id",
        "get_family_from_handle",
        "EditFamily",
    ),
    "Event": (
        "get_event_from_gramps_id",
        "get_event_from_handle",
        "EditEvent",
    ),
    "Place": (
        "get_place_from_gramps_id",
        "get_place_from_handle",
        "EditPlace",
    ),
    "Source": (
        "get_source_from_gramps_id",
        "get_source_from_handle",
        "EditSource",
    ),
    "Citation": (
        "get_citation_from_gramps_id",
        "get_citation_from_handle",
        "EditCitation",
    ),
    "Repository": (
        "get_repository_from_gramps_id",
        "get_repository_from_handle",
        "EditRepository",
    ),
    "Media": (
        "get_media_from_gramps_id",
        "get_media_from_handle",
        "EditMedia",
    ),
    "Note": (
        "get_note_from_gramps_id",
        "get_note_from_handle",
        "EditNote",
    ),
}

#: Lowercase category alias → canonical Gramps view-category name.
VIEW_NAMES: dict[str, str] = {
    "people": "People",
    "person": "People",
    "families": "Families",
    "family": "Families",
    "events": "Events",
    "event": "Events",
    "places": "Places",
    "place": "Places",
    "sources": "Sources",
    "source": "Sources",
    "citations": "Citations",
    "citation": "Citations",
    "repositories": "Repositories",
    "repository": "Repositories",
    "media": "Media",
    "notes": "Notes",
    "note": "Notes",
    "geography": "Geography",
    "charts": "Charts",
    "dashboard": "Dashboard",
}
