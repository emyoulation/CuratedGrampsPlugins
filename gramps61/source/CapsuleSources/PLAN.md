# Capsule Sources: plan
<!--  -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [PLAN.md](PLAN.md)

## Goal
Bring the evidence that [Genealogy Capsule](https://github.com/mjlawless/capsule-genealogy) saves (archived record pages, record images, Evidence Explained citations, SHA-256 hashes) into a desktop Gramps tree, without ever creating or merging people automatically. Capsule does the capturing in Chrome; this addon only reads the capture folders that Capsule writes to disk, so it works even when the Capsule backend is not running.

Capsule's own ROADMAP lists "Gramps integration" (targeting Gramps Web) under "Later: from evidence to a tree". Before Phase 2, contact the author in the project Discussions so that both efforts share one mapping.

## Phases
**Phase 1: Capsule Sources tool (done in 0.1, restructured in 0.2).** Tools > Family Tree Processing > Capsule Sources. Pick the Capsule captures folder, see every capture with its status, record type, person, site and files, tick the ones to bring in, and click Import selected. Creates Repository, Source, Citation, Media and Note objects only. Running it again skips captures already imported. 0.2 follows the [roadmap in the Gramps Discourse topic](https://gramps.discourse.group/t/capsule-source-a-genealogy-capsule-integration-addon-family-tree-processing-tool/10175): archive as Repository, site as Source, capture as Citation; double-click to edit the Citation; a manual refresh button; Open and Open with… for the saved files, because a fresh Fedora has no PDF or HTML viewer set.

**Phase 1a: primary person (done in 0.2).** The Person column works like the Name column of the Photo Tagging gramplet: it starts with the name Capsule read, the user can retype it, and a right-click menu links an existing Person (Link, Fuzzy Match Lookup) or creates one (Add a new person). The linked Person cites the Citation. Names and links live in `CapsuleSources_captures.json` in the addon folder, links per tree.

**Phase 1b: transcripts.** Add each `transcript/<id>/transcript.json` as a Note of type Transcript on the Citation, keeping the verbatim value and the annotation separate, with the "reading aid, not the record" caution at the top.

**Phase 2: Capsule Evidence review gramplet.** On the Citations view (and the Citation editor gramplet bar if practical), show the personas and facts from `extraction.json` for the active Citation, each with its stated/calculated/estimated marking and the words it came from. The user chooses an existing Person or creates one, and the fact is added through the normal Gramps editors with the Citation attached. Nothing is matched automatically. Phase 1a already gives one person per capture; Phase 2 extends that to every persona and fact. Needs the `extraction.json` schema studied first (`capsule/contracts/evidence.py`).

**Phase 3: integrity check.** A tool that recomputes SHA-256 for every Media object carrying a "SHA-256" attribute and reports files that changed, moved or disappeared.

**Maybe later:** drag a Person from a Gramps view onto a row to link it, as in Photo Tagging; ask the running backend (`http://127.0.0.1:8765/`) whether the active Citation URL was captured already; refresh Citations when a capture is superseded; an Import plugin for `capsule export` ZIP files (people would still go through the Phase 2 review); work out the folder size in the background if large archives make the statistics readout slow.

## Mapping (0.2)
| Capsule | Gramps |
|---|---|
| the captures archive | one Repository "Genealogy Capsule captures", type Collection, with Web Home URL to the Genealogy Capsule GitHub page and a custom "Capsule archive folder" URL (`file://` path of the captures folder) |
| site (`source.site_name`, else the URL host) | one Source per site, titled with the site, Publication info the site home page, RepoRef media type Electronic. Found again by its SrcAttribute "Capsule site", not by title. |
| one capture | one Citation. Volume/Page holds the record page title (`source.title`). Date is the capture day (`archive.captured_at`, else the access date). |
| `capture_id`, `source.id`, page URL, access date, archived URL | Citation attributes "Capsule capture id", "Capsule source id", "URL", "Accessed", "Archived URL" |
| reference note, short note, source list entry | one Note of type Citation on the Citation |
| `notes.json` | one Note of type Research per entry, oldest first |
| record image, page PDF, saved page (MHTML), document | Media objects linked in place inside the Capsule archive (not copied), attached to the Citation, with attributes "Capsule file", "SHA-256" and "URL" (where the bytes came from) |
| first persona in `extraction.json` | starting text of the Person column only; nothing is written to the tree from it |
| primary person linked in the tool | the Citation in that Person's own citation list (Source Citations tab) |
| gated or copyright-flagged capture | Citation, its Notes and its Media marked private |
| superseded capture (`lifecycle.json`) | hidden by default and never selectable |
| `extraction: "pending"` | imported normally; status shows "not read yet" |

## Files kept by the addon
- `CapsuleSources.ini`: folder, window size, pane position, column widths, Show superseded, and the viewer program chosen per content type.
- `CapsuleSources_captures.json`: per capture, the typed `name` (an empty string means deliberately cleared), its `given` and `surname` split, and `people` as `{tree id: person handle}`. The tree id is the folder name of the family tree (`db.get_dbid()`). This file is user data and must not be packaged with the addon.

## Assumptions made
- One Source per web site is the right grouping, following the Discourse roadmap. The record collection detail stays in the Evidence Explained source list entry, in the Citation note.
- The Citation Date is the capture day, as the roadmap asks, even though a Gramps Citation date often means the date of the record entry. The access date is also kept in the "Accessed" attribute.
- The archive Repository is found by its name. Two different captures folders imported into one tree share that Repository; its folder URL is the first one used.
- Captures imported with 0.1 are not converted to the new structure; the user can delete and import them again.
- The linked Person is shown from the JSON file, not worked out from the tree. If the user removes the Citation from that Person by hand in Gramps, the row still shows the person as linked.
- Typed names stay on this computer; they do not travel with a Gramps export.
- Media files stay where Capsule keeps them (`~/.local/share/Capsule/captures/...` on Linux), linked by absolute path. Moving or exporting the Capsule archive would break those links; Gramps Media Manager can fix paths in bulk.
- `snapshot.html` is not attached to Gramps. It is Capsule's text copy for reading; the Files section of the panel can still open it.
- Attribute names are kept in English and untranslated, because they are lookup keys.
- The tool lives under Family Tree Processing because it changes the tree.

## Open questions
- Should the Citation confidence be set from Capsule data (for example "original" versus "derivative" source quality)?
- Should a superseded capture that is already imported get a Tag in Gramps?
- Should the tool offer copying media into the Gramps base media path instead of linking in place?
- Should typed names also go into the tree (for example a Citation attribute), so they travel with an export?
- Should the tool offer to move captures imported with 0.1 to the new structure instead of asking the user to import them again?
