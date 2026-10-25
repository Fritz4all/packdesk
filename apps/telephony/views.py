"""Customer portal: the telephony calculator and saved quotes."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.customers.models import Customer, customer_of

from .models import Item, Quote, QuoteLine, TelephonySettings, automatic_quantities, calculate


def _customer(request):
    customer = customer_of(request.user)
    if customer is None or customer.status != Customer.Status.ACTIVE or not TelephonySettings.load().enabled:
        raise PermissionDenied
    return customer


def _number(value, default, cls=int):
    try:
        number = cls(str(value).replace(",", ".")) if value not in (None, "") else default
    except (ValueError, InvalidOperation):
        return default
    return number if number >= 0 else default


@login_required
def calculator(request):
    _customer(request)
    rules = TelephonySettings.load()
    items = list(Item.objects.filter(is_active=True).select_related("category").prefetch_related("quantity_from"))
    data = request.POST if request.method == "POST" else {}
    entered = {item.pk: _number(data.get(f"q-{item.pk}"), 0) for item in items}
    quantities = automatic_quantities(items, entered)
    margin_hire = _number(data.get("margin_hire"), rules.default_margin, Decimal)
    margin_buy = _number(data.get("margin_buy"), rules.default_margin, Decimal)
    view = data.get("view") if data.get("view") in Quote.View.values else Quote.View.CUSTOMER
    reference = data.get("reference", "").strip()[:200]
    if request.method == "POST" and data.get("action") == "save":
        if not any(quantities.values()):
            messages.error(request, _("Fill in at least one quantity."))
        else:
            with transaction.atomic():
                quote = Quote.objects.create(customer=customer_of(request.user), created_by=request.user,
                                             reference=reference, view=view, margin_hire=margin_hire,
                                             margin_buy=margin_buy, installation_costs=rules.installation_costs)
                QuoteLine.objects.bulk_create([
                    QuoteLine(quote=quote, item=item, quantity=quantities[item.pk], hire_per_month=item.hire_per_month,
                              buy_price=item.buy_price, buy_per_month=item.buy_per_month)
                    for item in items if quantities.get(item.pk)])
            messages.success(request, _("Quote saved."))
            return redirect("telephony_quote", pk=quote.pk)
    totals = calculate([(item, quantities.get(item.pk, 0), item) for item in items], margin_hire, margin_buy,
                       rules.installation_costs)
    groups = {}
    for item in items:
        groups.setdefault(item.category, []).append({
            "item": item, "quantity": quantities.get(item.pk, 0), "automatic": bool(item.quantity_from.all()),
            "sources": ",".join(str(i.pk) for i in item.quantity_from.all())})
    return render(request, "telephony/calculator.html", {
        "rules": rules, "groups": groups, "totals": totals, "margin_hire": margin_hire, "margin_buy": margin_buy,
        "view": view, "views": Quote.View.choices, "reference": reference, "calculated": request.method == "POST",
    })


@login_required
def my_quotes(request):
    customer = _customer(request)
    return render(request, "telephony/my_quotes.html", {"quotes": customer.telephony_quotes.all()[:200]})


@login_required
def quote_detail(request, pk):
    customer = _customer(request)
    quote = get_object_or_404(Quote, pk=pk, customer=customer)
    return render(request, "telephony/quote.html", {"quote": quote, "totals": quote.totals(),
                                                    "rules": TelephonySettings.load()})
