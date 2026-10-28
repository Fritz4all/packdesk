"""A link to the hardware shop in the website menu (can be changed or switched off under Settings → Menu)."""

from django.db import migrations

LABELS = {"nl": "Hardware", "en": "Hardware", "de": "Hardware"}


def add(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    MenuItem = apps.get_model("siteconfig", "MenuItem")
    site = SiteSettings.objects.order_by("pk").first()
    if site is None or MenuItem.objects.filter(url="/hardware/").exists():
        return
    position = max([item.position for item in MenuItem.objects.filter(settings=site)] or [0]) + 1
    MenuItem.objects.create(settings=site, url="/hardware/", position=position, visibility="all", is_active=True,
                            label=LABELS["nl"], **{f"label_{lang}": text for lang, text in LABELS.items()})


class Migration(migrations.Migration):
    dependencies = [("hardware", "0003_shop_display"), ("siteconfig", "0017_max_superadmins")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
