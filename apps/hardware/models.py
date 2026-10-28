"""Hardware for sale: desktops, laptops, monitors and the like, each piece on its own (with its serial number).

Prices are stored excluding VAT. The selling price is entered per device; left empty, it follows from the
purchase price and the standard markup (Hardware settings). On an order the customer's own discount for
hardware is taken off, like for service packs and spare parts; visitors see the price without discount.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.orders.models import HUNDRED, money


class HardwareSettings(models.Model):
    """Rules and texts for hardware (one row)."""

    enabled = models.BooleanField(_("hardware shop active"), default=True,
                                  help_text=_("Visitors and customers see the hardware for sale on the website."))
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=Decimal("21"))
    default_markup = models.DecimalField(
        _("standard markup (%)"), max_digits=6, decimal_places=2, default=Decimal("25"),
        help_text=_("Used when a device has no selling price: purchase price plus this percentage."),
    )
    default_warranty_months = models.PositiveSmallIntegerField(_("standard warranty (months)"), default=12)
    prices_incl_vat = models.BooleanField(
        _("show prices incl. VAT first"), default=True,
        help_text=_("How prices are shown on the website at first; visitors can switch between incl. and excl. VAT."),
    )
    per_page = models.PositiveSmallIntegerField(_("devices per page"), default=24,
                                                validators=[MinValueValidator(6), MaxValueValidator(96)])
    intro = models.TextField(_("introduction on the hardware page"), blank=True)
    terms_text = models.TextField(_("terms shown before ordering"), blank=True)
    notify_emails = models.CharField(
        _("internal recipients"), max_length=300, blank=True,
        help_text=_("Get new hardware orders. Email addresses separated by commas."),
    )

    class Meta:
        verbose_name = _("hardware settings")
        verbose_name_plural = _("hardware settings")

    def __str__(self):
        return str(_("Hardware settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class DeviceType(models.Model):
    """Desktop, laptop, monitor, ..."""

    name = models.CharField(_("name"), max_length=100)
    position = models.PositiveSmallIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("device type")
        verbose_name_plural = _("device types")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Specification(models.Model):
    """A property of devices of one or more types, e.g. processor, memory, screen size."""

    class Kind(models.TextChoices):
        TEXT = "text", _("Text")
        NUMBER = "number", _("Number")
        CHOICE = "choice", _("Choice from a list")
        YES_NO = "yes_no", _("Yes / no")

    key = models.CharField(
        _("code"), max_length=40, unique=True,
        validators=[RegexValidator(r"^[a-z][a-z0-9_]*$", _("Lower case letters, digits and _ only."))],
        help_text=_("Internal code, also the column name in import files, e.g. cpu or ram_gb."),
    )
    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.TEXT)
    choices = models.TextField(_("choices"), blank=True, help_text=_("For a choice from a list: one option per line."))
    unit = models.CharField(_("unit"), max_length=20, blank=True, help_text=_("E.g. GB, inch, GHz."))
    device_types = models.ManyToManyField(DeviceType, related_name="specifications", blank=True,
                                          verbose_name=_("device types"))
    required = models.BooleanField(_("required"), default=False)
    in_list = models.BooleanField(_("show in the overview"), default=True,
                                  help_text=_("Shown with each device in the list on the website."))
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("specification")
        verbose_name_plural = _("specifications")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    def options(self):
        return [line.strip() for line in self.choices.splitlines() if line.strip()]

    def display(self, value):
        """A stored value as people read it."""
        if value in (None, ""):
            return ""
        if self.kind == self.Kind.YES_NO:
            return str(_("Yes") if value else _("No"))
        return f"{value} {self.unit}".strip() if self.unit else str(value)


class Condition(models.Model):
    """New, refurbished A, refurbished B, ..."""

    name = models.CharField(_("name"), max_length=100)
    description = models.TextField(_("explanation for customers"), blank=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("condition")
        verbose_name_plural = _("conditions")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class DeliveryOption(models.Model):
    """How an order gets to the customer: picked up, or sent for a price."""

    class Kind(models.TextChoices):
        PICKUP = "pickup", _("Pick up")
        SHIPPING = "shipping", _("Shipping")

    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.SHIPPING)
    price = models.DecimalField(_("costs excl. VAT (€)"), max_digits=8, decimal_places=2, default=Decimal("0"))
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("delivery option")
        verbose_name_plural = _("delivery options")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Device(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        FOR_SALE = "for_sale", _("For sale")
        RESERVED = "reserved", _("Reserved")
        SOLD = "sold", _("Sold")
        WRITTEN_OFF = "written_off", _("Written off")

    number = models.CharField(_("stock number"), max_length=32, unique=True, editable=False)
    device_type = models.ForeignKey(DeviceType, on_delete=models.PROTECT, related_name="devices",
                                    verbose_name=_("device type"))
    brand = models.ForeignKey("licences.Vendor", on_delete=models.PROTECT, null=True, blank=True,
                              related_name="devices", verbose_name=_("brand"))
    model = models.CharField(_("model"), max_length=150)
    serial_nr = models.CharField(_("serial number"), max_length=80, unique=True)
    condition = models.ForeignKey(Condition, on_delete=models.SET_NULL, null=True, blank=True,
                                  verbose_name=_("condition"))
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.DRAFT,
                              db_index=True)

    purchase_date = models.DateField(_("purchase date"), null=True, blank=True)
    purchase_price = models.DecimalField(_("purchase price excl. VAT (€)"), max_digits=10, decimal_places=2,
                                         null=True, blank=True)
    supplier = models.CharField(_("supplier"), max_length=150, blank=True)
    sale_price = models.DecimalField(
        _("selling price excl. VAT (€)"), max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Empty = purchase price plus the standard markup (Hardware settings)."),
    )
    warranty_months = models.PositiveSmallIntegerField(
        _("warranty (months)"), null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(120)],
        help_text=_("Empty = the standard warranty (Hardware settings)."),
    )
    description = models.TextField(_("description"), blank=True)
    specs = models.JSONField(_("specifications"), default=dict, blank=True)
    internal_notes = models.TextField(_("internal notes"), blank=True)

    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="devices", verbose_name=_("sold to"))
    sold_at = models.DateTimeField(_("sold at"), null=True, blank=True)
    created_at = models.DateTimeField(_("added at"), default=timezone.now)
    updated_at = models.DateTimeField(_("changed at"), auto_now=True)

    class Meta:
        verbose_name = _("device")
        verbose_name_plural = _("devices")
        ordering = ["-created_at"]

    def __str__(self):
        brand = f"{self.brand} " if self.brand_id else ""
        return f"{self.number} · {brand}{self.model}"

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.numbering.models import NumberSequence

            _counter, self.number = NumberSequence.issue("hardware_device")
        super().save(*args, **kwargs)

    @property
    def price(self):
        """Selling price excl. VAT, before any customer discount."""
        if self.sale_price is not None:
            return self.sale_price
        if self.purchase_price is None:
            return None
        return money(self.purchase_price * (HUNDRED + HardwareSettings.load().default_markup) / HUNDRED)

    def price_incl_vat(self, vat_rate=None):
        price = self.price
        if price is None:
            return None
        rate = HardwareSettings.load().vat_rate if vat_rate is None else vat_rate
        return money(price * (HUNDRED + rate) / HUNDRED)

    @property
    def warranty(self):
        return self.warranty_months if self.warranty_months is not None else HardwareSettings.load().default_warranty_months


def photo_path(instance, filename):
    return f"hardware/{instance.device_id}/{filename}"


class DevicePhoto(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(_("photo"), upload_to=photo_path)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("photo")
        verbose_name_plural = _("photos")
        ordering = ["position", "pk"]

    def __str__(self):
        return self.image.name.rsplit("/", 1)[-1]
