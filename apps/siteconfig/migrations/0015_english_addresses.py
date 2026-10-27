"""Website addresses are English now (/my/ instead of /mijn/, ...). Translates the links in menu items and
home blocks; old addresses would also still work through a redirect."""

from django.db import migrations

from apps.core.old_addresses import translate


def english(apps, schema_editor):
    for model_name, field in (("MenuItem", "url"), ("HomeBlock", "link_url")):
        model = apps.get_model("siteconfig", model_name)
        for obj in model.objects.all():
            value = getattr(obj, field) or ""
            new = translate(value) if value.startswith("/") else value
            if new != value:
                setattr(obj, field, new)
                obj.save(update_fields=[field])


class Migration(migrations.Migration):
    dependencies = [("siteconfig", "0014_password_min_length")]
    operations = [migrations.RunPython(english, migrations.RunPython.noop)]
