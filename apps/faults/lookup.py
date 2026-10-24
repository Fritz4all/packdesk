from django.db.models import Q
from django.utils import timezone

from apps.licences.models import Licence, LicenceOption


def find_cover(value):
    """Find a registered licence by licence number or serial number (of the device or an option).

    Returns (licence, option, covered_until) or (None, None, None).
    """
    value = (value or "").strip()
    if len(value) < 4:
        return None, None, None
    licence = Licence.find(value)
    option = None
    if licence is None:
        licence = (Licence.objects.filter(registered_on__isnull=False, serial_nr__iexact=value)
                   .order_by("-end_date").first())
    if licence is None:
        option = (LicenceOption.objects.filter(serial_nr__iexact=value, licence__registered_on__isnull=False)
                  .select_related("licence", "vendor").order_by("-licence__end_date").first())
        licence = option.licence if option else None
    if licence is None or not licence.registered_on:
        return None, None, None
    return licence, option, licence.end_date


def is_covered(covered_until):
    return bool(covered_until and covered_until >= timezone.localdate())


def prefill_from(licence, option):
    """Device and reseller details to put in the form."""
    customer = licence.customer
    main = customer.address("main")
    vendor = (option.vendor if option and option.vendor else None) or licence.vendor or (licence.system.vendor if licence.system else None)
    return {
        "vendor": str(vendor or ""),
        "device": option.description if option else (f"{licence.system.name} – {licence.description}" if licence.system else licence.description),
        "serial_nr": option.serial_nr if option else licence.serial_nr,
        "reseller_name": customer.name,
        "reseller_address": main.line1 if main else "",
        "reseller_postal_code": main.postal_code if main else "",
        "reseller_city": main.city if main else "",
        "reseller_phone": customer.phone,
        "reseller_email": customer.email,
    }
