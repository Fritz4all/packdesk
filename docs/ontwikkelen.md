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

Zie [README](../README.md) en [Installatie](installatie.md). `docker-compose.yml` start PackDesk met
de code als gekoppelde map, zodat wijzigingen direct zichtbaar zijn, plus een testmailbox op
http://localhost:8025.

Handige opdrachten:

| Opdracht | Doet |
|---|---|
| `python manage.py create_user --email <adres> --superuser` | beheerder aanmaken |
| `python manage.py load_demo_catalogue` | kleine democatalogus met testlicenties |
| `python manage.py import_invoice_archive` | factuur-pdf's uit het archief registreren (`--relink`, `--fix-dates`) |

(Voer ze uit met `docker compose exec web …`.)

## Testen

```bash
docker compose exec web python -m pytest
```

Tegen MariaDB:

```bash
docker compose --profile mariadb up -d mariadb
docker compose exec -e DB_ENGINE=mariadb -e DB_HOST=mariadb web python -m pytest
```

De databasegebruiker heeft dan rechten nodig op de testdatabase:
`GRANT ALL ON test_packdesk.* TO packdesk@'%'`. Tests schrijven bestanden altijd in een tijdelijke map.

GitHub Actions draait bij elke push alle tests op PostgreSQL en MariaDB, controleert of er migraties
ontbreken en bouwt de productie-image.

## Vertalingen

Teksten in de code zijn Engels; de Nederlandse en Duitse vertalingen staan in `locale/nl/` en
`locale/de/`. Een test controleert dat ze compleet zijn.

```bash
docker compose exec web python manage.py makemessages -l nl -l de --ignore=venv --ignore=staticfiles --ignore=tests --no-obsolete
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
