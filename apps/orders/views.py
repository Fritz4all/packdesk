"""Customer portal: order service packs, see licences and extend them.

Ordering is two steps: fill in → check (totals shown, data signed into the page) → confirm.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.customers.models import Customer, customer_of
from apps.licences.models import Licence, SupportPack

from . import emails
from .forms import ExtendForm, LineFormSet, OrderDetailsForm
from .models import Order, OrderSettings, place_order
from .pricing import extension_packs, preview

SALT = "packdesk.order"


def _customer(request):
    customer = customer_of(request.user)
    if customer is None or customer.status != Customer.Status.ACTIVE:
        raise PermissionDenied
    return customer


def _sign(payload):
    return signing.dumps(payload, salt=SALT)


def _unsign(value):
    return signing.loads(value, salt=SALT, max_age=3600)


def _lines_from_payload(payload):
    packs = {p.pk: p for p in SupportPack.objects.filter(pk__in=[r["pack"] for r in payload["lines"]], enabled=True)}
    lines = []
    for row in payload["lines"]:
        if row["pack"] not in packs:
            raise signing.BadSignature("pack no longer available")
        lines.append({"pack": packs[row["pack"]], "quantity": row["quantity"], "reference": row.get("reference", ""),
                      "extends": Licence.objects.filter(pk=row.get("extends")).first() if row.get("extends") else None})
    return lines


def _confirm(request, customer, rules):
    try:
        payload = _unsign(request.POST.get("payload", ""))
        lines = _lines_from_payload(payload)
    except signing.BadSignature:
        messages.error(request, _("The order has expired or changed. Please check it again."))
        return redirect("order_packs")
    if payload.get("customer") != customer.pk:
        raise PermissionDenied
    for line in lines:
        if line["extends"] is not None and line["extends"].customer_id != customer.pk:
            raise PermissionDenied
    order = place_order(customer, request.user, lines, payload.get("reference", ""), payload.get("delivery"))
    emails.send_confirmation(order)
    request.session["placed_order"] = order.pk
    return redirect("order_done")


@login_required
def order_packs(request):
    customer, rules = _customer(request), OrderSettings.load()
    if not rules.enabled:
        raise Http404
    if request.method == "POST" and request.POST.get("action") == "confirm":
        return _confirm(request, customer, rules)
    formset = LineFormSet(request.POST or None, prefix="lines")
    details = OrderDetailsForm(request.POST or None, allow_boxes=rules.allow_boxes)
    if request.method == "POST" and formset.is_valid() and details.is_valid():
        lines = formset.lines()
        payload = {
            "customer": customer.pk, "reference": details.cleaned_data.get("reference", ""), "delivery": details.delivery(),
            "lines": [{"pack": line["pack"].pk, "quantity": line["quantity"], "reference": line["reference"]} for line in lines],
        }
        return render(request, "orders/review.html", {
            "customer": customer, "rules": rules, "totals": preview(customer, lines, rules.vat_rate),
            "payload": _sign(payload), "details": details.cleaned_data, "back": "order_packs",
        })
    return render(request, "orders/order_form.html", {"formset": formset, "details": details, "rules": rules,
                                                       "customer": customer})


@login_required
def done(request):
    order = Order.objects.filter(pk=request.session.get("placed_order"), customer=customer_of(request.user)).first()
    if order is None:
        return redirect("my_orders")
    return render(request, "orders/done.html", {"order": order})


@login_required
def my_orders(request):
    customer = _customer(request)
    orders = customer.orders.prefetch_related("lines")[:200]
    return render(request, "orders/my_orders.html", {"orders": orders})


@login_required
def order_detail(request, pk):
    customer = _customer(request)
    order = get_object_or_404(Order.objects.prefetch_related("lines__licences"), pk=pk, customer=customer)
    return render(request, "orders/order_detail.html", {"order": order})


@login_required
def my_licences(request):
    customer, rules = _customer(request), OrderSettings.load()
    today = timezone.localdate()
    window = today + timedelta(days=rules.extend_window_days)
    licences = customer.licences.select_related("pack__category", "pack__period", "system").order_by("end_date")
    show = request.GET.get("show", "all")
    if show == "ending":
        licences = licences.filter(end_date__gte=today, end_date__lte=window)
    elif show == "unregistered":
        licences = licences.filter(registered_on__isnull=True)
    query = request.GET.get("q", "").strip()
    if query:
        licences = licences.filter(Q(full_number__icontains=query) | Q(serial_nr__icontains=query)
                                   | Q(end_customer_reference__icontains=query) | Q(description__icontains=query))
    extended = set(Licence.objects.filter(prolongation_of__customer=customer).values_list("prolongation_of_id", flat=True))
    rows = [{"licence": lic, "can_extend": bool(lic.end_date and today <= lic.end_date <= window and lic.pk not in extended
                                                 and extension_packs(lic).exists()),
             "extended": lic.pk in extended} for lic in licences[:500]]
    return render(request, "orders/my_licences.html", {"rows": rows, "show": show, "q": query, "rules": rules})


@login_required
def extend(request, pk):
    customer, rules = _customer(request), OrderSettings.load()
    licence = get_object_or_404(Licence, pk=pk, customer=customer)
    if request.method == "POST" and request.POST.get("action") == "confirm":
        return _confirm(request, customer, rules)
    packs = extension_packs(licence)
    if not packs.exists():
        raise Http404
    form = ExtendForm(request.POST or None, packs=packs)
    if request.method == "POST" and form.is_valid():
        line = {"pack": form.cleaned_data["pack"], "quantity": 1, "reference": licence.full_number, "extends": licence}
        payload = {"customer": customer.pk, "reference": form.cleaned_data.get("reference", ""), "delivery": None,
                   "lines": [{"pack": line["pack"].pk, "quantity": 1, "reference": licence.full_number, "extends": licence.pk}]}
        return render(request, "orders/review.html", {
            "customer": customer, "rules": rules, "totals": preview(customer, [line], rules.vat_rate),
            "payload": _sign(payload), "details": {"reference": payload["reference"]}, "extending": licence,
            "back": "my_licences",
        })
    return render(request, "orders/extend.html", {"licence": licence, "form": form, "rules": rules})
