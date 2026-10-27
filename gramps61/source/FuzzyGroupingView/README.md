# Fuzzy Grouping

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

![Fuzzy Grouping icon](media/fuzzy-grouping.svg)

Fuzzy Grouping is a view for the People category of Gramps. It works like the built-in Grouped People view, but it puts people into groups by how their surnames sound, not by exact spelling. Smith, Smyth and Schmidt can appear in one group, so spelling variants of a family are easy to see side by side.

![The Fuzzy Matching person View mode](media/screenshot.png)

## Requirements
- Gramps 5.2, 6.0 or 6.1.
- Optional: the [Phonetic Filter Rules](https://github.com/emyoulation/CuratedGrampsPlugins/blob/main/gramps61/source/FuzzyRules/README.md) addon. Without it, the view uses Soundex only. With it, the view can also use NYSIIS, Match Rating Approach, Phonex, Metaphone, Double Metaphone and Daitch-Mokotoff.
- Optional: the Markdown Dash addon, to read this document inside Gramps from the Help icon.
- Recommended: PyICU, for correct subsorting. Most Gramps installations include it.

## Opening the view
Choose the **People** category, then click the **Fuzzy Grouping** button on the toolbar, or choose **Fuzzy Grouping** from the **View** menu.

The first time the view opens, the Configure dialog also opens, so that you can choose how groups are sorted. You can open it again at any time with the **Configure...** toolbar button.

## Reading the groups
Each group row lists the surname spellings in the group, the most used spelling first, followed by the phonetic code in brackets. For example: `Smith, Smyth, Schmidt +2 [S530]`. When a group has more than four spellings, "+N" tells how many more spellings the group has.

People with no surname are in a group of their own at the top.

A "Group as" value on a name, and the surname group mapping table of Gramps, still apply. The phonetic code is made from the group name that those settings give.

## Choosing the phonetic system
The toolbar has a menu button that shows the view icon and the name of the current phonetic system. Click it and choose another system. The view rebuilds its groups at once.

Soundex is always available and is the default. If the system that you chose earlier is no longer installed, the view goes back to Soundex.

## Getting help
The Help icon on the toolbar shows this document. If Markdown Dash is installed and active, the document opens inside Gramps. Otherwise, the Help web page opens in your browser. Hold the pointer over the icon to see which one a click will open.

## Configure: Columns tab
At the top of the Columns tab, **Grouping:** sets the order of the groups:
- **Fuzzy grouping ID** (the default) sorts the groups by their phonetic code.
- **Sample Surname** sorts the groups alphabetically by the most used spelling in each group.

The first column of the view is named **Grouping**. It always stays first. Below the Grouping choice, the usual list of columns works the same as in the Grouped People view: check a column to show it, drag a column to move it, then click **Apply**.

## Configure: Subsorting tab
The Subsorting tab sets the order of the people inside each group.

**Name format** chooses how names are compared for sorting. This choice is used only for sorting in this view. It does not change the Name format in the Gramps Preferences. The **Default** choice is your current Display name format without the surname parts, because the people in a group already have similar surnames. Click the edit icon to open the Display Name Editor and make your own formats. When you close the editor, the format that you last selected in it is chosen here.

Below Name format is a numbered list of everything that can be used for sorting. The view sorts by number 1 first, then uses number 2 when number 1 is the same, and so on. To change the order, drag a line to a new place, or click its number and type a new number. The first order is:
1. Name format
2. Birth Date
3. Death Date
4. Spouse
5. Last Changed
6. The other columns, in the order of the Columns tab

The subsort is used when the view is sorted by the Grouping column. When you click another column header, the view sorts by that column only, the same as the Grouped People view.

## When changes take effect
Changes in the Configure dialog take effect 5 seconds after your last change, so that several quick changes need only one rebuild. When you close the Configure dialog, a waiting change takes effect at once. The **Apply** button of the Columns tab and the phonetic system menu take effect at once.

When building the groups takes more than 1 second, a progress window shows how far the work has gone.

## Settings
The settings are saved in the file `FuzzyGrouping.ini` in the addon folder. To see the Configure dialog again on the next visit to the view, as on first use, close Gramps and delete that file.

## Assumptions I made
This list is for review while the addon is in draft.
- Groups are sorted by code by default. Daitch-Mokotoff codes are numbers, so with that system the group order looks random unless you choose Sample Surname.
- Systems that can give more than one code for a name (Daitch-Mokotoff, Double Metaphone) use the lowest code, so that each person is in exactly one group. Two spellings that share only a second code can end up in different groups.
- Sample Surname order is set when the groups are built. A person added later does not move a group, even if that person changes which spelling is used most.
- The progress window appears for every full rebuild, not only the first one after Gramps starts.
- The phonetic system menu is at the right end of the toolbar, with the Help icon after it.
- The Default name format keeps Familynick, because it is a nickname and not a surname part.
