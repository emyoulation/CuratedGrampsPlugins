#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
"""
PR2296 Live Preferences -- a "monkey patch" addon.

1. Applies these Preferences immediately instead of after a restart:
   - Data tab: Date format, Age display precision,
     Display ages for events after death
   - General tab: Show text label beside Navigator buttons
2. Field-tests Gramps PR 2296: the Date format drop-down shows a rendered
   example of each format (2001-04-21, the first Gramps release).

How the live switching works (core reads each value only once):
- Date format: the global date displayers are changed in place with
  set_format(); every _display_* method reads self.format at call time.
- Age settings: the module globals in eventrefmodel and the Events gramplet
  are updated; RelationshipView.age_precision becomes a live property.
- Navigator text: the existing sidebar buttons get their label shown/hidden
  (created if missing) and the icon resized, matching the core sidebars.
Open views and gramplets are then rebuilt (inactive ones are marked dirty).
"""

import functools
import logging
import sys

from gi.repository import GLib, Gtk

from gramps.gen import datehandler
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.datehandler import get_date_formats
from gramps.gen.lib import Date

LOG = logging.getLogger(".PR2296_LivePreferences")

# Core strings only: reuse the translations Gramps already ships.
_ = glocale.translation.gettext

DATE_KEY = "preferences.date-format"
PREC_KEY = "preferences.age-display-precision"
DEATH_KEY = "preferences.age-after-death"
SIDEBAR_KEY = "interface.sidebar-text"

# PR 2296: two-digit month and a day > 12, so every format looks different.
EXAMPLE_DATE = Date(2001, 4, 21)

_STATE = {"installed": False, "uistate": None, "refresh_id": 0}


# ------------------------------------------------------------
#
# Entry point
#
# ------------------------------------------------------------
def load_on_reg(dbstate, uistate, plugin):
    """Called by the plugin manager at startup (and on addon rescans)."""
    if uistate is None or _STATE["installed"]:
        return []  # CLI session, or already patched
    _STATE["installed"] = True
    _STATE["uistate"] = uistate

    _patch_preferences_dialog()
    config.connect(DATE_KEY, cb_date_format_changed)
    config.connect(PREC_KEY, cb_age_changed)
    config.connect(DEATH_KEY, cb_age_changed)
    config.connect(SIDEBAR_KEY, cb_sidebar_text_changed)
    LOG.debug("PR2296_LivePreferences installed")
    return []


# ------------------------------------------------------------
#
# Config callbacks (signature: config, cnxn_id, entry, data)
#
# ------------------------------------------------------------
def cb_date_format_changed(*_args):
    """Switch the global date displayers to the new format."""
    value = config.get(DATE_KEY)
    for displayer in (datehandler.displayer, glocale.date_displayer):
        try:
            displayer.set_format(value)
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Could not set date format on %r", displayer, exc_info=True)
    _schedule_refresh()


def cb_age_changed(*_args):
    """Push the age settings into the modules that cached them at import."""
    precision = config.get(PREC_KEY)
    after_death = config.get(DEATH_KEY)

    from gramps.gui.editors.displaytabs import eventrefmodel

    eventrefmodel.age_precision = precision
    eventrefmodel.age_after_death = after_death

    # Built-in plugins are imported by bare module name (e.g. "events"),
    # so find them by file path.
    for module in _modules_ending_with("plugins/gramplet/events.py"):
        module.age_precision = precision
    for module in _modules_ending_with("plugins/view/relview.py"):
        _patch_relview(module)

    _schedule_refresh()


def cb_sidebar_text_changed(*_args):
    """Show or hide the text beside the Navigator buttons."""
    use_text = config.get(SIDEBAR_KEY)
    viewmanager = getattr(_STATE["uistate"], "viewmanager", None)
    navigator = getattr(viewmanager, "navigator", None)
    if navigator is None:
        return
    for widget in _walk(navigator.get_top()):
        if isinstance(widget, Gtk.Box):
            _update_sidebar_box(widget, use_text)


# ------------------------------------------------------------
#
# Preferences dialog patches
#
# ------------------------------------------------------------
def _patch_preferences_dialog():
    from gramps.gui.configure import GrampsPreferences

    # The combo connects to self.date_format_changed when the panel is built,
    # so replacing the class method here is enough. No "restart" dialog.
    def date_format_changed(self, obj):
        config.set(DATE_KEY, obj.get_active())

    GrampsPreferences.date_format_changed = date_format_changed
    GrampsPreferences.add_data_panel = _wrap_panel(GrampsPreferences.add_data_panel)
    GrampsPreferences.add_general_panel = _wrap_panel(
        GrampsPreferences.add_general_panel
    )


def _wrap_panel(original):
    @functools.wraps(original)
    def wrapper(self, configdialog):
        result = original(self, configdialog)
        try:
            _polish_panel(result[1])
        except Exception:  # pylint: disable=broad-except
            LOG.warning("Could not adjust Preferences panel", exc_info=True)
        return result

    return wrapper


def _polish_panel(panel):
    """Drop the restart asterisks/footer and add PR 2296 date examples."""
    starred = {
        _("%s: ") % _("Date format *"),
        _("%s: ") % _("Age display precision *"),
        _("Display ages for events after death *"),
        _("Show text label beside Navigator buttons *"),
    }
    footer = _("* Requires Restart")
    sidebar_tip = _(
        "Show or hide text beside Navigator buttons "
        "(People, Families, Events...).\n"
        "Requires Gramps restart to apply."
    )

    for widget in _walk(panel):
        if isinstance(widget, Gtk.CheckButton):
            label = widget.get_label() or ""
            if label in starred:
                widget.set_label(_strip_star(label))
            if widget.get_tooltip_text() == sidebar_tip and "\n" in sidebar_tip:
                widget.set_tooltip_text(sidebar_tip.rsplit("\n", 1)[0])
        elif isinstance(widget, Gtk.Label):
            text = widget.get_text()
            if text in starred:
                widget.set_text(_strip_star(text))
            elif text == footer:
                # These four were the only restart items in 5.2 - 6.1.
                widget.set_no_show_all(True)
                widget.hide()
        elif isinstance(widget, Gtk.ComboBoxText):
            _add_date_examples(widget)


def _strip_star(text):
    return text.replace(" *", "").replace("*", "")


def _add_date_examples(combo):
    """PR 2296: append a rendered example to each date format entry."""
    formats = list(get_date_formats())
    model = combo.get_model()
    if model is None or [row[0] for row in model] != formats:
        return  # not the date format combo (or already patched by core)
    displayer_class = glocale.date_displayer.__class__
    for index, row in enumerate(model):
        try:
            # Temporary displayer, so the global one is never touched.
            temp = displayer_class(format=index, blocale=glocale)
            example = temp.display(EXAMPLE_DATE)
        except Exception:  # pylint: disable=broad-except
            continue
        # Editing the row text does not change the active item.
        row[0] = "%s  (%s)" % (formats[index], example)


# ------------------------------------------------------------
#
# Navigator sidebar buttons
#
# ------------------------------------------------------------
def _update_sidebar_box(box, use_text):
    """
    Core sidebars build each button as Box(Image[, Label]) inside a
    Gtk.(Toggle)Button, or as an Expander label widget (Expander sidebar).
    The label text is the same as the tooltip.
    """
    parent = box.get_parent()
    in_button = isinstance(parent, Gtk.Button)
    in_expander = isinstance(parent, Gtk.Expander) and parent.get_label_widget() is box
    if not (in_button or in_expander):
        return
    children = box.get_children()
    if not children or not isinstance(children[0], Gtk.Image):
        return
    labels = [child for child in children[1:] if isinstance(child, Gtk.Label)]
    if len(labels) != len(children) - 1:
        return  # unknown layout, leave it alone
    text = (parent if in_button else box).get_tooltip_text()
    if not text:
        return

    if use_text:
        if labels:
            labels[0].show()
        else:
            label = Gtk.Label(label=text)
            box.pack_start(label, False, True, 4 if in_expander else 0)
            label.show()
    else:
        for label in labels:
            label.hide()

    if in_button:  # Expander headers always use BUTTON size in core
        image = children[0]
        icon_name, _size = image.get_icon_name()
        if icon_name:
            size = Gtk.IconSize.BUTTON if use_text else Gtk.IconSize.DND
            image.set_from_icon_name(icon_name, size)


# ------------------------------------------------------------
#
# Refreshing views and gramplets
#
# ------------------------------------------------------------
def _schedule_refresh():
    """Coalesce several changes into one rebuild when Gtk is idle."""
    if not _STATE["refresh_id"]:
        _STATE["refresh_id"] = GLib.idle_add(_refresh_all)


def _refresh_all():
    _STATE["refresh_id"] = 0
    viewmanager = getattr(_STATE["uistate"], "viewmanager", None)
    for page in list(getattr(viewmanager, "pages", None) or []):
        if getattr(page, "active", False):
            try:
                page.build_tree()
            except Exception:  # pylint: disable=broad-except
                LOG.warning("Could not rebuild %r", page, exc_info=True)
        else:
            page.dirty = True  # PageView.set_active() rebuilds dirty views
        for gramplet in _page_gramplets(page):
            try:
                gramplet.update()  # inactive gramplets just mark themselves dirty
            except Exception:  # pylint: disable=broad-except
                LOG.warning("Could not update gramplet %r", gramplet, exc_info=True)
    return False


def _page_gramplets(page):
    """Gramplets in a view's sidebar/bottombar, or on the Dashboard."""
    for bar in (getattr(page, "sidebar", None), getattr(page, "bottombar", None)):
        if bar is not None:
            for child in bar.get_children():
                if getattr(child, "pui", None):
                    yield child.pui
    gramplet_map = getattr(getattr(page, "widget", None), "gramplet_map", None)
    if isinstance(gramplet_map, dict):
        for gui in gramplet_map.values():
            if gui is not None and getattr(gui, "pui", None):
                yield gui.pui


# ------------------------------------------------------------
#
# Helpers
#
# ------------------------------------------------------------
def _patch_relview(module):
    """Make RelationshipView.age_precision read the config every time."""
    cls = getattr(module, "RelationshipView", None)
    if cls is None or isinstance(cls.__dict__.get("age_precision"), property):
        return
    # The no-op setter swallows the assignment in RelationshipView.__init__.
    cls.age_precision = property(
        lambda self: config.get(PREC_KEY), lambda self, value: None
    )


def _modules_ending_with(tail):
    for module in list(sys.modules.values()):
        path = (getattr(module, "__file__", None) or "").replace("\\", "/")
        if path.endswith(tail):
            yield module


def _walk(widget):
    """Yield widget and all descendants, including Expander label widgets."""
    yield widget
    if isinstance(widget, Gtk.Expander):
        label_widget = widget.get_label_widget()
        if label_widget is not None:
            yield from _walk(label_widget)
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            yield from _walk(child)
