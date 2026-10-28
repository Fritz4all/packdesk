"""Step 3 of 3 of moving payment methods to orders: the table gets the name of its new place, each method says
whether it is offered for spare parts and for hardware, and the rights that roles have on payment methods move
along (same rights, now under orders)."""

from django.db import migrations, models


def move_rights(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    old = ContentType.objects.filter(app_label="parts", model="paymentmethod").first()
    if old is None:
        return
    new = ContentType.objects.filter(app_label="orders", model="paymentmethod").first()
    if new is None:
        old.app_label = "orders"
        old.save()
        return
    for perm in Permission.objects.filter(content_type=old):  # both exist: roles keep the rights they had
        twin = Permission.objects.filter(content_type=new, codename=perm.codename).first()
        if twin is None:
            perm.content_type = new
            perm.save()
            continue
        for group in perm.group_set.all():
            group.permissions.add(twin)
        perm.delete()
    old.delete()


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_payment_method_moved"), ("parts", "0005_payment_method_moved"),
                    ("contenttypes", "0002_remove_content_type_name"), ("auth", "0012_alter_user_first_name_max_length")]
    operations = [
        migrations.AlterModelTable(name="paymentmethod", table=None),
        migrations.AddField(model_name="paymentmethod", name="for_parts",
                            field=models.BooleanField(default=True, verbose_name="for spare parts")),
        migrations.AddField(model_name="paymentmethod", name="for_hardware",
                            field=models.BooleanField(default=True, verbose_name="for hardware")),
        migrations.RunPython(move_rights, migrations.RunPython.noop),
    ]
