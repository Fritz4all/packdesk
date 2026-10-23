from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LicencesConfig(AppConfig):
    name = "apps.licences"
    verbose_name = _("Service packs and licences")

    def ready(self):
        from apps.numbering.checks import register_source

        from .numbering import licence_numbers

        register_source("licence", licence_numbers)
