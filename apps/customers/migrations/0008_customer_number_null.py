"""Customer number: empty becomes NULL and the field itself is unique.

Replaces the conditional unique constraint, which MariaDB/MySQL do not support.
"""

from django.db import migrations, models


def empty_to_null(apps, schema_editor):
    apps.get_model("customers", "Customer").objects.filter(number="").update(number=None)


def null_to_empty(apps, schema_editor):
    apps.get_model("customers", "Customer").objects.filter(number__isnull=True).update(number="")


class Migration(migrations.Migration):
    dependencies = [("customers", "0007_export_import_permissions")]

    operations = [
        migrations.RemoveConstraint(model_name="customer", name="unique_customer_number"),
        migrations.AlterField(
            model_name="customer", name="number",
            field=models.CharField(blank=True, db_index=True, max_length=32, null=True, verbose_name="customer number",
                                   help_text="Account number (debtor number). Filled in automatically on approval if left empty."),
        ),
        migrations.RunPython(empty_to_null, null_to_empty),
        migrations.AlterField(
            model_name="customer", name="number",
            field=models.CharField(blank=True, max_length=32, null=True, unique=True, verbose_name="customer number",
                                   help_text="Account number (debtor number). Filled in automatically on approval if left empty."),
        ),
    ]
