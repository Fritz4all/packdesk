# Waar staat wat?

Overzicht van alle gegevens en instellingen van een PackDesk-installatie: waar ze staan, of ze buiten de
container blijven bestaan en of er een back-up van nodig is.

**Hoofdregel:** de containers zelf bevatten alleen programmacode. Alles wat van een klant is, staat
buiten de container: in de database of in een map op de server. Niets daarvan staat in Git.

## In één oogopslag

| # | Wat | Waar | Buiten de container? | In Git? | Back-up? |
|---|---|---|---|---|---|
| 1 | Alle bedrijfsgegevens en de meeste instellingen | eigen database van PackDesk (PostgreSQL of MariaDB/MySQL) | ja: de server in `DB_HOST`, of volume `dbdata` / `mariadbdata` | nee | **ja** |
| 2 | Uploads voor de website (logo, favicon, klantlogo's) | `MEDIA_ROOT` → `${DATA_DIR}/media` | ja | nee | **ja** |
| 3 | Privébestanden (factuur-pdf's, storingsbijlagen, wachtende imports) | `PRIVATE_MEDIA_ROOT` → `${DATA_DIR}/private` | ja | nee | **ja** |
| 4 | Oud factuurarchief (pdf's van de vorige webshop) | `DOCUMENT_ARCHIVE` → `/data/archive`, alleen-lezen | ja | nee | ja (eenmalig, verandert niet) |
| 5 | Serverinstellingen (geheime sleutel, databaseadres, mailserver, domein) | `.env` of omgevingsvariabelen | ja, op de server | nee (`.env` staat in `.gitignore`) | **ja** |
| 6 | Programmacode, vaste teksten en vertalingen | in de image (lokaal: de projectmap) | n.v.t. | ja | via Git |
| 7 | Keuzes van een bezoeker (taal, licht/donker) | browser van de bezoeker | n.v.t. | nee | nee |
| 8 | Logboek | uitvoer van de container (`docker compose logs`) | nee, verdwijnt met de container | nee | optioneel |

`DATA_DIR` staat standaard op `../packdesk-data`: naast de projectmap, niet erin.

## 1. Database (PostgreSQL of MariaDB/MySQL)

De databaseserver uit `.env` (`DB_ENGINE`, `DB_HOST`, …), of een databasecontainer met volume `dbdata`
(PostgreSQL) of `mariadbdata` (MariaDB). PackDesk heeft altijd een eigen database, ook op een server
waar de vorige webshop draait. Hier staat bijna alles.

**Klantgegevens**
- klanten, adressen, contactpersonen, klantsoorten, landen
- gebruikers (logins), met gehashte wachtwoorden
- licenties en licentie-opties, bestellingen en orderregels
- storingsmeldingen (de bijlagen zelf staan in map 3)
- facturen: nummer, bedragen, adres op dat moment, regels, verzendlog. Het pdf-bestand staat in map 3,
  en bij oude facturen alleen een verwijzing naar het archief (map 4).

**Catalogus**
- categorieën, hardwareklassen, merken, apparaattypes, soorten opties, looptijden, serviceniveaus,
  servicepacks met prijs en inkoopprijs, afhandelopties voor storingen

**Instellingen die je in het beheer aanpast** (elk één rij)

| Beheerpagina | Tabel/model |
|---|---|
| Instellingen (naam, logo-verwijzing, kleuren, talen, beheertaal, homepage, voettekst, bedrijfsgegevens, onderhoud) | `SiteSettings`, met `Address`, `HomeBlock`, `MenuItem` |
| Aanmeldinstellingen | `SignupSettings` |
| Licentie-instellingen | `LicenceSettings` |
| Storingsinstellingen | `FaultSettings` |
| Bestelinstellingen | `OrderSettings` |
| Factuurinstellingen | `InvoiceSettings` |
| Nummerreeksen (tellers, patronen) met correctielog en verklaringen van gaten | `NumberSequence`, `CounterChange`, `GapNote` |
| Rollen en rechten | Django-groepen en -rechten |
| Externe databases (zoals die van de vorige webshop): server, gebruiker, versleuteld wachtwoord | `ExternalDatabase` |
| Koppelingen: welke tabel en kolommen bij welk PackDesk-onderdeel en -veld horen | `TableMapping`, `FieldMapping` |
| Dashboardindeling en volgorde van het menu, per medewerker | `DashboardLayout` |
| Beheertaal per medewerker | veld op de gebruiker |

**Overig:** inlogsessies (Django-sessies) en de beheergeschiedenis (wie wat wanneer wijzigde).

Back-up:

```bash
docker compose exec postgres pg_dump -U packdesk packdesk > <bestand buiten Git>
# of, bij MariaDB:
docker compose exec mariadb mariadb-dump -u packdesk -p packdesk > <bestand buiten Git>
```

Bij een bestaande databaseserver maak je de back-up op die server zelf.

Het wachtwoord van een externe database is versleuteld met een sleutel die van `SECRET_KEY` is
afgeleid. Een kopie van de database alleen geeft het dus niet prijs. Na een andere `SECRET_KEY` vul je
het opnieuw in.

## 2. Uploads voor de website: `${DATA_DIR}/media`

Logo en favicon uit de instellingen, en logo's van klanten. Deze bestanden zijn via `/media/` op de
website te zien; zet hier dus niets vertrouwelijks.

## 3. Privébestanden: `${DATA_DIR}/private`

| Submap | Inhoud |
|---|---|
| `invoices/<jaar>/` | Factuur-pdf's die PackDesk zelf maakt, en kopieën van oude facturen die via een klantimport binnenkwamen |
| `faults/<id>/` | Bijlagen bij storingsmeldingen |
| `imports/` | Een geüpload importbestand dat op controle wacht. Wordt verwijderd na importeren of annuleren, en anders na een dag. |

Niet via de website bereikbaar. Alleen de eigen klant of een medewerker met het juiste recht kan een
bestand openen, en dan altijd via PackDesk.

## 4. Oud factuurarchief: `DOCUMENT_ARCHIVE`

De pdf's van de vorige webshop (13.456 facturen, 5,3 GB). PackDesk leest ze alleen; ze worden nooit
gewijzigd. In de database staat per factuur alleen de bestandsnaam, en PackDesk opent alleen bestanden
binnen deze map.

## 5. Serverinstellingen: `.env` / omgevingsvariabelen

Instellingen die per server verschillen of geheim zijn. Ze staan niet in het beheer en niet in Git; zie
`.env.example` voor de lijst.

| Variabele | Waarvoor |
|---|---|
| `SECRET_KEY` | ondertekening van sessies en links; geheim |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | eigen database van PackDesk: type, server en login; wachtwoord geheim |
| `DB_ROOT_PASSWORD`, `COMPOSE_PROFILES` | alleen voor een databasecontainer van docker-compose |
| `DATABASE_URL` | alternatief voor de `DB_*`-regels, in één adres |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | domeinnaam van de shop |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_BACKEND` | mailserver |
| `SECURE_COOKIES`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` | HTTPS |
| `DATA_DIR` | map op de server voor 2 en 3 (docker-compose) |
| `MEDIA_ROOT`, `PRIVATE_MEDIA_ROOT` | dezelfde mappen, gezien vanuit de container |
| `DOCUMENT_ARCHIVE` / `DOCUMENT_ARCHIVE_DIR` | archiefmap op de server / in de container |
| `FALLBACK_LANGUAGES`, `LOG_LEVEL`, `DEBUG` | gedrag |

## 6. Code: Git en de image

Programmacode, sjablonen, opmaak, vaste teksten en hun vertalingen (`locale/`), de standaardrollen
voor een nieuwe installatie, en de keuze van beschikbare talen (`LANGUAGES` in `packdesk/settings.py`).
De container bevat daarnaast de Python-pakketten en de verzamelde statische bestanden. Een container
kan altijd worden weggegooid en opnieuw gebouwd.

## 7. Browser van de bezoeker

- cookie `packdesk_language`: gekozen taal van de website
- `localStorage` `packdesk-theme`: licht, donker of automatisch
- `localStorage` `packdesk-nav-<sectie>`: welke menusecties in het beheer open of dicht staan
- sessie- en CSRF-cookie: ingelogd blijven en formulieren beveiligen

## Lokaal ontwikkelen

| Wat | Waar |
|---|---|
| Database | Docker-volume `packdesk_dbdata` (PostgreSQL) of `packdesk_mariadbdata` (MariaDB) |
| Media en privébestanden | `../packdesk-data/media` en `../packdesk-data/private` |
| Factuurarchief | `DOCUMENT_ARCHIVE` in `.env`; lokaal een kopie in `Source/extra/data/invoices` |
| Verstuurde mails | Mailpit, alleen in het geheugen (http://localhost:8025) |
