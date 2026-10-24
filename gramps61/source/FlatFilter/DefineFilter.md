# Saving a filter gramplet search as a custom filter

[Read Me](README.md) ● [Change Log](CHANGELOG.md) ● [Define Filter](DefineFilter.md)

A developer reference. It explains how the **Define filter** button of Gramps 6.0 works, why it could not save Flat Filter searches without help, what Flat Filter 2.0.1 (Kari Kujansuu) does about that, what is still missing, and a recipe for giving any other filter gramplet the same ability.

**Sources:** the Gramps 6.0.8 source (`gramps/gui/filters/sidebar/_sidebarfilter.py`, `gramps/gen/filters/_filterparser.py`, `gramps/gen/filters/_filterlist.py`, `gramps/gen/plug/_manager.py`) and `FlatFilter.py` 2.0.1, both checked on 23 October 2026. Nothing below has been run in Gramps unless it says so.

## What the Define filter button does
Gramps 6.0 added a **Define filter** button to `SidebarFilter`, the base class of every sidebar filter and of filter gramplets such as Flat Filter. Gramps 5.2 does not have it. When clicked, `SidebarFilter.define_filter()`:
1. Calls `self.get_filter()`, the same method **Find** uses. If it returns `None` (every box blank), it shows "Supply at least one value" in `self.msg_label` and stops.
2. Runs `self.filter_is_ok()`, which only checks the Place rule `WithinArea`.
3. Converts a few known rule arguments to strings (`WithinArea` can hold numbers, and `custom_filters.xml` only stores strings).
4. Sets a comment such as "Created by Filter gramplet on 2026-10-23".
5. Opens `EditFilter` (the Define Filter dialog) with the rules filled in, the custom filter list `gramps.gen.filters.CustomFilters`, and `update=self.update`.

When the person clicks OK in that dialog, `SidebarFilter.update()` saves `custom_filters.xml`, reloads the custom filters, and emits `filters-changed` so every custom filter list in Gramps refreshes.

## How custom filters are stored and loaded
`custom_filters.xml` stores each rule by its **class name**, its two flags, and its arguments as strings:

```xml
<rule class="HasNameOf" use_regex="False" use_case="False">
  <arg value="John"/>
  ...
</rule>
```

When Gramps reads the file (`_filterparser.py`), it finds each class by name, first as a fully qualified name, then as `gramps.gen.filters.rules.<namespace>.<ClassName>`. It then builds the rule with exactly three positional arguments:

```python
rule = rule_class(list_of_string_args, use_regex, use_case)
```

If the class cannot be found, it prints `ERROR: Filter rule '...' in filter '...' not found!` and drops that rule. If the number of arguments differs from `len(rule_class.labels)`, it prints a warning and tries to cope.

So a rule survives being saved and loaded again only if all three of these are true:
1. **Findable:** its class can be found by name in `gramps.gen.filters.rules.<namespace>`. Core rules are there. An addon rule gets there only by being registered as a `RULE` plugin.
2. **Constructible:** its constructor accepts `(arg_list, use_regex, use_case)` and nothing else is required.
3. **Complete:** everything that decides what it matches is in its string arguments and the two flags. Nothing may live only in extra constructor arguments or Python objects.

## Why Flat Filter rules could not be saved as they were
The rules that `FlatFilter.get_filter()` builds fail all three tests:
1. **Not findable.** `HasNamedFather`, `HasName`, `RegExpPersonal` and the others are ordinary classes inside `FlatFilter.py`. They are not registered, so the parser cannot find them, and the saved rule is dropped.
2. **Not constructible.** `_HasNamedRelation` and its subclasses take a second, required argument: the **name matcher class** (`RegExpPersonal` or `RegExpFamily`). The parser would pass `use_regex` in that place.
3. **Not complete.** Several settings exist only as constructor keyword arguments: the phonetic `encoder` (a Python function), and, for the Person row, `personal_fields`, `surname_fields` and `include_alternates` from the **Include:** checkboxes.

With the unchanged core `define_filter()`, the Define Filter dialog would open and save, but the saved filter would lose its Flat Filter rules the next time Gramps read `custom_filters.xml`.

## What Flat Filter 2.0.1 does
Kari Kujansuu solved tests 1 and 2 with one registered "carrier" rule that can stand in for any Flat Filter name rule.

### 1. A registered carrier rule
`FlatFilter.gpr.py` registers a second plugin besides the gramplet:

```python
if (6, 0, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        id="FlatFilterRule",
        name=_("Flat Filter rule"),
        description=_(
            "Rule used by custom filters saved with the Define filter "
            "button of the Flat Filter gramplet"
        ),
        version="0.0.1",
        gramps_target_version=major_version,
        status=STABLE,
        fname="FlatFilter.py",
        ruleclass="FlatFilterRule",  # rule class name
        namespace="Person",  # one of the primary object classes
        authors=["Kari Kujansuu"],
    )
```

Kari first named it `GenericRule`, registered for `gramps_target_version = "6.0"` only. Before 2.0.1 was shared, it was renamed `FlatFilterRule` and given `major_version` inside a 6.0-and-later range, for the reasons in "Naming and version rules" below.

At startup, for each `RULE` plugin, Gramps imports its module (here the whole of `FlatFilter.py`), takes the class named by `ruleclass`, adds it to `gramps.gen.filters.rules.person` with `setattr()`, and appends it to `editor_rule_list` (`BasePluginManager.reg_plugins()` in `_manager.py`). That makes `FlatFilterRule` findable by the filter parser, and also makes it appear in the Filter Editor.

### 2. The carrier rule class
In `FlatFilter.py`:

```python
class FlatFilterRule(Rule):
    labels = ["Name:", "Rule class:", "Name matcher class:"]
    name = _("Flat Filter rule")
    allow_regex = True
    def prepare(self, db, user):
        rule_class = globals()[self.list[1]]
        self.name_matcher = globals()[self.list[2]]
        self.rule = rule_class(self.list[0:1], self.name_matcher, use_regex=self.use_regex)
        self.rule.name_matcher.requestprepare(db, user)
    def apply_to_one(self, db, person):
        return self.rule.apply_to_one(db, person)
```

It has the standard `Rule` constructor, so test 2 passes. Its three string arguments are the search text, the class name of the real rule, and the class name of the name matcher. `prepare()` looks both classes up in the module namespace of `FlatFilter.py`, builds the real rule, and prepares its name matcher. `apply_to_one()` hands every person to the real rule.

### 3. Wrapping the rules before the dialog opens
`PersonSidebarFilter.define_filter()` in `FlatFilter.py` replaces the core method. It does the same as core, except that it wraps each rule first:

```python
for rule in the_filter.get_rules():
    if not isinstance(rule, _HasNamedRelation):
        # A core rule (ProbablyAlive): Gramps can already save and
        # reload it by class name, and it has no name_matcher.
        new_rules.append(rule)
        continue
    rule1 = FlatFilterRule(
        rule.list
        + [rule.__class__.__name__, rule.name_matcher.__class__.__name__],
        use_regex=rule.use_regex,
    )
    new_rules.append(rule1)
```

Every Flat Filter name rule is a `_HasNamedRelation`. The only other rule `get_filter()` adds is the core `ProbablyAlive`, which passes all three tests by itself and is saved unchanged. (In the first draft of 2.0.1 the loop wrapped every rule, so a filled-in **Probably Alive** raised `AttributeError` and the dialog never opened.)

So a Flat Filter search for a father named John is saved like this:

```xml
<rule class="FlatFilterRule" use_regex="False" use_case="False">
  <arg value="John"/>
  <arg value="HasNamedFather"/>
  <arg value="RegExpPersonal"/>
</rule>
```

### The full round trip
1. The person fills in Flat Filter and clicks **Define filter**.
2. `get_filter()` builds the real Flat Filter rules, as for **Find**.
3. `define_filter()` wraps each one in a `FlatFilterRule` and opens the Define Filter dialog.
4. On OK, `update()` writes `custom_filters.xml` with `class="FlatFilterRule"`.
5. On the next start, Gramps registers `FlatFilterRule` from `FlatFilter.gpr.py`, reads the XML, finds `rules.person.FlatFilterRule`, and builds it with the three saved strings.
6. When the custom filter runs, `FlatFilterRule.prepare()` rebuilds `HasNamedFather` with the `RegExpPersonal` matcher, and `apply_to_one()` asks it about each person.

## Known gaps in 2.0.1
These are the starting points for the next version. Item 1 changes what a person sees.
1. **Some settings are silently lost** (test 3). The carrier stores only the text, the two class names and `use_regex`. So a saved filter matches differently from **Find** whenever:
   - **Use fuzzy matching** was on. The saved filter would do a plain substring match instead, so `Smith` would no longer find `Smyth`. Until the carrier can store the phonetic system, `_update_define_filter_button()` dims **Define filter** whenever **Use fuzzy matching** is checked, with a tooltip saying why. It runs from `cb_fuzzy_toggled()`, so it also follows **Reset**, saved settings, and the regular expression checkbox turning fuzzy matching off.
   - The **Include:** checkboxes of the Person row were changed from searching every name part, or **Alternatives** was turned off.
2. **Class names become a saved contract.** The second and third arguments are names of classes in `FlatFilter.py`. Renaming `HasNamedFather`, `RegExpPersonal` or any other rule or matcher class breaks filters saved with the old name. `globals()[name]` also raises `KeyError` for any name that is not there.
3. **The carrier shows in the Filter Editor.** Because it is in `editor_rule_list`, a person can add "Flat Filter rule" by hand and must then type internal class names into "Rule class:" and "Name matcher class:". A typing mistake fails only when the filter runs.
4. **Saved filters need Flat Filter installed.** If the addon is removed or deactivated, the rule is not registered, and those filters lose their rules at the next start.
5. **Small details:**
   - The error message uses red Pango markup, while core uses the `error` style class on `msg_label`.
   - `FlatFilterRule` has no `reset()`, so its inner rule is never reset after a run. Its name matcher keeps any prepared state until the next `prepare()`.
   - `FlatFilterRule` has no `apply()` alias for Gramps 5.2. This is harmless only while the rule is registered for 6.0 and later.

## Naming and version rules
Two more problems in the first draft of 2.0.1 were fixed before it was shared. Both apply to every carrier rule.

**A unique name.** Gramps resolves names in three shared places, and a duplicate replaces the other one silently, with no warning (checked in the Gramps 6.0.8 source):
1. **Plugin ids.** When two `.gpr.py` files register the same id, the one scanned later replaces the earlier one in the plugin registry (`scan_dir()` in `_pluginreg.py`).
2. **Rule classes.** Each `RULE` plugin class is placed in `gramps.gen.filters.rules.<namespace>` with `setattr()`, so a second Person rule with the same class name overwrites the first.
3. **Saved filters.** `custom_filters.xml` stores only the bare class name, with no module or addon. A saved filter gets whichever class won step 2.

The first draft used `GenericRule`, a name any addon could choose. SuperTool, also by Kari, already saves filters with a similar pattern, `GenericFilterRule_<Namespace>`. The carrier is now `FlatFilterRule`. Because saved filters record the class name, it must never change again.

**The registered Gramps version.** Gramps registers a plugin only when its `gramps_target_version` matches the running major version (`valid_plugin_version()` in `_pluginreg.py`). The first draft hard-coded `"6.0"`, so on Gramps 6.1 the carrier was not registered, and every saved Flat Filter rule failed to load with "Filter rule '...' not found!". The registration now uses `major_version`, inside a 6.0-to-6.2 range, because Define filter does not exist on Gramps 5.2.

## Recipe: giving another filter gramplet Define filter support
### Step 1: decide whether anything is needed
List every rule class that your `get_filter()` can add. For each one, apply the three tests above (findable, constructible, complete).
- **All core rules, or registered `RULE` plugins, with only string arguments:** do nothing. The core `define_filter()` already works.
- **Any private rule, any extra constructor argument, or any setting that lives outside the string arguments:** you need a carrier rule (step 2) and a conversion step (step 3).

### Step 2: write one carrier rule per gramplet
- **Give it a specific, permanent class name**, such as `<AddonName>Rule`. Use the same name as the `RULE` plugin id. Never rename it after release.
- **Use the standard constructor:** `(arg, use_regex=False, use_case=False)`. Do not add required parameters.
- **Put everything in string arguments.** Make the first argument a format version, such as `"1"`, so a later version can read filters saved by an earlier one. Then store the search text, the real rule name, the matcher name, and every setting that changes the result: phonetic system id, name-part flags, alternates flag, and so on. Store booleans as `"0"`/`"1"` and lists as comma-separated text.
- **Rebuild in `prepare()`, not `__init__()`.** The parser builds the carrier while reading XML at startup, when other plugins (such as a phonetic system provider) may not be loaded yet.
- **Look classes up in an explicit table**, for example `_SAVEABLE_RULES = {"HasNamedFather": HasNamedFather, ...}`, rather than `globals()`. An unknown name should make the rule match nobody and log a warning, rather than raise.
- **Implement `prepare()`, `reset()` and `apply_to_one()`**, plus `apply = apply_to_one` if the addon also supports Gramps 5.2.
- **Give it readable `labels`, a translated `name`, and a `description` and `category`**, since it appears in the Filter Editor. Say there that it is made by your gramplet and is not meant to be added by hand.

### Step 3: convert only what needs converting
Override `define_filter()` in your `SidebarFilter` subclass. Keep everything the core method does, and add one conversion step:

```python
def define_filter(self, _obj):
    """Save the current search as a custom filter (Gramps 6.0 and later)."""
    self.filterdb = gramps.gen.filters.CustomFilters
    the_filter = self.get_filter()
    if the_filter is None:
        self.msg_label.set_text(_("Supply at least one value"))
        self.msg_label.get_style_context().add_class("error")
        return
    the_filter.flist = [self._to_saveable(rule) for rule in the_filter.get_rules()]
    the_filter.set_comment(
        _("Created by the {gramplet} gramplet on {today}").format(
            gramplet=_("Flat Filter"),
            today=time.strftime("%Y-%m-%d", time.localtime()),
        )
    )
    self.msg_label.set_text("")
    EditFilter(
        self.namespace, self.dbstate, self.uistate, [],
        the_filter, self.filterdb, update=self.update,
    )

def _to_saveable(self, rule):
    """Wrap a private rule in the carrier rule; pass core rules through."""
    if type(rule).__name__ not in _SAVEABLE_RULES:
        return rule  # a core rule, such as ProbablyAlive
    return AddonNameRule(encode_rule(rule), use_regex=rule.use_regex)
```

`encode_rule()` is the single place that turns a private rule and its settings into the string list of the carrier. The carrier `prepare()` is its exact inverse. Keep the two next to each other in the source, and test them together.

Copy any later fixes from the core `define_filter()` (such as the `WithinArea` conversion and `filter_is_ok()`) if your gramplet can produce those rules.

### Step 4: register the carrier
In the `.gpr.py`, next to the gramplet registration:

```python
if (6, 0, 0) <= VERSION_TUPLE <= (6, 2, 0):
    register(
        RULE,
        id="AddonNameRule",
        name=_("Addon Name rule"),
        description=_("Rule used by filters saved from the Addon Name gramplet"),
        version="1.0.0",
        gramps_target_version=major_version,
        status=STABLE,
        fname="AddonName.py",
        ruleclass="AddonNameRule",
        namespace="Person",
        authors=["..."],
    )
```

`namespace` must match the namespace of the sidebar filter (`Person`, `Family`, `Event`, and so on). `fname` is imported at every Gramps start, so keep that module quick to import.

### Step 5: test the round trip
1. Fill in the gramplet, click **Find**, and note the number of matches.
2. Click **Define filter**, name the filter, and save it.
3. Restart Gramps. Watch the terminal for "not found" or "Too many/few arguments" messages.
4. Choose the saved filter in the **Custom filter** list of the core Filter sidebar and click **Find**. The count must equal step 1.
5. Repeat for every row, every matching mode, and every setting that the carrier stores. Include the core rules, such as Probably Alive.
6. Open the filter in the Filter Editor and check that the carrier arguments are readable.
7. Deactivate the addon, restart, and confirm that the failure is understandable.
8. Test on every Gramps version the `.gpr.py` allows.
