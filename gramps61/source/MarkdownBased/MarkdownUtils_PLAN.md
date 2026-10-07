# MarkdownUtils — consolidated status and staged plan

Written to close out a long design conversation. Answers the question asked
directly: **no full redesign — a staged sequence of surgical changes.** The
existing `MarkdownUtils.py` already has the right internal shape for
everything discussed below (a flat `Segment` list that `render_markdown()`
only ever consumes, never the parser's own internals); the work is mostly
extraction and wiring, not rewriting working code. Given the whole family
has only ever shipped "experimental," now is the right time to do this
before there's a broader install base to stay compatible with.

## Why staged, not a rewrite

- `parse_markdown()` → `list[Segment]` → `render_markdown()` is already a
  clean two-stage pipeline. A pluggable backend only needs a second producer
  of that same `Segment` list — the consumer half doesn't change at all.
- The Gramps-specific syntax (`gramps:icon:`, `gramps:nav:`, `gramps:edit:`)
  is already isolated to two regex checks inside `_parse_inline`, not woven
  through the whole parser. Extracting them is a small, low-risk change.
- Several things discussed turned out not to need any MarkdownUtils change
  at all (WebP/AVIF thumbnailers, non-image mime dispatch) — the existing
  Gramps thumbnailer/plugin registries already generalize correctly.
- Nothing proposed here has been tested against the real file yet except
  the original help-button fix, which the user already verified live in
  Gramps across all four fallback branches. Everything below should be
  verified the same way, in the same order it's built, rather than batched.

## Phase 0 — Verify what's already drafted (do this first, nothing else depends on skipping it)

The `.gpr.py`/`lib/` packaging redesign has not been tested yet.

- [ ] Place `MarkdownUtils.py` + the drafted `MarkdownUtils.gpr.py` under
      `USER_PLUGINS/lib/` (not its own addon subfolder).
- [ ] Confirm it registers: appears in Plugin Manager as "Markdown Utils",
      category "Plugin library" (GENERAL ptype).
- [ ] Confirm `PluginManagerPlus.gpr.py`'s new `requires_mod=["MarkdownUtils"]`
      actually gates registration: temporarily remove `lib/MarkdownUtils.py`,
      rescan/restart, confirm Plugin Manager plus disappears entirely (not
      just a warning icon) — this is the "refuse to register" behavior found
      in `gramps/gen/plug/_pluginreg.py`, worth seeing happen for real once.
      Restore the file, confirm it reappears.
- [ ] Confirm `PluginManagerPlus.py`'s dropped `sys.path` hack still resolves
      `from MarkdownUtils import (...)` now that `lib/` is the real source
      (it should — `LIB_PATH` is unconditionally on `sys.path` from Gramps
      startup — but this hasn't been run yet).

## Phase 1 — Correctness fixes to MarkdownUtils.py itself (single-file, no architecture change)

Two concrete bugs found while reading the real file, independent of
everything else below — worth fixing regardless of which later phases
happen:

- [ ] **Titled-link parsing bug**: `_INLINE_RE`'s link group
      (`\[(?P<link_label>[^\]]+)\]\((?P<link_url>[^)]+)\)`) swallows a
      Markdown title into the URL — `[text](url "title")` breaks the
      actual link target. Needs the regex (or a small post-match split) to
      separate an optional quoted title from the URL.
- [ ] **`gramps:nav:`/`gramps:edit:` dispatch is currently a dead end.**
      MarkdownUtils classifies and styles these links (`gramps_link`,
      `NAMESPACE_MAP`/`VIEW_NAMES` provided as lookup tables) but never
      resolves them, and the one real consumer read so far
      (`PluginManagerPlus.py`'s `_MdInfoPane.open_uri`) treats `gramps_link`
      identically to a plain external hyperlink — handing
      `gramps:nav:Person:I0044` to `Gio.AppInfo.launch_default_for_uri()`,
      which has no handler for that scheme and will just fail silently.
      Recommend: add a shared `open_gramps_link(uri, dbstate, uistate)` (or
      similar) helper *in MarkdownUtils itself*, built on `NAMESPACE_MAP`,
      that any consumer with `dbstate` access calls instead of reinventing
      the dispatch — then fix `PluginManagerPlus.py` to call it.

Lower priority, same phase or later:
- [ ] `inline_to_pango()` duplicates `_parse_inline()`'s logic for table-cell
      rendering (same constructs, a second regex-driven walk). Worth
      collapsing onto `_parse_inline()` + a small `segments_to_pango()`
      eventually — not urgent, no external behavior change, just removes a
      "keep two parsers in sync by hand" liability.

## Phase 2 — Isolate the Gramps extension layer (unlocks everything below)

Extract the two Gramps-specific URL checks out of `_parse_inline` into
standalone functions operating purely on a `(url, label)` pair:

- `classify_image_url(url) -> gramps_icon tuple | None` (the
  `gramps:icon:NAME[:SIZE[:STYLE]]` check, currently inline in the `img`
  branch)
- `classify_link_url(url) -> style_name` (the `gramps:nav:`/`gramps:edit:`
  prefix check, currently inline in the `link` branch)

No behavior change expected — this is a pure refactor. Regression-check
against a representative test document before and after. This is what
makes the extension layer engine-agnostic: any future alternate parser's
adapter calls these same two functions for every link/image it encounters,
so the Gramps-specific syntax can't get out of sync between backends.

## Phase 3 — Media/thumbnail integration (`gramps:media:`)

Confirmed against the real `gramps/gen/utils/thumbnails.py` and
`gramps/gen/plug/_thumbnailer.py`:

- Thumbnail filenames are `md5(source_path + optional_rectangle)`, not
  handle-based — but callers never compute this; `get_thumbnail_image()` /
  `get_thumbnail_path()` do it internally and never crash (fall back to a
  generic `document.png`/`image-missing.png`/`gramps-url.png`).
- Non-image mime types (PDFs, etc.) already flow through the same function
  via the pluggable `Thumbnailer` registry (`imagethumb` + `gnomethumb`
  built in). A future WebP/AVIF thumbnailer addon needs zero MarkdownUtils
  changes — `get_reg_thumbnailers()`/`run_thumbnailer()` already dispatch
  generically by mime type.
- `Thumbnailer.run(mime_type, src_file, dest_file, size, rectangle)` has no
  page/frame parameter, and the cache-key hash has no room for one either —
  a real Gramps-core gap for a "one PDF, many on-demand page thumbnails"
  design. **Does not block this work**: page selection will be handled at
  the Media-object-curation layer (Citation galleries, extract-page-as-its-
  own-Media-object), not as a live parameter on the Markdown reference — so
  `gramps:media:` never needs a page argument.

Concrete steps:
- [ ] Add `Segment.gramps_media` field: `(id_or_handle, size)`, parallel to
      the existing `gramps_icon` field.
- [ ] Add a `resolve_media: Callable[[str, str], str | None] | None`
      parameter to `render_markdown()`, mirroring the existing `resolve_path`
      pattern — default `None` (no-op / falls back to plain text), so
      MarkdownUtils itself never imports `dbstate` or `gramps.gen.lib`, and
      still renders correctly in a context with no open family tree (e.g.
      Plugin Manager plus's own README pane).
- [ ] Recognize `gramps:media:<id>[:size]` in Phase 2's `classify_image_url`.
- [ ] Document the resolver contract explicitly: implementations must call
      `gramps.gen.utils.thumbnails.get_thumbnail_path()` /
      `get_thumbnail_image()` — never reimplement hashing, mime detection,
      or thumbnail generation. This was the specific requirement raised
      mid-conversation ("should leverage Gramps thumbnailing, not
      circumvent it") and is the main risk of a first-pass implementation
      quietly re-deriving its own thumbnail cache instead.
- [ ] Wire an actual `resolve_media` in whichever consumer has `dbstate` —
      almost certainly Markdown Dash (not `PluginManagerPlus.py`, which has
      no open family tree to resolve against).

## Phase 4 — Optional 3rd-party parser backend (do last; lowest urgency)

Only after 1-3 are stable and live-verified. Confirmed viable via the real
Gramps source (`gramps/gen/utils/pypi.py`, the Addon Manager install flow
in `gramps/gui/plug/_windows.py`):

- MarkdownUtils's own `.gpr.py` must **not** declare `requires_mod` on a
  3rd-party parser — that would make the dependency-free base layer's
  availability depend on an optional upgrade, backwards. Keep it internal:
  `try: import marko ... except ImportError: _BACKEND = None` inside
  `MarkdownUtils.py` itself.
- Licensing/bundling constraint (since this is a core-bundling candidate):
  never vendor a 3rd-party parser's source into MarkdownUtils.py. Optional
  backends are always the *user's own* PyPI install, kept at arm's length.
- For discoverable installation (not everyone will `pip install` by hand):
  a separate, thin, optional companion addon whose entire job is
  `requires_mod=["marko"]` — installing/updating *that* addon is what
  triggers Gramps' own Addon Manager to pull the dependency into `lib/` via
  its existing pip/stdlib-installer flow. MarkdownUtils itself stays
  untouched either way.
- `marko` is the best-fit candidate found: pure-Python, active GFM
  extension, and its import name matches its PyPI name (no
  `_IMPORT_TO_PYPI` mapping gap). **Avoid `markdown-it-py` for now** — its
  import name (`markdown_it`) doesn't match its PyPI name
  (`markdown-it-py`) closely enough for Gramps' existing name-resolution
  table to bridge automatically; using it today would silently fail to
  auto-install until Gramps core's own mapping table gets a new entry.
- Design: one canonical adapter contract,
  `_segments_from_<backend>(md_text) -> list[Segment]`, calling Phase 2's
  `classify_image_url`/`classify_link_url` for every link/image the
  backend's own AST produces — so the Gramps extension layer never
  duplicates itself per backend.
- Tables stay on the existing `build_table_widget()` regardless of
  backend — GTK `Gtk.TreeView` embedding is not something any of the
  candidate libraries give you, so this part of the pipeline doesn't
  change no matter which parser is active.

## Phase 5 — Documentation catch-up (ongoing, not just at the end)

- [ ] Revise `MarkdownUtils_DEVELOPER.md` — it was written before the real
      `MarkdownUtils.py` had been shared, so several sections are marked
      "NEEDS VERIFICATION" that are now fully confirmed (the `Segment` IR,
      exact `gramps:` syntax, `NAMESPACE_MAP`/`VIEW_NAMES`,
      `ICON_STYLE_*` constants, the real link-style taxonomy including
      `md_link`/`anchor_link`). Should happen right after Phase 2, since
      that's when the extension-layer contract stabilizes into its final
      shape.
- [ ] `MarkdownUtils_README.md` (end-user) was written at a superficial
      enough level that it likely doesn't need changes from any of this —
      re-check once Phase 3 (media/thumbnails) lands, since that's the
      concrete feature the README already alludes to.
- [ ] Each phase's own docstrings/comments should carry its own disclosure
      per Gramps' AI-generated-code policy at commit time, same as the
      help-button work earlier in this effort.

## What's already done and verified (no action needed)

- `help_doc_button.py` reference snippet + its inlining into
  `PhotoTaggingGramplet.py`: icon-fallback bug, URL-encoding bug,
  `GENERIC_FALLBACK`→`FORCE_REGULAR` correction, and the hidden/deactivated-
  plugin bug in both `resolve_markdown_dash_opener()` and
  `PluginManagerPlus.py`'s `_cb_open_doc_reader` — all fixed and confirmed
  live in real Gramps across every fallback branch (README+viewer, README
  missing, viewer not installed, viewer deactivated/re-enabled without
  restart).
