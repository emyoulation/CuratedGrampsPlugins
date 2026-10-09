# MarkdownUtils — consolidated status and staged plan

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [MarkdownUtils_PLAN.md](MarkdownUtils_PLAN.md) ● [MarkdownUtils_DEVELOPER.md](MarkdownUtils_DEVELOPER.md) ● [HelpDocButton.md](HelpDocButton.md)

Updated 8 October 2026, after the MarkdownUtils 0.2.0 work. The original answer still stands: **no full redesign — a staged sequence of surgical changes.** `parse_markdown()` → `list[Segment]` → `render_markdown()` is still the right shape, and every change since has fit into it.

Two facts changed the context since this plan was first written:
- **Packaging:** for Gramps 5.2 to 6.1, MarkdownUtils ships bundled in a parent folder (`plugins/MarkdownBased/`) together with the Markdown-based addons, each in its own subfolder. The `lib/` layout of the old Phase 0 is set aside.
- **Gramps core:** MarkdownUtils is being evaluated for inclusion in Gramps core from 6.2. The proposal is too preliminary to act on: no core module path yet, so no import changes in anticipation.

## Why staged, not a rewrite
- `parse_markdown()` → `list[Segment]` → `render_markdown()` is a clean two-stage pipeline. A pluggable backend only needs a second producer of that same `Segment` list.
- The Gramps-specific syntax is isolated to a few URL checks in `_parse_inline` (now `gramps:nav:`, `gramps:edit:` and `gramps:view:` links, plus `gramps:icon:` images), not woven through the parser.
- Thumbnailing for unusual formats needs no MarkdownUtils changes: the Gramps thumbnailer registry already dispatches by mime type, and MarkdownUtils now calls into it (see Phase 3).
- Verify each change in Gramps, in the order it is built, rather than in batches.

## Phase 0 — Packaging (revised)
- [x] **The `lib/` layout is set aside.** MarkdownUtils sits in `plugins/MarkdownBased/`. Each consuming addon puts that parent folder on `sys.path` and imports MarkdownUtils inside `try`/`except ImportError`, falling back to plain text (or a small stand-in) when it is missing.
- [x] **Finding: `requires_mod=["MarkdownUtils"]` cannot be used with this layout.** Gramps checks `requires_mod` during its startup registration scan (`Requirements.check_mod()` in `gramps/gen/utils/requirements.py`, called from `gramps/gen/plug/_pluginreg.py`, using `find_spec()`). At that moment `plugins/MarkdownBased/` is not yet on `sys.path`, so the check fails and Gramps silently drops the addon. Checked in the source of Gramps 5.2.4, 6.0.6 and the `maintenance/gramps61` branch.
- [ ] **When a core module path is settled:** change every consumer to try the core module first and fall back to the bundled copy (Plugin Manager plus, Markdown Dash, Icon Browser, `help_doc_button.py`, Note Styling Editor), and end the version range of the bundled `MarkdownUtils.gpr.py` below 6.2. Core inclusion also means the full AGENTS.md treatment, and the module must live under `gramps/gui/` because it uses GTK.

## Phase 1 — Correctness fixes to MarkdownUtils.py itself
- [ ] **Titled-link parsing bug — still present** (re-checked 8 October). `_INLINE_RE` takes everything inside the parentheses as the URL, so `[text](https://x.org "A title")` gets the URL `https://x.org "A title"`. The regex, or a small split after matching, must separate an optional quoted title.
- **Gramps link dispatch — partly done:**
  - [x] `gramps:view:` links were classified as ordinary web links, so clicking one in Markdown Dash asked the desktop to open the address and failed. They are now Gramps links (`gramps_link`), like `gramps:edit:` and `gramps:nav:`.
  - [x] Markdown Dash resolves `gramps:edit:` and `gramps:nav:` with the Gramps table of object editors (`gramps.gui.editors.EDITORS`) and `db.method()`, instead of `NAMESPACE_MAP`. Object types now match regardless of capitals, and an editor that is already open is brought forward without a traceback.
  - [ ] **Plugin Manager plus still hands `gramps:` links to the desktop**, which cannot open them. Revised recommendation: move the handler of Markdown Dash (`_handle_gramps_uri` and its helpers) into MarkdownUtils as one shared `open_gramps_link(uri, dbstate, uistate, ...)`, built on core `EDITORS` and `db.method()` (not on `NAMESPACE_MAP`), and have both Markdown Dash and Plugin Manager plus call it. Plugin Manager plus is a Tool and has `dbstate`.
- [ ] **`inline_to_pango()` duplicates `_parse_inline()`** for table cells — a second regex-driven walk over the same constructs. Collapse onto `_parse_inline()` plus a small `segments_to_pango()`. Not urgent; no visible change.

## Phase 2 — Isolate the Gramps extension layer
Still open. Extract the Gramps URL checks into standalone functions on a `(url, label)` pair: `classify_image_url(url)` for `gramps:icon:` (and later `gramps:media:`), and `classify_link_url(url)` for link styles. Pure refactor; regression-check against a representative document before and after.

New detail found on 8 October: link styles are decided in **two** places today — `_parse_inline()` (which sets the `gramps_link` attribute that Markdown Dash uses to route clicks) and the URL checks in `render_markdown()` (which treat any `gramps:` prefix as a Gramps link). `classify_link_url()` should serve both, so they cannot disagree again; that disagreement is exactly how `gramps:view:` links broke.

## Phase 3 — Media and thumbnail integration
Done on 8 October, as part of 0.2.0:
- [x] **All image loading goes through one function, `_load_scaled_image()`.** Scaled images are cached in `THUMB_MARKDOWN` (a `markdown` folder inside the Gramps `THUMB_DIR`), at fixed widths of 128, 260, 400 and 560 px. Files are named by an MD5 checksum of the source path plus the width, following the Gramps naming scheme, and rebuilt when the source file is newer. Measured with a 1920 × 1080 PNG: about 12 ms uncached, 0.2 ms cached.
- [x] **Formats GdkPixbuf cannot read** go to `get_thumbnail_path(..., size=SIZE_LARGE)`; a generic icon from `IMAGE_DIR` is treated as a failure, so the bracketed alt text still appears.
- **Why MarkdownUtils keeps its own cache for larger images:** the Gramps framework only makes 96 px (`normal`) and 180 px (`large`) thumbnails, and readable 260 px previews matter for screenshots. Asking core for a third size was considered and not pursued: Gramps 5.2 core will not change, and existing thumbnailers treat the size argument as a two-value code (`imagethumb.py` and `gnomethumb.py` test `size == SIZE_LARGE`), so a new size code would quietly produce 96 px images. The base docstring of `Thumbnailer.run()` claims the size is in pixels; that mismatch is worth reporting to Gramps on its own.

Revised resolver contract for `gramps:media:`: a `resolve_media` implementation finds the source file of the Media object and hands its path to the same loading path (`_load_scaled_image()`, which already uses `get_thumbnail_path()` where it helps). It must never build another cache or reimplement hashing, mime detection or thumbnail generation.

Still open:
- [ ] Add `Segment.gramps_media`: `(id_or_handle, size)`, parallel to `gramps_icon`.
- [ ] Add a `resolve_media` parameter to `render_markdown()`, default `None`, so MarkdownUtils never imports `dbstate` and still renders with no tree open.
- [ ] Recognize `gramps:media:<id>[:size]` in Phase 2's `classify_image_url()`.
- [ ] Wire a real `resolve_media` in Markdown Dash, which has `dbstate`.
- Page selection inside a PDF stays at the Media-curation layer, as before; `gramps:media:` never needs a page argument.

## Phase 4 — Optional 3rd-party parser backend (do last)
Unchanged: no `requires_mod` on a parser in the MarkdownUtils registration, never vendor a parser into MarkdownUtils, an optional companion addon whose only job is `requires_mod=["marko"]`, `marko` preferred over `markdown-it-py`, one adapter contract calling Phase 2's classifiers, and tables staying on `build_table_widget()`. Revisit this phase if MarkdownUtils enters Gramps core, since core has its own rules for optional dependencies.

## Phase 5 — Documentation
- [x] **End-user README revised** (8 October): a section on how the language of the Gramps interface selects the README, and a section on the additions to GitHub-Flavored Markdown (icons, Gramps links, links within the document, images, hidden comments, limits). Rendered with MarkdownUtils itself to confirm it displays correctly.
- [x] **CHANGELOG.md** written for the 0.2.0 public release.
- [ ] **`MarkdownUtils_DEVELOPER.md`**: still to revise. Its "NEEDS VERIFICATION" sections are now confirmed, and it should cover today's additions: the image cache, `VIEW_NAMES` aliases, the comment rule inside code, and the deprecation of `NAMESPACE_MAP`. Best done right after Phase 2.
- [ ] AI-generated-code disclosure in each phase at commit time.

## Other open items
- [ ] Delete `NAMESPACE_MAP` once the new Markdown Dash (which no longer uses it) has shipped. It is marked deprecated in 0.2.0.
- [ ] Markdown Dash: its notes say a fallback document is shown with an invitation to translate, but the code shows the invitation only on the "File Not Found" page. Show it under fallback documents, or correct the notes.
- [ ] Plugin Manager plus: its README pane, README column and "Open documentation reader" look only for a file named exactly `README.md` (`_readme_path()`). It should call `resolve_localized_path()`, as `help_doc_button.py` already does.
- [ ] Markdown Dash README: examples such as `gramps:nav:people:I0001` fail, because `people` is a view name, not an object type. Fix the examples or make the links accept view names.
- [ ] Markdown Dash keeps its own copy of the link colors in `make_link_tag`, duplicating the MarkdownUtils color table.
- [ ] Watch for: the pixman "Invalid rectangle" message during scrolling (not seen since the 8 October fixes), and a missing Windows-menu entry for the reader window opened from Plugin Manager plus (seen once, not reproduced after a restart).

## What is done and verified
Earlier, verified live in Gramps across every fallback branch:
- `help_doc_button.py` and its inlining into `PhotoTaggingGramplet.py`: the icon-fallback bug, the URL-encoding bug, the `GENERIC_FALLBACK` → `FORCE_REGULAR` correction, and the hidden or deactivated plugin bug in both `resolve_markdown_dash_opener()` and `_cb_open_doc_reader` of Plugin Manager plus.

8 October, **verified live in Gramps:**
- Scrolling past tables no longer prints `gtk_widget_size_allocate()` warnings (table frame margins replaced by line spacing).
- Plugin Manager plus shows the icon of a plugin beside its preview thumbnail or placeholder, resolved by MarkdownUtils.

8 October, **tested outside Gramps** (GTK 3 under a virtual display with the Gramps 5.2.4 package, or unit tests); confirm in Gramps:
- Icon lookup tries exact names before the GTK generic fallback (reproduced the wrong-icon case and the fix).
- The scaled-image cache: first view, cached view, a narrower pane, a changed source file, an unreadable file.
- Table columns line up from row to row (one `Gtk.SizeGroup` per column; 0 px drift in all 5 tables of the icon inventory).
- Comments inside code are shown, and hidden elsewhere (10 cases; two real documents parse identically).
- `gramps:view:` links classified as Gramps links; unresolvable icons shown as `[name]` in widget tables.
- The shared table helpers produce byte-identical output in both table styles.
- `VIEW_NAMES` with the new aliases gives the same results as the old private table of Plugin Manager plus (33 cases).
- Markdown Dash `gramps:edit:` and `gramps:nav:` links through core `EDITORS` and `db.method()` (7 cases).
- The Icon Browser lists icons through `list_icons_by_context()` with results identical to its old code (12 lists, 981 icons).
