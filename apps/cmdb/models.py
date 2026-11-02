"""CMDB: a register of what customers use, as an add-on next to the rest of PackDesk.

It only depends on customers and contacts. Three things decide who sees it: `CmdbSettings.enabled` for the
installation, `CmdbCustomer.enabled` per customer, and `CmdbCustomer.portal_access` for a customer's own login.
Switching something off hides the items and keeps them.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

# Columns of the import file; a property cannot have one of these as its code.
RESERVED_KEYS = {
    "number", "customer", "type", "name", "status", "manufacturer", "model", "serial_nr", "asset_tag", "location",
    "contact", "purchase_date", "warranty_until", "end_of_life", "description", "relations",
}


class CmdbSettings(models.Model):
    """One row: whether this installation uses the CMDB."""

    enabled = models.BooleanField(
        _("use the CMDB"), default=False,
        help_text=_("Off: the items and the switches on customers are hidden. Nothing is deleted."),
    )

    class Meta:
        verbose_name = _("CMDB settings")
        verbose_name_plural = _("CMDB settings")

    def __str__(self):
        return str(_("CMDB settings"))

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class CmdbCustomer(models.Model):
    """Whether a customer uses the CMDB. Kept here so the customer module knows nothing about this add-on."""

    customer = models.OneToOneField("customers.Customer", on_delete=models.CASCADE, related_name="cmdb",
                                    verbose_name=_("customer"))
    enabled = models.BooleanField(_("uses the CMDB"), default=False,
                                  help_text=_("Off: the items of this customer are hidden and kept."))
    portal_access = models.BooleanField(_("may see items when logged in"), default=False,
                                        help_text=_("Contacts with a login see a read-only list of the items."))

    class Meta:
        verbose_name = _("CMDB")
        verbose_name_plural = _("CMDB")

    def __str__(self):
        return str(self.customer)


class ItemType(models.Model):
    """Kind of item, e.g. hardware, software, network (configurable)."""

    name = models.CharField(_("name"), max_length=60)
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("item type")
        verbose_name_plural = _("item types")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class ItemProperty(models.Model):
    """An extra field for items of one or more types, e.g. IP address or version."""

    class Kind(models.TextChoices):
        TEXT = "text", _("Text")
        NUMBER = "number", _("Number")
        CHOICE = "choice", _("Choice from a list")
        YES_NO = "yes_no", _("Yes / no")

    key = models.CharField(
        _("code"), max_length=40, unique=True,
        validators=[RegexValidator(r"^[a-z][a-z0-9_]*$", _("Lower case letters, digits and _ only."))],
        help_text=_("Internal code, also the column name in import files, e.g. ip_address."),
    )
    name = models.CharField(_("name"), max_length=100)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.TEXT)
    choices = models.TextField(_("choices"), blank=True, help_text=_("For a choice from a list: one option per line."))
    item_types = models.ManyToManyField(ItemType, related_name="properties", blank=True, verbose_name=_("item types"))
    required = models.BooleanField(_("required"), default=False)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("item property")
        verbose_name_plural = _("item properties")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.key in RESERVED_KEYS:
            raise ValidationError({"key": _("This code is already a column of the import file.")})

    def options(self):
        return [line.strip() for line in self.choices.splitlines() if line.strip()]

    def display(self, value):
        """A stored value as people read it."""
        if value in (None, ""):
            return ""
        if self.kind == self.Kind.YES_NO:
            return str(_("Yes") if value else _("No"))
        return str(value)


class ConfigurationItem(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", _("Planned")
        IN_USE = "in_use", _("In use")
        IN_REPAIR = "in_repair", _("In repair")
        RETIRED = "retired", _("Retired")

    number = models.CharField(_("number"), max_length=32, unique=True, editable=False)
    # Not selectable for customers without the CMDB; this also holds for the search box on the form.
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="configuration_items",
                                 verbose_name=_("customer"), limit_choices_to={"cmdb__enabled": True})
    item_type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="items", verbose_name=_("type"))
    name = models.CharField(_("name"), max_length=120)
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.IN_USE)
    manufacturer = models.CharField(_("manufacturer"), max_length=80, blank=True)
    model = models.CharField(_("model"), max_length=120, blank=True)
    serial_nr = models.CharField(_("serial number"), max_length=80, blank=True, db_index=True)
    asset_tag = models.CharField(_("asset tag"), max_length=80, blank=True)
    location = models.CharField(_("location"), max_length=120, blank=True)
    contact = models.ForeignKey("customers.Contact", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                verbose_name=_("contact"), help_text=_("A contact of the same customer."))
    purchase_date = models.DateField(_("purchase date"), null=True, blank=True)
    warranty_until = models.DateField(_("warranty until"), null=True, blank=True)
    end_of_life = models.DateField(_("end of life"), null=True, blank=True)
    description = models.TextField(_("internal description"), blank=True)
    properties = models.JSONField(_("properties"), default=dict, blank=True)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated"), auto_now=True)

    class Meta:
        verbose_name = _("configuration item")
        verbose_name_plural = _("configuration items")
        ordering = ["customer__name", "name"]
        permissions = [
            ("export_configurationitem", _("Can export configuration items")),
            ("import_configurationitem", _("Can import configuration items")),
        ]

    def __str__(self):
        return f"{self.number} {self.name}".strip()

    def clean(self):
        if self.contact_id and self.customer_id and self.contact.customer_id != self.customer_id:
            raise ValidationError({"contact": _("This contact belongs to another customer.")})
        if self.pk and self.customer_id:
            old_customer = type(self).objects.filter(pk=self.pk).values_list("customer_id", flat=True).first()
            if old_customer != self.customer_id and (self.relations_out.exists() or self.relations_in.exists()):
                raise ValidationError({"customer": _("Remove the relations of this item before moving it to another customer.")})

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.numbering.models import NumberSequence

            _n, self.number = NumberSequence.issue("cmdb")
        super().save(*args, **kwargs)

    def affected_items(self):
        """Everything that has a problem when this item fails: what points at it, directly or through others."""
        seen, found, current = {self.pk}, [], [self.pk]
        while current:
            rows = list(Relation.objects.filter(target_id__in=current).exclude(source_id__in=seen)
                        .select_related("source", "source__contact"))
            current = []
            for relation in rows:
                if relation.source_id not in seen:
                    seen.add(relation.source_id)
                    found.append(relation.source)
                    current.append(relation.source_id)
        return found


class Relation(models.Model):
    """`source` <kind> `target`: the source has a problem when the target fails."""

    class Kind(models.TextChoices):
        DEPENDS_ON = "depends_on", _("depends on")
        RUNS_ON = "runs_on", _("runs on")
        CONNECTED_TO = "connected_to", _("is connected to")
        PART_OF = "part_of", _("is part of")
        USES = "uses", _("uses")

    source = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name="relations_out",
                               verbose_name=_("item"))
    kind = models.CharField(_("relation"), max_length=14, choices=Kind.choices, default=Kind.DEPENDS_ON)
    target = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name="relations_in",
                               verbose_name=_("other item"))

    class Meta:
        verbose_name = _("relation")
        verbose_name_plural = _("relations")
        constraints = [models.UniqueConstraint(fields=["source", "kind", "target"], name="cmdb_one_relation_of_a_kind")]

    def __str__(self):
        return f"{self.get_kind_display()} {self.target}"

    def clean(self):
        if not (self.source_id and self.target_id):
            return
        if self.source_id == self.target_id:
            raise ValidationError({"target": _("An item cannot have a relation with itself.")})
        if self.source.customer_id != self.target.customer_id:
            raise ValidationError({"target": _("Both items must belong to the same customer.")})


class ItemChange(models.Model):
    """One line of an item's history. Lines are only ever added."""

    class Source(models.TextChoices):
        ADMIN = "admin", _("Admin")
        IMPORT = "import", _("Import")

    item = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name="changes")
    changed_at = models.DateTimeField(_("when"), auto_now_add=True, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                             verbose_name=_("who"))
    source = models.CharField(_("source"), max_length=8, choices=Source.choices, default=Source.ADMIN)
    field = models.CharField(_("field"), max_length=120)
    old_value = models.TextField(_("old value"), blank=True)
    new_value = models.TextField(_("new value"), blank=True)

    class Meta:
        verbose_name = _("item change")
        verbose_name_plural = _("item changes")
        ordering = ["-changed_at", "-pk"]

    def __str__(self):
        return f"{self.item_id}: {self.field}"
