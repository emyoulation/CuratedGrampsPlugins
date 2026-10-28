# Markdown Dash - Changelog
<!-- undocked=false -->
[Markdown Based tools](../README.md) ● [README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable changes to the Markdown Dash gramplet. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.5.2]
### Added
- Double-click an image in the document to open the image file in the default viewer of the desktop, the same way as double-clicking the thumbnail in the Gramps Edit Media dialog.

### Fixed
- A document heading that matched the title of another Dashboard gramplet could remove that other gramplet from the Dashboard records. The other gramplet then disappeared from the Configure dialog and from the saved Dashboard layout. This happened, for example, with the built-in "What's Next?" gramplet.
- Adding a second Markdown Dash to the Dashboard could give two gramplets the same title. The Configure dialog then showed two tabs with the same name that changed the wrong gramplet, and the next start of Gramps could fail to load the Dashboard layout and reset it to the default gramplets.
- A heading that contains `&`, `<` or `>` left the gramplet title out of step with the Dashboard records. The gramplet now keeps its current title instead.
- With a dark theme, headings stayed black on the dark background while the body text turned white. Headings, block quotes, list bullets, code, and links (also links inside tables) now use colors that are readable on both light and dark themes.

### Changed
- On the Dashboard, the title from the document heading is applied only after Gramps has finished adding the gramplet, and always through the standard Gramps title check. When another gramplet already uses the title, a number is added (for example `What's Next?-1`), the same way Gramps does when it loads the Dashboard.
- The gramplet frame label shows the title that was actually accepted, not the one requested.
- The README explains the unique-title rule, and its heading no longer includes a version number.
- Images are now shown by the shared Markdown Utils library, the same way as in Plugin Manager plus. Scaled images are saved in the Gramps thumbnail folder, so a document with large photos opens faster the next time. A linked file that is not a normal image (for example a video or a PDF) is shown with its Gramps thumbnail when Gramps can make one.
- The dark theme colors and the double-click feature need the updated Markdown Utils. With an older Markdown Utils, the gramplet still works with the previous colors, and double-clicking an image does nothing.

## [1.5.1]
- Publicly shared version. Starting point for this changelog.
