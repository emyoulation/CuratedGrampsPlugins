#!/usr/bin/env python3
"""
Build Translation Updater language packs for one Gramps branch.

Reads the Weblate-maintained .po files from a checkout of gramps (core) and
addons-source, compiles them into .mo files and writes a manifest for each
language plus an index for the branch.  The client addon (TranslationUpdater)
downloads only what changed, by comparing sha256 hashes.

Output layout (under --out):

    <branch>/index.json
    <branch>/<lang>/manifest.json
    <branch>/<lang>/core/gramps.mo
    <branch>/<lang>/addons/<AddonFolder>.mo

Requires the GNU gettext tools (msgfmt, msgmerge) on PATH.

Example:

    python3 build_translation_packs.py --branch gramps60 \
        --gramps ../gramps --addons ../addons-source --out ../site
"""

import argparse
import concurrent.futures
import datetime
import glob
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile

FORMAT = 1


def git_date(path):
    """Committer date (ISO 8601) of HEAD in a checkout, or now if not git."""
    try:
        out = subprocess.run(
            ["git", "-C", path, "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if out:
            return out
    except (OSError, subprocess.CalledProcessError):
        pass
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def git_commit(path):
    """HEAD commit hash of a checkout, or empty string."""
    try:
        return subprocess.run(
            ["git", "-C", path, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def sha256(path):
    """Hex sha256 of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        for block in iter(lambda: fp.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def mo_count(path):
    """Number of translated messages in a .mo file (header excluded)."""
    with open(path, "rb") as fp:
        head = fp.read(12)
    magic = struct.unpack("<I", head[:4])[0]
    order = "<" if magic == 0x950412DE else ">"
    count = struct.unpack(order + "I", head[8:12])[0]
    return max(count - 1, 0)


STRICT = False


def compile_po(po_file, mo_file):
    """
    Compile a .po file. Returns an error string or None.

    Plain msgfmt by default, the same as Gramps' own setup.py, so packs match
    what a release would ship (Gramps tolerates some intentionally omitted
    date-format arguments).  --strict adds --check-format.
    """
    os.makedirs(os.path.dirname(mo_file), exist_ok=True)
    cmd = ["msgfmt", "-o", mo_file, po_file]
    if STRICT:
        cmd.insert(1, "--check-format")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        if os.path.exists(mo_file):
            os.remove(mo_file)
        return result.stderr.strip() or "msgfmt failed"
    return None


def languages_in(po_dir):
    """Language codes of the <lang>.po files in a po directory."""
    langs = set()
    for path in glob.glob(os.path.join(po_dir, "*.po")):
        code = os.path.basename(path)[:-3]
        if code and "-" not in code and code != "template":
            langs.add(code)
    return langs


def addon_folders(addons_src):
    """Addon folders that have a template.pot (i.e. translatable strings)."""
    return sorted(
        name
        for name in os.listdir(addons_src)
        if os.path.isfile(os.path.join(addons_src, name, "po", "template.pot"))
    )


def build_addon(addons_src, lang, addon, out_dir, tmp_dir):
    """
    Extract one addon's strings from the aggregated Weblate po and compile it.

    Mirrors make.py extract_po(): msgmerge --for-msgfmt --no-fuzzy-matching.
    Returns (addon, entry-dict or None, error or None).
    """
    lang_po = os.path.join(addons_src, "po", f"{lang}.po")
    pot = os.path.join(addons_src, addon, "po", "template.pot")
    tmp_po = os.path.join(tmp_dir, f"{lang}-{addon}.po")
    result = subprocess.run(
        [
            "msgmerge",
            "--quiet",
            "--for-msgfmt",
            "--no-fuzzy-matching",
            "-o",
            tmp_po,
            lang_po,
            pot,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return addon, None, result.stderr.strip() or "msgmerge failed"
    mo_file = os.path.join(out_dir, "addons", f"{addon}.mo")
    error = compile_po(tmp_po, mo_file)
    os.remove(tmp_po)
    if error:
        return addon, None, error
    count = mo_count(mo_file)
    if count == 0:
        os.remove(mo_file)
        return addon, None, None
    return (
        addon,
        {
            "path": f"addons/{addon}.mo",
            "sha256": sha256(mo_file),
            "size": os.path.getsize(mo_file),
            "translated": count,
        },
        None,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--branch", required=True, help="e.g. gramps60")
    parser.add_argument("--gramps", help="gramps checkout (core translations)")
    parser.add_argument("--addons", help="addons-source checkout")
    parser.add_argument("--out", required=True, help="output site directory")
    parser.add_argument("--languages", default="", help="comma list; default all")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    parser.add_argument(
        "--strict", action="store_true", help="also run msgfmt --check-format"
    )
    args = parser.parse_args()
    global STRICT  # pylint: disable=global-statement
    STRICT = args.strict

    for tool in ("msgfmt", "msgmerge"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found; install GNU gettext")

    core_langs = languages_in(os.path.join(args.gramps, "po")) if args.gramps else set()
    addon_langs = (
        languages_in(os.path.join(args.addons, "po")) if args.addons else set()
    )
    langs = sorted(core_langs | addon_langs)
    if args.languages:
        wanted = {code.strip() for code in args.languages.split(",") if code.strip()}
        langs = [code for code in langs if code in wanted]
    addons = addon_folders(args.addons) if args.addons else []

    branch_dir = os.path.join(args.out, args.branch)
    if os.path.isdir(branch_dir):
        shutil.rmtree(branch_dir)
    os.makedirs(branch_dir)

    generated = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    sources = {}
    if args.gramps:
        sources["gramps"] = {
            "commit": git_commit(args.gramps),
            "date": git_date(args.gramps),
        }
    if args.addons:
        sources["addons"] = {
            "commit": git_commit(args.addons),
            "date": git_date(args.addons),
        }

    index = {
        "format": FORMAT,
        "branch": args.branch,
        "generated": generated,
        "sources": sources,
        "languages": {},
    }
    problems = 0
    with tempfile.TemporaryDirectory() as tmp_dir:
        for lang in langs:
            out_dir = os.path.join(branch_dir, lang)
            manifest = {
                "format": FORMAT,
                "branch": args.branch,
                "lang": lang,
                "generated": generated,
                "sources": sources,
                "core": None,
                "addons": {},
            }
            if lang in core_langs:
                po_file = os.path.join(args.gramps, "po", f"{lang}.po")
                mo_file = os.path.join(out_dir, "core", "gramps.mo")
                error = compile_po(po_file, mo_file)
                if error:
                    problems += 1
                    print(f"[{lang}] core skipped: {error}", file=sys.stderr)
                else:
                    manifest["core"] = {
                        "path": "core/gramps.mo",
                        "sha256": sha256(mo_file),
                        "size": os.path.getsize(mo_file),
                        "translated": mo_count(mo_file),
                    }
            if lang in addon_langs:
                with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                    jobs = [
                        pool.submit(
                            build_addon, args.addons, lang, addon, out_dir, tmp_dir
                        )
                        for addon in addons
                    ]
                    for job in jobs:
                        addon, entry, error = job.result()
                        if error:
                            problems += 1
                            print(f"[{lang}] {addon} skipped: {error}", file=sys.stderr)
                        elif entry:
                            manifest["addons"][addon] = entry
            if not manifest["core"] and not manifest["addons"]:
                shutil.rmtree(out_dir, ignore_errors=True)
                continue
            os.makedirs(out_dir, exist_ok=True)
            with open(
                os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8"
            ) as fp:
                json.dump(manifest, fp, indent=1, sort_keys=True)
            index["languages"][lang] = {
                "core": bool(manifest["core"]),
                "addons": len(manifest["addons"]),
            }
            print(
                f"[{lang}] core={'yes' if manifest['core'] else 'no'} "
                f"addons={len(manifest['addons'])}"
            )

    with open(os.path.join(branch_dir, "index.json"), "w", encoding="utf-8") as fp:
        json.dump(index, fp, indent=1, sort_keys=True)
    print(f"{len(index['languages'])} languages written to {branch_dir}")
    if problems:
        print(f"{problems} item(s) skipped; see messages above", file=sys.stderr)


if __name__ == "__main__":
    main()
