# Enhancement Request: Extend `register()` to support `maintainers` and `maintainers_email` parameters

**Component:** `gramps/gen/plug/_pluginreg.py` — `PluginData` class and `register()` function  
**Type:** Feature enhancement (non-breaking, backwards-compatible)  
**Priority:** Low  
**Affects:** All plugin types (`REPORT`, `TOOL`, `VIEW`, `GRAMPLET`, `GENERAL`, etc.)

---

## Problem Statement

The Gramps `register()` function currently recognises `authors` and `authors_email`
as first-class parameters, storing them on the `PluginData` object where other code
can read them programmatically. There is no equivalent for `maintainers` and
`maintainers_email`.

Addon authors who wish to distinguish the **original author** of a plugin from its
**current maintainer** (a common scenario for adopted or community-continued addons)
have no standard way to do so. Any `maintainers` key passed to `register()` today
is silently ignored by `PluginData.__init__` and is not stored anywhere.

Workarounds (parsing `.gpr.py` source text at runtime) are fragile: they break on
conditional registration blocks, version guards, multi-line values, and any syntax
the simple parser does not anticipate.

---

## Proposed Change

### 1. `PluginData` class — add two new attributes

In `_pluginreg.py`, inside `PluginData.__init__`, add:

```python
self.maintainers       = []   # list[str] — names of current maintainers
self.maintainers_email = []   # list[str] — contact addresses for maintainers
```

Apply the same validation logic already used for `authors` and `authors_email`:
- Value must be a `list` of `str`.
- An empty list `[]` is the default (field is optional).
- If a non-list or non-str-element value is supplied, raise or warn the same way
  `authors` validation does today.

### 2. `register()` / `PluginData` attribute setter — accept the new keys

In the block where `register()` keyword arguments are mapped to `PluginData`
attributes (the `setattr`/`_set_*` pattern already used for `authors`), add
handling for `maintainers` and `maintainers_email` using identical logic to the
existing `authors` / `authors_email` handling.

### 3. No other files require changes

`PTYPE_STR`, plugin-type constants, the addon listing format (`addons-en.json`),
and all existing callers are unaffected. The new fields are purely additive.

---

## Expected `.gpr.py` usage after this change

```python
register(
    TOOL,
    id    = "MyAddon",
    name  = _("My Addon"),
    ...
    authors        = ["Alice Original"],
    authors_email  = ["alice@example.com"],
    maintainers        = ["Bob Maintainer"],        # NEW
    maintainers_email  = ["bob@example.com"],       # NEW
)
```

---

## Acceptance Criteria

1. `PluginData` instances have `.maintainers` (list) and `.maintainers_email`
   (list) attributes initialised to `[]` by default.
2. When `maintainers=["Name"]` or `maintainers_email=["addr"]` is passed to
   `register()`, the values are stored on the resulting `PluginData` object and
   readable via those attributes.
3. Existing `.gpr.py` files that do **not** include these keys continue to
   register without error or warning.
4. The Plugin Manager UI can display maintainer information by reading
   `pdata.maintainers` and `pdata.maintainers_email` without parsing source files.
5. No existing tests fail.
