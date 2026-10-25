from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PrintingConfig(AppConfig):
    name = "apps.printing"
    verbose_name = _("Printing services")
