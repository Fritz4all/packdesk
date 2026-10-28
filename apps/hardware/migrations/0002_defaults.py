"""Starting values for hardware; everything can be changed in the admin afterwards."""

from decimal import Decimal

from django.contrib.auth.management import create_permissions
from django.db import migrations

TYPES = [
    (0, {"nl": "Laptop", "en": "Laptop", "de": "Laptop"}),
    (1, {"nl": "Desktop", "en": "Desktop", "de": "Desktop"}),
    (2, {"nl": "Monitor", "en": "Monitor", "de": "Monitor"}),
    (3, {"nl": "Accessoire", "en": "Accessory", "de": "Zubehör"}),
]
CONDITIONS = [
    (0, {"nl": "Nieuw", "en": "New", "de": "Neu"},
     {"nl": "Nieuw en ongebruikt.", "en": "New and unused.", "de": "Neu und unbenutzt."}),
    (1, {"nl": "Refurbished A", "en": "Refurbished A", "de": "Refurbished A"},
     {"nl": "Gebruikt, nagekeken, nauwelijks gebruikssporen.", "en": "Used, checked, hardly any signs of use.",
      "de": "Gebraucht, geprüft, kaum Gebrauchsspuren."}),
    (2, {"nl": "Refurbished B", "en": "Refurbished B", "de": "Refurbished B"},
     {"nl": "Gebruikt, nagekeken, zichtbare gebruikssporen.", "en": "Used, checked, visible signs of use.",
      "de": "Gebraucht, geprüft, sichtbare Gebrauchsspuren."}),
]
DELIVERY = [
    (0, "pickup", "0", {"nl": "Ophalen", "en": "Pick up", "de": "Abholung"}),
    (1, "shipping", "12.50", {"nl": "Verzenden", "en": "Shipping", "de": "Versand"}),
]
# key, kind, unit, types (by position in TYPES), required, names
SPECS = [
    ("cpu", "text", "", [0, 1], False, {"nl": "Processor", "en": "Processor", "de": "Prozessor"}),
    ("ram_gb", "number", "GB", [0, 1], False, {"nl": "Werkgeheugen", "en": "Memory", "de": "Arbeitsspeicher"}),
    ("storage", "text", "", [0, 1], False, {"nl": "Opslag", "en": "Storage", "de": "Speicher"}),
    ("screen_inch", "number", "inch", [0, 2], False, {"nl": "Schermgrootte", "en": "Screen size", "de": "Bildschirmgröße"}),
    ("os", "text", "", [0, 1], False, {"nl": "Besturingssysteem", "en": "Operating system", "de": "Betriebssystem"}),
]
ADMIN_ROLE_MODELS = ["device", "devicephoto", "devicetype", "specification", "condition", "deliveryoption"]


def names(field, texts):
    return {field: texts["nl"], **{f"{field}_{lang}": text for lang, text in texts.items()}}


def add(apps, schema_editor):
    DeviceType = apps.get_model("hardware", "DeviceType")
    Condition = apps.get_model("hardware", "Condition")
    DeliveryOption = apps.get_model("hardware", "DeliveryOption")
    Specification = apps.get_model("hardware", "Specification")
    HardwareSettings = apps.get_model("hardware", "HardwareSettings")
    NumberSequence = apps.get_model("numbering", "NumberSequence")
    if not DeviceType.objects.exists():
        types = [DeviceType.objects.create(position=pos, **names("name", texts)) for pos, texts in TYPES]
        for position, (key, kind, unit, type_positions, required, texts) in enumerate(SPECS):
            spec = Specification.objects.create(key=key, kind=kind, unit=unit, required=required, position=position,
                                                **names("name", texts))
            spec.device_types.set([types[i] for i in type_positions])
    if not Condition.objects.exists():
        for pos, name, description in CONDITIONS:
            Condition.objects.create(position=pos, **names("name", name), **names("description", description))
    if not DeliveryOption.objects.exists():
        for pos, kind, price, texts in DELIVERY:
            DeliveryOption.objects.create(position=pos, kind=kind, price=Decimal(price), **names("name", texts))
    HardwareSettings.objects.get_or_create(pk=1, defaults={
        "intro_nl": "Nieuwe en refurbished laptops, desktops en monitoren, nagekeken en met garantie.",
        "intro_en": "New and refurbished laptops, desktops and monitors, checked and with warranty.",
        "intro_de": "Neue und generalüberholte Laptops, Desktops und Monitore, geprüft und mit Garantie.",
    })
    if not NumberSequence.objects.filter(key="hardware_device").exists():
        NumberSequence.objects.create(key="hardware_device", pattern="HW{nr:5}", next_number=1, name="Hardware",
                                      name_nl="Hardware (voorraadnummers)", name_en="Hardware (stock numbers)",
                                      name_de="Hardware (Lagernummern)")
    # Existing default roles get the hardware rights (new installations get them from roles.py).
    config = apps.get_app_config("hardware")
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    hardware = Permission.objects.filter(content_type__app_label="hardware")
    admin_codes = [f"{a}_{m}" for m in ADMIN_ROLE_MODELS for a in ("view", "add", "change", "delete")]
    admin_codes += ["view_hardwaresettings", "change_hardwaresettings"]
    for name, codes in (("Administrator", admin_codes), ("Employee", ["view_device"])):
        group = Group.objects.filter(name=name).first()
        if group is not None:
            group.permissions.add(*hardware.filter(codename__in=codes))


class Migration(migrations.Migration):
    dependencies = [("hardware", "0001_initial"), ("numbering", "0004_archive_help"), ("accounts", "0007_role_internal_names"),
                    ("auth", "0012_alter_user_first_name_max_length"), ("contenttypes", "0002_remove_content_type_name")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
