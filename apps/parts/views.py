"""Customer portal for spare parts: ask for parts, see the answer, order from it, follow the orders.

Ordering is two steps like service packs: choose → check (totals shown, choice signed into the page) → confirm.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.customers.models import Customer, customer_of
from apps.invoices.services import invoice_part_order
from apps.numbering.models import NumberSequence

from . import emails
from .forms import DELIVERY_FIELDS, OrderForm, RequestForm, RequestLineFormSet
from .models import (PartOrder, PartRequest, PartsSettings, PaymentMethod, Remark, RequestLine,
                     place_order, price_order)

SALT = "packdesk.parts.order"


def _customer(request):
    customer = customer_of(request.user)
    if customer is None or customer.status != Customer.Status.ACTIVE or not PartsSettings.load().enabled:
        raise PermissionDenied
    return customer


def _default_delivery(customer):
    address = customer.address("delivery")
    if address is None:
        return {}
    return {"delivery_name": customer.name, "delivery_contact": address.attention, "delivery_address": address.line1,
            "delivery_postal_code": address.postal_code, "delivery_city": address.city,
            "delivery_country": str(address.country or ""), "delivery_phone": customer.phone}


@login_required
def overview(request):
    customer = _customer(request)
    requests = customer.part_requests.prefetch_related("lines")[:100]
    orders = customer.part_orders.select_related("request")[:100]
    return render(request, "parts/overview.html", {"requests": requests, "orders": orders,
                                                   "today": timezone.localdate()})


@login_required
def new_request(request):
    customer, rules = _customer(request), PartsSettings.load()
    formset = RequestLineFormSet(request.POST or None, prefix="lines")
    form = RequestForm(request.POST or None, initial=_default_delivery(customer))
    if request.method == "POST" and formset.is_valid() and form.is_valid():
        with transaction.atomic():
            _n, number = NumberSequence.issue("part_request")
            part_request = PartRequest.objects.create(
                number=number, customer=customer, created_by=request.user, reference=form.cleaned_data["reference"],
                urgent=form.cleaned_data["urgent"],
                **(form.delivery() if form.cleaned_data["urgent"] else {}),
            )
            for line in formset.lines():
                RequestLine.objects.create(
                    request=part_request, vendor=line["vendor"], article_number=line["article_number"],
                    quantity=line["quantity"], description=line["description"],
                    machine_model=line["machine_model"], machine_serial=line["machine_serial"],
                )
        emails.request_received(part_request)
        messages.success(request, _("Request %(number)s has been sent. You will get an email when it has been answered.")
                         % {"number": number})
        return redirect("part_request", pk=part_request.pk)
    return render(request, "parts/request_form.html", {"formset": formset, "form": form, "rules": rules})


def _choices_from_post(part_request, data):
    """The quantities the customer chose: [(line, packing, quantity)]."""
    chosen = []
    for line in part_request.orderable_lines():
        for offer in line.offers():
            try:
                quantity = int(data.get(f"q-{line.pk}-{offer['packing']}") or 0)
            except ValueError:
                quantity = 0
            if quantity > 0:
                chosen.append((line, offer["packing"], quantity))
    return chosen


@login_required
def request_detail(request, pk):
    customer, rules = _customer(request), PartsSettings.load()
    part_request = get_object_or_404(PartRequest.objects.prefetch_related("lines__remarks"), pk=pk, customer=customer)
    action = request.POST.get("action") if request.method == "POST" else None

    if action == "remark":
        line = get_object_or_404(RequestLine, pk=request.POST.get("line"), request=part_request)
        text = request.POST.get("text", "").strip()
        if text:
            Remark.objects.create(line=line, author=request.user, from_customer=True, text=text)
            if line.status == RequestLine.Status.INFORMATION:
                line.status = RequestLine.Status.OPEN
                line.save(update_fields=["status"])
            part_request.update_status()
            emails.request_received(part_request)
            messages.success(request, _("Your remark has been sent."))
        return redirect("part_request", pk=part_request.pk)

    if action == "confirm":
        return _confirm(request, customer, part_request)

    urgent_costs = part_request.urgent_costs if part_request.urgent and part_request.urgent_possible else None
    initial = {**_default_delivery(customer), "reference": part_request.reference,
               **{k: getattr(part_request, k) for k in DELIVERY_FIELDS if getattr(part_request, k)},
               "payment_method": PaymentMethod.objects.filter(is_active=True, for_parts=True).first(), "urgent": urgent_costs is not None}
    form = OrderForm(request.POST if action == "check" else None, initial=initial, urgent_costs=urgent_costs)
    if action == "check" and form.is_valid():
        chosen = _choices_from_post(part_request, request.POST)
        if not chosen:
            messages.error(request, _("Fill in how many parts you want to order."))
        else:
            urgent = bool(form.cleaned_data.get("urgent"))
            order, lines = price_order(customer, part_request, chosen, form.cleaned_data["payment_method"],
                                       form.delivery(), urgent)
            payload = signing.dumps({
                "request": part_request.pk, "customer": customer.pk, "reference": form.cleaned_data["reference"],
                "payment": form.cleaned_data["payment_method"].pk, "delivery": form.delivery(), "urgent": urgent,
                "lines": [[line.pk, packing, quantity] for line, packing, quantity in chosen],
            }, salt=SALT)
            return render(request, "parts/review.html", {"order": order, "lines": lines, "payload": payload,
                                                         "part_request": part_request, "rules": rules})
    orderable = part_request.orderable_lines()
    rows = [{"line": line, "orderable": line in orderable,
             "offers": [{**offer, "name": f"q-{line.pk}-{offer['packing']}",
                         "value": request.POST.get(f"q-{line.pk}-{offer['packing']}", "")} for offer in line.offers()]}
            for line in part_request.lines.all()]
    return render(request, "parts/request_detail.html", {
        "part_request": part_request, "form": form, "rules": rules, "orderable": orderable, "rows": rows,
    })


def _confirm(request, customer, part_request):
    try:
        payload = signing.loads(request.POST.get("payload", ""), salt=SALT, max_age=3600)
    except signing.BadSignature:
        messages.error(request, _("The order has expired or changed. Please check it again."))
        return redirect("part_request", pk=part_request.pk)
    if payload["customer"] != customer.pk or payload["request"] != part_request.pk:
        raise PermissionDenied
    lines = {line.pk: line for line in part_request.orderable_lines()}
    chosen = []
    for line_pk, packing, quantity in payload["lines"]:
        if line_pk not in lines or lines[line_pk].purchase_price(packing) is None:
            messages.error(request, _("The prices have changed in the meantime. Please check your order again."))
            return redirect("part_request", pk=part_request.pk)
        chosen.append((lines[line_pk], packing, quantity))
    payment = get_object_or_404(PaymentMethod, pk=payload["payment"], is_active=True, for_parts=True)
    order = place_order(customer, request.user, part_request, chosen, payment, payload["reference"],
                        payload["delivery"], payload["urgent"])
    emails.order_placed(order)
    _invoice, error = invoice_part_order(order)
    if error:
        from apps.orders.emails import notify_invoice_problem

        notify_invoice_problem(order, error)
    messages.success(request, _("Order %(number)s has been placed.") % {"number": order.number})
    return redirect("part_order", pk=order.pk)


@login_required
def order_detail(request, pk):
    customer = _customer(request)
    order = get_object_or_404(PartOrder.objects.prefetch_related("lines__request_line", "lines__deliveries"),
                              pk=pk, customer=customer)
    return render(request, "parts/order_detail.html", {"order": order})

