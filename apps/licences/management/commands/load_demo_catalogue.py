from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.customers.models import Customer, CustomerType
from apps.licences.models import (
    Category, HardwareClass, HardwareSystem, Licence, OptionType, SupportPack, SupportPeriod, SupportService, Vendor,
)


def tr(model, **names):
    """Create with the same value in base and nl/en/de fields where translations are given as tuples."""
    fields = {}
    for field, value in names.items():
        if isinstance(value, tuple):
            nl, en, de = value
            fields.update({field: nl, f"{field}_nl": nl, f"{field}_en": en, f"{field}_de": de})
        else:
            fields[field] = value
    return model.objects.create(**fields)


class Command(BaseCommand):
    help = "Create a small demo catalogue and demo licences (for trying out; not real data)."

    def add_arguments(self, parser):
        parser.add_argument("--licences", type=int, default=3, help="Demo licences per pack.")

    @transaction.atomic
    def handle(self, *args, **options):
        if SupportPack.objects.exists():
            self.stdout.write("Catalogue already has packs; nothing created.")
            return
        server = tr(Category, name=("Server Servicepack", "Server service pack", "Server-Servicepaket"), position=1)
        printer = tr(Category, name=("Laserprinter Servicepack", "Laser printer service pack", "Laserdrucker-Servicepaket"), position=2)
        disk = tr(OptionType, name=("Harde schijf", "Hard disk", "Festplatte"), internal=True)
        memory = tr(OptionType, name=("Geheugen", "Memory", "Arbeitsspeicher"), internal=True)
        tape = tr(OptionType, name=("Tapedrive", "Tape drive", "Bandlaufwerk"), internal=False)
        server.option_types.set([disk, memory, tape])
        class_a = tr(HardwareClass, name=("Server klasse A", "Server class A", "Server Klasse A"), position=1)
        class_p = tr(HardwareClass, name=("A4 kleur t/m 21 ppm", "A4 colour up to 21 ppm", "A4 Farbe bis 21 S./Min."), position=2)
        hp = Vendor.objects.create(name="HP", at_top=True, product_nr_regex=r"[A-Z0-9]{5,}(-[A-Z0-9]{3})?",
                                   product_nr_help="Bijvoorbeeld 826684-B21", product_nr_help_nl="Bijvoorbeeld 826684-B21",
                                   product_nr_help_en="For example 826684-B21", product_nr_help_de="Zum Beispiel 826684-B21")
        dell = Vendor.objects.create(name="Dell")
        for vendor, name in [(hp, "ProLiant DL380 Gen10"), (hp, "ProLiant ML350 Gen10"), (dell, "PowerEdge R740")]:
            HardwareSystem.objects.create(vendor=vendor, hardware_class=class_a, name=name, warranty_years=3)
        HardwareSystem.objects.create(vendor=hp, hardware_class=class_p, name="Color LaserJet Pro M454", warranty_years=1)
        three = SupportPeriod.objects.create(years=3)
        post = SupportPeriod.objects.create(years=1, post_warranty=True)
        nbd = tr(SupportService, abbreviation="NBD", name=("Op locatie", "On site", "Vor Ort"),
                 response=("volgende werkdag", "next business day", "nächster Werktag"))
        packs = [
            tr(SupportPack, code="SRV-A-3", category=server, hardware_class=class_a, service=nbd, period=three,
               price=Decimal("495.00"), max_internal_options=4, max_external_options=1,
               description=("Server klasse A, 3 jaar op locatie", "Server class A, 3 years on site", "Server Klasse A, 3 Jahre vor Ort")),
            tr(SupportPack, code="PRN-1-PW", category=printer, hardware_class=class_p, service=nbd, period=post,
               price=Decimal("129.00"),
               description=("Kleurenprinter, 1 jaar na garantie", "Colour printer, 1 year post-warranty", "Farbdrucker, 1 Jahr nach Garantie")),
        ]
        customer = Customer.objects.filter(status=Customer.Status.ACTIVE).first()
        if customer is None:
            customer = Customer.objects.create(name="Demo Reseller BV", status=Customer.Status.ACTIVE,
                                               customer_type=CustomerType.objects.filter(is_reseller=True).first())
            customer.assign_number()
            customer.save()
        created = []
        for pack in packs:
            created += Licence.create_for(pack, customer, options["licences"], order_reference="DEMO")
        self.stdout.write(self.style.SUCCESS(
            f"Demo catalogue created; licences for {customer.name}: " + ", ".join(lic.full_number for lic in created)
        ))
