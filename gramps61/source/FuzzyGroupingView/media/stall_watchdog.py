#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026       Claude AI (wish coding by Brian McCullough)
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
GTK main loop stall watchdog (debugging aid, not part of any addon).

Finds what blocks the GTK main loop when a window shows "Not responding".
A GLib timeout "beats" every BEAT_MS while the main loop runs. A daemon
thread checks the beat; when the main loop has not beaten for REPORT
seconds (the desktop shows "Not responding" after about 5), it logs the
Python stack of the main thread at that moment, again every REPEAT seconds
while the stall lasts, and then how long the stall was.

Used to find the quadratic TreeBaseModel.do_get_path() in Expand all Nodes
(Fuzzy Grouping view, October 2026). Kept here for the GTK Diagnostics
Toolkit; Gramps does not load it (no .gpr.py registers it).

Use, from any code that runs once the GUI exists:

    from stall_watchdog import start_stall_watchdog
    start_stall_watchdog()

Output goes to the "stall_watchdog" logger at WARNING level, so it shows on
the terminal without any -d flag. Pass log=print for plain prints.
"""

import logging
import sys
import threading
import traceback
from time import perf_counter

from gi.repository import GLib

BEAT_MS = 250  # main loop heartbeat interval
REPORT = 2.0  # seconds without a beat before the first report
REPEAT = 5.0  # seconds between reports while a stall lasts
STACK_FRAMES = 14  # innermost frames of the main thread to show

_STATE = {"beat": 0.0, "main": None, "started": False}


def _cb_beat():
    _STATE["beat"] = perf_counter()
    return True  # keep beating


def _watch(log):
    reported_at = None  # (time of first report, gap at first report)
    while True:
        threading.Event().wait(0.5)
        gap = perf_counter() - _STATE["beat"]
        if gap < REPORT:
            if reported_at is not None:
                blocked = reported_at[1] + (perf_counter() - reported_at[0]) - gap
                log("STALL ended, the main loop was blocked about %.2f s" % blocked)
                reported_at = None
            continue
        if reported_at is not None and perf_counter() - reported_at[0] < REPEAT:
            continue
        frame = sys._current_frames().get(_STATE["main"])  # pylint: disable=protected-access
        stack = traceback.format_stack(frame)[-STACK_FRAMES:] if frame else []
        log(
            "STALL main loop blocked for %.2f s, main thread is in:\n%s"
            % (gap, "".join(stack).rstrip())
        )
        if reported_at is None:
            reported_at = (perf_counter(), gap)


def start_stall_watchdog(log=None):
    """
    Start the heartbeat and the watchdog thread (once per process).
    Call from the main (GTK) thread.
    """
    if _STATE["started"]:
        return
    if log is None:
        log = logging.getLogger("stall_watchdog").warning
    _STATE["started"] = True
    _STATE["main"] = threading.main_thread().ident
    _STATE["beat"] = perf_counter()
    GLib.timeout_add(BEAT_MS, _cb_beat)
    threading.Thread(
        target=_watch, args=(log,), name="StallWatchdog", daemon=True
    ).start()
