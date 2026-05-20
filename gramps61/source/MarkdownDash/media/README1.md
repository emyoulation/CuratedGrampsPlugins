Browse to  [Welcome.md (english)](Welcome.en.md) | [icon-browser.md](icon-browser.md) | [README.md](../README.md) | [README1.md](README1.md) | [GrampsGlossary.md](GrampsGlossary.md).

# Markdown Dash

A [Gramps](https://gramps-project.org/) Dashboard gramplet for viewing Markdown
(`.md`) files with proper formatting — **no WebKit, no third-party packages**.

![Built with Claude](media/logo-claude-official.png)

Click the **folder icon** (bottom-right) to open any `.md` file.
Browse to [icon-browser.md](icon-browser.md) for a full icon inventory.

---

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
|-------|:-------:|----:|-----------------------|
| `person`  | Object | 16 px | Left-aligned default |
| **family**   | Object | 22 px | *Bold cells work* |
| `gramps-geo` | View | 48 px | Full GTK name |
| [Gramps](https://gramps-project.org/) | Link | — | Links work too |

`[code]`
```
| Name | Type | Size | Notes |
|-------|:-------:|----:|-----------------------|
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

[gramps:nav:people:I0001](gramps:nav:people:I0001)
[gramps:nav:relationships:I0001](gramps:nav:relationships:I0001)
[gramps:nav:Person:I0001](gramps:nav:Person:I0001)

## Navigation link samples

### gramps:nav — switch view and select object by Gramps ID
[Margaret Mullen](gramps:nav:Person:I0001)
[Moss/Jackson family](gramps:nav:Family:F0002)
[Brooklyn GEO5110302](gramps:nav:Place:GEO5110302)
[Birth of Morton Moss](gramps:nav:Event:E0003)
[Numbering](gramps:nav:Source:S0001)

### gramps:nav — same but by internal handle (hex string)
[I0001 f744bb99da77baf8c5178dbfa90](gramps:nav:Person:handle:f744bb99da77baf8c5178dbfa90) 
[F0002 f744bb9b1da7dcb43d46f48817c](gramps:nav:Family:handle:f744bb9b1da7dcb43d46f48817c)
[GEO5110302 10217f6afae8332029891d71cf44](gramps:nav:Place:handle:10217f6afae8332029891d71cf44)

### gramps:edit — open the object editor directly
[Edit I0001 Margaret Mullen](gramps:edit:Person:I0001)
[Edit F0002  Moss/Jackson](gramps:edit:Family:F0002)
[Edit GEO5110302 Brooklyn](gramps:edit:Place:GEO5110302)
[Edit S0001 Numbering](gramps:edit:Source:S0001)
[I0001 f744bb99da77baf8c5178dbfa90](gramps:edit:Person:handle:f744bb99da77baf8c5178dbfa90) 
[F0002 f744bb9b1da7dcb43d46f48817c](gramps:edit:Family:handle:f744bb9b1da7dcb43d46f48817c)
[GEO5110302 10217f6afae8332029891d71cf44](gramps:edit:Place:handle:10217f6afae8332029891d71cf44)
[S0001 f744d9807b93a40c2be91ba6586](gramps:edit:Source:handle:f744d9807b93a40c2be91ba6586)

### gramps:view — switch to a named view category (no object)
[Go to People view](gramps:view:people)
[Go to Families view](gramps:view:families)
[Go to Places view](gramps:view:places)
[Go to Dashboard](gramps:view:dashboard)
[Go to Geography](gramps:view:geography)


### Inline Theme Icons

`![](gramps:icon:<alias>)` at 16 px default, or `![](gramps:icon:<alias>:<size>)`.

Object icons (22 px) 
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
