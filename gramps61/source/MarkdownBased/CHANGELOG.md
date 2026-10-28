# Changelog: MarkdownUtils

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [MarkdownUtils_PLAN.md](MarkdownUtils_PLAN.md) ● [MarkdownUtils_DEVELOPER.md](MarkdownUtils_DEVELOPER.md) ● [HelpDocButton.md](HelpDocButton.md)

## v0.2.1
### Added
- Fixed-size thumbnails. A new `image_max_height` argument of `render_markdown()` (and `max_height` of `insert_image_into_buffer()`) fits each image inside an `image_max_width` × `image_max_height` box and keeps its proportions, the same way Gramps fits its own 96 px "normal" and 180 px "large" thumbnails into a square. Images are never enlarged. A box thumbnail is cached once at the box size, under a different cache key than the width-step copies. Plugin Manager plus uses a 260 × 260 box in its Preview pane. The default (`None`) scales by width only, as before.
- Double-click an image to open the image file in the default viewer of the desktop for its file type, the same way as double-clicking the thumbnail in the Gramps Edit Media dialog. This uses the Gramps function `open_file_with_default_application()`. For a file shown with a Gramps thumbnail (for example a video or a PDF), the double-click opens the original file. New public functions: `markdown_image_double_click()` (for the `button-press-event` handler of the caller), `markdown_image_at()`, `open_image_with_default_application()` and `mark_image_source()`. The source file is recorded in a text tag on each image, so it stays with the buffer. Images inside table widgets and `gramps:icon:` pictures are not covered.
- Dark theme support. `theme_is_dark()` decides from the actual text color of the theme whether the theme draws light text on dark, so it also detects dark CSS that is not applied through the theme name or the prefer-dark setting. `define_tags()` takes a new `dark` argument (`None` detects it), and `link_style_colours()` returns the link colors for either palette. `render_markdown()` checks the TextView it renders into. The light palette is the same as the previous colors.

### Changed
- `_insert_image_into_buffer()` is now public as `insert_image_into_buffer()`. The old private name stays as an alias for older add-ons. Markdown Dash now uses this function instead of its own copy, so it gets the image cache, the Gramps thumbnail fallback and the double-click feature.

### Fixed
- With a dark theme, headings stayed near-black on the dark background while body text followed the theme and turned white. Block quotes, list bullets, code, code blocks and links had the same problem, and so did links and keyboard keys (`<kbd>`) inside table widgets. These now use the dark palette on dark themes. The colors are chosen when a document is rendered, so after a theme change an open document updates at its next load or refresh.

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
