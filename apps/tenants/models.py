from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

hex_color = RegexValidator(r"^#[0-9a-fA-F]{6}$", _("Use a colour like #1f6feb."))


def logo_upload_path(instance, filename):
    return f"tenants/{instance.slug}/logo/{filename}"


class Tenant(models.Model):
    """A customer organisation running its own shop on PackDesk.

    Everything a tenant can change itself (branding, company details shown on
    pages, mails and invoices) lives here, so nothing is hard-coded per customer.
    """

    name = models.CharField(_("name"), max_length=120)
    slug = models.SlugField(_("code"), unique=True, help_text=_("Short internal code, e.g. previous-webshop."))
    is_active = models.BooleanField(_("active"), default=True)
    language = models.CharField(_("language"), max_length=8, choices=settings.LANGUAGES, default="nl")
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    # Branding
    logo = models.ImageField(_("logo"), upload_to=logo_upload_path, blank=True)
    primary_color = models.CharField(_("primary colour"), max_length=7, default="#1f6feb", validators=[hex_color])
    accent_color = models.CharField(_("accent colour"), max_length=7, default="#0ea5e9", validators=[hex_color])
    tagline = models.CharField(_("tagline"), max_length=200, blank=True)

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

    class Meta:
        verbose_name = _("organisation")
        verbose_name_plural = _("organisations")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def display_name(self):
        return self.legal_name or self.name


class Domain(models.Model):
    """Host name that serves a tenant's shop, e.g. shop.previous webshop.nl."""

    domain = models.CharField(_("domain"), max_length=253, unique=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="domains", verbose_name=_("organisation"))
    is_primary = models.BooleanField(_("primary"), default=False)

    class Meta:
        verbose_name = _("domain")
        verbose_name_plural = _("domains")
        ordering = ["domain"]

    def __str__(self):
        return self.domain

    def save(self, *args, **kwargs):
        self.domain = self.domain.strip().lower()
        super().save(*args, **kwargs)


class TenantScopedQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantScopedModel(models.Model):
    """Base class for all data that belongs to one tenant."""

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, verbose_name=_("organisation"))

    objects = TenantScopedQuerySet.as_manager()

    class Meta:
        abstract = True
