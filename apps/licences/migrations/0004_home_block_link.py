from django.db import migrations


def link(apps, schema_editor):
    """Point the default 'Register a licence' home block at the registration wizard."""
    HomeBlock = apps.get_model("siteconfig", "HomeBlock")
    for block in HomeBlock.objects.filter(title_en="Register a licence", link_url=""):
        block.link_url = "/registreren/"
        block.link_text = block.link_text_nl = "Nu registreren"
        block.link_text_en = "Register now"
        block.link_text_de = "Jetzt registrieren"
        block.save()


class Migration(migrations.Migration):
    dependencies = [("licences", "0003_licence_vendor"), ("siteconfig", "0008_default_home_blocks")]
    operations = [migrations.RunPython(link, migrations.RunPython.noop)]
