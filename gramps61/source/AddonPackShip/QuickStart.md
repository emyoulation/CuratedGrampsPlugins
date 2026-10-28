# Quick Start (AddonPackShip — Gramps Addon Packaging Tool)
[**QuickStart.md**](QuickStart.md) ● [**README.md**](README.md) ● [**Change Log**](CHANGELOG.md)

**Version 1.9.19** — 5-Minute Guide 

---

## Install
**Via Addon Manager** (not the Plugin Manager): 

1. **Tools** → **Addon Manager** → **Projects** tab
2. Add repository URL:  
   `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/main/gramps60`
   (The Addon Manager will append the `/listings/addons-en.json` to find the listings.)
3. **Refresh** → Find "Addon Pack and Ship" → **Install** → **Restart Gramps**

---

## Access the Tool
**Tools** → **Utilities** → **Addon Pack and Ship**

---

## Package Your First Addon
### Step 1: Select
✅ Check the addon(s) you want to package in the scrollable list

**Filter** if you have many addons — type name, author, or email in the "Name/Contributor contains:" box

### Step 2: Choose Mode
The **β Beta** and **Δ Release** radio buttons are in the **Filter Addons** frame at the top — they stay visible as the list scrolls.

**β Beta** (default) — Includes translation source files, docs, everything except `__pycache__`  
**Δ Release** — Clean end-user package only

💡 **Use β Beta** for beta testing and translation work

### Step 3: Pack and Ship
Click **📦 Pack and Ship** (bottom center of window)

✅ Shows a progress window naming each step  
✅ Builds `.addon.tgz` package  
✅ Generates `template.pot` if missing  
✅ Creates/amends JSON listings, sorted by addon name, and repairs any outdated entries for the selected addons  
✅ Shows output location  
✅ A **📁 folder icon** appears next to the button — click it to see the exact command that ran, in `logs/`

### Step 4: Upload
1. Find files in `~/.gramps/gramps60/plugins/AddonPackShip/gramps60/`
2. Upload the `gramps60/` folder to your GitHub repository
3. Share URL: `https://raw.githubusercontent.com/username/repo/main/gramps60` 
(The Addon Manager will append the `/listings/addons-en.json` or appropriate localized variant.)

**Done!** Users can install from your repository via their Addon Manager.

---

## Test Locally First
Before uploading to GitHub:

1. **Tools** → **Addon Manager** → **Projects** tab
2. Add: `file:///home/username/.gramps/gramps60/plugins/AddonPackShip/gramps60/listings/addons-en.json`
   - (Windows: `file:///C:/Users/username/...`)
3. **Refresh** → Install your addon → **Test** it works correctly → **Then** upload to GitHub

---

## Individual Operations
**Build Selected** — Just create `.addon.tgz` packages

**Compile Translations** — Generate `template.pot` + compile `.po` → `.mo` files

**Amend Listings** — Add/update JSON metadata entries  
> ℹ️ This *adds or updates* entries — it does not remove old ones.  
> To shrink the listing (e.g., remove a retired addon), **delete the `gramps60/listings/` folder** first, then re-run for only the addons you want listed.

**Translation:** + **Edit translation…** (Options tab, Listings frame) — Choose a language, select addons, and click to open each `po/<code>-local.po` in your `.po` editor (created or updated from `template.pot` first). After saving: **Compile Translations**, then **restart Gramps** — a reload is not enough. See the README section *Translating an Addon*.

**Right-click the addon list** → **Filter list to addons in Gramps 6.0's listing**, then **Select All Visible** — selects exactly the addons already in that version's `addons-en.json` (needs exactly one Gramps Version checked)

**📂 Folder icon button** (on each addon row) — Create or open the MANIFEST.beta / MANIFEST for that addon  
You do not need to select the addon first — just click its folder button directly.

---

## Build Modes Explained
### β Beta
**Includes**: Everything — source files, docs, translations, data
**For**: Translators, beta testers, developers
**Use when**: Sharing work-in-progress or requesting help

### Δ Release
**Includes**: Core files, README.md, compiled translations only
**For**: End users installing finished addons
**Use when**: Publishing final stable release
⚠ **Warning dialog** appears before Δ Release to confirm you understand it's lossy

---

## MANIFEST Files (Optional)
**Without MANIFEST**:
- β Beta auto-includes everything
- Δ Release auto-includes core + README.md
**With MANIFEST / MANIFEST.beta**:
- Explicit control over what's included
**When to use**: You have custom data directories or want to exclude specific files
**How to create/edit**: Click the **📂 folder icon button** on the right side of any addon's row — this opens the correct MANIFEST file (beta or release, based on current mode) in your text editor, creating it if it doesn't exist. The file includes an annotated directory listing to help you identify which files need manual entries.

---

## Common Tasks
### Share Beta for Translation
1. Select addon → **β Beta** mode
2. **Compile Translations** (generates `template.pot`)
3. **Pack and Ship**
4. Upload to GitHub → Share URL with translators

### Publish Final Release
1. Select addon → **Δ Release** mode
2. **Pack and Ship** (confirm warning)
3. Upload to GitHub → Announce on forums

### Remove an Addon from Listings
1. Delete the `gramps60/listings/` folder
2. Select only the addons you want listed
3. **Amend Listings** (or **Pack and Ship**)

### Update Translation Template
1. Edit your `.py` files to add/change strings
2. **Compile Translations** — updates `template.pot`
3. Share updated `template.pot` with translators

---

## Troubleshooting
**"No Addons Found"** → Install at least one addon first via the Addon Manager
**"Malformed .gpr.py"** → Fix commas in list fields:
- Wrong: `authors = ["Smith, John"]`
- Right: `authors = ["Smith", "John"]`
**Translations not compiling** → Install `gettext` tools:
- Linux: `sudo apt install gettext`
- Windows: https://mlocati.github.io/articles/gettext-iconv-windows.html
- macOS: `brew install gettext`
**Old listing entries not disappearing** → Delete `gramps60/listings/` folder, then re-run
**An addon listed at an older version** → Run **Amend Listings** (or **Pack and Ship**) for it again with that Gramps Version checked — the listing is checked and repaired

---

## Next Steps
📖 **Read [README.md](README.md)** for complete documentation
🔧 **Use 📂 folder buttons** to manage MANIFEST files per addon
🧪 **Test locally** with `file://` URLs before publishing
🌍 **Request translations** by sharing β Beta packages
📦 **Publish** when ready!

---

**AddonPackShip** — Your addon packaging simplified!
