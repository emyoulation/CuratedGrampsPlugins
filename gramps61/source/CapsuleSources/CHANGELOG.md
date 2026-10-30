# Capsule Sources changelog
<!--  -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md) ● [PLAN.md](PLAN.md)

Capsule Sources imports captures made with [Genealogy Capsule](https://github.com/mjlawless/capsule-genealogy) ([announcement](https://www.reddit.com/r/GenealogySoftwareDevs/comments/1xioiq6/new_chrome_extension_released_for_saving/), [release notes](https://github.com/mjlawless/capsule-genealogy/releases)) into Gramps.
## 0.1.0
First experimental version, for Gramps 5.2 and newer.
- New tool: Tools > Family Tree Processing > Capsule Sources.
- Reads Genealogy Capsule capture folders (capture-folder v1 and v2) from the Capsule data folder, or any folder you choose. The folder choice and window size are remembered.
- Lists every capture with its date, site, title, status (current, not read yet, superseded) and privacy, and marks captures already in the tree.
- Imports the selected captures as Repositories (one per site), Sources (one per source list entry), Citations (one per capture), Citation and Research notes, and Media objects linked in place with their SHA-256 fingerprints.
- Marks subscription and copyright-flagged captures private.
- Skips captures already imported, so running the tool again adds nothing twice.
- Hides superseded captures unless asked, and never imports them.
- Creates no people, events or facts.
- A Help icon at the lower left opens this README in Markdown Dash when it is installed, or the help page on GitHub in a browser otherwise.
