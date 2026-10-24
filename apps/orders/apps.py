from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class OrdersConfig(AppConfig):
    name = "apps.orders"
    verbose_name = _("Orders")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import order_numbers

        register_source("order", order_numbers)
