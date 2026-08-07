# Plugin Manager 2 (prototype)

![Plugin Manager 2 screenshot](media/PluginMgr2_capture.png)


![AddRemoveTool](https://gramps-project.org/wiki/index.php/Special:FilePath/AddRemoveTagTool-GeneralOptionsDialog-51.png)

Plugin Manager 2 is a prototyping fork of **Plugin Manager plus**
(`PluginManagerPlus`), an enhanced replacement for Gramps' built-in
Help → Plugin Manager. It shows an installed/available addon's details
and a preview thumbnail above the plugin list, instead of the stock
manager's bare list-and-description layout.

This fork adds two things on top of the parent addon:

1. **Fault-tolerant addon-listing import** — a malformed or
   unrecognized line in the cached addon listing (`new_addons.txt`) no
   longer aborts the whole list or crashes a later lookup; it's skipped
   and logged instead.
2. **A local, all-columns wiki addon catalog** — the Gramps wiki's
   `Template:Addons5.2` table is parsed (fetching it once if not
   already bundled) and cached locally as JSON, preserving every column
   of the table, not just the ones currently displayed.

It is a **prototype**: functional, but not yet brought into full
compliance with the Gramps project's `AGENTS.md` coding conventions
(that pass is deferred until the prototype's behavior is settled).

## Status

Experimental. Known issue: the wiki-table thumbnail does not currently
appear in the upper-right preview panel as expected — under
investigation.

## Installation

Place these files together in Gramps' addon plugin directory (the same
folder Plugin Manager plus/other addons install into):

```
PluginManager2.py
PluginManager2.gpr.py
PluginManager2Load.py
README.md
media/
    Template_Addons5.2.txt
```

`media/Template_Addons5.2.txt` is optional at install time — if it's
missing, Plugin Manager 2 fetches it once from the Gramps wiki and
saves a local copy on first use. If your Gramps installation has no
network access, bundle the file yourself so the wiki catalog features
work offline.

Restart Gramps after installing. Plugin Manager 2 registers with
`load_on_reg = True`, so `PluginManager2Load.py` patches Gramps' Help →
Plugin Manager window to use Plugin Manager 2's enhanced version as
soon as the addon is loaded — no separate menu entry is added.

**Note:** Plugin Manager plus and Plugin Manager 2 both patch the same
Gramps attribute (`gramps.gui.viewmanager.PluginWindows.PluginStatus`).
If both are installed and enabled, whichever one loads last wins. Don't
run both at once.

## Using Plugin Manager 2

Open it via **Help → Plugin Manager**. The window is split into two
panes:

- **Top pane** — plugin details (left) and a preview thumbnail
  (right), for whichever plugin row is currently selected.
- **Bottom pane** — the plugin list itself, with filter checkboxes and
  action buttons (Deactivate/Reactivate, Install/Uninstall, Load).

The bottom-bar **Help** button toggles the top pane between:

- **Details** — plugin registration info (name, ID, version, type,
  authors, file paths, help link) rendered as Markdown.
- **README** — the selected plugin's own `README.md` (falling back to
  this addon's own `README_fallback.md` if it has none), alongside a
  screenshot if one is bundled.

Other controls:

- **Update** — re-fetches the addon listing from each repository
  enabled under Preferences → Addons.
- **Export Plugin List** — writes every known field for every
  registered and available plugin to `plugin_debug_export.json`, for
  troubleshooting.
- **Search** — filters the plugin list by name/description.

## What's different from Plugin Manager plus

### Fault-tolerant addon-listing import

`new_addons.txt` (the locally cached addon listing) is read one line
at a time. Each line is parsed as JSON first, then as a Python dict
literal (the historical format) if that fails, and is required to
contain the fields the dialog actually needs (`i`, `n`, `d`, `t`, `v`,
`z`). A line that's blank, unparsable by either method, not an
object/dict, or missing a required field is skipped and logged with
the reason — it no longer aborts the rest of the import or causes a
`KeyError` later when the list is displayed.

### Local wiki addon catalog

Plugin Manager plus already bundled a local copy of the Gramps wiki's
`Template:Addons5.2` table (the same table on the
[Third-party Addons](https://gramps-project.org/wiki/index.php/Third-party_Addons)
wiki page) to match installed/available plugins against extra
metadata such as a preview image and a documentation link. Plugin
Manager 2 extends this:

- If `media/Template_Addons5.2.txt` isn't already bundled, it's
  fetched once from
  `https://gramps-project.org/wiki/index.php?title=Template:Addons5.2&action=raw`
  and saved locally — after that, no network access is needed to use
  the catalog.
- Every column of the table (`Plugin / Documentation`, `Type`, `Image`,
  `Description`, `Use`, `Rating`, `Contact`, `Download`) is preserved
  verbatim for every row under a `raw_columns` key, in addition to the
  cleaned-up fields (`help_url`, `display_name`, `image_file`,
  `description`, `use`, `rating`, `contact`, `download_stem`) the UI
  currently uses. Nothing from the table is discarded even though not
  all of it is displayed yet.
- The parsed catalog is cached as JSON at
  [`media/addons_wiki_catalog.json`](media/addons_wiki_catalog.json),
  next to the raw wikitext, and is only re-parsed when the source
  `.txt` file is newer than the cache. Other tools/scripts can read
  this JSON file directly without going through Plugin Manager 2's
  code. A real sample generated from the bundled
  `Template_Addons5.2.txt` (104 addons, every column preserved) is
  included — open it in a text/JSON viewer to see the shape of the
  data; it's too large to render usefully inline here. It will be
  regenerated automatically if the bundled `.txt` table is ever
  updated.
- The matched entry's `Image` (via
  `https://gramps-project.org/wiki/Special:FilePath/<file>`) is meant
  to populate the upper-right preview thumbnail for both installed
  *and* available (not-yet-installed) plugins — previously this only
  worked for installed/built-in plugins, since available-only addons
  have no `PluginData` entry in the registry to hang the lookup off
  of. **This is the part currently not displaying as expected; see
  Status above.**

## Files

| File | Purpose |
|---|---|
| `PluginManager2.py` | Main dialog implementation (`PluginStatus` class). |
| `PluginManager2.gpr.py` | Gramps addon registration. |
| `PluginManager2Load.py` | `load_on_reg` hook; patches the built-in Plugin Manager. |
| `README.md` | This file. |
| `README_fallback.md` *(optional)* | Shown in README mode for a selected plugin that has no `README.md` of its own. |
| `media/PluginMgr2_capture.png` | Screenshot shown alongside this README (bundled; currently a placeholder — see Status). |
| `media/Template_Addons5.2.txt` | Local copy of the wiki addon table (bundled; re-fetched automatically only if absent). |
| `media/addons_wiki_catalog.json` | Parsed wiki catalog (bundled sample; regenerated automatically if the `.txt` table changes). |
| `media/wiki_cache/` | Downloaded wiki preview-image cache (generated automatically, not bundled). |
| `new_addons.txt` | Cached addon listing from enabled repositories (generated by "Update"). |
| `plugin_debug_export.json` | Output of "Export Plugin List" (generated on demand). |

## AI-assistance disclosure

Portions of this addon were generated with AI coding assistance
(Claude, various releases — see the `Generated-by:` / `Co-authored-by:`
headers in each source file for specifics per change), per the Gramps
project's
[AI-generated code guidelines](https://www.gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code).
This prototype has not yet been brought into compliance with
[AGENTS.md](https://github.com/gramps-project/gramps/blob/master/AGENTS.md)
formatting/typing/testing conventions — that pass is deferred until the
prototype's behavior is settled, per the project's understanding with
its maintainer.

## License

GPL-2.0-or-later, consistent with the rest of Gramps and its addons.
