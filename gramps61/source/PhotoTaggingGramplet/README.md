# Photo Tagging Gramplet
[ReadMe](README.md) ● [Change Log](CHANGELOG.md) ● [XMP data](XMP_Region_Name.md) ● [Icon List](media/icons/ICONLIST.md)

The **Photo Tagging** addon is a Media category [**gramplet**](https://www.gramps-project.org/wiki/index.php/Gramps_Glossary#gramplet) for [Gramps](https://gramps-project.org), the free genealogy software. It lets you draw marquees directly on a photo overlay to mark where each person appears, and link each marquee to the Gramps record for that person — similar to how photo tagging works in most modern photo apps.

Tagging your photos this way means Gramps can tell you, and later generate reports showing, which people appear together in which pictures — turning a folder of scanned family photos into a searchable part of your family tree.
![The undocked Photo Tagging gramplet](media/screenshot.png)

## Features
- **Tag people in photos** by drawing a marquee (a rectangle) around them and linking it to a person in your tree, or by dragging a person directly onto the image or onto the list.
- **Precise marquees.** Marquees are drawn and saved at full pixel precision, so a marquee fits a face closely even in a large scan of a crowded group photo. See [How marquees are saved](#how-marquees-are-saved).
- **Quick Draw mode** — draw one marquee after another with nothing popping up in between. Every marquee already on the photo stays visible with its row number, so you can see who is placed, and in what order, while you add more. It switches on by itself for a photo with nothing on it yet. See [Quick Draw mode](#quick-draw-mode).
- **Placeholder names for people you have not researched yet** — type a name straight into the Name column of any unlinked row (or drag one in from the Caption panel). It is saved with the photo, so nothing you type is lost while the research continues, and it pre-fills **Add a new person** and **Fuzzy Match Lookup** when you get to that row.
- **Turn those tags into a real photo caption**, not just an in-app label. A **Caption panel** below the photo shows a "Caption"-type Note, built from your tags and any Metadata clues, that you can rearrange into an actual caption. Every name in it is the name the person used as of the date of the photo. And because it is a normal Gramps Note attached to the Media object, it is available to the narrative reports and books in Gramps. See [Using the Caption panel](#using-the-caption-panel).
- **Optional automatic face detection** — one click finds faces in the photo and draws marquees for you, ready to be assigned to people. (Requires the OpenCV and NumPy libraries; see [Requirements](#requirements).)
- **Optional Fuzzy Matching integration** — with the Fuzzy Matching gramplet installed, look up the name in a row phonetically to check whether that person is already in your tree before creating a new one, and double-click a match to link it to the row.
- **Reorder tagged people** — drag and drop rows in the list, use the Move Up/Down toolbar buttons or right-click menu, press Alt+↑ / Alt+↓, or double-click a row number and type the position you want. Your order is remembered the next time you open the photo.
- **The name shown for each person is the one they were actually using in that photo** — a birth name in a childhood photo, a married name in a later one — chosen from their Gramps Name records by the date of the photo, and shown in the "Display As" format of that Name when one is set.
- **Age at time of photo** — shown right under the name, calculated from the date of the photo (or from the date today if the photo has no date). An age that does not add up — the photo predates the birth of the person, or postdates their death — is shown in red, a useful way to catch a wrong photo date or a wrongly tagged person.
- **Rotated photos display upright.** A photo whose orientation metadata calls for a 90°, 180°, or 270° rotation is shown corrected, marquees and thumbnails included. The original file is never modified.
- **Show/hide face marquees** and **cycle marquee labels** between row number, Gramps ID, or no label at all, via two toggle buttons on the toolbar.
- **Metadata clues column** — if a photo already has names recorded by another program, the gramplet shows them as a starting point, without creating anything in Gramps until you confirm them:
  - Named face regions written by a camera, phone, or photo organizer that uses Metadata Working Group (MWG) region tags — shown at their own position on the photo. These are read from the image file itself, or from a same-named `.xmp` sidecar file next to it (for example, `photo.xmp` beside `photo.jpg`).
  - If there are none, named faces recorded by Picasa in the `picasa.ini` file of the folder.
  - If there are none of those either, a flat list of names from the `Xmp.dc.subject` tag of the file (much more commonly supported, but with no per-person positions) — shown as whole-photo placeholders.
  - The first time a photo is opened, everything found is saved with the photo (see [How marquees are saved](#how-marquees-are-saved)). After that, the saved copy is used and the original files are not read again.
  - A toolbar toggle button shows or hides this column entirely.
- **Right-click context menu** for the selected marquee or row — see [Right-click menu reference](#right-click-menu-reference).
- **Selection is coupled across all three panels** — the tagged-people list, the marquees on the photo, and the linked names in the Caption panel. Selecting a person in any one highlights them in all three, and makes them the active person elsewhere in Gramps; a double click on any one opens the editor for that person.
- **Drag a person in** from the Clipboard or another Gramps view (such as the People list) straight onto the photo or onto the tagged-people list.
- Alternating rows in the list are lightly shaded for easier reading on longer lists.

## Requirements
- Gramps 5.2 or 6.x, with the [GExiv2 image-metadata library](https://wiki.gnome.org/Projects/gexiv2) available (normally bundled with a standard Gramps install). The gramplet will not load without it.
- **Automatic face detection is optional.** To enable it, install the [OpenCV](https://opencv.org/about/) and [NumPy](https://numpy.org/about/) Python libraries for the same Python that Gramps uses. Windows users in particular should note that these do not ship with Gramps by default. Without them, the **Detect faces** button is simply hidden; everything else works.
- **Fuzzy Matching lookups are optional.** They require the Fuzzy Matching gramplet addon. Without it, the Fuzzy Match Lookup actions do nothing.
- **Markdown Dash is optional.** If installed, the **Help** button opens this README inside Gramps.

## Installation
Install the Photo Tagging Gramplet from within Gramps using the built-in **Addon Manager** (*Edit → Addon Manager*, or search for "Photo Tagging" in *Help → Check for updated addons*). Restart Gramps after installing, and the gramplet will be ready to add to a view.

## Usage
1. Open the **Media** category view.
2. Right-click the sidebar or bottombar and choose **Add a Gramplet → Photo Tagging**.
3. Select a photo. The gramplet shows the image (with the Caption panel below it) on the left, and the list of tagged people on the right.

![Sample data from a `.xmp` sidecar](media/Antietam_Sample.png)

### The tagged-people list
| Column | What it shows |
|-----|----------------------------|
| *(row number)* | The position of the row. Double-click it to open a small box beside it, type the new position, and press Enter (Esc cancels). |
| Preview | A thumbnail cropped from the marquee. |
| **+** icon | Shown only on unlinked rows. Opens **Add a new person**, pre-filled from the placeholder name of the row. |
| Name / Age on *date* | The name of the linked person and their age as of the date of the photo. On an unlinked row, an editable placeholder name. |
| Search (magnifier) icon | Shown only on unlinked rows that have a Metadata clue. Click once to copy the clue to the clipboard as "Surname, Given"; double-click to open a **Fuzzy Match Lookup** for it. |
| Metadata clues | The name recorded in the metadata of the photo, if any. It stays visible after the row is linked, so you can always see what the file originally said. |

Click a row to select that person everywhere: the row, the marquee on the photo, and their link in the Caption panel.

### Tagging a person
- Drag a marquee (a rectangle) around the face or figure of the person on the image.
- With the marquee selected, either:
  - Click **Add a new person** (or the **+** icon of the row) to create a new Person and link them — the new person is linked to the row automatically when you close their editor with OK, or
  - Click **Link** to link an existing Person from your tree, or
  - Drag a person from another Gramps view directly onto the marquee or its row.
- Click **Edit referenced Person** (or double-click the row, or right-click it and choose **See the person details**) to open the editor for the linked person, **Clear Reference** to unlink the person from that marquee (keeping the marquee), or **Remove Selection** to delete the marquee entirely.

### Quick Draw mode
Quick Draw mode is for placing many marquees at once. While it is on, nothing pops up after each marquee you draw, and every marquee on the photo stays visible with its row number.

- **When it switches on:** when you open a photo that has nothing on it yet — no tagged people, no saved placeholders, and no names found in its metadata.
- **When it switches off:** when you open a photo that already has marquees, or when you click a row in the list or a linked name in the Caption panel to select a person.
- You can switch it on or off yourself at any time with the **Quick Draw** toolbar button.

With Quick Draw off, the right-click menu opens automatically after you draw each marquee, ready for you to link or add a person.

### Tagging a group photo quickly
This is the workflow Quick Draw mode is built for — a class photo, a family reunion, a newspaper clipping with a list of names underneath.

1. **Draw every marquee first.** On a photo with no marquees yet, Quick Draw is already on: drag one marquee after another. Nothing pops up between them, and the row numbers on the photo show the order you have drawn them in.
2. **Put the rows in caption order.** Drag rows, use Move Up/Down, or double-click a row number to move it straight to a position, so the numbering matches how the caption reads (left to right, front row first, and so on).
3. **Name each row.** Type a placeholder name into the Name cell of each row. If the photo already has a Caption Note (for example, text scanned with OCR from beneath a newspaper photo), you can select a name in the Caption panel and drag it onto a row instead of retyping it. Placeholder names are saved with the photo.
4. **Research and link each row**, one at a time:
   - Right-click → **Fuzzy Match Lookup…** (or double-click the search icon, if the row has a Metadata clue) to check whether the person is already in your tree. Double-click a match to link it to the row.
   - If they are not in the tree yet, click the **+** icon of the row to create them, pre-filled from the placeholder name.
   - Or **Link** an existing person by hand.

### How marquees are saved
Gramps stores the position of a person in a photo as four whole-number percentages. On a large scan, 1% can be 60 pixels or more, which is too coarse to fit a face closely. This gramplet keeps two copies of each marquee:

- **A whole-number copy for Gramps**, in the Media Reference of the person, rounded outward so that it always contains the real marquee. Reports, the Media Reference editor, exports, and other gramplets use this copy exactly as before.
- **A precise copy for this gramplet**, in a `PhotoTagging Regions` attribute on the Media object, together with the row order, placeholder names, and Metadata clues.

When a photo is opened, the precise copy is used as long as it still matches the whole-number copy. If the marquee was changed somewhere else in the meantime (for example, in the Media Reference editor), that change wins. Photos tagged with earlier versions of this gramplet open exactly as before.

### Using the Caption panel
The Caption panel sits below the photo preview and shows the "Caption"-type Note of the photo — the closest thing this gramplet has to a finished, human-readable caption, as opposed to the tags themselves (which only ever show up inside this window).

- **Creating a caption for a photo that does not have one yet**: the Show/Hide Caption toolbar button is dimmed when there is nothing to show. Double-click it (or right-click the list and choose **Transcribe list to a Note**) to generate a Caption Note from your current tags and Metadata clues.
- The generated text is a **starting draft**, not a finished caption: it opens in the Note editor, unsaved, for you to rearrange, trim, or rewrite before it is saved to the photo. Every name in it is already the name the person used as of the date of the photo, so you are editing wording, not looking up names.
- Once saved, it appears in the Caption panel automatically — and, being a normal Gramps Note, it also shows up wherever the reports and books in Gramps include Media notes.
- **Reading it**: the Caption panel is read-only. Click the name of a linked person to select them everywhere (their row, their marquee, and their highlighted name here); double-click their name to open their Person editor. Double-click any other linked object, or a plain web link, to open it the same way Ctrl+click would elsewhere in Gramps.
- **Using it as a name source**: select a name in the Caption panel and drag it onto an unlinked row to set the placeholder name of that row.
- **Editing it**: double-click anywhere in the Caption panel that is *not* a link to open the Note editor for the whole caption.
- **Showing/hiding it**: click the Show/Hide Caption toolbar button. The divider between the photo and the Caption panel can be dragged to whatever split you prefer — it is remembered as a proportion of the available height, so it stays put whether you resize the gramplet or undock it into its own window.
- **Changing its font**: right-click inside the Caption panel and choose **Caption Font...** to pick a base font family and size for the panel, independent of your overall Gramps font.

### Toolbar reference
![Toolbar buttons](media/PhotoTagging_toolbar.png)

| Button Name | Action |
|-----|----------------------------|
| Quick Draw | Draw several marquees in a row with nothing popping up in between; all marquees stay visible with their row numbers while it is on. Switches on by itself for a photo with nothing on it yet (see [Quick Draw mode](#quick-draw-mode)). |
| Show/Hide face marquees | Temporarily hides all marquees so you can see the photo clearly. |
| Show ID | Cycles the label shown in each marquee: row number, Gramps ID, or none. |
| Show/Hide Caption | Shows or hides the Caption panel. Dimmed when the photo has no Caption Note yet — double-click it to generate one (see [Using the Caption panel](#using-the-caption-panel)). |
| Show/Hide Metadata clues | Shows or hides the Metadata clues column without discarding anything it found. |
| Link | Link the selected marquee to an existing person in your tree. |
| Add a new person | Create a new person and link them to the selected marquee. |
| Clear Reference | Unlink the person from the selected marquee, keeping the marquee. |
| Remove Selection | Delete the selected marquee entirely. |
| Edit referenced Person | Open the Person Editor for whoever is linked to the selected marquee. |
| Move Up / Move Down | Reorder the selected person in the list. |
| Zoom In / Zoom Out | Zoom the photo in/out. |
| Detect faces | Automatically find faces in the photo and draw marquees for them. Only shown when OpenCV is installed. |
| Settings | Open the settings dialog of the gramplet (see below). |
| Help | Open this README (in Markdown Dash, if installed), otherwise the online help page of the gramplet. |

### Right-click menu reference
Right-click a marquee on the photo, or a row in the list, for a context menu with the following, in order:

| Menu Item | Action |
|-----|----------------------------|
| See the person details | Opens the Person Editor for whoever is linked to the selected marquee — the same action as double-clicking the row. |
| See ancestor family details | Opens the Family editor for the family in which the linked person is a child. If the person has more than one parent family (for example, birth and adoptive), one Family editor opens for each. Dimmed when there is no parent family. |
| See descendant family details | Opens the Family editor for the family in which the linked person is a parent. If the person has more than one spouse or partner, one Family editor opens for each family. Dimmed when there is no such family. |
| Make the person active | Sets whoever is linked to the selected marquee as the active person elsewhere in Gramps. |
| Link | Link the selected marquee to an existing person in your tree. |
| Add a new person | Create a new person, pre-filled from the placeholder name of the row, and link them to the selected marquee. |
| Clear Reference | Unlink the person from the selected marquee, keeping the marquee. |
| Fuzzy Match Lookup… | Opens the lookup window of the Fuzzy Matching addon, seeded with the Name of the row, to find a possible existing match. Double-click a match there to link it to this row. Requires the Fuzzy Matching addon. |
| Remove | Delete the selected marquee entirely. |
| Move Up / Move Down | Reorder the selected person in the list. |
| Transcribe list to a Note | Creates the Caption-type Note of the photo (the one the Caption panel shows — see [Using the Caption panel](#using-the-caption-panel)), pre-filled with the title, date, and ID of the photo, the tagged people (each linked to their Gramps record, with the name they were using as of the date of the photo), any Metadata clues, and the underlying tagging order, as a starting draft to rearrange into an actual caption. |
| Swap with *(name)* | One entry per other tagged person on the same photo. Swaps person assignments between the selected marquee and the marquee of that person — both marquees stay exactly where they are; only who is linked to each one trades places. |

### Reordering people
Once more than one person is tagged, you can put them in whatever order makes sense to you (for example, left-to-right, or by age):

- Drag and drop a row in the list, or
- Select a row and click **Move Up** / **Move Down**, or use the right-click menu, or
- Select a row and press **Alt+Up** / **Alt+Down**, or
- Double-click the row number, type the row number to move it to, and press Enter.

The order is saved automatically when you move to a different photo or close Gramps, so it will still be there next time.

### Settings
Click the **Settings** toolbar button to adjust:

- **Options**
  - **Suppress warning when re-assigning Person reference** — skip the confirmation when you link a person who is already tagged elsewhere in the same photo.
  - **Display as** — a name format for the Name column and generated captions of this gramplet only, overriding *Preferences → Data → Name format*. Leave it on the default to use your normal preference.
- **Face detection** — the minimum face width and height (in pixels) to detect, whether to detect faces inside marquees that already exist, and a sensitivity setting from 1 (least sensitive) to 20 (most sensitive).

## Getting help
Click the **Help** toolbar button, or visit the [Photo Tagging Gramplet page](https://www.gramps-project.org/wiki/index.php/Addon:Photo_Tagging_Gramplet) on the Gramps wiki. For details on the Metadata clues column specifically — what it reads, how it is stored, and troubleshooting — see [XMP data](XMP_Region_Name.md).

Discuss the Photo Tagging Gramplet on the Gramps support forum (powered by Discourse):
* [Gramps resists being a photo detective](https://gramps.discourse.group/t/gramps-resists-being-a-photo-detective/1889)
* [Photo tagging attributes not being written to the media file](https://gramps.discourse.group/t/photo-tagging-attributes-not-being-written-to-the-media-file/7727/6)
* [Cannot find Photo Tagging addon gramplet](https://gramps.discourse.group/t/cannot-find-photo-tagging-addon-gramplet/6853)
* [Could image marquee definition have higher resolution?](https://gramps.discourse.group/t/could-image-marquee-definition-have-higher-resolution/6795)
* [Problème de traduction du nom du gramplet PhotoTagging](https://gramps.discourse.group/t/probleme-de-traduction-du-nom-du-gramplet-phototagging/4906)
* [Photo tagging in Gramps & more](https://gramps.discourse.group/t/photo-tagging-in-gramps-more/3066)
* [Suggested update to PhotoTaggingGramplet to support XMP face regions](https://gramps.discourse.group/t/suggested-update-to-phototagginggramplet-to-support-xmp-face-regions/1209)
* [Utilize media metadata date and face tags in import and references](https://gramps.discourse.group/t/utilize-media-metadata-date-and-face-tags-in-import-and-references/1430)
* [New gramplet to show all images for a person](https://gramps.discourse.group/t/new-gramplet-to-show-all-images-for-a-person/1799)

## License
This addon is free software, licensed under the GNU General Public License, version 2 or later, consistent with Gramps itself.
