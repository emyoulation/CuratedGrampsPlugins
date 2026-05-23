# encoding:utf-8
#
# Gramps plugin - a GTK+/GNOME based genealogy program extension
#
# Copyright (C) 2009 Benny Malengier
# Copyright (C) 2011 Nick Hall
# Copyright (C) 2011 Tim G L Lyons
# Copyright (C) 2023 Brian McCullough
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

# ------------------------------------------------------------------------
#
# Gramps modules
#
# ------------------------------------------------------------------------

# from gramps.gen.plug._pluginreg import register, STABLE, BETA, EXPERIMENTAL, UNSTABLE, DEVELOPER, GRAMPLET
# from gramps.gen.const import GRAMPS_LOCALE as glocale
# _ = glocale.translation.sgettext

MODULE_VERSION = "5.2"

# ------------------------------------------------------------------------
#
# Register Gramps plugin
#
# ------------------------------------------------------------------------

register(GRAMPLET,
         id="Beta What's Next",
         name=_("Beta What's Next"), # shown in menus
         description=_("Beta Gramplet suggesting items to research"),
         gramplet='BetaWhatNextGramplet',
         gramplet_title=_("β What's Next?"), # shown in tab/dialog titlebar
         fname="Betawhatsnext.py",
         version = '0.1.7',
         status=STABLE,
         audience=EVERYONE,
         gramps_target_version=MODULE_VERSION,
         authors=["Reinhard Mueller", "Jakim Friant"],
         authors_email=["", "jmodule@friant.org"],
         maintainers=["Brian McCullough"],
         maintainers_email=["emyoulation@yahoo.com"],
         height=300,
         expand=True,
         help_url="Gramps_5.2_Wiki_Manual_-_Gramplets#What.27s_Next",
         )
