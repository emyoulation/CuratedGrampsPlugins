# BreadcrumbFormatter.py — API documentation
**Version 0.1.0** — Development Release  
**For Gramps 5.2.x** desktop genealogy software  
[**BreadcrumbFormatterAPI.md**](BreadcrumbFormatterAPI.md) | [**README.md**](README.md)

`BreadcrumbFormatter.py` is a standalone formatting module used by the Pedigree Breadcrumbs gramplet. It accepts an ordered list of pedigree entries (youngest to oldest) and returns plain‑text and "tagged" representations of a breadcrumb line and a generation list, suitable for conversion into Gramps `StyledText` objects or other rich‑text environments.   

## Design goals

The module is deliberately independent of Gramps imports: it uses only standard Python types and named‑tuples so that it can be tested and reused in isolation. All Gramps‑specific types like `StyledText` and `StyledTextTag` are handled in the calling gramplet, which maps the ranges and URLs supplied by this module into UI widgets and Notes.     

## Data types

### `PedigreeEntry`

```python
PedigreeEntry = namedtuple(
    "PedigreeEntry",
    ["handle", "family_handle", "gramps_id", "label",
     "given", "surname", "name_full", "birth_year", "death_year"],
)
```

Represents a single person in the pedigree.   

**Fields:**

- `handle` (`str`): Gramps internal person handle.
- `family_handle` (`str`): handle of the person's first parent family, or `""` if none.
- `gramps_id` (`str`): visible Gramps ID (e.g. `"I0042"`).
- `label` (`str`): generation marker — can be numeric (`"1"`, `"2"`, …), alphabetic (`"A"`, `"B"`, …), or any other string.
- `given` (`str`): given name(s), including any suffix (e.g. `"John, Jr."`).
- `surname` (`str`): primary surname.
- `name_full` (`str`): full name, normally using Gramps Name Display preferences.
- `birth_year` (`str`): 4‑digit birth year or `""`.
- `death_year` (`str`): 4‑digit death year or `""`.

**Important:** Entries must be supplied **youngest → oldest**; the module relies on this order when suppressing repeated surnames and computing link positions.

### `FormattedText`

```python
FormattedText = namedtuple(
    "FormattedText",
    ["plain", "sup_ranges", "link_ranges"],
)
```

Encapsulates a plain Unicode string plus styling information.   

**Fields:**

- `plain` (`str`): the complete text with no markup.
- `sup_ranges` (`list[tuple[int, int]]`): character spans `(start, end)` for superscript generation labels.
- `link_ranges` (`list[tuple[str, int, int]]`): items of `(url, start, end)` describing clickable ranges.

The caller can build one "superscript" tag from the union of all `sup_ranges`, and a separate "link" tag for each `(url, start, end)` entry.   

## Helper: life span

### `_life_span(entry)`

```python
def _life_span(entry) -> str:
    """Return 'YYYY–YYYY', 'YYYY–', '–YYYY', or '' for the entry."""
```

Computes a compact life‑span string from `entry.birth_year` and `entry.death_year`.   

- Returns `"YYYY–YYYY"` when both years are present.
- Returns `"YYYY–"` when only `birth_year` is present.
- Returns `"–YYYY"` when only `death_year` is present.
- Returns `""` when neither is present.

Used internally by the list formatters.   

## Plain‑text formatters

### `format_breadcrumb_plain(entries)`

```python
def format_breadcrumb_plain(entries: list[PedigreeEntry]) -> str:
    """
    Return the breadcrumb as a plain Unicode string.

    Format per token: "{given}{label}[ {SURNAME}]"
    Tokens separated by "; ".
    """
```

Generates a single‑line breadcrumb string.   

**Behavior:**

- Each person is rendered as `{given}{label}` with an optional `" SURNAME"`.
- **Surname suppression rule:** If a person's surname matches the previous entry's surname, it is omitted, **unless** the person is the last (oldest) entry.
- The last entry always shows its surname when non‑empty.
- Tokens are joined by `"; "` (semicolon plus space).

Returns `""` when `entries` is empty.   

### `format_list_plain(entries)`

```python
def format_list_plain(entries: list[PedigreeEntry]) -> str:
    """
    Return the generation list as a plain multi-line string.

    Each line: "label: Full Name YYYY–YYYY; GrampsID"
    """
```

Produces a multi‑line generation list.   

**Behavior:**

- For each entry: `label: name_full[ span]; gramps_id`
- If `_life_span(entry)` is non‑empty, appends a space and the span.
- Lines are joined with `"\n"`.

Returns `""` when `entries` is empty.   

## Tagged breadcrumb formatter

### `format_breadcrumb_tagged(entries)`

```python
def format_breadcrumb_tagged(entries: list[PedigreeEntry]) -> FormattedText:
    """
    Return breadcrumb FormattedText with superscript and Family link ranges.
    """
```

Creates `FormattedText` for the breadcrumb line.   

**Plain layout per entry:**

```
{given}{label}[ {SURNAME}]
```

**Styling:**

- **Superscript:** `label` characters → `sup_ranges`
- **Family links:** If `family_handle` non‑empty, link covers `{given}` only:
`gramps://Family/handle/{family_handle}`
- **Surname suppression:** Same as plain formatter.

Returns `FormattedText("", [], [])` when empty.   

## Tagged generation list formatter

### `format_list_tagged(entries)`

```python
def format_list_tagged(entries: list[PedigreeEntry]) -> FormattedText:
    """
    Return generation list FormattedText with superscript and Person link ranges.
    """
```

Creates `FormattedText` for the multi‑line list.   

**Plain layout per line:**

```
{label}: {Full Name}[ {YYYY–YYYY}]; {GrampsID}
```

**Styling:**

- **Superscript:** Each line's `label` → `sup_ranges`
- **Person links:** `GrampsID` → `gramps://Person/handle/{handle}`

Returns `FormattedText("", [], [])` when empty.   

## Combined helper

### `format_all(entries)`

```python
def format_all(entries: list[PedigreeEntry]) -> dict:
    """
    Return all four representations in a dict.

    Keys:
        "breadcrumb_plain"  : str
        "breadcrumb_tagged" : FormattedText
        "list_plain"        : str
        "list_tagged"       : FormattedText
    """
```

**Returns:**

```python
{
    "breadcrumb_plain": format_breadcrumb_plain(entries),
    "breadcrumb_tagged": format_breadcrumb_tagged(entries),
    "list_plain": format_list_plain(entries),
    "list_tagged": format_list_tagged(entries),
}
```

Primary entry point used by the gramplet.     

## Usage in Gramps gramplet

1. Build `PedigreeEntry` list (youngest→oldest) from path computation
2. Call `format_all(entries)`
3. **Display:** Use plain strings or Pango markup
4. **Notes:** Convert `*_tagged` → `StyledText`:

```python
# One tag for all superscripts
sup_tag = StyledTextTag("superscript", "", sup_ranges)
# One tag per link
link_tags = [StyledTextTag("link", url, [(start,end)]) for url,start,end in link_ranges]
styled = StyledText(plain, [sup_tag] + link_tags)
```


## Credits

**Concept/integration:** Brian McCullough      

**Code generation:**
`Generated-by: Claude Sonnet 4.6 (Anthropic) <https://claude.ai>`
`Prompts: Design a Gramps 5.2 gramplet showing a generation-numbered breadcrumb path between Proband, Progenitor, and optional Founder, with a companion formatting module, clickable Pango links opening EditPerson/EditFamily editors, and a context menu for clipboard copy and Note creation.`     

**This API doc:**
`Generated-by: Perplexity based on BreadcrumbFormatter.py source code.`
