# Capsule Sources: plan
<!--  -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [PLAN.md](PLAN.md)

## Goal
Bring the evidence that [Genealogy Capsule](https://github.com/mjlawless/capsule-genealogy) saves (archived record pages, record images, Evidence Explained citations, SHA-256 hashes) into a desktop Gramps tree, without ever creating or merging people automatically. Capsule does the capturing in Chrome; this addon only reads the capture folders that Capsule writes to disk, so it works even when the Capsule backend is not running.

Capsule's own ROADMAP lists "Gramps integration" (targeting Gramps Web) under "Later: from evidence to a tree". Before Phase 2, contact the author in the project Discussions so that both efforts share one mapping.

## Phases
**Phase 1: Capsule Sources tool (this draft).** Tools > Family Tree Processing > Capsule Sources. Pick the Capsule captures folder, see every capture with its site, title, status and whether it is already in the tree, tick the ones to bring in, and click Import selected. Creates Repository, Source, Citation, Media and Note objects only. Running it again skips captures already imported.

**Phase 1b: transcripts.** Add each `transcript/<id>/transcript.json` as a Note of type Transcript on the Citation, keeping the verbatim value and the annotation separate, with the "reading aid, not the record" caution at the top.

**Phase 2: Capsule Evidence review gramplet.** On the Citations view (and the Citation editor gramplet bar if practical), show the personas and facts from `extraction.json` for the active Citation, each with its stated/calculated/estimated marking and the words it came from. The user chooses an existing Person or creates one, and the fact is added through the normal Gramps editors with the Citation attached. Nothing is matched automatically. Needs the `extraction.json` schema studied first (`capsule/contracts/evidence.py`).

**Phase 3: integrity check.** A tool that recomputes SHA-256 for every Media object carrying a "SHA-256" attribute and reports files that changed, moved or disappeared.

**Maybe later:** ask the running backend (`http://127.0.0.1:8765/`) whether the active Citation URL was captured already; refresh Citations when a capture is superseded; an Import plugin for `capsule export` ZIP files (people would still go through the Phase 2 review).

## Phase 1 mapping
| Capsule | Gramps |
|---|---|
| site (`source.site_name`, else the URL host) | Repository, type Web site, with the site home page as a Web Home URL. One per site. |
| `citation.json` source list entry | Source title. Captures whose source list entry is identical share one Source. Abbreviation is the site name. RepoRef media type Electronic. |
| one capture | one Citation. Volume/Page holds the Evidence Explained reference note. |
| `capture_id`, `source.id`, page URL, access date, archived URL | Citation attributes "Capsule capture id", "Capsule source id", "URL", "Accessed", "Archived URL" |
| reference note, short note, source list entry | one Note of type Citation on the Citation |
| `notes.json` | one Note of type Research per entry, oldest first |
| record image, page PDF, saved page (MHTML), document | Media objects linked in place inside the Capsule archive (not copied), attached to the Citation, with attributes "Capsule file", "SHA-256" and "URL" (where the bytes came from) |
| gated or copyright-flagged capture | Citation, its Notes and its Media marked private |
| superseded capture (`lifecycle.json`) | hidden by default and never selectable |
| `extraction: "pending"` | imported normally; status shows "not read yet" |

## Assumptions made
- One Source per distinct source list entry is the right grouping. If Capsule writes record-specific text into that entry, every capture gets its own Source, which still works but clutters the Sources view.
- The Citation date stays empty. The access date goes into an attribute, because the Gramps Citation date normally means the date of the record entry.
- Media files stay where Capsule keeps them (`~/.local/share/Capsule/captures/...` on Linux), linked by absolute path. Moving or exporting the Capsule archive would break those links; Gramps Media Manager can fix paths in bulk.
- `snapshot.html` is not attached. It is Capsule's text copy for reading; the saved page (MHTML) and page PDF are the human-viewable versions.
- Attribute names are kept in English and untranslated, because they are lookup keys.
- The tool lives under Family Tree Processing because it changes the tree.

## Open questions
- Should the Citation confidence be set from Capsule data (for example "original" versus "derivative" source quality)?
- Should a superseded capture that is already imported get a Tag in Gramps?
- Should Phase 1 offer copying media into the Gramps base media path instead of linking in place?
