"""Prices on the website: excl. and incl. VAT, for visitors (list price) and for logged-in customers (their own
hardware discount taken off, as it will be on the order)."""

from decimal import Decimal

from apps.customers.models import Customer, customer_of
from apps.orders.models import HUNDRED, money

from .models import HardwareSettings

SESSION_KEY = "hardware_prices_incl_vat"
VIEW_KEY = "hardware_view"


def shop_customer(request):
    """The active customer of the visitor, or None (visitor, staff, or a customer not yet approved)."""
    customer = customer_of(request.user)
    return customer if customer is not None and customer.status == Customer.Status.ACTIVE else None


def show_incl_vat(request, settings=None):
    """Whether the visitor sees prices incl. VAT first: their own choice (?vat=incl/excl), else the setting."""
    choice = request.GET.get("vat")
    if choice in ("incl", "excl"):
        request.session[SESSION_KEY] = choice == "incl"
    if SESSION_KEY in request.session:
        return request.session[SESSION_KEY]
    return (settings or HardwareSettings.load()).prices_incl_vat


def show_as_list(request, theme):
    """Whether the shop shows a list instead of tiles: the visitor's own choice (?view=list/tiles), else what fits
    the website theme."""
    choice = request.GET.get("view")
    if choice in ("list", "tiles"):
        request.session[VIEW_KEY] = choice
    return request.session.get(VIEW_KEY, "list" if theme == "workbench" else "tiles") == "list"


def price(device, customer=None, settings=None):
    """{"excl", "incl", "list_excl", "list_incl", "discount_pct"} or None when the device has no price."""
    settings = settings or HardwareSettings.load()
    list_excl = device.price
    if list_excl is None:
        return None
    pct = (customer.margin_hardware or Decimal("0")) if customer else Decimal("0")
    excl = money(list_excl * (HUNDRED - pct) / HUNDRED)
    with_vat = lambda amount: money(amount * (HUNDRED + settings.vat_rate) / HUNDRED)  # noqa: E731
    return {"excl": excl, "incl": with_vat(excl), "list_excl": list_excl, "list_incl": with_vat(list_excl),
            "discount_pct": pct}
