from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TrashConfig(AppConfig):
    name = "apps.trash"
    verbose_name = _("Trash")

    def ready(self):
        from . import admin_hooks

        admin_hooks.install()
