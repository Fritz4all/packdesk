# Ontwikkelen

Voor wie aan PackDesk zelf werkt.

## Techniek

| Onderdeel | Keuze |
|---|---|
| Taal en framework | Python 3.13, Django 5.2 (LTS, ondersteund tot april 2028) |
| Database | PostgreSQL 17 of MariaDB 10.6+ / MySQL |
| Beheer | Django-admin met het thema django-unfold |
| Inhoud in meerdere talen | django-modeltranslation (een kolom per taal) |
| Pdf maken / lezen | WeasyPrint / poppler (`pdftotext`) |
| Draaien | Docker; gunicorn en WhiteNoise in de productie-image |
| Testen | pytest, op PostgreSQL én MariaDB via GitHub Actions |

Afspraak: alles onder water is Engels (code, commentaar, map-, bestands- en instellingsnamen). De
documentatie en de teksten op het scherm zijn Nederlands, met vertalingen in het Engels en Duits.

## Indeling van de code

| Map | Inhoud |
|---|---|
| `packdesk/` | instellingen (`settings.py`) en URL's |
| `apps/siteconfig/` | instellingen per installatie, adressen, homepage, menu, onderhoudsmodus, beheertaal |
| `apps/accounts/` | gebruikers, rollen en rechten, inloggen |
| `apps/numbering/` | nummerreeksen en de controle daarvan |
| `apps/customers/` | klanten, aanmelden, export en import |
| `apps/licences/` | catalogus, licenties, registratiewizard |
| `apps/faults/` | storingsmeldingen |
| `apps/orders/` | bestellen en verlengen |
| `apps/invoices/` | facturen, pdf's, oud factuurarchief |
| `apps/dashboard/` | dashboard, rapportage, zoeken, menu |
| `apps/legacy/` | externe databases, koppelingen, vergelijken |
| `apps/core/` | gedeelde hulpmiddelen (bestandsopslag, knoppen in het beheer) |
| `templates/`, `static/` | pagina's, opmaak en scripts |
| `locale/` | vertalingen; `locale_vendor/` voor teksten van het beheerthema |
| `tests/` | alle tests |

## Lokaal draaien

Gebruik `docker-compose.dev.yml`: PackDesk in foutopsporingsmodus met de code als gekoppelde map,
zodat wijzigingen direct zichtbaar zijn, plus een testmailbox op http://localhost:8025. Zet in `.env`:

```bash
COMPOSE_FILE=docker-compose.dev.yml
COMPOSE_PROFILES=postgres
DB_ENGINE=postgres
DB_HOST=postgres
DB_PASSWORD=<zelfgekozen>
```

Daarna werkt gewoon `docker compose up -d`. De andere compose-bestanden zijn voor echte installaties
(zie [Installatie](installatie.md)).

Met `COMPOSE_PROFILES=mariadb` (en `DB_ENGINE=mariadb`, `DB_HOST=mariadb`, `DB_ROOT_PASSWORD=…`) draait
PackDesk op MariaDB en start er ook **phpMyAdmin** mee op http://localhost:8081, om de databases op die
server in te zien. Log in met `root` en `DB_ROOT_PASSWORD`, of maak een gebruiker die alleen mag lezen:
`GRANT SELECT, SHOW VIEW ON *.* TO viewer@'%'`.

Handige opdrachten:

| Opdracht | Doet |
|---|---|
| `python manage.py setup_database` | draait bij elke start: maakt de tabellen van een lege database aan en meldt wachtende databasewijzigingen en de installatiecode |
| `python manage.py create_user --email <adres> --superuser` | beheerder aanmaken zonder de wizard |
| `python manage.py load_demo_catalogue` | kleine democatalogus met testlicenties |
| `python manage.py import_invoice_archive` | factuur-pdf's uit het archief registreren (`--relink`, `--fix-dates`) |

(Voer ze uit met `docker compose exec web …`.)

## Testen

```bash
# Draai alle tests (tegen de database uit .env).
docker compose exec web python -m pytest
```

Tegen MariaDB:

```bash
# Start (ook) een MariaDB-container.
docker compose --profile mariadb up -d mariadb
# Draai de tests met MariaDB in plaats van de database uit .env.
docker compose exec -e DB_ENGINE=mariadb -e DB_HOST=mariadb web python -m pytest
```

De databasegebruiker heeft dan rechten nodig op de testdatabase:
`GRANT ALL ON test_packdesk.* TO packdesk@'%'`. Tests schrijven bestanden altijd in een tijdelijke map en
gaan uit van een ingerichte installatie (`SETUP_WIZARD` uit); de tests van de wizard zetten hem aan.

GitHub Actions draait bij elke push alle tests op PostgreSQL en MariaDB, controleert of er migraties
ontbreken en bouwt de productie-image.

## Vertalingen

Teksten in de code zijn Engels; de Nederlandse en Duitse vertalingen staan in `locale/nl/` en
`locale/de/`. Een test controleert dat ze compleet zijn.

```bash
# Zoek nieuwe of gewijzigde teksten in de code en zet ze in de vertaalbestanden (locale/*/django.po).
docker compose exec web python manage.py makemessages -l nl -l de --ignore=venv --ignore=staticfiles --ignore=tests --no-obsolete
# Na het vertalen: zet de .po-bestanden om naar het formaat dat PackDesk leest (.mo).
docker compose exec web python manage.py compilemessages --ignore=/venv
```

Een taal toevoegen: zet hem in `LANGUAGES` in `packdesk/settings.py`, draai `makemessages -l <code>`,
vertaal de `.po`-bestanden in `locale/` en `locale_vendor/`, en maak een migratie voor de extra
inhoudsvelden (`makemigrations`).

## Rollen en rechten

Rechten zijn de gewone Django-rechten. Een nieuwe module voegt zijn app toe aan `MANAGED_APPS` in
`apps/accounts/permissions.py`, zodat de rechten in de roleditor verschijnen. De standaardrollen in
`apps/accounts/roles.py` worden alleen bij een nieuwe installatie aangemaakt en daarna nooit meer
automatisch aangepast.

## Uitgangspunten

- Alles wat per bedrijf verschilt, staat in de instellingen of in beheerbare inhoud, in drie talen.
  In de code staan alleen knoppen en labels van de software zelf.
- Bestaande gegevens worden nooit ongemerkt overschreven: imports tonen eerst een controle.
- Externe databases worden alleen gelezen.
- Klantgegevens, wachtwoorden en bestanden komen nooit in Git.

## Een nieuwe versie uitbrengen

Na elke push naar `main` draaien de tests; slagen ze, dan bouwt GitHub het image en zet het op
`ghcr.io/fritz4all/packdesk` met de tags `latest` en de korte commit-ID. Installaties halen het op met
`docker compose pull && docker compose up -d`.

Een vaste versie maak je met een tag:

```bash
# Markeer de huidige versie als 1.2.0 en zet de tag op GitHub; het image krijgt dan ook de tags 1.2.0 en 1.2.
git tag v1.2.0
git push origin v1.2.0
```

Wie een vaste versie wil draaien, zet `PACKDESK_VERSION=1.2` in `.env`.

## Foutpagina's

PackDesk heeft eigen foutpagina's (404 niet gevonden, 403 geen toegang, 400 verzoek niet begrepen, 500
er ging iets mis) in de stijl van de site: `templates/404.html` enz. Ook met `DEBUG=1` toont een onbekend
adres de eigen 404-pagina; `TECHNICAL_404=1` in `.env` geeft Django's technische pagina met alle adressen.
Bij 500 toont Django met `DEBUG=1` de foutmelding met details. Alle eigen pagina's zijn te bekijken op
`/errors/404/`, `/errors/403/`, `/errors/400/` en `/errors/500/` (alleen met `DEBUG=1`).
