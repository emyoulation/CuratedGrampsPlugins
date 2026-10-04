# Change Log (Photo Tagging gramplet)
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [XMP data](XMP_Region_Name.md) ● [Icon List](media/icons/ICONLIST.md) 

## What's New
Version 1.2.3 - Sep 2026

#### Stability fixes
- Fixed placeholder marquees silently disappearing on reload whenever their rectangle touched or overlapped a neighboring tagged face's marquee — the common case in any tightly-packed group photo (a school class, a family portrait), where adjacent people's marquees legitimately share an edge by construction rather than duplicating the same face. A real-world 26-person class photo surfaced this directly: two still-unlinked placeholders sitting shoulder-to-shoulder with already-tagged neighbors kept vanishing every time the photo was reopened, forcing them to be redrawn from scratch each time.
- Fixed several crashes (`SIGSEGV`, not a catchable Python error — Gramps simply disappeared) traced to mutating the region list's own internal model from inside a GTK cell-editing or drag-and-drop signal handler before it had finished unwinding. The underlying actions (committing a typed placeholder name, completing a drag) are now deferred until that settles, the same fix applied everywhere else this pattern already existed.
- Fixed the region list losing track of the selected row, or the photo preview narrowing down to a single dimmed marquee instead of showing every tagged face, after drawing a new marquee or reordering rows while Quick Draw mode was active — several separate places that read "what's currently selected" weren't accounting for Quick Draw mode deliberately keeping nothing selected on the image itself.
- Fixed the Name column showing a person's alternate name instead of their preferred one, and ages not displaying at all regardless of whether the photo had its own date. Both traced to the same mistake: a Gramps date-validity check (`get_valid()`) that only rules out unparseable text, not an actual empty/unset date — so a Name or Event with no date entered at all was being treated as if it had a real one.
- Fixed the photo preview's initial size ignoring the Caption panel's own height until something else (a window resize, switching to another application and back) forced a fresh layout pass.
- The Fuzzy Matching gramplet's lookup window can now report a double-clicked match straight back to the row that opened it, rather than only ever opening that person's own editor — closing a gap in that addon's own API that had no other way to hand a chosen match back to a caller.

#### Known limitations
- **The Row ID column's "Move Row" dialog is more interface friction than it should be.** Double-clicking a row's number opens a full modal dialog (a spin button plus OK/Cancel) instead of editing the number in place. A direct inline edit was tried twice and reproduced the same GtkTreeView crash fixed above — mutating the treeview's model from inside a cell's own "edited" signal handler, even deferred, was enough to corrupt its internal row-height bookkeeping. The dialog sidesteps that by being a separate widget entirely, but it's acknowledged to be too heavy for how often this gets used; a lighter option (e.g. a small popover anchored to the cell, with no OK/Cancel chrome) is worth revisiting once the rest of the gramplet has settled.
- **Row selection during Quick Draw mode doesn't yet survive every action.** Drawing a marquee or reordering rows already capture their target row before triggering a refresh, so the list stays correctly focused afterward (see the fix above) — but Add a new person, Link, Clear Reference, Remove, Move Up/Down, Edit Person, and Set Active Person don't yet do the same, so the list can still drop back to no row focused after one of those runs during Quick Draw mode.

### Future objectives
* extend the pre-refresh selection-capture fix above to every remaining toolbar/context-menu action
* a lighter-weight replacement for the Row ID "Move Row" dialog
* a companion tool to flatten this gramplet's tagging (and other metadata) back into the file's own embedded/sidecar XMP
* piping a placeholder name to other gramplets' own fields (Relationship Filter, Data Entry) beyond the Fuzzy Matching integration and clipboard copy added in 1.2.2
* more flexibility in indexing (row/column? e.g., 7a, or G5)
* persistent Indexing (re-index options: automatic, on-demand)

---

Version 1.2.2 - Sep 2026 (beta)

A field test tagging a photo — an AI-"restored" newspaper clipping that had reconstituted several faces as similar-but-different people, so every single one of them needed researching from scratch — took over 90 minutes with the gramplet as it stood: drawing rectangles, reordering them so the row numbers matched the caption's own left-to-right order, typing placeholder names, and linking each one to a Person one at a time. That's the process this release is aimed at. The same test, redone after these changes, took about 15 minutes.

#### Quick Draw mode
- New **Quick Draw** toggle button leads the toolbar, and is on by default: draw one marquee after another with nothing popping up in between and no placeholder name required until you're ready to type one. A context menu appearing after every single rectangle — previously unavoidable — was most of the original friction on its own.
- While it's on, every already-tagged marquee stays visible with its row number overlaid, so you can see exactly who's already placed, and in what order, while adding more.
- Rows can be reordered afterward by drag-and-drop, the right-click menu's Move Up/Down, or by double-clicking a row's own index number and entering a new position directly.

#### Turning a caption into a research worklist
- If a photo already has its own descriptive text — say, OCR'd from underneath a newspaper clipping — saved as a Caption-type Note on the Media object, a name selected in that Note's editor can now be dragged straight onto the region list to create a placeholder row for it. A caption naming eight people becomes eight rows to research, without retyping any of them by hand.

#### Fuzzy Matching integration
- With the Fuzzy Matching gramplet installed, each row's Metadata clues icon (and its own context-menu entry) now offers a **Fuzzy Match Lookup** — opens that addon's own lookup window, pre-seeded with the row's name, to check whether a matching Person already exists in the tree before creating a new one.
- Double-click a match there (or drag it out, as before) to link it straight to the row that asked for it.
- A found match's age is calculated from the photo's own date and their birth information, the same as everywhere else in this gramplet — shown in red if that date falls outside their actual lifespan.
- If nothing matches, the placeholder name and its rectangle are still cached in a Custom Attribute on the Media object either way, so nothing typed is ever lost while the research continues.

#### One name, several ways to use it
- Typing or confirming a name once now cascades to everywhere it's needed: the **+** icon on a row sends it straight to the New Person dialog, linking that Person to the row automatically the moment its editor is closed with OK; the same name seeds a Fuzzy Match Lookup; and it's still available as plain text copied to the clipboard for pasting into another tool entirely.

### Future objectives
* place holder rectangles that don't disappear when adjacent to another marquee — fixed in 1.2.3
* more flexibility in indexing (row/column? e.g., 7a, or G5)
* persistent Indexing (re-index options: automatic, on-demand)

---

Version 1.2.0 - Sep 2026

#### Region storage rewritten as structured metadata, not a private table
- The manual reorder table this gramplet kept in a `PhotoTagging Order` Attribute is replaced by a `PhotoTagging Regions` Attribute: a small JSON document using the same field names as the embedded MWG metadata this gramplet already reads (name, type, position, size), rather than a bespoke layout of this gramplet's own invention. A photo already tagged under 1.1.x has its order recovered automatically the first time it's opened under 1.2.0.
- Each entry now also records **where it came from** — confirmed and linked in Gramps, read from the file's own embedded metadata, or typed in by hand — so a clue from the file is remembered even after being superseded by a real link, instead of being silently dropped the moment it's no longer the one being shown.

#### Metadata clues no longer disappear as a group
- Previously, linking **any one** embedded face on a photo to a Gramps person stopped the gramplet from reading embedded metadata for that photo at all — every other, still-unclaimed clue vanished from the list along with it. Assigning one person now only suppresses the clue **at that same position**; everyone else the file already knows about stays offered.
- `mwg-rs:Type` (Face, Pet, Focus, etc.) is now carried through into the gramplet's own records instead of being read and thrown away.

#### Placeholder names for people you haven't linked or created yet
- The **Name** column is now directly editable for any row that isn't linked to a Person yet — pre-filled from an embedded clue when there is one, and remembered once you type your own.
- A new icon beside the Name column opens **Add a new person**, pre-filled from that row's placeholder text — one click closer than typing the name twice.
- A new icon beside Metadata clues copies that same name, formatted "Surname, Given", to the clipboard, ready to paste into another tool's own name field.

#### Rotated photos now display upright, marquees included
- A photo whose embedded orientation metadata calls for a 90°, 180°, or 270° rotation is now displayed corrected — both the photo itself and every marquee on it, whether already tagged, freshly drawn, or resized.
- Thumbnails in the region list are cropped from that same corrected image, matching what the Preview panel shows.
- Mirrored orientation values (as opposed to a plain rotation) are not corrected — real cameras essentially never produce them, only manual edits do.
- This is a **display-only** correction. It does not modify the original file, and does not change what any other program (including Gramps's own other thumbnail displays, and other gramplets) shows for the same photo — see the [XMP data](XMP_Region_Name.md) writeup for why that's a deliberately separate, bigger decision this release doesn't make on its own.

#### Selection and stability fixes
- Selecting a row, marquee, or a linked name in the Caption panel now also sets that person as active elsewhere in Gramps, matching the existing "Make the person active" menu item's own effect.
- The Caption panel's text is now center-aligned.
- Fixed the gramplet not noticing a Person had been deleted elsewhere in the tree while their tagged photo was still open, which could leave a row referencing them until something else happened to trigger a refresh.
- Fixed a rare crash while dragging a marquee's resize handle, caused by an image reload racing with an in-progress drag.
- Fixed a crash clicking the new "Add a new person" icon when the placeholder text included a surname.

### Future objectives
* a companion tool to flatten this gramplet's tagging (and other metadata) back into the file's own embedded/sidecar XMP
* piping a placeholder name to other gramplets' own fields (Fuzzy Match, Relationship Filter, Data Entry) beyond the current clipboard copy
* more flexibility in indexing (row/column? e.g., 7a, or G5)
* persistent Indexing (re-index options: automatic, on-demand

---

Version 1.1.3 - Sep 2026

#### Caption panel
- A new **Caption panel** sits below the photo preview, showing the photo's own "Caption"-type Note live — the same Note "Transcribe list to a Note" creates (see below), and the one visible on the Media editor's own Notes tab. It's read-only there; double-click it to open it for actual editing.
- **Selection is now coupled across all three panels that can show it** — the region list, the marquees on the photo, and the Caption panel's own linked person names. Selecting a person in any one of the three highlights them in all three; double-clicking any one opens that person's editor.
- A new **Show/Hide Caption** toolbar button toggles the panel, and is dimmed when the current photo has no Caption Note yet. **Double-clicking that dimmed button** creates one on the spot — the same action as "Transcribe list to a Note" below.
- The split between the photo preview and the Caption panel is a draggable divider, remembered as a proportion of the available height (not a fixed pixel count), so it survives resizing the gramplet or undocking it into its own window.
- Right-click the Caption panel for a **Caption Font...** option, to choose its own base font family and size — remembered across sessions, independent of your overall Gramps font.

#### Transcribe list to a Note, now feeding the Caption panel
- "Transcribe list to a Note" (right-click menu, or double-clicking the dimmed Show/Hide Caption button above) now always creates the same **Caption**-type Note the new Caption panel displays, rather than a plain Note — so the two features produce and show the same thing, instead of two disconnected ones.
- This is worth calling out on its own, separately from the tagging itself: **every name in the generated text is the person's own name as of the photo's date** — the same date-aware, "Display As"-respecting name lookup the region list itself already uses (see Person and Age display, 1.1.1 below) — not just whichever name or format happens to be their current one. Getting that right by hand, for every person, across a large multi-generation photo archive, is exactly the kind of tedious, easy-to-get-wrong work this automates.
- Unlike the tagging itself — marquees and thumbnails that only ever show up inside this gramplet's own window — a Caption Note is a normal Gramps Note attached to the Media object, so it's available to Gramps's own narrative reports and books wherever they include Media notes. A tagged photo becomes an actually captioned one outside of Gramps too, not just inside this gramplet.
- The Note still opens for review, unsaved, before anything is written — free to rearrange or rewrite by hand into a polished caption; the generated text is meant as a starting draft, not a finished one.

#### Selection and scrolling fixes
- A click that switched the selection from one marquee to another no longer visibly flashes the whole photo mask, Caption highlight, and row selection off and back on.
- A double click on a marquee or a row now reliably opens the Person editor for the person actually clicked, instead of sometimes doing nothing, or shifting the row selection instead. Row selection no longer sporadically jumps to row 1 after resizing a marquee or editing a person from a double-clicked marquee.
- Resizing a marquee by dragging one of its handles no longer risks collapsing it to zero width/height — a resize that would leave it smaller than a sane minimum is rejected and the marquee snaps back to its prior size instead.
- Fixed a crash (`WindowActiveError`) double-clicking a marquee or row whose person already had an editor window open — it's simply ignored now, the same as everywhere else in the gramplet this can happen.
- The region list and the Preview panel now both scroll a newly selected row or marquee into view only when it's actually off screen, rather than the list unpredictably re-centering itself on every click.

### Future objectives
* place holder marquees
* more flexibility in indexing (row/column? e.g., 7a, or G5)
* persistent Indexing (re-index options: automatic, on-demand
* "Common name" label overlays with CSS

---

Version 1.1.1 - Sep 2026

#### Metadata clues (renamed from "XMP Region Name")
- The column is now called **Metadata clues**, and can be shown or hidden with a new toolbar toggle button, without discarding anything it found.
- When a photo has no usable face-region metadata at all, the gramplet now falls back to the file's `Xmp.dc.subject` tag — a much more commonly supported, if less precise, list of names with no per-person position — rather than showing nothing. Names found this way are shown against the whole photo, labeled "*(whole photo, no region)*" so they're never mistaken for a real, positioned region.
- See [XMP data](XMP_Region_Name.md) for the full technical detail, including a real, now-fixed bug that could leave this column silently empty on some installs (a missing optional component of the underlying GExiv2 library, unrelated to the photo file itself).
- A context menu to "Transcribe list to a Note" will create a new (unsaved) Note for the Media object. The simplified list of XMP metadata is one subsection of the Note. 

#### Person and Age display
- The Person and Age columns are now one column, "Name", showing the person's name and their age on two lines.
- **The name shown is the one the person was actually using at the time of that photo** — their birth name in a childhood photo, a married name in a later one — chosen from their own Gramps Name records by the photo's date (or today's date, if the photo has none), and rendered using that specific Name record's own "Display As" format when one is set, not just whichever format is configured as your overall Gramps default.
- The age shown is now always calculated as of the photo's own date, or today's date if the photo has none — previously a photo with no date fell back to showing a deceased person's age at death instead; it now shows their age as of today consistently, matching how the name is chosen.

#### Right-click context menu
- New **See the person details** item, doing the same thing as double-clicking the row.
- "Set as active person" is now **Make the person active**.
- "Select" is now **Link**, and "Add" is now **Add a new person** — matching wording used elsewhere in Gramps for the same actions, and now used consistently for the equivalent toolbar buttons and dialog titles too.
- "Replace to *(name)*" is now **Swap with *(name)***, and — more importantly — now does what that name implies: it swaps person assignments between the two marquees involved, leaving both exactly where they are, rather than deleting the other person's own marquee and losing track of whoever was previously in the selected one.
- "Clear" is now **Clear Reference**, matching the toolbar button for the same action.
- New **Transcribe list to a Note** item — see below.

#### Transcribe list to a Note
- A new context menu action creates a Note attached to the photo — the same effect as clicking "create and add a new note" in the Media editor — pre-filled with:
  - The photo's title (bold), date, and Gramps ID (linked).
  - Every tagged person's name, semicolon-separated, each linked to their Gramps record. (Formatted to be the foundation of a caption.)
  - Any Metadata clues for people who aren't tagged yet, one per line.
  - The underlying row-to-person tagging order, with each ID linked and each person's name alongside it.
- The Note opens for you to review before saving, exactly like any other new Note.

#### Visual polish
- Alternating rows in the list are now lightly shaded for easier reading on longer lists, in a neutral gray that works on both light and dark Gramps themes.
- All "box"/"boxes" wording in the interface — tooltips, the settings dialog, menu items — now consistently says "marquee"/"marquees".
- The new "Show/Hide Metadata clues" toggle button now matches the existing "Show/Hide face marquees" button's convention: the default, data-showing state is a plain, unpressed icon, and only the non-default "hidden" state shows a pressed/highlighted button — previously the two toggle buttons used opposite conventions.

#### Stability fixes
- Fixed a real, confirmed cause of the Metadata clues column staying silently empty on some installs (see [XMP data](XMP_Region_Name.md) for the full writeup): the gramplet no longer depends on an optional Python convenience layer some GExiv2 packages don't include, and now logs a genuine, unexpected metadata-reading failure instead of discarding it with no trace, while still quietly ignoring the routine case of a non-photo file (such as an SVG icon) having no metadata to read.
- Fixed a crash when saving a newly-created person for a tagged marquee before giving them a birth date.
- Fixed a crash when swapping person assignments between two marquees (see "Swap with" above), caused by Gramps's own database-update notifications firing in the middle of the swap.
- Notes created by "Transcribe list to a Note" contain working links, rather than plain, unlinked text.

---

Version 1.1.0 - 1 Sep 2026


#### Reordering tagged people
- You can now reorder the people tagged in a photo — drag and drop a row in the list, use the new Move Up/Down toolbar buttons or right-click menu, or press Alt+Up / Alt+Down.
- The row you just moved stays selected, so you can move it again right away without re-clicking it.
- Your custom order is saved and will still be there the next time you open that photo, or reopen Gramps — it's written efficiently (only when you leave the photo), not after every single move.

#### Age display
- The Age column now shows how old each person was *in that photo* (calculated from the photo's own date), instead of always showing their age as of today. If the photo has no date, it falls back to their age at death, or their current age if still living.
- If an age doesn't add up — the photo is dated more than about 10 months before the person was born, or more than a month after they died — that age is shown in red, flagging a possible wrong photo date or wrong person tagged.

#### Face marquee display
- New "Show/Hide face marquees" toggle button — temporarily hide all the outline boxes to see the photo clearly; it automatically turns boxes back on if you select a row or draw a new one.
- New "Show ID" toggle button (click repeatedly to cycle): show the row number in each box, show the person's Gramps ID instead, or show nothing.
- That label is now blue text on a white background (matching the box color) instead of yellow, and the row-number version is drawn extra large for easy reading.
- Both new toggle buttons are now the first two icons on the toolbar, and all toolbar icons are bigger (32×32) for visibility.

#### Refreshed and enlarged toolbar icons
- Several toolbar buttons now use new, clearer artwork instead of generic system icons that could look ambiguous or barely different from one another depending on your desktop theme: Select Person, Add Person, Clear Reference, and Edit Referenced Person all have distinct new icons, and Move Up/Down now use up/down sorting arrows that are easier to tell apart at a glance.
* ![Select existing Person](media/icons/gtk-edit.svg) 
* ![Add Person Marquee](media/icons/List-add.svg) 
* ![Remove Marquee](media/icons/List-remove.svg) 
* ![Edit Person](media/icons/gtk-edit.svg) 
* ![Move Up](media/icons/Gnome-view-sort-ascending.svg) 
* ![Move down](media/icons/Gnome-view-sort-descending.svg) 
* ![Zoom in](media/icons/gramps-zoom-in.svg) 
* ![Zoom out](media/icons/gramps-zoom-out.svg)  
* ![Face Detection](media/icons/gramps-face-detection.svg) 

#### Stability fixes
- Fixed a crash that could take down the whole photo view if a bundled icon file was missing from the install.
- Fixed an issue where the gramplet could fail to start, or pick up the wrong image-metadata library, on systems with more than one version of the underlying [GExiv2 library](https://wiki.gnome.org/Projects/gexiv2) installed.
- Fixed a couple of console warnings/glitches related to unusual face-box shapes and empty selections.
