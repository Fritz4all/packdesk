"""Catalogue items the import makes for references that no longer exist got a new name. Renames existing
ones, so a new import keeps using them."""

from django.db import migrations

OLD, NEW = "Onbekend (oude" " shop)", "Onbekend (vorige webshop)"  # the old name, split on purpose


def rename(apps, schema_editor):
    for model_name in ("Category", "HardwareClass", "Vendor"):
        model = apps.get_model("licences", model_name)
        fields = {f.name for f in model._meta.get_fields()}
        for field in [f for f in ("name", "name_nl", "name_en", "name_de") if f in fields]:
            model.objects.filter(**{field: OLD}).update(**{field: NEW})


class Migration(migrations.Migration):
    dependencies = [("legacy", "0003_importrun_importedrecord"), ("licences", "0006_licence_order_line")]
    operations = [migrations.RunPython(rename, migrations.RunPython.noop)]
