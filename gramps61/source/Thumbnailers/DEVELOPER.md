# WebP and AVIF thumbnailers for Gramps — developer notes
<!-- -->
[README.md](README.md) • [CHANGELOG.md](CHANGELOG.md) • [DEVELOPER.md](DEVELOPER.md) • [.webp and .avif format (native) support in the primary OSes](webp_and_avif.md)
This document is for developers. It holds the original specification and coding plan for format-specific thumbnailer addons, and notes on how the WebP Thumbnailer was actually built. For installation and use, see [README.md](README.md).

## Current state
The WebP part of the plan is built and published; the AVIF part is not part of this addon.

| Plan | Built as |
|---|---|
| Addon folder `WebPThumbnailer/` | Package and folder `Thumbnailers/` (`Thumbnailers.addon.tgz`), so that more thumbnailers can join it later |
| `WebPThumbnailer.gpr.py` | `webp_thumb.gpr.py`, plugin id `webpthumb`, `order=START`, `requires_gi=[("GdkPixbuf", "2.0")]` |
| `WebPThumbnailer.py` | `webp_thumb.py`, class `WebPThumb` |
| Decoders: GdkPixbuf, then Pillow | GdkPixbuf, then Pillow, then FFmpeg (first frame, decoded to a temporary PNG) |
| Strict `image/webp` matching | `is_supported()` matches `image/webp` exactly |
| Clear failure reporting | Content signature check (WEBP or AVIF data) before decoding, and a header dump when all decoders fail |

### Implementation notes
- **Thumbnail output:** `run(mime_type, src_file, dest_file, size, rectangle)` writes a PNG to `dest_file` and returns `True`, or returns `False` so that Gramps tries the next thumbnailer. Gramps does not cache a failed thumbnail and tries again the next time.
- **Shared crop and scale:** `_crop_box()` turns a Gramps region (corner coordinates in percent) into a pixel box, and `_thumb_size()` scales the long side to `THUMBSCALE` (96) or `THUMBSCALE_LARGE` (180). All three decoders use them.
- **Saving with GdkPixbuf:** call `pixbuf.savev(dest_file, "png", [], [])`, as in the core `imagethumb.py`. The option keys and values must be lists. Older PyGObject versions accept empty strings, but newer ones (for example on Fedora 44) fail with "Unable to marshal str as an array". An earlier version had this bug: every save failed after a good decode, and the Pillow fallback did the work again.
- **Log levels:** WARNING only for real failures, damaged or mislabeled files and MIME mismatches; INFO when a fallback decoder is used; DEBUG for the Pillow codec diagnostic. Messages use the `.thumbnail` logger, like the core thumbnailers.
- **Thumbnail cache:** the cache file name is the MD5 of the source path plus the region, in separate folders for the normal and large sizes. One picture with regions therefore has several cache files, each made once.

### Testing notes
- The PyGObject in some test containers accepts the old empty-string `savev` call. To reproduce the Fedora 44 behavior, replace `GdkPixbuf.Pixbuf.savev` with a wrapper that raises `TypeError` when the option arguments are strings.
- Test cases used for this fix: normal and large sizes, a region, a 5000×2 picture (which gave a zero-size thumbnail before the fix), and a real WebP file through the Pillow path. The fixed module produces the same thumbnails with no warnings.

## Original specification
This section keeps the specification that started the work. It updates the approach to use **separate addon plugins per format** rather than changing the built-in Gramps thumbnailers.

### Development note credit
- Technical draft and implementation plan prepared with assistance from **GPT-5.3-Codex (OpenAI)**.
- Final integration and testing decisions remain with repository maintainers.

### Key architecture observation from built-in thumbnailers
From the behavior of the built-in Gramps thumbnailers:
1. `ImageThumb` handles generic `image/*` decoding through `GdkPixbuf` and writes PNG thumbnail output.
2. `GnomeThumb` delegates to system `.thumbnailer` entries based on the MIME type.

This means that WEBP and AVIF failures are usually environment or decoder registration problems. Addons can avoid the ambiguity by providing explicit format-specific thumbnailer plugins.

### Specification: two separate addon thumbnailer plugins
Create **two addons** (or one addon package with two plugin registrations):
- `WebPThumbnailer` for MIME type `image/webp`
- `AvifThumbnailer` for MIME type `image/avif`

Each plugin should:
- Implement `is_supported(mime_type)` with an explicit exact match for one MIME type.
- Implement `run()` / `generate_thumbnail()` to decode the source media, scale and crop as required by Gramps thumbnail conventions, and write PNG output.
- Return failure cleanly when the required codec support is unavailable.
- Keep user-visible messages translated with `_()`.

### Why separate plugins per format
- Clear diagnostics: failures can be attributed to WEBP or AVIF independently.
- Cleaner dependency handling: AVIF support may be unavailable while WEBP works.
- Easier maintenance and targeted bug reports.

### Addon registration approach (not built-in)
- Add plugin registration files in addon folders (for example `webp_thumb.gpr.py` and `avif_thumb.gpr.py`), so that installation and removal are independent from Gramps core.
- Do not modify the built-in files in `gramps/plugins/thumbnailer`.
- Use addon metadata (`id`, `name`, `description`, `version`, `gramps_target_version`) consistent with other addons in this repository.

### Decoder strategy
Preferred strategy for each plugin:
1. Try the `GdkPixbuf` decode path first (if a loader exists).
2. Fall back to the Pillow decode path if Pillow is available and built with the required codec.
3. If neither path works, report a clear error in the log or user interface and skip the thumbnail.

This preserves compatibility across Linux distributions where codec availability varies.

### Development coding plan
1. Create the addon folder `WebPThumbnailer/`.
    - Add the `WebPThumbnailer.gpr.py` registration.
    - Add the `WebPThumbnailer.py` implementation with strict `image/webp` support.
2. Create the addon folder `AvifThumbnailer/`.
    - Add the `AvifThumbnailer.gpr.py` registration.
    - Add the `AvifThumbnailer.py` implementation with strict `image/avif` support.
3. Add shared utility helpers only if duplication becomes significant; keep each plugin independently installable.
4. Add tests for:
    - MIME matching behavior.
    - The decode success and failure path for each format.
    - The shape and size of the generated thumbnail.
5. Document platform prerequisites (GdkPixbuf loader and/or Pillow codec libraries).

#### Coding plan credit
- Initial coding plan prepared with assistance from **GPT-5.3-Codex (OpenAI)**.

### Verification checklist
1. Install only the `WebPThumbnailer` addon and check that WEBP thumbnails are created.
2. Install only the `AvifThumbnailer` addon and check that AVIF thumbnails are created.
3. Check the behavior when codec support is intentionally missing.
4. Run the Gramps thumbnail regeneration and confirm that there are no regressions for JPEG and PNG.

### Refined prompt re-statement (per AGENTS.md directive)
Below is a refined user prompt set that would produce the intended final output for this work item:
1. **Architecture prompt:** "Design thumbnail support for WEBP and AVIF as **addons only** (no changes to Gramps built-ins), and use **separate plugins per format**."
2. **Plugin scope prompt:** "Create two addon plugin specs: `WebPThumbnailer` for `image/webp` and `AvifThumbnailer` for `image/avif`, each with independent registration and implementation files."
3. **Behavior prompt:** "Specify explicit MIME matching, decode/resize/crop logic, PNG thumbnail output, translated user messages, and graceful failure when codecs are unavailable."
4. **Dependency prompt:** "Use decoder preference order: `GdkPixbuf` first, Pillow fallback second, and document platform codec prerequisites."
5. **Delivery prompt:** "Include a development coding plan, verification checklist, and explicit development credit attribution in both the note and coding plan."

This refined prompt bundle is the direct requirements trace for the specification in this document.
