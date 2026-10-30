# Quick Start (AddonPackShip — Gramps Addon Packaging Tool)
[**QuickStart.md**](QuickStart.md) ● [**README.md**](README.md) ● [**Change Log**](CHANGELOG.md)

**5-Minute Guide** — package and publish your first addon. Everything else is in the [FAQ](#faq) at the bottom.

---

## Install
**Via Addon Manager** (not the Plugin Manager):

1. **Edit** → **Addon Manager** → **Projects** tab
2. Add the repository URL `https://raw.githubusercontent.com/emyoulation/CuratedGrampsPlugins/main/gramps60` (the Addon Manager adds `/listings/addons-en.json` by itself).
3. **Refresh** → find **Addon Pack and Ship** → **Install** → restart Gramps

---

## Access the Tool
**Tools** → **Utilities** → **Addon Pack and Ship**

---

## Package Your First Addon
### Step 1: Select
✅ Check the addon(s) you want to package in the scrollable list.

**Filter** if you have many addons — type any part of a name, author, id or path in the **Search bundles and plugins…** box, or pick a plugin type in the type filter.

### Step 2: Check the mode
Keep the default **β Beta** mode (on the **Options** tab). It includes translation sources and documents, which is right for testing and translation work. Use **Δ Release** only for a final release.

⚠ Check more than one **Gramps Versions** box only when the `.gpr.py` of the addon is adaptive (has a version check). Otherwise keep only the version you are running checked. See the FAQ below.

### Step 3: Pack and Ship
Click **📦 Pack and Ship** (bottom center of the window).

- Shows a progress window naming each step
- Builds the `.addon.tgz` package
- Creates or amends the JSON listings
- Shows where the files were written

### Step 4: Upload
1. Click **Output location** to open the folder with the new `gramps60/` folder (by default, the folder of Addon Pack and Ship).
2. Upload the `gramps60/` folder to your GitHub repository.
3. Share the URL `https://raw.githubusercontent.com/username/repo/main/gramps60` (the Addon Manager adds `/listings/addons-en.json` or the listing for its language).

**Done!** Users can install from your repository with their Addon Manager.

---

## Test Locally First
Before uploading to GitHub:

1. **Edit** → **Addon Manager** → **Projects** tab
2. Add `file:///<output-location>/gramps60/listings/addons-en.json` (click **Output location** to see the folder; on Windows, `file:///C:/Users/username/...`).
3. **Refresh** → install your addon → test that it works → **then** upload to GitHub.

---

## FAQ
- [How do I choose between β Beta and Δ Release?](README.md#build-modes)
- [Can I pack an addon for several Gramps versions at once? (Only when its .gpr.py is adaptive.)](README.md#packing-for-several-gramps-versions)
- [How do I publish with GitHub Desktop instead of uploading by hand?](README.md#publishing-with-github-desktop)
- [What do Build Selected, Compile Translations and Amend Listings do on their own?](README.md#build-operations)
- [How do I control which files go into a package (MANIFEST files)?](README.md#manifest-files)
- [How do I save my settings for next time?](README.md#named-configurations)
- [How do I share a Beta for translators?](README.md#share-a-beta-for-translators)
- [How do I publish a final release?](README.md#publish-a-final-release)
- [How do I update the translation template after changing strings?](README.md#update-the-translation-template)
- [How do I rebuild every addon I have already published?](README.md#rebuild-everything-already-published)
- [How do I remove a retired addon from the listings?](README.md#remove-an-addon-from-the-listings)
- [How do I translate an addon, with a .po editor or an AI assistant?](README.md#translating-an-addon)
- [Why does my new translation not appear?](README.md#why-gramps-must-restart)
- [Where can I see the exact commands that ran, and learn make.py from them?](README.md#learning-from-the-session-logs)
- [Something went wrong. Where do I look?](README.md#troubleshooting)
