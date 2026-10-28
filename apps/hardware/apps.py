from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class HardwareConfig(AppConfig):
    name = "apps.hardware"
    verbose_name = _("Hardware")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import device_numbers

        register_source("hardware_device", device_numbers)
