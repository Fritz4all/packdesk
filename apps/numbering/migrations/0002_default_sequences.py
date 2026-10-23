from django.db import migrations

SEQUENCES = [
    ("invoice", {"nl": "Facturen", "en": "Invoices", "de": "Rechnungen"}, "{nr}", r"invoice_(\d+)\.pdf"),
    ("quote", {"nl": "Offertes", "en": "Quotes", "de": "Angebote"}, "{nr}", ""),
    ("order", {"nl": "Orders", "en": "Orders", "de": "Aufträge"}, "{nr}", ""),
    ("licence", {"nl": "Licenties", "en": "Licences", "de": "Lizenzen"}, "{nr}", ""),
    ("customer", {"nl": "Klanten (debiteurnummers)", "en": "Customers (account numbers)", "de": "Kunden (Debitorennummern)"}, "{nr}", ""),
    ("ticket", {"nl": "Storingsmeldingen", "en": "Fault reports", "de": "Störungsmeldungen"}, "{nr}", ""),
]


def add(apps, schema_editor):
    NumberSequence = apps.get_model("numbering", "NumberSequence")
    for key, names, pattern, regex in SEQUENCES:
        if NumberSequence.objects.filter(key=key).exists():
            continue
        NumberSequence.objects.create(
            key=key, pattern=pattern, archive_regex=regex, name=names["nl"],
            name_nl=names["nl"], name_en=names["en"], name_de=names["de"],
        )


class Migration(migrations.Migration):
    dependencies = [("numbering", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
