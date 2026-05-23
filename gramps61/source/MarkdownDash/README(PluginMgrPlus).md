# Plugin Manager v2
![](media/PluginMgrV2.png)

Adds:
* Show Addons checkbox
* extends search to Authors fields
* adds diagnostic readout



## Installation via Addon Manager

1. Open Gramps → **Help** → **Plugin Manager** → **Install Addons...**
2. Under **Settings**, add this repository if not already listed:
   - Project name: **Emyoulation GitHub curated addons**
   - URL: `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/master/gramps52/`
3. Find **Markdown Dash** and click **Install**, then restart Gramps.
4. Add the **Markdown Dash** gramplet to your Dashboard.

---

## Markdown Syntax Reference

Each example shows the rendered result followed by raw Markdown in `[code]…[/code]`.

---

### Emphasis

**Bold** `[code]**Bold**[/code]`    
*Italic* `[code]*Italic*[/code]`    
***Bold-italic*** `[code]***Bold-italic***[/code]`    
~~Strikethrough~~ `[code]~~Strikethrough~~[/code]`    
`inline code` `[code]` `` `code` `` `[/code]`

---

### Headings

# Heading 1  `[code]# Heading 1[/code]`
## Heading 2  `[code]## Heading 2[/code]`
### Heading 3  `[code]### Heading 3[/code]`
#### Heading 4  `[code]#### Heading 4[/code]`

---

### Tables

GFM pipe tables with optional column alignment:

| Name | Type | Size | Notes |
|------|:----:|-----:|-------|
| `person`  | Object | 16 px | Left-aligned default |
| **family**   | Object | 22 px | *Bold cells work* |
| `gramps-geo` | View | 48 px | Full GTK name |
| [Gramps](https://gramps-project.org/) | Link | — | Links work too |

`[code]`
```
| Name | Type | Size | Notes |
|------|:----:|-----:|-------|
| `person` | Object | 16 px | Left-aligned default |
```
`[/code]`

Column alignment: `:---` left (default), `:---:` center, `---:` right.

---

### Links

[Gramps project](https://gramps-project.org/) `[code][label](url)[/code]`

[Load icon browser](icon-browser.md) — relative `.md` links open in the viewer

---

### Images

![Built with Claude](media/logo-claude-official.png) `[code]![alt](media/logo-claude-official.png)[/code]`

Alternate logo styles in `media/`: dark badge, light badge, pill, text-only.

Missing images become clickable placeholders: ![missing](no-such-file.png)

---

## Gramps Extensions
[August Dvorak](gramps:nav:people:I0001)
[August Dvorak](gramps:nav:relationships:I0001)
[edit:Person August Dvorak](gramps:edit:Person:I0001)
[nav:Person August Dvorak](gramps:nav:Person:I0001)
[nav:People August Dvorak](gramps:nav:People:I0001)

### Inline Theme Icons

`![](gramps:icon:<alias>)` at 16 px default, or `![](gramps:icon:<alias>:<size>)`.

| Object icons (22 px) | | | | | | | | | |
|---|---|---|---|---|---|---|---|---|---|
| ![](gramps:icon:person:22) | ![](gramps:icon:family:22) | ![](gramps:icon:event:22) | ![](gramps:icon:place:22) | ![](gramps:icon:source:22) | ![](gramps:icon:citation:22) | ![](gramps:icon:repository:22) | ![](gramps:icon:media:22) | ![](gramps:icon:note:22) | ![](gramps:icon:tag:22) |
| person | family | event | place | source | citation | repository | media | note | tag |

Dashboard at all sizes:
![](gramps:icon:dashboard:16) 16  ![](gramps:icon:dashboard:22) 22  ![](gramps:icon:dashboard:24) 24  ![](gramps:icon:dashboard:32) 32  ![](gramps:icon:dashboard:48) 48

See [icon-browser.md](icon-browser.md) for a complete visual inventory including SVG support tests.

---

### Gramps Object Links

Purple links that interact with your open database.

**Open editor:** `[label](gramps:edit:Person:I0001)` — opens the editor for that Gramps ID

**Navigate view:** `[label](gramps:nav:Person:I0001)` — switches view and sets active record

**Switch category:** `[label](gramps:view:geography)` — valid: `people`, `families`, `events`, `places`, `sources`, `citations`, `repositories`, `media`, `notes`, `geography`, `charts`, `dashboard`

Both `gramps:edit` and `gramps:nav` accept either a Gramps ID (`I0001`) or
`handle:<handle>` for an internal handle.

---

### Lists and Blockquotes

- Unordered `[code]- item[/code]`
  - Nested item

1. Ordered `[code]1. item[/code]`

> Blockquote `[code]> text[/code]`

---

### Code Blocks

```python
def hello(name):
    return f"Hello, {name}!"
```

---

## Compatibility

Gramps 5.2 / Python 3.11+ / GTK 3. No WebKit, no `markdown` package.
SVG icons require `librsvg2` (standard on most Linux desktops).

## Credits

Developed with [Claude](https://claude.ai) (Anthropic) by Brian McCullough.
License: GPL v2 or later.
