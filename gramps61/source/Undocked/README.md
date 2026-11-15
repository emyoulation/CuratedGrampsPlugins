# Undocked Gramplets
<!-- undocked=false -->

Welcome. Any gramplet in the sidebar or bottombar of a Gramps view can be pulled out into its own floating window. That floating window has a plain **Close** button, which does not say that closing it puts the gramplet back where it came from. Undocked Gramplets makes the window clearer.

![An undocked gramplet with the Dock button](media/screenshot.png)

## What you get

**A Dock button instead of Close.** The button shows the icon of the view the gramplet came from, the word **Dock**, and an icon showing the destination, either the sidebar or the bottombar. Hover over the button for a longer description. Clicking it returns the gramplet to its place, exactly as Close did before.
![the Sidebar Dock indicator](media/sidebar-show-bottom.svg)
![the Bottombar Dock indicator](media/sidebar-show-bottom.svg)

**A smarter Help button, when available.** If the Markdown Utils addon is installed and active, the standard Help button is replaced by the small unlabeled Help button from that addon. It stays in the lower left corner of the window. If Markdown Utils is not installed, is hidden in the Plugin Manager, or is too old to offer this button, the standard Help button is left exactly as it is.

## Which gramplets are affected

Every gramplet that can be undocked from a sidebar or bottombar, for example Filters, Fan Chart, Statistics, or the Collections Clipboard. The addon is not tied to any one gramplet.

Gramplets undocked from the **Dashboard** use a different kind of window and are not changed. They keep the plain Close button.

## Installing

1. Install the addon with the Gramps Addon Manager, or copy the **UndockedGramplets** folder into your Gramps user plugins folder.
2. Close Gramps completely and start it again. The addon takes effect at startup.

Nothing in Gramps is overwritten. The addon adjusts the floating window while Gramps starts.

## Removing

Delete the **UndockedGramplets** folder, or hide the addon in the Plugin Manager, then restart Gramps. The original Close and Help buttons return.

## Good to know

- Your family tree data is never changed.
- Some custom views have no icon of their own in the current icon theme. In that case the icon of the view category is shown instead, and if neither is available the button shows only the word and the destination icon.
- You may see a harmless message in the terminal, such as `Gtk-WARNING: Drawing a gadget with negative dimensions`. It comes from the way the sidebar and bottombar draw their tab arrows. It was present before this addon and does not affect anything.
- Works with Gramps 5.2 and newer.
- Runs alongside the Clipboard Ref Menu addon. The two are independent and each works without the other.

## Troubleshooting

- **Still see the Close button:** restart Gramps completely, then check that the addon is listed and not hidden in the Plugin Manager. Also check that the gramplet was undocked from a sidebar or bottombar and not from the Dashboard.
- **Still see the standard Help button:** this is expected unless Markdown Utils is installed, active, and new enough to provide the smart Help button.
