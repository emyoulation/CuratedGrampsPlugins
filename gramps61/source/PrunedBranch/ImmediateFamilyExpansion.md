# Expanding a Pruned Branch with Immediate Family Rules
A note on a possible feature: using the Immediate Family Rules addon to grow the working subset of a Pruned Branch session one "ring" of relatives at a time. Nothing here is built yet.

## The idea
A pruned branch is defined by people. The first thing a user usually wants after pruning is "and their immediate families too." The Immediate Family Rules addon already computes exactly that set: parents, spouses, children and associations at 1 degree, siblings, parents-in-law and children-in-law at 2 degrees, and siblings-in-law at 3 degrees. Its Families rule finds the Family records around the same people.

An **Expand…** action in Pruned Branch could take the current subset as the anchor, run the same traversal, and add the results to the subset.

## Why it must be a Pruned Branch action, not a filter
Pruned Branch wraps only the listing calls. Single-record reads stay whole-tree. That splits the behavior of the rules in a session:

- **Walking to relatives** uses single-record reads (`get_person_from_handle`, `get_family_from_handle`), so it reaches people outside the branch. That is what an expansion needs.
- **A Person filter or Family filter anchor** gets its list of people from a listing call, so in a session it sees only the branch. That is also correct: "the tagged people in this branch."
- **Used as a sidebar filter**, a rule only tests the people the view lists, which are the branch members. Inside a session it can narrow the view but never add anyone. So expansion cannot be done with a filter. Pruned Branch has to call the traversal itself and add the results to the subset.

## Proposed split
**In Immediate Family Rules:** a small public API that returns handle sets, used by both rules internally so there is only one copy of the traversal logic (the same principle as MarkdownUtils):

```python
people_around(db, person_handles, keys, inclusive) -> set[PersonHandle]
families_around(db, person_handles, family_handles, keys, inclusive) -> set[FamilyHandle]
```

`keys` uses the same English keys that the rules save in filters (`parents`, `siblings_in_law`, `of_parents_in_law`, and so on), so the Expand dialog and saved filters speak the same language. Nothing changes for people who only use the filter rules.

**In Pruned Branch:** an **Expand…** action that:

1. Takes the current subset as the anchor people (and anchor families).
2. Shows the same degree rows as the rules, all checked by default.
3. Shows a preview before committing, for example "adds 312 people and 104 families."
4. Adds the results to the subset on OK.

Each use is one more ring, so a user can grow the branch step by step and see what each degree costs. Running the Families side after the People side pulls in the Family records that connect the new people, so the branch does not end up with people whose families are missing.

## Variant: expand before the session starts
A simpler first step than an in-session **Expand…** action: a checkbox in the Start Branch dialog (working name "Fat Selections") that post-processes the Tag or Filter selection, widening the perimeter by the immediate families of the selected people before the branch is built.

This variant avoids the session question entirely. Before Start Branch, nothing is wrapped yet, so the traversal and any filter anchor see the whole tree, and the result simply becomes the starting subset. It needs only `people_around()` and `families_around()`, with no changes to how a running session manages its subset.

Possible shape:

- One checkbox, off by default, with all degree rows included when checked. A small "…" button beside it could open the degree rows for users who want to leave some out.
- The count next to the Start Branch button updates to show the fattened size, for example "1,258 people, 4,970 with immediate families," so the user sees the cost before starting.
- The in-session **Expand…** action can come later and reuse the same API and the same degree rows.

## Soft dependency
Neither addon should require the other. Pruned Branch looks up Immediate Family Rules through the plugin manager and offers **Expand…** only when it is installed:

```python
from gramps.gen.plug import BasePluginManager

pmgr = BasePluginManager.get_instance()
pdata = pmgr.get_plugin("ImmediateFamilyRules_ImmediateFamilyPeople")
module = pmgr.load_plugin(pdata) if pdata else None
if module is not None and hasattr(module, "people_around"):
    ...  # enable Expand…
```

The `hasattr` check keeps Pruned Branch working with an older Immediate Family Rules that does not have the API yet.

## Open questions
- Should the Fat Selections checkbox remember its last setting between sessions?
- Does the Pruned Branch prototype keep its subset as a stored set of handles, or does it rebuild the subset by re-running a filter? A stored set makes expansion a simple union. A filter-defined subset would need the expansion saved as extra handles on top of the filter, or folded into a new filter definition.
- Should an expansion be undoable on its own (for example a "Shrink to previous ring" step), or is starting a new session good enough?
- Should Expand… also offer the Families rule rows separately, or always add the connecting families automatically?
- With a large subset (thousands of anchor people), the preview count may take a while. Is a progress indicator needed, or is the preview fast enough to compute on every checkbox change?
