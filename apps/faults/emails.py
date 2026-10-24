from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.customers.emails import sender
from apps.siteconfig.models import SiteSettings

from .models import FaultSettings


def _split(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def send_report(fault):
    rules, site = FaultSettings.load(), SiteSettings.load()
    to = _split(rules.recipients) or [site.email or settings.DEFAULT_FROM_EMAIL]
    body = render_to_string("faults/email_report.txt", {"fault": fault, "site_settings": site})
    prefix = _("UNDER CONTRACT") if fault.is_covered else _("No cover found")
    subject = _("Fault report %(number)s – %(company)s – %(prefix)s") % {
        "number": fault.number, "company": fault.reseller_name, "prefix": prefix,
    }
    message = EmailMessage(subject, body, sender(), to, cc=_split(rules.cc), reply_to=[fault.location_email])
    for item in fault.attachments.all():
        with item.file.open("rb") as f:
            message.attach(item.name, f.read())
    message.send()


def send_confirmation(fault):
    rules, site = FaultSettings.load(), SiteSettings.load()
    values = {"number": fault.number, "name": fault.location_contact, "company": site.display_name}
    subject = (rules.confirmation_subject or _("Confirmation of fault report {number}")).format(**values)
    body = (rules.confirmation_body or _("We have received your fault report {number}.")).format(**values)
    EmailMessage(subject, body, sender(), [fault.location_email]).send()
