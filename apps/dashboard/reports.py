"""Sales report: revenue, cost and margin per month, per category and per customer.

Service packs: orders give exact amounts. Licences without an order (made by hand or imported) are estimated
at the pack's current price minus the customer's discount; the page says how many sales are estimates.
Spare parts: each ordered part with its own selling and purchase price, minus the order discount and minus
corrections; surcharges count as revenue without cost; cancelled orders are left out.
"""

from collections import OrderedDict, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.licences.models import Licence, SupportPack

HUNDRED = Decimal("100")


def _period(choice, today):
    if choice == "this_year":
        return date(today.year, 1, 1), today
    if choice == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    start = date(today.year - 1, today.month, 1)
    return (date(start.year + (start.month == 12), start.month % 12 + 1, 1)), today


def _months(start, end):
    months, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


def sale_values(licence):
    pack = licence.pack
    discount = licence.customer.margin_packs or Decimal("0")
    revenue = (pack.price * (HUNDRED - discount) / HUNDRED).quantize(Decimal("0.01"))
    return revenue, pack.cost_price


def month_range(year, month):
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1))
    return date(year, month, 1), last


def parse_range(request, today):
    """Preset (12m, this_year, last_year) or a custom from/to range; returns (key, start, end)."""
    start, end = request.GET.get("from"), request.GET.get("to")
    if start or end:
        try:
            start = date.fromisoformat(start) if start else today - timedelta(days=365)
            end = date.fromisoformat(end) if end else today
        except ValueError:
            return ("12m", *_period("12m", today))
        if start > end:
            start, end = end, start
        return "custom", start, end
    choice = request.GET.get("period", "12m")
    if choice not in ("12m", "this_year", "last_year"):
        choice = "12m"
    return (choice, *_period(choice, today))


KINDS = ("all", "packs", "parts", "hardware")


def sale_items(start, end, kind="all"):
    """Everything sold in the period, as items with: when, customer, category, product, count, revenue, cost,
    label, url, exact."""
    items = []
    if kind in ("all", "packs"):
        items += pack_items(start, end)
    if kind in ("all", "parts"):
        items += part_items(start, end)
    if kind in ("all", "hardware"):
        items += hardware_items(start, end)
    return items


def pack_items(start, end):
    """Order lines (exact prices at order time) and licences without an order (e.g. created by hand),
    valued at the current pack price minus the customer's discount."""
    from apps.orders.models import OrderLine

    items = []
    lines = (OrderLine.objects.filter(order__created_at__date__gte=start, order__created_at__date__lte=end,
                                      pack__isnull=False).select_related("order__customer", "pack__category"))
    for line in lines:
        revenue = (line.line_total * (HUNDRED - line.order.discount_pct) / HUNDRED).quantize(Decimal("0.01"))
        items.append({"when": line.order.created_at, "customer": line.order.customer, "category": str(line.pack.category),
                      "product": str(line.pack), "count": line.quantity, "revenue": revenue,
                      "cost": line.pack.cost_price * line.quantity, "label": line.order.number,
                      "url": ("admin:orders_order_change", line.order.pk), "exact": True})
    licences = (Licence.objects.filter(created_at__date__gte=start, created_at__date__lte=end, order_line__isnull=True)
                .select_related("pack__category", "customer"))
    for lic in licences:
        revenue, cost = sale_values(lic)
        items.append({"when": lic.created_at, "customer": lic.customer, "category": str(lic.pack.category),
                      "product": str(lic.pack), "count": 1, "revenue": revenue, "cost": cost, "label": lic.full_number,
                      "url": ("admin:licences_licence_change", lic.pk), "exact": False})
    return items


def hardware_items(start, end):
    """Each device sold on an order (not cancelled), at its order price minus the order discount, with its purchase
    price as cost; delivery and payment costs count as revenue without cost."""
    from apps.orders.models import Order, OrderLine

    orders = (Order.objects.filter(kind=Order.Kind.HARDWARE, created_at__date__gte=start, created_at__date__lte=end,
                                   cancelled_at__isnull=True).select_related("customer"))
    orders = {o.pk: o for o in orders}
    items = []
    for line in OrderLine.objects.filter(order__in=orders.keys(), device__isnull=False).select_related("device__device_type"):
        order = orders[line.order_id]
        revenue = (line.line_total * (HUNDRED - order.discount_pct) / HUNDRED).quantize(Decimal("0.01"))
        items.append({"when": order.created_at, "customer": order.customer,
                      "category": f"{_('Hardware')}: {line.device.device_type}", "product": line.description,
                      "count": line.quantity, "revenue": revenue, "cost": line.device.purchase_price or Decimal("0"),
                      "label": order.number, "url": ("admin:orders_order_change", order.pk), "exact": True})
    for order in orders.values():
        costs = order.costs()
        if costs:
            items.append({"when": order.created_at, "customer": order.customer,
                          "category": _("Hardware: delivery and payment costs"),
                          "product": ", ".join(str(label) for label, _amount in costs), "count": 0,
                          "revenue": sum((amount for _label, amount in costs), Decimal("0")), "cost": Decimal("0"),
                          "label": order.number, "url": ("admin:orders_order_change", order.pk), "exact": True})
    return items


def part_items(start, end):
    from django.db.models import Sum

    from apps.parts.models import Correction, PartOrder, PartOrderLine

    orders = (PartOrder.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
              .exclude(status=PartOrder.Status.CANCELLED).select_related("customer"))
    orders = {o.pk: o for o in orders}
    corrected = dict(Correction.objects.filter(line__order__in=orders.keys()).values("line")
                     .annotate(n=Sum("quantity")).values_list("line", "n"))
    category, extras = _("Spare parts"), _("Spare parts: surcharges and costs")
    items = []
    for line in PartOrderLine.objects.filter(order__in=orders.keys()).select_related("request_line"):
        order = orders[line.order_id]
        quantity = max(line.quantity + corrected.get(line.pk, 0), 0)
        if not quantity:
            continue
        revenue = (line.unit_price * quantity * (HUNDRED - order.discount_pct) / HUNDRED).quantize(Decimal("0.01"))
        part = line.request_line
        items.append({"when": order.created_at, "customer": order.customer, "category": category,
                      "product": f"{part.article_number} ({line.get_packing_display()})", "count": quantity,
                      "revenue": revenue, "cost": (line.purchase_price or Decimal("0")) * quantity, "label": order.number,
                      "url": ("admin:parts_partorder_change", order.pk), "exact": True})
    for order in orders.values():
        costs = order.costs()
        if costs:
            items.append({"when": order.created_at, "customer": order.customer, "category": extras,
                          "product": ", ".join(str(label) for label, _amount in costs), "count": 0,
                          "revenue": sum((amount for _label, amount in costs), Decimal("0")), "cost": Decimal("0"),
                          "label": order.number, "url": ("admin:parts_partorder_change", order.pk), "exact": True})
    return items


def build_report(start, end, kind="all"):
    items = sale_items(start, end, kind)
    per_month = OrderedDict((key, {"revenue": Decimal(0), "cost": Decimal(0), "count": 0}) for key in _months(start, end))
    per_category = defaultdict(lambda: {"revenue": Decimal(0), "count": 0})
    per_customer = defaultdict(lambda: {"revenue": Decimal(0), "margin": Decimal(0), "count": 0})
    totals = {"revenue": Decimal(0), "cost": Decimal(0), "count": 0, "estimated": 0}
    for item in items:
        created = timezone.localtime(item["when"]).date()
        bucket = per_month.setdefault((created.year, created.month), {"revenue": Decimal(0), "cost": Decimal(0), "count": 0})
        for target in (bucket, totals):
            target["revenue"] += item["revenue"]
            target["cost"] += item["cost"]
            target["count"] += item["count"]
        if not item["exact"]:
            totals["estimated"] += 1
        per_category[item["category"]]["revenue"] += item["revenue"]
        per_category[item["category"]]["count"] += item["count"]
        per_customer[item["customer"].name]["revenue"] += item["revenue"]
        per_customer[item["customer"].name]["margin"] += item["revenue"] - item["cost"]
        per_customer[item["customer"].name]["count"] += item["count"]
    sales = [{**item, "date": timezone.localtime(item["when"]).date(), "margin": item["revenue"] - item["cost"]}
             for item in sorted(items, key=lambda i: i["when"], reverse=True)[:500]]
    totals["margin"] = totals["revenue"] - totals["cost"]
    totals["margin_pct"] = (totals["margin"] / totals["revenue"] * HUNDRED) if totals["revenue"] else None
    return {
        "totals": totals,
        "months": [{"year": y, "month": m, **v, "margin": v["revenue"] - v["cost"]} for (y, m), v in per_month.items()],
        "categories": sorted(({"name": k, **v} for k, v in per_category.items()), key=lambda r: -r["revenue"]),
        "customers": sorted(({"name": k, **v} for k, v in per_customer.items()), key=lambda r: -r["revenue"])[:10],
        "sales": sales,
    }


def bar_chart(months, height=180):
    """Geometry for an SVG bar chart of revenue (bar) and margin (inner bar) per month."""
    peak = max([m["revenue"] for m in months] + [Decimal(1)])
    width = 36
    bars = []
    for i, m in enumerate(months):
        rev_h = float(m["revenue"] / peak) * height
        mar_h = max(float(m["margin"] / peak) * height, 0)
        first, last = month_range(m["year"], m["month"])
        bars.append({
            "url": f"?from={first.isoformat()}&to={last.isoformat()}",
            "x": i * (width + 8), "w": width, "rev_y": height - rev_h, "rev_h": rev_h, "mar_y": height - mar_h, "mar_h": mar_h,
            "label": f"{m['month']:02d}/{m['year'] % 100:02d}", "revenue": m["revenue"], "margin": m["margin"], "count": m["count"],
        })
    return {"bars": bars, "height": height, "width": len(months) * (width + 8), "peak": peak}


@staff_member_required
def report_view(request):
    if not request.user.has_perm("dashboard.view_reports"):
        raise PermissionDenied
    choice, start, end = parse_range(request, timezone.localdate())
    kind = request.GET.get("kind") if request.GET.get("kind") in KINDS else "all"
    report = build_report(start, end, kind)
    top = max([c["revenue"] for c in report["categories"]] + [Decimal(1)])
    for c in report["categories"]:
        c["pct"] = float(c["revenue"] / top * 100)
    packs = SupportPack.objects.select_related("category", "period").order_by("category__position", "price")
    price_list = [{
        "pack": p, "price": p.price, "cost": p.cost_price, "margin": p.price - p.cost_price,
        "margin_pct": ((p.price - p.cost_price) / p.price * HUNDRED) if p.price else None,
    } for p in packs]
    context = {
        **admin.site.each_context(request),
        "title": _("Sales and margin"),
        "report": report, "chart": bar_chart(report["months"]), "price_list": price_list,
        "period": choice, "start": start, "end": end, "kind": kind,
        "kinds": [("all", _("Everything")), ("packs", _("Service packs")), ("parts", _("Spare parts")),
                  ("hardware", _("Hardware"))],
        "periods": [("12m", _("Last 12 months")), ("this_year", _("This year")), ("last_year", _("Last year"))],
    }
    return render(request, "dashboard/report.html", context)
