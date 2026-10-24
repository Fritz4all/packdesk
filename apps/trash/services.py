"""Move deleted objects to the trash and bring them back.

Deleting in the admin goes through `delete_to_trash()`: Django's own collector finds everything
that is deleted along with the object (cascade) and every link that is emptied (SET_NULL). All of
it is stored as JSON before the deletion. Restoring saves the objects again with their original
ids, parents first, and restores the emptied links. Files (PDFs, attachments) stay on disk while an
item is in the trash and are removed only when it is deleted for good.
"""

import json
from collections import Counter
from datetime import timedelta

from django.apps import apps
from django.core import serializers
from django.db import IntegrityError, models, router, transaction
from django.db.models.deletion import Collector
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext as _

from .models import TrashEntry

# Technical records that are not worth keeping in the trash.
NOT_TRASHED = {"trash.trashentry", "admin.logentry", "sessions.session", "contenttypes.contenttype",
               "auth.permission"}


class RestoreError(Exception):
    pass


def _label(model):
    return model._meta.label_lower


def keeps(obj):
    return _label(type(obj)) not in NOT_TRASHED


def delete_to_trash(obj, user=None):
    """Delete `obj` (and what cascades with it), keeping a copy in the trash."""
    using = router.db_for_write(type(obj), instance=obj)
    collector = Collector(using=using, origin=obj)
    collector.collect([obj])
    collector.sort()

    groups = [list(instances) for instances in collector.data.values()]
    restore_order = [o for group in reversed(groups) for o in group]
    for qs in collector.fast_deletes:
        restore_order.extend(list(qs))
    restore_order = [o for o in restore_order if keeps(o)]

    updates = []
    for (field, _value), items in collector.field_updates.items():
        for item in items:
            rows = item if isinstance(item, (models.QuerySet, list, tuple)) else [item]
            for row in rows:
                updates.append([_label(type(row)), row.pk, field.attname, _json_value(getattr(row, field.attname))])

    counts = Counter(capfirst(str(o._meta.verbose_name)) for o in restore_order if o is not obj)
    with transaction.atomic(using=using):
        TrashEntry.objects.create(
            deleted_by=user if getattr(user, "is_authenticated", False) else None,
            model=_label(type(obj)), kind=capfirst(str(obj._meta.verbose_name)), label=str(obj)[:300],
            object_count=len(restore_order), summary=", ".join(f"{n}× {k}" for k, n in sorted(counts.items())),
            data=serializers.serialize("json", restore_order), field_updates=json.dumps(updates),
        )
        collector.delete()


def _json_value(value):
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


def restore(entry):
    """Put everything back as it was; raises RestoreError when that is no longer possible."""
    try:
        with transaction.atomic():
            for item in serializers.deserialize("json", entry.data):
                model = type(item.object)
                if model.objects.filter(pk=item.object.pk).exists():
                    raise RestoreError(_("%(kind)s %(name)s exists again; it was restored or re-created.") % {
                        "kind": model._meta.verbose_name, "name": item.object})
                item.save()
            for label, pk, attname, value in json.loads(entry.field_updates):
                model = apps.get_model(label)
                model.objects.filter(pk=pk).update(**{attname: value})
            entry.delete()
    except IntegrityError as exc:
        raise RestoreError(_("Restoring is not possible: %(error)s") % {"error": exc}) from exc


def delete_for_good(entry):
    """Remove an item from the trash, including its files."""
    for item in serializers.deserialize("json", entry.data):
        for field in item.object._meta.concrete_fields:
            if isinstance(field, models.FileField):
                file = getattr(item.object, field.attname)
                if file and file.name and not type(item.object).objects.filter(**{field.attname: file.name}).exists():
                    file.storage.delete(file.name)
    entry.delete()


def purge_old(days):
    """Delete items that have been in the trash longer than `days` days (0 = never)."""
    if not days:
        return 0
    old = TrashEntry.objects.filter(deleted_at__lt=timezone.now() - timedelta(days=days))
    count = 0
    for entry in old:
        delete_for_good(entry)
        count += 1
    return count
