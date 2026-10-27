# Phonetic Grouped People — Changelog

[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

## 0.1.0 — Fork (beginning state)
Forked from the Gramps core **Grouped People** view (`personview`) on 2026-10-27, as the starting point for a Phonetic Grouped People view addon.

- Source view: [gramps/plugins/view/persontreeview.py](https://github.com/gramps-project/gramps/blob/maintenance/gramps61/gramps/plugins/view/persontreeview.py) on `maintenance/gramps61`, at commit `5cebb2c55fdbb0a92428625d409918216409db70`.
- Source registration: [view.gpr.py lines 196–213](https://github.com/gramps-project/gramps/blob/5cebb2c55fdbb0a92428625d409918216409db70/gramps/plugins/view/view.gpr.py#L196-L213) at the same commit.
- The view code in `maintenance/gramps60` is identical to the source; `maintenance/gramps52` differs only in the license header wording and one cosmetic tuple unpacking, so the fork targets Gramps 5.2 through 6.1.
- Changes from the source are renames only, so that the addon can be installed beside the core view: module `phoneticpersontreeview.py`, class `PhoneticPersonTreeView`, plugin id `phoneticpersonview`, view name "Phonetic Grouped People", title "Phonetic People Tree View".
- The registration drops `order=START`, so the addon does not replace Grouped People as the default view of the People category.
- Behavior is unchanged: people are still grouped by exact surname group (`PersonTreeModel` from `gramps/gui/views/treemodels/peoplemodel.py`). Column settings are stored separately from the core view because the view config name comes from the module name.
