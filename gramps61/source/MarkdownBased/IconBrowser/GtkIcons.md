# GtkIcons.md — GTK3 icon-theme symbolic/color resolution reference

Working notes from debugging `resolve_icon_pixbuf()` in `MarkdownUtils.py`
(the native/basic engine). Captured as a springboard for a deeper dive, not
as verified-on-live-GTK fact — see "Unverified / needs live testing" below.

## Symptom that started this

Icons in table cells and inline text randomly showed full color or B&W
symbolic on the same machine, same icon theme. Reported pattern: even
pixel sizes → symbolic B&W; odd pixel sizes → full color, scaled.

## Root causes found (3 distinct bugs, in the code we control)

### 1. Local file-fallback tier had zero symbolic awareness (dominant cause)
`resolve_icon_pixbuf()` has a 5-tier resolution order: live `Gtk.IconTheme`
cascade (2 tiers: exact name, then `GRAMPS_ICONS` alias candidates) → local
raster PNG search in `DATA_DIR/icons/hicolor/{size}x{size}/{category}/` →
local scalable SVG search → `IMAGE_DIR` fallback. The last three tiers
did a naive `name + ".png"` search — **never** tried `name + "-symbolic" +
ext`, regardless of size or any preference. Since icon themes only define
fixed-size buckets at conventional *even* sizes (16/22/24/32/48/64...), an
odd-size request routinely misses the live theme cascade entirely (tiers
1–2 return `None` for every candidate, every style) and falls through to
these naive local tiers — which are then unconditionally full color.
Even sizes usually hit a real theme bucket and never reach this tier.
**Fix:** local tiers now build the same style-ordered candidate name list
(`_name_variants()`) as the theme-cascade tier.

### 2. Symbolic-vs-color decision used *our own request string*, not GTK's actual resolution
Original check: `lookup_name.endswith("-symbolic")` — true whenever *we*
decided to try the symbolic name, regardless of what
`Gtk.IconTheme.lookup_icon()` actually resolved (with
`GENERIC_FALLBACK` set, GTK can silently substitute a different icon/style
when no exact match exists at that size). **Fix:** use
`GtkIconInfo.is_symbolic()` — GTK's own answer to "is this actually
symbolic" — instead of the request-string heuristic.

### 3. No `FORCE_SIZE` flag
Without it, per GTK docs, GTK "avoids scaling icons it considers
sufficiently close to the requested size" — inconsistent apparent sizing
between the color and symbolic paths. **Fix:** added
`Gtk.IconLookupFlags.FORCE_SIZE` to the lookup flags.

## Key GTK3 API facts (from docs, not yet live-verified — see below)

- **Icon theme directories are conventionally fixed at even pixel sizes**
  (16/22/24/32/48/64/96/128/256) per the freedesktop icon theme spec.
  Odd/arbitrary sizes are essentially always a nearest-match/miss
  scenario, never an exact bucket hit.
- **`Gtk.IconTheme.has_icon(name)` is size-agnostic** — checks existence
  anywhere in the cascade, at any size. Not useful for predicting whether
  a lookup will succeed at a *specific* requested size.
- **`Gtk.IconTheme.lookup_icon(name, size, flags)`** does nearest-size
  matching within each directory's declared `Threshold`/`MinSize`/
  `MaxSize` (icon theme spec); can return `None` if nothing is close
  enough, or substitute per `GENERIC_FALLBACK` name-shortening rules
  (chops trailing `-word` segments, e.g. `foo-bar-symbolic` → `foo-bar` →
  `foo`) when the exact name isn't found.
- **`Gtk.IconLookupFlags.FORCE_SIZE`** — without it, GTK may return an
  asset "close enough" to the requested size unscaled, for sharpness.
- **`GtkIconInfo.is_symbolic()`** — "Checks if the icon is symbolic or
  not. This currently uses only the file name and not the file contents."
  I.e. it's still a naming-convention check under the hood, just done by
  GTK against the *actually resolved* file rather than our request.
- **`GtkIconInfo.load_symbolic_for_context(style_context)`** — per docs,
  gracefully degrades: *"If the icon is not a symbolic one, the function
  will return the result from `gtk_icon_info_load_icon()`"* (i.e. plain
  full color, silently, no error/signal). This is what let bug #2 hide
  for a long time — the wrong-condition call still often "worked" because
  this function's own fallback papered over it.
- **`GtkIconTheme.has_icon("name")` gotcha** (GNOME wiki "nice to know"):
  can return `FALSE` even when `name-symbolic.svg` is literally present on
  disk, due to strict resource-path/index-cache expectations. Treat
  `has_icon()` results with suspicion in edge cases.
- **`Gtk.IconLookupFlags.FORCE_SYMBOLIC`** exists in GTK3 (≥3.14ish) as an
  alternative to manually appending `-symbolic` to the name — NOT
  currently used in our code. Worth evaluating in the deep dive as a
  cleaner replacement for manual name-suffixing.

## What we built on top (feature, not bug fix)

Added a 3-way `icon_style` control: `'auto'` (old fixed behavior: symbolic
≤32px / color >32px, hard fallback to `None` if that style doesn't exist),
`'color'`, `'symbolic'` (the latter two prefer one style but gracefully
degrade to the other if nothing exists for that specific icon in the
preferred style — never silently blank). Settable three ways:
1. Document-wide: `<!-- icon_style=color -->` control-comment (2nd line,
   consumed by `MarkdownDash._parse_directives()`).
2. Per-icon: `gramps:icon:NAME:SIZE:STYLE` (third URL segment).
3. Programmatically: `icon_style=` kwarg on `resolve_icon_pixbuf()`,
   `parse_markdown()`, `build_table_widget()`.

Implementation detail worth remembering: `_parse_inline()` recurses
through 13+ call sites (nested emphasis/links/lists/blockquotes), so the
per-document default isn't threaded as a parameter through all of them —
it's stashed in a module-level `_current_default_icon_style`, set at the
top of `parse_markdown()`. Documented as single-threaded-GTK-safe only
(not safe for concurrent `parse_markdown()` calls from multiple threads).
`build_table_widget()` is a separate call path (table cells rendered
outside `parse_markdown()`), so it needs `default_icon_style` passed
explicitly by the caller — does not share the ambient value.

## Verification methodology used (important caveat)

**No live GTK/icon theme was available in the sandbox this was debugged
in.** All verification was via hand-built fakes:
- `gi_stub/` — a minimal fake `gi.repository.Gtk/Gdk/GdkPixbuf/Pango`
  package tree, just enough surface area to import and exercise
  `MarkdownUtils.py`'s logic (not a real GTK binding).
- `FakeIconTheme`/`FakeIconInfo` classes simulating specific scenarios
  (e.g. "symbolic only exists at buckets {16,24,32}, GENERIC_FALLBACK
  substitutes color outside those") to prove the *decision logic* is
  correct given a hypothesized GTK behavior — this validates our code's
  logic against a *model* of GTK, not against real GTK.
- `fake_gramps_pkg/` — stub `gramps.gen.const` module with `DATA_DIR`/
  `IMAGE_DIR` pointing at `/tmp/fake_gramps_data`, plus real tiny 1x1 PNG
  fixture files, to exercise the actual filesystem-search code
  (`os.path.isfile` etc.) for real.

**None of this confirms the hypothesized GTK behaviors are what a real
GTK3 install actually does.** The GTK API facts above are drawn from
public documentation/wiki pages found via web search, not from reading
GTK's C source or running against a live `Gtk.IconTheme`.

## Unverified / needs live testing (deep-dive candidates)

- [ ] Does `GENERIC_FALLBACK` actually cause silent style substitution the
      way we hypothesized, on a real install (Adwaita, Gramps' bundled
      icon set, a random distro theme)? Test with real odd-size requests
      against `Gtk.IconTheme.get_default()` and print `info.get_filename()`.
- [ ] What is the actual `Threshold`/`MinSize`/`MaxSize` for the specific
      icon directories Gramps ships/depends on? (Check the theme's
      `index.theme` files directly.)
- [ ] Does `Gtk.IconLookupFlags.FORCE_SYMBOLIC` behave better than manual
      `-symbolic` suffixing + `is_symbolic()` checking? Worth a real
      side-by-side.
- [ ] HiDPI/scale-factor interaction — none of this considered
      `gtk_icon_theme_lookup_icon_for_scale()` or output scale >1.
      Symbolic vs color asset availability might differ by scale bucket
      too.
- [ ] Dark-mode / live theme-switch behavior — `load_symbolic_for_context`
      recoloring should track theme changes automatically since it reads
      the `style_context` at call time, but this was never tested against
      an actual theme switch while a gramplet is open.
- [ ] GTK4 differences — Gramps is GTK3-only today per this codebase, but
      if that ever changes, `GtkIconTheme`'s API changed substantially in
      GTK4 (`Gtk.IconPaintable` replaces `GtkIconInfo`).
- [ ] Wayland vs X11 — no reason to expect a difference for icon theme
      resolution specifically, but untested.
- [ ] Real performance: `_load_any()`/`_name_variants()` now does up to
      2x the lookup attempts per icon compared to the original code in
      forced-style modes. Not measured against a live theme cascade,
      which may have non-trivial per-call cost.

## File/function map (for quick navigation next time)

- `MarkdownUtils.py`
  - `ICON_STYLE_AUTO` / `_COLOR` / `_SYMBOLIC`, `_VALID_ICON_STYLES` —
    style constants.
  - `_GRAMPS_ICON_URL_RE` — regex for `gramps:icon:NAME[:SIZE[:STYLE]]`.
  - `_current_default_icon_style` — ambient module-level default, set by
    `parse_markdown()`.
  - `_extract_leading_icon()` — table-cell icon extraction (own
    `default_icon_style` param, not ambient).
  - `_parse_inline()` — inline (non-table) icon extraction, reads the
    ambient default.
  - `resolve_icon_pixbuf()` — the actual resolution logic; see
    `_name_variants()` and `_load_any()` inside it for the
    style-preference-with-fallback mechanism.
  - `build_table_widget()` — table rendering; takes `default_icon_style`
    explicitly (separate call path from `parse_markdown()`).
- `MarkdownDash.py`
  - `_parse_directives()` — consumes the `<!-- icon_style=... -->`
    control-comment option.
  - `_load()` — validates `options.get("icon_style")` against the 3 valid
    values, falls back to `"auto"`.
  - `_render()` — threads `default_icon_style` into both
    `parse_markdown()` and `build_table_widget()` calls.
