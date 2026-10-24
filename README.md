# PackDesk

Webshop voor ICT-supportpakketten, licenties, bestellingen en facturen.
Functioneel gebaseerd op de previous-webshop-shop, maar volledig beheerbaar via een admin-omgeving.
Herbruikbaar voor meerdere klanten: elke klant krijgt een eigen installatie (on-site), en naam,
logo, kleuren, bedrijfsgegevens en talen stel je in via de admin. Beschikbaar in het Nederlands, Engels en Duits.

Status: in opbouw. Zie [docs/plan.md](docs/plan.md).

## Techniek

Python 3.13, Django 5.2 LTS, PostgreSQL 17, admin met django-unfold, Docker.

## Hoe het werkt

- **Eén installatie per klant.** Alles wat per klant verschilt staat op de pagina **Instellingen** in de
  admin: naam, logo, favicon, kleuren, slogan, introductietekst, bedrijfsgegevens (KvK, btw, IBAN)
  en talen. Er staat niets klantspecifieks in de code.
- **Adressen:** onder het tabblad *Adressen* voeg je een of meer adressen toe (bezoekadres, postadres,
  factuuradres, ...). Per adres vink je aan waar het gebruikt wordt: website, facturen, offertes,
  orderbevestigingen, e-mails of afzender op labels. Elk gebruik kan bij maar één adres aan staan;
  wat nergens is aangevinkt, valt terug op het eerste adres. Per adres kun je een eigen telefoonnummer
  en e-mailadres opgeven (bijv. de administratie op facturen).
- **Licht, donker of auto:** in de instellingen kies je de standaardweergave (auto volgt het apparaat)
  en of bezoekers zelf mogen kiezen. Hun keuze wordt in de browser onthouden. De merkkleur wordt in
  elke weergave automatisch iets lichter of donkerder gemaakt, zodat links leesbaar blijven.
  De admin heeft een eigen keuze voor licht/donker/systeem.
- **Inhoud van de site:** homepageblokken (pictogram, titel, tekst, link, zichtbaar voor iedereen /
  gasten / ingelogde klanten), menu-items in de kopregel, knoptekst op de homepage, omschrijving voor
  zoekmachines en de voettekst (wat er getoond wordt en eigen tekst). Alles per taal.
- **Onderhoudsmodus:** zet je hem aan, dan zien bezoekers een onderhoudspagina (HTTP 503) met je eigen
  melding en eventueel een verwachte eindtijd, en kunnen klanten niet inloggen. Medewerkers kunnen het
  beheer en de site gewoon blijven gebruiken. Daarnaast is er een **meldingsbalk** bovenaan elke pagina,
  bijvoorbeeld om onderhoud vooraf aan te kondigen.
- **Nummerreeksen** (Configuratie → Nummerreeksen): per documentsoort (facturen, offertes, orders,
  licenties, klanten, storingsmeldingen) een patroon, bijv. `F{year}-{nr:5}`, en de volgende
  nummer. Nummers worden veilig uitgegeven (nooit dubbel, nooit hergebruikt).
  - **Controle tegen documenten:** PackDesk vergelijkt de teller met de documenten die echt bestaan
    (nu: de pdf's in `DOCUMENT_ARCHIVE_DIR`; straks ook de facturen in PackDesk zelf). Het toont het
    aantal documenten, het hoogste nummer, en **ontbrekende nummers**. Is de teller te laag, of zijn
    er nummers weg, dan verschijnt een waarschuwing en een teller in het admin-menu.
  - **Rechtzetten:** knop *Teller op hoogste nummer + 1 zetten*, of handmatig een nieuw volgende nummer
    met verplichte reden. De teller kan nooit lager dan een nummer dat al bestaat. Elke correctie komt
    in het logboek (wie, wanneer, oud → nieuw, reden).
  - **Gaten verklaren:** ontbrekende nummers kun je verklaren (bijv. "geannuleerd voor verzending");
    verklaarde gaten tellen niet meer als probleem.
  - Alleen de rollen Beheerder en Financieel mogen tellers corrigeren.
- **Klanten** (Klanten → Klanten): bedrijfsgegevens, klanttype, status (wacht op goedkeuring / actief /
  geblokkeerd), klantnummer (automatisch uit de nummerreeks *Klanten* bij goedkeuring, of handmatig),
  aparte e-mailadressen voor bestellingen, onderdelen en facturen, marges, hoofd-, factuur- en
  afleveradres, en contactpersonen met of zonder login.
  - Knoppen: *Goedkeuren* (klantnummer, logins actief, activeringsmail), *Blokkeren* (logins uit) en
    *Login sturen naar contactpersonen zonder login* (uitnodiging met link om een wachtwoord te kiezen).
  - Klanttypes en landen (met "btw-nummer verplicht") zijn zelf te beheren, in drie talen.
- **Aanmeldformulier** (`/aanmelden/`, link op de inlogpagina): bedrijven melden zich zelf aan. Onder
  *Klantinstellingen* stel je in: aan/uit, titel en teksten, klanttype, of goedkeuring nodig is, wie een
  melding krijgt, de activeringsmail, standaardmarges, en **per veld verborgen / optioneel / verplicht**.
  Bescherming tegen spam met een onzichtbaar veld en een minimale invultijd.
- **Klantportaal:** *Mijn gegevens* (bedrijfsgegevens en adressen bekijken, eigen contactgegevens
  wijzigen), wachtwoord wijzigen en *wachtwoord vergeten*.
- **Servicepacks en licenties** (menu *Servicepacks en licenties*):
  - Catalogus: packcategorieën, hardwareklassen, merken (met optionele controle van het artikelnummer),
    apparaattypes per merk en klasse, optietypes (intern / extern / beeldscherm), looptijden (ook "na
    garantie"), serviceniveaus en servicepacks met prijs, maximaal aantal interne/externe opties,
    beeldscherm ja/nee en registratie verplicht ja/nee. Alles in drie talen.
  - Licenties: aanmaken per klant en pack (meerdere tegelijk), nummer uit de nummerreeks *Licenties*
    (standaard het oude formaat `26A0001` + drie willekeurige letters + `-1`), status niet
    geregistreerd / geregistreerd / afgelopen, zoeken op nummer, serienummer, klant of referentie.
  - Licentie-instellingen: registratietermijnen (standaard 1920 dagen na aanschaf, 40 dagen vooruit,
    95 dagen vooruit na garantie), aantal letters en verboden lettercombinaties, interne ontvangers van
    registraties en de teksten van de wizard.
- **Registratiewizard** (`/registreren/`, ook gelinkt vanaf de homepage): licentienummer → eindklant →
  reseller (alleen als de klant geen reseller is) → apparaat (merk/type, artikel- en serienummer,
  aanschaf- of ingangsdatum) → beeldscherm (als het pack dat heeft) → opties (binnen de maxima) →
  controle → klaar. Pas bij de laatste stap wordt opgeslagen. De einddatum volgt de regels van de oude
  shop; opties krijgen serienummer `<serienummer>/001`, `/002`, ... Het servicecertificaat gaat per
  e-mail naar de eindklant, met interne ontvangers in bcc. Categorieën kunnen ook op "registreren via
  contact" staan.
- **Storing melden** (`/storing-melden/`, ook op de homepage en in het klantportaal): optioneel een
  licentie- of serienummer opzoeken (ook serienummers van opties); het apparaat en de reseller worden
  ingevuld en je ziet direct of het onder contract valt. Daarna storing, gewenste afhandeling,
  gegevens van melder en locatie, en bijlagen (aantal en grootte instelbaar). Elke melding krijgt een
  nummer uit de nummerreeks *Storingsmeldingen*, gaat per mail (met bijlagen) naar de ingestelde
  ontvangers en de melder krijgt een bevestiging. Bijlagen staan in `PRIVATE_MEDIA_ROOT` en zijn alleen
  via het beheer te downloaden. In het beheer: status nieuw / in behandeling / afgesloten, interne
  notities, dekking, en een teller in het menu. Klanten zien hun meldingen onder *Mijn storingsmeldingen*.
- **Democatalogus:** `docker compose exec web python manage.py load_demo_catalogue` maakt een kleine
  catalogus en testlicenties aan om de wizard te proberen (alleen als er nog geen packs zijn).
- **Dashboard** (beheer-startpagina): totalen (actieve klanten, te keuren aanmeldingen, licenties, nog
  niet geregistreerd, aflopend binnen 90 dagen, nummerreeksen met problemen) en lijsten. Elke beheerder
  kan via *Aanpassen* blokken verslepen en verbergen; *Standaard herstellen* zet alles terug. Blokken
  volgen de rechten van de rol.
- **Verkoop en marge** (`/beheer/rapportage/`, recht *Mag verkooprapportage bekijken*): omzet, brutomarge
  en margepercentage, grafiek per maand, omzet per categorie, beste klanten en een prijslijst met
  inkoopprijs en marge per pack. Zolang bestellingen en facturen nog niet in PackDesk staan, telt elke
  licentie als verkocht pack tegen de huidige prijs min de korting van de klant (dat staat op de pagina).
- **Zoeken (Ctrl/Cmd+K):** doorzoekt alle lijsten waar je rechten voor hebt, met hun zoekvelden:
  licentienummers (ook een deel), serienummers van apparaten en opties, klanten (naam, nummer, btw, KvK,
  adres, contactpersonen), gebruikers, packs, enz.
- **Inloggen** met e-mailadres.
- **Admin** op `/beheer/`.
- **Rollen en rechten** (Gebruikers → Rollen): maak zelf rollen aan en vink per onderdeel aan wat
  een rol mag (bekijken, toevoegen, wijzigen, verwijderen, plus speciale rechten zoals *nummertellers
  corrigeren*). Elke medewerker (admin-gebruiker) heeft verplicht één rol; die rol bepaalt wat hij in
  het beheer ziet en kan. Klanten hebben geen rol en geen toegang tot het beheer.
  - Je kunt alleen rechten en rollen toekennen die je zelf hebt; rechten die je niet ziet, blijven bij
    het bewerken van een rol behouden.
  - Een rol die nog gebruikers heeft, kan niet worden verwijderd.
  - Een nieuwe installatie krijgt vier standaardrollen (Beheerder, Financieel, Service, Medewerker,
    `apps/accounts/roles.py`); daarna worden ze nooit meer automatisch aangepast.
  - Een superuser kan alles. Nieuwe modules voegen hun app toe aan `MANAGED_APPS` in
    `apps/accounts/permissions.py`, zodat hun functies in de roleditor verschijnen.

## Lokaal ontwikkelen

Vereist: Docker met Compose v2.

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py create_user --email admin@example.test --superuser
```

- Shop: http://localhost:8000
- Admin: http://localhost:8000/beheer/ → **Instellingen** voor naam, logo en kleuren
- Mailpit (verstuurde mails): http://localhost:8025

Bestaande documenten (bijv. het factuurarchief van de vorige webshop) koppel je alleen-lezen met
`DOCUMENT_ARCHIVE=<map>` in een lokaal `.env`-bestand.

## Testen

```bash
docker compose exec web python -m pytest
```

GitHub Actions draait bij elke push de tests tegen PostgreSQL en bouwt de productie-image.

## Talen

PackDesk is volledig beschikbaar in het **Nederlands, Engels en Duits**.

- **Bezoekers** kiezen hun taal rechtsboven; de keuze wordt in een cookie onthouden.
- **In de instellingen** kies je de standaardtaal en welke talen beschikbaar zijn.
  Met één taal verdwijnt de taalkeuze.
- **Inhoud** die per klant verschilt (nu: slogan en introductietekst; later ook producten, mails, enz.)
  vul je per taal in via tabbladen NL / EN / DE. Is een vertaling leeg, dan wordt de volgende taal
  uit `FALLBACK_LANGUAGES` getoond (standaard `nl,en,de`).
- **Vaste teksten** staan in de code in het Engels, met vertalingen in
  `locale/nl/` en `locale/de/`. Teksten van het admin-thema (django-unfold) die Django zelf niet
  vertaalt, staan in `locale_vendor/`.
- Een test controleert dat alle Nederlandse en Duitse vertalingen compleet zijn.

```bash
docker compose exec web python manage.py makemessages -l nl -l de --ignore=venv --ignore=staticfiles --ignore=tests --no-obsolete
docker compose exec web python manage.py compilemessages --ignore=/venv
```

Een taal toevoegen: zet hem in `LANGUAGES` in `packdesk/settings.py`, draai `makemessages -l <code>`,
vertaal de `.po`-bestanden in `locale/` en `locale_vendor/`, en maak een migratie
(`makemigrations`) voor de extra inhoudsvelden.

## Productie-image

```bash
docker build -t packdesk:<versie> .
```

- Draait als non-root gebruiker `app` met gunicorn op poort 8000.
- Configuratie via environment-variabelen, zie [.env.example](.env.example).
- Migraties draaien alleen met `RUN_MIGRATIONS=1`, zodat een nieuwe image de database niet ongemerkt wijzigt.
- Geüploade bestanden in `/data/media` (volume).

Een productie-`docker-compose.yml` volgt in stap E van het plan.

## Documentatie

- [docs/plan.md](docs/plan.md) – opbouwplan
- [docs/vorige-webshop/](docs/vorige-webshop/) – analyse en functioneel ontwerp van de oude previous-webshop-shop
