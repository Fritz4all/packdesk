from django.db import migrations

TEXTS = {
    "wizard_intro": {
        "nl": "Registreer uw servicepack met het licentienummer dat u bij uw bestelling heeft ontvangen. Daarna volgen de gegevens van de eindklant en het apparaat.",
        "en": "Register your service pack with the licence number you received with your order. Next you enter the details of the end customer and the device.",
        "de": "Registrieren Sie Ihr Servicepaket mit der Lizenznummer aus Ihrer Bestellung. Danach folgen die Daten des Endkunden und des Geräts.",
    },
    "wizard_done": {
        "nl": "Hartelijk dank voor de registratie. Het servicecertificaat is per e-mail verstuurd.",
        "en": "Thank you for registering. The service certificate has been sent by email.",
        "de": "Vielen Dank für die Registrierung. Das Servicezertifikat wurde per E-Mail versendet.",
    },
    "contact_text": {
        "nl": "Deze licentie kan niet online worden geregistreerd. Neem contact met ons op, dan regelen wij de registratie.",
        "en": "This licence cannot be registered online. Please contact us and we will arrange the registration.",
        "de": "Diese Lizenz kann nicht online registriert werden. Bitte kontaktieren Sie uns, wir übernehmen die Registrierung.",
    },
}


def add(apps, schema_editor):
    LicenceSettings = apps.get_model("licences", "LicenceSettings")
    OptionType = apps.get_model("licences", "OptionType")
    NumberSequence = apps.get_model("numbering", "NumberSequence")
    obj, _ = LicenceSettings.objects.get_or_create(pk=1)
    for field, texts in TEXTS.items():
        setattr(obj, field, texts["nl"])
        for lang, text in texts.items():
            setattr(obj, f"{field}_{lang}", text)
    obj.save()
    if not OptionType.objects.filter(is_monitor=True).exists():
        OptionType.objects.create(name="Monitor", name_nl="Beeldscherm", name_en="Monitor", name_de="Monitor",
                                  internal=False, is_monitor=True)
    # Same format as the previous webshop: two-digit year + letter + 4 digits (26A0001), restarting every year.
    NumberSequence.objects.filter(key="licence", pattern="{nr}").update(pattern="{yy}{block:4}", reset_yearly=True)


class Migration(migrations.Migration):
    dependencies = [("licences", "0001_initial"), ("numbering", "0002_default_sequences")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
