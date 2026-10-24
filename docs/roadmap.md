# Roadmap

Wat PackDesk nu kan en wat er nog komt.

## Klaar

- Basis: instellingen per installatie, huisstijl, licht/donker, drie talen, onderhoudsmodus, rollen en rechten.
- Nummerreeksen met controle, correctie en logboek.
- Klanten, aanmelden, klantportaal, export en import van klanten.
- Catalogus, licenties, registratiewizard en storing melden.
- Bestellen en verlengen.
- Facturen als pdf, opnieuw versturen, oud factuurarchief.
- Dashboard, verkoop en marge, zoeken in alles.
- PostgreSQL en MariaDB/MySQL.
- Externe databases, koppelingen en vergelijken.
- Installatiewizard voor een nieuwe installatie en database bijwerken via de browser.
- Prullenbak met terugzetten, en instelbaar automatisch uitloggen.

## Nog te doen

1. **Mails bewerkbaar** als sjablonen in het beheer.
2. **Overzichten:** aflopende licenties, verlengvoorstellen, herinneringen, omzet.
3. **Onderdelen:** aanvragen, offertes en orders.
4. **Inhoud:** pagina's (over ons, contact), veelgestelde vragen, artikelen, formulieren.
5. **Export naar Exact.**
6. **Documentarchief** voor andere documentsoorten dan facturen.
7. **Overstap van de vorige webshop:** klanten, licenties, bestellingen en facturen overnemen met de
   bestaande koppelingen; nummerreeksen laten doorlopen. Nodig: een (geanonimiseerde) kopie van de
   oude database met gegevens.
8. **Importeren uit andere systemen**, terugkerend als dat nodig is:
   - één route voor elke bron: een database (bestaat al), een bestand (CSV, Excel, PackDesk-export,
     tijdelijk in `/data/imports/`) of een map met documenten (alleen-lezen onder `/data-sources/<naam>`);
   - dezelfde stappen: koppelen → proefrun → per record kiezen → importeren → verslag;
   - per koppeling in te stellen: handmatig of automatisch op een vast moment. Bij automatisch
     importeren geldt per onderdeel een vooraf gekozen regel (nieuwe toevoegen, wijzigingen overnemen
     of alleen melden); twijfelgevallen komen als melding in het beheer.
9. **Livegang:** productie-opzet en een draaiboek voor de overstap.
