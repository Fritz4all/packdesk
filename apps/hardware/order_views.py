"""Ordering hardware on the website: cart → delivery and payment → check → order placed.

Like ordering service packs, the check step signs the choices into the page; placing the order checks again
that every device is still for sale (another customer may have been faster)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.invoices.services import invoice_order
from apps.orders import emails
from apps.orders.models import Order

from . import pricing, services
from .forms import ADDRESS_FIELDS, CheckoutForm
from .models import Device, HardwareSettings

SALT = "packdesk.hardware.order"


def _customer(request):
    settings = HardwareSettings.load()
    if not settings.enabled:
        raise Http404
    customer = pricing.shop_customer(request)
    if customer is None:
        raise PermissionDenied
    return customer, settings


@login_required
@require_POST
def add(request, number):
    _customer(request)
    device = get_object_or_404(Device, number=number)
    if device.status != Device.Status.FOR_SALE:
        messages.error(request, _("This device is no longer for sale."))
        return redirect("hardware_device", number)
    services.add_to_cart(request, device)
    messages.success(request, _("%(device)s is in your cart.") % {"device": services.line_description(device)})
    return redirect(request.POST.get("next") or "hardware_cart")


@login_required
@require_POST
def remove(request, number):
    _customer(request)
    services.remove_from_cart(request, number)
    return redirect("hardware_cart")


def _default_address(customer):
    address = customer.address("delivery") or customer.address("invoice")
    if address is None:
        return {"delivery_name": customer.name}
    return {"delivery_name": customer.name, "delivery_contact": address.attention, "delivery_address": address.line1,
            "delivery_postal_code": address.postal_code, "delivery_city": address.city}


@login_required
def cart(request):
    customer, settings = _customer(request)
    if request.method == "POST" and request.POST.get("action") == "confirm":
        return _confirm(request, customer)
    devices, gone = services.cart_devices(request)
    for device in gone:
        messages.warning(request, _("%(device)s is no longer for sale and was taken out of your cart.")
                         % {"device": device})
    form = CheckoutForm(request.POST or None, initial=_default_address(customer), terms=settings.terms_text)
    if request.method == "POST" and devices and form.is_valid():
        data = form.cleaned_data
        payload = {"customer": customer.pk, "numbers": [d.number for d in devices], "delivery": data["delivery"].pk,
                   "payment": data["payment"].pk, "reference": data["reference"], "address": form.address()}
        return render(request, "hardware/review.html", {
            "totals": services.totals(customer, devices, data["delivery"], data["payment"]), "data": data,
            "address": form.address(), "payload": signing.dumps(payload, salt=SALT), "settings": settings,
        })
    for device in devices:
        device.shop_price = pricing.price(device, customer, settings)
    return render(request, "hardware/cart.html", {
        "devices": devices, "form": form, "settings": settings, "customer": customer,
        "totals": services.totals(customer, devices) if devices else None, "address_fields": ADDRESS_FIELDS,
        "incl_vat": pricing.show_incl_vat(request, settings),
    })


def _confirm(request, customer):
    try:
        payload = signing.loads(request.POST.get("payload", ""), salt=SALT, max_age=3600)
    except signing.BadSignature:
        messages.error(request, _("The order has expired or changed. Please check it again."))
        return redirect("hardware_cart")
    if payload.get("customer") != customer.pk:
        raise PermissionDenied
    delivery = services.delivery_options().filter(pk=payload["delivery"]).first()
    payment = services.payment_methods().filter(pk=payload["payment"]).first()
    if delivery is None or payment is None:
        messages.error(request, _("The order has expired or changed. Please check it again."))
        return redirect("hardware_cart")
    try:
        order = services.place_order(customer, request.user, payload["numbers"], delivery, payment,
                                     payload.get("reference", ""), payload.get("address"))
    except services.NotAvailable as exc:
        messages.error(request, _("Sorry, not everything can be ordered any more: %(devices)s. Please check your "
                                  "order again.") % {"devices": exc})
        return redirect("hardware_cart")
    services.empty_cart(request)
    emails.send_confirmation(order)
    services.notify(order)
    _invoice, error = invoice_order(order)
    if error:
        emails.notify_invoice_problem(order, error)
    request.session["placed_order"] = order.pk
    return redirect("hardware_done")


@login_required
def done(request):
    customer, _settings = _customer(request)
    order = Order.objects.filter(pk=request.session.get("placed_order"), customer=customer).first()
    if order is None:
        return redirect("my_orders")
    return render(request, "hardware/done.html", {"order": order, "orders_url": reverse("my_orders")})
