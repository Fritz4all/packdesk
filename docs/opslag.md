# Waar staat wat?

Overzicht van alle gegevens en instellingen van een PackDesk-installatie: waar ze staan, of ze buiten de
container blijven bestaan en of er een back-up van nodig is.

**Hoofdregel:** de containers zelf bevatten alleen programmacode. Alles wat van een klant is, staat
buiten de container: in de database of in een map op de server. Niets daarvan staat in Git.

## In één oogopslag

| # | Wat | Waar | Buiten de container? | In Git? | Back-up? |
|---|---|---|---|---|---|
| 1 | Alle bedrijfsgegevens en de meeste instellingen | eigen database van PackDesk (PostgreSQL of MariaDB/MySQL) | ja: de server in `DB_HOST`, of volume `dbdata` / `mariadbdata` | nee | **ja** |
| 2 | Bestanden van PackDesk: website-uploads, factuur-pdf's, storingsbijlagen, wachtende imports | `${DATA_DIR}` op de server, in de container `/data` (`DATA_ROOT`) | ja | nee | **ja** |
| 3 | Oud factuurarchief (pdf's van de vorige webshop), alleen als je het opgeeft | `DOCUMENT_ARCHIVE` op de server, in de container `/data-sources/archive-invoices`, alleen-lezen | ja | nee | ja (eenmalig, verandert niet) |
| 5 | Serverinstellingen (geheime sleutel, database) | `packdesk.env` in de datamap (gemaakt door de wizard), of `.env` / omgevingsvariabelen | ja, op de server | nee | **ja** |
| 6 | Programmacode, vaste teksten en vertalingen | in de image (lokaal: de projectmap) | n.v.t. | ja | via Git |
| 7 | Keuzes van een bezoeker (taal, licht/donker) | browser van de bezoeker | n.v.t. | nee | nee |
| 8 | Logboek | uitvoer van de container (`docker compose logs`) | nee, verdwijnt met de container | nee | optioneel |

`DATA_DIR` staat standaard op `../packdesk-data`: naast de projectmap, niet erin.

## 1. Database (PostgreSQL of MariaDB/MySQL)

De databasecontainer van `docker-compose.yml` (volume `postgres-data`) of `docker-compose.mariadb.yml`
(volume `mariadb-data`), of een bestaande databaseserver. PackDesk heeft altijd een eigen database, ook
op een server waar andere databases staan. Hier staat bijna alles, ook de mailserver en de domeinnaam
uit *Instellingen* (het wachtwoord van de mailserver versleuteld).

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

## 2. Bestanden van PackDesk: `${DATA_DIR}` → `/data`

Eén map op de server, in de container `/data` (`DATA_ROOT`), met een submap per doel. De submappen
worden aangemaakt zodra ze nodig zijn.

| Submap | Inhoud | Via de website te zien? |
|---|---|---|
| `website/` | Logo en favicon uit de instellingen, logo's van klanten | ja, via `/media/`; zet hier niets vertrouwelijks |
| `invoices/<jaar>/` | Factuur-pdf's die PackDesk maakt, en kopieën van oude facturen die via een klantimport binnenkwamen | nee |
| `fault-attachments/<id>/` | Bijlagen bij storingsmeldingen | nee |
| `imports/` | Een geüpload importbestand dat op controle wacht; verwijderd na importeren of annuleren, anders na een dag | nee |
| `packdesk.env` | Serverinstellingen uit de installatiewizard (geheime sleutel, eventueel de database) | nee |
| `setup-code.txt` | De installatiecode zolang die nodig is; verdwijnt na gebruik | nee |

Wat niet via de website te zien is, opent alleen de eigen klant of een medewerker met het juiste
recht, en altijd via PackDesk.

## 3. Oud factuurarchief (optioneel): `DOCUMENT_ARCHIVE` → `/data-sources/archive-invoices`

Alleen voor een installatie die de vorige webshop overneemt: de pdf's van de vorige webshop (13.456 facturen,
5,3 GB). De map staat los van `/data` en wordt alleen-lezen gekoppeld, via een
`docker-compose.override.yml` (staat niet in Git; compose leest dat bestand vanzelf):

```yaml
services:
  web:
    volumes:
      - ${DOCUMENT_ARCHIVE}:/data-sources/archive-invoices:ro
```

met `DOCUMENT_ARCHIVE=<map>` in `.env`. Zonder deze koppeling is er geen archief en werkt de rest
gewoon. PackDesk leest de pdf's alleen en wijzigt ze nooit. In de database staat per factuur alleen
de bestandsnaam, en PackDesk opent alleen bestanden binnen deze map.

## 5. Serverinstellingen: `packdesk.env`, `.env` en omgevingsvariabelen

Instellingen die PackDesk nodig heeft om te kunnen starten. Ze staan niet in Git. Waar ze vandaan
komen, in deze volgorde:

1. omgevingsvariabelen (bijv. uit het compose-bestand);
2. `.env` in de map van PackDesk (optioneel, zie `.env.example`);
3. `packdesk.env` in de datamap: daar bewaart de installatiewizard de geheime sleutel en, bij een
   bestaande databaseserver, de database-gegevens. Alleen leesbaar voor PackDesk.

| Variabele | Waarvoor |
|---|---|
| `SECRET_KEY` | ondertekening van sessies en links, en versleuteling van opgeslagen wachtwoorden; maakt PackDesk zelf aan als hij ontbreekt |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | de eigen database van PackDesk |
| `SETUP_CODE` | eigen installatiecode in plaats van een willekeurige |
| `PORT`, `DATA_DIR` | poort en datamap op de server (docker-compose) |
| `EMAIL_HOST`, `EMAIL_PORT`, … | mailserver; zonder deze regels geldt de mailserver uit het beheer |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SECURE_*` | domein en HTTPS; zonder `ALLOWED_HOSTS` geldt de domeinnaam uit het beheer |
| `DOCUMENT_ARCHIVE` / `DOCUMENT_ARCHIVE_DIR` | optioneel: archiefmap op de server / in de container |
| `RUN_MIGRATIONS`, `FALLBACK_LANGUAGES`, `LOG_LEVEL`, `DEBUG` | gedrag |

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
| Database (ontwikkelen) | Docker-volume `packdesk_dbdata` (PostgreSQL) of `packdesk_mariadbdata` (MariaDB) |
| Bestanden van PackDesk | `../packdesk-data/` met `website/`, `invoices/`, `fault-attachments/`, `imports/` |
| Factuurarchief (optioneel) | `DOCUMENT_ARCHIVE` in `.env`, gekoppeld via `docker-compose.override.yml` |
| Verstuurde mails | Mailpit, alleen in het geheugen (http://localhost:8025) |
