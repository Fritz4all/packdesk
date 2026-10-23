from django.db import migrations

TYPES = [
    ({"nl": "Reseller", "en": "Reseller", "de": "Reseller"}, True),
    ({"nl": "Distributeur", "en": "Distributor", "de": "Distributor"}, False),
    ({"nl": "Leverancier", "en": "Vendor", "de": "Hersteller"}, False),
    ({"nl": "Eindklant", "en": "End customer", "de": "Endkunde"}, False),
]
COUNTRIES = [
    ("NL", {"nl": "Nederland", "en": "Netherlands", "de": "Niederlande"}, False),
    ("BE", {"nl": "België", "en": "Belgium", "de": "Belgien"}, True),
    ("LU", {"nl": "Luxemburg", "en": "Luxembourg", "de": "Luxemburg"}, True),
    ("DE", {"nl": "Duitsland", "en": "Germany", "de": "Deutschland"}, True),
]


def add(apps, schema_editor):
    CustomerType = apps.get_model("customers", "CustomerType")
    Country = apps.get_model("customers", "Country")
    if not CustomerType.objects.exists():
        for position, (names, reseller) in enumerate(TYPES):
            CustomerType.objects.create(
                name=names["nl"], name_nl=names["nl"], name_en=names["en"], name_de=names["de"],
                is_reseller=reseller, position=position,
            )
    if not Country.objects.exists():
        for position, (code, names, vat) in enumerate(COUNTRIES):
            Country.objects.create(
                code=code, name=names["nl"], name_nl=names["nl"], name_en=names["en"], name_de=names["de"],
                vat_number_required=vat, position=position,
            )


class Migration(migrations.Migration):
    dependencies = [("customers", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
