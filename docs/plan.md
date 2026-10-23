# PackDesk – opbouwplan

Status: stap A en B klaar. Laatst bijgewerkt: 2026-10-23.

## Doel

Een nieuwe webshop die functioneel hetzelfde doet als de previous-webshop-shop, maar:

- volledig instelbaar via een admin-omgeving (teksten, mails, factuursjabloon, prijzen, huisstijl, SMTP, nummering);
- modern en verzorgd van uiterlijk;
- volledig meertalig: Nederlands, Engels en Duits (vaste teksten én inhoud per taal);
- herbruikbaar voor meerdere klanten: per klant een **eigen installatie** (on-site), met naam, logo, kleuren, bedrijfsgegevens en alle andere instellingen aan te passen in de admin;
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

Python + Django, PostgreSQL, Docker, GitHub Actions, inloggen en rollen, rollen en rechten (eigen rollen met rechtenmatrix, elke medewerker één rol), instellingenpagina (naam, logo, kleuren, licht/donker, talen, adressen per documentsoort, homepageblokken, menu, footer, onderhoudsmodus en meldingsbalk), admin-opzet, ontwerp.
De oude Ruby-code dient alleen als naslag voor de werking; er wordt niets van overgenomen.

### C. Modules, één voor één

0. **Nummerreeksen** (per documentsoort instelbaar, zie hieronder) – **gebouwd**, incl. controle tegen het factuurarchief, correctie met reden en logboek, en verklaren van gaten
1. Klanten, resellers, gebruikers, **aanmeldformulier "reseller worden"** (met goedkeuring door beheer) – **gebouwd**, incl. klantportaal "Mijn gegevens", wachtwoord vergeten/wijzigen en uitnodigingen
2. Supportpakketten en licenties, **registratiewizard** (licentie → reseller → eindklant → apparaat → monitor → interne/externe opties) en **storing melden** – catalogus, licenties en registratiewizard **gebouwd**; storing melden volgt
3. Bestellen en verlengen
4. Facturen en pdf's (sjabloon instelbaar, zonder Java); **facturen zichtbaar, downloadbaar en opnieuw te versturen** – in het beheer per klant én voor de klant zelf in het klantportaal
5. Mails (sjablonen bewerkbaar)
6. Overzichten: aflopend, herinneringen, verlengingen, omzet
7. Onderdelen: aanvragen, offertes, orders
8. Content: pagina's (over ons, contact, producten), FAQ, artikelen, formulieren – homepage, menu en footer zijn al instelbaar (stap B)
9. Export naar Exact
10. **Documentarchief**: oude en nieuwe pdf's opzoeken op nummer, klant, datum, soort (en optioneel op tekst in de pdf); oude facturen uit het archief koppelen aan klanten, zodat ze ook in het beheer en het klantportaal te zien, te downloaden en opnieuw te versturen zijn

### D. Data overzetten

- Klanten, licenties, orders, facturen enz. uit de oude MySQL-database.
- **Pdf-archief importeren** en koppelen aan klant en document; originelen blijven ongewijzigd.
- **Nummerreeksen laten doorlopen**: het volgende nummer wordt per reeks op het hoogste bestaande nummer + 1 gezet.
- Eerst testen op geanonimiseerde data; de echte import pas bij de overstap.

### E. Livegang en documentatie

Productie-compose, README, beheerdocumentatie, draaiboek voor de overstap, en een **installatiehandleiding voor een nieuwe klant** (on-site neerzetten, eerste instellingen).

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

Per documentsoort een reeks, in te stellen in de admin:

- **Patroon**, bijvoorbeeld `WS{nr}{letters:2}`, `F{jaar}-{nr:5}`, `C{nr:6}`
- **Volgende nummer** (bij import automatisch hoogste bestaande + 1)
- **Opnieuw beginnen** per jaar: ja/nee
- **Voorbeeld** van het volgende nummer, live in de admin
- Nummers worden uitgegeven binnen een database-transactie, zodat er nooit dubbele nummers ontstaan
- Een uitgegeven nummer wordt nooit hergebruikt of gewijzigd (belangrijk voor facturen)

## Nodig van Roy

Ontvangen: productie-`const.rb`, kopie van `/data/previous-webshop/data/` (factuurarchief), kopie van de app uit de container, databaseschema (zie `docs/vorige-webshop/analyse.md` §12 en §13).

Nog nodig:

- Database met data: voor het testen van de import een geanonimiseerde dump; voor de echte overstap later een verse dump. (Het schema is ontvangen.)

## Keuzes

Besloten (2026-10-23):

1. **Python + Django** (gekozen boven Rails, Laravel, Dolibarr en Odoo: bekende taal, ingebouwde admin, zelfde Docker-werkwijze als apparatenbeheer).
2. **Eén installatie per klant, on-site** – geen multi-tenant platform. Alles wat per klant verschilt staat in de instellingen in de admin, niet in de code.
3. Django 5.2 LTS (ondersteund tot april 2028) op Python 3.13, officiële `python`-image.
4. PostgreSQL 17.
5. Admin-thema django-unfold.
6. Talen nl/en/de; inhoud per taal met django-modeltranslation.

Aanbevolen, nog te bevestigen:

7. Pdf's uit HTML-sjablonen met WeasyPrint (geen Java).
8. Achtergrondtaken (herinneringen, mails) via de database, geen Redis.

## Uitgangspunt: alles instelbaar

Alles wat een bezoeker op de site ziet en per klant kan verschillen, komt uit de instellingen of uit beheerbare inhoud, in drie talen. Vaste teksten in de code zijn alleen knoppen en labels van de software zelf (ook vertaald). Bij elke nieuwe module wordt dit gecontroleerd.
