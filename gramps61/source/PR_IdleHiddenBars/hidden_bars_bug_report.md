# Gramplets in a hidden sidebar/bottombar keep updating; undocked gramplets may never update
<!-- undocked=false -->

**Category:** GUI ● **Severity:** minor ● **Product version:** Gramps 6.0.8

## Description
1. Hiding a gramplet bar (View > Sidebar or View > Bottombar) only hides the widget: `PageView.__sidebar_toggled()` and `__bottombar_toggled()` call `hide()`, and `PageView.set_active()` calls `set_active()` on both bars whether they are visible or not. The front tab of a hidden bar therefore stays active and runs `main()` on every change, unseen.
2. `DetachedWindow` (`gramps/gui/widgets/grampletbar.py`) never makes an undocked gramplet active. It keeps the state it had as a tab, so a gramplet undocked from a tab behind the front one never updates in its own window. Docking back does not reset the state either.

Tabs behind the front tab of a visible bar are handled correctly (inactive until chosen).

## Steps to reproduce
1. In the People view, hide the Bottombar and change the active person 3 times. Person Details runs `main()` 3 times.
2. In the Bottombar, undock Person Events while another tab is in front, then change the active person. The undocked Person Events window does not update.

## Suggested fix
Keep the front tab of a bar active only while the bar is visible and its view is active (for example: connect to `notify::visible`, and skip `GrampletBar.set_active()` while the bar is hidden). Make a gramplet active in `DetachedWindow.page_added()`, and re-check the tab states when it is docked back.

The addon "Idle Hidden Bars" (IdleHiddenBars) implements this as a monkey patch for Gramps 5.2 to 6.2.

*Diagnosis by Claude (Anthropic).*
