# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2000-2006  Donald N. Allingham
# Copyright (C) 2008       Brian G. Matherly
# Copyright (C) 2010       Jakim Friant
# Copyright (C) 2026       Claude Sonnet 5
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
from gramps.version import major_version, VERSION_TUPLE

# ------------------------------------------------------------------------
#
# Fuzzy Matching (built-in Soundex gramplet fork)
#
# ------------------------------------------------------------------------

if (5, 2, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        GRAMPLET,
        id="Fuzzy Matching",
        name=_("Fuzzy Matching"),
        description=_(
            "Gramplet for finding people in the Family Tree whose surname "
            "phonetically matches a given surname, using a cached per-tree "
            "index so it stays fast on large Family Trees"
        ),
        status=STABLE,
        version="0.5.4",
        gramps_target_version=major_version,
        fname="FuzzyMatchingGramplet.py",
        height=300,
        expand=True,
        gramplet="FuzzyMatchingGramplet",
        gramplet_title=_("Fuzzy Matching"),
        navtypes=["Person", "Media", "Note"],
        authors=["Claude"],
        maintainers=["Brian McCullough"],
        help_url="https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/Fuzzy/README.md",
        #help_url="https://gramps.discourse.group/t/9951/14",
        # https://gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#SoundEx
    )

    # ------------------------------------------------------------------
    #
    # Fuzzy Match API (library, for other addons)
    #
    # ------------------------------------------------------------------
    # A GENERAL plugin, not a hard-coded "every addon's folder is on
    # sys.path" assumption: Gramps only adds an addon's own folder to
    # sys.path *while it is itself importing that addon's registered
    # module* (see BasePluginManager.import_plugin()'s own docstring),
    # not permanently for the rest of the session. A bare
    # `import FuzzyMatchLookupWindow` from a *different* addon has no
    # such guarantee and does not work reliably. Another addon looks
    # this up via BasePluginManager.get_instance().get_plugin("Fuzzy
    # Match API"), then .import_plugin(pdata) to get the module itself
    # - see FuzzyMatchAPI.md for the full calling convention, and
    # PhotoTaggingGramplet.py's _get_fuzzy_match_lookup() for a worked
    # example. load_on_reg is deliberately False: nothing needs this
    # imported at every Gramps startup regardless of whether any other
    # installed addon actually calls it - only the one call site above
    # (via import_plugin) triggers the import, on demand.
    register(
        GENERAL,
        id="Fuzzy Match API",
        name=_("Fuzzy Match API"),
        description=_(
            "Library for other addons: phonetic surname matching "
            "(fuzzy_match_index.py), person-display formatting "
            "(fuzzy_match_display.py), and a standalone lookup window "
            "(FuzzyMatchLookupWindow.py) for a quick 'does someone like "
            "this already exist' check from another plugin. See "
            "FuzzyMatchAPI.md in this addon's own folder for the "
            "calling convention."
        ),
        status=STABLE,
        version="0.5.1",
        gramps_target_version=major_version,
        category="FuzzyMatching",
        fname="FuzzyMatchLookupWindow.py",
        load_on_reg=False,
        authors=["Claude"],
        maintainers=["Brian McCullough"],
    )
