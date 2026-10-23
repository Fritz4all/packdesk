# PackDesk

Webshop voor ICT-supportpakketten, licenties, bestellingen en facturen.
Functioneel gebaseerd op de previous-webshop-shop, maar volledig beheerbaar via een admin-omgeving.
Herbruikbaar voor meerdere klanten: elke klant krijgt een eigen installatie (on-site), en naam,
logo, kleuren, bedrijfsgegevens en taal stel je in via de admin.

Status: in opbouw. Zie [docs/plan.md](docs/plan.md).

## Techniek

Python 3.13, Django 5.2 LTS, PostgreSQL 17, admin met django-unfold, Docker.

## Hoe het werkt

- **Eén installatie per klant.** Alles wat per klant verschilt staat op de pagina **Instellingen** in de
  admin: naam, logo, favicon, kleuren, slogan, introductietekst, bedrijfsgegevens (adres, KvK, btw, IBAN)
  en taal. Er staat niets klantspecifieks in de code.
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

## Vertalingen

Teksten in de code zijn Engels; Nederlands staat in `locale/nl/LC_MESSAGES/django.po`.
De taal kies je in de instellingen.

```bash
docker compose exec web python manage.py makemessages -l nl --ignore=venv --ignore=staticfiles --ignore=tests
docker compose exec web python manage.py compilemessages --ignore=/venv
```

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
