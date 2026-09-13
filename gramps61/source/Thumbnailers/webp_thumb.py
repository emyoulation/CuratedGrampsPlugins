#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026 OpenAI (GPT-5.3-Codex)
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
import logging
import importlib
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


class WebPThumb(Thumbnailer):
    """Thumbnailer implementation for image/webp."""

    MIME_TYPE = "image/webp"

    def is_supported(self, mime_type):
        """Return True only for WEBP MIME."""
        return mime_type == self.MIME_TYPE

    def run(self, mime_type, src_file, dest_file, size, rectangle):
        """
        Build a thumbnail by scaling a WEBP image and writing PNG output.
        """
        detected_type = self._detect_content_type(src_file)
        if detected_type is not None and detected_type != mime_type:
            LOG.warning(
                "MIME/content mismatch for thumbnail decode: mime=%s detected=%s file=%s",
                mime_type,
                detected_type,
                src_file,
            )

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(src_file)
            width = pixbuf.get_width()
            height = pixbuf.get_height()

            if rectangle is not None:
                upper_x = min(rectangle[0], rectangle[2]) / 100.0
                lower_x = max(rectangle[0], rectangle[2]) / 100.0
                upper_y = min(rectangle[1], rectangle[3]) / 100.0
                lower_y = max(rectangle[1], rectangle[3]) / 100.0

                sub_x = int(upper_x * width)
                sub_y = int(upper_y * height)
                sub_width = int((lower_x - upper_x) * width)
                sub_height = int((lower_y - upper_y) * height)

                if sub_width > 0 and sub_height > 0:
                    pixbuf = pixbuf.new_subpixbuf(sub_x, sub_y, sub_width, sub_height)
                    width = sub_width
                    height = sub_height

            thumbscale = THUMBSCALE_LARGE if size == SIZE_LARGE else THUMBSCALE
            scale = thumbscale / float(max(width, height))

            scaled_width = int(width * scale)
            scaled_height = int(height * scale)

            pixbuf = pixbuf.scale_simple(
                scaled_width, scaled_height, GdkPixbuf.InterpType.BILINEAR
            )
            pixbuf.savev(dest_file, "png", "", "")
            return True
        except Exception as err:
            LOG.warning("GdkPixbuf WEBP decode failed, trying Pillow fallback: %s",
                        str(err))
            return self._run_with_pillow(src_file, dest_file, size, rectangle)

    def _run_with_pillow(self, src_file, dest_file, size, rectangle):
        """
        Fallback renderer using Pillow if GdkPixbuf cannot decode WEBP.
        """
        pil_spec = importlib.util.find_spec("PIL.Image")
        if pil_spec is None:
            LOG.warning("Pillow fallback unavailable; PIL.Image not installed")
            return False

        Image = importlib.import_module("PIL.Image")
        pil_features = importlib.import_module("PIL.features")
        webp_codec_available = pil_features.check("webp")
        LOG.warning(
            "Pillow fallback diagnostic: WEBP codec available=%s, file=%s",
            webp_codec_available,
            src_file,
        )

        try:
            image = Image.open(src_file)
            width, height = image.size

            if rectangle is not None:
                upper_x = min(rectangle[0], rectangle[2]) / 100.0
                lower_x = max(rectangle[0], rectangle[2]) / 100.0
                upper_y = min(rectangle[1], rectangle[3]) / 100.0
                lower_y = max(rectangle[1], rectangle[3]) / 100.0

                left = int(upper_x * width)
                top = int(upper_y * height)
                right = int(lower_x * width)
                bottom = int(lower_y * height)

                if right > left and bottom > top:
                    image = image.crop((left, top, right, bottom))
                    width, height = image.size

            thumbscale = THUMBSCALE_LARGE if size == SIZE_LARGE else THUMBSCALE
            scale = thumbscale / float(max(width, height))
            scaled_width = max(1, int(width * scale))
            scaled_height = max(1, int(height * scale))

            image = image.resize((scaled_width, scaled_height))
            image.save(dest_file, format="PNG")
            return True
        except Exception as err:
            LOG.warning("Pillow WEBP fallback failed: %s", str(err))
            self._log_webp_signature(src_file)
            return self._run_with_ffmpeg(src_file, dest_file, size, rectangle)

    def _run_with_ffmpeg(self, src_file, dest_file, size, rectangle):
        """
        Final fallback: use ffmpeg to decode the first frame, then scale as PNG.
        """
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            LOG.warning("ffmpeg fallback unavailable; ffmpeg executable not found")
            return False

        with tempfile.TemporaryDirectory(prefix="gramps_webp_thumb_") as temp_dir:
            decoded_path = os.path.join(temp_dir, "decoded.png")
            cmd = [
                ffmpeg_path,
                "-v", "error",
                "-y",
                "-i", src_file,
                "-frames:v", "1",
                decoded_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                LOG.warning("ffmpeg WEBP fallback failed: %s", result.stderr.strip())
                return False

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(decoded_path)
                width = pixbuf.get_width()
                height = pixbuf.get_height()

                if rectangle is not None:
                    upper_x = min(rectangle[0], rectangle[2]) / 100.0
                    lower_x = max(rectangle[0], rectangle[2]) / 100.0
                    upper_y = min(rectangle[1], rectangle[3]) / 100.0
                    lower_y = max(rectangle[1], rectangle[3]) / 100.0

                    sub_x = int(upper_x * width)
                    sub_y = int(upper_y * height)
                    sub_width = int((lower_x - upper_x) * width)
                    sub_height = int((lower_y - upper_y) * height)

                    if sub_width > 0 and sub_height > 0:
                        pixbuf = pixbuf.new_subpixbuf(sub_x, sub_y, sub_width, sub_height)
                        width = sub_width
                        height = sub_height

                thumbscale = THUMBSCALE_LARGE if size == SIZE_LARGE else THUMBSCALE
                scale = thumbscale / float(max(width, height))
                scaled_width = max(1, int(width * scale))
                scaled_height = max(1, int(height * scale))

                pixbuf = pixbuf.scale_simple(
                    scaled_width, scaled_height, GdkPixbuf.InterpType.BILINEAR
                )
                pixbuf.savev(dest_file, "png", "", "")
                LOG.warning("ffmpeg WEBP fallback succeeded for file=%s", src_file)
                return True
            except Exception as err:
                LOG.warning("ffmpeg decode succeeded but PNG scaling failed: %s", str(err))
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
            has_avif_ftyp = len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] == b"avif"
            LOG.warning(
                "WEBP header diagnostic: riff=%s webp=%s avif_ftyp=%s header_hex=%s file=%s",
                has_riff,
                has_webp,
                has_avif_ftyp,
                header.hex(),
                src_file,
            )
            if has_avif_ftyp:
                LOG.warning(
                    "File appears to be AVIF data mislabeled as WEBP: %s",
                    src_file,
                )
        except Exception as err:
            LOG.warning("WEBP header diagnostic failed: %s", str(err))

    def _detect_content_type(self, src_file):
        """
        Best-effort content signature check for WEBP/AVIF.
        """
        try:
            with open(src_file, "rb") as file_handle:
                header = file_handle.read(16)
            if len(header) >= 12 and header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
                return "image/webp"
            if len(header) >= 12 and header[4:8] == b"ftyp" and header[8:12] in (b"avif", b"avis"):
                return "image/avif"
        except Exception as err:
            LOG.warning("Content signature detection failed: %s", str(err))
        return None
