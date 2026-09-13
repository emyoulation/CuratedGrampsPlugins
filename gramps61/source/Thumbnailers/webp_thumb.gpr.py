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

"""
Gramps plugin registration for WebP thumbnailer plugin.

Author: Brian McCullough
Development: AI-assisted using OpenAI (GPT-5.3-Codex)
Date: April 2026
"""

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.version import major_version, VERSION_TUPLE

_ = glocale.translation.gettext

if VERSION_TUPLE >= (5, 2, 0):
    register(
        THUMBNAILER,
        id="webpthumb",
        name=_("WebP Thumbnailer"),
        description=_("Dedicated thumbnailer for WEBP format images"),
        version="0.1.3",
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
