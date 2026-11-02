"""Starting values for the CMDB; everything can be changed in the admin afterwards."""

from django.contrib.auth.management import create_permissions
from django.db import migrations

TYPES = [
    (0, {"nl": "Hardware", "en": "Hardware", "de": "Hardware"}),
    (1, {"nl": "Software", "en": "Software", "de": "Software"}),
    (2, {"nl": "Virtuele machine", "en": "Virtual machine", "de": "Virtuelle Maschine"}),
    (3, {"nl": "Netwerk", "en": "Network", "de": "Netzwerk"}),
    (4, {"nl": "Dienst", "en": "Service", "de": "Dienst"}),
    (5, {"nl": "Locatie", "en": "Location", "de": "Standort"}),
]
# key, kind, types (by position in TYPES), names
PROPERTIES = [
    ("ip_address", "text", [0, 2, 3], {"nl": "IP-adres", "en": "IP address", "de": "IP-Adresse"}),
    ("operating_system", "text", [0, 2], {"nl": "Besturingssysteem", "en": "Operating system", "de": "Betriebssystem"}),
    ("version", "text", [1], {"nl": "Versie", "en": "Version", "de": "Version"}),
]
ADMIN_ROLE_MODELS = ["configurationitem", "relation", "cmdbcustomer", "itemtype", "itemproperty"]


def names(field, texts):
    return {field: texts["nl"], **{f"{field}_{lang}": text for lang, text in texts.items()}}


def add(apps, schema_editor):
    ItemType = apps.get_model("cmdb", "ItemType")
    ItemProperty = apps.get_model("cmdb", "ItemProperty")
    NumberSequence = apps.get_model("numbering", "NumberSequence")
    if not ItemType.objects.exists():
        types = [ItemType.objects.create(position=pos, **names("name", texts)) for pos, texts in TYPES]
        for position, (key, kind, type_positions, texts) in enumerate(PROPERTIES):
            prop = ItemProperty.objects.create(key=key, kind=kind, position=position, **names("name", texts))
            prop.item_types.set([types[i] for i in type_positions])
    if not NumberSequence.objects.filter(key="cmdb").exists():
        NumberSequence.objects.create(key="cmdb", pattern="CI-{nr:5}", next_number=1, name="CMDB",
                                      name_nl="CMDB (itemnummers)", name_en="CMDB (item numbers)",
                                      name_de="CMDB (Elementnummern)")
    # The existing default role gets the CMDB rights (new installations get them from roles.py).
    config = apps.get_app_config("cmdb")
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    codes = [f"{a}_{m}" for m in ADMIN_ROLE_MODELS for a in ("view", "add", "change", "delete")]
    codes += ["export_configurationitem", "import_configurationitem", "view_cmdbsettings", "change_cmdbsettings"]
    group = Group.objects.filter(name="Administrator").first()
    if group is not None:
        group.permissions.add(*Permission.objects.filter(content_type__app_label="cmdb", codename__in=codes))


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0001_initial"), ("numbering", "0004_archive_help"), ("accounts", "0007_role_internal_names"),
                    ("auth", "0012_alter_user_first_name_max_length"), ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
