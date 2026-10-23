# PackDesk

Multi-tenant webshop voor ICT-supportpakketten, licenties, bestellingen en facturen.
Functioneel gebaseerd op de previous-webshop-shop, maar volledig beheerbaar via een admin-omgeving
en geschikt voor meerdere klanten (organisaties), elk met een eigen domein, huisstijl en data.

Status: in opbouw. Zie [docs/plan.md](docs/plan.md).

## Techniek

Python 3.13, Django 5.2 LTS, PostgreSQL 17, admin met django-unfold, Docker.

## Hoe het werkt

- **Organisaties (tenants):** elke klant van PackDesk is een organisatie met een of meer domeinen.
  PackDesk herkent aan de hostnaam welke organisatie het is. Onbekende hostnamen geven 404.
- **Platformhosts** (`PLATFORM_HOSTS`) tonen alleen de admin, voor het beheer van alle organisaties.
- **Inloggen** met e-mailadres, binnen de organisatie van het domein. Hetzelfde e-mailadres kan bij
  meerdere organisaties bestaan.
- **Admin** op `/beheer/`. Platformbeheerders zien alles; beheerders van een organisatie zien alleen
  hun eigen gegevens en kunnen huisstijl, bedrijfsgegevens, taal en gebruikers aanpassen.
- **Rollen:** Beheerder, Financieel, Service, Medewerker (`apps/accounts/roles.py`).

## Lokaal ontwikkelen

Vereist: Docker met Compose v2.

```bash
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web python manage.py create_tenant --name "Demo" --slug demo --domain demo.localhost
docker compose exec web python manage.py create_user --email beheer@demo.test --tenant demo --role Beheerder
docker compose exec web python manage.py create_user --email admin@example.test
```

- Site van de organisatie: http://demo.localhost:8000 (`*.localhost` werkt in moderne browsers zonder hosts-file)
- Admin van de organisatie: http://demo.localhost:8000/beheer/
- Platform-admin: http://localhost:8000/beheer/
- Mailpit (verstuurde mails): http://localhost:8025

## Testen

```bash
docker compose exec web python -m pytest
```

GitHub Actions draait bij elke push de tests tegen PostgreSQL en bouwt de productie-image.

## Vertalingen

Teksten in de code zijn Engels; Nederlands staat in `locale/nl/LC_MESSAGES/django.po`.
De taal is een instelling per organisatie.

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
