# Plan: the full addon catalog (addons-full-xx.json)

Development note for AddonPackShip (APS) and the Addon Marketplace. Written 2026-11-06 by Claude (Anthropic), from a design discussion with Brian McCullough. Status: agreed in principle, not started.

## Goal

APS writes a second, parallel catalog for each language, next to the catalogs that Gramps reads today. Each entry carries every JSON-serializable field of the `register()` call of its `.gpr.py`, under the field name itself (`name`, `version`, `authors`, `maintainers`, ...), never an abbreviated key. Instead of one listing and one download folder per Gramps version, an entry states the range of Gramps versions it works with, and one shared download folder serves them all. The Addon Marketplace prefers this catalog, and falls back to today's `addons-xx.json` when it is missing or unusable.

Why: the short keys of today (`n`, `i`, `v`, ...) are a lossy translation of the registry. Every field needs a code that someone invents and teaches to every reader, so most fields (authors and maintainers among them) never reach the catalog. Author and maintainer names are the most wanted missing fields, so that "brand-conscious" shoppers can search for them.

## Constraints

- Gramps 5.2, 6.0 and 6.1 read only `listings/addons-xx.json` and `download/*.addon.tgz` inside each version folder (`gramps52`, `gramps60`, `gramps61`), and only the short keys. `get_addons()` of Gramps fails on an entry without `"i"`. APS must keep writing those folders and files exactly as today, for the Addon Manager of Gramps and for its check for updates at startup.
- Project addresses saved by users point at a version folder, for example `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/main/gramps60`. Nobody should have to change their project list.
- The full catalog lives outside the version folders, so the Addon Marketplace needs a reliable way to find it from a version-folder address.

## Where the files go

Proposed layout in the repository:

```
CuratedGrampsPlugins/
  catalog/
    listings/addons-full-en.json      the full catalog, one per language
    listings/addons-full-fi.json
    download/AddonMarketplace.addon.tgz   one shared download folder
  gramps60/
    listings/addons-en.json           unchanged, for Gramps itself
    listings/addons-full-en.json      pointer to ../../catalog/... (see below)
    download/...                      unchanged, for Gramps itself
  gramps61/ ...                       same as gramps60
```

## Finding the full catalog: pointer files

In each version folder, APS writes a small pointer with the same name as the full catalog:

```json
{"format": 1, "catalog": "../../catalog/listings/addons-full-en.json"}
```

The Addon Marketplace reads `<project address>/listings/addons-full-<lang>.json`. When that file is a pointer (it has `"catalog"` and no `"addons"`), it follows the address, resolved relative to the pointer with `urllib.parse.urljoin()`, at most once (no chains). When the file is itself a full catalog (it has `"addons"`), it uses it directly, so a small project can skip the shared folder.

Why a pointer and not a guess: it works for any folder name, keeps the decision with the project, and costs one small request. Fallback when no pointer exists: if the project address ends in `/gramps<digits>`, try `<parent>/catalog/listings/addons-full-<lang>.json`; if that also fails, read `addons-<lang>.json` as today.

Language order is the one used for today's catalogs: the languages of the user, then English.

## Format of the full catalog

```json
{
  "format": 1,
  "addons": [
    {
      "id": "AddonMarketplace",
      "name": "Addon Marketplace",
      "version": "0.1.2",
      "ptype": 9,
      "status": 1,
      "audience": 0,
      "description": "Replaces the Addon Manager ...",
      "authors": ["Claude AI", "Brian McCullough"],
      "authors_email": ["", ""],
      "maintainers": ["Brian McCullough"],
      "maintainers_email": [""],
      "help_url": "https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source/AddonMarketplace",
      "requires_mod": [],
      "gramps_versions": {"min": "5.2", "max": "6.1"},
      "download": "../download/AddonMarketplace.addon.tgz"
    }
  ]
}
```

- `format`: the version of this layout. A reader that meets a higher number reads what it understands and ignores the rest.
- Every JSON-serializable `register()` field, under its own name. Tuples become lists. Values that cannot be written as JSON (functions, classes) are left out, never converted to text.
- `gramps_versions`: the Gramps versions the entry works with, as major.minor, both ends included. The same `id` may appear more than once with different ranges and downloads, for an addon that needs a separate build for some versions.
- `download`: the address of the `.tgz`, relative to the catalog file or a full URL.
- `gramps_target_version` is not written: the range replaces it.

## APS tasks

1. Collect the `register()` fields of each `.gpr.py` the way `make.py` of Gramps does (execute the file with a `register` function that records its keyword arguments), but keep every field.
2. Find the range of each addon by executing its `.gpr.py` once per candidate Gramps version (5.2, 6.0, 6.1, and the next one), with `gramps.version.VERSION_TUPLE` and `major_version` faked for that version. The versions for which `register()` is called form the range. This reads the version-range `if` of the Emyoulation `.gpr.py` files exactly as Gramps would, without parsing it.
3. Translate per language as `make.py` does (`glocale.get_addon_translator(gpr, languages=[lang, "en.UTF-8"])`), and write one full catalog per language.
4. Write the shared `.tgz` once into `catalog/download/`, and the pointer files into every version folder.
5. Keep writing today's version folders, listings and downloads unchanged.
6. Validate before publishing: every entry has `id`, `version`, `gramps_versions` and a `download` that exists; no `id` has two entries with overlapping ranges.

## Addon Marketplace tasks

1. Discovery: try the pointer or full catalog, then the `/gramps<digits>` parent fallback, then `addons-xx.json`. Report a broken pointer or full catalog in the warning bar like other catalog problems, and fall back.
2. Read entries with the existing normalizer (`_normalize_catalog_entry()`), which already prefers `register()` names over short keys and keeps unknown fields. Two additions: accept `download` where it now requires `z`, and keep the resolved download address on the entry.
3. Skip entries whose `gramps_versions` range does not include the running Gramps (`VERSION_TUPLE[:2]`). An entry without a range is treated as made for the version folder it was found through.
4. Install, update and downgrade from the resolved download address, instead of building `<project>/download/<z>`.
5. The search already finds authors and maintainers. Next: a "by ..." line in each addon row, where a click on a name filters to that person, as the other lozenges do.

## Testing

- A local `file:///` project with all three cases: pointer file, full catalog in the version folder, no full catalog.
- A full catalog with an addon in two ranges (two downloads), an entry outside the range of the running Gramps, a relative and a full download address, and a broken pointer.
- The hostile-catalog test already used for the normalizer (missing keys, wrong types, unknown fields and types), now inside the `addons` list.
- Gramps itself (the Addon Manager and the check at startup) must see no change: compare its view of each version folder before and after.

## Open questions

- Folder name: `catalog/` at the top of the repository, or another name?
- Should the pointer files be required, or is the `/gramps<digits>` fallback enough for the Emyoulation collection?
- Range granularity: major.minor (proposed) or full versions such as 6.0.8?
- E-mail addresses: list them in the full catalog (they are public in the `.gpr.py` files), or names only?
- Later: propose the same idea for `make.py` of Gramps, so that every project can publish full catalogs.
