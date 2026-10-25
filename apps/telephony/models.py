"""Telephony: a calculator in the customer portal that makes a quote for a phone system, to hire per month
or to buy. Items have a hire price per month and/or a purchase price (one-off and/or per month). Some items
count themselves: their quantity is the sum of other items (e.g. one user licence per phone)."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.orders.models import HUNDRED, money


class TelephonySettings(models.Model):
    enabled = models.BooleanField(_("telephony calculator active"), default=False)
    installation_costs = models.DecimalField(_("one-off installation costs (€)"), max_digits=8, decimal_places=2,
                                             default=Decimal("0"))
    default_margin = models.DecimalField(_("default margin (%)"), max_digits=5, decimal_places=2, default=Decimal("10"),
                                         help_text=_("Suggested margin for resellers on hire and purchase prices."))
    intro = models.TextField(_("introduction on calculator page"), blank=True)
    terms_text = models.TextField(_("text under each quote"), blank=True)

    class Meta:
        verbose_name = _("telephony settings")
        verbose_name_plural = _("telephony settings")

    def __str__(self):
        return str(_("Telephony settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class Category(models.Model):
    name = models.CharField(_("name"), max_length=120)
    position = models.PositiveSmallIntegerField(_("order"), default=0)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("telephony category")
        verbose_name_plural = _("telephony categories")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items", verbose_name=_("category"))
    name = models.CharField(_("name"), max_length=250)
    description = models.TextField(_("description"), blank=True)
    image = models.ImageField(_("image"), upload_to="telephony/", blank=True)
    hire_per_month = models.DecimalField(_("hire per month (€)"), max_digits=8, decimal_places=2, null=True, blank=True,
                                         help_text=_("Empty = cannot be hired."))
    buy_price = models.DecimalField(_("purchase price (€)"), max_digits=8, decimal_places=2, null=True, blank=True,
                                    help_text=_("One-off when bought. Empty = nothing one-off."))
    buy_per_month = models.DecimalField(_("per month when bought (€)"), max_digits=8, decimal_places=2, null=True,
                                        blank=True, help_text=_("E.g. licences or subscriptions that also cost "
                                                                "something per month when the system is bought."))
    quantity_from = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="+", verbose_name=_("quantity = sum of"),
        help_text=_("The quantity is counted automatically: the total of these items (e.g. one user licence "
                    "per phone)."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("telephony item")
        verbose_name_plural = _("telephony items")
        ordering = ["category__position", "position", "name"]

    def __str__(self):
        return self.name


class Quote(models.Model):
    class View(models.TextChoices):
        CUSTOMER = "customer", _("For my customer (prices with my margin)")
        RESELLER = "reseller", _("For myself (purchase prices and margin)")

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="telephony_quotes", verbose_name=_("customer"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("made by"))
    reference = models.CharField(_("reference"), max_length=200, blank=True)
    view = models.CharField(_("view"), max_length=10, choices=View.choices, default=View.CUSTOMER)
    margin_hire = models.DecimalField(_("margin hire (%)"), max_digits=6, decimal_places=2, default=Decimal("0"))
    margin_buy = models.DecimalField(_("margin purchase (%)"), max_digits=6, decimal_places=2, default=Decimal("0"))
    installation_costs = models.DecimalField(_("installation costs"), max_digits=8, decimal_places=2,
                                             default=Decimal("0"))
    old_price_per_port = models.DecimalField(_("price per port (previous webshop)"), max_digits=8, decimal_places=2, null=True,
                                             blank=True, editable=False)
    created_at = models.DateTimeField(_("made at"), default=timezone.now)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("telephony quote")
        verbose_name_plural = _("telephony quotes")
        ordering = ["-created_at"]

    def __str__(self):
        return f"T{self.pk}" + (f" · {self.reference}" if self.reference else "")

    def totals(self):
        return calculate([(line.item, line.quantity, line) for line in self.lines.select_related("item")],
                         self.margin_hire, self.margin_buy, self.installation_costs)


class QuoteLine(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name=_("item"))
    quantity = models.PositiveIntegerField(_("quantity"))
    hire_per_month = models.DecimalField(_("hire per month"), max_digits=8, decimal_places=2, null=True, blank=True)
    buy_price = models.DecimalField(_("purchase price"), max_digits=8, decimal_places=2, null=True, blank=True)
    buy_per_month = models.DecimalField(_("per month when bought"), max_digits=8, decimal_places=2, null=True, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("quote line")
        verbose_name_plural = _("quote lines")
        ordering = ["item__category__position", "item__position", "pk"]

    def __str__(self):
        return f"{self.quantity} × {self.item}"


def with_margin(amount, pct):
    return money(amount * (1 + pct / HUNDRED))


def automatic_quantities(items, quantities):
    """Fill in the quantities of items that count other items (repeated, so chains like phones → user
    licences → installation work out). `quantities` = {item pk: quantity}."""
    result = dict(quantities)
    counted = [(item, [i.pk for i in item.quantity_from.all()]) for item in items]
    counted = [(item, sources) for item, sources in counted if sources]
    for _round in range(5):
        changed = False
        for item, sources in counted:
            total = sum(result.get(pk, 0) for pk in sources)
            if result.get(item.pk) != total:
                result[item.pk], changed = total, True
        if not changed:
            break
    return result


def calculate(rows, margin_hire, margin_buy, installation_costs=Decimal("0")):
    """rows: [(item, quantity, prices)] where prices has hire_per_month, buy_price, buy_per_month (an item or a
    saved quote line). Purchase prices get the margin added (price × (1 + margin %))."""
    lines = []
    hire = buy_once = buy_monthly = Decimal("0")
    for item, quantity, prices in rows:
        if not quantity:
            continue
        line = {"item": item, "quantity": quantity}
        for field, pct in (("hire_per_month", margin_hire), ("buy_price", margin_buy), ("buy_per_month", margin_buy)):
            cost = getattr(prices, field)
            line[f"{field}_cost"] = cost
            line[field] = with_margin(cost, pct) if cost is not None else None
            line[f"{field}_total"] = money(line[field] * quantity) if cost is not None else None
        hire += line["hire_per_month_total"] or 0
        buy_once += line["buy_price_total"] or 0
        buy_monthly += line["buy_per_month_total"] or 0
        lines.append(line)
    return {"lines": lines, "hire_per_month": hire, "buy_once": buy_once + installation_costs,
            "buy_per_month": buy_monthly, "installation_costs": installation_costs,
            "hire_once": installation_costs}
