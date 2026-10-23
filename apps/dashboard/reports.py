"""Sales report: revenue, cost and margin per month, per category and per customer.

Until orders and invoices live in PackDesk, a sold pack is a licence, valued at the pack's current
price minus the customer's service pack discount, and the pack's current cost price. The page says so.
"""

from collections import OrderedDict, defaultdict
from datetime import date
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


def build_report(start, end):
    licences = (Licence.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
                .select_related("pack__category", "customer"))
    per_month = OrderedDict((key, {"revenue": Decimal(0), "cost": Decimal(0), "count": 0}) for key in _months(start, end))
    per_category = defaultdict(lambda: {"revenue": Decimal(0), "count": 0})
    per_customer = defaultdict(lambda: {"revenue": Decimal(0), "margin": Decimal(0), "count": 0})
    totals = {"revenue": Decimal(0), "cost": Decimal(0), "count": 0}
    for lic in licences:
        revenue, cost = sale_values(lic)
        created = timezone.localtime(lic.created_at).date()
        bucket = per_month.setdefault((created.year, created.month), {"revenue": Decimal(0), "cost": Decimal(0), "count": 0})
        for target in (bucket, totals):
            target["revenue"] += revenue
            target["cost"] += cost
            target["count"] += 1
        per_category[str(lic.pack.category)]["revenue"] += revenue
        per_category[str(lic.pack.category)]["count"] += 1
        per_customer[lic.customer.name]["revenue"] += revenue
        per_customer[lic.customer.name]["margin"] += revenue - cost
        per_customer[lic.customer.name]["count"] += 1
    totals["margin"] = totals["revenue"] - totals["cost"]
    totals["margin_pct"] = (totals["margin"] / totals["revenue"] * HUNDRED) if totals["revenue"] else None
    return {
        "totals": totals,
        "months": [{"year": y, "month": m, **v, "margin": v["revenue"] - v["cost"]} for (y, m), v in per_month.items()],
        "categories": sorted(({"name": k, **v} for k, v in per_category.items()), key=lambda r: -r["revenue"]),
        "customers": sorted(({"name": k, **v} for k, v in per_customer.items()), key=lambda r: -r["revenue"])[:10],
    }


def bar_chart(months, height=180):
    """Geometry for an SVG bar chart of revenue (bar) and margin (inner bar) per month."""
    peak = max([m["revenue"] for m in months] + [Decimal(1)])
    width = 36
    bars = []
    for i, m in enumerate(months):
        rev_h = float(m["revenue"] / peak) * height
        mar_h = max(float(m["margin"] / peak) * height, 0)
        bars.append({
            "x": i * (width + 8), "w": width, "rev_y": height - rev_h, "rev_h": rev_h, "mar_y": height - mar_h, "mar_h": mar_h,
            "label": f"{m['month']:02d}/{m['year'] % 100:02d}", "revenue": m["revenue"], "margin": m["margin"], "count": m["count"],
        })
    return {"bars": bars, "height": height, "width": len(months) * (width + 8), "peak": peak}


@staff_member_required
def report_view(request):
    if not request.user.has_perm("dashboard.view_reports"):
        raise PermissionDenied
    choice = request.GET.get("period", "12m")
    start, end = _period(choice, timezone.localdate())
    report = build_report(start, end)
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
        "period": choice, "start": start, "end": end,
        "periods": [("12m", _("Last 12 months")), ("this_year", _("This year")), ("last_year", _("Last year"))],
    }
    return render(request, "dashboard/report.html", context)
