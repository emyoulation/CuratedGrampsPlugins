#
# vcardenhanced.gpr.py — Gramps plugin registration for Enhanced vCard
# Import/Export addon (vCard versions 1, 2.1, 3.0, 4.0).
#
# This addon is a fork-and-hide workaround as described in GEPS 048
# (Format Negotiation Layer). It forks the built-in vCard importer and
# exporter, extends them with multi-version dialect support, and
# registers unique plugin IDs. Users (or the addon itself) should hide
# the built-in plugins "im_vcard" and "ex_vcard" via Addon Manager
# Enhanced once this addon is installed, to eliminate file-type
# ambiguity in the import/export dialog.
#
# ── Fork/Hide Workaround Notes (GEPS 048) ────────────────────────────
#
# HURDLE 1 – Unique plugin IDs
#   The built-in vCard plugins use IDs "im_vcard" and "ex_vcard"
#   (defined in gramps/plugins/lib/..gpr.py, not a standalone file).
#   If this addon reuses those IDs, Gramps raises a duplicate-plugin
#   error that is not clearly reported to the user — it silently drops
#   one registration or crashes on startup. IDs here are intentionally
#   distinct ("im_vcard_enh" / "ex_vcard_enh").
#
# HURDLE 2 – Amalgamated .gpr.py in core
#   The built-in vCard plugins are registered inside a shared
#   gramps/plugins/lib/...gpr.py file alongside many other plugins.
#   There is no standalone vcard.gpr.py to copy; the addon author must
#   create one from scratch. Gramps gives no actionable error if a
#   fname= points to a missing file — startup simply skips the plugin
#   silently.
#
# HURDLE 3 – Import paths differ in addons vs core
#   Core plugins import from relative paths (e.g. "from libgedcom import
#   ..."). Addon plugins must use fully qualified Gramps package paths
#   (e.g. "from gramps.plugins.lib.libgedcom import ...") or place
#   shared code in the addon's own directory. This addon is self-
#   contained.
#
# HURDLE 4 – Hiding the built-in
#   The automatic hide below calls into PluginRegister's hidden-plugin
#   infrastructure. In practice, Addon Manager Enhanced stores the
#   hidden-plugin list in a user config file; the exact API may vary
#   across Gramps versions. If the automatic hide fails silently, the
#   user must hide the built-ins manually via Addon Manager Enhanced.
#   A preference in the export options dialog allows toggling which
#   plugin is active.
#
# ─────────────────────────────────────────────────────────────────────

from gramps.version import major_version
from gramps.gen.const import GRAMPS_LOCALE as glocale
_ = glocale.translation.gettext

# ── Automatic hide of upstream built-in plugins (best-effort) ─────────
# This runs at registration time. If PluginRegister does not expose
# get_hidden_plugin_ids / save_hidden_plugin_ids in this Gramps version,
# the try/except swallows the error gracefully and the user must hide
# manually.

_UPSTREAM_IDS = ("im_vcard", "ex_vcard")

def _auto_hide_upstream():
    try:
        from gramps.gen.plug import PluginRegister
        pmgr = PluginRegister.get_instance()
        # The hidden-plugin set is stored in the user config managed by
        # Addon Manager Enhanced. Try both the standard attribute name and
        # the one used by Addon Manager Enhanced.
        if hasattr(pmgr, 'get_hidden_plugin_ids'):
            hidden = set(pmgr.get_hidden_plugin_ids())
            changed = False
            for pid in _UPSTREAM_IDS:
                if pid not in hidden:
                    hidden.add(pid)
                    changed = True
            if changed and hasattr(pmgr, 'save_hidden_plugin_ids'):
                pmgr.save_hidden_plugin_ids(hidden)
        # Addon Manager Enhanced may use a different attribute:
        elif hasattr(pmgr, '_hidden'):
            for pid in _UPSTREAM_IDS:
                pmgr._hidden.add(pid)
    except Exception:
        pass  # Silently degrade; user hides manually.

_auto_hide_upstream()
# ─────────────────────────────────────────────────────────────────────


# ── vCard Enhanced Import ─────────────────────────────────────────────
register(IMPORT,
    id          = "im_vcard_enh",
    name        = _("vCard (Enhanced — v1/2.1/3.0/4.0)"),
    description = _(
        "Import contacts from vCard files (.vcf). "
        "Supports vCard versions 1, 2.1, 3.0, and 4.0. "
        "Unhandled properties are preserved as Person attributes. "
        "Variant Call Format (DNA) files are detected and rejected."
    ),
    version     = "1.0.0",
    gramps_target_version = major_version,
    status      = STABLE,
    fname       = "importvcard_enh.py",
    import_function = "importData",
    extension   = "vcf",
    help_url    = "Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#Importing_data",
)

# ── vCard Enhanced Export ─────────────────────────────────────────────
register(EXPORT,
    id          = "ex_vcard_enh",
    name        = _("vCard (Enhanced — v1/2.1/3.0/4.0)"),
    name_accell = _("_vCard (Enhanced)"),
    description = _(
        "Export contacts to vCard files (.vcf). "
        "Supports vCard versions 1, 2.1, 3.0, and 4.0 (default: 3.0)."
    ),
    version     = "1.0.0",
    gramps_target_version = major_version,
    status      = STABLE,
    fname       = "exportvcard_enh.py",
    export_function     = "exportData",
    export_options      = "VCardVersionOptionBox",
    export_options_title = _("vCard export options"),
    extension   = "vcf",
    help_url    = "Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#vCard_export",
)
