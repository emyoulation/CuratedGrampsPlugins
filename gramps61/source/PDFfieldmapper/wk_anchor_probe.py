#!/usr/bin/env python3
"""
Show how wkhtmltopdf names the anchors (named destinations) of a PDF.

Run this on the machine that builds the manuals, with the same wkhtmltopdf:

    python3 wk_anchor_probe.py [--wkhtmltopdf /path/to/wkhtmltopdf]

It builds a tiny consolidated manual in several ways and prints the destination
names that each way produces:

  A, B  links written as GrampsUserManual.html#<id> (as the sed scripts do now),
        built in a shallow and in a deep folder: do the names contain the folder?
  C, D  links written as #<id> only, built in the same two folders
  E     built through a local web server, so the address is the same on every machine

Needs: wkhtmltopdf, python3 and pypdf.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

from pypdf import PdfReader

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # keep the screen for the results
        pass


PAGE = """<html><head><meta charset="utf-8"><title>Probe manual</title></head><body>
<h1>Contents</h1>
<p>See <a href="{link}#L9-3-Address_Editor_dialog">Address Editor</a> and <a href="{link}#L14-Tools_Overview">Tools</a>.</p>
<div style="page-break-before:always"><h2 id="L9-3-Address_Editor_dialog">Address Editor dialog</h2><p>text</p></div>
<div style="page-break-before:always"><h2 id="L14-Tools_Overview">Tools overview</h2><p>text</p>
<h3 id="L14-Never_linked_heading">Never linked heading</h3><p>text</p></div>
</body></html>"""


def names_of(pdf):
    reader = PdfReader(pdf)
    producer = (reader.metadata or {}).get("/Producer")
    return producer, sorted(str(key).lstrip("/") for key in reader.named_destinations)


def show(label, pdf):
    producer, names = names_of(pdf)
    print(f"\n{label}   [{producer}]")
    if not names:
        print("      no named destinations in this PDF")
    for name in names:
        print("      ", name)
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wkhtmltopdf", default="wkhtmltopdf")
    args = parser.parse_args()
    root = tempfile.mkdtemp(prefix="wk_probe_")
    results = {}

    def build(label, subdir, link, url=None):
        folder = os.path.join(root, subdir)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "GrampsUserManual.html"), "w", encoding="utf-8") as handle:
            handle.write(PAGE.format(link=link))
        out = os.path.join(root, label + ".pdf")
        source = url or os.path.join(folder, "GrampsUserManual.html")
        subprocess.run([args.wkhtmltopdf, "-q", "--enable-local-file-access", source, out], cwd=folder, check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        results[label] = show(f"{label}: {subdir} / links '{link or '(fragment only)'}'", out)

    build("A", "shallow/en", "GrampsUserManual.html")
    build("B", "a/much/deeper/folder/en", "GrampsUserManual.html")
    build("C", "shallow_c/en", "")
    build("D", "a/much/deeper/folder_c/en", "")
    folder = os.path.join(root, "web/en")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "GrampsUserManual.html"), "w", encoding="utf-8") as handle:
        handle.write(PAGE.format(link="GrampsUserManual.html"))
    server = HTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=folder))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = os.path.join(root, "E.pdf")
    subprocess.run([args.wkhtmltopdf, "-q", f"http://127.0.0.1:{server.server_port}/GrampsUserManual.html", out],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    server.shutdown()
    results["E"] = show("E: through a local web server, links 'GrampsUserManual.html'", out)

    print("\n--- what this means ---")
    if not any(results.values()):
        print("This wkhtmltopdf writes no named destinations at all (an unpatched Qt build?). Use the build that made the manuals.")
        return
    carries_path = any("/" in n.split("#")[0] and "://" in n for names in (results["A"], results["B"]) for n in names)
    print("names carry the build folder:           ", "YES" if carries_path else "no")
    print("shallow and deep folders give same names:", "yes" if results["A"] == results["B"] else "NO (the folder is part of the name)")
    print("fragment-only links change the names:    ", "yes" if results["C"] != results["A"] else "no")
    print("fragment-only names, shallow = deep:     ", "yes" if results["C"] == results["D"] else "NO")
    print("local web server gives a fixed address:  ", "yes" if results["E"] else "no names produced")


if __name__ == "__main__":
    main()
