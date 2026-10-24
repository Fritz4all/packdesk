"""Emails about spare parts. Customers get them in the website's language; the internal recipients of the
spare parts settings get new requests and orders, cancellations and corrections."""

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.translation import gettext as _

from apps.customers.emails import sender
from apps.siteconfig.language import in_customer_language
from apps.siteconfig.models import SiteSettings

from .models import PartsSettings


def _customer_recipients(customer, user=None):
    return list(dict.fromkeys(e for e in [user.email if user else "", customer.email_for("parts")] if e))


def _send(subject, kind, context, to, bcc=()):
    to, bcc = [t for t in to if t], [b for b in bcc if b and b not in to]
    if not (to or bcc):
        return
    context = {**context, "kind": kind, "site_settings": SiteSettings.load(), "rules": PartsSettings.load()}
    body = render_to_string("parts/email.txt", context)
    EmailMessage(subject, body, sender(), to or bcc, bcc=bcc if to else ()).send()


@in_customer_language
def request_received(request):
    _send(_("Spare parts request %(number)s received") % {"number": request.number}, "received",
          {"request": request, "lines": request.lines.select_related("vendor")},
          _customer_recipients(request.customer, request.created_by), PartsSettings.load().internal_recipients())


@in_customer_language
def request_answered(request):
    _send(_("Spare parts request %(number)s answered") % {"number": request.number}, "answered",
          {"request": request, "lines": request.lines.select_related("vendor", "time_new", "time_pack", "time_refurbished")},
          _customer_recipients(request.customer, request.created_by))


@in_customer_language
def order_placed(order):
    _send(_("Spare parts order %(number)s") % {"number": order.number}, "ordered",
          {"order": order, "lines": order.lines.select_related("request_line")},
          _customer_recipients(order.customer, order.created_by), PartsSettings.load().internal_recipients())


@in_customer_language
def order_delivered(order, complete):
    subject = (_("Spare parts order %(number)s delivered") if complete
               else _("Spare parts order %(number)s partly delivered")) % {"number": order.number}
    _send(subject, "delivered", {"order": order, "complete": complete, "lines": order.lines.select_related("request_line")},
          _customer_recipients(order.customer, order.created_by))


def order_changed(order, user, what, reason, credit):
    """To the internal recipients: an order was cancelled or corrected; a credit invoice may be needed."""
    _send(_("Spare parts order %(number)s %(what)s") % {"number": order.number, "what": what}, "changed",
          {"order": order, "user": user, "what": what, "reason": reason, "credit": credit},
          PartsSettings.load().internal_recipients() or [SiteSettings.load().email])
