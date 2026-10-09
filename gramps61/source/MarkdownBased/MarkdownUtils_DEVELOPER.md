# Markdown Utils — developer reference

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [MarkdownUtils_PLAN.md](MarkdownUtils_PLAN.md) ● [MarkdownUtils_DEVELOPER.md](MarkdownUtils_DEVELOPER.md) ● [HelpDocButton.md](HelpDocButton.md)

**Source of this document:** checked against `MarkdownUtils.py` 0.2.0, `MarkdownDash.py` and `PluginManagerPlus.py` on 8 October 2026. Signatures below are copied from the code. Open work is tracked in [MarkdownUtils_PLAN.md](MarkdownUtils_PLAN.md).

## Packaging and importing
For Gramps 5.2 to 6.1, `MarkdownUtils.py` and `MarkdownUtils.gpr.py` ship bundled in a parent folder, `plugins/MarkdownBased/`, together with the addons that use them, each addon in its own subfolder. The registration uses `GENERAL`, the Gramps "Plugin library" category: there is nothing to launch, and the registration only lets the addon installer find the package and lets Plugin Manager show the library with its version.

MarkdownUtils is being evaluated for inclusion in Gramps core from 6.2. The proposal is preliminary, so consumers should not change their imports in anticipation.

A consuming addon puts the parent folder on `sys.path` and imports inside `try`/`except`, as the Icon Browser does:

```python
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from MarkdownUtils import markdown_link_at, render_markdown
    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False
```

Gate every call on `_MARKDOWN_AVAILABLE` and fall back to plain text (`Gtk.TextBuffer.set_text()`) or a small stand-in. Gate event handlers too: a motion or click handler that calls `markdown_link_at()` unconditionally raises `NameError` on every mouse movement when MarkdownUtils is missing.

**Do not use `requires_mod=["MarkdownUtils"]`** with this layout. Gramps checks `requires_mod` during its startup registration scan (`Requirements.check_mod()` in `gramps/gen/utils/requirements.py`, called from `gramps/gen/plug/_pluginreg.py`, using `find_spec()`). At that moment `plugins/MarkdownBased/` is not on `sys.path` yet, so the check fails and Gramps silently drops the addon. The same holds in Gramps 5.2.4, 6.0.6 and the `maintenance/gramps61` branch.

## Rendering into a TextView
```python
render_markdown(
    textview: Gtk.TextView,
    md_text: str,
    resolve_path: Callable[[str], str] | None = None,
    image_max_width: int = 560,
    center_images: bool = False,
    show_image_captions: bool = True,
    image_adds_newline: bool = True,
    default_icon_style: str = ICON_STYLE_AUTO,
    table_style: str = "widget",
) -> dict
```

Builds a fresh `Gtk.TextBuffer` on `textview` from `md_text`. It does not connect any signals; the caller owns hover and click handling.

| Parameter | Meaning |
|---|---|
| `resolve_path` | Resolves a relative image path or a link without a scheme against the folder of the document. Default: paths are used as given. |
| `image_max_width` | Images wider than this are scaled down. It is also narrowed to fit the visible width of the view. |
| `center_images` | Center images and their captions. |
| `show_image_captions` | Show the alt text of each image under it. |
| `image_adds_newline` | Insert a line break after each image. |
| `default_icon_style` | Style for `gramps:icon:` references that do not name their own: `auto`, `color` or `symbolic`. |
| `table_style` | `"widget"` (a real GTK grid, with icons in cells) or `"text"` (monospace text, no icons). |

Returns `{"tags": ..., "link_uris": ..., "anchor_marks": ...}`:
- `tags`: the dictionary from `define_tags()`.
- `link_uris`: maps the name of each per-link tag to `(uri, style)`. Pass it to `markdown_link_at()`.
- `anchor_marks`: maps each heading anchor slug to its `Gtk.TextMark`, for "jump to heading".

```python
markdown_link_at(textview, link_uris, x: int, y: int) -> tuple[str | None, str | None]
```

Returns `(style, uri)` for the link under a pixel position in `textview`, or `(None, None)`. Use it on `motion-notify-event` (to show a pointer over links) and `button-press-event` (to act on a click).

**Worked examples:** the `_MdInfoPane` class of `PluginManagerPlus.py` (a small read-only pane), and the `_MarkdownViewer` of `MarkdownDash.py`, which builds its buffer itself from `parse_markdown()` segments.

### What rendering does with images
All images go through one function, `_load_scaled_image()`:
- A local image is decoded once per change of the file, scaled to the smallest of the widths 128, 260, 400 or 560 px that fits, and cached as a PNG in `THUMB_MARKDOWN` (a `markdown` folder inside the Gramps `THUMB_DIR`). Files are named by an MD5 checksum of the source path plus the width, and rebuilt when the source file is newer. Later renders load the cached copy and shrink it in memory if needed. Images are never enlarged.
- A file GdkPixbuf cannot read (PDF, video and so on) goes to `gramps.gen.utils.thumbnails.get_thumbnail_path(..., size=SIZE_LARGE)`, so installed Gramps thumbnailers can supply a 180 px picture. A generic icon from `IMAGE_DIR` counts as a failure.
- An image that cannot be loaded shows as `[image: alt text]`.

### Tables
With `table_style="widget"`, each table is a `Gtk.Frame` placed at a child anchor in the text. Two rules keep it well behaved, and both have comments in the code:
- **No margins on the anchored widget.** While a table is scrolled out of view, GTK gives it a temporary height of a pixel or so and subtracts the margins from that, which printed "height -7" warnings. The space above and below a table is line spacing on the anchor line (a `table_spacing` tag).
- **One `Gtk.SizeGroup` per column.** Each row is its own box, and without size groups the columns drifted out of line whenever rows differed in icons or text length.

Links inside table cells cannot be clicked. When a table contains one, a short notice is added under it (`table_has_uninteractive_links()`, `emit_enhanced_renderer_notice()`).

### Comments
`<!-- ... -->` comments are hidden from the rendered document, as on GitHub. Inside an inline code span or a fenced code block (three or more backticks or tildes), a comment is shown exactly as written. Markdown Dash reads its own options comment on line 2 of a file itself, before handing the rest to MarkdownUtils.

## Link styles
| Style | Produced for | Markdown Dash | Plugin Manager plus |
|---|---|---|---|
| `hyperlink` | `http://`, `https://` | Opens in the desktop | Opens in the desktop |
| `gramps_link` | `gramps:edit:`, `gramps:nav:`, `gramps:view:` | Acts on the open tree (see below) | Hands to the desktop, which cannot open it (open item) |
| `anchor_link` | `#slug` | Scrolls to the heading | — |
| `image_link` | A missing image | Opens the file or address | — |
| `mailto_link` | `mailto:` | — | Opens in the desktop |
| `file_link` | `file://` | — | Opens with the default application |
| `md_link` | A relative link to a local `.md` file | Loads it in the reader | Shows it in the same pane |

Styles are decided in two places today: `parse_markdown()` sets attributes on segments (Markdown Dash uses these), and `render_markdown()` checks the URL prefix. Keep them in step; the plan proposes one `classify_link_url()` for both.

## The `gramps:` syntax
### Icons
```
![](gramps:icon:NAME)
![](gramps:icon:NAME:SIZE)
![](gramps:icon:NAME:SIZE:STYLE)
```
- `NAME`: a GTK icon name (`gramps-person`) or a short name from `GRAMPS_ICONS` (`person`).
- `SIZE`: pixels, default 16.
- `STYLE`: `auto`, `color` or `symbolic`. With `auto`, 32 px and smaller prefer the symbolic version.
- In a table cell, an icon at the start of the cell is shown beside the text; only the first counts. An icon that cannot be resolved shows as `[NAME]` in both table styles.

### Links
```
[label](gramps:edit:TYPE:ID)            open the editor
[label](gramps:edit:TYPE:handle:HANDLE) the same, by internal handle
[label](gramps:nav:TYPE:ID)             go to the record in its view
[label](gramps:view:CATEGORY)           switch to a view category
```
MarkdownUtils only styles these links; the consumer carries them out. Markdown Dash matches `TYPE` against the Gramps table of editors (`gramps.gui.editors.EDITORS`: Person, Family, Event, Place, Source, Citation, Repository, Media, Note), regardless of capitals, and looks the record up with `db.method("get_%s_from_%s", TYPE, "gramps_id" or "handle")`. `CATEGORY` goes through `VIEW_NAMES`. `people` is a view category, not an object type, so `gramps:nav:people:I0001` does not work.

## Icons API
```python
resolve_icon_pixbuf(
    icon_name: str,
    size: int,
    icon_theme: Gtk.IconTheme | None = None,
    style_context: Gtk.StyleContext | None = None,
    icon_style: str = ICON_STYLE_AUTO,
) -> GdkPixbuf.Pixbuf | None
```

Returns `None` when nothing is found. Lookup order: every style variant of the exact name first, then the same with the GTK generic fallback (which shortens the name at dashes), then the `GRAMPS_ICONS` aliases, then PNG and SVG files in the Gramps `DATA_DIR`, then files in `IMAGE_DIR`. The exact-name pass comes first because GTK checks every themed icon for every fallback name before it checks loose icon files added with `append_search_path()`, which is how Gramps registers plugin icons; otherwise `gramps-quilt` could resolve to a themed `gramps` icon. Pass `style_context` so symbolic icons take the colors of the widget. GTK caches icon lookups (about 0.02 ms each), so callers do not need their own cache.

`ICON_STYLE_AUTO`, `ICON_STYLE_COLOR` and `ICON_STYLE_SYMBOLIC` are the strings `"auto"`, `"color"` and `"symbolic"`.

`list_icons_by_context(context: str | None = None, icon_theme: Gtk.IconTheme | None = None) -> list[str]` lists icon names from the live theme, sorted without regard to capitals. `GRAMPS_ICONS` maps short names to lists of GTK icon names.

## Localization API
- `locale_lang() -> tuple[str, str]`: the full and short codes of the Gramps interface language, such as `("fr_FR", "fr")`; `("en_US", "en")` when unknown.
- `resolve_localized_path(path: str) -> PathResolution`: given the canonical `<folder>/README.md`, returns the best variant, in this order: `locale/<ll_CC>/README.md`, `locale/<ll>/README.md`, `README.md` (English), `README_<ll_CC>.md` or `README_<ll>.md`, then any other labeled file such as `README_fi.md`. A `README.md` hides every labeled file.
- `PathResolution`: fields `path`, `is_fallback` (no variant in the user language was found), `source_lang` (the language of a labeled file, or `None`) and `user_lang`; method `exists()`.
- `resolve_localized_asset(base_dir: str, rel_path: str) -> str`: the same order for images and linked files, relative to the canonical folder.
- `LANG_SUFFIX_RE`: matches `<stem>_<ll>[_CC].<ext>`; codes are two lowercase letters with an optional region.

Markdown Dash, its reader, `help_doc_button.py` and Note Styling Editor use these. The README pane of Plugin Manager plus does not yet (open item).

## Lookup tables
- `VIEW_NAMES`: lowercase aliases to view category names. Since 0.2.0 it also accepts `relationship`, `relationships`, `chart`, `pedigree`, `ancestry` and `geo`. Plugin Manager plus uses it for gramplet view restrictions; Markdown Dash uses it for `gramps:view:` links.
- `NAMESPACE_MAP`: **deprecated in 0.2.0**; no current addon uses it. Use `gramps.gui.editors.EDITORS` and `db.method()` instead. It stays for one release so an older Markdown Dash still loads.

## Lower-level building blocks
- `parse_markdown(md_text: str, default_icon_style: str = ICON_STYLE_AUTO) -> list[Segment]`
- `Segment`: fields `text`, `attrs` (tag names), `url`, `image_path`, `gramps_icon` (`(name, size, style)`), `table_data` and `anchor` (the heading slug, as on GitHub).
- `define_tags(buf: Gtk.TextBuffer) -> dict[str, Gtk.TextTag]`
- `inline_to_pango(text: str) -> str`: inline Markdown to Pango markup, used for table cells. It repeats the logic of `_parse_inline()`; the plan proposes merging them.
- `build_table_widget(columns, align, body_rows, sep_widths=None, default_icon_style=ICON_STYLE_AUTO) -> Gtk.Frame`
- `build_table_text(columns, align, body_rows, sep_widths=None, default_icon_style=ICON_STYLE_AUTO) -> list[tuple[str, str | GdkPixbuf.Pixbuf]]`
- `apply_table_no_wrap_tag(buf, start_it, end_it) -> None`
- `table_has_uninteractive_links(columns, body_rows) -> bool` and `emit_enhanced_renderer_notice(buf, it, tags, make_link_tag) -> None`, with the constants `ENHANCED_RENDERER_NOTICE`, `ENHANCED_RENDERER_LINK_TEXT` and `ENHANCED_RENDERER_LINK_URL`.
- `THUMB_MARKDOWN`: the image cache folder.

## Guidance for consumers
Lessons from the consumers, each found in real use:
- **Run menu actions after the menu closes.** Opening a window or dialog, or loading a document, inside a menu "activate" handler makes the GTK Wayland backend report "Tried to map a popup with a non-top most parent". Plugin Manager plus uses a `_run_after_menu_closes` helper (`GLib.idle_add`).
- **No tooltips on menu items.** A tooltip still open on the chosen item makes Wayland report "Tried to unmap the parent of a popup".
- **Reader windows need `Gdk.WindowTypeHint.NORMAL`.** A plain `Gtk.Dialog` defaults to the `DIALOG` hint, which breaks Windows-menu behavior on many window managers. The reader window of Markdown Dash does not set it yet (checked 8 October 2026).
- **Restart Gramps after replacing addon files.** Python loads a module once per session, and Load in the Plugin Manager does not reload a module that is already loaded.
