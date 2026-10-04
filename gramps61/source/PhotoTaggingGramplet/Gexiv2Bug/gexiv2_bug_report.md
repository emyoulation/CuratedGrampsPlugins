# gexiv2 fails to read `Xmp.mwg-rs.Regions` (structured/array XMP) when built against exiv2 0.28, while flat XMP tags read correctly

## Summary

`GExiv2.Metadata.get()` returns nothing for a structured/array XMP
property (`Xmp.mwg-rs.Regions/mwg-rs:RegionList[n]/...`, the Metadata
Working Group "Regions" schema used for face/region tagging) on a
GNOME/Flathub runtime pairing **libgexiv2 2.14.2 with libexiv2 0.28.2**,
even for a minimal, well-formed, single-region test file. Flat XMP
properties (e.g. `Xmp.dc.subject`, keyword-list tags) read correctly on
the same runtime, from the same files. The identical structured
property reads correctly through:

- **GExiv2 0.10 + libgexiv2 0.14.2 + libexiv2 0.27.6** (Ubuntu 24.04
  packages)
- **exiv2 0.28.8** read directly (via the unrelated `pyexiv2` Python
  binding, which links its own bundled libexiv2 rather than going
  through gexiv2)

This narrows the fault to the specific **libgexiv2 build linked against
exiv2 0.28.x**, rather than to exiv2 itself (which handles the same
data correctly in both 0.27.6 and 0.28.8), the file content (which is
valid, well-formed XML, confirmed with `xmllint`), or gexiv2's general
XMP support (flat tags work fine on every combination tested).

## Environment

Reporting from two machines while diagnosing this from the Gramps
genealogy application's ["Photo Tagging" community
gramplet](https://gramps-project.org), which reads
`Xmp.mwg-rs.Regions` via GExiv2 to list named face regions embedded in
photos:

**Machine A -- exhibits the bug** (Fedora host, Gramps via Flathub):

- OS: Fedora (`fedora-vm`)
- Gramps: 5.2.1, installed via Flathub (`org.gramps_project.Gramps`,
  `stable` channel)
- Inside the Flatpak sandbox (`/app/lib/`):
  - `libexiv2.so.0.28.2` (SONAME `libexiv2.so.28`)
  - `libgexiv2.so.2.14.2` (SONAME `libgexiv2.so.2`)
- Host system (`rpm -q gexiv2`): **gexiv2 is not installed on the host
  at all** -- only used from inside the Flatpak sandbox
- Host `exiv2` CLI (a *separate* install, not what Gramps uses):
  version 0.27.6, `have_xmptoolkit=1`, `adobe_xmpsdk=0`,
  `libexpat.so.1.8.10`

**Machine B -- does not exhibit the bug** (used to isolate the fault):

- Ubuntu 24.04 (noble)
- `exiv2` CLI: 0.27.6, `have_xmptoolkit=1`, `adobe_xmpsdk=0`,
  `libexpat.so.1.9.1`
- `gir1.2-gexiv2-0.10` / `libgexiv2-2` (Ubuntu package): reports as
  libgexiv2 0.14.2, SONAME-linked to `libexiv2.so.27`
- Also tested exiv2 0.28.8 directly via the bundled library in the
  PyPI `pyexiv2` 2.16.0 wheel (a different, independent Python binding
  -- not gexiv2/GObject-Introspection-based)

## Steps to reproduce

1. Take the attached `test_combined_dc_and_mwg.jpg` (840x700 JPEG,
   EXIF orientation normal, no other complicating metadata). Its XMP
   packet contains exactly two properties:
   - `Xmp.dc.subject` = a plain `XmpBag` of two strings: `Marie Curie`,
     `Pierre Curie`
   - `Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name` = `Test
     Person` (plus a matching minimal `mwg-rs:Area` struct and
     `mwg-rs:Type` = `Face`), the standard MWG Regions schema shape.
   Both properties were confirmed present and well-formed with
   `exiv2 -pa` and `xmllint --noout` on the raw extracted XMP packet
   before embedding.
2. On Machine A (Flathub Gramps 5.2.1 / gexiv2 2.14.2 / exiv2 0.28.2),
   read this file with `GExiv2.Metadata`:
   ```python
   import gi
   gi.require_version("GExiv2", "0.10")
   from gi.repository import GExiv2

   m = GExiv2.Metadata("test_combined_dc_and_mwg.jpg")
   print(m.get("Xmp.dc.subject"))
   print(m.get("Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name"))
   ```
   (This can be run inside the Flatpak sandbox itself with:
   `flatpak run --command=python3 org.gramps_project.Gramps
   /path/to/script.py`, so it uses exactly the same GExiv2/libexiv2
   that the Gramps process does.)
3. Compare against Machine B (Ubuntu 24.04, gexiv2 2.14.2/libexiv2
   0.27.6) running the identical script against the identical file.

## Actual results

- **Machine A** (gexiv2 + exiv2 0.28.2): `Xmp.dc.subject` reads back
  the two names correctly (confirmed indirectly via a second, unrelated
  Gramps gramplet that uses gexiv2's general tag-enumeration API and
  displayed the `Xmp.dc / Subject / Marie Curie, Pierre Curie` row).
  `Xmp.mwg-rs.Regions/mwg-rs:RegionList[1]/mwg-rs:Name` produces no
  result -- nothing is shown for it anywhere, and (for this minimal
  file specifically) no error or warning is logged either.
  Separately, a larger/more complex file with multiple regions plus
  several other XMP schema blocks (Microsoft Photo, digiKam, Lightroom,
  ACDSee, etc. alongside `mwg-rs`) *did* additionally produce, on
  Machine A only:
  ```
  ** CRITICAL **: XMP Toolkit error 201: Error in XMLValidator
  ** WARNING **: Failed to decode XMP metadata.
  ```
  even though that file's raw XMP also validates cleanly with
  `xmllint` and reads back correctly (all regions, all schemas) via
  exiv2 0.28.8 directly through `pyexiv2`.
- **Machine B** (gexiv2 + exiv2 0.27.6): both properties read back
  correctly, including the more complex multi-region/multi-schema
  file, with no errors or warnings.

## Expected results

`Xmp.mwg-rs.Regions/mwg-rs:RegionList[n]/...` (or any structured/array
XMP property) should read consistently across gexiv2 builds regardless
of which exiv2 major version it's linked against, the same way flat
properties like `Xmp.dc.subject` already do.

## Additional notes / narrowing already done

- The XMP packets involved are confirmed well-formed XML
  (`xmllint --noout` exits 0) and are confirmed fully readable --
  including every `mwg-rs` region and the flat tags -- by exiv2 0.28.8
  itself when accessed directly (bypassing gexiv2 entirely) via the
  independent `pyexiv2` binding. This rules out both "malformed file"
  and "exiv2-level regression" as explanations.
- `libgexiv2.so.2.14.2` on Machine B is SONAME-linked specifically to
  `libexiv2.so.27` and cannot load `libexiv2.so.28` without being
  rebuilt; Machine A's identically-versioned `libgexiv2.so.2.14.2`
  must therefore be a separate build compiled against exiv2 0.28's
  ABI. That rebuild, not a change in gexiv2's own version number, is
  the most likely point where this regression was introduced --
  possibly in how gexiv2 enumerates/serializes `XmpData` array/struct
  members against exiv2 0.28's revised internal `Value`/`Metadatum`
  types.
- This was found while investigating why the Gramps "Photo Tagging"
  community gramplet's XMP-region-reading feature
  (`GExiv2.Metadata.get()` on indexed `mwg-rs:RegionList[n]` paths)
  produced empty results exclusively on Flathub-distributed Gramps,
  not on a native Ubuntu install using an older exiv2/gexiv2 pairing.

## Attachments

- `test_combined_dc_and_mwg.jpg` -- minimal reproduction file (one
  working flat tag, one non-working structured tag, nothing else in
  the XMP packet)

---

*Environment details and reproduction steps in this report were
compiled with the assistance of an AI coding tool (an Anthropic Claude
model) during interactive debugging; the underlying test files, log
output, and version information are from the reporter's own systems
and direct testing. Please let me know if any additional diagnostics
would help (e.g. running the reproduction script from Step 2 directly
inside the Flatpak sandbox, which hasn't been captured yet with its
own stdout/stderr).*
