# HelpDocButton.py -- companion notes

Exposition and parameter docs for `help_doc_button.py`, kept out of the module itself to keep the code short. Function bodies carry only a one-line docstring naming the function and linking to its section below.

## What it does

Adds a color "Help" button to a gramplet/report/tool dialog. Clicking it opens a plugin's own local `README.md` in an undocked, Windows-menu-registered Markdown Dash window when one exists and Markdown Dash is available, parented to the main Gramps window (never the calling dialog); otherwise it falls back to opening the plugin's registered `help_url` in the desktop's default browser.

Beyond the feature itself, this snippet exists as a worked example of several things that reliably bite developers new to GTK/Gramps. Each is called out below with the function that demonstrates the fix.

- **Icon-name lookup can silently return the wrong variant** (`resolve_help_icon`). Most theme icons ship both a full-color asset (`help-browser`) and a flat "symbolic" one (`help-browser-symbolic`) meant for auto-recoloring chrome. Relying on default lookup flags does not guarantee you get the color one, and the fix is `Gtk.IconLookupFlags.FORCE_REGULAR` (available since GTK 3.24, well within Gramps' minimum GTK version) -- not, as an earlier revision of this doc claimed, `GENERIC_FALLBACK`. `GENERIC_FALLBACK` only controls a different behavior (progressively shortening the name at `-` characters, e.g. `foo-bar-baz` -> `foo-bar` -> `foo`, when the exact name has no match) and does not select between regular/symbolic variants; it has been removed from `resolve_help_icon()`'s flag set and replaced with `FORCE_REGULAR`. Any explanation of a GTK/Gio flag's behavior in this document should be treated as needing a docs check before being trusted verbatim, this one included -- flag semantics are a common source of confidently-wrong claims, from humans and AI tools alike.
- **`FORCE_SIZE` matters and is easy to omit.** Without it, `lookup_icon()` can return the theme's nearest available size instead of the one you asked for, which renders blurry or oddly cropped once scaled. It's in the flag set here for exactly that reason.
- **The "icon not found" fallback must not reintroduce the bug it's guarding against.** An earlier revision of `resolve_help_icon()` fell back to `image.set_from_icon_name(_HELP_ICON_NAME, Gtk.IconSize.DIALOG)` when `lookup_icon()` found nothing -- exactly the unreliable-variant call the rest of the function exists to avoid, and it also silently ignored the requested `size`. It now leaves the `Gtk.Image` empty and logs a warning instead: a visibly missing icon is easier to notice and fix (install/complete the icon theme) than one that is silently the wrong variant or the wrong size.
- **`set_image()` alone never puts a text label on the button, and a label without `always_show_image` can hide the icon.** An earlier revision of `add_help_button()` called `button.set_image(...)` and `button.set_tooltip_text(...)` but never `button.set_label(...)` at all -- the button was icon-only, with "Help" existing only as a hover tooltip, not as visible text. It now also calls `button.set_label(_("Help"))`. That alone is not sufficient on every desktop theme: GTK's `gtk-button-images` setting can suppress a button's icon whenever the button also has a text label (several GNOME-based themes do this by default), so the icon set via `set_image()` could still silently vanish next to the word "Help". `button.set_always_show_image(True)` forces the icon to stay visible regardless of that setting.
- **The 48px default `size` suits a dialog's own action area, not a compact button row.** A gramplet packing this button into a horizontal `Gtk.Box` alongside normal-sized text buttons (e.g. `NoteStylingEditor.py`'s "Undo" / "Clear Markup") should pass a smaller `size`, such as `16`, so the Help button doesn't dwarf its neighbours -- the function's own default is left at `48` since other callers may be packing it into a larger space, such as a Tool/Report dialog's own action area.
- **A `Gtk.Image`'s own tooltip does not show once it's inside a `Gtk.Button`.** `Gtk.Image.set_tooltip_text()` only works if the image itself can receive pointer/focus events, which it generally can't as a button's child widget. `add_help_button()` therefore calls `button.set_tooltip_text(...)` on the *button*, after `button.set_image(...)`, not on the image returned by `resolve_help_icon()` -- setting it on the image would silently produce no visible tooltip at all, a common source of "I set a tooltip but nothing shows up" confusion.
- **"Not hidden", "registered", "loadable", and "has this function" are four different questions.** A plugin can appear in `PluginRegister` (its `.gpr.py` was found and parsed) yet still fail to import (a broken install, a missing dependency), import fine but be an older version that predates the API you want to call -- or, distinctly, be registered and perfectly loadable but *deliberately turned off* by the user via the Plugin Manager's Deactivate button. `resolve_markdown_dash_opener()` checks all four, in order, precisely because collapsing them into one boolean check ("is it in the registry?") produces confusing failures later, when `load_plugin()` returns `None` or `getattr(mod, "open_markdown_file", None)` is `None` and the caller has no idea why.
- **`GuiPluginManager.load_plugin()` does not itself respect a user's "Deactivate" choice -- confirmed by a live test, and traced to a matching gap in the very source this was modeled on.** `GuiPluginManager.get_hidden_plugin_ids()` (see `PluginManagerPlus.py`'s own `self.hidden = self._pmgr.get_hidden_plugin_ids()`) is how Gramps' own UI tracks which plugins the user has hidden/deactivated -- but it is only *consulted* by that UI's own listing/filtering and by Gramps' startup autoload. `load_plugin()` itself will happily import and return a hidden plugin's module if called directly, which is exactly what a live test against this addon found: Markdown Dash registered-but-deactivated in Plugin Manager was still used to open the README. Tracing this back, `PluginManagerPlus.py`'s own `_cb_open_doc_reader` (the method `resolve_markdown_dash_opener()` was modeled on) has the same gap -- it calls `self._pmgr.load_plugin(pdata)` with no hidden-state check either. `resolve_markdown_dash_opener()` now checks `_MARKDOWNDASH_ID in GuiPluginManager.get_instance().get_hidden_plugin_ids()` first and falls back to `help_url` if so, treating "the user turned this off" the same as "not installed" rather than silently overriding that choice. `_cb_open_doc_reader` in `PluginManagerPlus.py` was not changed here (out of scope for this snippet) but has the identical bug and would benefit from the same fix.
- **`PluginData.fpath` can be `None` or empty even for a real, registered id.** This happens for built-in plugins with no on-disk addon folder, and for entries left over from a previous scan whose files have since been removed. Code that does `os.path.join(pdata.fpath, "README.md")` without checking `pdata.fpath` first will raise on `None`, or silently build a bogus path.
- **A `Gtk.Dialog` opened as a plain object is invisible to Gramps' own window management.** Gramps tracks its top-level windows through `uistate.gwm` (the `GrampsWindowManager`), which is what populates the **Windows** menu, handles click-to-restore, and lets Gramps enumerate/close its own windows on shutdown. A dialog built without going through `ManagedWindow` never registers with any of that -- it can still work as a window, but it won't appear in the Windows menu and Gramps has no way to know it exists. `open_markdown_file()` (in `MarkdownDash.py`, not reproduced here) wraps its reader in a `ManagedWindow` subclass specifically so this snippet's dialog gets that Windows-menu presence for free.
- **`ManagedWindow` wrapping alone is not sufficient for correct Windows-menu behavior -- a plain `Gtk.Dialog`'s own default window-manager type hint is a separate, additional problem.** Found the hard way, in a *different* addon (`GtkDiagnosticsToolkit`) built on this exact same pattern: a `Gtk.Dialog` defaults to the `DIALOG` type hint, which on many window managers is what actually breaks correct Windows-menu tracking, appearance, and restore -- independently of whether the window is a proper `ManagedWindow`, and independently of `build_menu_names()`'s own leaf/branch setting (a detour chased first, before landing on this). The fix, confirmed against `PluginManagerPlus.py`'s own working code and its own comment on precisely this: `self.window.set_type_hint(Gdk.WindowTypeHint.NORMAL)`, called once, right after constructing the `Gtk.Dialog`. **This has not been verified one way or the other in `open_markdown_file()`'s own `Gtk.Dialog` construction in `MarkdownDash.py`** -- if that dialog doesn't already set this hint, every addon using this snippet inherits the same Windows-menu misbehavior silently, with nothing in this doc's own worked example to point at why. Confirming (and, if missing, adding) this hint in `open_markdown_file()` itself is on the integration checklist below.
- **Parenting a spawned window to the wrong widget closes it prematurely, or never closes it.** The natural-looking `parent=self.window` (the calling Tool/Report dialog) means the reader window is destroyed the moment that dialog closes -- surprising for a "documentation" window someone may want to keep open while browsing other plugins. `cb_show_help()` passes `parent=uistate.window` (Gramps' own main window) instead, so the reader survives the calling dialog closing, exactly the same convention Gramps' own top-level windows use.
- **A bare `except Exception` around a GTK/GIO call hides the actual failure mode.** `Gio.AppInfo.launch_default_for_uri()` raises `GLib.Error`, a specific, catchable type; `open_help_url()` catches that specifically (and logs it) rather than swallowing every possible exception, which would also mask real bugs elsewhere in the same `try` block.
- **`help_url` is not always a URL.** Gramps' plugin registration lets `help_url` be either a full `http(s)://` URL or a bare wiki page title (resolved against gramps-project.org by convention). Code that always treats it as a ready-to-open URL will send people to a 404 for any plugin using the short form; `open_help_url()` checks the prefix and resolves accordingly.
- **A wiki page title is not automatically a valid URL query value.** An earlier revision of `open_help_url()` built the fallback URL with an f-string (`f"...?title={help_url}"`), which is only safe for titles with no spaces or other characters that need percent-encoding -- a `help_url` such as `"Addon: Photo Tagging"` would have produced a broken URI passed straight to `Gio.AppInfo.launch_default_for_uri()`. It now encodes the title with `urllib.parse.quote(help_url, safe=":")` (the `:` in `Addon:` kept literal since it is valid unescaped in a URL query component, everything else escaped).
- **User-visible strings need `_()`, and the translator lookup itself can fail.** `glocale.get_addon_translator(__file__)` raises `ValueError` for an addon with no translation catalog registered yet (e.g. during early development) -- the `try`/`except ValueError: _trans = glocale.translation` fallback avoids a hard crash for that ordinary, temporary state rather than assuming every addon always has translations wired up already.

## AI-generated-code disclosure

Per the ["AI generated code"](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code) section of the Gramps contribution guide:

- **Tool, provider, version:** Claude (Anthropic), model "Claude Sonnet 5", web chat (claude.ai). Generated 2026-09-02.
- **Prompts used (summarised across the conversation):** (1) review `PluginManagerPlus.py`, `MarkdownDash.py`, `MarkdownUtils.py`, `gramps_icon_inventory.md` and `doc_reader_integration.md`, and produce a tight, reusable snippet giving a gramplet/report/tool dialog a color help-browser button that opens the plugin's own local README.md in an undocked, Windows-menu Markdown Dash window when available, else falls back to the plugin's registered `help_url`; (2) a follow-up question about whether `PluginRegister` rescanning was needed, resolved by removing the rescan-retry logic entirely (see "Why there's no rescan-retry" below); (3) a follow-up request to move exposition out of the `.py` into this companion document; (4) this request, to squeeze the header comment to three lines, reduce in-code docstrings to a name-plus-anchor-link each, and unwrap this document's paragraphs.
- **Constraint documents the assistant worked under:** [Gramps AGENTS.md](https://github.com/gramps-project/gramps/blob/master/AGENTS.md) (code style, docstrings, import grouping, `cb_` callback prefix, type hints, etc. -- note that the license-header and full-docstring conventions there were deliberately relaxed in this module at the requester's explicit instruction, see below) and the "AI generated code" wiki section linked above.
- **Provenance:** distilled from patterns already present in, and supplied as reference material from, `PluginManagerPlus.py`, `MarkdownDash.py`, `MarkdownUtils.py`, `gramps_icon_inventory.md`, and `doc_reader_integration.md` -- see "Where each piece came from" below. No third-party copyrighted source was reproduced verbatim; only the interfaces documented in those files were relied upon.
- **Verification:** formatted with Black (clean) and checked with Pylint (10.00/10 as of the revision below, ignoring `import-error`/`no-member`/`no-name-in-module` findings caused by `gi`/`gramps` not being importable outside a real Gramps environment).
- **Deviations from AGENTS.md, by explicit request:** the standard GPL-2.0-or-later boilerplate header is replaced with a 3-line copyright/license notice, and per-function Sphinx `:param:`/`:returns:` docstrings are replaced with a one-line "name -- see HelpDocButton.md#anchor" pointer, with the actual parameter documentation moved here.
- **Follow-up revision:** Claude (Anthropic), model "Claude Sonnet 5", Claude Code CLI (claude.ai/code). Prompted to review this snippet and its companion doc for improvements, then to apply the resulting fixes. Changes made: replaced the icon-fallback path in `resolve_help_icon()` (no longer calls `new_from_icon_name()`, the exact pattern the function exists to avoid, and no longer ignores `size`); replaced `GENERIC_FALLBACK` with `FORCE_REGULAR` in that function's lookup flags and corrected this document's explanation of what `GENERIC_FALLBACK` actually does; added percent-encoding (`urllib.parse.quote`) to the wiki-title branch of `open_help_url()`; added the "TEMPLATE SHORTCUT" warning at the top of the `.py` header; and added checklist items 7 and 8 below. Re-verified with Black and Pylint after each change.
- **Second follow-up revision (human-found bug, 2026-09-03):** the human tester found, via a live test in real Gramps, that a registered-but-Deactivated Markdown Dash was still being used to open the README -- `resolve_markdown_dash_opener()` never checked hidden/deactivated state. Traced to a matching gap in `PluginManagerPlus.py`'s own `_cb_open_doc_reader` (see the bullet above on `GuiPluginManager.load_plugin()`). Fixed by checking `GuiPluginManager.get_hidden_plugin_ids()` before calling `load_plugin()`. Re-verified live (see below): falls back correctly while deactivated, and works again immediately on re-enabling -- no Gramps restart needed, confirming `get_hidden_plugin_ids()` reflects a live/current state rather than something cached at startup.
- **Live integration test (human-run, in real Gramps, 2026-09-03) -- all branches confirmed on first or immediately-following pass:** the README/Markdown-Dash/help_url routing logic was inlined into `PhotoTaggingGramplet.py` (per the checklist -- `resolve_help_icon`/`add_help_button` were *not* brought in, since that host module already had its own, better icon-loading path; see its own file for what was actually merged) and exercised in a running Gramps instance, which this sandbox cannot do (no working PyGObject, no Gramps install here -- only a mocked-dependency `unittest` smoke test was possible pre-flight, see `help_button_logic_test.py`, 16/16 passing including the two regression cases for the bug below). Confirmed: (1) README.md present + Markdown Dash registered -> opens in Markdown Dash; (2) README.md renamed away (Markdown Dash still registered) -> falls back cleanly to `help_url`; (3) Markdown Dash not registered/installed at all -> falls back cleanly; (4) Markdown Dash registered but Deactivated in Plugin Manager -> falls back cleanly, and resumes using Markdown Dash immediately on re-enabling, without restarting Gramps. This also confirms `MARKDOWNDASH_ID = "markdowndash"` (an unverified guess at the time it was written, since Markdown Dash isn't present in this repo) is correct. All four states this function distinguishes (not hidden+loadable / hidden / not registered / registered-but-unloadable-or-outdated) are now exercised live except the broken-install and outdated-version cases, which are edge cases arising only from a corrupted install (see the integration checklist's note on these being hard to trigger deliberately).
- **Third follow-up revision (2026-09-18):** Claude (Anthropic), model "Claude Sonnet 5", web chat (claude.ai), working on a separate addon (`GtkDiagnosticsToolkit`) built on this same Help-button pattern. Prompted to review this doc against lessons that addon's own development surfaced, then update it. Two additions, both from that addon's own live debugging, neither previously documented here: (1) extended the `ManagedWindow`/Windows-menu bullet above with the `Gdk.WindowTypeHint.NORMAL` finding -- a plain `Gtk.Dialog`'s default type hint breaks Windows-menu behavior independently of `ManagedWindow` wrapping itself, confirmed against `PluginManagerPlus.py`'s own working code, and not yet verified one way or the other in `open_markdown_file()`'s own dialog construction; (2) added the new "Using MarkdownUtils directly, without Markdown Dash" section, documenting an alternative integration shape this doc previously had no guidance for -- an addon rendering with the shared `MarkdownUtils` library directly, without depending on the full Markdown Dash reader gramplet, which needs its own hidden-state check (against MarkdownUtils' own id, not Markdown Dash's), its own `ManagedWindow`/type-hint handling (none of it inherited from `open_markdown_file()`), and its own content-derived title. No changes made to `help_doc_button.py` itself or to its own test file -- both additions describe an alternative pattern and a gap to verify elsewhere, not a bug in this file's own code.

## Where each piece came from

- **README discovery** (`find_local_readme`) -- the `pdata.fpath`/`README.md` check from `doc_reader_integration.md` section 1, also used in `PluginManagerPlus.py`'s `_cb_populate_info_pane_popup`.
- **Markdown Dash verification chain** (`resolve_markdown_dash_opener`) -- the registered -> loadable -> API-present sequence from `doc_reader_integration.md` section 2 / `PluginManagerPlus.py`'s `_cb_open_doc_reader`, and the `parent=uistate.window` convention that keeps the reader window a child of the *Gramps main window*, not the calling dialog.
- **`help_url` fallback** (`open_help_url`) -- mirrors `PluginManagerPlus.py`'s `_MdInfoPane.resolve_help_full_url` / `_cb_open_help_url`: a bare wiki page title is resolved against gramps-project.org, a full URL is used as-is.
- **Color icon resolution** (`resolve_help_icon`) -- the "Forcing the color variant over the symbolic fallback" pattern from `gramps_icon_inventory.md`.

## Why resolve the icon by name, not a hardcoded path

The original ask named a literal path: `/usr/share/icons/gnome/48x48/apps/help-browser.png`. That path only exists if the GNOME icon theme specifically is installed, at that exact size. `resolve_help_icon()` instead asks the active `Gtk.IconTheme` for `"help-browser"` by name, color variant preferred -- the same 48x48, full-color "apps" asset the hardcoded path was reaching for, but found correctly under whatever theme is actually active, on any platform.

## If Markdown Dash merges into Gramps core

`_MARKDOWNDASH_ID` / `resolve_markdown_dash_opener()` assume Markdown Dash is a registered *addon*, found via `PluginRegister.get_instance().get_plugin("markdowndash")`. There is discussion of folding MarkdownUtils/Markdown Dash into Gramps core for 6.2/7.0. If that happens, `PluginRegister` will no longer have this id at all -- `resolve_markdown_dash_opener()` will keep returning `None` (its normal "not available" result), so every caller falls back to `help_url` forever. That is not a crash, and matches this function's designed degrade-gracefully behavior -- but it silently mistakes "now built into Gramps" for "never installed," permanently losing the in-app README viewer without any error to notice by. Confirmed working against the real `MarkdownDash.gpr.py` (id `"markdowndash"`) via a live integration test on 2026-09-03, so this note only applies from whenever that core migration lands. Whoever does that migration should replace this addon-id lookup with however the core module is actually detected/imported at that point, in every host module this snippet has been inlined into -- not just here.

## Why there's no rescan-retry

`PluginRegister` is always the authoritative answer to "does Gramps currently know about Markdown Dash" -- but it only *learns* that from an on-disk scan that runs once at Gramps startup, and otherwise only on explicit request (e.g. Plugin Manager's own "Load"/"Update" actions, or an addon tool that triggers a rescan). An earlier version of this snippet added an automatic rescan-and-retry for the case where Markdown Dash was installed mid-session without one of those being used. That was removed: it pulled in `dbstate`/`CLIManager`-adjacent plumbing for a genuinely rare case Gramps' own GUI already covers, and the cost of getting it wrong (falling back to `help_url` instead of the in-app README) is minor and self-correcting -- the button works correctly again on the very next lookup after any rescan.

<a id="markdownutils-direct"></a>
## Using MarkdownUtils directly, without Markdown Dash

Every pattern above assumes going through Markdown Dash's own
`open_markdown_file()` -- the right choice when the full reader
(editor mode, switching between other `.md` files in the same folder,
folder navigation) is wanted, or already available as a dependency.
Not every host addon wants that: a small tool or gramplet that just
needs to render one `README.md` in a plain popup, without taking on a
dependency on the whole Markdown Dash reader gramplet, can instead
import `MarkdownUtils` (the shared rendering *library* the two
addons are built on) directly. `GtkDiagnosticsToolkit` is a real,
worked example of this alternative -- its own Help button renders
`README.md` with `MarkdownUtils.render_markdown()`/`markdown_link_at()`
inside a small popup it builds and owns itself, only falling back to
`open_help_url()`-equivalent behavior when MarkdownUtils itself isn't
usable.

This is a genuinely different shape from every pattern above, not
just a smaller version of the same one, in three specific ways:

- **The hidden-state check is against a different id.**
  `resolve_markdown_dash_opener()` checks whether *Markdown Dash* is
  hidden. An addon importing MarkdownUtils directly never touches
  Markdown Dash at all, so that check tells it nothing -- it needs its
  own check, against MarkdownUtils' own registered id, since the two
  addons can be independently activated/deactivated:

  ```python
  def markdown_utils_usable() -> bool:
      """Whether MarkdownUtils is both importable and not deactivated
      via Plugin Manager -- see this section's own note on why
      "importable" and "not hidden" are different questions here too,
      exactly as they are for resolve_markdown_dash_opener() above."""
      try:
          import MarkdownUtils  # noqa: F401  (import success is the check)
      except ImportError:
          return False
      try:
          from gramps.gen.plug import PluginRegister
          from gramps.gui.pluginmanager import GuiPluginManager

          hidden = GuiPluginManager.get_instance().get_hidden_plugin_ids()
          return "MarkdownUtils" not in hidden
      except Exception:  # pylint: disable=broad-except
          return True  # can't confirm hidden state; don't disable a working import over it
  ```

  Checked live on every call, not cached at import time, for the same
  reason `resolve_markdown_dash_opener()` is: a user can toggle
  MarkdownUtils' active state in Plugin Manager mid-session, and that
  needs to take effect immediately, not after a restart.

- **None of the Windows-menu handling comes for free.** The whole
  point of `open_markdown_file()`'s own `ManagedWindow` wrapping (see
  above) is that every *caller* of it gets Windows-menu presence
  without doing anything themselves. An addon rendering with
  MarkdownUtils directly is building its own popup from scratch, so it
  needs its *own* `ManagedWindow` subclass, its own distinct
  `build_window_key()`/`build_menu_names()` (a second window sharing
  the *calling* window's own key/instance will compete for one menu
  slot rather than each getting its own -- confirmed live), and its
  own `Gdk.WindowTypeHint.NORMAL` fix (see this doc's own note on that,
  above) -- none of it inherited from anywhere.
- **The title has to come from the document itself, not be invented.**
  `open_markdown_file()` already titles its reader from the opened
  file's own first heading. A hand-built popup needs to do the same
  itself, deliberately -- extracting the document's own first `#`
  heading and using it verbatim, with nothing prepended or appended --
  rather than hardcoding a title string, which quietly limits what the
  README's own author can put there.

If the host addon might later want the fuller reader experience,
structure the fallback as a real cascade rather than an either/or:
prefer `open_markdown_file()` when Markdown Dash is genuinely usable
(registered, not hidden, loadable, has the expected function -- the
four-question check `resolve_markdown_dash_opener()` already does),
fall back to a MarkdownUtils-direct popup when only that is usable,
and fall back to `open_help_url()` only when neither is. `add_help_button()`
above doesn't do this today -- it only ever tries Markdown Dash, then
`open_help_url()` -- so a host wanting the three-way cascade needs to
write that routing itself, following `cb_show_help()`'s own shape as
the starting point.

## Usage

```python
from help_doc_button import add_help_button
from gramps.gen.plug import PluginRegister

my_pdata = PluginRegister.get_instance().get_plugin("my_plugin_id")
add_help_button(self.window.get_action_area(), self.uistate, my_pdata)
```

Works the same way for a gramplet's own toolbar box, or a report/tool wizard's action-area box -- pass whichever `Gtk.Box` is appropriate as `container`.

<a id="integration-checklist"></a>
## Integration checklist (for whoever/whatever merges this into a host module)

This snippet is meant to be inlined into an existing gramplet/report/tool file, not kept as a standalone importable module. Do the following, in order, before considering the merge complete:

1. **Check for name collisions before copying anything in.** The host module very likely already defines a translator (`_`), a module logger (`LOG`), and possibly its own icon/id constants. Search the host file for `_ =`, `LOG = logging.getLogger`, `_HELP_ICON_NAME`, and `_MARKDOWNDASH_ID` first. If the host already has a translator and logger, delete this snippet's copies and use the host's; do not leave two loggers or two `_` bindings in the same file. If the host has no translator/logger yet, keep this snippet's versions but verify they don't shadow anything the host adds later in the same file.
2. **Rename on collision, don't silently duplicate.** If the host module already uses the name `resolve_help_icon`, `find_local_readme`, `resolve_markdown_dash_opener`, `open_help_url`, `cb_show_help`, or `add_help_button` for something unrelated, rename this snippet's function (and its call site) rather than overwriting or duplicating a definition.
3. **Decide where the parameter docs live.** These functions' docstrings are one-liners pointing at `HelpDocButton.md#<name>-parameters`. If `HelpDocButton.md` is being kept alongside the host file, leave the docstrings as-is. If it is not travelling with the code (e.g. a single-file plugin submission), copy the relevant parameter documentation from the "Function parameter reference" section below back into each function's docstring as proper Sphinx `:param:`/`:returns:` entries, per the host project's normal docstring convention -- do not leave a dangling reference to a file that won't exist alongside the merged code.
4. **Find or create the container `Gtk.Box`.** `add_help_button()` needs a `Gtk.Box` to pack into. For a `ManagedWindow`-based Tool/Report dialog this is usually `self.window.get_action_area()` (a `Gtk.Dialog`'s own button row). For a gramplet, it's whatever toolbar/button box the gramplet already builds (or a new one, added to the gramplet's main container, if it doesn't have one yet). Identify which of these applies to the specific host module before calling `add_help_button()`, and pass that box, not a placeholder.
5. **Confirm the host module has `uistate` and its own `pdata` available at the call site.** `add_help_button()` needs both: `uistate` for window parenting (usually `self.uistate` on a `ManagedWindow`/gramplet), and the host's own `PluginData` (usually obtained once via `PluginRegister.get_instance().get_plugin(<this plugin's own registered id>)`, not Markdown Dash's id -- that lookup is internal to `resolve_markdown_dash_opener()`).
6. **Re-run Black and Pylint on the merged file**, not just on the snippet in isolation -- merging can reintroduce the same import-grouping, line-length, or duplicate-definition issues this snippet was already checked against on its own.
7. **Carry the AI-generated-code disclosure into the merge commit message, regardless of whether this `.md` travels with the merged file.** Per step 3, `HelpDocButton.md` may not survive the merge -- but the tool/provider/version, prompts, and constraint documents recorded in its "AI-generated-code disclosure" section above are still required by Gramps' AI-generated-code policy at the point that actually matters: the commit that introduces this code into the host module. Copy that section's content (or a summary of it) into the commit message's `Generated-by:` tag rather than letting it exist only in a document that gets dropped.
8. **Add tests for the merge's pure logic**, per AGENTS.md's per-flow testing requirement, which this snippet's own "Verification" note (Black/Pylint only) does not satisfy on its own. `find_local_readme()` and the URL-vs-title branch of `open_help_url()` do not need a running GTK/Gramps environment to test -- `gi.repository` and `gramps.gui.dialog.OkDialog` can be stubbed/mocked so those two functions' branches (present/missing README; `http(s)://` URL vs. bare title, including a title needing percent-encoding) are exercised directly. Name the test file `<host_module>_test.py` in a `test/` subdirectory alongside the host module, per AGENTS.md.
9. **Confirm `open_markdown_file()`'s own `Gtk.Dialog`, in `MarkdownDash.py`, sets `set_type_hint(Gdk.WindowTypeHint.NORMAL)`.** See this doc's own note above, under the `ManagedWindow`/Windows-menu bullet: a plain `Gtk.Dialog` defaults to the `DIALOG` type hint, which breaks correct Windows-menu behavior on many window managers independently of whether the window is otherwise a proper `ManagedWindow`. This has not been checked one way or the other as of this writing. If it's missing there, add it, once, in `MarkdownDash.py` itself -- every host module using this snippet inherits the fix for free the same way it already inherits the `ManagedWindow` wrapping itself, rather than each host needing to notice and patch around the gap independently.

## Function parameter reference

<a id="constants"></a>
### Module constants

`_MARKDOWNDASH_ID` is the registered id of the Markdown Dash gramplet (see `MarkdownDash.gpr.py`). `_HELP_ICON_NAME` is `"help-browser"`, resolved through the active `Gtk.IconTheme` by name rather than a hardcoded path -- see "Why resolve the icon by name" above.

<a id="resolve_help_icon-parameters"></a>
### `resolve_help_icon(size=48)`

Returns a `Gtk.Image` showing the color `"help-browser"` icon at `size`. **size** -- desired pixel size (square). **Returns** a `Gtk.Image` showing the resolved icon.

<a id="find_local_readme-parameters"></a>
### `find_local_readme(pdata)`

Returns the path to `pdata`'s own `README.md`, or `None`. **pdata** -- the plugin's `PluginData`; `None` is tolerated so a `PluginRegister.get_plugin(pid)` result can be passed straight through without an extra caller-side check. **Returns** an absolute path if the plugin's own folder has a `README.md`, else `None`.

<a id="resolve_markdown_dash_opener-parameters"></a>
### `resolve_markdown_dash_opener()`

Returns Markdown Dash's `open_markdown_file()`, or `None`. Verifies the gramplet is not user-hidden, is registered, is loadable, and still exposes the expected API -- each a distinct failure mode (deactivated / not installed / broken install / outdated install), collapsed here to a single `None` since every caller does the same thing either way: fall back to `open_help_url`. Takes no parameters. **Returns** the `open_markdown_file` callable, or `None` if Markdown Dash has been deactivated via Plugin Manager, is not registered, fails to load, or does not (yet) provide that function.

<a id="open_help_url-parameters"></a>
### `open_help_url(pdata, parent)`

Opens `pdata`'s registered `help_url` in the desktop's default browser; a bare wiki page title is resolved against gramps-project.org, a full URL is used as-is. **pdata** -- the `PluginData` whose `help_url` should be opened. **parent** -- transient parent for the "nothing to show" notice.

<a id="cb_show_help-parameters"></a>
### `cb_show_help(_button, uistate, pdata)`

Shows the closest documentation available for `pdata`: local `README.md` via Markdown Dash when available, else `open_help_url`. **_button** -- the clicked `Gtk.Button` (unused). **uistate** -- the Gramps `UiState`, used for window parenting. **pdata** -- the calling plugin's own `PluginData`.

<a id="add_help_button-parameters"></a>
### `add_help_button(container, uistate, pdata, *, size=48)`

Packs a color "Help" button (icon plus a "Help" text label, `always_show_image` forced on -- see the gotchas above) into `container` for a gramplet/report/tool. **container** -- the `Gtk.Box` to pack the button into: a report/tool dialog's action-area box, or a gramplet's toolbar box. **uistate** -- the Gramps `UiState`, passed through to Markdown Dash. **pdata** -- the calling plugin's own `PluginData`, e.g. `PluginRegister.get_instance().get_plugin(my_id)`. **size** -- icon pixel size (square); defaults to `48` for a dialog's action area, but pass something smaller (e.g. `16`) when packing into a compact gramplet button row. **Returns** the created, already-packed `Gtk.Button`.
