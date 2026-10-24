"""Spare parts: a customer asks for parts (request), the company answers with prices and delivery times per
packing (new, pack, refurbished), the customer orders from that answer, and the order is delivered (in
parts if needed), corrected or cancelled.

Prices entered on a request are purchase prices. The selling price is the purchase price times a markup
that depends on the price (Markup tiers); on the order the customer's own discount for parts is taken off.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.orders.models import HUNDRED, money


class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class PartsSettings(SingletonModel):
    """Rules and texts for spare parts (one row)."""

    enabled = models.BooleanField(_("spare parts active"), default=True,
                                  help_text=_("Customers can ask for spare parts and order them."))
    quote_valid_days = models.PositiveIntegerField(_("an answered request is valid for (days)"), default=30)
    small_order_limit = models.DecimalField(
        _("small order below (€)"), max_digits=8, decimal_places=2, default=Decimal("50"),
        help_text=_("Orders below this amount (excl. VAT, after discount) get the small order surcharge."),
    )
    small_order_costs = models.DecimalField(_("small order surcharge (€)"), max_digits=8, decimal_places=2,
                                            default=Decimal("15"))
    foreign_delivery_costs = models.DecimalField(
        _("delivery costs abroad (€)"), max_digits=8, decimal_places=2, default=Decimal("18"),
        help_text=_("Added when the delivery address is outside the home country."),
    )
    home_country = models.ForeignKey(
        "customers.Country", on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("home country"),
        help_text=_("Deliveries outside this country pay the delivery costs abroad. If both the delivery and the "
                    "invoice address are abroad, no VAT is charged (intra-community delivery)."),
    )
    approval_limit = models.DecimalField(
        _("approval needed from (€)"), max_digits=10, decimal_places=2, default=Decimal("2000"),
        help_text=_("Orders on account from this amount (incl. VAT) wait for approval before delivery."),
    )
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=Decimal("21"))
    max_quantity = models.PositiveIntegerField(_("maximum quantity per line"), default=150)
    intro = models.TextField(_("introduction on request page"), blank=True)
    terms_text = models.TextField(_("terms shown before ordering"), blank=True)
    notify_emails = models.CharField(
        _("internal recipients"), max_length=300, blank=True,
        help_text=_("Get new requests, orders, cancellations and corrections. Email addresses separated by commas."),
    )

    class Meta:
        verbose_name = _("spare parts settings")
        verbose_name_plural = _("spare parts settings")

    def __str__(self):
        return str(_("Spare parts settings"))

    def internal_recipients(self):
        return [e.strip() for e in self.notify_emails.split(",") if e.strip()]


class MarkupTier(models.Model):
    """Selling price = purchase price × factor of the highest tier the purchase price is above."""

    above = models.DecimalField(_("purchase price above (€)"), max_digits=10, decimal_places=2, unique=True)
    factor = models.DecimalField(_("factor"), max_digits=5, decimal_places=2,
                                 help_text=_("E.g. 1.40 = selling price is 40% above the purchase price."))

    class Meta:
        verbose_name = _("markup tier")
        verbose_name_plural = _("markup tiers")
        ordering = ["above"]

    def __str__(self):
        return f"> € {self.above}: × {self.factor}"


def selling_price(purchase):
    """The selling price for a purchase price (before the customer's discount)."""
    if purchase is None:
        return None
    tier = MarkupTier.objects.filter(above__lt=purchase).order_by("-above").first()
    return money(purchase * (tier.factor if tier else Decimal("1")))


class DeliveryTime(models.Model):
    code = models.SlugField(_("code"), max_length=32, unique=True, help_text=_("Internal code, e.g. in_stock."))
    name = models.CharField(_("name"), max_length=100)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("delivery time")
        verbose_name_plural = _("delivery times")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class PaymentMethod(models.Model):
    code = models.SlugField(_("code"), max_length=32, unique=True)
    name = models.CharField(_("name"), max_length=100)
    on_account = models.BooleanField(
        _("on account"), default=False,
        help_text=_("Delivered before payment. Large orders wait for approval (see the settings). Without this, "
                    "an order waits until it is paid."),
    )
    extra_costs = models.DecimalField(_("extra costs (€)"), max_digits=8, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("payment method")
        verbose_name_plural = _("payment methods")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Packing(models.TextChoices):
    NEW = "new", _("New")
    PACK = "pack", _("Pack")
    REFURBISHED = "refurbished", _("Refurbished")


class AddressFields(models.Model):
    delivery_name = models.CharField(_("delivery to (company)"), max_length=200, blank=True)
    delivery_contact = models.CharField(_("delivery contact"), max_length=200, blank=True)
    delivery_address = models.CharField(_("delivery address"), max_length=200, blank=True)
    delivery_postal_code = models.CharField(_("delivery postal code"), max_length=20, blank=True)
    delivery_city = models.CharField(_("delivery city"), max_length=100, blank=True)
    delivery_country = models.CharField(_("delivery country"), max_length=100, blank=True)
    delivery_phone = models.CharField(_("delivery phone"), max_length=40, blank=True)

    class Meta:
        abstract = True

    def delivery_lines(self):
        return [v for v in (self.delivery_name, self.delivery_contact, self.delivery_address,
                            f"{self.delivery_postal_code} {self.delivery_city}".strip(), self.delivery_country) if v]


class PartRequest(AddressFields):
    """A customer's request for one or more spare parts; answered with prices per line."""

    class Status(models.TextChoices):
        TO_HANDLE = "to_handle", _("To handle")
        ANSWERED = "answered", _("Answered")

    number = models.CharField(_("request number"), max_length=32, unique=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="part_requests",
                                 verbose_name=_("customer"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("requested by"))
    reference = models.CharField(_("your reference"), max_length=128, blank=True)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.TO_HANDLE,
                              db_index=True)
    urgent = models.BooleanField(_("urgent"), default=False)
    urgent_possible = models.BooleanField(_("urgent delivery possible"), null=True, blank=True)
    urgent_costs = models.DecimalField(_("urgent delivery costs (€)"), max_digits=8, decimal_places=2,
                                       null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    created_at = models.DateTimeField(_("requested at"), default=timezone.now)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("spare parts request")
        verbose_name_plural = _("spare parts requests")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    def is_valid(self):
        return self.valid_until is None or self.valid_until >= timezone.localdate()

    def is_complete(self):
        """Answered: urgent costs known (if urgent) and no line still open or being looked into."""
        if self.urgent and self.urgent_possible and self.urgent_costs is None:
            return False
        return not self.lines.filter(status__in=[RequestLine.Status.OPEN, RequestLine.Status.HANDLING]).exists()

    def update_status(self):
        self.status = self.Status.ANSWERED if self.is_complete() else self.Status.TO_HANDLE
        self.save(update_fields=["status", "updated_at"])

    def orderable_lines(self):
        return [line for line in self.lines.all() if line.is_orderable()]


class RequestLine(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        HANDLING = "handling", _("Answer follows soon")
        INFORMATION = "information", _("More information needed")
        UNAVAILABLE = "unavailable", _("Not available")
        AGREED = "agreed", _("Price known")

    request = models.ForeignKey(PartRequest, on_delete=models.CASCADE, related_name="lines")
    article_number = models.CharField(_("article number"), max_length=64)
    vendor = models.ForeignKey("licences.Vendor", on_delete=models.PROTECT, null=True, blank=True,
                               verbose_name=_("brand"))
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    description = models.TextField(_("description"), blank=True)
    info = models.TextField(_("extra information"), blank=True)
    machine_model = models.CharField(_("device model"), max_length=64, blank=True)
    machine_serial = models.CharField(_("device serial number"), max_length=64, blank=True)
    machine_description = models.TextField(_("device description"), blank=True)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.OPEN)
    price_new = models.DecimalField(_("purchase price new"), max_digits=10, decimal_places=2, null=True, blank=True)
    price_pack = models.DecimalField(_("purchase price pack"), max_digits=10, decimal_places=2, null=True, blank=True)
    price_refurbished = models.DecimalField(_("purchase price refurbished"), max_digits=10, decimal_places=2,
                                            null=True, blank=True)
    time_new = models.ForeignKey(DeliveryTime, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                 verbose_name=_("delivery time new"))
    time_pack = models.ForeignKey(DeliveryTime, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                  verbose_name=_("delivery time pack"))
    time_refurbished = models.ForeignKey(DeliveryTime, on_delete=models.PROTECT, null=True, blank=True,
                                         related_name="+", verbose_name=_("delivery time refurbished"))
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("requested part")
        verbose_name_plural = _("requested parts")
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.quantity} × {self.article_number}"

    def purchase_price(self, packing):
        return getattr(self, f"price_{packing}")

    def delivery_time(self, packing):
        return getattr(self, f"time_{packing}")

    def offers(self):
        """What the customer can choose from: per packing with a price, the selling price and delivery time."""
        return [{"packing": p, "label": label, "purchase": self.purchase_price(p),
                 "price": selling_price(self.purchase_price(p)), "time": self.delivery_time(p)}
                for p, label in Packing.choices if self.purchase_price(p) is not None]

    def is_orderable(self):
        request = self.request
        if self.status != self.Status.AGREED or not request.is_valid():
            return False
        return not (request.urgent and request.urgent_possible and request.urgent_costs is None)


class RequestLineChange(models.Model):
    """Who answered or changed a requested part, and when (status, prices and delivery times at that moment)."""

    line = models.ForeignKey(RequestLine, on_delete=models.CASCADE, related_name="changes")
    changed_at = models.DateTimeField(_("changed at"), default=timezone.now)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             verbose_name=_("by"))
    status = models.CharField(_("status"), max_length=12, choices=RequestLine.Status.choices)
    price_new = models.DecimalField(_("new"), max_digits=10, decimal_places=2, null=True, blank=True)
    price_pack = models.DecimalField(_("pack"), max_digits=10, decimal_places=2, null=True, blank=True)
    price_refurbished = models.DecimalField(_("refurbished"), max_digits=10, decimal_places=2, null=True, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("change")
        verbose_name_plural = _("changes")
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.get_status_display()} ({self.changed_at:%d-%m-%Y %H:%M})"


class Remark(models.Model):
    """A message about a requested part, from the customer or from the company."""

    line = models.ForeignKey(RequestLine, on_delete=models.CASCADE, related_name="remarks")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               verbose_name=_("by"))
    from_customer = models.BooleanField(_("from customer"), default=False)
    text = models.TextField(_("remark"))
    created_at = models.DateTimeField(_("at"), default=timezone.now)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("remark")
        verbose_name_plural = _("remarks")
        ordering = ["-created_at"]

    def __str__(self):
        return self.text[:60]


class PartOrder(AddressFields):
    class Status(models.TextChoices):
        AWAITING_PAYMENT = "payment", _("Waiting for payment")
        AWAITING_APPROVAL = "approval", _("Waiting for approval")
        TO_DELIVER = "deliver", _("To deliver")
        DONE = "done", _("Done")
        CANCELLED = "cancelled", _("Cancelled")

    number = models.CharField(_("order number"), max_length=40, unique=True)
    request = models.ForeignKey(PartRequest, on_delete=models.PROTECT, related_name="orders",
                                verbose_name=_("request"))
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="part_orders",
                                 verbose_name=_("customer"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("ordered by"))
    created_at = models.DateTimeField(_("ordered at"), default=timezone.now)
    reference = models.CharField(_("your reference"), max_length=128, blank=True)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.TO_DELIVER,
                              db_index=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, null=True, blank=True,
                                       verbose_name=_("payment method"))
    urgent = models.BooleanField(_("urgent"), default=False)
    being_picked = models.BooleanField(_("being picked"), default=False,
                                       help_text=_("Marks that someone is getting this order ready."))

    discount_pct = models.DecimalField(_("discount (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    urgent_costs = models.DecimalField(_("urgent delivery costs"), max_digits=8, decimal_places=2, null=True, blank=True)
    small_order_costs = models.DecimalField(_("small order surcharge"), max_digits=8, decimal_places=2, null=True,
                                            blank=True)
    handling_costs = models.DecimalField(_("handling costs"), max_digits=8, decimal_places=2, null=True, blank=True)
    payment_costs = models.DecimalField(_("payment costs"), max_digits=8, decimal_places=2, null=True, blank=True)
    delivery_costs = models.DecimalField(_("delivery costs"), max_digits=8, decimal_places=2, null=True, blank=True)
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=Decimal("21"))
    gross = models.DecimalField(_("parts"), max_digits=12, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(_("discount"), max_digits=12, decimal_places=2, default=Decimal("0"))
    net = models.DecimalField(_("total excl. VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))
    vat = models.DecimalField(_("VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(_("total incl. VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))

    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", verbose_name=_("approved by"))
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancel_reason = models.TextField(_("reason for cancelling"), blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("spare parts order")
        verbose_name_plural = _("spare parts orders")
        ordering = ["-created_at"]
        permissions = [("deliver_partorder", _("Can deliver and correct spare parts orders"))]

    def __str__(self):
        return self.number

    def costs(self):
        """The extra cost lines, as (label, amount)."""
        return [(label, amount) for label, amount in (
            (_("Urgent delivery"), self.urgent_costs), (_("Small order surcharge"), self.small_order_costs),
            (_("Handling costs"), self.handling_costs), (_("Payment costs"), self.payment_costs),
            (_("Delivery costs"), self.delivery_costs),
        ) if amount]

    def recalculate(self):
        self.gross = money(sum((line.line_total for line in self.lines.all()), Decimal("0")))
        self.discount = money(self.gross * self.discount_pct / HUNDRED)
        self.net = self.gross - self.discount + sum((amount for _label, amount in self.costs()), Decimal("0"))
        self.vat = money(self.net * self.vat_rate / HUNDRED)
        self.total = self.net + self.vat

    def is_delivered(self):
        return all(line.to_deliver() == 0 for line in self.lines.all())

    def is_open(self):
        return self.status not in (self.Status.DONE, self.Status.CANCELLED)


class PartOrderLine(models.Model):
    order = models.ForeignKey(PartOrder, on_delete=models.CASCADE, related_name="lines")
    request_line = models.ForeignKey(RequestLine, on_delete=models.PROTECT, related_name="order_lines",
                                     verbose_name=_("requested part"))
    packing = models.CharField(_("packing"), max_length=12, choices=Packing.choices)
    quantity = models.PositiveIntegerField(_("quantity"))
    purchase_price = models.DecimalField(_("purchase price"), max_digits=10, decimal_places=2, null=True, blank=True)
    unit_price = models.DecimalField(_("price each"), max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(_("created"), default=timezone.now)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("ordered part")
        verbose_name_plural = _("ordered parts")
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.quantity} × {self.request_line.article_number} ({self.get_packing_display()})"

    @property
    def line_total(self):
        return money(self.unit_price * self.quantity)

    def delivered(self):
        return self.deliveries.aggregate(n=Sum("quantity"))["n"] or 0

    def corrected(self):
        """Negative: fewer parts than ordered after a correction."""
        return self.corrections.aggregate(n=Sum("quantity"))["n"] or 0

    def to_deliver(self):
        return max(self.quantity + self.corrected() - self.delivered(), 0)


class Delivery(models.Model):
    line = models.ForeignKey(PartOrderLine, on_delete=models.CASCADE, related_name="deliveries")
    quantity = models.IntegerField(_("quantity"), help_text=_("Negative: parts taken back."))
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             verbose_name=_("by"))
    created_at = models.DateTimeField(_("delivered at"), default=timezone.now)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("delivery")
        verbose_name_plural = _("deliveries")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.quantity} × {self.line.request_line.article_number}"


class Correction(models.Model):
    line = models.ForeignKey(PartOrderLine, on_delete=models.CASCADE, related_name="corrections")
    quantity = models.IntegerField(_("quantity"), help_text=_("Negative: fewer parts than ordered."))
    reason = models.TextField(_("reason"), blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             verbose_name=_("by"))
    created_at = models.DateTimeField(_("corrected at"), default=timezone.now)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("correction")
        verbose_name_plural = _("corrections")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.quantity} × {self.line.request_line.article_number}"


# --- placing an order -------------------------------------------------------------------------------


def is_abroad(country_name):
    """True when a country (name or code, in any language) is not the home country of the settings."""
    home = PartsSettings.load().home_country
    if not home or not country_name:
        return False
    names = {home.code.lower(), home.name.lower()}
    names |= {(getattr(home, f"name_{code}", "") or "").lower() for code, _label in settings.LANGUAGES}
    return country_name.strip().lower() not in names


def price_order(customer, request, choices, payment_method=None, delivery=None, urgent=False):
    """The order as it will be: lines and totals, without saving. `choices` is a list of
    (request line, packing, quantity). Same rules as the previous webshop."""
    rules = PartsSettings.load()
    order = PartOrder(customer=customer, request=request, discount_pct=customer.margin_parts or Decimal("0"),
                      vat_rate=rules.vat_rate, urgent=urgent, payment_method=payment_method, **(delivery or {}))
    lines = [PartOrderLine(request_line=line, packing=packing, quantity=quantity,
                           purchase_price=line.purchase_price(packing), unit_price=selling_price(line.purchase_price(packing)))
             for line, packing, quantity in choices if quantity]
    gross = money(sum((line.line_total for line in lines), Decimal("0")))
    discount = money(gross * order.discount_pct / HUNDRED)
    if gross - discount < rules.small_order_limit:
        order.small_order_costs = rules.small_order_costs
    if urgent and request.urgent_costs:
        order.urgent_costs = request.urgent_costs
    if payment_method and payment_method.extra_costs:
        order.payment_costs = payment_method.extra_costs
    if is_abroad(order.delivery_country):
        order.delivery_costs = rules.foreign_delivery_costs
        invoice_address = customer.address("invoice")
        if invoice_address and invoice_address.country and is_abroad(str(invoice_address.country)):
            order.vat_rate = Decimal("0")
    order.gross, order.discount = gross, discount
    order.net = gross - discount + sum((amount for _label, amount in order.costs()), Decimal("0"))
    order.vat = money(order.net * order.vat_rate / HUNDRED)
    order.total = order.net + order.vat
    return order, lines


def place_order(customer, user, request, choices, payment_method, reference="", delivery=None, urgent=False):
    rules = PartsSettings.load()
    order, lines = price_order(customer, request, choices, payment_method, delivery, urgent)
    with transaction.atomic():
        count = PartOrder.objects.filter(request=request).count()
        order.number = f"{request.number}-{count + 1}"
        while PartOrder.objects.filter(number=order.number).exists():
            count += 1
            order.number = f"{request.number}-{count + 1}"
        order.created_by, order.reference = user, reference
        if not payment_method.on_account:
            order.status = PartOrder.Status.AWAITING_PAYMENT
        elif order.total >= rules.approval_limit:
            order.status = PartOrder.Status.AWAITING_APPROVAL
        else:
            order.status = PartOrder.Status.TO_DELIVER
        order.save()
        for line in lines:
            line.order = order
            line.save()
    return order
