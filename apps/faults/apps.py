from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FaultsConfig(AppConfig):
    name = "apps.faults"
    verbose_name = _("Fault reports")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import ticket_numbers

        register_source("ticket", ticket_numbers)
