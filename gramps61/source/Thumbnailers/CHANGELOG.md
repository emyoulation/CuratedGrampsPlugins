# Changelog — WebP Thumbnailer
<!-- -->
[README.md](README.md) • [CHANGELOG.md](CHANGELOG.md) • [DEVELOPER.md](DEVELOPER.md) • [.webp and .avif format (native) support in the primary OSes](webp_and_avif.md)
## 0.1.5 — 2026-11-24
### Fixed
- WebP images imported on systems where Python does not know the `.webp` extension (reported for Gramps 5.2.3 on Windows 10, Python 3.11) are now recorded with the MIME type `image/webp` instead of `unknown`, so they get a thumbnail. The addon registers the type at Gramps startup, and only when it is missing. Gramps 6.0.8 on Windows (Python 3.14) already knew the type and is not changed.
- Media records imported before this fix keep their stored `unknown` MIME type. Those records must be corrected separately.

### Credits
- Problem report, tested fix and Dynamic Web Extended check: [johnvitlin](https://github.com/johnvitlin) in [issue #4](https://github.com/emyoulation/CuratedGrampsPlugins/issues/4). Placement at startup: Claude (Anthropic, Claude Opus 5.5), wish coding by Brian McCullough.

## 0.1.4 — 2026-10-26
### Fixed
- Thumbnails are now written by GdkPixbuf as intended. The save call passed empty strings where lists are required, and newer PyGObject (for example on Fedora 44) rejects that with the message "Unable to marshal str as an array". Every WEBP thumbnail then failed after a successful decode and was made a second time by the Pillow fallback, with two log warnings each time.
- The same mistake in the ffmpeg fallback is fixed.
- A very wide or very tall image no longer gives a thumbnail with a size of zero and a GdkPixbuf-CRITICAL message.
- The Pillow fallback no longer depends on another module having imported `importlib.util` first.
- The image file opened by the Pillow fallback is now closed after use.

### Changed
- One shared function now crops and scales the image for all three decoders (GdkPixbuf, Pillow and ffmpeg), instead of three copies of the same code.
- The log tells a decode failure apart from a save failure.
- Log levels: the Pillow codec diagnostic is now DEBUG, and "GdkPixbuf cannot decode" and "ffmpeg fallback succeeded" are now INFO. WARNING is kept for real failures, damaged or mislabeled files, and MIME mismatches.

### Documentation
- README: credits for the creators of the WebP format (Google, On2 Technologies for VP8, Jyrki Alakuijala for lossless compression, and the authors of RFC 9649).
- README rewritten as a user document: what the addon does, WebP images in Gramps (with the GdkPixbuf WebP loader packages), installation with the Addon Manager from the Emyoulation collection or by hand, thumbnails and thumbnailers in Gramps, and troubleshooting.
- The development specification and coding plan moved from the README to the new DEVELOPER.md, with notes on how the addon was actually built.
- README, CHANGELOG and DEVELOPER: title, GUI control line and navigation links as the first three lines.

### Credits
- Fixes: Claude (Anthropic, Claude Opus 5.5), wish coding by Brian McCullough.

## 0.1.0 to 0.1.3 — 2026-04
First versions, made with OpenAI GPT-5.3-Codex.
- Thumbnailer for `image/webp` only, writing PNG thumbnails in the normal and large Gramps sizes, with support for regions.
- Decoders tried in order: GdkPixbuf, Pillow, then ffmpeg (first frame).
- Diagnostics for mislabeled or damaged files: content signature check (WEBP or AVIF data) and a header dump.
