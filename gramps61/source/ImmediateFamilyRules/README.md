# Immediate Family Rules
[README](README.md) ● [CHANGELOG](CHANGELOG.md) ● [Advanced Topics](ADVANCED.md) ● [Forum discussion](https://gramps.discourse.group/t/addon-filter-rule-requests/4148)

Sometimes you want to look at one person together with the people closest to them: parents, brothers and sisters, husbands, wives and partners, children, in-laws, and friends or witnesses. Building that group with the standard Gramps filter rules takes many rules joined together. This addon gives you that whole group in one filter rule.

There are two rules. One finds the people. The other finds the Family records around a person: the families the person belongs to, and the families of everyone in those families.

## The two rules
| Rule | Where to find it | What it matches |
|---|---|---|
| People in the immediate families of \<anchor\> | Person filters, under **Family filters** | People in the immediate families of the anchor |
| Families in the immediate families of \<anchor\> | Family filters, under **Family filters** | The families of the anchor, and the families of the people in them |

## Choosing the anchor
The anchor is the starting point. The first two values of each rule describe it.

**Anchor type** is a drop-down list with five choices:

| Choice | The anchor is |
|---|---|
| Person ID | One person, given by Gramps ID |
| Person filter | Every person matched by one of your custom Person filters |
| Family ID | One family, given by Gramps ID. Both partners of the family become anchor people. |
| Family filter | Every family matched by one of your custom Family filters, and the partners of each |
| Home Person | The Home Person of the family tree. A filter with this choice follows the Home Person when you change it. |

**ID or filter name** changes to match the anchor type, so choose the anchor type first. For Person ID or Family ID, type the Gramps ID (for example `I0044` or `F0012`). For Person filter or Family filter, pick the filter from the drop-down list, which shows only the custom filters of that kind. For Home Person, the field is grayed out because nothing is needed. A warning icon appears when the ID or filter name cannot be found. When an ID is found, hold the pointer over the field to see the name of the person or family.

## Choosing who to include
The remaining values are checkboxes, arranged by how far each relative is from the anchor person.

**Inclusive** uses the same wording as other Gramps rules. **Include selected Gramps ID** includes the anchor itself: the anchor people in the People rule, or the anchor families in the Families rule. Like every checkbox in these rules, it starts out checked.

The degree rows count steps through the family tree. One step is one link between a parent and a child, or between two spouses. Uncheck the relatives you do not want.

| Row | Checkboxes | How the steps add up |
|---|---|---|
| 1 degree | Parents, Spouses, Children, Associations | One direct link to the anchor |
| 2 degrees | Siblings, Parents-in-law, Children-in-law | Sibling: up to a parent, then down. Parent-in-law: to the spouse, then up. Child-in-law: to the child, then to the spouse of the child. |
| 3 degrees | Siblings-in-law | Brothers and sisters of the spouse, and spouses of the brothers and sisters of the anchor |

The rows show something that families often find surprising. Most people think of a brother or sister as close family, but counted in steps, a sibling is two degrees away, the same distance as a grandparent. A sibling-in-law is three steps away, the same distance as an aunt or uncle. This rule keeps the people a family would call "immediate family" together, and the rows show how far each group really is.

Associations are people listed on the Associations tab of the anchor person, such as godparents, friends or witnesses. They are a direct link, so they sit in the first row, even though they are not family.

## Choosing families
The Families rule counts steps between families instead of between people. Two families are one step apart when one person belongs to both, as a parent or as a child. All checkboxes start out checked.

| Row | Checkbox | Families returned |
|---|---|---|
| Inclusive | Include selected Gramps ID | The anchor families (Family ID or Family filter only) |
| 1 degree | As child | The families the anchor person was born into |
| 1 degree | As parent | The families the anchor person formed |
| 2 degrees | Parents | All other families of the parents: the families they were born into, and other marriages |
| 2 degrees | Siblings | All other families of the brothers and sisters, such as the families they formed |
| 2 degrees | Spouses | Other marriages of the spouses |
| 2 degrees | Parents-in-law | The families the spouses were born into |
| 2 degrees | Children | All other families of the children, such as the families they formed |
| 3 degrees | Siblings-in-law | All other families of the brothers and sisters of each spouse, and of the spouses of each brother and sister |
| 3 degrees | Children-in-law | All other families of the spouses of the children, such as the families they were born into |

A row never repeats a family that a closer row already found. With a Family anchor, both partners are anchor people, so the family each partner was born into is 1 degree away.

For example, start from Anna. At 1 degree you get the family she grew up in and the family she formed with her husband. At 2 degrees, Parents adds the family her father grew up in and his second marriage, Parents-in-law adds the family her husband grew up in, and Children adds the families her children formed. At 3 degrees, Siblings-in-law adds the family her sister-in-law formed and the family her brother-in-law grew up in, and Children-in-law adds the families her daughters-in-law and sons-in-law grew up in.

## Using a rule
1. In the People view, open **Edit → Person Filter Editor**. For the Families rule, use **Edit → Family Filter Editor** in the Families view.
2. Create a new filter and click **Add Rule**. To start from a group of people, such as everyone with a tag, first make a custom filter for that group.
3. Type *immediate* in the search box and pick the rule under **Family filters**.
4. Choose the anchor type and enter the ID or filter name. Uncheck **Include selected Gramps ID** if you do not want the anchor itself, and uncheck any relatives you do not want.
5. Click **OK**, save the filter, and pick it from the **Custom filter** list in the Filter sidebar.

You can combine this rule with other rules in the same filter. For example, add "People with the \<tag\>" and choose "All rules must apply" to see only the tagged members of an immediate family group.

## Installing
Immediate Family Rules is part of the Emyoulation addons collection. If you have not used the collection before, follow the setup steps on the [CuratedGrampsPlugins](https://github.com/emyoulation/CuratedGrampsPlugins/) page to add it to the Gramps Addon Manager. Then open the Addon Manager, find **Immediate Family Rules**, install it, and restart Gramps.

To install by hand instead, copy the `ImmediateFamilyRules` folder from [gramps61/source](https://github.com/emyoulation/CuratedGrampsPlugins/tree/main/gramps61/source) into your Gramps plugins folder and restart Gramps. On Linux, the plugins folder is inside `~/.local/share/gramps/` in a folder named for your Gramps version, for example `gramps60/plugins/`.

## Good to know
- A filter that uses a Person filter or Family filter as its anchor runs that other filter first, so large trees can take a moment longer.
- If the anchor ID or filter name cannot be found, or the tree has no Home Person, the rule matches nobody. The reason is written to the Gramps log.
- A filter cannot use itself as its own anchor. The rule notices this, matches nobody and writes a warning to the log.

## Assumptions made in this draft
- With a Family anchor, **Include selected Gramps ID** in the People rule means the two partners only. The children of the anchor family come from the Children checkbox.
- With several anchor people (a Person filter or a Family filter), unchecking **Include selected Gramps ID** leaves out every anchor person, even one who is also a relative of another anchor.
- Associations means the people on the Associations tab of the anchor person, not people who list the anchor on their own Associations tab.
- The ID field has no **Select...** button, because one field serves several anchor types.
