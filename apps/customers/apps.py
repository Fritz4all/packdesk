from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CustomersConfig(AppConfig):
    name = "apps.customers"
    verbose_name = _("Customers")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import customer_numbers

        register_source("customer", customer_numbers)
