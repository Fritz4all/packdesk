from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.customers.emails import sender
from apps.siteconfig.models import SiteSettings

from .models import OrderSettings


def send_confirmation(order):
    rules, site = OrderSettings.load(), SiteSettings.load()
    to = list(dict.fromkeys(e for e in [order.created_by.email if order.created_by else "",
                                        order.customer.email_for("orders")] if e))
    internal = [e.strip() for e in rules.notify_emails.split(",") if e.strip()]
    context = {"order": order, "rules": rules, "site_settings": site,
               "lines": order.lines.prefetch_related("licences").select_related("pack")}
    body = render_to_string("orders/email_confirmation.txt", context)
    subject = _("Order %(number)s – %(company)s") % {"number": order.number, "company": order.customer.name}
    if to or internal:
        EmailMessage(subject, body, sender(), to, bcc=internal).send()
