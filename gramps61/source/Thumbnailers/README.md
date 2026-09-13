#  Thumbnailer plug-ins for Gramps
[README.md](README.md) • [.webp and .avif format (native) support in the primary OSes](webp_and_avif.md)

## WEBP and AVIF thumbnailers in Gramps (Addon Specification)

This note updates the specification to use **separate addon plugins per format**
rather than changing built-in Gramps thumbnailers.

### Development note credit

- Technical draft and implementation plan prepared with assistance from
  **GPT-5.3-Codex (OpenAI)**.
- Final integration and testing decisions remain with repository maintainers.

### Key architecture observation from built-in thumbnailers

From Gramps built-in thumbnailer behavior:

1. `ImageThumb` handles generic `image/*` decoding via `GdkPixbuf` and writes PNG
   thumbnail output.
2. `GnomeThumb` delegates to system `.thumbnailer` entries based on MIME type.

This means WEBP/AVIF failures are usually environment/decoder registration
issues. For addons, we can bypass ambiguity by providing explicit format-specific
thumbnailer plugins.

### New specification: two separate addon thumbnailer plugins

Create **two addons** (or one addon package with two plugin registrations):

- `WebPThumbnailer` for MIME type `image/webp`
- `AvifThumbnailer` for MIME type `image/avif`

Each plugin should:

- Implement `is_supported(mime_type)` with an explicit exact match for one MIME.
- Implement `run()`/`generate_thumbnail()` to decode source media, scale/crop as
  required by Gramps thumbnail conventions, and write PNG output.
- Return failure cleanly when required codec support is unavailable.
- Keep user-visible messages translated with `_()`.

### Why separate plugins per format

- Clear diagnostics: failures can be attributed to WEBP vs AVIF independently.
- Cleaner dependency handling: AVIF support may be unavailable while WEBP works.
- Easier maintenance and targeted bug reports.

### Addon registration approach (not built-in)

- Add plugin registration files in addon directories (e.g., `webp_thumb.gpr.py`
  and `avif_thumb.gpr.py`) so installation/removal is independent from Gramps
  core.
- Do not modify `gramps/plugins/thumbnailer` built-in files.
- Use addon metadata (`id`, `name`, `description`, `version`, `gramps_target_version`)
  consistent with other addons in this repository.

### Decoder strategy

Preferred strategy per plugin:

1. Try `GdkPixbuf` decode path first (if loader exists).
2. Fallback to Pillow decode path if available and built with the required codec.
3. If neither path works, report a clear error in logs/UI and skip thumbnail.

This preserves compatibility across Linux distributions where codec availability
varies.

### Development coding plan

1. Create addon directory `WebPThumbnailer/`.
   - Add `WebPThumbnailer.gpr.py` registration.
   - Add `WebPThumbnailer.py` implementation with strict `image/webp` support.
2. Create addon directory `AvifThumbnailer/`.
   - Add `AvifThumbnailer.gpr.py` registration.
   - Add `AvifThumbnailer.py` implementation with strict `image/avif` support.
3. Add shared utility helpers only if duplication becomes significant; keep each
   plugin independently installable.
4. Add tests for:
   - MIME matching behavior.
   - decode success/failure path per format.
   - thumbnail output generation shape/size.
5. Document platform prerequisites (gdk-pixbuf loader and/or Pillow codec libs).

#### Coding plan credit

- Initial coding plan prepared with assistance from
  **GPT-5.3-Codex (OpenAI)**.

### Verification checklist

1. Install only `WebPThumbnailer` addon and validate WEBP thumbnails are created.
2. Install only `AvifThumbnailer` addon and validate AVIF thumbnails are created.
3. Validate behavior when codec support is intentionally missing.
4. Run Gramps thumbnail regeneration utility and confirm no regressions on JPEG/PNG.

### Refined prompt re-statement (per AGENTS.md directive)

Below is a refined user prompt set that would produce the intended final output
for this work item:

1. **Architecture prompt**
   - "Design thumbnail support for WEBP and AVIF as **addons only** (no changes to
     Gramps built-ins), and use **separate plugins per format**."
2. **Plugin scope prompt**
   - "Create two addon plugin specs:
     `WebPThumbnailer` for `image/webp` and `AvifThumbnailer` for `image/avif`,
     each with independent registration and implementation files."
3. **Behavior prompt**
   - "Specify explicit MIME matching, decode/resize/crop logic, PNG thumbnail
     output, translated user messages, and graceful failure when codecs are
     unavailable."
4. **Dependency prompt**
   - "Use decoder preference order: `GdkPixbuf` first, Pillow fallback second,
     and document platform codec prerequisites."
5. **Delivery prompt**
   - "Include a development coding plan, verification checklist, and explicit
     development credit attribution in both the note and coding plan."

This refined prompt bundle is the direct requirements trace for the final
specification in this document.

### See also:
* Discourse forum: [.webp and .avif format (native) support in the primary OSes](https://gramps.discourse.group/t/webp-and-avif-formats/9841)
