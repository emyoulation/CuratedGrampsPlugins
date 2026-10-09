# Changelog: MarkdownUtils

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [MarkdownUtils_PLAN.md](MarkdownUtils_PLAN.md) ● [MarkdownUtils_DEVELOPER.md](MarkdownUtils_DEVELOPER.md) ● [HelpDocButton.md](HelpDocButton.md)

## v0.2.0
### Added
- Scaled images are cached in a new `markdown` folder inside the Gramps thumbnail folder (`THUMB_MARKDOWN`). An image is decoded and scaled once per change of the file, at the smallest of the widths 128, 260, 400 or 560 px that fits, and later views load the small cached copy. The cached copy is rebuilt when the image file is newer, the same rule Gramps uses for its own thumbnails. Measured with a 1920 × 1080 PNG: about 12 ms without the cache, 0.2 ms from the cache.
- Files that GdkPixbuf cannot read, such as PDF or video files, are passed to the Gramps thumbnail framework (`get_thumbnail_path()`, 180 px), so installed Gramps thumbnailers can supply a picture.
- `VIEW_NAMES` accepts six more names: `relationship` and `relationships` (Relationships), `chart`, `pedigree` and `ancestry` (Charts), and `geo` (Geography). Plugin Manager plus now uses `VIEW_NAMES` instead of keeping its own copy of that table. In Markdown Dash, `gramps:view:ancestry` and `gramps:view:pedigree` links now open Charts.

### Changed
- MarkdownUtils is now the only icon resolver for Plugin Manager plus when it is installed.
- In widget tables, an icon that cannot be resolved now shows its name in brackets, such as `[gramps-quilt]`, the same as in text tables. Before, the icon was silently dropped.
- The two table builders (`build_table_widget` and `build_table_text`) share three new helpers instead of repeating the same code. The output is unchanged.

### Deprecated
- `NAMESPACE_MAP`. Markdown Dash now uses the Gramps table of object editors (`gramps.gui.editors.EDITORS`) and `db.method()` instead. `NAMESPACE_MAP` stays for this release so an older Markdown Dash still loads, and will be removed in a later release.

### Fixed
- `resolve_icon_pixbuf()` could return the wrong icon for a plugin. The lookup used the GTK generic fallback from the start, which retries a missing name with the last dash-separated part removed (for example, `gramps-quilt` becomes `gramps`). GTK checks every themed icon for each of those names before it checks loose icon files in folders added with `append_search_path()`, which is how Gramps registers plugin icons. On a system whose icon theme has a `gramps` icon, the Quilt Chart view showed that icon instead of its own. The lookup now tries every style variant of the exact name first, and uses the generic fallback only when no exact match exists. This was tested with GTK 3 and the icon folders of Gramps 5.2.4.
- Scrolling past a table printed "gtk_widget_size_allocate(): attempt to allocate widget with ... height -7" warnings to the console. The table frame had margins, and GTK subtracts margins from the small temporary height it gives a table that is scrolled out of view. The space above and below a table is now line spacing in the text instead.
- Table columns did not line up from row to row (by up to 39 px) when some rows had an icon, or longer or shorter text, than others. Every cell in a column now gets the same width.
- `gramps:view:` links were treated as ordinary web links. In Markdown Dash, clicking one asked the desktop to open the address, which failed. They are now Gramps links, shown in purple like `gramps:edit:` and `gramps:nav:` links.
- An HTML comment inside backticks or a fenced code block was hidden, so a document could not show comment syntax as an example. Comments are now shown exactly as written inside code, as on GitHub, and are still hidden everywhere else.

### Documentation
- The README has a new section on how the language of the Gramps interface selects which README file is shown, and a new section on the additions to GitHub-Flavored Markdown: Gramps icons, Gramps links, links within a document, images, hidden comments and limits.
