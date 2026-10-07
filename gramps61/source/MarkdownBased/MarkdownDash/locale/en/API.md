## What was built (Claude 22 Jun 2026)
New module-level public surface

### resolve_localized_path(path) → (resolved_path, is_fallback)
The locale resolution logic was promoted from a private instance method to a proper module-level function. It returns a two-tuple so callers can know whether a locale fallback occurred — which drives the translation invitation. The instance `_get_localized_filepath()` now delegates to it.

### _locale_lang() → (lang_full, lang_short)
Tiny helper that wraps `glocale.get_language_bcp47()` with a safe fallback, used by both the path resolver and the invitation notice. Avoids repeating the try/except in three places.

### _fetch_remote(url, timeout=10) → tmp_path | None
Downloads a remote `https://` URL to a temp file and returns the path. Returns `None` on any network failure. The temp file is deleted by `_MarkdownViewer.__del__`. Uses a `Gramps-MarkdownDash/1.0` User-Agent so server logs are identifiable.

### open_markdown_file(path, uistate, parent, title, addon_name) → Gtk.Dialog
The primary public API for external addons. Handles the full decision tree:

* Local path → `resolve_localized_path()` → detect if English fallback → pass show_locale_invite=True if so
* Remote URL → `_fetch_remote()` → on failure, show network error page
* Constructs a `Gtk.Dialog` sized 700×550 with a `Close` button, embeds a `_MarkdownViewer`, shows it, returns the dialog (caller can connect to `"response"` if needed)

New `_MarkdownViewer` class
A self-contained widget shell that the dialog uses. It builds its own textview + scrolled window + status bar but shares all rendering logic with `MarkdownDash` via late method binding at module load time (the `_SHARED_METHODS` block at the bottom of the file). No code duplication of `_render`, `_load`, `_on_click`, `_on_motion`, `_handle_gramps_link`, etc.
Its `_render_error_md()` is richer than the gramplet's version — it distinguishes between local file-not-found and remote network failure, and when `show_locale_invite=True` appends a proper "`🌐 Help us translate`" section with links to the Gramps Translation HOWTO and Discourse forum.

### MarkdownDash.init() — flexible startup
Priority chain: `_initial_path` attribute (if set by any caller before `init()` runs) → plugin `README.md` → silent Ready state. The gramplet is no longer hard-wired to `README.md`.

### MarkdownDash.cb_home() — respects _initial_path
If a caller set `_initial_path`, Home returns to that document, not the plugin's own README. This means if a help button launched the gramplet pointing at `MyAddon/README.md`, the user can always navigate back to it with Home.

## Caller example (for addon authors)
``` Python
# In any Gramps addon callback:
from MarkdownDash import open_markdown_file

def cb_help(self, _widget):
    open_markdown_file(
        os.path.join(os.path.dirname(__file__), "README.md"),
        self.uistate,
        parent=self.window,
        addon_name=_("My Add-on Name"),
    )
```
That single call handles local/remote path, locale variants, fallback chain, error rendering, and the translation invitation — the addon author writes nothing else.
