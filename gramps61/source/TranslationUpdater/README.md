# Translation Updater

## Screen captures to take (remove this list before release)

1. `media/screenshot.png` — The whole Translation Updater window on Linux, at its default size, right after a successful **Check for updates**. German and French are checked and appear at the top of the Languages list, and their Status column shows something like "Gramps, 12 addons, checked 2026-11-16". All four check boxes are visible (the first three checked, startup checking unchecked). **Advanced** is expanded so the source address, branch and packs folder show. The Full-coverage launcher section is visible after **Create launcher** was pressed, so **Remove launcher** is active and the status text reads "Look for "Gramps (updated translations)" in your menu." Close the "Translations checked" summary before capturing.

Translators improve the Gramps translations every day, but those improvements usually reach you only when Gramps or an addon gets a new release. Translation Updater brings them to you sooner. Choose the languages you use, press one button, and Gramps and your installed addons pick up the newest translations. The addons themselves stay exactly as they are, with the same version numbers.

![The Translation Updater window, with German and French chosen and up to date](media/screenshot.png)

## What it does

Volunteer translators work on the Gramps and addon translations in Weblate. Every day, those translations are collected and published as small language packs. Translation Updater downloads the packs for the languages you choose, and only for the addons you have installed.

The downloaded translations are layered on top of the ones that came with Gramps and with each addon. When a downloaded pack has a translation for a phrase, that translation is used. When it does not, the original translation is used, just as before. Nothing inside Gramps or inside your addon folders is changed.

## Getting started

1. Open a family tree, then choose **Tools > Utilities > Translation Updater**.
2. Press **Refresh list** to see which languages are published.
3. Put a check mark next to each language you want. The language you use in Gramps is already checked the first time.
4. Press **Check for updates**. A short summary tells you what was downloaded.
5. Restart Gramps so that every window uses the new translations.

After the first time, you only need to repeat step 4. Only translations that changed are downloaded again.

## The Translation Updater window

**Languages** lists every published language. Your chosen languages appear at the top of the list. The Status column shows what was downloaded for each language and when it was last checked.

**Gramps translations** downloads updated translations for Gramps itself.

**Addon translations** downloads updated translations for the addons you have installed.

**Also use updated Gramps translations in Glade-built dialogs** applies the updated Gramps translations to the dialogs that Gramps builds from Glade design files, such as many editors. This takes effect when Gramps restarts.

**Check for updates when Gramps starts** checks quietly in the background, at most once a day. When something new arrives, a message appears in the status bar.

**Advanced** shows the address the packs are downloaded from, the Gramps branch the packs are chosen for, and the folder where they are kept on your computer.

**Help** opens this document. **Check for updates** downloads anything new for your chosen languages. **Close** closes the window and remembers its size.

## The full-coverage launcher

A few words in Gramps, such as some menu labels, are translated while Gramps is starting, before any addon has a chance to run. Translation Updater cannot change those words in a session that has already started.

On Linux, the **Full-coverage launcher** section can create a second menu entry called **Gramps (updated translations)**. Starting Gramps from that entry uses the updated translations from the very first moment, so every word is covered. The window also shows the matching command line, if you prefer to start Gramps from a terminal.

Press **Remove launcher** to remove the menu entry again. Your normal Gramps menu entry is never changed.

## When an update is paused

A downloaded translation is only used together with the exact files it was downloaded for. If your system installs a newer Gramps translation, or an addon update brings its own newer translation, the matching download is paused. This makes sure that an older download never hides newer work by the translators.

A paused download shows "paused" in the Status column. Press **Check for updates** to bring it up to date, and it is used again.

## Works well with Addon Locale Fix

Addon Locale Fix is a separate, small addon that corrects two old problems in how Gramps finds addon translations. With it installed, an addon that has no translation for your language still loads, and the translation that comes with an addon is used before the Gramps translation of the same phrase. Translation Updater works with or without it, and the two can be installed in any order.

## Where the files are kept

Downloaded packs are kept outside Gramps and outside your addon folders, in the `translation-packs` folder inside your Gramps user data folder. On Linux, that is usually `~/.local/share/gramps/translation-packs/`. Reinstalling or updating an addon does not touch them.

When you remove the check mark from a language and check for updates, the packs for that language are deleted.

Your settings are kept in `TranslationUpdater.ini`, in the same folder as the addon.

## Limitations

- Gramps needs to restart before every window shows the new translations. Text that Gramps translates each time it is shown, such as most dialogs, messages and reports, changes right away.
- Addons that start together with Gramps, and that happen to start before Translation Updater, keep their original translations until the next restart.
- On Windows, the Glade-built dialogs and the full-coverage launcher are not available. On macOS, the full-coverage launcher is not available.
- The packs follow the Gramps branch you are running (for example, the packs for Gramps 6.0). Phrases that only exist in a newer Gramps are simply ignored.

## For maintainers: publishing the packs

The `server` folder holds the tools that build and publish the packs. They are not part of the installed addon.

`build_translation_packs.py` reads the Weblate translations from a copy of the gramps and addons-source repositories, compiles them, and writes one manifest per language. It needs the GNU gettext tools (`msgfmt` and `msgmerge`).

```
python3 build_translation_packs.py --branch gramps60 --gramps ../gramps --addons ../addons-source --out ../site
```

`translation-packs.yml` is a GitHub Actions workflow. Copy it to `.github/workflows/` in the repository. It runs every day, builds packs for each supported Gramps branch, and publishes them to the `translation-packs` branch. You can also start it by hand from the Actions tab with **Run workflow**.

To test without publishing, run the builder on your own computer and enter the output folder as the source address under **Advanced**, for example `file:///home/you/site`.

## Assumptions I made

- The addon is called Translation Updater, with a startup part and a tool under Tools > Utilities.
- The packs are published every day by GitHub Actions to the `translation-packs` branch of CuratedGrampsPlugins.
- The packs are built from the newest translations on the Gramps maintenance branches (5.2, 6.0 and 6.1), not fetched directly from Weblate.
- Packs are downloaded only for addons that are installed in the user plugin folder.
- Checking at startup is turned off until the user turns it on.
- The full-coverage launcher is an extra menu entry, not a replacement for the normal one.
- The tool can only be opened while a family tree is open, like other tools.
- Addon Locale Fix stays a separate, optional addon rather than being built into Translation Updater.
- One screenshot is enough: the main window shows nearly everything a user touches, and the other windows are small or are described well in words.
