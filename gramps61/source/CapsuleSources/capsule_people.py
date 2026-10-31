# Based on Genealogy Capsule, Copyright (c) 2026 the Genealogy Capsule authors
# (mjlawless), MIT License:
# https://github.com/mjlawless/capsule-genealogy/blob/main/LICENSE
#
# Capsule Sources - per-capture person names and links
#
# Copyright (C) 2026  Brian McCullough
# 2026      Claude AI (wish coding by Brian McCullough)
#
# GPL-2.0-or-later. The placeholder-name rules follow the Name column of
# the Photo Tagging gramplet (PhotoTaggingGramplet.py:
# split_placeholder_name(), effective_placeholder_name()).
#
# DRAFT MODE: working and readable first; not yet commit-ready.

"""The "Attribute data" for each capture folder, kept in a JSON file in this
addon's folder (never inside the Capsule archive, which belongs to Capsule).

For each capture it holds:

* ``name``: what the user typed in the Person column. Present even when
  empty: an empty name means "deliberately cleared, do not suggest the
  Capsule reading again", as in Photo Tagging.
* ``given`` and ``surname``: that name split, for prefilling a new Person.
* ``people``: the linked primary Person, per family tree, as
  ``{tree id: person handle}``. Handles only mean something inside one
  tree, so each tree keeps its own link.

No Gramps or GTK imports, so it can be tested on its own.
"""

import json
import logging
import os

LOG = logging.getLogger(".CapsuleSources")

PLUGIN_ID = "CapsuleSources"  # id= in CapsuleSources.gpr.py
# the id used by 0.1.x and test builds, still accepted when reading
OLD_PLUGIN_IDS = ("capsulesources",)
SCHEMA_VERSION = "1"
FILE_NAME = "CapsuleSources_captures.json"

# what capsule_reader puts in place of a persona with no label
UNLABELED = "(unlabeled)"


def split_placeholder_name(name):
    """Split "Surname, Given" or "Given Surname" into (given, surname).

    A single word is taken as a surname, as Gramps does for an unparsed
    name. Same rules as Photo Tagging's split_placeholder_name().
    """
    name = (name or "").strip()
    if not name:
        return "", ""
    if "," in name:
        surname, _sep, given = name.partition(",")
        return given.strip(), surname.strip()
    parts = name.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]


def capsule_clue(cap):
    """The name Genealogy Capsule read for the capture's first person, or ""."""
    name = cap.primary_persona or ""
    return "" if name == UNLABELED else name


# ------------------------------------------------------------
# CapturePeople
# ------------------------------------------------------------
class CapturePeople:
    """Load, change and save CapsuleSources_captures.json."""

    def __init__(self, folder):
        self.path = os.path.join(folder, FILE_NAME)
        self.captures = {}
        self.load()

    # --- file ---------------------------------------------------------
    def load(self):
        self.captures = {}
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as err:
            LOG.warning("could not read %s: %s", self.path, err)
            return
        meta = data.get("meta") or {}
        if meta.get("plugin_id") not in (PLUGIN_ID, *OLD_PLUGIN_IDS):
            LOG.warning("%s is not a Capsule Sources file; ignored", self.path)
            return
        captures = data.get("captures")
        if isinstance(captures, dict):
            self.captures = {
                cid: entry for cid, entry in captures.items() if isinstance(entry, dict)
            }

    def save(self):
        data = {
            "meta": {"plugin_id": PLUGIN_ID, "schema_version": SCHEMA_VERSION},
            "captures": self.captures,
        }
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, self.path)
        except OSError as err:
            LOG.warning("could not write %s: %s", self.path, err)

    def _entry(self, cid, create=False):
        entry = self.captures.get(cid)
        if entry is None and create:
            entry = self.captures[cid] = {}
        return entry

    def _tidy(self, cid):
        entry = self.captures.get(cid)
        if entry is not None and not entry.get("people"):
            entry.pop("people", None)
        if entry == {}:
            del self.captures[cid]

    # --- names --------------------------------------------------------
    def manual_name(self, cid):
        """The typed name, "" if deliberately cleared, None if never edited."""
        entry = self._entry(cid)
        return entry.get("name") if entry else None

    def effective_name(self, cap):
        """Typed name if there is one (even ""), else the Capsule reading."""
        manual = self.manual_name(cap.capture_id)
        return capsule_clue(cap) if manual is None else manual

    def set_name(self, cap, text):
        """Store a typed name. Typing back exactly what Capsule read removes
        the edit, so a later, better Capsule reading still shows."""
        text = (text or "").strip()
        entry = self._entry(cap.capture_id, create=True)
        if text and text == capsule_clue(cap):
            for key in ("name", "given", "surname"):
                entry.pop(key, None)
        else:
            given, surname = split_placeholder_name(text)
            entry.update(name=text, given=given, surname=surname)
        self._tidy(cap.capture_id)
        self.save()

    # --- links --------------------------------------------------------
    def link(self, cid, tree_id):
        """Handle of the primary Person linked in this tree, or None."""
        entry = self._entry(cid)
        return (entry.get("people") or {}).get(tree_id) if entry else None

    def set_link(self, cid, tree_id, handle):
        """Link (or with handle None, unlink) the primary Person."""
        entry = self._entry(cid, create=True)
        people = entry.setdefault("people", {})
        if handle:
            people[tree_id] = handle
        else:
            people.pop(tree_id, None)
        self._tidy(cid)
        self.save()

    def links(self, tree_id):
        """{capture_id: person handle} for every capture linked in this tree."""
        found = {}
        for cid, entry in self.captures.items():
            handle = (entry.get("people") or {}).get(tree_id)
            if handle:
                found[cid] = handle
        return found
