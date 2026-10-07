# Markdown Utils

Markdown Utils is a small shared library that some Gramps addons use so
their own documentation shows up nicely formatted *inside* Gramps,
instead of as a wall of `**bold**`/`#` symbols or a trip out to a wiki
page.

## What you'll actually notice

Nothing about Markdown Utils has its own window or menu — it has no
screen of its own to open. You'll see it listed once, quietly, in
**Tools → Plugin Manager** (or Plugin Manager plus, if installed) as
"Markdown Utils," but there's nothing to click there. What you *will*
notice is the addons that depend on it looking better:

- **An addon's own documentation travels with it, and is available
  immediately.** Addons that use Markdown Utils ship a `README.md`
  written in standard GitHub-Flavored Markdown right alongside their
  code. As soon as both the addon and Markdown Utils are installed,
  that documentation is ready to read, formatted, right where you're
  already looking — a color "Help" button on a gramplet/tool/report's
  own dialog, or an addon's entry in Plugin Manager plus's own info
  panel. No separate download, no visiting a website, nothing to turn
  on.
- **Headings, bold and italic text, bullet lists, links, and images all
  render properly** — the same Markdown you'd see rendered on GitHub
  or in a wiki, but inside a Gramps window.

## The extra layer: documentation that can show you Gramps itself

Beyond plain formatting, an addon's documentation written this way can
go a step further: it can embed pieces of the actual Gramps interface —
the same icon shown on a toolbar button, for instance — right in the
text, and can include links that don't just open a web page but *act*
on what's in front of you inside Gramps: jumping to a place in a tree
or view, or opening something for editing. Used this way, an addon's
README stops being just something you read and becomes closer to a
short guided tour, if the addon's author chose to write it that way.
Not every addon's documentation uses this — it's an option available
to addon authors, not something that changes how you read a plain
README.

## If an addon's documentation looks plain instead of formatted

That means Markdown Utils isn't installed (or isn't currently enabled).
The documentation still opens and is still fully readable — addons are
written to fall back to plain text rather than fail — it just won't
have the nicer formatting or the extra Gramps-aware touches described
above. Installing Markdown Utils from the addon list fixes this for
every addon that uses it, automatically, without configuring anything
addon-by-addon.
