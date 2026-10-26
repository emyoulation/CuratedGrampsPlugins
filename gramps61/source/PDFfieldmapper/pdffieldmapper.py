"""
PDF Field Mapper gramplet (draft).

Lists the form fields of the active PDF media object, lets the user assign a
GEDCOM-style tag to each field, set a reading order (#) and a tab order (Tab),
and write the result to a new PDF either by renaming the fields or by
embedding the tag as a /GrampsTag entry on each field (a name -> tag
crosswalk).  The original media file is never modified.

Tags use "/" as separator (INDI1/BIRT/DATE).  A PDF field name cannot contain a
period (the period separates a field from its parent), so "/" is used instead;
it is also never part of a GEDCOM tag, so a tag maps back to its name exactly.
Whatever is typed with "." is converted to "/", so the Tag column always shows
exactly what is written, both as a field name (Rename) and in /GrampsTag.

Columns
  #    working/reading order, starts as the order of the widgets in the PDF
  Tab  tab order; starts from the page's /Tabs setting (R, C or S) or, when
       the PDF has none, follows #.  Once Tab is edited it is independent.
Off   a widget switched off is written with the PDF annotation Hidden flag, so
      viewers neither show nor tab to it (use it for duplicate widgets of one
      field).  Widgets already hidden in the PDF start switched off.
Del   a widget marked Del is removed from the PDF when it is written (the form
      field goes with it when it was the field's only widget).  Nothing is
      removed from the original file, and the mark can be undone until then.
Multi text fields flagged multi-line.  Several viewers (Okular, for one) type a
      tab character in a multi-line box instead of moving to the next field, so
      Tab gets stuck there.  Untick it for fields that should be one line.
Double-click a row (or press Edit row...) to type its # and Tab positions
directly; this works like dropping the row at that position, whatever the sort.
Values  "Clear values" empties the text and choice fields and "Names -> values"
      fills each text field with the name it will have when written (the tag
      when Rename fields is selected and a tag is set).  Both change the table
      first; the PDF only changes when it is written, and the fields are then
      redrawn by the viewer (NeedAppearances), so each keeps its own font size.
Crosswalk files are sidecars: "<pdf name>.crosswalk.json" next to the PDF they
were made for, which is where Save proposes to put them and Load looks first.
Suggest tags reads placeholder values ("ID08,Birthdate") and, failing that, the
field names: English relationship descriptors such as "Your Father-POD",
"Paternal Grandfather-DOB" or "Maternal-Paternal Great-Grandmother-Name" become
ancestor numbers (INDI4/..., INDI12/...), so such forms need no manual tagging.
"Tab + names -> values" writes each field's tab position and name into its
value, to see in a viewer which fields are visited out of order.
Harmony: the tab order is written to every place a viewer may read it from, all
in the same order: the page's annotation order, the form's field list and its
nested groups, the tag tree (a Form branch is added to an existing tag tree that
does not list the fields) and /Tabs.  Viewers that tab by position (Firefox,
Xreader) ignore all of these.
Anchors: with Write anchors ticked, each field also gets a named destination in
the PDF, named like its tag (INDI4/BIRT/DATE) or, without a tag, like its name.
A link such as file:///path/form.pdf#INDI4/BIRT/DATE then scrolls to the field
in viewers that read named destinations from the address (Okular, Firefox).
Sorting is always by page first.  Editing a tag, checkbox or value never moves a
row: a column you can edit is re-sorted only when you click its header again.
Each newly loaded PDF starts sorted by #.  Rows can be reordered (drag and drop,
Up/Down, Auto-order) only while the table is sorted ascending by # or Tab, and
the reordering changes the values of that column.
"""
from __future__ import annotations

import contextlib
import itertools
import json
import logging
import os
import re
from collections.abc import Callable
from urllib.parse import quote

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import Gramplet, PluginRegister
from gramps.gen.plug._pluginreg import PluginData
from gramps.gen.utils.file import media_path_full
from gramps.gui.dialog import OkDialog
from gramps.gui.pluginmanager import GuiPluginManager

_ = glocale.translation.gettext

LOG = logging.getLogger(__name__)

# The id= of this gramplet in pdffieldmapper.gpr.py (the Help button looks up its README and help_url by it).
_PLUGIN_ID = "PDFFieldMapper"

# ======================================================================
# BEGIN HELP BUTTON BLOCK -- from help_doc_button.py (HelpDocButton.md).
# Uses this module's own `_` and LOG.
# ======================================================================
_MARKDOWNDASH_ID = "markdowndash"
_HELP_ICON_NAME = "help-browser"


def resolve_help_icon(size: int = 16) -> Gtk.Image:
    """
    Return a Gtk.Image of the full-color help-browser icon.

    :param size: icon size in pixels (square).
    :returns: the image; empty (with a logged warning) if the theme has
        no such icon at that size.
    """
    theme = Gtk.IconTheme.get_default()
    flags = (
        Gtk.IconLookupFlags.FORCE_REGULAR  # color, not the symbolic variant
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE  # exactly `size`, not nearest
    )
    info = theme.lookup_icon(_HELP_ICON_NAME, size, flags)
    image = Gtk.Image()
    if info is not None:
        image.set_from_pixbuf(info.load_icon())
    else:
        # Deliberately no new_from_icon_name() fallback: that is the
        # unreliable variant/size lookup this function exists to avoid.
        LOG.warning(
            "resolve_help_icon: theme has no '%s' icon at size %d",
            _HELP_ICON_NAME,
            size,
        )
    return image


def find_local_readme(pdata: PluginData | None) -> str | None:
    """
    Return the canonical README.md path of the plugin, or None if the
    plugin has no README of any kind.

    "Any kind" is decided by ``MarkdownUtils.resolve_localized_path()``:
    ``README.md``, a source-language ``README_<lang>.md``, or a
    ``locale/<lang>/README.md`` translation. The returned path need not
    exist on disk; Markdown Dash resolves it to the best variant for the
    user's language, falling back to the English baseline. If
    MarkdownUtils cannot be imported, only a literal ``README.md`` counts.

    :param pdata: the plugin's PluginData; None is tolerated.
    """
    if pdata is None or not pdata.fpath:
        return None
    readme_path = os.path.join(pdata.fpath, "README.md")
    try:
        # Imported here, not at module level, so a missing MarkdownUtils
        # never stops the host module from loading. Since MarkdownUtils
        # 0.2.1 (load_on_reg=True), Gramps imports it at startup, so this
        # normally succeeds; cb_show_help() also loads Markdown Dash
        # first, which imports it too, as a fallback for older installs.
        # pylint: disable-next=import-outside-toplevel,import-error
        from MarkdownUtils import resolve_localized_path
    except ImportError:
        return readme_path if os.path.isfile(readme_path) else None
    return readme_path if resolve_localized_path(readme_path).exists() else None


def resolve_markdown_dash_opener() -> Callable[..., Gtk.Dialog] | None:
    """
    Return Markdown Dash's open_markdown_file(), or None.

    None means Markdown Dash is deactivated, not registered, fails to
    load, or lacks that function -- callers treat all four the same way
    (fall back to help_url). Each case logs a warning naming itself, so
    a Help button that unexpectedly opens the browser can be diagnosed
    from the terminal; they only appear when Help is clicked.
    """
    gpm = GuiPluginManager.get_instance()
    if _MARKDOWNDASH_ID in gpm.get_hidden_plugin_ids():
        LOG.warning("help button: Markdown Dash is deactivated")
        return None
    pdata = PluginRegister.get_instance().get_plugin(_MARKDOWNDASH_ID)
    if pdata is None or not pdata.fpath:
        LOG.warning("help button: no plugin registered as '%s'", _MARKDOWNDASH_ID)
        return None
    mod = gpm.load_plugin(pdata)
    if not mod:
        LOG.warning(
            "help button: Markdown Dash at %s failed to load (see the "
            "'Plugin error' above, often a missing MarkdownUtils)",
            pdata.fpath,
        )
        return None
    opener = getattr(mod, "open_markdown_file", None)
    if opener is None:
        LOG.warning(
            "help button: Markdown Dash at %s has no open_markdown_file()",
            pdata.fpath,
        )
    return opener


def open_help_url(pdata: PluginData | None, parent: Gtk.Window | None) -> None:
    """
    Open the plugin's registered help_url in the default browser.

    A bare wiki page title is resolved against gramps-project.org; a full
    http(s) URL is used as-is.

    :param pdata: the plugin's PluginData.
    :param parent: transient parent for the "no documentation" notice.
    """
    help_url = getattr(pdata, "help_url", None)
    if not help_url:
        OkDialog(
            _("No documentation available"),
            _("This plugin has neither a README.md nor a registered help_url."),
            parent=parent,
        )
        return
    full_url = (
        help_url
        if help_url.startswith(("http://", "https://"))
        else "https://gramps-project.org/wiki/index.php?title="
        + quote(help_url, safe=":")
    )
    try:
        Gio.AppInfo.launch_default_for_uri(full_url, None)
    except GLib.Error:
        LOG.exception("help button: could not open help_url: %s", full_url)


def cb_show_help(_button: Gtk.Button, uistate, pdata: PluginData | None) -> None:
    """
    Show the best documentation available: the plugin's own README.md in
    a Markdown Dash window if possible, else its help_url in a browser.

    :param uistate: the Gramps UiState (its main window parents the reader).
    :param pdata: the calling plugin's own PluginData.
    """
    # Load Markdown Dash first. MarkdownUtils is normally already loaded at
    # startup (load_on_reg in MarkdownUtils 0.2.1), but loading Markdown
    # Dash also imports it, so find_local_readme() can recognize
    # translated READMEs even with an older MarkdownUtils installed.
    open_markdown_file = resolve_markdown_dash_opener()
    if open_markdown_file is not None:
        readme_path = find_local_readme(pdata)
        if readme_path is not None:
            open_markdown_file(
                readme_path,
                uistate,
                parent=uistate.window,
                addon_name=pdata.name,
            )
            return
    open_help_url(pdata, uistate.window)


def add_help_button(
    container: Gtk.Box,
    uistate,
    plugin: PluginData | str | None,
    *,
    size: int = 16,
) -> Gtk.Button:
    """
    Pack a color "Help" button (icon plus visible label) into container.

    :param container: the Gtk.Box to pack into -- a gramplet's button row,
        or a dialog's action area.
    :param uistate: the Gramps UiState.
    :param plugin: the calling plugin's own registered id (the id= in its
        .gpr.py), or its PluginData.
    :param size: icon size in pixels; the default suits a row of ordinary
        text buttons.
    :returns: the created, already-packed button.
    """
    if isinstance(plugin, str):
        plugin_id = plugin
        plugin = PluginRegister.get_instance().get_plugin(plugin_id)
        if plugin is None:
            LOG.warning("add_help_button: no registered plugin '%s'", plugin_id)
    button = Gtk.Button()
    button.set_image(resolve_help_icon(size))
    button.set_always_show_image(True)  # else some themes hide the icon
    button.set_label(_("Help"))
    # Tooltip on the button: a Gtk.Image inside a button never shows its own.
    button.set_tooltip_text(_("Show documentation for this plugin"))
    button.connect("clicked", cb_show_help, uistate, plugin)
    container.pack_start(button, False, False, 0)
    button.show_all()
    return button


# END HELP BUTTON BLOCK

TAG_KEY = "/GrampsTag"
TAG_SEP = "/"


class _WarningCollector(logging.Handler):
    """Collects the messages logged to it."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


@contextlib.contextmanager
def _capture_pypdf_warnings():
    """
    Keep pypdf's warnings (for instance about a damaged cross-reference table
    that it repairs in memory) off the console and hand them back as a list,
    so the gramplet can show one short note instead.
    """
    logger = logging.getLogger("pypdf")
    collector = _WarningCollector()
    old_propagate, old_level = logger.propagate, logger.level
    logger.addHandler(collector)
    logger.propagate = False
    logger.setLevel(logging.WARNING)
    try:
        yield collector.messages
    finally:
        logger.removeHandler(collector)
        logger.propagate = old_propagate
        logger.setLevel(old_level)


def _pdf_version(header):
    """Return (major, minor) for a header such as b"%PDF-1.6" ((1, 3) if odd)."""
    if isinstance(header, bytes):  # pypdf versions differ: str or bytes
        header = header.decode("ascii", "replace")
    try:
        major, minor = header.split("-")[1].split(".")[:2]
        return int(major), int(minor)
    except (ValueError, IndexError):
        return (1, 3)


def _pdf_warning_note(messages):
    """Return a short status note for captured pypdf warnings, or ''."""
    if not messages:
        return ""
    for message in messages:
        LOG.info("pypdf: %s", message)
    if any("xref" in message.lower() for message in messages):
        return _("PDF has a damaged cross-reference table (repaired in memory)")
    return _("pypdf reported %d warning(s)") % len(messages)


def _normalize_tag(tag):
    """Return the tag with surrounding blanks removed and '.' turned into '/'."""
    return (tag or "").strip().replace(".", TAG_SEP)


# Suggestions only; the entry accepts any text.
COMMON_TAGS = [
    "CHART/TITLE",
    "CHART/NO",
    "CHART/PAGE",
    "CHART/PREV/PERSON",
    "CHART/PREV/NO",
    "INDI/NAME",
    "INDI/NAME/GIVN",
    "INDI/NAME/SURN",
    "INDI/SEX",
    "INDI/BIRT/DATE",
    "INDI/BIRT/PLAC",
    "INDI/CHR/DATE",
    "INDI/DEAT/DATE",
    "INDI/DEAT/PLAC",
    "INDI/BURI/DATE",
    "INDI/BURI/PLAC",
    "INDI/OCCU",
    "INDI/RESI/ADDR",
    "INDI/RESI/DATE",
    "INDI/IMMI/DATE",
    "INDI/EVEN",
    "INDI/NOTE",
    "INDI/SOUR",
    "INDI/CONT",
    "FAM/HUSB",
    "FAM/WIFE",
    "FAM/SPOU",
    "FAM/MARR/DATE",
    "FAM/MARR/PLAC",
    "FAM/DIV/DATE",
    "FAM/CHIL",
]

# store columns
(
    C_PAGE, C_NUM, C_TAB, C_OFF, C_DEL, C_MULTI,
    C_NAME, C_TYPE, C_VALUE, C_TAG, C_ID,
) = range(11)

# Columns the user edits.  Their sort keys are a snapshot taken when the sort
# is chosen, so editing a cell does not make its row jump somewhere else.
_LAZY_COLS = (C_OFF, C_DEL, C_MULTI, C_VALUE, C_TAG)
_COLUMN_TITLES = {
    C_PAGE: "Pg",
    C_NUM: "#",
    C_TAB: "Tab",
    C_OFF: "Off",
    C_DEL: "Del",
    C_MULTI: "Multi",
    C_NAME: "PDF field",
    C_TYPE: "Type",
    C_VALUE: "Current value",
    C_TAG: "GEDCOM tag",
}

# Anchors point a little up and left of a field so that the field shows with
# some context instead of sitting at the very corner of the window (points).
ANCHOR_MARGIN = 24.0

# PDF annotation flags: Hidden (bit 2) and NoView (bit 6)
F_HIDDEN = 2
F_NOVIEW = 32

# PDF field flag: Multiline text (bit 13)
FF_MULTILINE = 4096

# Sort ranks for Auto-order: fields are ordered by person/family number, then
# by the order the facts normally appear on a form.  CHART.* fields (chart
# number and "continued from" fields) come first on a page.
_ROLE_RANK = [
    "NAME", "SEX", "BIRT", "CHR", "MARR", "DIV", "DEAT", "BURI", "OCCU",
    "RESI", "IMMI", "EVEN", "NOTE", "SOUR", "HUSB", "WIFE", "SPOU", "CHIL",
    "CONT",
]
_SUB_RANK = ["DATE", "PLAC", "ADDR"]
_CHART_RANK = [
    "CHART/TITLE",
    "CHART/NO",
    "CHART/PAGE",
    "CHART/PREV/PERSON",
    "CHART/PREV/NO",
]
_TAG_RE = re.compile(r"^(?:INDI|FAM)(\d*)/([A-Z]+)(?:/([A-Z]+))?$")

# "Suggest tags" understands the placeholder values of the pedigree test form:
# "ID08,Birthdate", "F04,Marriageplace", "F01.Sp,Name", "ID08" (person on the
# previous chart) and "Chart00".."Chart15" (chart numbers).
_SUGGEST_RE = re.compile(r"^(ID|F)(\d+)(\.Sp)?,(\w+)$")
_PREV_PERSON_RE = re.compile(r"^ID\d+$")
_CHART_VALUE_RE = re.compile(r"^Chart(\d+)$")
_SUGGEST_ROLE = {
    "Name": "NAME",
    "Birthdate": "BIRT/DATE",
    "Birthplace": "BIRT/PLAC",
    "Deathdate": "DEAT/DATE",
    "Deathplace": "DEAT/PLAC",
    "Marriagedate": "MARR/DATE",
    "Marriageplace": "MARR/PLAC",
}


def _tag_sort_key(tag):
    """Return (number, role rank, sub rank) for a tag, or None if unparsable."""
    tag = _normalize_tag(tag)
    if tag.startswith("CHART/"):
        rank = _CHART_RANK.index(tag) if tag in _CHART_RANK else len(_CHART_RANK)
        return (-1, rank, 0)
    match = _TAG_RE.match(tag)
    if not match:
        return None
    num = int(match.group(1) or 0)
    role = match.group(2)
    sub = match.group(3)
    return (
        num,
        _ROLE_RANK.index(role) if role in _ROLE_RANK else len(_ROLE_RANK),
        _SUB_RANK.index(sub) if sub in _SUB_RANK else len(_SUB_RANK),
    )


def _suggest_tag(value):
    """Return a suggested tag for a placeholder value, or an empty string."""
    value = (value or "").strip()
    match = _CHART_VALUE_RE.match(value)
    if match:
        num = int(match.group(1))
        if num == 0:
            return "CHART/PREV/NO"
        if num == 1:
            return "CHART/NO"
        return "INDI%d/CONT" % num
    if _PREV_PERSON_RE.match(value):
        return "CHART/PREV/PERSON"
    match = _SUGGEST_RE.match(value)
    if not match:
        return ""
    kind, num, spouse, label = match.groups()
    num = int(num)
    if spouse:
        return "FAM%d/SPOU" % num if label == "Name" else ""
    role = _SUGGEST_ROLE.get(label)
    if not role:
        return ""
    return "%s%d/%s" % ("INDI" if kind == "ID" else "FAM", num, role)


# Facts as forms abbreviate or spell them (letters only, lower case) -> the
# GEDCOM part of the tag.  Marriage facts belong to the family numbered like
# the person, as in the pedigree form this tool was first built around.
_FACT_TAGS = {
    "name": ("INDI", "NAME"),
    "dob": ("INDI", "BIRT/DATE"),
    "birthdate": ("INDI", "BIRT/DATE"),
    "dateofbirth": ("INDI", "BIRT/DATE"),
    "born": ("INDI", "BIRT/DATE"),
    "pob": ("INDI", "BIRT/PLAC"),
    "birthplace": ("INDI", "BIRT/PLAC"),
    "placeofbirth": ("INDI", "BIRT/PLAC"),
    "dom": ("FAM", "MARR/DATE"),
    "marriagedate": ("FAM", "MARR/DATE"),
    "dateofmarriage": ("FAM", "MARR/DATE"),
    "married": ("FAM", "MARR/DATE"),
    "pom": ("FAM", "MARR/PLAC"),
    "marriageplace": ("FAM", "MARR/PLAC"),
    "placeofmarriage": ("FAM", "MARR/PLAC"),
    "dod": ("INDI", "DEAT/DATE"),
    "deathdate": ("INDI", "DEAT/DATE"),
    "dateofdeath": ("INDI", "DEAT/DATE"),
    "died": ("INDI", "DEAT/DATE"),
    "pod": ("INDI", "DEAT/PLAC"),
    "deathplace": ("INDI", "DEAT/PLAC"),
    "placeofdeath": ("INDI", "DEAT/PLAC"),
}
_SELF_WORDS = ("self", "individual", "person", "subject", "proband", "me")
_RELATIVE_RE = re.compile(
    r"^(?P<sides>(?:(?:paternal|maternal)[\s-]*)*)"
    r"(?P<great>(?:great[\s-]*)*)(?P<grand>grand)?(?P<sex>father|mother)$"
)
_CHART_NAME_TAGS = (
    (re.compile(r"^pedigree chart( for)?$", re.I), "CHART/TITLE"),
    (re.compile(r"^chart[\s_.-]*(no|num|number)?\.?$", re.I), "CHART/NO"),
    (re.compile(r"^page[\s_.-]*(no|num|number)?\.?$", re.I), "CHART/PAGE"),
)
_CONT_NAME_RE = re.compile(r"^cont(?:inued)?[\s_.-]*(\d+)$", re.I)


def _ancestor_number(descriptor):
    """
    Ahnentafel number for an English relationship descriptor, or None.

    "Your" or a word like "Individual" is 1, "Your Father" 2, "Your Mother" 3.
    Further back, each Paternal/Maternal word is one step up the tree (father
    or mother) and father/mother is the last step: "Paternal Grandmother" is 5,
    "Maternal-Paternal Great-Grandfather" is 12 (mother, then father, then
    father).  The number of steps must fit the generation named.
    """
    text = descriptor.strip().lower()
    text = re.sub(r"^your\s*", "", text).strip(" -:")
    if text in ("",) + _SELF_WORDS:
        return 1
    match = _RELATIVE_RE.match(text)
    if not match:
        return None
    sides = re.findall(r"paternal|maternal", match.group("sides"))
    generation = (
        1 + (1 if match.group("grand") else 0) + len(re.findall("great", match.group("great")))
    )
    if len(sides) != generation - 1:
        return None
    steps = [1 if side == "maternal" else 0 for side in sides]
    steps.append(1 if match.group("sex") == "mother" else 0)
    number = 1
    for step in steps:
        number = number * 2 + step
    return number


def _split_fact(name):
    """Split "Paternal Grandfather-DOB" into ("Paternal Grandfather", fact)."""
    for match in re.finditer(r"[\s:_-]+", name):
        descriptor, fact = name[: match.start()], name[match.end():]
        key = re.sub(r"[^a-z]", "", fact.lower())
        if descriptor and key in _FACT_TAGS:
            return descriptor, _FACT_TAGS[key]
    return None


def _suggest_tag_from_name(name):
    """Return a suggested tag for a field name, or an empty string."""
    name = (name or "").strip()
    for pattern, tag in _CHART_NAME_TAGS:
        if pattern.match(name):
            return tag
    match = _CONT_NAME_RE.match(name)
    if match and 1 <= int(match.group(1)) <= 8:
        return "INDI%d/CONT" % (7 + int(match.group(1)))
    split = _split_fact(name)
    if split:
        number = _ancestor_number(split[0])
        if number:
            kind, fact = split[1]
            return "%s%d/%s" % (kind, number, fact)
    return ""


def _inherited(node, key):
    """Return key from node or the nearest parent that has it, else None."""
    while node is not None:
        if key in node:
            return node[key]
        node = node["/Parent"] if "/Parent" in node else None
    return None


def _field_node(annot):
    """Return the nearest node (widget or ancestor) that has a /T name."""
    node = annot
    while "/T" not in node and "/Parent" in node:
        node = node["/Parent"]
    return node


def _full_name(field):
    """Return the fully qualified field name (parts joined by '.')."""
    parts = []
    node = field
    while node is not None:
        if "/T" in node:
            parts.append(str(node["/T"]))
        node = node["/Parent"] if "/Parent" in node else None
    return ".".join(reversed(parts))


def _tab_ranks(rows, mode):
    """
    Return {id(row): rank} for the widgets of one page, following the page's
    /Tabs mode.  R (row) and C (column) are approximated from the widget
    rectangles; S or no /Tabs mean the order of the /Annots array (= #).
    """
    if mode == "/R":

        def key(row):
            return (-round(row.yc / 8), row.x0)

    elif mode == "/C":

        def key(row):
            return (round(row.x0 / 8), -row.yc)

    else:

        def key(row):
            return row.num

    ordered = sorted(rows, key=key)
    return {id(row): rank for rank, row in enumerate(ordered, 1)}


class _Row:
    """One widget annotation on a page."""

    def __init__(
        self, page, annot_idx, name, ftype, value, tag, rect, off=False, multi=False
    ):
        self.page = page
        self.annot_idx = annot_idx
        self.name = name
        self.ftype = ftype
        self.value = value
        self.tag = tag
        self.x0 = min(rect[0], rect[2])
        self.yc = (rect[1] + rect[3]) / 2
        self.num = 0
        self.tab = 0
        self.off = off
        self.multi = multi


class PDFFieldMapper(Gramplet):
    """Interactive PDF form field mapper for PDF media objects."""

    def init(self):
        self._path = None
        self._rows = []
        self._tab_linked = True
        self.gui.WIDGET = self._build_gui()
        container = self.gui.get_container_widget()
        container.remove(self.gui.textview)
        container.add(self.gui.WIDGET)
        self.gui.WIDGET.show_all()

    def db_changed(self):
        self.connect(self.dbstate.db, "media-update", self.update)
        self.connect_signal("Media", self.update)

    # ------------------------------------------------------------------
    # GUI
    # ------------------------------------------------------------------
    def _build_gui(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._snap = {}
        self._snap_state = None
        self._reorder_buttons = []

        self._status = Gtk.Label(
            xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR
        )
        vbox.pack_start(self._status, False, False, 0)

        self._store = Gtk.ListStore(int, int, int, bool, bool, bool, str, str, str, str, int)
        self._sorted = Gtk.TreeModelSort(model=self._store)
        for col in (
            C_PAGE, C_NUM, C_TAB, C_OFF, C_DEL, C_MULTI,
            C_NAME, C_TYPE, C_VALUE, C_TAG,
        ):
            self._sorted.set_sort_func(col, self._compare, col)
        self._sorted.set_sort_column_id(C_NUM, Gtk.SortType.ASCENDING)
        self._sorted.connect("sort-column-changed", self.cb_sort_changed)

        self._view = Gtk.TreeView(model=self._sorted)
        self._sel = self._view.get_selection()
        self._sel.connect("changed", self.cb_selection_changed)

        for title, col in (
            (_("Pg"), C_PAGE),
            (_("#"), C_NUM),
            (_("Tab"), C_TAB),
            (_("Off"), C_OFF),
            (_("Del"), C_DEL),
            (_("Multi"), C_MULTI),
            (_("PDF field"), C_NAME),
            (_("Type"), C_TYPE),
            (_("Current value"), C_VALUE),
        ):
            if col in (C_OFF, C_DEL, C_MULTI):
                toggle = Gtk.CellRendererToggle()
                toggle.connect(
                    "toggled",
                    {
                        C_OFF: self.cb_off_toggled,
                        C_DEL: self.cb_del_toggled,
                        C_MULTI: self.cb_multi_toggled,
                    }[col],
                )
                column = Gtk.TreeViewColumn(title, toggle, active=col)
            else:
                column = Gtk.TreeViewColumn(
                    title, Gtk.CellRendererText(), text=col, strikethrough=C_DEL
                )
            column.set_resizable(True)
            column.set_clickable(True)
            column.set_sort_column_id(col)
            self._view.append_column(column)

        tags = Gtk.ListStore(str)
        for tag in COMMON_TAGS:
            tags.append([tag])
        renderer = Gtk.CellRendererCombo()
        renderer.set_property("model", tags)
        renderer.set_property("text-column", 0)
        renderer.set_property("has-entry", True)
        renderer.set_property("editable", True)
        renderer.connect("edited", self.cb_tag_edited)
        column = Gtk.TreeViewColumn(
            _("GEDCOM tag"), renderer, text=C_TAG, strikethrough=C_DEL
        )
        column.set_resizable(True)
        column.set_min_width(140)
        column.set_clickable(True)
        column.set_sort_column_id(C_TAG)
        self._view.append_column(column)

        # Drag and drop is handled here (GTK cannot reorder a sorted model).
        self._view.enable_model_drag_source(
            Gdk.ModifierType.BUTTON1_MASK, [], Gdk.DragAction.COPY
        )
        self._view.enable_model_drag_dest([], Gdk.DragAction.COPY)
        self._view.drag_source_add_text_targets()
        self._view.drag_dest_add_text_targets()
        self._view.connect("drag-data-get", self.cb_drag_get)
        self._view.connect("drag-data-received", self.cb_drag_received)
        # GTK refuses drops on a sorted model (TreeModelSort is no drag
        # destination), so motion, leave and drop are handled here.
        self._view.connect("drag-motion", self.cb_drag_motion)
        self._view.connect("drag-leave", self.cb_drag_leave)
        self._view.connect("drag-drop", self.cb_drag_drop)
        self._view.connect("row-activated", self.cb_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(160)
        scroll.add(self._view)
        vbox.pack_start(scroll, True, True, 0)

        self._detail = Gtk.Label(
            xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, selectable=True
        )
        vbox.pack_start(self._detail, False, False, 0)

        mode_box = self._new_flow()
        self._rb_rename = Gtk.RadioButton.new_with_label_from_widget(
            None, _("Rename fields")
        )
        self._rb_cross = Gtk.RadioButton.new_with_label_from_widget(
            self._rb_rename, _("Embed crosswalk")
        )
        self._rb_cross.set_active(True)
        for button in (self._rb_rename, self._rb_cross):
            button.connect("toggled", self.cb_selection_changed)
            mode_box.add(button)
        self._cmb_tabs = Gtk.ComboBoxText()
        for text in (
            _("Tab order: structure (/S, adds tags)"),
            _("Tab order: annotation order (/A, PDF 2.0)"),
            _("Tab order: leave /Tabs unchanged"),
        ):
            self._cmb_tabs.append_text(text)
        self._cmb_tabs.set_active(0)
        self._cmb_tabs.set_tooltip_text(
            _(
                "Only viewers that follow the PDF's own tab order use this. "
                "Xreader and Firefox's PDF viewer ignore it and tab by field "
                "position."
            )
        )
        mode_box.add(self._cmb_tabs)
        self._chk_anchors = Gtk.CheckButton(label=_("Write anchors"))
        self._chk_anchors.set_active(True)
        self._chk_anchors.set_tooltip_text(
            _(
                "Add a named destination (anchor) for each field, so that a link "
                "such as form.pdf#INDI4/BIRT/DATE scrolls to that field"
            )
        )
        mode_box.add(self._chk_anchors)
        self._finish_flow(mode_box)
        vbox.pack_start(mode_box, False, False, 0)

        for group in (
            (
                (_("Up"), lambda _w: self._step(-1)),
                (_("Down"), lambda _w: self._step(1)),
                (_("Edit row…"), self.cb_edit_row),
                (_("Suggest tags"), self.cb_suggest),
                (_("Auto-order"), self.cb_auto_order),
                (_("Tab = #"), self.cb_reset_tab),
            ),
            (
                (_("Clear values"), self.cb_clear_values),
                (_("Names → values"), self.cb_names_to_values),
                (_("Tab + names → values"), self.cb_tabs_to_values),
            ),
            (
                (_("Load crosswalk…"), self.cb_load_crosswalk),
                (_("Save crosswalk…"), self.cb_save_crosswalk),
                (_("Write PDF…"), self.cb_write),
            ),
        ):
            buttons = self._new_flow()
            for label, callback in group:
                button = Gtk.Button(label=label)
                button.connect("clicked", callback)
                if label in (_("Up"), _("Down")):
                    button.set_tooltip_text(
                        _("Sort the table ascending by # or Tab to move rows")
                    )
                    self._reorder_buttons.append(button)
                buttons.add(button)
            self._finish_flow(buttons)
            if any(callback == self.cb_write for _label, callback in group):
                # The wrapping flow of buttons takes all spare width, so the
                # Help button packed after it sits at the far right edge.
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                row.pack_start(buttons, True, True, 0)
                # The Help button gets a flow box cell of its own, so the theme
                # pads it exactly like the buttons beside it.
                help_box = Gtk.Box()
                add_help_button(help_box, self.uistate, _PLUGIN_ID)
                help_flow = self._new_flow()
                help_flow.add(help_box)
                self._finish_flow(help_flow)
                help_flow.set_valign(Gtk.Align.START)  # stay on line 1 when the buttons wrap
                row.pack_start(help_flow, False, False, 0)
                vbox.pack_start(row, False, False, 0)
            else:
                vbox.pack_start(buttons, False, False, 0)

        # Scrollable, so a small gramplet bar never forces a negative size.
        outer = Gtk.ScrolledWindow()
        outer.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        outer.add(vbox)
        return outer

    @staticmethod
    def _new_flow():
        """A row of widgets that wraps onto more lines when space is short."""
        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(False)
        flow.set_column_spacing(6)
        flow.set_row_spacing(2)
        flow.set_max_children_per_line(20)
        return flow

    @staticmethod
    def _finish_flow(flow):
        """Let Tab go to the widgets, not to the flow box's wrappers."""
        for child in flow.get_children():
            child.set_can_focus(False)

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------
    @staticmethod
    def _live_key(row, col):
        """Current sort value of an editable column."""
        return row[col].lower() if col in (C_VALUE, C_TAG) else row[col]

    def _refresh_snapshot(self, col):
        """Remember the current values of an editable column for sorting."""
        self._snap = {col: {r[C_ID]: self._live_key(r, col) for r in self._store}}

    def _sync_sort_snapshot(self):
        """Take the snapshot for the sort column now in use."""
        self._snap_state = self._sort_state()
        self._snap = {}
        if self._snap_state[0] in _LAZY_COLS:
            self._refresh_snapshot(self._snap_state[0])

    def _sort_key(self, row, col):
        """Sort key for a column; ties fall back to # and then to the id."""
        if col in _LAZY_COLS:
            first = self._snap.get(col, {}).get(
                row[C_ID], self._live_key(row, col)
            )
        elif col == C_TAB:
            first = row[C_TAB]
        elif col == C_NAME:
            first = row[C_NAME].lower()
        elif col == C_TYPE:
            first = row[C_TYPE]
        else:  # C_NUM and C_PAGE
            first = 0
        return (first, row[C_NUM], row[C_ID])

    def _compare(self, model, iter1, iter2, col):
        """Sort function: page first (always ascending), then the column."""
        if self._sort_state() != self._snap_state:  # a new sort was chosen
            self._sync_sort_snapshot()
        row1, row2 = model[iter1], model[iter2]
        if row1[C_PAGE] != row2[C_PAGE]:
            result = -1 if row1[C_PAGE] < row2[C_PAGE] else 1
            # GTK reverses the result for a descending sort; undo that for
            # the page so pages stay in ascending order.
            if self._sort_state()[1] == Gtk.SortType.DESCENDING:
                result = -result
            return result
        key1, key2 = self._sort_key(row1, col), self._sort_key(row2, col)
        return (key1 > key2) - (key1 < key2)

    def _sort_state(self):
        """Return (sort column id or None, sort order)."""
        result = self._sorted.get_sort_column_id()
        if len(result) == 3:  # older PyGObject: (found, column, order)
            return (result[1] if result[0] else None, result[2])
        col, order = result  # (None, None) when unsorted
        return (col if col is not None and col >= 0 else None, order)

    def _can_reorder(self):
        """Reordering needs an ascending sort by # or Tab."""
        col, order = self._sort_state()
        return col in (C_NUM, C_TAB) and order == Gtk.SortType.ASCENDING

    def _order_col(self):
        """The column that reordering changes: Tab if sorted by Tab, else #."""
        return C_TAB if self._sort_state()[0] == C_TAB else C_NUM

    def _update_reorder_ui(self):
        """Up and Down only work while the table is sorted by # or Tab."""
        for button in self._reorder_buttons:
            button.set_sensitive(self._can_reorder())

    def cb_sort_changed(self, *_args):
        """Tell the user whether reordering is available."""
        self._update_reorder_ui()
        if self._rows:
            if self._can_reorder():
                self._status.set_text(
                    _("Reordering changes the %s column")
                    % ("Tab" if self._order_col() == C_TAB else "#")
                )
            else:
                self._status.set_text(
                    _("Sort ascending by # or Tab to reorder rows")
                )

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def main(self):
        """Load the active media object if it is a PDF."""
        self._store.clear()
        self._snap, self._snap_state = {}, None
        # every PDF starts sorted by #, whatever the last one was sorted by
        self._sorted.set_sort_column_id(C_NUM, Gtk.SortType.ASCENDING)
        self._rows = []
        self._path = None
        self._tab_linked = True
        self._detail.set_text("")
        handle = self.get_active("Media")
        if not handle:
            self._status.set_text(_("Select a PDF media object."))
            return
        media = self.dbstate.db.get_media_from_handle(handle)
        if media.get_mime_type() != "application/pdf":
            self._status.set_text(_("The active media object is not a PDF."))
            return
        with _capture_pypdf_warnings() as warned:
            self._load(media_path_full(self.dbstate.db, media.get_path()))
        note = _pdf_warning_note(warned)
        if note and self._rows:
            self._status.set_text(self._status.get_text() + "; " + note)

    def _load(self, path):
        try:
            from pypdf import PdfReader
        except ImportError:
            self._status.set_text(_("The pypdf package is required."))
            return
        rows = []
        try:
            reader = PdfReader(path)
            for p_idx, page in enumerate(reader.pages):
                if "/Annots" not in page:
                    continue
                page_rows = []
                for a_idx, ref in enumerate(page["/Annots"]):
                    annot = ref.get_object()
                    if annot.get("/Subtype") != "/Widget":
                        continue
                    field = _field_node(annot)
                    value = _inherited(annot, "/V")
                    ftype = _inherited(annot, "/FT")
                    flags = int(_inherited(annot, "/Ff") or 0)
                    row = _Row(
                        p_idx,
                        a_idx,
                        _full_name(field),
                        str(ftype or "").lstrip("/"),
                        "" if value is None else str(value),
                        _normalize_tag(str(field.get(TAG_KEY, ""))),
                        [float(v) for v in annot["/Rect"]],
                        bool(int(annot.get("/F", 0)) & (F_HIDDEN | F_NOVIEW)),
                        str(ftype) == "/Tx" and bool(flags & FF_MULTILINE),
                    )
                    row.num = len(page_rows) + 1
                    page_rows.append(row)
                ranks = _tab_ranks(page_rows, str(page.get("/Tabs") or ""))
                for row in page_rows:
                    row.tab = ranks[id(row)]
                rows.extend(page_rows)
        except Exception as err:  # pylint: disable=broad-except
            self._status.set_text(_("Cannot read PDF: %s") % err)
            return

        self._path = path
        self._rows = rows
        self._tab_linked = all(row.tab == row.num for row in rows)
        for idx, row in enumerate(rows):
            self._store.append(
                [
                    row.page + 1,
                    row.num,
                    row.tab,
                    row.off,
                    False,
                    row.multi,
                    row.name,
                    row.ftype,
                    row.value,
                    row.tag,
                    idx,
                ]
            )
        sidecar = self._sidecar_path()
        multi = sorted({row.name for row in rows if row.multi})
        text = _("%(n)d fields in %(f)s") % {
            "n": len(rows),
            "f": os.path.basename(path),
        }
        if multi:
            text += _(
                "; multi-line (Tab may get stuck in some viewers): %s"
            ) % ", ".join(multi)
        if os.path.exists(sidecar):
            text += _("; crosswalk found: %s") % os.path.basename(sidecar)
        self._status.set_text(text)
        self._sync_sort_snapshot()
        self._update_reorder_ui()

    # ------------------------------------------------------------------
    # Ordering helpers
    # ------------------------------------------------------------------
    def _page_rows(self, page, col):
        """Store rows of one page, in the order of column col."""
        return sorted(
            (r for r in self._store if r[C_PAGE] == page),
            key=lambda r: (r[col], r[C_NUM]),
        )

    def _set_ranks(self, col, rows):
        """Number the rows (one page, in the given order) in column col."""
        for rank, row in enumerate(rows, 1):
            row[col] = rank
        if col == C_NUM and self._tab_linked:
            for row in rows:
                row[C_TAB] = row[C_NUM]
        elif col == C_TAB:
            self._tab_linked = False

    def _move_row(self, src_id, dest_id, after):
        """Move row src next to row dest within the order column."""
        src, dest = self._store[src_id], self._store[dest_id]
        if src_id == dest_id:
            return
        if src[C_PAGE] != dest[C_PAGE]:
            self._status.set_text(_("Rows can only be moved within a page"))
            return
        col = self._order_col()
        rows = [r for r in self._page_rows(src[C_PAGE], col) if r[C_ID] != src_id]
        pos = [r[C_ID] for r in rows].index(dest_id) + (1 if after else 0)
        rows.insert(pos, src)
        self._set_ranks(col, rows)
        self.cb_selection_changed()

    def _step(self, step):
        """Move the selected row one position up (-1) or down (+1)."""
        if not self._can_reorder():
            self._status.set_text(_("Sort ascending by # or Tab to reorder rows"))
            return
        model, it = self._sel.get_selected()
        if not it:
            return
        src_id, page = model[it][C_ID], model[it][C_PAGE]
        order = [r[C_ID] for r in self._page_rows(page, self._order_col())]
        pos = order.index(src_id) + step
        if 0 <= pos < len(order):
            self._move_row(src_id, order[pos], after=step > 0)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def cb_tag_edited(self, _renderer, path, text):
        """Store an edited tag."""
        child = self._sorted.convert_path_to_child_path(Gtk.TreePath(path))
        self._store[child][C_TAG] = _normalize_tag(text)
        self.cb_selection_changed()

    def cb_off_toggled(self, _renderer, path):
        """Switch a widget off or on."""
        child = self._sorted.convert_path_to_child_path(Gtk.TreePath(path))
        row = self._store[child]
        row[C_OFF] = not row[C_OFF]
        self._status.set_text(
            _("%(f)s switched %(s)s")
            % {"f": row[C_NAME], "s": _("off") if row[C_OFF] else _("on")}
        )
        self.cb_selection_changed()

    def cb_del_toggled(self, _renderer, path):
        """Mark a widget for deletion (or take the mark away)."""
        child = self._sorted.convert_path_to_child_path(Gtk.TreePath(path))
        row = self._store[child]
        row[C_DEL] = not row[C_DEL]
        total = sum(1 for r in self._store if r[C_DEL])
        self._status.set_text(
            _("%(f)s %(s)s; %(n)d widget(s) will be deleted")
            % {
                "f": row[C_NAME],
                "s": _("marked for deletion") if row[C_DEL] else _("kept"),
                "n": total,
            }
        )
        self.cb_selection_changed()

    def cb_multi_toggled(self, _renderer, path):
        """Switch a text field between single-line and multi-line."""
        child = self._sorted.convert_path_to_child_path(Gtk.TreePath(path))
        row = self._store[child]
        if row[C_TYPE] != "Tx":
            self._status.set_text(_("Only text fields can be multi-line"))
            return
        new = not row[C_MULTI]
        name = row[C_NAME]
        for other in self._store:  # widgets of one field share the flag
            if other[C_NAME] == name:
                other[C_MULTI] = new
        self._status.set_text(
            _("%(f)s is now %(s)s")
            % {"f": name, "s": _("multi-line") if new else _("single-line")}
        )
        self.cb_selection_changed()

    def cb_selection_changed(self, *_args):
        """Show what will be written for the selected field."""
        model, it = self._sel.get_selected()
        if not it:
            self._detail.set_text("")
            return
        row = model[it]
        tag = row[C_TAG]
        if not tag:
            outcome = _("tag not set")
        elif self._rb_rename.get_active():
            outcome = _("field renamed to %s") % tag
        else:
            outcome = _("%(k)s = %(t)s embedded") % {"k": TAG_KEY, "t": tag}
        same = sum(1 for r in self._store if r[C_NAME] == row[C_NAME])
        extra = ""
        if same > 1:
            extra += _(" [one of %d widgets of this field]") % same
        if row[C_OFF]:
            extra += _(" [OFF: hidden in the PDF]")
        if not self._can_reorder():
            title = _COLUMN_TITLES.get(self._sort_state()[0], "")
            extra += _(
                " [sorted by %s, so rows can't be moved: click the # or Tab header]"
            ) % title
        original = self._rows[row[C_ID]].value
        if row[C_VALUE] != original:
            extra += _(" [VALUE changes on write; was '%s']") % original[:30]
        if row[C_MULTI]:
            extra += _(" [multi-line: Tab may not leave it in some viewers]")
        if row[C_DEL]:
            whole = all(r[C_DEL] for r in self._store if r[C_NAME] == row[C_NAME])
            extra += (
                _(" [DELETE: the whole field is removed on write]")
                if whole
                else _(" [DELETE: this widget is removed on write]")
            )
        self._detail.set_text(
            _("Page %(p)d, # %(n)d, Tab %(o)d (%(l)s): %(f)s = '%(v)s' → %(r)s")
            % {
                "p": row[C_PAGE],
                "n": row[C_NUM],
                "o": row[C_TAB],
                "l": _("Tab follows #") if self._tab_linked else _("Tab independent"),
                "f": row[C_NAME],
                "v": row[C_VALUE],
                "r": outcome + extra,
            }
        )

    def cb_drag_get(self, widget, _context, selection, _info, _time):
        """Provide the id of the dragged row."""
        model, it = widget.get_selection().get_selected()
        if it:
            selection.set_text(str(model[it][C_ID]), -1)

    def _drop_position(self, widget, x_pos, y_pos):
        """Return (path, position) for a drop at x, y; position is BEFORE/AFTER."""
        dest = widget.get_dest_row_at_pos(x_pos, y_pos)
        if dest is None:
            return None
        path, position = dest
        if position == Gtk.TreeViewDropPosition.INTO_OR_BEFORE:
            position = Gtk.TreeViewDropPosition.BEFORE
        elif position == Gtk.TreeViewDropPosition.INTO_OR_AFTER:
            position = Gtk.TreeViewDropPosition.AFTER
        return path, position

    @staticmethod
    def _autoscroll(widget, y_pos):
        """Scroll the table when the pointer is near its top or bottom edge."""
        adj = widget.get_vadjustment()
        margin, step = 28, 24
        bin_y = widget.convert_bin_window_to_widget_coords(0, 0)[1]
        top = bin_y + adj.get_value()  # height of the column header
        if y_pos < top + margin:
            adj.set_value(max(adj.get_lower(), adj.get_value() - step))
        elif y_pos > widget.get_allocated_height() - margin:
            adj.set_value(
                min(adj.get_upper() - adj.get_page_size(), adj.get_value() + step)
            )

    def cb_drag_motion(self, widget, context, x_pos, y_pos, time):
        """Accept the drag over any row and show where it would land."""
        target = None
        if self._can_reorder():
            target = self._drop_position(widget, x_pos, y_pos)
        if target is None:
            widget.set_drag_dest_row(None, Gtk.TreeViewDropPosition.BEFORE)
            Gdk.drag_status(context, 0, time)
            return True
        widget.set_drag_dest_row(*target)
        self._autoscroll(widget, y_pos)
        Gdk.drag_status(context, Gdk.DragAction.COPY, time)
        return True

    def cb_drag_leave(self, widget, _context, _time):
        """Remove the drop marker."""
        widget.set_drag_dest_row(None, Gtk.TreeViewDropPosition.BEFORE)

    def cb_drag_drop(self, widget, context, _x_pos, _y_pos, time):
        """Ask for the dragged row's id; cb_drag_received then moves the row."""
        text_targets = {
            "text/plain;charset=utf-8",
            "UTF8_STRING",
            "text/plain",
            "STRING",
            "TEXT",
        }
        for target in context.list_targets():
            if target.name() in text_targets:
                widget.drag_get_data(context, target, time)
                return True
        return False

    def cb_drag_received(self, widget, context, x_pos, y_pos, selection, _info, time):
        """Move the dragged row next to the row it was dropped on."""
        # GTK's default handler assumes a model that accepts drops
        widget.stop_emission_by_name("drag-data-received")
        moved = False
        if not self._can_reorder():
            self._status.set_text(_("Sort ascending by # or Tab to reorder rows"))
        else:
            try:
                src_id = int(selection.get_text())
            except (TypeError, ValueError):
                src_id = None
            target = self._drop_position(widget, x_pos, y_pos)
            if src_id is not None and target is not None:
                path, position = target
                after = position == Gtk.TreeViewDropPosition.AFTER
                self._move_row(src_id, self._sorted[path][C_ID], after)
                moved = True
        widget.set_drag_dest_row(None, Gtk.TreeViewDropPosition.BEFORE)
        Gtk.drag_finish(context, moved, False, time)

    # ------------------------------------------------------------------
    # Row editor
    # ------------------------------------------------------------------
    def _move_to(self, col, row_id, new_pos):
        """Put a row at position new_pos (1-based) of its page in column col."""
        row = self._store[row_id]
        rows = [r for r in self._page_rows(row[C_PAGE], col) if r[C_ID] != row_id]
        rows.insert(max(0, min(len(rows), new_pos - 1)), row)
        self._set_ranks(col, rows)

    def _apply_row_edit(self, row_id, new_num, new_tab):
        """Apply typed # and Tab positions, like dropping the row there."""
        row = self._store[row_id]
        old_num, old_tab = row[C_NUM], row[C_TAB]
        if new_num != old_num:
            self._move_to(C_NUM, row_id, new_num)  # Tab follows while linked
        if new_tab != old_tab:
            self._move_to(C_TAB, row_id, new_tab)
        self._status.set_text(
            _("%(f)s: # %(n)d, Tab %(t)d")
            % {"f": row[C_NAME], "n": row[C_NUM], "t": row[C_TAB]}
        )
        self.cb_selection_changed()

    def _row_editor(self, row_id):
        """Dialog for typing the # and Tab positions of one row."""
        row = self._store[row_id]
        total = sum(1 for r in self._store if r[C_PAGE] == row[C_PAGE])
        dialog = Gtk.Dialog(
            title=_("Row editor"), parent=self.uistate.window, modal=True
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(10)
        box.pack_start(
            Gtk.Label(
                label=_("%(f)s (%(n)d fields on Page %(p)d)")
                % {"f": row[C_NAME], "p": row[C_PAGE], "n": total},
                xalign=0,
            ),
            False,
            False,
            0,
        )
        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        spins = []
        for line, (title, col) in enumerate(
            ((_("# (position)"), C_NUM), (_("Tab"), C_TAB))
        ):
            spin = Gtk.SpinButton.new_with_range(1, total, 1)
            spin.set_value(row[col])
            spin.set_activates_default(True)
            grid.attach(Gtk.Label(label=title, xalign=0), 0, line, 1, 1)
            grid.attach(spin, 1, line, 1, 1)
            spins.append(spin)
        box.pack_start(grid, False, False, 0)
        box.pack_start(
            Gtk.Label(
                label=_(
                    "The row moves to that position and the others shift, as "
                    "if dropped there. Tab follows # until Tab is edited."
                ),
                xalign=0,
                wrap=True,
                max_width_chars=48,
            ),
            False,
            False,
            0,
        )
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            self._apply_row_edit(
                row_id, spins[0].get_value_as_int(), spins[1].get_value_as_int()
            )
        dialog.destroy()

    def cb_row_activated(self, _view, path, _column):
        """Double-click or Enter on a row opens the row editor."""
        self._row_editor(self._sorted[path][C_ID])

    def cb_edit_row(self, _widget):
        """Open the row editor for the selected row."""
        _model, it = self._sel.get_selected()
        if it:
            self._row_editor(self._sorted[it][C_ID])

    def cb_suggest(self, _widget):
        """Fill empty tags from placeholder values, else from the field names."""
        from_values = from_names = 0
        left = []
        for row in self._store:
            if row[C_TAG]:
                continue
            tag = _suggest_tag(row[C_VALUE])
            if tag:
                from_values += 1
            else:
                tag = _suggest_tag_from_name(row[C_NAME])
                if tag:
                    from_names += 1
            if tag:
                row[C_TAG] = tag
            elif row[C_NAME] not in left:
                left.append(row[C_NAME])
        text = _("Suggested %(n)d tags (%(v)d from values, %(m)d from names)") % {
            "n": from_values + from_names,
            "v": from_values,
            "m": from_names,
        }
        if left:
            text += _("; %(n)d fields left without a tag, e.g. %(e)s") % {
                "n": len(left),
                "e": ", ".join(left[:3]),
            }
        self._status.set_text(text)
        self.cb_selection_changed()

    def cb_auto_order(self, _widget):
        """Order each page by person/family number, then by fact order.

        Applies to the Tab column when the table is sorted by Tab, otherwise to
        #.  Fields without a parsable tag keep their relative order after the
        tagged ones; switched-off and deleted widgets go last on their page.
        """
        col = self._order_col()

        def key(row):
            tkey = _tag_sort_key(row[C_TAG])
            if tkey is None:
                tkey = (1, 0, 0, 0)
            else:
                tkey = (0,) + tkey
            return (row[C_PAGE], row[C_DEL], row[C_OFF]) + tkey + (row[col], row[C_NUM])

        rows = sorted(self._store, key=key)
        for _page, group in itertools.groupby(rows, key=lambda r: r[C_PAGE]):
            self._set_ranks(col, list(group))
        untagged = sum(1 for r in self._store if _tag_sort_key(r[C_TAG]) is None)
        self._status.set_text(
            _("Ordered %(c)s by tag; %(n)d fields without a usable tag are last")
            % {"c": "Tab" if col == C_TAB else "#", "n": untagged}
        )
        self.cb_selection_changed()

    def _written_name(self, row):
        """The field name the row will have in the written PDF."""
        tag = _normalize_tag(row[C_TAG])
        if tag and self._rb_rename.get_active():
            return tag
        return row[C_NAME]

    def cb_clear_values(self, _widget):
        """Empty the value of every text and choice field (in the table)."""
        cleared = skipped = 0
        for row in self._store:
            if row[C_DEL]:
                continue
            if row[C_TYPE] not in ("Tx", "Ch"):
                skipped += 1
                continue
            if row[C_VALUE]:
                row[C_VALUE] = ""
                cleared += 1
        text = _("Cleared %d values; write the PDF to keep this") % cleared
        if skipped:
            text += _(" (%d other fields left alone)") % skipped
        self._status.set_text(text)
        self.cb_selection_changed()

    def cb_names_to_values(self, _widget):
        """Put each text field's name into its value (in the table)."""
        changed = 0
        for row in self._store:
            if row[C_DEL] or row[C_TYPE] != "Tx":
                continue
            name = self._written_name(row)
            if row[C_VALUE] != name:
                row[C_VALUE] = name
                changed += 1
        self._status.set_text(
            _("Set %(n)d values to the %(m)s; write the PDF to keep this")
            % {
                "n": changed,
                "m": _("new field names")
                if self._rb_rename.get_active()
                else _("current field names"),
            }
        )
        self.cb_selection_changed()

    def cb_tabs_to_values(self, _widget):
        """Put each text field's tab position and name into its value."""
        tab_stops = {}
        for row in sorted(
            self._store, key=lambda r: (r[C_PAGE], r[C_TAB], r[C_NUM], r[C_ID])
        ):
            if not (row[C_DEL] or row[C_OFF]):  # hidden widgets are no tab stop
                tab_stops.setdefault(row[C_PAGE], []).append(row)
        multi_page = len(tab_stops) > 1
        changed = 0
        for page, rows in tab_stops.items():
            for position, row in enumerate(rows, 1):
                if row[C_TYPE] != "Tx":
                    continue
                prefix = "%d-" % page if multi_page else ""
                text = "%s%d: %s" % (prefix, position, self._written_name(row))
                if row[C_VALUE] != text:
                    row[C_VALUE] = text
                    changed += 1
        self._status.set_text(
            _("Set %d values to tab position + name; open the written PDF and Tab "
              "through it: the numbers should count up. Clear values removes them")
            % changed
        )
        self.cb_selection_changed()

    def cb_reset_tab(self, _widget):
        """Make Tab equal to # again and keep it following #."""
        for row in self._store:
            row[C_TAB] = row[C_NUM]
        self._tab_linked = True
        self._status.set_text(_("Tab now follows #"))
        self.cb_selection_changed()

    def _sidecar_path(self):
        """Path of this PDF's crosswalk sidecar: <pdf name>.crosswalk.json."""
        stem = os.path.splitext(os.path.basename(self._path))[0]
        return os.path.join(os.path.dirname(self._path), stem + ".crosswalk.json")

    def _choose(self, title, action, name, pattern, mime, preselect=None):
        dialog = Gtk.FileChooserDialog(
            title=title, parent=self.uistate.window, action=action
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name(pattern)
        file_filter.add_mime_type(mime)
        dialog.add_filter(file_filter)
        if action == Gtk.FileChooserAction.SAVE:
            dialog.set_do_overwrite_confirmation(True)
            dialog.set_current_name(name)
            if self._path:
                dialog.set_current_folder(os.path.dirname(self._path))
        elif preselect and os.path.exists(preselect):
            dialog.set_filename(preselect)
        elif self._path:
            dialog.set_current_folder(os.path.dirname(self._path))
        result = None
        if dialog.run() == Gtk.ResponseType.OK:
            result = dialog.get_filename()
        dialog.destroy()
        return result

    def _off_keys(self):
        """Return {row id: 'name#k'} (k counts same-name widgets in PDF order)."""
        seen = {}
        keys = {}
        for row in sorted(self._store, key=lambda r: r[C_ID]):
            k = seen.get(row[C_NAME], 0)
            seen[row[C_NAME]] = k + 1
            keys[row[C_ID]] = "%s#%d" % (row[C_NAME], k)
        return keys

    def _names_in_order(self, col):
        """Field names in the order of col (page first), without repeats."""
        names = []
        for row in sorted(
            self._store, key=lambda r: (r[C_PAGE], r[col], r[C_NUM])
        ):
            if row[C_NAME] not in names:
                names.append(row[C_NAME])
        return names

    def cb_save_crosswalk(self, _widget):
        """Save tags and orders as JSON ({"tags", "order", "tab"})."""
        if not self._rows:
            return
        path = self._choose(
            _("Save crosswalk"),
            Gtk.FileChooserAction.SAVE,
            os.path.basename(self._sidecar_path()),
            "JSON",
            "application/json",
        )
        if path:
            tags = {r[C_NAME]: r[C_TAG] for r in self._store if r[C_TAG]}
            keys = self._off_keys()
            data = {
                "pdf": os.path.basename(self._path),
                "tags": tags,
                "order": self._names_in_order(C_NUM),
            }
            data["disabled"] = [keys[r[C_ID]] for r in self._store if r[C_OFF]]
            data["deleted"] = [keys[r[C_ID]] for r in self._store if r[C_DEL]]
            if not self._tab_linked:
                data["tab"] = self._names_in_order(C_TAB)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
            self._status.set_text(_("Saved %d mappings") % len(tags))

    def _apply_name_order(self, col, names):
        """Rank rows in col by the position of their name in names."""
        rank = {name: i for i, name in enumerate(names)}
        rows = sorted(
            self._store,
            key=lambda r: (r[C_PAGE], rank.get(r[C_NAME], len(rank)), r[C_NUM]),
        )
        for _page, group in itertools.groupby(rows, key=lambda r: r[C_PAGE]):
            self._set_ranks(col, list(group))

    def cb_load_crosswalk(self, _widget):
        """Apply a JSON crosswalk (tags and orders) to matching fields."""
        if not self._rows:
            return
        path = self._choose(
            _("Load crosswalk"),
            Gtk.FileChooserAction.OPEN,
            "",
            "JSON",
            "application/json",
            preselect=self._sidecar_path(),
        )
        if not path:
            return
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        mapping = data.get("tags", data)
        hits = 0
        for row in self._store:
            if row[C_NAME] in mapping:
                row[C_TAG] = _normalize_tag(mapping[row[C_NAME]])
                hits += 1
        if "disabled" in data:
            keys = self._off_keys()
            off = set(data["disabled"])
            for row in self._store:
                row[C_OFF] = keys[row[C_ID]] in off
        if "deleted" in data:
            keys = self._off_keys()
            gone = set(data["deleted"])
            for row in self._store:
                row[C_DEL] = keys[row[C_ID]] in gone
        if data.get("order"):
            self._apply_name_order(C_NUM, data["order"])
        if data.get("tab"):
            self._apply_name_order(C_TAB, data["tab"])
        text = _("Applied %d mappings") % hits
        made_for = data.get("pdf") if "tags" in data else None
        if made_for and made_for != os.path.basename(self._path):
            text += _(" (this crosswalk was saved for %s)") % made_for
        self._status.set_text(text)
        self.cb_selection_changed()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    def cb_write(self, _widget):
        """Write the mapped PDF to a new file."""
        if not self._path:
            return
        stem = os.path.splitext(os.path.basename(self._path))[0]
        out = self._choose(
            _("Write PDF"),
            Gtk.FileChooserAction.SAVE,
            stem + "_mapped.pdf",
            "PDF",
            "application/pdf",
        )
        if not out:
            return
        if os.path.abspath(out) == os.path.abspath(self._path):
            self._status.set_text(_("Refusing to overwrite the original file."))
            return
        try:
            with _capture_pypdf_warnings() as warned:
                note = self._write(out)
        except Exception as err:  # pylint: disable=broad-except
            self._status.set_text(_("Write failed: %s") % err)
            return
        extra = _pdf_warning_note(warned)
        if extra:
            note = (note + "; " if note else "") + extra
        self._status.set_text(
            (_("Wrote %s") % os.path.basename(out)) + (" - " + note if note else "")
        )

    def _write(self, out):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import (
            ArrayObject,
            BooleanObject,
            NameObject,
            NumberObject,
            TextStringObject,
        )

        try:
            writer = PdfWriter(clone_from=self._path)
        except AssertionError:
            # pypdf's cloner chokes on PDFs with a damaged xref table (seen
            # in real-world fillable forms); append() copes with them.
            writer = PdfWriter()
            source = PdfReader(self._path)
            writer.append(source)
            # append() copies the pages and the form, but not the document
            # information or the XMP metadata, so carry them over
            if source.metadata:
                writer.add_metadata(dict(source.metadata))
            try:
                xmp = source.xmp_metadata
            except Exception:  # pylint: disable=broad-except
                xmp = None
            if xmp is not None:
                writer.xmp_metadata = xmp
        rename = self._rb_rename.get_active()
        # keep the original's PDF version (pypdf would label a rebuilt copy 1.3)
        src_header = PdfReader(self._path).pdf_header

        # tags / names / values
        seen = {}
        changed_values = 0
        for srow in self._store:
            if srow[C_DEL]:
                continue
            row = self._rows[srow[C_ID]]
            page = writer.pages[row.page]
            annot = page["/Annots"][row.annot_idx].get_object()
            field = _field_node(annot)
            tag = _normalize_tag(srow[C_TAG])
            flags = int(annot.get("/F", 0))
            if srow[C_OFF]:
                new_flags = flags | F_HIDDEN
            else:
                new_flags = flags & ~(F_HIDDEN | F_NOVIEW)
            if new_flags != flags:
                annot[NameObject("/F")] = NumberObject(new_flags)
            if srow[C_TYPE] in ("Tx", "Ch") and srow[C_VALUE] != row.value:
                changed_values += 1
                if srow[C_VALUE]:
                    field[NameObject("/V")] = TextStringObject(srow[C_VALUE])
                elif "/V" in field:
                    del field["/V"]
                if "/RV" in field:
                    del field["/RV"]
                if annot is not field and "/V" in annot:
                    del annot["/V"]  # a widget must not override its field
                if "/AP" in annot:
                    del annot["/AP"]  # stale drawing; the viewer redraws from /V
            if srow[C_TYPE] == "Tx":
                ff = int(_inherited(annot, "/Ff") or 0)
                new_ff = (ff | FF_MULTILINE) if srow[C_MULTI] else (ff & ~FF_MULTILINE)
                if new_ff != ff:
                    field[NameObject("/Ff")] = NumberObject(new_ff)
            if rename:
                if tag:
                    new = tag  # no '.', which cannot be part of a /T name
                    if seen.setdefault(new, id(field)) != id(field):
                        raise ValueError(
                            _("'%s' would be used by two different fields") % new
                        )
                    field[NameObject("/T")] = TextStringObject(new)
            elif tag:
                field[NameObject(TAG_KEY)] = TextStringObject(tag)
            elif TAG_KEY in field:
                del field[TAG_KEY]

        # tab order: reorder the widget slots of /Annots per page by Tab
        by_page = {}
        off_widgets = set()
        for srow in sorted(
            self._store, key=lambda r: (r[C_PAGE], r[C_TAB], r[C_NUM])
        ):
            if srow[C_DEL]:
                continue
            row = self._rows[srow[C_ID]]
            by_page.setdefault(row.page, []).append(row.annot_idx)
            if srow[C_OFF]:
                off_widgets.add((row.page, row.annot_idx))
        # the widgets' indirect references as they are before any reordering
        refs = {
            p: list(writer.pages[p]["/Annots"]) for p in {r.page for r in self._rows}
        }
        for p_idx, display in by_page.items():
            slots = sorted(display)
            if slots == display:
                continue
            page = writer.pages[p_idx]
            items = refs[p_idx]
            new_items = list(items)
            for slot, src in zip(slots, display):
                new_items[slot] = items[src]
            page[NameObject("/Annots")] = ArrayObject(new_items)

        if changed_values:
            # without stored drawings the viewer draws each field from its value
            writer._root_object["/AcroForm"][  # pylint: disable=protected-access
                NameObject("/NeedAppearances")
            ] = BooleanObject(True)

        anchors = owned = None
        if self._chk_anchors.get_active():
            anchors, owned = self._plan_anchors(writer, refs)

        # widgets marked Del: take them out of the page, their field and /Fields
        doomed = [
            (self._rows[r[C_ID]].page, self._rows[r[C_ID]].annot_idx)
            for r in self._store
            if r[C_DEL]
        ]
        self._delete_widgets(writer, doomed, refs)

        # How a viewer is told about the order:
        #  /S needs a structure tree (tags) to have any effect, so one is added
        #  /A (PDF 2.0) means "order of the /Annots array"
        note = ""
        signals = [_("annotations"), _("field list")]
        mode = self._cmb_tabs.get_active()
        if mode == 0:
            done, extra = self._add_structure(writer, by_page, refs, off_widgets)
            if done:
                signals += [_("tag tree"), "/Tabs /S"]
            if extra:
                note = extra
        elif mode == 1:
            for p_idx in by_page:
                writer.pages[p_idx][NameObject("/Tabs")] = NameObject("/A")
            signals.append("/Tabs /A")
        self._order_fields(writer, by_page, refs)
        if anchors is not None:
            written, skipped = self._write_anchors(writer, anchors, owned)
            if written or skipped:
                signals.append(_("%d anchors") % written)
            if skipped:
                note = (note + "; " if note else "") + (
                    _("%d anchors skipped because the PDF already has others of that name")
                    % skipped
                )
        tabs_note = _("tab order set in: %s") % ", ".join(signals)
        note = (note + "; " if note else "") + tabs_note

        header = src_header
        if mode == 0 and _pdf_version(header) < (1, 4):  # tagged PDF needs 1.4
            header = "%PDF-1.4" if isinstance(header, str) else b"%PDF-1.4"
        writer.pdf_header = header

        with open(out, "wb") as handle:
            writer.write(handle)
        if doomed:
            note = (note + "; " if note else "") + (
                _("%d widget(s) deleted") % len(doomed)
            )
        if changed_values:
            note = (note + "; " if note else "") + (
                _("%d value(s) changed") % changed_values
            )
        return note

    @staticmethod
    def _delete_widgets(writer, targets, refs):
        """
        Remove widgets (page, /Annots index) from the PDF: from the page's
        /Annots, from their parent field's /Kids and, when a field is left
        without widgets, from its parent or the AcroForm /Fields (and /CO).
        """
        from pypdf.generic import ArrayObject, NameObject

        if not targets:
            return
        root_obj = writer._root_object  # pylint: disable=protected-access
        acro = root_obj["/AcroForm"] if "/AcroForm" in root_obj else None
        removed = set()

        def without(array, ref):
            return ArrayObject(
                [k for k in array if getattr(k, "idnum", None) != ref.idnum]
            )

        def drop(ref):
            """Detach a widget or field node from its parent or /Fields."""
            node = ref.get_object()
            if "/Parent" in node:
                parent_ref = node.raw_get("/Parent")
                parent = parent_ref.get_object()
                parent[NameObject("/Kids")] = without(parent["/Kids"], ref)
                if not parent["/Kids"]:
                    drop(parent_ref)
            elif acro is not None and "/Fields" in acro:
                acro[NameObject("/Fields")] = without(acro["/Fields"], ref)
            removed.add(ref.idnum)

        gone = {}
        for p_idx, annot_idx in targets:
            ref = refs[p_idx][annot_idx]
            gone.setdefault(p_idx, set()).add(ref.idnum)
            drop(ref)
        PDFFieldMapper._drop_struct_refs(
            writer, {i for ids in gone.values() for i in ids}
        )
        for p_idx, ids in gone.items():
            page = writer.pages[p_idx]
            page[NameObject("/Annots")] = ArrayObject(
                [a for a in page["/Annots"] if getattr(a, "idnum", None) not in ids]
            )
        if acro is not None and "/CO" in acro:
            acro[NameObject("/CO")] = ArrayObject(
                [f for f in acro["/CO"] if getattr(f, "idnum", None) not in removed]
            )

    def _plan_anchors(self, writer, refs):
        """
        Work out the anchors to write: [(name, page reference, left, top)] for
        the visible fields in tab order, and the set of positions that anchors
        of this tool would have had (every widget, also deleted and hidden
        ones), which is how earlier anchors of this tool are recognized.
        """
        def target(page, annot_idx):
            rect = [float(v) for v in refs[page][annot_idx].get_object()["/Rect"]]
            left = max(min(rect[0], rect[2]) - ANCHOR_MARGIN, 0.0)
            top = max(rect[1], rect[3]) + ANCHOR_MARGIN
            return round(left, 2), round(top, 2)

        owned = set()
        for srow in self._store:
            row = self._rows[srow[C_ID]]
            page_ref = writer.pages[row.page].indirect_reference
            owned.add((page_ref.idnum,) + target(row.page, row.annot_idx))
        wanted = []
        seen = set()
        for srow in sorted(
            self._store, key=lambda r: (r[C_PAGE], r[C_TAB], r[C_NUM], r[C_ID])
        ):
            if srow[C_DEL] or srow[C_OFF]:
                continue
            name = _normalize_tag(srow[C_TAG]) or srow[C_NAME]
            if not name or name in seen:
                continue
            seen.add(name)
            row = self._rows[srow[C_ID]]
            left, top = target(row.page, row.annot_idx)
            wanted.append((name, writer.pages[row.page].indirect_reference, left, top))
        return wanted, owned

    @staticmethod
    def _destination_entries(root_obj):
        """All (name, destination) pairs of the PDF's named destination tree."""
        entries = []
        names = root_obj["/Names"].get_object() if "/Names" in root_obj else None
        if names is None or "/Dests" not in names:
            return entries
        todo = [names["/Dests"]]
        while todo:
            node = todo.pop(0).get_object()
            if "/Kids" in node:
                todo = list(node["/Kids"]) + todo
            elif "/Names" in node:
                pairs = node["/Names"].get_object()
                for i in range(0, len(pairs) - 1, 2):
                    key = pairs[i].get_object() if hasattr(pairs[i], "get_object") else pairs[i]
                    entries.append((str(key), pairs[i + 1]))
        return entries

    @staticmethod
    def _is_own_anchor(value, owned):
        """True if a destination is an XYZ one at a position of this tool."""
        dest = value.get_object()
        if hasattr(dest, "keys") and "/D" in dest:
            dest = dest["/D"].get_object()
        if not isinstance(dest, list) or len(dest) < 4:
            return False
        if str(dest[1].get_object() if hasattr(dest[1], "get_object") else dest[1]) != "/XYZ":
            return False
        page = getattr(dest[0], "idnum", None)
        try:
            left = round(float(dest[2]), 2)
            top = round(float(dest[3]), 2)
        except (TypeError, ValueError):
            return False
        return (page, left, top) in owned

    @staticmethod
    def _write_anchors(writer, anchors, owned):
        """
        Make the PDF's named destinations hold one anchor per visible field.
        Anchors this tool wrote earlier are replaced, other destinations are
        kept as they are (a name already used by another one is not taken).
        Returns (anchors written, anchors skipped).
        """
        from pypdf.generic import (
            ArrayObject,
            DictionaryObject,
            FloatObject,
            NameObject,
            NullObject,
            TextStringObject,
        )

        root_obj = writer._root_object  # pylint: disable=protected-access
        kept = [
            (name, value)
            for name, value in PDFFieldMapper._destination_entries(root_obj)
            if not PDFFieldMapper._is_own_anchor(value, owned)
        ]
        used = {name for name, _value in kept}
        # Some viewers (the poppler based ones: Okular, Papers, Xreader) read only
        # the old style list of destinations when a PDF has one, and ignore the
        # name tree.  So the anchors go into that list too.
        legacy = root_obj["/Dests"].get_object() if "/Dests" in root_obj else None
        if legacy is not None:
            for key in list(legacy.keys()):
                if PDFFieldMapper._is_own_anchor(legacy.raw_get(key), owned):
                    del legacy[key]
            used |= {str(key).lstrip("/") for key in legacy}
        added = []
        skipped = 0
        for name, page_ref, left, top in anchors:
            if name in used:
                skipped += 1
                continue
            used.add(name)
            added.append(
                (
                    name,
                    ArrayObject(
                        [
                            page_ref,
                            NameObject("/XYZ"),
                            FloatObject(left),
                            FloatObject(top),
                            NullObject(),
                        ]
                    ),
                )
            )
        if legacy is not None:
            for name, value in added:
                legacy[NameObject("/" + name)] = ArrayObject(list(value))
        entries = sorted(kept + added, key=lambda pair: pair[0])
        names = root_obj["/Names"].get_object() if "/Names" in root_obj else None
        if not entries:
            if names is not None and "/Dests" in names:
                del names["/Dests"]
            return 0, skipped
        flat = ArrayObject()
        for name, value in entries:
            flat.append(TextStringObject(name))
            flat.append(value)
        if names is None:
            names = DictionaryObject()
            root_obj[NameObject("/Names")] = names
        names[NameObject("/Dests")] = DictionaryObject({NameObject("/Names"): flat})
        return len(added), skipped

    @staticmethod
    def _form_elements(
        writer, by_page, refs, off_widgets, parent_ref, first_key, skip_ids=()
    ):
        """
        Create one Form structure element per widget that is not switched off,
        in tab order, each pointing at its widget.  Returns (the new elements,
        the parent-tree entries [key, element, ...], the next free key).
        """
        from pypdf.generic import (
            ArrayObject,
            DictionaryObject,
            NameObject,
            NumberObject,
        )

        def new(obj):
            return writer._add_object(obj)  # pylint: disable=protected-access

        kids = ArrayObject()
        nums = ArrayObject()
        key = first_key
        for p_idx in sorted(by_page):
            page = writer.pages[p_idx]
            for annot_idx in by_page[p_idx]:
                if (p_idx, annot_idx) in off_widgets:
                    continue
                widget_ref = refs[p_idx][annot_idx]
                if widget_ref.idnum in skip_ids:
                    continue
                elem_ref = new(
                    DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/StructElem"),
                            NameObject("/S"): NameObject("/Form"),
                            NameObject("/P"): parent_ref,
                            NameObject("/Pg"): page.indirect_reference,
                            NameObject("/K"): DictionaryObject(
                                {
                                    NameObject("/Type"): NameObject("/OBJR"),
                                    NameObject("/Obj"): widget_ref,
                                    NameObject("/Pg"): page.indirect_reference,
                                }
                            ),
                        }
                    )
                )
                kids.append(elem_ref)
                widget_ref.get_object()[NameObject("/StructParent")] = NumberObject(key)
                nums.append(NumberObject(key))
                nums.append(elem_ref)
                key += 1
        return kids, nums, key

    @staticmethod
    def _referenced_widgets(tree, widget_ids):
        """The ids of those widgets that the tag tree already points at."""
        found = set()
        seen = set()
        todo = [tree.raw_get("/K")] if "/K" in tree else []
        while todo:
            item = todo.pop()
            ident = getattr(item, "idnum", None)
            if ident is not None:
                if ident in seen:
                    continue
                seen.add(ident)
            node = item.get_object()
            if isinstance(node, list):
                todo.extend(node)
            elif hasattr(node, "keys"):
                if str(node.get("/Type", "")) == "/OBJR" and "/Obj" in node:
                    target = getattr(node.raw_get("/Obj"), "idnum", None)
                    if target in widget_ids:
                        found.add(target)
                elif "/K" in node:
                    todo.append(node.raw_get("/K"))
        return found

    @staticmethod
    def _wrapped_widget(child, widget_ids):
        """Widget id if child is a structure element wrapping exactly one."""
        node = child.get_object()
        if not (hasattr(node, "keys") and "/K" in node):
            return None
        inner = node["/K"].get_object()
        if isinstance(inner, list) and len(inner) == 1:
            inner = inner[0].get_object()
        if (
            hasattr(inner, "keys")
            and str(inner.get("/Type", "")) == "/OBJR"
            and "/Obj" in inner
        ):
            target = getattr(inner.raw_get("/Obj"), "idnum", None)
            return target if target in widget_ids else None
        return None

    @staticmethod
    def _widget_elements(tree, widget_ids):
        """List (kids array, index, widget id) of elements wrapping one widget."""
        found = []
        seen = set()
        todo = [tree.raw_get("/K")] if "/K" in tree else []
        while todo:
            item = todo.pop()
            ident = getattr(item, "idnum", None)
            if ident is not None:
                if ident in seen:
                    continue
                seen.add(ident)
            node = item.get_object()
            if isinstance(node, list):
                for index, child in enumerate(node):
                    target = PDFFieldMapper._wrapped_widget(child, widget_ids)
                    if target is None:
                        todo.append(child)
                    else:
                        found.append((node, index, target))
            elif hasattr(node, "keys") and "/K" in node:
                todo.append(node.raw_get("/K"))
        return found

    @staticmethod
    def _parent_tree_leaves(tree):
        """The leaf nodes (those with /Nums) of the tree's parent tree, in order."""
        leaves = []
        todo = [tree["/ParentTree"]]
        while todo:
            node = todo.pop(0).get_object()
            if "/Kids" in node:
                todo = list(node["/Kids"]) + todo
            elif "/Nums" in node:
                leaves.append(node)
        return leaves

    @staticmethod
    def _append_parent_tree(tree, nums, last_key):
        """Add [key, element, ...] entries to the end of the parent tree."""
        from pypdf.generic import NumberObject

        parent_tree = tree["/ParentTree"].get_object()
        node, path = parent_tree, [parent_tree]
        while "/Kids" in node:
            node = node["/Kids"].get_object()[-1].get_object()
            path.append(node)
        for item in nums:
            node["/Nums"].get_object().append(item)
        for step in path:  # keep the number tree's limits right
            if "/Limits" in step:
                step["/Limits"].get_object()[1] = NumberObject(last_key)

    @staticmethod
    def _first_free_key(tree):
        """First parent-tree key that no existing entry uses."""
        highest = -1
        for leaf in PDFFieldMapper._parent_tree_leaves(tree):
            nums = leaf["/Nums"].get_object()
            if len(nums):
                highest = max(highest, int(nums[len(nums) - 2]))
        return max(int(tree.get("/ParentTreeNextKey", 0)), highest + 1)

    @staticmethod
    def _drop_struct_refs(writer, deleted_ids):
        """Remove structure elements that wrap deleted widgets, and their entries."""
        root_obj = writer._root_object  # pylint: disable=protected-access
        if "/StructTreeRoot" not in root_obj or not deleted_ids:
            return
        tree = root_obj["/StructTreeRoot"].get_object()
        gone = set()
        by_array = {}
        for array, index, _wid in PDFFieldMapper._widget_elements(tree, deleted_ids):
            by_array.setdefault(id(array), (array, []))[1].append(index)
        for array, indexes in by_array.values():
            for index in indexes:
                gone.add(getattr(array[index], "idnum", None))
            array[:] = [x for i, x in enumerate(array) if i not in set(indexes)]
        for leaf in PDFFieldMapper._parent_tree_leaves(tree):
            nums = leaf["/Nums"].get_object()
            keep = []
            for i in range(0, len(nums), 2):
                if getattr(nums[i + 1], "idnum", None) not in gone:
                    keep += [nums[i], nums[i + 1]]
            nums[:] = keep

    @staticmethod
    def _add_structure(writer, by_page, refs, off_widgets):
        """
        Make the tag tree carry the tab order as /Tabs /S expects: a new tree
        when there is none, otherwise a "Form fields" branch added to the
        existing one (its other content is left alone).  Returns (done, note).
        """
        from pypdf.generic import (
            ArrayObject,
            BooleanObject,
            DictionaryObject,
            NameObject,
            NumberObject,
            TextStringObject,
        )

        root_obj = writer._root_object  # pylint: disable=protected-access

        def new(obj):
            return writer._add_object(obj)  # pylint: disable=protected-access

        def set_tabs():
            for p_idx in by_page:
                writer.pages[p_idx][NameObject("/Tabs")] = NameObject("/S")

        if "/StructTreeRoot" not in root_obj:  # no tags at all: make a tree
            tree = DictionaryObject()
            tree_ref = new(tree)
            doc = DictionaryObject()
            doc_ref = new(doc)
            kids, nums, key = PDFFieldMapper._form_elements(
                writer, by_page, refs, off_widgets, doc_ref, 0
            )
            doc[NameObject("/Type")] = NameObject("/StructElem")
            doc[NameObject("/S")] = NameObject("/Document")
            doc[NameObject("/P")] = tree_ref
            doc[NameObject("/K")] = kids
            tree[NameObject("/Type")] = NameObject("/StructTreeRoot")
            tree[NameObject("/K")] = doc_ref
            tree[NameObject("/ParentTree")] = DictionaryObject(
                {NameObject("/Nums"): nums}
            )
            tree[NameObject("/ParentTreeNextKey")] = NumberObject(key)
            root_obj[NameObject("/StructTreeRoot")] = tree_ref
            root_obj[NameObject("/MarkInfo")] = DictionaryObject(
                {NameObject("/Marked"): BooleanObject(True)}
            )
            set_tabs()
            return True, ""

        tree_ref = root_obj.raw_get("/StructTreeRoot")
        tree = tree_ref.get_object()
        widget_ids = {refs[p][i].idnum for p in by_page for i in by_page[p]}
        listed = PDFFieldMapper._referenced_widgets(tree, widget_ids)
        if listed:
            return PDFFieldMapper._reorder_listed(
                writer, tree, by_page, refs, off_widgets, widget_ids, listed, set_tabs
            )
        # Hang a "Form fields" branch under the top element of the tree.
        top_raw = tree.raw_get("/K") if "/K" in tree else None
        top = top_raw.get_object() if top_raw is not None else None
        if top is not None and hasattr(top, "keys") and hasattr(top_raw, "idnum"):
            container, container_ref = top, top_raw
        else:
            container, container_ref = tree, tree_ref
        sect = DictionaryObject()
        sect_ref = new(sect)
        first_key = PDFFieldMapper._first_free_key(tree)
        kids, nums, key = PDFFieldMapper._form_elements(
            writer, by_page, refs, off_widgets, sect_ref, first_key
        )
        sect[NameObject("/Type")] = NameObject("/StructElem")
        sect[NameObject("/S")] = NameObject("/Sect")
        sect[NameObject("/T")] = TextStringObject("Form fields")
        sect[NameObject("/P")] = container_ref
        sect[NameObject("/K")] = kids
        if "/K" not in container:
            container[NameObject("/K")] = ArrayObject([sect_ref])
        else:
            existing = container["/K"].get_object()
            if isinstance(existing, list):
                existing.append(sect_ref)
            else:  # a single child: turn /K into an array
                container[NameObject("/K")] = ArrayObject(
                    [container.raw_get("/K"), sect_ref]
                )
        PDFFieldMapper._append_parent_tree(tree, nums, key - 1)
        tree[NameObject("/ParentTreeNextKey")] = NumberObject(key)
        set_tabs()
        return True, _("a Form fields branch was added to the existing tag tree")

    @staticmethod
    def _reorder_listed(
        writer, tree, by_page, refs, off_widgets, widget_ids, listed, set_tabs
    ):
        """
        The tag tree already has elements for the fields (for instance from an
        earlier write).  When they all sit in one list, bring that list into
        tab order and add elements for any visible field that lacks one.
        """
        from pypdf.generic import NameObject, NumberObject

        # a switched-off widget is no tab stop: drop its element, keep the rest
        off_ids = {refs[p][i].idnum for (p, i) in off_widgets}
        if off_ids & listed:
            PDFFieldMapper._drop_struct_refs(writer, off_ids & listed)
            listed = listed - off_ids
        found = PDFFieldMapper._widget_elements(tree, widget_ids)
        arrays = {id(array) for array, _i, _w in found}
        if not found or {w for _a, _i, w in found} != listed or len(arrays) != 1:
            return False, _(
                "the tag tree groups the fields in several places, so it was not changed"
            )
        array = found[0][0]
        parent_ref = array[found[0][1]].get_object().raw_get("/P")
        missing = {
            refs[p][i].idnum
            for p in by_page
            for i in by_page[p]
            if (p, i) not in off_widgets and refs[p][i].idnum not in listed
        }
        if missing:
            skip = widget_ids - missing
            first_key = PDFFieldMapper._first_free_key(tree)
            kids, nums, key = PDFFieldMapper._form_elements(
                writer, by_page, refs, off_widgets, parent_ref, first_key, skip
            )
            start = len(array)
            for kid in kids:
                array.append(kid)
            found += [
                (array, start + n, PDFFieldMapper._wrapped_widget(kid, widget_ids))
                for n, kid in enumerate(kids)
            ]
            PDFFieldMapper._append_parent_tree(tree, nums, key - 1)
            tree[NameObject("/ParentTreeNextKey")] = NumberObject(key)
        rank = {}
        for p_idx in sorted(by_page):
            for annot_idx in by_page[p_idx]:
                rank.setdefault(refs[p_idx][annot_idx].idnum, len(rank))
        slots = sorted(index for _a, index, _w in found)
        entries = sorted(
            ((array[index], wid) for _a, index, wid in found),
            key=lambda pair: rank.get(pair[1], len(rank)),
        )
        for slot, (element, _wid) in zip(slots, entries):
            array[slot] = element
        set_tabs()
        return True, _("the tag tree's Form elements were put in tab order")

    @staticmethod
    def _order_fields(writer, by_page, refs):
        """
        Put the AcroForm field list, and every nested group of fields, in tab
        order: a group goes where its first widget is.
        """
        from pypdf.generic import ArrayObject, NameObject

        root_obj = writer._root_object  # pylint: disable=protected-access
        if "/AcroForm" not in root_obj or "/Fields" not in root_obj["/AcroForm"]:
            return
        rank = {}
        for p_idx in sorted(by_page):
            for annot_idx in by_page[p_idx]:
                rank.setdefault(refs[p_idx][annot_idx].idnum, len(rank))
        big = len(rank)
        lowest = {}

        def order(ref):
            """Sort the kids below ref; return the lowest rank in its subtree."""
            ident = getattr(ref, "idnum", None)
            if ident in lowest:
                return lowest[ident]
            lowest[ident] = big  # guards against loops
            node = ref.get_object()
            if hasattr(node, "keys") and "/Kids" in node:
                kids = list(node["/Kids"])
                for kid in kids:
                    order(kid)
                kids.sort(key=lambda k: lowest.get(getattr(k, "idnum", None), big))
                node[NameObject("/Kids")] = ArrayObject(kids)
                value = min(
                    (lowest.get(getattr(k, "idnum", None), big) for k in kids),
                    default=big,
                )
            else:
                value = rank.get(ident, big)
            lowest[ident] = value
            return value

        fields = list(root_obj["/AcroForm"]["/Fields"])
        for field in fields:
            order(field)
        fields.sort(key=lambda f: lowest.get(getattr(f, "idnum", None), big))
        root_obj["/AcroForm"][NameObject("/Fields")] = ArrayObject(fields)
