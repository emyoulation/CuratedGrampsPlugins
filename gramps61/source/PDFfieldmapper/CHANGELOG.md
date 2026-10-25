# Changelog
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 0.0.2
Named destinations (anchors) for the fields, and a corrected installation guide.

### Anchors
- New check box Write anchors, selected by default. Each visible field receives a named destination at its upper left corner, named like its tag, or like its field name when it has no tag. A link such as `form.pdf#INDI4/BIRT/DATE` is expected to scroll to the field in Okular and Firefox. This was checked in the source code of both viewers and with the poppler library, and was not yet tried in the viewer windows.
- Hidden and deleted widgets get no anchor. When two fields would receive the same name, only the first in tab order gets it.
- Anchors written earlier by the gramplet are replaced on every write. Anchors from other sources are kept, and the status line reports the number of anchors skipped because the name was taken.
- The anchors are stored in the name tree and in the older Dests dictionary, because viewers built on poppler read only the older one when it exists.

### Documentation
- Corrected the plugins folder: `~/.local/share/gramps/gramps60/plugins` for Gramps 6.0 on Linux.
- Added the sections Where the plugins folder is, Installing pypdf, and Anchors.
- Explained why Gramps silently skips the gramplet when pypdf is installed with `pip install --user` on Fedora, and added the other ways to install pypdf.
- Added troubleshooting for a gramplet that does not appear, the Papers console warnings, and anchor links that do nothing.

### Checked
- The automated checks gave identical results with pypdf 4.2.0, 5.9.0, and 6.21.2.

## 0.0.1
First version of the PDF Field Mapper gramplet for Media objects that are PDF forms.

### Fields table
- Lists every form widget of the selected PDF with page, working order (#), tab order (Tab), Off, Del, Multi, field name, type, current value, and GEDCOM tag.
- Sorting by any column, always with the page first. Editing a cell never moves a row. A column that can be edited is sorted again only when its header is clicked.
- Each newly loaded PDF starts sorted by #.
- The detail line shows what will be written for the selected row, and names the sort column when reordering is not possible.
- The layout shrinks to a small gramplet bar. Rows of buttons wrap, and the whole gramplet scrolls.

### Tags
- Tags use the slash as separator, for example INDI4/BIRT/DATE. A period cannot be part of a PDF field name. Typed periods are converted automatically.
- Suggest tags reads placeholder values such as ID08,Birthdate.
- Suggest tags also reads field names. English relationship names such as Your Father-POD, Paternal Grandfather-DOB, and Maternal-Paternal Great-Grandmother-Name become ancestor numbers.
- Chart fields (Page no, Chart no, Pedigree Chart for, cont1 to cont8) are recognized.
- The status line reports how many tags came from values and from names, and which fields remain without a tag.

### Ordering
- Tab order starts from the page setting of the PDF, or follows # when there is none. Tab becomes independent after it is edited. The Tab = # button links it again.
- Reorder with drag and drop, Up and Down, or the Row Editor. Reordering needs an ascending sort by # or Tab.
- The Row Editor opens with a double-click, Enter, or the Edit row… button. It takes the # position and the Tab position and moves the row there.
- Auto-order sorts by chart fields, ancestor number, and fact. Hidden and deleted rows go last.
- Up and Down are gray when reordering is not possible.

### Cleaning fields
- Off hides a widget.
- Del deletes a widget, and its field when no widget is left, together with its element in the structure tree.
- Multi turns the multi-line flag of a text field on or off. A warning names the multi-line fields when a PDF is loaded.

### Values
- Clear values empties text and choice fields.
- Names → values puts the name that will be written into each text field.
- Tab + names → values puts the tab position and the name into each text field, to find fields that are visited out of order.
- Values are written without stored drawings, so a viewer draws each field with its own font size.

### Writing
- Write PDF… saves a new file and never overwrites the original.
- Embed crosswalk stores each tag under the key /GrampsTag. Rename fields uses the tag as the field name.
- Three tab order modes: structure tree with /Tabs S, annotation order with /Tabs A, and no page setting.
- The tab order is written in the same order to the page annotation list, the field list with nested groups, and the structure tree.
- A PDF with a structure tree that does not list the fields receives a Form fields branch. A branch written earlier is updated, and widgets switched on again are added.
- The status line lists the places that carry the tab order.
- The PDF version of the original is kept, and so is the document information. The written file is not encrypted.
- A PDF with a damaged cross-reference table is read and rewritten correctly. A short note replaces the console messages.

### Crosswalk sidecar
- The sidecar file is named like the PDF, with the ending .crosswalk.json, and is stored next to the PDF.
- It holds the tags, the # order, the Tab order, and the widgets marked Off or Del, plus the name of the PDF.
- Save proposes the sidecar name, Load selects the sidecar when it exists, and the status line announces a sidecar when a PDF is selected.
- Loading a crosswalk saved for another PDF works and shows a note.

### Compatibility
- Registered for Gramps 5.2 through 6.2. Developed on Gramps 6.0.
- Requires the Python module pypdf.
- The tab order is followed by Okular. Firefox and Xreader sort by position and ignore it.
