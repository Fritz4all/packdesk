from django.db import migrations

COUNTRIES = {"NL": "Nederland", "BE": "België", "DE": "Deutschland", "LU": "Luxemburg"}


def copy_address(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    Address = apps.get_model("siteconfig", "Address")
    for site in SiteSettings.objects.all():
        if site.address_line and not Address.objects.filter(settings=site).exists():
            Address.objects.create(
                settings=site,
                label="Adres",
                line1=site.address_line,
                postal_code=site.postal_code,
                city=site.city,
                country=COUNTRIES.get(site.country, site.country),
                on_website=True,
                on_invoices=True,
                on_quotes=True,
                on_orders=True,
                on_mails=True,
                on_labels=True,
            )


class Migration(migrations.Migration):
    dependencies = [("siteconfig", "0004_address")]
    operations = [migrations.RunPython(copy_address, migrations.RunPython.noop)]
