#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026      Claude AI (wish coding by Brian McCullough)
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
Tip of the Day Fix: a monkey patch for gramps.gui.tipofday.

Tip of the Day splits each tip into paragraphs on the exact text "<br/>" and
shows the result as Pango markup. When a tip arrives with its line break
written any other way ("<br></br>", "<br>", "<br />"), for example from a
tips.xml built with a gettext version that writes empty elements differently,
or from a translation, the text is not split and GTK rejects the markup:

    Gtk-WARNING: Failed to set text '<markup>...<br></br>...</markup>' from
    markup due to error parsing markup: Unknown tag 'br'

The patch writes every line break as "<br/>" at the two places a tip passes
through: TipOfDay.escape() before the translation lookup (so the English text
matches its translation again) and the module's _() after it (in case a
translation has the odd form). Gramps 5.2, 6.0 and 6.1 all use both.
"""

import logging
import re

LOG = logging.getLogger(".TipOfDayFix")

# <br>, <br/>, <br />, <BR>, optionally followed by a closing </br>; or a
# stray </br> on its own.
_BREAK = re.compile(r"<br\s*/?>(?:\s*</br>)?|</br>", re.IGNORECASE)
_MARK = "_tip_of_day_fix"


def normalize_breaks(text):
    """Write every line break in a tip as <br/>."""
    if not isinstance(text, str) or "br" not in text.lower():
        return text
    return _BREAK.sub("<br/>", text)


def _patched_escape(self, text):
    return _patched_escape.__wrapped__(self, normalize_breaks(text))


def _wrap_gettext(gettext):
    def gettext_fixed(message):
        return normalize_breaks(gettext(normalize_breaks(message)))

    gettext_fixed.__wrapped__ = gettext
    setattr(gettext_fixed, _MARK, True)
    return gettext_fixed


def install():
    """Patch gramps.gui.tipofday (idempotent). Returns True if patched."""
    from gramps.gui import tipofday  # pylint: disable=import-outside-toplevel

    patched = False
    cls = getattr(tipofday, "TipOfDay", None)
    escape = getattr(cls, "escape", None)
    if escape is not None and not getattr(escape, _MARK, False):
        _patched_escape.__wrapped__ = escape
        setattr(_patched_escape, _MARK, True)
        cls.escape = _patched_escape
        patched = True
    gettext = getattr(tipofday, "_", None)
    if callable(gettext) and not getattr(gettext, _MARK, False):
        tipofday._ = _wrap_gettext(gettext)  # pylint: disable=protected-access
        patched = True
    if escape is None or not callable(gettext):
        LOG.warning("Tip of the Day Fix: Gramps' Tip of the Day code has changed")
    return patched


def load_on_reg(dbstate, uistate, plugin):  # pylint: disable=unused-argument
    """Called by Gramps at startup."""
    try:
        install()
    except Exception:  # pylint: disable=broad-except
        LOG.warning("Tip of the Day Fix could not be installed", exc_info=True)
    return []
