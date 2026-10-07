# Markdown Dash (v1.4.0)
<!-- undocked=false -->
[Markdown-pohjaiset työkalut](../README.md)
![gramps:icon:io.github.shiftey.Desktop:256](gramps:icon:io.github.shiftey.Desktop:256) ![gramps:icon:org.gramps_project.Gramps:256](gramps:icon:org.gramps_project.Gramps:256) 
![gramps:icon:gramps-addon:128](gramps:icon:gramps-addon:128) ![gramps:icon:gramps-gramplet:128](gramps:icon:gramps-gramplet:128) ![gramps:icon:gramps-notes:128](gramps:icon:gramps-notes:128) ![gramps:icon:gramps-pedigree:128](gramps:icon:gramps-pedigree:128)

`README.md`-tiedostoista on tullut yleisiä Gramps-lisäosasäilöjen kehitysprojekteissa GitHubissa. Valitettavasti suurin osa Markdown-muunnoksesta tehdään palvelinpuolella. Tiedostojen avaaminen paikallisesti selaimella ei tue Markdownia. Niinpä nämä kehitys-`README.md`-tiedostot ovat kyllä saatavilla, mutta rajoitetusti käytettävissä, kun ne avataan paikallisesti.

Tätä varten on olemassa **MarkdownDash**-gramplet. Se on joustava, paikallinen dokumenttien lukija Markdown-(`.md`) asiakirjojen natiiviin renderöintiin ja selaamiseen sukuhistoriallisessa työtilassamme. Suorituskykyä ja siistiä työpöytäintegraatiota varten suunniteltu ratkaisu tarjoaa vuorovaikutteisen dokumenttiympäristön käyttäen pelkästään **GTK+ 3:aa, Pangoa ja GdkPixbufia** — ilman raskaita riippuvuuksia kuten WebKit, upotetut selaimet tai kolmannen osapuolen jäsennyspaketit.

---

## Keskeiset ominaisuudet

- **Arkkitehtoninen erottelu:** Suunniteltu korkean suorituskyvyn kevyenä kuorena (`MarkdownDash.py`), joka delegoi token-jäsennyksen, sisäisten taulukoiden rakentamisen, mukautetut tyylitunnisteet ja kuvakehakuoperaatiot irrotettuun apuprosessiketjuun (`MarkdownUtils.py`).
- **Dynaaminen istuntovälimuisti:** Seuraa automaattisesti lukuhistoriaasi sovelluksen uudelleenkäynnistysten välillä ja säilyttää aktiivisen asiakirjan sijainnin sisäisen tiedostojärjestelmävälimuistin kautta (`.last_file.cache`).
- **Täysin integroitu toimintopalkki:** Varustettu vuorovaikutteisella alatyökalurivillä, jossa on:
    **✎ Muokkaa tiedostoa** — Yhdellä napsautuksella käynnistettävä toiminto, joka avaa nykyisen asiakirjan turvallisesti työpöytäympäristösi oletusteksti- tai Markdown-editoriin.
    **Tiedostotilan palkki** — Kontekstin mukainen polkukuvaus, joka näyttää asiakirjan tilan ja lokalisoinnin alkuperän suhteessa peruslisäosapuuhun.
    **📂 Selaa kansioita** — Natiivi GTK-tiedostonvalitsin, jota on täydennetty älykkäillä tiedostosuodattimilla (`*.md`, `*.markdown`) ja joka lajittelee oletuksena saatavilla olevat kohteet muokkausajan mukaan laskevasti.
    **▾ Tiedostonvalitsin** — Dynaaminen rinnakkaisvalikko, joka näyttää reaaliaikaisen luettelon saman kansion Markdown-tiedostoista sujuvia yhteydenvaihtoja varten.
![Markdown Dashboard Interface Preview](media/gui.png)

---

## Mukautetut ohjeet

Markdown Dash tarkistaa minkä tahansa ladatun asiakirjan kaksi ensimmäistä riviä tiedostokohtaisten ohjeiden ja etulehtimäärityksen lohkojen varalta.

### 1. Asiakirjan otsikon korvaus
Jos asiakirja alkaa tavallisella Markdown-otsikolla 1 (`#`), gramplet kirjoittaa työtilan kehysotsikon dynaamisesti vastaamaan tekstin sisältöä.
```markdown
# Mukautettu hallintapaneelin otsikko
```

### 2. Asettelun näkyvyysmääritys

Voit välittää tekstimoottorille tiukkoja totuusarvokytkimiä tai asettelukomentoja tavallisten HTML-kommenttien sisällä (``), jotka sijoitetaan kahden ensimmäisen rivin sisään:

Käytettävissä olevat parametrit:

  * `controls=false`: Piilottaa kokonaan toimintopalkin työkalurivin, jolloin näkymä on mukaansatempaavampi ja vain luettavaksi tarkoitettu.

  * `edit=false / status=false / browse=false / folder=false`: Piilottaa yksittäisiä painikkeita toimintopalkista, mutta jättää muut näkyviin.

  * `undocked=true`: Irrottaa grampletin automaattisesti sen ylätason paneeliruudukosta omaan erilliseen, kelluvaan GTK-ikkunakonttoriinsa latauksen yhteydessä.

## ![gramps:icon:insert-link:48](gramps:icon:insert-link:48) Rikkaat linkkikaavat ja vuorovaikutteiset toiminnot

Linkit ovat tekstialueella täysin semanttisia ja tyyliteltyjä värikoodattuja merkkejä. Elementtien napsauttaminen käynnistää erilaisia natiiveja toimintoja niiden kohde-etuliitteiden perusteella:

1. Hyperlinkit (sininen teksti)

Tavalliset ulkoiset verkko-osoitteet tai eksplisiittiset järjestelmäprotokollat avautuvat suoraan käyttöjärjestelmäsi oletuskäsittelijällä.

Esimerkki:
``` markdown
Lue Visual Icon Inventory -luettelo saatavilla olevista resursseista.
