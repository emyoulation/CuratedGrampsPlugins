[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)
# vcardenhanced — Multi-version vCard Import/Export for Gramps
![](gramps:icon:gramps-attribute:64) **vCard** `.vcf` addons — Plug-in Types: ![](gramps:icon:gramps-import:24) Importer / ![](gramps:icon:gramps-export:24) Exporter

- **vCard versions supported:** 1.0, 2.1, 3.0, 4.0
- **Gramps versions:** 5.2 and later
- **Addon type:** Fork-and-Hide workaround (GEPS 048, Workaround A)
- **Status:** Experimental

## What this addon does
This addon replaces the built-in Gramps vCard importer and exporter with versions that understand vCard 1.0, 2.1, 3.0 and 4.0, and the common extensions written by Apple, Android, Evolution, KDE and Outlook.

The importer brings every vCard property that has a place in the Gramps database into that place: names, events, places, addresses, web links, notes, tags, photos (as Media objects), family relationships (as Families) and other relationships (as Associations). Properties that have no place in Gramps are kept as text in a Person attribute, so no data is lost.

The exporter writes the same data back out. A file that is imported and then exported again gives the same Gramps data when it is imported a second time (a "round trip").

See [vCard on Wikipedia](https://wikipedia.org/wiki/VCard) for background on the format.

## Installation
1. Copy these files into one folder inside the Gramps plugins folder, for example `~/.local/share/gramps/gramps60/plugins/vcardenhanced/` on Linux:
    - `vcardenhanced.gpr.py`
    - `importvcard_enh.py`
    - `exportvcard_enh.py`
    - `README.md`
    - `CHANGELOG.md`
2. Restart Gramps.
3. Hide the built-in vCard plugins, so that only one vCard choice appears in the Import and Export dialogs:
    - Open **Help → Plugin Manager Enhanced**.
    - Find the two built-in plugins named `vCard` (one importer, one exporter) and set them to **Hidden**.
    - The addon plugins are named **vCard (Enhanced — v1/2.1/3.0/4.0)**.

Automatic hiding is not possible yet. See Hurdle 4 below.

## Importing
Use **Family Trees → Import** and select a `.vcf` file. Each vCard (from `BEGIN:VCARD` to `END:VCARD`) becomes one Person.

### Where each vCard property goes
| vCard property | Gramps destination |
|---|---|
| `N`, `FN` | Primary name (given names, surnames, title, suffix, call name) |
| `NICKNAME` | Alternate name with a nickname |
| `ORG` (when there is no name) | Surname of the Person (business cards) |
| `ORG` (when there is a name) | "Agency" attribute on the Occupation event |
| `TITLE`, `ROLE` | Occupation event (description); a different `ROLE` becomes a "Role" event attribute |
| `GENDER`, `X-GENDER` | Gender; the identity text of `GENDER` (for example `F;woman`) becomes a "Gender identity" attribute |
| `BDAY` | Birth event date |
| `BIRTHPLACE` | Birth event place |
| `DEATHDATE` | Death event date |
| `DEATHPLACE` | Death event place |
| `ANNIVERSARY`, `X-ANNIVERSARY`, Apple anniversary `X-ABDATE` | Marriage event on a Family (see below) |
| `ADR` | Address |
| `TEL` | Address with only a phone number |
| `EMAIL` | Internet link of type E-mail |
| `URL` | Internet link of type Web Home |
| `IMPP`, `X-AIM`, `X-SKYPE`, `X-JABBER` and similar | Internet link of type "Instant Messaging" |
| `SOCIALPROFILE`, `X-SOCIALPROFILE`, `X-TWITTER` | Internet link of type "Social Profile" |
| `FBURL`, `CALURI`, `CALADRURI` | Internet links of type "Free/Busy", "Calendar", "Calendar address" |
| `NOTE` | Person note |
| `CATEGORIES` | Tags (existing tags with the same name are reused) |
| `PHOTO`, `LOGO`, `SOUND` | Media objects in the Gallery (see below) |
| `RELATED`, `X-ABRELATEDNAMES`, `X-SPOUSE`, `X-MANAGER`, `X-ASSISTANT`, `AGENT` | Families (spouse, parent, child) or Associations (all other types) (see below) |

The `TYPE` of an e-mail address or web link (for example `HOME` or `WORK`) becomes the description of the link.

Dates may be complete (`1950-04-15` or `19500415`), partial (`1950-04`, `1950`, `--0415` for a birthday without a year, `---15`), or text. A date that is not valid (for example February 30) is kept as text and reported.

A place that is given as coordinates (`geo:29.76,-95.37`) becomes a Place with that latitude and longitude. A place given as text reuses an existing Place with the same full title, or a new Place is created.

### Embedded photos, logos and sounds
Images and sounds that are embedded in a vCard are saved as files in a folder named `media`, in the same folder as the imported `.vcf` file. Each file becomes a Media object in the Gallery of the Person. The photo is placed first in the Gallery, so it is the image that Gramps shows for the Person.

- File names are made from the name of the Person, the kind of media and a short checksum, for example `Doe_John_photo_ee767024.png`.
- The file type is read from the data itself, not from the `TYPE` given in the vCard, because that `TYPE` is often wrong.
- An image that is already in the Family Tree (same checksum) is reused, not duplicated. A company logo on many vCards becomes one Media object. Importing the same file twice does not create new media files.
- A photo given as a `file:` link points to that file; the file is not copied.
- A photo given as an `http:` or `https:` link is not downloaded. It becomes an Internet link of type "Photo", "Logo" or "Sound".

If the `media` folder is inside the base media folder of the Family Tree, the Media paths are stored as relative paths. Otherwise they are stored as absolute paths. The **Media Manager** tool can change them later.

### Relationships become Families and Associations
Relationships are read from `RELATED`, from the Apple form (`item1.X-ABRELATEDNAMES` with `item1.X-ABLabel`, or `X-ABRELATEDNAMES;TYPE=spouse:…`), and from the older vendor properties `X-SPOUSE`, `X-MANAGER`, `X-ASSISTANT` and `AGENT`. They are linked after the whole file is read, so the order of the vCards does not matter.

The other person is found by UID (`urn:uuid:…`), by e-mail address (`mailto:…`) or by name. A name matches when it is the same as the formatted name, or when all of its words are found in the name of exactly one person: "Henry VIII" finds `N:Tudor;Henry;;King;VIII`, and "Catherine of Aragon" finds `FN:Queen Catherine of Aragon`. Only the People in the same `.vcf` file are searched, never the People that are already in the Family Tree, to avoid linking to the wrong person.

- When a name matches nobody in the file, a small Person is created with that name. That Person has a "vCard RELATED" attribute that names the vCard it came from.
- When a UID or e-mail address matches nobody, or a name matches more than one person, nothing is linked. The original line is kept in a "vCard RELATED" attribute and the problem is listed in the import report.

**Family relationships build Families:**
- `spouse` (also `husband`, `wife`) makes a Family with the two people as father and mother, with the relationship type Married. `partner` makes a Family with the relationship type Unknown. When both people list each other, only one Family is made.
- `child` and `parent` (also `son`, `daughter`, `father`, `mother`) place the child in the Family of the parents. A child goes into the Family of a couple only when both parents are named, either in the vCard of the child or in the vCards of both parents. A child with only one known parent goes into a Family with that parent and an unknown second parent; children with the same single known parent share that Family.
- `sibling` (also `brother`, `sister`) is not stored separately when the two people are children of the same Family and the word agrees with the recorded gender ("brother" for a male, "sister" for a female), because the Family already says the same thing and the exporter writes it back from the Family. In every other case it becomes an Association, so nothing in the vCard is lost: half-siblings (who share only one parent and are in different Families), siblings with no known parents, and "brother" or "sister" for a person whose gender is not recorded.
- The father and mother places are chosen by the gender of each person. When the gender is not recorded, the given-name statistics of the Family Tree are used, and then a title such as King or Queen. The gender of the Person is not changed.

**Marriage dates:** `ANNIVERSARY`, `X-ANNIVERSARY` and the Apple anniversary become the Marriage event of the Family of that person and their spouse. When both spouses give the same date, only one event is made. A person with an anniversary but no known spouse gets a Married Family with an unknown spouse. A person with several spouses keeps the Marriage event on the Person, because the vCard does not say which marriage it belongs to; this is listed in the import report.

**All other relationship types become Associations**, with the type as the association label (for example "Friend, Coworker" when there are several types). A relationship with both kinds of type, for example `TYPE=child,friend`, makes both a Family link and an Association.

| RELATED `TYPE` | Becomes |
|---|---|
| `spouse`, `husband`, `wife` | Married Family |
| `partner` | Family (relationship Unknown) |
| `child`, `son`, `daughter`, `parent`, `father`, `mother` | Child in a Family |
| `sibling`, `brother`, `sister` | Nothing extra when both are children of the same Family (and the word agrees with the gender); otherwise Association "Sibling", "Brother" or "Sister" |
| `kin`, `sweetheart`, `crush`, `date`, `muse` | Association: Kin, Sweetheart, Crush, Date, Muse |
| `colleague`, `co-worker`, `agent`, `assistant`, `manager` | Association: Colleague, Coworker, Agent, Assistant, Manager |
| `friend`, `acquaintance`, `met`, `contact` | Association: Friend, Acquaintance, Met, Contact |
| `neighbor`, `co-resident` | Association: Neighbor, Co-resident |
| `emergency` | Association: Emergency contact |
| `me` | Nothing (it points to the same person) |
| anything else | Association with the `TYPE` text as the label |

### vCards without a name
A vCard that has no `N`, `FN` or `ORG` property is imported as a placeholder Person with the given name **unidentified** and the surname **vCard Import**. Search for that surname to find these People after the import. A vCard that contains no data at all (only `BEGIN`, `VERSION` and `END`) is skipped.

### Properties kept as text
Some properties have no place in the Gramps database, for example `UID`, `KEY`, `GEO`, `TZ`, `REV`, `KIND`, `LANG`, `PRONOUNS`, `X-PHONETIC-FIRST-NAME`, and the `TYPE` of a phone number or address. These lines are stored without change in a Person attribute named `vCard <version> source` (for example `vCard 3.0 source`). The exporter writes them back out.

### The import report
At the end of the import, a report shows how many People, events, places, media objects, media files, notes, tags and associations were created, and the location of the `media` folder.

Each problem is listed with its line number. The complete vCard that caused the problem is shown below the message, so the record can be found without a text editor that can jump to a line number. Very long lines (embedded images) are shortened in the report.

## Exporting
Use **Family Trees → Export** and select **vCard (Enhanced — v1/2.1/3.0/4.0)**. The export options page has a choice of vCard version. The default is 3.0, which is read by the most programs.

The exporter writes everything that the importer reads, in the form that is correct for the selected version:

- **Photo:** the first image in the Gallery of the Person, taken from the large Gramps thumbnail (180 pixels on the long side) and embedded as PNG. When the Gallery reference has a selected region, only that region is used, so a face selection exports as the face.
- **Logo and sound:** an image that was imported as a logo is exported as `LOGO` in the same way. A sound file is embedded without change.
- **Relationships:** the spouses and children in the Families of the Person, the parents and siblings in the Family where the Person is a child (siblings as "brother" or "sister" when their gender is recorded), and all Associations are written as relationships. In vCard 4.0 they become `RELATED` properties. Versions 1.0 to 3.0 have no `RELATED` property, so the Apple form (`X-ABRELATEDNAMES` with `X-ABLabel`) is written, which Apple, Android and this importer all read.
- **Marriage:** the first Marriage event of the Person, or of the first family of the Person, becomes `ANNIVERSARY` (4.0) or `X-ANNIVERSARY` (older versions).
- **Placeholder People:** they are written without a name, as in the original vCard.
- **People created from RELATED names:** they are not written as separate vCards; they appear only as the name in the `RELATED` line.
- **Kept text:** the lines in `vCard <version> source` attributes are written back out without change.

### Round trip
A `.vcf` file that is imported, exported and imported again gives the same Gramps data, including Families, Marriage events and Associations. The only difference is the photo: Gramps thumbnails are always PNG images and smaller than the original, so a JPEG photo comes back as a smaller PNG.

### Differences from the vCard standards
To make the round trip complete, the exporter sometimes writes data in a form that the standards do not strictly allow:

- A placeholder Person is written without `FN`, which vCard 3.0 and 4.0 require.
- `BIRTHPLACE`, `DEATHPLACE`, `DEATHDATE`, partial or text birth dates, and `GENDER` (only when there is a gender identity) are also written in vCard 1.0 to 3.0, although they come from vCard 4.0.
- Kept text lines are written in the form of the vCard version that they were imported from.

Most programs ignore properties that they do not know, so these differences do not usually cause problems.

## vCard version notes
| Version | Standard | Notes |
|---|---|---|
| 1.0 | Versit 1995 | Rarely seen; QUOTED-PRINTABLE is common |
| 2.1 | Versit 1996 | Widely supported; used by Outlook and older phones; QUOTED-PRINTABLE and BASE64 |
| 3.0 | RFC 2426 (1998) | Default of this addon; UTF-8 |
| 4.0 | RFC 6350 (2011) | Current standard; `GENDER`, `ANNIVERSARY`, `RELATED`, `data:` URIs |
| 4.0 extensions | RFC 6474, RFC 9554 | `BIRTHPLACE`, `DEATHPLACE`, `DEATHDATE`, `SOCIALPROFILE`, `PRONOUNS` |

## Variant Call Format (DNA) detection
The `.vcf` file extension is also used by Variant Call Format files, which hold genetic (DNA) data. These files begin with `##fileformat=VCFv`. The importer reads the first 32 bytes of the file before it starts. If the file is a DNA file, the import stops with a clear message.

## Fork-and-Hide workaround — hurdles found
This addon is an experiment in the GEPS 048 "Workaround A: Fork-and-Hide" approach. These problems were found during development, as input to the full GEPS 048 design.

### Hurdle 1 — Duplicate plugin IDs fail silently
The built-in vCard plugins use the IDs `im_vcard` and `ex_vcard`. An addon that reuses those IDs causes a duplicate registration error that does not clearly tell the user which plugin caused it.

**Workaround:** this addon uses the IDs `im_vcard_enh` and `ex_vcard_enh`. As a result, both the built-in plugins and the addon plugins are registered, and both appear in the Import and Export dialogs (see Hurdle 4).

**GEPS 048 implication:** a "supersedes" or "replaces" registration field would let an addon declare that it replaces a built-in plugin, so that Gramps can remove the duplicate automatically.

### Hurdle 2 — The built-in registration file is shared
The built-in importers and exporters are registered together in shared `.gpr.py` files. There is no separate vCard registration file to copy, so the registration of a fork must be written from scratch.

Also, when `fname=` in a `.gpr.py` names a file that does not exist, Gramps skips the plugin with no message at the default log level. A typing error in `fname=` is very hard to find.

**GEPS 048 implication:** Gramps should log a warning when the `fname=` file is missing, and the Plugin Manager could show "file missing" next to the plugin.

### Hurdle 3 — Import paths differ between core plugins and addons
Core plugins can use relative imports. Addons live outside the Gramps package and must use full `gramps.*` import paths, so a copied core plugin needs its imports changed, not only its registration. This addon is self-contained and uses full import paths only.

**GEPS 048 implication:** the Fork-and-Hide guide should include a checklist of these import changes.

### Hurdle 4 — There is no stable way to hide a built-in plugin
To remove the duplicate vCard entries, the built-in plugins must be hidden. The list of hidden plugins is kept by the Plugin Manager in a user configuration file, and there is no documented API to change it from an addon. The `.gpr.py` contains a trial function, `_auto_hide_upstream()`, that tries two undocumented attribute names; it is disabled because it cannot work reliably and would fail without telling the user. Users must hide the built-in plugins by hand (see Installation).

**GEPS 048 implication:** a stable, documented API to hide a plugin by ID is essential for a reliable Fork-and-Hide approach. It should be part of the core plugin system, not depend on a separate Plugin Manager addon.

### Hurdle 5 — There is no way to switch between the built-in plugin and the fork
After one plugin is hidden, Gramps has no built-in control to switch back. That needs the Plugin Manager Enhanced addon or manual editing of a configuration file. A future version of the export options page could offer a "Restore built-in" button.

## Credits
- Original vCard import and export: Martin Hawlisch, Donald N. Allingham, Brian G. Matherly, Jakim Friant, Michiel D. Nauta (Gramps project)
- Export option box pattern: Kari Kujansuu (isotammiexportxml)
- Multi-version fork: Claude (Anthropic, claude-sonnet-4-6), GEPS 048 experiment, March 2026
- Media, Families and Associations, full property mapping and round-trip export: Claude (Anthropic, Claude Opus 5.5), October 2026
- Author and tester: Brian McCullough (emyoulation), Gramps project

![](gramps:icon:kasumi:32)
