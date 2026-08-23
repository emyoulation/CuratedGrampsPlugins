> From Claude 20260823 05:17 CT
> 
> Glad it's landing well — this has been a fun one to iterate on, and the design's ended up in a pretty good place: real delegation to upstream `make.py` for the parts that actually drift, your own bundled logic kept deliberately for the parts where you wanted manual control (versioning, translation cleanup), and now a proper settings story via `APS.ini` instead of leaning on Gramps' global config for something that's really per-tool state.
> 
> A few loose threads worth keeping in mind as you keep testing:
> 
> - The `git status`/`git diff` check from a few rounds back, if you haven't already confirmed it — worth double-checking once more now that the version-bump control exists, since that's the mechanism that actually produces a real content diff for GitHub Desktop to pick up.
> - The `gramps-preferences` and `folder-publicshare`/`color-select-symbolic` icon names are all assumptions about what's registered in your icon theme — if any of them render blank, that's a one-line fix, just let me know which.
> - The Markdown Dash / undocked README viewer is still just a documented `TODO` in `on_help_icon_clicked()` — (Claude continues: "happy to wire that up for real whenever that gramplet's API is something you can point me at.")

