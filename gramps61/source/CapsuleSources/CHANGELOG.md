# Capsule Sources changelog
<!--  -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [PLAN.md](PLAN.md)

Capsule Sources imports captures made with [Genealogy Capsule](https://github.com/mjlawless/capsule-genealogy) ([announcement](https://www.reddit.com/r/GenealogySoftwareDevs/comments/1xioiq6/new_chrome_extension_released_for_saving/), [release notes](https://github.com/mjlawless/capsule-genealogy/releases)) into Gramps.
## 0.2.0
New Repository, Source and Citation structure, person linking, and easier access to the saved files. Suggested in the [Capsule Sources topic on the Gramps Discourse forum](https://gramps.discourse.group/t/capsule-source-a-genealogy-capsule-integration-addon-family-tree-processing-tool/10175).
- Changed structure: one Repository, "Genealogy Capsule captures", stands for the captures archive; each web site is a Source in it; each capture is a Citation of that Source, dated with the day of the capture. Before, each site was a Repository and each source list entry a Source.
- The Citation Volume/Page now holds the record page title. The full Evidence Explained citation stays in the Citation note.
- Sources are found by a "Capsule site" attribute, so a renamed Source is still used by later imports, and a Source of your own with the same title is never taken over.
- Captures imported with 0.1 keep their old Repository and Source. Delete those Citations and import them again to get the new structure.
- The Person column can be edited, like the Name column of the Photo Tagging gramplet: it starts with the name Genealogy Capsule read, shown in red until a person is linked.
- New right-click menu on each row: See the person details, See ancestor family details, See descendant family details, Make the person active, Link, Add a new person, Clear Reference, Fuzzy Match Lookup (needs the Fuzzy Matching addon), Edit the Citation, Clipboard the Citation (puts it on the Gramps Clipboard), Open the capture folder and Copy the reference note.
- A linked person cites the Citation of the capture. Links made before the import are applied during the import.
- Typed names and linked people are kept in `CapsuleSources_captures.json` in the addon folder, with links kept separately for each family tree. The "Capsule person" Citation attribute and the `[people]` settings from test builds are no longer used.
- Double-click a row that is in the tree, or click the Citation ID in the right panel, to open Edit Citation.
- New Primary person line at the top of the right panel; the linked name is a link to the person.
- New Files section in the right panel, with Open and Open with… buttons for every saved file, including the page text copy. When the computer has no program set for a kind of file, the tool asks once and remembers the choice.
- The Genealogy Capsule icon to the left of the folder name reads the folder again.
- The folder chooser takes about a third of the row; the number of captures and sites shows at the right end of the row, with a full breakdown in its tooltip.
- Copy icons to the left of Reference note, Short note and Source list entry in the right panel copy that part of the citation. They replace the Copy button under the reference note. The whole heading row is the click target; it lights up under the pointer, and the icon briefly turns into a check mark after a copy.
- The Status and Files chips use see-through tints behind the normal text color, so they read well in both light and dark themes.
- The capture folder name next to Local in the right panel is a link that opens the folder; it replaces the Open folder button.
- The Close button is gone; the x in the title bar and the Esc key close the window.
- Column widths are remembered. On first use, the Person and Site columns share their room equally, so the Site column is no longer too narrow.
- The "in tree" status comes first in the Status column, so it stays visible in a narrow column; sorting by Status now groups the captures already in the tree.
- The row tooltip shows what Genealogy Capsule read when you have changed the name.
- The registered plugin id is now "CapsuleSources", matching the file names CapsuleSources.py, CapsuleSources.gpr.py and CapsuleSources.ini (it was "capsulesources"). The main module is renamed from capsule_sources.py to CapsuleSources.py.
## 0.1.0
First experimental version, for Gramps 5.2 and newer.
- New tool: Tools > Family Tree Processing > Capsule Sources.
- Reads Genealogy Capsule capture folders (capture-folder v1 and v2) from the Capsule data folder, or any folder you choose. The folder choice and window size are remembered.
- Lists every capture with its date, site, title, status (current, not read yet, superseded) and privacy, and marks captures already in the tree.
- Imports the selected captures as Repositories (one per site), Sources (one per source list entry), Citations (one per capture), Citation and Research notes, and Media objects linked in place with their SHA-256 fingerprints.
- Marks subscription and copyright-flagged captures private.
- Skips captures already imported, so running the tool again adds nothing twice.
- Hides superseded captures unless asked, and never imports them.
- Creates no people, events or facts.
- A Help icon at the lower left opens this README in Markdown Dash when it is installed, or the help page on GitHub in a browser otherwise.
