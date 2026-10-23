"""Saving a completed registration and the service certificate email."""

from datetime import date

from django.core.mail import EmailMessage
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.customers.emails import sender
from apps.siteconfig.models import SiteSettings

from .models import HardwareSystem, Licence, LicenceOption, LicenceSettings, OptionType, Vendor


def _date(value):
    return date.fromisoformat(value) if value else None


@transaction.atomic
def complete_registration(licence_id, data):
    """Store everything the wizard collected. `data` holds only JSON-safe values (ids, ISO dates)."""
    licence = Licence.objects.select_for_update().get(pk=licence_id)
    if licence.registered_on:
        raise ValueError("already registered")
    end_customer, device = data["end_customer"], data["device"]
    reseller = data.get("reseller") or {}

    licence.end_customer_email = end_customer["email"]
    licence.end_customer_reference = end_customer.get("reference", "")
    licence.memo = end_customer.get("memo", "")
    licence.reseller_name = reseller.get("name", "")
    licence.reseller_address = reseller.get("address", "")
    licence.reseller_postal_code = reseller.get("postal_code", "")
    licence.reseller_city = reseller.get("city", "")
    licence.reseller_phone = reseller.get("phone", "")
    licence.system = HardwareSystem.objects.filter(pk=device.get("system")).first()
    licence.vendor = Vendor.objects.filter(pk=device.get("vendor")).first()
    licence.product_nr = device.get("product_nr", "")
    licence.description = device["description"]
    licence.serial_nr = device["serial_nr"]
    licence.purchase_date = _date(device.get("purchase_date"))
    licence.start_date = _date(device["cover_start"])
    licence.end_date = _date(device["cover_end"])
    licence.registered_on = timezone.now()
    licence.save()

    monitor = data.get("monitor")
    if monitor:
        LicenceOption.objects.create(
            licence=licence, option_type=OptionType.objects.filter(is_monitor=True).first(),
            vendor=Vendor.objects.filter(pk=monitor.get("vendor")).first(), product_nr=monitor.get("product_nr", ""),
            description=monitor.get("description", ""), serial_nr=monitor.get("serial_nr", ""),
        )
    counter = 0
    for row in data.get("options", []):
        for _i in range(row["quantity"]):
            counter += 1
            LicenceOption.objects.create(
                licence=licence, option_type_id=row["option_type"], vendor_id=row.get("vendor"),
                product_nr=row.get("product_nr", ""), description=row.get("description", ""),
                # Options share the device's serial number with a running suffix, as in the previous webshop.
                serial_nr=f"{licence.serial_nr}/{counter:03d}",
            )
    return licence


def send_certificate(licence):
    rules = LicenceSettings.load()
    internal = [e.strip() for e in rules.notify_emails.split(",") if e.strip()]
    context = {"licence": licence, "site_settings": SiteSettings.load(), "options": licence.options.select_related("option_type", "vendor")}
    body = render_to_string("licences/email_certificate.txt", context)
    subject = _("Registration licence %(number)s") % {"number": licence.full_number}
    recipients = [licence.end_customer_email] if licence.end_customer_email else []
    if recipients or internal:
        EmailMessage(subject, body, sender(), recipients, bcc=internal).send()
