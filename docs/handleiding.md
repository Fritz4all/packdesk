# Handleiding

Wat PackDesk kan en hoe je het gebruikt, per onderdeel van het beheer en het klantportaal.
Het beheer staat op `/beheer/`. Wat een medewerker ziet en mag, hangt af van zijn rol.

## Werken in het beheer

- **Inloggen** gaat met e-mailadres en wachtwoord.
- **Menu:** elke sectie is in en uit te klappen; je browser onthoudt wat je open of dicht hebt gezet.
  Bovenaan staan *Alles uitklappen* en *Alles inklappen*.
- **Zoeken in alles:** Ctrl+K (Mac: Cmd+K) zoekt in alle lijsten waar je rechten voor hebt:
  licentienummers, serienummers, klanten, contactpersonen, gebruikers, servicepakketten, enz.
- **Taal van het beheer:** kies NL, EN of DE in het accountmenu rechtsboven. De standaard staat in
  *Instellingen → Algemeen → Beheertaal*. Mails aan klanten blijven in de taal van de website.
- **Licht of donker:** via het accountmenu.
- **Lijsten:** elke lijst heeft een zoekveld en filters; de knop om iets toe te voegen staat naast het
  zoekveld. Regels met meer details (zoals adressen) staan ingeklapt; *Bewerken* klapt ze open.
  Kolommen met vaste waarden (zoals soort, status, ja/nee, datums of rol) hebben een filterknopje in de
  kop: klik erop en kies een waarde. Een paars knopje betekent dat er op die kolom gefilterd wordt.
- **Sectiepagina's:** klik je in het kruimelpad op een sectie (bijv. *Servicepakketten en licenties*), dan
  zie je dezelfde onderdelen als in het menu.

## Overzicht

- **Dashboard** (startpagina): totalen zoals actieve klanten, aanmeldingen die op goedkeuring wachten,
  licenties die nog niet geregistreerd zijn of binnenkort aflopen, en problemen met nummering. Met
  *Aanpassen* versleep en verberg je blokken; *Standaard herstellen* zet alles terug.
- **Verkoop en marge:** omzet, brutomarge en margepercentage, per maand en per categorie, de beste
  klanten en een prijslijst met inkoopprijs en marge per pakket. Kies een periode of klik op een maand,
  en kies *Alles*, *Servicepakketten* of *Onderdelen*.
  - Servicepakketten rekenen met de inkoopprijs die het pakket nu heeft; vul die in bij de pakketten,
    anders is de marge te hoog (de vorige webshop had geen inkoopprijzen).
  - Onderdelen rekenen met de verkoop- en inkoopprijs van elk besteld onderdeel, min correcties en de
    korting van de klant. Toeslagen (kleine bestelling, spoed, verzending) tellen als omzet zonder inkoop;
    geannuleerde bestellingen tellen niet mee.

## Klanten

- **Een klant openen** toont eerst een overzicht om te lezen: gegevens, adressen, e-mail en kortingen, en
  tabbladen met alles wat bij de klant hoort (contactpersonen, licenties, bestellingen, facturen,
  onderdelenaanvragen en -bestellingen, storingen). Per tabblad de laatste 50, met een link naar de
  volledige lijst. Wijzigen of verwijderen kan pas na *Bewerken*.
- **Klantsoort wijzigen:** vink klanten aan in de lijst en kies *Klanttype van geselecteerde klanten wijzigen*.
- **Klanten:** bedrijfsgegevens, klantsoort, status (wacht op goedkeuring, actief, geblokkeerd),
  klantnummer, aparte e-mailadressen voor bestellingen, onderdelen en facturen, kortingen, adressen en
  contactpersonen.
  - *Goedkeuren* geeft de klant een nummer, zet de logins aan en stuurt een activeringsmail.
  - *Blokkeren* zet de logins uit.
  - *Login sturen naar contactpersonen zonder login* stuurt een uitnodiging met een link om zelf een
    wachtwoord te kiezen. PackDesk mailt nooit wachtwoorden.
- **Klantsoorten en landen** beheer je zelf, in drie talen. Per land kun je een btw-nummer verplicht maken.
- **Aanmelden:** bedrijven melden zich zelf aan via `/aanmelden/`. Onder *Klantinstellingen* bepaal je
  of dat kan, welke teksten er staan, of je aanmeldingen eerst goedkeurt, wie een melding krijgt, de
  activeringsmail, de standaardkorting en per veld of het verborgen, optioneel of verplicht is.
- **Exporteren en importeren:** *Exporteren* maakt een zip-bestand met klanten en alles wat erbij hoort
  (adressen, contactpersonen, bestellingen, licenties, storingen, facturen), met de onderlinge
  koppelingen. *Importeren* leest zo'n bestand in, maar laat eerst per klant zien wat er zou gebeuren:
  wat nieuw is, wat al bestaat en welke gegevens verschillen. Per klant kies je *overslaan*,
  *overschrijven* of *als nieuwe klant importeren*. Er wordt nooit iets verwijderd. Wachtwoorden worden
  nooit geëxporteerd.

## Bestellingen en facturen

- **Bestellingen:** alle bestellingen van klanten, met de regels en de aangemaakte licenties.
  *Factuur maken* maakt alsnog een factuur als dat bij het bestellen niet lukte.
- **Facturen:** bij elke bestelling maakt PackDesk een factuur als pdf en mailt die naar het
  factuuradres van de klant (uit te zetten, ook per klant). Per factuur: bekijken, downloaden,
  *Opnieuw naar klant sturen* en een logboek van verzonden mails. Facturen kunnen niet worden
  verwijderd.
  - **Factuurinstellingen:** betaaltermijn, betaaltekst, opvallende mededeling, voettekst en de tekst
    van de mail, per taal. Voor gevorderden kan een eigen sjabloon de standaardopmaak vervangen.
  - **Veilige nummering:** staat de factuurteller niet boven het hoogste bestaande factuurnummer, dan
    maakt PackDesk geen factuur en krijg je een melding. Zo ontstaat nooit een dubbel nummer.
- **Bestelinstellingen:** btw-percentage, teksten, hoe lang vooraf klanten kunnen verlengen, en of
  klanten fysieke pakketten met labels kunnen laten sturen.

## Servicepakketten en licenties

- **Catalogus:** categorieën, hardwareklassen, merken (optioneel met controle van het artikelnummer),
  apparaattypes, soorten opties, looptijden, serviceniveaus en de servicepakketten met prijs en
  inkoopprijs. Alles in drie talen.
- **Licenties:** per klant en pakket, met status (niet geregistreerd, geregistreerd, afgelopen),
  apparaat, opties en looptijd. Zoeken op licentienummer, serienummer, klant of referentie.
- **Licentie-instellingen:** termijnen voor registreren, de opbouw van het licentienummer, wie een
  melding krijgt van een registratie, en de teksten van de registratiewizard.

## Onderdelen

Zo werkt het, net als in de vorige webshop:

1. **Aanvraag:** de klant vult in het klantportaal (*Onderdelen*) per onderdeel het merk, het
   artikelnummer, het aantal en eventueel het apparaat in, en kan om spoed vragen (dan met afleveradres).
   De aanvraag krijgt een nummer (`WS…`); klant en interne ontvangers krijgen een mail.
2. **Beantwoorden** (*Onderdelenaanvragen*): vul per onderdeel de status en de inkoopprijs en levertijd
   per verpakking (nieuw, pack, refurbished) in. Onder elk onderdeel staat de verkoopprijs die daaruit
   volgt (inkoopprijs × factor uit *Opslagstaffels*). Bij spoed: of het kan en wat het kost. Een
   opmerking voor de klant typ je bij het onderdeel. Is alles beantwoord, dan krijgt de klant
   automatisch een mail en is de aanvraag een aantal dagen geldig (*Instellingen onderdelen*).
   Elke wijziging komt in de geschiedenis van het onderdeel.
3. **Bestellen:** de klant kiest per onderdeel en verpakking hoeveel, het afleveradres en de betaalwijze,
   ziet de totalen (met de eigen korting voor onderdelen, toeslag kleine bestelling, spoedkosten,
   verzendkosten buitenland) en bevestigt. De bestelling krijgt het nummer van de aanvraag plus `-1`,
   `-2`, … en een factuur.
4. **Uitleveren** (*Onderdelenbestellingen*):
   - *Op rekening* gaat direct naar *Uit te leveren*; vanaf het bedrag in de instellingen eerst naar
     *Wacht op vrijgave* (knop *Vrijgeven*). Andere betaalwijzen wachten op betaling (knop *Betaling ontvangen*).
   - *Uitleveren* legt vast hoeveel er nu geleverd is (ook in delen); de klant krijgt een mail. Is alles
     geleverd, dan is de bestelling klaar.
   - *Corrigeren* verlaagt aantallen die niet geleverd kunnen worden; *Annuleren* annuleert de hele
     bestelling. Beide vragen een reden en mailen de administratie het bedrag om te crediteren.
   - *Paklijst* is een afdrukbare lijst van wat nog geleverd moet worden.
5. **Instellingen:** betaalwijzen (op rekening of eerst betalen, extra kosten), levertijden, opslagstaffels,
   geldigheid, toeslagen, thuisland (voor verzendkosten buitenland en verlegde btw), grens voor vrijgave,
   teksten en interne ontvangers. Alles in drie talen waar het om teksten gaat.

Wie wat mag: de rol *Service* behandelt aanvragen en levert uit, *Financieel* ziet alles en mag
uitleveren en corrigeren, *Beheerder* mag ook de instellingen wijzigen.

## Telefonie

Een calculator in het klantportaal (*Telefonie*) waarmee klanten, zoals resellers, een telefooncentrale
doorrekenen en huren met kopen vergelijken. Staat standaard uit: zet hem aan onder *Instellingen telefonie*.

- **Artikelen** (*Telefonie-artikelen*, per categorie): huur per maand, koopprijs (eenmalig) en per maand
  bij koop. Een leeg veld betekent dat het artikel niet zo te krijgen is. Bij *aantal = som van* telt
  PackDesk het aantal zelf, bijvoorbeeld één gebruikerslicentie per toestel en installatie per licentie.
- **Rekenen:** de klant vult aantallen in en ziet het totaal voor huren (per maand, plus eenmalige
  installatiekosten) en voor kopen (eenmalig en per maand). Op de prijzen komt de marge die de klant
  invult (prijs × (1 + marge %)); de standaardmarge staat in de instellingen.
- **Offertes:** de klant kan een berekening opslaan als offerte, voor de eigen klant (prijzen met marge)
  of voor zichzelf (inkoopprijs, marge en verkoopprijs), en die afdrukken. Een opgeslagen offerte houdt
  de prijzen van dat moment. In het beheer zie je alle offertes onder *Telefonie-offertes*.

## Printing services (archief)

De vorige webshop bood printing services aan (printers met support en afdrukprijzen). Dat is gestopt; de
laatste offerte is uit 2013. De gegevens zijn bewaard om in te zien: printers en verbruiksartikelen,
supportpakketten, offertes, contracten (met serienummers en tellerstanden) en verbruiksbestellingen.
Je kunt zoeken en kijken, maar niets wijzigen of nieuw maken; de rekenregels van de vorige webshop zijn
niet meer bekend.

## Storingsmeldingen

- Meldingen met status nieuw, in behandeling of afgesloten, interne notities, de dekking van de
  licentie en de bijlagen. Het menu toont hoeveel nieuwe meldingen er zijn.
- **Instellingen:** aan of uit, teksten, wie de meldingen ontvangt, de bevestigingsmail, het maximale
  aantal en de grootte van bijlagen, en de keuzes voor de gewenste afhandeling.

## Gebruikers en rollen

- **Gebruikers:** medewerkers en klantlogins. Elke medewerker heeft precies één rol. Bij klantlogins
  staan beheertaal, rol en superuser niet; alleen superusers zien de superuser-schakelaar. In de lijst kun
  je meerdere gebruikers tegelijk uit- of inschakelen (jezelf niet). Bij *Wachtwoord* zie je of er een
  wachtwoord is ingesteld, met knoppen om er een in te stellen of een resetmail te sturen.
- **Rollen:** maak zelf rollen en vink per onderdeel aan wat een rol mag (bekijken, toevoegen,
  wijzigen, verwijderen, en speciale rechten zoals *nummertellers corrigeren* of *databases
  vergelijken*). Je kunt alleen rechten geven die je zelf hebt. Een nieuwe installatie heeft vier
  standaardrollen: Beheerder, Financieel, Service en Medewerker.

## Configuratie

- **Instellingen:** alles wat per bedrijf verschilt.
  - *Algemeen:* naam, standaardtaal, beschikbare talen, beheertaal, omschrijving voor zoekmachines
    (de korte tekst onder de titel in Google en bij gedeelde links).
  - *Huisstijl:* logo, favicon, kleuren, standaard licht/donker en of bezoekers dat zelf kiezen.
  - *Homepage:* slogan, introductie, knoptekst.
  - *Voettekst* en *bedrijfsgegevens* (KvK, btw, IBAN).
  - *Onderhoud:* de onderhoudsmodus (bezoekers zien een melding en kunnen niet inloggen; medewerkers
    wel) en een meldingsbalk bovenaan de site, bijvoorbeeld om onderhoud aan te kondigen.
  - *Adressen:* een of meer adressen; per adres vink je aan waar het gebruikt wordt (website,
    facturen, offertes, orderbevestigingen, mails, afzender op labels).
  - *Homepageblokken* en *menu-items:* de vakjes op de homepage en de links in de kopregel, per taal,
    zichtbaar voor iedereen, alleen gasten of alleen ingelogde klanten.
- **Instellingen → Beveiliging:** na hoeveel minuten zonder activiteit medewerkers en klanten
  automatisch worden uitgelogd (standaard 120 en 60 minuten; 0 = ingelogd blijven, hooguit twee
  weken), en na hoeveel dagen de prullenbak wordt geleegd.
- **Prullenbak:** alles wat je in het beheer verwijdert, komt hier terecht, samen met wat er automatisch
  mee verwijderd werd (bijv. de adressen en contactpersonen van een klant). Zoeken, sorteren op elke
  kolom en filteren op soort, datum en wie het verwijderde. Vink items aan om ze in één keer
  **terug te zetten** of **definitief te verwijderen**; bij een item staan dezelfde knoppen. Terugzetten
  zet alles terug met dezelfde nummers en koppelingen. Lukt dat niet omdat er intussen iets met hetzelfde
  nummer is aangemaakt, dan blijft het item in de prullenbak en zie je waarom. Bestanden (zoals bijlagen)
  worden pas weggegooid bij definitief verwijderen. Na het ingestelde aantal dagen (standaard 30) wordt
  de prullenbak vanzelf geleegd.
- **Nummerreeksen:** per documentsoort een patroon (bijv. `F{year}-{nr:5}`) en het volgende nummer.
  PackDesk geeft nummers nooit dubbel uit en controleert de teller tegen de documenten die bestaan.
  Klopt iets niet (teller te laag, ontbrekende nummers), dan zie je een waarschuwing. *Teller op hoogste
  nummer + 1 zetten* lost het op; een handmatige correctie vraagt een reden en komt in het logboek.
  Wie tellers mag corrigeren, kan in het logboek (*Tellerwijzigingen*) de reden aanpassen of een regel
  weggooien (naar de prullenbak). *Volgend nummer ziet eruit als* toont de naam van de reeks met het
  volgende nummer volgens het patroon, en past zich aan terwijl je het patroon wijzigt.
  Ontbrekende nummers kun je verklaren (bijv. "geannuleerd").
  - *Bestandsnamen in archief* is alleen nodig als er pdf's uit een vorig systeem in de archiefmap
    staan. Het vertelt PackDesk hoe die bestanden heten, zodat het hun nummers kan lezen: om de teller te
    controleren en om oude facturen in te lezen. `(\d+)` staat voor het nummer; `invoice_(\d+)\.pdf`
    past bijvoorbeeld op `invoice_1030953.pdf`. Zonder archief laat je het leeg.
- **Externe databases:** de database van een ander systeem waarmee je wilt vergelijken of waaruit je
  wilt overnemen, zoals die van een vorige webshop. Je vult server, poort, databasenaam, gebruiker en
  wachtwoord in; het wachtwoord wordt versleuteld bewaard en niet meer getoond. *Verbinding testen*
  laat zien of het werkt. PackDesk leest alleen en verandert nooit iets in een externe database. Gebruik
  daarom ook op die server een gebruiker die alleen mag lezen.
- **Koppelingen:** per onderdeel van PackDesk (klanten, contactpersonen, logins, bestellingen,
  licenties, licentie-opties, facturen) vertel je waar het in de externe database staat: een tabel, of
  een SELECT-query voor gegevens uit meerdere tabellen. Daarna koppel je per veld een kolom. De pagina
  toont de tabellen en kolommen en de eerste rijen zoals PackDesk ze leest. Voor de vorige webshop is er
  een kant-en-klare koppeling (*Koppeling voor de vorige webshop laden*).
- **Importeren uit de vorige webshop** (bij de externe database: *Importeren*; recht *Mag gegevens importeren*):
  neemt alles over wat PackDesk kent: catalogus, klanten met adressen, contactpersonen met hun login
  (met hun eigen wachtwoord uit de vorige webshop), medewerkers met een passende rol, bestellingen, licenties
  met opties en verlengingen, facturen met betalingen, onderdelen (aanvragen met antwoorden, opmerkingen
  en geschiedenis, bestellingen met leveringen en correcties, gekoppeld aan hun facturen), printing
  services (als archief), telefonie (artikelen, instellingen en offertes) en de nummertellers.
  - Start eerst een **proefimport**: die doet alles en draait het daarna terug, zodat je het verslag
    kunt bekijken zonder dat er iets verandert. Daarna **importeren** (eerst een back-up maken).
  - Opnieuw importeren werkt bij wat eerder is overgenomen en maakt niets dubbel aan; er wordt niets
    verwijderd. Zo kun je nu testen en bij de echte overstap opnieuw importeren.
  - Het **verslag** (CSV) heeft één regel per rij van de oude database: nieuw, bijgewerkt, ongewijzigd of
    overgeslagen, met de reden. Het bevat persoonsgegevens; bewaar het zorgvuldig.
  - Wat bewust niet meekomt: contactpersonen en opties die in de vorige webshop verwijderd waren, een tweede
    login met een e-mailadres dat al gebruikt wordt (de contactpersoon komt wel mee), en de
    Acer-onderdelencatalogus uit 2009. Catalogusitems waar de oude gegevens naar verwijzen maar die niet
    meer bestonden, komen mee als "Onbekend (vorige webshop)".
  - Een nummer dat de vorige webshop meer dan eens gebruikte (licenties uit 2003–2004, één onderdelenbestelling),
    houdt bij de eerste zijn nummer; de volgende krijgen `dup2`, `dup3`, … erachter (bijv. `04NBH015dup2-1`),
    met een notitie bij de licentie.
- **Nieuw wachtwoord laten kiezen:** bij *Contactpersonen*, *Klanten* (voor alle contactpersonen van de
  geselecteerde klanten) en *Gebruikers* vink je mensen aan en kies je *… een nieuw wachtwoord laten
  kiezen*. Hun huidige wachtwoord werkt dan niet meer en ze krijgen een e-mail met een link. Is de link
  verlopen, dan werkt *Wachtwoord vergeten* gewoon. De kolom *Login* / *Wachtwoord* laat zien wie nog
  een nieuw wachtwoord moet kiezen.
- **Databases vergelijken:** zet de externe database en PackDesk naast elkaar, per onderdeel: hoeveel
  er alleen oud, alleen nieuw, verschillend en gelijk zijn. Klik door voor de lijst met verschillen per
  veld, of download die als CSV. Daarnaast de hoogste nummers tegenover de tellers van PackDesk, de
  factuur-pdf's in het archief, en een zoekveld dat in beide databases tegelijk zoekt.

## Het klantportaal

Ingelogde klanten zien *Mijn omgeving* met:

- **Servicepakketten bestellen:** pakketten kiezen met aantal en referentie, controleren (subtotaal,
  korting, btw, totaal) en bestellen. De licenties worden direct aangemaakt en de klant krijgt een
  orderbevestiging.
- **Mijn licenties:** status en einddatum, filters en zoeken. Licenties die binnenkort aflopen hebben
  een knop *Verlengen*; de nieuwe licentie sluit aan op de oude.
- **Licentie registreren** (`/registreren/`): een wizard van licentienummer via eindklant, reseller en
  apparaat naar opties en controle. Het servicecertificaat gaat per mail naar de eindklant.
- **Storing melden** (`/storing-melden/`): een licentie- of serienummer opzoeken vult apparaat en
  reseller in en laat zien of het apparaat onder contract valt; daarna de storing, de locatie en
  bijlagen. Melder en interne ontvangers krijgen een mail. Onder *Mijn storingsmeldingen* volgt de klant
  de afhandeling.
- **Mijn facturen:** bekijken, downloaden en naar zichzelf mailen, ook oude facturen.
- **Mijn gegevens:** bedrijfsgegevens en adressen bekijken, eigen contactgegevens en wachtwoord wijzigen.

## Talen

- Bezoekers kiezen hun taal rechtsboven op de website; de keuze wordt onthouden.
- In *Instellingen* kies je de standaardtaal en welke talen beschikbaar zijn. Met één taal verdwijnt de
  taalkeuze.
- Teksten die je zelf invult (homepage, mails, catalogus, ...) vul je per taal in via de tabbladen
  NL / EN / DE. Is een vertaling leeg, dan toont PackDesk de tekst in een andere taal.

## Oud factuurarchief inlezen

Komen er factuur-pdf's mee uit een vorig systeem en zijn die gekoppeld (zie [Installatie](installatie.md)),
dan registreert deze opdracht ze als facturen, zodat ze in het beheer en bij de klant te vinden zijn:

```bash
# Lees alle pdf's in de archiefmap uit en registreer ze als facturen.
docker compose exec web python manage.py import_invoice_archive
```

De originele pdf's blijven onveranderd. Opnieuw draaien slaat bestaande facturen over. Na het
importeren van de klanten koppelt `--relink` de facturen aan de juiste klant; `--fix-dates` vult
ontbrekende factuurdatums aan.
