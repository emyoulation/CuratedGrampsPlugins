# encoding: utf-8
#
# "What's Next?" Gramplet, a modular plugin for Gramps
# (Gramps - the genealogy software suite built on GTK+/GNOME)
#
# Copyright (C) 2008 Reinhard Mueller
# Copyright (C) 2010 Jakim Friant
# Copyright (C) 2023, 2024 Brian McCullough
# Copyright (C) 2026 Claude AI (wish coding by Brian McCullough)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.
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
# For the Gramps-Project volunteer community's contact information, visit:
# https://gramps-project.org/wiki/index.php/Contact

# ------------------------------------------------------------------------
#
# Python modules
#
# ------------------------------------------------------------------------
import os

# ------------------------------------------------------------------------
#
# GTK modules
#
# ------------------------------------------------------------------------
from gi.repository import Gtk

# ------------------------------------------------------------------------
#
# Gramps modules
#
# ------------------------------------------------------------------------
from gramps.gen.config import config as configman
from gramps.gen.db import DbTxn
from gramps.gen.lib import EventType, FamilyRelType, Tag
from gramps.gen.plug import Gramplet, PluginRegister
from gramps.gen.display.name import displayer as name_displayer
from gramps.gen.plug.report import utils
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui.utils import is_right_click
from gramps.gui.display import display_url

_ = glocale.translation.sgettext

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

    def add_help_button(container, uistate, plugin, *, size=16):
        """
        Pack a plain text "Help" button that opens the help_url of the
        plugin. Stand-in for MarkdownUtils.add_help_button(); *size* is
        accepted for the same call signature and not used.
        """
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

show_diagnostic = False

# How many people or families to examine before handing control back to
# Gramps, so the window stays responsive during a long search.
WORK_PER_STEP = 40

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
    "birth_event": True,  # date and place of the Birth event
    "death_event": True,  # date and place of the Death event
    # False: only the preferred Birth and Death events are examined.
    # True: every Birth and Death event with the Primary role is examined
    # (the older behavior, which reads every event of every person).
    "alternate_events": False,
    "person_complete_tag": True,  # needs the "Completed Person" option
    # Families
    "marriage_missing": True,  # Married, but no Marriage event
    "marriage_event": True,  # date and place of the Marriage event
    "divorce_event": True,  # date and place of the Divorce event
    "relationship_unknown": True,  # relationship type is Unknown
    "family_complete_tag": True,  # needs the "Completed offspring" option
    # Links between people
    "spouse_missing": True,
    "father_missing": True,
    "mother_missing": True,
    # People with no parent family are reported (the upstream intent,
    # which the earlier beta accidentally dropped). Configurable.
    "parents_missing": True,
    # Details examined for each of the events above
    "date_unknown": True,
    "date_incomplete": True,
    "place_unknown": True,
}

# Checks offered in the Configuration dialog, in display order, each with a
# label. Adding a (key, label) pair here is all that is needed to expose
# another test; the search already asks self.__on(key) before running it.
# Tests borrowed from the "Verify the Data" tool can be added the same way.
CHECK_OPTIONS = [
    ("parents_missing", _("Report a missing parent family")),
]
# Tooltip text for the options above, by key.
CHECK_HELP = {
    "parents_missing": _("List each person who has no parent family"),
}


# ------------------------------------------------------------------------
#
# Persistent settings
#
# The .ini sits in this addon's own folder, next to this module, following
# the ConfigManager pattern used by the other Emyoulation gramplets. The
# [meta] block records the plugin id and a schema version so an outdated
# settings file can be ignored rather than misread.
#
# ------------------------------------------------------------------------
PLUGIN_ID = "Beta What's Next"
SCHEMA_VERSION = "1"

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
CONFIG = configman.register_manager(
    "Betawhatsnext", use_plugins_path=False
)
CONFIG.register("meta.plugin_id", PLUGIN_ID)
CONFIG.register("meta.schema_version", SCHEMA_VERSION)
# The chosen Complete, Ignore and Prune tags, by name. Stored here so a tag
# created by a batch button is saved and shows in the Configuration menu.
CONFIG.register("tags.complete", "")
CONFIG.register("tags.ignore", "")
CONFIG.register("tags.prune", "")
# Display preferences (not tree data integrity tests).
CONFIG.register("display.show_next_steps", True)
for _key, _label in CHECK_OPTIONS:
    CONFIG.register("checks.%s" % _key, CHECKS[_key])
CONFIG.init()
if CONFIG.get("meta.schema_version") != SCHEMA_VERSION:
    # Settings from an incompatible version: start fresh rather than
    # misread them.
    CONFIG.set("meta.schema_version", SCHEMA_VERSION)
    CONFIG.set("display.show_next_steps", True)
    for _key, _label in CHECK_OPTIONS:
        CONFIG.set("checks.%s" % _key, CHECKS[_key])
    CONFIG.save()

def no_tree_message(show_next_steps):
    """Build the "no tree loaded" guidance, with or without the Next Steps."""
    message = _(
        "\n ⛔ A local Genealogical Tree database has not yet been loaded.\n\n"
    )
    if show_next_steps:
        message += _(" 👣 Next Steps:\n")
        message += _('  •  From the "Family Trees" menu,')
        message += _(' use the "Manage Family Trees..." option to')
        message += _(" create a New (or to select an existing) Tree database.\n")
        message += _('  •  Click the "Load Family Tree" button to begin')
        message += _(" working with the selected genealogical tree.\n\n")
        message += _("Create and load an empty new tree to import a backup (or")
        message += _(" GEDCOM file) from another genealogical tool.\n\n")
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


class BetaWhatNextGramplet(Gramplet):

    def init(self):
        self.set_tooltip(
            _(
                'Use the "Configure" in the "View" menu to'
                " change the Gramplet options."
            )
        )
        # init() runs before on_load(), so read the saved value directly.
        self.set_text(no_tree_message(CONFIG.get("display.show_next_steps")))

    def post_init(self):
        """
        Take over the text view's button handling.

        The gramplet pane connects its own button-press handler, which opens
        the editor on a right-click over a Person or Family link. We replace
        it with our own handler so a right-click instead offers a small menu
        (Review, Tag as Complete, Tag to Ignore), and we hand every other
        click back to the pane's handler unchanged.
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

    def cb_populate_popup(self, _view, menu):
        """Append an Organize Tags item to the text view's default menu."""
        if not isinstance(menu, Gtk.Menu):
            return
        separator = Gtk.SeparatorMenuItem()
        separator.show()
        menu.append(separator)
        item = Gtk.MenuItem.new_with_label(_("Organize Tags"))
        item.connect("activate", self.cb_organize_tags)
        item.show()
        menu.append(item)

    def __build_button_bar(self):
        """
        Add a row of buttons at the bottom of the gramplet: a Help button on
        the far left, then batch "Tag all shown" buttons for Complete, Ignore
        and Prune. The row is appended to the box that holds the scrolling
        text area, so it stays fixed below the text.
        """
        try:
            container = self.gui.get_container_widget()
            parent = container.get_parent()
            if parent is None or not hasattr(parent, "pack_start"):
                return
            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            bar.set_border_width(2)
            # Help button on the far left.
            add_help_button(bar, self.uistate, PLUGIN_ID)
            bar.pack_start(
                self.__batch_button(
                    _("Complete"),
                    _("Tag listed People and Families as Completed"),
                    self.cb_batch_complete,
                ),
                False,
                False,
                0,
            )
            bar.pack_start(
                self.__batch_button(
                    _("Ignore"),
                    _("Tag to Ignore People and Families"),
                    self.cb_batch_ignore,
                ),
                False,
                False,
                0,
            )
            bar.pack_start(
                self.__batch_button(
                    _("Prune"),
                    _("Tag to Prune (exclude) listed People and Families from testing"),
                    self.cb_batch_prune,
                ),
                False,
                False,
                0,
            )
            parent.pack_start(bar, False, False, 0)
            bar.show_all()
            self.__button_bar = bar
        except Exception:  # pylint: disable=broad-except
            # The gramplet still works without the button bar; the right-click
            # menu offers the same tagging per object.
            pass

    def __batch_button(self, label, tooltip, callback):
        """A button with the themed tag icon (menu size) and a text label."""
        button = Gtk.Button()
        button.set_image(
            Gtk.Image.new_from_icon_name("gramps-tag-new", Gtk.IconSize.MENU)
        )
        button.set_always_show_image(True)  # else some themes hide the icon
        button.set_label(label)
        button.set_tooltip_text(tooltip)
        button.connect("clicked", callback)
        return button

    def build_options(self):
        """
        Build the configuration options.
        """
        from gramps.gen.plug.menu import (
            NumberOption,
            EnumeratedListOption,
            BooleanOption,
        )

        self.opts = []

        # Minimum number of lines we want to see. Further lines with the same
        # distance to the main person will be added on top of this.
        name = _("Search Quota ")
        opt = NumberOption(name, self.__todos_wanted, 1, 300)
        opt.set_help(
            _("The least number of lines to show. The search stops once this many problems are found")
        )
        self.opts.append(opt)

        # How many generations of descendants to process before we go up to the
        # next level of ancestors.
        name = _("Depth per loop")
        opt = NumberOption(name, self.__downs_per_up, 1, 15)
        opt.set_help(
            _("How many generations of descendants to check before going up one more generation of ancestors")
        )
        self.opts.append(opt)

        # After an ancestor was processed, how many extra rounds to delay until
        # the descendants of this ancestor are processed.
        name = _("Pause search expansion")
        opt = NumberOption(name, self.__ancestor_delay, 1, 10)
        opt.set_help(
            _("How many extra rounds to wait after checking an ancestor before checking the descendants of that ancestor")
        )
        self.opts.append(opt)

        # Complete tag: the object is finished (its gaps will never be
        # filled). Hidden from the list, but still travelled through.
        opt = EnumeratedListOption(_("Complete tag"), self.__complete_tag)
        opt.set_help(
            _("Finished. Hide the object, and keep searching through it")
        )
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
        opt.set_help(
            _("Dead end. Hide the object, and stop searching through it")
        )
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
        opt = BooleanOption(_("Show suggested Next Steps"), self.__show_next_steps)
        opt.set_help(
            _("Show the guidance steps and the 👣 suggestions. Turn off for a shorter list")
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
        # its label the option's tooltip, and hide that label for check
        # boxes, which already carry their own label.
        for opt in self.opts:
            widget = self.option_dict[opt.get_label()][0]
            widget.connect("parent-set", self.cb_option_parent_set, opt)

    def cb_option_parent_set(self, widget, _old_parent, option):
        """Adjust the dialog label that sits to the left of an option."""
        grid = widget.get_parent()
        if not isinstance(grid, Gtk.Grid):
            return
        row = grid.child_get_property(widget, "top-attach")
        label = grid.get_child_at(0, row)
        if label is None or label is widget:
            return
        if option.get_help():
            label.set_tooltip_text(option.get_help())
        if isinstance(widget, Gtk.CheckButton):
            label.set_no_show_all(True)
            label.hide()

    def save_options(self):
        """
        Save gramplet configuration data.
        """
        self.__todos_wanted = int(self.opts[0].get_value())
        self.__downs_per_up = int(self.opts[1].get_value())
        self.__ancestor_delay = int(self.opts[2].get_value())
        self.__complete_tag = self.opts[3].get_value()
        self.__ignore_tag = self.opts[4].get_value()
        self.__prune_tag = self.opts[5].get_value()
        self.__persist_tags()

        changed = False

        show_next_steps = bool(self.opts[self.__display_first].get_value())
        self.__show_next_steps = show_next_steps
        if CONFIG.get("display.show_next_steps") != show_next_steps:
            CONFIG.set("display.show_next_steps", show_next_steps)
            changed = True

        for offset, (key, _label) in enumerate(CHECK_OPTIONS):
            value = bool(self.opts[self.__check_first + offset].get_value())
            self.__checks[key] = value
            if CONFIG.get("checks.%s" % key) != value:
                CONFIG.set("checks.%s" % key, value)
                changed = True
        if changed:
            CONFIG.save()

    def save_update_options(self, obj):
        """
        Save a gramplet's options to file.
        """
        self.save_options()
        self.__sync_gui_data()
        self.update()

    def __sync_gui_data(self):
        """
        Store the numeric options in the gramplet bar. The three tags live
        in this addon's own settings file instead (see __persist_tags).
        """
        self.gui.data = [
            self.__todos_wanted,
            self.__downs_per_up,
            self.__ancestor_delay,
        ]

    def __persist_tags(self):
        """Save the three chosen tag names to this addon's settings file."""
        CONFIG.set("tags.complete", self.__complete_tag)
        CONFIG.set("tags.ignore", self.__ignore_tag)
        CONFIG.set("tags.prune", self.__prune_tag)
        CONFIG.save()

    def on_load(self):
        """
        Load stored configuration data.
        """
        # Which tree data integrity tests run. Start from the defaults,
        # then apply the choices saved in this addon's own settings file
        # for the tests that are exposed in the Configuration dialog.
        self.__checks = dict(CHECKS)
        for key, _label in CHECK_OPTIONS:
            self.__checks[key] = CONFIG.get("checks.%s" % key)

        # Display preference: whether 👣 Next Steps suggestions are shown.
        self.__show_next_steps = CONFIG.get("display.show_next_steps")

        # The three tags live in this addon's own settings file, so a tag
        # created by a batch button is saved and appears in the options.
        self.__complete_tag = CONFIG.get("tags.complete")
        self.__ignore_tag = CONFIG.get("tags.ignore")
        self.__prune_tag = CONFIG.get("tags.prune")

        # The numeric options stay in the gramplet bar, as in the built-in
        # gramplet.
        if len(self.gui.data) >= 3:
            self.__todos_wanted = int(self.gui.data[0])
            self.__downs_per_up = int(self.gui.data[1])
            self.__ancestor_delay = int(self.gui.data[2])
            # One-time migration of the old six-slot tag settings into the
            # settings file. Slots 3-5 were person-complete, family-complete
            # and ignore; the old ignore tag blocked the search, now "prune".
            if len(self.gui.data) == 6 and not (
                self.__complete_tag or self.__ignore_tag or self.__prune_tag
            ):
                self.__complete_tag = self.gui.data[3] or ""
                self.__prune_tag = self.gui.data[5] or ""
                self.__persist_tags()
        else:
            self.__todos_wanted = 10
            self.__downs_per_up = 1
            self.__ancestor_delay = 5

    def db_changed(self):
        # Each signal is connected once. A burst of signals (one save can
        # send several) now leads to a single search, because main() runs
        # in the background and a newer request replaces a pending one.
        for signal in REFRESH_SIGNALS:
            self.connect(self.dbstate.db, signal, self.update)

    def _no_db(self):
        super()._no_db()
        self.__clear_links()
        self.set_text(no_tree_message(self.__show_next_steps))

    # ------------------------------------------------------------------
    # Right-click menu and tagging
    # ------------------------------------------------------------------
    def cb_button_press(self, view, event):
        """
        Offer a tag menu on a right-click over a reported object; otherwise
        let the gramplet pane handle the click as usual.
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

    def __link_at(self, view, event):
        """
        Return (link_type, handle) for the link under the pointer, or None.
        """
        buffer_location = view.window_to_buffer_coords(
            Gtk.TextWindowType.TEXT, int(event.x), int(event.y)
        )
        text_iter = view.get_iter_at_location(*buffer_location)
        if isinstance(text_iter, tuple):
            text_iter = text_iter[1]
        for tag, link_type, handle, _tooltip in self.gui._tags:
            if text_iter.has_tag(tag):
                return (link_type, handle)
        return None

    def __popup_tag_menu(self, link_type, handle, event):
        """Build and show the Review / Tag menu for one object."""
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
        self.__tag_menu = menu
        menu.popup_at_pointer(event)

    def cb_organize_tags(self, _item):
        """Open the Gramps Organize Tags dialog."""
        from gramps.gui.views.tags import OrganizeTagsDialog

        OrganizeTagsDialog(self.dbstate.db, self.uistate, [])

    def __tag_menu_item(self, label, kind, link_type, handle):
        """A menu item carrying the themed tag icon at menu (16x16) size."""
        item = Gtk.MenuItem()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        image = Gtk.Image.new_from_icon_name("gramps-tag-new", Gtk.IconSize.MENU)
        box.pack_start(image, False, False, 0)
        box.pack_start(Gtk.Label(label=label, xalign=0.0), True, True, 0)
        item.add(box)
        item.connect("activate", self.cb_tag_one, kind, link_type, handle)
        item.show_all()
        return item

    def cb_review(self, _item, link_type, handle):
        """Open the editor for the object, as a double-click would."""
        from gramps.gui.editors import EditPerson, EditFamily
        from gramps.gen.errors import WindowActiveError

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

    def __effective_tag(self, kind):
        """
        The tag name chosen for a kind, or "" when none is chosen.

        Each kind needs its own tag. If two kinds are set to the same tag,
        the later one (in the order complete, ignore, prune) counts as not
        chosen, so Prune can never act as Complete. Both the tag buttons and
        the search use this one rule.
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

    def __tag_for_kind(self, kind):
        """
        Return (tag_name, color, is_default) for a tag kind. If no tag is
        chosen for it, this returns the default name and color and flags it
        so the caller can remember the new tag as the chosen one.
        """
        defaults = {
            "complete": (DEFAULT_COMPLETE_TAG, DEFAULT_COMPLETE_COLOR),
            "ignore": (DEFAULT_IGNORE_TAG, DEFAULT_IGNORE_COLOR),
            "prune": (DEFAULT_PRUNE_TAG, DEFAULT_PRUNE_COLOR),
        }
        chosen = self.__effective_tag(kind)
        name, color = defaults[kind]
        return (chosen or name, color, not chosen)

    def __remember_tag(self, kind, tag_name):
        """Record an auto-created tag name as the chosen tag for its kind."""
        if kind == "complete":
            self.__complete_tag = tag_name
        elif kind == "ignore":
            self.__ignore_tag = tag_name
        else:
            self.__prune_tag = tag_name
        self.__persist_tags()

    def cb_tag_one(self, _item, kind, link_type, handle):
        """Apply one kind of tag to a single Person or Family."""
        tag_name, color, is_default = self.__tag_for_kind(kind)
        objects = {"Person": [], "Family": []}
        objects[link_type].append(handle)
        self.__apply_tag_batch(objects, tag_name, color)
        if is_default:
            self.__remember_tag(kind, tag_name)
        self.update()

    def cb_batch_complete(self, _button):
        """Tag every shown Person and Family as Complete."""
        self.__batch_tag("complete")

    def cb_batch_ignore(self, _button):
        """Tag every shown Person and Family as Ignore."""
        self.__batch_tag("ignore")

    def cb_batch_prune(self, _button):
        """Tag every shown Person and Family as Prune."""
        self.__batch_tag("prune")

    def __batch_tag(self, kind):
        """Apply one kind of tag to all currently shown objects."""
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

    def __get_or_create_tag(self, tag_name, color, trans):
        """
        Return the handle of the named tag, creating it at the top of the
        tag list (with the given color) when it does not exist yet.
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

    def __apply_tag_batch(self, objects, tag_name, color):
        """
        Add one tag to the given People and Families in a single transaction,
        creating the tag if needed. objects is {"Person": [handles], "Family":
        [handles]}. The caller refreshes the list afterwards.
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

    def __on(self, key):
        """Is this tree data integrity test switched on?"""
        return self.__checks.get(key, False)

    def __clear_links(self):
        """
        Forget the clickable links of the previous list.

        Gramps core keeps every link a gramplet has ever shown (the list in
        the gramplet pane is never emptied), so a gramplet that refreshes
        often makes mouse movement over its text slower and slower. Core
        has no method for this, so the pane's list is emptied here.
        """
        gui = self.gui
        tags = getattr(gui, "_tags", None)
        if not tags:
            return
        try:
            tag_table = gui.buffer.get_tag_table()
            for link_data in tags:
                tag_table.remove(link_data[0])
        except Exception:  # never let housekeeping stop the gramplet
            pass
        gui._tags = []

    def __trace(self, where):
        """Quota-counter trace line, shown only when show_diagnostic is on."""
        if show_diagnostic:
            self.append_text(
                f"[{where}: {self.__counter}/{self.__todos_wanted}]\n"
            )

    def main(self):
        """
        Build the list.

        This is a generator: Gramps runs it a little at a time while idle,
        so the window stays responsive, and a newer refresh request stops
        an unfinished search instead of waiting for it.
        """
        self.__clear_links()

        # Fail gracefully if no database is loaded; warn or no entry ⚠ ☡ ⛔ 🚫 🛑 🚧 🚨 👣
        if not self.dbstate.db.is_open():
            self.set_text(no_tree_message(self.__show_next_steps))
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
            message = _(
                '\n ⛔ No Person has been chosen as the focal "Home Person".\n'
            )
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
        self.__shown_persons = set()
        self.__shown_families = set()

        self.__counter = 0
        self.__work = 0

        self.set_text("")
        base_message = " focal Home Person.\n"
        self.__missing_link(default_person, base_message)
        self.__counter = 0

        # Already processed persons and families, to avoid recursing
        # back down to ourselves or meeting the same person through different
        # paths.
        self.__processed_persons = {default_person.get_handle()}
        self.__processed_families = set()

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
        families = []
        families_queue = [[] for i in range(self.__ancestor_delay)]

        # List of spouses to add to ancestors list so we track ancestors of
        # spouses, too, but delayed as defined by the parameter.
        spouses = []
        spouses_queue = []

        while ancestors or families:
            # (Other) families of parents
            for ancestor_group in ancestors_queue.pop(0):
                new_family_group = []
                new_spouses_group = []
                for person in ancestor_group:
                    for family in self.__get_families(person):
                        spouse = self.__get_spouse(person, family)
                        if spouse is UnknownPerson:
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

                for down in range(self.__downs_per_up):
                    new_families = []
                    for family_group in families:
                        children = []
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
                                if spouse is UnknownPerson:
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
                new_ancestor_group_1 = []
                new_ancestor_group_2 = []
                new_family_group = []
                for person in ancestor_group:
                    (father, mother, family) = self.__get_parents(person)
                    if family is UnknownFamily:
                        self.__missing_parents(person)
                    elif family is not None:
                        if father is UnknownPerson:
                            self.__missing_father(person)
                        elif father is not None:
                            self.__process_person(father, new_ancestor_group_1)
                        if mother is UnknownPerson:
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
    def __person_name(self, person):
        name = name_displayer.display_name(person.get_primary_name())
        return name or _("(person with unknown name)")

    def __partner_name(self, person):
        if person is UnknownPerson or person is None:
            return _("(unknown person)")
        return name_displayer.display(person) or _("(person with unknown name)")

    def __family_name(self, person1, person2):
        return _("%(name1)s and %(name2)s") % {
            "name1": self.__partner_name(person1),
            "name2": self.__partner_name(person2),
        }

    def __report(self, name, link_type, handle, missingbits):
        self.link(name, link_type, handle)
        self.append_text(
            _(": %(list)s\n") % {"list": _(", ").join(missingbits)}
        )  # Arabic OK
        if link_type == "Person":
            self.__shown_persons.add(handle)
        else:
            self.__shown_families.add(handle)
        self.__counter += 1

    # ------------------------------------------------------------------
    # Tests on people
    # ------------------------------------------------------------------
    def __process_person(self, person, append_list):

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

        primary_name = person.get_primary_name()

        if self.__on("first_name") and not primary_name.get_first_name():
            missingbits.append(_("first name unknown"))

        if self.__on("surname") and not primary_name.get_surname():
            missingbits.append(_("surname unknown"))

        has_birth = self.__person_events(person, missingbits)

        if not has_birth and self.__on("birth_missing"):
            base_message = _("Birth event missing.")
            suggestion_message = _("Add via the Events tab of the Edit Person dialog.")
            if self.__show_next_steps:
                base_message = f"{base_message}\n  👣{suggestion_message}\n"
            missingbits.append(base_message)

        if missingbits:
            self.__report(self.__person_name(person), "Person", handle, missingbits)

        append_list.append(person)

    def __person_events(self, person, missingbits):
        """
        Examine the Birth and Death events. Returns True if the person has
        a Birth event.

        Normally only the preferred Birth and Death events are fetched (two
        database reads at most). Every Primary-role event is read only when
        the "alternate_events" test is on, or when no preferred Birth is set
        and the event list has to be searched for one.
        """
        db = self.dbstate.db
        birth_ref = person.get_birth_ref()

        if self.__on("alternate_events") or birth_ref is None:
            has_birth = False
            for event_ref in person.get_primary_event_ref_list():
                event = db.get_event_from_handle(event_ref.ref)
                event_type = event.get_type()
                if event_type == EventType.BIRTH:
                    has_birth = True
                    if self.__on("birth_event"):
                        missingbits.extend(self.__process_event(event))
                elif event_type == EventType.DEATH:
                    if self.__on("death_event"):
                        missingbits.extend(self.__process_event(event))
            return has_birth

        if self.__on("birth_event"):
            event = db.get_event_from_handle(birth_ref.ref)
            missingbits.extend(self.__process_event(event))

        if self.__on("death_event"):
            death_ref = person.get_death_ref()
            if death_ref is not None:
                event = db.get_event_from_handle(death_ref.ref)
                missingbits.extend(self.__process_event(event))

        return True

    # ------------------------------------------------------------------
    # Tests on families
    # ------------------------------------------------------------------
    def __process_family(self, family, person1, person2, append_list):

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

        has_marriage = False

        for event_ref in family.get_event_ref_list():
            event = self.dbstate.db.get_event_from_handle(event_ref.ref)
            event_type = event.get_type()
            if event_type == EventType.MARRIAGE:
                has_marriage = True
                if self.__on("marriage_event"):
                    missingbits.extend(self.__process_event(event))
            elif event_type == EventType.DIVORCE:
                if self.__on("divorce_event"):
                    missingbits.extend(self.__process_event(event))

        relationship = family.get_relationship()
        if relationship == FamilyRelType.MARRIED:
            if not has_marriage and self.__on("marriage_missing"):
                missingbits.append(_("marriage event missing"))
        elif relationship == FamilyRelType.UNKNOWN:
            if self.__on("relationship_unknown"):
                missingbits.append(_("relationship type unknown"))

        if missingbits:
            self.__report(
                self.__family_name(person1, person2), "Family", handle, missingbits
            )

        append_list.append((family, person1, person2))

    # ------------------------------------------------------------------
    # Tests on an event
    # ------------------------------------------------------------------
    def __process_event(self, event):

        missingbits = []

        date = event.get_date_object()
        if date.is_empty():
            if self.__on("date_unknown"):
                missingbits.append(_("date unknown"))
        elif not date.is_regular():
            if self.__on("date_incomplete"):
                missingbits.append(_("date incomplete"))

        if self.__on("place_unknown") and not event.get_place_handle():
            missingbits.append(_("place unknown for the Event"))

        if missingbits:
            # translators: needed for French, ignore otherwise
            return [
                _("%(str1)s: %(str2)s")
                % {"str1": event.get_type(), "str2": _(", ").join(missingbits)}
            ]  # Arabic OK
        else:
            return []

    # ------------------------------------------------------------------
    # Tests on links between people
    # ------------------------------------------------------------------
    def __missing_spouse(self, person):
        if self.__on("spouse_missing") and not self.__suppressed(person):
            self.__missing_link(
                person, _("A partner relationship exists but the spouse is missing")
            )
        # suggestion (not shown yet):
        # _("Add missing partner using the Edit Family dialog.")

    def __missing_father(self, person):
        if self.__on("father_missing") and not self.__suppressed(person):
            self.__missing_link(person, _("Father missing from the parent family"))

    def __missing_mother(self, person):
        if self.__on("mother_missing") and not self.__suppressed(person):
            self.__missing_link(person, _("Mother missing from the parent family"))

    def __missing_parents(self, person):
        if self.__on("parents_missing") and not self.__suppressed(person):
            self.__missing_link(person, _("Parent family is unknown."))
        # suggestion (not shown yet):
        # _('"Add New/Existing Parents" from the Edit menu of the'
        #   " Relationships view.")

    def __missing_link(self, person, text):

        name = name_displayer.display(person)
        self.link(name, "Person", person.get_handle())
        self.append_text(_(": %s\n") % text)
        self.__shown_persons.add(person.get_handle())
        self.__trace("Missing Link")
        self.__counter += 1

    # ------------------------------------------------------------------
    # Walking the tree
    # ------------------------------------------------------------------
    def __handle_for(self, tag_name):
        """Return the handle of a configured tag by name, or None."""
        if not tag_name:
            return None
        tag = self.dbstate.db.get_tag_from_name(tag_name)
        return tag.get_handle() if tag is not None else None

    def __pruned(self, obj):
        """Pruned objects are not travelled through by the search."""
        return (
            self.__prune_handle is not None
            and self.__prune_handle in obj.get_tag_list()
        )

    def __suppressed(self, obj):
        """
        Complete or Ignore objects are hidden from the list, but the search
        still travels through them.
        """
        tags = obj.get_tag_list()
        return (
            self.__complete_handle is not None and self.__complete_handle in tags
        ) or (self.__ignore_handle is not None and self.__ignore_handle in tags)

    def __get_spouse(self, person, family):

        spouse_handle = utils.find_spouse(person, family)
        if not spouse_handle:
            if family.get_relationship() == FamilyRelType.MARRIED:
                return UnknownPerson
            else:
                return None
        spouse = self.dbstate.db.get_person_from_handle(spouse_handle)
        if self.__pruned(spouse):
            return None
        else:
            return spouse

    def __get_children(self, family):

        for child_ref in family.get_child_ref_list():
            # Someone already examined would be skipped anyway, so do not
            # read that person from the database again.
            if child_ref.ref in self.__processed_persons:
                continue
            child = self.dbstate.db.get_person_from_handle(child_ref.ref)
            if self.__pruned(child):
                continue
            yield child

    def __get_families(self, person):

        for family_handle in person.get_family_handle_list():
            if family_handle in self.__processed_families:
                continue
            family = self.dbstate.db.get_family_from_handle(family_handle)
            if self.__pruned(family):
                continue
            yield family

    def __get_parents(self, person):

        family_handle = person.get_main_parents_family_handle()
        if not family_handle:
            return (UnknownPerson, UnknownPerson, UnknownFamily)
        if family_handle in self.__processed_families:
            return (None, None, None)

        family = self.dbstate.db.get_family_from_handle(family_handle)
        if self.__pruned(family):
            return (None, None, None)

        father_handle = family.get_father_handle()
        if not father_handle:
            if family.get_relationship() == FamilyRelType.MARRIED:
                father = UnknownPerson
            else:
                father = None
        else:
            father = self.dbstate.db.get_person_from_handle(father_handle)
            if self.__pruned(father):
                father = None

        mother_handle = family.get_mother_handle()
        if not mother_handle:
            mother = UnknownPerson
        else:
            mother = self.dbstate.db.get_person_from_handle(mother_handle)
            if self.__pruned(mother):
                mother = None

        return (father, mother, family)


class UnknownPersonClass:
    pass


class UnknownFamilyClass:
    pass


UnknownPerson = UnknownPersonClass()
UnknownFamily = UnknownFamilyClass()
