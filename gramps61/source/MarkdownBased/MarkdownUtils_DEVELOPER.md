# Markdown Utils — developer reference

**Source of this document:** written without access to `MarkdownUtils.py`
itself — everything below is reconstructed from how `PluginManagerPlus.py`
(specifically its `_MdInfoPane` class) calls into it. Sections marked
**CONFIRMED** reflect calls actually observed in that file; sections
marked **NEEDS VERIFICATION** are inferred from context (a docstring
comment, a style-name constant, a design conversation) and should be
checked against `MarkdownUtils.py` (and ideally `MarkdownDash.py`, which
likely implements a richer consumer of the `gramps_link` style than
`PluginManagerPlus.py` does) before being treated as accurate API
documentation. Please correct/fill in this document once those files can
be reviewed directly, rather than trusting the inferred sections as-is.

## Packaging and distribution

Ships as its own addon under `USER_PLUGINS/lib/` (a `MarkdownUtils.gpr.py`
+ `MarkdownUtils.py` pair), not inside any consuming addon's own folder.
`USER_PLUGINS/lib` is unconditionally on `sys.path` from Gramps startup
(`gramps/gen/const.py`'s `LIB_PATH`), and is walked by Gramps' own addon
scanner the same as any other addon directory — so a `.gpr.py` there
registers normally. `MarkdownUtils.gpr.py` registers under `GENERAL`,
Gramps' own `"Plugin library"` category (see `PTYPE_STR` in
`gramps/gen/plug/_pluginreg.py`) — there's nothing to launch, this
registration exists only so Gramps' addon installer has a valid
`.gpr.py` to find, and so the library is visible/versioned in Plugin
Manager like anything else it distributes.

## Depending on it from your own addon

In your addon's `.gpr.py`:

```python
register(
    ...,
    requires_mod=["MarkdownUtils"],
)
```

`requires_mod` is checked via `importlib.util.find_spec`/`import_module`
during Gramps' plugin-registration scan (`gramps/gen/utils/requirements.py`
-> `gramps/gen/plug/_pluginreg.py`). A failing check removes your plugin
from the registry entirely for that session — not a warning, an actual
deregistration (`del self.__id_to_pdata[...]`, `del self.__plugindata[...]`)
— so your addon simply won't appear if Markdown Utils isn't installed.
Because `lib/` is on `sys.path` before that scan runs, this reliably
detects Markdown Utils once it's installed under `lib/`.

In your addon's own `.py`:

```python
try:
    from MarkdownUtils import (
        ICON_STYLE_COLOR,
        markdown_link_at,
        render_markdown,
        resolve_icon_pixbuf,
    )
    _MARKDOWN_AVAILABLE = True
except ImportError:
    _MARKDOWN_AVAILABLE = False
```

No `sys.path` manipulation needed — plain import, since `lib/` is
already on `sys.path`. Keep the `try`/`except` even alongside
`requires_mod`: the latter guards the common case at registration time,
but isn't a runtime guarantee against every failure mode (a corrupted
install, a partial upgrade). Gate every call site on `_MARKDOWN_AVAILABLE`
and fall back to plain text (a bare `Gtk.TextBuffer.set_text()`) rather
than assuming the import always succeeded.

## Public API — CONFIRMED (observed call sites)

### `render_markdown(textview, md_text, resolve_path=None, image_max_width=..., center_images=..., show_image_captions=..., image_adds_newline=...)`

Renders `md_text` (GitHub-Flavored Markdown) into an already-constructed
`Gtk.TextView`, replacing its buffer's content. Observed keyword
arguments and their apparent purpose, from one consumer's usage:

- `resolve_path`: a callable `(path: str) -> str`, used to resolve an
  image or bare-relative link against wherever the source document
  itself lives (e.g. a plugin's own directory) rather than the current
  working directory. Absolute paths should presumably be returned
  unchanged by your own `resolve_path` implementation.
- `image_max_width`: pixel width cap for rendered images (observed
  values: 560 for a full-width detail pane, 260 for a narrower preview
  pane).
- `center_images`: bool, whether images render centered.
- `show_image_captions`: bool.
- `image_adds_newline`: bool, whether an image forces a following line
  break.

Returns a `dict` with (at least) two keys:

- `"tags"`: some tag-tracking structure (consumed opaquely by the
  caller as `self._tags`, purpose beyond that not confirmed here).
- `"link_uris"`: a structure describing every link/image found, in a
  form `markdown_link_at()` (below) expects to receive back.

### `markdown_link_at(textview, link_uris, x, y)`

Given the `link_uris` structure `render_markdown()` returned and a
pixel position within `textview`, returns `(style, uri)` — the link
under that position (for hover/click handling), or a falsy `style`/`uri`
if there's no link there. Used both on `motion-notify-event` (to swap
the cursor to a pointer over a link) and `button-press-event` (to act
on a click).

### `resolve_icon_pixbuf(icon_name, size, icon_style=ICON_STYLE_COLOR)`

Resolves a themed/Gramps icon name to a `GdkPixbuf.Pixbuf` at the given
pixel size, honoring `icon_style`. Returns `None` (or raises — one
observed caller wraps this in a bare `except Exception`) if the icon
can't be resolved, in which case callers fall back to
`Gtk.IconTheme.get_default().load_icon(...)` directly.

### `ICON_STYLE_COLOR`

A style constant passed to `resolve_icon_pixbuf`, requesting the
full-color variant of an icon rather than a symbolic/monochrome one.
One caller's comment describes `resolve_icon_pixbuf`'s own default (when
`icon_style` is omitted) as `'auto'`, with a `prefer_symbolic = size <=
32` heuristic — implying at least one other style constant exists
(a symbolic counterpart, and possibly an explicit "auto" sentinel).
**NEEDS VERIFICATION:** exact name(s) and full set of style constants.

## Link styles — PARTIALLY CONFIRMED

`markdown_link_at()` returns a `style` string. Five values have been
observed handled by a caller:

| style | Observed handling in one consumer |
|---|---|
| `hyperlink` | Launched via `Gio.AppInfo.launch_default_for_uri()` (desktop default handler) |
| `mailto_link` | Same as `hyperlink` in the observed consumer |
| `gramps_link` | Same as `hyperlink` in the observed consumer — see note below |
| `file_link` | Strips a `file://` prefix if present, then opens the local path with the OS default application if it exists |
| `md_link` | Strips a `file://` prefix if present, reads that local `.md` file, and re-renders it in the same pane (in-place navigation between sibling doc files, e.g. a README linking to another doc in the same folder) |

**NEEDS VERIFICATION — this is the "extra layer" (embedding/navigating/
editing Gramps objects from documentation) the end-user doc describes,
and it is the least-confirmed part of this reference.** In
`PluginManagerPlus.py`'s own `_MdInfoPane`, `gramps_link` is handled
identically to a plain external hyperlink — it does not itself look up
or navigate to a Gramps object. That strongly suggests the richer
behavior (jumping to a person/place/etc., opening an editor) is
implemented by a *different* consumer with access to `dbstate`/`uistate`
(Markdown Dash is the likely candidate, given its role as the primary
in-app documentation reader), which intercepts `gramps_link` URIs
itself rather than relying on `MarkdownUtils` to resolve them — or,
alternatively, `MarkdownUtils` exposes a lookup/dispatch helper for this
that simply isn't used by `PluginManagerPlus.py`. Either way: **do not
copy `_MdInfoPane`'s handling of `gramps_link` as a reference for
building the object-navigation feature** — confirm the real mechanism
against `MarkdownDash.py` and/or `MarkdownUtils.py` first.

## Image syntax — NEEDS VERIFICATION

One source comment references a `gramps:icon:name:size` image syntax
for embedding a themed Gramps icon inline in rendered Markdown (e.g. as
the target of a Markdown image tag). The exact syntax, delimiter
conventions, and whether other `gramps:`-scheme forms exist (for object
references, as opposed to icons) are not confirmed here.

## Worked example of a consumer

`PluginManagerPlus.py`'s `_MdInfoPane` class is a reasonably complete
example of wiring this library into a `Gtk.TextView`: constructing the
view, setting motion/click event masks, connecting
`motion-notify-event`/`button-press-event` to swap the cursor and
dispatch clicks via `markdown_link_at()`, and implementing `render()`/
`open_uri()` around `render_markdown()`. Worth reading directly rather
than re-deriving this pattern from scratch for a new consumer.

## What's still needed to make this document reliable

- `MarkdownUtils.py` itself, to confirm full function signatures
  (parameter types, defaults, exceptions raised), the complete set of
  `ICON_STYLE_*` constants, and the actual `gramps:` URI grammar.
- `MarkdownDash.py`, to confirm how (or whether) `gramps_link` actually
  drives object navigation/editing, since `PluginManagerPlus.py` alone
  doesn't demonstrate it.
