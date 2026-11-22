# PR2296 Live Preferences
[README.md](README.md) ● [DEVELOPER.md](DEVELOPER.md)

In standard Gramps, a few Preferences do not take effect until you restart Gramps. They are marked with an asterisk ( * ). This addon makes them take effect right away. It also shows an example of each choice in the Date format menu, so you can see what each format looks like before you pick it.

The date format examples come from Gramps pull request [#2296: Show date format examples in Preferences Data tab date format menu](https://github.com/gramps-project/gramps/pull/2296), by Brian McCullough (Emyoulation) and Doug Blank. This addon lets you try that change before it becomes part of Gramps.

This is a "monkey patch" addon. It changes how Gramps behaves while Gramps is running, but it does not change any Gramps files. To return to standard Gramps behavior, hide or uninstall the addon and restart Gramps.

## What changes in Preferences
- **Data tab, Date format:** the new format is used immediately in views and gramplets. The "Change is not immediate" message no longer appears.
- **Data tab, Date format menu:** each format shows an example date, for example "Month Day, Year  (April 21, 2001)". The example date is April 21, 2001, the date of the first Gramps release.
- **Data tab, Age display precision:** ages change immediately in the Relationships view, the Events gramplet and the Events tab of editors.
- **Data tab, Display ages for events after death:** takes effect immediately in the Events tab of editors.
- **General tab, Show text label beside Navigator buttons:** the Navigator buttons gain or lose their text labels immediately.
- **Both tabs:** the asterisks and the "* Requires Restart" notes are removed, because no restart is needed for these settings.

## Good to know
- An editor window that is already open keeps showing the old dates and ages. Close the editor and open it again to see the new setting.
- A gramplet in its own separate (undocked) window may not update until you change the active person or reopen the gramplet.
- Navigator layouts added by other addons change only if they build their buttons the same way that the standard Gramps Navigator layouts do.
