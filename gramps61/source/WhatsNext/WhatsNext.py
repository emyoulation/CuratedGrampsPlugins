# encoding: utf-8
#
# Gramps - a GTK+/GNOME based genealogy program - What's Next Gramplet plugin
#
# Copyright (C) 2008  Reinhard Mueller
# Copyright (C) 2010  Jakim Friant
# Copyright (C) 2023-2024  Brian McCullough
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
# pylint: disable=invalid-name,too-many-lines
# (The module name follows the addon file naming: WhatsNext.py,
# WhatsNext.gpr.py, WhatsNext.ini.)
"""
What's Next? gramplet: suggests the next research or documentation tasks.

Starting at the Home Person, it works outward through ancestors,
descendants and their partners, and lists the People and Families with
missing or incomplete information, each with a 👣 suggested next step.

This addon registers with the id of the built-in "What's Next" gramplet,
which it replaces (Gramps registers the addons in the user plugins folder
after its built-in plugins, and a later registration with the same id
replaces the earlier one).
"""

# ------------------------------------------------------------------------
#
# Python modules
#
# ------------------------------------------------------------------------
from __future__ import annotations

import ast
import logging
from typing import TYPE_CHECKING, Any, Callable, Iterator

# ------------------------------------------------------------------------
#
# GTK modules
#
# ------------------------------------------------------------------------
from gi.repository import GLib, Gtk

# ------------------------------------------------------------------------
#
# Gramps modules
#
# ------------------------------------------------------------------------
from gramps.gen.config import config as configman
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import DbTxn
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.errors import WindowActiveError
from gramps.gen.lib import Date, EventType, FamilyRelType, Tag
from gramps.gen.plug import Gramplet, PluginRegister
from gramps.gen.plug.menu import BooleanOption, EnumeratedListOption, NumberOption
from gramps.gen.plug.report import utils
from gramps.gen.utils.alive import probably_alive
from gramps.gui.display import display_url
from gramps.gui.editors import EditFamily, EditPerson
from gramps.gui.utils import is_right_click
from gramps.gui.views.tags import OrganizeTagsDialog

if TYPE_CHECKING:
    # For type hints only. gramps.gen.types first appears in Gramps 6.0, so
    # it is not imported at run time (this addon also supports 5.2).
    from gi.repository import Gdk, GObject
    from gramps.gen.lib import Event, Family, Person
    from gramps.gen.plug import PluginData
    from gramps.gen.plug.menu import Option
    from gramps.gen.types import FamilyHandle, PersonHandle, TagHandle
    from gramps.gui.displaystate import DisplayState

# The addon translator checks the core catalog first, then this addon's own
# catalog (locale/<lang>/LC_MESSAGES/addon.mo), so strings Gramps already
# translates keep their core translations and new strings come from the
# consolidated addon catalog.
_ = glocale.get_addon_translator(__file__).sgettext
LOG = logging.getLogger(__name__)

# ======================================================================
# BEGIN HELP BUTTON BLOCK (recipe: HelpDocButton.md)
# The color Help button of MarkdownUtils (README.md in Markdown Dash,
# else help_url), or a plain text Help button that opens help_url when
# MarkdownUtils is missing, too old, or fails to load.
# ======================================================================
try:
    # pylint: disable-next=import-error
    from MarkdownUtils import add_help_button
except Exception:  # pylint: disable=broad-except

    def add_help_button(
        container: Gtk.Box,
        uistate: DisplayState,
        plugin: str | PluginData,
        *,
        size: int = 16,
    ) -> Gtk.Button:
        """
        Pack a plain text "Help" button that opens the help_url of the plugin.

        Stand-in for MarkdownUtils.add_help_button(), used when MarkdownUtils is
        missing, too old, or fails to load.

        :param container: The box the button is packed into.
        :param uistate: The Gramps display state (unused here; kept for the same
            call signature as MarkdownUtils).
        :param plugin: The plugin id, or its registered plugin data.
        :param size: The icon size (unused here; kept for the same call signature).
        :returns: The new button.
        """
        del uistate, size  # same call signature as MarkdownUtils
        if isinstance(plugin, str):
            plugin = PluginRegister.get_instance().get_plugin(plugin)
        button = Gtk.Button(label=_("Help"))
        help_url = getattr(plugin, "help_url", None)
        if help_url:
            button.connect("clicked", lambda _btn: display_url(help_url))
        else:
            button.set_sensitive(False)
        container.pack_start(button, False, False, 0)
        button.show()
        return button


# END HELP BUTTON BLOCK

SHOW_DIAGNOSTIC = False

# How many people or families to examine before handing control back to
# Gramps, so the window stays responsive during a long search.
WORK_PER_STEP = 40

# Pixel size of the borderless Help icon in the button bar (larger than the
# 16 px default, since it has no outline or text taking up the space).
HELP_ICON_SIZE = 22

# The batch "Tag all shown" buttons (Complete, Ignore, Prune) are hidden for
# now: they complicate the interface until a better UI concept is found. The
# right-click menu still tags one object at a time. True brings them back.
SHOW_TAG_BUTTONS = False

# ------------------------------------------------------------------------
#
# Tree data integrity tests
#
# Every test the search can report is listed here with its default state.
# The search asks self.__on("key") before running a test, so each entry
# can later become a Configuration option (and tests borrowed from the
# Verify the Data tool can be added as new entries) without touching the
# search loop.
#
# ------------------------------------------------------------------------
CHECKS = {
    # People
    "first_name": True,  # first name unknown
    "surname": True,  # surname unknown
    "birth_missing": True,  # no Birth event
    # No Death event, for a person Gramps judges is no longer alive (from
    # dates, ages and relatives, with the limits set in Preferences).
    "death_missing": True,
    "birth_event": True,  # date and place of the Birth event
    "death_event": True,  # date and place of the Death event
    # Families
    "marriage_missing": True,  # Married, but no Marriage event
    "marriage_event": True,  # date and place of the Marriage event
    "divorce_event": True,  # date and place of the Divorce event
    "relationship_unknown": True,  # relationship type is Unknown
    # Links between people
    "spouse_missing": True,
    "father_missing": True,
    "mother_missing": True,
    # People with no parent family are reported (the upstream intent,
    # which an earlier beta accidentally dropped). Configurable.
    "parents_missing": True,
    # Details examined for each of the events above
    "date_unknown": True,
    "date_text_only": True,  # text Gramps could not read as a date
    "date_inexact": True,  # before, after, about, range, span, estimated...
    "date_incomplete": True,  # a single date without its day or month
    "place_unknown": True,
}

# The tests offered in the Configuration dialog, in groups. Each group has
# a heading (strings Gramps already translates) and (key, label, tooltip)
# entries; the dialog shows them as check boxes in a second column. Adding
# an entry here is all that is needed to expose another test: the search
# already asks self.__on(key) before running it. Tests borrowed from the
# "Verify the Data" tool can be added the same way.
CHECK_GROUPS = [
    (
        _("People"),
        [
            (
                "first_name",
                _("Unknown first name"),
                _("Report a person without a first name"),
            ),
            ("surname", _("Unknown surname"), _("Report a person without a surname")),
            (
                "birth_missing",
                _("Missing Birth event"),
                _("Report a person without a Birth event"),
            ),
            (
                "birth_event",
                _("Birth date and place"),
                _("Check the date and place of the Birth event"),
            ),
            (
                "death_missing",
                _("Missing Death event"),
                _(
                    "Report a person without a Death event, when Gramps judges"
                    " from the dates of the person and relatives that the person"
                    " is no longer alive"
                ),
            ),
            (
                "death_event",
                _("Death date and place"),
                _("Check the date and place of the Death event"),
            ),
        ],
    ),
    (
        _("Families"),
        [
            (
                "relationship_unknown",
                _("Unknown relationship type"),
                _('Report a family with the relationship type "Unknown"'),
            ),
            (
                "marriage_missing",
                _("Missing Marriage event"),
                _('Report a family of the "Married" type without a Marriage event'),
            ),
            (
                "marriage_event",
                _("Marriage date and place"),
                _("Check the date and place of the Marriage event"),
            ),
            (
                "divorce_event",
                _("Divorce date and place"),
                _("Check the date and place of the Divorce event"),
            ),
        ],
    ),
    (
        _("Relationships"),
        [
            (
                "parents_missing",
                _("Missing parent family"),
                _("List each person who has no parent family"),
            ),
            (
                "spouse_missing",
                _("Missing partner"),
                _("Report a family with only one partner"),
            ),
            (
                "father_missing",
                _("Missing father"),
                _("Report a person whose parent family has no father"),
            ),
            (
                "mother_missing",
                _("Missing mother"),
                _("Report a person whose parent family has no mother"),
            ),
        ],
    ),
    (
        _("Events"),
        [
            ("date_unknown", _("Unknown date"), _("Report an event without a date")),
            (
                "date_text_only",
                _("Date is text only"),
                _("Report a date that Gramps could not read as a date"),
            ),
            (
                "date_inexact",
                _("Inexact date"),
                _(
                    'Report a range, a span, or a date with "before", "after",'
                    ' "about", "estimated" or "calculated"'
                ),
            ),
            (
                "date_incomplete",
                _("Incomplete date"),
                _("Report a single date without its day or month"),
            ),
            ("place_unknown", _("Unknown place"), _("Report an event without a place")),
        ],
    ),
]
# The same tests as a flat list of (key, label), in display order, and
# their tooltips by key.
CHECK_OPTIONS = [
    (key, label) for _group, items in CHECK_GROUPS for key, label, _help in items
]
CHECK_HELP = {
    key: help_text for _group, items in CHECK_GROUPS for key, _label, help_text in items
}

# The 👣 suggested next step for each kind of problem, shown on its own line
# under the reported Person or Family when "Show suggested Next Steps" is on.
# Each step is shown once per line, however many problems of its kind the
# Person or Family has.
NEXT_STEPS = {
    "name": _("Enter the missing name in the Edit Person dialog."),
    "add_event": _("Add via the Events tab of the Edit Person dialog."),
    "person_event": _(
        "Open the event on the Events tab of the Edit Person dialog,"
        " and complete its date and place."
    ),
    "family_event": _(
        "Open the event on the Events tab of the Edit Family dialog,"
        " and complete its date and place."
    ),
    "marriage": _("Add a Marriage event on the Events tab of the Edit Family dialog."),
    "relationship": _('Choose the relationship "Type" in the Edit Family dialog.'),
    "spouse": _("Add the missing partner in the Edit Family dialog."),
    "father": _("Add the father in the Edit Family dialog of the parent family."),
    "mother": _("Add the mother in the Edit Family dialog of the parent family."),
    "parents": _(
        'In the Relationships view, choose "Add New Parents..." or'
        ' "Add Existing Parents..." from the Edit menu.'
    ),
}


# ------------------------------------------------------------------------
#
# Persistent settings
#
# WhatsNext.ini sits in this addon folder, next to this module. Its [meta]
# block is written as ";;" comment lines at the top (through Gramps'
# ConfigManager.save(comments=...)), not as a section, so it always stays
# first (Gramps writes sections in alphabetical order) and Gramps ignores
# it when loading. The same pattern is used by PR2215_NamedDashboards.
#
#   ;; Gramps key file
#   ;; Automatically created at 2026/11/26 16:00:00
#
#   ;; [meta]
#   ;; plugin_id="What's Next"
#   ;; schema_version='1'
#   [display]
#   ...
#
# The chosen Complete, Ignore and Prune tags are kept for each Family Tree
# (tags belong to a tree), in [trees] tags, keyed by the tree id (the name
# of its folder in the Family Trees folder, from db.get_dbid()).
#
# ------------------------------------------------------------------------
PLUGIN_ID = "What's Next"  # same id as the built-in, which it replaces
META_START = "[meta]"
#: Settings file format. Raise it when the format changes in a way older
#: versions of the addon cannot read, and add a step to CONFIG_MIGRATIONS.
CONFIG_SCHEMA_VERSION = 1
#: {from_version: function(config)} upgrading loaded settings by one
#: version. Version 1 is the first; a file without a meta block is not
#: loaded at all.
CONFIG_MIGRATIONS: dict[int, Callable[[Any], None]] = {}

# When no tag is chosen in the Configuration, these are created on first use
# and placed at the top of the tag list. Color is a hex string.
# Three tags, each applied to a Person or a Family. All three hide the
# object from the list; they differ in how they affect the search and in
# how long they are meant to last:
#   Complete - finished; information will never be found. Hidden, but the
#              search still travels through it to reach relatives. Permanent.
#   Ignore   - gaps acknowledged for now. Hidden, still travelled through.
#              Delete the tag to re-expose and try again. Temporary.
#   Prune    - a dead end. Hidden, and the search does NOT travel through it,
#              so nothing reached only through it is examined. Shapes search
#              direction. Delete the tag to bring that branch back.
# When no tag is chosen in the Configuration, the matching tag below is
# created on first use at the top of the tag list, in the given color.
DEFAULT_COMPLETE_TAG = _("Completed")
DEFAULT_COMPLETE_COLOR = "#808080"  # 50% grey
DEFAULT_IGNORE_TAG = _("Ignored")
DEFAULT_IGNORE_COLOR = "#BFBFBF"  # 25% pale grey
DEFAULT_PRUNE_TAG = _("Pruned")
DEFAULT_PRUNE_COLOR = "#B8860B"  # dark amber
CONFIG = configman.register_manager("WhatsNext", __file__, use_plugins_path=False)
# Display preferences (not tree data integrity tests).
CONFIG.register("display.show_next_steps", True)
for _key, _label in CHECK_OPTIONS:
    CONFIG.register(f"checks.{_key}", CHECKS[_key])
# {tree id: {"tree": tree name, "complete": tag, "ignore": tag,
# "prune": tag}}. The tree name is only there to make the file readable.
CONFIG.register("trees.tags", {})


def read_meta_block(path: str) -> dict[str, Any]:
    """
    Read the ";; [meta]" comment block at the top of a settings file.

    :param path: The full path of the settings file.
    :returns: The values of the block, with ``schema_version`` as an int, or
        an empty dict when the file is missing or has no meta block.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return {}
    meta = {}
    inside = False
    for line in lines:
        if not line.startswith(";;"):
            if inside:
                break
            continue
        text = line[2:].strip()
        if text == META_START:
            inside = True
        elif inside and "=" in text:
            key, value = text.split("=", 1)
            try:
                meta[key.strip()] = ast.literal_eval(value.strip())
            except (ValueError, SyntaxError):
                meta[key.strip()] = value.strip()
    if not inside:
        return {}
    try:
        meta["schema_version"] = int(meta.get("schema_version", 0))
    except (TypeError, ValueError):
        meta["schema_version"] = 0
    return meta


def meta_lines(version: int = CONFIG_SCHEMA_VERSION) -> list[str]:
    """
    Build the meta block as comment lines for ConfigManager.save().

    :param version: The settings schema version to record.
    :returns: The comment lines, without their ";;" prefix.
    """
    return [
        META_START,
        f"plugin_id={PLUGIN_ID!r}",
        f"schema_version='{version}'",
    ]


def load_config() -> bool:
    """
    Load WhatsNext.ini if its meta block says it is ours.

    A file without a meta block (or with another plugin_id) is ignored, and
    fresh settings replace it at the first save. Older files are upgraded one
    version at a time through CONFIG_MIGRATIONS.

    :returns: False if the file was written by a newer version of this addon:
        it is used, but never saved over. True otherwise.
    """
    meta = read_meta_block(CONFIG.filename)
    if not meta:
        return True  # missing file, or no meta block: start fresh
    if meta.get("plugin_id") != PLUGIN_ID:
        LOG.warning(
            "What's Next: %s belongs to '%s'; using fresh settings",
            CONFIG.filename,
            meta.get("plugin_id"),
        )
        return True
    version = meta["schema_version"]
    CONFIG.load()
    if version > CONFIG_SCHEMA_VERSION:
        LOG.warning(
            "What's Next: %s was written by a newer version of this addon "
            "(settings schema %d; this version knows %d). It is used, but "
            "changes are not saved.",
            CONFIG.filename,
            version,
            CONFIG_SCHEMA_VERSION,
        )
        return False
    while version < CONFIG_SCHEMA_VERSION:
        migrate = CONFIG_MIGRATIONS.get(version)
        if migrate is not None:
            migrate(CONFIG)
        version += 1
    return True


CONFIG_WRITABLE = load_config()


def save_config() -> None:
    """Save WhatsNext.ini with its meta block, unless it is from a newer version."""
    if CONFIG_WRITABLE:
        CONFIG.save(comments=meta_lines())


def can_import_without_tree(uistate: DisplayState) -> bool:
    """
    Tell whether "Import..." in the "Family Trees" menu works with no tree.

    The Import With No Tree change (in Gramps core or as an addon) enables
    the Import action with no tree loaded; stock Gramps disables it until a
    tree is loaded.

    :param uistate: The Gramps display state.
    :returns: True when the Import action is enabled.
    """
    try:
        viewmanager = uistate.viewmanager
        action = viewmanager.uimanager.get_action(viewmanager.actiongroup, "Import")
        return bool(action is not None and action.get_enabled())
    except AttributeError:
        return False


def no_tree_message(show_next_steps: bool, import_ready: bool = False) -> str:
    """
    Build the "no tree loaded" guidance.

    :param show_next_steps: Include the 👣 Next Steps.
    :param import_ready: Import works with no tree loaded, so the step to
        create an empty tree first is left out.
    :returns: The guidance text.
    """
    message = _("\n ⛔ A local Genealogical Tree database has not yet been loaded.\n\n")
    if show_next_steps:
        message += _(" 👣 Next Steps:\n")
        message += _('  •  From the "Family Trees" menu,')
        message += _(' use the "Manage Family Trees..." option to')
        message += _(" create a New (or to select an existing) Tree database.\n")
        message += _('  •  Click the "Load Family Tree" button to begin')
        message += _(" working with the selected genealogical tree.\n\n")
        if import_ready:
            message += _(
                "To use a backup from Gramps, or a GEDCOM file from another"
                ' genealogical tool, choose "Import..." in the "Family Trees"'
                " menu.\n\n"
            )
        else:
            message += _(
                "To use a backup from Gramps, or a GEDCOM file from another"
                " genealogical tool, first create and load a new, empty tree."
                ' Then choose "Import..." in the "Family Trees" menu.\n\n'
            )
    return message


# Signals that can change what the search reports.
REFRESH_SIGNALS = (
    "home-person-changed",
    "person-add",
    "person-delete",
    "person-update",
    "person-rebuild",
    "family-add",
    "family-delete",
    "family-update",
    "family-rebuild",
    "event-add",
    "event-delete",
    "event-update",
    "event-rebuild",
    "tag-add",
    "tag-update",
    "tag-delete",
    "tag-rebuild",
)

# ------------------------------------------------------------------------
#
# The Gramplet
#
# ------------------------------------------------------------------------


# ------------------------------------------------------------
#
# WhatNextGramplet
#
# ------------------------------------------------------------
# Gramplets set up their state in init() and on_load(), which Gramps calls
# from Gramplet.__init__, so attributes are defined outside __init__.
# pylint: disable-next=too-many-instance-attributes,too-many-public-methods
class WhatNextGramplet(Gramplet):
    """
    The What's Next? gramplet.

    It lists the People and Families with missing or incomplete information,
    starting at the Home Person, with a 👣 suggested next step for each.
    """

    # pylint: disable=attribute-defined-outside-init

    # Tag slots saved by the built-in 1.0.0 gramplet, waiting for a tree.
    __legacy_tags: tuple[str, str] | None

    def init(self) -> None:
        """Show the no-tree guidance until a tree is loaded."""
        self.set_tooltip(
            _(
                'Use the "Configure" in the "View" menu to'
                " change the Gramplet options."
            )
        )
        # init() runs before on_load(), so read the saved value directly.
        self.set_text(no_tree_message(CONFIG.get("display.show_next_steps")))
        # The Import action may be switched on after this gramplet is built,
        # so check again once Gramps has finished starting up.
        GLib.idle_add(self.cb_refresh_no_tree)

    def cb_refresh_no_tree(self) -> bool:
        """
        Show the no-tree guidance again, now that Import can be checked.

        :returns: False, so the idle callback runs once.
        """
        if not self.dbstate.db.is_open():
            self.set_text(
                no_tree_message(
                    CONFIG.get("display.show_next_steps"),
                    can_import_without_tree(self.uistate),
                )
            )
        return False  # run once

    def post_init(self) -> None:
        """
        Take over the button handling of the text view, and add the button bar.

        The gramplet pane connects its own button-press handler, which opens the
        editor on a right-click over a Person or Family link. It is replaced by
        cb_button_press, which offers a small menu (Review, Tag as Complete, Tag
        to Ignore, Tag to Prune) and hands every other click back to the pane.
        """
        try:
            self.gui.textview.disconnect_by_func(self.gui.on_button_press)
            self.gui.textview.connect("button-press-event", self.cb_button_press)
        except (TypeError, AttributeError):
            # If the core handler cannot be found, leave the pane's behavior
            # in place rather than break clicking.
            pass
        # Add "Organize Tags" to the text view's own context menu (which
        # still carries Copy, Select All and so on).
        self.gui.textview.connect("populate-popup", self.cb_populate_popup)
        self.__build_button_bar()

    def cb_populate_popup(self, _view: Gtk.TextView, menu: Gtk.Widget) -> None:
        """
        Append an Organize Tags item to the default menu of the text view.

        :param _view: The text view (unused).
        :param menu: The menu about to be shown.
        """
        if not isinstance(menu, Gtk.Menu):
            return
        separator = Gtk.SeparatorMenuItem()
        separator.show()
        menu.append(separator)
        item = Gtk.MenuItem.new_with_label(_("Organize Tags"))
        item.connect("activate", self.cb_organize_tags)
        item.show()
        menu.append(item)

    def __build_button_bar(self) -> None:
        """
        Add a row of buttons below the text of the gramplet.

        The row holds a Help button on the far left, then (only when
        SHOW_TAG_BUTTONS is True) batch "Tag all shown" buttons for Complete,
        Ignore and Prune. It is appended to the box that holds the scrolling text
        area, so it stays fixed below the text.
        """
        try:
            container = self.gui.get_container_widget()
            parent = container.get_parent()
            if parent is None or not hasattr(parent, "pack_start"):
                return
            button_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            button_bar.set_border_width(2)
            # Help button on the far left.
            help_button = add_help_button(
                button_bar, self.uistate, PLUGIN_ID, size=HELP_ICON_SIZE
            )
            help_image = help_button.get_image() if help_button else None
            if help_image is not None:
                # The color icon (and its tooltip) is enough: no text and no
                # outline, so the larger icon fits in the same space. The
                # plain fallback button has no icon, so it keeps both.
                help_button.set_property("label", None)
                help_button.set_relief(Gtk.ReliefStyle.NONE)
                help_button.set_focus_on_click(False)
                if isinstance(help_image, Gtk.Image):
                    help_image.set_pixel_size(HELP_ICON_SIZE)
            self.__help_button = help_button
            if SHOW_TAG_BUTTONS:
                button_bar.pack_start(
                    self.__batch_button(
                        _("Complete"),
                        _("Tag listed People and Families as Completed"),
                        self.cb_batch_complete,
                    ),
                    False,
                    False,
                    0,
                )
                button_bar.pack_start(
                    self.__batch_button(
                        _("Ignore"),
                        _("Tag to Ignore People and Families"),
                        self.cb_batch_ignore,
                    ),
                    False,
                    False,
                    0,
                )
                button_bar.pack_start(
                    self.__batch_button(
                        _("Prune"),
                        _(
                            "Tag to Prune (exclude) listed People and Families from testing"
                        ),
                        self.cb_batch_prune,
                    ),
                    False,
                    False,
                    0,
                )
            parent.pack_start(button_bar, False, False, 0)
            # Show the buttons now, but let the bar's own visibility follow
            # the text area: collapsing a Dashboard gramplet hides only its
            # scrolled text window, so without this the bar stays behind.
            for child in button_bar.get_children():
                child.show_all()
            button_bar.set_no_show_all(True)
            self.__button_bar = button_bar
            container.connect("notify::visible", self.cb_text_visible)
            # Moving into (or back out of) a detached window re-parents the
            # whole gramplet frame, which this signal reports.
            button_bar.connect("hierarchy-changed", self.cb_bar_moved)
            self.cb_text_visible(container, None)
            self.cb_bar_moved(button_bar, None)
        except Exception:  # pylint: disable=broad-except
            # The gramplet still works without the button bar; the right-click
            # menu offers the same tagging per object.
            pass

    def cb_text_visible(
        self, widget: Gtk.Widget, _pspec: GObject.ParamSpec | None
    ) -> None:
        """
        Show the button bar only while the text area is shown (expanded).

        :param widget: The scrolled text area of the gramplet.
        :param _pspec: The changed property (unused).
        """
        self.__button_bar.set_visible(widget.get_visible())

    def cb_bar_moved(self, _bar: Gtk.Widget, _old_toplevel: Gtk.Widget | None) -> None:
        """
        Hide the Help button while the gramplet is undocked.

        The detached window has its own Help button; the button shows again when
        the gramplet is docked.

        :param _bar: The button bar (unused).
        :param _old_toplevel: The previous top-level window (unused).
        """
        if self.__help_button is not None:
            detached = getattr(self.gui, "gstate", "") == "detached"
            self.__help_button.set_visible(not detached)

    def __batch_button(
        self, label: str, tooltip: str, callback: Callable[[Gtk.Button], None]
    ) -> Gtk.Button:
        """
        Make a button with the themed tag icon (menu size) and a text label.

        :param label: The text of the button.
        :param tooltip: The tooltip of the button.
        :param callback: Called when the button is clicked.
        :returns: The new button.
        """
        button = Gtk.Button()
        button.set_image(
            Gtk.Image.new_from_icon_name("gramps-tag-new", Gtk.IconSize.MENU)
        )
        button.set_always_show_image(True)  # else some themes hide the icon
        button.set_label(label)
        button.set_tooltip_text(tooltip)
        button.connect("clicked", callback)
        return button

    def build_options(self) -> None:
        """Build the configuration options."""
        self.opts: list[Any] = []

        # Minimum number of lines we want to see. Further lines with the same
        # distance to the main person will be added on top of this.
        name = _("Search Quota ")
        opt: Any = NumberOption(name, self.__todos_wanted, 1, 300)
        opt.set_help(
            _(
                "The least number of lines to show. The search stops once"
                " this many problems are found"
            )
        )
        self.opts.append(opt)

        # How many generations of descendants to process before we go up to the
        # next level of ancestors.
        name = _("Depth per loop")
        opt = NumberOption(name, self.__downs_per_up, 1, 15)
        opt.set_help(
            _(
                "How many generations of descendants to check before going up"
                " one more generation of ancestors"
            )
        )
        self.opts.append(opt)

        # After an ancestor was processed, how many extra rounds to delay until
        # the descendants of this ancestor are processed.
        name = _("Pause search expansion")
        opt = NumberOption(name, self.__ancestor_delay, 1, 10)
        opt.set_help(
            _(
                "How many extra rounds to wait after checking an ancestor"
                " before checking the descendants of that ancestor"
            )
        )
        self.opts.append(opt)

        # Complete tag: the object is finished (its gaps will never be
        # filled). Hidden from the list, but still travelled through.
        opt = EnumeratedListOption(_("Complete tag"), self.__complete_tag)
        opt.set_help(_("Finished. Hide the object, and keep searching through it"))
        self.opts.append(opt)

        # Ignore tag: gaps acknowledged for now. Hidden from the list, still
        # travelled through. Delete the tag to re-expose and try again.
        opt = EnumeratedListOption(_("Ignore tag"), self.__ignore_tag)
        opt.set_help(
            _("Set aside for now. Hide the object, and keep searching through it")
        )
        self.opts.append(opt)

        # Prune tag: a dead end. Hidden, and the search does not travel
        # through it. Delete the tag to bring that branch back.
        opt = EnumeratedListOption(_("Prune tag"), self.__prune_tag)
        opt.set_help(_("Dead end. Hide the object, and stop searching through it"))
        self.opts.append(opt)

        self.opts[3].add_item("", "")
        self.opts[4].add_item("", "")
        self.opts[5].add_item("", "")
        if self.dbstate.db.is_open():
            for tag_handle in self.dbstate.db.get_tag_handles(sort_handles=True):
                tag = self.dbstate.db.get_tag_from_handle(tag_handle)
                tag_name = tag.get_name()
                self.opts[3].add_item(tag_name, tag_name)
                self.opts[4].add_item(tag_name, tag_name)
                self.opts[5].add_item(tag_name, tag_name)

        # Display preferences. self.__display_first is the index of the first
        # of these, so save_options can read them back by offset.
        self.__display_first = len(self.opts)
        opt = BooleanOption(_("Show suggested 👣 Next Steps"), self.__show_next_steps)
        opt.set_help(
            _(
                "Show the guidance steps and the 👣 suggestions. Turn off for a shorter list"
            )
        )
        self.opts.append(opt)

        # Tree data integrity test switches. self.__check_first is the index
        # of the first of these in self.opts, so save_options can read them
        # back whatever comes before them.
        self.__check_first = len(self.opts)
        for key, label in CHECK_OPTIONS:
            opt = BooleanOption(label, self.__checks[key])
            opt.set_help(CHECK_HELP.get(key, ""))
            self.opts.append(opt)

        list(map(self.add_option, self.opts))

        # The Configure dialog puts a label in front of every option and
        # gives it no tooltip. Once an option is placed in the dialog, give
        # its label the option's tooltip.
        for opt in self.opts[: self.__display_first]:
            widget = self.option_dict[opt.get_label()][0]
            widget.connect("parent-set", self.cb_option_parent_set, opt)
        # The check boxes (which carry their own label and tooltip) are moved
        # into columns to the right, under headings, once the last option is
        # placed in the dialog.
        self.__arranged = False
        last = self.option_dict[self.opts[-1].get_label()][0]
        last.connect("parent-set", self.cb_arrange_check_boxes)

    def cb_arrange_check_boxes(
        self, widget: Gtk.Widget, _old_parent: Gtk.Widget | None
    ) -> None:
        """
        Move the check boxes of the Configure dialog into headed columns.

        The check boxes are moved out of the label/widget rows of the dialog into
        columns to the right, under headings::

            Search Quota    [10 ]         People          Relationships
            Depth per loop  [1  ]         [x] ...         [x] ...
            ...                           ...             ...
            Prune tag       [    ]        Families        Events
                    [x] Show suggested    [x] ...         [x] ...
                        👣 Next Steps

        Gramps (make_gui_options in grampletpane.py, the same in 5.2 to 6.1)
        attaches every option in order, so the last check box being attached
        means all options are in place.

        :param widget: The last check box, just attached.
        :param _old_parent: Its previous parent (unused).
        """
        grid = widget.get_parent()
        if self.__arranged or not isinstance(grid, Gtk.Grid):
            return
        self.__arranged = True  # re-attaching sets the parent again
        # Rearrange once GTK has finished attaching this check box.
        GLib.idle_add(self.__arrange_check_boxes, grid)

    # pylint: disable-next=too-many-locals
    def __arrange_check_boxes(self, grid: Gtk.Grid) -> bool:
        """
        Do the work of cb_arrange_check_boxes.

        :param grid: The grid of options built by Gramps.
        :returns: False, so the idle callback runs once.
        """

        def take(opt: Option) -> Gtk.Widget:
            """
            Remove a check box and the label in front of it from the grid.

            :param opt: The option shown by the check box.
            :returns: The check box.
            """
            box = self.option_dict[opt.get_label()][0]
            row = grid.child_get_property(box, "top-attach")
            label = grid.get_child_at(0, row)
            if label is not None and label is not box:
                grid.remove(label)
            grid.remove(box)
            return box

        def heading(text: str) -> Gtk.Label:
            """
            Make a bold heading for a group of check boxes.

            :param text: The heading text.
            :returns: The new label.
            """
            label = Gtk.Label()
            label.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
            label.set_halign(Gtk.Align.START)
            label.set_margin_top(6)
            return label

        display = [
            take(opt) for opt in self.opts[self.__display_first : self.__check_first]
        ]
        checks = iter(take(opt) for opt in self.opts[self.__check_first :])

        # The display check box goes at the bottom of the labelled options,
        # in the widget column, without a label of its own.
        row = self.__display_first
        for box in display:
            grid.attach(box, 1, row, 1, 1)
            row += 1

        # Test columns: People and Families, then the other groups.
        columns: dict[int, list[tuple[str, list[Gtk.Widget]]]] = {2: [], 3: []}
        for index, (group, items) in enumerate(CHECK_GROUPS):
            boxes = [next(checks) for _item in items]
            columns[2 if index < 2 else 3].append((group, boxes))

        # The grid of labelled options and the check box columns sit side
        # by side in a new row box, each at its own natural height. The row
        # box takes the place of the grid in the dialog.
        holder = grid.get_parent()
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        if isinstance(holder, Gtk.Box):
            position = holder.child_get_property(grid, "position")
            holder.remove(grid)
            holder.pack_start(row_box, False, False, 0)
            holder.reorder_child(row_box, position)
        grid.set_valign(Gtk.Align.START)
        row_box.pack_start(grid, False, False, 0)
        for column in sorted(columns):
            stack = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            stack.set_margin_start(24)
            stack.set_valign(Gtk.Align.START)
            for group, boxes in columns[column]:
                stack.pack_start(heading(group), False, False, 0)
                for box in boxes:
                    box.set_margin_start(12)
                    stack.pack_start(box, False, False, 0)
            row_box.pack_start(stack, False, False, 0)
        row_box.show_all()
        return False  # run once

    def cb_option_parent_set(
        self, widget: Gtk.Widget, _old_parent: Gtk.Widget | None, option: Option
    ) -> None:
        """
        Give the dialog label to the left of an option the tooltip of the option.

        :param widget: The widget of the option, just placed in the dialog.
        :param _old_parent: Its previous parent (unused).
        :param option: The option.
        """
        grid = widget.get_parent()
        if not isinstance(grid, Gtk.Grid):
            return
        row = grid.child_get_property(widget, "top-attach")
        label = grid.get_child_at(0, row)
        if label is None or label is widget:
            return
        if option.get_help():
            label.set_tooltip_text(option.get_help())

    def save_options(self) -> None:
        """Save the gramplet configuration data."""
        self.__todos_wanted = int(self.opts[0].get_value())
        self.__downs_per_up = int(self.opts[1].get_value())
        self.__ancestor_delay = int(self.opts[2].get_value())
        self.__complete_tag = self.opts[3].get_value()
        self.__ignore_tag = self.opts[4].get_value()
        self.__prune_tag = self.opts[5].get_value()

        show_next_steps = bool(self.opts[self.__display_first].get_value())
        self.__show_next_steps = show_next_steps
        CONFIG.set("display.show_next_steps", show_next_steps)
        for offset, (key, _label) in enumerate(CHECK_OPTIONS):
            value = bool(self.opts[self.__check_first + offset].get_value())
            self.__checks[key] = value
            CONFIG.set(f"checks.{key}", value)
        # Also saves the settings file.
        self.__persist_tags()

    def save_update_options(self, obj: Gtk.Widget) -> None:
        """
        Save the options of the gramplet and refresh the list.

        :param obj: The Save button (unused).
        """
        self.save_options()
        self.__sync_gui_data()
        self.update()

    def __sync_gui_data(self) -> None:
        """
        Store the numeric options in the gramplet bar.

        The tags of each tree and the on-or-off options are kept in WhatsNext.ini
        instead (see __persist_tags).
        """
        self.gui.data = [
            self.__todos_wanted,
            self.__downs_per_up,
            self.__ancestor_delay,
        ]

    def __tree_id(self) -> str:
        """
        Get the id of the open Family Tree.

        :returns: The tree id (the name of its folder), or "" when no tree is open.
        """
        db = self.dbstate.db
        try:
            if db is not None and db.is_open():
                return db.get_dbid() or ""
        except (AttributeError, NotImplementedError):
            pass
        return ""

    def __tree_name(self) -> str:
        """
        Get the name of the open Family Tree, for readability of the .ini.

        :returns: The tree name, or "".
        """
        try:
            return self.dbstate.db.get_dbname() or ""
        except (AttributeError, NotImplementedError, OSError):
            return ""

    def __load_tree_tags(self) -> None:
        """
        Read the three chosen tags of the open Family Tree.

        A tree with no saved choice starts with none (the default tags are
        created on first use), except that the tag slots saved with this gramplet
        by the built-in 1.0.0 gramplet are carried over once, to the first tree
        that is opened.
        """
        entry = CONFIG.get("trees.tags").get(self.__tree_id(), {})
        self.__complete_tag = entry.get("complete", "")
        self.__ignore_tag = entry.get("ignore", "")
        self.__prune_tag = entry.get("prune", "")
        if not entry and self.__legacy_tags and self.__tree_id():
            self.__complete_tag, self.__prune_tag = self.__legacy_tags
            self.__legacy_tags = None
            self.__persist_tags()

    def __persist_tags(self) -> None:
        """Save the chosen tags of the open tree, and the settings file."""
        tree_id = self.__tree_id()
        if tree_id:
            tags = dict(CONFIG.get("trees.tags"))
            tags[tree_id] = {
                "tree": self.__tree_name(),
                "complete": self.__complete_tag or "",
                "ignore": self.__ignore_tag or "",
                "prune": self.__prune_tag or "",
            }
            CONFIG.set("trees.tags", tags)
        save_config()

    def on_load(self) -> None:
        """Load the stored configuration data."""
        # Which tree data integrity tests run. Start from the defaults,
        # then apply the choices saved in WhatsNext.ini for the tests that
        # are exposed in the Configuration dialog.
        self.__checks = dict(CHECKS)
        for key, _label in CHECK_OPTIONS:
            self.__checks[key] = CONFIG.get(f"checks.{key}")

        # Display preference: whether 👣 Next Steps suggestions are shown.
        self.__show_next_steps = CONFIG.get("display.show_next_steps")

        # The three tags are kept for each tree in WhatsNext.ini, so a tag
        # created on first use is saved and appears in the options.
        self.__legacy_tags = None

        # The numeric options stay in the gramplet bar, as in the built-in
        # gramplet.
        if len(self.gui.data) >= 3:
            self.__todos_wanted = int(self.gui.data[0])
            self.__downs_per_up = int(self.gui.data[1])
            self.__ancestor_delay = int(self.gui.data[2])
            # The built-in 1.0.0 gramplet kept six slots: slots 3-5 were the
            # person-complete, family-complete and ignore tags (that ignore
            # tag blocked the search, so it is now "prune"). They are given
            # to the first tree opened that has no saved choice.
            if len(self.gui.data) == 6 and (self.gui.data[3] or self.gui.data[5]):
                self.__legacy_tags = (self.gui.data[3] or "", self.gui.data[5] or "")
        else:
            self.__todos_wanted = 10
            self.__downs_per_up = 1
            self.__ancestor_delay = 5
        # The tags of the open tree (none yet if no tree is open; db_changed
        # loads them again whenever a tree is opened).
        self.__load_tree_tags()

    def db_changed(self) -> None:
        """
        Connect the signals of a newly opened tree, and load its tags.

        Each signal is connected once. A burst of signals (one save can send
        several) leads to a single search, because main() runs in the background
        and a newer request replaces a pending one.
        """
        # Each signal is connected once. A burst of signals (one save can
        # send several) now leads to a single search, because main() runs
        # in the background and a newer request replaces a pending one.
        for signal in REFRESH_SIGNALS:
            self.connect(self.dbstate.db, signal, self.update)
        # The chosen tags belong to the tree that was just opened.
        self.__load_tree_tags()

    def _no_db(self) -> None:
        """Show the no-tree guidance when the tree is closed."""
        super()._no_db()
        self.__clear_links()
        self.set_text(
            no_tree_message(
                self.__show_next_steps, can_import_without_tree(self.uistate)
            )
        )
        # Gramps may switch the Import action off after this runs.
        GLib.idle_add(self.cb_refresh_no_tree)

    # ------------------------------------------------------------------
    # Right-click menu and tagging
    # ------------------------------------------------------------------
    def cb_button_press(self, view: Gtk.TextView, event: Gdk.EventButton) -> bool:
        """
        Offer a tag menu on a right-click over a reported object.

        Every other click is handled by the gramplet pane as usual.

        :param view: The text view.
        :param event: The button press.
        :returns: True when the click was handled here.
        """
        if is_right_click(event):
            hit = self.__link_at(view, event)
            if hit is not None:
                link_type, handle = hit
                if link_type in ("Person", "Family"):
                    self.__popup_tag_menu(link_type, handle, event)
                    return True  # handled
        # Everything else (left-click to select, double-click to edit, other
        # link types, and a right-click away from a name, which keeps the
        # text view's own Copy and Select All menu) is the pane's job.
        return self.gui.on_button_press(view, event)

    def __link_at(
        self, view: Gtk.TextView, event: Gdk.EventButton
    ) -> tuple[str, Any] | None:
        """
        Find the link under the pointer.

        :param view: The text view.
        :param event: The button press.
        :returns: (link_type, handle) for the link, or None.
        """
        buffer_location = view.window_to_buffer_coords(
            Gtk.TextWindowType.TEXT, int(event.x), int(event.y)
        )
        text_iter = view.get_iter_at_location(*buffer_location)
        if isinstance(text_iter, tuple):
            text_iter = text_iter[1]
        # The pane keeps its links in _tags; Gramps has no public accessor.
        # pylint: disable-next=protected-access
        for tag, link_type, handle, _tooltip in self.gui._tags:
            if text_iter.has_tag(tag):
                return (link_type, handle)
        return None

    def __popup_tag_menu(
        self,
        link_type: str,
        handle: PersonHandle | FamilyHandle,
        event: Gdk.EventButton,
    ) -> None:
        """
        Build and show the Review / Tag menu for one object.

        :param link_type: "Person" or "Family".
        :param handle: The handle of the object.
        :param event: The button press that opens the menu.
        """
        menu = Gtk.Menu()
        menu.set_reserve_toggle_size(False)

        review = Gtk.MenuItem.new_with_mnemonic(_("_Review (open editor)"))
        review.connect("activate", self.cb_review, link_type, handle)
        review.show()
        menu.append(review)

        separator = Gtk.SeparatorMenuItem()
        separator.show()
        menu.append(separator)

        for label, kind in (
            (_("Tag as Complete"), "complete"),
            (_("Tag to Ignore"), "ignore"),
            (_("Tag to Prune"), "prune"),
        ):
            item = self.__tag_menu_item(label, kind, link_type, handle)
            menu.append(item)

        sep = Gtk.SeparatorMenuItem()
        sep.show()
        menu.append(sep)
        organize = Gtk.MenuItem.new_with_label(_("Organize Tags"))
        organize.connect("activate", self.cb_organize_tags)
        organize.show()
        menu.append(organize)

        # Keep a reference so the menu is not garbage-collected before it is
        # shown. Gramps 5.2 through 6.1 are GTK 3.
        self.__tag_menu = menu  # pylint: disable=unused-private-member
        menu.popup_at_pointer(event)

    def cb_organize_tags(self, _item: Gtk.MenuItem) -> None:
        """
        Open the Gramps Organize Tags dialog.

        :param _item: The menu item (unused).
        """
        OrganizeTagsDialog(self.dbstate.db, self.uistate, [])

    def __tag_menu_item(
        self, label: str, kind: str, link_type: str, handle: PersonHandle | FamilyHandle
    ) -> Gtk.MenuItem:
        """
        Make a menu item carrying the themed tag icon at menu (16x16) size.

        :param label: The text of the item.
        :param kind: "complete", "ignore" or "prune".
        :param link_type: "Person" or "Family".
        :param handle: The handle of the object to tag.
        :returns: The new menu item.
        """
        item = Gtk.MenuItem()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        image = Gtk.Image.new_from_icon_name("gramps-tag-new", Gtk.IconSize.MENU)
        box.pack_start(image, False, False, 0)
        box.pack_start(Gtk.Label(label=label, xalign=0.0), True, True, 0)
        item.add(box)
        item.connect("activate", self.cb_tag_one, kind, link_type, handle)
        item.show_all()
        return item

    def cb_review(
        self, _item: Gtk.MenuItem, link_type: str, handle: PersonHandle | FamilyHandle
    ) -> None:
        """
        Open the editor for the object, as a double-click would.

        :param _item: The menu item (unused).
        :param link_type: "Person" or "Family".
        :param handle: The handle of the object.
        """
        db = self.dbstate.db
        try:
            if link_type == "Person" and db.has_person_handle(handle):
                person = db.get_person_from_handle(handle)
                EditPerson(self.dbstate, self.uistate, [], person)
            elif link_type == "Family" and db.has_family_handle(handle):
                family = db.get_family_from_handle(handle)
                EditFamily(self.dbstate, self.uistate, [], family)
        except WindowActiveError:
            pass

    def __effective_tag(self, kind: str) -> str:
        """
        Get the tag name chosen for a kind.

        Each kind needs its own tag. If two kinds are set to the same tag, the
        later one (in the order complete, ignore, prune) counts as not chosen, so
        Prune can never act as Complete. Both the tag buttons and the search use
        this one rule.

        :param kind: "complete", "ignore" or "prune".
        :returns: The tag name, or "" when none is chosen.
        """
        chosen = {
            "complete": self.__complete_tag,
            "ignore": self.__ignore_tag,
            "prune": self.__prune_tag,
        }
        order = ("complete", "ignore", "prune")
        name = chosen[kind] or ""
        for earlier in order[: order.index(kind)]:
            if chosen[earlier] and chosen[earlier] == name:
                return ""
        return name

    def __tag_for_kind(self, kind: str) -> tuple[str, str, bool]:
        """
        Get the tag to apply for a kind.

        :param kind: "complete", "ignore" or "prune".
        :returns: (tag_name, color, is_default). When no tag is chosen for the
            kind, the default name and color are returned, flagged so the caller
            can remember the new tag as the chosen one.
        """
        defaults = {
            "complete": (DEFAULT_COMPLETE_TAG, DEFAULT_COMPLETE_COLOR),
            "ignore": (DEFAULT_IGNORE_TAG, DEFAULT_IGNORE_COLOR),
            "prune": (DEFAULT_PRUNE_TAG, DEFAULT_PRUNE_COLOR),
        }
        chosen = self.__effective_tag(kind)
        name, color = defaults[kind]
        return (chosen or name, color, not chosen)

    def __remember_tag(self, kind: str, tag_name: str) -> None:
        """
        Record an automatically created tag as the chosen tag for its kind.

        :param kind: "complete", "ignore" or "prune".
        :param tag_name: The name of the tag.
        """
        if kind == "complete":
            self.__complete_tag = tag_name
        elif kind == "ignore":
            self.__ignore_tag = tag_name
        else:
            self.__prune_tag = tag_name
        self.__persist_tags()

    def cb_tag_one(
        self,
        _item: Gtk.MenuItem,
        kind: str,
        link_type: str,
        handle: PersonHandle | FamilyHandle,
    ) -> None:
        """
        Apply one kind of tag to a single Person or Family.

        :param _item: The menu item (unused).
        :param kind: "complete", "ignore" or "prune".
        :param link_type: "Person" or "Family".
        :param handle: The handle of the object.
        """
        tag_name, color, is_default = self.__tag_for_kind(kind)
        objects: dict[str, list[Any]] = {"Person": [], "Family": []}
        objects[link_type].append(handle)
        self.__apply_tag_batch(objects, tag_name, color)
        if is_default:
            self.__remember_tag(kind, tag_name)
        self.update()

    def cb_batch_complete(self, _button: Gtk.Button) -> None:
        """
        Tag every shown Person and Family as Complete.

        :param _button: The button (unused).
        """
        self.__batch_tag("complete")

    def cb_batch_ignore(self, _button: Gtk.Button) -> None:
        """
        Tag every shown Person and Family as Ignore.

        :param _button: The button (unused).
        """
        self.__batch_tag("ignore")

    def cb_batch_prune(self, _button: Gtk.Button) -> None:
        """
        Tag every shown Person and Family as Prune.

        :param _button: The button (unused).
        """
        self.__batch_tag("prune")

    def __batch_tag(self, kind: str) -> None:
        """
        Apply one kind of tag to all currently shown objects.

        :param kind: "complete", "ignore" or "prune".
        """
        if not self.__shown_persons and not self.__shown_families:
            return
        tag_name, color, is_default = self.__tag_for_kind(kind)
        # The Home Person's line is the root of the search, not a finding, so
        # the batch buttons leave it out. It can still be tagged on its own
        # from the right-click menu.
        home = self.dbstate.db.get_default_person()
        home_handle = home.get_handle() if home is not None else None
        objects = {
            "Person": [h for h in self.__shown_persons if h != home_handle],
            "Family": list(self.__shown_families),
        }
        self.__apply_tag_batch(objects, tag_name, color)
        if is_default:
            self.__remember_tag(kind, tag_name)
        # Re-run the search so the newly tagged objects drop out (or, for
        # Prune, their branch is cut). The commit signal does not reliably
        # trigger this from inside a button handler, so refresh explicitly,
        # after the tag name has been remembered.
        self.update()

    def __get_or_create_tag(self, tag_name: str, color: str, trans: DbTxn) -> TagHandle:
        """
        Get the named tag, creating it at the top of the tag list if needed.

        :param tag_name: The name of the tag.
        :param color: The color for a new tag, as a hex string.
        :param trans: The open database transaction.
        :returns: The handle of the tag.
        """
        db = self.dbstate.db
        tag = db.get_tag_from_name(tag_name)
        if tag is not None:
            return tag.get_handle()

        # New tag goes to the top: push every existing tag down one priority.
        for existing_handle in db.get_tag_handles():
            existing = db.get_tag_from_handle(existing_handle)
            existing.set_priority(existing.get_priority() + 1)
            db.commit_tag(existing, trans)

        tag = Tag()
        tag.set_name(tag_name)
        tag.set_color(color)
        tag.set_priority(0)
        db.add_tag(tag, trans)
        return tag.get_handle()

    def __apply_tag_batch(
        self, objects: dict[str, list[Any]], tag_name: str, color: str
    ) -> None:
        """
        Add one tag to the given People and Families in a single transaction.

        The tag is created if needed. The caller refreshes the list afterwards.

        :param objects: {"Person": [handles], "Family": [handles]}.
        :param tag_name: The name of the tag.
        :param color: The color for a new tag, as a hex string.
        """
        db = self.dbstate.db
        with DbTxn(_("Tag as %s") % tag_name, db) as trans:
            tag_handle = self.__get_or_create_tag(tag_name, color, trans)
            for handle in objects.get("Person", []):
                if not db.has_person_handle(handle):
                    continue
                obj = db.get_person_from_handle(handle)
                if tag_handle not in obj.get_tag_list():
                    obj.add_tag(tag_handle)
                    db.commit_person(obj, trans)
            for handle in objects.get("Family", []):
                if not db.has_family_handle(handle):
                    continue
                obj = db.get_family_from_handle(handle)
                if tag_handle not in obj.get_tag_list():
                    obj.add_tag(tag_handle)
                    db.commit_family(obj, trans)

    def __on(self, key: str) -> bool:
        """
        Tell whether a tree data integrity test is switched on.

        :param key: The key of the test in CHECKS.
        :returns: True when the test runs.
        """
        return self.__checks.get(key, False)

    def __clear_links(self) -> None:
        """
        Forget the clickable links of the previous list.

        Gramps core keeps every link a gramplet has ever shown (the list in the
        gramplet pane is never emptied), so a gramplet that refreshes often makes
        mouse movement over its text slower and slower. Core has no method for
        this, so the list of the pane is emptied here.
        """
        gui = self.gui
        tags = getattr(gui, "_tags", None)
        if not tags:
            return
        try:
            tag_table = gui.buffer.get_tag_table()
            for link_data in tags:
                tag_table.remove(link_data[0])
        except Exception:  # pylint: disable=broad-except
            pass  # never let housekeeping stop the gramplet
        gui._tags = []  # pylint: disable=protected-access

    def __trace(self, where: str) -> None:
        """
        Write a quota-counter trace line, when SHOW_DIAGNOSTIC is on.

        :param where: A label for the place in the search.
        """
        if SHOW_DIAGNOSTIC:
            self.append_text(f"[{where}: {self.__counter}/{self.__todos_wanted}]\n")

    # The search loop comes from the built-in gramplet; its shape is kept so
    # that the two can still be compared.
    # pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
    def main(self) -> Iterator[bool]:
        """
        Build the list.

        This is a generator: Gramps runs it a little at a time while idle, so the
        window stays responsive, and a newer refresh request stops an unfinished
        search instead of waiting for it.

        :returns: An iterator that yields True after each slice of work.
        """
        # pylint: disable=too-many-nested-blocks
        self.__clear_links()

        # Fail gracefully if no database is loaded; warn or no entry ⚠ ☡ ⛔ 🚫 🛑 🚧 🚨 👣
        if not self.dbstate.db.is_open():
            self.set_text(
                no_tree_message(
                    self.__show_next_steps, can_import_without_tree(self.uistate)
                )
            )
            return

        # complain if database is empty
        people = self.dbstate.db.get_number_of_people()
        if not people:
            message = _("\n ⛔ The current Tree database contains no people.\n")
            if self.__show_next_steps:
                message += _(
                    "\n 👣 Next Steps:"
                    "\n Add a Family and a person in that family:"
                    '\n  • A Family may be added via the "Add" menu'
                    '\n  • A person may be added by pressing the "+"'
                    ' (plus) in the spouse ("Father/partner1" or'
                    ' "Mother/partner2") panels or "Children" tab.'
                    "\n\nOr Import People from an external file:"
                    "\n  • An external file may be used to populate the"
                    ' tree via "Import..." in the "Family Trees" menu.'
                )
            self.set_text(message)
            return

        # complain if no Home Person
        default_person = self.dbstate.db.get_default_person()
        if default_person is None:
            message = _('\n ⛔ No Person has been chosen as the focal "Home Person".\n')
            if self.__show_next_steps:
                message += _(
                    "\n 👣 Next Steps:"
                    "\n  •  Select the People view icon in the Navigator sidebar."
                    '\n  •  Select someone to make them the "Active Person".'
                    '\n  •  Choose "Set Home Person" from the Edit menu or from the'
                    " (right-click) context menu."
                    '\n\n This sets them as the focal "Home Person".'
                )
            self.set_text(message)
            return

        self.set_tooltip(_("Double-click color text to edit details"))
        # Complete and Ignore hide the object from the list but the search
        # still travels through it. Prune hides it and the search does not
        # travel through it.
        self.__complete_handle = self.__handle_for(self.__effective_tag("complete"))
        self.__ignore_handle = self.__handle_for(self.__effective_tag("ignore"))
        self.__prune_handle = self.__handle_for(self.__effective_tag("prune"))

        # Handles of the objects actually shown, so the batch buttons can
        # tag exactly what the reader sees.
        self.__shown_persons: set[str] = set()
        # Suggested next steps for the object being checked.
        self.__steps: list[str] = []
        self.__shown_families: set[str] = set()

        self.__counter = 0
        self.__work = 0

        self.set_text("")
        self.__missing_link(default_person, _("focal Home Person"))
        self.append_text("\n")  # set the Home Person apart from the list
        self.__counter = 0

        # Already processed persons and families, to avoid recursing
        # back down to ourselves or meeting the same person through different
        # paths.
        self.__processed_persons = {default_person.get_handle()}
        self.__processed_families: set[str] = set()

        # List of lists of ancestors in currently processed generation. We go
        # up one generation in each round.
        # The lists are separated into my own ancestors, the ancestors of my
        # spouses, the ancestors of my children's spouses, the ancestors of my
        # parent's other spouses, the ancestors of my grandchildren's spouses,
        # the ancestors of my sibling's spouses etc.
        ancestors = [[default_person]]
        ancestors_queue = [[[default_person]]] + [
            [] for i in range(self.__ancestor_delay)
        ]

        # List of lists of families of relatives in currently processed
        # distance. We go up one level of distance in each round.
        # For example, at the end of the third round, this is (potentially) a
        # list of 4 lists:
        # 1. my own great-grandchildren
        # 2. grandchildren of my parents (= my nephews and nieces)
        # 3. children of my grandparents (= my uncles and aunts)
        # 4. my great-grandparents
        # At the beginning of the fourth round, the other families of my
        # great-grandparents are added (if they were married more than once).
        # The separation into these levels is done to allow the spouses of the
        # earlier level to be listed before the kins of the later level, e.g.
        # the spouses of my nephews and nieces are listed before my uncles and
        # aunts.
        # Not that this may slightly vary with the parameters given at the
        # beginning of this class definition, but the principle remains the
        # same.
        families: list[list[Any]] = []
        families_queue: list[list[Any]] = [[] for i in range(self.__ancestor_delay)]

        # List of spouses to add to ancestors list so we track ancestors of
        # spouses, too, but delayed as defined by the parameter.
        spouses: list[list[Person]] = []
        spouses_queue: list[list[list[Person]]] = []

        while ancestors or families:
            # (Other) families of parents
            for ancestor_group in ancestors_queue.pop(0):
                new_family_group: list[Any] = []
                new_spouses_group: list[Person] = []
                for person in ancestor_group:
                    for family in self.__get_families(person):
                        spouse = self.__get_spouse(person, family)
                        if spouse is UNKNOWN_PERSON:
                            self.__missing_spouse(person)
                        elif spouse is not None:
                            self.__process_person(spouse, new_spouses_group)
                        self.__process_family(family, person, spouse, new_family_group)
                    if self.__work >= WORK_PER_STEP:
                        self.__work = 0
                        yield True
                if new_family_group:
                    families.append(new_family_group)
                if new_spouses_group:
                    spouses.append(new_spouses_group)
            self.__trace("(Other) families of parents")
            if self.__counter >= self.__todos_wanted:
                break

            # Next generation of children
            if self.__downs_per_up:

                for _down in range(self.__downs_per_up):
                    new_families = []
                    for family_group in families:
                        children: list[Person] = []
                        for family, person, spouse in family_group:
                            for child in self.__get_children(family):
                                self.__process_person(child, children)
                            if self.__work >= WORK_PER_STEP:
                                self.__work = 0
                                yield True
                        self.__trace("Family Group in Families")
                        if self.__counter >= self.__todos_wanted:
                            break

                        # Families of children
                        new_family_group = []
                        new_spouses_group = []
                        for person in children:
                            self.__trace("children")
                            if self.__counter >= self.__todos_wanted:
                                break
                            for family in self.__get_families(person):
                                spouse = self.__get_spouse(person, family)
                                if spouse is UNKNOWN_PERSON:
                                    self.__missing_spouse(person)
                                elif spouse is not None:
                                    self.__process_person(spouse, new_spouses_group)
                                self.__process_family(
                                    family, person, spouse, new_family_group
                                )
                            if self.__work >= WORK_PER_STEP:
                                self.__work = 0
                                yield True
                        if new_family_group:
                            new_families.append(new_family_group)
                        if new_spouses_group:
                            spouses.append(new_spouses_group)
                        self.__trace("Families of children")
                        if self.__counter >= self.__todos_wanted:
                            break
                    families = new_families
                    spouses_queue.append(spouses)
                    spouses = []
                    self.__trace("Spouses")
                    if self.__counter >= self.__todos_wanted:
                        break
                self.__trace("Next generation of children")
                if self.__counter >= self.__todos_wanted:
                    break

            # Parents
            new_ancestors = []
            new_families = []
            for ancestor_group in ancestors:
                new_ancestor_group_1: list[Person] = []
                new_ancestor_group_2: list[Person] = []
                new_family_group = []
                for person in ancestor_group:
                    father, mother, family = self.__get_parents(person)
                    if family is UNKNOWN_FAMILY:
                        self.__missing_parents(person)
                    elif family is not None:
                        if father is UNKNOWN_PERSON:
                            self.__missing_father(person)
                        elif father is not None:
                            self.__process_person(father, new_ancestor_group_1)
                        if mother is UNKNOWN_PERSON:
                            self.__missing_mother(person)
                        elif mother is not None:
                            if father is None:
                                self.__process_person(mother, new_ancestor_group_1)
                            else:
                                self.__process_person(mother, new_ancestor_group_2)
                        self.__process_family(family, father, mother, new_family_group)
                    if self.__work >= WORK_PER_STEP:
                        self.__work = 0
                        yield True
                if new_ancestor_group_1 or new_ancestor_group_2:
                    new_ancestors.append(new_ancestor_group_1 + new_ancestor_group_2)
                if new_family_group:
                    new_families.append(new_family_group)
                self.__trace("ancestor_group in ancestors")
                if self.__counter >= self.__todos_wanted:
                    break
            ancestors = new_ancestors + spouses_queue.pop(0)
            ancestors_queue.append(ancestors)
            families_queue.append(new_families)
            families += families_queue.pop(0)
            self.__trace("Parents")
            if self.__counter >= self.__todos_wanted:
                break

            # Separator between rounds
            if self.__counter > 0:
                self.__trace("New Round of Generations")
                self.append_text("\n")

        self.append_text("", scroll_to="begin")

    # ------------------------------------------------------------------
    # Names (only worked out when something is actually reported)
    # ------------------------------------------------------------------
    def __person_name(self, person: Person) -> str:
        """
        Get the display name of a person.

        :param person: The person.
        :returns: The name to show.
        """
        name = name_displayer.display_name(person.get_primary_name())
        return name or _("(person with unknown name)")

    def __partner_name(self, person: Person | Any | None) -> str:
        """
        Get the display name of a partner in a family line.

        :param person: The partner.
        :returns: The name to show.
        """
        if person is UNKNOWN_PERSON or person is None:
            return _("(unknown person)")
        return name_displayer.display(person) or _("(person with unknown name)")

    def __family_name(
        self, person1: Person | Any | None, person2: Person | Any | None
    ) -> str:
        """
        Get the display name of a family from its two partners.

        :param person1: The first partner, None, or UNKNOWN_PERSON.
        :param person2: The second partner, None, or UNKNOWN_PERSON.
        :returns: The name to show.
        """
        return _("%(name1)s and %(name2)s") % {
            "name1": self.__partner_name(person1),
            "name2": self.__partner_name(person2),
        }

    def __add_step(self, step: str) -> None:
        """
        Remember a suggested next step for the object being checked.

        :param step: The key of the step in NEXT_STEPS.
        """
        if step not in self.__steps:
            self.__steps.append(step)

    def __show_steps(self) -> None:
        """Write the 👣 suggested next steps under the line just reported."""
        if self.__show_next_steps:
            for step in self.__steps:
                self.append_text(f"  👣 {NEXT_STEPS[step]}\n")
        self.__steps = []

    def __gap_tag(self) -> Gtk.TextTag:
        """
        Get the text tag that puts space above each reported entry.

        The space is about 60% of a line, measured from the font of the text
        view, so each reported Person or Family and its 👣 steps read as a group.
        The tag is created once; Gramps keeps the tag table of the text view.

        :returns: The text tag.
        """
        buffer = self.gui.buffer
        tag = buffer.get_tag_table().lookup("whatsnext-gap")
        if tag is None:
            layout = self.gui.textview.create_pango_layout("Ag")
            line_height = layout.get_pixel_size()[1] or 16
            tag = buffer.create_tag(
                "whatsnext-gap", pixels_above_lines=round(line_height * 0.6)
            )
        return tag

    def __start_entry(self) -> int:
        """
        Mark the start of a reported line; see __end_entry.

        :returns: The character offset where the line starts.
        """
        return self.gui.buffer.get_char_count()

    def __end_entry(self, offset: int) -> None:
        """
        Put the gap above the reported line that started at *offset*.

        :param offset: The value returned by __start_entry.
        """
        try:
            buffer = self.gui.buffer
            start = buffer.get_iter_at_offset(offset)
            end = buffer.get_iter_at_offset(offset + 1)
            buffer.apply_tag(self.__gap_tag(), start, end)
        except (AttributeError, TypeError):
            pass  # spacing is cosmetic; never stop the search for it

    def __report(
        self,
        name: str,
        link_type: str,
        handle: PersonHandle | FamilyHandle,
        missingbits: list[str],
    ) -> None:
        """
        Report one Person or Family with its problems and next steps.

        :param name: The name to show as a link.
        :param link_type: "Person" or "Family".
        :param handle: The handle of the object.
        :param missingbits: The problems found.
        """
        entry = self.__start_entry()
        self.link(name, link_type, handle)
        self.append_text(
            _(": %(list)s\n") % {"list": _(", ").join(missingbits)}
        )  # Arabic OK
        self.__show_steps()
        self.__end_entry(entry)
        if link_type == "Person":
            self.__shown_persons.add(handle)
        else:
            self.__shown_families.add(handle)
        self.__counter += 1

    # ------------------------------------------------------------------
    # Tests on people
    # ------------------------------------------------------------------
    def __process_person(self, person: Person, append_list: list[Person]) -> None:
        """
        Check one person, and add them to the list the search continues from.

        :param person: The person.
        :param append_list: The group of people for the next step of the search.
        """
        handle = person.get_handle()
        if handle in self.__processed_persons:
            return

        self.__processed_persons.add(handle)
        self.__work += 1

        # A Complete or Ignore tag hides the person from the list, but we
        # still append them so the search travels through to relatives.
        if self.__suppressed(person):
            append_list.append(person)
            return

        missingbits = []
        self.__steps = []

        primary_name = person.get_primary_name()

        if self.__on("first_name") and not primary_name.get_first_name():
            missingbits.append(_("first name unknown"))
            self.__add_step("name")

        if self.__on("surname") and not primary_name.get_surname():
            missingbits.append(_("surname unknown"))
            self.__add_step("name")

        has_birth, has_death = self.__person_events(person, missingbits)

        if not has_birth and self.__on("birth_missing"):
            missingbits.append(_("Birth event missing"))
            self.__add_step("add_event")

        # Only the preferred Death event may have been read, so a person
        # without one is checked for any Death event before being reported.
        if (
            not has_death
            and self.__on("death_missing")
            and not probably_alive(person, self.dbstate.db)
            and not self.__has_death_event(person)
        ):
            missingbits.append(_("Death event missing"))
            self.__add_step("add_event")

        if missingbits:
            self.__report(self.__person_name(person), "Person", handle, missingbits)

        append_list.append(person)

    def __person_events(
        self, person: Person, missingbits: list[str]
    ) -> tuple[bool, bool]:
        """
        Examine the Birth and Death events of a person.

        Only the preferred Birth and Death events are checked (two database reads
        at most). Every Primary-role event is read only when no preferred Birth
        is set and the event list has to be searched for one. Non-preferred Birth
        and Death events are usually kept on purpose, to record a source that
        disagrees, so they are not reported.

        :param person: The person.
        :param missingbits: The list the problems found are added to.
        :returns: (has_birth, has_death): whether the person has a Birth event,
            and whether a Death event was seen.
        """
        db = self.dbstate.db
        birth_ref = person.get_birth_ref()

        if birth_ref is None:
            has_birth = False
            has_death = False
            for event_ref in person.get_primary_event_ref_list():
                event = db.get_event_from_handle(event_ref.ref)
                event_type = event.get_type()
                if event_type == EventType.BIRTH:
                    has_birth = True
                    if self.__on("birth_event"):
                        missingbits.extend(self.__process_event(event, "person_event"))
                elif event_type == EventType.DEATH:
                    has_death = True
                    if self.__on("death_event"):
                        missingbits.extend(self.__process_event(event, "person_event"))
            return has_birth, has_death

        if self.__on("birth_event"):
            event = db.get_event_from_handle(birth_ref.ref)
            missingbits.extend(self.__process_event(event, "person_event"))

        death_ref = person.get_death_ref()
        if self.__on("death_event") and death_ref is not None:
            event = db.get_event_from_handle(death_ref.ref)
            missingbits.extend(self.__process_event(event, "person_event"))

        return True, death_ref is not None

    def __has_death_event(self, person: Person) -> bool:
        """
        Tell whether any Primary-role event of the person is a Death event.

        :param person: The person.
        :returns: True when a Death event is found.
        """
        db = self.dbstate.db
        for event_ref in person.get_primary_event_ref_list():
            if db.get_event_from_handle(event_ref.ref).get_type() == EventType.DEATH:
                return True
        return False

    # ------------------------------------------------------------------
    # Tests on families
    # ------------------------------------------------------------------
    def __process_family(
        self,
        family: Family,
        person1: Person | Any | None,
        person2: Person | Any | None,
        append_list: list[tuple[Family, Any, Any]],
    ) -> None:
        """
        Check one family, and add it to the list the search continues from.

        :param family: The family.
        :param person1: The first partner, None, or UNKNOWN_PERSON.
        :param person2: The second partner, None, or UNKNOWN_PERSON.
        :param append_list: The group of families for the next step of the search.
        """
        handle = family.get_handle()
        if handle in self.__processed_families:
            return

        self.__processed_families.add(handle)
        self.__work += 1

        # A Complete or Ignore tag hides the family from the list, but we
        # still append it so the search travels through to children.
        if self.__suppressed(family):
            append_list.append((family, person1, person2))
            return

        missingbits = []
        self.__steps = []

        has_marriage = False

        for event_ref in family.get_event_ref_list():
            event = self.dbstate.db.get_event_from_handle(event_ref.ref)
            event_type = event.get_type()
            if event_type == EventType.MARRIAGE:
                has_marriage = True
                if self.__on("marriage_event"):
                    missingbits.extend(self.__process_event(event, "family_event"))
            elif event_type == EventType.DIVORCE:
                if self.__on("divorce_event"):
                    missingbits.extend(self.__process_event(event, "family_event"))

        relationship = family.get_relationship()
        if relationship == FamilyRelType.MARRIED:
            if not has_marriage and self.__on("marriage_missing"):
                missingbits.append(_("marriage event missing"))
                self.__add_step("marriage")
        elif relationship == FamilyRelType.UNKNOWN:
            if self.__on("relationship_unknown"):
                missingbits.append(_("relationship type unknown"))
                self.__add_step("relationship")

        if missingbits:
            self.__report(
                self.__family_name(person1, person2), "Family", handle, missingbits
            )

        append_list.append((family, person1, person2))

    # ------------------------------------------------------------------
    # Tests on an event
    # ------------------------------------------------------------------
    def __process_event(self, event: Event, step: str) -> list[str]:
        """
        Check the date and place of an event.

        Each date is reported once, in the first of these that fits: unknown,
        text only, inexact (a range, a span, before, after, about, estimated or
        calculated), or incomplete (a single exact date without its day or month).

        :param event: The event.
        :param step: The key in NEXT_STEPS suggested when something is missing.
        :returns: The problems found, as one "Type: problems" entry, or [].
        """
        missingbits = []

        # Each date is reported once, in the first of these that fits:
        # unknown, text only, inexact (a range, a span, before, after,
        # about, estimated or calculated), or incomplete (a single exact
        # date without its day or month).
        date = event.get_date_object()
        if date.is_empty():
            if self.__on("date_unknown"):
                missingbits.append(_("date unknown"))
        elif date.get_modifier() == Date.MOD_TEXTONLY:
            if self.__on("date_text_only"):
                missingbits.append(_("date is text only"))
        elif (
            date.get_modifier() != Date.MOD_NONE or date.get_quality() != Date.QUAL_NONE
        ):
            if self.__on("date_inexact"):
                missingbits.append(_("date inexact"))
        elif not date.is_regular():
            if self.__on("date_incomplete"):
                missingbits.append(_("date incomplete"))

        if self.__on("place_unknown") and not event.get_place_handle():
            missingbits.append(_("place unknown for the Event"))

        if missingbits:
            self.__add_step(step)
            # translators: needed for French, ignore otherwise
            return [
                _("%(str1)s: %(str2)s")
                % {"str1": event.get_type(), "str2": _(", ").join(missingbits)}
            ]  # Arabic OK
        return []

    # ------------------------------------------------------------------
    # Tests on links between people
    # ------------------------------------------------------------------
    def __missing_spouse(self, person: Person) -> None:
        """
        Report a person whose family has no partner.

        :param person: The person.
        """
        if self.__on("spouse_missing") and not self.__suppressed(person):
            self.__missing_link(
                person,
                _("A partner relationship exists but the spouse is missing"),
                "spouse",
            )

    def __missing_father(self, person: Person) -> None:
        """
        Report a person whose parent family has no father.

        :param person: The person.
        """
        if self.__on("father_missing") and not self.__suppressed(person):
            self.__missing_link(
                person, _("Father missing from the parent family"), "father"
            )

    def __missing_mother(self, person: Person) -> None:
        """
        Report a person whose parent family has no mother.

        :param person: The person.
        """
        if self.__on("mother_missing") and not self.__suppressed(person):
            self.__missing_link(
                person, _("Mother missing from the parent family"), "mother"
            )

    def __missing_parents(self, person: Person) -> None:
        """
        Report a person who has no parent family.

        :param person: The person.
        """
        if self.__on("parents_missing") and not self.__suppressed(person):
            self.__missing_link(person, _("Parent family is unknown."), "parents")

    def __missing_link(
        self, person: Person, text: str, step: str | None = None
    ) -> None:
        """
        Report one Person with a single line of text.

        :param person: The person.
        :param text: The text after the name.
        :param step: The key in NEXT_STEPS of the suggested next step, or None
            for a line with no step (the Home Person line at the top of the list).
        """

        entry = self.__start_entry()
        name = name_displayer.display(person)
        self.link(name, "Person", person.get_handle())
        self.append_text(_(": %s\n") % text)
        self.__steps = [step] if step else []
        self.__show_steps()
        self.__end_entry(entry)
        self.__shown_persons.add(person.get_handle())
        self.__trace("Missing Link")
        self.__counter += 1

    # ------------------------------------------------------------------
    # Walking the tree
    # ------------------------------------------------------------------
    def __handle_for(self, tag_name: str) -> TagHandle | None:
        """
        Get the handle of a configured tag by name.

        :param tag_name: The name of the tag.
        :returns: The handle, or None when there is no such tag.
        """
        if not tag_name:
            return None
        tag = self.dbstate.db.get_tag_from_name(tag_name)
        return tag.get_handle() if tag is not None else None

    def __pruned(self, obj: Person | Family) -> bool:
        """
        Tell whether an object carries the Prune tag.

        Pruned objects are not travelled through by the search.

        :param obj: The Person or Family.
        :returns: True when the object is pruned.
        """
        return (
            self.__prune_handle is not None
            and self.__prune_handle in obj.get_tag_list()
        )

    def __suppressed(self, obj: Person | Family) -> bool:
        """
        Tell whether an object carries the Complete or the Ignore tag.

        Such objects are hidden from the list, but the search still travels
        through them.

        :param obj: The Person or Family.
        :returns: True when the object is hidden.
        """
        tags = obj.get_tag_list()
        return (
            self.__complete_handle is not None and self.__complete_handle in tags
        ) or (self.__ignore_handle is not None and self.__ignore_handle in tags)

    def __get_spouse(self, person: Person, family: Family) -> Person | Any | None:
        """
        Get the partner of a person in a family.

        :param person: The person.
        :param family: The family.
        :returns: The partner; UNKNOWN_PERSON when a married family has no
            partner; or None when there is no partner to follow (none expected,
            or pruned).
        """
        spouse_handle = utils.find_spouse(person, family)
        if not spouse_handle:
            if family.get_relationship() == FamilyRelType.MARRIED:
                return UNKNOWN_PERSON
            return None
        spouse = self.dbstate.db.get_person_from_handle(spouse_handle)
        if self.__pruned(spouse):
            return None
        return spouse

    def __get_children(self, family: Family) -> Iterator[Person]:
        """
        Get the children of a family that are not yet examined or pruned.

        :param family: The family.
        :returns: An iterator over the children.
        """
        for child_ref in family.get_child_ref_list():
            # Someone already examined would be skipped anyway, so do not
            # read that person from the database again.
            if child_ref.ref in self.__processed_persons:
                continue
            child = self.dbstate.db.get_person_from_handle(child_ref.ref)
            if self.__pruned(child):
                continue
            yield child

    def __get_families(self, person: Person) -> Iterator[Family]:
        """
        Get the families of a person that are not yet examined or pruned.

        :param person: The person.
        :returns: An iterator over the families.
        """
        for family_handle in person.get_family_handle_list():
            if family_handle in self.__processed_families:
                continue
            family = self.dbstate.db.get_family_from_handle(family_handle)
            if self.__pruned(family):
                continue
            yield family

    def __get_parents(self, person: Person) -> tuple[Any, Any, Any]:
        """
        Get the parents and parent family of a person.

        :param person: The person.
        :returns: (father, mother, family). Each is the object, None when there
            is nothing to follow, or UNKNOWN_PERSON / UNKNOWN_FAMILY when it is
            missing and should be reported.
        """
        family_handle = person.get_main_parents_family_handle()
        if not family_handle:
            return (UNKNOWN_PERSON, UNKNOWN_PERSON, UNKNOWN_FAMILY)
        if family_handle in self.__processed_families:
            return (None, None, None)

        family = self.dbstate.db.get_family_from_handle(family_handle)
        if self.__pruned(family):
            return (None, None, None)

        father_handle = family.get_father_handle()
        if not father_handle:
            if family.get_relationship() == FamilyRelType.MARRIED:
                father = UNKNOWN_PERSON
            else:
                father = None
        else:
            father = self.dbstate.db.get_person_from_handle(father_handle)
            if self.__pruned(father):
                father = None

        mother_handle = family.get_mother_handle()
        if not mother_handle:
            mother = UNKNOWN_PERSON
        else:
            mother = self.dbstate.db.get_person_from_handle(mother_handle)
            if self.__pruned(mother):
                mother = None

        return (father, mother, family)


# ------------------------------------------------------------
#
# UnknownPersonMarker
#
# ------------------------------------------------------------
class UnknownPersonMarker:  # pylint: disable=too-few-public-methods
    """Stands for a person who is missing and should be reported."""


# ------------------------------------------------------------
#
# UnknownFamilyMarker
#
# ------------------------------------------------------------
class UnknownFamilyMarker:  # pylint: disable=too-few-public-methods
    """Stands for a parent family that is missing and should be reported."""


UNKNOWN_PERSON = UnknownPersonMarker()
UNKNOWN_FAMILY = UnknownFamilyMarker()
