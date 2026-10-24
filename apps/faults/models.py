import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.storage import data_storage


class RepairOption(models.Model):
    """How the customer wants the fault handled, e.g. on site, bring it in, send a part (configurable)."""

    name = models.CharField(_("name"), max_length=150)
    position = models.PositiveSmallIntegerField(_("order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        verbose_name = _("handling option")
        verbose_name_plural = _("handling options")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class FaultSettings(models.Model):
    """Texts, recipients and rules for fault reports (one row)."""

    enabled = models.BooleanField(_("fault report form active"), default=True)
    intro = models.TextField(_("introduction"), blank=True)
    office_hours_text = models.TextField(
        _("text about reporting by phone"), blank=True, help_text=_("E.g. outside office hours call ..."),
    )
    thanks = models.TextField(_("text after sending"), blank=True)
    recipients = models.CharField(
        _("send reports to"), max_length=300, blank=True,
        help_text=_("Email addresses separated by commas. Empty = the general email address from the settings."),
    )
    cc = models.CharField(_("copy to"), max_length=300, blank=True, help_text=_("Email addresses separated by commas."))
    confirmation_subject = models.CharField(_("subject of confirmation"), max_length=200, blank=True)
    confirmation_body = models.TextField(
        _("text of confirmation"), blank=True, help_text=_("Placeholders: {number}, {name}, {company}."),
    )
    max_attachment_mb = models.PositiveSmallIntegerField(_("max. size of attachments (MB, total)"), default=3)
    max_attachments = models.PositiveSmallIntegerField(_("max. number of attachments"), default=5)

    class Meta:
        verbose_name = _("fault report settings")
        verbose_name_plural = _("fault report settings")

    def __str__(self):
        return str(_("Fault report settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FaultReport(models.Model):
    class Status(models.TextChoices):
        NEW = "new", _("New")
        IN_PROGRESS = "in_progress", _("In progress")
        CLOSED = "closed", _("Closed")

    number = models.CharField(_("number"), max_length=32, db_index=True)
    status = models.CharField(_("status"), max_length=12, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(_("reported at"), default=timezone.now)

    customer = models.ForeignKey("customers.Customer", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="fault_reports", verbose_name=_("customer"))
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+", verbose_name=_("reported by"))
    licence = models.ForeignKey("licences.Licence", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="fault_reports", verbose_name=_("licence"))
    covered_until = models.DateField(_("covered until"), null=True, blank=True,
                                     help_text=_("End date of the licence at the time of reporting; empty = no cover found."))

    # Device and fault
    vendor = models.CharField(_("brand"), max_length=120)
    device = models.CharField(_("device"), max_length=200)
    serial_nr = models.CharField(_("serial number"), max_length=80, db_index=True)
    operating_system = models.CharField(_("operating system"), max_length=200, blank=True)
    description = models.TextField(_("description of the fault"))
    repair_option = models.ForeignKey(RepairOption, on_delete=models.SET_NULL, null=True, blank=True,
                                      verbose_name=_("desired handling"))
    reference = models.CharField(_("your reference"), max_length=128, blank=True)

    # Reseller (who reports)
    reseller_name = models.CharField(_("company"), max_length=128)
    reseller_address = models.CharField(_("address"), max_length=200, blank=True)
    reseller_postal_code = models.CharField(_("postal code"), max_length=20, blank=True)
    reseller_city = models.CharField(_("city"), max_length=100, blank=True)
    reseller_phone = models.CharField(_("phone"), max_length=40, blank=True)
    reseller_email = models.EmailField(_("email"), blank=True)

    # Location of the device
    location_name = models.CharField(_("company at location"), max_length=128)
    location_contact = models.CharField(_("contact person at location"), max_length=128)
    location_address = models.CharField(_("address of location"), max_length=200)
    location_postal_code = models.CharField(_("postal code of location"), max_length=20)
    location_city = models.CharField(_("city of location"), max_length=100)
    location_country = models.CharField(_("country of location"), max_length=60, blank=True)
    location_phone = models.CharField(_("phone at location"), max_length=40)
    location_email = models.EmailField(_("email at location"), help_text=_("The confirmation is sent here."))

    internal_notes = models.TextField(_("internal notes"), blank=True)

    class Meta:
        verbose_name = _("fault report")
        verbose_name_plural = _("fault reports")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.number} · {self.device} ({self.serial_nr})"

    @property
    def is_covered(self):
        return bool(self.covered_until and self.covered_until >= timezone.localtime(self.created_at).date())


def attachment_path(instance, filename):
    return f"fault-attachments/{instance.report_id}/{uuid.uuid4().hex[:8]}-{filename}"


class FaultAttachment(models.Model):
    report = models.ForeignKey(FaultReport, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(_("file"), upload_to=attachment_path, storage=data_storage)
    name = models.CharField(_("name"), max_length=200)
    size = models.PositiveIntegerField(_("size"), default=0)

    class Meta:
        verbose_name = _("attachment")
        verbose_name_plural = _("attachments")

    def __str__(self):
        return self.name
