# AddonPackShip Quick Start

**Version 1.8.3** — 5-Minute Guide  
**Read [README.md](README.md) for full documentation**

---

## Install

**Via Addon Manager** (not the Plugin Manager):

1. **Tools** → **Addon Manager** → **Projects** tab
2. Add repository URL:  
   `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/main/gramps52`
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

Click **📦 Pack and Ship** (bottom centre of window)

✅ Builds `.addon.tgz` package  
✅ Generates `template.pot` if missing  
✅ Creates/amends JSON listings  
✅ Shows output location

### Step 4: Upload

1. Find files in `~/.gramps/gramps52/plugins/AddonPackShip/gramps52/`
2. Upload the `gramps52/` folder to your GitHub repository
3. Share URL: `https://raw.githubusercontent.com/username/repo/main/gramps52/listings/addons-en.json`

**Done!** Users can install from your repository via their Addon Manager.

---

## Test Locally First

Before uploading to GitHub:

1. **Tools** → **Addon Manager** → **Projects** tab
2. Add: `file:///home/username/.gramps/gramps52/plugins/AddonPackShip/gramps52/listings/addons-en.json`
   - (Windows: `file:///C:/Users/username/...`)
3. **Refresh** → Install your addon → **Test** it works correctly → **Then** upload to GitHub

---

## Individual Operations

**Build Selected** — Just create `.addon.tgz` packages

**Compile Translations** — Generate `template.pot` + compile `.po` → `.mo` files

**Amend Listings** — Add/update JSON metadata entries  
> ℹ️ This *adds or updates* entries — it does not remove old ones.  
> To shrink the listing (e.g., remove a retired addon), **delete the `gramps52/listings/` folder** first, then re-run for only the addons you want listed.

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

1. Delete the `gramps52/listings/` folder
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

**Old listing entries not disappearing** → Delete `gramps52/listings/` folder, then re-run

---

## Next Steps

📖 **Read [README.md](README.md)** for complete documentation

🔧 **Use 📂 folder buttons** to manage MANIFEST files per addon

🧪 **Test locally** with `file://` URLs before publishing

🌍 **Request translations** by sharing β Beta packages

📦 **Publish** when ready!

---

**AddonPackShip** — Your addon packaging simplified!
