"""Home page: one card for service packs and spare parts together, and a new card for hardware.

Only cards that still have their standard wording are changed; cards someone has edited are left alone
(the hardware card is then still added)."""

from django.db import migrations

PACKS_EN, PARTS_EN = "Service packs", "Spare parts"
COMBINED = {
    "nl": ("Servicepacks en onderdelen", "Bestel en verleng ondersteuning voor servers, desktops, printers en meer, "
                                          "en vraag onderdelen aan."),
    "en": ("Service packs and spare parts", "Order and extend support for servers, desktops, printers and more, "
                                            "and request spare parts."),
    "de": ("Servicepakete und Ersatzteile", "Bestellen und verlängern Sie Support für Server, Desktops, Drucker und "
                                            "mehr, und fragen Sie Ersatzteile an."),
}
HARDWARE = {
    "nl": ("Hardware", "Nieuwe en refurbished laptops, desktops en monitoren, nagekeken en met garantie.",
           "Bekijk het aanbod"),
    "en": ("Hardware", "New and refurbished laptops, desktops and monitors, checked and with warranty.",
           "View what is for sale"),
    "de": ("Hardware", "Neue und generalüberholte Laptops, Desktops und Monitore, geprüft und mit Garantie.",
           "Angebot ansehen"),
}


def change(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    HomeBlock = apps.get_model("siteconfig", "HomeBlock")
    site = SiteSettings.objects.order_by("pk").first()
    if site is None:
        return
    blocks = HomeBlock.objects.filter(settings=site)
    packs = blocks.filter(title_en=PACKS_EN).first()
    parts = blocks.filter(title_en=PARTS_EN).first()
    hardware_position = parts.position if parts else max([b.position for b in blocks] or [0]) + 1
    if packs and parts:
        packs.title = COMBINED["nl"][0]
        packs.text = COMBINED["nl"][1]
        for lang, (title, text) in COMBINED.items():
            setattr(packs, f"title_{lang}", title)
            setattr(packs, f"text_{lang}", text)
        packs.save()
        parts.delete()
    if not blocks.filter(link_url="/hardware/").exists():
        HomeBlock.objects.create(
            settings=site, icon="🖥", link_url="/hardware/", position=hardware_position, visibility="all",
            title=HARDWARE["nl"][0], text=HARDWARE["nl"][1], link_text=HARDWARE["nl"][2],
            **{f"{field}_{lang}": texts[i] for lang, texts in HARDWARE.items()
               for i, field in enumerate(("title", "text", "link_text"))},
        )


class Migration(migrations.Migration):
    dependencies = [("hardware", "0004_menu_item"), ("siteconfig", "0017_max_superadmins")]
    operations = [migrations.RunPython(change, migrations.RunPython.noop)]
