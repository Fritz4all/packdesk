"""The history of an item: compare before and after a save, and add a line per field that changed."""

from django.utils.translation import gettext as _

from .models import ConfigurationItem, ItemChange, ItemProperty, Relation

TRACKED = ["customer", "item_type", "name", "status", "manufacturer", "model", "serial_nr", "asset_tag", "location",
           "contact", "purchase_date", "warranty_until", "end_of_life", "description"]


def snapshot(item):
    """{field label: value as text} of an item as it is now on the object."""
    values = {}
    for name in TRACKED:
        field = ConfigurationItem._meta.get_field(name)
        if field.is_relation:
            value = str(getattr(item, name)) if getattr(item, field.attname) else ""
        elif field.choices:
            value = str(getattr(item, f"get_{name}_display")())
        else:
            value = getattr(item, name)
            value = "" if value is None else str(value)
        values[str(field.verbose_name).capitalize()] = value
    properties = {p.key: p for p in ItemProperty.objects.all()}
    for key, value in (item.properties or {}).items():
        prop = properties.get(key)
        values[prop.name if prop else key] = prop.display(value) if prop else str(value)
    return values


def relation_texts(item):
    return sorted(f"{r.get_kind_display()} {r.target}" for r in item.relations_out.select_related("target"))


def record(item, before, user, source=ItemChange.Source.ADMIN):
    """Add history lines for what differs from `before` (None for an item that was just made)."""
    if before is None:
        ItemChange.objects.create(item=item, user=user, source=source, field=_("Created"), new_value=str(item))
        return
    after = snapshot(item)
    ItemChange.objects.bulk_create([
        ItemChange(item=item, user=user, source=source, field=label[:120],
                   old_value=before.get(label, ""), new_value=after.get(label, ""))
        for label in [*before, *[k for k in after if k not in before]]
        if before.get(label, "") != after.get(label, "")
    ])


def record_relations(item, before, user, source=ItemChange.Source.ADMIN):
    """Add a history line when the relations of an item differ from the texts in `before`."""
    after = relation_texts(item)
    if before != after:
        ItemChange.objects.create(item=item, user=user, source=source, field=str(Relation._meta.verbose_name_plural).capitalize(),
                                  old_value=", ".join(before), new_value=", ".join(after))
