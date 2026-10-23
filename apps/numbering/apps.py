from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NumberingConfig(AppConfig):
    name = "apps.numbering"
    verbose_name = _("Numbering")
