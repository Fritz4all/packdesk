"""Fault attachments move from DATA_ROOT/faults/ to DATA_ROOT/fault-attachments/ (clearer name)."""

import os

from django.conf import settings
from django.db import migrations


def move(apps, schema_editor, old="faults/", new="fault-attachments/"):
    root = str(settings.DATA_ROOT)
    for item in apps.get_model("faults", "FaultAttachment").objects.filter(file__startswith=old):
        target = new + item.file.name[len(old):]
        source_path, target_path = os.path.join(root, item.file.name), os.path.join(root, target)
        if os.path.exists(source_path) and not os.path.exists(target_path):
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            os.replace(source_path, target_path)
        item.file.name = target
        item.save(update_fields=["file"])


def move_back(apps, schema_editor):
    move(apps, schema_editor, old="fault-attachments/", new="faults/")


class Migration(migrations.Migration):
    dependencies = [("faults", "0003_private_storage_callable")]

    operations = [migrations.RunPython(move, move_back)]
