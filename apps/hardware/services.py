"""Ordering hardware: a customer orders devices from their cart; the order is an ordinary order with an invoice.

A device is reserved when it is ordered, so nobody else can order it; it counts as sold once the invoice is made
(sold to that customer). Cancelling an order without an invoice puts its devices back up for sale.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.orders.models import Order, OrderLine, PaymentMethod, money

from .models import DeliveryOption, Device, HardwareSettings

CART_KEY = "hardware_cart"
MAX_CART = 50


class NotAvailable(Exception):
    """One or more devices were ordered or taken out of sale by someone else in the meantime."""

    def __init__(self, devices):
        super().__init__(", ".join(str(d) for d in devices))
        self.devices = devices


# --- cart (in the session: a list of stock numbers) ---------------------------------------------------------

def cart_numbers(request):
    return list(request.session.get(CART_KEY, []))


def cart_devices(request):
    """The devices in the cart that are still for sale; others are taken out (returned as `gone`)."""
    numbers = cart_numbers(request)
    devices = {d.number: d for d in Device.objects.filter(number__in=numbers).select_related("device_type", "brand")}
    available = [devices[n] for n in numbers if n in devices and devices[n].status == Device.Status.FOR_SALE]
    gone = [devices.get(n) or n for n in numbers if n not in devices or devices[n].status != Device.Status.FOR_SALE]
    if gone:
        request.session[CART_KEY] = [d.number for d in available]
    return available, gone


def add_to_cart(request, device):
    numbers = cart_numbers(request)
    if device.number not in numbers and len(numbers) < MAX_CART:
        numbers.append(device.number)
    request.session[CART_KEY] = numbers


def remove_from_cart(request, number):
    request.session[CART_KEY] = [n for n in cart_numbers(request) if n != number]


def empty_cart(request):
    request.session.pop(CART_KEY, None)


# --- totals and placing ---------------------------------------------------------------------------------------

def line_description(device):
    brand = f"{device.brand.name} " if device.brand_id else ""
    return f"{device.device_type}: {brand}{device.model} ({_('serial number')} {device.serial_nr})"[:250]


def totals(customer, devices, delivery_option=None, payment_method=None):
    """The totals as the order will get them (same rules as Order.recalculate)."""
    settings = HardwareSettings.load()
    rows = [{"device": d, "price": d.price or Decimal("0")} for d in devices]
    gross = money(sum((r["price"] for r in rows), Decimal("0")))
    pct = customer.margin_hardware or Decimal("0")
    discount = money(gross * pct / Decimal("100"))
    costs = []
    if delivery_option is not None and delivery_option.price:
        costs.append((_("Delivery costs"), delivery_option.price))
    if payment_method is not None and payment_method.extra_costs:
        costs.append((_("Payment costs"), payment_method.extra_costs))
    net = gross - discount + sum((amount for _label, amount in costs), Decimal("0"))
    vat = money(net * settings.vat_rate / Decimal("100"))
    return {"rows": rows, "gross": gross, "discount_pct": pct, "discount": discount, "costs": costs, "net": net,
            "vat_rate": settings.vat_rate, "vat": vat, "total": net + vat}


def place_order(customer, user, numbers, delivery_option, payment_method, reference="", address=None):
    """Order the devices with these stock numbers; raises NotAvailable when one of them can no longer be ordered.
    The devices are reserved for this customer."""
    from apps.numbering.models import NumberSequence

    settings = HardwareSettings.load()
    with transaction.atomic():
        devices = list(Device.objects.select_for_update().filter(number__in=numbers).select_related("device_type", "brand"))
        found = {d.number for d in devices}
        gone = [d for d in devices if d.status != Device.Status.FOR_SALE or d.price is None]
        gone += [n for n in numbers if n not in found]
        if gone or not devices:
            raise NotAvailable(gone)
        _n, number = NumberSequence.issue("order")
        shipping = delivery_option.kind == DeliveryOption.Kind.SHIPPING
        order = Order.objects.create(
            number=number, kind=Order.Kind.HARDWARE, customer=customer, created_by=user, reference=reference,
            discount_pct=customer.margin_hardware or Decimal("0"), vat_rate=settings.vat_rate,
            delivery_method=delivery_option.name, shipping=shipping, delivery_costs=delivery_option.price or None,
            payment_method=payment_method, payment_costs=payment_method.extra_costs or None,
            **((address or {}) if shipping else {}),
        )
        for device in sorted(devices, key=lambda d: numbers.index(d.number)):
            OrderLine.objects.create(order=order, device=device, description=line_description(device), quantity=1,
                                     unit_price=device.price, line_total=device.price)
            device.status = Device.Status.RESERVED
            device.customer = customer
            device.save(update_fields=["status", "customer", "updated_at"])
        order.recalculate()
        order.save()
    return order


def mark_sold(order):
    """After the invoice: the order's devices are sold to its customer."""
    now = timezone.now()
    for line in order.lines.select_related("device").filter(device__isnull=False):
        device = line.device
        device.status = Device.Status.SOLD
        device.customer = order.customer
        device.sold_at = device.sold_at or now
        device.save(update_fields=["status", "customer", "sold_at", "updated_at"])


def cancel(order):
    """Cancel a hardware order that has no invoice yet: its devices are for sale again."""
    with transaction.atomic():
        order.cancelled_at = timezone.now()
        order.save(update_fields=["cancelled_at"])
        Device.objects.filter(order_lines__order=order, status=Device.Status.RESERVED).update(
            status=Device.Status.FOR_SALE, customer=None)


def notify(order):
    """The hardware recipients get the new order as well (the order confirmation goes to the customer)."""
    from django.core.mail import EmailMessage
    from django.template.loader import render_to_string

    from apps.customers.emails import sender
    from apps.siteconfig.models import SiteSettings

    settings = HardwareSettings.load()
    to = [e.strip() for e in settings.notify_emails.split(",") if e.strip()]
    if not to:
        return
    body = render_to_string("hardware/email_new_order.txt", {"order": order, "site_settings": SiteSettings.load(),
                                                             "lines": order.lines.select_related("device")})
    subject = _("Hardware order %(number)s – %(company)s") % {"number": order.number, "company": order.customer.name}
    EmailMessage(subject, body, sender(), to).send()


def payment_methods():
    return PaymentMethod.objects.filter(is_active=True, for_hardware=True)


def delivery_options():
    return DeliveryOption.objects.filter(is_active=True)
