from django.db import migrations

# The three cards the home page showed before they became editable.
BLOCKS = [
    ("⟳", {
        "nl": ("Servicepacks", "Bestel ondersteuning voor servers, desktops, printers en meer, en verleng op tijd."),
        "en": ("Service packs", "Order support for servers, desktops, printers and more, and extend it on time."),
        "de": ("Servicepakete", "Bestellen Sie Support für Server, Desktops, Drucker und mehr und verlängern Sie ihn rechtzeitig."),
    }),
    ("✓", {
        "nl": ("Licentie registreren", "Koppel uw apparaat aan een licentie, zodat de ondersteuning direct ingaat."),
        "en": ("Register a licence", "Link your device to a licence so support starts right away."),
        "de": ("Lizenz registrieren", "Verknüpfen Sie Ihr Gerät mit einer Lizenz, damit der Support sofort beginnt."),
    }),
    ("⚙", {
        "nl": ("Onderdelen", "Vraag onderdelen aan, accepteer offertes en volg leveringen."),
        "en": ("Spare parts", "Request parts, accept quotes and follow deliveries."),
        "de": ("Ersatzteile", "Ersatzteile anfragen, Angebote annehmen und Lieferungen verfolgen."),
    }),
]


INTRO = {
    "nl": "Bestel en verleng hardware-servicepacks, registreer licenties en volg uw bestellingen – alles op één plek.",
    "en": "Order and extend hardware service packs, register licences and follow your orders – all in one place.",
    "de": "Hardware-Servicepakete bestellen und verlängern, Lizenzen registrieren und Bestellungen verfolgen – alles an einem Ort.",
}
MAINTENANCE = {
    "nl": "We voeren onderhoud uit. De site is zo snel mogelijk weer beschikbaar.",
    "en": "We are carrying out maintenance. The site will be back as soon as possible.",
    "de": "Wir führen Wartungsarbeiten durch. Die Website ist so bald wie möglich wieder verfügbar.",
}


def add_blocks(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    HomeBlock = apps.get_model("siteconfig", "HomeBlock")
    site, _ = SiteSettings.objects.get_or_create(pk=1)
    for field, texts in (("intro_text", INTRO), ("maintenance_message", MAINTENANCE)):
        if not getattr(site, f"{field}_nl"):
            setattr(site, field, texts["nl"])
            for lang, text in texts.items():
                setattr(site, f"{field}_{lang}", text)
    site.save()
    if HomeBlock.objects.filter(settings=site).exists():
        return
    for position, (icon, texts) in enumerate(BLOCKS):
        fields = {"title": texts["nl"][0], "text": texts["nl"][1]}
        for lang, (title, text) in texts.items():
            fields[f"title_{lang}"] = title
            fields[f"text_{lang}"] = text
        HomeBlock.objects.create(settings=site, icon=icon, position=position, **fields)


class Migration(migrations.Migration):
    dependencies = [("siteconfig", "0007_content_and_maintenance")]
    operations = [migrations.RunPython(add_blocks, migrations.RunPython.noop)]
