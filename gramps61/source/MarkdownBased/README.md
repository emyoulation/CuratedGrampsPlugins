# Markdown Utils v0.2.0 - a shared library

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [MarkdownUtils_PLAN.md](MarkdownUtils_PLAN.md) ● [MarkdownUtils_DEVELOPER.md](MarkdownUtils_DEVELOPER.md) ● [HelpDocButton.md](HelpDocButton.md)

**Markdown Utils** is a small shared library that some Gramps addons use so documentation of the addons shows up nicely formatted inside Gramps, instead of as a wall of raw Markdown symbols or a trip out to a wiki page.

## What you will notice
Nothing about **Markdown Utils** has a separate window or menu. **Markdown Utils** has no screen to open. You will see **Markdown Utils** listed once in **Tools → Plugin Manager** (or Plugin Manager Plus, if installed) as "**Markdown Utils**," but there is nothing to click in that menu. What you will notice is that the addons depending on **Markdown Utils** look better:

* **Documentation of an addon travels with the addon and is available immediately.** Addons that use **Markdown Utils** include a `README.md` file written in standard GitHub-Flavored Markdown right alongside the code of the addon. As soon as both the addon and **Markdown Utils** are installed, that documentation is ready to read and formatted right where you are looking. You will see this on a colored "Help" button on the dialog of a gramplet, tool, or report, or in the info panel of Plugin Manager Plus. There is no separate download, no need to visit a website, and nothing to turn on.
* **Headings, bold and italic text, bullet lists, links, and images all render properly.** You see the same Markdown that renders on GitHub or in a wiki, but inside a Gramps window.

## Documentation in your language
**Markdown Utils** shows documentation in the language of the Gramps interface when a translation exists. For a French interface (`fr_FR`), the first file found is shown:

1. `locale/fr_FR/README.md`
2. `locale/fr/README.md`
3. `README.md` (treated as English)
4. `README_fr_FR.md` or `README_fr.md`
5. Any other labeled file, such as `README_fi.md`

Images and linked files are found the same way: first in `locale/fr_FR/`, then in `locale/fr/`, then in the main folder. In a translated README, write image paths relative to the main folder.

**For translators and authors:** a `README.md` file hides every `README_xx.md` file, so put translations in `locale/xx/README.md`. Name a file like `README_fi.md` only when the documentation exists in that one non-English language. Language codes are 2 lowercase letters, optionally followed by a region, such as `pt_BR`.

## The extra layer: documentation that can show you Gramps itself
Beyond plain formatting, documentation of an addon written this way can go a step further. The documentation can embed pieces of the actual Gramps interface, such as the icon shown on a toolbar button, right inside the text. The documentation can also include links that do not just open a web page, but act on what is in front of you inside Gramps. For example, a link can jump to a place in a tree or view, or open an item for editing. Used this way, the README of an addon stops being just text to read. The README becomes closer to a short guided tour if the author of the addon chooses to write the text that way. Not all addon documentation uses this feature. This feature is an option available to authors of addons, not something that changes how you read a plain README file.

## Additions to GitHub-Flavored Markdown
These features work only inside Gramps. On GitHub, they show as broken images or plain links.

### Gramps icons
Show any icon of the current Gramps icon theme:

```
![](gramps:icon:gramps-person)        16 px, the default size
![](gramps:icon:gramps-person:48)     48 px
![](gramps:icon:person:24:color)      short name, 24 px, color style
```

The optional style is `auto`, `color` or `symbolic`. With `auto`, icons of 32 px or smaller use the one-color symbolic version, and larger icons use the color version. Short names such as `person`, `family`, `event`, `place`, `note`, `dashboard`, `pedigree` and `geography` stand for the matching Gramps icons. In a table, an icon at the start of a cell appears beside the text of that cell, and only the first icon in a cell is shown.

### Gramps links
Links can act on the open Family Tree. The addon that shows the document carries out the action, as Markdown Dash does.

```
[August Dvorak](gramps:edit:Person:I0001)          open the editor
[August Dvorak](gramps:nav:Person:I0001)           go to the record in its view
[August Dvorak](gramps:edit:Person:handle:<handle>) find the record by internal handle
[All places](gramps:view:places)                   switch to a view category
```

Object types are `Person`, `Family`, `Event`, `Place`, `Source`, `Citation`, `Repository`, `Media` and `Note`; capital letters are optional. View categories are `people`, `relationships`, `families`, `charts`, `events`, `places`, `geography`, `sources`, `citations`, `repositories`, `media`, `notes` and `dashboard`. Gramps links show in purple on a pale background.

### Links within the document
`[Installing](#installing)` scrolls to the heading "Installing". As on GitHub, the target name is the heading text in lowercase, with punctuation removed and spaces replaced by hyphens. These links show in green.

### Images
Local images are scaled to fit the window and kept in a cache in the Gramps thumbnail folder, so each image is scaled only once per change of the file. Files that are not ordinary images, such as PDF or video files, show a thumbnail of 180 px when Gramps has a thumbnailer for that format. A missing image shows as `[image: alt text]`.

### Hidden comments
A `<!-- ... -->` comment is hidden from the rendered document, as on GitHub, so authors can leave notes in a file. The file itself is never changed. Inside backticks or a fenced code block, a comment is shown exactly as written. An addon may read settings from a comment: Markdown Dash reads `<!-- icon_style=color -->` on the second line of a document to set the default icon style for the whole document.

### Limits
Links inside table cells cannot be clicked. A short notice appears under such a table.

## If documentation of an addon looks plain instead of formatted
Plain text means **Markdown Utils** is not installed or is not currently enabled. The documentation still opens and remains fully readable because addons fall back to plain text rather than fail. The text simply will not have the nicer formatting or the extra Gramps-aware touches described above. Installing **Markdown Utils** from the addon list fixes this issue automatically for every addon that uses **Markdown Utils**, without configuring anything on an addon-by-addon basis.
