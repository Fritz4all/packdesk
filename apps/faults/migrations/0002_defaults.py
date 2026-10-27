from django.db import migrations

OPTIONS = [
    {"nl": "Op locatie van het defecte apparaat", "en": "At the location of the faulty device", "de": "Vor Ort beim defekten Gerät"},
    {"nl": "Aanleveren bij ons", "en": "Bring it to us", "de": "Bei uns anliefern"},
    {"nl": "Vervangend onderdeel opsturen (zonder engineer)", "en": "Send a replacement part (no engineer)",
     "de": "Ersatzteil zusenden (ohne Techniker)"},
]
TEXTS = {
    "intro": {
        "nl": "Meld hier een hardwarestoring. Heeft u een licentie- of serienummer? Vul dat in, dan vullen wij het apparaat in en zien we direct of het onder contract valt.",
        "en": "Report a hardware fault here. Do you have a licence or serial number? Enter it and we fill in the device and see right away whether it is covered.",
        "de": "Melden Sie hier eine Hardwarestörung. Haben Sie eine Lizenz- oder Seriennummer? Geben Sie sie ein, dann ergänzen wir das Gerät und sehen sofort, ob es abgedeckt ist.",
    },
    "thanks": {
        "nl": "Bedankt voor uw melding. U ontvangt een bevestiging per e-mail; wij nemen zo snel mogelijk contact met u op.",
        "en": "Thank you for your report. You will receive a confirmation by email; we will contact you as soon as possible.",
        "de": "Vielen Dank für Ihre Meldung. Sie erhalten eine Bestätigung per E-Mail; wir melden uns so schnell wie möglich.",
    },
    "confirmation_subject": {
        "nl": "Ontvangstbevestiging storingsmelding {number}",
        "en": "Confirmation of fault report {number}",
        "de": "Eingangsbestätigung Störungsmeldung {number}",
    },
    "confirmation_body": {
        "nl": "Geachte {name},\n\nHartelijk dank voor uw melding. Wij hebben deze ontvangen onder nummer {number}.\nStoringen onder contract of garantie hebben voorrang. Hebben wij meer informatie nodig, dan nemen wij contact met u op.\n\nMet vriendelijke groet,\n{company}",
        "en": "Dear {name},\n\nThank you for your report. We have received it under number {number}.\nFaults under contract or warranty have priority. If we need more information, we will contact you.\n\nKind regards,\n{company}",
        "de": "Sehr geehrte(r) {name},\n\nvielen Dank für Ihre Meldung. Wir haben sie unter der Nummer {number} erhalten.\nStörungen mit Vertrag oder Garantie haben Vorrang. Falls wir weitere Informationen benötigen, melden wir uns.\n\nMit freundlichen Grüßen\n{company}",
    },
}


def add(apps, schema_editor):
    RepairOption = apps.get_model("faults", "RepairOption")
    FaultSettings = apps.get_model("faults", "FaultSettings")
    HomeBlock = apps.get_model("siteconfig", "HomeBlock")
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    if not RepairOption.objects.exists():
        for position, names in enumerate(OPTIONS):
            RepairOption.objects.create(position=position, name=names["nl"], name_nl=names["nl"],
                                        name_en=names["en"], name_de=names["de"])
    obj, _ = FaultSettings.objects.get_or_create(pk=1)
    for field, texts in TEXTS.items():
        setattr(obj, field, texts["nl"])
        for lang, text in texts.items():
            setattr(obj, f"{field}_{lang}", text)
    obj.save()
    site, _ = SiteSettings.objects.get_or_create(pk=1)
    if not HomeBlock.objects.filter(link_url="/report-fault/").exists():
        HomeBlock.objects.create(
            settings=site, icon="🛠", position=3, link_url="/report-fault/",
            title="Storing melden", title_nl="Storing melden", title_en="Report a fault", title_de="Störung melden",
            text="Meld een hardwarestoring en volg de afhandeling.",
            text_nl="Meld een hardwarestoring en volg de afhandeling.",
            text_en="Report a hardware fault and follow its handling.",
            text_de="Melden Sie eine Hardwarestörung und verfolgen Sie die Bearbeitung.",
            link_text="Storing melden", link_text_nl="Storing melden", link_text_en="Report a fault", link_text_de="Störung melden",
        )


class Migration(migrations.Migration):
    dependencies = [("faults", "0001_initial"), ("siteconfig", "0008_default_home_blocks")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
