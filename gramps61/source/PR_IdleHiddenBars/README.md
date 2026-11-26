# Idle Hidden Bars
<!-- undocked=false -->

Idle Hidden Bars makes Gramps do less work behind the scenes. When you hide the Sidebar or the Bottombar, the gramplets in that bar now rest until you show the bar again. Gramplets that you undock into their own windows always stay up to date.

There is nothing to set up. Install the addon, restart Gramps, and keep working as usual.

## What changes
Each view in Gramps can have a Sidebar on the right and a Bottombar below. Each bar holds gramplets in tabs, and only the gramplet in the front tab is shown.

- **Tabs behind the front tab** already rest in Gramps. They update when you click their tab. The addon does not change this.
- **A hidden bar** is new. When you turn off the Sidebar or the Bottombar in the View menu, Gramps hides the bar but its front gramplet keeps working. For example, Person Details in the People view reads the database again every time the active person changes, even though nobody can see it. With this addon, the gramplets of a hidden bar rest.
- **Showing the bar again** brings the front gramplet up to date at once, so you never see old information.

## Undocked gramplets
You can drag a gramplet tab out of a bar to give it a window of its own. Such an undocked gramplet is always on the screen, so it always stays up to date: when its bar is hidden, when you switch to another view, and when it came from a tab that was not in front.

Without this addon, Gramps does not always wake an undocked gramplet. A gramplet undocked from a tab that was not in front could sit in its window and never update.

When you dock a gramplet back into its bar, it becomes a tab again and follows the same rules as the other tabs.

## Good to know
- The Dashboard is not changed by this addon. It has no Sidebar or Bottombar.
- Your gramplets and their settings are not touched. The addon only decides when they do their work.
- To go back to the usual Gramps behavior, disable or remove the addon and restart Gramps.

## Why this addon exists
This addon is a "monkey patch": it changes how Gramps itself behaves while it is installed, without replacing any Gramps files. The problem it solves is reported to the Gramps project in [Bug Report 14391](https://gramps-project.org/bugs/view.php?id=14391): "hidden_bars_bug_report.md". If Gramps fixes it, this addon will no longer be needed.
