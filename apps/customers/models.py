from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _


class CustomerType(models.Model):
    """Kind of customer, e.g. reseller, distributor, vendor (configurable)."""

    name = models.CharField(_("name"), max_length=60)
    is_reseller = models.BooleanField(_("is reseller"), default=False)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("customer type")
        verbose_name_plural = _("customer types")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Country(models.Model):
    """Countries customers can be in, with country-specific rules."""

    code = models.CharField(_("code"), max_length=2, unique=True, help_text=_("Two letters, e.g. NL."))
    name = models.CharField(_("name"), max_length=60)
    vat_number_required = models.BooleanField(
        _("VAT number required"), default=True, help_text=_("E.g. for customers outside your own country."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("country")
        verbose_name_plural = _("countries")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class Customer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", _("Waiting for approval")
        ACTIVE = "active", _("Active")
        BLOCKED = "blocked", _("Blocked")

    number = models.CharField(
        _("customer number"), max_length=32, blank=True, null=True, unique=True,
        # Empty is stored as NULL, so several customers can be without a number while numbers stay
        # unique. (A conditional unique constraint would do this too, but MariaDB/MySQL lack those.)
        help_text=_("Account number (debtor number). Filled in automatically on approval if left empty."),
    )
    name = models.CharField(_("company name"), max_length=120)
    customer_type = models.ForeignKey(
        CustomerType, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("customer type"),
    )
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.ACTIVE)

    vat_number = models.CharField(_("VAT number"), max_length=32, blank=True)
    coc_number = models.CharField(_("Chamber of Commerce number"), max_length=32, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("general email"), blank=True)
    website = models.URLField(_("website"), blank=True)

    email_orders = models.EmailField(_("email for orders"), blank=True, help_text=_("Order confirmations; empty = general email."))
    email_parts = models.EmailField(_("email for spare parts"), blank=True, help_text=_("Empty = general email."))
    email_invoices = models.EmailField(_("email for invoices"), blank=True, help_text=_("Empty = general email."))

    margin_packs = models.DecimalField(_("margin service packs (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    margin_parts = models.DecimalField(_("margin spare parts (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    no_pack_invoice = models.BooleanField(
        _("no invoice for service packs"), default=False, help_text=_("Service pack orders of this customer are not invoiced."),
    )
    logo = models.ImageField(_("logo"), upload_to="customers/logos/", blank=True)
    remark = models.TextField(_("internal remark"), blank=True)

    signup_message = models.TextField(
        _("message from sign-up form"), blank=True,
        help_text=_("What the customer typed in the 'Message' field of the sign-up form."),
    )
    approved_at = models.DateTimeField(_("approved at"), null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name=_("approved by"),
    )
    legacy_id = models.CharField(_("ID in old system"), max_length=36, blank=True, db_index=True, editable=False)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("customer")
        verbose_name_plural = _("customers")
        ordering = ["name"]
        permissions = [
            ("export_customer", _("Can export customers")),
            ("import_customer", _("Can import customers")),
        ]

    def __str__(self):
        return f"{self.name} ({self.number})" if self.number else self.name

    def clean(self):
        main = self.addresses.filter(kind=CustomerAddress.Kind.MAIN).select_related("country").first() if self.pk else None
        if main and main.country and main.country.vat_number_required and not self.vat_number:
            raise ValidationError({"vat_number": _("A VAT number is required for customers in %(country)s.") % {"country": main.country}})

    def address(self, kind):
        """Address of a kind (main, invoice, delivery); invoice and delivery fall back to the main address."""
        addresses = {a.kind: a for a in self.addresses.all()}
        return addresses.get(kind) or addresses.get(CustomerAddress.Kind.MAIN)

    def email_for(self, purpose):
        return {"orders": self.email_orders, "parts": self.email_parts, "invoices": self.email_invoices}.get(purpose) or self.email

    def assign_number(self):
        if not self.number:
            from apps.numbering.models import NumberSequence

            _n, self.number = NumberSequence.issue("customer")

    def approve(self, by):
        """Activate a customer: give it a number and let its contacts log in."""
        with transaction.atomic():
            self.assign_number()
            self.status = self.Status.ACTIVE
            self.approved_at = timezone.now()
            self.approved_by = by
            self.save()
            for contact in self.contacts.select_related("user"):
                if contact.user and not contact.user.is_active:
                    contact.user.is_active = True
                    contact.user.save(update_fields=["is_active"])

    def block(self):
        with transaction.atomic():
            self.status = self.Status.BLOCKED
            self.save(update_fields=["status", "updated_at"])
            for contact in self.contacts.select_related("user"):
                if contact.user and contact.user.is_active:
                    contact.user.is_active = False
                    contact.user.save(update_fields=["is_active"])


class CustomerAddress(models.Model):
    class Kind(models.TextChoices):
        MAIN = "main", _("Main address")
        INVOICE = "invoice", _("Invoice address")
        DELIVERY = "delivery", _("Delivery address")

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.MAIN)
    attention = models.CharField(_("attention of"), max_length=120, blank=True)
    line1 = models.CharField(_("address"), max_length=200)
    line2 = models.CharField(_("address line 2"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20)
    city = models.CharField(_("city"), max_length=100)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("country"))

    class Meta:
        verbose_name = _("customer address")
        verbose_name_plural = _("customer addresses")
        constraints = [models.UniqueConstraint(fields=["customer", "kind"], name="one_address_per_kind")]

    def __str__(self):
        return self.one_line

    @property
    def one_line(self):
        parts = [self.line1, self.line2, f"{self.postal_code} {self.city}".strip(), str(self.country or "")]
        return ", ".join(p for p in parts if p)

    def get_inline_title(self):
        return f"{self.get_kind_display()}: {self.one_line}"


class Contact(models.Model):
    """A person at a customer, optionally with a login for the customer portal."""

    class Salutation(models.TextChoices):
        NONE = "", "—"
        MR = "mr", _("Mr")
        MRS = "mrs", _("Mrs")

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="contacts")
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="contact",
        verbose_name=_("login"),
    )
    salutation = models.CharField(_("salutation"), max_length=4, choices=Salutation.choices, blank=True)
    initials = models.CharField(_("initials"), max_length=16, blank=True)
    first_name = models.CharField(_("first name"), max_length=60, blank=True)
    last_name = models.CharField(_("last name"), max_length=80)
    function = models.CharField(_("job title"), max_length=100, blank=True)
    department = models.CharField(_("department"), max_length=100, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"))
    is_primary = models.BooleanField(_("primary contact"), default=False)
    remark = models.TextField(_("remark"), blank=True)
    legacy_id = models.CharField(_("ID in old system"), max_length=36, blank=True, db_index=True, editable=False)

    class Meta:
        verbose_name = _("contact")
        verbose_name_plural = _("contacts")
        ordering = ["-is_primary", "last_name"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        given = self.first_name or self.initials
        return f"{given} {self.last_name}".strip()

    def get_inline_title(self):
        """Title of the collapsed row in the admin: name, then (smaller) job title and email."""
        details = " · ".join(p for p in [self.function, self.email] if p)
        star = f"★ {_('primary contact')} · " if self.is_primary else ""
        return format_html('{} <span class="pd-dim">— {}{}</span>', self.full_name, star, details)


def customer_of(user):
    """The customer a portal user belongs to, or None."""
    contact = getattr(user, "contact", None) if user.is_authenticated else None
    return contact.customer if contact else None


class FieldMode(models.TextChoices):
    HIDDEN = "hidden", _("Hidden")
    OPTIONAL = "optional", _("Optional")
    REQUIRED = "required", _("Required")


class SignupSettings(models.Model):
    """Settings for customers and the public sign-up form (one row)."""

    # Defaults for new customers
    default_margin_packs = models.DecimalField(_("default margin service packs (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    default_margin_parts = models.DecimalField(_("default margin spare parts (%)"), max_digits=5, decimal_places=2, default=Decimal("15"))

    # Sign-up form
    enabled = models.BooleanField(_("sign-up form active"), default=True)
    # No defaults on translated fields: django-modeltranslation treats a value equal to the
    # default as "not filled in" and would show another language. Texts are set by a migration.
    menu_label = models.CharField(_("link text"), max_length=60, blank=True,
                                  help_text=_("Text of the link to the form on the login page."))
    title = models.CharField(_("title"), max_length=120, blank=True)
    intro = models.TextField(_("introduction"), blank=True)
    thanks = models.TextField(_("text after sending"), blank=True)
    customer_type = models.ForeignKey(
        CustomerType, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("customer type for sign-ups"),
    )
    require_approval = models.BooleanField(
        _("approval required"), default=True,
        help_text=_("New customers can only log in after a staff member approves them."),
    )
    notify_email = models.EmailField(_("notify about new sign-ups"), blank=True,
                                     help_text=_("Empty = the general email address from the settings."))
    activation_subject = models.CharField(_("subject of activation email"), max_length=200, blank=True)
    activation_body = models.TextField(
        _("text of activation email"), blank=True,
        help_text=_("Placeholders: {name}, {company}, {number}, {login_url}."),
    )

    field_phone = models.CharField(_("phone"), max_length=8, choices=FieldMode.choices, default=FieldMode.REQUIRED)
    field_vat_number = models.CharField(_("VAT number"), max_length=8, choices=FieldMode.choices, default=FieldMode.OPTIONAL,
                                        help_text=_("Always required for countries that need a VAT number."))
    field_coc_number = models.CharField(_("Chamber of Commerce number"), max_length=8, choices=FieldMode.choices, default=FieldMode.OPTIONAL)
    field_website = models.CharField(_("website"), max_length=8, choices=FieldMode.choices, default=FieldMode.HIDDEN)
    field_salutation = models.CharField(_("salutation"), max_length=8, choices=FieldMode.choices, default=FieldMode.OPTIONAL)
    field_function = models.CharField(_("job title"), max_length=8, choices=FieldMode.choices, default=FieldMode.OPTIONAL)
    field_department = models.CharField(_("department"), max_length=8, choices=FieldMode.choices, default=FieldMode.HIDDEN)
    field_contact_phone = models.CharField(_("direct phone of contact"), max_length=8, choices=FieldMode.choices, default=FieldMode.HIDDEN)
    field_address_line2 = models.CharField(_("address line 2"), max_length=8, choices=FieldMode.choices, default=FieldMode.HIDDEN)
    field_message = models.CharField(_("message"), max_length=8, choices=FieldMode.choices, default=FieldMode.OPTIONAL)

    class Meta:
        verbose_name = _("customer settings")
        verbose_name_plural = _("customer settings")

    def __str__(self):
        return str(_("Customer settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def mode(self, name):
        return getattr(self, f"field_{name}", FieldMode.REQUIRED)
