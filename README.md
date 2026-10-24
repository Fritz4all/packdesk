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

## Snel starten

Nodig: [Docker](https://docs.docker.com/get-docker/) met Docker Compose.

```bash
# Haal PackDesk binnen en ga naar de map.
git clone https://github.com/Fritz4all/packdesk.git
cd packdesk

# Start PackDesk met een eigen database op de achtergrond (de eerste keer een paar minuten).
docker compose up -d

# Toon de installatiecode die je zo nodig hebt.
docker compose logs web | grep "Installation code"
```

Open daarna http://localhost:8000. De installatiewizard vraagt de code, maakt je beheerdersaccount aan
en loopt de basisinstellingen, de mailserver en de nummering met je door. Wil je oefenen, vink dan in
de laatste stap de democatalogus aan. Instellingen vooraf in een `.env`-bestand zijn niet nodig.

Liever MariaDB, of een bestaande databaseserver? Daarvoor zijn er kant-en-klare startbestanden; zie
[Installatie](docs/installatie.md).

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
