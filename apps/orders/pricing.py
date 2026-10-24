from decimal import Decimal

from .models import HUNDRED, money


def preview(customer, lines, vat_rate):
    """Totals as the order will get them (same rules as Order.recalculate)."""
    rows = [{**line, "unit_price": line["pack"].price, "line_total": money(line["pack"].price * line["quantity"])}
            for line in lines]
    gross = money(sum((r["line_total"] for r in rows), Decimal("0")))
    pct = customer.margin_packs or Decimal("0")
    discount = money(gross * pct / HUNDRED)
    net = gross - discount
    vat = money(net * vat_rate / HUNDRED)
    return {"rows": rows, "gross": gross, "discount_pct": pct, "discount": discount, "net": net,
            "vat_rate": vat_rate, "vat": vat, "total": net + vat}


def extension_packs(licence):
    """Packs a licence can be extended with: same category and hardware class, post-warranty first."""
    from apps.licences.models import SupportPack

    packs = SupportPack.objects.filter(enabled=True, category=licence.pack.category,
                                       hardware_class=licence.pack.hardware_class)
    post = packs.filter(period__post_warranty=True)
    return (post if post.exists() else packs).order_by("period__years", "price")
