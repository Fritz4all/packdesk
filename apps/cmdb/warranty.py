"""Warranty reminders: an overview for staff and, per customer that wants it, a mail to the customer.

Run every hour by the container (docker/entrypoint.sh → manage.py cmdb_warranty_mails). A reminder is noted before it
goes out, so two runs cannot send it twice, and taken back when sending fails, so the next run tries again. An item
that comes within several moments at once (added late) gets only the nearest one.
"""

import datetime
import logging
import re
from collections import defaultdict

from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import formats, timezone
from django.utils.translation import gettext as _

from apps.customers.emails import sender
from apps.customers.models import Customer
from apps.siteconfig.language import customer_language
from apps.siteconfig.models import SiteSettings

from .models import CmdbSettings, ConfigurationItem, WarrantyReminder

logger = logging.getLogger(__name__)
FIRST_HOUR = 8


def moments(settings_=None):
    settings_ = settings_ or CmdbSettings.load()
    return sorted({int(part) for part in settings_.warranty_mail_days.split(",") if part.strip().isdigit()})


def due(today=None):
    """[(item, days)]: items whose warranty has not ended yet and is within a moment; `days` is the nearest moment."""
    today = today or timezone.localdate()
    days = moments()
    if not days:
        return []
    items = (ConfigurationItem.objects
             .filter(customer__cmdb__enabled=True, status__out_of_use=False, warranty_until__gte=today,
                     warranty_until__lte=today + datetime.timedelta(days=days[-1]))
             .select_related("customer", "customer__cmdb", "item_type").order_by("warranty_until"))
    return [(item, next(d for d in days if (item.warranty_until - today).days <= d)) for item in items]


def _claim(rows, audience):
    """Note the reminders that did not go out yet; returns those notes with their items."""
    claimed = []
    for item, days in rows:
        try:
            with transaction.atomic():
                note, created = WarrantyReminder.objects.get_or_create(
                    item=item, warranty_until=item.warranty_until, days=days, audience=audience)
        except IntegrityError:  # another run was just ahead of this one
            continue
        if created:
            claimed.append((note, item))
    return claimed


def _line(item, today):
    return _("%(number)s %(name)s – until %(date)s (%(days)s days)") % {
        "number": item.number, "name": item.name, "date": formats.date_format(item.warranty_until),
        "days": (item.warranty_until - today).days}


def _fill(template, **values):
    """Fills in {placeholders}; other text between braces stays as it is."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), template)


def _send_claimed(claimed, build):
    """Send one mail about the claimed reminders; the notes are taken back when it fails. Returns the error or None."""
    subject, body, recipients = build()
    try:
        send_mail(subject, body, sender(), recipients)
    except Exception as exc:
        logger.exception("Warranty reminder not sent")
        WarrantyReminder.objects.filter(pk__in=[note.pk for note, _item in claimed]).delete()
        return exc
    return None


def _staff_addresses(settings_):
    parts = [part.strip() for part in settings_.warranty_mail_to.split(",") if part.strip()]
    return parts or [address for address in [SiteSettings.load().email] if address]


def send_due(today=None):
    """Send what is due now. Returns {"overview": items in the staff mail, "customers": mails, "errors": failures}."""
    today = today or timezone.localdate()
    settings_ = CmdbSettings.load()
    result = {"overview": 0, "customers": 0, "errors": 0}
    rows = due(today)
    if not rows:
        return result

    staff_to = _staff_addresses(settings_)
    if staff_to:
        claimed = _claim(rows, WarrantyReminder.Audience.STAFF)
        if claimed:
            def overview():
                groups = defaultdict(list)
                for _note, item in claimed:
                    groups[item.customer.name].append(_line(item, today))
                text = "\n\n".join(f"{name}\n" + "\n".join(f"  {line}" for line in lines) for name, lines in sorted(groups.items()))
                return (_("Warranty running out: %(count)s item(s)") % {"count": len(claimed)},
                        _("The warranty of these items runs out soon:") + "\n\n" + text, staff_to)
            with customer_language():
                error = _send_claimed(claimed, overview)
            result["errors" if error else "overview"] += 1 if error else len(claimed)

    per_customer = defaultdict(list)
    for item, days in rows:
        if item.customer.cmdb.warranty_mail and item.customer.status == Customer.Status.ACTIVE and item.customer.email:
            per_customer[item.customer_id].append((item, days))
    for customer_rows in per_customer.values():
        claimed = _claim(customer_rows, WarrantyReminder.Audience.CUSTOMER)
        if not claimed:
            continue
        customer = customer_rows[0][0].customer

        def customer_mail(claimed=claimed, customer=customer):
            values = {"company": SiteSettings.load().display_name, "customer": customer.name, "count": len(claimed),
                      "items": "\n".join(_line(item, today) for _note, item in claimed)}
            return (_fill(settings_.warranty_subject, **values), _fill(settings_.warranty_body, **values), [customer.email])

        with customer_language():
            error = _send_claimed(claimed, customer_mail)
        result["errors" if error else "customers"] += 1
    return result
