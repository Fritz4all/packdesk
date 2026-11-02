"""Made-up customers for trying out PackDesk: each one stands for a situation, as its name and remark say.

Only for a development installation: nothing here is real, the mail addresses end in .test and no mail is sent.
"""

import datetime
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.cmdb import discovery, history
from apps.cmdb.models import (
    CmdbCustomer, CmdbSettings, ConfigurationItem, DiscoveredItem, DiscoverySource, ItemChange, ItemStatus, ItemType,
    Relation, RelationKind,
)
from apps.customers.models import Contact, Country, Customer, CustomerAddress, CustomerType
from apps.faults.models import FaultReport
from apps.hardware.models import Condition, Device, DeviceType
from apps.invoices.services import create_for_order, create_for_part_order
from apps.licences.models import Licence, SupportPack, Vendor
from apps.numbering.models import NumberSequence
from apps.orders.models import Order, OrderLine, PaymentMethod, place_order
from apps.parts.models import Packing, PartOrder, PartOrderLine, PartRequest, RequestLine
from apps.printing.models import Printer, PrintingSettings, PrintContract, PrintQuote, PrintQuoteLine
from apps.telephony.models import Category, Item, Quote, QuoteLine, TelephonyCustomer, TelephonySettings

MARKER = "Alles Tegelijk BV"
MODULES_MARKER = "Telefonie Uit BV"
DOMAIN = "example.test"


class Command(BaseCommand):
    help = "Create made-up customers in many situations (with and without purchases, licences, CMDB, ...)."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="", help="Password of the test logins; without it they cannot log in yet.")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Only for a development installation (DEBUG on).")
        base_missing = not Customer.objects.filter(name=MARKER).exists()
        modules_missing = not Customer.objects.filter(name=MODULES_MARKER).exists()
        if not (base_missing or modules_missing):
            self.stdout.write("The demo customers are already there; nothing created.")
            return
        self.password = options["password"]
        self.logins = []
        self.made = []
        self.today = timezone.localdate()
        with transaction.atomic():
            if base_missing:
                self.build()
            if modules_missing:
                self.telephony_and_printing()
        self.stdout.write(self.style.SUCCESS(f"{len(self.made)} demo customers created."))
        for name, situation in self.made:
            self.stdout.write(f"  {name}: {situation}")
        for name, email in self.logins:
            self.stdout.write(f"  login {email} ({name})")

    # --- building blocks ------------------------------------------------------------------------------------

    def customer(self, name, situation, country="NL", type_name="Eindklant", status=Customer.Status.ACTIVE, contact=True,
                 login=False, **fields):
        customer = Customer(name=name, status=status, customer_type=CustomerType.objects.filter(name=type_name).first(),
                            email=f"info@{self.slug(name)}.{DOMAIN}", phone="010-0000000", remark=situation, **fields)
        if status != Customer.Status.PENDING:
            customer.assign_number()
        customer.save()
        self.made.append((name, situation))
        CustomerAddress.objects.create(customer=customer, line1="Voorbeeldstraat 1", postal_code="1234 AB", city="Voorbeeldstad",
                                       country=Country.objects.filter(code=country).first())
        if contact:
            self.contact(customer, login)
        return customer

    @staticmethod
    def slug(name):
        return "".join(c for c in name.lower() if c.isalnum())[:30]

    def contact(self, customer, login):
        email = f"contact@{self.slug(customer.name)}.{DOMAIN}"
        user = None
        if login:
            user = User(email=email, first_name="Test", last_name="Contact", kind=User.Kind.CUSTOMER,
                        is_active=customer.status == Customer.Status.ACTIVE)
            if self.password:
                user.set_password(self.password)
            else:
                user.set_unusable_password()
            user.save()
            self.logins.append((customer.name, email))
        return Contact.objects.create(customer=customer, user=user, first_name="Test", last_name="Contact", email=email,
                                      phone="06-00000000", is_primary=True)

    def licence(self, customer, state="registered", order_line=None, serial=""):
        """A licence that did not come from an order here, e.g. taken over from another system."""
        lic = Licence.create_for(self.pack, customer, 1, order_reference="")[0]
        lic.order_line = order_line
        if state != "unregistered":
            start = self.today - datetime.timedelta(days=30 if state == "registered" else 1500)
            lic.registered_on = timezone.now()
            lic.start_date = start
            lic.end_date = start + datetime.timedelta(days=1095)
            lic.vendor = Vendor.objects.first()
            lic.description = "Testserver"
            lic.serial_nr = serial or f"LIC{lic.number}"
            lic.purchase_date = start
        lic.save()
        return lic

    def pack_order(self, customer, invoice=True, paid=False, quantity=1):
        order = place_order(customer, None, [{"pack": self.pack, "quantity": quantity}], reference="Demo")
        if invoice:
            bill = create_for_order(order)
            if paid:
                bill.paid_on = self.today
                bill.save(update_fields=["paid_on"])
        return order

    def register_order_licences(self, order):
        for line in order.lines.all():
            for lic in line.licences.all():
                start = self.today - datetime.timedelta(days=10)
                lic.registered_on, lic.start_date, lic.end_date = timezone.now(), start, start + datetime.timedelta(days=1095)
                lic.vendor, lic.description, lic.serial_nr, lic.purchase_date = Vendor.objects.first(), "Testserver", f"LIC{lic.number}", start
                lic.save()

    def hardware_order(self, customer, model="Refurbished laptop"):
        device = Device.objects.create(
            device_type=DeviceType.objects.first(), brand=Vendor.objects.first(), model=model,
            serial_nr=f"HW{NumberSequence.objects.get(key='hardware_device').next_number:05}",
            condition=Condition.objects.first(), status=Device.Status.FOR_SALE, sale_price=Decimal("450.00"),
            purchase_price=Decimal("300.00"),
        )
        _n, number = NumberSequence.issue("order")
        order = Order.objects.create(number=number, kind=Order.Kind.HARDWARE, customer=customer, reference="Demo",
                                     payment_method=PaymentMethod.objects.filter(for_hardware=True).first())
        OrderLine.objects.create(order=order, device=device, description=str(device), quantity=1,
                                 unit_price=device.sale_price, line_total=device.sale_price)
        order.recalculate()
        order.save()
        create_for_order(order)
        return order

    def part_request(self, customer, answered=False):
        _n, number = NumberSequence.issue("part_request")
        request = PartRequest.objects.create(
            number=number, customer=customer, reference="Demo",
            status=PartRequest.Status.ANSWERED if answered else PartRequest.Status.TO_HANDLE,
            valid_until=self.today + datetime.timedelta(days=30) if answered else None,
        )
        line = RequestLine.objects.create(
            request=request, article_number="DEMO-1234", vendor=Vendor.objects.first(), quantity=2, description="Testonderdeel",
            status=RequestLine.Status.AGREED if answered else RequestLine.Status.OPEN,
            price_new=Decimal("80.00") if answered else None,
        )
        return request, line

    def part_order(self, customer):
        request, line = self.part_request(customer, answered=True)
        order = PartOrder.objects.create(number=f"{request.number}-1", request=request, customer=customer, reference="Demo",
                                         status=PartOrder.Status.TO_DELIVER,
                                         payment_method=PaymentMethod.objects.filter(for_parts=True).first())
        PartOrderLine.objects.create(order=order, request_line=line, packing=Packing.choices[0][0], quantity=2,
                                     purchase_price=Decimal("80.00"), unit_price=Decimal("120.00"))
        order.recalculate()
        order.save()
        create_for_part_order(order)
        return order

    def fault(self, customer, licence=None):
        _n, number = NumberSequence.issue("ticket")
        return FaultReport.objects.create(
            number=number, customer=customer, licence=licence, vendor="Voorbeeldmerk", device="Testserver",
            serial_nr=licence.serial_nr if licence else "ZONDERLICENTIE1", description="Start niet meer op.",
            covered_until=licence.end_date if licence else None,
            reseller_name=customer.name, location_name=customer.name, location_contact="Test Contact",
            location_address="Voorbeeldstraat 1", location_postal_code="1234 AB", location_city="Voorbeeldstad",
            location_phone="010-0000000", location_email=customer.email,
        )

    def cmdb(self, customer, enabled=True, portal=False, warranty=False):
        CmdbCustomer.objects.update_or_create(customer=customer, defaults={
            "enabled": enabled, "portal_access": portal, "warranty_mail": warranty})

    def item(self, customer, name, kind="Hardware", status="in_use", warranty_days=None, **fields):
        contact = customer.contacts.first()
        item = ConfigurationItem(
            customer=customer, name=name, item_type=self.types[kind], status=self.statuses[status], contact=contact,
            location=fields.pop("location", "Serverruimte"),
            warranty_until=self.today + datetime.timedelta(days=warranty_days) if warranty_days is not None else None,
            **fields)
        item.save()
        history.record(item, None, None, ItemChange.Source.ADMIN)
        return item

    def relate(self, source, kind, target):
        Relation.objects.create(source=source, kind=self.kinds[kind], target=target)

    def landscape(self, customer):
        """A small set of connected items: application → server → hardware → power and network."""
        firewall = self.item(customer, "Firewall", "Network", manufacturer="Voorbeeldmerk", model="FW-100", serial_nr=f"FW{customer.pk:04}",
                             warranty_days=400, properties={"ip_address": "192.0.2.1"})
        switch = self.item(customer, "Core switch", "Network", manufacturer="Voorbeeldmerk", model="SW-48", serial_nr=f"SW{customer.pk:04}",
                           warranty_days=45, properties={"ip_address": "192.0.2.2"})
        host = self.item(customer, "Hypervisor 1", "Hardware", manufacturer="Voorbeeldmerk", model="Rack 200", serial_nr=f"HV{customer.pk:04}",
                         warranty_days=20, properties={"ip_address": "192.0.2.10", "operating_system": "Linux"})
        vm_mail = self.item(customer, "Mailserver", "Virtual machine", properties={"ip_address": "192.0.2.20", "operating_system": "Linux"})
        vm_erp = self.item(customer, "ERP-server", "Virtual machine", properties={"ip_address": "192.0.2.21", "operating_system": "Windows Server"})
        mail = self.item(customer, "E-mail", "Service")
        erp = self.item(customer, "ERP-pakket", "Software", properties={"version": "5.2"}, warranty_days=-30)
        self.relate(mail, "runs_on", vm_mail)
        self.relate(erp, "runs_on", vm_erp)
        self.relate(vm_mail, "runs_on", host)
        self.relate(vm_erp, "runs_on", host)
        self.relate(host, "connected_to", switch)
        self.relate(switch, "connected_to", firewall)
        self.relate(erp, "uses", mail)
        return host

    # --- the situations ---------------------------------------------------------------------------------------

    def telephony_and_printing(self):
        TelephonySettings.objects.update_or_create(pk=1, defaults={
            "enabled": True, "installation_costs": Decimal("25"), "default_margin": Decimal("10")})
        PrintingSettings.objects.update_or_create(pk=1, defaults={"enabled": True})
        devices = Category.objects.create(name_nl="Toestellen", name_en="Phones", position=1)
        licences = Category.objects.create(name_nl="Licenties", name_en="Licences", position=2)
        phone = Item.objects.create(category=devices, name_nl="IP-toestel", name_en="IP phone",
                                    hire_per_month=Decimal("2.60"), buy_price=Decimal("132"))
        licence = Item.objects.create(category=licences, name_nl="Gebruikerslicentie", name_en="User licence",
                                      hire_per_month=Decimal("5.90"), buy_per_month=Decimal("5.90"))
        licence.quantity_from.set([phone])

        def quote(customer, reference):
            made = Quote.objects.create(customer=customer, reference=reference, margin_hire=Decimal("10"),
                                        margin_buy=Decimal("10"), installation_costs=Decimal("25"))
            for item in (phone, licence):
                QuoteLine.objects.create(quote=made, item=item, quantity=4, hire_per_month=item.hire_per_month,
                                         buy_price=item.buy_price, buy_per_month=item.buy_per_month)

        quote(self.customer("Telefonie Aan BV", "Gebruikt telefonie: ziet de calculator en heeft een offerte.", login=True),
              "Kantoor Rotterdam")
        off = self.customer(MODULES_MARKER, "Telefonie uitgezet voor deze klant: geen calculator, de offerte is bewaard.",
                            login=True)
        quote(off, "Oude offerte")
        TelephonyCustomer.objects.create(customer=off, enabled=False)

        archive = self.customer("Printing Archief BV", "Heeft een oude offerte en een contract in het printing-archief.")
        printer = Printer.objects.create(name="Voorbeeldprinter 4000", product_nr="VP4000", vendor=Vendor.objects.first(),
                                         price=Decimal("899"), color=True)
        old_quote = PrintQuote.objects.create(number="DEMO-1", customer=archive, reference="Kantoorprinters",
                                              created_at=timezone.now() - datetime.timedelta(days=4000))
        PrintQuoteLine.objects.create(quote=old_quote, printer=printer)
        PrintContract.objects.create(number="DEMO-C1", quote=old_quote, customer=archive, company="Eindklant Voorbeeld",
                                     start_date=self.today - datetime.timedelta(days=4000),
                                     end_date=self.today - datetime.timedelta(days=2500))

    def build(self):
        self.customer("Alleen Gegevens BV", "Alleen bedrijfsgegevens: geen contactpersoon, aankopen, licenties of CMDB.", contact=False)
        if not SupportPack.objects.exists():
            call_command("load_demo_catalogue", licences=0, stdout=self.stdout)
        self.pack = SupportPack.objects.first()
        self.types = {t.name_en: t for t in ItemType.objects.all()}
        self.statuses = {s.key: s for s in ItemStatus.objects.all()}
        self.kinds = {k.key: k for k in RelationKind.objects.all()}

        settings_ = CmdbSettings.load()
        settings_.enabled = True
        settings_.warranty_mail_enabled = True
        settings_.warranty_mail_to = f"beheer@{DOMAIN}"
        settings_.save()

        # Not (yet) a normal customer
        self.customer("Contact Zonder Login BV", "Contactpersoon zonder login; verder niets.")
        pending = self.customer("Aanmelding Wacht BV", "Heeft zich aangemeld en wacht op goedkeuring.", status=Customer.Status.PENDING, login=True)
        pending.signup_message = "Wij willen graag servicepacks bestellen."
        pending.save()
        blocked = self.customer("Geblokkeerd BV", "Geblokkeerd, met een oude bestelling en licentie.", login=True)
        self.pack_order(blocked, paid=True)
        self.licence(blocked)
        blocked.block()

        # Licences, with and without purchases
        lic = self.customer("Licentie Zonder Aankoop BV", "Licenties maar geen bestelling hier: geregistreerd, niet geregistreerd en verlopen.", login=True)
        self.licence(lic)
        self.licence(lic, "unregistered")
        self.licence(lic, "ended")
        pack_buyer = self.customer("Servicepack Koper BV", "Servicepack gekocht: bestelling, betaalde factuur en licenties; geen CMDB.", login=True)
        self.register_order_licences(self.pack_order(pack_buyer, paid=True, quantity=2))
        unregistered = self.customer("Servicepack Niet Geregistreerd BV", "Servicepack gekocht, factuur open, licentie nog niet geregistreerd.")
        self.pack_order(unregistered)
        reseller = self.customer("Reseller Zonder Factuur BV", "Reseller zonder factuur voor servicepacks; bestelling zonder factuur.",
                                 type_name="Reseller", no_pack_invoice=True, margin_packs=Decimal("10"))
        self.register_order_licences(self.pack_order(reseller, invoice=False, quantity=3))

        # Other purchases, without licences
        self.hardware_order(self.customer("Hardware Koper BV", "Alleen een apparaat gekocht; factuur open; geen licentie.", login=True))
        self.part_order(self.customer("Onderdelen Koper BV", "Alleen onderdelen gekocht; nog te leveren; geen licentie.", login=True))
        self.part_request(self.customer("Onderdelen Aanvraag BV", "Alleen een onderdelenaanvraag, nog niet beantwoord; geen aankoop."))

        # Faults
        self.fault(self.customer("Storing Zonder Licentie BV", "Storing gemeld zonder licentie; geen aankopen."))
        covered = self.customer("Storing Met Licentie BV", "Licentie met een storing erop.")
        self.fault(covered, self.licence(covered))

        # CMDB, with and without the rest
        only = self.customer("CMDB Zonder Aankopen BV", "Gebruikt alleen de CMDB: geen aankopen of licenties; geen login.")
        self.cmdb(only)
        self.landscape(only)
        with_lic = self.customer("CMDB Met Licenties BV", "CMDB met meekijken na inloggen, plus licenties; geen aankopen.", login=True)
        self.cmdb(with_lic, portal=True)
        lic_item = self.licence(with_lic)
        self.item(with_lic, "Testserver", manufacturer="Voorbeeldmerk", serial_nr=lic_item.serial_nr, warranty_days=700,
                  description="Interne opmerking die de klant niet ziet.")
        buy_cmdb = self.customer("CMDB Met Aankopen BV", "CMDB plus hardware-aankoop, zonder licenties en zonder meekijken.")
        self.cmdb(buy_cmdb)
        self.hardware_order(buy_cmdb, "Werkplek-pc")
        self.item(buy_cmdb, "Werkplek-pc receptie", warranty_days=300)
        self.cmdb(self.customer("CMDB Leeg BV", "CMDB aangezet, nog geen items."))
        off = self.customer("CMDB Uitgezet BV", "Had de CMDB; staat nu uit, dus de items zijn verborgen en bewaard.")
        self.cmdb(off)
        self.item(off, "Oude server")
        self.cmdb(off, enabled=False)
        guarantee = self.customer("Garantie Scenario BV", "Alle garantiesituaties; krijgt zelf ook garantiemails.")
        self.cmdb(guarantee, warranty=True)
        for name, days, status in [("Garantie verlopen", -10, "in_use"), ("Garantie over 10 dagen", 10, "in_use"),
                                   ("Garantie over 60 dagen", 60, "in_use"), ("Garantie over 200 dagen", 200, "in_use"),
                                   ("Buiten gebruik, garantie over 10 dagen", 10, "retired"),
                                   ("In reparatie, garantie over 25 dagen", 25, "in_repair"),
                                   ("Gepland, garantie over 80 dagen", 80, "planned"), ("Zonder garantiedatum", None, "in_use")]:
            self.item(guarantee, name, status=status, warranty_days=days)

        # Abroad, with discovery
        german = self.customer("Deutscher Kunde GmbH", "Klant in Duitsland met licentie, CMDB en automatisch ontdekken.", country="DE",
                               vat_number="DE000000000")
        self.licence(german)
        self.cmdb(german)
        known = self.item(german, "Dateiserver", serial_nr="DE-FILE-1", manufacturer="Beispiel", model="Alt")
        source = DiscoverySource(customer=german, name="Hauptsitz", item_type=self.types["Hardware"])
        source.new_token()
        source.save()
        discovery.report(source, {"items": [
            {"key": "DE-NEW-1", "name": "Neuer Server", "manufacturer": "Beispiel", "model": "R100", "serial_nr": "DE-NEW-1",
             "properties": {"ip_address": "198.51.100.5", "operating_system": "Linux"}},
            {"key": known.serial_nr, "name": known.name, "serial_nr": known.serial_nr, "model": "Neu",
             "properties": {"ip_address": "198.51.100.6"}},
            {"key": "aa:bb:cc:00:00:01", "name": "198.51.100.7", "properties": {"ip_address": "198.51.100.7", "mac_address": "aa:bb:cc:00:00:01"}},
        ]})
        DiscoveredItem.objects.filter(customer=german, key="aa:bb:cc:00:00:01").update(status=DiscoveredItem.Status.IGNORED)

        # Everything at once
        everything = self.customer(MARKER, "Alles: licenties, servicepack, hardware, onderdelen, storing, CMDB met meekijken en garantiemails.",
                                   type_name="Reseller", login=True, margin_packs=Decimal("5"))
        self.register_order_licences(self.pack_order(everything, paid=True, quantity=2))
        self.hardware_order(everything, "Testserver groot")
        self.part_order(everything)
        self.part_request(everything)
        self.fault(everything, self.licence(everything))
        self.licence(everything, "unregistered")
        self.cmdb(everything, portal=True, warranty=True)
        self.landscape(everything)
