"""Give the existing default roles the telephony permissions (new installations get them from roles.py)."""

from django.contrib.auth.management import create_permissions
from django.db import migrations


def grant(apps, schema_editor):
    from apps.accounts.roles import ROLES

    config = apps.get_app_config("telephony")
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    for name, codes in ROLES.items():
        group = Group.objects.filter(name=name).first()
        if group is None:
            continue
        codenames = [code.split(".")[1] for code in codes if code.startswith("telephony.")]
        group.permissions.add(*Permission.objects.filter(content_type__app_label="telephony", codename__in=codenames))


class Migration(migrations.Migration):
    dependencies = [("telephony", "0001_initial"), ("auth", "0012_alter_user_first_name_max_length"),
                    ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
