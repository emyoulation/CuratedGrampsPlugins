[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)
# Changelog — vcardenhanced
## 2.0.0 — 2026-10-25
Both the importer and the exporter are now version 2.0.0. Before this release the importer was 1.0.2 and the exporter was 1.0.1.

### Added — importer
- Embedded `PHOTO`, `LOGO` and `SOUND` data (vCard 2.1 BASE64, vCard 3.0 `ENCODING=b`, vCard 4.0 `data:` URIs) is saved to a `media` folder beside the imported file and attached to the Person as Media objects. Identical images are stored once. `file:` links are attached without copying; `http:` links become Internet links.
- Relationships (`RELATED`, Apple `X-ABRELATEDNAMES` with `X-ABLabel` or with `TYPE=`, `X-SPOUSE`, `X-MANAGER`, `X-ASSISTANT`, `AGENT`) are linked within the imported file by UID, e-mail address or name. Unmatched names create a small Person; other unmatched values are kept in a "vCard RELATED" attribute and reported.
- Spouse, partner, parent and child relationships build Families: spouses become the father and mother of a Family, and children are placed in the Family of their parents (or of their single known parent). Father and mother places use the recorded gender, else the given-name statistics of the Family Tree, else a title such as King or Queen.
- Sibling relationships are kept as Associations unless both people are children of the same Family and "brother" / "sister" agree with the recorded gender (the Family then holds the same information and the exporter writes it back). Half-siblings, siblings without known parents and gender words for people without a recorded gender are always kept. Other relationship types become Associations.
- Names match when all of their words appear in the name of exactly one person, so "Henry VIII" finds `N:Tudor;Henry;;King;VIII`.
- `NOTE` becomes a Person note.
- `CATEGORIES` becomes Tags.
- `DEATHDATE`, `BIRTHPLACE` and `DEATHPLACE` fill the Birth and Death events; places given as `geo:` coordinates get latitude and longitude, and existing Places with the same title are reused.
- `ORG` (on a vCard with a name) becomes an "Agency" attribute on the Occupation event; `TITLE` and `ROLE` are combined into one Occupation event.
- The identity text of `GENDER` becomes a "Gender identity" attribute.
- `IMPP` and legacy IM properties (`X-AIM`, `X-SKYPE`, `X-JABBER` and others), `SOCIALPROFILE`, `X-SOCIALPROFILE`, `FBURL`, `CALURI` and `CALADRURI` become Internet links.
- `ANNIVERSARY`, `X-ANNIVERSARY` and the Apple anniversary `X-ABDATE` become the Marriage event of the Family of the person and their spouse (one event when both spouses give the date). Without a known spouse, a Married Family with an unknown spouse is made.
- The `TYPE` of an e-mail address or web link becomes the description of the link.
- A vCard with no `N`, `FN` or `ORG` is imported as the placeholder Person "unidentified vCard Import" instead of being skipped.
- A vCard with only `FN` (allowed in vCard 4.0) is imported, with the name split from `FN`.
- The import report starts with counts of the People, events, places, media, notes, tags and associations created.
- Each problem in the import report is followed by the complete vCard that caused it. Very long lines are shortened.

### Added — exporter
- `PHOTO` is exported from the large Gramps thumbnail of the first image in the Gallery, embedded as PNG. A region selected on the Gallery reference is used. A logo is exported as `LOGO` and a sound file as `SOUND`.
- Spouses, children, parents and siblings (as brother or sister when the gender is recorded) from Families, and all Associations, are exported as `RELATED` in vCard 4.0 and as Apple `X-ABRELATEDNAMES` / `X-ABLabel` groups in vCard 1.0 to 3.0.
- New exported properties: `NOTE`, `CATEGORIES`, `DEATHDATE`, `BIRTHPLACE`, `DEATHPLACE`, `ORG`, `ROLE` (with `TITLE`), `IMPP` and legacy IM properties, `SOCIALPROFILE` / `X-SOCIALPROFILE`, `FBURL`, `CALURI`, `CALADRURI`, and `PHOTO` / `LOGO` / `SOUND` links.
- `ANNIVERSARY` is exported in all versions (`X-ANNIVERSARY` before 4.0), also from the Marriage event of the first family.
- Gender identity is exported with `GENDER`.
- Partial dates (`1950-04`, `1950`, `--0612`) and text dates are exported.
- In vCard 2.1, notes with line breaks or non-ASCII text use QUOTED-PRINTABLE.
- Lines kept in `vCard <version> source` attributes and unresolved `RELATED` lines are written back out without change.
- Placeholder People are written without a name, and People created from `RELATED` names are not written as separate vCards, so the export matches the original file.
- The Gramps thumbnail folder is created when it does not exist yet, so a command-line export before the first start of the Gramps window still includes photos.

### Changed
- The plugin status in `vcardenhanced.gpr.py` is now Experimental (it was Stable), to match the README.
- An `ORG` value with several units is stored in the Agency attribute with "; " between the units (for example `Acme Corp; Research`), so that the exporter can split the units again. Data imported with an earlier version used ", ".
- The importer reads QUOTED-PRINTABLE in any vCard version, honors `CHARSET=`, and joins QUOTED-PRINTABLE soft line breaks.
- BASE64 data in vCard 2.1 is read also when the continuation lines are not indented.
- `SORT-STRING` is kept only when it differs from the sort string that Gramps computes, so files exported by Gramps do not add extra source text.
- In vCard 1.0 to 3.0 the occupation is still written as `ROLE`, which the built-in Gramps importer reads. It is written as `TITLE` only when the Occupation event also has a separate "Role" attribute.

### Fixed
- A skipped vCard no longer leaves Birth or Occupation events without a Person in the Family Tree. Events, notes, tags and media are now written only when the Person is written.
- A vCard at the end of the file without `END:VCARD` is now imported instead of being lost.
- Ungrouped `X-ABRELATEDNAMES;TYPE=…` lines lost their relationship type.
- Partial dates are read correctly: `--MM` was read as a day, and `---DD`, `YYYY-MM` and `YYYY` were not recognized.
- `SORT-STRING` was dropped without being kept.
- Notes from vCard 2.1 kept Windows line endings.
- Escaped Apple labels (for example `Friend\, Coworker`) kept the backslash.

### Documentation
- README rewritten: property mapping table, media folder, Families and Associations, placeholder People, import report, export and round trip, and differences from the vCard standards.
- README corrected: the plugin IDs are `im_vcard_enh` and `ex_vcard_enh`; automatic hiding of the built-in plugins is disabled; `RELATED` is a URI by default in vCard 4.0.

## 1.0.2 (importer) and 1.0.1 (exporter) — 2026
First versions of the Fork-and-Hide experiment for GEPS 048, made from the built-in Gramps vCard importer and exporter.

- Import of vCard 1.0, 2.1, 3.0 and 4.0, with version-specific handling.
- Unhandled properties kept in a `vCard <version> source` Person attribute.
- Variant Call Format (DNA) files detected and refused with a clear message.
- `ORG` used as the surname for vCards without a name.
- vCard 4.0 `GENDER`, `ANNIVERSARY`, `TITLE` and partial birth dates.
- Export with a choice of vCard version (default 3.0).
