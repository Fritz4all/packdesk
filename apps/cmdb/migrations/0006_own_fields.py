"""Own fields move to the list of fields, so that all fields of an item are in one place."""

import django.core.validators
from django.db import migrations, models


def move(apps, schema_editor):
    ItemField = apps.get_model("cmdb", "ItemField")
    ItemProperty = apps.get_model("cmdb", "ItemProperty")
    start = ItemField.objects.count()
    for prop in ItemProperty.objects.order_by("position", "name"):
        field = ItemField.objects.create(
            key=prop.key, name=prop.name, name_nl=prop.name_nl, name_en=prop.name_en, name_de=prop.name_de, kind=prop.kind,
            choices=prop.choices, mode="required" if prop.required else "optional", position=start + prop.position)
        field.item_types.set(prop.item_types.all())
    apps.get_model("auth", "Permission").objects.filter(content_type__app_label="cmdb",
                                                        content_type__model="itemproperty").delete()


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0005_configurable_finish"), ("auth", "0012_alter_user_first_name_max_length"),
                    ("contenttypes", "0002_remove_content_type_name")]
    operations = [
        migrations.AlterField(
            model_name="itemfield",
            name="key",
            field=models.CharField(
                blank=True, max_length=40, unique=True, verbose_name="code",
                help_text="Internal code, also the column name in import files, e.g. ip_address. Empty: made from the name.",
                validators=[django.core.validators.RegexValidator("^[a-z][a-z0-9_]*$", "Lower case letters, digits and _ only.")]),
        ),
        migrations.AddField(
            model_name="itemfield",
            name="kind",
            field=models.CharField(choices=[("text", "Text"), ("number", "Number"), ("choice", "Choice from a list"),
                                            ("yes_no", "Yes / no")], default="text", max_length=10, verbose_name="kind"),
        ),
        migrations.AddField(
            model_name="itemfield",
            name="choices",
            field=models.TextField(blank=True, help_text="For a choice from a list: one option per line.", verbose_name="choices"),
        ),
        migrations.AddField(
            model_name="itemfield",
            name="item_types",
            field=models.ManyToManyField(blank=True, related_name="own_fields", to="cmdb.itemtype", verbose_name="item types"),
        ),
        migrations.RunPython(move, migrations.RunPython.noop),
        migrations.DeleteModel(name="ItemProperty"),
    ]
