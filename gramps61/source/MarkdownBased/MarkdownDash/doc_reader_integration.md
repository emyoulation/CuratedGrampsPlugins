# Integrating with the "Open documentation reader" pattern

This note documents three small, reusable snippets extracted from
`PluginManagerPlus.py` for detecting a plugin's `README.md` and opening it
in Markdown Dash's standalone viewer. It is written for addon authors who
want to reuse the same pattern, not as end-user documentation.

All snippets assume `self._preg` and `self._pmgr` have already been
obtained the standard Gramps way:

```python
self._pmgr = GuiPluginManager.get_instance()
self._preg = PluginRegister.get_instance()
```

## 1. Does the selected plugin have a `README.md`, and what is its path?

A plugin's on-disk folder is available as `pdata.fpath` once you have its
`PluginData` from the `PluginRegister`. Guard against `pdata` being `None`
and `fpath` being falsy (e.g. for a plugin whose files were not found on
disk) before touching the filesystem:

```python
pdata = self._preg.get_plugin(pid)
if pdata is None or not pdata.fpath:
    # Plugin not registered, or its folder is unknown.
    return

readme_path = os.path.join(pdata.fpath, "README.md")
if not os.path.isfile(readme_path):
    # No README.md alongside this plugin.
    return

# readme_path now points at a real README.md on disk.
```

This is the same check used to decide whether to draw the "has its own
README" indicator icon in the plugin list, and again when building the
info pane's right-click "Open documentation reader" menu item.

## 2. Confirming the plugins needed for "Open document reader" are registered

The feature depends on the Markdown Dash gramplet (`id="markdowndash"` in
`MarkdownDash.gpr.py`) being registered *and* loadable *and* exposing the
`open_markdown_file()` function. Check all three before relying on it —
each is a distinct failure mode with a distinct message:

```python
pdata = self._preg.get_plugin("markdowndash")
if pdata is None or not pdata.fpath:
    # Not registered. A rescan can help if the addon was just installed
    # or its files landed on disk slightly after Gramps' own startup
    # plugin scan ran (see PluginRegister rescan below).
    self.__rebuild_reg_list(rescan=True)
    pdata = self._preg.get_plugin("markdowndash")
if pdata is None or not pdata.fpath:
    # Still not found after a rescan: genuinely not installed/enabled.
    ...

mod = self._pmgr.load_plugin(pdata)
if not mod:
    # Registered, but the module failed to import/load.
    ...

open_markdown_file = getattr(mod, "open_markdown_file", None)
if open_markdown_file is None:
    # Loaded, but an older version without the expected API.
    ...
```

Only once all three checks pass is it safe to call `open_markdown_file()`.

## 3. Opening the document reader on a specific `.md` file

Once `open_markdown_file` has been resolved as above, call it with the
target path, the current `DbState`/`uistate`, a parent window, and a
display name for the file being shown:

```python
open_markdown_file(
    readme_path,
    self.uistate,
    parent=self.uistate.window,
    addon_name=addon_name,
)
```

Notes:

- Pass `self.uistate.window` (Gramps' own main window) as `parent`, not
  the calling dialog's own window, so closing the calling dialog does not
  also close the documentation window.
- `addon_name` is the plugin's translated `pdata.name`, used by Markdown
  Dash for its own locale-related wording; it is not required to be a
  plugin name specifically — any short descriptive label for the file
  being opened is appropriate.
- Capture `readme_path` and `addon_name` at the point the menu item (or
  equivalent trigger) is built, rather than re-deriving them from the
  current selection at click time, in case the selection changes between
  building the menu and the item being activated.
