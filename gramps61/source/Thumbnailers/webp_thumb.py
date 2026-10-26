#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026 OpenAI (GPT-5.3-Codex)
# Copyright (C) 2026 Claude AI (wish coding by Brian McCullough)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""A dedicated thumbnailer addon for WEBP images."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import importlib
import importlib.util
import logging
import os
import shutil
import subprocess
import tempfile

# -------------------------------------------------------------------------
#
# GTK/Gnome modules
#
# -------------------------------------------------------------------------
import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.const import THUMBSCALE, THUMBSCALE_LARGE, SIZE_LARGE
from gramps.gen.plug import Thumbnailer

# -------------------------------------------------------------------------
#
# Constants
#
# -------------------------------------------------------------------------
LOG = logging.getLogger(".thumbnail")


def _crop_box(rectangle, width, height):
    """
    Convert a Gramps region (percent corners) into a pixel box
    (left, top, right, bottom), or None for the whole image.
    """
    if rectangle is None:
        return None
    left = int(min(rectangle[0], rectangle[2]) / 100.0 * width)
    right = int(max(rectangle[0], rectangle[2]) / 100.0 * width)
    top = int(min(rectangle[1], rectangle[3]) / 100.0 * height)
    bottom = int(max(rectangle[1], rectangle[3]) / 100.0 * height)
    if right > left and bottom > top:
        return left, top, right, bottom
    return None


def _thumb_size(width, height, size):
    """Scaled (width, height) for the requested Gramps thumbnail size."""
    thumbscale = THUMBSCALE_LARGE if size == SIZE_LARGE else THUMBSCALE
    scale = thumbscale / float(max(width, height))
    return max(1, int(width * scale)), max(1, int(height * scale))


def _pixbuf_to_thumb(pixbuf, dest_file, size, rectangle):
    """Crop, scale and save a GdkPixbuf as the PNG thumbnail."""
    box = _crop_box(rectangle, pixbuf.get_width(), pixbuf.get_height())
    if box:
        left, top, right, bottom = box
        pixbuf = pixbuf.new_subpixbuf(left, top, right - left, bottom - top)
    new_w, new_h = _thumb_size(pixbuf.get_width(), pixbuf.get_height(), size)
    pixbuf = pixbuf.scale_simple(new_w, new_h, GdkPixbuf.InterpType.BILINEAR)
    # Option keys/values must be lists: newer PyGObject (Fedora 44) rejects
    # "" with "Unable to marshal str as an array". Same call as core
    # gramps/plugins/thumbnailer/imagethumb.py.
    pixbuf.savev(dest_file, "png", [], [])


class WebPThumb(Thumbnailer):
    """Thumbnailer implementation for image/webp."""

    MIME_TYPE = "image/webp"

    def is_supported(self, mime_type):
        """Return True only for WEBP MIME."""
        return mime_type == self.MIME_TYPE

    def run(self, mime_type, src_file, dest_file, size, rectangle):
        """
        Build a thumbnail by scaling a WEBP image and writing PNG output.
        Tries GdkPixbuf, then Pillow, then ffmpeg.
        """
        detected_type = self._detect_content_type(src_file)
        if detected_type is not None and detected_type != mime_type:
            LOG.warning(
                "MIME/content mismatch for thumbnail decode: "
                "mime=%s detected=%s file=%s",
                mime_type,
                detected_type,
                src_file,
            )

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(src_file)
        except Exception as err:  # no WEBP loader, or damaged file
            LOG.info(
                "GdkPixbuf cannot decode WEBP, trying Pillow: %s (%s)", err, src_file
            )
            return self._run_with_pillow(src_file, dest_file, size, rectangle)

        try:
            _pixbuf_to_thumb(pixbuf, dest_file, size, rectangle)
            return True
        except Exception as err:
            LOG.warning(
                "GdkPixbuf decoded WEBP but writing the thumbnail failed, "
                "trying Pillow: %s (%s)",
                err,
                src_file,
            )
            return self._run_with_pillow(src_file, dest_file, size, rectangle)

    def _run_with_pillow(self, src_file, dest_file, size, rectangle):
        """
        Fallback renderer using Pillow if GdkPixbuf cannot decode WEBP.
        """
        if importlib.util.find_spec("PIL.Image") is None:
            LOG.warning("Pillow fallback unavailable; PIL.Image not installed")
            return self._run_with_ffmpeg(src_file, dest_file, size, rectangle)

        image_mod = importlib.import_module("PIL.Image")
        pil_features = importlib.import_module("PIL.features")
        LOG.debug(
            "Pillow fallback: WEBP codec available=%s, file=%s",
            pil_features.check("webp"),
            src_file,
        )

        try:
            with image_mod.open(src_file) as image:
                box = _crop_box(rectangle, *image.size)
                if box:
                    image = image.crop(box)
                image = image.resize(_thumb_size(*image.size, size))
                image.save(dest_file, format="PNG")
            return True
        except Exception as err:
            LOG.warning("Pillow WEBP fallback failed: %s", err)
            self._log_webp_signature(src_file)
            return self._run_with_ffmpeg(src_file, dest_file, size, rectangle)

    def _run_with_ffmpeg(self, src_file, dest_file, size, rectangle):
        """
        Final fallback: use ffmpeg to decode the first frame, then scale as PNG.
        """
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            LOG.warning(
                "No WEBP thumbnail for %s: ffmpeg fallback unavailable "
                "(executable not found)",
                src_file,
            )
            return False

        with tempfile.TemporaryDirectory(prefix="gramps_webp_thumb_") as temp_dir:
            decoded_path = os.path.join(temp_dir, "decoded.png")
            cmd = [
                ffmpeg_path,
                "-v",
                "error",
                "-y",
                "-i",
                src_file,
                "-frames:v",
                "1",
                decoded_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                LOG.warning("ffmpeg WEBP fallback failed: %s", result.stderr.strip())
                return False

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(decoded_path)
                _pixbuf_to_thumb(pixbuf, dest_file, size, rectangle)
                LOG.info("ffmpeg WEBP fallback succeeded for file=%s", src_file)
                return True
            except Exception as err:
                LOG.warning("ffmpeg decode succeeded but PNG scaling failed: %s", err)
                return False

    def _log_webp_signature(self, src_file):
        """
        Log WEBP signature diagnostics to help identify mislabeled/corrupt files.
        """
        try:
            with open(src_file, "rb") as file_handle:
                header = file_handle.read(16)
            has_riff = len(header) >= 12 and header[0:4] == b"RIFF"
            has_webp = len(header) >= 12 and header[8:12] == b"WEBP"
            has_avif_ftyp = (
                len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] == b"avif"
            )
            LOG.warning(
                "WEBP header diagnostic: riff=%s webp=%s avif_ftyp=%s "
                "header_hex=%s file=%s",
                has_riff,
                has_webp,
                has_avif_ftyp,
                header.hex(),
                src_file,
            )
            if has_avif_ftyp:
                LOG.warning(
                    "File appears to be AVIF data mislabeled as WEBP: %s", src_file
                )
        except Exception as err:
            LOG.warning("WEBP header diagnostic failed: %s", err)

    def _detect_content_type(self, src_file):
        """
        Best-effort content signature check for WEBP/AVIF.
        """
        try:
            with open(src_file, "rb") as file_handle:
                header = file_handle.read(16)
            if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
                return "image/webp"
            if (
                len(header) >= 12
                and header[4:8] == b"ftyp"
                and header[8:12] in (b"avif", b"avis")
            ):
                return "image/avif"
        except Exception as err:
            LOG.warning("Content signature detection failed: %s", err)
        return None
