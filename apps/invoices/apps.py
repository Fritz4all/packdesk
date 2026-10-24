from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class InvoicesConfig(AppConfig):
    name = "apps.invoices"
    verbose_name = _("Invoices")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import invoice_numbers

        register_source("invoice", invoice_numbers)
