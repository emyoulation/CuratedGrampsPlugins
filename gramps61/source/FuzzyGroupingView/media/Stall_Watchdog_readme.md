# Stall Watchdog
A debugging aid that shows what blocks the GTK main loop when Gramps shows "Not responding". It is not part of the Fuzzy Grouping view, and Gramps never loads it by itself, because no `.gpr.py` file registers it.

## How it works
A GLib timer records a heartbeat every 0.25 seconds while the main loop runs. A background thread checks the heartbeat. When the main loop has not beaten for 2 seconds, the thread logs the Python stack of the main thread at that moment. It logs again every 5 seconds while the stall lasts, and then logs how long the stall was.

## Use
Call it once, from code that runs on the main (GTK) thread after the Gramps window exists:
```python
from stall_watchdog import start_stall_watchdog
start_stall_watchdog()
```
The reports go to the `stall_watchdog` logger at WARNING level, so they show in the terminal without a `-d` flag. To use plain prints instead, call `start_stall_watchdog(log=print)`.

Start Gramps from a terminal, do the action that freezes the window, and read the `STALL` lines. The innermost frames of each stack show the code that holds the main loop.

## Settings
Change these constants at the top of `stall_watchdog.py`: `BEAT_MS` (heartbeat interval), `REPORT` (seconds before the first report), `REPEAT` (seconds between reports) and `STACK_FRAMES` (number of stack frames shown).

## Limits
- It shows Python frames only. A stall inside C code (GTK itself) shows the last Python call before it.
- It adds one thread and one timer for the whole session, so use it while you investigate, then remove the call.

## History
Written in October 2026 to find the slow Expand all Nodes in the Grouped People and Fuzzy Grouping views: the core `TreeBaseModel.do_get_path()` takes quadratic time when it opens thousands of groups.

## Credits
Written by Claude (Anthropic), wish-coded by Brian McCullough.
