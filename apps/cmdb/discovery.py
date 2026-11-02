"""Automatic discovery: a script at the customer reports what it finds; PackDesk compares that with the items.

PackDesk cannot look into a customer's network from outside, so the finding is done there (templates/cmdb/discovery)
and only the result comes in, with the key of a DiscoverySource. Rules:

- What is new waits under Discovered items until someone accepts it, unless the source accepts automatically.
- A report only fills in what it knows: an empty value never empties a field, and a report never removes an item.
- An ignored thing stays ignored. An item is linked by its serial number, or else by a name only it has.
"""

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from . import history, transfer
from .models import (
    CmdbSettings, ConfigurationItem, DiscoveredItem, DiscoverySource, ItemChange, ItemField, token_hash,
)

MAX_ITEMS = 500
TEXT_FIELDS = ["name", "manufacturer", "model", "serial_nr"]
MAX_PROPERTIES = 30
MAX_VALUE = 200


class ReportError(Exception):
    pass


def source_for(token):
    """The active source with this key, while its customer and the installation use the CMDB."""
    if not token or not CmdbSettings.load().enabled:
        return None
    return (DiscoverySource.objects.select_related("customer", "item_type")
            .filter(token_digest=token_hash(token), is_active=True, customer__cmdb__enabled=True).first())


def _text(value, limit=MAX_VALUE):
    return str(value).strip()[:limit] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def clean(raw):
    """(key, data) of one reported thing; only known fields and short text get through."""
    if not isinstance(raw, dict):
        return None, None
    data = {}
    for name in TEXT_FIELDS:
        limit = ConfigurationItem._meta.get_field(name).max_length
        value = _text(raw.get(name), limit)
        if value:
            data[name] = value
    properties = raw.get("properties")
    if isinstance(properties, dict):
        found = {_text(k, 40): _text(v) for k, v in list(properties.items())[:MAX_PROPERTIES]}
        data["properties"] = {k: v for k, v in found.items() if k and v}
    key = _text(raw.get("key"), 120) or data.get("serial_nr") or data.get("name")
    return key, data


def _find_item(source, data):
    items = ConfigurationItem.objects.filter(customer=source.customer)
    if data.get("serial_nr"):
        item = items.filter(serial_nr__iexact=data["serial_nr"]).first()
        if item:
            return item
    if data.get("name"):
        found = list(items.filter(name__iexact=data["name"])[:2])
        if len(found) == 1:
            return found[0]
    return None


def _property_values(item_type, data):
    """The reported properties this item type has, as the kind of value each property needs."""
    values = {}
    for prop in ItemField.objects.filter(item_types=item_type):
        reported = (data.get("properties") or {}).get(prop.key)
        if reported:
            try:
                values[prop.key] = transfer._property_value(prop, reported)
            except ValueError:
                pass
    return values


def differences(found):
    """[(label, now, reported)] of what accepting would change on the linked item."""
    if found.item is None:
        return []
    item = ConfigurationItem.objects.select_related("customer", "contact", "item_type", "status").get(pk=found.item_id)
    before = history.snapshot(item)
    _fill(item, found.data)
    after = history.snapshot(item)
    return [(label, before.get(label, "") or "–", after[label]) for label in after if before.get(label, "") != after[label]]


def _fill(item, data):
    for name in TEXT_FIELDS:
        if data.get(name):
            setattr(item, name, data[name])
    if item.item_type_id:
        item.properties = {**(item.properties or {}), **_property_values(item.item_type, data)}


@transaction.atomic
def accept(found, user=None):
    """Make or update the item from what was reported, with a line in its history."""
    if found.item_id:
        item = ConfigurationItem.objects.select_related("customer", "contact", "item_type", "status").get(pk=found.item_id)
        before = history.snapshot(item)
    else:
        item = ConfigurationItem(customer=found.customer, item_type=found.source.item_type, name=found.key[:120])
        before = None
    _fill(item, found.data)
    item.save()
    history.record(item, before, user, ItemChange.Source.SCAN)
    found.item = item
    found.status = DiscoveredItem.Status.ACCEPTED
    found.save(update_fields=["item", "status"])
    return item


@transaction.atomic
def report(source, payload):
    """Process what a source sent; returns the counts for the script."""
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ReportError("expected {\"items\": [...]}")
    if len(rows) > MAX_ITEMS:
        raise ReportError(f"at most {MAX_ITEMS} items per report")
    counts = {"new": 0, "changed": 0, "accepted": 0, "ignored": 0, "skipped": 0}
    now = timezone.now()
    for raw in rows:
        key, data = clean(raw)
        if not key:
            counts["skipped"] += 1
            continue
        found, created = DiscoveredItem.objects.get_or_create(
            customer=source.customer, key=key, defaults={"source": source, "data": data, "last_seen": now})
        found.source, found.data, found.last_seen = source, data, now
        if found.status == DiscoveredItem.Status.IGNORED:
            found.save(update_fields=["source", "data", "last_seen"])
            counts["ignored"] += 1
            continue
        if found.item_id is None:
            found.item = _find_item(source, data)
        if found.item_id is None:
            found.status = DiscoveredItem.Status.NEW
        else:
            found.status = DiscoveredItem.Status.CHANGED if differences(found) else DiscoveredItem.Status.ACCEPTED
        found.save(update_fields=["source", "data", "last_seen", "item", "status"])
        if source.auto_accept and found.status != DiscoveredItem.Status.ACCEPTED:
            accept(found)
        counts[found.status] += 1
    source.reported()
    return counts


def scripts():
    """The scripts that can be downloaded: {code: (file name, template, description)}."""
    return {
        "windows": ("packdesk-discovery.ps1", "cmdb/discovery/report.ps1", _("Windows (PowerShell)")),
        "linux": ("packdesk-discovery.sh", "cmdb/discovery/report.sh", _("Linux")),
    }
