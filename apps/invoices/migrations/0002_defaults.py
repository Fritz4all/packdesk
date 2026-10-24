from django.db import migrations

TEXTS = {
    "payment_text": {
        "nl": "Wij verzoeken u het bedrag binnen {days} dagen, uiterlijk op {due_date}, over te maken op {iban} onder vermelding van factuurnummer {number}.",
        "en": "Please pay the amount within {days} days, no later than {due_date}, to {iban}, quoting invoice number {number}.",
        "de": "Bitte überweisen Sie den Betrag innerhalb von {days} Tagen, spätestens bis {due_date}, auf {iban} unter Angabe der Rechnungsnummer {number}.",
    },
    "email_subject": {"nl": "Factuur {number} van {company}", "en": "Invoice {number} from {company}", "de": "Rechnung {number} von {company}"},
    "email_body": {
        "nl": "Geachte relatie,\n\nIn de bijlage vindt u factuur {number} ({total}).\n\nMet vriendelijke groet,\n{company}",
        "en": "Dear customer,\n\nPlease find attached invoice {number} ({total}).\n\nKind regards,\n{company}",
        "de": "Sehr geehrte Damen und Herren,\n\nim Anhang finden Sie die Rechnung {number} ({total}).\n\nMit freundlichen Grüßen\n{company}",
    },
}


def add(apps, schema_editor):
    InvoiceSettings = apps.get_model("invoices", "InvoiceSettings")
    obj, _ = InvoiceSettings.objects.get_or_create(pk=1)
    for field, texts in TEXTS.items():
        setattr(obj, field, texts["nl"])
        for lang, text in texts.items():
            setattr(obj, f"{field}_{lang}", text)
    obj.save()


class Migration(migrations.Migration):
    dependencies = [("invoices", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
