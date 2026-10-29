# Date Modifiers Rule changelog
<!-- edit=False status=True browse=False undocked=True -->
[README.md](README.md) ● [CHANGELOG.md](CHANGELOG.md)

All notable changes to the Date Modifiers Rule addon are listed here, newest first.
## 0.0.0 - 2026-10-29
First draft for field testing, for Gramps 5.2, 6.0 and 6.1.
### Added
- One custom filter rule, "Dates by modifiers or invalid text", for Events, Citations and Media, in the General filters category.
- Valid dates section with check boxes for the Type modifiers (Regular, Before, After, About, Range, From, To, Span) and the Quality modifiers (Regular, Estimated, Calculated). Within a row, a date matches any checked choice; a row with nothing checked matches all valid dates.
- Invalid dates (Text only) section with an optional text search. The Use regular expressions and Case sensitive options of the Define filter dialog apply to this search.
- The two sections cannot be used at the same time: the section that is not chosen is grayed out.
- The rule settings are saved in the filter as text that does not depend on the language of Gramps.
