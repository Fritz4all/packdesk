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
  admin: naam, logo, favicon, kleuren, slogan, introductietekst, bedrijfsgegevens (adres, KvK, btw, IBAN)
  en talen. Er staat niets klantspecifieks in de code.
- **Licht, donker of auto:** in de instellingen kies je de standaardweergave (auto volgt het apparaat)
  en of bezoekers zelf mogen kiezen. Hun keuze wordt in de browser onthouden. De merkkleur wordt in
  elke weergave automatisch iets lichter of donkerder gemaakt, zodat links leesbaar blijven.
  De admin heeft een eigen keuze voor licht/donker/systeem.
- **Inloggen** met e-mailadres.
- **Admin** op `/beheer/`.
- **Rollen:** Beheerder, Financieel, Service, Medewerker (`apps/accounts/roles.py`).
  Een superuser kan alles, ook rollen beheren.

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
