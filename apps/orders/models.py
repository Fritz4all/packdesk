from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class OrderSettings(models.Model):
    """Rules and texts for ordering and extending service packs (one row)."""

    enabled = models.BooleanField(_("ordering active"), default=True)
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=Decimal("21"))
    intro = models.TextField(_("introduction on order page"), blank=True)
    terms_text = models.TextField(
        _("terms shown before ordering"), blank=True, help_text=_("E.g. which terms and conditions apply."),
    )
    allow_boxes = models.BooleanField(
        _("customers can ask for physical packs"), default=True,
        help_text=_("Shows the option to receive boxes with labels at a delivery address."),
    )
    extend_window_days = models.PositiveIntegerField(
        _("licences can be extended from (days before end)"), default=90,
    )
    notify_emails = models.CharField(
        _("internal recipients of orders"), max_length=300, blank=True, help_text=_("Email addresses separated by commas."),
    )
    confirmation_text = models.TextField(
        _("text in order confirmation"), blank=True, help_text=_("Shown at the top of the confirmation email."),
    )

    class Meta:
        verbose_name = _("order settings")
        verbose_name_plural = _("order settings")

    def __str__(self):
        return str(_("Order settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class PaymentMethod(models.Model):
    """How a customer pays: on account, cash on delivery, pro forma, ... Shared by spare parts and hardware; per
    method you choose where it is offered."""

    code = models.SlugField(_("code"), max_length=32, unique=True)
    name = models.CharField(_("name"), max_length=100)
    on_account = models.BooleanField(
        _("on account"), default=False,
        help_text=_("Delivered before payment. Large orders wait for approval (see the settings). Without this, "
                    "an order waits until it is paid."),
    )
    extra_costs = models.DecimalField(_("extra costs (€)"), max_digits=8, decimal_places=2, null=True, blank=True)
    for_parts = models.BooleanField(_("for spare parts"), default=True)
    for_hardware = models.BooleanField(_("for hardware"), default=True)
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("payment method")
        verbose_name_plural = _("payment methods")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Order(models.Model):
    """An order of service packs, or of hardware (devices, with delivery and payment). Both get an invoice."""

    class Kind(models.TextChoices):
        PACKS = "packs", _("Service packs")
        HARDWARE = "hardware", _("Hardware")

    number = models.CharField(_("order number"), max_length=32, db_index=True)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.PACKS, db_index=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="orders", verbose_name=_("customer"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+", verbose_name=_("ordered by"))
    created_at = models.DateTimeField(_("ordered at"), default=timezone.now)
    reference = models.CharField(_("your reference"), max_length=128, blank=True, help_text=_("Shown on the invoice."))

    gross = models.DecimalField(_("subtotal"), max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_pct = models.DecimalField(_("discount (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(_("discount"), max_digits=12, decimal_places=2, default=Decimal("0"))
    net = models.DecimalField(_("total excl. VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=Decimal("21"))
    vat = models.DecimalField(_("VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(_("total incl. VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))

    send_boxes = models.BooleanField(_("send physical packs"), default=False)
    delivery_name = models.CharField(_("delivery to (company)"), max_length=128, blank=True)
    delivery_contact = models.CharField(_("delivery contact"), max_length=128, blank=True)
    delivery_address = models.CharField(_("delivery address"), max_length=200, blank=True)
    delivery_postal_code = models.CharField(_("delivery postal code"), max_length=20, blank=True)
    delivery_city = models.CharField(_("delivery city"), max_length=100, blank=True)
    boxes_sent = models.BooleanField(_("packs sent"), default=False)

    # Hardware: how it gets to the customer and how it is paid; the costs are added to the total.
    delivery_method = models.CharField(_("delivery"), max_length=100, blank=True)
    shipping = models.BooleanField(_("shipped"), default=False)
    delivery_costs = models.DecimalField(_("delivery costs"), max_digits=8, decimal_places=2, null=True, blank=True)
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="orders", verbose_name=_("payment method"))
    payment_costs = models.DecimalField(_("payment costs"), max_digits=8, decimal_places=2, null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)

    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} · {self.customer.name}"

    def costs(self):
        """The extra cost lines, as (label, amount)."""
        return [(label, amount) for label, amount in (
            (_("Delivery costs"), self.delivery_costs), (_("Payment costs"), self.payment_costs),
        ) if amount]

    def recalculate(self):
        self.gross = money(sum((line.line_total for line in self.lines.all()), Decimal("0")))
        self.discount = money(self.gross * self.discount_pct / HUNDRED)
        self.net = self.gross - self.discount + sum((amount for _label, amount in self.costs()), Decimal("0"))
        self.vat = money(self.net * self.vat_rate / HUNDRED)
        self.total = self.net + self.vat


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    pack = models.ForeignKey("licences.SupportPack", on_delete=models.PROTECT, null=True, blank=True,
                             verbose_name=_("service pack"))
    device = models.ForeignKey("hardware.Device", on_delete=models.PROTECT, null=True, blank=True,
                               related_name="order_lines", verbose_name=_("device"))
    description = models.CharField(_("description"), max_length=250)
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    unit_price = models.DecimalField(_("price each"), max_digits=10, decimal_places=2)
    line_total = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    reference = models.CharField(_("reference"), max_length=128, blank=True)
    extends = models.ForeignKey("licences.Licence", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="extended_by_lines", verbose_name=_("extends licence"))

    class Meta:
        verbose_name = _("order line")
        verbose_name_plural = _("order lines")

    def __str__(self):
        return f"{self.quantity} × {self.description}"


def place_order(customer, user, lines, reference="", delivery=None):
    """Create an order with its lines and the licences that come with it.

    `lines` is a list of dicts: pack, quantity, reference, extends (licence or None).
    Extension lines create a licence that continues the old one (already registered, same device).
    """
    from apps.licences.models import Licence, add_years
    from apps.numbering.models import NumberSequence

    rules = OrderSettings.load()
    with transaction.atomic():
        _n, number = NumberSequence.issue("order")
        order = Order.objects.create(
            number=number, customer=customer, created_by=user, reference=reference,
            discount_pct=customer.margin_packs or Decimal("0"), vat_rate=rules.vat_rate,
            **({"send_boxes": True, **delivery} if delivery else {}),
        )
        for data in lines:
            pack, quantity, old = data["pack"], data["quantity"], data.get("extends")
            line = OrderLine.objects.create(
                order=order, pack=pack, description=str(pack), quantity=quantity, unit_price=pack.price,
                line_total=money(pack.price * quantity), reference=data.get("reference", ""), extends=old,
            )
            if old is not None:
                start = max(old.end_date + timedelta(days=1), timezone.localdate()) if old.end_date else timezone.localdate()
                new = Licence.create_for(pack, customer, 1, order_reference=reference or number)[0]
                for field in ("vendor", "system", "description", "product_nr", "serial_nr", "purchase_date",
                              "end_customer_email", "end_customer_reference", "memo", "reseller_name", "reseller_address",
                              "reseller_postal_code", "reseller_city", "reseller_phone"):
                    setattr(new, field, getattr(old, field))
                new.prolongation_of = old
                new.registered_on = timezone.now()
                new.start_date = start
                new.end_date = add_years(start, pack.period.years) - timedelta(days=1)
                new.order_line = line
                new.save()
                for option in old.options.all():
                    option.pk = None
                    option.licence = new
                    option.save()
            elif pack.registration_required:
                for lic in Licence.create_for(pack, customer, quantity, order_reference=reference or number):
                    lic.order_line = line
                    lic.save(update_fields=["order_line"])
        order.recalculate()
        order.save()
    return order
