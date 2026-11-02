from django.db import migrations, models

NAMES = {"info": "blue", "success": "green", "warning": "orange", "danger": "red"}


def rename(apps, schema_editor):
    ItemStatus = apps.get_model("cmdb", "ItemStatus")
    for old, new in NAMES.items():
        ItemStatus.objects.filter(colour=old).update(colour=new)


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0006_own_fields")]
    operations = [
        migrations.AlterField(
            model_name="itemstatus",
            name="colour",
            field=models.CharField(
                choices=[("grey", "Grey"), ("brown", "Brown"), ("red", "Red"), ("orange", "Orange"), ("yellow", "Yellow"),
                         ("lime", "Lime"), ("green", "Green"), ("teal", "Teal"), ("blue", "Blue"), ("indigo", "Indigo"),
                         ("purple", "Purple"), ("pink", "Pink")],
                default="blue", max_length=8, verbose_name="colour"),
        ),
        migrations.RunPython(rename, migrations.RunPython.noop),
    ]
