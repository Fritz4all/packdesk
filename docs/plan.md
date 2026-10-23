# PackDesk – opbouwplan

Status: voorstel; techniekkeuze (Django) besloten. Laatst bijgewerkt: 2026-10-23.

## Doel

Een nieuwe webshop die functioneel hetzelfde doet als de previous-webshop-shop, maar:

- volledig instelbaar via een admin-omgeving (teksten, mails, factuursjabloon, prijzen, huisstijl, SMTP, nummering);
- modern en verzorgd van uiterlijk;
- geschikt voor meerdere klanten (eigen domein, data, huisstijl en instellingen per klant);
- met behoud van alle historie van de vorige webshop: klanten, documentnummers en de bestaande pdf's.

## Stappen

### A. Vorige webshop in kaart brengen

- Oude image lokaal draaien met test-MySQL en dummydata.
- Functioneel ontwerp: elk scherm, elke mail, elk pdf-document.
- Secret-scan van code en Git-historie (alleen bestand/regel/type rapporteren).
- 13 override-bestanden vergelijken met de repository.
- **Pdf-archief inventariseren**: welke soorten pdf's, hoeveel, naamgeving, koppeling aan klant/order.
- **Nummering inventariseren**: per documentsoort het formaat en hoe het volgende nummer wordt bepaald.

### B. Basis PackDesk

Python + Django, PostgreSQL, Docker, GitHub Actions, inloggen en rollen, multi-tenant, admin-opzet, ontwerp.
De oude Ruby-code dient alleen als naslag voor de werking; er wordt niets van overgenomen.

### C. Modules, één voor één

0. **Nummerreeksen** (per klant en per documentsoort instelbaar, zie hieronder)
1. Klanten, resellers, gebruikers
2. Supportpakketten en licenties
3. Bestellen en verlengen
4. Facturen en pdf's (sjabloon instelbaar, zonder Java)
5. Mails (sjablonen bewerkbaar)
6. Overzichten: aflopend, herinneringen, verlengingen, omzet
7. Onderdelen: aanvragen, offertes, orders
8. Content: homepage, menu, FAQ, artikelen, formulieren
9. Export naar Exact
10. **Documentarchief**: oude en nieuwe pdf's opzoeken op nummer, klant, datum, soort (en optioneel op tekst in de pdf)

### D. Data overzetten

- Klanten, licenties, orders, facturen enz. uit de oude MySQL-database.
- **Pdf-archief importeren** en koppelen aan klant en document; originelen blijven ongewijzigd.
- **Nummerreeksen laten doorlopen**: het volgende nummer wordt per reeks op het hoogste bestaande nummer + 1 gezet.
- Eerst testen op geanonimiseerde data; de echte import pas bij de overstap.

### E. Livegang en documentatie

Productie-compose, README, beheerdocumentatie, draaiboek voor de overstap.

## Nummering in de vorige webshop (gevonden in de code)

Nog niet geverifieerd tegen echte data.

| Documentsoort | Formaat in de oude code | Bron |
| --- | --- | --- |
| Factuur-pdf | bestand `invoice_<id, 10 cijfers>.pdf` in `/srv/www/data/invoices/` | `app/controllers/application_controller.rb:9`, `const.rb` `PATH_INVOICE` |
| Offerte onderdelen | `WS` + volgnummer (minimaal 17000) + 2 willekeurige letters | `app/models/part_tender.rb:157-175` |
| Order onderdelen | offertenummer + `-` + volgnummer | `app/models/part_order.rb:363-366` |
| Licentie | licentienummer + suffix + `-` + volgnummer | `app/models/hw_support_pack_license.rb:126` |
| Klant | debiteurnummer (`number_deb`), herkomst nog onbekend | `app/models/customer.rb` |
| Pakketbestelling | database-id | `app/mailers/hw_order_mailer.rb:14` |
| Onderdelenaanvraag ("ticket"?) | veld `number`, logica nog uitzoeken | `app/models/part_request.rb` |

Het factuurnummer lijkt het database-id te zijn. Dat moet bij de import behouden blijven, anders kloppen oude bestandsnamen en verwijzingen niet meer.

## Nummerreeksen in PackDesk (voorstel)

Per klant (tenant) en per documentsoort een reeks, in te stellen in de admin:

- **Patroon**, bijvoorbeeld `WS{nr}{letters:2}`, `F{jaar}-{nr:5}`, `C{nr:6}`
- **Volgende nummer** (bij import automatisch hoogste bestaande + 1)
- **Opnieuw beginnen** per jaar: ja/nee
- **Voorbeeld** van het volgende nummer, live in de admin
- Nummers worden uitgegeven binnen een database-transactie, zodat er nooit dubbele nummers ontstaan
- Een uitgegeven nummer wordt nooit hergebruikt of gewijzigd (belangrijk voor facturen)

## Nodig van Roy

- Een kopie van `/data/previous-webshop/data/` van de oude webserver (o.a. `invoices/`), aangeleverd als backup; ik maak zelf geen verbinding met productie.
- Voor de test: een geanonimiseerde dump of alleen het schema. Voor de echte overstap later: een verse dump.
- De productie-`const.rb`.

## Keuzes

Besloten (2026-10-23):

1. **Python + Django** (gekozen boven Rails, Laravel, Dolibarr en Odoo: bekende taal, ingebouwde admin, zelfde Docker-werkwijze als apparatenbeheer).

Aanbevolen, nog te bevestigen:

2. Django 5.2 LTS (ondersteund tot april 2028) op Python 3.13, officiële `python`-image.
3. PostgreSQL.
4. Eén database, elke regel gekoppeld aan een klant (tenant); klant herkend aan het domein.
5. Admin-thema voor een moderne look (bijv. django-unfold).
6. Pdf's uit HTML-sjablonen met WeasyPrint (geen Java).
7. Achtergrondtaken (herinneringen, mails) via de database, geen Redis.
