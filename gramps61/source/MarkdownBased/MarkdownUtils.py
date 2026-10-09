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
  - ``resolve_icon_pixbuf()``   -- resolve a GTK/Gramps icon to a GdkPixbuf (Theme-aware)
  - ``list_icons_by_context()`` -- enumerate icon names from the live theme cascade
  - ``GRAMPS_ICONS``            -- short-name → GTK icon-name alias map
  - ``NAMESPACE_MAP``           -- Gramps object-type → DB getter / editor map
  - ``VIEW_NAMES``              -- lowercase category alias → canonical view name
  - ``locale_lang()``           -- (``ll_CC``, ``ll``) for the current Gramps locale
  - ``resolve_localized_path()``-- best locale variant of a document (README.md → README.fr.md etc.)
  - ``resolve_localized_asset()``-- best locale variant of an image / linked asset
  - ``PathResolution``          -- result of ``resolve_localized_path()``
  - ``LANG_SUFFIX_RE``          -- matches ``<stem>_<lang>.<ext>`` source-language names

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

Theme & Context Sync Alignment
-------------------------------
This version brings the pixel-rendering layer into synchronization with live
GTK widgets. By passing a widget's ``Gtk.StyleContext`` to ``resolve_icon_pixbuf``,
symbolic line-art variants inherit foreground, background, and state-based colors
directly from the active window workspace, preventing invisible or inverted icons
across light/dark mode variations while still permitting full-scale color imagery
for illustrative documentation text blocks.

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
list_icons_by_context() public helper for IconBrowserGramplet enumeration;
implement theme context syncing for symbolic variants via load_symbolic_for_context."
Revision prompt (19 Sep 2026, Claude Sonnet 5, Anthropic, claude-sonnet-5): "extend MarkdownUtils
with the localization support so it can be trimmed out of the other modules
(including MarkdownDash.py) and call a common codebase" -- locale_lang,
PathResolution, LANG_SUFFIX_RE and resolve_localized_path moved here verbatim
from MarkdownDash.py; resolve_localized_asset and PathResolution.exists added.
Constraints: https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
             https://github.com/gramps-project/gramps/blob/master/AGENTS.md

Revised 20 Aug 2026  for bug fixes.
- More control over fallback to Symbolic icons
- Better support for image inset in tables
- enhanced to reduce redundant Markdown Rendering Code in Plugin Manager plus

Fixed 8 Oct 2026:
- "gtk_widget_size_allocate(): attempt to allocate widget with ... height
  -7" warnings while scrolling past tables: the table Frame no longer has
  margins (see the end of build_table_widget); confirmed in Gramps.
- Table columns drifting out of line from row to row: one Gtk.SizeGroup
  per column.

Next target for fixes:
- console warnings during scrolling, if they still appear (not reproduced
  since the fixes above):
    *** BUG ***
    In pixman_region32_init_rect: Invalid rectangle passed
    Set a breakpoint on '_pixman_log_error' to debug

Wishlist:
    search for string in Markdown text (stripped of formatting, lower case forced)
    support for showing normal/large thumbnail for the 1st Gallery object

"""
# ------------------------
# Python modules
# ------------------------
import os
import re
from typing import Callable

# ------------------------
# Gramps modules
# ------------------------
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.const import IMAGE_DIR, THUMB_DIR

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
import logging

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#
# Localization -- locale-aware document and asset lookup
#
# The single implementation shared by MarkdownDash, Plugin Manager Plus and
# any add-on's Help button, so the lookup convention lives in one place:
#
#   <addon_dir>/
#       README.md                    # English baseline
#       README_fi.md                 # or: source-language baseline (Finnish)
#       locale/
#           fr_FR/README.md          # full locale variant (highest priority)
#           fr/README.md             # short-code variant
#           fr/diagram.png           # localized asset, same lookup order
#
# See resolve_localized_path() for the full resolution order.
#
# ---------------------------------------------------------------------------


def locale_lang() -> tuple[str, str]:
    """Return ``(lang_full_normalized, lang_short)`` from the Gramps locale.

    Uses the real :class:`~gramps.gen.utils.grampslocale.GrampsLocale` API:

    - ``glocale.lang``       — POSIX locale string, e.g. ``"fi_FI.UTF-8"``
    - ``glocale.language``   — list of translation codes, e.g. ``["fi"]``

    The full form is normalised to ``<ll_CC>`` (stripping ``.UTF-8`` etc.) for
    use as a directory name component.  Falls back to ``("en_US", "en")`` on
    any error so callers never need to handle ``None``.

    :returns: Tuple ``(lang_full_normalized, lang_short)`` e.g.
        ``("fi_FI", "fi")`` or ``("en_US", "en")``.
    """
    try:
        lang_short = (glocale.language or ["en"])[0] or "en"
        # glocale.lang is a POSIX string like "fi_FI.UTF-8"; strip the codeset
        lang_full = (glocale.lang or "en_US").split(".")[0].split("@")[0]
        if not lang_full or lang_full == "C":
            lang_full = "en_US"
        return lang_full, lang_short
    except Exception:  # pylint: disable=broad-exception-caught
        return "en_US", "en"


# ------------------------------------------------------------
#
# PathResolution
#
# ------------------------------------------------------------
class PathResolution:  # pylint: disable=too-few-public-methods
    """Result of :func:`resolve_localized_path`.

    :param path:           Best-matching file path to display.
    :param is_fallback:    ``True`` when no locale variant was found and the
        baseline (or source-language) file is being shown instead.
    :param source_lang:    ISO 639-1 code of the file's *authoring* language
        (e.g. ``"fi"`` for Finnish), or ``None`` when the baseline is
        unlabelled English (``README.md``).
    :param user_lang:      Short BCP-47 language code for the current user
        (e.g. ``"en"``).  Provided for convenience so callers don't need to
        call :func:`locale_lang` themselves.
    """

    __slots__ = ("path", "is_fallback", "source_lang", "user_lang")

    def __init__(
        self,
        path: str,
        is_fallback: bool = False,
        source_lang: str | None = None,
        user_lang: str = "en",
    ) -> None:
        """Initialise a PathResolution result."""
        self.path = path
        self.is_fallback = is_fallback
        self.source_lang = source_lang
        self.user_lang = user_lang

    def exists(self) -> bool:
        """Return ``True`` if :attr:`path` names an existing local file.

        Lets a caller that only needs to know *whether any* variant exists
        (e.g. a Help button choosing between a README viewer and a browser)
        avoid re-implementing the lookup convention.
        """
        return bool(self.path) and os.path.isfile(self.path)


# Matches  README_fi.md / README_fr_FR.md / MyAddon_help_de.md etc.
LANG_SUFFIX_RE = re.compile(
    r"^(?P<stem>.+?)_(?P<lang>[a-z]{2}(?:_[A-Z]{2})?)(?P<ext>\.[^.]+)$"
)


def resolve_localized_path(path: str) -> PathResolution:
    """Resolve *path* to the best available locale variant.

    Resolution order
    ----------------
    1. ``<dir>/locale/<lang_full>/<filename>``  e.g. ``locale/fr_FR/README.md``
    2. ``<dir>/locale/<lang_short>/<filename>`` e.g. ``locale/fr/README.md``
    3. ``<dir>/<filename>`` — the unlabelled English baseline.
    4. ``<dir>/<stem>_<lang><ext>`` — a source-language-labelled baseline
       (e.g. ``README_fi.md`` meaning the add-on documentation is in Finnish).
       The matching file with the *user's* language suffix is tried first.

    In cases 3 and 4, :attr:`PathResolution.is_fallback` is ``True`` when the
    user's locale is not English (case 3) or does not match the source language
    (case 4).

    :param path: Absolute or ``~``-prefixed path to the *canonical* (English
        or unlabelled) baseline file.  The filename need not exist on disk;
        the stem and extension are used to locate labelled variants.
    :returns: A :class:`PathResolution` describing the best available file.
    """
    if not path:
        return PathResolution(path)

    path = os.path.abspath(os.path.expanduser(path))
    base_dir = os.path.dirname(path)
    filename = os.path.basename(path)
    lang_full, lang_short = locale_lang()

    # ── 1 & 2: locale sub-directory variants ────────────────────────────
    for lang_code in (lang_full, lang_short):
        variant = os.path.join(base_dir, "locale", lang_code, filename)
        if os.path.isfile(variant):
            return PathResolution(
                variant, is_fallback=False, source_lang=None, user_lang=lang_short
            )

    # ── 3: unlabelled baseline (README.md) ──────────────────────────────
    if os.path.isfile(path):
        is_fb = lang_short not in ("en",)
        return PathResolution(
            path, is_fallback=is_fb, source_lang=None, user_lang=lang_short
        )

    # ── 4: source-language-labelled baseline (README_fi.md) ─────────────
    stem, ext = os.path.splitext(filename)
    # Try the user's own language first (Finnish user + README_fi.md → no invite)
    for lang_code in (lang_full, lang_short):
        candidate = os.path.join(base_dir, f"{stem}_{lang_code}{ext}")
        if os.path.isfile(candidate):
            return PathResolution(
                candidate,
                is_fallback=False,
                source_lang=lang_code,
                user_lang=lang_short,
            )

    # Scan for any labelled variant (e.g. README_fi.md when user is English)
    try:
        entries = os.listdir(base_dir)
    except OSError:
        entries = []

    for entry in sorted(entries):
        m = LANG_SUFFIX_RE.match(entry)
        if m and m.group("stem") == stem and m.group("ext") == ext:
            found_lang = m.group("lang")
            candidate = os.path.join(base_dir, entry)
            if os.path.isfile(candidate):
                # is_fallback: user differs from source language
                is_fb = found_lang.split("_")[0] != lang_short
                return PathResolution(
                    candidate,
                    is_fallback=is_fb,
                    source_lang=found_lang,
                    user_lang=lang_short,
                )

    # Nothing found at all — return the original path (will trigger error page)
    return PathResolution(
        path, is_fallback=False, source_lang=None, user_lang=lang_short
    )


def resolve_localized_asset(base_dir: str, rel_path: str) -> str:
    """Resolve a relative asset path (image, linked file) to its best locale variant.

    Asset paths in a Markdown file are relative to the *canonical* document
    directory, not to the ``locale/<lang>/`` folder a translated README may
    live in, so the lookup order is:

    1. ``<base_dir>/locale/<lang_full>/<rel_path>`` e.g. ``locale/fr_FR/x.png``
    2. ``<base_dir>/locale/<lang_short>/<rel_path>`` e.g. ``locale/fr/x.png``
    3. ``<base_dir>/<rel_path>`` -- the canonical asset.

    :param base_dir: The canonical document directory.
    :param rel_path: Relative asset path taken from the Markdown source.
    :returns: The best existing file path, or *rel_path* unchanged if nothing
        resolves (the caller handles a missing asset).
    """
    lang_full, lang_short = locale_lang()
    for lang_code in (lang_full, lang_short):
        localized = os.path.join(base_dir, "locale", lang_code, rel_path)
        if os.path.isfile(localized):
            return localized
    candidate = os.path.join(base_dir, rel_path)
    if os.path.isfile(candidate):
        return candidate
    return rel_path


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
    :param gramps_icon: ``(icon_name, size, icon_style)`` tuple to embed a
        GTK theme icon
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
#
# <br>/<kbd> support: neither is Markdown proper, but both are common
# enough inside Markdown documents (a forced line break, a keyboard-
# shortcut hint) that GFM and most renderers pass them through. ``kbd``
# supports up to one level of nesting (e.g. ``<kbd>Ctrl+<kbd>C</kbd></kbd>``)
# via an explicit "one optional nested pair" shape -- Python's ``re`` has
# no general balanced-tag/recursion support, so arbitrary nesting depth
# isn't representable here, but one level covers every real-world
# keyboard-combo example seen in the wild. Case-insensitive throughout
# (``<BR>``, ``<Kbd>``, ...); every other alternative below is built from
# punctuation with no letter case to worry about, so applying
# ``re.IGNORECASE`` to the whole pattern is safe.
_INLINE_RE = re.compile(
    r"(?P<img>!\[(?P<img_alt>[^\]]*)\]\((?P<img_url>[^)]*)\))"
    r"|(?P<link>\[(?P<link_label>[^\]]+)\]\((?P<link_url>[^)]+)\))"
    r"|(?P<br><br\s*/?>)"
    r"|(?P<kbd><kbd>(?P<kbd_t>(?:(?!</?kbd>).)*"
    r"(?:<kbd>(?:(?!</?kbd>).)*</kbd>(?:(?!</?kbd>).)*)?)</kbd>)"
    r"|(?P<bold3>\*{3}(?P<bold3_t>.+?)\*{3})"
    r"|(?P<und3>_{3}(?P<und3_t>.+?)_{3})"
    r"|(?P<bold2>\*{2}(?P<bold2_t>.+?)\*{2})"
    r"|(?P<und2>_{2}(?P<und2_t>.+?)_{2})"
    r"|(?P<code>`(?P<code_t>[^`\n]+)`)"
    r"|(?P<strike>~~(?P<strike_t>.+?)~~)"
    r"|(?P<em1>(?<!\*)\*(?!\*)(?P<em1_t>[^*\n]+?)(?<!\*)\*(?!\*))"
    r"|(?P<em2>(?<!\w)_(?!_)(?P<em2_t>[^_\n]+?)(?<!_)_(?!\w))",
    re.DOTALL | re.IGNORECASE,
)



#: A fenced code block opening line: up to 3 spaces, then 3+ backticks
#: or 3+ tildes (GFM). The block runs to a line of the same character,
#: at least as long.
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

#: One left-to-right scan for whichever comes first: an inline code span
#: (a run of backticks, its content on one line, and a matching run) or a
#: comment. Scanning both together means a comment that itself contains
#: backticks is still hidden whole, and a comment inside a code span is
#: still shown.
_CODE_SPAN_OR_COMMENT_RE = re.compile(
    r"(?P<code>(?P<ticks>`+)[^\n]*?(?<!`)(?P=ticks)(?!`))|(?P<comment><!--.*?-->)",
    re.DOTALL,
)


def _strip_comments_outside_code_spans(text: str) -> str:
    """Hide ``<!-- ... -->`` comments in *text*, keeping inline code spans.

    :param text: Markdown text containing no fenced code blocks.
    :returns: *text* with comments outside code spans removed.
    """
    return _CODE_SPAN_OR_COMMENT_RE.sub(
        lambda m: "" if m.group("comment") is not None else m.group(0), text
    )


def _strip_hidden_comments(md_text: str) -> str:
    """Remove ``<!-- ... -->`` comment blocks from *md_text* before parsing.

    Comments -- single- or multi-line -- are hidden from the rendered
    document, as GitHub hides them, so authors can leave notes in a file.
    Only the display is affected: the file on disk is never changed.

    Comments inside a fenced code block (three or more backticks or
    tildes) or an inline code span are shown exactly as written, as on
    GitHub, so a document can show comment syntax as an example (such as
    Markdown Dash's own layout-options comment).

    This is a *document-body* concern only: MarkdownDash's own leading
    title (``# Title`` on line 1) and layout-options directive
    (``<!-- key=value ... -->`` on line 2) are a separate, file-header
    convention consumed by that gramplet's own ``_parse_directives()``
    *before* the remaining text is ever handed to :func:`parse_markdown`
    -- so this function never sees, and does not need to special-case,
    that directive line.

    :param md_text: Raw Markdown document text, before block parsing.
    :returns: *md_text* with comments outside code removed.
    """
    out: list[str] = []
    plain: list[str] = []  # lines outside fenced blocks, not yet processed
    fence = None  # the opening fence string while inside a fenced block
    for line in md_text.splitlines(keepends=True):
        if fence is None:
            m = _FENCE_OPEN_RE.match(line)
            if m:
                out.append(_strip_comments_outside_code_spans("".join(plain)))
                plain = []
                fence = m.group(1)
                out.append(line)
            else:
                plain.append(line)
        else:
            out.append(line)
            closing = line.strip()
            if (
                len(closing) >= len(fence)
                and closing.startswith(fence[0])
                and set(closing) == {fence[0]}
            ):
                fence = None
    out.append(_strip_comments_outside_code_spans("".join(plain)))
    return "".join(out)


#: Accepted values for icon color-fallback control, used both by
#: :func:`resolve_icon_pixbuf`'s ``icon_style`` parameter and by the
#: optional third field of the inline ``gramps:icon:NAME[:SIZE[:STYLE]]``
#: Markdown syntax:
#:
#: - ``'auto'``     -- the previous fixed default: prefer the symbolic
#:                     (B&W) asset for icon sizes <=32px, prefer the
#:                     full-color asset above that; falls back to
#:                     whichever variant actually exists if the preferred
#:                     one is missing for that icon.
#: - ``'color'``    -- always prefer the full-color asset regardless of
#:                     size; falls back to symbolic only if no color
#:                     asset exists anywhere for that icon.
#: - ``'symbolic'`` -- always prefer the symbolic/B&W asset regardless of
#:                     size; falls back to color only if no symbolic
#:                     asset exists anywhere for that icon.
#:
#: An unrecognized value is treated as ``'auto'``.
ICON_STYLE_AUTO = "auto"
ICON_STYLE_COLOR = "color"
ICON_STYLE_SYMBOLIC = "symbolic"
_VALID_ICON_STYLES = {ICON_STYLE_AUTO, ICON_STYLE_COLOR, ICON_STYLE_SYMBOLIC}

# ---------------------------------------------------------------------------
#
# Enhanced-renderer nudge for Markdown this bundled renderer can't render
#
# ---------------------------------------------------------------------------
# Neither table_style ("widget" or "text") makes a Markdown link inside a
# table cell clickable -- both render it as styled-but-inert text (see
# render_cell() in build_table_widget/build_table_text) -- and that's very
# unlikely to be the last such gap in a deliberately lightweight,
# dependency-free fallback renderer. Rather than growing this renderer's
# own handling further every time a new one turns up, any such situation
# can instead show one small, genuinely clickable (this is a normal
# paragraph-level hyperlink, which already works everywhere in this
# renderer) note pointing at wherever you want to advertise a more
# fully-featured Markdown renderer as the real answer for documents that
# need it -- see emit_enhanced_renderer_notice() below, and its current
# call site for the table-cell-link case in render_markdown()/_render().
# The wording is deliberately generic (not "this table...") so the same
# notice and call site can be reused for whatever the next gap turns out
# to be. Edit the three constants below to taste; none of this fires
# unless a caller actually detects something it can't render, so it
# costs an already-fully-renderable document nothing.
ENHANCED_RENDERER_NOTICE = (
    "This contains Markdown tags that cannot be rendered by the basic "
    "bundled Markdown handler."
)
ENHANCED_RENDERER_LINK_TEXT = "Learn about enabling enhanced Markdown rendering"
# TODO: point this at whatever richer Markdown renderer you want to
# advertise as the answer for documents that need more than this bundled
# renderer supports (e.g. a WebKit2-backed HTML renderer, or a full
# markdown-it/python-markdown pipeline) -- this placeholder just points
# at this addon's own wiki page.
ENHANCED_RENDERER_LINK_URL = "https://gramps-project.org/wiki/index.php/Addon:MarkdownDash"

_CELL_LINK_DETECT_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")


def table_has_uninteractive_links(columns: list[str], body_rows: list[list[str]]) -> bool:
    """
    Return whether any header or body cell contains a Markdown link.

    Used to decide whether to show the enhanced-renderer fallback note
    (:func:`emit_enhanced_renderer_notice`) below a rendered table --
    see :data:`ENHANCED_RENDERER_NOTICE`'s own comment for the
    rationale. A false positive (e.g. literal `[x](y)`-shaped text that
    isn't meant as a link) only costs an extra, still genuinely useful
    notice; there is no false-negative cost worth guarding harder
    against here.

    :param columns: Header cell strings.
    :param body_rows: Table body rows; each row is a list of cell strings.
    :returns: ``True`` if any cell's raw text matches ``[label](url)``.
    """
    all_cells = list(columns) + [str(cell) for row in body_rows for cell in row]
    return any(_CELL_LINK_DETECT_RE.search(cell) for cell in all_cells)


def emit_enhanced_renderer_notice(
    buf: Gtk.TextBuffer,
    it: Gtk.TextIter,
    tags: dict[str, Gtk.TextTag],
    make_link_tag: Callable[[str, str], Gtk.TextTag],
) -> None:
    """
    Insert one italic, genuinely-clickable "enhanced renderer" note.

    Call this at any point where a caller has just detected Markdown it
    cannot fully render (currently: a link inside a table cell, via
    :func:`table_has_uninteractive_links` -- see that constant's own
    comment on :data:`ENHANCED_RENDERER_NOTICE` for the rationale for
    keeping this generic rather than growing this renderer's own
    handling indefinitely). The note itself is ordinary paragraph text
    with a real hyperlink tag, the same mechanism every other clickable
    link in the document already uses -- unlike whatever content
    triggered showing it, this note itself is always clickable.

    :param buf: The buffer to insert into.
    :param it: Iterator at the current insert position; left at the end
        of the inserted note (a trailing newline) on return.
    :param tags: The document's style tags, as returned by
        :func:`define_tags` -- only ``tags["italic"]`` is used, and its
        absence is tolerated (the note is then inserted un-italicized
        rather than failing).
    :param make_link_tag: A ``(style, uri) -> Gtk.TextTag`` callable, as
        defined locally by :func:`render_markdown` and by
        ``MarkdownDash._render`` -- creates a uniquely-named tag and
        registers it in the caller's own ``link_uris`` mapping so the
        existing click-handling machinery picks it up.
    """
    notice_start_mark = buf.create_mark(None, it, True)
    buf.insert(it, "\u2139\ufe0f " + ENHANCED_RENDERER_NOTICE + " ")
    link_start_mark = buf.create_mark(None, it, True)
    buf.insert(it, ENHANCED_RENDERER_LINK_TEXT)
    link_start_it = buf.get_iter_at_mark(link_start_mark)
    note_tag = make_link_tag("hyperlink", ENHANCED_RENDERER_LINK_URL)
    buf.apply_tag(note_tag, link_start_it, it)
    buf.delete_mark(link_start_mark)
    italic_tag = tags.get("italic")
    if italic_tag:
        notice_start_it = buf.get_iter_at_mark(notice_start_mark)
        buf.apply_tag(italic_tag, notice_start_it, it)
    buf.delete_mark(notice_start_mark)
    buf.insert(it, "\n")

#: Ambient default icon style for the current :func:`parse_markdown` call,
#: read by :func:`_parse_inline`'s image handling when a ``gramps:icon:``
#: reference doesn't specify its own ``:STYLE`` suffix. ``_parse_inline``
#: recurses through more than a dozen call sites (nested emphasis, links,
#: list items, blockquotes...), so this is set once at the top of
#: :func:`parse_markdown` and restored afterwards rather than threaded
#: through every one of those signatures individually. Safe under Gramps'
#: single-threaded GTK main-loop model; not safe if ``parse_markdown`` is
#: ever called concurrently from multiple threads.
_current_default_icon_style = ICON_STYLE_AUTO

#: Matches a Gramps inline icon image URL:
#: ``gramps:icon:NAME``, ``gramps:icon:NAME:SIZE``, or
#: ``gramps:icon:NAME:SIZE:STYLE`` (STYLE is one of :data:`_VALID_ICON_STYLES`).
#: Shared between :func:`_parse_inline` (regular TextBuffer flow) and
#: :func:`_extract_leading_icon` (table cells).
_GRAMPS_ICON_URL_RE = re.compile(
    r"^gramps:icon:([^:]+)(?::(\d+))?(?::(auto|color|symbolic))?$"
)


def _extract_leading_icon(
    text: str, default_icon_style: str = ICON_STYLE_AUTO
) -> tuple:
    """Pull the first ``gramps:icon:`` image reference out of *text*.

    A :class:`Gtk.TreeView` table cell can only display a single real
    ``GdkPixbuf.Pixbuf`` per column (via a paired ``CellRendererPixbuf`` +
    ``CellRendererText``, see :func:`build_table_widget`), so only the
    *first* Gramps icon reference in a cell becomes an actual rendered
    icon. Any additional image/icon references later in the same cell
    still render as italicized alt text via :func:`inline_to_pango`,
    unchanged from before.

    :param text:               Raw cell Markdown text.
    :param default_icon_style: :data:`ICON_STYLE_AUTO`/``'color'``/``'symbolic'``
        to use when the icon reference doesn't specify its own ``:STYLE``
        suffix (e.g. a document-wide default from a control-comment option).
    :returns: ``((icon_name, size, icon_style), remaining_text)`` if a
             Gramps icon reference was found and removed from *text*, else
             ``(None, text)`` with *text* unchanged.
    """
    for m in _INLINE_RE.finditer(text):
        if m.lastgroup != "img":
            continue
        gi_m = _GRAMPS_ICON_URL_RE.match(m.group("img_url"))
        if gi_m:
            icon_name = gi_m.group(1)
            size = int(gi_m.group(2)) if gi_m.group(2) else 16
            icon_style = gi_m.group(3) or default_icon_style
            remaining = (text[: m.start()] + text[m.end() :]).strip()
            return (icon_name, size, icon_style), remaining
    return None, text


def _esc(text: str) -> str:
    """XML-escape *text* for use inside Pango markup.

    :param text: Raw text string.
    :returns: XML-safe string.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _heading_anchor(text: str) -> str:
    """Derive a GitHub-style anchor slug from a heading's plain text.

    Algorithm:
      1. Strip inline Markdown tokens to get display text.
      2. Lower-case.
      3. Remove everything that is not a letter, digit, space, or hyphen.
      4. Replace runs of whitespace with a single ``-``.

    :param text: Raw heading text (may contain inline Markdown).
    :returns: Anchor slug string.
    """
    plain = re.sub(r"</?kbd>|<br\s*/?>", "", text, flags=re.IGNORECASE)
    plain = re.sub(r"[*_`~\[\]!]", "", plain)
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
            gi_m = _GRAMPS_ICON_URL_RE.match(url)
            if gi_m:
                icon_name = gi_m.group(1)
                size = int(gi_m.group(2)) if gi_m.group(2) else 16
                icon_style = gi_m.group(3) or _current_default_icon_style
                segments.append(
                    Segment(
                        alt or icon_name,
                        base[:],
                        gramps_icon=(icon_name, size, icon_style),
                    )
                )
            else:
                segments.append(
                    Segment(alt or url, base + ["image_link"], image_path=url)
                )

        elif kind == "link":
            label = m.group("link_label")
            url = m.group("link_url")
            if url.startswith("#"):
                inner = _parse_inline(label, base + ["anchor_link"])
                for seg in inner:
                    seg.url = url
                segments.extend(inner)
            # gramps:view: is a Gramps link too: a consumer such as Markdown
            # Dash routes "gramps_link" clicks to its own Gramps handler but
            # hands every other link to the desktop, which cannot open a
            # gramps: address.
            elif url.startswith(("gramps:nav:", "gramps:edit:", "gramps:view:")):
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

        elif kind == "br":
            segments.append(Segment("\n", base[:]))

        elif kind == "kbd":
            segments.extend(_parse_inline(m.group("kbd_t"), base + ["kbd"]))

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
def parse_markdown(
    md_text: str, default_icon_style: str = ICON_STYLE_AUTO
) -> list[Segment]:
    """Parse a Markdown document into a flat list of :class:`Segment` objects.

    Supported block constructs:
      - ATX headings (``# H1`` … ``###### H6``) with anchor slugs
      - Setext headings (underlined with ``=`` or ``-``)
      - Fenced code blocks (backtick or tilde)
      - GFM tables
      - Blockquotes
      - Unordered and ordered lists (with nesting)
      - Horizontal rules (Width tuned to 25 to protect narrow responsive columns)
      - Blank lines and paragraphs

    Heading :class:`Segment` objects carry a non-``None`` ``anchor`` attribute
    equal to the GitHub-style anchor slug so the caller can place a
    ``Gtk.TextMark`` for in-document scroll navigation.

    :param md_text: Full Markdown document text.
    :param default_icon_style: :data:`ICON_STYLE_AUTO` (default),
        ``'color'``, or ``'symbolic'`` -- applies to every
        ``gramps:icon:NAME[:SIZE]`` reference in the document that doesn't
        specify its own ``:STYLE`` suffix. Typically sourced from a
        document-wide control-comment option (e.g. MarkdownDash's
        ``<!-- icon_style=color -->``) rather than hardcoded by the caller.
    :returns: List of :class:`Segment` objects.
    """
    global _current_default_icon_style
    if default_icon_style not in _VALID_ICON_STYLES:
        default_icon_style = ICON_STYLE_AUTO
    _current_default_icon_style = default_icon_style

    md_text = _strip_hidden_comments(md_text)
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

        Per GFM, ``\\|`` inside a cell is an escaped, literal pipe
        character -- not a column delimiter. A naive ``line.split("|")``
        here previously split on those too, silently producing extra
        cells for any row containing one (confirmed: a real regex
        pattern cell, ``^(John\\|Jon\\|Jonathan)$``, split into three
        cells instead of one). Worse, since :func:`flush_table` sets
        the whole table's column count to the *maximum* cell count seen
        across every row, that single malformed row corrupted every
        other row in the same table too, padding them with spurious
        empty trailing columns.

        :param line: A raw table row line.
        :returns: List of cell content strings, with any ``\\|`` already
            un-escaped back to a literal ``|``.
        """
        s = line.strip()
        if s.startswith("|"):
            s = s[1:]
        if s.endswith("|") and not s.endswith("\\|"):
            s = s[:-1]
        cells = re.split(r"(?<!\\)\|", s)
        return [c.strip().replace("\\|", "|") for c in cells]

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
        ncols = max(len(header_row), max((len(r) for r in body_rows), default=0))
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
        if fence := re.match(r"^(`{3,}|~{3,})(.*)", raw):
            if not in_code:
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

            if len(header_row) != len(sep_cells):
                # Malformed table: the header and separator rows (the
                # "first 2 rows" of a GFM table) disagree on column
                # count. flush_table below pads header_row/body_rows up
                # to ncols = max(...) when they're short, but align/
                # sep_widths are sized only from sep_cells and were
                # never given the same treatment -- so build_table_widget
                # indexing align[ci]/sep_widths[ci] up to that wider
                # ncols raised IndexError there. Because parse_markdown
                # builds this whole document's segment list in one call,
                # before MarkdownDash._render's per-segment loop ever
                # starts, that IndexError aborted the *entire* document,
                # not just this one table.
                #
                # Rather than guess how to reconcile the mismatched
                # counts into a real table, render this table's own raw
                # lines as plain (monospace) text -- preserving its
                # original pipe/dash layout so the malformed markup
                # itself stays visible and diagnosable -- and keep
                # parsing the rest of the document normally.
                table_lines = [raw, lines[i + 1]]
                j = i + 2
                while j < len(lines) and "|" in lines[j] and lines[j].strip():
                    table_lines.append(lines[j])
                    j += 1
                for table_line in table_lines:
                    add(table_line + "\n", ("code_block",))
                add("\n")
                i = j
                continue

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
        if bq := re.match(r"^>\s?(.*)", raw):
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
        if h := re.match(r"^(#{1,6})\s+(.*)", raw):
            add_heading(h.group(2).rstrip("# ").strip(), len(h.group(1)))
            i += 1
            continue

        # ── horizontal rule ──────────────────────────────────────────────
        if re.match(r"^(\*{3,}|-{3,}|_{3,})\s*$", raw):
            add("─" * 25 + "\n\n", ("hr",))
            i += 1
            continue

        # ── unordered list ───────────────────────────────────────────────
        if ul := re.match(r"^(\s*)([-*+])\s+(.*)", raw):
            depth = len(ul.group(1)) // 2
            add("    " * depth + "\u2022 ", ("list_bullet",))
            segments.extend(_parse_inline(ul.group(3)))
            add("\n")
            i += 1
            continue

        # ── ordered list ─────────────────────────────────────────────────
        if ol := re.match(r"^(\s*)(\d+)\.\s+(.*)", raw):
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
    tag(
        "blockquote",
        foreground="#555555",
        style=S_ITALIC,
        left_margin=28,
        indent=-28,
        pixels_above_lines=2,
        pixels_below_lines=2,
    )
    tag("blockquote_bar", foreground="#aaaaaa", weight=W_BOLD)
    # code_block/code_fence_marker previously also carried
    # paragraph_background, which paints a background rectangle across
    # the tag's full paragraph width rather than just its characters.
    # A live report described that rectangle reaching the right edge
    # of the window with no matching gutter on that side, unlike the
    # left; setting right_margin directly on these tags (tried first,
    # since it's the smaller change) made no visible difference,
    # confirming paragraph_background doesn't reliably respect a
    # right_margin here regardless of where it's set. Dropped
    # paragraph_background entirely -- plain background (kept below)
    # only colors the actual character runs, so it can't run past a
    # margin it never tries to reach in the first place. The tradeoff:
    # a solid block became a highlight that stops wherever each
    # line's own text ends, which will look ragged on the right for
    # code blocks with lines of uneven length, not a clean rectangle.
    # Not yet confirmed which look is preferred, only that this is the
    # one true fix available for the edge-to-edge complaint itself.
    tag(
        "code_block",
        family="Monospace",
        foreground="#222222",
        background="#f5f5f5",
        # wrap_mode=NONE: code lines are never meant to reflow -- a
        # line either fits or it doesn't, and wrapping it mid-token
        # actively hurts readability. Mirrors table_no_wrap just below
        # in this file, for the identical reason on table rows.
        # CONFIRMED NOT the fix for the "gtk_widget_size_allocate():
        # ... negative height" warnings this addon has been chasing --
        # a live reproduction after adding this still showed the exact
        # same warnings, with the same fixed width (2050) in every
        # occurrence across unrelated sessions. That fixed width is
        # itself the tell: it doesn't move with window size the way a
        # wrap-width recalculation would, and is suspiciously close to
        # 75% of a real monitor's width -- the same fraction
        # _size_and_center_on_current_monitor() uses for this dialog's
        # own sizing. That points at something carrying the *dialog's*
        # width into a height computation elsewhere, not at this tag's
        # own wrapping. Left in place regardless, since it's still the
        # right behavior for code on its own terms.
        wrap_mode=Gtk.WrapMode.NONE,
    )
    tag(
        "code_fence_marker",
        family="Monospace",
        foreground="#888888",
        background="#e8e8e8",
    )
    tag("list_bullet", foreground="#555555", weight=W_BOLD)

    # Inline emphasis
    tag("bold", weight=W_BOLD)
    tag("italic", style=S_ITALIC)
    tag("strike", strikethrough=True)
    tag("code_inline", family="Monospace", foreground="#333333", background="#f0f0f0")
    tag("kbd", family="Monospace", foreground="#333333", background="#eeeeee", scale=0.92)

    # Interactive (visual only -- click handling is done by the consumer)
    tag("hyperlink", foreground="#0055cc", underline=U_SINGLE)
    tag("image_link", foreground="#0077aa", underline=U_SINGLE, background="#eef4ff")
    tag("gramps_link", foreground="#8800aa", underline=U_SINGLE, background="#f5eeff")
    tag("anchor_link", foreground="#006633", underline=U_SINGLE)

    return tags


# Per-link tag colors, keyed by link style. Distinct from define_tags'
# fixed-name style tags above: every individual link gets its own
# uniquely-named Gtk.TextTag (see render_markdown below), since a click/
# hover handler needs to tell exactly *which* link occurrence was under
# the pointer, not just that some "hyperlink"-styled text was -- so
# these colors are looked up by style name each time a new tag is
# created, rather than being one shared, reusable tag per style the way
# bold/italic/etc. are.
_LINK_STYLE_COLOURS: dict[str, tuple[str, str | None]] = {
    "hyperlink": ("#0055cc", None),
    "gramps_link": ("#8800aa", "#f5eeff"),
    "image_link": ("#0077aa", "#eef4ff"),
    "anchor_link": ("#006633", None),
    "mailto_link": ("#007755", None),
    "file_link": ("#885500", "#fff8ee"),
    "md_link": ("#006688", "#eaf6fb"),
}


# ---------------------------------------------------------------------------
# Scaled-image disk cache
# ---------------------------------------------------------------------------

#: Folder for images scaled by this module, beside Gramps' own ``normal``
#: (96 px) and ``large`` (180 px) thumbnail folders inside ``THUMB_DIR``.
THUMB_MARKDOWN = os.path.join(THUMB_DIR, "markdown")

#: Widths images are cached at. ``render_markdown`` narrows the requested
#: width to fit the pane, so the exact width changes whenever a pane is
#: resized; caching at a few fixed steps (then shrinking in memory, which
#: is cheap) avoids one cached file per pane width. 560 is the default
#: ``max_width`` of :func:`_insert_image_into_buffer`.
_THUMB_WIDTH_STEPS = (128, 260, 400, 560)


def _scale_to_width(pixbuf: GdkPixbuf.Pixbuf, width: int) -> GdkPixbuf.Pixbuf:
    """
    Shrink *pixbuf* to *width* pixels wide, keeping its proportions.

    :param pixbuf: the image
    :param width: the new width; must be smaller than the current width
    :returns: the scaled image
    """
    # max(1, ...): an extreme-aspect-ratio source image could
    # otherwise round down to a *zero*-height scaled pixbuf --
    # a degenerate anchor size for the TextView to lay out, the
    # same broad class of bug as the negative heights this
    # module's docstring lists under "Next target for fixes"
    # (see also render_markdown's own live-viewport-width
    # clamping of max_width, which addresses the other half:
    # an image that fits max_width but not the actual, possibly
    # narrower, live view).
    height = max(1, int(pixbuf.get_height() * width / pixbuf.get_width()))
    return pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)


def _cached_image_path(img_path: str, width: int) -> str:
    """
    Return the cache file path for *img_path* scaled to *width*.

    Named the way Gramps names its own thumbnails (an MD5 checksum of the
    source path, see ``__build_thumb_path`` in
    ``gramps/gen/utils/thumbnails.py``), plus the width. The name does not
    depend on the file date, so a new revision of an image overwrites its
    old cached copy instead of adding another file.

    :param img_path: the source image path
    :param width: the cached width step
    :returns: the full path of the cached PNG
    """
    import hashlib  # deferred: only needed when an image is shown

    key = ("%s?w=%d" % (os.path.abspath(img_path), width)).encode("utf-8")
    return os.path.join(THUMB_MARKDOWN, hashlib.md5(key).hexdigest() + ".png")


def _load_with_gramps_thumbnailer(img_path: str) -> GdkPixbuf.Pixbuf | None:
    """
    Get a 180 px image from Gramps' own thumbnail framework.

    Used only for files GdkPixbuf cannot read itself (video, PDF and other
    formats), so thumbnailer plugins installed in Gramps can still supply
    a picture. Uses :func:`gramps.gen.utils.thumbnails.get_thumbnail_path`
    with ``SIZE_LARGE``, the same in Gramps 5.2, 6.0 and 6.1.

    :param img_path: the source file path
    :returns: the thumbnail, or ``None`` if Gramps could only offer one of
              its generic icons (it returns those from ``IMAGE_DIR``
              instead of raising an error)
    """
    try:
        # Deferred: needs Gramps' plugin manager, and is rarely used.
        from gramps.gen.const import SIZE_LARGE
        from gramps.gen.utils.thumbnails import get_thumbnail_path

        thumb_path = get_thumbnail_path(img_path, size=SIZE_LARGE)
        if not thumb_path or os.path.abspath(thumb_path).startswith(
            os.path.abspath(IMAGE_DIR) + os.sep
        ):
            return None
        return GdkPixbuf.Pixbuf.new_from_file(thumb_path)
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Gramps thumbnailer failed for %s", img_path, exc_info=True)
        return None


def _load_scaled_image(img_path: str, max_width: int) -> GdkPixbuf.Pixbuf | None:
    """
    Load *img_path* no wider than *max_width*, using a disk cache.

    The image is decoded and scaled once per revision of the source file,
    to the smallest width step (:data:`_THUMB_WIDTH_STEPS`) that is at
    least *max_width* (or *max_width* itself above the largest step), and
    saved in :data:`THUMB_MARKDOWN`. Later calls load that small cached
    PNG and shrink it to the exact width in memory. The cached copy is
    rebuilt when the source file is newer, the same rule Gramps uses for
    its own thumbnails. Images are never enlarged.

    Files GdkPixbuf cannot read are passed to Gramps' thumbnail framework
    (180 px, see :func:`_load_with_gramps_thumbnailer`); those results are
    not cached here, because Gramps caches them itself.

    :param img_path: local path of the source image
    :param max_width: the widest the result may be, in pixels
    :returns: the image, or ``None`` if it could not be loaded
    """
    step = next((w for w in _THUMB_WIDTH_STEPS if w >= max_width), max_width)
    cache_path = _cached_image_path(img_path, step)
    try:
        src_mtime = os.path.getmtime(img_path)
    except OSError:
        return None

    pixbuf = None
    try:
        if os.path.getmtime(cache_path) >= src_mtime:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
    except (OSError, GLib.Error):
        pixbuf = None  # no usable cached copy yet

    if pixbuf is None:
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(img_path)
        except GLib.Error:
            pixbuf = _load_with_gramps_thumbnailer(img_path)
            if pixbuf is None:
                return None
        else:
            if pixbuf.get_width() > step:
                pixbuf = _scale_to_width(pixbuf, step)
            # Write to a temporary file, then rename it into place, so a
            # second Gramps window never reads a half-written PNG.
            tmp_path = "%s.%d.tmp" % (cache_path, os.getpid())
            try:
                os.makedirs(THUMB_MARKDOWN, exist_ok=True)
                pixbuf.savev(tmp_path, "png", [], [])
                os.replace(tmp_path, cache_path)
            except (OSError, GLib.Error):
                LOG.debug("Could not cache scaled image %s", cache_path, exc_info=True)
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    if pixbuf.get_width() > max_width:
        pixbuf = _scale_to_width(pixbuf, max_width)
    return pixbuf


def _insert_image_into_buffer(
    buf: Gtk.TextBuffer,
    it: Gtk.TextIter,
    tags: dict[str, Gtk.TextTag],
    img_path: str,
    alt_text: str,
    max_width: int = 560,
    center: bool = False,
    show_caption: bool = True,
    add_trailing_newline: bool = True,
) -> bool:
    """
    Insert a local image file into *buf* at *it*, scaled to fit.

    Shared by every :func:`render_markdown` caller (the embedded
    MarkdownDash gramplet, its standalone reader window, and Plugin
    Manager *plus*'s own Details/README pane *and* its small thumbnail-
    preview pane) so a wide image is capped at the same practical width
    everywhere, rather than each keeping its own copy of this scaling
    arithmetic — the last three of those differ only in *how* the
    resulting image is framed (centered thumbnail vs. left-aligned
    inline figure, captioned or not), which the three parameters below
    cover.

    :param buf: the buffer to insert into
    :param it: insertion point (the buffer's own end iter)
    :param tags: this buffer's style tags (see :func:`define_tags`) --
                 used for the optional caption's ``blockquote`` styling
    :param img_path: local filesystem path to the image file
    :param alt_text: the image's Markdown alt text, shown as a caption
                      underneath when present and *show_caption*
    :param max_width: pixel width to scale down to if the image is wider
    :param center: center the image (and its caption, if any)
                    horizontally, rather than the buffer's normal
                    left-aligned flow -- for a small standalone preview
                    thumbnail rather than an inline document figure
    :param show_caption: show *alt_text* as a caption underneath the
                          image; ``False`` for a plain thumbnail with no
                          accompanying text
    :param add_trailing_newline: insert a newline after the image (and
                                  before its caption, if shown); ``False``
                                  for a thumbnail that's the buffer's
                                  only content, where trailing
                                  whitespace would just waste space
    :returns: ``True`` if the image was inserted, ``False`` on any
               failure (caller falls back to a text placeholder)
    """
    try:
        pixbuf = _load_scaled_image(img_path, max_width)
        if pixbuf is None:
            raise ValueError("image could not be loaded")
        image_start = buf.create_mark(None, it, True)
        buf.insert_pixbuf(it, pixbuf)
        if center:
            center_tag = buf.create_tag(None, justification=Gtk.Justification.CENTER)
            buf.apply_tag(center_tag, buf.get_iter_at_mark(image_start), it)
        buf.delete_mark(image_start)
        if add_trailing_newline:
            buf.insert(it, "\n")
        caption_tag = tags.get("blockquote")
        if show_caption and alt_text and caption_tag:
            start_mark = buf.create_mark(None, it, True)
            buf.insert(it, alt_text + "\n")
            start_it = buf.get_iter_at_mark(start_mark)
            buf.apply_tag(caption_tag, start_it, it)
            buf.delete_mark(start_mark)
        return True
    except Exception:  # pylint: disable=broad-except
        LOG.debug("Could not insert image: %s", img_path, exc_info=True)
        return False


def render_markdown(
    textview: Gtk.TextView,
    md_text: str,
    resolve_path: Callable[[str], str] | None = None,
    image_max_width: int = 560,
    center_images: bool = False,
    show_image_captions: bool = True,
    image_adds_newline: bool = True,
    default_icon_style: str = ICON_STYLE_AUTO,
    table_style: str = "widget",
) -> dict:
    """
    Render *md_text* into a fresh :class:`Gtk.TextBuffer` on *textview*.

    The shared rendering engine behind every plugin that displays
    rendered Markdown in a :class:`Gtk.TextView`: parses *md_text* (via
    :func:`parse_markdown`) and fills a fresh buffer with styled text,
    inline images, ``gramps:icon:`` pixbufs, GFM tables (via
    :func:`build_table_widget`), heading anchors, and seven kinds of
    clickable link (plain ``hyperlink``, ``gramps_link``, ``anchor_link``,
    ``image_link`` for a broken/missing image, ``mailto_link``,
    ``file_link``, and ``md_link`` for a bare relative reference that
    resolves to another local ``.md`` file) — the same way in every
    caller, so they can't silently drift out of sync with each other one
    bugfix at a time the way separately-maintained copies of this same
    logic once did.

    Callers still own hover/click handling themselves (this function
    only builds the buffer and hands back what's needed for that, it
    doesn't connect any signals) — see :func:`markdown_link_at` for the
    matching lookup half.

    :param textview: the view whose buffer is (re)built; also the widget
                      any table's :func:`build_table_widget` result is
                      attached to via ``add_child_at_anchor``
    :param md_text: document text to render (already locale-resolved and
                     directive-stripped by the caller, if applicable)
    :param resolve_path: optional callable resolving a relative image
                          path or bare (schemeless) link reference
                          against the document's own base directory;
                          defaults to a no-op (paths/references are only
                          ever treated as already-resolved/absolute)
    :param image_max_width: pixel width local images are scaled down to
                             fit, if wider (see
                             :func:`_insert_image_into_buffer`)
    :param center_images: center inline images (and their captions);
                           see :func:`_insert_image_into_buffer`
    :param show_image_captions: show each image's alt text underneath it
                                 as a caption; see
                                 :func:`_insert_image_into_buffer`
    :param image_adds_newline: insert a newline after each image; see
                                :func:`_insert_image_into_buffer`
    :param default_icon_style: :data:`ICON_STYLE_AUTO` (default),
                                ``'color'``, or ``'symbolic'`` -- the
                                document-wide default for any
                                ``gramps:icon:NAME[:SIZE]`` reference
                                that doesn't specify its own ``:STYLE``
                                suffix
    :param table_style: ``'widget'`` (default) renders each GFM table via
                         :func:`build_table_widget` (a real, interactive
                         ``Gtk.Grid``, with per-cell icon rendering);
                         ``'text'`` renders it via :func:`build_table_text`
                         instead (plain monospace markup text, no embedded
                         widget at all, no per-cell icons) -- see
                         :func:`build_table_text`'s own docstring for why
                         this alternative exists. Set via the
                         ``table_style=...`` control-comment option.
    :returns: ``{"tags": ..., "link_uris": ..., "anchor_marks": ...}`` --
              ``tags`` is :func:`define_tags`'s own return value;
              ``link_uris`` maps each per-link tag's own name to
              ``(uri, style)``, for :func:`markdown_link_at`;
              ``anchor_marks`` maps each heading's anchor slug to the
              :class:`Gtk.TextMark` at its position, for in-document
              "jump to heading" navigation
    """
    if resolve_path is None:
        resolve_path = lambda path: path  # noqa: E731

    buf = Gtk.TextBuffer()
    textview.set_buffer(buf)

    # Clamp the effective image width to whatever the view can actually
    # show right now, never to more than the caller's own image_max_width
    # -- a caller-supplied smaller thumbnail size (e.g. Plugin Manager
    # plus's preview pane) is still honoured, this only ever makes the
    # effective width smaller, never larger. Without this, an image
    # rendered while the view is narrower than image_max_width (a docked
    # gramplet sidebar pane, or a reader window later shrunk after the
    # image was already inserted at the wider cap) can end up wider than
    # the TextView's live allocation -- see _insert_image_into_buffer's
    # own comment, and this module's docstring's "Next target for fixes"
    # note on negative-height allocation warnings while scrolling.
    allocated = textview.get_allocated_width()
    if allocated > 1:
        left = textview.get_left_margin()
        right = textview.get_right_margin()
        padding = 16  # breathing room beyond the margins alone
        image_max_width = max(
            1, min(image_max_width, allocated - left - right - padding)
        )

    tags = define_tags(buf)
    link_uris: dict[str, tuple[str, str]] = {}
    anchor_marks: dict[str, Gtk.TextMark] = {}
    link_counter = [0]

    def make_link_tag(style: str, uri: str) -> Gtk.TextTag:
        link_counter[0] += 1
        name = f"_link_{link_counter[0]}"
        fg, bg = _LINK_STYLE_COLOURS.get(style, _LINK_STYLE_COLOURS["hyperlink"])
        kw: dict = {"foreground": fg, "underline": Pango.Underline.SINGLE}
        if bg:
            kw["background"] = bg
        new_tag = buf.create_tag(name, **kw)
        link_uris[name] = (uri, style)
        return new_tag

    segments = parse_markdown(md_text, default_icon_style=default_icon_style)
    it = buf.get_end_iter()
    current_style_ctx = textview.get_style_context()

    for seg in segments:
        if seg.table_data:
            columns, align, body_rows, sep_widths = seg.table_data
            if table_style == "text":
                table_chunks = build_table_text(
                    columns,
                    align,
                    body_rows,
                    sep_widths,
                    default_icon_style=default_icon_style,
                )
                start_mark = buf.create_mark(None, it, True)
                for kind, payload in table_chunks:
                    if kind == "icon":
                        buf.insert_pixbuf(it, payload)
                    else:
                        buf.insert_markup(it, payload, -1)
                start_it = buf.get_iter_at_mark(start_mark)
                apply_table_no_wrap_tag(buf, start_it, it)
                buf.delete_mark(start_mark)
            else:
                tbl_widget = build_table_widget(
                    columns,
                    align,
                    body_rows,
                    sep_widths,
                    default_icon_style=default_icon_style,
                )
                anchor_start = buf.create_mark(None, it, True)
                anchor = buf.create_child_anchor(it)
                textview.add_child_at_anchor(tbl_widget, anchor)
                tbl_widget.show_all()
                # Space above and below the table, as line spacing on the
                # anchor's own line rather than as widget margins (see
                # the comment at the end of build_table_widget).
                spacing_tag = buf.get_tag_table().lookup("table_spacing")
                if spacing_tag is None:
                    spacing_tag = buf.create_tag(
                        "table_spacing", pixels_above_lines=4, pixels_below_lines=4
                    )
                buf.apply_tag(spacing_tag, buf.get_iter_at_mark(anchor_start), it)
                buf.delete_mark(anchor_start)

            if table_has_uninteractive_links(columns, body_rows):
                emit_enhanced_renderer_notice(buf, it, tags, make_link_tag)

        elif seg.gramps_icon:
            icon_name, size, icon_style = seg.gramps_icon
            pixbuf = resolve_icon_pixbuf(
                icon_name, size, style_context=current_style_ctx, icon_style=icon_style
            )
            if pixbuf:
                buf.insert_pixbuf(it, pixbuf)
            else:
                start_mark = buf.create_mark(None, it, True)
                buf.insert(it, f"[{icon_name}]")
                start_it = buf.get_iter_at_mark(start_mark)
                quote_tag = tags.get("blockquote")
                if quote_tag:
                    buf.apply_tag(quote_tag, start_it, it)
                buf.delete_mark(start_mark)

        elif seg.image_path:
            img_path = resolve_path(seg.image_path)
            inserted = False
            if os.path.isfile(img_path):
                inserted = _insert_image_into_buffer(
                    buf,
                    it,
                    tags,
                    img_path,
                    seg.text,
                    image_max_width,
                    center=center_images,
                    show_caption=show_image_captions,
                    add_trailing_newline=image_adds_newline,
                )
            if not inserted:
                display = f"[image: {seg.text or seg.image_path}]"
                link_tag = make_link_tag("image_link", seg.image_path)
                start_mark = buf.create_mark(None, it, True)
                buf.insert(it, display)
                start_it = buf.get_iter_at_mark(start_mark)
                buf.apply_tag(link_tag, start_it, it)
                buf.delete_mark(start_mark)

        elif seg.url:
            resolved_url = seg.url
            if seg.url.startswith("mailto:"):
                style = "mailto_link"
            elif seg.url.startswith("file://"):
                style = "file_link"
            elif seg.url.startswith("#"):
                style = "anchor_link"
            elif seg.url.startswith("gramps:"):
                style = "gramps_link"
            elif seg.url.startswith("image:"):
                style = "image_link"
            elif seg.url.startswith(("http://", "https://")):
                style = "hyperlink"
            else:
                # A bare relative reference (e.g. a README's own
                # navigation link to a sibling doc file) has no scheme
                # at all. Opening it as-is via
                # Gio.AppInfo.launch_default_for_uri()/xdg-open resolves
                # it against the *process's* current working directory,
                # not this document's own folder -- producing a
                # file:///home/<user>/... "No such file or directory"
                # error. Resolve it against the caller's own base
                # directory instead; if that lands on another local
                # .md file, the caller can navigate to it in-pane
                # instead of shelling out to the OS.
                candidate = resolve_path(seg.url)
                if candidate != seg.url and os.path.isfile(candidate):
                    resolved_url = candidate
                    style = (
                        "md_link" if candidate.lower().endswith(".md") else "file_link"
                    )
                else:
                    style = "hyperlink"
            link_tag = make_link_tag(style, resolved_url)
            start_mark = buf.create_mark(None, it, True)
            buf.insert(it, seg.text)
            start_it = buf.get_iter_at_mark(start_mark)
            buf.apply_tag(link_tag, start_it, it)
            buf.delete_mark(start_mark)

            if seg.anchor:
                anchor_marks[seg.anchor] = buf.create_mark(
                    f"anchor:{seg.anchor}", start_it, True
                )

        else:
            start_mark = buf.create_mark(None, it, True)
            buf.insert(it, seg.text)
            start_it = buf.get_iter_at_mark(start_mark)

            if seg.anchor:
                anchor_marks[seg.anchor] = buf.create_mark(
                    f"anchor:{seg.anchor}", start_it, True
                )

            for attr in seg.attrs:
                attr_tag = tags.get(attr)
                if attr_tag:
                    buf.apply_tag(attr_tag, start_it, it)
            buf.delete_mark(start_mark)

        it = buf.get_end_iter()

    return {"tags": tags, "link_uris": link_uris, "anchor_marks": anchor_marks}


def markdown_link_at(
    textview: Gtk.TextView, link_uris: dict[str, tuple[str, str]], x: int, y: int
) -> tuple[str | None, str | None]:
    """
    Return the ``(style, uri)`` of the link under widget point *(x, y)*.

    The matching lookup half of :func:`render_markdown`'s own
    ``link_uris`` return value — call this from a ``"motion-notify-
    event"``/``"button-press-event"`` handler on the same *textview* to
    drive hover-cursor switching and click-to-open, the same way in
    every caller.

    :param textview: the same view :func:`render_markdown` was called on
    :param link_uris: the ``"link_uris"`` dict :func:`render_markdown`
                       returned
    :param x: widget-relative pointer X, from the GDK event
    :param y: widget-relative pointer Y, from the GDK event
    :returns: ``(style, uri)`` if a link tag covers this point, else
              ``(None, None)``
    """
    buf_x, buf_y = textview.window_to_buffer_coords(Gtk.TextWindowType.WIDGET, x, y)
    it = textview.get_iter_at_position(buf_x, buf_y)[1]
    for text_tag in it.get_tags():
        name = text_tag.get_property("name")
        entry = link_uris.get(name)
        if entry is not None:
            uri, style = entry
            return style, uri
    return None, None


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
        elif kind == "br":
            result.append("\n")
        elif kind == "kbd":
            result.append(
                '<span font_family="monospace" background="#eeeeee" '
                'foreground="#333333">{}</span>'.format(
                    inline_to_pango(m.group("kbd_t"))
                )
            )
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
_TABLE_CSS_PROVIDER: Gtk.CssProvider | None = None


def _ensure_table_css_provider() -> None:
    """
    Load and register the ``.md-table-header-cell``/``-body-cell`` CSS.

    Forces a specific, deterministic background for each -- rather than
    leaving it to whatever the active GTK theme does with a bare
    ``Gtk.Box`` in this position, which on at least one real system
    auto-striped table rows such that the header row blended into a
    themed stripe instead of standing out from the body rows. The
    header is the visually darker of the two, with every body row a
    single, uniform lighter shade (not alternating/zebra-striped) --
    the conventional table convention, and what was specifically asked
    for after an earlier revision's header-only shading (with body rows
    left transparent) read as "only the first row has a background"
    rather than a header clearly set apart from a shared body style.
    Safe to call on every :func:`build_table_widget` invocation:
    registers the provider with the default screen once per process
    (subsequent calls are a no-op), using
    ``Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION`` so a user's own GTK
    theme can still override these two classes if they want to.
    """
    global _TABLE_CSS_PROVIDER  # pylint: disable=global-statement
    if _TABLE_CSS_PROVIDER is not None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(
        b".md-table-header-cell { background-color: #c8c8c8; }"
        b".md-table-body-cell { background-color: #f5f5f5; }"
    )
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    _TABLE_CSS_PROVIDER = provider


def _pad_table_specs(
    align: list[str], sep_widths: list[int] | None, ncols: int, default_width: int
) -> tuple[list[str], list[int]]:
    """Pad a table's alignment and separator-width lists to *ncols* entries.

    Shared by :func:`build_table_widget` and :func:`build_table_text`.

    :param align: per-column alignment strings (``'left'`` pads)
    :param sep_widths: per-column separator dash counts, or ``None``
    :param ncols: the number of columns the table really has
    :param default_width: the dash count used for missing entries (and for
                          every column when *sep_widths* is ``None``)
    :returns: ``(align, sep_widths)``, each at least *ncols* long
    """
    if sep_widths is None:
        sep_widths = [default_width] * ncols
    if len(align) < ncols:
        align = align + ["left"] * (ncols - len(align))
    if len(sep_widths) < ncols:
        sep_widths = sep_widths + [default_width] * (ncols - len(sep_widths))
    return align, sep_widths


def _strip_pango(markup_str: str) -> str:
    """Strip Pango tags from *markup_str*, leaving the visible text.

    Used for a table cell's tooltip text and approximate display length
    (:func:`build_table_widget`) and for its on-screen character count
    (:func:`build_table_text`).
    """
    return re.sub(r"<[^>]+>", "", markup_str)


def _split_cell_icon(
    raw: str, default_icon_style: str
) -> tuple["GdkPixbuf.Pixbuf | None", str, str | None]:
    """Split one table cell into its leading icon and its remaining markup.

    Shared start of both table builders' ``render_cell``.

    :param raw: the cell's raw Markdown
    :param default_icon_style: style for a ``gramps:icon`` reference that
                               does not name its own
    :returns: ``(pixbuf, markup, icon_name)`` -- *pixbuf* is the resolved
              leading icon or ``None``; *markup* is the rest of the cell
              as Pango markup; *icon_name* is the leading icon's name when
              there was one (so a caller can show it in brackets if
              *pixbuf* is ``None``), otherwise ``None``
    """
    icon_info, remaining = _extract_leading_icon(raw, default_icon_style)
    markup = inline_to_pango(remaining)
    if icon_info is None:
        return None, markup, None
    icon_name, size, icon_style = icon_info
    return resolve_icon_pixbuf(icon_name, size, icon_style=icon_style), markup, icon_name


def build_table_widget(
    columns: list[str],
    align: list[str],
    body_rows: list[list[str]],
    sep_widths: list[int] | None = None,
    default_icon_style: str = ICON_STYLE_AUTO,
) -> Gtk.Frame:
    """Return a :class:`Gtk.Frame` containing a :class:`Gtk.Grid` for a GFM table.

    Each cell's raw Markdown is rendered in two parts: the first
    ``![...](gramps:icon:...)`` reference (if any) becomes a real
    ``GdkPixbuf.Pixbuf`` shown in a ``Gtk.Image``, resolved via
    :func:`resolve_icon_pixbuf`; everything else is rendered as Pango
    markup by :func:`inline_to_pango` in a paired ``Gtk.Label``
    -- so ``| ![](gramps:icon:person/16) John Smith |`` shows an actual
    person icon followed by the name, rather than the icon's alt text in
    italics. Header cells get the same treatment, in bold. A cell can
    only carry *one* real icon this way (one image + one label per
    cell); additional icon/image references in the same cell still fall
    back to italicized alt text, as before.

    A plain :class:`Gtk.Grid` of cells is used here rather than a
    :class:`Gtk.TreeView` (this function's own original implementation)
    specifically because a TreeView's internal size negotiation --
    built for its own independent scrolling, not for living inside
    another widget's incrementally-validated child anchor -- was
    confirmed, via a live scroll/resize stress test, to let its
    *allocation* drift away from its own *requested* size purely from
    repeatedly scrolling the enclosing ``Gtk.TextView`` (no resize
    involved at all), eventually going negative: exactly the
    "``gtk_widget_size_allocate(): ... negative height``" /
    ``pixman_region32_init_rect: Invalid rectangle passed`` warnings
    this module's docstring lists under "Next target for fixes". A
    ``Gtk.Grid`` of plain ``Gtk.Label``/``Gtk.Image`` cells has no
    internal scrolling or adjustment model of its own to conflict with
    the child anchor's, and was confirmed clean (zero warnings) under
    the identical stress test.

    Column widths are derived from whichever is larger:
    1. Content measure — max plain-text length across header + all body
       cells for that column (after icon extraction), multiplied by an
       estimated ~7 px per character, plus an icon-width allowance for any
       column that has at least one resolved icon.
    2. Separator hint — the number of dashes in the GFM separator row
       (``|---|:-----:|``).

    :param columns:    List of header cell strings (may contain inline Markdown).
    :param align:      Per-column alignment strings: ``'left'``, ``'center'``,
                       or ``'right'``.
    :param body_rows:  List of rows; each row is a list of cell strings.
    :param sep_widths: Per-column dash count from the GFM separator row, used
                       as a minimum-width hint.  Defaults to 5 per column.
    :param default_icon_style: :data:`ICON_STYLE_AUTO` (default), ``'color'``,
                       or ``'symbolic'`` -- applies to any
                       ``gramps:icon:NAME[:SIZE]`` reference in a cell that
                       doesn't specify its own ``:STYLE`` suffix. Table
                       cells are rendered outside :func:`parse_markdown`'s
                       call, so (unlike inline document text) this must be
                       passed explicitly by the caller if a non-default
                       document-wide style is in effect.
    :returns: A :class:`Gtk.Frame` containing the styled table (a
        :class:`Gtk.Grid` of cells -- see the "Gtk.TreeView was used
        here originally" comment below for why).
    """
    _MIN_COL_PX = 40
    _CELL_XPAD = 12
    # Only used as a floor for a document that deliberately used a wider
    # separator-row dash count than its actual content needs (e.g.
    # ``|-----------|``) to hint at a wider column than its content
    # alone would require -- actual content width below is measured
    # directly via Pango now, not estimated from it.
    _PX_PER_SEP_CHAR = 7

    _ensure_table_css_provider()

    ncols = len(columns)
    # Defensive backstop, independent of the header/separator mismatch
    # check parse_markdown now performs before ever building table_data:
    # this function is itself public and reusable, so pad align/
    # sep_widths (each usually built from the separator row's own cell
    # count) up to ncols (usually the header row's) for any other
    # caller that hands in mismatched lists directly, the same way
    # parse_markdown's own flush_table already pads header_row/body_rows
    # -- rather than raising IndexError below when this loop reaches an
    # index neither list actually has. (Shared with build_table_text via
    # _pad_table_specs, which also supplies the default when sep_widths
    # is None.)
    align, sep_widths = _pad_table_specs(align, sep_widths, ncols, 5)

    # A throwaway, never-shown Gtk.Label used purely to ask Pango for a
    # markup string's *actual* rendered pixel width in the active font
    # -- reused across every cell in this table rather than a fixed
    # px-per-character guess, which is what previously let a proportional
    # (non-monospace) font's real character widths -- routinely wider
    # than the guess for a bold header, capital-heavy text, or just an
    # unlucky font -- overflow the column and silently ellipsize despite
    # there being plenty of unused space in the window, a real report of
    # exactly that (aggravated by there being no tooltip/selection to
    # recover the cropped text at the time, both since fixed separately).
    _measure_label = Gtk.Label()

    def measure_px(markup_str: str) -> int:
        """Return *markup_str*'s actual rendered width in pixels."""
        _measure_label.set_markup(markup_str)
        width, _height = _measure_label.get_layout().get_pixel_size()
        return width

    def render_cell(raw: str) -> tuple:
        """Split *raw* cell Markdown into (pixbuf-or-None, Pango markup)."""
        pixbuf, markup, icon_name = _split_cell_icon(raw, default_icon_style)
        if icon_name is not None and pixbuf is None:
            # Same bracketed alt-text convention as build_table_text and
            # broken images, rather than silently dropping the icon.
            markup = f"[{_esc(icon_name)}] {markup}".strip()
        return pixbuf, markup

    header_cells = [render_cell(c) for c in columns]
    body_cells = [[render_cell(str(cell)) for cell in row] for row in body_rows]

    col_content_px: list[int] = []
    col_icon_px: list[int] = []
    for ci in range(ncols):
        hdr_pb, hdr_markup = header_cells[ci]
        # Measured with the same <b> wrapping the header actually
        # renders with below -- bold text is measurably wider than
        # plain text of the same characters, so measuring the
        # unbolded markup here would underestimate exactly the row
        # most likely to need the room (the header itself).
        hdr_px = measure_px(f"<b>{hdr_markup}</b>")
        cell_max_px = 0
        icon_px = hdr_pb.get_width() if hdr_pb is not None else 0
        for row in body_cells:
            if ci < len(row):
                pb, markup = row[ci]
                cell_max_px = max(cell_max_px, measure_px(markup))
                if pb is not None:
                    icon_px = max(icon_px, pb.get_width())
        col_content_px.append(max(hdr_px, cell_max_px))
        col_icon_px.append(icon_px)

    # Icons are never scaled here (see build_table_widget's own
    # docstring note above render_cell): a "gramps:icon:name:SIZE"
    # reference is the document author's own explicit, deliberate size
    # choice, not a hint for this renderer to second-guess -- if a
    # chosen size doesn't fit well, that's exactly the kind of thing
    # proofreading the document is for, not something to silently
    # correct out from under the author. Each icon column's own budget
    # is therefore sized to whichever icon actually found in it is
    # largest (col_icon_px above, taken directly from the real resolved
    # pixbuf's own width) rather than one fixed guess at "an icon" --
    # that's what previously let an icon larger than the guess get
    # squeezed into less room than its own real size, clipping it
    # (understood at the time as the likely source of the Cairo/pixman
    # "invalid rectangle" warnings while scrolling).
    col_min_px: list[int] = []
    for ci in range(ncols):
        content_px = col_content_px[ci] + _CELL_XPAD
        sep_px = sep_widths[ci] * _PX_PER_SEP_CHAR + _CELL_XPAD
        icon_px = col_icon_px[ci] + _CELL_XPAD if col_icon_px[ci] else 0
        col_min_px.append(max(content_px, sep_px, _MIN_COL_PX, icon_px))

    # A Gtk.TreeView was used here originally, but empirically confirmed
    # (via a live scroll/resize stress test against this exact table)
    # to be the actual source of the "gtk_widget_size_allocate():
    # attempt to allocate widget with width W and height NEGATIVE" /
    # "pixman_region32_init_rect: Invalid rectangle passed" warnings
    # this module's docstring lists under "Next target for fixes" --
    # not the image insertion path, which was investigated and ruled
    # out first (zero warnings with a table-free document containing
    # only an image, under the identical stress test). A TreeView's own
    # internal size negotiation (built for its own independent
    # scrolling, not for living inside another widget's incrementally-
    # validated child anchor) was seen to let its *allocation* drift
    # away from its *requested* size purely from repeated scrolling of
    # the enclosing Gtk.TextView -- no resize involved at all -- with
    # the explicit set_size_request() calls previously here
    # (documented below, kept as a still-reasonable belt-and-suspenders
    # measure) visibly unable to hold it in place; a live counter-fix
    # that reasserted the size request on every stray allocation still
    # wasn't enough to outrun it. A Gtk.Grid of plain Gtk.Label/
    # Gtk.Image cells has no internal scrolling or adjustment model of
    # its own to conflict with the child anchor's -- confirmed clean
    # (zero warnings) under the identical stress test this same
    # TreeView-based table reproduced the warnings under every time.
    _xalign = {"left": 0.0, "center": 0.5, "right": 1.0}

    grid = Gtk.Grid()
    grid.set_column_spacing(2 * _CELL_XPAD)
    grid.set_row_spacing(4)

    # One horizontal Gtk.SizeGroup per column, holding that column's cell
    # in every row. Each row is its own Box (see build_row_box), and a Box
    # shares out spare width according to each cell's own natural width
    # -- which differs from row to row whenever one row's cell has an
    # icon, or longer or shorter text, than another's. Equal minimum
    # widths alone (col_min_px) therefore did not keep columns aligned:
    # columns drifted by up to ~40 px between rows. A size group makes
    # every cell in a column report the same minimum *and* natural width,
    # so every row divides its width identically.
    col_size_groups = [Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL) for _ in range(ncols)]

    def build_cell_content(col: int, pixbuf, markup: str, xalign: float, bold: bool) -> Gtk.Box:
        """Build one cell's own icon+label content (no background of its own)."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        if pixbuf is not None:
            box.pack_start(Gtk.Image.new_from_pixbuf(pixbuf), False, False, 0)
        label = Gtk.Label()
        label.set_markup(f"<b>{markup}</b>" if bold else markup)
        label.set_xalign(xalign)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_size_request(col_min_px[col], -1)
        # Ellipsized text with neither of these is a dead end: there was
        # no way to actually read what got cropped, and no way to work
        # around it either (a real report: no tooltip on hover, and
        # selecting/copying the visible, truncated text into an editor
        # doesn't recover the missing part, because the text was never
        # selectable to begin with).
        label.set_selectable(True)
        label.set_tooltip_text(_strip_pango(markup))
        box.pack_start(label, True, True, 0)
        return box

    def build_row_box(cells: list[tuple], bold: bool, header: bool) -> Gtk.Box:
        """
        Build one whole row as a single Box, so its background is one
        continuous surface rather than several separate per-cell boxes
        with the grid's own column-spacing gaps showing through between
        them -- a real report of exactly that: "an inexplicable light
        background rectangle between the header columns", where the
        grid's own (unstyled) column gap was visible between two
        separately-backgrounded header cell boxes. One Box per row,
        carrying the background itself, has no such internal gap to
        show through -- the cells inside it still line up with the
        matching cells in every other row's own Box, since all rows use
        the same per-column minimum widths (col_min_px) and packing
        flags, laid out by the same Gtk.Grid column tracking below.
        """
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2 * _CELL_XPAD)
        row_box.get_style_context().add_class(
            "md-table-header-cell" if header else "md-table-body-cell"
        )
        for ci in range(ncols):
            col_align = align[ci] if ci < len(align) else "left"
            pb, markup = cells[ci] if ci < len(cells) else (None, "")
            cell_box = build_cell_content(ci, pb, markup, _xalign.get(col_align, 0.0), bold)
            col_size_groups[ci].add_widget(cell_box)
            row_box.pack_start(cell_box, True, True, 0)
        return row_box

    grid.attach(build_row_box(header_cells, bold=True, header=True), 0, 0, ncols, 1)

    header_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
    grid.attach(header_sep, 0, 1, ncols, 1)

    for ri, row in enumerate(body_cells):
        grid_row = ri + 2
        grid.attach(build_row_box(row, bold=False, header=False), 0, grid_row, ncols, 1)
        if ri < len(body_cells) - 1:
            row_sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            grid.attach(row_sep, 0, grid_row + 1, ncols, 1)

    frame = Gtk.Frame()
    frame.set_shadow_type(Gtk.ShadowType.NONE)
    frame.add(grid)
    # No margins on this Frame: it is placed in a Gtk.TextView child
    # anchor, and while its line is scrolled out of view GtkTextView
    # gives the anchored widget a provisional height of a pixel or two.
    # GTK subtracts a widget's margins from whatever height it is given,
    # so the former 4 px top + 4 px bottom margins produced
    # "gtk_widget_size_allocate(): ... height -7" (1 - 8) warnings while
    # scrolling. render_markdown adds the same 4 px of space above and
    # below with a "table_spacing" text tag on the anchor's line instead.
    # Halign START (not FILL, GTK's own default) is what actually keeps
    # this Frame from being stretched to match whatever width its own
    # parent has available -- a Gtk.TextView child anchor easily offers
    # 700px+ in a normal-sized reader window, and a FILL-aligned widget
    # claims all of it regardless of anything set on its own children
    # (set_expand(False) on the TreeViewColumns above only stops *them*
    # stretching to fill the TreeView's own allocation -- it does
    # nothing to stop the TreeView/Frame itself being stretched by
    # *its* parent, confirmed directly: the Frame still claimed a full
    # 1233px allocation with that alone). START keeps the Frame at its
    # own requested size — the column-width budget already computed
    # above — regardless of how much wider its parent actually is.
    frame.set_halign(Gtk.Align.START)
    frame.show_all()
    return frame


def apply_table_no_wrap_tag(buf: Gtk.TextBuffer, start_it, end_it) -> None:
    """
    Prevent Gtk.TextView's own word-wrap from mangling a text-mode table.

    A ``table_style="text"`` table (see :func:`build_table_text`) is one
    long monospace line per row; if a row is wider than the
    ``Gtk.TextView``'s current width, GTK's own ``WORD_CHAR`` wrapping
    breaks it mid-row onto a continuation line that carries none of that
    row's leading border/indent -- visually destroying the table's
    alignment (confirmed: a real report of exactly this, box-drawing
    borders and cell text scattered outside the box, on a wide,
    3-column table). A ``Gtk.TextTag`` with ``wrap-mode`` set to
    :data:`Gtk.WrapMode.NONE` overrides the ``TextView``'s own wrap
    setting for exactly the tagged range, so a wide table instead
    simply extends past the viewport width -- reachable via the
    enclosing ``Gtk.ScrolledWindow``'s own horizontal scrollbar
    (``Gtk.PolicyType.AUTOMATIC`` on both axes is already set on every
    caller of this module) -- rather than being broken apart.

    :param buf: The buffer the table was just inserted into.
    :param start_it: Iterator at the start of the inserted table text.
    :param end_it: Iterator at the end of the inserted table text.
    """
    tag = buf.get_tag_table().lookup("table_no_wrap")
    if tag is None:
        tag = buf.create_tag("table_no_wrap", wrap_mode=Gtk.WrapMode.NONE)
    buf.apply_tag(tag, start_it, end_it)


def build_table_text(
    columns: list[str],
    align: list[str],
    body_rows: list[list[str]],
    sep_widths: list[int] | None = None,
    default_icon_style: str = ICON_STYLE_AUTO,
) -> list[tuple[str, "str | GdkPixbuf.Pixbuf"]]:
    """
    Render a GFM table as an ordered list of text/icon chunks.

    An alternative to :func:`build_table_widget`, which -- even after
    being rewritten from a ``Gtk.TreeView`` to a ``Gtk.Grid`` to fix one
    confirmed cause of this module's own documented "negative-height
    allocation while scrolling" bug -- was found under further live
    testing to still be able to trigger it under plain repeated
    scrolling, with no window resize involved at all. That further
    testing narrowed the trigger to the embedded ``Gtk.Separator``
    rows specifically, but did not fully isolate the exact remaining
    interaction (it was not reproducible in a simplified synthetic
    table, only in the real, larger document) in the time available.

    This function sidesteps the entire risk category rather than
    chasing it further: every ``"text"`` chunk is Pango markup for
    ``Gtk.TextBuffer.insert_markup()`` and every ``"icon"`` chunk is a
    real ``GdkPixbuf.Pixbuf`` for ``Gtk.TextBuffer.insert_pixbuf()`` --
    neither creates a widget for ``add_child_at_anchor()``, so there is
    no child-anchor for ``Gtk.TextView`` to incrementally (and, per the
    above, apparently sometimes incorrectly) re-validate as it scrolls
    into view. A bare pixbuf insert was directly confirmed clean under
    the exact same live scroll-stress test that reproduces the
    child-anchor bug (a table-free document containing only an image
    produced zero warnings, every time), which is what makes real
    per-cell icon rendering safe to bring back here: earlier revisions
    of this function fell back to bracketed ``[icon_name]`` text for a
    leading ``gramps:icon:`` reference specifically to avoid touching
    that risk at all, before the image-vs-table distinction had been
    isolated. A Markdown link inside a cell remains styled-but-inert
    text (see :data:`ENHANCED_RENDERER_NOTICE`) -- unlike an icon, a
    real hyperlink still needs the same click-tracking infrastructure
    normal paragraph text has, which is a materially larger addition
    this deliberately lightweight renderer still opts out of.

    Column width math treats an icon as contributing
    :data:`_ICON_CHAR_WIDTH_ESTIMATE` character-widths -- an
    approximation (this module doesn't have live font metrics to
    convert the icon's actual pixel width into an exact character
    count), in the same spirit as :func:`build_table_widget`'s own
    ~7px-per-character estimate elsewhere in this module.

    Enable per-document with the ``table_style=text`` control-comment
    option; the default remains ``table_style=widget`` (this function
    is opt-in, not a replacement -- see :func:`build_table_widget`'s
    own caller for how the two are selected).

    :param columns: Header cell strings (may contain inline Markdown).
    :param align: Per-column alignment: ``'left'``, ``'center'``, or ``'right'``.
    :param body_rows: Table body rows; each row is a list of cell strings.
    :param sep_widths: Per-column dash count from the GFM separator row,
        used as a minimum character-width hint. Defaults to 3 per column.
    :param default_icon_style: :data:`ICON_STYLE_AUTO` (default),
        ``'color'``, or ``'symbolic'`` -- the document-wide default for
        any ``gramps:icon:NAME[:SIZE]`` reference that doesn't specify
        its own ``:STYLE`` suffix, matching :func:`build_table_widget`'s
        own handling of the same option.
    :returns: An ordered list of ``("text", pango_markup)`` and
        ``("icon", pixbuf)`` tuples. The caller inserts each in order --
        ``Gtk.TextBuffer.insert_markup()`` for ``"text"``,
        ``Gtk.TextBuffer.insert_pixbuf()`` for ``"icon"`` -- to
        reproduce the table; no chunk on its own spans a full row, so
        the caller must not skip or reorder any of them.
    """
    ncols = len(columns)
    align, sep_widths = _pad_table_specs(align, sep_widths, ncols, 3)

    # Approximate character-width contribution of one rendered icon, for
    # column-width/padding purposes only -- see the docstring above.
    _ICON_CHAR_WIDTH_ESTIMATE = 2

    def render_cell(raw: str) -> tuple["GdkPixbuf.Pixbuf | None", str, int]:
        """
        Render one cell.

        :returns: ``(icon_pixbuf_or_None, markup, visible_width)`` --
            ``markup`` never itself contains the icon (that's a
            separate ``Gtk.TextBuffer.insert_pixbuf()`` call the caller
            makes), and already includes a single leading space to
            separate it from the icon when one is present.
        """
        pixbuf, markup, icon_name = _split_cell_icon(raw, default_icon_style)
        if icon_name is None:
            return None, markup, len(_strip_pango(markup))
        if pixbuf is None:
            # Icon failed to resolve -- fall back to the same bracketed
            # alt-text convention used throughout this module for a
            # broken image reference, rather than silently dropping it.
            markup = f"[{_esc(icon_name)}] {markup}".strip()
            return None, markup, len(_strip_pango(markup))
        markup = (" " + markup) if markup else markup
        return pixbuf, markup, _ICON_CHAR_WIDTH_ESTIMATE + len(_strip_pango(markup))

    # Headers get explicit <b> wrapping here -- unlike build_table_widget,
    # which bolds its header via a separate Gtk.Label markup call outside
    # render_cell entirely, this function's headers and body cells share
    # the exact same render_cell(), so without this the header row was
    # rendering completely unstyled (confirmed: a real report of "tables
    # stopped rendering formatting" after switching to text mode, tracked
    # to this exact omission).
    def render_header_cell(raw: str) -> tuple["GdkPixbuf.Pixbuf | None", str, int]:
        pixbuf, markup, width = render_cell(raw)
        return pixbuf, f"<b>{markup}</b>", width

    header_cells = [render_header_cell(c) for c in columns]
    body_cells = [[render_cell(str(cell)) for cell in row] for row in body_rows]

    col_widths: list[int] = []
    for ci in range(ncols):
        hdr_width = header_cells[ci][2]
        cell_max = max((row[ci][2] for row in body_cells if ci < len(row)), default=0)
        col_widths.append(max(hdr_width, cell_max, sep_widths[ci], 3))

    def cell_chunks(
        cell: tuple["GdkPixbuf.Pixbuf | None", str, int], width: int, col_align: str
    ) -> list[tuple[str, str]]:
        """Return this cell's own (padding + icon + text) chunks, in order."""
        pixbuf, markup, visible_width = cell
        gap = max(0, width - visible_width)
        left_gap = gap // 2 if col_align == "center" else (gap if col_align == "right" else 0)
        right_gap = gap - left_gap if col_align == "center" else (0 if col_align == "right" else gap)
        chunks: list[tuple[str, str]] = []
        if left_gap:
            chunks.append(("text", " " * left_gap))
        if pixbuf is not None:
            chunks.append(("icon", pixbuf))
        chunks.append(("text", markup))
        if right_gap:
            chunks.append(("text", " " * right_gap))
        return chunks

    def row_chunks(cells: list[tuple], header: bool = False) -> list[tuple[str, str]]:
        """Return one full row's chunks: left border, cells, separators, right border."""
        out: list[tuple[str, str]] = [("text", "│ ")]
        for ci in range(ncols):
            cell = cells[ci] if ci < len(cells) else (None, "", 0)
            col_align = align[ci] if ci < len(align) else "left"
            out.extend(cell_chunks(cell, col_widths[ci], col_align))
            out.append(("text", " │ " if ci < ncols - 1 else " │"))
        del header  # reserved: see the header-icon shading note below
        return out

    def rule(left: str, mid: str, right: str, fill: str = "─") -> str:
        return left + mid.join(fill * (w + 2) for w in col_widths) + right

    # Box-drawing borders (rather than plain ASCII "-"/"+") -- still just
    # Pango-markup TEXT and real pixbuf inserts, not any embedded widget,
    # so this remains immune to the child-anchor scroll instability
    # documented above; this is purely a visual improvement in response
    # to the plain version reading as "unformatted" next to the
    # widget-based table's bordered grid look. The header row's light
    # background shading from an earlier revision is not reproduced
    # here: it was applied by wrapping the header row's markup text in
    # a <span background=...>, which cannot also cover a real icon
    # pixbuf sitting in the same row (a Pango markup span cannot wrap a
    # buffer-level pixbuf insert) -- rather than have the shading
    # visibly stop and start around any header icon, bold text alone
    # now marks the header row for every table, with or without icons.
    chunks: list[tuple[str, str]] = [("text", rule("┌", "┬", "┐") + "\n")]
    chunks.extend(row_chunks(header_cells, header=True))
    chunks.append(("text", "\n" + rule("├", "┼", "┤") + "\n"))
    for row in body_cells:
        chunks.extend(row_chunks(row))
        chunks.append(("text", "\n"))
    chunks.append(("text", rule("└", "┴", "┘") + "\n"))

    # Wrap every "text" chunk's markup in the monospace span individually
    # (rather than one span around the whole table) since chunks are
    # inserted with separate insert_markup() calls, each needing its own
    # well-formed, self-contained markup string.
    return [
        ("text", f'<span font_family="monospace">{markup}</span>') if kind == "text" else (kind, markup)
        for kind, markup in chunks
    ]


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
# resolve_icon_pixbuf (Theme and Context-Aware Alignment Revision)
#
# ---------------------------------------------------------------------------
def resolve_icon_pixbuf(
    icon_name: str,
    size: int,
    icon_theme: Gtk.IconTheme | None = None,
    style_context: Gtk.StyleContext | None = None,
    icon_style: str = ICON_STYLE_AUTO,
) -> GdkPixbuf.Pixbuf | None:
    """Return a styled :class:`GdkPixbuf.Pixbuf` matching active GUI theme properties.

    Uses the *live* default :class:`Gtk.IconTheme` (or a caller-supplied theme)
    so the rendered icon always matches what the running Gramps GUI displays.

    If a style_context is provided, symbolic assets are automatically colorized
    using the theme's active palette (preventing dark-on-dark invisible renderings).

    Resolution order:
    1. Exact GTK named icon via current theme cascade, parsing variants
       dynamically -- first *without* GTK's generic fallback, then with it
       (see ``_load_any`` for why).
    2. All candidate names from :data:`GRAMPS_ICONS` alias list.
    3. Raster PNG fallback from Gramps installation ``DATA_DIR``.
    4. Scalable SVG fallback from Gramps installation ``DATA_DIR``.
    5. Gramps local fallback ``IMAGE_DIR`` files.

    Within each of those, the color vs. symbolic (B&W) variant tried first
    -- and whether the *other* variant is tried at all as a fallback -- is
    controlled by *icon_style*:

    - ``'auto'`` (default): prefer symbolic for icon sizes <=32px, color
      above that (matching every previous release's fixed behavior);
      falls back to whichever variant actually exists for that icon.
    - ``'color'``: always prefer the full-color asset regardless of size;
      falls back to symbolic only if no color asset exists anywhere for
      that icon.
    - ``'symbolic'``: always prefer the symbolic/B&W asset regardless of
      size; falls back to color only if no symbolic asset exists anywhere
      for that icon.

    :param icon_name:     GTK or Gramps short icon name.
    :param size:          Desired pixel size.
    :param icon_theme:    Optional :class:`Gtk.IconTheme` to query; when ``None``
                          the process-wide default theme is used.
    :param style_context: Optional active window :class:`Gtk.StyleContext` to drive
                          contextual re-coloration palettes across dark mode shifts.
    :param icon_style:    :data:`ICON_STYLE_AUTO` (default), ``'color'``, or
                          ``'symbolic'``. An unrecognized value is treated
                          as ``'auto'``.
    :returns: :class:`GdkPixbuf.Pixbuf` or ``None`` if not found anywhere.
    """
    if icon_theme is None:
        icon_theme = Gtk.IconTheme.get_default()
    if icon_style not in _VALID_ICON_STYLES:
        icon_style = ICON_STYLE_AUTO

    if icon_style == ICON_STYLE_COLOR:
        prefer_symbolic = False
    elif icon_style == ICON_STYLE_SYMBOLIC:
        prefer_symbolic = True
    else:
        # PRESENTATION HEURISTIC: symbolic for small layouts only.
        prefer_symbolic = size <= 32

    _EXACT_FLAGS = Gtk.IconLookupFlags.USE_BUILTIN | Gtk.IconLookupFlags.FORCE_SIZE
    _FLAGS = _EXACT_FLAGS | Gtk.IconLookupFlags.GENERIC_FALLBACK

    def _name_variants(name: str) -> list[str]:
        """Return [name] candidates for *name*, in style-preference order.

        Under ``icon_style='auto'`` only the single preferred style is
        ever tried, matching every previous release's behavior exactly
        (no cross-style fallback). The two *forced* styles additionally
        try the other style as a last resort, so requesting a style that
        simply doesn't have an asset for this particular icon still shows
        something rather than nothing.
        """
        if "missing" in name or name.endswith("-symbolic"):
            return [name]
        symbolic_name = name + "-symbolic"
        if icon_style == ICON_STYLE_AUTO:
            return [symbolic_name] if prefer_symbolic else [name]
        return [symbolic_name, name] if prefer_symbolic else [name, symbolic_name]

    def _load_named(
        lookup_name: str, px_size: int, flags: Gtk.IconLookupFlags = _FLAGS
    ) -> GdkPixbuf.Pixbuf | None:
        """Try to load *lookup_name* verbatim from the theme cascade at *px_size*."""
        try:
            info = icon_theme.lookup_icon(lookup_name, px_size, flags)
            if info:
                # CONTEXT SYNCHRONIZATION: colorize only when GTK actually
                # resolved a genuine symbolic asset. Icon theme fixed-size
                # directories exist almost exclusively at conventional even
                # pixel sizes (16/22/24/32/...); an odd-size request often
                # has no matching bucket for one style, and with
                # GENERIC_FALLBACK set, GTK can silently substitute the
                # other style's asset. info.is_symbolic() asks GTK
                # directly what it actually resolved, rather than trusting
                # the name we asked for.
                if style_context is not None and info.is_symbolic():
                    pb, _ = info.load_symbolic_for_context(style_context)
                    if pb:
                        return pb
                pb = info.load_icon()
                if pb:
                    return pb
        except Exception:
            pass
        return None

    def _load_any(name: str, px_size: int) -> GdkPixbuf.Pixbuf | None:
        """Try each style variant of *name*, in preference order, via the theme cascade.

        Every variant is tried as an exact name first, and only then with
        GTK's ``GENERIC_FALLBACK`` (which retries with dash-separated parts
        dropped from the end: ``gramps-quilt`` -> ``gramps``). GTK searches
        all *themed* icons for every fallback name before it looks at
        *unthemed* icons -- loose files in a folder added with
        ``append_search_path()``, which is how Gramps registers a plugin's
        own icons (see ``GuiPluginManager.load_plugin``). With the fallback
        on from the start, a plugin icon such as ``gramps-quilt`` would
        lose to any themed ``gramps`` icon and the wrong picture would be
        shown.
        """
        variants = _name_variants(name)
        for flags in (_EXACT_FLAGS, _FLAGS):
            for variant in variants:
                pb = _load_named(variant, px_size, flags)
                if pb:
                    return pb
        return None

    # Step 1 & 2: Process through the synchronized theme cascade
    pb = _load_any(icon_name, size)
    if pb:
        return pb

    candidates = GRAMPS_ICONS.get(icon_name.lower(), [])
    for cand in candidates:
        pb = _load_any(cand, size)
        if pb:
            return pb

    # Fallback to local files if theme layers miss entirely
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

        # Odd/uncommon pixel sizes routinely fall outside every icon
        # theme's fixed-size buckets (which are conventionally even --
        # 16/22/24/32/...), so the live Gtk.IconTheme cascade above often
        # returns None entirely at those sizes -- for both styles alike --
        # and execution reaches this local-file tier. Apply the same
        # per-icon style-preference order here, via _name_variants(), so a
        # size that merely missed the live theme doesn't silently ignore
        # icon_style. Files loaded this way bypass
        # Gtk.IconTheme/load_symbolic_for_context entirely, so a symbolic
        # SVG renders in its own baked-in default color rather than being
        # dynamically recolored to match the active foreground -- still
        # visually "symbolic" (flat, low-saturation), just not
        # theme-reactive the way a genuine theme-cascade hit is.
        search_names: list[str] = []
        for name in all_names:
            search_names.extend(_name_variants(name))
        seen_names: set[str] = set()
        search_names = [
            n for n in search_names if not (n in seen_names or seen_names.add(n))
        ]

        for d in subdirs_raster:
            for name in search_names:
                fp = os.path.join(d, name + ".png")
                if os.path.isfile(fp):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(fp, size, size)
                        if pb:
                            return pb
                    except Exception:
                        pass

        for d in subdirs_svg:
            for name in search_names:
                fp = os.path.join(d, name + ".svg")
                if os.path.isfile(fp):
                    try:
                        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(fp, size, size)
                        if pb:
                            return pb
                    except Exception:
                        pass

        for name in search_names:
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

    Wraps :meth:`Gtk.IconTheme.list_icons` so callers (e.g. :class:`IconBrowserGramplet`)
    do not need to import GTK directly. The enumeration follows the full freedesktop
    inheritance chain — current theme → parent themes → hicolor.

    :param context:    Freedesktop context name (e.g. ``'Actions'``), or
                       ``None`` to return every icon in the cascade.
    :param icon_theme: Optional :class:`Gtk.IconTheme` to query; when ``None``
                       the process-wide default theme is used.
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
#:
#: Deprecated: no current addon uses it. Markdown Dash now uses Gramps'
#: own ``gramps.gui.editors.EDITORS`` table and ``db.method()`` instead.
#: Kept for one release so an older Markdown Dash, installed alongside
#: this version, still imports cleanly; remove it after that.
NAMESPACE_MAP: dict[str, tuple[str, str, str]] = {
    "Person": ("get_person_from_gramps_id", "get_person_from_handle", "EditPerson"),
    "Family": ("get_family_from_gramps_id", "get_family_from_handle", "EditFamily"),
    "Event": ("get_event_from_gramps_id", "get_event_from_handle", "EditEvent"),
    "Place": ("get_place_from_gramps_id", "get_place_from_handle", "EditPlace"),
    "Source": ("get_source_from_gramps_id", "get_source_from_handle", "EditSource"),
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
    "Media": ("get_media_from_gramps_id", "get_media_from_handle", "EditMedia"),
    "Note": ("get_note_from_gramps_id", "get_note_from_handle", "EditNote"),
}

#: Lowercase category alias → canonical Gramps view-category name.
VIEW_NAMES: dict[str, str] = {
    "people": "People",
    "person": "People",
    "relationships": "Relationships",
    "relationship": "Relationships",
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
    "geo": "Geography",
    "charts": "Charts",
    "chart": "Charts",
    "pedigree": "Charts",
    # Gramps' own Pedigree/Fan/Descendant/etc. View plugins still register
    # under the legacy internal codename "Ancestry" (see
    # gramps/plugins/view/view.gpr.py -- category=("Ancestry", _("Charts"))
    # -- even though the user-facing category was renamed to "Charts"), so
    # it must resolve to the same name as "charts"/"chart". (Moved here
    # from Plugin Manager plus, which keeps no alias table of its own.)
    "ancestry": "Charts",
    "dashboard": "Dashboard",
}
