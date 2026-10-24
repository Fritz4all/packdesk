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


def notify_invoice_problem(order, error):
    """The order was placed but no invoice could be made (e.g. the invoice counter is behind)."""
    rules, site = OrderSettings.load(), SiteSettings.load()
    to = [e.strip() for e in rules.notify_emails.split(",") if e.strip()] or [site.email]
    body = _("Order %(number)s for %(company)s was placed, but its invoice could not be made:\n\n%(error)s\n\n"
             "Make the invoice from the order in the admin once this is solved.") % {
        "number": order.number, "company": order.customer.name, "error": error}
    EmailMessage(_("No invoice for order %(number)s") % {"number": order.number}, body, sender(),
                 [t for t in to if t]).send()
