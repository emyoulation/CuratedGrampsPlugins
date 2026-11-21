# Undocked Gramplets Changelog
<!-- undocked=false -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 0.1.2
- Fixed: undocking a sidebar or bottombar gramplet by dropping its tab on the toolbar or the navigator printed "g_object_ref: assertion 'G_IS_OBJECT (object)' failed" and Gtk-CRITICAL messages in the terminal. The gramplet was removed from its bar while GTK still counted the tab as dragged; it is now undocked only after the drag has ended and the tab is back in the bar.
- Fixed (Gramps core bug, same in 5.2 to 6.1): after the last gramplet of a sidebar or bottombar was undocked, "Restore to defaults" failed with "AttributeError: 'Label' object has no attribute 'gname'", because the bar then lists its undocked gramplets as objects instead of names and asks its "Gramplet Bar" placeholder tab for a gramplet name. GrampletBar.all_gramplets and remove_gramplet are corrected while this addon is active.

## 0.1.1
- Gramplets undocked from the Dashboard (GrampletWindow in grampletpane.py) are now covered too, in addition to those undocked from a sidebar or bottombar (DetachedWindow in grampletbar.py): Dock button, a title bar close button that really closes, and the smart Help button. The Dock tooltip names the view when the Dashboard category has several views (extra Dashboard views added by addons). The separate Dashboard work was merged into this addon instead of becoming a second addon.
- Sidebar and bottombar: a tab dropped in the view area (the main panel, a sidebar or a bottombar) or within 24 pixels of it no longer undocks by accident; the drag is cancelled and the tab stays. Dropping on the tabs still reorders them (or moves the gramplet to the other bar). Dropping on the main toolbar (although it borders the sidebar), the navigator, or outside the view area undocks.
- Right-click menu on a gramplet tab (sidebar or bottombar) and on the title row or drag button of a Dashboard gramplet: Move (undock without dragging) and Help (the smart Help of Markdown Utils when active, else the standard gramplet help). "Help" reuses the core "_Help" translation without its mnemonic; "Move" is a new string.
- While dragging a gramplet tab or the Dashboard drag button, a badge follows at the lower right corner of the pointer: a green square and white check mark where a drop works, or a red square and white x where it does not, replacing the subtle pointer accents. For sidebar and bottombar tabs the main window accepts the drop itself, so GTK shows its normal drag pointer where the badge is good (toolbar, navigator) and its no-drop pointer where it is bad. The badges are media/drop-point-good.svg and media/drop-point-bad.svg (drawn in code if a file is missing), with PNG copies for the README.
- The open hand pointer shows over gramplet tabs and over the Dashboard drag button, and the wrench (document-properties) icon on the Dashboard "Drag to move; click to detach" button is replaced by a larger open hand (media/hand-grab.svg, falling back to the pointer theme hand), so dragging is easier to discover. A hand drawn as the drag icon showed as a second pointer, so the hand is not used while dragging.
- Sidebar and bottombar: the tab scroll arrows are switched off while a tab is dragged and back on afterwards. Dragging the only gramplet of a bar made GTK draw those arrows with negative sizes, huge and overlapping over the bar (the "Drawing a gadget with negative dimensions" warnings).
- Dashboard: while undocked, the title row (redundant with the window title bar) is hidden and the 10 pixel border and frame are removed; both are restored on docking.
- The window title drops the redundant word "Gramplet" ("Filter - Gramps") for sidebar, bottombar and Dashboard gramplets, also after a Dashboard gramplet is renamed from the Configure dialog while undocked. The Windows menu entry keeps the word.

## 0.1.0
- Sidebar and bottombar: the Close button of the floating window becomes a Dock button showing the icon of the view the gramplet came from, the word Dock, and a sidebar or bottombar icon from the addon media folder. The tooltip names the category, and also the view when the category has several views.
- The title bar close button (x) really closes the gramplet: it is removed from its sidebar or bottombar, and can be added again from the bar menu. Only the Dock button docks. Quitting Gramps still keeps floating gramplets floating.
- The standard Help button is replaced by the unlabeled, outline-free smart Help button of Markdown Utils, only while that plugin is registered, not hidden, and provides add_help_button.
- The repeating terminal message "Drawing a gadget with negative dimensions" from the GrampletBar tab arrows is filtered out; all other GTK warnings pass through.

## Outstanding issues
### Planned / NYI
- README screenshot of an undocked Dashboard gramplet (current screenshot shows a sidebar gramplet only).
- Field-test the drag feedback and the drop rules on both X11 and Wayland: the pointer position is read from the main window, which may be stale on Wayland once the pointer leaves it.

### Needs discussion
- The context menu Help clicks an off-screen smart Help button made by MarkdownUtils add_help_button, so the menu and the button open the same help. A direct MarkdownUtils function to open the help of a plugin would be cleaner, and belongs in MarkdownUtils rather than in this addon.
- The 24 pixel band around the view area is a first guess; it makes the statusbar and the edge of the navigator next to the view cancel a drop too.
- GTK 3 always draws its own drag pointer; an addon cannot replace it with a hand. Outside the Gramps window it still shows its no-drop sign although the drop undocks (no widget there to accept the drop).
- Relabeling a Dashboard gramplet while undocked: the title row that allowed it is hidden, so the gramplet must be docked to rename it. A rename option in the floating window is possible if wanted.
- The small built-in margin of the floating dialog itself (Gtk.Dialog content area) is kept; only the Dashboard frame border is removed.

### Beyond scope
- Report the GrampletBar all_gramplets / remove_gramplet bug (empty bar with undocked gramplets) to Gramps core, so the fix does not depend on this addon.
- Making these changes in Gramps core ([grampletbar.py](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/gui/widgets/grampletbar.py), [grampletpane.py](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/gui/widgets/grampletpane.py)) instead of a monkey patch; see the earlier grampletbar.py tweaks.
