# Gramps DoroTree Importer Addon

## Description
The DoroTree Importer is a custom Gramps extension designed to handle direct migration from the legacy DoroTree bilingual genealogy application. Rather than requiring users to convert files using intermediate software or external Windows-only database engines, this plugin reads native DoroTree backup files directly.

The plugin opens the native archive format, parses the underlying binary Borland Paradox database structure using memory streams, translates the legacy text layers, and cleanly populates your active Gramps database tree.

## System Features
- **Zero Configuration:** No native Windows database drivers (BDE, ODBC, OLEDB) or external command-line utilities are required.
- **Memory-Safe Extraction:** Archives are dissected safely in-memory to prevent local disk clutter or loose temporary files.
- **Full Bilingual Support:** Text elements are programmatically processed using the Windows-1255 Hebrew codepage, seamlessly retaining simultaneous Hebrew and English formatting across names, places, and descriptions.
- **Database Transaction Protection:** Imports run via standard Gramps transaction states to ensure that if a process failure occurs, modifications can be rolled back safely without corrupting your active family tree.

## Installation Instructions

1. Find your personal Gramps User Directory:
   - On Linux/Unix: `~/.gramps/plugins/`
   - On Windows: `%APPDATA%\gramps\plugins\`
   - On macOS: `~/Library/Application Support/gramps/plugins/`

2. Within the `plugins` directory, look for or create a subfolder named:
   `importer`

3. Safely copy your two plugin files into that directory:
   - `DoroTreeImporter.gpr.py` (The plugin configuration file)
   - `DoroTreeImporter.py` (The functional processing code)

4. Completely close and restart your Gramps application to allow the system to index the new plugin.

## How to Use the Importer

1. Launch Gramps and open the specific Family Tree into which you want to bring the new records. *(It is highly recommended to create a blank, fresh family tree before importing large archives).*
2. Go to the top navigation bar and select **Family Trees**, then click **Import**.
3. In the file choice dialog window, locate your DoroTree backup archive. *(These files usually feature a `.dte` extension, such as `DoroTreeDTDEMO.dte`).*
4. Select the file and click the **Import** button.
5. Watch the progress notification bar. Once processing finishes, your new individual profiles, names, genders, and structural relationships will be populated in your workspace.

## Supported Data Matrix

The current module architecture evaluates and aligns data objects across the following core application tables:

| DoroTree Paradox Source File | Target Gramps Object Component | Description |
| :--- | :--- | :--- |
| `People.db` | `Person` / `Name` | Handles main personal identities, alternate names, and genders. |
| `Families.db` | `Family` | Builds ancestral structural bonds linking mothers, fathers, and children. |
| `PDetail.db` / `FDetail.db` | `Event` / `Place` | Integrates demographic landmarks like births and marriages. |
| `Note.db` / `Note.mb` | `Note` | Preserves rich text commentary, character logs, and family footnotes. |

## Technical Architecture Details
This importer is engineered entirely in compliance with the Gramps Plugin System specifications. By building a pure Python binary unpacker using Python's `struct` utility, it extracts big-endian network integers and padded cell blocks directly from the legacy Paradox table records. This isolates the runtime environment, meaning the tool functions smoothly regardless of whether Gramps is deployed on a Linux desktop, a macOS machine, or a Windows environment.

## System Troubleshooting

- **Unrecognized File Extension:** If Gramps does not display your file, ensure that the `DoroTreeImporter.gpr.py` registration file is inside the correct plugins subdirectory and that your file ends with a lower-case or upper-case `.dte` extension.
- **Partially Encrypted Records:** If string fields display unreadable blocks, check that your local Python installation supports standard legacy codepages. The module falls back gracefully to standard UTF-8 string decoding if a character array fails to clear the Windows-1255 validation layer.
