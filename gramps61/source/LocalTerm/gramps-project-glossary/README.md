# CSV download files for Weblate

During the development phase of [LocalTerm](../README.md), a set of `language` context metadata must be manually added to each CSV to make recognizable by the LocalTerm gramplet.
These rows tell the **LocalTerm** Dashboard gramplet how to manage, display and link that language translation file. The expectation is that these `language` context `source` terms will be added to the stings in the Weblate Glossary.

# Sample `language` metadata for EnglishCSV
``` csv
location,source,target,id,fuzzy,context,translator_comments,developer_comments
,EnglishExonym,English Term,,no,language,"language name in english",Gramps_Glossary/en
,endonym,English Term,,no,language,"название языка на родном языке",Gramps_Glossary/ru
,language code,ru,,no,language,"language code in ISO 639 standard",https://hosted.weblate.org/projects/gramps-project/-/ru/
,translators,translators,,yes,language,"lead translator for GUI",Portal:Translators#ru
,translations,переводы,,yes,language,"status of wiki translation",User_manual_translations#ru
,documentation,документация,,yes,language,"translated wiki page index",Category:Ru:Documentation
```

# Sample `language` metadata for Turkish CSV
``` csv
location,source,target,id,fuzzy,context,translator_comments,developer_comments
,EnglishExonym,Turkish,,no,language,"İngilizce dil adı",https://gramps-project.org/wiki/index.php/Gramps_Glossary/en
,endonym,Türkçe,,no,language,"ana dildeki dil adı",https://gramps-project.org/wiki/index.php/Gramps_Glossary/tr
,language code,tr,,no,language,"ISO 639 standardında dil kodu",https://hosted.weblate.org/projects/gramps-project/-/tr/
,translators,çevirmenler,,yes,language,"GUI için baş çevirmen",https://gramps-project.org/wiki/index.php/Portal:Translators#tr
,translations,çeviriler,,yes,language,"wiki çevirisinin durumu",https://gramps-project.org/wiki/index.php/User_manual_translations#tr
,documentation,dokümantasyon,,yes,language,"çevrilmiş wiki sayfası dizini",https://gramps-project.org/wiki/index.php/Category:Tr:Documentation
```

These Weblate download CSV files are in a folder named in the pattern that Weblate sets for a Component. (e.g., `gramps-project-glossary`) 
Likewise, the filenames follow the same pattern but append a language code designation. (e.g., `gramps-project-glossary-en.csv`)

The Gramps components available on Weblate are:
* [Program](https://hosted.weblate.org/projects/gramps-project/gramps/)
* [Addons](https://hosted.weblate.org/projects/gramps-project/addons/)
* [Web](https://hosted.weblate.org/projects/gramps-project/web/)
* [Gramps Glossary](https://hosted.weblate.org/projects/gramps-project/glossary/) 
