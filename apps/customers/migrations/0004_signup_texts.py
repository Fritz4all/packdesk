from django.db import migrations

TEXTS = {
    "menu_label": {"nl": "Reseller worden", "en": "Become a reseller", "de": "Reseller werden"},
    "title": {"nl": "Reseller worden", "en": "Become a reseller", "de": "Reseller werden"},
    "intro": {
        "nl": "Meld uw bedrijf aan als reseller. Na goedkeuring kunt u inloggen en servicepacks bestellen.",
        "en": "Sign up your company as a reseller. Once approved you can log in and order service packs.",
        "de": "Melden Sie Ihr Unternehmen als Reseller an. Nach der Freigabe können Sie sich anmelden und Servicepakete bestellen.",
    },
    "thanks": {
        "nl": "Bedankt voor uw aanmelding. We beoordelen deze zo snel mogelijk; u ontvangt een e-mail zodra uw account actief is.",
        "en": "Thank you for signing up. We will review it as soon as possible; you will receive an email once your account is active.",
        "de": "Vielen Dank für Ihre Anmeldung. Wir prüfen sie so schnell wie möglich; Sie erhalten eine E-Mail, sobald Ihr Konto aktiv ist.",
    },
    "activation_subject": {
        "nl": "Uw account bij {company} is actief",
        "en": "Your account with {company} is active",
        "de": "Ihr Konto bei {company} ist aktiv",
    },
    "activation_body": {
        "nl": "Beste {name},\n\nUw account is goedgekeurd. Uw klantnummer is {number}.\nU kunt nu inloggen via {login_url}\n\nMet vriendelijke groet,\n{company}",
        "en": "Dear {name},\n\nYour account has been approved. Your customer number is {number}.\nYou can now log in at {login_url}\n\nKind regards,\n{company}",
        "de": "Sehr geehrte(r) {name},\n\nIhr Konto wurde freigegeben. Ihre Kundennummer ist {number}.\nSie können sich jetzt unter {login_url} anmelden.\n\nMit freundlichen Grüßen\n{company}",
    },
}


def add(apps, schema_editor):
    SignupSettings = apps.get_model("customers", "SignupSettings")
    CustomerType = apps.get_model("customers", "CustomerType")
    obj, _ = SignupSettings.objects.get_or_create(pk=1)
    for field, texts in TEXTS.items():
        setattr(obj, field, texts["nl"])
        for lang, text in texts.items():
            setattr(obj, f"{field}_{lang}", text)
    obj.customer_type = CustomerType.objects.filter(is_reseller=True).first()
    obj.save()


class Migration(migrations.Migration):
    dependencies = [("customers", "0003_signup_settings")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]
