#!/usr/bin/env python3
"""
Classify addon releases in an addons-source checkout.

addons-source bumps an addon's version every time its package is rebuilt,
including rebuilds that only bring new translations (make.py do_tar() always
calls increment_target()). This script walks the branch history, finds each
version change of each addon, and labels it:

    translations  only translations (po/*-local.po, locale/) changed, plus
                  the version line and perhaps po/template.pot
    docs          documentation or images, perhaps with translations
    version       nothing a user would notice: only the version line and
                  perhaps po/template.pot changed (manual bumps, rebuilds)
    code          anything else (Python, Glade, other .gpr.py lines ...)
    new           the first version seen for the addon

Every release also gets "translated": true when its translations changed,
so a code release that also brings translations can be shown as such.

Output (JSON): {"format": 1, "branch": ..., "generated": ...,
                "addons": {folder: [{"version", "kind", "translated", "date",
                                     "commit"}...]}}
newest release first.  Needs a full-history clone (not --depth).

Example:

    python3 classify_releases.py --addons ../addons-source --branch gramps60 \
        --out ../site/gramps60/releases.json --summary
"""

import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys

FORMAT = 1
VERSION_RE = re.compile(r"""^\s*version\s*=\s*["']([^"']+)["']""", re.M)
DOC_EXT = (".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf")


def git(repo, *args):
    """Run git in repo and return stdout."""
    return subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        check=True,
        errors="replace",
    ).stdout


def gpr_version(repo, commit, path):
    """Version string in a .gpr.py at commit, or None."""
    try:
        text = git(repo, "show", "%s:%s" % (commit, path))
    except subprocess.CalledProcessError:
        return None
    match = VERSION_RE.search(text)
    return match.group(1) if match else None


def mainline(repo, since=None):
    """
    First-parent history, oldest first: [(commit, date, [changed paths])].

    Merges are compared with their first parent, so a merged pull request and
    the version bump made while merging it count as one change.
    """
    args = ["log", "--first-parent", "-m", "--reverse", "--name-only"]
    args += ["--format=\x01%H %cI"]
    if since:
        args.append("--since=%s" % since)
    out = git(repo, *args)
    commits = []
    for block in out.split("\x01")[1:]:
        lines = [line for line in block.splitlines() if line.strip()]
        commit, date = lines[0].split(" ", 1)
        commits.append((commit, date, lines[1:]))
    return commits


def is_translation_path(rel):
    """po/ or locale/ inside an addon folder."""
    parts = rel.split("/")
    return len(parts) > 1 and parts[1] in ("po", "locale")


def gpr_only_version_changed(repo, old, new, path):
    """True if the .gpr.py differs between old and new only in version lines."""
    try:
        diff = git(repo, "diff", "-U0", old, new, "--", path)
    except subprocess.CalledProcessError:
        return False
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@", "diff ", "index ")):
            continue
        if line[:1] in "+-":
            body = line[1:].strip()
            if not body or VERSION_RE.match(body) or body.startswith("#"):
                continue
            return False
    return True


def classify(repo, addon, old, new):
    """(kind, translated) of the change to addon between commits old and new."""
    try:
        changed = git(repo, "diff", "--name-only", old, new, "--", addon + "/")
    except subprocess.CalledProcessError:
        return "code", False
    translated = docs = code = False
    for rel in changed.splitlines():
        if is_translation_path(rel):
            if not rel.endswith("/template.pot"):
                translated = True
        elif rel.endswith(".gpr.py"):
            if not gpr_only_version_changed(repo, old, new, rel):
                code = True
        elif rel.lower().endswith(DOC_EXT) or "/screenshots/" in rel:
            docs = True
        else:
            code = True
    if code:
        kind = "code"
    elif docs:
        kind = "docs"
    elif translated:
        kind = "translations"
    else:
        kind = "version"
    return kind, translated


def walk(repo):
    """{addon: [release dicts, oldest first]} for the whole branch."""
    versions = {}  # gpr path -> current version
    last = {}  # addon -> commit of its previous release
    releases = collections.defaultdict(list)
    for commit, date, paths in mainline(repo):
        touched = {}
        for rel in paths:
            if rel.endswith(".gpr.py") and rel.count("/") == 1:
                touched.setdefault(rel.split("/")[0], []).append(rel)
        for addon, gprs in touched.items():
            bumped = None
            for path in gprs:
                new = gpr_version(repo, commit, path)
                if new and new != versions.get(path):
                    versions[path] = new
                    bumped = new
            if not bumped:
                continue
            if addon in last:
                kind, translated = classify(repo, addon, last[addon], commit)
            else:
                kind, translated = "new", False
            releases[addon].append(
                {
                    "version": bumped,
                    "kind": kind,
                    "translated": translated,
                    "date": date[:10],
                    "commit": commit,
                }
            )
            last[addon] = commit
    return releases


def summary(releases, since):
    """Print counts of release kinds since a date."""
    counts = collections.Counter()
    with_translations = 0
    for items in releases.values():
        for item in items:
            if item["date"] >= since:
                counts[item["kind"]] += 1
                if item["kind"] == "code" and item["translated"]:
                    with_translations += 1
    total = sum(counts.values())
    print("Releases since %s: %d" % (since, total))
    for kind in ("code", "translations", "docs", "version", "new"):
        share = 100.0 * counts[kind] / total if total else 0
        print("  %-13s %4d  (%.0f%%)" % (kind, counts[kind], share))
    print("  code releases that also changed translations: %d" % with_translations)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--addons", required=True, help="addons-source checkout")
    parser.add_argument("--branch", default="", help="e.g. gramps60 (for output)")
    parser.add_argument("--out", help="write releases JSON here")
    parser.add_argument("--keep", type=int, default=20, help="releases per addon")
    parser.add_argument(
        "--summary",
        nargs="?",
        const=(datetime.date.today() - datetime.timedelta(days=365)).isoformat(),
        help="print counts since this date (default: one year ago)",
    )
    args = parser.parse_args()

    if git(args.addons, "rev-parse", "--is-shallow-repository").strip() == "true":
        sys.exit("needs full history: clone without --depth")
    releases = walk(args.addons)
    if args.summary:
        summary(releases, args.summary)
    if args.out:
        data = {
            "format": FORMAT,
            "branch": args.branch,
            "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "addons": {
                addon: list(reversed(items))[: args.keep]
                for addon, items in sorted(releases.items())
            },
        }
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fp:
            json.dump(data, fp, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
