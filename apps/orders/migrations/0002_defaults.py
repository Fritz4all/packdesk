from django.db import migrations

TEXTS = {
    "intro": {
        "nl": "Kies de servicepacks en het aantal. De prijzen zijn exclusief btw; uw korting wordt bij het controleren berekend.",
        "en": "Choose the service packs and the quantity. Prices exclude VAT; your discount is calculated when you check the order.",
        "de": "Wählen Sie die Servicepakete und die Anzahl. Preise zzgl. MwSt.; Ihr Rabatt wird bei der Prüfung berechnet.",
    },
    "terms_text": {
        "nl": "Op deze bestelling zijn onze algemene voorwaarden van toepassing.",
        "en": "Our general terms and conditions apply to this order.",
        "de": "Für diese Bestellung gelten unsere Allgemeinen Geschäftsbedingungen.",
    },
    "confirmation_text": {
        "nl": "Hartelijk dank voor uw bestelling. Hieronder vindt u de gegevens; de licentienummers kunt u gebruiken om de packs te registreren.",
        "en": "Thank you for your order. You will find the details below; use the licence numbers to register the packs.",
        "de": "Vielen Dank für Ihre Bestellung. Unten finden Sie die Details; mit den Lizenznummern registrieren Sie die Pakete.",
    },
}


def add(apps, schema_editor):
    OrderSettings = apps.get_model("orders", "OrderSettings")
    obj, _ = OrderSettings.objects.get_or_create(pk=1)
    for field, texts in TEXTS.items():
        setattr(obj, field, texts["nl"])
        for lang, text in texts.items():
            setattr(obj, f"{field}_{lang}", text)
    obj.save()


class Migration(migrations.Migration):
    dependencies = [("orders", "0001_initial")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
