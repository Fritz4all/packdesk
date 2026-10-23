from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

hex_color = RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a colour like #1f6feb."))


class Theme(models.TextChoices):
    AUTO = "auto", _("Auto (follow device)")
    LIGHT = "light", _("Light")
    DARK = "dark", _("Dark")


class SiteSettings(models.Model):
    """Everything that differs per customer installation.

    One row per installation, edited in the admin. Name, logo, colours and
    company details are shown on pages, mails and invoices, so nothing is
    hard-coded per customer.
    """

    name = models.CharField(_("name"), max_length=120, default="PackDesk")
    language = models.CharField(
        _("default language"),
        max_length=8,
        choices=settings.LANGUAGES,
        default="nl",
        help_text=_("Language for visitors who have not chosen one."),
    )
    languages = models.CharField(
        _("available languages"),
        max_length=64,
        default=",".join(code for code, _name in settings.LANGUAGES),
        help_text=_("Languages visitors can choose from."),
    )

    # Branding
    logo = models.ImageField(_("logo"), upload_to="branding/", blank=True)
    favicon = models.ImageField(_("favicon"), upload_to="branding/", blank=True)
    primary_color = models.CharField(_("primary colour"), max_length=7, default="#1f6feb", validators=[hex_color])
    accent_color = models.CharField(_("accent colour"), max_length=7, default="#0ea5e9", validators=[hex_color])
    theme = models.CharField(
        _("default appearance"),
        max_length=8,
        choices=Theme.choices,
        default=Theme.AUTO,
        help_text=_("Light or dark appearance for visitors who have not chosen one."),
    )
    theme_switch = models.BooleanField(
        _("visitors can choose appearance"),
        default=True,
        help_text=_("Shows a light/dark switch in the header."),
    )
    tagline = models.CharField(_("tagline"), max_length=200, blank=True)
    intro_text = models.TextField(
        _("introduction"),
        blank=True,
        help_text=_("Short text on the home page under the tagline."),
    )

    # Company details
    legal_name = models.CharField(_("legal name"), max_length=200, blank=True)
    phone = models.CharField(_("phone"), max_length=40, blank=True)
    email = models.EmailField(_("email"), blank=True)
    website = models.URLField(_("website"), blank=True)
    coc_number = models.CharField(_("Chamber of Commerce number"), max_length=20, blank=True)
    vat_number = models.CharField(_("VAT number"), max_length=20, blank=True)
    iban = models.CharField(_("IBAN"), max_length=34, blank=True)

    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("settings")
        verbose_name_plural = _("settings")

    def __str__(self):
        return str(_("Settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Site settings cannot be deleted.")

    @classmethod
    def load(cls):
        # One small query per request; no cache, so every worker sees changes at once.
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def language_codes(self):
        """Available language codes, always including the default language."""
        known = {code for code, _name in settings.LANGUAGES}
        codes = [c for c in self.languages.split(",") if c in known]
        if self.language not in codes:
            codes.insert(0, self.language)
        return codes

    @property
    def language_choices(self):
        names = dict(settings.LANGUAGES)
        return [(code, names[code]) for code in self.language_codes]

    @property
    def display_name(self):
        return self.legal_name or self.name

    def address_for(self, usage):
        """The address to show for a usage: website, invoice, quote, order, mail or label."""
        field = Address.USAGES[usage]
        addresses = list(self.addresses.all())
        for address in addresses:
            if getattr(address, field):
                return address
        return addresses[0] if addresses else None

    @property
    def website_address(self):
        return self.address_for("website")


class Address(models.Model):
    """A company address, e.g. visiting address, postal address or billing address.

    Each usage (website, invoices, quotes, ...) is ticked on at most one address.
    A usage nobody ticked falls back to the first address, so documents always
    have an address.
    """

    USAGES = {
        "website": "on_website",
        "invoice": "on_invoices",
        "quote": "on_quotes",
        "order": "on_orders",
        "mail": "on_mails",
        "label": "on_labels",
    }

    settings = models.ForeignKey(SiteSettings, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(_("name"), max_length=60, help_text=_("For yourself, e.g. visiting address or postal address."))
    line1 = models.CharField(_("address"), max_length=200)
    line2 = models.CharField(_("address line 2"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20)
    city = models.CharField(_("city"), max_length=100)
    country = models.CharField(_("country"), max_length=60, blank=True, default="Nederland")
    phone = models.CharField(_("phone"), max_length=40, blank=True, help_text=_("Leave empty to use the general phone number."))
    email = models.EmailField(_("email"), blank=True, help_text=_("Leave empty to use the general email address."))

    on_website = models.BooleanField(_("website"), default=False)
    on_invoices = models.BooleanField(_("invoices"), default=False)
    on_quotes = models.BooleanField(_("quotes"), default=False)
    on_orders = models.BooleanField(_("order confirmations"), default=False)
    on_mails = models.BooleanField(_("emails"), default=False)
    on_labels = models.BooleanField(_("sender on labels"), default=False)

    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.label}: {self.one_line}"

    @property
    def one_line(self):
        parts = [self.line1, self.line2, f"{self.postal_code} {self.city}".strip(), self.country]
        return ", ".join(p for p in parts if p)

    def contact_phone(self):
        return self.phone or self.settings.phone

    def contact_email(self):
        return self.email or self.settings.email
