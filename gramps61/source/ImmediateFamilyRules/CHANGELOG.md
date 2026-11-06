# Immediate Family Rules Changelog
[README](README.md) ● [CHANGELOG](CHANGELOG.md) ● [Advanced Topics](ADVANCED.md) ● [Forum discussion](https://gramps.discourse.group/t/addon-filter-rule-requests/4148)

## 0.1.1 (2026-11-06)
- Fixed the Add Rule dialog. Every value row showed a label such as `<class 'FamilyNetworkRules._BoolSelf'>` beside an empty text box. The rows now have proper labels, an anchor type drop-down and real checkboxes.
- Fixed an "Unhandled exception" error in Gramps 6 whenever a filter that uses either rule was run, for example from the Filter sidebar.
- Rearranged the relative checkboxes into rows by degrees of separation (1, 2 and 3 degrees) instead of one "Include" checkbox per row. Including the anchor itself uses the familiar Gramps wording, "Inclusive: Include selected Gramps ID". Every checkbox, Inclusive included, starts out checked, and a row wraps onto a second line when the dialog is too narrow to show all of its checkboxes.
- Redesigned the Families rule to select families, not to mirror the people checkboxes. At 1 degree it finds the families of the anchor person as child or as parent. At 2 degrees it finds the families of the parents, siblings, spouses, parents-in-law and children. At 3 degrees it finds the families of the siblings-in-law and children-in-law.
- The ID or filter name field now follows the anchor type. For a filter anchor, its drop-down lists only the custom filters of that kind. For an ID it shows the name of the person or family, a warning icon marks an ID or filter name that cannot be found, and for Home Person the field is grayed out. Before, the field listed every filter whatever the anchor type, so a filter name could be picked while the anchor type still said Person ID, and the rule then quietly matched nobody.
- Renamed the addon from FamilyNetworkRules to Immediate Family Rules (`ImmediateFamilyRules`) and moved it to the Emyoulation addons collection. Rules saved under the old name must be added again.
- Fixed the Person filter and Family filter anchors, which could not find any custom filter. They now use the custom filters already loaded by Gramps.
- Fixed the Families rule, which always matched the families of the anchor person even with every checkbox unchecked. It now follows the checkboxes.
- Added Home Person as an anchor type. A saved filter follows the Home Person of the tree, so it stays useful when you change the Home Person.
- Split In-laws into Parents-in-law, Children-in-law and Siblings-in-law. Siblings-in-law now also covers the spouses of brothers and sisters, and Children-in-law is new.
- A filter that uses itself as its own anchor now matches nobody and writes a warning to the log, instead of running forever.
- The People rule no longer counts a spouse as their own sibling-in-law.
- Filters on large trees run faster in Gramps 6, which can now skip everyone outside the matched group.
- Added support for Gramps 5.2.
- Filters saved with 0.1.0 do not open correctly. Delete and add the rule again.
- Rewrote the README and Advanced Topics pages, and added this changelog.

## 0.1.0
- First build, named FamilyNetworkRules: two filter rules, "People in the immediate families of \<anchor\>" and "Families in the immediate families of \<anchor\>", with an anchor type selector and seven include options.

## Outstanding issues
Ideas and open questions for later releases.

### Planned / NYI
- A **Select...** button for the ID field. The Filter Editor gives custom widgets only the database, not what a selector dialog needs.

### Needs discussion
- With a Family anchor, should "Include selected Gramps ID" in the People rule include the children of the anchor family, or only the two partners?
- Should more distant relatives (grandparents, grandchildren, aunts, uncles) get their own checkboxes in the degree rows, or stay with the built-in Ancestral and Descendant filters?
- Should Associations also include people who list the anchor person on their own Associations tab?
- "Degree" counts different things in the two rules: person-to-person links in the People rule, family-to-family hops in the Families rule. Try giving the Families rule its own row labels, such as "1 step:" and "2 steps:" (one more plural string to translate), if testing shows that users confuse the two.

### Beyond scope
- Cousins and other relatives beyond three degrees. The built-in Ancestral, Descendant and Relationship filters cover these.
