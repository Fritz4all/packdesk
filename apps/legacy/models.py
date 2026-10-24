from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
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


IDENTIFIER = RegexValidator(r"^[A-Za-z_][A-Za-z0-9_]*$", _("Use a table or column name: letters, digits and _ only."))


def part_choices():
    from .parts import PARTS

    return [(p.key, p.label) for p in PARTS]


class TableMapping(models.Model):
    """Where one PackDesk part (customers, licences, ...) is found in an external database.

    The source is a table, or for data spread over several tables a SELECT query whose columns
    are then mapped. The connection is read-only either way.
    """

    database = models.ForeignKey(ExternalDatabase, on_delete=models.CASCADE, related_name="mappings",
                                 verbose_name=_("external database"))
    part = models.CharField(_("PackDesk part"), max_length=20, choices=part_choices)
    enabled = models.BooleanField(_("used"), default=True)
    source_table = models.CharField(_("table"), max_length=64, blank=True, validators=[IDENTIFIER])
    source_query = models.TextField(
        _("or a SELECT query"), blank=True,
        help_text=_("For data from several tables. Only SELECT; give columns a clear name with AS."),
    )
    id_column = models.CharField(
        _("column with the old ID"), max_length=64, blank=True, validators=[IDENTIFIER],
        help_text=_("Links rows to PackDesk records imported from this database (their 'ID in old system')."),
    )
    skip_column = models.CharField(_("leave out rows where column"), max_length=64, blank=True, validators=[IDENTIFIER])
    skip_value = models.CharField(_("has the value"), max_length=100, blank=True,
                                  help_text=_("E.g. column 'deleted' with value 1."))

    class Meta:
        verbose_name = _("table mapping")
        verbose_name_plural = _("table mappings")
        ordering = ["database", "part"]
        constraints = [models.UniqueConstraint(fields=["database", "part"], name="one_mapping_per_part")]

    def __str__(self):
        return f"{self.database} · {self.get_part_display()}"

    def clean(self):
        if bool(self.source_table) == bool(self.source_query.strip()):
            raise ValidationError(_("Fill in either a table or a SELECT query."))
        query = self.source_query.strip().rstrip(";").strip()
        if query and (not query.lower().startswith("select") or ";" in query):
            raise ValidationError({"source_query": _("Only one SELECT query is allowed.")})
        self.source_query = query

    def select_sql(self):
        return self.source_query or f"SELECT * FROM `{self.source_table}`"


class FieldMapping(models.Model):
    mapping = models.ForeignKey(TableMapping, on_delete=models.CASCADE, related_name="fields")
    field = models.CharField(_("PackDesk field"), max_length=40)
    column = models.CharField(_("column in external database"), max_length=64, validators=[IDENTIFIER])

    class Meta:
        verbose_name = _("field mapping")
        verbose_name_plural = _("field mappings")
        constraints = [models.UniqueConstraint(fields=["mapping", "field"], name="one_column_per_field")]

    def __str__(self):
        return f"{self.field} ← {self.column}"
