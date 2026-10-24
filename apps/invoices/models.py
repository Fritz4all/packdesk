import os
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.storage import data_storage


class InvoiceSettings(models.Model):
    """Texts and rules for invoices (one row). The layout itself is an HTML template."""

    auto_on_order = models.BooleanField(
        _("make invoice when an order is placed"), default=True,
        help_text=_("Customers with 'no invoice for service packs' never get one."),
    )
    send_on_create = models.BooleanField(_("email invoice when it is made"), default=True)
    payment_term_days = models.PositiveSmallIntegerField(_("payment term (days)"), default=14)
    payment_text = models.TextField(
        _("payment text"), blank=True, help_text=_("Placeholders: {days}, {number}, {iban}, {due_date}."),
    )
    notice_text = models.TextField(
        _("notice on invoice"), blank=True, help_text=_("Highlighted text, e.g. a changed bank account."),
    )
    footer_text = models.TextField(_("footer text"), blank=True)
    email_subject = models.CharField(_("email subject"), max_length=200, blank=True,
                                     help_text=_("Placeholders: {number}, {company}."))
    email_body = models.TextField(_("email text"), blank=True, help_text=_("Placeholders: {number}, {company}, {name}, {total}."))
    custom_template = models.TextField(
        _("own invoice layout (HTML)"), blank=True,
        help_text=_("Advanced: a Django template that replaces the standard layout. Leave empty for the standard one."),
    )

    class Meta:
        verbose_name = _("invoice settings")
        verbose_name_plural = _("invoice settings")

    def __str__(self):
        return str(_("Invoice settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def pdf_path(instance, filename):
    return f"invoices/{instance.issued_on:%Y}/{filename}"


class Invoice(models.Model):
    number = models.CharField(_("invoice number"), max_length=32, unique=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="invoices", verbose_name=_("customer"))
    order = models.OneToOneField("orders.Order", on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="invoice", verbose_name=_("order"))
    issued_on = models.DateField(_("invoice date"), default=timezone.localdate)
    due_on = models.DateField(_("due date"), null=True, blank=True)
    reference = models.CharField(_("your reference"), max_length=128, blank=True)

    # Customer details at the time of invoicing
    customer_name = models.CharField(_("customer name"), max_length=200, blank=True)
    customer_number = models.CharField(_("customer number"), max_length=32, blank=True, db_index=True)
    customer_vat = models.CharField(_("customer VAT number"), max_length=32, blank=True)
    address_attention = models.CharField(_("attention of"), max_length=120, blank=True)
    address_line1 = models.CharField(_("address"), max_length=200, blank=True)
    address_line2 = models.CharField(_("address line 2"), max_length=200, blank=True)
    address_postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    address_city = models.CharField(_("city"), max_length=100, blank=True)
    address_country = models.CharField(_("country"), max_length=60, blank=True)
    email = models.EmailField(_("invoice email"), blank=True)

    gross = models.DecimalField(_("subtotal"), max_digits=12, decimal_places=2, default=Decimal("0"))
    discount_pct = models.DecimalField(_("discount (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(_("discount"), max_digits=12, decimal_places=2, default=Decimal("0"))
    net = models.DecimalField(_("total excl. VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))
    vat_rate = models.DecimalField(_("VAT rate (%)"), max_digits=5, decimal_places=2, default=Decimal("0"))
    vat = models.DecimalField(_("VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(_("total incl. VAT"), max_digits=12, decimal_places=2, default=Decimal("0"))

    pdf = models.FileField(_("PDF"), upload_to=pdf_path, storage=data_storage, blank=True)
    is_archive = models.BooleanField(_("from old archive"), default=False, db_index=True)
    archive_file = models.CharField(_("file in archive"), max_length=200, blank=True)
    paid_on = models.DateField(_("paid on"), null=True, blank=True)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    class Meta:
        verbose_name = _("invoice")
        verbose_name_plural = _("invoices")
        ordering = ["-issued_on", "-number"]

    def __str__(self):
        return f"{self.number} · {self.customer_name}"

    def pdf_bytes(self):
        """The invoice as PDF: the original file for archived invoices, otherwise the stored PDF.

        An archived invoice brought in by a customer import may carry its own copy instead."""
        if self.is_archive and self._archive_path():
            with open(self._archive_path(), "rb") as f:
                return f.read()
        with self.pdf.open("rb") as f:
            return f.read()

    def _archive_path(self):
        if not (self.archive_file and settings.DOCUMENT_ARCHIVE_DIR):
            return ""
        root = os.path.realpath(settings.DOCUMENT_ARCHIVE_DIR)
        path = os.path.realpath(os.path.join(root, self.archive_file))
        # Only files inside the archive folder (archive_file can come from an imported file).
        return path if path.startswith(root + os.sep) and os.path.isfile(path) else ""

    def has_pdf(self):
        return bool(self.is_archive and self._archive_path()) or bool(self.pdf)

    @property
    def filename(self):
        return f"invoice-{self.number}.pdf"


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    code = models.CharField(_("code"), max_length=32, blank=True)
    description = models.CharField(_("description"), max_length=300)
    quantity = models.DecimalField(_("quantity"), max_digits=10, decimal_places=2, default=Decimal("1"))
    unit_price = models.DecimalField(_("price each"), max_digits=12, decimal_places=2)
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("invoice line")
        verbose_name_plural = _("invoice lines")
        ordering = ["id"]

    def __str__(self):
        return self.description


class InvoicePayment(models.Model):
    """A (part) payment received for an invoice."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(_("amount"), max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(_("paid at"))
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", verbose_name=_("recorded by"))

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["paid_at"]

    def __str__(self):
        return f"€ {self.amount} ({self.paid_at:%d-%m-%Y})"


class InvoiceEmail(models.Model):
    """Every time an invoice was emailed."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="emails")
    sent_at = models.DateTimeField(_("sent at"), auto_now_add=True)
    sent_to = models.CharField(_("sent to"), max_length=300)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name=_("sent by"))

    class Meta:
        verbose_name = _("sent invoice email")
        verbose_name_plural = _("sent invoice emails")
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.sent_to} ({self.sent_at:%d-%m-%Y %H:%M})"
