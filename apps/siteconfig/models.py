from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.utils.html import format_html
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
    setup_completed = models.BooleanField(
        _("installation finished"), default=False, editable=False,
        help_text=_("Set by the installation wizard."),
    )
    admin_language = models.CharField(
        _("admin language"),
        max_length=8,
        choices=settings.LANGUAGES,
        default="nl",
        help_text=_("Language of the admin. Each staff user can choose another one under the account menu."),
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

    meta_description = models.CharField(
        _("description for search engines"), max_length=300, blank=True,
        help_text=_("Shown by Google and others under the page title."),
    )
    hero_button_text = models.CharField(
        _("button text on home page"), max_length=60, blank=True,
        help_text=_("Leave empty for the standard text (Log in / Go to my account)."),
    )

    # Footer
    footer_text = models.TextField(_("footer text"), blank=True, help_text=_("Extra text at the bottom of every page."))
    footer_show_address = models.BooleanField(_("show address"), default=True)
    footer_show_phone = models.BooleanField(_("show phone"), default=True)
    footer_show_email = models.BooleanField(_("show email"), default=True)
    footer_show_coc = models.BooleanField(_("show Chamber of Commerce number"), default=True)
    footer_show_vat = models.BooleanField(_("show VAT number"), default=False)

    # Maintenance and announcements
    maintenance_mode = models.BooleanField(
        _("maintenance mode"), default=False,
        help_text=_("Visitors see the maintenance message and cannot log in. Staff can still use the admin."),
    )
    maintenance_message = models.TextField(_("maintenance message"), blank=True)
    maintenance_until = models.DateTimeField(
        _("expected back"), null=True, blank=True, help_text=_("Optional; shown in the maintenance message."),
    )
    announcement_enabled = models.BooleanField(_("show announcement"), default=False)
    announcement_text = models.CharField(
        _("announcement"), max_length=300, blank=True,
        help_text=_("Bar at the top of every page, e.g. to announce maintenance."),
    )
    announcement_level = models.CharField(
        _("announcement colour"), max_length=8, default="info",
        choices=[("info", _("Information")), ("warning", _("Warning")), ("success", _("Positive"))],
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

    def usage_labels(self):
        return [str(self._meta.get_field(f).verbose_name) for f in self.USAGES.values() if getattr(self, f)]

    def get_inline_title(self):
        """Title of the collapsed row in the admin: name and address, then (smaller) where it is used."""
        usages = ", ".join(self.usage_labels()) or str(_("not used yet"))
        return format_html('{} · {} <span class="pd-dim">— {}</span>', self.label, self.one_line, usages)

    def contact_phone(self):
        return self.phone or self.settings.phone

    def contact_email(self):
        return self.email or self.settings.email


class Visibility(models.TextChoices):
    ALL = "all", _("Everyone")
    ANONYMOUS = "anonymous", _("Only when not logged in")
    LOGGED_IN = "logged_in", _("Only when logged in")


def _row_state(item):
    if not item.is_active:
        return _("not active")
    return item.get_visibility_display()


class HomeBlock(models.Model):
    """A card on the home page."""

    settings = models.ForeignKey(SiteSettings, on_delete=models.CASCADE, related_name="home_blocks")
    icon = models.CharField(_("icon"), max_length=8, blank=True, help_text=_("A symbol or emoji, e.g. ✓ or 🛠"))
    title = models.CharField(_("title"), max_length=100)
    text = models.TextField(_("text"), blank=True)
    link_url = models.CharField(_("link"), max_length=300, blank=True, help_text=_("Page address, e.g. /mijn/ or https://…"))
    link_text = models.CharField(_("link text"), max_length=60, blank=True)
    visibility = models.CharField(_("visible for"), max_length=12, choices=Visibility.choices, default=Visibility.ALL)
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("home page block")
        verbose_name_plural = _("home page blocks")
        ordering = ["position", "id"]

    def __str__(self):
        return self.title

    def get_inline_title(self):
        """Collapsed row in the admin: icon and title, then (smaller) who sees it."""
        return format_html('{} {} <span class="pd-dim">— {}</span>', self.icon, self.title, _row_state(self))


class MenuItem(models.Model):
    """A link in the header menu."""

    settings = models.ForeignKey(SiteSettings, on_delete=models.CASCADE, related_name="menu_items")
    label = models.CharField(_("text"), max_length=60)
    url = models.CharField(_("link"), max_length=300, help_text=_("Page address, e.g. /mijn/ or https://…"))
    new_tab = models.BooleanField(_("open in new tab"), default=False)
    visibility = models.CharField(_("visible for"), max_length=12, choices=Visibility.choices, default=Visibility.ALL)
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("menu item")
        verbose_name_plural = _("menu items")
        ordering = ["position", "id"]

    def __str__(self):
        return self.label

    def get_inline_title(self):
        """Collapsed row in the admin: text and link, then (smaller) who sees it."""
        return format_html('{} · {} <span class="pd-dim">— {}</span>', self.label, self.url, _row_state(self))


def visible_for(items, user):
    """Active items the current visitor may see."""
    logged_in = user.is_authenticated
    return [
        item for item in items
        if item.is_active
        and (item.visibility == Visibility.ALL or (item.visibility == Visibility.LOGGED_IN) == logged_in)
    ]
