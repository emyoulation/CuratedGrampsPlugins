# Supplanting Built-in Gramps GUI Dialogs with Addons

## A Developer's Guide to Load-on-Registration Monkey-Patching

***Monkey patching**  is the practice of dynamically modifying or extending the behavior of code—such as classes, modules, or functions—at runtime without changing the original source code.*

**Audience:** New Gramps addon developers familiar with Python and GTK basics  
**Gramps version:** 5.2+ / 6.1+ (examples tested against 6.1 APIs)  
**Reference implementation:** `PluginManagerPlus` by Paul Culley / Brian McCullough  
**Subject:** How to replace a built-in Gramps dialog class with an enhanced addon version, without modifying the Gramps core source.

---

## Table of Contents

1. [Background and Motivation](#1-background-and-motivation)
2. [The Gramps Plugin System: A Primer](#2-the-gramps-plugin-system-a-primer)
3. [The Two Mechanisms at Work](#3-the-two-mechanisms-at-work)
4. [Inside `_windows.py`: What You Are Replacing](#4-inside-_windowspy-what-you-are-replacing)
5. [Anatomy of PluginManagerPlus](#5-anatomy-of-pluginmanagerplus)
6. [Applying the Pattern: Supplanting the Addon Manager](#6-applying-the-pattern-supplanting-the-addon-manager)
7. [Step-by-Step: Building Your Own Replacement Addon](#7-step-by-step-building-your-own-replacement-addon)
8. [Key Gramps APIs Every Replacement Dialog Must Use](#8-key-gramps-apis-every-replacement-dialog-must-use)
9. [Internationalization](#9-internationalization)
10. [Coding Standards Compliance](#10-coding-standards-compliance)
11. [Testing Your Replacement](#11-testing-your-replacement)
12. [Pitfalls and Edge Cases](#12-pitfalls-and-edge-cases)
13. [Generalizing the Pattern to Other Built-in Dialogs](#13-generalizing-the-pattern-to-other-built-in-dialogs)
14. [Commit Message and AI Disclosure Requirements](#14-commit-message-and-ai-disclosure-requirements)
15. [Quick Reference Summary](#15-quick-reference-summary)
16. [References](#16-references)

---

## 1. Background and Motivation

Gramps is a mature GTK application with a rich plugin architecture. Its built-in dialogs — the Plugin Manager (`PluginStatus` in `gramps/gui/plug/_windows.py`) and the Addon Manager (`AddonManager` in the same file) — are useful but deliberately conservative in scope, since they must serve the broadest possible user base.

As an addon developer you may want to replace one of these dialogs entirely with an enhanced version: richer filtering, Markdown-rendered descriptions, clickable hyperlinks, screenshot previews, a search-as-you-type entry, or any other capability beyond what the built-in offers. The **correct** way to do this is **not** to fork or patch the Gramps core. Instead, Gramps's own plugin registration mechanism gives you hooks that, used together, let an addon take over a built-in dialog transparently at startup — no core changes, no forks, fully reversible by uninstalling the addon.

The `PluginManagerPlus` addon by Paul Culley and Brian McCullough is the canonical reference implementation of this technique. This paper dissects it and shows how to apply the same pattern to any other built-in class, with the Addon Manager as the worked example.

### Why not just submit a patch to core?

Core changes require community review, consensus, backward-compatibility analysis, and a release cycle. An addon ships immediately, works across multiple Gramps versions with a `VERSION_TUPLE` guard, can be experimental or user-specific, and is fully opt-in. The techniques described here are the right tool for any enhancement that is either too opinionated, too niche, or too fast-moving for the core codebase.

---

## 2. The Gramps Plugin System: A Primer

### 2.1 PluginRegister — the central registry

`gramps/gen/plug/_pluginreg.py` hosts the `PluginRegister` singleton. Every plugin in Gramps — whether built-in or user-installed — is registered here at startup by executing its `.gpr.py` file (a "Gramps Plugin Registration" file). Each registration call produces a `PluginData` object stored in a dictionary keyed by the plugin's `id` string.

```
PluginRegister._instance
    └── _plugindata: dict[str, PluginData]
            "PluginManager"   → PluginData(...)   # built-in entry
            "SomeReport"      → PluginData(...)
            ...
```

Because this is a plain Python dictionary, a later write to the same key **overwrites the earlier entry**. This is the first hook available to addon developers.

### 2.2 Load order: builtins first, user plugins second

When Gramps starts, it scans plugin directories in this order:

1. Gramps installation directories (builtins, shipped with Gramps itself)
2. User plugin directories (`~/.gramps/gramps6X/plugins/` etc.)

Each `.gpr.py` found is executed in turn, calling the `register(...)` function provided by the scan context. Because user directories are scanned **after** builtins, a user plugin that calls `register(..., id="PluginManager", ...)` will overwrite the built-in's entry in `PluginRegister._plugindata`. From that point on, any code that asks the registry for `"PluginManager"` will receive the addon's `PluginData`.

### 2.3 GENERAL plugins and `load_on_reg`

The `GENERAL` plugin type is a catch-all for utility plugins that do not fit the standard Report / Tool / View categories. When a `GENERAL` plugin is registered with `load_on_reg = True`, Gramps immediately imports and executes the Python file named in `fname` **at registration time** — before the main window appears, before any user action. This is the second hook.

The file named in `fname` is not the main class file. It is a small **loader file** whose only job is to run the monkey-patch. This separation keeps the large class file out of the import chain until it is actually needed, and it makes the loader's intent immediately clear to anyone reading the code.

### 2.4 Python module objects are mutable namespaces

Python's import system caches imported modules in `sys.modules`. Once `gramps.gui.plug._windows` is imported, its module object lives at `sys.modules["gramps.gui.plug._windows"]`. That module object is just a Python namespace — a dict-like object of names bound to values. You can write new values into it at any time:

```python
import gramps.gui.plug._windows as _win
_win.AddonManager = MyAddonManagerPlus  # replaces the class in the namespace
```

Every piece of code that subsequently accesses `_win.AddonManager` (or does `from gramps.gui.plug._windows import AddonManager` **after** this line runs) will get `MyAddonManagerPlus`. This is Python monkey-patching.

### 2.5 The Python import cache and module-level names

There is a subtlety you must understand. Consider two different import styles:

**Style A — lazy import (inside a function):**
```python
def cb_open_manager(self):
    from gramps.gui.plug._windows import AddonManager  # runs each time called
    AddonManager(self.dbstate, self.uistate, [])
```

**Style B — module-level import (at the top of the file):**
```python
from gramps.gui.plug._windows import AddonManager  # runs once at import time

class ViewManager:
    def cb_open_manager(self):
        AddonManager(self.dbstate, self.uistate, [])  # uses name cached above
```

In Style A, each time the function is called it re-executes the import statement, which looks up `AddonManager` fresh in `sys.modules["gramps.gui.plug._windows"]`. If you have patched `_windows.AddonManager`, the function will see the patched class.

In Style B, the name `AddonManager` in `viewmanager.py`'s namespace was bound **once**, when `viewmanager.py` was first imported. Patching `_windows.AddonManager` does not update that cached binding. You must also patch `viewmanager.AddonManager` directly.

This distinction determines how many places your loader needs to patch.

---

## 3. The Two Mechanisms at Work

For any given built-in dialog there are two distinct things that may need replacing:

| Layer | What is replaced | Mechanism |
|---|---|---|
| **Registry layer** | The `PluginData` entry in `PluginRegister` | Same `id` in `.gpr.py` overwrites the built-in's entry |
| **Python namespace layer** | The class object in the source module (and any cached references) | `load_on_reg` loader runs at startup and monkey-patches the module |

`PluginManagerPlus` uses **both** layers because the Plugin Manager is itself a registered plugin with a known `id`. The Addon Manager requires only the **Python namespace layer** because it is not a registered plugin — it is just a class invoked directly by the GUI. This distinction matters and is spelled out fully in Section 6.

### 3.1 Why both layers for the Plugin Manager

The built-in Plugin Manager is registered as a `GENERAL` plugin with `id = "PluginManager"`. When Gramps opens it from the Help menu, the call chain goes through the registry: Gramps asks `PluginRegister` for the `PluginData` with that id and then invokes whatever module and class it names. An addon that registers with the same `id` wins that lookup — its `PluginData` is what Gramps finds, so its class is what gets instantiated.

The monkey-patch in the loader is still needed to handle any code paths that bypass the registry and reference `_windows.PluginStatus` directly. Using both layers together gives full coverage and also ensures that the metadata visible in the plugin list (name, version, authors, help URL) reflects the addon, not the built-in.

### 3.2 Why only the namespace layer for the Addon Manager

`AddonManager` has no `id` in any `.gpr.py`. It is a plain Python class in `_windows.py` that calling code instantiates directly. There is no registry lookup involved. The monkey-patch alone is sufficient: replace the class in `_windows`'s namespace (and any cached references in calling modules), and every future instantiation of `AddonManager` anywhere in Gramps will get your class.

---

## 4. Inside `_windows.py`: What You Are Replacing

Before writing a replacement, study what you are replacing. Both target classes live in `gramps/gui/plug/_windows.py` (2383 lines, ~85 KB as of Gramps master).

### 4.1 Structure of `AddonManager`

`AddonManager` is a `ManagedWindow` subclass. Its key characteristics:

```python
class AddonManager(ManagedWindow):
    def __init__(self, dbstate, uistate, track):
        self.dbstate = dbstate
        self.title = _("Addon Manager")
        ManagedWindow.__init__(self, uistate, [], self)
        self.__pmgr = GuiPluginManager.get_instance()
        self.__preg = PluginRegister.get_instance()
        dialog = Gtk.Dialog(
            title="", transient_for=uistate.window, destroy_with_parent=True
        )
        dialog.add_button(_("Refresh"), RELOAD)
        dialog.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        dialog.add_button(_("_Help"), Gtk.ResponseType.HELP)
        self.set_window(dialog, None, self.title)
        self.req = Requirements()
        self.setup_configs("interface.addonmanager", 750, 400)
        self.window.connect("response", self.__on_dialog_button)
        ...
        self.show()
        self.refresh()
```

Internal helper classes used by `AddonManager`:

- `GetAddons(threading.Thread)` — background thread that fetches the addon list from the configured project URLs via `get_all_addons()`.
- `AddonRow(Gtk.ListBoxRow)` — a single row in the addon `Gtk.ListBox`, with Install / Update / Wiki / Requires buttons built inline.
- `ProjectRow(Gtk.ListBoxRow)` — a row in the Projects configuration tab.

Public methods of `AddonManager` that you will likely want to preserve or override:

| Method | Purpose |
|---|---|
| `refresh()` | Clears and reloads the addon list via a background `GetAddons` thread |
| `load_addons(addon_list)` | Populates the `Gtk.ListBox` from the fetched list |
| `install_addon(addon_id)` | Registers and loads a newly downloaded addon |
| `update_addon(addon_id)` | Reloads an updated addon's directory |
| `find_addon(addon_id)` | Looks up an addon dict by id from the cached list |
| `build_menu_names(obj)` | Required by `ManagedWindow`; returns the window title |
| `create_settings_panel()` | Builds the Settings tab widget tree |
| `create_projects_panel()` | Builds the Projects tab widget tree |
| `help()` | Opens the help wiki page |
| `edit_project(row)` | Opens the add/edit project dialog |
| `update_project_list()` | Rebuilds project combos after a change |

The `__filter_func(row)` method implements the addon list filtering logic. It checks the search text entry and all combo box selections. This is a prime candidate for enhancement in a replacement class.

### 4.2 Structure of `PluginStatus`

`PluginStatus` (the built-in Plugin Manager) inherits from both `tool.Tool` and `ManagedWindow`. Its `__init__` sets up a `Gtk.Dialog` with a `Gtk.VPaned` containing an info panel (top) and a plugin list (bottom). The list is a `Gtk.TreeView` backed by a `Gtk.ListStore`. It has columns for Type, Status, Name, Description, and ID.

The key difference from `AddonManager` is that `PluginStatus` manages **already registered and installed** plugins, while `AddonManager` manages plugins from **remote repositories** (available to download and install).

### 4.3 Supporting infrastructure in `_windows.py`

The file also defines several module-level items you may need:

```python
RELOAD = 777  # Custom Gtk response_type for the Refresh button

LOG = logging.getLogger(".gui.plug")  # logger used throughout the file

def display_message(message):  # simple print-based fallback
    print(message)
```

And it imports a broad set of Gramps utilities that your replacement will also
want to import:

```python
from gramps.gen.plug import (
    PluginRegister, PTYPE_STR, load_addon_file,
    AUDIENCETEXT, STATUSTEXT,
)
from gramps.gen.plug.utils import get_all_addons, available_updates
from gramps.gen.utils.requirements import Requirements
from gramps.gui.pluginmanager import GuiPluginManager
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.dialog import InfoDialog, OkDialog, QuestionDialog2
from gramps.gui.display import display_help, display_url
from gramps.gen.config import config
from gramps.gen.const import USER_PLUGINS, LIB_PATH
```

---

## 5. Anatomy of PluginManagerPlus

Understanding the real implementation solidifies the theory. The addon
consists of three primary files:

```
PluginManagerPlus/
├── PluginManagerPlus.gpr.py   # registration — triggers both mechanisms
├── PluginManagerLoad.py       # loader — performs the monkey-patch at startup
└── PluginManagerPlus.py       # the full enhanced PluginStatus replacement
```

### 5.1 `PluginManagerPlus.gpr.py` — the registration file

```python
from gramps.version import major_version, VERSION_TUPLE

if VERSION_TUPLE >= (5, 2, 0):
    register(
        GENERAL,
        id              = "PluginManager",        # ← same id as the built-in
        name            = _("Plugin Manager plus"),
        description     = "An Addon/Plugin Manager with several additional "
                          "capabilities",
        version         = '1.3.0',
        gramps_target_version = major_version,
        status          = EXPERIMENTAL,
        fname           = "PluginManagerLoad.py", # ← loader file, not the class
        authors         = ["Paul Culley", "Claude AI"],
        authors_email   = ["paulr2787@gmail.com"],
        maintainers     = ["Brian McCullough"],
        maintainers_email = ["emyoulation@yahoo.com"],
        category        = TOOL_UTILS,
        load_on_reg     = True,                   # ← execute at startup
        help_url        = 'Addon:Plugin_Manager_plus',
    )
```

The three critical fields are:

- **`id = "PluginManager"`** — collides intentionally with the built-in registration. The addon's `PluginData` overwrites the built-in's entry in
  `PluginRegister._plugindata`.
- **`fname = "PluginManagerLoad.py"`** — names the loader, not the large class file. Only the loader is executed eagerly; the class file is imported by the loader only when needed.
- **`load_on_reg = True`** — causes `PluginManagerLoad.py` to run immediately during the plugin scan, before the main Gramps window appears.

### 5.2 `PluginManagerLoad.py` — the monkey-patch loader

The loader is a small file with one job. It imports the enhanced class and
injects it into the `_windows` module namespace:

```python
# PluginManagerLoad.py

# ------------------------
# Python modules
# ------------------------
import logging
import sys

# ------------------------
# Gramps modules
# ------------------------
import gramps.gui.plug._windows as _windows

# ------------------------
# Gramps specific
# ------------------------
from PluginManagerPlus import PluginStatus as PluginStatusPlus

LOG = logging.getLogger(__name__)


def _patch() -> None:
    """Replace the built-in PluginStatus with the enhanced version.

    Patches both the source module and any module-level cached references
    found in sys.modules at the time this loader runs.
    """
    _windows.PluginStatus = PluginStatusPlus
    LOG.debug("PluginManagerPlus: patched _windows.PluginStatus")

    # Cover module-level cached imports in known call sites
    for mod_name in ["gramps.gui.plug", "gramps.gui.viewmanager"]:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "PluginStatus"):
            setattr(mod, "PluginStatus", PluginStatusPlus)
            LOG.debug("PluginManagerPlus: patched %s.PluginStatus", mod_name)


_patch()
```

> **Note:** The actual `PluginManagerLoad.py` in the repository may differ
> slightly from this reconstruction. The pattern described here accurately
> reflects the intent and the technique, as confirmed by the `.gpr.py` and the
> class structure in `PluginManagerPlus.py`.

### 5.3 `PluginManagerPlus.py` — the enhanced class

The main file (1876 lines) defines `PluginStatus` as a **full replacement** class (not a subclass of the built-in), inheriting from `tool.Tool` and `ManagedWindow` — exactly the same parent classes as the original. It adds:

- A two-column info panel: Markdown-rendered plugin details on the left, a thumbnail icon or screenshot on the right, via a `Gtk.Paned(HORIZONTAL)`.
- A Help ↔ Details toggle button that swaps between a README view (with screenshot) and the per-plugin registration details view.
- Clickable hyperlinks on file paths, help URLs, and author/maintainer emails.
- Boolean registration flags rendered as checkmark/cross icons rather than raw `True`/`False` text.
- A `Gtk.SearchEntry` in the button bar for live search filtering.
- Persistent pane-position storage using `PluginManagerOptions`.
- A `_MdInfoPane` helper class: a `Gtk.TextView`-based widget that renders Markdown text and handles link clicks, using `MarkdownUtils` if available.

The choice to write a full replacement (rather than a subclass) was made because the original `PluginStatus` layout — info panel below the list — was inverted, and the original used `Gtk.TreeView` while the replacement uses a custom layout. When the structural changes are extensive enough that `super().__init__()` would do more harm than good, a full replacement is the cleaner approach.

---

## 6. Applying the Pattern: Supplanting the Addon Manager

### 6.1 The key difference from the Plugin Manager case

| | Plugin Manager (`PluginStatus`) | Addon Manager (`AddonManager`) |
|---|---|---|
| Lives in | `gramps/gui/plug/_windows.py` | `gramps/gui/plug/_windows.py` |
| Registered plugin? | Yes — `id = "PluginManager"` | No — plain class |
| Registry collision needed? | Yes | No |
| Monkey-patch needed? | Yes | Yes |
| Loader approach | Same-id registration + patch | New unique id + patch only |

### 6.2 Finding every call site

Before writing your addon, audit every reference to `AddonManager` in the Gramps source. From a local checkout:

```bash
grep -rn "AddonManager" gramps/gui/ gramps/plugins/
```

As of Gramps master, the primary call sites are:

- **`gramps/gui/plug/_windows.py`** — class definition (the monkey-patch target itself).
- **`gramps/gui/configure.py`** — `AddonManager` is imported and instantiated   from the Preferences dialog's "Addon Manager" button.
- **`gramps/gui/viewmanager.py`** — instantiated from a Help menu callback   (style varies by Gramps version: may be lazy or module-level).

For each site, determine whether the import is **lazy** (inside a function, re-executed on each call) or **module-level** (bound once at import time). Only module-level sites need explicit secondary patching in your loader.

### 6.3 The registry layer is not applicable

There is no `id = "AddonManager"` in any `.gpr.py` anywhere in the Gramps source. `AddonManager` is not a registered plugin — it is a class that other code calls directly. Do not attempt to invent a collision: there is nothing to collide with. Register your addon with a fresh, unique id:

```python
register(
    GENERAL,
    id          = "AddonManagerPlus",   # unique; no collision needed or possible
    name        = _("Addon Manager Plus"),
    ...
    fname       = "AddonManagerLoad.py",
    load_on_reg = True,
)
```

### 6.4 The monkey-patch is still essential

Even though there is no registry to collide with, the Python namespace patch is required. Without it, all existing `AddonManager(...)` call sites in the Gramps source will continue to use the original class. With it, they transparently get your enhanced class.

---

## 7. Step-by-Step: Building Your Own Replacement Addon

This section provides complete, copy-paste-ready code for a minimal working `AddonManagerPlus`. Expand each component to suit your enhancement goals.

### Step 1 — Create the directory and install it

```
~/.gramps/gramps61/plugins/AddonManagerPlus/
├── AddonManagerPlus.gpr.py
├── AddonManagerLoad.py
└── AddonManagerPlus.py
```

Gramps discovers plugin directories by scanning the user plugin path. Each directory containing a `.gpr.py` is treated as a plugin package, and its directory is added to `sys.path` so that `import AddonManagerPlus` works from any other file in the same directory.

### Step 2 — The `.gpr.py` registration file

```python
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Your Name
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
"""AddonManagerPlus — replaces the built-in Addon Manager dialog."""

from gramps.version import major_version, VERSION_TUPLE

# Guard: only register if Gramps is new enough to have AddonManager
if VERSION_TUPLE >= (5, 2, 0):
    register(
        GENERAL,
        id                  = "AddonManagerPlus",
        name                = _("Addon Manager Plus"),
        description         = _(
            "An enhanced Addon Manager with improved search, "
            "filtering, and display capabilities."
        ),
        version             = "0.1.0",
        gramps_target_version = major_version,
        status              = EXPERIMENTAL,
        fname               = "AddonManagerLoad.py",
        authors             = ["Your Name"],
        authors_email       = ["your@email.example"],
        category            = TOOL_UTILS,
        load_on_reg         = True,
        help_url            = "",      # fill in once you have a wiki page
    )
```

### Step 3 — The loader file

The loader must patch `_windows.AddonManager` and any module-level cached references. The critical runtime question is: which Gramps modules have already been imported by the time the plugin scan runs? The answer depends on the Gramps startup sequence, so the loader checks `sys.modules` defensively and patches whatever it finds.

```python
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Your Name
#
# [GPL-2.0-or-later header as above]
#
"""AddonManagerLoad — patches AddonManager in-place at Gramps startup.

This module is executed at plugin-registration time because
AddonManagerPlus.gpr.py sets load_on_reg = True.  It replaces
AddonManager in gramps.gui.plug._windows and in any calling modules
that cached a module-level reference, before the main window appears.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6)
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
"""

# ------------------------
# Python modules
# ------------------------
import logging
import sys

# ------------------------
# Gramps modules
# ------------------------
import gramps.gui.plug._windows as _windows

# ------------------------
# Gramps specific
# ------------------------
from AddonManagerPlus import AddonManagerPlus

LOG = logging.getLogger(__name__)

# Modules that are known to import AddonManager at module level.
# Add to this list if grep reveals additional call sites in the
# version of Gramps you are targeting.
_SECONDARY_PATCH_TARGETS = [
    "gramps.gui.configure",
    "gramps.gui.viewmanager",
]


def _patch() -> None:
    """Monkey-patch AddonManager with AddonManagerPlus everywhere it is used.

    Replaces the class in its source module first, then covers any
    module-level cached references found in sys.modules.
    """
    # Primary patch: the source module itself
    original = getattr(_windows, "AddonManager", None)
    _windows.AddonManager = AddonManagerPlus
    LOG.debug(
        "AddonManagerPlus: replaced _windows.AddonManager (was %r)",
        original,
    )

    # Secondary patches: calling modules that may have cached the name
    for mod_name in _SECONDARY_PATCH_TARGETS:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "AddonManager"):
            setattr(mod, "AddonManager", AddonManagerPlus)
            LOG.debug(
                "AddonManagerPlus: patched cached reference in %s", mod_name
            )
        elif mod is None:
            # Module not yet imported — lazy imports will pick up the
            # already-patched _windows.AddonManager automatically.
            LOG.debug(
                "AddonManagerPlus: %s not yet imported; lazy imports "
                "will use patched class automatically",
                mod_name,
            )


_patch()
```

### Step 4 — The enhanced class (subclass approach)

When your enhancements are additive — new widgets, extended filtering, extra buttons — subclassing is the right approach. You inherit all of `AddonManager`'s existing functionality and override only what you need.

```python
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Your Name
#
# [GPL-2.0-or-later header]
#
"""AddonManagerPlus — enhanced Addon Manager dialog.

This module provides AddonManagerPlus, a subclass of the built-in
AddonManager that adds live keyword search over all addon fields, a
status-bar showing the visible/total count, and a keyboard shortcut
(Ctrl+F) to focus the search entry.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6)
Prompts: "Subclass AddonManager; add a search entry in the header bar
  that filters all addon fields live; add a visible/total counter label;
  wire Ctrl+F to the search entry."
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>
"""

# ------------------------
# Python modules
# ------------------------
import logging

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import Gdk, Gtk
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gui.plug._windows import AddonManager

# ------------------------
# Gramps specific
# ------------------------
# (local imports would go here)

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation
_ = _trans.sgettext

LOG = logging.getLogger(__name__)


#------------------------------------------------------------
#
# AddonManagerPlus
#
#------------------------------------------------------------
class AddonManagerPlus(AddonManager):
    """Enhanced Addon Manager dialog.

    Subclasses the built-in :class:`AddonManager` and adds:

    * A ``Gtk.SearchEntry`` in the header bar that filters all addon
      text fields live (name, description, id, authors).
    * A count label showing visible/total addons after filtering.
    * A ``Ctrl+F`` accelerator to focus the search entry.

    :param dbstate: The Gramps database state object.
    :param uistate: The Gramps UI state object.
    :param track: ManagedWindow tracking list.
    """

    def __init__(self, dbstate, uistate, track):
        """Initialise the enhanced Addon Manager.

        Calls the parent ``__init__``, which builds and shows the full
        dialog, then injects the additional widgets and wires up the
        accelerator.

        :param dbstate: The Gramps database state object.
        :param uistate: The Gramps UI state object.
        :param track: ManagedWindow tracking list.
        """
        # The parent __init__ builds the entire UI and calls self.show(),
        # so our additional widgets must be injected after the super call.
        super().__init__(dbstate, uistate, track)
        self._plus_search_text: str = ""
        self._plus_total: int = 0
        self._plus_visible: int = 0
        self._inject_plus_widgets()
        self._wire_accelerator()

    # ----------------------------------------------------------------
    # Additional widget injection
    # ----------------------------------------------------------------

    def _inject_plus_widgets(self) -> None:
        """Add the extra search entry and count label to the dialog header.

        Injects a :class:`Gtk.SearchEntry` and a count label into the
        dialog's action area, above the existing notebook widget, so the
        search box is always visible regardless of which tab is active.
        """
        # The parent places a Gtk.Notebook as the only child of the
        # dialog's content area.  We wrap it in a new vbox.
        content_area = self.window.get_content_area()
        children = content_area.get_children()
        if not children:
            LOG.warning("AddonManagerPlus: could not find content area children")
            return

        notebook = children[0]
        content_area.remove(notebook)

        outer_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        outer_vbox.set_margin_start(4)
        outer_vbox.set_margin_end(4)
        outer_vbox.set_margin_top(4)

        # Search row
        search_hbox = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label=_("Search") + ":")
        self._plus_search_entry = Gtk.SearchEntry()
        self._plus_search_entry.set_placeholder_text(
            _("Filter by name, description, or id…")
        )
        self._plus_search_entry.set_hexpand(True)
        self._plus_search_entry.connect("search-changed", self._cb_plus_search_changed)

        self._plus_count_label = Gtk.Label()
        self._plus_count_label.set_markup(
            "<small>{}</small>".format(_("Loading…"))
        )

        search_hbox.pack_start(lbl, False, False, 0)
        search_hbox.pack_start(self._plus_search_entry, True, True, 0)
        search_hbox.pack_end(self._plus_count_label, False, False, 0)

        outer_vbox.pack_start(search_hbox, False, False, 0)
        outer_vbox.pack_start(Gtk.Separator.new(Gtk.Orientation.HORIZONTAL),
                              False, False, 2)
        outer_vbox.pack_start(notebook, True, True, 0)
        outer_vbox.show_all()
        content_area.pack_start(outer_vbox, True, True, 0)

    def _wire_accelerator(self) -> None:
        """Bind Ctrl+F to focus the search entry.

        Uses :class:`Gtk.AccelGroup` attached to the dialog window so
        that the accelerator works regardless of which widget has focus.
        """
        accel_group = Gtk.AccelGroup()
        self.window.add_accel_group(accel_group)
        key, mods = Gtk.accelerator_parse("<Control>f")
        self._plus_search_entry.add_accelerator(
            "grab-focus", accel_group, key, mods, Gtk.AccelFlags.VISIBLE
        )

    # ----------------------------------------------------------------
    # Callbacks
    # ----------------------------------------------------------------

    def _cb_plus_search_changed(self, entry: Gtk.SearchEntry) -> None:
        """Callback: live-filter the addon list as the user types.

        :param entry: The :class:`Gtk.SearchEntry` that changed.
        """
        self._plus_search_text = entry.get_text().lower()
        self.lb.invalidate_filter()
        self._update_count_label()

    def _update_count_label(self) -> None:
        """Refresh the visible/total count label after a filter change."""
        total = len(self.lb.get_children())
        visible = sum(
            1 for row in self.lb.get_children() if row.get_visible()
        )
        self._plus_count_label.set_markup(
            "<small>{}</small>".format(
                # Translators: e.g. "Showing 12 of 47 addons"
                _("Showing %(visible)d of %(total)d addons")
                % {"visible": visible, "total": total}
            )
        )

    # ----------------------------------------------------------------
    # Override the parent's filter function to add our search logic
    # ----------------------------------------------------------------

    def _AddonManager__filter_func(self, row) -> bool:
        """Override the parent's private filter function.

        Python name-mangling means the parent's ``__filter_func``
        is stored as ``_AddonManager__filter_func``.  We override it
        here to first check our extra search text, then delegate to
        the parent's logic for all other filters.

        :param row: The :class:`AddonRow` being evaluated.
        :returns: ``True`` if the row should be shown.
        """
        # Our extra full-text filter
        if self._plus_search_text:
            addon = row.addon
            haystack = " ".join([
                addon.get("n", ""),
                addon.get("d", ""),
                addon.get("i", ""),
                " ".join(addon.get("au", [])),
            ]).lower()
            if self._plus_search_text not in haystack:
                return False

        # Delegate the rest to the original parent logic.
        # We call the parent method via its mangled name on the
        # AddonManager class (not self) to avoid infinite recursion.
        return AddonManager._AddonManager__filter_func(self, row)

    # ----------------------------------------------------------------
    # Override load_addons to update the count after loading
    # ----------------------------------------------------------------

    def load_addons(self, addon_list: list) -> None:
        """Load addons and update the count label.

        Calls the parent implementation then refreshes the count label
        once the list is populated.

        :param addon_list: List of addon dicts from :func:`get_all_addons`.
        """
        super().load_addons(addon_list)
        self._update_count_label()
```

### Step 5 — Verify the private method override

Python name-mangles any method whose name starts with double underscores into `_ClassName__method_name`. This means `AddonManager.__filter_func` is stored as `AddonManager._AddonManager__filter_func`. A subclass cannot override it with a method named `__filter_func` — that would create a new `_AddonManagerPlus__filter_func` instead.

To override it, define the method under the mangled name directly:

```python
def _AddonManager__filter_func(self, row) -> bool:
    ...
```

This is a deliberate Python design choice that makes private methods hard to override accidentally. When you do need to override them intentionally, using the mangled name is the correct approach.

### Step 6 — Handle the full-replacement case

If your enhancements require a complete structural rewrite — for example, replacing the `Gtk.ListBox` with a `Gtk.TreeView`, or changing the tab structure — subclassing becomes impractical. In that case, write a full replacement that inherits only from `ManagedWindow`:

```python
class AddonManagerPlus(ManagedWindow):
    """Full replacement for AddonManager."""

    def __init__(self, dbstate, uistate, track):
        self.dbstate = dbstate
        self.title = _("Addon Manager Plus")
        ManagedWindow.__init__(self, uistate, [], self)
        self.__pmgr = GuiPluginManager.get_instance()
        self.__preg = PluginRegister.get_instance()
        self.req = Requirements()
        # Build your own dialog from scratch
        dialog = Gtk.Dialog(
            title="",
            transient_for=uistate.window,
            destroy_with_parent=True,
        )
        self.set_window(dialog, None, self.title)
        self.setup_configs("interface.addonmanagerplus", 800, 500)
        self.window.connect("response", self._cb_response)
        # ... build your own UI ...
        self.show()
        self.refresh()

    def build_menu_names(self, obj) -> tuple[str, str]:
        """Return menu names for the ManagedWindow title bar.

        :param obj: Unused.
        :returns: Tuple of (primary, secondary) title strings.
        """
        return (self.title, self.title)

    def refresh(self) -> None:
        """Fetch the addon list in the background and populate the UI."""
        from gramps.gui.plug._windows import GetAddons
        thread = GetAddons(self.load_addons)
        thread.start()

    def load_addons(self, addon_list: list) -> None:
        """Populate the UI with the fetched addon list.

        :param addon_list: List of addon dicts from :func:`get_all_addons`.
        """
        # Your custom population logic here
        ...
```

---

## 8. Key Gramps APIs Every Replacement Dialog Must Use

This section documents the Gramps APIs that `AddonManager` uses and that your replacement must either call or replicate.

### 8.1 `ManagedWindow` — the dialog base class

All Gramps tool/utility dialogs inherit from `gramps.gui.managedwindow.ManagedWindow`.
It provides:

- **Single-instance enforcement**: if a window with the same class is already open, `ManagedWindow.__init__` raises `WindowActiveError` (handled by the caller) and brings the existing window to the front instead of opening a second one.
- **`set_window(dialog, title_widget, title_str, icon)`**: registers the `Gtk.Dialog` with the managed window system.
- **`setup_configs(config_key, default_width, default_height)`**: restores the window's last-used size from the Gramps config store.
- **`show()`**: calls `window.show_all()` and registers the window. **Always call this at the end of `__init__`**, after all widgets are built.
- **`close(dialog=None)`**: unregisters the window and destroys the dialog. Call from your response handler on `Gtk.ResponseType.CLOSE`.
- **`build_menu_names(obj)`**: must be overridden; returns `(title, title)`.

```python
# Minimal correct ManagedWindow subclass pattern
class MyDialog(ManagedWindow):
    def __init__(self, dbstate, uistate, track):
        ManagedWindow.__init__(self, uistate, track, self)  # note: self as key
        dialog = Gtk.Dialog(transient_for=uistate.window)
        self.set_window(dialog, None, _("My Dialog"), None)
        self.setup_configs("interface.mydialog", 600, 400)
        self.window.connect("response", self._cb_response)
        # ... build widgets ...
        self.show()  # always last

    def build_menu_names(self, obj):
        return (_("My Dialog"), _("My Dialog"))

    def _cb_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            self.close(dialog)
```

### 8.2 `GuiPluginManager` — the GUI-layer plugin manager

```python
from gramps.gui.pluginmanager import GuiPluginManager

pmgr = GuiPluginManager.get_instance()  # always use the singleton

# Load a plugin given its PluginData
pmgr.load_plugin(pdata)

# Re-scan a directory after installing an addon
pmgr.reg_plugin_dir(directory, dbstate, uistate, load_on_reg=True)

# Re-scan the user plugin directory
pmgr.reg_plugins(USER_PLUGINS, dbstate, uistate, load_on_reg=True)

# Signal that the plugin set has changed (updates views, menus, etc.)
pmgr.emit("plugins-reloaded")
```

### 8.3 `PluginRegister` — the plugin metadata registry

```python
from gramps.gen.plug import PluginRegister

preg = PluginRegister.get_instance()

# Look up a plugin by its id string
pdata = preg.get_plugin("SomePluginId")  # returns PluginData or None
```

### 8.4 `Requirements` — dependency checking

```python
from gramps.gen.utils.requirements import Requirements

req = Requirements()

# Check whether an addon's Python/system requirements are met
if req.check_addon(addon):
    ...

# Check and also try to install missing Python packages
if req.check_addon(addon, install=True):
    ...

# Get a human-readable requirements description
info_text = req.info(addon)

# Return list of Python packages that need installing
packages = req.install(addon)
```

### 8.5 `get_all_addons` — fetching available addons

```python
from gramps.gen.plug.utils import get_all_addons

# Returns a list of addon dicts from all configured project URLs.
# This is a blocking network call — always run it in a background thread.
addon_list = get_all_addons()
```

The `GetAddons` thread class in `_windows.py` wraps this correctly:

```python
from gramps.gui.plug._windows import GetAddons
from gi.repository import GLib

class GetAddons(threading.Thread):
    def run(self):
        self.addon_list = get_all_addons()
        GLib.idle_add(self.emit_signal)  # marshal result back to GTK thread

    def emit_signal(self):
        self.callback(self.addon_list)

thread = GetAddons(self.load_addons)
thread.start()
```

Always use `GLib.idle_add` to hand results back to the GTK main thread. Never update GTK widgets directly from a background thread.

### 8.6 `load_addon_file` — installing a downloaded addon

```python
from gramps.gen.plug import load_addon_file

# Download and unpack an addon tgz/zip from a URL
path = addon["_u"] + "/download/" + addon["z"]
success = load_addon_file(path)
```

### 8.7 Config system — persistent settings

```python
from gramps.gen.config import config

# Read a setting (with a default if not set)
value = config.get("behavior.check-for-addon-updates")

# Write a setting
config.set("behavior.check-for-addon-updates", 2)

# Force immediate save to disk
config.save()
```

The Addon Manager also uses `config.get("behavior.addons-projects")` to
read/write the list of configured project URLs.

### 8.8 Dialog utilities

```python
from gramps.gui.dialog import OkDialog, InfoDialog, QuestionDialog2
from gramps.gui.display import display_help, display_url

# Show a simple OK message
OkDialog(_("Title"), _("Message"), parent=self.window)

# Show an informational message (same API)
InfoDialog(_("Title"), _("Message"), parent=self.window)

# Show a yes/no question
result = QuestionDialog2(
    _("Title"), _("Question?"), _("Yes"), _("No"),
    parent=self.window
)
if result:
    ...

# Open a Gramps wiki page (wiki page name, not full URL)
display_help("Addon:Plugin_Manager_plus")

# Open an arbitrary URL in the system browser
display_url("https://github.com/gramps-project/gramps")
```

### 8.9 `open_file_with_default_application`

```python
from gramps.gui.utils import open_file_with_default_application

# Open a local file using the OS default application
open_file_with_default_application(file_path, uistate)
```

---

## 9. Internationalization

All user-visible strings must be wrapped with `_()` for translation support. Follow this pattern for addons exactly:

```python
from gramps.gen.const import GRAMPS_LOCALE as glocale

try:
    _trans = glocale.get_addon_translator(__file__)
except ValueError:
    _trans = glocale.translation

_ = _trans.sgettext
ngettext = _trans.ngettext  # for plural forms
```

The `get_addon_translator(__file__)` call loads the addon's own `.po`/`.mo` files from its `locale/` subdirectory. The `ValueError` fallback uses the main Gramps translation, which is correct for addons that have not yet provided their own translations.

Use `sgettext` (not `gettext`) for `_`. The `s` variant handles the disambiguation comment syntax used in Gramps, where the same English string may need different translations in different contexts:

```python
_("Type|Filter")    # context "Type", translatable string "Filter"
```

In the `.gpr.py` file, `_()` is provided by the registration scanner itself.
Do not import it there.

Any file that contains translatable strings must be listed in `po/POTFILES.in` if you intend to submit the addon to the official addons repository. Files that intentionally contain no translatable strings go in `po/POTFILES.skip`.

---

## 10. Coding Standards Compliance

Gramps enforces strict coding standards. Your addon must comply with all of them, regardless of whether it will be submitted upstream.

### 10.1 File header

Every `.py` file must begin with the GPL-2.0-or-later license header:

```python
#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2026  Your Name
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
```

### 10.2 Black formatting

All Python files must be formatted with Black before committing:

```bash
black AddonManagerPlus.py AddonManagerLoad.py AddonManagerPlus.gpr.py
```

Black is non-negotiable. It takes precedence over PEP 8 wherever they conflict.
Run it on every file you touch.

### 10.3 Type hints (Python 3.10+ syntax)

All functions and methods must have full type hints:

```python
# Correct — Python 3.10+ union syntax
def my_method(self, value: str | None) -> list[str]:
    ...

# Incorrect — do not use Optional or Union from typing
from typing import Optional, Union  # avoid
def my_method(self, value: Optional[str]) -> List[str]:  # avoid
    ...
```

Use handle types from `gramps/gen/types.py` for database handle parameters:

```python
from gramps.gen.types import PersonHandle
def get_person(self, handle: PersonHandle) -> Person | None:
    ...
```

### 10.4 Docstrings — Sphinx format

Every function and method needs a Sphinx-format docstring:

```python
def load_addons(self, addon_list: list) -> None:
    """Populate the addon list box from the fetched addon list.

    Called from the :class:`GetAddons` background thread via
    ``GLib.idle_add`` once the addon list has been retrieved from
    all configured project URLs.

    :param addon_list: List of addon metadata dicts, each containing
        keys ``n`` (name), ``d`` (description), ``i`` (id), etc.
    """
```

### 10.5 Import grouping

Three sections, each with a comment header and a blank line between them:

```python
# ------------------------
# Python modules
# ------------------------
import logging
import os
import sys
import threading

# ------------------------
# Gramps modules
# ------------------------
from gi.repository import GLib, Gtk
from gramps.gen.config import config
from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.plug import PluginRegister, load_addon_file
from gramps.gen.plug.utils import get_all_addons
from gramps.gen.utils.requirements import Requirements
from gramps.gui.dialog import InfoDialog, OkDialog
from gramps.gui.display import display_help, display_url
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.plug._windows import AddonManager
from gramps.gui.pluginmanager import GuiPluginManager

# ------------------------
# Gramps specific
# ------------------------
from AddonManagerLocal import SomeLocalHelper  # your own local modules
```

### 10.6 Class headers

Each class gets a navigation header:

```python
#------------------------------------------------------------
#
# AddonManagerPlus
#
#------------------------------------------------------------
class AddonManagerPlus(AddonManager):
    ...
```

### 10.7 Callback naming

All GTK callback functions must be prefixed with `cb_` (for public callbacks) or `_cb_` (for private ones):

```python
# Correct
def _cb_search_changed(self, entry: Gtk.SearchEntry) -> None:
    ...

self.search_entry.connect("changed", self._cb_search_changed)

# Incorrect
def on_search_changed(self, entry):  # avoid
    ...
```

### 10.8 Logging

Use module-level loggers; never `print()`:

```python
import logging
LOG = logging.getLogger(__name__)

# In code:
LOG.debug("AddonManagerPlus: loaded %d addons", len(addon_list))
LOG.warning("AddonManagerPlus: patch target %s not in sys.modules", mod_name)
```

### 10.9 Pylint

Run pylint on all new files. Aim for a score of 9 or higher:

```bash
pylint AddonManagerPlus.py
```

Common issues to fix proactively:

- Missing type hints → add them
- Missing docstrings → add them
- Unused imports → remove them
- `# pylint: disable=...` comments are acceptable for justified suppressions
  (e.g. `# pylint: disable=unused-argument` on GTK callback stubs)

---

## 11. Testing Your Replacement

### 11.1 Manual smoke test

1. Drop the addon directory into your user plugins folder.
2. Start Gramps from a terminal with debug logging enabled:
   ```bash
   gramps 2>&1 | grep -i "addonmanager"
   ```
3. Confirm the loader's debug messages appear, confirming the patch fired.
4. Open Help → Install Addons (or however the Addon Manager is accessed in your Gramps version). Confirm your class appears.
5. Test all original functionality: install, update, refresh, filter combos, settings tab, projects tab, close, help link.
6. Test your new functionality.

### 11.2 Confirming the patch fired

Add a distinctive log message to your loader:

```python
LOG.debug(
    "AddonManagerPlus: patch complete; _windows.AddonManager is now %r",
    _windows.AddonManager,
)
```

Run Gramps with the `.gui.plug` logger enabled:

```bash
gramps -d .gui.plug 2>&1 | grep "AddonManager"
```

The output should confirm `_windows.AddonManager` is now your class.

### 11.3 Unit tests

Write unit tests in a `test/` subdirectory with the `_test.py` suffix:

```
AddonManagerPlus/
├── test/
│   └── addonmanagerplus_test.py
```

Tests must use the `unittest` framework (not pytest):

```python
#
# Gramps - a GTK+/GNOME based genealogy program
# [license header]
#
"""Tests for AddonManagerPlus."""

# ------------------------
# Python modules
# ------------------------
import sys
import unittest
from unittest.mock import MagicMock, patch

# ------------------------
# Gramps modules
# ------------------------
# Gramps is not importable in isolation without a running instance,
# so tests that require GTK must be skipped in headless environments.
try:
    import gramps.gui.plug._windows as _windows
    HAS_GRAMPS = True
except ImportError:
    HAS_GRAMPS = False


#------------------------------------------------------------
#
# TestMonkeyPatch
#
#------------------------------------------------------------
@unittest.skipUnless(HAS_GRAMPS, "Gramps GUI not available")
class TestMonkeyPatch(unittest.TestCase):
    """Test that the monkey-patch replaces the correct class."""

    def test_patch_replaces_class(self) -> None:
        """Verify that after patching, _windows.AddonManager is our class."""
        # Save original
        original = _windows.AddonManager

        # Apply patch
        fake_class = type("FakeAddonManager", (), {})
        _windows.AddonManager = fake_class

        try:
            self.assertIs(_windows.AddonManager, fake_class)
        finally:
            # Restore original so other tests are unaffected
            _windows.AddonManager = original

    def test_patch_secondary_modules(self) -> None:
        """Verify that secondary module patches update the cached name."""
        import gramps.gui.configure as configure
        fake_class = type("FakeAddonManager", (), {})
        original = getattr(configure, "AddonManager", None)

        try:
            configure.AddonManager = fake_class
            self.assertIs(configure.AddonManager, fake_class)
        finally:
            if original is not None:
                configure.AddonManager = original


if __name__ == "__main__":
    unittest.main()
```

Run the tests:

```bash
GRAMPS_RESOURCES=. python3 -m unittest discover -p "*_test.py"
```

### 11.4 Test the uninstall path

Remove the addon directory and restart Gramps. Verify that:

- No error messages appear in the console about the missing addon.
- The built-in `AddonManager` is used without any residue from your patch.
- The registry for `"PluginManager"` (if you replaced that) reverts to the built-in entry.

---

## 12. Pitfalls and Edge Cases

### 12.1 Module load order and the `sys.modules` cache

Your loader runs during the plugin scan. At that point, the Gramps startup sequence has already imported some modules but not others. Modules imported lazily (on first use) will not yet be in `sys.modules`. Your secondary patch loop silently skips them — which is correct, because when they are eventually imported, they will execute `from gramps.gui.plug._windows import AddonManager`, which now returns your patched class.

The risk is with modules that are already in `sys.modules` **and** have cached `AddonManager` at module level. Use `LOG.debug` to confirm at runtime which patches actually fired. If you discover a call site that is always imported before the plugin scan, add it to `_SECONDARY_PATCH_TARGETS` in your loader.

### 12.2 Name mangling of private methods

As shown in Section 7, Step 5, Python name-mangles any method whose name begins with double underscores. `AddonManager.__filter_func` becomes `AddonManager._AddonManager__filter_func`. To override it in a subclass, define it under the mangled name. To call the parent's version from your override without infinite recursion, call it explicitly:

```python
def _AddonManager__filter_func(self, row):
    # Your extra logic first
    if not my_filter(row):
        return False
    # Delegate to parent for the rest
    return AddonManager._AddonManager__filter_func(self, row)
```

### 12.3 The `ManagedWindow` singleton check

`ManagedWindow.__init__` checks whether a window with the same class is already open. It uses the class as the key. Because your replacement class is a different class from `AddonManager`, users could theoretically open both simultaneously if something bypassed the patch. In practice this cannot happen once the patch is applied — but be aware that the singleton key is **your class**, not `AddonManager`.

If you need to ensure that neither your class nor the original can be open at the same time, override `build_menu_names` to return the same title strings as the original, and check for `WindowActiveError` in any code that opens the dialog.

### 12.4 GTK thread safety

`GLib.idle_add` is the only safe way to update GTK widgets from a background thread. The `GetAddons` thread in `_windows.py` already uses this correctly — if you reuse it (by importing it from `_windows`), you inherit that safety. If you write your own background thread, always marshal GTK updates through `GLib.idle_add(callback, ...)`.

Never call `.show()`, `.set_text()`, `.add()`, or any other GTK widget method directly from a non-main thread. GTK is not thread-safe.

### 12.5 `if __debug__` blocks

The `RELOAD` button in `AddonManager` and `PluginManagerPlus` uses `if __debug__` to show developer-only controls only when Python is running without the `-O` flag. Gramps runs in "User mode" with `-O` (the startup wrapper sets this), and in "Developer mode" without it. Respect this convention in your own class:

```python
if __debug__:
    debug_button = self.window.add_button(_("Debug"), DEBUG_RESPONSE)
```

### 12.6 The `VERSION_TUPLE` guard

Always guard your `.gpr.py` registration:

```python
if VERSION_TUPLE >= (5, 2, 0):
    register(...)
```

This prevents your addon from attempting to patch a class that does not exist in older Gramps versions, which would cause a hard error at startup. Check the Gramps version in which the class you are targeting first appeared, and use that as your lower bound.

### 12.7 Do not import from `gramps.gui` inside `gramps.gen`

The Gramps architecture mandates that the `gen` submodule is self-contained and must not import from `gui`, `plugins`, or other submodules. Your addon lives in the user plugin directory, outside `gen`, so this rule does not directly apply to you. However, if you extract any shared logic into a utility module, keep this boundary in mind. If you ever want to contribute your utility to `gen`, it cannot import from `gui`.

### 12.8 Reversibility

When the user removes the addon by deleting the directory and restarting Gramps,
the patch is never applied. Gramps reverts to the built-in class cleanly — no config files are modified, no registry entries left over. The only exception is `setup_configs`: if your enhanced class stored settings under a config key,
those settings remain in `gramps.ini` but are harmlessly ignored. If you used the same config key as the original class (e.g. `"interface.addonmanager"`),
the settings remain and are picked up again if the user reinstalls the addon.

---

## 13. Generalizing the Pattern to Other Built-in Dialogs

The same three-file technique (`gpr.py` + loader + enhanced class) applies to any built-in Gramps dialog. The steps are always the same:

1. Find the class in the Gramps source.
2. Run `grep -rn "ClassName"` to find all call sites.
3. Determine for each call site whether the import is lazy or module-level.
4. Check whether the class has a registered plugin `id`.
5. Write the `.gpr.py` (with `load_on_reg = True`; use the same `id` if one exists).
6. Write the loader to patch all necessary namespaces.
7. Write the enhanced class (subclass or full replacement).

Here is a map of the most commonly targeted dialogs:

| Dialog class | Source file | Registered `id` | Collision? |
|---|---|---|---|
| `PluginStatus` | `gramps/gui/plug/_windows.py` | `"PluginManager"` | Yes |
| `AddonManager` | `gramps/gui/plug/_windows.py` | None | No |
| `Preferences` (`ConfigureDialog`) | `gramps/gui/configure.py` | None | No |
| `EditPerson` | `gramps/gui/editors/editperson.py` | None | No |
| `NoteEditor` | `gramps/gui/editors/editnote.py` | None | No |

> **Caution:** Replacing core editor dialogs like `EditPerson` is
> high-risk — they have many call sites, complex internal state machines, and are invoked from drag-and-drop, keyboard shortcuts, and dozens of other places.
> The Addon Manager and Plugin Manager are lower-risk targets because they are self-contained utility dialogs with a small number of well-defined call sites.

---

## 14. Commit Message and AI Disclosure Requirements

The Gramps project requires specific disclosure when AI tools contribute to code. If you used an AI assistant (Claude, GitHub Copilot, ChatGPT, or any other) while writing your addon, your commit message must include the required tags.

### 14.1 When the code is substantially AI-generated

Use `Generated-by:`:

```
Add AddonManagerPlus: enhanced replacement for the built-in Addon Manager.

Replaces gramps.gui.plug._windows.AddonManager at startup using the load_on_reg monkey-patching technique pioneered by PluginManagerPlus.
The enhanced class adds full-text search over all addon fields, a visible/total count label, and Ctrl+F keyboard shortcut.

The three-file structure (gpr.py + loader + class) follows the pattern documented in gramps_supplanting_builtin_dialogs.md.

Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6)
Prompts: "Subclass AddonManager; add a SearchEntry that filters all addon fields; add a count label; wire Ctrl+F to the entry; follow Gramps AGENTS.md coding standards."
Constraints:
  https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code
  https://github.com/gramps-project/gramps/blob/master/AGENTS.md
Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>

references 0012345
```

### 14.2 When AI provided review or partial assistance

Use `Co-authored-by:` alone (without `Generated-by:`):

```
Fix AddonManagerPlus filter to respect project combo.

The __filter_func override was not delegating project filtering back to the parent, causing all project filters to be ignored. Fixed by calling AddonManager._AddonManager__filter_func explicitly after the extra search-text check.

Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>

fixes 0012346
```

### 14.3 Gramps AI contribution policy summary

Per the Gramps contribution guidelines:

- AI-generated code **must** be disclosed.
- You are responsible for verifying the code and ensuring it does not include copyrighted material.
- The AI tool's terms must not conflict with the Gramps GPL-2.0-or-later license.
- Both `Generated-by:` and `Co-authored-by:` tags are acceptable and may both appear in the same commit if AI wrote the bulk of the code and also reviewed it.

---

## 15. Quick Reference Summary

### The three-file addon structure

| File | Purpose |
|---|---|
| `MyAddon.gpr.py` | Registers with `GENERAL`, `load_on_reg=True`, `id` = your unique id (or built-in's id if colliding) |
| `MyAddonLoad.py` | Executed at startup; performs all monkey-patches; imports the class file |
| `MyAddon.py` | The enhanced replacement class (subclass or full replacement) |

### Choosing subclass vs. full replacement

| Approach | When to use |
|---|---|
| **Subclass** `class MyClass(OriginalClass)` | Enhancements are additive; parent `__init__` can be called without harm |
| **Full replacement** `class MyClass(ManagedWindow)` | Layout changes are structural; parent `__init__` builds widgets you are discarding |

### When to use the registry collision trick

| Target dialog | Has a registered `id`? | Use same `id` in `.gpr.py`? |
|---|---|---|
| `PluginStatus` (Plugin Manager) | Yes — `"PluginManager"` | Yes |
| `AddonManager` (Addon Manager) | No | No — new unique id |
| Any other `GENERAL` plugin | Check its `.gpr.py` | Yes if you want registry-level replacement |

### The minimal loader template

```python
import logging
import sys
import gramps.gui.plug._windows as _windows
from MyAddonPlus import MyAddonPlusClass

LOG = logging.getLogger(__name__)

_SECONDARY_PATCH_TARGETS = [
    "gramps.gui.viewmanager",
    "gramps.gui.configure",
]

def _patch() -> None:
    _windows.OriginalClass = MyAddonPlusClass
    LOG.debug("Patched _windows.OriginalClass")
    for mod_name in _SECONDARY_PATCH_TARGETS:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "OriginalClass"):
            setattr(mod, "OriginalClass", MyAddonPlusClass)
            LOG.debug("Patched %s.OriginalClass", mod_name)

_patch()
```

### Decision flowchart

```
Do you want to replace a built-in dialog?
│
├── Audit call sites: grep -rn "ClassName" gramps/gui/
│
├── Does the dialog have its own registered plugin id?
│   ├── YES → Use the same id in your .gpr.py  AND  monkey-patch in loader
│   └── NO  → Use a new unique id in .gpr.py   AND  monkey-patch in loader
│
├── Are any call sites using module-level imports?
│   ├── YES → Also patch those modules in your loader via sys.modules
│   └── NO  → Patching _windows.TheClass alone is sufficient
│
└── How extensive are your changes?
    ├── ADDITIVE (new widgets, new filters) → subclass the original
    └── STRUCTURAL (new layout, new widget types) → full replacement from ManagedWindow
```

### Essential Gramps APIs for a replacement dialog

| API | Import path | Purpose |
|---|---|---|
| `ManagedWindow` | `gramps.gui.managedwindow` | Base class for all tool/utility dialogs |
| `GuiPluginManager` | `gramps.gui.pluginmanager` | Load, reload, hide/unhide plugins |
| `PluginRegister` | `gramps.gen.plug` | Look up plugin metadata by id |
| `Requirements` | `gramps.gen.utils.requirements` | Check/install addon Python dependencies |
| `get_all_addons` | `gramps.gen.plug.utils` | Fetch available addons from project URLs |
| `load_addon_file` | `gramps.gen.plug` | Download and install an addon archive |
| `OkDialog`, `InfoDialog` | `gramps.gui.dialog` | Standard Gramps message dialogs |
| `display_help`, `display_url` | `gramps.gui.display` | Open wiki or browser URL |
| `config` | `gramps.gen.config` | Read/write persistent settings |

---

## 16. References

### Source files discussed in this paper

- `PluginManagerPlus.gpr.py` — <https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/MarkdownDash/PluginManagerPlus.gpr.py>
- `PluginManagerPlus.py` — <https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/MarkdownDash/PluginManagerPlus.py>
- `gramps/gui/plug/_windows.py` (`PluginStatus`, `AddonManager`, `AddonRow`, `GetAddons`) — <https://github.com/gramps-project/gramps/blob/master/gramps/gui/plug/_windows.py>
- `gramps/gui/pluginmanager.py` (`GuiPluginManager`) — <https://github.com/gramps-project/gramps/blob/master/gramps/gui/pluginmanager.py>
- `gramps/gen/plug/_pluginreg.py` (`PluginRegister`) — <https://github.com/gramps-project/gramps/blob/master/gramps/gen/plug/_pluginreg.py>
- `gramps/gui/managedwindow.py` (`ManagedWindow`) — <https://github.com/gramps-project/gramps/blob/master/gramps/gui/managedwindow.py>
- `gramps/gen/utils/requirements.py` (`Requirements`) — <https://github.com/gramps-project/gramps/blob/master/gramps/gen/utils/requirements.py>

### Gramps project documentation

- Addons Development wiki — <https://www.gramps-project.org/wiki/index.php/Addons_development>
- AI contribution guidelines — <https://gramps-project.org/wiki/index.php/Howto:_Contribute_to_Gramps#AI_generated_code>
- Gramps AGENTS.md coding standards — <https://github.com/gramps-project/gramps/blob/master/AGENTS.md>
- Plugin Manager Plus addon wiki page — <https://gramps-project.org/wiki/index.php/Addon:Plugin_ManagerV2>
- 6.0 Addons wiki page — <https://gramps-project.org/wiki/index.php?title=Plugins>
- addons-source repository — <https://github.com/gramps-project/addons-source>

---

*This document was prepared with assistance from Claude Sonnet 4.6 (Anthropic,claude-sonnet-4-6). AI disclosure per Gramps contribution guidelines.*

*Generated-by: Claude Sonnet 4.6 (Anthropic, claude-sonnet-4-6)*  
*Co-authored-by: Claude Sonnet 4.6 <claude-sonnet-4-6@anthropic.com>*
