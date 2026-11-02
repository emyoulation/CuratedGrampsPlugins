"""
Unittests for CellRendererTextEdit.

Since PyGObject 3.55.0 (stable 3.56.0), when a Python vfunc returns a newly
created GObject that nothing else references, PyGObject adds a reference
that is never released and emits:

    RuntimeWarning: Adding extra reference for <Gtk.Entry ...>, for nothing
    is holding a reference to this object. This could potentially lead to a
    memory leak. See: https://bugzilla.gnome.org/show_bug.cgi?id=687522

CellRendererTextEdit.do_start_editing returns a new Gtk.Entry and keeps no
reference to it, so every cell edit in an EmbeddedList (for example the
multiple surnames table in Edit Person) leaks one entry on Python 3.14 with
PyGObject 3.56 or newer.

TestStartEditingReference needs no display and fails on any PyGObject while
the renderer drops its entry. TestStartEditingWithGtk drives a real
Gtk.TreeView and only runs with a display (for example under xvfb-run).
"""

import gc
import os
import unittest
import warnings
import weakref
from types import SimpleNamespace
from unittest import mock

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from gramps.gui.widgets import cellrenderertextedit  # noqa: E402
from gramps.gui.widgets.cellrenderertextedit import (  # noqa: E402
    CellRendererTextEdit,
)


def _has_gtk_display():
    """
    Return True only if a real Gtk display is available.

    The gramps CI exports GDK_BACKEND=- and runs without an X server.
    """
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return False
    if os.environ.get("GDK_BACKEND") == "-":
        return False
    try:
        return bool(Gtk.init_check([])[0])
    except Exception:
        return False


_HAS_GTK_DISPLAY = _has_gtk_display()


class FakeEntry:
    """Display-free stand-in for Gtk.Entry with the methods the renderer uses."""

    def __init__(self):
        self.text = ""

    def set_has_frame(self, setting):
        pass

    def set_alignment(self, xalign):
        pass

    def set_width_chars(self, n_chars):
        pass

    def set_text(self, text):
        self.text = text

    def get_text(self):
        return self.text

    def add_events(self, events):
        pass

    def connect(self, *args):
        return 0

    def show(self):
        pass


class TestStartEditingReference(unittest.TestCase):
    """
    The entry returned by do_start_editing must stay referenced after the
    vfunc returns, or PyGObject 3.56+ adds a reference that is never released.
    """

    def setUp(self):
        self.renderer = CellRendererTextEdit()
        self.renderer.set_property("text", "Smith")
        # Only Gtk.Entry is replaced, after the real renderer exists.
        fake_gtk = SimpleNamespace(Entry=FakeEntry)
        patcher = mock.patch.object(cellrenderertextedit, "Gtk", fake_gtk)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _start_editing(self):
        return self.renderer.do_start_editing(None, None, "0", None, None, 0)

    def test_entry_still_referenced_after_return(self):
        self.renderer.set_property("editable", True)
        entry = self._start_editing()
        self.assertIsInstance(entry, FakeEntry)
        self.assertEqual(entry.get_text(), "Smith")

        entry_ref = weakref.ref(entry)
        del entry
        gc.collect()
        self.assertIsNotNone(
            entry_ref(),
            "do_start_editing returned an entry that nothing else references. "
            "PyGObject 3.56+ then adds a never-released reference and warns "
            "'Adding extra reference for <Gtk.Entry ...>'. Keep a reference "
            "to the entry (for example on self) until editing ends.",
        )

    def test_not_editable_returns_none(self):
        self.renderer.set_property("editable", False)
        self.assertIsNone(self._start_editing())


@unittest.skipUnless(_HAS_GTK_DISPLAY, "needs a real Gtk display (run under xvfb-run)")
class TestStartEditingWithGtk(unittest.TestCase):
    """
    Edit cells in a real Gtk.TreeView. On Python 3.14 with PyGObject 3.56+ the
    unfixed renderer warns once per edit and never frees the entries.
    """

    EDITS = 4

    def test_editing_entries_do_not_leak(self):
        store = Gtk.ListStore(str)
        store.append(["Smith"])
        store.append(["Jones"])
        treeview = Gtk.TreeView(model=store)
        renderer = CellRendererTextEdit()
        renderer.set_property("editable", True)
        column = Gtk.TreeViewColumn("Surname", renderer, text=0)
        treeview.append_column(column)
        window = Gtk.Window()
        window.add(treeview)
        window.show_all()

        finalized = []
        edited = []
        renderer.connect("edited", lambda r, path, text: edited.append(text))

        def pump():
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pump()
            for count in range(self.EDITS):
                path = Gtk.TreePath(count % 2)
                treeview.set_cursor_on_cell(path, column, renderer, True)
                pump()
                entries = [
                    child
                    for child in treeview.get_children()
                    if isinstance(child, Gtk.Entry)
                ]
                self.assertEqual(len(entries), 1, "no editing entry appeared")
                entry = entries[0]
                entry.weak_ref(lambda: finalized.append(True))
                entry.set_text("Edit %d" % count)
                renderer.focus_out(entry, None, str(path))
                del entry, entries
                pump()
            window.destroy()
            del window, treeview
            pump()
            gc.collect()
            pump()

        self.assertEqual(len(edited), self.EDITS, "edits were not committed")
        extra_refs = [
            str(warning.message)
            for warning in caught
            if issubclass(warning.category, RuntimeWarning)
            and "Adding extra reference" in str(warning.message)
        ]
        self.assertEqual(extra_refs, [], "PyGObject added extra references")
        # The renderer may legitimately keep the most recent entry alive.
        self.assertGreaterEqual(
            len(finalized),
            self.EDITS - 1,
            "editing entries were never freed (leak)",
        )


if __name__ == "__main__":
    unittest.main()
