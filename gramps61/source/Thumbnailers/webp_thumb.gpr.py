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

"""
Gramps plugin registration for WebP thumbnailer plugin.

Author: Brian McCullough
Development: AI-assisted using OpenAI (GPT-5.3-Codex)
Date: April 2026
"""

import mimetypes

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.version import major_version, VERSION_TUPLE

_ = glocale.translation.gettext

if VERSION_TUPLE >= (5, 2, 0):
    # Gramps classifies new Media with mimetypes.guess_type(). Some Python
    # builds (e.g. Gramps 5.2.3 for Windows, Python 3.11) do not know ".webp",
    # so the Media gets MIME "unknown" and no thumbnailer is ever asked.
    # Registered here, not in webp_thumb.py, because this file runs at
    # startup while the thumbnailer module is only loaded on first use,
    # which can be after the MIME type of the first import was guessed.
    # Only added when missing, so a platform mapping is never overridden.
    if mimetypes.guess_type("x.webp")[0] is None:
        mimetypes.add_type("image/webp", ".webp")

    register(
        THUMBNAILER,
        id="webpthumb",
        name=_("WebP Thumbnailer"),
        description=_("Dedicated thumbnailer for WEBP format images"),
        version="0.1.5",  # build 20261124.0420
        gramps_target_version=major_version,
        status=EXPERIMENTAL,
        order=START,
        fname="webp_thumb.py",
        thumbnailer="WebPThumb",
        authors=["OpenAI (GPT-5.3-Codex)"],
        authors_email=["https://openai.com"],
        maintainers=["Brian McCullough"],
        maintainers_email=["emyoulation@yahoo.com"],
        requires_gi=[("GdkPixbuf", "2.0")],
        help_url="https://gramps.discourse.group/t/webp-image-not-supported/8246/5",
    )
