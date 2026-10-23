from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class DashboardLayout(models.Model):
    """Per admin user: order of the dashboard blocks and which ones are hidden."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboard_layout")
    order = models.JSONField(default=list)
    hidden = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("dashboard layout")
        verbose_name_plural = _("dashboard layouts")
        permissions = [("view_reports", _("Can view sales reports"))]

    def __str__(self):
        return str(self.user)
