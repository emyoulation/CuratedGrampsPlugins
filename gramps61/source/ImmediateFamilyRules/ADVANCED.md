# Advanced Topics: Immediate Family Rules
[README](README.md) ● [CHANGELOG](CHANGELOG.md) ● [Advanced Topics](ADVANCED.md) ● [Forum discussion](https://gramps.discourse.group/t/addon-filter-rule-requests/4148)

This page is for people who want to change or extend the rules. It explains how the Gramps Filter Editor builds the rule widgets, how the rules do their work, and how to test them.

## How the Filter Editor builds rule widgets
The `EditRule` dialog in `gramps/gui/editors/filtereditor.py` reads the `labels` list of a rule and builds one row per entry. The code is the same in Gramps 5.2, 6.0 and 6.1. For each entry it does this:

1. If the entry is a string that matches one of the known label strings (`_("ID:")`, `_("Filter name:")`, `_("Person filter name:")`, `_("Family filter name:")`, `_("Inclusive:")` and others), it builds the matching built-in widget.
2. If the entry is a **tuple** `(label_text, factory)`, it shows `label_text` on the left and calls `factory(db)` to build the widget.
3. Anything else gets a plain text entry (`MyEntry`), with `str(entry)` as the label.

There is no other way in. A bare class in `labels` falls into step 3. That is why an earlier build of this addon showed rows such as `<class 'FamilyNetworkRules._BoolSelf'>` with empty text boxes instead of checkboxes. The factory receives only `db`, not `dbstate`, `uistate` or `track`, so a custom widget cannot open a Gramps selector dialog. That is the reason the ID field has no **Select...** button.

The labels in this addon mix both kinds:

```python
_PERSON_LABELS = [
    (_("Anchor type:"), _make_anchor_type),
    (_("ID or filter name:"), _AnchorValue),
    (_("Inclusive:"), _make_inclusive),
    (_degree_label(1), _degree_row(_DEGREE_1)),
    (_degree_label(2), _degree_row(_DEGREE_2)),
    (_degree_label(3), _degree_row(_DEGREE_3)),
]
```

A factory can be a plain function, a class, or a function that returns a function (as `_degree_row()` does, so each row knows its own checkboxes). Either way it must accept one argument and return a widget.

The Inclusive row reuses the core wording, `_("Inclusive:")` and `_("Include selected Gramps ID")`, so it needs no new translations. It is a tuple, not the bare known string, on purpose: the built-in widget for the bare string starts unchecked, and these rules start with every box checked. `_make_inclusive()` builds the same `MyBoolean` and checks it.

## The widget contract
Every widget must provide `get_text()` and `set_text(value)`, both using strings. `EditRule` calls `get_text()` when the rule is saved and `set_text()` when a saved rule is opened again. The saved string should not depend on the language of the user.

- `MyList(keys, labels)` shows the translated labels but saves the untranslated key (`"person_id"`, `"person_filter"`, `"family_id"`, `"family_filter"` or `"home_person"`), so saved filters work in every language.
- `_AnchorValue` is a `Gtk.ComboBoxText` with an entry. It saves whatever is in the entry, with spaces trimmed. It follows the Anchor type combo: the drop-down lists only Person filters or only Family filters, the placeholder text says what to type, the field is grayed out for Home Person, and a warning icon shows when an ID or filter name is not found. The factory receives `db`, which is enough to look up IDs and show the name of the person or family as a tooltip.
- The Inclusive checkbox (`MyBoolean`) saves `"1"` or `"0"`. `_make_inclusive()` checks it for a new rule.
- `_DegreeRow` is a `Gtk.FlowBox` holding one `Gtk.CheckButton` per relative. It must wrap: `EditRule` puts the value grid inside a scrolled window, so a plain horizontal `Gtk.Box` that is wider than the dialog runs off the right edge and hides its last checkboxes behind a horizontal scroll bar. It saves the checked keys as a comma-separated list, such as `"parents,spouses,children"`. The keys are English and never translated. A key that is missing counts as unchecked, so a checkbox added later starts unchecked in filters saved before it existed. All boxes start out checked for a new rule.

Keys in a single string also keep the saved filter readable, because `Rule.display_values()` shows each label next to its saved value in the filter list, for example `2 degrees:='siblings,parents_in_law'`.

Widgets of one rule normally know nothing about each other. `_AnchorValue` needs to follow the Anchor type combo, so `_make_anchor_type()` stores the combo it builds in `_LAST_ANCHOR_TYPE`, and `_AnchorValue` picks it up and connects to its `changed` signal. This works because `EditRule` builds the widgets of one rule in label order, and the anchor type label comes right before the value label. Restoring a saved rule also goes in label order: setting the anchor type clears the value, and then `EditRule` sets the saved value.

Cautions for new widgets:

- Do not use `_("")` as a label. `gettext("")` returns the header of the translation catalog, not an empty string, and every row needs a real label for `display_values()`.
- Define a GObject subclass such as `_DegreeRow` once, at module level. Defining it inside a factory would register a new GType on every call.
- Reuse strings that Gramps already translates where you can. "Parents", "Spouses", "Children", "Siblings" and "Associations" come from the Gramps catalog. The degree labels (one plural string, `"%d degree:"` / `"%d degrees:"`), the three in-law names and "As child" / "As parent" are new.

The GUI imports sit inside a `try` block, and `_HAVE_GUI` records the result. Without Gtk the module still loads, so the rules work from the command line and in tests. The widgets are only built inside the Filter Editor.

## Parameter layout
`Rule.list` holds one string per label, in the same order.

| Index | People rule | Families rule |
|---|---|---|
| 0 | Anchor type key, such as `person_id` | Anchor type key |
| 1 | ID or filter name, such as `I0044` | ID or filter name |
| 2 | Inclusive, `1` or `0` | Inclusive, `1` or `0` |
| 3 | 1 degree: `parents,spouses,children,associations` | 1 degree: `as_child,as_parent` |
| 4 | 2 degrees: `siblings,parents_in_law,children_in_law` | 2 degrees: `of_parents,of_siblings,of_spouses,of_parents_in_law,of_children` |
| 5 | 3 degrees: `siblings_in_law` | 3 degrees: `of_siblings_in_law,of_children_in_law` |

`_wanted()` reads indexes 2 and up and returns the Inclusive flag and the set of all checked keys, so a checkbox can move to another row later without breaking saved filters. Gramps checks that the number of saved values equals the number of labels, so adding or removing a whole row does break filters saved by older builds.

## The prepare() and apply_to_one() contract
The filter engine calls the rule once for every object in the tree, so that call must be cheap. All database work happens in `prepare()`, which runs once per filter run.

- `prepare()` builds a fresh set of handles named `selected_handles`. Gramps 6 has a filter optimizer that looks for an attribute with exactly that name and skips every object outside the set. Gramps 5.2 ignores it.
- `apply_to_one()` only tests membership in the set. Gramps 6.0 and newer call `rule.apply_to_one(db, obj)`, while Gramps 5.2 calls `rule.apply(db, obj)`, so each rule sets `apply = apply_to_one`. A rule that defines only `apply()` loads and edits fine in Gramps 6, then fails with an `AttributeError` the first time a filter runs.
- `reset()` empties the set after the run. Gramps calls it through `requestreset()`.
- The rules never keep a reference to `db`. They keep only the handles.

## Turning the anchor into people and families
`_resolve_anchors()` returns two lists, anchor people and anchor families:

| Anchor type | Anchor people | Anchor families |
|---|---|---|
| Person ID | That person | (none) |
| Person filter | Everyone the filter matches | (none) |
| Family ID | Both partners | That family |
| Family filter | Both partners of each family | Every family the filter matches |
| Home Person | `db.get_default_person()`; the ID or filter name is ignored | (none) |

Both rules then work from each anchor person. Inclusive decides about the anchor itself at the end: if checked, the anchor people (or anchor families) are added; if unchecked, they are removed. Removing matters for a Family anchor, where each partner is the spouse of the other, and the anchor family is a family of each partner.

An unknown ID, filter name or anchor type, or a tree with no Home Person, writes a warning to the log and matches nobody.

### People: relatives by degree
`_relatives()` walks the family graph around one anchor person and returns a set of Person handles for every key. One step is one parent, child or spouse link.

| Key | Relatives | Steps |
|---|---|---|
| `parents` | Partners of each family of origin | 1 |
| `spouses` | Other partners of each own family | 1 |
| `children` | Children of each own family | 1 |
| `associations` | People on the Associations tab | 1 (not a family link) |
| `siblings` | Other children of each family of origin | 2 |
| `parents_in_law` | Partners of the families of origin of each spouse | 2 |
| `children_in_law` | Spouses of each child | 2 |
| `siblings_in_law` | Siblings of each spouse, and spouses of each sibling | 3 |

### Families: families by degree
The Families rule uses a different graph. Its nodes are families, and two families are one step apart when one person belongs to both, as a partner or as a child. `_family_steps()` returns a set of Family handles for every key:

| Key | Families | Steps |
|---|---|---|
| `as_child` | Families of origin of the anchor person | 1 |
| `as_parent` | Own families of the anchor person | 1 |
| `of_parents` | Every family of the partners of the families of origin | 2 |
| `of_siblings` | Every family of the other children of the families of origin | 2 |
| `of_spouses` | The families of each spouse other than the ones the spouse was born into | 2 |
| `of_parents_in_law` | The families each spouse was born into | 2 |
| `of_children` | Every family of the children of the own families | 2 |
| `of_siblings_in_law` | Every family of the siblings of each spouse and of the spouses of each sibling | 3 |
| `of_children_in_law` | Every family of the spouses of each child | 3 |

`_all_family_handles()` gives "every family" of a person: the families of origin plus the own families. `_FAMILY_DEGREE_OF` maps each key to its row. `prepare()` collects every family each anchor person reaches, by degree, whether or not its box is checked, and a checked family is kept only at the closest degree any anchor person reaches it. So with a Family anchor the family of origin of one partner never shows up as a 2-degree parents-in-law family of the other partner, and the family of origin of a spouse never shows up again as a 3-degree sibling-in-law family.

## Running a named filter from inside a rule
`_run_named_filter()` follows the pattern of the core `MatchesFilterBase` rule. It takes the filter from the shared list `gramps.gen.filters.CustomFilters`, which the Gramps window has already loaded. If the list has not been loaded yet (for example from the command line), it calls `reload_custom_filters()` first.

It then calls `named.apply(db, user=user)`. `GenericFilter.apply()` prepares and resets the rules of that filter by itself, in both Gramps 5.2 and 6.x.

A filter could name itself as its own anchor, directly or through another filter. `_ACTIVE_FILTERS` remembers which filters are running, and a second entry into the same filter logs a warning and returns nothing instead of recursing forever.

## Why two rules
One rule per output type keeps the Filter Editor short. The anchor type drop-down covers all five kinds of anchor, and a sixth kind would mean one more key in `_ANCHOR_KEYS` and one more branch in `_resolve_anchors()`, not another rule. A new kind of relative means one entry in a `_DEGREE_n` list and a few lines in `_relatives()`; a new group of families means one entry in a `_FAMILY_DEGREE_n` list and a few lines in `_family_steps()`.

## Registration
`ImmediateFamilyRules.gpr.py` registers both rules inside one `if VERSION_TUPLE >= (5, 2, 0):` block, with `gramps_target_version=major_version`. Each registered `id` must be unique across all Gramps addons, so the ids use the form `ImmediateFamilyRules_<ClassName>`. A new rule needs a class in `ImmediateFamilyRules.py`, a matching `register(RULE, ...)` call with `ruleclass` set to the class name and `namespace` set to the object type it matches, and tests.

## Testing
`ImmediateFamilyRules_test.py` uses `unittest` and mock databases, so it needs the Gramps Python sources but no display and no family tree. To run it against a Gramps source checkout instead of an installed Gramps:

```bash
PYTHONPATH=/path/to/gramps python3 -m unittest ImmediateFamilyRules_test
```

The `gramps.gen.lib` package of Gramps 6 also needs the `orjson` module.

The tests cover:

- the label shapes: `(text, factory)` tuples everywhere, with the core `Inclusive:` wording at index 2, so the widget bug cannot come back quietly
- the key parser, the degree labels and `_wanted()`
- each degree row on its own, Inclusive on its own, and everything checked
- siblings-in-law from both sides
- Person ID, Family ID, Person filter and Home Person anchors, including a tree with no Home Person
- unknown IDs, unknown filter names and unknown anchor types (warning, no matches)
- a missing family record being skipped
- a second `prepare()` call starting from an empty set
- both rules run through a real Gramps `GenericFilter.match()`, which uses `apply()` on 5.2 and `apply_to_one()` on 6.x, the way the Filter sidebar does
- the Families rule: each key of each row on its own, everything checked, and a Family anchor with Inclusive on and off

The tests cannot open the Filter Editor itself, so check the Add Rule dialog by eye after changing any label or widget.
