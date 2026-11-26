#!/usr/bin/env python3
"""
Reproduce: Gtk.TextIter.get_tags() loses memory on every call that
returns an empty list (an untagged character). No Gramps code involved.

Run:  python3 textiter_get_tags_leak.py
Expected: 0 bytes per call in every line.
"""
import gc

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango  # noqa: E402

CALLS = 300000


def rss_kb():
    with open("/proc/self/status", encoding="utf-8") as status:
        for line in status:
            if line.startswith("VmRSS"):
                return int(line.split()[1])
    return 0


def bytes_per_call(func):
    for _i in range(2000):  # warm up
        func()
    gc.collect()
    before = rss_kb()
    for _i in range(CALLS):
        func()
    gc.collect()
    return (rss_kb() - before) * 1024.0 / CALLS


buf = Gtk.TextBuffer()
buf.set_text("x" * 100)
bold = buf.create_tag("bold", weight=Pango.Weight.BOLD)
buf.apply_tag(bold, buf.get_iter_at_offset(50), buf.get_end_iter())
untagged = buf.get_iter_at_offset(10)
tagged = buf.get_iter_at_offset(60)

print(
    "PyGObject %s, GTK %d.%d.%d"
    % (
        gi.__version__,
        Gtk.get_major_version(),
        Gtk.get_minor_version(),
        Gtk.get_micro_version(),
    )
)
print("get_tags() on an untagged character: %5.1f bytes per call"
      % bytes_per_call(untagged.get_tags))
print("get_tags() on a tagged character:    %5.1f bytes per call"
      % bytes_per_call(tagged.get_tags))
print("has_tag() on an untagged character:  %5.1f bytes per call"
      % bytes_per_call(lambda: untagged.has_tag(bold)))
