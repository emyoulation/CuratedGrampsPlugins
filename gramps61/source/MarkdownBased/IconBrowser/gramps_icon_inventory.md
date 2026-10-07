# Gramps Icon Theme Inventory

Source: [`gramps-project/gramps`](https://github.com/gramps-project/gramps), `master` branch
(cloned locally at commit time; icons live under `gramps/images/hicolor/`, following the
freedesktop.org icon-theme spec).

## How these icons get loaded

`gramps/gui/grampsgui.py` registers the search path once, at application start:

```python
theme = Gtk.IconTheme.get_default()
theme.append_search_path(IMAGE_DIR)
```

`IMAGE_DIR` (from `gramps.gen.const`) points at `gramps/images/`, which contains a
`hicolor/` theme directory laid out as `hicolor/<size>/<context>/<icon-name>.<ext>`
(`scalable` SVGs plus `16x16`, `22x22`, `24x24`, `48x48`, `128x128`, `256x256` PNG
fallbacks, under `actions/`, `apps/`, `mimetypes/`, and `source/`). Once registered,
any Gramps code can request an icon purely **by name** — e.g.
`Gtk.Image.new_from_icon_name("gramps-person", Gtk.IconSize.BUTTON)` — and GTK resolves
it to the right file/size automatically. This is distinct from `gui/dialog.py`'s
`ICON`, which is a single hard-coded `Pixbuf` loaded directly from `images/gramps.png`
for use as the app/window icon, not looked up through the icon theme.

Two additional call sites feed icon names into the theme from plugin/view registration
rather than a hardcoded Python string:
- `stock_icon = "..."` fields in `.gpr.py` plugin registration files (views, gramplets,
  reports) — 13 distinct names found across 17 `.gpr.py` files.
- Direct `Gtk.Image.new_from_icon_name("gramps-<name>", ...)` / dialog-icon calls
  scattered through `gramps/gui/*.py`.

## Forcing the color variant over the symbolic fallback

Many icons in the theme cascade above — and any add-on icon shipped the same
way — actually exist as **two** related assets: a full-color one
(`gramps-person`) and a flat, monochrome "symbolic" one
(`gramps-person-symbolic`), the latter intended for chrome like header bars
that GTK wants to auto-recolor for light/dark mode. This is a real gotcha:

- `Gtk.Image.new_from_icon_name("gramps-person", size)` with default lookup
  flags does **not** guarantee the color version. Depending on the active
  icon theme and requested pixel size, GTK's `GENERIC_FALLBACK` behavior is
  allowed to substitute across style variants when the exact one it wants
  isn't available at that size — so the same call can silently return the
  symbolic asset instead, or vice-versa.
- There is no single `Gtk.IconLookupFlags` value that means "color only,
  never symbolic." The lookup order has to be controlled explicitly by which
  name string is tried first, and — critically — the result has to be
  **verified**, via `Gtk.IconInfo.is_symbolic()`, rather than trusting the
  name that was requested.

This surfaced in practice while building two Gramps add-ons that render
inline icons inside Markdown text (`MarkdownUtils.py` / `MarkdownDash.py`):
inline documentation and dashboard icons needed to render predictably in
full color regardless of size, while still degrading gracefully if a given
icon genuinely only ships a symbolic asset. Their shared resolver,
`resolve_icon_pixbuf()`, takes an `icon_style` parameter (`"auto"` / `"color"`
/ `"symbolic"`) and builds a per-call name-preference list:

- `icon_style="color"` → try `[name, name + "-symbolic"]` — color first,
  symbolic only as a last resort if no color asset exists anywhere in the
  cascade for that icon.
- `icon_style="symbolic"` → the reverse order.
- `icon_style="auto"` → picks one style by icon size (symbolic ≤32px, color
  above that) and does **not** cross-fall-back, matching older fixed
  behavior.

Each candidate name is looked up via `Gtk.IconTheme.lookup_icon()` with
`GENERIC_FALLBACK | USE_BUILTIN | FORCE_SIZE`, and — only when a
`Gtk.StyleContext` has been supplied and `info.is_symbolic()` confirms GTK
actually resolved a *symbolic* asset — the pixbuf is recolored via
`load_symbolic_for_context()` to match the active foreground/background so it
isn't invisible in dark mode. A genuine color hit is returned as-is, never
recolored or second-guessed.

### Minimal GTK Python example: force color, add a tooltip

```python
def make_color_icon_image(
    icon_name: str,
    tooltip: str,
    size: int = 24,
) -> Gtk.Image:
    """Return a Gtk.Image showing the full-color variant of *icon_name*.

    Tries the plain icon name first (the color/full-art asset) and only
    falls back to the ``-symbolic`` variant if no color asset exists
    anywhere in the active icon-theme cascade for this icon. This mirrors
    ``MarkdownUtils.resolve_icon_pixbuf(..., icon_style="color")``.

    :param icon_name: GTK or Gramps theme icon name, without the
        ``-symbolic`` suffix (e.g. ``"gramps-person"``).
    :param tooltip:   Tooltip text to attach to the returned widget.
    :param size:      Desired pixel size (square).
    :returns: A :class:`Gtk.Image` with its tooltip set, showing the
        color icon wherever the theme provides one.
    """
    theme = Gtk.IconTheme.get_default()
    flags = (
        Gtk.IconLookupFlags.GENERIC_FALLBACK
        | Gtk.IconLookupFlags.USE_BUILTIN
        | Gtk.IconLookupFlags.FORCE_SIZE
    )

    # Color name first, symbolic only as a last-resort fallback.
    for candidate in (icon_name, f"{icon_name}-symbolic"):
        info = theme.lookup_icon(candidate, size, flags)
        if info is not None:
            break
    else:
        info = None

    image = Gtk.Image()
    if info is not None:
        pixbuf = info.load_icon()
        image.set_from_pixbuf(pixbuf)
    else:
        # Nothing in the cascade at all -- last-ditch generic fallback.
        image.set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)

    image.set_tooltip_text(tooltip)
    return image


# Usage, e.g. inside a gramplet or editor toolbar:
person_icon = make_color_icon_image("gramps-person", _("Person"), size=32)
```

Two things worth noting for anyone adapting this in real Gramps code:

- `Gtk.Image.set_tooltip_text()` only shows a tooltip if the image itself can
  receive pointer/focus events, which it usually can't inside a
  `Gtk.Button`. There, call `button.set_tooltip_text(...)` on the button
  after `button.set_image(image)`, the same pattern `MarkdownDash.py`'s
  footer buttons use (`self._edit_btn.set_tooltip_text(...)`, etc.).
- To react correctly to a live dark/light theme switch (e.g. via the Gramps
  Themes add-on), pass a `Gtk.StyleContext` through and only recolor when
  `info.is_symbolic()` is `True` — never recolor a genuine color hit. That's
  the one behavior `resolve_icon_pixbuf()` adds beyond this minimal example.

## Full inventory (76 icons)

|Icon|icon name|icon path|
|---|---|---|
|![](gramps:icon:FS-BLA-16:48)| FS-BLA-16 |`gramps/images/hicolor/16x16/actions/FS-BLA-16.png`|
|![](gramps:icon:FS-G-16:48)| FS-G-16 |`gramps/images/hicolor/16x16/actions/FS-G-16.png`|
|![](gramps:icon:add-parent-existing-family:48)| add-parent-existing-family |`gramps/images/hicolor/scalable/actions/add-parent-existing-family.svg`|
|![](gramps:icon:application-x-gedcom:48)| application-x-gedcom |`gramps/images/hicolor/scalable/mimetypes/application-x-gedcom.svg`|
|![](gramps:icon:application-x-geneweb:48)| application-x-geneweb |`gramps/images/hicolor/scalable/mimetypes/application-x-geneweb.svg`|
|![](gramps:icon:application-x-gramps:48)| application-x-gramps |`gramps/images/hicolor/scalable/mimetypes/application-x-gramps.svg`|
|![](gramps:icon:application-x-gramps-package:48)| application-x-gramps-package |`gramps/images/hicolor/scalable/mimetypes/application-x-gramps-package.svg`|
|![](gramps:icon:application-x-gramps-xml:48)| application-x-gramps-xml |`gramps/images/hicolor/scalable/mimetypes/application-x-gramps-xml.svg`|
|![](gramps:icon:format-text-subscript-symbolic:48)| format-text-subscript-symbolic |`gramps/images/hicolor/scalable/actions/format-text-subscript-symbolic.svg`|
|![](gramps:icon:format-text-superscript-symbolic:48)| format-text-superscript-symbolic |`gramps/images/hicolor/scalable/actions/format-text-superscript-symbolic.svg`|
|![](gramps:icon:geo-fixed-zoom:48)| geo-fixed-zoom |`gramps/images/hicolor/scalable/actions/geo-fixed-zoom.svg`|
|![](gramps:icon:geo-free-zoom:48)| geo-free-zoom |`gramps/images/hicolor/scalable/actions/geo-free-zoom.svg`|
|![](gramps:icon:geo-place-add:48)| geo-place-add |`gramps/images/hicolor/scalable/actions/geo-place-add.svg`|
|![](gramps:icon:geo-place-link:48)| geo-place-link |`gramps/images/hicolor/scalable/actions/geo-place-link.svg`|
|![](gramps:icon:geo-show-event:48)| geo-show-event |`gramps/images/hicolor/scalable/actions/geo-show-event.svg`|
|![](gramps:icon:geo-show-family:48)| geo-show-family |`gramps/images/hicolor/scalable/actions/geo-show-family.svg`|
|![](gramps:icon:geo-show-family-down:48)| geo-show-family-down |`gramps/images/hicolor/scalable/actions/geo-show-family-down.svg`|
|![](gramps:icon:geo-show-family-up:48)| geo-show-family-up |`gramps/images/hicolor/scalable/actions/geo-show-family-up.svg`|
|![](gramps:icon:geo-show-person:48)| geo-show-person |`gramps/images/hicolor/scalable/actions/geo-show-person.svg`|
|![](gramps:icon:geo-show-place:48)| geo-show-place |`gramps/images/hicolor/scalable/actions/geo-show-place.svg`|
|![](gramps:icon:gramps-addon:48)| gramps-addon |`gramps/images/hicolor/scalable/actions/gramps-addon.svg`|
|![](gramps:icon:gramps-address:48)| gramps-address |`gramps/images/hicolor/scalable/actions/gramps-address.svg`|
|![](gramps:icon:gramps-attribute:48)| gramps-attribute |`gramps/images/hicolor/scalable/actions/gramps-attribute.svg`|
|![](gramps:icon:gramps-bookmark:48)| gramps-bookmark |`gramps/images/hicolor/scalable/actions/gramps-bookmark.svg`|
|![](gramps:icon:gramps-bookmark-delete:48)| gramps-bookmark-delete |`gramps/images/hicolor/scalable/actions/gramps-bookmark-delete.svg`|
|![](gramps:icon:gramps-bookmark-edit:48)| gramps-bookmark-edit |`gramps/images/hicolor/scalable/actions/gramps-bookmark-edit.svg`|
|![](gramps:icon:gramps-bookmark-new:48)| gramps-bookmark-new |`gramps/images/hicolor/scalable/actions/gramps-bookmark-new.svg`|
|![](gramps:icon:gramps-citation:48)| gramps-citation |`gramps/images/hicolor/scalable/actions/gramps-citation.svg`|
|![](gramps:icon:gramps-config:48)| gramps-config |`gramps/images/hicolor/scalable/actions/gramps-config.svg`|
|![](gramps:icon:gramps-date:48)| gramps-date |`gramps/images/hicolor/scalable/actions/gramps-date.svg`|
|![](gramps:icon:gramps-date-edit:48)| gramps-date-edit |`gramps/images/hicolor/scalable/actions/gramps-date-edit.svg`|
|![](gramps:icon:gramps-event:48)| gramps-event |`gramps/images/hicolor/scalable/actions/gramps-event.svg`|
|![](gramps:icon:gramps-family:48)| gramps-family |`gramps/images/hicolor/scalable/actions/gramps-family.svg`|
|![](gramps:icon:gramps-fanchart:48)| gramps-fanchart |`gramps/images/hicolor/scalable/actions/gramps-fanchart.svg`|
|![](gramps:icon:gramps-fanchart2way:48)| gramps-fanchart2way |`gramps/images/hicolor/scalable/actions/gramps-fanchart2way.svg`|
|![](gramps:icon:gramps-fanchartdesc:48)| gramps-fanchartdesc |`gramps/images/hicolor/scalable/actions/gramps-fanchartdesc.svg`|
|![](gramps:icon:gramps-font:48)| gramps-font |`gramps/images/hicolor/scalable/actions/gramps-font.svg`|
|![](gramps:icon:gramps-font-bgcolor:48)| gramps-font-bgcolor |`gramps/images/hicolor/scalable/actions/gramps-font-bgcolor.svg`|
|![](gramps:icon:gramps-font-color:48)| gramps-font-color |`gramps/images/hicolor/scalable/actions/gramps-font-color.svg`|
|![](gramps:icon:gramps-geo:48)| gramps-geo |`gramps/images/hicolor/scalable/actions/gramps-geo.svg`|
|![](gramps:icon:gramps-geo-altmap:48)| gramps-geo-altmap |`gramps/images/hicolor/scalable/actions/gramps-geo-altmap.svg`|
|![](gramps:icon:gramps-geo-birth:48)| gramps-geo-birth |`gramps/images/hicolor/scalable/actions/gramps-geo-birth.svg`|
|![](gramps:icon:gramps-geo-death:48)| gramps-geo-death |`gramps/images/hicolor/scalable/actions/gramps-geo-death.svg`|
|![](gramps:icon:gramps-geo-mainmap:48)| gramps-geo-mainmap |`gramps/images/hicolor/scalable/actions/gramps-geo-mainmap.svg`|
|![](gramps:icon:gramps-geo-marriage:48)| gramps-geo-marriage |`gramps/images/hicolor/scalable/actions/gramps-geo-marriage.svg`|
|![](gramps:icon:gramps-gramplet:48)| gramps-gramplet |`gramps/images/hicolor/scalable/actions/gramps-gramplet.svg`|
|![](gramps:icon:gramps-lock:48)| gramps-lock |`gramps/images/hicolor/scalable/actions/gramps-lock.svg`|
|![](gramps:icon:gramps-media:48)| gramps-media |`gramps/images/hicolor/scalable/actions/gramps-media.svg`|
|![](gramps:icon:gramps-merge:48)| gramps-merge |`gramps/images/hicolor/scalable/actions/gramps-merge.svg`|
|![](gramps:icon:gramps-notes:48)| gramps-notes |`gramps/images/hicolor/scalable/actions/gramps-notes.svg`|
|![](gramps:icon:gramps-parents:48)| gramps-parents |`gramps/images/hicolor/scalable/actions/gramps-parents.svg`|
|![](gramps:icon:gramps-parents-add:48)| gramps-parents-add |`gramps/images/hicolor/scalable/actions/gramps-parents-add.svg`|
|![](gramps:icon:gramps-parents-open:48)| gramps-parents-open |`gramps/images/hicolor/scalable/actions/gramps-parents-open.svg`|
|![](gramps:icon:gramps-pedigree:48)| gramps-pedigree |`gramps/images/hicolor/scalable/actions/gramps-pedigree.svg`|
|![](gramps:icon:gramps-person:48)| gramps-person |`gramps/images/hicolor/scalable/actions/gramps-person.svg`|
|![](gramps:icon:gramps-place:48)| gramps-place |`gramps/images/hicolor/scalable/actions/gramps-place.svg`|
|![](gramps:icon:gramps-preferences:48)| gramps-preferences |`gramps/images/hicolor/scalable/actions/gramps-preferences.svg`|
|![](gramps:icon:gramps-relation:48)| gramps-relation |`gramps/images/hicolor/scalable/actions/gramps-relation.svg`|
|![](gramps:icon:gramps-reports:48)| gramps-reports |`gramps/images/hicolor/scalable/actions/gramps-reports.svg`|
|![](gramps:icon:gramps-repository:48)| gramps-repository |`gramps/images/hicolor/scalable/actions/gramps-repository.svg`|
|![](gramps:icon:gramps-source:48)| gramps-source |`gramps/images/hicolor/scalable/actions/gramps-source.svg`|
|![](gramps:icon:gramps-spouse:48)| gramps-spouse |`gramps/images/hicolor/scalable/actions/gramps-spouse.svg`|
|![](gramps:icon:gramps-tag:48)| gramps-tag |`gramps/images/hicolor/scalable/actions/gramps-tag.svg`|
|![](gramps:icon:gramps-tag-new:48)| gramps-tag-new |`gramps/images/hicolor/scalable/actions/gramps-tag-new.svg`|
|![](gramps:icon:gramps-tools:48)| gramps-tools |`gramps/images/hicolor/scalable/actions/gramps-tools.svg`|
|![](gramps:icon:gramps-tree-group:48)| gramps-tree-group |`gramps/images/hicolor/scalable/actions/gramps-tree-group.svg`|
|![](gramps:icon:gramps-tree-list:48)| gramps-tree-list |`gramps/images/hicolor/scalable/actions/gramps-tree-list.svg`|
|![](gramps:icon:gramps-tree-select:48)| gramps-tree-select |`gramps/images/hicolor/scalable/actions/gramps-tree-select.svg`|
|![](gramps:icon:gramps-unlock:48)| gramps-unlock |`gramps/images/hicolor/scalable/actions/gramps-unlock.svg`|
|![](gramps:icon:gramps-view:48)| gramps-view |`gramps/images/hicolor/scalable/actions/gramps-view.svg`|
|![](gramps:icon:gramps-viewmedia:48)| gramps-viewmedia |`gramps/images/hicolor/scalable/actions/gramps-viewmedia.svg`|
|![](gramps:icon:gramps-zoom-best-fit:48)| gramps-zoom-best-fit |`gramps/images/hicolor/scalable/actions/gramps-zoom-best-fit.svg`|
|![](gramps:icon:gramps-zoom-fit-width:48)| gramps-zoom-fit-width |`gramps/images/hicolor/scalable/actions/gramps-zoom-fit-width.svg`|
|![](gramps:icon:gramps-zoom-in:48)| gramps-zoom-in |`gramps/images/hicolor/scalable/actions/gramps-zoom-in.svg`|
|![](gramps:icon:gramps-zoom-out:48)| gramps-zoom-out |`gramps/images/hicolor/scalable/actions/gramps-zoom-out.svg`|
|![](gramps:icon:org.gramps_project.Gramps:48)| org.gramps_project.Gramps |`gramps/images/hicolor/scalable/apps/org.gramps_project.Gramps.svg`|
|![](gramps:icon:gramps:48)| gramps |`gramps/images/gramps.svg` (also `gramps/images/gramps.png`) — used for the About-dialog window icon; a root-level file resolved by GTK's icon-theme fallback, not the `hicolor/` structure|

Note on **icon path**: this is the canonical highest-quality asset for each name
(the `scalable/` SVG when one exists, else the best available raster size).
Every `gramps-*`/`geo-*`/`application-x-*` name above also has PNG fallbacks at
`48x48`, `24x24`, `22x22`, and `16x16` under the matching context folder
(`actions`, `apps`, or `mimetypes`), except `FS-BLA-16` / `FS-G-16` (16×16-only)
and `org.gramps_project.Gramps`, which also has `128x128` and `256x256` variants.

## Where these icons are actually used

### Navigator sidebar — Category and View-mode organization

This follows the structure `gramps/plugins/sidebar/dropdownsidebar.py` actually
consumes (it's the clearer reference, as you suggested): the sidebar is built
from a `categories` list of `(cat_num, cat_name, cat_icon)`, plus a parallel
`views` dict of `{cat_num: [(view_num, view_name, view_icon), ...]}`. Each
category shows **one** button with its `cat_icon`; if a category has more than
one registered view, a drop-down arrow next to it lists those views by name
with their own `view_icon` — that per-view icon is the "view mode" piece that
was missing before (e.g. switching People between its grouped and flat-list
views, or Ancestry between Pedigree/Fan Chart/Descendant Fan/2-Way Fan).

Both `categories` and `views` are assembled in `gramps/gui/navigator.py`: the
category icon comes from a hardcoded `CATEGORY_ICON` dict (falling back to a
view's `stock_category_icon`/`stock_icon` if a category isn't listed there);
each view's icon comes from that view's own `stock_icon=` in its `.gpr.py`
registration (`gramps/plugins/view/view.gpr.py` and `geography.gpr.py`), or the
category icon if the view didn't set one.

|Icon|Category|cat_icon|View (mode)|view_icon|
|---|---|---|---|---|
|![](gramps:icon:gramps-gramplet:48)|Dashboard|gramps-gramplet|Dashboard|*(none set → falls back to gramps-gramplet)*|
|![](gramps:icon:gramps-person:48)|People|gramps-person|Grouped People *(default)*|![](gramps:icon:gramps-tree-group:48) gramps-tree-group|
| | | |People (flat list)|![](gramps:icon:gramps-tree-list:48) gramps-tree-list|
|![](gramps:icon:gramps-relation:48)|Relationships|gramps-relation|Relationships|*(none set → falls back to gramps-relation)*|
|![](gramps:icon:gramps-family:48)|Families|gramps-family|Families|*(none set → falls back to gramps-family)*|
|![](gramps:icon:gramps-event:48)|Events|gramps-event|Events|*(none set → falls back to gramps-event)*|
|![](gramps:icon:gramps-pedigree:48)|Ancestry (label "Charts")|gramps-pedigree|Pedigree *(default)*|![](gramps:icon:gramps-pedigree:48) gramps-pedigree|
| | | |Fan Chart|![](gramps:icon:gramps-fanchart:48) gramps-fanchart|
| | | |Descendant Fan|![](gramps:icon:gramps-fanchartdesc:48) gramps-fanchartdesc|
| | | |2-Way Fan|![](gramps:icon:gramps-fanchart2way:48) gramps-fanchart2way|
|![](gramps:icon:gramps-place:48)|Places|gramps-place|Places (flat list)|![](gramps:icon:gramps-tree-list:48) gramps-tree-list|
| | | |Place Tree *(default)*|![](gramps:icon:gramps-tree-group:48) gramps-tree-group|
|![](gramps:icon:gramps-geo:48)|Geography|gramps-geo|All known places for one Person|![](gramps:icon:geo-show-person:48) geo-show-person|
| | | |All known places for one Family|![](gramps:icon:geo-show-family:48) geo-show-family|
| | | |Every residence/move for a person + descendants|![](gramps:icon:geo-show-family-down:48) geo-show-family-down|
| | | |Have these two families been able to meet?|![](gramps:icon:geo-show-family:48) geo-show-family|
| | | |Have they been able to meet?|![](gramps:icon:gramps-relation:48) gramps-relation|
| | | |All known Places|![](gramps:icon:geo-show-place:48) geo-show-place|
| | | |All places related to Events|![](gramps:icon:geo-show-event:48) geo-show-event|
|![](gramps:icon:gramps-source:48)|Sources|gramps-source|Sources *(default)*|![](gramps:icon:gramps-tree-list:48) gramps-tree-list|
| | | |Citation Tree|![](gramps:icon:gramps-tree-select:48) gramps-tree-select|
|![](gramps:icon:gramps-repository:48)|Repositories|gramps-repository|Repositories|*(none set → falls back to gramps-repository)*|
|![](gramps:icon:gramps-media:48)|Media|gramps-media|Media|*(none set → falls back to gramps-media)*|
|![](gramps:icon:gramps-notes:48)|Notes|gramps-notes|Notes|*(none set → falls back to gramps-notes)*|
|![](gramps:icon:gramps-citation:48)|Citations|gramps-citation|Citations|*(none set → falls back to gramps-citation)*|

Every icon in this table — category and view-mode alike — is one of the 76
already listed in the main inventory above; the paths are identical, this
table just shows the actual Category/View organization they're used in
(note `Citation Tree` is registered under the **Sources** category, not
Citations — that's a Gramps registration quirk, not a mistake here).

### `.gpr.py` `stock_icon=` registrations (13 names, all view-mode icons above)
`geo-show-event`, `geo-show-family`, `geo-show-family-down`, `geo-show-person`,
`geo-show-place`, `gramps-fanchart`, `gramps-fanchart2way`, `gramps-fanchartdesc`,
`gramps-pedigree`, `gramps-relation`, `gramps-tree-group`, `gramps-tree-list`,
`gramps-tree-select`.

## Editor-tab and other toolbar icons (system/GTK theme — not bundled by Gramps)

These are the icons you flagged as missing. They're real, heavily-used icons in
the GUI, but they are **not** Gramps assets — no matching file exists anywhere
under `gramps/images/`. They're plain freedesktop/GTK icon-theme names, resolved
at runtime from whatever icon theme is installed on the user's system (GTK's
default "Adwaita" theme on most Linux desktops). Note that most of these
(`edit-undo`, `edit-redo`, `format-text-bold`, etc.) are exactly the kind of
name that ships as a **color/symbolic pair** in Adwaita — see
["Forcing the color variant over the symbolic fallback"](#forcing-the-color-variant-over-the-symbolic-fallback)
above if you need one of these to render predictably rather than whatever
GTK's fallback logic happens to pick. The **Icon** column below uses
the same `gramps:icon:` macro as the main table for consistency, but since there
is no file in the Gramps repo, the **path** column instead points at the
equivalent icon in the Adwaita theme repo (the icon set GTK ships by default) —
that's the closest thing to a "source" that exists for these.

### Person/Family/Event/etc. editor tab toolbars (Add / Edit / Remove / Move / Jump)
Defined once in the shared base class `ButtonTab`
(`gramps/gui/editors/displaytabs/buttontab.py`) and reused by every embedded-list
tab across the editors (Addresses, Attributes, Names, Media References, Notes,
Sources, Citations, Web/Internet, Associations, LDS ordinances, etc.):

|Icon|icon name|path (system theme, not in Gramps repo)|button / action|
|---|---|---|---|
|![](gramps:icon:list-add:48)|list-add|`Adwaita/*/actions/list-add-symbolic.svg`|Add|
|![](gramps:icon:gtk-edit:48)|gtk-edit|*(deprecated GTK2-era stock-icon alias; no direct Adwaita equivalent — modern GTK themes still map it via the stock-icon compatibility table)*|Edit|
|![](gramps:icon:list-remove:48)|list-remove|`Adwaita/*/actions/list-remove-symbolic.svg`|Remove|
|![](gramps:icon:gtk-index:48)|gtk-index|*(deprecated GTK2-era stock-icon alias, same as gtk-edit)*|Select Existing (share)|
|![](gramps:icon:go-up:48)|go-up / go-previous|`Adwaita/*/actions/go-up-symbolic.svg` / `go-previous-symbolic.svg`|Move Up / Move Left|
|![](gramps:icon:go-down:48)|go-down / go-next|`Adwaita/*/actions/go-down-symbolic.svg` / `go-next-symbolic.svg`|Move Down / Move Right|
|![](gramps:icon:go-jump:48)|go-jump|`Adwaita/*/actions/go-jump-symbolic.svg`|Jump To|

The same `list-add` / `list-remove` / `go-up` / `go-down` / `gtk-index` /
`document-revert` set also appears directly in a handful of plugin option
dialogs (`gramps/gui/plug/_guioptions.py`, `gramps/gui/plug/_windows.py`).

### Note/rich-text tab toolbar (`gui/widgets/styledtexteditor.py`)
This is the formatting toolbar shown on every Note tab (Person, Family, Event,
Place, Source, Repository, Media, Citation editors all embed it):

|Icon|icon name|path|button|
|---|---|---|---|
|![](gramps:icon:format-text-italic:48)|format-text-italic|`Adwaita/*/actions/format-text-italic-symbolic.svg`|Italic|
|![](gramps:icon:format-text-bold:48)|format-text-bold|`Adwaita/*/actions/format-text-bold-symbolic.svg`|Bold|
|![](gramps:icon:format-text-underline:48)|format-text-underline|`Adwaita/*/actions/format-text-underline-symbolic.svg`|Underline|
|![](gramps:icon:format-text-strikethrough:48)|format-text-strikethrough|`Adwaita/*/actions/format-text-strikethrough-symbolic.svg`|Strikethrough|
|![](gramps:icon:format-text-superscript:48)|format-text-superscript|`Adwaita/*/actions/format-text-superscript-symbolic.svg`|Superscript|
|![](gramps:icon:format-text-subscript:48)|format-text-subscript|`Adwaita/*/actions/format-text-subscript-symbolic.svg`|Subscript|
|![](gramps:icon:edit-undo:48)|edit-undo|`Adwaita/*/actions/edit-undo-symbolic.svg`|Undo|
|![](gramps:icon:edit-redo:48)|edit-redo|`Adwaita/*/actions/edit-redo-symbolic.svg`|Redo|
|![](gramps:icon:gramps-font-color:48)|gramps-font-color|`gramps/images/hicolor/scalable/actions/gramps-font-color.svg` *(bundled Gramps icon — already in the main table)*|Font color|
|![](gramps:icon:gramps-font-bgcolor:48)|gramps-font-bgcolor|`gramps/images/hicolor/scalable/actions/gramps-font-bgcolor.svg` *(bundled Gramps icon — already in the main table)*|Highlight color|
|![](gramps:icon:go-jump:48)|go-jump|`Adwaita/*/actions/go-jump-symbolic.svg`|Insert link|
|![](gramps:icon:edit-clear:48)|edit-clear|`Adwaita/*/actions/edit-clear-symbolic.svg`|Clear formatting|

Gramps ships two of its own `format-text-*` icons in the main inventory
(`format-text-subscript-symbolic`, `format-text-superscript-symbolic`) that
look like duplicates of the system ones above — they aren't actually used by
`styledtexteditor.py` (which requests the plain, non-`-symbolic` names and lets
GTK resolve those from the system theme); those two bundled SVGs currently have
no confirmed call site in the codebase.

### Other Glade-defined dialog/toolbar icons found across `gramps/gui/glade/*.glade`
Scattered one-offs used in specific dialogs (Rule editor, Book tool, Gramplet
pane, Tip of the Day, child-reference editor, event-reference editor, address
editor, generic message dialogs). All are standard system-theme names:

|Icon|icon name|used in|
|---|---|---|
|![](gramps:icon:dialog-information:48)|dialog-information|`dialog.glade`|
|![](gramps:icon:dialog-password:48)|dialog-password|`editaddress.glade`|
|![](gramps:icon:dialog-question:48)|dialog-question|`dialog.glade`|
|![](gramps:icon:dialog-warning:48)|dialog-warning|`dialog.glade`|
|![](gramps:icon:document-open:48)|document-open|`book.glade`|
|![](gramps:icon:document-properties:48)|document-properties|`grampletpane.glade`|
|![](gramps:icon:document-save:48)|document-save|`book.glade`|
|![](gramps:icon:edit-copy:48)|edit-copy|`rule.glade`|
|![](gramps:icon:edit-find-symbolic:48)|edit-find-symbolic|`rule.glade`|
|![](gramps:icon:image-missing:48)|image-missing|`tipofday.glade`|
|![](gramps:icon:preferences-desktop:48)|preferences-desktop|`book.glade`|
|![](gramps:icon:system-run:48)|system-run|`rule.glade`|
|![](gramps:icon:text-x-generic:48)|text-x-generic|`editeventref.glade`|
|![](gramps:icon:window-close:48)|window-close|`grampletpane.glade`|

## Orphaned/legacy image files (not part of the icon theme, not referenced anywhere)

A handful of loose `gramps-*.png` files sit directly under `gramps/images/`
(outside the `hicolor/` theme tree) with no remaining Python or Glade references
found in the current codebase — they appear to be leftovers from an earlier
icon layout: `gramps-export.png`, `gramps-import.png`, `gramps-undo-history.png`.
A few other root-level files (`gramps-parents.png`, `gramps-parents-add.png`,
`gramps-parents-open.png`, `add-parent-existing-family.png`) are superseded
duplicates of icons that now live properly in `hicolor/scalable/actions/`.
