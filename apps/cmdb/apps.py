from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CmdbConfig(AppConfig):
    name = "apps.cmdb"
    verbose_name = _("CMDB")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import item_numbers

        register_source("cmdb", item_numbers)
