from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PartsConfig(AppConfig):
    name = "apps.parts"
    verbose_name = _("Spare parts")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import request_numbers

        register_source("part_request", request_numbers)
