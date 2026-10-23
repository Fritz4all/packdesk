import random
import string
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext


def add_years(day, years):
    """Same day `years` later; 29 February becomes 28 February in a non-leap year."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


# --- Catalogue -------------------------------------------------------------------


class Category(models.Model):
    """Kind of service pack, e.g. Server Servicepack, Laserprinter Servicepack."""

    class EndDateFrom(models.TextChoices):
        PURCHASE = "purchase", _("Purchase date of the device")
        REGISTRATION = "registration", _("Registration date")

    name = models.CharField(_("name"), max_length=100)
    explanation = models.TextField(_("explanation"), blank=True)
    end_date_from = models.CharField(
        _("cover counts from"), max_length=12, choices=EndDateFrom.choices, default=EndDateFrom.PURCHASE,
        help_text=_("For packs bought with a new device (not post-warranty)."),
    )
    contact_to_register = models.BooleanField(
        _("register by contacting us"), default=False,
        help_text=_("Licences of this category cannot be registered online; the customer is asked to contact you."),
    )
    option_types = models.ManyToManyField("OptionType", blank=True, verbose_name=_("option types"))
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("pack category")
        verbose_name_plural = _("pack categories")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class HardwareClass(models.Model):
    """Class of hardware a pack covers, e.g. server class A, A4 colour printers."""

    name = models.CharField(_("name"), max_length=120)
    explanation = models.TextField(_("explanation"), blank=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("hardware class")
        verbose_name_plural = _("hardware classes")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Vendor(models.Model):
    name = models.CharField(_("name"), max_length=120)
    product_nr_regex = models.CharField(
        _("check of article number"), max_length=128, blank=True,
        help_text=_("Optional regular expression the article number must match."),
    )
    product_nr_help = models.CharField(_("explanation of article number"), max_length=256, blank=True)
    is_real_vendor = models.BooleanField(_("hardware brand"), default=True)
    at_top = models.BooleanField(_("show at top of lists"), default=False)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ["-at_top", "name"]

    def __str__(self):
        return self.name


class HardwareSystem(models.Model):
    """A device type of a brand within a hardware class, e.g. HP ProLiant DL380."""

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="systems", verbose_name=_("brand"))
    hardware_class = models.ForeignKey(HardwareClass, on_delete=models.CASCADE, related_name="systems", verbose_name=_("hardware class"))
    name = models.CharField(_("type"), max_length=120)
    warranty_years = models.PositiveSmallIntegerField(_("factory warranty (years)"), default=0)
    visible = models.BooleanField(_("selectable"), default=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("device type")
        verbose_name_plural = _("device types")
        ordering = ["vendor__name", "name"]

    def __str__(self):
        return f"{self.vendor} {self.name}"


class OptionType(models.Model):
    """Kind of extra component that can be covered, e.g. hard disk (internal) or tape drive (external)."""

    name = models.CharField(_("name"), max_length=80)
    internal = models.BooleanField(_("internal"), default=True)
    is_monitor = models.BooleanField(_("is monitor"), default=False)

    class Meta:
        verbose_name = _("option type")
        verbose_name_plural = _("option types")
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupportPeriod(models.Model):
    years = models.PositiveSmallIntegerField(_("duration (years)"))
    post_warranty = models.BooleanField(
        _("after factory warranty"), default=False,
        help_text=_("The customer chooses the start date; otherwise cover follows the purchase date."),
    )

    class Meta:
        verbose_name = _("support period")
        verbose_name_plural = _("support periods")
        ordering = ["years", "post_warranty"]

    def __str__(self):
        text = ngettext("%(n)s year", "%(n)s years", self.years) % {"n": self.years}
        return f"{text} ({_('post-warranty')})" if self.post_warranty else text


class SupportService(models.Model):
    abbreviation = models.CharField(_("abbreviation"), max_length=10)
    name = models.CharField(_("service"), max_length=60)
    response = models.CharField(_("response time"), max_length=40, blank=True)
    office_hours = models.BooleanField(_("office hours only"), default=True)

    class Meta:
        verbose_name = _("service level")
        verbose_name_plural = _("service levels")
        ordering = ["abbreviation"]

    def __str__(self):
        return f"{self.name} {self.response}".strip()


class SupportPack(models.Model):
    code = models.CharField(_("code"), max_length=16, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="packs", verbose_name=_("category"))
    hardware_class = models.ForeignKey(HardwareClass, on_delete=models.PROTECT, related_name="packs", verbose_name=_("hardware class"))
    service = models.ForeignKey(SupportService, on_delete=models.PROTECT, verbose_name=_("service level"))
    period = models.ForeignKey(SupportPeriod, on_delete=models.PROTECT, verbose_name=_("period"))
    description = models.CharField(_("description"), max_length=200, blank=True, help_text=_("Shown to customers and in emails."))
    price = models.DecimalField(_("price"), max_digits=10, decimal_places=2, default=Decimal("0"))
    cost_price = models.DecimalField(
        _("cost price"), max_digits=10, decimal_places=2, default=Decimal("0"),
        help_text=_("What the pack costs you; used for margin reports."),
    )
    enabled = models.BooleanField(_("for sale"), default=True)
    registration_required = models.BooleanField(_("registration required"), default=True)
    requires_monitor = models.BooleanField(_("includes monitor"), default=False)
    max_internal_options = models.PositiveSmallIntegerField(_("max. internal options"), default=0)
    max_external_options = models.PositiveSmallIntegerField(_("max. external options"), default=0)
    remark = models.CharField(_("remark"), max_length=100, blank=True)
    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("service pack")
        verbose_name_plural = _("service packs")
        ordering = ["category__position", "hardware_class__position", "period__years"]

    def __str__(self):
        return self.description or f"{self.category} – {self.hardware_class} – {self.service} – {self.period}"


# --- Licences ---------------------------------------------------------------------


class LicenceSettings(models.Model):
    """Rules and texts for licences and the registration wizard (one row)."""

    register_after_days = models.PositiveIntegerField(
        _("register up to (days after purchase)"), default=1920,
        help_text=_("Packs bought with a new device can be registered up to this many days after purchase."),
    )
    register_ahead_days = models.PositiveIntegerField(_("purchase date at most (days ahead)"), default=40)
    register_ahead_days_post_warranty = models.PositiveIntegerField(_("start date post-warranty at most (days ahead)"), default=95)
    suffix_length = models.PositiveSmallIntegerField(
        _("letters after licence number"), default=3, help_text=_("Random letters that make numbers hard to guess; 0 = none."),
    )
    forbidden_suffixes = models.TextField(
        _("forbidden letter combinations"), blank=True, default="lul kut god del fuk fok pik bef bil",
        help_text=_("Separated by spaces."),
    )
    notify_emails = models.CharField(
        _("internal recipients of registrations"), max_length=300, blank=True, help_text=_("Email addresses separated by commas."),
    )
    wizard_intro = models.TextField(_("introduction of registration"), blank=True)
    wizard_done = models.TextField(_("text after registration"), blank=True)
    contact_text = models.TextField(_("text for 'register by contacting us'"), blank=True)

    class Meta:
        verbose_name = _("licence settings")
        verbose_name_plural = _("licence settings")

    def __str__(self):
        return str(_("Licence settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def new_suffix(self, rng=random):
        forbidden = {w.strip().upper() for w in self.forbidden_suffixes.split()}
        while True:
            # No letter O: it is easily confused with a zero.
            suffix = "".join(rng.choice(string.ascii_uppercase.replace("O", "")) for _ in range(self.suffix_length))
            if suffix not in forbidden:
                return suffix


class Licence(models.Model):
    class Status(models.TextChoices):
        UNREGISTERED = "unregistered", _("Not registered")
        REGISTERED = "registered", _("Registered")
        ENDED = "ended", _("Ended")

    number = models.CharField(_("licence number"), max_length=20, db_index=True)
    suffix = models.CharField(_("letters"), max_length=8, blank=True)
    sequence = models.PositiveSmallIntegerField(_("sequence number"), default=1)
    full_number = models.CharField(_("full licence number"), max_length=40, unique=True, editable=False)

    pack = models.ForeignKey(SupportPack, on_delete=models.PROTECT, related_name="licences", verbose_name=_("service pack"))
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="licences", verbose_name=_("customer"))
    order_reference = models.CharField(_("order reference"), max_length=128, blank=True)
    prolongation_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="prolonged_by", verbose_name=_("extension of"),
    )

    # Filled in on registration
    registered_on = models.DateTimeField(_("registered on"), null=True, blank=True)
    start_date = models.DateField(_("start date"), null=True, blank=True)
    end_date = models.DateField(_("end date"), null=True, blank=True)
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("brand"))
    system = models.ForeignKey(HardwareSystem, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("device type"))
    description = models.CharField(_("description"), max_length=128, blank=True)
    product_nr = models.CharField(_("article number"), max_length=64, blank=True)
    serial_nr = models.CharField(_("serial number"), max_length=64, blank=True, db_index=True)
    purchase_date = models.DateField(_("purchase date"), null=True, blank=True)
    end_customer_email = models.EmailField(_("email end customer"), blank=True)
    end_customer_reference = models.CharField(_("reference end customer"), max_length=128, blank=True)
    memo = models.TextField(_("memo"), blank=True)
    reseller_name = models.CharField(_("reseller"), max_length=128, blank=True)
    reseller_address = models.CharField(_("reseller address"), max_length=200, blank=True)
    reseller_postal_code = models.CharField(_("reseller postal code"), max_length=20, blank=True)
    reseller_city = models.CharField(_("reseller city"), max_length=100, blank=True)
    reseller_phone = models.CharField(_("reseller phone"), max_length=40, blank=True)

    legacy_id = models.CharField(max_length=36, blank=True, db_index=True, editable=False)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    class Meta:
        verbose_name = _("licence")
        verbose_name_plural = _("licences")
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_number

    def save(self, *args, **kwargs):
        self.full_number = self.compose_full_number()
        super().save(*args, **kwargs)

    def compose_full_number(self):
        return f"{self.number}{self.suffix}-{self.sequence}"

    @property
    def status(self):
        if not self.registered_on:
            return self.Status.UNREGISTERED
        if self.end_date and self.end_date < timezone.localdate():
            return self.Status.ENDED
        return self.Status.REGISTERED

    def get_status_display(self):
        return self.Status(self.status).label

    @classmethod
    def find(cls, value):
        """Look up by full licence number; '-1' is assumed when the sequence is left out."""
        value = (value or "").strip().upper().replace(" ", "")
        if value and "-" not in value:
            value += "-1"
        return cls.objects.filter(full_number__iexact=value).select_related("pack__category", "pack__period", "customer").first()

    @classmethod
    def create_for(cls, pack, customer, quantity=1, order_reference=""):
        """Create licences with new numbers (one per pack)."""
        from apps.numbering.models import NumberSequence

        settings_ = LicenceSettings.load()
        created = []
        with transaction.atomic():
            for _i in range(quantity):
                _n, number = NumberSequence.issue("licence")
                created.append(cls.objects.create(
                    number=number, suffix=settings_.new_suffix(), pack=pack, customer=customer,
                    order_reference=order_reference,
                ))
        return created

    def cover_dates(self, purchase_date, start_date, today=None):
        """Start and end date of cover, or ValidationError, following the previous webshop's rules."""
        today = today or timezone.localdate()
        rules = LicenceSettings.load()
        period = self.pack.period
        if period.post_warranty:
            if not start_date:
                raise ValidationError({"start_date": _("Enter the start date.")})
            if start_date > today + timedelta(days=rules.register_ahead_days_post_warranty):
                raise ValidationError({"start_date": _("The start date is too far in the future.")})
            return start_date, add_years(start_date, period.years) - timedelta(days=1)
        if not purchase_date:
            raise ValidationError({"purchase_date": _("Enter the purchase date.")})
        if purchase_date < today:
            if (today - purchase_date).days > rules.register_after_days:
                raise ValidationError({"purchase_date": _("The purchase date is too long ago; this device can no longer be registered.")})
            base = today if self.pack.category.end_date_from == Category.EndDateFrom.REGISTRATION else purchase_date
            return today, add_years(base, period.years)
        if (purchase_date - today).days > rules.register_ahead_days:
            raise ValidationError({"purchase_date": _("The purchase date is too far in the future; this device cannot be registered yet.")})
        return purchase_date, add_years(purchase_date, period.years)


class LicenceOption(models.Model):
    """An extra component covered by a licence (internal, external or monitor)."""

    licence = models.ForeignKey(Licence, on_delete=models.CASCADE, related_name="options")
    option_type = models.ForeignKey(OptionType, on_delete=models.PROTECT, verbose_name=_("type"))
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("brand"))
    description = models.CharField(_("description"), max_length=128, blank=True)
    product_nr = models.CharField(_("article number"), max_length=64, blank=True)
    serial_nr = models.CharField(_("serial number"), max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("licence option")
        verbose_name_plural = _("licence options")
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.option_type}: {self.description}"
