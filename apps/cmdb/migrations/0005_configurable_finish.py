import django.db.models.deletion
from django.db import migrations, models

import apps.cmdb.models


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0004_configurable_values")]
    operations = [
        migrations.RemoveField(model_name="configurationitem", name="old_status"),
        migrations.RemoveField(model_name="relation", name="old_kind"),
        migrations.AlterField(
            model_name="configurationitem",
            name="status",
            field=models.ForeignKey(default=apps.cmdb.models.default_status,
                                    on_delete=django.db.models.deletion.PROTECT, related_name="items",
                                    to="cmdb.itemstatus", verbose_name="status"),
        ),
        migrations.AlterField(
            model_name="relation",
            name="kind",
            field=models.ForeignKey(default=apps.cmdb.models.default_relation_kind,
                                    on_delete=django.db.models.deletion.PROTECT, related_name="relations",
                                    to="cmdb.relationkind", verbose_name="relation"),
        ),
        migrations.AddConstraint(
            model_name="relation",
            constraint=models.UniqueConstraint(fields=("source", "kind", "target"), name="cmdb_one_relation_of_a_kind"),
        ),
    ]
