# PackDesk

PackDesk is een webshop en klantportaal voor ICT-servicepakketten. Resellers en klanten bestellen er
servicepakketten, registreren licenties voor hun apparaten, melden storingen en vinden hun facturen.
Het bedrijf dat PackDesk gebruikt, regelt alles in een overzichtelijk beheergedeelte: klanten,
prijzen, teksten, huisstijl, nummering, rechten van medewerkers.

- **Eén installatie per bedrijf.** Elk bedrijf krijgt een eigen PackDesk op een eigen server. Naam,
  logo, kleuren, adressen en teksten stel je in via het beheer; er hoeft niets in de code te veranderen.
- **Drie talen.** Website en beheer zijn er in het Nederlands, Engels en Duits.
- **Licht en donker.** Bezoekers en medewerkers kiezen zelf.
- **Database naar keuze.** PostgreSQL of MariaDB/MySQL, ook op een bestaande databaseserver.
- **Overstappen vanuit een ander systeem.** Gegevens uit een bestaande database vergelijken en
  overnemen, met eerst een controle; er wordt nooit iets ongemerkt overschreven.

## Wat zit erin

| Voor klanten | Voor het bedrijf (beheer) |
|---|---|
| Aanmelden als nieuwe klant | Klanten goedkeuren, blokkeren en uitnodigen |
| Servicepakketten bestellen en verlengen | Catalogus met servicepakketten en prijzen |
| Licenties registreren voor een apparaat | Licenties, registraties en dekking |
| Storingen melden, met bijlagen | Storingsmeldingen afhandelen |
| Facturen bekijken, downloaden en mailen | Facturen als pdf, opnieuw versturen, oud archief |
| Eigen gegevens en wachtwoord beheren | Dashboard, verkoop en marge, zoeken in alles |
| | Rollen en rechten per medewerker |
| | Nummering van klanten, orders, licenties en facturen |
| | Klanten exporteren en importeren |
| | Externe databases koppelen en vergelijken |

## Snel starten (om uit te proberen)

Nodig: [Docker](https://docs.docker.com/get-docker/) met Docker Compose.

```bash
# Maak je eigen instellingenbestand op basis van het voorbeeld.
cp .env.example .env
```

Zet in `.env` voor een proefopstelling: `DB_ENGINE=postgres`, `DB_HOST=postgres`, `DB_PASSWORD=` een
zelfgekozen wachtwoord en `COMPOSE_PROFILES=postgres`. Daarna:

```bash
# Start PackDesk, de database en de testmailbox op de achtergrond (de eerste keer wordt alles
# gedownload en gebouwd; dat duurt een paar minuten).
docker compose up -d

# Maak de tabellen in de lege database aan.
docker compose exec web python manage.py migrate

# Maak het eerste beheerdersaccount; je wordt gevraagd een wachtwoord te kiezen.
docker compose exec web python manage.py create_user --email admin@example.com --superuser

# Optioneel: vul een kleine democatalogus met servicepakketten en testlicenties om mee te oefenen.
docker compose exec web python manage.py load_demo_catalogue
```

`docker compose exec web …` voert een opdracht uit binnen de draaiende PackDesk-container (`web`).
Regels die met `#` beginnen zijn uitleg; die mag je meekopiëren.

Daarna open je in de browser:

- Website: http://localhost:8000
- Beheer: http://localhost:8000/beheer/
- Verstuurde mails (testmailbox): http://localhost:8025

## Documentatie

| Document | Voor wie | Inhoud |
|---|---|---|
| [Installatie](docs/installatie.md) | wie PackDesk neerzet | server, database, mappen, mail, back-ups, updates |
| [Handleiding](docs/handleiding.md) | beheerders en medewerkers | alle onderdelen van het beheer en het klantportaal |
| [Waar staat wat](docs/opslag.md) | beheerders | waar gegevens, bestanden en instellingen bewaard worden |
| [Ontwikkelen](docs/ontwikkelen.md) | ontwikkelaars | techniek, tests, vertalingen |
| [Roadmap](docs/roadmap.md) | iedereen | wat er is en wat er nog komt |
| [Vorige webshop](docs/vorige-webshop/) | wie de overstap begeleidt | analyse en werking van de webshop die PackDesk vervangt |

## Techniek in het kort

Python 3.13 en Django 5.2 (LTS), PostgreSQL 17 of MariaDB 10.6+, beheer met django-unfold, pdf's met
WeasyPrint, alles in Docker. Elke wijziging wordt automatisch getest op beide databases.
