# Gramps Glossary
*This glossary gives an overview of terms that appear in the [Gramps](https://gramps-project.org/) genealogy software, with a short description, and a link to relevant articles.*
*(Since knowing a feature's name is necessary for finding the corresponding glossary term, also refer to the* [Visual Guide to the Gramps Interface](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Main_Window).)

For a glossary of genealogical terms, see [Genealogy Glossary](https://www.gramps-project.org/wiki/index.php/Genealogy_Glossary) and [Latin words and expressions](https://www.gramps-project.org/wiki/index.php/Latin_words_and_expressions).

[A](#a) · [B](#b) · [C](#c) · [D](#d) · [E](#e) · [F](#f) · [G](#g) · [H](#h) · [I](#i) · [J](#j) · [K](#k) · [L](#l) · [M](#m) · [N](#n) · [O](#o) · [P](#p) · [Q](#q) · [R](#r) · [S](#s) · [T](#t) · [U](#u) · [V](#v) · [W](#w) · [X](#x) · [Y](#y) · [Z](#z)

## A 
#### Active Person
(*core concept*) - The person designated (or 'selected') as the momentary center of focus in the open Gramps database. The perspective of this person defines the context for actions and for displaying all the surrounding information. Changing this focus is done by [navigating the Active Person](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Navigation#Setting_the_Active_Person) selection to another person.
The Active Person's relationship to the [Home Person](#home-person) defines the scope of the perspective.
*nota bene*: There is ***always*** an Active Person selection, even when the [primary object](#primary-object) (*aka* record) selected in the current view is not a 'Person' [object](#object).

#### addon ![](gramps:icon:gramps-addon:48)
(*aka* [add-on](https://wikipedia.org/wiki/Plug-in_(computing)))
An optional [**third-party** expansion](https://www.gramps-project.org/wiki/index.php/6.0_Addons#Addon_List) to Gramps that leverages Gramps [plugin](#plugin) customization framework to add and [register](https://www.gramps-project.org/wiki/index.php/Addons_development#Create_a_Gramps_Plugin_Registration_file) a specific feature. The [Addon Manager](#addon-manager) allows installing and updating from curated collections of Addons. (These curated collections are called "Projects" in the [Addon Manager](#addon-manager).)
Addons may not conform to the same design or code quality standards of built-in plug-in modules bundled with **Gramps**. Use with caution!
Optional parts bundled with the core project are called by the more generic name: builtin plugins. After installation and being registered, both the "builtin" and "addon" plugins may be disabled or re-enabled with the [Plugin Manager](#plugin-manager).

#### address
(*[sec. obj.](#secondary-object)*) - The Gramps concept of an Address is a particular location with an associated time frame. Think of it as a mailing address. It is intended to represent where a person lived and when the person lived there. The Address consists of:
  - Date
  - Street Address, Locality
  - City, County
  - State/Province, Postal/Zip code, Country
  - Phone
Not to be confused with a [Place](#place) which has a fixed position (its location). [Use this with care.](https://www.gramps-project.org/wiki/index.php/Why_residence_event_and_not_Address%3F) For genealogical research you can also use the residence event coupled with a [Place](#place). For mailing (email, postal), add an address to a [Person](#person) or [Repository](#repository).

#### administrative division
a unit of a layered system subdividing a geopolitical (geographic or political) region. Such divisions are recorded as [Place](#place) Types in Gramps. Meanwhile the structure of a Place Tree is built by layering via the ['Enclosed by' tab in the Place Editor.](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Enclosed_By) The subdivisions are sometimes categorized as an entity, locality, area, or region. The terms of subnational entity, constituent unit, or country subdivision tend to imply divisions that are more related to political representation than administrative.   
See wikipedia's [Administrative division](https://wikipedia.org/wiki/Administrative_division) for a conceptional definition or [List of administrative divisions by country](https://wikipedia.org/wiki/List_of_administrative_divisions_by_country) for specific countries.

#### Aide
(*[event role](#event-role)*) A term to refer to the role of an assistant.

#### Anglicization
process of making something English. If an immigrant (or their descendant) adopts a naturalized variation of their birth name, that [preferred alias](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Preferred_name_section) can be added with an *Also Known As* [name type](https://www.gramps-project.org/wiki/index.php/Names_in_Gramps#Name_Types) in the [Names](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Names) tab. All aliases can be categorized by type and surname variants may be [grouped](https://www.gramps-project.org/wiki/index.php/Grouping_Surnames) with the [Name Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_3#Name_Editor).

#### Association
(*[sec. obj.](#secondary-object)*) - The [roles](#role) in [Associations](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Associations) are to explicitly define the how one person relates to another.
Association roles are used when the relationship falls outside the implicit roles of a family relationship or the explicit roles in shared events. These custom roles convey relationships that might not readily apparent... such as a [penpal](https://wikipedia.org/wiki/Pen_pal) or the [eponymous person](https://wikipedia.org/wiki/Eponym) honored by a namesake. Association roles may also be used as placeholder when the actual genetic connection has not yet been discovered.
Association roles are created and edited with the [Person Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Person_Reference_Editor), which includes no pre-defined roles. This feature starts with a blank list of [custom types](#custom-types)) and the default "Godfather" role is only shown as a hint.

#### attribute
(*[sec. obj.](#secondary-object)*) - [Attributes](https://www.gramps-project.org/wiki/index.php/Attributes_in_Gramps) are for something permanent, or at least somewhat permanent: eye color, blood type, etc. Usually you would have not more than one of each attribute type for a [Person](#person)/[Family](#family)/etc. Attributes are managed from an Attributes tab in each [primary Object](#primary-object) Editor. There are a few pre-defined Attributes to support GEDCOM, but [custom types](#custom-types) will tend to be needed.

## B
#### Books Report
A [Reports menu](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports) feature of Gramps that allows the [design or generation of a repeatable custom genealogy *Book*](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports_-_part_3). A Book consists of an ordered collation of Gramps textual and graphical reports in a single document. The individual report configuration options are also stored with the Book but the Book's document pagesize and print destination configuration options override.

#### Bride
(*[event role](#event-role)*) A term to refer to the woman a marriage ceremony who will have the role of *wife* in the marriage. See also: *mother*.

#### BSDDB
(*[database backend](https://www.gramps-project.org/wiki/index.php/Database_Backends) engine*) The [Berkeley Software Distribution database](http://www.oracle.com/us/products/database/berkeley-db/overview/index.html) (also known as BSDDB) was the first *default database engine* used by the [2.0](https://www.gramps-project.org/wiki/index.php/Database_Formats#Gramps_2.0) through the [5.0](https://www.gramps-project.org/wiki/index.php/Database_Formats#Gramps_5.0) versions of Gramps. Originally, Gramps [XML](#xml) was used directly rather than as a Backup and data exchange format. The default db engine changed to [SQLite](#sqlite) in the 5.1 version via the [DB-API Database Backend](https://www.gramps-project.org/wiki/index.php/DB-API_Database_Backend). ([Manual updates to the BSDDB engine](https://www.gramps-project.org/wiki/index.php/Install_latest_BSDDB) for the 5.1.3 version may be advisable.)

## C
#### Category
(*core concept*)  Gramps divides and organizes the information about each [Primary Object](#primary-object) into a series of different descriptive schemas called Categories, each with their own [View](#view). Each Category is a smaller, more digestible portion of the total information that comprises a Genealogical Tree. The View categories are: ![Dashboard](gramps:icon:dashboard:16) [Dashboard](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Dashboard_Category), [People](gramps:icon:person:16) [People](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#People_Category), ![Relationships](gramps:icon:relation:16) [Relationships](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Relationships_Category), ![Family](gramps:icon:family:16) [Families](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Families_Category), ![Charts](gramps:icon:pedigree:16) [Charts](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Charts_Category), ![Events](gramps:icon:event:16) [Events](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Events_Category), ![Places](gramps:icon:place:16) [Places](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Places_Category), ![Geography](gramps:icon:geo:16) [Geography](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Geography_Category), ![Sources (v3.4.x)](gramps:icon:source:16) [Sources](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Sources_Category), ![](gramps:icon:citation:16) [Citations](citation), ![](gramps:icon:repository:16) [Repositories](#repostitory), ![Media](gramps:icon:media:16) [Media](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Media_Category), ![Notes](gramps:icon:note:16) [Notes](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Notes_Category)

#### Celebrant
(*[event role](#event-role)*)  A term describing a role of the person who performs a rite, especially referring to a priest at the Eucharist.

#### Citation ![](gramps:icon:citation:48) 
(![Citations](gramps:icon:citation:16) *[prim. obj.](#primary-object)*) - Contains the information  that enables you or others to locate your source document. An isolated [Citation can be created](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_source_citations) without first creating separate [Source](#source) object. But, should the same source be referenced repeatedly in a Tree, a separate Source simplifies the Citation and eliminates redundant information that must be harmonized.

#### Clergy
(*[event role](#event-role)*)  A term applied to a religious person regardless of religion. For example, a monk or priest. See also: *[celebrant](#celebrant)*.  
 <small>Religious terminology is often subject to dispute, see the [Merriam-Webster](https://www.merriam-webster.com/dictionary/clergy) for an independent definition.</small>

#### Clipboard ![](gramps:icon:edit-paste-symbolic:48)
(![Gramps Clipboard48x48 win.png](gramps:icon:edit-paste:16) [graphical user interface terminology](#gui)) - The [Gramps Clipboard](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Navigation#Using_the_Clipboard) is a shortcut system for [sharing](#sharing) a [secondary](#secondary-object) object, navigation, and custom [filter](#filter) creation.   
**Usage:** The Clipboard can be opened from a icon on the [Toolbar](#toolbar), from the **Edit▽Clipboard** menu choice or by using the Copy [keybinding](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Keybindings#7) for the Active Record in the Active main view of a View category. A floating clipboard dialog that has become buried can be brought to the top of the stack by selecting **Clipboard...** from the Windows menu.  
The Clipboard can greatly improve data entry efficiency, see the "[How to use the Gramps Clipboard](https://www.gramps-project.org/wiki/index.php/How_to_use_the_Gramps_Clipboard)" article for more information.

#### Context Menu
*([graphical user interface terminology](#gui))* - a [contextual pop-up menu](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Pop-up_menus) (*aka* ["context menu"](https://wikipedia.org/wiki/Context_menu)) is a menu that appears when right-clicking (or pressing the [Menu keyboard key](https://wikipedia.org/wiki/Menu_key)) when the menu options directly relate to the item indicated by the mouse pointer. Thus, the indicated item provided the "context."

#### Custom Types
This indicates a user-defined classification, as opposed to classifications that came pre-defined in Gramps. (i.e.: 'Birth' and 'Marriage' are 2 of the pre-defined 'types' of Events.)
When none of the pre-defined Types are suitable, add a new *[custom](#custom-types)* Type by typewriting directly into the [selector combo box](#selector-combo-box). If the value doesn't precisely match any of the existing menu items, a new *custom* Type will be created when the `OK` button is clicked.   
Any added *custom* Type will remain available in that expanded menu... unless the Tree is exported and re-imported or removed via a [Third party addon](https://www.gramps-project.org/wiki/index.php/Third-party_Addons) Utility like [Type Cleanup](https://www.gramps-project.org/wiki/index.php/Addon:Types_Cleanup_Tool).  
 
***custom* Types** can be defined for: Event [Attributes](#attribute), Family [Attributes](#attribute), media [Attributes](#attribute), Person [Attributes](#attribute), [Event Roles](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#General), [Event types](https://www.gramps-project.org/wiki/index.php/Custom_Event_Types), Family [Relationship Information](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Relationship_Information) types, [Child Reference](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Child_Reference_Editor) Types, [Name Origin Types](https://www.gramps-project.org/wiki/index.php/Names_in_Gramps#Origin_Attributes), [Names Types](https://www.gramps-project.org/wiki/index.php/Names_in_Gramps#Name_Types), [Note Types](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Note_editor_dialog), [Place Types](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Place_Editor_dialog), [Repository](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Repository_Reference_Editor) Types, Source [Attributes](#attribute), [Repository](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Repository_Reference_Editor) Media Types, [Internet Address (URL)](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Internet_Address_Editor) Types.

## D
#### Date
(*[sec. obj.](#secondary-object)*) - Dates in Gramps are much more complex than just a month, day, and year. Dates are always in a [particular calendar](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Calendars), can span a time frame with the [Date Type](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Date_Type), the [Date Quality](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Date_Quality) can be exact (or an approximation variant), and have support for many other subtleties specific to genealogy data. The approximation can be fine-tuned with the [Limits](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Limits) preferences.  
The [date parsing rules](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Date_formats_and_parsing_rules) are applied whenever data is entered into a [date text field](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Editing_dates) or a [date selection dialog](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Date_selection_dialog).

#### DNA
1. acronym: **d**eoxyribo**n**ucleic **a**cid
2. a [nucleic acid](https://wikipedia.org/wiki/Nucleic_acid) that carries genetic information. Genetic testing compares for matching sequence lengths (measured in centimorgans, aka cMs) at various loci on specific chromosomes to determine common ancestry.

#### Dock
*([graphical user interface terminology](#gui))* - a [dock](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Pop-up_menus) is one of the multitude of containers offering controlled access and context to Gramplets. Gramplets can be added to, removed from, or undocked from a container to float free of the main window.  
The Dashboard was the original container and can be configured with multiple columns and stacks of Gramplets. The [sidebar and bottombar splitbars](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Bottombar_and_Sidebar) are Category-specific containers. The splitbars only show a single gramplet at a time but with tabs to quickly switch between them. Each view mode has its own set of splitbars. So the basic configuration of Gramps has the Dashboard plus 24 Category view modes... or 49 separate gramplet containers.

#### DTD
acronym: **D**ocument **T**ype **D**efinition. A document that defines the tagging structure which identifies the individual components of an [SGML](https://wikipedia.org/wiki/Standard_Generalized_Markup_Language) or [XML](#xml) document.  
See the [reference documentation for the versions](https://www.gramps-project.org/xml/) of Gramps [RELAX NG](https://www.gramps-project.org/wiki/index.php/Gramps_XML#RELAX_NG_generation) (**RE**gular **LA**nguage for **X**ML **N**ext **G**eneration)(`.rng`) schema [XML](#xml) and DTD

## E
#### Event ![](gramps:icon:event:48) 
(![Events](gramps:icon:event:16) *[prim. obj.](#primary-object)*) - Contains the information related to an happening. [Adding an Event record](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_events) provides the context of an interaction of the roles of People/Families, dates & places in activities.  
An Event is a defining moment in a person's life. See [events](https://www.gramps-project.org/wiki/index.php/Events_in_Gramps) for the use in genealogy, for predefined events in Gramps and suggested naming for [common events](https://www.gramps-project.org/wiki/index.php/Events_in_Gramps).

#### Event role
The [role](#role) a [Person](#person) plays in an [Event](#Event). The focal Person(s) holds a [***Primary role***](#primary) in personal Events and the Family holds a [***Family role***](#family-role) in Family events. In Gramps, an Event can be linked to as many participants as desired. Each [Person](#person) may participate in different roles but more than one Person might play the same role. The Event Role captures this and can be changed in the [Event Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Event_Reference_Editor_dialog). Some common Roles are pre-defined but the user can add other [custom](#custom) Roles by just typing in the appropriate new label into the [selector combo box](#selector-combo-box).
<small>Pre-defined Types of Event Role: [Aide](#aide), [Bride](#bride), [Celebrant](#celebrant), [Clergy](#clergy), [***Family***](#family-role), [Godparent](#godparent), [Groom](#groom), [Informant](#informant), [***Primary***](#primary), [Witness](#witness), [***Unknown***](#unknown), *[custom](#custom)*</small>

#### Event type
The general denominator to which an event belongs, e.g., a christian, civil, tibetan, ... marriage, are all denoted by the event type *marriage*. See [events in Gramps](https://www.gramps-project.org/wiki/index.php/Events_in_Gramps) for an overview.

## F
#### Fallback events
Certain [event](#event) types are definitive bookends marking the beginning or end of a life (Birth/Death) or relationship (Marriage/Divorce). Those bookend events are key factors in any kind of timeline analysis.
If the definitive event types are missing, Gramps will look for similar event types to calculate a 'fallback' approximation. When dates are shown in italics, it indicates that the preferred bookend event was not found and one of the [pre-defined Fallback events](https://www.gramps-project.org/wiki/index.php/Events_in_Gramps#Fallback_Events) had to be used. Markers for some fallback events can be customized using the **Genealogical Symbols** tab of [Preferences](#preferences).

#### Family ![](gramps:icon:family:48) 
1. (![Family](gramps:icon:family:16) *[prim. obj.](#primary-object)*) - Contains the information specific to relationships between people.  The information may be edited directly using the [Edit Family](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Editing_information_about_relationships) dialog.  
This traditionally contains one or two parents and zero or more children. A family unit is created in Gramps by [adding Parents to an individual](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_brief#Specifying_a_relationship_using_the_Relationship_View), by [adding a partner/spouse](https://www.gramps-project.org/wiki/index.php/Add_a_spouse) to an individual, or by adding a family first then adding the people. (A family can even consist of just the offspring.)  
The Family  relationship is a core concept in Gramps. It depicts the basic relations between people. Commonly this will contain a father, a mother and some children, however, it can also contain only parts of this (e.g., two brothers, a mother and child). People can be part of several families (adoption, remarried, ...)
2. ([event role](#event-role)) An event can be coupled to a family, denoting that the both partners were equally involved in the event. Typically, the Marriage event will be coupled to a family with event role *family*. **Family** is the *default* role when adding a new Event in the [Edit Family](#edit-family) dialog.

#### File Chooser
Picking external files or folders for import, export, reports and media is done using a File Chooser dialog from [GTK](https://wikipedia.org/wiki/GTK) (formerly known as "GIMP ToolKit" and "GTK+") rather than those of the native Operating System. While generally familiar, the **[GTK File Chooser](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#File_Chooser)** has customizable features, [context menus](#context-menu), options and keybindings that are documented in the [Settings](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings) section of the manual.

#### File formats
File formats repackage the Tree database information for archiving, data exchange with other software or display.
  **[Import](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#Importing_data) formats:** GRAMPS v2.x database (obsolete) `.grdb`, Comma Separated Values `.csv`, GEDCOM (Genealogical Data Communication) `.ged`, GeneWeb `.gw`, Pro-Gen `.def`, vCard (virtual contact card) `.vcf`, JSON (JavaScript Object Notation) `.json`, SQLite `.sql`
  **[Export](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#Exporting_data) formats:** Gramps native XML format (compressed & uncompressed variants) `.gramps`, Gramps Package (Gramps XML plus media) `.gpkg`, GEDCOM (Genealogical Data Communication) `.ged`, GeneWeb `.gw`, Web Family Tree (a GEDCOM variant) `.ged`, vCalendar `.ics`, vCard (virtual contact card) `.vcf`
  [**Output formats**](https://www.gramps-project.org/wiki/index.php/Output_formats) including: Comma Separated Values `.csv`, Data-Driven Documents (D3) ``.d3``, Graphviz graph description language `.dot`, Hypertext Markup Language `.html .htm`, LaTeX `.tex`, Open Document Text `.odt`, Portable Document Format `.pdf`, Plain Text `.txt`, PostScript `.ps`, Print (hardcopy), Rich Text Format `.rtf`, Scalable Vector Graphics `.svg`, vCard (virtual contact card) `.vcf`, Extensible Markup Language `.xml`

#### Filter
A [filter](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters) (*aka* query) in a database finds (or hides by 'filtering out') records, displaying only those records that match certain criteria. (The criteria are comparison or query [rules](#rule) describing some attribute of a record.) Layers of criteria can be applied but each layer requires additional processing and slows performance of the interface.   
The [basic Search](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Filter_vs._Search) is a single criteria filter. The search value is compares only one attribute of a record that has been selected from a pop-up menu.   
The **[Filter Gramplets](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#Filter)** will compare several predefined common attributes simultaneously with simplified access to changing the search value. The default is for exact matching but [Regular Expressions (RegEx)](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Regular_Expressions) can be used for pattern matching. A Custom Filter may be also layered in.   
A [Custom Filter](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Custom_Filters) adds richly complex [Rules](#rule)-based comparison with [layers of intersection](https://www.gramps-project.org/wiki/index.php/Example_filters) options for those rules. Custom Filters allow repeatable filters to be created with pre-defined rules and values to be matched.  Beyond interactively  hiding (or revealing) records in views, Custom Filters are used to set limits for exporting, setting scopes for reports, and targeting tool actions.  
In addition to the [builtin rules](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Which_filter_rules_in_which_Category.3F) for filtering,  [Addon:Rule expansions](https://www.gramps-project.org/wiki/index.php/Addon:Rule_expansions) are available for Custom Filters.

## G
#### GEDCOM
1. acronym: **Ge**nealogy **D**ata **Com**munication
2. a format for [importing](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#GEDCOM_import) and [exporting](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Manage_Family_Trees#Exporting_data) genealogical data. The open specification for the [GEDCOM format](https://www.familysearch.org/developers/docs/guides/gedcom) was developed by The Church of Jesus Christ of Latter-day Saints (LDS Church) as an aid to genealogical research. The long standing standard release was version 5.5 in 1996 with a 5.5.1 draft update presented for comment in 1999. (Belatedly, the 'draft' label was officially removed in the annotated 2019 release. After 20 years as the de facto standard format, it remained unimproved excepting for 2 tags and the copyright.)

  As an Open Standard, there are extensive and constantly changing incompatibilities between implementations and data loss when transferring GEDCOM formatted data between competing software tools is common. Gramps has implemented a variety of [GEDCOM support features](https://www.gramps-project.org/wiki/index.php/GEDCOM).
  GEDCOM [X proposed in 2012](https://www.familysearch.org/developers/docs/guides/gedcom-x) and [5.5.5 proposed in 2019](https://blog.eogn.com/2019/10/04/the-proposed-gedcom-5-5-5-standard-is-a-better-gedcom/) are improvements that have not gained the approval of the copyright holder. As of June 2021, these proposals have been superseded by the GEDCOM 7.0.1 version.

#### Godparent
(*[event role](#event-role)*) A term to refer to the person who presents a child at a christening or baptism and promises to take responsibility for guiding the child emotionally, practically, and spiritually. This person will be referred to as *godfather* or *godmother* after the christening or baptism. See also: *[Add a godfather-godmother](https://www.gramps-project.org/wiki/index.php/Add_a_godfather-godmother)*.

#### Gramplet ![](gramps:icon:gramps-gramplet:48)
a [Gramplet](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#definition) is a plug-in (*aka* [widget](https://wikipedia.org/wiki/Software_widget) or [applet](https://wikipedia.org/wiki/Applet)) that can be [docked](#dock) in the ![Dashboard](gramps:icon:dashboard:16) [Dashboard](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Dashboard_Category) category view. Later [sidebar or bottombar](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Bottombar_and_Sidebar) were added to the remaining [views](#view) to extend [adding](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Gramplet_Bar_Menu) and [undocking](#undock) a Gramplet functionality of those view.   
Gramplets dynamically update as the different records are selected in the main display area of a view. Gramplets typically create an alternate interface to your Family Tree data. Collections of [builtin](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#Summary_of_Gramplets) and ["3rd party addon"](https://www.gramps-project.org/wiki/index.php/6.0_Addons#Addon_List) gramplets are available for [installation](https://www.gramps-project.org/wiki/index.php/6.0_Addons#Installing_Addons_in_Gramps) and download with the [Plug-in Manager](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Plugin_Manager).  The Plug-in Manager also regulates a [wide variety of other builtin and addons](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#Aren.27t_all_Plugins_also_Gramplets.3F) which can expand functionality unrelated to the interface.
*See the [Gramplets development](https://www.gramps-project.org/wiki/index.php/Gramplets_development) for independent information.*

#### Gramps *for Desktops*
[Gramps](https://gramps-project.org/blog/features/) is an open-source genealogy application, a free software project and community.   
**Gramps** is an affectionate nickname for a "Grandfather". Originally, the all capital letter [backronym](https://wikipedia.org/wiki/Backronym) stood for "**G**enealogical **R**esearch and **A**nalysis **M**anagement **P**rogramming **S**ystem" and was coined by Larry Allingham. ([GRAMPS was created around 2001](https://gramps-project.org/blog/2006/04/looking-back-over-5-years/) by [Don Allingham](https://www.gramps-project.org/wiki/index.php/User:Don) for use by his father, Larry.) This backronym was phased out around March 2010 in favor of **Gramps** as the official name of the software. All upper-case acronym-based names have become unfashionable for software.

#### Gramps Web *for Servers*
[Gramps Web](https://gramps-project.org/blog/web/) is collaborative interface (frontend) and backend created by David M. Straub for running the Gramps genealogy database engine on servers. It is one of the [Web Solutions for Gramps](https://www.gramps-project.org/wiki/index.php/Web_Solutions_for_Gramps).  
It is a multi-user system genealogical web application with different levels of options for Visitors, Members, Contributors, Editors, and Owners. Trees in [[Gramps Web on a server](https://www.grampsweb.org)] can be synchronized with the more mature and feature laden [Gramps for Desktops](#gramps). Single Tree or multiple Tree sites can be self-managed on a hosted service from an ISP, leased from a managed hosting ISP, or leased from an application-specific fully managed CMS provider, or installed locally for access from a local area network.

#### Graphical User Interface
A visual way of indicating interactive features of a computer operating system or application/program.
The **Gramps *for Desktops*** GUI is introduced in [Visual Guide to Gramps Interface](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window). It uses a "windows, icons, menus, pointer" ([WIMP](https://wikipedia.org/wiki/WIMP_(computing))) based approach with [post-WIMP](https://wikipedia.org/wiki/Post-WIMP) elements like hyperlinked redirection and custom interface objects. The desktop interface is built with [Gtk](https://wikipedia.org/wiki/GTK) (the Gimp Toolkit), a free and open-source cross-platform widget toolkit for creating graphical user interfaces.
The appearance and interaction may vary by conventions dictated by the [Operating System (OS)](https://www.gramps-project.org/wiki/index.php/Download), installation option (such as [language localization support](https://www.gramps-project.org/wiki/index.php/Portal:Translators) or [addon/plug-in](https://www.gramps-project.org/wiki/index.php/6.0_Addons)), [theme](https://wikipedia.org/wiki/Theme_(computing)) (at the OS or [internal](https://www.gramps-project.org/wiki/index.php/Addon:ThemePreferences) levels), and/or [user preferences customization](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Preferences).
The specific interface elements are identified by customary name, general appearance & behavior in the [Visual Guide to Gramps Interface](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window). Expansion interface elements are described in the user documentation for [each specific addon](https://www.gramps-project.org/wiki/index.php/6.0_Addons).
The **Gramps Web** GUI (or frontend) is a platform-agnostic web browser interface built with the [Lit](https://lit.dev/) lightweight JavaScript library for building fast, interoperable web components. Although the hosting side requires a webmaster with significant skills, genealogical collaborators can use web browser on almost any device.

#### Groom
(*[event role](#event-role)*) A term to refer to the man at a marriage who will be referred to as *husband* after the marriage. See also: *[Add a spouse](https://www.gramps-project.org/wiki/index.php/Add_a_spouse)*.

#### GUI
An acronym. *see [Graphical User Interface](#graphical-user-interface)*.

## H
#### Home Person ![Gramps Go-Home48x48 win.png](gramps:icon:go-home:48)
(*core concept*) - The persistently designated **Home Person** is the foundational [Person](#person) (the [Proband](https://www.gramps-project.org/wiki/index.php/Genealogy_Glossary#proband), [Progenitor](https://www.gramps-project.org/wiki/index.php/Genealogy_Glossary#progenitor), or [Progenitrix](https://www.gramps-project.org/wiki/index.php/Genealogy_Glossary#progenitrix)) in the Tree (the currently open Gramps database). This Person is the central target of genealogical research and family references extend from this center. Ideally, every person, event and source in the Tree will (however directly or indirectly) relate back to the **Home Person**.  
By default, the database reports describe everything else in contextual relation to this person. The [Status Bar](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Status_Bar_and_Progress_Bar), the [Quick View](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#Quick_View) called "[Relation to Home Person](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports_-_part_8#Relation_to_Home_Person)", and the Third party addon [Gramplet](#gramplet) called "[Deep Connections](https://www.gramps-project.org/wiki/index.php/Addon:Deep_Connections_Gramplet)" all describe different aspects of the relationship of the [Active Person](#active-person) to the **Home Person**.  
You (or your client) are customarily designated ([set](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Setting_Home_person)) as the Home Person. And this *Home* designation serves as a persistent point of reference for the rest of the Tree in Reports generally and for the Active Person in detail. But a different **Home Person** might be temporarily [set](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Setting_Home_person) when generating reports or when researching a complex biography or obituary.   
Fascinating tidbits often lure Gramps researchers into wandering off-course. When the [Active Person](#active-person) has become lost, the bearings can be instantly regained by navigating the [Active Person](#active-person) selection back to the **Home Person**.  
Navigate to **Home Person** - *keyboard shortcut* `Alt`+`Home` or press the toolbar ![Gramps Go-Home48x48 win.png](gramps:icon:go-home:16) `Home` button.   
The custom filter rule for finding the **Home Person** is in a People category filter under the General filters and was named 'Default person' until the 5.1 version.

## I
#### Informant
(*[event role](#event-role)*) A term to refer to the [Role](#role) of Person who reports an [Event](#event).

## J
#### JSON
acronym: [**J**ava**S**cript **O**bject **N**otation](https://wikipedia.org/wiki/JSON). JSON is a lightweight, text-based data format designed to be easy for humans to read while still structured enough for machines to parse efficiently. It organizes data in key-value pairs, allowing information to be grouped together in a clear and straightforward way.

## K
#### Keybinding
Keyboard shortcuts (*aka* hotkeys) key (or combination of keys) that can be used to navigate a Graphical User Interface (*aka* [GUI](#gui)) as an alternative to using the mouse. A single keystroke (or combination of keys on a keyboard) executes a command.
*see [Gramps GUI keybindings](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Keybindings#toc)*

## L
## M
#### matronym
(*[origin](#name-origin) Name attrib.*) - personal name based on the name of one's mother

#### Media ![Gramps-media.png](gramps:icon:media:48) 
(![Media](gramps:icon:media:16) *[prim. obj.](#primary-object)*) - Contains the information related to a media object. Media objects include images, videos, audio recordings, documents, webpages or any other type of related files.  
When new Media objects are edited from the Gallery tabs of Object Editors or from the Media category view, the [New Media editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_media_objects) allows the metadata to be modified.

#### Merge ![Gramps Merge48x48 win.png](gramps:icon:merge:48) 

To combine the objects in two selected rows in a [category view](#view-category) into a single object. This reduces duplicates while consolidating references and [secondary objects](#secondary-object). The [merge process](https://www.gramps-project.org/wiki/index.php/Merging_people) involves selecting two rows (a target row to be kept and a row to be deleted) then choosing **Merge** from the Toolbar or Edit menu. Choices are offered about which secondary objects take precedence when there are conflicts, but no data (except one of the descriptions in an Event merge) is lost by default. All secondary objects from both selected rows are conveyed to the surviving merged row. Only two objects may be merged at a time unless using addon tools designed for multiple object merges or batches of merges.

#### Mode
*see [View mode](#viewmode)*

## N
#### Name Origin
An optional attribute (characteristic) identifying how a name was derived for a [Person](#person). Pre-defined items of the [origin selection menu](https://www.gramps-project.org/wiki/index.php/Names_in_Gramps#Origin_Attributes) include: inherited, patrilineal, matrilineal, given, taken, [patronymic](#patronymic), [matronymic](#matronymic), feudal, pseudonym, occupation. The Name Origin of [Multiple surnames](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Multiple_Surnames) and [Alternative names](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Names) can be added from the [Edit Person](#edit-person) dialog.  
*Available as a standard attribute of [Names in Gramps](https://www.gramps-project.org/wiki/index.php/Names_in_Gramps).*

#### Navigator
*([graphical user interface terminology](#gui))* - the [Navigator](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Navigator) is a Gramps-specific name for a left sidebar layout of [category](#category) view icons, allowing movement between (aka 'navigating') the different View categories. There are [multiple layout modes](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Switching_Navigator_modes) and a [text label preferences option](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Environment_Settings) for the sidebar. This sidebar may be hidden or revealed from the menu **[View▽Navigator](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Navigation#View)** or by using the [keybinding](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Keybindings#7). Navigator layout modes are 'Sidebar' type [plugins](#plugin) that can be added, removed, hidden or revealed using the Plugin Manager.  
Gramps divides and organizes the information about each [Primary Object](#primary-object) into a series of [Categories](#category), each with their own View. Each of the Category Views displays a smaller, more digestible portion of the total information that comprises a Genealogical Tree. The View categories are: ![Dashboard](gramps:icon:dashboard:16) [Dashboard](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Dashboard_Category), ![People](gramps:icon:person:16) [People](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#People_Category), ![Relationships](gramps:icon:relation:16) [Relationships](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Relationships_Category), ![Family](gramps:icon:family:16) [Families](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Families_Category), ![Charts](gramps:icon:pedigree:16) [Charts](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Charts_Category), ![Events](gramps:icon:event:16) [Events](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Events_Category), ![Places](gramps:icon:place:16) [Places](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Places_Category), ![Geography](gramps:icon:geo:16) [Geography](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Geography_Category), ![Sources (v3.4.x)](gramps:icon:source:16) [Sources](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Sources_Category), ![Citations](gramps:icon:citation:16) [Citations](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Citations_Category), ![Repositories](gramps:icon:repository:16) [Repositories](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Repositories_Category), ![Media](gramps:icon:media:16) [Media](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Media_Category), ![Notes](gramps:icon:note:16) [Notes](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Notes_Category)

#### Note ![Gramps-notes.png](gramps:icon:note:48) 
(![Notes](gramps:icon:note:16) *[prim. obj.](#primary-object)*) - Contains the information representing a textual brief record of facts and how it [references](#reference) other objects in the Tree. Notes can be added to any object at any any level of the Tree and are often used to detail the context of that record in the Tree.
Records in the [Note Category](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Notes_Category) contain free-form text with [basic formatting](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Note_markup_and_preformat_in_reports) and [linking](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Link_Editor) features. Notes can be categorized by [Tag](#tag) and [Type](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#note_type) in addition to the object to which it is attached. That information is created and modified using the [Notes Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_notes).

## O
#### Object
The most basic framework unit of genealogical data as structured in the Gramps [data model](https://www.gramps-project.org/wiki/index.php/Gramps_Data_Model).
The most complex structures are the [Primary Object](#primary-object) of a [category](#category). Each has an [Object Editor](#object-editor) that organizes entering data in that structure but also allows attaching or creating [secondary objects](#secondary-object).

#### Object Editor
*(aka Edit Object dialogs)*
(*core concept*) The object editor dialogs show the basic info of the [Primary Object](#primary-object) in the structured form of the header area where it can be directly edited. And the bottom tabbed section allows the editing of interrelationships with [secondary objects](#secondary-object) and provides access to the Object Editors for those secondary objects.
Click the following links for instructions of how to open and use each type of Edit Object dialog.
The available categories of object editor dialogs are: ![](gramps:icon:person:16) [Edit Person](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Editing_information_about_people), ![](gramps:icon:family:16) [Edit Family](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Editing_information_about_relationships), ![](gramps:icon:event:16) [Edit Event](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_events), ![](gramps:icon:place:16) [Edit Place](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_places), ![](gramps:icon:source:16) [Edit Source](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_sources), ![](gramps:icon:citation:16) [Edit Citation](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_source_citations), ![](gramps:icon:repository:16) [Edit Repository](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_repositories), ![](gramps:icon:media:16) [Edit Media](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_media_objects), ![](gramps:icon:note:16) [Edit Note](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_notes)
The available categories of object reference editor dialogs for [shared objects](#sharing) are: [Person Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Person_Reference_Editor) *(see [Associations](#association))*, [Child Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#Child_Reference_Editor), [Event Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Event_Reference_Editor_dialog), [Place Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Place_Reference_Editor), [Repository Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Repository_Reference_Editor), [Media Reference Editor](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Media_Reference_Editor_dialog)

#### Officiator
(*[event role](#event-role)*) A term to refer to the role of a person authorized to conduct an official duty or function. (Such as performing a marriage or funeral ceremony or conferring a vocational degree.) Jurisdiction may be derived from a from holding a position of civil or religious authority.   <small>*Use 'OFFICIATOR' rather than 'Officiant' for [GEDCOM7](#gedcom) Roles compatibility.*</small>

## P
#### patronym
(*[origin](#name-origin) Name attrib.*) - personal name based on the name of one's father.

#### Person ![Gramps-person.png](gramps:icon:person:48) 
(![People](gramps:icon:person:16) *[prim. obj.](#primary-object)*) - Contains the information specific to an individual person in the People category. The information may be edited directly using the [Edit Person](#edit-person) dialog.

#### Places ![Gramps-place.png](gramps:icon:place:48) 
(![Places](gramps:icon:place:16) *[prim. obj.](#primary-object)*) - The Gramps concept of a Place is a particular location independent of time. Over time, the same Place may have different hierarchical (or name) information due to changing borders and political situation. For example, Leningrad and St. Petersburg represent the same place, but with different names. Places in Gramps are stored in a hierarchy and are direct accessed via the
[Places category view](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Places_Category)
. Places can be defined (or refined) through the Place Editor and shared with the
[Select Place](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Select_Place_selector)
object selector. A Place consists of:
  - Descriptive Title
  - Name (with optional date span and language attributes)
  - A list of alternative names for the place
  - Type ([administrative divisions](#administrative-division) such as country, state, county ...)
  - Longitude/Latitude
  - Code (such as a country code or postal code)
  - A hierachical list of regions which enclose the place

#### plugin
(*aka* [plug-in](https://wikipedia.org/wiki/Plug-in_(computing)))
  - a type of [expansion framework that allows Gramps customization](https://www.gramps-project.org/wiki/index.php/Writing_a_plugin) by providing interface hooks to recognize and use external code.
  - customized module of code built to provide a specific feature or functionality that is not part of the core program.

The [various types](https://www.gramps-project.org/wiki/index.php/Addon_list_legend#Type) of Gramps plugin code modules can be enabled or disabled via a [plugin manager](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Plugin_Manager). Plugin types include: Citation formatter, [Database](https://www.gramps-project.org/wiki/index.php/Database_Backends), Doc creator, Exporter, [Gramplet](#gramplet), Gramps View ([*Category*](#view) or [*mode*](#viewmode)), Importer, [Map Service](https://www.gramps-project.org/wiki/index.php/Map_Services), Plugin lib, [Quickreport**/**Quickview](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports_-_part_8#Quick_Views), Relationships, [Report](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports_-_part_1), [Rule](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Add_Rule_dialog), Sidebar, Thumbnailer [Tool](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Tools).
Plugins can be builtin (*included with the normal distribution of Gramps*) or an [addon](https://www.gramps-project.org/wiki/index.php/6.0_Addons#Addon_List) (*installed via the [Third party addons management](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Third_party_addons_management) in Preferences*).

#### POSIX
[Portable Operating System Interface](https://wikipedia.org/wiki/Posix): a family of OS standards specified by the [IEEE](https://wikipedia.org/wiki/IEEE_Computer_Society) Computer Society for maintaining compatibility with variants of Unix (such as Linux) and other operating systems. Although the MacOS is "POSIX-certified", the term is used in this manual to generically refer to just the "Mostly POSIX-compliant" Linux and BSD distributions  [with verified Gramps downloads](https://www.gramps-project.org/wiki/index.php/Download#Linux_and_BSD_distributions) and which use the POSIX-style [environment](https://wikipedia.org/wiki/Filesystem_Hierarchy_Standard).

#### Preferences ![](gramps:icon:gramps-preferences:48)
The [Preferences](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Preferences) is an option in the **Edit** main menu that allows ***global*** customization of the appearance, defaults and behavior of Gramps. The customizations are categorized into the following tabs: [Data](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Data), [General](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#General), [Family Tree](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Family_Tree), [Import](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Import), [Limits](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Limits), [Colors](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Colors), [Genealogical Symbols](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Genealogical_Symbols), [ID Formats](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#ID_Formats), [Text](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Text), [Warnings](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Warnings), [Researcher](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Researcher).
(A [Theme](https://www.gramps-project.org/wiki/index.php/Addon:ThemePreferences) tab is available as an addon.)  
(see also ***Configure...*** option in the **View** main menu is an option. Those customization are limited to the currently active view and its Gramplets. The feature may also be accessed by the ![](gramps:icon:gramps-config:22) `Configure...` toolbar icon.)
The Gramps 5.1 and older preferences are categorized into the following tabs: [General](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#General), [Family Tree](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Family_Tree), [Display](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Display), [Text](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Text), [ID Formats](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#ID_Formats), [Dates](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Dates), [Researcher](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Researcher), [Warnings](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Warnings), [Colors](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Colors), [Genealogical Symbols](https://www.gramps-project.org/wiki/index.php/Gramps_5.1_Wiki_Manual_-_Settings#Genealogical_Symbols).

#### Prerequisites
Additional software required to make certain features of Gramps work and or some [addons](https://www.gramps-project.org/wiki/index.php/Category:Prerequisites).

#### Primary object
Primary objects are the [data structures](https://www.gramps-project.org/wiki/index.php/Using_database_API) at the top level of a [hierarchical collection of records](https://www.gramps-project.org/wiki/index.php/Gramps_Data_Model) in the Gramps [data model](https://www.gramps-project.org/wiki/index.php/Gramps_Data_Model). Beside the main structure of data, they can contain a hierarchy of [secondary objects](#secondary-object), and can be referenced by other primary or secondary objects. In the Gramps database, primary objects and the secondary objects that they contain are stored as separate records.  Each primary object type is stored in a separate table. See [Using database API, Primary Objects](https://www.gramps-project.org/wiki/index.php/Using_database_API#Primary_Objects) (see also *[secondary object](#secondary-object)*)
The types of [primary objects](https://www.gramps-project.org/wiki/index.php/Using_database_API#Primary_Objects) are:   
![Citations](gramps:icon:citation:16) [Citation](#citation), ![Events](gramps:icon:event:16) [Event](#event), ![Family](gramps:icon:family:16) [Family](#family), ![Media](gramps:icon:media:16) [Media](#media), ![Notes](gramps:icon:note:16) [Note](#note), ![People](gramps:icon:person:16) [Person](#person), ![Places](gramps:icon:place:16) [Place](#place), ![Repositories](gramps:icon:repository:16) [Repository](#repository), ![Sources (v3.4.x)](gramps:icon:source:16) [Source](#source), ![16x16-gramps-tag.png](gramps:icon:tag:16) [Tag](#tag).

#### Primary role
(*[event role](#event-role)*) A term to refer to the [role](#role) of the focal participant of an [Event](#event). **Primary** is the *default* role when adding a new Event in the [Edit Person](#edit-person) dialog.

#### Private flag ![](gramps:icon:gramps-lock:48)  
The Private option identifies sensitive information that should be redacted when sharing data or printing reports. *(This marker should not be confused with the generic user-definable [Tags](#tag) used for custom filters and color highlighting.)* Records are shown with: a ![22x22-gramps-lock.png](gramps:icon:dialog-warning:16)locked padlock when private; and, an ![22x22-gramps-unlock.png](gramps:icon:dialog-information:16)unlocked padlock when public. Clicking the padlock icon toggles between Private & Public flags. This manual override supplements the automated [Probably Alive](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Probably_Alive) and custom [Filter](https://www.gramps-project.org/wiki/index.php/Filter) features which help Gramps to respect Personal Privacy.
Gramps is a single user database and omits the typical security features of a multi-user system. So even "Private" data will be accessible from within Gramps. However, generating reports and exporting data default to redacting information flagged as Private.

#### Public flag ![](gramps:icon:gramps-unlock:48) 
The Public option identifies information that should be included when sharing data or printing reports. Records are shown with: a ![22x22-gramps-unlock.png](gramps:icon:dialog-information:16)unlocked padlock when public; and, an ![22x22-gramps-lock.png](gramps:icon:dialog-warning:16)locked padlock when private. Clicking the padlock icon toggles between Public & Private flags. By default, all records are created as Public.

## Q
#### Quick View
On-screen [reports](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports_-_part_8#Quick_Views) about information surrounding the active object that do not print or save to file. Generally the report is selected from a [context menu](#context-menu) for the selected category of record and will have no configurable options.   
The [Quick View **gramplet**](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Gramplets#Quick_View) refreshes a builtin [builtin](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Reports_-_part_8#Quick_Views) or [addon](https://www.gramps-project.org/wiki/index.php/6.0_Addons#Addon_List) QuickView reports as the focus of the active record is changed. The specific QuickView report is selected in a view configuration dialog opened with the **View▽Configure...** menu.

## R
#### Reference
the basic a system of linking relationships between objects in Gramps. When when an object is added in the Editor for record, a [Reference](https://www.gramps-project.org/wiki/index.php/References#definition) (link) is created in the object that was added.

#### References tab ![Gramps-relation.png](gramps:icon:relation:48) 
a system of linking between objects in Gramps. When objects of Gramps are linked, the [References tab](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_1#References) lists the objects to link toward it.

#### Regular Expressions
[RegEx](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Regular_Expressions) is a system to specify a text string pattern for comparing and matching. Optionally used to extend a power of the Filter Gramplets and Custom Filters rules.
Filters in [Gramps use the RegEx format specified by the installed version of Python](https://gramps.discourse.group/t/which-regex-syntax-does-gramps-use/2278/8)

#### Re-order ![](gramps:icon:go-up:48) 
To change the sequence of items within a list of [secondary objects](#secondary-object). [The interface for (and consequences of) re-ordering that sequence varies based on the list type.](https://gramps.discourse.group/t/re-ordering-data-in-gramps-topic-expansion-outline-for-wiki/5568)
The natural order of a list follows when the data was created. The first item in an ordered list is often considered the primary or preferred item of that type. The primary/preferred may be the only object considered in some charts and analyses. So when data entry of related objects was out of sequence, a re-ordering option becomes necessary.
Re-ordering affects display order in the Tree, charts, and most reports. Note that in some contexts, dates can override the manual order, particularly for Places and Names.

#### Repository ![Gramps-repository.png](gramps:icon:repository:48) 
(![Repositories](gramps:icon:repository:16) *[prim. obj.](#primary-object)*) - Contains the information related to a physical or virtual structure where genealogical and family history sources are stored. Once a [Repository is added](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_repositories) to a Gramps Tree, it can used to organize [Sources](#source).

#### role
function performed or part played by a person (or other Gramps [object](#object)) in a particular situation. When objects of Gramps are linked, a Reference is created where the implicit Role disambiguates the relative nature of the reference. *For explicitly defined roles, see [event role](#event-role) and [association role](#association)*

#### Romanization
linguistic representation of a word in the Roman (Latin) alphabet

#### Rule
a pre-defined abstraction that simplifies the interface for a structured query about a particular facet of your family tree. Rules allows users to choose search criteria without needing to understand the intricate details of the actual database query language.   Rules are layered via the [Custom Filters](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Custom_Filters) interface to [filter](#filter) with complex criteria.

## S

#### Secondary object
Secondary objects are contained within other [objects](#object) of the structured Gramps [data model](https://www.gramps-project.org/wiki/index.php/Gramps_Data_Model), and cannot be referenced directly. They can contain other secondary objects. Examples include:  Name, Date and Address. See [Using database API, Secondary Objects](https://www.gramps-project.org/wiki/index.php/Using_database_API#Secondary_Objects) (see also *[primary object](#primary-object)*)

#### Selector combo box
*([graphical user interface terminology](#gui))* - a [standard text entry box paired with pull-down list button](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Selector_Combo_Boxes) is a [Gtk toolbox widget](https://docs.gtk.org/gtk3/visual_index.html) (based on the standard [combo box](https://wikipedia.org/wiki/Combo_box)). The combination of a drop-down list and a single-line editable textbox allows the user to: either key in a value directly; or, select a value from the list. Moreover, keying in a value that is not already in the list will add that [custom type](#custom) to the drop-down list.

#### Shared objects ![](gramps:icon:gtk-index:48)
![](gramps:icon:gtk-index:16) Sharing allows an Object to be linked at multiple places in the tree. Doing so establishes a relationship or maintains single set of attributes (or [secondary objects](#secondary-object)) that they hold in common. ([Roles](#role) for shared Events define the person or family participation level.)
**[Object Reference Editors](#object-reference-editors)** allow updates to a shared object to be reflected in all instances mentioning (referencing) that shared object. Redundantly creating object with the same information should be avoided. (So, refining a Transcription Note shared by multiple Citations will show the updated transcription in all the Citations.)
Object descriptions are grouped in two distinct sections:   
 • The **Reference Information** section contains information unique to one instance.   
 • The **Shared Information** of an object will be seen in all instances that are linked to it.

#### selector
combo interface box that allows you to select an object. The [Select Family selector](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Selector_dialogs) is one example.

#### Source ![](gramps:icon:source:48) 
(![Sources (v3.4.x)](gramps:icon:source:16) *[prim. obj.](#primary-object)*) - Sources can be a person *(family, friend, another researcher)*, thing *(book, magazine newspaper, census)*, or place *(courthouse, church, library, genealogical/historical society... although places might be better handled as Repositories)* from which information comes, arises, or is obtained. After [adding a Source](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#Editing_information_about_sources) with the [new source dialog](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Entering_and_editing_data:_detailed_-_part_2#New_Source_dialog) to the [Sources category](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Sources_Category) of a Gramps Tree, the Source can be referenced when adding a [Citations](#citation) and organized within [Repositories](#repository). The same Source may exist in multiple Repositories and may have different Media Types (such as book, microfilm, or electronic) and Call numbers in each Repository.
[more](https://www.gramps-project.org/wiki/index.php/Sources#Definition)

#### SQLite
(*[database backend](https://www.gramps-project.org/wiki/index.php/Database_Backends) engine*) The [SQLite project's in-process library](https://sqlite.org/about.html) (also known simply as SQLite) is the *default database engine* used since the [5.1](https://www.gramps-project.org/wiki/index.php/Database_Formats#Gramps_5.1) version of Gramps. The support was extended from [BSDDB](#bsddb) in the 5.0 version via the [DB-API Database Backend](https://www.gramps-project.org/wiki/index.php/DB-API_Database_Backend).

#### Swatch
*([graphical user interface terminology](#gui))* - a [color swatch](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Pick_a_Color_selector) is a sample square of a color or color pattern. Swatches may be dragged from the [Pick a Color selector](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Settings#Pick_a_Color_selector) to apply that specific color to preferences.
The word originally referred to sample pieces of cloth or fabric used for choosing or testing colors, patterns, or textures for interior or exterior design. It now means any small sample or representation of a larger whole and is commonly usage in the context of color representation and selection in software applications.

## T
#### Tag ![](gramps:icon:tag:48) 
(![](gramps:icon:tag:16) *[prim. obj.](#primary-object)*) - A custom titled and color-coded label that [can be created with the Organize Tags dialog and attached](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Filters#Tagging) to selected ![Citations](gramps:icon:citation:16) [Citation](#citation), ![Events](gramps:icon:event:16) [Event](#event), ![Family](gramps:icon:family:16) [Family](#family), ![Media](gramps:icon:media:16) [Media](#media), ![Notes](gramps:icon:note:16) [Note](#note), ![People](gramps:icon:person:16) [Person](#person), ![Places](gramps:icon:place:16) [Place](#place), ![Repositories](gramps:icon:repository:16) [Repository](#repository) or ![Sources (v3.4.x)](gramps:icon:source:16) [Source](#source) objects for the purpose of easy identification and filtering.  
A keyword or phrase used to group the collection to produce a report. Multiple tags may be used to label and categorize objects into multiple groups when filtering by other attributes is not viable.

#### Toolbar
*([graphical user interface terminology](#gui))* - The [Toolbar](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Toolbar) is a ribbon (located below the application menubar) with button shortcuts for the most widely needed functions associated with the current view. The selection of buttons changes in response to the context of the current view. (e.g., toolbar buttons for switching mapping [view modes](#view-mode) will only appear for the [Geography view](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Geography_Category).)

#### Typographical conventions
The [customary formatting](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Preface#Typographical_conventions) having special (and possibly peculiar) meaning when used throughout the MediaWiki driven [Gramps manual](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual) and documentation. The different typeface accents, highlighting and enclosures indicate specific parts of the Gramps [Graphical User Interface](#graphical-user-interface) ([GUI](#GUI)) or prompt a User activity.

## U

#### Unknown
(*[event role](#event-role)*) A placeholder for when the [role](#role) of a participant in an [Event](#event) has not yet been defined. Gramps sets an appropriate default Role as each new Event type is created. But when a new participant is associated with an existing Event via Share or drag'n'drop, the Role isn't as predictable. In such a case, an Unknown placeholder is inserted.
Any Unknown [Event Role](#event-role) type causes a variety of reporting problems. [(Rule_expansions)Persons and Families with Unknown Roles](https://www.gramps-project.org/wiki/index.php/Addon:Rule_expansions#People_with_events_with_a_selected_role) should be found and the Roles manually replaced as soon as is practical.

#### User Directory 
(*core concept*) An alias for the file folder (directory) location where customizations (e.g.: preferences files, [addons](#addon), [plugins](#plugin)) are stored for the Gramps family of genealogy tools. Since this folder location varies by which Operating System and which Gramps fork has been installed, the **User Directory** is an 'alias' (aka placeholder) used in instructions about re-configuring Gramps.   
This alias allows [instructions for locating your specific **User Directory** file location](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_User_Directory) to be consolidated in the documentation.

## V

#### View category
*([graphical user interface terminology](#gui))* - a [**View category**](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window) (often simply called a  "**[View](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window)**") is a Gramps-specific name for the collection of [View modes](#view-mode) (display layouts) presenting information in a structured and predictable manner. Different Views are selected from the [Navigator](#navigator) (left sidebar),   
Layouts are in table, outline or graphical formats; depending on the preferred way to represent how the data elements relate to on another.   
Gramps divides and organizes the information about each [Primary Object](#primary-object) into a series of [Categories](#category), each with their own View. Each of the Category Views displays a smaller, more digestible portion of the total information that comprises a Genealogical Tree. The View categories are: ![](gramps:icon:dashboard:16) [Dashboard](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Dashboard_Category), ![](gramps:icon:person:16) [People](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#People_Category), ![](gramps:icon:gramps-relation:16) [Relationships](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Relationships_Category), ![](gramps:icon:family:16) [Families](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Families_Category), ![](gramps:icon:pedigree:16) [Charts](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Charts_Category), ![](gramps:icon:event:16) [Events](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Events_Category), ![](gramps:icon:place:16) [Places](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Places_Category), ![Geography](gramps:icon:geo:16) [Geography](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Geography_Category), ![](gramps:icon:source:16) [Sources](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Sources_Category), ![](gramps:icon:citation:16) [Citations](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Citations_Category), ![](gramps:icon:repository:16) [Repositories](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Repositories_Category), ![](gramps:icon:media:16) [Media](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Media_Category), ![](gramps:icon:note:16)[Notes](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Categories#Notes_Category)

#### View mode
*([graphical user interface terminology](#gui))* - a **[View mode](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window)** is a Gramps-specific name for the display layouts presenting [View category](#view-category) information in a structured and predictable manner. A [View category](#view-category) may have alternate **view modes** (subcategories) of display layout. (e.g., Views with Table layouts might have flat listed or hierarchically grouped modes.) Navigating between View modes is from the [toolbar](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Toolbar) and [Navigator](https://www.gramps-project.org/wiki/index.php/Gramps_6.0_Wiki_Manual_-_Main_Window#Switching_Navigator_modes).   
Each mode of a category can be independently ![Gramps-config.png](gramps:icon:preferences-system:16) configured. Each mode may maintain a separate object selection, filtering, and organization for its Gramplet bars.  
View data may be further subdivided with tabbed pages of layouts.

## W

#### wiki
(Hawaiian [loanword](https://wikipedia.org/wiki/Loanword)) meaning 'quick'; or 'wikiwiki' meaning 'very quick'. For Gramps users, ***[the Wiki](https://www.gramps-project.org/wiki/index.php/User_manual)*** (aka ***[Wiki Manual](https://www.gramps-project.org/wiki/index.php/User_manual)***) refers to the collaborative website of educational material which is organized using the [MediaWiki](https://mediawiki.org/wiki/MediaWiki) [content management system](https://wikipedia.org/wiki/Content_management_system). The core pages of that website being the structured reference-style [Gramps](#gramps) software user's operating guide.  <small>*(Note that specific [tutorial](https://www.gramps-project.org/wiki/index.php/Category:Tutorials) documents are also part of the wiki.)*</small>
For most internet users, the word is most often an inadvertent allusion to the 1995 [WikiWikiWeb](http://wiki.c2.com/?WikiWikiWeb), the first website that builtin tools encouraging users to quickly & easily collaborate to expand the content of the site. See the term: ['wiki'](https://wiktionary.org/wiki/wiki) in [Wiktionary](https://wiktionary.org/wiki/Wiktionary)

#### Witness
(*[event role](#event-role)*) The term that applies to the people asked to be present at an event so as to be able to testify to its having taken place

## X

#### XML
acronym: [E**x**tensible **M**arkup **L**anguage](https://wikipedia.org/wiki/XML). A schema used to define the expected structure of data in a text format.  The system annotates a document in a way that data elements are syntactically distinguishable from identifying tags. A markup language defines a set of rules for encoding documents in a fault tolerant format that is both (marginally) human-readable and machine-readable.   
Gramps will [generate XML](https://www.gramps-project.org/wiki/index.php/Generate_XML) format natively in compressed and uncompressed forms identified with a `.gramps` or `.gpkg` file extension. It is the format that definitively supports every piece of genealogical data stored by Gramps. Used as the working format until Gramps 2.0 started using a *[database backend](https://www.gramps-project.org/wiki/index.php/Database_Backends)* to improve performance, XML is now the standard Tree data backup format and recommended data exchange format.  
See the [reference documentation for the versions](https://www.gramps-project.org/xml/) of Gramps [RELAX NG](https://www.gramps-project.org/wiki/index.php/Gramps_XML#RELAX_NG_generation) (**RE**gular **LA**nguage for **X**ML **N**ext **G**eneration)(`.rng`) schema XML and [DTD](#dtd)

## Y

## Z
