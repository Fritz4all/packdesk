"""The fields of an item as they are set up under CMDB settings → Fields."""

from apps.customers.models import FieldMode

from .models import ItemField

# The field of an item → the column of an import file, where they differ.
COLUMN = {"item_type": "type"}


def config():
    return {field.key: field for field in ItemField.objects.all()}


def label(key):
    """The name of a field for people. The model's own name is the fallback for a row without one."""
    from .models import ConfigurationItem

    field = ItemField.objects.filter(key=key).first()
    return (field.name if field else "") or str(ConfigurationItem._meta.get_field(key).verbose_name).capitalize()


def labels():
    return {field.key: field.name for field in ItemField.objects.all() if field.name}


def hidden():
    return set(ItemField.objects.filter(mode=FieldMode.HIDDEN).values_list("key", flat=True))


def required_columns():
    """Import columns that need a value. The status has a value of its own when it is left empty."""
    keys = (ItemField.objects.filter(mode=FieldMode.REQUIRED, key__in=ItemField.STANDARD).exclude(key="status")
            .values_list("key", flat=True))
    return [COLUMN.get(key, key) for key in keys]
