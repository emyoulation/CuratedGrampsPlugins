#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Brian McCullough
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
"""Registration for MarkdownUtils, a shared Markdown-rendering/icon-resolution
library used by Markdown Dash, Plugin Manager plus, and other addons.

Ships bundled in a parent folder (plugins/MarkdownBased/) together with
the Markdown-based addons that use it, each in its own subfolder. Each
consuming addon puts that parent folder on ``sys.path`` before importing
``MarkdownUtils``. GENERAL is Gramps' own "Plugin library" category (see
``PTYPE_STR`` in ``gramps/gen/plug/_pluginreg.py``) -- there is nothing
here for a user to launch; this registration exists so Gramps' addon
installer (``load_addon_file()``) has a valid ``.gpr.py`` to find in this
package, and so MarkdownUtils appears, versioned, in Plugin Manager like
any other addon it distributes alongside.

DO NOT set requires_mod here -- MarkdownUtils does not depend on itself.
Consuming addons cannot use requires_mod=["MarkdownUtils"] either, with
this layout: Gramps checks requires_mod during its startup registration
scan (``Requirements.check_mod()`` in ``gramps/gen/utils/requirements.py``,
called from ``gramps/gen/plug/_pluginreg.py``), before any addon has put
plugins/MarkdownBased/ on ``sys.path``, so the check would fail and
Gramps would silently drop the addon. Consuming addons instead import
MarkdownUtils inside ``try``/``except ImportError`` and fall back to
plain text (or a small stand-in) when it is missing.
"""

from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# MarkdownUtils (shared library)
#
# ------------------------------------------------------------------------
if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GENERAL,
        id="MarkdownUtils",
        name=_("Markdown Utils"),
        description=_(
            "Shared Markdown rendering and icon-resolution library used by "
            "Markdown Dash, Plugin Manager plus, and other addons. Not a "
            "tool or gramplet itself -- installed so those addons can "
            "import it."
        ),
        version="0.2.0",  # build 20261009.2042
        gramps_target_version=major_version,
        status=STABLE,
        fname="MarkdownUtils.py",
        authors=["Claude AI"],
        authors_email=[""],
        maintainers=["Brian McCullough"],
        maintainers_email=["emyoulation@yahoo.com"],
        include_in_listing=True,
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/MarkdownBased",
    )
