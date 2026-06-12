# -*- coding: utf-8 -*-
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2007-2008  Douglas S. Blank
# Copyright (C) 2000-2007  Donald N. Allingham
# Copyright (C) 2008       Raphael Ackerman
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2011       Tim G L Lyons
# Copyright (C) 2013       Vassilii Khachaturov
# Copyright (C) 2026       Douglas S. Blank
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
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.
#

# ------------------------
# Gramps modules
# ------------------------
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.version import major_version

_ = glocale.translation.gettext

# ── CSV Enhanced import ─────────────────────────────────────────────

register(
    IMPORT,
    id="im_csv_enhanced",
    name=_("Comma Separated Values Spreadsheet (CSV) — Enhanced"),
    description=_("Import data from CSV files (enhanced: events, citations, media)"),
    version="1.1.0",
    gramps_target_version=major_version,
    status=EXPERIMENTAL,
    audience=EXPERT,
    fname="importcsv.py",
    import_function="importData",
    extension="csv",
    help_url="Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#Gramps_CSV_import",
)

# ── CSV Enhanced export ─────────────────────────────────────────────

register(
    EXPORT,
    id="ex_csv_enhanced",
    name=_("Comma Separated Values Spreadsheet (CSV) — Enhanced"),
    name_accell=_("Comma _Separated Values Spreadsheet (CSV) — Enhanced"),
    description=_(
        "CSV is a common spreadsheet format."
        "\nThis enhanced exporter includes events, citations, and media."
        "\nYou can change this behavior in the 'Configure active"
        " view' of any list-based view"
    ),
    version="1.1.0",
    gramps_target_version=major_version,
    status=EXPERIMENTAL,
    audience=EXPERT,
    fname="exportcsv.py",
    export_function="exportData",
    export_options="CSVWriterOptionBox",
    export_options_title=_("CSV spreadsheet options"),
    extension="csv",
    help_url="Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#csv_export",
)
