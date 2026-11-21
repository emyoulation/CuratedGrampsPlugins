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

Optionally, a newer branch can lend its translations (--donor-gramps,
--donor-addons). Weblate follows one branch at a time, so once translators
move to the next Gramps branch, the older branch stops getting translations
even for strings that are word-for-word the same. With a donor, a translated
entry from the donor branch wins over the older branch's entry for the same
string (msgctxt + msgid); strings the older branch does not have are dropped.

Requires the GNU gettext tools (msgfmt, msgmerge, msgcat, msgattrib) on PATH.

Example:

    python3 build_translation_packs.py --branch gramps60 \
        --gramps ../gramps --addons ../addons-source --out ../site

    python3 build_translation_packs.py --branch gramps60 \
        --gramps ../gramps60 --addons ../addons60 \
        --donor-gramps ../gramps61 --donor-addons ../addons61 --out ../site
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


def run(cmd):
    """Run a gettext tool. Returns an error string or None."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return result.stderr.strip() or "%s failed" % cmd[0]
    return None


def with_donor(po_file, donor_po, tmp_dir, tag):
    """
    A .po combining po_file with the translated entries of donor_po; the
    donor wins for identical strings. Returns (path, error); path is po_file
    itself when there is no donor file.
    """
    if not donor_po or not os.path.isfile(donor_po):
        return po_file, None
    clean = os.path.join(tmp_dir, "%s-donor.po" % tag)
    combined = os.path.join(tmp_dir, "%s-combined.po" % tag)
    # Only finished donor work: no fuzzy, untranslated or obsolete entries.
    # --force-po: gettext tools write no file at all when the result is
    # empty (a donor language with nothing translated yet).
    error = run(
        [
            "msgattrib",
            "--force-po",
            "--translated",
            "--no-fuzzy",
            "--no-obsolete",
            "-o",
            clean,
            donor_po,
        ]
    )
    if error:
        return po_file, error
    # --use-first: the donor translation wins; the header comes from the
    # donor too, which only matters for Plural-Forms (the same per language).
    error = run(["msgcat", "--force-po", "--use-first", "-o", combined, clean, po_file])
    if os.path.exists(clean):
        os.remove(clean)
    if error:
        return po_file, error
    return combined, None


def restrict(po_file, pot, out_po):
    """Keep only the strings in pot (no fuzzy guesses). Returns an error."""
    return run(
        [
            "msgmerge",
            "--quiet",
            "--force-po",
            "--for-msgfmt",
            "--no-fuzzy-matching",
            "-o",
            out_po,
            po_file,
            pot,
        ]
    )


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


def build_addon(addons_src, lang, addon, out_dir, tmp_dir, lang_po=None):
    """
    Extract one addon's strings from the aggregated Weblate po and compile it.

    Mirrors make.py extract_po(): msgmerge --for-msgfmt --no-fuzzy-matching.
    Returns (addon, entry-dict or None, error or None).
    """
    lang_po = lang_po or os.path.join(addons_src, "po", f"{lang}.po")
    pot = os.path.join(addons_src, addon, "po", "template.pot")
    tmp_po = os.path.join(tmp_dir, f"{lang}-{addon}.po")
    result = subprocess.run(
        [
            "msgmerge",
            "--quiet",
            "--force-po",
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
    if os.path.exists(tmp_po):
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
    parser.add_argument(
        "--donor-gramps", help="newer gramps checkout lending translations"
    )
    parser.add_argument(
        "--donor-addons", help="newer addons-source checkout lending translations"
    )
    parser.add_argument("--out", required=True, help="output site directory")
    parser.add_argument("--languages", default="", help="comma list; default all")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    parser.add_argument(
        "--strict", action="store_true", help="also run msgfmt --check-format"
    )
    args = parser.parse_args()
    global STRICT  # pylint: disable=global-statement
    STRICT = args.strict

    for tool in ("msgfmt", "msgmerge", "msgcat", "msgattrib"):
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
    for key, path in (
        ("donor_gramps", args.donor_gramps),
        ("donor_addons", args.donor_addons),
    ):
        if path:
            sources[key] = {"commit": git_commit(path), "date": git_date(path)}
    core_pot = os.path.join(args.gramps, "po", "gramps.pot") if args.gramps else ""
    if args.donor_gramps and not os.path.isfile(core_pot):
        sys.exit("--donor-gramps needs po/gramps.pot in --gramps")

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
                error = None
                if args.donor_gramps:
                    donor = os.path.join(args.donor_gramps, "po", f"{lang}.po")
                    combined, error = with_donor(po_file, donor, tmp_dir, lang)
                    if not error and combined != po_file:
                        merged = os.path.join(tmp_dir, f"{lang}-core.po")
                        error = restrict(combined, core_pot, merged)
                        if os.path.exists(combined):
                            os.remove(combined)
                        po_file = merged
                if not error:
                    error = compile_po(po_file, mo_file)
                plain = os.path.join(args.gramps, "po", f"{lang}.po")
                if error and po_file != plain:
                    # A broken donor entry must not cost the branch its own
                    # translation: fall back to the branch file alone.
                    print(f"[{lang}] core donor dropped: {error}", file=sys.stderr)
                    error = compile_po(plain, mo_file)
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
                lang_po = os.path.join(args.addons, "po", f"{lang}.po")
                if args.donor_addons:
                    donor = os.path.join(args.donor_addons, "po", f"{lang}.po")
                    lang_po, error = with_donor(
                        lang_po, donor, tmp_dir, f"{lang}-addons"
                    )
                    if error:
                        problems += 1
                        print(f"[{lang}] addon donor skipped: {error}", file=sys.stderr)
                with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                    jobs = [
                        pool.submit(
                            build_addon,
                            args.addons,
                            lang,
                            addon,
                            out_dir,
                            tmp_dir,
                            lang_po,
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
