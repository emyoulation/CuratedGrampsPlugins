# Edit Date Calculator changelog
<!-- edit=False status=True browse=False undocked=True -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable changes to the Edit Date Calculator addon are listed here, newest first.
## 0.1.0 - 2026-10-28
Second field-test release.
### Added
- A Parse button at the end of the Text comment row: at the right for left-to-right languages, at the left for right-to-left languages. It is faint while parsing is off. Click it to read the Text comment as a date at once; the button then shows in full color, and the Text comment is read again each time you pause while typing. A date that Gramps understands fills the Type, Quality, Calendar and date fields; any other text makes the Type Text only. Click the button again to stop parsing.
- While the Type is Text only, the Text comment and the Text only item of the Type menu are shown in red. Only the color changes, never the weight of the letters, so the text does not move under the mouse pointer. The red, and the Parse button, change with a short fade.
- A double-click on the Evaluates to line also puts the evaluated date on the Gramps Clipboard, as a Text item, the same way Ctrl+C copies a selected person in the People view: an open Clipboard window is used as it is, otherwise a new Clipboard window opens.
### Changed
- After a double-click on the Evaluates to line, the line keeps its text and adds "(Copied to the clipboard)" for a moment, so the date does not move.
- The Evaluates to line starts directly below the "Text comment:" label.
- The Start date and End date sections have the same width, and the space between them is twice as wide. Before, the End date calendar was wider, because it reached over two empty columns of the dialog (this is also so in Gramps 6.1 itself).
- The triangle tab of the calculator is at the right edge of the dialog, and the space before it is the same as the space at the left of the Start date calendar. The tab shows the background of the dialog; it shows as a button only when the mouse pointer is over it, and it shows as pressed while the calculator is open.
- The tab shows black triangles (▶ and ◀), so it no longer looks like the year arrows of the calendar beside it.
## 0.0.2 - 2026-10-28
- double-click on Evaluation line copies to OS clipboard
## 0.0.1 - 2026-10-26
First field-test release. The addon changes the Date selection dialog (Date Editor) of Gramps 5.2, 6.0 and 6.1 when Gramps starts, without replacing any Gramps files.
### Added
- Slide-out date calculator on the right edge of the Date selection dialog, opened and closed with a triangle tab. The dialog grows by the width of the calculator and returns to its original width when the calculator closes.
- Reference date is filled from the dialog when the calculator opens, unless you typed something there yourself.
- "Date or offset" accepts a date, a number of years (`5`), years, months and days (`-2, 3, 10`), or units in any order (`-2y, 3m, 10d`). A leading minus, or "Age" / "Aged" (`Aged 45y 3m`), subtracts the whole offset.
- Result to Start Date, Result to End Date, Calculate, Copy and Clear buttons. When a "Result to" button fills a dimmed side, the Type changes so both sides are active: From and To become Span (From-To), Before and After become Range (Between), other Types become Range.
- Text dropped on the calculator, outside a text box, replaces the Reference date.
- Month calendars for the Start date and the End date, backported to the Gramps 5.2 and 6.0 Date Editor from the Gramps 6.1 Date Editor work by Serge Noiraud: pull request [#2001](https://github.com/gramps-project/gramps/pull/2001) ("New calendar") and pull request [#2209](https://github.com/gramps-project/gramps/pull/2209) ("Calendar enhancements"), which replaced #2001 and was merged for Gramps 6.1. On Gramps 6.1, the calendars of Gramps itself are used.
- Each month calendar has a heading row with Month and Year buttons. Clicking the Month button puts that month and year in the date fields of its section; clicking the Year button puts only that year there. Both buttons can be dragged as text. The Month button is as wide as the longest month name, so the arrows do not move.
- A day, Month or Year dragged from one calendar and dropped anywhere on the other section (label, date fields or calendar) works like a click on that item on the other calendar. When the drop fills a dimmed side, the Type changes so both sides are active: From and To become Span (From-To), Before and After become Range (Between), other Types become Span.
- A line below the Text comment shows the date as Gramps evaluates it when comparing dates, using the About, Before and After ranges from Preferences (for example, "About 16 Mar 1923" evaluates to "Between 16 Mar 1873 and 16 Mar 1973").
### Changed
- The "Date" and "Second date" sections are named "Start date" and "End date".
- The Type menu items Range and Span are named "Range (Between)" and "Span (From-To)".
- A Before or To date is shown in the End date section, with the Start date section dimmed and showing the date of today. Changing the Type moves the date to the correct section.
- Typing in the Text comment box changes the Type to Text only. For other Types, Gramps does not keep the comment.
- A day in a calendar is selected when the mouse button is released, not when it is pressed. Dragging a day copies that date as text and leaves the selection and the keyboard focus as they were.
- The calendar heading arrows, and Page Up and Page Down, only show another month or year; they no longer change the date fields.
- A calendar no longer writes back to the date fields while it is only following them. Before, a date with only a year made the calendar show January, and January then filled the Month field.
- The Help button of the dialog opens the README of this addon, in Markdown Dash when it is installed and active, otherwise the help page of this addon on the web. Before, it opened the Gramps wiki page about editing dates.
- The Date selection dialog can be moved separately from the editor that opened it (for example, Edit Event). The editor behind it is no longer dimmed or locked to it, but it still does not accept input until the Date selection dialog closes.
### Notes
- To switch the addon off, hide it in the Plugin Manager and restart Gramps.
- The calculation logic comes from the Date Calculator gramplet addon (Douglas S. Blank, Steve Youngs and others).
