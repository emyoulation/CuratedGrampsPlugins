#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
#
# (Draft mode: full GPL header to be added when made commit-ready.)
#
"""
StrictPyGObjectCompat

PyGObject 3.55.0 (first stable: 3.56.0) changed constructor keyword
arguments to use strict typed conversion (PyGObject MR !469, "Unify
properties handling"). Older versions quietly called str() on any object
passed to a string property, so code like

    Gtk.Label(label=place.get_type())

worked for years and now raises "TypeError: Must be string, not PlaceType".

The same PyGObject release also started warning, and leaking a reference,
when a Python vfunc returns a new widget that nothing else holds. Gramps
CellRendererTextEdit.do_start_editing (editable cells in editor tabs, such
as multiple surnames) does exactly that:

    RuntimeWarning: Adding extra reference for <Gtk.Entry ...>

At registration this addon probes for the strict behavior. Only when it is
present does it:

1. wrap Gtk.Label.__init__ so a non-string label is converted with str()
   first. Each distinct calling line is logged once, so the offending code
   can be reported upstream.
2. swap in a CellRendererTextEdit subclass that keeps a Python reference to
   the editing Gtk.Entry, so PyGObject neither warns nor adds a reference.
"""

import inspect
import logging
import os
import re
import traceback

from gi.repository import Gio

LOG = logging.getLogger(".StrictPyGObjectCompat")

_PATCH_MARK = "_strict_pygobject_compat"
_original_label_init = None
_reported_callsites = set()


def pygobject_is_strict():
    """Return True if PyGObject refuses non-string values for string props.

    Gio.SimpleAction has an introspected string property ('name') and needs
    no display, so it is a safe probe in any environment.
    """
    try:
        Gio.SimpleAction(name=1)
    except TypeError:
        return True
    return False


def _report_once(value):
    """Log the first coercion from each calling line."""
    # Stack: ... caller -> Gtk override new_init? -> _patched_label_init
    # -> _coerce -> _report_once. Find the first frame outside this file
    # and outside gi itself.
    for frame in reversed(traceback.extract_stack()[:-1]):
        filename = frame.filename.replace("\\", "/")
        if filename.endswith("StrictPyGObjectCompat.py") or "/gi/" in filename:
            continue
        key = (filename, frame.lineno)
        if key not in _reported_callsites:
            _reported_callsites.add(key)
            LOG.warning(
                "Converted %s to str for Gtk.Label at %s:%d",
                type(value).__name__,
                filename,
                frame.lineno,
            )
        return


def _coerce(value):
    """Return value unchanged if None/str/bytes, otherwise str(value)."""
    if value is None or isinstance(value, (str, bytes)):
        return value
    _report_once(value)
    return str(value)


def _patched_label_init(self, *args, **kwargs):
    """Gtk.Label.__init__ replacement that tolerates non-string labels."""
    if args:
        args = (_coerce(args[0]),) + args[1:]
    if "label" in kwargs:
        kwargs["label"] = _coerce(kwargs["label"])
    _original_label_init(self, *args, **kwargs)


def apply_label_patch():
    """Wrap Gtk.Label.__init__ once. Return False if it was already wrapped."""
    global _original_label_init

    from gi.repository import Gtk  # deferred: CLI sessions may lack GTK

    if getattr(Gtk.Label.__init__, _PATCH_MARK, False):
        return False  # already patched (plugin reloaded)

    _original_label_init = Gtk.Label.__init__
    setattr(_patched_label_init, _PATCH_MARK, True)
    Gtk.Label.__init__ = _patched_label_init
    return True


def patch_text_edit_renderer():
    """Replace CellRendererTextEdit in embeddedlist with a fixed subclass.

    PyGObject binds a vfunc to the Python function present when the class is
    created, so reassigning do_start_editing on the existing class would have
    no effect. A subclass registers its own vfunc. EmbeddedList is the only
    place in Gramps (5.2 and 6.0) that creates CellRendererTextEdit, and it
    looks the name up in its module globals each time, so rebinding that
    global is enough. Return False if it was already replaced.
    """
    from gramps.gui.editors.displaytabs import embeddedlist

    base = embeddedlist.CellRendererTextEdit
    if getattr(base, _PATCH_MARK, False):
        return False

    class StrictCompatCellRendererTextEdit(base):
        """CellRendererTextEdit that holds a reference to its editing entry."""

        __gtype_name__ = "StrictCompatCellRendererTextEdit"

        def do_start_editing(
            self, event, treeview, path, background_area, cell_area, flags
        ):
            entry = base.do_start_editing(
                self, event, treeview, path, background_area, cell_area, flags
            )
            # Keeping this reference (until the next edit replaces it) is what
            # stops PyGObject from adding its own, never-released reference.
            self._strict_compat_entry = entry
            return entry

    setattr(StrictCompatCellRendererTextEdit, _PATCH_MARK, True)
    embeddedlist.CellRendererTextEdit = StrictCompatCellRendererTextEdit
    return True


def unfixed_core_files():
    """Return the Gramps core files that still have the strict-PyGObject bugs.

    Used only to decide whether to point the user at the "Permanent fix"
    section of the README. Any file that cannot be checked is left out.
    """
    unfixed = []
    try:
        import gramps

        path = os.path.join(
            os.path.dirname(gramps.__file__), "plugins", "gramplet", "placedetails.py"
        )
        with open(path, encoding="utf-8") as source:
            if re.search(
                r"add_row\(_\([\"']Type[\"']\),\s*place\.get_type\(\)\)",
                source.read(),
            ):
                unfixed.append(path)
    except Exception:
        pass
    try:
        from gramps.gui.widgets import cellrenderertextedit

        source = inspect.getsource(
            cellrenderertextedit.CellRendererTextEdit.do_start_editing
        )
        if not re.search(r"self\.\w+\s*=\s*entry\b", source):
            unfixed.append(cellrenderertextedit.__file__)
    except Exception:
        pass
    return unfixed


def load_on_reg(dbstate, uistate, plugin):
    """Called by the Gramps plugin manager at startup."""
    import gi

    if uistate is None:
        return []  # CLI: no GTK widgets are built

    if not pygobject_is_strict():
        LOG.debug(
            "PyGObject %s converts strings leniently; no patch needed.",
            gi.__version__,
        )
        return []

    applied = []
    for name, patch in (
        ("Gtk.Label string", apply_label_patch),
        ("CellRendererTextEdit reference", patch_text_edit_renderer),
    ):
        try:  # each patch on its own; never stop Gramps from starting
            if patch():
                applied.append(name)
        except Exception:
            LOG.exception("Could not apply the %s compatibility patch.", name)

    if applied:
        LOG.warning(
            "Strict PyGObject %s detected; applied compatibility patches: %s.",
            gi.__version__,
            ", ".join(applied),
        )
        if unfixed_core_files():
            LOG.warning(
                "A permanent fix to the Gramps program files is possible for "
                "technically adept users. See 'Permanent fix' in the "
                "StrictPyGObjectCompat documentation: %s",
                os.path.join(os.path.dirname(__file__), "README.md"),
            )
    return []
