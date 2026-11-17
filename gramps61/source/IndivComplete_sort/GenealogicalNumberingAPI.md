# Genealogical Numbering module — developer guide
`genealogical_numbering.py` gives any Gramps report, gramplet or tool the same set of identifier options: a Person label, a Family label, a Center Person, and separate ancestor and descendant numbering systems. It works with Gramps 5.2 and newer.

## Files
| File | Purpose |
|---|---|
| `genealogical_numbering.py` | Numbering systems, menu options, labels. No GTK code, so it is safe for the command line. |
| `center_person_gui.py` | Optional GUI widgets: the Center Person list and the Attribute submenus. Loaded automatically, only when the Gramps window is running. |

Copy both files into your addon folder. Import the module at the top of your plugin module (not inside a function): Gramps removes the plugin folder from `sys.path` after the plugin is imported, so a later import fails.

## Quick start
```python
import os
import genealogical_numbering as gn

gn.use_attribute_memory("<plugin id>", os.path.dirname(__file__))

# Options class: add_menu_options(self, menu)
category_name = _("Identifiers")
gn.add_person_label_option(menu, category_name, self.__db)
gn.add_numbering_options(menu, category_name, self.__db)
gn.add_family_label_option(menu, category_name, self.__db)

# Report class
person_label = gn.person_label_from_menu(menu)
family_label = gn.family_label_from_menu(menu)
anc, desc = gn.numbering_from_menu(self._db, menu, person_label)
```

## Menu options
| Option name | Constant | Values | Default |
|---|---|---|---|
| `inc_id` | `OPT_PERSON_LABEL` | `none`, `gramps_id`, `attr:<type>` | `gramps_id` |
| `num_focal` | `OPT_FOCAL` | `home`, `active`, a Gramps ID | `home` |
| `num_ancestor` | `OPT_ANCESTOR` | `none`, a system id, `attr:<type>` | `none` (or `default_ancestor`) |
| `num_descendant` | `OPT_DESCENDANT` | `none`, a system id, `attr:<type>` | `none` |
| `family_label` | `OPT_FAMILY_LABEL` | `none`, `gramps_id`, `attr:<type>` | `gramps_id` |

The Person label reuses the name `inc_id` from the core "Include Gramps ID" option, so saved settings and Books from core reports carry over (0 becomes `none`, 1 or 2 becomes `gramps_id`). All values are strings, so they stay valid in saved settings, Books and command lines when systems or attribute types are added. Any `attr:<type>` and any Gramps ID in the tree are accepted, even if they are not in the list.

`attr:<type>` uses the attribute type name as stored by Gramps: the English name for a standard type (`attr:Identification Number`), the name itself for a custom type (`attr:Ahnentafel`).

## Built-in systems
| Direction | System id | Menu example |
|---|---|---|
| Ancestor | `sosa` (Sosa-Stradonitz, Kekulé) | 1, 2, 3, 4 |
| Ancestor | `ahnentafel` (same numbers as `sosa`) | 1, 2, 3, 4 |
| Descendant | `simple` (generation number) | 1, 2, 2, 3 |
| Descendant | `henry` | 1, 11, 1A |
| Descendant | `modified_henry` | 1, 11, 1(10) |
| Descendant | `daboville` | 1, 1.1, 1.2.3 |
| Descendant | `villiers_pama` | a1, a1b1, a1b2c3 |
| Descendant | `meurgey` | I, II-1, III-1 |
| Descendant | `record` (running number, generation order) | 1, 2, 3, 4 |

Menus show each system as its label plus its `example`, for example "Henry numbering (1, 11, 1A)" (`get_menu_label()`). The example is not translated.

Both directions also accept `attr:<type>`: the same relatives are numbered, but the shown value is that attribute, falling back to the Person label, then the Gramps ID.

## Run-time objects
**`Numbering`** (from `numbering_from_menu`, or built directly as `Numbering(db, focal_handle, system_id)`):

| Call | Returns |
|---|---|
| `handle in numbering` | whether the person is numbered |
| `numbers(handle)` | list of display numbers; pedigree collapse gives several, for example `["8", "14"]` |
| `primary(handle)` | first number, or `None` |
| `generation(handle)` | 1 for the Center Person, or `None` |
| `sort_key(handle)` | the system order (Sosa value, Henry path, and so on) |
| `handles()` | numbered handles in system order |

`max_generations` (default all) and `max_numbers` (default 10 per person) limit the work. Pedigree loops cannot hang the walk.

**`Label`** (from `person_label_from_menu` / `family_label_from_menu`): call it with a Person or Family to get its label (`""` for "Do not include"). `bool(label)` is false for "Do not include". `label.attribute` is the attribute type, or `""`.

**Center Person:** `numbering_from_menu` resolves it. For other uses, `menu.get_option_by_name(gn.OPT_FOCAL).get_center_person(db)`. "Active person" is only known while the dialog is open; otherwise the Home Person is used.

## Suggested identifier rule
This is the rule the Complete Individual Report (Sorted) uses for the text in brackets after each name:

```python
def person_identifier(self, person):
    handle = person.get_handle()
    for numbering in (self.anc_numbering, self.desc_numbering):
        if numbering is not None and handle in numbering:
            return ", ".join(numbering.numbers(handle))
    return self.person_label(person)
```

## Adding a numbering system
```python
class MyNumbering(gn.DescendantSystem):      # or gn.AncestorSystem
    system_id = "my_numbering"               # stable: saved in settings
    label = gn.N_("My numbering")           # translated when shown
    example = "1, 1-1, 1-2"                  # shown in menus, keep it short

    def format(self, rec):                   # rec is a NumberRecord
        return "-".join(str(i) for i in (1,) + rec.path)

    def sort_key(self, rec):
        return rec.path

gn.register_system(MyNumbering())
```

`NumberRecord` fields: `handle`, `generation` (1 is the Center Person), `number` (Sosa value, ancestors only), `path` (child positions below the Center Person, descendants only), `seq` (order found, generation by generation), `gen_seq` (order within its generation). Set `unique = True` if a person should get only one number. Register before the menu is built; the new system appears in the menus by itself.

## Remembered attributes
`use_attribute_memory()` keeps the attribute type last used in each choice in `<plugin id>.ini` next to the module, with a `[meta]` block (`plugin_id`, `schema_version`). A file from another plugin id or an older schema is replaced. Books and saved report settings are not affected; the `.ini` only chooses which type the "Attribute" item shows.

## Translation
Labels reuse core Gramps strings where possible. New strings: "Person label", "Family label", "Ancestor numbering system", "Descendant numbering system", "Ahnentafel numbering" and the help texts. The module uses `get_addon_translator(__file__)`; for report output in another language, translate with the report locale (see `self._addon_` in `IndivComplete_sort.py`).
