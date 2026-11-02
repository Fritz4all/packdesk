"""An installation that already holds printing data keeps seeing it, and the default roles get the new settings
permissions (new installations get them from roles.py)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

ARCHIVE = ["Printer", "Consumable", "SupportPlan", "PrintQuote", "PrintContract", "SuppliesOrder"]


def keep_existing_archive_visible(apps, schema_editor):
    if any(apps.get_model("printing", name).objects.exists() for name in ARCHIVE):
        apps.get_model("printing", "PrintingSettings").objects.update_or_create(pk=1, defaults={"enabled": True})


def grant(apps, schema_editor):
    from apps.accounts.roles import ROLES

    config = apps.get_app_config("printing")
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, codes in ROLES.items():
        group = Group.objects.filter(name=name).first()
        if group is None:
            continue
        codenames = [code.split(".")[1] for code in codes if code.startswith("printing.") and code.endswith("_printingsettings")]
        group.permissions.add(*Permission.objects.filter(content_type__app_label="printing", codename__in=codenames))


class Migration(migrations.Migration):
    dependencies = [("printing", "0003_module_switches"), ("auth", "0012_alter_user_first_name_max_length"),
                    ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunPython(keep_existing_archive_visible, migrations.RunPython.noop),
                  migrations.RunPython(grant, migrations.RunPython.noop)]
