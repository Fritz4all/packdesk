# Installatie

Hoe je PackDesk neerzet voor een bedrijf: welke onderdelen er zijn, wat je instelt en hoe je back-ups
maakt en bijwerkt. Voor een snelle proefopstelling op je eigen computer: zie de [README](../README.md).

## Wat er draait

| Onderdeel | Wat het doet |
|---|---|
| **PackDesk** (container `web`) | de website en het beheer |
| **Database** | alle gegevens: klanten, licenties, bestellingen, facturen, instellingen, gebruikers |
| **Datamap** | bestanden die PackDesk bewaart: logo's, factuur-pdf's, bijlagen |
| **Mailserver** | voor uitgaande mail (bestaande mailserver van het bedrijf of een maildienst) |

De database en de datamap staan altijd buiten de PackDesk-container. Een container kun je dus
weggooien en vervangen door een nieuwe versie zonder dat er iets verloren gaat.

## 1. Instellingen in `.env`

Kopieer `.env.example` naar `.env` en vul het in. Elke regel heeft een korte uitleg. De belangrijkste:

| Instelling | Uitleg |
|---|---|
| `SECRET_KEY` | lange willekeurige tekst, geheim houden |
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | de domeinnaam van de shop, bijv. `shop.bedrijf.nl` en `https://shop.bedrijf.nl` |
| `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | de database (zie hieronder) |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` | de mailserver |
| `DATA_DIR` | de datamap op de server |

`.env` bevat wachtwoorden: zet het nooit in Git en geef het alleen aan wie de server beheert.

## 2. Database

PackDesk werkt met **PostgreSQL** en met **MariaDB / MySQL**. Kies wat bij de omgeving past:

| Situatie | In `.env` |
|---|---|
| Bestaande databaseserver van het bedrijf | `DB_ENGINE=mariadb` (of `postgres`), `DB_HOST=<ip-adres>`, naam, gebruiker en wachtwoord; `COMPOSE_PROFILES=` leeg |
| PostgreSQL in een container naast PackDesk | `DB_ENGINE=postgres`, `DB_HOST=postgres`, `COMPOSE_PROFILES=postgres` |
| MariaDB in een container naast PackDesk | `DB_ENGINE=mariadb`, `DB_HOST=mariadb`, `DB_ROOT_PASSWORD=…`, `COMPOSE_PROFILES=mariadb` |

PackDesk krijgt altijd een **eigen** database, ook op een server waar al andere databases staan. Op
een bestaande MariaDB-server maakt de beheerder van die server hem eenmalig aan:

```sql
CREATE DATABASE packdesk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'packdesk'@'<ip van de PackDesk-server>' IDENTIFIED BY '<wachtwoord>';
GRANT ALL ON packdesk.* TO 'packdesk'@'<ip van de PackDesk-server>';
```

De tekenset `utf8mb4` is nodig voor alle tekens, zoals de pictogrammen op de homepage.

## 3. Mappen

| Op de server | In de container | Inhoud |
|---|---|---|
| `DATA_DIR` (standaard `../packdesk-data`) | `/data` | alles wat PackDesk bewaart, met een submap per doel: `website/`, `invoices/`, `fault-attachments/`, `imports/` |
| optioneel, bijv. het oude factuurarchief | `/data-sources/<naam>` | bestanden uit een ander systeem, alleen-lezen |

Alleen `website/` (logo's) is via de website te zien. Facturen en bijlagen opent PackDesk alleen voor
de eigen klant of een medewerker met het juiste recht. Meer details: [Waar staat wat](opslag.md).

Een bron alleen-lezen koppelen (bijvoorbeeld de factuur-pdf's van een vorig systeem) doe je in een
`docker-compose.override.yml` naast `docker-compose.yml`; Docker Compose leest dat bestand vanzelf:

```yaml
services:
  web:
    volumes:
      - ${DOCUMENT_ARCHIVE}:/data-sources/archive-invoices:ro
```

met `DOCUMENT_ARCHIVE=<map met de pdf's>` in `.env`.

## 4. Starten en eerste keer inrichten

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py create_user --email <jouw e-mailadres> --superuser
```

Daarna in het beheer (`/beheer/`):

1. **Instellingen:** naam, logo, kleuren, talen, adressen, bedrijfsgegevens (KvK, btw, IBAN).
2. **Nummerreeksen:** patroon en beginnummer voor klanten, bestellingen, licenties en facturen.
3. **Catalogus:** categorieën, merken, apparaattypes en servicepakketten met prijzen.
4. **Medewerkers:** toevoegen en een rol geven. De standaardrollen staan al klaar.

Komt het bedrijf over van een ander systeem? Zie *Externe databases* in de [handleiding](handleiding.md).

## 5. Op een server

`docker-compose.yml` is bedoeld voor ontwikkelen en testen: hij zet de foutopsporing aan en vangt alle
mail af in een testmailbox. Op een server gebruik je de productie-image:

```bash
docker build -t packdesk:<versie> .
```

- De image draait als gewone gebruiker (niet als root) en luistert op poort 8000. Zet er een
  webserver of reverse proxy voor die HTTPS regelt.
- Alle instellingen komen uit `.env` / omgevingsvariabelen.
- Koppel `DATA_DIR` als `/data`.
- Databasewijzigingen bij een nieuwe versie gebeuren alleen als je `RUN_MIGRATIONS=1` meegeeft, of met
  `python manage.py migrate`. Zo verandert een update de database nooit ongemerkt.

## 6. Back-ups

Maak regelmatig een back-up van:

1. **de database**, bijvoorbeeld
   `docker compose exec postgres pg_dump -U packdesk packdesk > packdesk.sql` of
   `docker compose exec mariadb mariadb-dump -u packdesk -p packdesk > packdesk.sql`
   (bij een bestaande databaseserver: met de back-up van die server);
2. **de datamap** (`DATA_DIR`);
3. **`.env`**, op een veilige plek.

Bronnen uit andere systemen (zoals een oud factuurarchief) veranderen niet; daarvan is één kopie genoeg.

## 7. Bijwerken naar een nieuwe versie

1. Back-up maken (zie hierboven).
2. Nieuwe versie ophalen of bouwen.
3. Container vervangen: `docker compose up -d --build`.
4. Databasewijzigingen doorvoeren: `docker compose exec web python manage.py migrate`.
