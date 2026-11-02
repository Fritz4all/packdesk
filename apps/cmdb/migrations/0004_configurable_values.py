"""The starting values of what became configurable; everything can be changed in the admin afterwards."""

from django.db import migrations

FIELDS = [
    # key, mode, in the list, names
    ("customer", "required", True, {"nl": "Klant", "en": "Customer", "de": "Kunde"}),
    ("item_type", "required", True, {"nl": "Type", "en": "Type", "de": "Typ"}),
    ("name", "required", True, {"nl": "Naam", "en": "Name", "de": "Name"}),
    ("status", "required", True, {"nl": "Status", "en": "Status", "de": "Status"}),
    ("manufacturer", "optional", False, {"nl": "Fabrikant", "en": "Manufacturer", "de": "Hersteller"}),
    ("model", "optional", False, {"nl": "Model", "en": "Model", "de": "Modell"}),
    ("serial_nr", "optional", True, {"nl": "Serienummer", "en": "Serial number", "de": "Seriennummer"}),
    ("asset_tag", "optional", False, {"nl": "Inventarisnummer", "en": "Asset tag", "de": "Inventarnummer"}),
    ("location", "optional", True, {"nl": "Locatie", "en": "Location", "de": "Standort"}),
    ("contact", "optional", False, {"nl": "Contactpersoon", "en": "Contact", "de": "Ansprechpartner"}),
    ("description", "optional", False, {"nl": "Interne omschrijving", "en": "Internal description", "de": "Interne Beschreibung"}),
    ("purchase_date", "optional", False, {"nl": "Aankoopdatum", "en": "Purchase date", "de": "Kaufdatum"}),
    ("warranty_until", "optional", True, {"nl": "Garantie tot", "en": "Warranty until", "de": "Garantie bis"}),
    ("end_of_life", "optional", False, {"nl": "Einde levensduur", "en": "End of life", "de": "Lebensende"}),
]
STATUSES = [
    ("planned", "info", False, {"nl": "Gepland", "en": "Planned", "de": "Geplant"}),
    ("in_use", "success", False, {"nl": "In gebruik", "en": "In use", "de": "In Betrieb"}),
    ("in_repair", "warning", False, {"nl": "In reparatie", "en": "In repair", "de": "In Reparatur"}),
    ("retired", "danger", True, {"nl": "Buiten gebruik", "en": "Retired", "de": "Außer Betrieb"}),
]
KINDS = [
    ("depends_on", {"nl": "is afhankelijk van", "en": "depends on", "de": "hängt ab von"}),
    ("runs_on", {"nl": "draait op", "en": "runs on", "de": "läuft auf"}),
    ("connected_to", {"nl": "is verbonden met", "en": "is connected to", "de": "ist verbunden mit"}),
    ("part_of", {"nl": "is onderdeel van", "en": "is part of", "de": "ist Teil von"}),
    ("uses", {"nl": "gebruikt", "en": "uses", "de": "verwendet"}),
]
SUBJECT = {
    "nl": "Garantie loopt af: {count} item(s) van {customer}",
    "en": "Warranty running out: {count} item(s) of {customer}",
    "de": "Garantie läuft ab: {count} Element(e) von {customer}",
}
BODY = {
    "nl": "Beste {customer},\n\nDe garantie van deze items loopt binnenkort af:\n\n{items}\n\nNeem gerust contact met ons op als u wilt verlengen.\n\nMet vriendelijke groet,\n{company}",
    "en": "Dear {customer},\n\nThe warranty of these items runs out soon:\n\n{items}\n\nPlease contact us if you would like to extend it.\n\nKind regards,\n{company}",
    "de": "Sehr geehrte Damen und Herren von {customer},\n\ndie Garantie dieser Elemente läuft bald ab:\n\n{items}\n\nBitte wenden Sie sich an uns, wenn Sie sie verlängern möchten.\n\nMit freundlichen Grüßen\n{company}",
}
RIGHTS = ["itemfield", "itemstatus", "relationkind", "discoverysource", "discovereditem"]


def names(field, texts):
    return {field: texts["nl"], **{f"{field}_{lang}": text for lang, text in texts.items()}}


def add(apps, schema_editor):
    ItemField = apps.get_model("cmdb", "ItemField")
    ItemStatus = apps.get_model("cmdb", "ItemStatus")
    RelationKind = apps.get_model("cmdb", "RelationKind")
    Item = apps.get_model("cmdb", "ConfigurationItem")
    Relation = apps.get_model("cmdb", "Relation")
    ItemType = apps.get_model("cmdb", "ItemType")
    ItemProperty = apps.get_model("cmdb", "ItemProperty")
    CmdbSettings = apps.get_model("cmdb", "CmdbSettings")

    for position, (key, mode, in_list, texts) in enumerate(FIELDS):
        ItemField.objects.create(key=key, mode=mode, in_list=in_list, position=position, **names("name", texts))
    statuses = {key: ItemStatus.objects.create(key=key, colour=colour, out_of_use=out, position=position, **names("name", texts))
                for position, (key, colour, out, texts) in enumerate(STATUSES)}
    kinds = {key: RelationKind.objects.create(key=key, position=position, **names("name", texts))
             for position, (key, texts) in enumerate(KINDS)}
    for key, status in statuses.items():
        Item.objects.filter(old_status=key).update(status=status)
    for key, kind in kinds.items():
        Relation.objects.filter(old_kind=key).update(kind=kind)

    settings = CmdbSettings.objects.filter(pk=1).first() or CmdbSettings(pk=1)
    for lang in ("nl", "en", "de"):
        setattr(settings, f"warranty_subject_{lang}", SUBJECT[lang])
        setattr(settings, f"warranty_body_{lang}", BODY[lang])
    settings.warranty_subject, settings.warranty_body = SUBJECT["nl"], BODY["nl"]
    settings.save()

    if not ItemProperty.objects.filter(key="mac_address").exists():
        types = ItemType.objects.filter(name_en__in=["Hardware", "Network"])
        position = ItemProperty.objects.count()
        prop = ItemProperty.objects.create(key="mac_address", kind="text", position=position, **names(
            "name", {"nl": "MAC-adres", "en": "MAC address", "de": "MAC-Adresse"}))
        prop.item_types.set(types)

    # The existing default role gets the rights (new installations get them from roles.py).
    from django.contrib.auth.management import create_permissions

    config = apps.get_app_config("cmdb")
    config.models_module = True
    create_permissions(config, verbosity=0, apps=apps)
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    group = Group.objects.filter(name="Administrator").first()
    if group is not None:
        codes = [f"{a}_{m}" for m in RIGHTS for a in ("view", "add", "change", "delete")]
        group.permissions.add(*Permission.objects.filter(content_type__app_label="cmdb", codename__in=codes))


class Migration(migrations.Migration):
    dependencies = [("cmdb", "0003_configurable_discovery_warranty")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
