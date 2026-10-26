# Installatie

Hoe je PackDesk neerzet voor een bedrijf: kiezen welke database, starten, de installatiewizard,
back-ups en updates.

## Wat er draait

| Onderdeel | Wat het doet |
|---|---|
| **PackDesk** (container `web`) | de website en het beheer |
| **Database** | alle gegevens: klanten, licenties, bestellingen, facturen, instellingen, gebruikers |
| **Datamap** | bestanden die PackDesk bewaart: logo's, factuur-pdf's, bijlagen, en de instellingen uit de wizard |

De database en de datamap staan altijd buiten de PackDesk-container. Een container kun je dus
weggooien en vervangen door een nieuwe versie zonder dat er iets verloren gaat.

## 1. Kies een variant

Er zijn drie kant-en-klare startbestanden. Kies er één:

| Bestand | Database | Starten met |
|---|---|---|
| `docker-compose.yml` | eigen **PostgreSQL**, draait mee | `docker compose up -d` |
| `docker-compose.mariadb.yml` | eigen **MariaDB**, draait mee | `docker compose -f docker-compose.mariadb.yml up -d` |
| `docker-compose.external-db.yml` | een **bestaande databaseserver** (MariaDB, MySQL of PostgreSQL) | `docker compose -f docker-compose.external-db.yml up -d` |

Bij `docker-compose.mariadb.yml` draait ook **phpMyAdmin** mee, om in de database te kijken:
`http://<server>:8081`, inloggen als `packdesk` met het `DB_PASSWORD` uit `.env` (standaard
`packdesk-internal`). phpMyAdmin is alleen vanaf de server zelf bereikbaar. Vanaf een andere computer:
`ssh -L 8081:localhost:8081 <server>` en dan `http://localhost:8081`; of zet op een vertrouwd netwerk
`PHPMYADMIN_ADDRESS=0.0.0.0` in `.env` (andere poort: `PHPMYADMIN_PORT=`).

Twijfel je, kies dan de eerste. De database draait dan in een eigen container en is alleen bereikbaar
voor PackDesk.

Bij een andere variant dan de eerste zet je in de opdrachten hieronder steeds `-f <bestand>` achter
`docker compose`.

## 2. Starten

```bash
# Haal PackDesk binnen en ga naar de map.
git clone https://github.com/Fritz4all/packdesk.git
cd packdesk

# Bouw en start PackDesk (en de database van je variant) op de achtergrond. De eerste keer duurt dit
# een paar minuten. Een nieuwe, lege database krijgt vanzelf zijn tabellen.
docker compose up -d

# Toon de installatiecode die de wizard vraagt.
docker compose logs web | grep "Installation code"
```

Een `.env`-bestand is niet nodig. Wie liever vooraf instelt, kopieert `.env.example` naar `.env`:
wat daar staat, gaat altijd vóór wat de wizard vraagt.

Standaard luistert PackDesk op poort 8000 en staan de bestanden in `../packdesk-data` (naast de map
van PackDesk). Anders? Zet `PORT=` of `DATA_DIR=` in `.env`.

## 3. De installatiewizard

Open `http://<server>:8000` in de browser. Zolang de installatie niet klaar is, opent vanzelf de
wizard. Met `docker-compose.external-db.yml` komt eerst de stap **Database**:

- Vul de databaseserver in (IP-adres of naam, poort, databasenaam, gebruiker en wachtwoord voor
  PackDesk). Staat de databaseserver op dezelfde computer, gebruik dan `host.docker.internal`.
- **Bestaat de database nog niet?** Vink aan dat PackDesk hem aanmaakt en vul een beheerderslogin van
  de databaseserver in (bijv. `root` of `postgres`). Die wordt één keer gebruikt en nooit opgeslagen.
  PackDesk maakt dan de database en een eigen gebruiker met rechten op alleen die database.
- Mag de beheerder niet op afstand inloggen, dan vraag je de beheerder van de databaseserver om een
  lege database en gebruiker aan te maken, bijvoorbeeld voor MariaDB:

  ```sql
  CREATE DATABASE packdesk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
  CREATE USER 'packdesk'@'%' IDENTIFIED BY '<wachtwoord>';
  GRANT ALL ON packdesk.* TO 'packdesk'@'%';
  ```

- PackDesk test de verbinding, slaat de gegevens op en start zichzelf opnieuw.

Daarna, voor alle varianten:

1. **Installatiecode:** bewijst dat jij de server beheert (zie hieronder).
2. **Eerste beheerder:** e-mailadres en wachtwoord van het account dat alles mag.
3. **Basisinstellingen:** naam, domeinnaam, talen, beheertaal, algemeen e-mailadres en logo.
4. **Mailserver:** de server waarmee PackDesk mail verstuurt, met een testmail. Niet bij de hand? Kies
   *Overslaan, later instellen* en vul hem later in onder *Instellingen → Mailserver*.
5. **Nummering:** het eerste nummer voor klanten, bestellingen, licenties en facturen.
6. **Democatalogus** (optioneel, alleen om te oefenen).

Daarna sluit de wizard voorgoed en kom je in het beheer. Alles uit de wizard is later aan te passen
onder *Instellingen* en *Nummerreeksen*.

**Waarom een installatiecode?** Een nieuwe installatie heeft nog geen beheerder. Zonder code kan de
eerste bezoeker die de site vindt zichzelf beheerder maken. De code staat alleen in het logboek van de
server (`docker compose logs web`), of je kiest hem zelf als `SETUP_CODE` in `.env`. Een code die
PackDesk zelf maakt, verdwijnt na gebruik.

## 4. Verder inrichten

In het beheer (`/beheer/`):

1. **Instellingen:** kleuren, adressen, homepage, bedrijfsgegevens (KvK, btw, IBAN).
2. **Catalogus:** categorieën, merken, apparaattypes en servicepakketten met prijzen.
3. **Medewerkers:** toevoegen en een rol geven. De standaardrollen staan al klaar.

Komt het bedrijf over van een ander systeem? Zie *Externe databases* in de [handleiding](handleiding.md).

## 5. Op internet

- Zet een webserver of reverse proxy voor PackDesk die HTTPS regelt (bijv. Caddy, nginx of Traefik).
  Zet dan in `.env`: `SECURE_COOKIES=1`, `SECURE_SSL_REDIRECT=1` en `CSRF_TRUSTED_ORIGINS=https://<domein>`.
- Vul in *Instellingen → Algemeen* de **domeinnaam** in. De website antwoordt dan alleen op die naam
  (en op `localhost`), niet op elke naam of elk IP-adres.
- Doe de installatiewizard bij voorkeur via HTTPS of op het eigen netwerk; je vult er wachtwoorden in.

## 6. Een map uit een ander systeem koppelen (optioneel)

Neemt het bedrijf factuur-pdf's mee uit een vorig systeem, koppel die map dan alleen-lezen. Maak naast
het startbestand een `docker-compose.override.yml`:

```yaml
services:
  web:
    volumes:
      - ${DOCUMENT_ARCHIVE}:/data-sources/archive-invoices:ro
    environment:
      DOCUMENT_ARCHIVE_DIR: /data-sources/archive-invoices
```

en zet `DOCUMENT_ARCHIVE=<map met de pdf's>` in `.env`. Docker Compose leest het override-bestand
vanzelf bij `docker-compose.yml`; bij de andere varianten geef je het mee:
`docker compose -f docker-compose.mariadb.yml -f docker-compose.override.yml up -d`.

## 7. Back-ups

Maak regelmatig een back-up van:

1. **de database**, bijvoorbeeld
   `docker compose exec db pg_dump -U packdesk packdesk > packdesk.sql` (PostgreSQL) of
   `docker compose -f docker-compose.mariadb.yml exec db mariadb-dump -u packdesk -p packdesk > packdesk.sql`
   (MariaDB). Bij een bestaande databaseserver: met de back-up van die server.
2. **de datamap** (standaard `../packdesk-data`). Daar staan ook de instellingen uit de wizard, met
   wachtwoorden: bewaar de back-up veilig.
3. **`.env`**, als je die gebruikt.

## 8. Bijwerken naar een nieuwe versie

```bash
# 1. Maak eerst een back-up (zie hierboven).
# 2. Haal de nieuwe versie op.
git pull
# 3. Bouw en start de nieuwe versie; database en datamap blijven staan.
docker compose up -d --build
```

Heeft de nieuwe versie wijzigingen voor de database, dan tonen website en beheer de pagina
**Database bijwerken**. Vul de installatiecode in (`docker compose logs web | grep "Installation code"`,
of de `SETUP_CODE` uit `.env`), bevestig dat je een back-up hebt gemaakt en klik op
*Database bijwerken*. Daarna werkt alles weer.

## Problemen bij de installatie

- **"De databaseserver weigert de gebruikersnaam of het wachtwoord"** terwijl gebruiker en wachtwoord in
  het startbestand of `.env` staan: dan moet `DB_PASSWORD` van `web` gelijk zijn aan het wachtwoord van de
  databasegebruiker (bij de meegeleverde MariaDB: `MARIADB_PASSWORD`). Laat beide op `${DB_PASSWORD}` staan.
  MariaDB gebruikt `MARIADB_PASSWORD` alleen bij de allereerste start, als de data wordt aangemaakt; later
  aanpassen verandert het wachtwoord niet. Bij een nieuwe, lege installatie: `docker compose down -v`
  (verwijdert de database!) en opnieuw starten. Anders het wachtwoord in MariaDB zelf aanpassen.
- **Database aanmaken lukt niet:** vul bij *Database aanmaken* een echte beheerder van de databaseserver
  in (bijv. `root`) met wachtwoord. Bij de MariaDB-container is dat het `MARIADB_ROOT_PASSWORD`.
- **"WORKER TIMEOUT" in het logboek:** kwam voor bij oudere versies als een browser een verbinding vooraf
  opende en open liet staan; onschuldig. Nieuwe versies hebben er geen last van.

## Zonder browser installeren

Voor een geautomatiseerde installatie kan alles ook zonder wizard: zet de database en de mailserver in
`.env` en maak de eerste beheerder met
`docker compose exec web python manage.py create_user --email <e-mailadres> --superuser`
(het wachtwoord wordt gevraagd; in een script geef je het mee met `-e PACKDESK_PASSWORD=…`).
Daarmee is de installatie afgerond en opent de wizard niet meer. Wijzigingen van een nieuwe versie
voert PackDesk bij het starten zelf door als je `RUN_MIGRATIONS=1` in `.env` zet.
