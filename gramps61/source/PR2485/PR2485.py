#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# (Draft mode: full GPL header to be added when made commit-ready.)
#
"""
PR2485 (Edit Person Tweaks)

Monkey patches for the New/Edit Person dialogs, Gramps 5.2 to 6.2.

1. PR 2485 (Doug Blank, fixes Mantis 0013365): Multiple Surnames table
   column widths persist for all five columns, the Origin column drags
   like the others (FIXED sizing), and wider default widths.
   Done without touching EmbeddedList: SurnameTab.build_columns() is
   wrapped to fix the Origin column and restore the saved widths again
   once its two extra columns exist. Skipped if the core already has
   the PR (detected from EmbeddedList.__init__).
   At startup, a saved width list collapsed to 2 in the Prefix,
   Connector and Origin columns (e.g. [2, 49.2, 2, 2] in gramps.ini)
   is reset to the default, so those columns are usable again.
1b. Global column-width fix in PersistentTreeView (all editor tabs and
   lists, not just Edit Person). A table that was never drawn (the
   hidden Multiple Surnames table, a notebook tab never opened) has
   column widths of 0. The core rounds every width below 2 up to 2
   before its "don't save if a width is 0" check, so that check never
   fires and 2s are saved; 2 characters then collapses a text column,
   and the collapsed width is saved again on every close. The patch
   keeps 0 as 0 so the core check skips the save, and on restore
   ignores a saved 2 for text columns (2 is only meaningful as the
   icon-column marker), which also heals values already in gramps.ini.
   Skipped if the core is already fixed.
2. "Use Multiple Surnames" (button or Ctrl+A) switches to the table,
   adds a new surname row and starts editing its Prefix cell. If the
   only existing surname row is completely empty, that row is edited
   instead of adding a second blank one. In Multiple Surnames mode,
   Ctrl+A then runs the table's "Create and add a new surname" action
   (in single surname mode it stays on "Use Multiple Surnames").
3. A Fuzzy Match Lookup button right of the single Surname field, shown
   only while the Fuzzy Matching addon's "Fuzzy Match API" plugin is
   registered and not hidden.
4. A "surname" field tip (placeholder text) in the Surname field, like
   the existing "prefix" and "suffix" tips.
"""

import inspect
import logging

from gi.repository import Gdk, GLib, Gtk

from gramps.gen.config import config as global_config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import BasePluginManager

_ = glocale.get_addon_translator(__file__).gettext

LOG = logging.getLogger(".PR2485")

_PATCH_MARK = "_pr2485"

# id= of the Fuzzy Matching addon's GENERAL "API" plugin
# (FuzzyMatchingGramplet.gpr.py, FuzzyMatchAPI.md).
FUZZY_API_ID = "Fuzzy Match API"
FUZZY_ICON_SIZE = 22

# PR 2485 default widths: (old, new). Only changed if still the old value.
PR2485_TEXT_WIDTHS = {0: (150, 170), 2: (100, 130)}  # Prefix, Connector
PR2485_ORIGIN_WIDTH = (150, 160)


# ----------------------------------------------------------------------
# Fuzzy Matching helpers (see "Gramplet feature recipes", recipe 4)
# ----------------------------------------------------------------------
def fuzzy_match_registered():
    """True if the Fuzzy Match API plugin is registered and not hidden."""
    if BasePluginManager.get_instance().get_plugin(FUZZY_API_ID) is None:
        return False
    return FUZZY_API_ID not in global_config.get("plugin.hiddenplugins")


def get_fuzzy_match_lookup():
    """Return show_fuzzy_lookup from the Fuzzy Match API, or None."""
    pmgr = BasePluginManager.get_instance()
    pdata = pmgr.get_plugin(FUZZY_API_ID)
    if pdata is None:
        return None
    try:
        module = pmgr.import_plugin(pdata)
    except ImportError:
        return None
    if module is None:
        return None
    return getattr(module, "show_fuzzy_lookup", None)


# ----------------------------------------------------------------------
# 1. PR 2485: Multiple Surnames column widths
# ----------------------------------------------------------------------
def core_has_pr2485():
    """True if EmbeddedList already restores widths after build_columns()."""
    from gramps.gui.editors.displaytabs.embeddedlist import EmbeddedList

    try:
        source = inspect.getsource(EmbeddedList.__init__)
    except (OSError, TypeError):
        return False
    return "restore_column_size" in source


SURNAME_SPACING_KEY = "spacing.person_editor_surnames"

# PersistentTreeView saves widths in "characters" of this many pixels.
# 2 is the value it stores for icon columns (header is a Gtk.Image).
ICON_COLUMN_SIZE = 2


def _char_width():
    """Pixel width of one saved 'character', as PersistentTreeView uses."""
    font_desc = Gtk.Label().get_pango_context().get_font_description()
    return 1.2 * (font_desc.get_size() / 1000)


def _is_icon_column(column):
    """True for columns whose header is an icon (Private, Source...)."""
    return isinstance(column.get_widget(), Gtk.Image)


def ptv_get_columns_size(self):
    """
    PersistentTreeView.get_columns_size() that reports 0 for a column
    that was never drawn, instead of rounding it up to 2, so
    save_column_info() skips saving (its "0 not in newsize" check).
    """
    columns = self.get_columns()
    char_width = _char_width()
    newsize = []
    for nbc, column in enumerate(columns):
        # As the core: skip the last column unless it is the only one.
        if nbc < len(columns) - 1 or len(columns) == 1:
            if _is_icon_column(column):
                size = ICON_COLUMN_SIZE
            else:
                size = column.get_width() / char_width
                if 0 < size < 2:
                    size = 2
            newsize.append(size)
    return newsize


def ptv_restore_column_size(self):
    """
    PersistentTreeView.restore_column_size() that leaves a text column
    at its default width when its saved value is 2 or less: such a
    value comes from the never-drawn bug, never from a real drag.
    """
    if self.config_name == "undefined":
        return
    size = global_config.get(self.config_name)
    if not size:
        return
    char_width = _char_width()
    for nbc, column in enumerate(self.get_columns()):
        if nbc >= len(size):
            break
        if size[nbc] <= ICON_COLUMN_SIZE and not _is_icon_column(column):
            continue  # collapsed by the bug; keep the default width
        column.set_fixed_width(size[nbc] * char_width)


def patch_persistent_treeview():
    """Apply the never-drawn width fix. Return False if not applied."""
    from gramps.gui.widgets.persistenttreeview import PersistentTreeView

    if getattr(PersistentTreeView.get_columns_size, _PATCH_MARK, False):
        return False
    try:
        source = inspect.getsource(PersistentTreeView.get_columns_size)
    except (OSError, TypeError):
        return False
    if "size = 2 if size < 2 else size" not in source:
        LOG.debug("PersistentTreeView already fixed; left alone.")
        return False
    setattr(ptv_get_columns_size, _PATCH_MARK, True)
    PersistentTreeView.get_columns_size = ptv_get_columns_size
    PersistentTreeView.restore_column_size = ptv_restore_column_size
    return True


def reset_collapsed_surname_widths():
    """
    Reset the saved Multiple Surnames widths if they are collapsed.

    Collapsed means the 1st, 3rd and 4th saved values (Prefix,
    Connector, Origin) are all 2, as in
    ``person_editor_surnames=[2, 49.16720920138889, 2, 2]``.
    The default is an empty list (what PersistentTreeView registers),
    which makes the table use its built-in column widths.
    Return True if a reset was made.
    """
    # gramps.ini values are loaded into config even before
    # PersistentTreeView registers the key, so is_set/get work here.
    if not global_config.is_set(SURNAME_SPACING_KEY):
        return False
    size = global_config.get(SURNAME_SPACING_KEY)
    if not isinstance(size, list) or len(size) < 4:
        return False
    if not size[0] == size[2] == size[3] == 2:
        return False
    if not global_config.has_default(SURNAME_SPACING_KEY):
        global_config.register(SURNAME_SPACING_KEY, [])
    global_config.reset(SURNAME_SPACING_KEY)
    global_config.save()
    LOG.warning(
        "Reset collapsed Multiple Surnames column widths %s to the default.",
        size,
    )
    return True


def patch_surnametab():
    """Apply PR 2485 to SurnameTab. Return False if not applied."""
    from gramps.gui.editors.displaytabs.surnametab import SurnameTab

    if getattr(SurnameTab.build_columns, _PATCH_MARK, False):
        return False  # already patched (plugin reloaded)
    if core_has_pr2485():
        LOG.debug("Gramps core already has PR 2485; SurnameTab left alone.")
        return False

    # Wider defaults. The translated names are kept as the core built them.
    names = list(SurnameTab._column_names)
    for index, (old, new) in PR2485_TEXT_WIDTHS.items():
        row = names[index]
        if row[2] == old:
            names[index] = (row[0], row[1], new) + tuple(row[3:])
    SurnameTab._column_names = names
    combo = SurnameTab._column_combo
    if combo[2] == PR2485_ORIGIN_WIDTH[0]:
        SurnameTab._column_combo = (
            combo[0],
            combo[1],
            PR2485_ORIGIN_WIDTH[1],
        ) + tuple(combo[3:])

    original = SurnameTab.build_columns

    def build_columns(self):
        """SurnameTab.build_columns() plus the PR 2485 fixes."""
        original(self)
        # The core appends Origin then Primary after the text columns.
        origin = self.columns[-2]
        # FIXED sizing, as the other columns use; GROW_ONLY (the GTK
        # default) resists shrinking, so the handle feels stuck.
        origin.set_min_width(-1)
        origin.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        origin.set_fixed_width(self._column_combo[2])
        # The base build_columns() restored the saved widths before
        # Origin and Primary existed; restore again now all five do.
        self.tree.restore_column_size()

    setattr(build_columns, _PATCH_MARK, True)
    SurnameTab.build_columns = build_columns
    return True


# ----------------------------------------------------------------------
# 2. Multiple Surnames: add a row and edit its Prefix cell
# ----------------------------------------------------------------------
def _surname_is_blank(surname):
    """True if a Surname has no prefix, surname or connector text."""
    return not (
        surname.get_prefix().strip()
        or surname.get_surname().strip()
        or surname.get_connector().strip()
    )


def _cb_start_prefix_edit(tab, row):
    """Idle callback: start editing the Prefix cell of ``row``."""
    try:
        if row >= len(tab.model):
            return False
        path = Gtk.TreePath.new_from_indices([row])
        tab.selection.select_path(path)
        tab.tree.grab_focus()
        tab.tree.set_cursor_on_cell(path, tab.columns[0], None, True)
    except AttributeError:
        pass  # dialog closed before the idle call ran
    return False  # run once


def patch_mult_surn_clicked(edit_person_class):
    """Wrap EditPerson._mult_surn_clicked. Return False if not applied."""
    original = edit_person_class._mult_surn_clicked
    if getattr(original, _PATCH_MARK, False):
        return False

    def _mult_surn_clicked(self, obj):
        """Show the Multiple Surnames table, add a row, edit its Prefix."""
        # The core switches views and rebuilds self.surntab.
        original(self, obj)
        if self.db.readonly:
            return
        tab = self.surntab
        surnames = tab.obj.get_surname_list()
        if len(surnames) == 1 and _surname_is_blank(surnames[0]):
            row = 0  # edit the empty row rather than add a second one
        else:
            # Same path as the table's own "+" button: appends a blank
            # Surname, sets the primary flag if needed, calls on_change.
            tab.add_button_clicked(obj)
            row = len(tab.model) - 1
        # The table was only just shown and is not yet laid out, so the
        # cell editor started by add_button_clicked may not stick. Start
        # it again once GTK has drawn the table.
        GLib.idle_add(_cb_start_prefix_edit, tab, row)

    setattr(_mult_surn_clicked, _PATCH_MARK, True)
    edit_person_class._mult_surn_clicked = _mult_surn_clicked
    return True


def _cb_add_surname_accel(editor, *_args):
    """
    Ctrl+A in Multiple Surnames mode: "Create and add a new surname".

    Returns False in single surname mode (and read-only trees), so the
    core Ctrl+A accelerator on "Use Multiple Surnames" still runs. That
    button is hidden in Multiple Surnames mode, and GTK does not
    activate accelerators of hidden widgets, so the two never clash.
    """
    if editor.db.readonly or not editor.multsurnfr.get_visible():
        return False
    tab = editor.surntab
    # Commit a cell still being typed in; starting the new row's editor
    # cancels it. get_parent() is None once that editor has finished.
    celle = getattr(tab, "curr_celle", None)
    if celle is not None and celle.get_parent() is not None:
        if isinstance(celle, Gtk.Entry):
            # Prefix/Surname/Connector use Gramps' CellRendererTextEdit,
            # which saves only on focus-out (editing_done() does nothing
            # for it); send the same "edited" signal its focus_out does.
            tab.curr_cellr.emit("edited", tab.curr_path, celle.get_text())
        else:
            celle.editing_done()  # Origin combo: a standard renderer
    tab.add_button_clicked(None)
    GLib.idle_add(_cb_start_prefix_edit, tab, len(tab.model) - 1)
    return True


def install_add_surname_accel(editor):
    """Add the Multiple Surnames Ctrl+A accelerator to the editor window."""
    window = getattr(editor, "window", None) or editor.top.toplevel
    accel_group = Gtk.AccelGroup()
    accel_group.connect(
        Gdk.KEY_a,
        Gdk.ModifierType.CONTROL_MASK,
        Gtk.AccelFlags.VISIBLE,
        lambda *args: _cb_add_surname_accel(editor, *args),
    )
    window.add_accel_group(accel_group)
    return accel_group


# ----------------------------------------------------------------------
# 3 and 4. Surname field: Fuzzy Match Lookup button and "surname" tip
# ----------------------------------------------------------------------
def _cb_fuzzy_lookup_clicked(editor, button):
    """Open the Fuzzy Match Lookup window seeded from the name fields."""
    show_fuzzy_lookup = get_fuzzy_match_lookup()
    if show_fuzzy_lookup is None:
        button.hide()  # addon removed or broken since the dialog opened
        return
    surname = editor.top.get_object("surname").get_text().strip()
    given = editor.top.get_object("given_name").get_text().strip()
    kwargs = {"surname": surname, "given_name": given}
    try:
        params = inspect.signature(show_fuzzy_lookup).parameters
    except (TypeError, ValueError):
        params = {}
    if "given_filter" in params:
        kwargs["given_filter"] = given
    # No on_select: double-click opens that person's editor, which is
    # what a "does this person already exist?" check needs here.
    # Track is [] (a top-level window), not editor.track: nested under
    # the editor, closing the editor makes Gramps close the lookup
    # window too, and FuzzyMatchLookupWindow (up to at least 0.5.x)
    # never calls ManagedWindow.show(), so it has no "opened" attribute
    # and that cascade raises AttributeError. Top-level also means the
    # lookup window and any editor opened from it outlive this dialog.
    try:
        show_fuzzy_lookup(editor.dbstate, editor.uistate, [], **kwargs)
    except Exception:  # pylint: disable=broad-except
        LOG.exception("Fuzzy Match Lookup failed")


def add_fuzzy_button(editor, entry):
    """Pack a Fuzzy Match Lookup button right of the Surname entry."""
    button = Gtk.Button()
    image = Gtk.Image.new_from_icon_name("gtk-find", Gtk.IconSize.BUTTON)
    image.set_pixel_size(FUZZY_ICON_SIZE)
    image.show()  # no_show_all on the button also skips its child
    button.add(image)
    button.set_relief(Gtk.ReliefStyle.NONE)
    button.set_focus_on_click(False)
    button.set_tooltip_text(
        _("Fuzzy Match Lookup: find people whose surname sounds like this one")
    )
    # Visibility is managed here, not by the dialog's show_all().
    button.set_no_show_all(True)
    button.connect(
        "clicked", lambda btn: _cb_fuzzy_lookup_clicked(editor, btn)
    )
    entry.get_parent().pack_start(button, False, False, 0)

    def cb_sync_visible(*_args):
        # Follows the Surname entry: hidden in Multiple Surnames mode.
        button.set_visible(entry.get_visible() and fuzzy_match_registered())

    entry.connect("notify::visible", cb_sync_visible)
    cb_sync_visible()
    return button


def patch_setup_fields(edit_person_class):
    """Wrap EditPerson._setup_fields. Return False if not applied."""
    original = edit_person_class._setup_fields
    if getattr(original, _PATCH_MARK, False):
        return False

    def _setup_fields(self):
        """EditPerson._setup_fields() plus the Surname field additions."""
        original(self)
        entry = self.top.get_object("surname")
        # Same style as the core's "prefix" and "suffix" field tips.
        entry.set_placeholder_text(_("surname"))
        self._ept_fuzzy_button = add_fuzzy_button(self, entry)
        self._ept_accel_group = install_add_surname_accel(self)

    setattr(_setup_fields, _PATCH_MARK, True)
    edit_person_class._setup_fields = _setup_fields
    return True


# ----------------------------------------------------------------------
# Registration entry point
# ----------------------------------------------------------------------
def load_on_reg(dbstate, uistate, plugin):
    """Called by the Gramps plugin manager at startup."""
    if uistate is None:
        return []  # CLI: no dialogs are built

    from gramps.gui.editors.editperson import EditPerson

    for label, patch in (
        ("Reset collapsed surname widths", reset_collapsed_surname_widths),
        ("Never-drawn column widths", patch_persistent_treeview),
        ("PR 2485 surname columns", patch_surnametab),
        ("Multiple Surnames add row", lambda: patch_mult_surn_clicked(EditPerson)),
        ("Surname field tip, lookup, Ctrl+A", lambda: patch_setup_fields(EditPerson)),
    ):
        try:
            LOG.debug("%s: %s", label, "applied" if patch() else "skipped")
        except Exception:  # pylint: disable=broad-except
            # One failed patch must not stop the others or Gramps.
            LOG.exception("PR2485: %s patch failed", label)
    return []
