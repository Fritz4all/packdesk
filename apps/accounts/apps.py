from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = _("Users")

    def ready(self):
        from django.db.models.signals import post_save

        from .models import User
        from .roles import ensure_roles, sync_superadmin

        post_migrate.connect(ensure_roles, sender=self)
        post_save.connect(sync_superadmin, sender=User, dispatch_uid="sync_superadmin")
