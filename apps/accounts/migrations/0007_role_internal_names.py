"""The default roles get English internal names; the names people see now come from RoleInfo per language
(filled in by roles.ensure_roles after migrating)."""

from django.db import migrations

RENAMED = {"Beheerder": "Administrator", "Financieel": "Finance", "Medewerker": "Employee"}


def rename(apps, schema_editor, mapping=RENAMED):
    Group = apps.get_model("auth", "Group")
    for old, new in mapping.items():
        if not Group.objects.filter(name=new).exists():
            Group.objects.filter(name=old).update(name=new)


def rename_back(apps, schema_editor):
    rename(apps, schema_editor, {new: old for old, new in RENAMED.items()})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_role_info")]
    operations = [migrations.RunPython(rename, rename_back)]
