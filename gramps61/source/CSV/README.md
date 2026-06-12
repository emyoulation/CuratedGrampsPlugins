# CSV Import and Export v1.1.0
<!-- undocked=false edit=True status=True browse=True -->
_Experimental_ version for Gramps 6.0 testing 
Use only on Backup Tree data.

DSBlank spent some time refining the CSV import/export in [PR2372](https://github.com/gramps-project/gramps/pull/2372). It has been expanded to handle: Place, Person, Marriage, Family, **Event**, **Citation**, and allows full (and custom) type entries.

## The two new row types are:

**Event table columns**: 
  `event`, `eventtype`, `date`, `place`, `description`, `source`, `note`, `note_type`, `role`, `tag`, `person`, `family`, `media`, `media_description`, `media_date`
**Citation table columns**: 
  `citation`, `source`, `page`, `date`, `confidence`, `note`, `note_type`, `tag`, `person`, `family`, `event`, `place`, `media`, `media_description`, `media_date`

The Gramps primary object types that are not handled after the update:
* Source — citations reference sources by title string, but sources themselves aren't exported/imported as a table
* Repository — no table at all
* Media — no table at all
* Note — only inline note text on persons/families, not standalone Note objects
* Tag — exporter writes tag names on some objects, but there's no Tag table for standalone tag management

The importer stores the media path as-is without checking if the file exists — no error is raised. `mimetypes.guess_type()` infers the MIME type from the extension alone (no file access). The Media object is committed to the database with whatever path was given, and Gramps will show it as missing when it tries to display it later. This is consistent with how all other Gramps importers behave: path validation is deferred to display time, not import time.

Does this upgrade handle most of the issues with CSV import?

As this is a new feature, it is slated to appear in the Gramps 6.2 released around Oct. 2026.

## References:
* [Gramps 6.0 CSV Import](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#Gramps_CSV_import)
* [Gramps 6.0 CSV Export](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#csv_export)

