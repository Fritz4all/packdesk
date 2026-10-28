from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class DashboardLayout(models.Model):
    """Per admin user: order of the dashboard blocks and which ones are hidden."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboard_layout")
    order = models.JSONField(default=list)
    hidden = models.JSONField(default=list)
    hidden_items = models.JSONField(default=list, help_text="Hidden parts of blocks, e.g. 'stats:active_customers'.")
    sidebar_order = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("dashboard layout")
        verbose_name_plural = _("dashboard layouts")
        permissions = [("view_reports", _("Can view sales reports"))]

    def __str__(self):
        return str(self.user)


class AdminMenu(models.Model):
    """The admin sidebar for everyone (one row): order and names of the main menus and which items each one
    holds. Empty = the standard menu. Edited under Configuration → Menu."""

    layout = models.JSONField(_("layout"), default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("admin menu")
        verbose_name_plural = _("admin menu")

    def __str__(self):
        return str(_("Admin menu"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
