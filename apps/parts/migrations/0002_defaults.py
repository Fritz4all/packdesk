from decimal import Decimal

from django.db import migrations

# Taken from the previous webshop; everything can be changed in the admin afterwards.
DELIVERY_TIMES = [
    ("in_stock", 0, {"nl": "Op voorraad", "en": "In stock", "de": "Auf Lager"}),
    ("days_2_5", 1, {"nl": "2 tot 5 werkdagen", "en": "2 to 5 working days", "de": "2 bis 5 Werktage"}),
    ("days_6_10", 2, {"nl": "6 tot 10 werkdagen", "en": "6 to 10 working days", "de": "6 bis 10 Werktage"}),
    ("weeks_2_more", 3, {"nl": "Minimaal 2 weken", "en": "At least 2 weeks", "de": "Mindestens 2 Wochen"}),
    ("see_remark", 4, {"nl": "Zie opmerking", "en": "See remark", "de": "Siehe Bemerkung"}),
]
PAYMENT_METHODS = [
    ("on_account", 0, True, {"nl": "Op rekening", "en": "On account", "de": "Auf Rechnung"}),
    ("cash_on_delivery", 1, False, {"nl": "Onder rembours", "en": "Cash on delivery", "de": "Nachnahme"}),
    ("proforma", 2, False, {"nl": "Proforma factuur", "en": "Pro forma invoice", "de": "Proforma-Rechnung"}),
    ("ideal", 3, False, {"nl": "iDEAL", "en": "iDEAL", "de": "iDEAL"}),
    ("bank_transfer", 4, False, {"nl": "Telefonisch overboeken", "en": "Bank transfer by phone",
                                 "de": "Telefonische Überweisung"}),
]
MARKUP = [("0", "2.00"), ("19", "1.70"), ("39", "1.50"), ("69", "1.40"), ("299", "1.35"), ("999", "1.30")]


def add(apps, schema_editor):
    DeliveryTime = apps.get_model("parts", "DeliveryTime")
    PaymentMethod = apps.get_model("parts", "PaymentMethod")
    MarkupTier = apps.get_model("parts", "MarkupTier")
    NumberSequence = apps.get_model("numbering", "NumberSequence")
    for code, position, names in DELIVERY_TIMES:
        DeliveryTime.objects.get_or_create(code=code, defaults={
            "position": position, "name": names["nl"], **{f"name_{k}": v for k, v in names.items()}})
    for code, position, on_account, names in PAYMENT_METHODS:
        PaymentMethod.objects.get_or_create(code=code, defaults={
            "position": position, "on_account": on_account, "name": names["nl"],
            **{f"name_{k}": v for k, v in names.items()}})
    if not MarkupTier.objects.exists():
        for above, factor in MARKUP:
            MarkupTier.objects.create(above=Decimal(above), factor=Decimal(factor))
    if not NumberSequence.objects.filter(key="part_request").exists():
        NumberSequence.objects.create(
            key="part_request", pattern="WS{nr}{letters:2}", next_number=17000, name="Onderdelenaanvragen",
            name_nl="Onderdelenaanvragen", name_en="Spare parts requests", name_de="Ersatzteilanfragen")


class Migration(migrations.Migration):
    dependencies = [("parts", "0001_initial"), ("numbering", "0004_archive_help")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
