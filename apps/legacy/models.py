from django.db import models
from django.utils.translation import gettext_lazy as _

from . import crypto


class ExternalDatabase(models.Model):
    """Another database PackDesk may read, e.g. the database of the previous webshop. Never written to."""

    class Engine(models.TextChoices):
        MARIADB = "mariadb", _("MariaDB / MySQL")
        POSTGRES = "postgres", _("PostgreSQL")

    name = models.CharField(_("name"), max_length=100, help_text=_("For yourself, e.g. 'Previous webshop (production)'."))
    engine = models.CharField(_("type"), max_length=10, choices=Engine.choices, default=Engine.MARIADB)
    host = models.CharField(_("server"), max_length=200, help_text=_("IP address or host name."))
    port = models.PositiveIntegerField(_("port"), null=True, blank=True, help_text=_("Empty = standard port (3306 or 5432)."))
    database = models.CharField(_("database name"), max_length=100)
    user = models.CharField(_("user"), max_length=100, help_text=_("Use a user that may only read."))
    password_encrypted = models.TextField(_("password (encrypted)"), blank=True, editable=False)
    notes = models.TextField(_("notes"), blank=True)

    last_checked_at = models.DateTimeField(_("last tested"), null=True, blank=True, editable=False)
    last_check_ok = models.BooleanField(_("connection works"), null=True, editable=False)
    last_check_message = models.TextField(_("result of last test"), blank=True, editable=False)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("external database")
        verbose_name_plural = _("external databases")
        ordering = ["name"]
        permissions = [("compare_databases", _("Can compare databases"))]

    def __str__(self):
        return self.name

    def set_password(self, raw):
        self.password_encrypted = crypto.encrypt(raw)

    def get_password(self):
        return crypto.decrypt(self.password_encrypted)

    @property
    def default_port(self):
        return 3306 if self.engine == self.Engine.MARIADB else 5432
