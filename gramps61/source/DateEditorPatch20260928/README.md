# Date Calculator slide-out for the Edit Date dialog

- **Slide-out panel.** A narrow triangle tab on the dialog's right edge (▸ closed, ◂ open) opens the calculator. The window grows by the panel's width and shrinks back exactly on collapse; while open, resizing changes only the panel.
- **Reference date.** Prefilled from the dialog when the panel opens (unless you typed something). Blank shows the Result hint.
- **Date or offset.** A date, years (`5`), or years/months/days as `-2, 3, 10` or `-2y, 3m, 10d`. A leading minus subtracts the whole offset.
- **Result to Date** loads the result into the Date fields (a Range or Span keeps its type and second date).
- **Result to Second Date** copies the result into the Second date; the Type becomes Span unless it is already a Range or Span.
- **Calculate, Copy, Clear.** Clear empties all three fields.
- **Drag and drop.** Text dropped on the panel, outside a text box, replaces the Reference date. Text boxes take drops as usual.
- **Errors** name the field: `Error: invalid Reference date`, `Error: invalid Date or offset`.
- **Runs on stock 5.2/6.x.** `markdown_render` is optional (built-in fallback).

Files: `gramps/gui/editors/editdate.py`, `gramps/gui/widgets/datecalculator.py` (new).

## Patch installation

Whole files, not diffs: copy them over the installed Gramps (no `patch` needed). The paths below are for a pip user install on Python 3.11.

| From this package | Install to |
|---|---|
| `gramps/gui/editors/editdate.py` | `~/.local/lib/python3.11/site-packages/gramps/gui/editors/editdate.py` (replaces the existing file) |
| `gramps/gui/widgets/datecalculator.py` | `~/.local/lib/python3.11/site-packages/gramps/gui/widgets/datecalculator.py` (new file) |

For another install, use its own Gramps folder (for example `/usr/lib/python3/dist-packages/gramps`, which needs `sudo`). This finds it:

```bash
python3 -c "import os, gramps; print(os.path.dirname(gramps.__file__))"
```

```bash
G=~/.local/lib/python3.11/site-packages/gramps/gui        # adjust to your install
cp -n "$G/editors/editdate.py" "$G/editors/editdate.py.orig"   # one-time backup
cp gramps/gui/editors/editdate.py       "$G/editors/"
cp gramps/gui/widgets/datecalculator.py "$G/widgets/"
```

Restart Gramps, open any Edit Date dialog, and look for the triangle tab on its right edge.

**Uninstall:** `mv "$G/editors/editdate.py.orig" "$G/editors/editdate.py"` and delete `"$G/widgets/datecalculator.py"`.
Upgrading Gramps replaces both files, so copy them again afterwards.

## Assumptions
- Only plain text is accepted for drops (not Gramps objects such as events).
- For a range or span result, "Result to Second Date" uses the result's first date.
- The panel prefill is refreshed on each open only if you have not edited the field.

## AI disclosure

```
Generated-by: Claude Sonnet 5 (model ID claude-sonnet-5), Anthropic, via the claude.ai chat interface, 2026-09-28
Co-authored-by: Claude Sonnet 5 <noreply@anthropic.com>
Prompted by: Brian McCullough
```

- **Scope:** `gramps/gui/widgets/datecalculator.py` (new) and the calculator integration in `gramps/gui/editors/editdate.py`. The calculation logic is derived from the Date Calculator addon (Doug Blank, Steve Youngs and others).
- **Prompts (summary):** a slide-out Date Calculator panel for the Edit Date dialog, refined over many rounds: handle and gutters, animation without stretching, prefill and hints, unit offsets (`2y, 3m, 10d`), Result to Date / Result to Second Date, button layout, and drag and drop.
- **Constraints:** worked in "draft mode": the Gramps [AGENTS.md](https://github.com/gramps-project/gramps/blob/master/AGENTS.md) style rules (type hints, docstrings, Black, pylint, headers) were intentionally not applied. The Gramps [AI-generated code policy](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code) is the reference for this disclosure.
- **Verification:** run headless against Gramps 5.2.4 and its stock Glade file (GTK 3.24, virtual display, simulated mouse drags). Not run on a live desktop by the AI.
- **For the contributor:** confirming that the AI tool's terms do not conflict with the Gramps license.
