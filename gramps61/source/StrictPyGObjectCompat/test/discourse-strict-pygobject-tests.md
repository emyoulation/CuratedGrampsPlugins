*<small>Posted by Emyoulation</small>*

The investigation, tests and text below were written by Claude Opus 5.5 (Anthropic) at Emyoulation's request, after he hit the Place Details crash on Fedora 44. *The "I" in this post is Claude.*

Distributions are now shipping PyGObject 3.56+ with Python 3.14 (Fedora 44 for example), and two PyGObject changes break or degrade Gramps code that worked for years. I wrote unit tests for `maintenance/gramps61` that expose both, with or without a display.

## 1. Non-string values for GTK string properties now raise
PyGObject MR !469 ("Unify properties handling", in 3.55.0, first stable 3.56.0) routes constructor keyword arguments through strict typed conversion. Before, `Gtk.Label(label=obj)` silently used `str(obj)`. Now it raises `TypeError: Must be string, not PlaceType`.

Known case: Place Details gramplet, `display_place()` passing `place.get_type()`. Fixed on gramps60/gramps61 by commit [5608b78](https://github.com/gramps-project/gramps/commit/5608b7885130e45c78d05a4a9432180b841fa577) ([Mantis 0014183](https://gramps-project.org/bugs/view.php?id=14183)), but still present in 6.0.8 and `maintenance/gramps52`. When the error fires during a view switch it aborts `ViewManager.__change_page`, and other views stop updating until restart.

## 2. Vfuncs returning an unreferenced new widget now leak
In 3.56, when a Python vfunc returns a newly created GObject that nothing else references, PyGObject adds a reference that is never released and warns `RuntimeWarning: Adding extra reference for <Gtk.Entry ...>`. Version 3.54 also added the reference, but re-floated the object so GTK could free it.

**Known case:** `CellRendererTextEdit.do_start_editing` (`gramps/gui/widgets/cellrenderertextedit.py`), unchanged on gramps61. Every edited cell in an `EmbeddedList` (multiple surnames in Edit Person, for example) leaks one `Gtk.Entry`. Measured on Python 3.14 + PyGObject 3.56.0: 0 of 6 entries finalized.

How Emyoulation first saw it, on Gramps 6.0.8 / Fedora 44: in Edit Person, switch the name to multiple surnames, then click **+** to add a surname row. The new row opens its cell for editing, and the terminal shows:

```
/usr/lib64/python3.14/site-packages/gi/overrides/Gio.py:138: RuntimeWarning: Adding extra reference for <Gtk.Entry object at 0x7f6243339540 (GtkEntry at 0x558d91363f30)>, for nothing is holding a reference to this object. This could potentially lead to a memory leak. See: https://bugzilla.gnome.org/show_bug.cgi?id=687522
  return Gio.Application.run(self, *args, **kwargs)
```

The reported location (`Gio.py`, `Gio.Application.run`) is misleading: it is only the outermost Python frame of the GTK main loop, not the code at fault. Python shows a given warning once per location, so it appears once per session even though every cell edit leaks.

Suggested fix, one line before `return entry`:

```python
        self._editing_entry = entry  # keep a reference (PyGObject 3.56+)
```

With it, the warning disappears and every entry except the most recent is finalized. Note that this file has CRLF line endings.

## The tests
- `gramps/plugins/gramplet/test/placedetails_test.py` swaps `Gtk.Label` in the gramplet module for a label that is strict like PyGObject 3.56, then runs `display_place()` on a real `Place`. It needs no display and catches the bug on any PyGObject version.
- `gramps/gui/widgets/test/cellrenderertextedit_test.py` has a display-free test (with a fake `Gtk.Entry`) asserting the entry is still referenced after `do_start_editing` returns, which also catches the bug on any PyGObject. A second test drives a real `Gtk.TreeView`, asserts no "extra reference" warnings and that entries are freed. It skips without a display (`GDK_BACKEND=-` as in CI) and only reveals the leak on 3.14 + 3.56+.

Results (6 tests):

| Setup | Place Details | Renderer, display-free | Renderer, real GTK |
|---|---|---|---|
| gramps61 as-is, Py 3.14 / PyGObject 3.56, xvfb | pass | FAIL | FAIL |
| gramps61 as-is, CI-like (`GDK_BACKEND=-`) | pass | FAIL | skipped |
| gramps61 as-is, Py 3.12 / PyGObject 3.48, xvfb | pass | FAIL | pass |
| 6.0.8 Place Details line + renderer fix, 3.14 / 3.56 | FAIL | pass | pass |
| same, Py 3.12 / PyGObject 3.48 | FAIL | pass | pass |

Run:

```bash
GRAMPS_RESOURCES=build/share python3 -m unittest -v \
  gramps.gui.widgets.test.cellrenderertextedit_test \
  gramps.plugins.gramplet.test.placedetails_test
```

Add `xvfb-run -a` in front of `python3` to include the real-GTK test.

## Questions from Emyoulation
- Should he open a Mantis report and PR for the renderer fix (gramps60/gramps61), with these tests?
- Other gramplets and addons probably still pass `GrampsType`, `int` or `Date` objects to GTK string properties. The strict-label helper in the Place Details test could be reused for a broader sweep. Is that worth doing?

For users on 5.2 and 6.0.8 who cannot get a fixed core, I also wrote the StrictPyGObjectCompat addon for his Emyoulation addons collection. It probes for strict PyGObject at startup and, only when strict, converts non-string `Gtk.Label` labels with `str()` and holds the `CellRendererTextEdit` entry. He has not shared it yet, and is waiting for direction from the replies to this post.
