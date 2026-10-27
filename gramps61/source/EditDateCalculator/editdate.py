#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2002-2006  Donald N. Allingham
# Copyright (C) 2009       Douglas S. Blank
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

"""
Date editing module for Gramps.

The EditDate provides visual feedback to the user to indicate if
the associated GtkEntry box contains a valid date.
Red means that the date is not valid, and will be viewed as a text string
instead of a date.

The DateEditor provides a dialog in which the date can be
unambiguously built using UI controls such as menus and spin buttons.
"""

# -------------------------------------------------------------------------
#
# Python modules
#
# -------------------------------------------------------------------------


# -------------------------------------------------------------------------
#
# set up logging
#
# -------------------------------------------------------------------------
import logging
import re

# -------------------------------------------------------------------------
#
# GNOME modules
#
# -------------------------------------------------------------------------
from gi.repository import GLib, GObject, Gtk, Pango

# -------------------------------------------------------------------------
#
# gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.config import config
from gramps.gen.lib.date import Date, DateError, calendar_has_fixed_newyear, Today
from gramps.gen.datehandler import displayer
from gramps.gen.const import URL_MANUAL_SECT1
from ..display import display_help
from ..managedwindow import ManagedWindow
from ..glade import Glade
from ..widgets.datecalculator import DateCalculatorPanel

try:
    from ..widgets.markdown_render import render_md, setup_tags
except ImportError:
    # markdown_render only exists in some forks of Gramps.  Fall back to a
    # minimal stand-in that understands **bold** and `code`.
    def setup_tags(buf):
        """Create the text tags used by render_md."""
        buf.create_tag("bold", weight=Pango.Weight.BOLD)
        buf.create_tag("code", family="monospace")

    def render_md(text, buf, links):
        """Insert text into buf, honouring **bold** and `code`."""
        for part in re.split(r"(\*\*.+?\*\*|`.+?`)", text):
            if len(part) > 4 and part.startswith("**") and part.endswith("**"):
                buf.insert_with_tags_by_name(buf.get_end_iter(), part[2:-2], "bold")
            elif len(part) > 2 and part.startswith("`") and part.endswith("`"):
                buf.insert_with_tags_by_name(buf.get_end_iter(), part[1:-1], "code")
            elif part:
                buf.insert(buf.get_end_iter(), part)


LOG = logging.getLogger(".EditDate")
_ = glocale.translation.sgettext
# -------------------------------------------------------------------------
#
# Constants
#
# -------------------------------------------------------------------------
MOD_TEXT = (
    (Date.MOD_NONE, _("Regular")),
    (Date.MOD_BEFORE, _("Before")),
    (Date.MOD_AFTER, _("After")),
    (Date.MOD_ABOUT, _("About")),
    (Date.MOD_RANGE, _("Range")),
    (Date.MOD_FROM, _("From")),
    (Date.MOD_TO, _("To")),
    (Date.MOD_SPAN, _("Span")),
    (Date.MOD_TEXTONLY, _("Text only")),
)

QUAL_TEXT = (
    (Date.QUAL_NONE, _("Regular")),
    (Date.QUAL_ESTIMATED, _("Estimated")),
    (Date.QUAL_CALCULATED, _("Calculated")),
)

CAL_TO_MONTHS_NAMES = {
    Date.CAL_GREGORIAN: displayer.short_months,
    Date.CAL_JULIAN: displayer.short_months,
    Date.CAL_HEBREW: displayer.hebrew,
    Date.CAL_FRENCH: displayer.french,
    Date.CAL_PERSIAN: displayer.persian,
    Date.CAL_ISLAMIC: displayer.islamic,
    Date.CAL_SWEDISH: displayer.swedish,
}

WIKI_HELP_PAGE = URL_MANUAL_SECT1
WIKI_HELP_SEC = _("Editing_dates", "manual")

# Slide-out date calculator panel: width, and the tallest the dialog will
# grow (pixels) to make room for it
CALC_PANEL_WIDTH = DateCalculatorPanel.PANEL_WIDTH
CALC_PANEL_MAX_HEIGHT = 420
# what is left of the dialog's right margin once the open panel reaches into it
CALC_RIGHT_MARGIN = 7


# -------------------------------------------------------------------------
#
# EditDate
#
# -------------------------------------------------------------------------
class EditDate(ManagedWindow):
    """
    Dialog allowing to build the date precisely, to correct possible
    limitations of parsing and/or underlying structure of :class:`.Date`.
    """

    def __init__(self, date, uistate, track):
        """
        Initiate and display the dialog.
        """
        ManagedWindow.__init__(self, uistate, track, self)

        # Create self.date as a copy of the given Date object.
        self.date = Date(date)

        self.top = Glade()

        self.set_window(
            self.top.toplevel, self.top.get_object("title"), _("Date selection")
        )
        self.setup_configs("interface.editdate", 620, 320)

        self.statusbar = self.top.get_object("statusbar")
        self.ok_button = self.top.get_object("ok_button")
        self.calendar_box = self.top.get_object("calendar_box")
        for name in Date.ui_calendar_names:
            self.calendar_box.get_model().append([name])

        self.new_year = self.top.get_object("newyear")
        self.new_year.set_text(self.date.newyear_to_str())

        cal = self.date.get_calendar()
        self.calendar_box.set_active(cal)
        self.align_newyear_ui_with_calendar(cal)
        self.calendar_box.connect("changed", self.switch_calendar)

        self.info_button = self.top.get_object("info_button")
        if self.info_button is not None:
            self.info_button.connect("clicked", self.cb_show_date_syntax)

        self.quality_box = self.top.get_object("quality_box")
        for item_number, item in enumerate(QUAL_TEXT):
            self.quality_box.append_text(item[1])
            if self.date.get_quality() == item[0]:
                self.quality_box.set_active(item_number)

        self.type_box = self.top.get_object("type_box")
        for item_number, item in enumerate(MOD_TEXT):
            self.type_box.append_text(item[1])
            if self.date.get_modifier() == item[0]:
                self.type_box.set_active(item_number)
        self.type_box.connect("changed", self.switch_type)

        self.start_month_box = self.top.get_object("start_month_box")
        self.stop_month_box = self.top.get_object("stop_month_box")
        month_names = CAL_TO_MONTHS_NAMES[self.date.get_calendar()]
        for name in month_names:
            self.start_month_box.append_text(name)
            self.stop_month_box.append_text(name)
        self.start_month_box.set_active(self.date.get_month())
        self.stop_month_box.set_active(self.date.get_stop_month())

        self.start_day = self.top.get_object("start_day")
        self.start_day.set_value(self.date.get_day())
        self.start_year = self.top.get_object("start_year")
        self.start_year.set_value(self.date.get_year())

        self.stop_day = self.top.get_object("stop_day")
        self.stop_day.set_value(self.date.get_stop_day())
        self.stop_year = self.top.get_object("stop_year")
        self.stop_year.set_value(self.date.get_stop_year())

        self.dual_dated = self.top.get_object("dualdated")

        # The following is not described in the glade file.
        # glade is not for Gtk4.
        table48 = self.top.get_object("table48")
        self.first_date = Gtk.Calendar()
        self.first_date.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
            | Gtk.CalendarDisplayOptions.SHOW_HEADING
        )
        self.first_date.connect("day-selected", self.date_change_in_calendar, "start")
        self.second_date = Gtk.Calendar()
        self.second_date.set_display_options(
            Gtk.CalendarDisplayOptions.SHOW_DAY_NAMES
            | Gtk.CalendarDisplayOptions.SHOW_HEADING
        )
        self.second_date.connect("day-selected", self.date_change_in_calendar, "stop")
        table48.attach(self.first_date, 0, 6, 3, 6)
        table48.attach(self.second_date, 3, 6, 5, 6)
        self.ofdate = self.first_date.get_date()
        self.osdate = self.second_date.get_date()
        self.showcal = True

        # Disable second date controls if not compound date
        if not self.date.is_compound():
            self.stop_day.set_sensitive(0)
            self.stop_month_box.set_sensitive(0)
            self.stop_year.set_sensitive(0)
            self.second_date.set_sensitive(0)

        # Disable the rest of controls if a text-only date
        if self.date.get_modifier() == Date.MOD_TEXTONLY:
            self.start_day.set_sensitive(0)
            self.start_month_box.set_sensitive(0)
            self.start_year.set_sensitive(0)
            self.calendar_box.set_sensitive(0)
            self.quality_box.set_sensitive(0)
            self.dual_dated.set_sensitive(0)
            self.new_year.set_sensitive(0)
            self.first_date.set_sensitive(0)
            self.second_date.set_sensitive(0)

        self.text_entry = self.top.get_object("date_text_entry")
        self.text_entry.set_text(self.date.get_text())

        if self.date.get_slash():
            self.dual_dated.set_active(1)
            self.calendar_box.set_sensitive(0)
            self.calendar_box.set_active(Date.CAL_JULIAN)
        self.dual_dated.connect("toggled", self.switch_dual_dated)

        # Use the calendar from user preferences for new dates only.
        if self.date.is_empty():
            cal = config.get("preferences.calendar-format-input")
            self.calendar_box.set_active(cal)
            self.type_box.set_active(0)

        # The dialog is modal -- since dates don't have names, we don't
        # want to have several open dialogs, since then the user will
        # loose track of which is which. Much like opening files.

        self.validated_date = self.return_date = None

        for obj in self.top.get_objects():
            if obj != self.ok_button:
                for signal in ["changed", "value-changed"]:
                    try:
                        obj.connect_after(signal, self.revalidate)
                    except TypeError:
                        # some of them don't support the signal, ignore them...
                        pass
        self.revalidate()
        self._add_calculator_panel()
        self.show()

        while True:
            response = self.window.run()
            LOG.debug("response: {0}".format(response))
            if response == Gtk.ResponseType.HELP:
                display_help(webpage=WIKI_HELP_PAGE, section=WIKI_HELP_SEC)
            elif response == Gtk.ResponseType.DELETE_EVENT:
                break
            else:
                if response == Gtk.ResponseType.OK:
                    # if the user pressed OK/enter while inside an edit field,
                    # e.g., the year,
                    # build_date_from_ui won't pick up the new text in the
                    # run of revalidate that allowed the OK!
                    if not self.revalidate():
                        continue
                    self.return_date = Date()
                    self.return_date.copy(self.validated_date)
                self.close()
                break

    def _add_calculator_panel(self):
        """
        Add a slide-out date calculator on the right side of the dialog.

        The Glade-defined children of the content area are moved into a
        box, and a [original content | handle | revealer] row is placed
        above the action buttons.  The panel scrolls if the dialog is too
        short, and the dialog grows in height only while it is open.
        """
        content = self.window.get_content_area()
        action_area = self.window.get_action_area()
        keep_in_place = (action_area, action_area.get_parent())

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        for child in content.get_children():
            if child in keep_in_place:
                continue
            expand, fill, padding, pack_type = content.query_child_packing(child)
            content.remove(child)
            if pack_type == Gtk.PackType.START:
                main_box.pack_start(child, expand, fill, padding)
            else:
                main_box.pack_end(child, expand, fill, padding)

        self.calc_panel = DateCalculatorPanel(
            get_date=self.cb_calc_get_date,
            use_date=self.cb_calc_use_date,
            use_second_date=self.cb_calc_use_second_date,
        )
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_min_content_width(CALC_PANEL_WIDTH)
        scroll.set_min_content_height(1)
        scroll.add(self.calc_panel)

        panel_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        panel_box.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0
        )
        panel_box.pack_start(scroll, True, True, 0)

        self.calc_revealer = Gtk.Revealer()
        self.calc_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.calc_revealer.set_transition_duration(200)
        self.calc_revealer.add(panel_box)
        self.calc_revealer.set_reveal_child(False)
        self.calc_revealer.connect("notify::child-revealed", self.cb_calc_revealed)
        self.calc_revealer.connect("size-allocate", self.cb_calc_panel_allocated)

        # the slide-out handle: a slim, full-height toggle with an arrow
        self.calc_arrow = Gtk.Image.new_from_icon_name(
            "pan-end-symbolic", Gtk.IconSize.BUTTON
        )
        self.calc_handle = Gtk.ToggleButton()
        self.calc_handle.set_focus_on_click(False)
        self.calc_handle.set_tooltip_text(_("Show or hide the date calculator"))
        self.calc_handle.add(self.calc_arrow)
        # keep the handle slim, with a small gutter before it
        handle_css = Gtk.CssProvider()
        handle_css.load_from_data(b"button.calc-handle { padding: 0 2px; min-width: 0; }")
        handle_style = self.calc_handle.get_style_context()
        handle_style.add_class("calc-handle")
        handle_style.add_provider(handle_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.calc_handle.set_margin_start(3)
        self.calc_handle.connect("toggled", self.cb_toggle_calculator)

        self.calc_main = main_box
        self.calc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.calc_row.pack_start(main_box, True, True, 0)
        self.calc_row.pack_start(self.calc_handle, False, True, 0)
        self.calc_row.pack_start(self.calc_revealer, False, False, 0)
        content.pack_start(self.calc_row, True, True, 0)
        content.reorder_child(self.calc_row, 0)
        self._calc_grown_height = 0
        self._calc_grown_width = 0
        self._calc_bleed = 0

        # show only our own widgets; the Glade children keep their own state
        self.calc_row.show()
        main_box.show()
        self.calc_revealer.show()
        panel_box.show_all()
        self.calc_handle.show_all()

    def _calc_set_bleed(self, bleed):
        """
        Let the row reach `bleed` pixels further into the dialog's right margin.

        That margin belongs to the content area (GTK ignores negative margins
        on the row itself), so it is narrowed there, and the same room is given
        back around the action buttons, which must not move.
        """
        change = bleed - self._calc_bleed
        content = self.window.get_content_area()
        actions = self.window.get_action_area().get_parent()
        content.set_margin_end(content.get_margin_end() - change)
        actions.set_margin_end(actions.get_margin_end() + change)
        self._calc_bleed = bleed

    def _calc_freeze_main(self):
        """
        Pin the dialog's own content at its current size.

        The window is resized in one step, but the panel takes a moment to
        slide.  Without this the content would be stretched to fill the gap
        and then squashed back as the panel grows (and the reverse when the
        panel slides away).  Frozen, only the panel area changes.
        """
        alloc = self.calc_main.get_allocation()
        self.calc_main.set_size_request(alloc.width, alloc.height)
        self.calc_main.set_halign(Gtk.Align.START)
        self.calc_main.set_valign(Gtk.Align.START)
        self.calc_main.set_hexpand(False)
        self.calc_main.set_vexpand(False)
        self.calc_row.set_child_packing(
            self.calc_main, False, False, 0, Gtk.PackType.START
        )

    def _calc_thaw_main(self, keep_width=False):
        """
        Let the dialog's content follow the window size again.

        With keep_width the content's width stays pinned, so that while the
        panel is open a resized window gives its extra width to the panel
        alone.
        """
        width = self.calc_main.get_size_request()[0] if keep_width else -1
        self.calc_main.set_size_request(width, -1)
        self.calc_main.set_valign(Gtk.Align.FILL)
        self.calc_main.set_vexpand_set(False)
        if keep_width:
            return
        # the panel is gone: the row no longer needs to reach into the margin
        self._calc_set_bleed(0)
        self.calc_main.set_halign(Gtk.Align.FILL)
        self.calc_main.set_hexpand_set(False)
        if self.calc_main.get_parent() is self.calc_row:
            self.calc_row.set_child_packing(
                self.calc_main, True, True, 0, Gtk.PackType.START
            )

    def _calc_thaw_when_sized(self, width, height):
        """
        Thaw the content once the window has really shrunk to this size.

        Thawing sooner would let the content stretch for a frame.  A timeout
        thaws it anyway should the window never reach the size.
        """
        state = {}

        def finish(*_args):
            if not state.get("done"):
                state["done"] = True
                if GObject.signal_handler_is_connected(self.window, state["handler"]):
                    self.window.disconnect(state["handler"])
                self._calc_thaw_main()
            return False

        def cb_size_allocate(window, _allocation):
            win_width, win_height = window.get_size()
            if win_width <= width + 1 and win_height <= height + 1:
                GLib.idle_add(finish)

        state["handler"] = self.window.connect("size-allocate", cb_size_allocate)
        GLib.timeout_add(500, finish)

    def cb_toggle_calculator(self, button):
        """
        Slide the calculator panel in or out.  Opening makes room for it by
        growing the window; closing hands the room back in cb_calc_revealed.
        """
        opened = button.get_active()
        self.calc_arrow.set_from_icon_name(
            "pan-start-symbolic" if opened else "pan-end-symbolic",
            Gtk.IconSize.BUTTON,
        )
        grown = bool(self._calc_grown_width or self._calc_grown_height)
        if not opened:
            # (reveal first: the panel's tracked width must stop updating)
            self.calc_revealer.set_reveal_child(False)
            if grown:
                self._calc_freeze_main()
                self.calc_row.set_child_packing(
                    self.calc_revealer, False, False, 0, Gtk.PackType.START
                )
            return

        self.calc_panel.prefill_from_dialog()
        if self.window.is_maximized() or grown:
            # (grown: closed and reopened mid-slide, the window is still wide)
            self.calc_revealer.set_reveal_child(True)
            return
        self._calc_freeze_main()
        # Let the open panel reach into the dialog's right margin, so that the
        # gap left beside it is CALC_RIGHT_MARGIN (plus the panel's own padding).
        content = self.window.get_content_area()
        margin = content.get_margin_end() + content.get_border_width()
        self._calc_set_bleed(max(0, margin - CALC_RIGHT_MARGIN))
        width, height = self.window.get_size()
        self._calc_grown_width = self.calc_panel.get_preferred_width()[1] + 1
        wanted = min(self.calc_panel.get_preferred_height()[1], CALC_PANEL_MAX_HEIGHT)
        available = self.calc_row.get_allocated_height()
        self._calc_grown_height = max(0, wanted - available)
        self.window.resize(
            width + self._calc_grown_width, height + self._calc_grown_height
        )
        self.calc_revealer.set_reveal_child(True)

    def cb_calc_revealed(self, revealer, _pspec):
        """
        Called when a slide has finished.  Fully open: the content keeps its
        width (it stays pinned when we grew the window), so the panel takes
        any later resizing.  Fully closed: give the window back the room the
        panel took, and let the content flex again.

        The shrink must wait for the end of the slide animation: until then
        the panel still asks for its width, and GTK will not shrink the
        window below what its contents ask for.
        """
        if revealer.get_child_revealed():
            pinned = bool(self._calc_grown_width)
            self._calc_thaw_main(keep_width=pinned)
            if pinned:
                # the panel, not the content, now takes any later resizing
                self.calc_row.set_child_packing(
                    self.calc_revealer, True, True, 0, Gtk.PackType.START
                )
            return
        grown = self._calc_grown_width or self._calc_grown_height
        if grown and not self.window.is_maximized():
            width, height = self.window.get_size()
            target = (
                max(width - self._calc_grown_width, 1),
                max(height - self._calc_grown_height, 1),
            )
            self.window.resize(*target)
            self._calc_thaw_when_sized(*target)
        else:
            self._calc_thaw_main()
        self._calc_grown_width = 0
        self._calc_grown_height = 0

    def cb_calc_panel_allocated(self, revealer, allocation):
        """
        Once the panel is fully open, track its real width: the window may
        have been resized, and closing must hand back exactly that much.
        """
        if (
            self._calc_grown_width
            and revealer.get_reveal_child()
            and revealer.get_child_revealed()
        ):
            # (the part reaching into the dialog's margin is not window width)
            self._calc_grown_width = allocation.width - self._calc_bleed

    def _save_size(self):
        """
        Save the dialog size, leaving out the room taken by the calculator
        panel, so the stored size is always that of the closed dialog.
        """
        ManagedWindow._save_size(self)
        if self.width_key is not None and getattr(self, "_calc_grown_width", 0):
            config.set(self.width_key, config.get(self.width_key) - self._calc_grown_width)
            config.set(
                self.height_key, config.get(self.height_key) - self._calc_grown_height
            )
            config.save()

    def cb_calc_get_date(self):
        """
        Return the date as currently built in the dialog (or None).
        """
        return self.validated_date

    def cb_calc_use_date(self, date):
        """
        Result to Date: load a date computed by the calculator into the
        dialog's Date fields.

        A simple date leaves a Range or Span as it is, second date included.
        """
        modifier_index = 0
        for index, (modifier, dummy_text) in enumerate(MOD_TEXT):
            if modifier == date.get_modifier():
                modifier_index = index
        quality_index = 0
        for index, (quality, dummy_text) in enumerate(QUAL_TEXT):
            if quality == date.get_quality():
                quality_index = index
        keep_second = not date.is_compound() and (
            MOD_TEXT[self.type_box.get_active()][0] in (Date.MOD_RANGE, Date.MOD_SPAN)
        )

        # A dual date forces the Julian calendar, so handle it first.
        self.dual_dated.set_active(bool(date.get_slash()))
        if not date.get_slash():
            # repopulates the month names if the calendar changes
            self.calendar_box.set_active(date.get_calendar())
        if not keep_second:
            self.type_box.set_active(modifier_index)
        self.quality_box.set_active(quality_index)

        self.start_day.set_value(date.get_day())
        self.start_month_box.set_active(date.get_month())
        self.start_year.set_value(date.get_year())
        if not keep_second:
            self.stop_day.set_value(date.get_stop_day())
            self.stop_month_box.set_active(date.get_stop_month())
            self.stop_year.set_value(date.get_stop_year())
        self.new_year.set_text(date.newyear_to_str())
        self.revalidate()

    def cb_calc_use_second_date(self, date):
        """
        Result to Second Date: copy a date computed by the calculator into
        the dialog's Second date fields.  Unless the Type is already a Range
        or Span, it becomes Span.
        """
        calendar = self.calendar_box.get_active()
        second = Date(date)
        if second.get_calendar() != calendar:
            second.convert_calendar(calendar)
        if MOD_TEXT[self.type_box.get_active()][0] not in (
            Date.MOD_RANGE,
            Date.MOD_SPAN,
        ):
            for index, (modifier, dummy_text) in enumerate(MOD_TEXT):
                if modifier == Date.MOD_SPAN:
                    self.type_box.set_active(index)
        self.stop_day.set_value(second.get_day())
        self.stop_month_box.set_active(second.get_month())
        self.stop_year.set_value(second.get_year())
        self.revalidate()

    def show_on_calendar(self, calendar, date):
        if self.calendar_box.get_active() != Date.CAL_GREGORIAN:
            return
        if date.is_empty():
            return
        date = date.to_calendar("gregorian")
        year = date.get_year()
        if year < 0:  # Gtk.Calendar only works for positive years
            date = Today()
            year = date.get_year()
        month = date.get_month()
        if month > 0 and month < 13:
            month -= 1
        else:
            month = 0
        if not self.showcal:
            # not set a date for any calendar other than the Gregorian calendar
            # only true after calendar change
            return
        calendar.select_month(month, date.get_year())
        calendar.select_day(date.get_day())

    def date_change_in_calendar(self, calendar, date):
        if self.calendar_box.get_active() != Date.CAL_GREGORIAN:
            return
        current = calendar.get_date()
        if date == "start" and current == self.ofdate:
            return False
        elif current == self.osdate:
            return False
        newdate = Date(current.year, current.month + 1, current.day)
        newdate = newdate.to_calendar(self.calendar_box.get_active())
        if date == "start":
            if self.ofdate.day != current.day:
                self.start_day.set_value(newdate.get_day())
            if self.ofdate.month != current.month:
                self.start_month_box.set_active(newdate.get_month())
            if self.ofdate.year != current.year:
                self.start_year.set_value(newdate.get_year())
            self.ofdate = current
        else:
            if self.osdate.day != current.day:
                self.stop_day.set_value(newdate.get_day())
            if self.osdate.month != current.month:
                self.stop_month_box.set_active(newdate.get_month())
            if self.osdate.year != current.year:
                self.stop_year.set_value(newdate.get_year())
            self.osdate = current

    def revalidate(self, obj=None):
        """
        If anything changed, revalidate the date and
        enable/disable the "OK" button based on the result.
        """
        (
            the_quality,
            the_modifier,
            the_calendar,
            the_value,
            the_text,
            the_newyear,
        ) = self.build_date_from_ui()
        LOG.debug("revalidate: {0} changed, value: {1}".format(obj, the_value))
        dat = Date(self.date)
        if not self.ok_button.get_sensitive():
            self.statusbar.pop(1)
        try:
            dat.set(
                quality=the_quality,
                modifier=the_modifier,
                calendar=the_calendar,
                value=the_value,
                text=the_text,
                newyear=the_newyear,
            )
            # didn't throw yet?
            self.validated_date = dat
            LOG.debug("validated_date set to: {0}".format(dat.__dict__))
            self.ok_button.set_sensitive(1)
            self.calendar_box.set_sensitive(1)
            if self.calendar_box.get_active() == Date.CAL_GREGORIAN:
                self.first_date.set_sensitive(1)
            else:
                self.first_date.set_sensitive(0)
            return True
        except DateError as dummy_err:
            self.ok_button.set_sensitive(0)
            self.calendar_box.set_sensitive(0)
            curmode = MOD_TEXT[self.type_box.get_active()][1]
            txtmode = MOD_TEXT[-1][1]
            self.statusbar.push(
                1,
                _(
                    "Correct the date or switch from `{cur_mode}'" " to `{text_mode}'"
                ).format(cur_mode=curmode, text_mode=txtmode),
            )
            return False

    def build_menu_names(self, obj):
        """
        Define the menu entry for the :class:`.ManagedWindow`
        """
        return (_("Date selection"), None)

    def build_date_from_ui(self):
        """
        Collect information from the UI controls and return
        5-tuple of (quality,modifier,calendar,value,text)
        """
        # It is important to not set date based on these controls.
        # For example, changing the caledar makes the date inconsistent
        # until the callback of the calendar menu is finished.
        # We need to be able to use this function from that callback,
        # so here we just report on the state of all widgets, without
        # actually modifying the date yet.
        modifier = MOD_TEXT[self.type_box.get_active()][0]
        text = self.text_entry.get_text()

        if modifier == Date.MOD_TEXTONLY:
            return (
                Date.QUAL_NONE,
                Date.MOD_TEXTONLY,
                Date.CAL_GREGORIAN,
                Date.EMPTY,
                text,
                Date.NEWYEAR_JAN1,
            )

        quality = QUAL_TEXT[self.quality_box.get_active()][0]

        new_cal = self.calendar_box.get_active()

        if modifier in (Date.MOD_RANGE, Date.MOD_SPAN):
            value = (
                self.start_day.get_value_as_int(),
                self.start_month_box.get_active(),
                self.start_year.get_value_as_int(),
                self.dual_dated.get_active(),
                self.stop_day.get_value_as_int(),
                self.stop_month_box.get_active(),
                self.stop_year.get_value_as_int(),
                self.dual_dated.get_active(),
            )
            if self.calendar_box.get_active() == Date.CAL_GREGORIAN:
                dat1 = Date()
                dat1.set_yr_mon_day(
                    self.start_year.get_value_as_int(),
                    self.start_month_box.get_active(),
                    self.start_day.get_value_as_int(),
                )
                dat1.set_calendar(new_cal)
                self.show_on_calendar(self.first_date, dat1)
                dat2 = Date()
                dat2.set_yr_mon_day(
                    self.stop_year.get_value_as_int(),
                    self.stop_month_box.get_active(),
                    self.stop_day.get_value_as_int(),
                )
                dat2.set_calendar(new_cal)
                self.show_on_calendar(self.second_date, dat2)
        else:
            value = (
                self.start_day.get_value_as_int(),
                self.start_month_box.get_active(),
                self.start_year.get_value_as_int(),
                self.dual_dated.get_active(),
            )
            if self.calendar_box.get_active() == Date.CAL_GREGORIAN:
                dat1 = Date()
                dat1.set_calendar(self.calendar_box.get_active())
                dat1.set_yr_mon_day(
                    self.start_year.get_value_as_int(),
                    self.start_month_box.get_active(),
                    self.start_day.get_value_as_int(),
                )
                dat1.set_calendar(new_cal)
                self.show_on_calendar(self.first_date, dat1)

        calendar = self.calendar_box.get_active()
        newyear = Date.newyear_to_code(self.new_year.get_text())
        return (quality, modifier, calendar, value, text, newyear)

    def switch_type(self, obj):
        """
        Disable/enable various date controls depending on the date
        type selected via the menu.
        """

        the_modifier = MOD_TEXT[self.type_box.get_active()][0]

        # Disable/enable second date controls based on whether
        # the type allows compound dates
        if the_modifier in (Date.MOD_RANGE, Date.MOD_SPAN):
            stop_date_sensitivity = 1
            start_date_sensitivity = 1
        elif the_modifier == Date.MOD_TEXTONLY:
            stop_date_sensitivity = 0
            start_date_sensitivity = 0
        else:
            if self.calendar_box.get_active() != Date.CAL_GREGORIAN:
                start_date_sensitivity = 0
            else:
                start_date_sensitivity = 1
            stop_date_sensitivity = 0
        self.stop_day.set_sensitive(stop_date_sensitivity)
        self.stop_month_box.set_sensitive(stop_date_sensitivity)
        self.stop_year.set_sensitive(stop_date_sensitivity)
        self.second_date.set_sensitive(stop_date_sensitivity)
        self.first_date.set_sensitive(start_date_sensitivity)

        # Disable/enable the rest of the controls if the type is text-only.
        date_sensitivity = not the_modifier == Date.MOD_TEXTONLY
        self.start_day.set_sensitive(date_sensitivity)
        self.start_month_box.set_sensitive(date_sensitivity)
        self.start_year.set_sensitive(date_sensitivity)
        self.calendar_box.set_sensitive(date_sensitivity)
        self.quality_box.set_sensitive(date_sensitivity)
        self.dual_dated.set_sensitive(date_sensitivity)
        self.new_year.set_sensitive(date_sensitivity)

    def switch_dual_dated(self, obj):
        """
        Changed whether this is a dual dated year, or not.
        Dual dated years are represented in the Julian calendar
        so that the day/months don't changed in the Text representation.
        """
        if self.dual_dated.get_active():
            self.calendar_box.set_active(Date.CAL_JULIAN)
            self.calendar_box.set_sensitive(0)
        else:
            self.calendar_box.set_sensitive(1)

    def align_newyear_ui_with_calendar(self, cal):
        if calendar_has_fixed_newyear(cal):
            LOG.debug("new year disabled for cal {0}".format(cal))
            self.new_year.set_sensitive(0)
            self.new_year.set_text("")
        else:
            LOG.debug("new year enabled for cal {0}".format(cal))
            self.new_year.set_sensitive(1)

    def switch_calendar(self, obj):
        """
        Change month names and convert the date based on the calendar
        selected via the menu.
        """

        old_cal = self.date.get_calendar()
        new_cal = self.calendar_box.get_active()
        LOG.debug(
            ">>>switch_calendar: {0} changed, {1} -> {2}".format(obj, old_cal, new_cal)
        )

        if new_cal == Date.CAL_GREGORIAN:
            self.first_date.set_sensitive(1)
            self.second_date.set_sensitive(1)
            self.showcal = True
        else:
            self.showcal = False
            self.first_date.set_sensitive(0)
            self.second_date.set_sensitive(0)
        self.align_newyear_ui_with_calendar(new_cal)

        (
            the_quality,
            the_modifier,
            dummy_the_calendar,
            the_value,
            the_text,
            the_newyear,
        ) = self.build_date_from_ui()
        try:
            self.date.set(
                quality=the_quality,
                modifier=the_modifier,
                calendar=old_cal,
                value=the_value,
                text=the_text,
                newyear=the_newyear,
            )
        except DateError:
            pass
        else:
            if not self.date.is_empty():
                self.date.convert_calendar(new_cal)

        self.start_month_box.get_model().clear()
        self.stop_month_box.get_model().clear()
        month_names = CAL_TO_MONTHS_NAMES[new_cal]
        for name in month_names:
            self.start_month_box.append_text(name)
            self.stop_month_box.append_text(name)

        self.start_day.set_value(self.date.get_day())
        self.start_month_box.set_active(self.date.get_month())
        self.start_year.set_value(self.date.get_year())
        self.stop_day.set_value(self.date.get_stop_day())
        self.stop_month_box.set_active(self.date.get_stop_month())
        self.stop_year.set_value(self.date.get_stop_year())
        LOG.debug(
            "<<<switch_calendar: {0} changed, {1} -> {2}".format(obj, old_cal, new_cal)
        )

    @classmethod
    def get_help_topics(cls) -> list[dict]:
        """Return help topics describing date entry syntax for this locale."""
        return [
            {
                "title": _("Calendar"),
                # fmt: off
                # Translators: this string may contain markdown formatting; preserve it
                "body": _("Choose the calendar system: **Gregorian**, **Julian**, "
                          "**Hebrew**, **French Republican**, **Persian**, **Islamic**, "
                          "or **Swedish**. "
                          "The selector is disabled when the date type is "
                          "**Free text**, when **Dual dated** is active, or when "
                          "the date contains a validation error (shown in the "
                          "status bar at the bottom of this dialog)."),
                # fmt: on
            },
            {
                "title": _("Dual-dated dates"),
                # fmt: off
                # Translators: this string may contain markdown formatting; preserve it
                "body": _("Slash dates such as `Jan 23, 1735/6` mark a historic transition "
                          "between New Year conventions (e.g., March 25 vs. January 1). "
                          "Enter a slash between years to create one: `1721/2`, `1719/20`, "
                          "`1799/800`. Dual-dated dates use the Julian calendar. "
                          "An alternate New Year day can be added in parentheses after "
                          "the calendar name: `Jan 20, 1750 (Julian,Mar25)` or "
                          "`Feb 23, 1710/1 (Mar25)`. Valid New Year codes: "
                          "`Jan1`, `Mar1`, `Mar25`, `Sep1`."),
                # fmt: on
            },
            {
                "title": _("Date entry syntax for this locale"),
                "examples": cls._build_date_examples(),
            },
        ]

    @staticmethod
    def _build_date_examples() -> list[tuple[str, str]]:
        """Build list of (description, example) pairs for the current locale displayer."""

        def make(
            yr: int,
            mon: int = 0,
            day: int = 0,
            mod: int = Date.MOD_NONE,
            qual: int = Date.QUAL_NONE,
            cal: int = Date.CAL_GREGORIAN,
            yr2: int = 0,
            mon2: int = 0,
            day2: int = 0,
        ) -> Date:
            """Create a Date object with the given parameters."""
            d = Date()
            value: (
                tuple[int, int, int, bool, int, int, int, bool]
                | tuple[int, int, int, bool]
            )
            if mod in (Date.MOD_RANGE, Date.MOD_SPAN):
                value = (day, mon, yr, False, day2, mon2, yr2, False)
            else:
                value = (day, mon, yr, False)
            d.set(
                quality=qual,
                modifier=mod,
                calendar=cal,
                value=value,
                text="",
                newyear=Date.NEWYEAR_JAN1,
            )
            return d

        text_date = Date()
        text_date.set(
            quality=Date.QUAL_NONE,
            modifier=Date.MOD_TEXTONLY,
            calendar=Date.CAL_GREGORIAN,
            value=Date.EMPTY,
            text=_("sometime in the 1800s"),
            newyear=Date.NEWYEAR_JAN1,
        )

        rows: list[tuple[str, Date]] = [
            (_("Year only"), make(1800)),
            (_("Month and year"), make(1800, mon=3)),
            (_("Full date"), make(1800, mon=3, day=15)),
            (_("Before"), make(1800, mod=Date.MOD_BEFORE)),
            (_("After"), make(1800, mod=Date.MOD_AFTER)),
            (_("About/circa"), make(1800, mod=Date.MOD_ABOUT)),
            (_("Estimated"), make(1800, qual=Date.QUAL_ESTIMATED)),
            (_("Calculated"), make(1800, qual=Date.QUAL_CALCULATED)),
            (
                _("Estimated, before"),
                make(1800, mod=Date.MOD_BEFORE, qual=Date.QUAL_ESTIMATED),
            ),
            (
                _("Calculated, after"),
                make(1800, mod=Date.MOD_AFTER, qual=Date.QUAL_CALCULATED),
            ),
            (_("Span (from/to)"), make(1800, mod=Date.MOD_SPAN, yr2=1810)),
            (_("Range (between/and)"), make(1800, mod=Date.MOD_RANGE, yr2=1810)),
            (_("Julian calendar"), make(1800, mon=2, day=10, cal=Date.CAL_JULIAN)),
            (_("Hebrew calendar"), make(5780, mon=1, day=1, cal=Date.CAL_HEBREW)),
            (_("French Republican"), make(10, mon=3, day=1, cal=Date.CAL_FRENCH)),
            (_("Persian calendar"), make(1400, mon=1, cal=Date.CAL_PERSIAN)),
            (_("Islamic calendar"), make(1400, mon=1, cal=Date.CAL_ISLAMIC)),
            (_("Swedish calendar"), make(1712, mon=3, cal=Date.CAL_SWEDISH)),
            (_("Text only"), text_date),
        ]
        return [(desc, displayer.display(d)) for desc, d in rows]

    def cb_show_date_syntax(self, obj: Gtk.Button) -> None:
        """Show a popover rendering the help topics for the current locale."""
        popover = Gtk.Popover()
        popover.set_relative_to(self.info_button)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        vbox.set_margin_top(12)
        vbox.set_margin_bottom(12)
        vbox.set_margin_start(12)
        vbox.set_margin_end(12)

        for i, topic in enumerate(self.get_help_topics()):
            if i > 0:
                vbox.pack_start(Gtk.Separator(), False, False, 4)

            lbl = Gtk.Label()
            lbl.set_markup("<b>" + topic["title"] + "</b>")
            lbl.set_xalign(0)
            vbox.pack_start(lbl, False, False, 0)

            if "body" in topic:
                buf = Gtk.TextBuffer()
                setup_tags(buf)
                links: list = []
                render_md(topic["body"], buf, links)
                tv = Gtk.TextView(buffer=buf)
                tv.set_editable(False)
                tv.set_cursor_visible(False)
                tv.set_wrap_mode(Gtk.WrapMode.WORD)
                tv.set_size_request(450, -1)
                vbox.pack_start(tv, False, False, 0)

            if "examples" in topic:
                store = Gtk.ListStore(str, str)
                for description, example in topic["examples"]:
                    store.append([description, example])

                view = Gtk.TreeView(model=store)
                view.set_headers_visible(True)
                view.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)

                renderer1 = Gtk.CellRendererText()
                renderer1.set_padding(6, 2)
                col1 = Gtk.TreeViewColumn(_("What to express"), renderer1, text=0)
                col1.set_expand(True)
                view.append_column(col1)

                renderer2 = Gtk.CellRendererText()
                renderer2.set_padding(6, 2)
                col2 = Gtk.TreeViewColumn(_("Example"), renderer2, text=1)
                col2.set_expand(True)
                view.append_column(col2)

                scroll = Gtk.ScrolledWindow()
                scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
                scroll.set_min_content_height(300)
                scroll.set_min_content_width(450)
                scroll.add(view)

                vbox.pack_start(scroll, True, True, 0)

        popover.add(vbox)
        popover.show_all()
        popover.popup()
