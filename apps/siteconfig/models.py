from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

hex_color = RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a colour like #1f6feb."))


class SiteSettings(models.Model):
    """Everything that differs per customer installation.

    One row per installation, edited in the admin. Name, logo, colours and
    company details are shown on pages, mails and invoices, so nothing is
    hard-coded per customer.
    """

    name = models.CharField(_("name"), max_length=120, default="PackDesk")
    language = models.CharField(_("language"), max_length=8, choices=settings.LANGUAGES, default="nl")

    # Branding
    logo = models.ImageField(_("logo"), upload_to="branding/", blank=True)
    favicon = models.ImageField(_("favicon"), upload_to="branding/", blank=True)
    primary_color = models.CharField(_("primary colour"), max_length=7, default="#1f6feb", validators=[hex_color])
    accent_color = models.CharField(_("accent colour"), max_length=7, default="#0ea5e9", validators=[hex_color])
    tagline = models.CharField(_("tagline"), max_length=200, blank=True)
    intro_text = models.TextField(
        _("introduction"),
        blank=True,
        help_text=_("Short text on the home page under the tagline."),
    )

    # Company details
    legal_name = models.CharField(_("legal name"), max_length=200, blank=True)
    address_line = models.CharField(_("address"), max_length=200, blank=True)
    postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    city = models.CharField(_("city"), max_length=100, blank=True)
    country = models.CharField(_("country"), max_length=2, default="NL")
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
    def display_name(self):
        return self.legal_name or self.name
