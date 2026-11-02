"""CMDB: a register of what customers use, as an add-on next to the rest of PackDesk.

It only depends on customers and contacts. Three things decide who sees it: `CmdbSettings.enabled` for the
installation, `CmdbCustomer.enabled` per customer, and `CmdbCustomer.portal_access` for a customer's own login.
Switching something off hides the items and keeps them.
"""

import hashlib
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.customers.models import FieldMode

# Columns of the import file; an own field cannot have one of these as its code.
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
    warranty_mail_enabled = models.BooleanField(
        _("send warranty reminders"), default=False,
        help_text=_("PackDesk checks this every hour and mails from 08:00. Each item is reported once per moment below."),
    )
    warranty_mail_days = models.CharField(
        _("days before the end of the warranty"), max_length=60, default="90,30",
        validators=[RegexValidator(r"^\s*\d{1,4}(\s*,\s*\d{1,4})*\s*$", _("Numbers separated by commas, e.g. 90,30."))],
        help_text=_("Numbers separated by commas, e.g. 90,30."),
    )
    warranty_mail_to = models.CharField(
        _("send the overview to"), max_length=300, blank=True,
        help_text=_("Email addresses separated by commas. Empty = the general email address from the settings."),
    )
    # No defaults on translated fields: django-modeltranslation treats a value equal to the
    # default as "not filled in" and would show another language. Texts are set by a migration.
    warranty_subject = models.CharField(_("subject of the mail to a customer"), max_length=200, blank=True,
                                        help_text=_("Placeholders: {company}, {customer}, {count}."))
    warranty_body = models.TextField(_("text of the mail to a customer"), blank=True,
                                     help_text=_("Placeholders: {company}, {customer}, {count}, {items}."))

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
    warranty_mail = models.BooleanField(
        _("gets warranty reminders"), default=False,
        help_text=_("Also mail this customer when warranty runs out (general email address of the customer)."),
    )

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


class ItemField(models.Model):
    """A field of an item: a standard one (a column of the item, one row each, made by a migration) or an own one
    for items of one or more types (kept in `ConfigurationItem.properties`). Standard fields cannot be removed."""

    class Kind(models.TextChoices):
        TEXT = "text", _("Text")
        NUMBER = "number", _("Number")
        CHOICE = "choice", _("Choice from a list")
        YES_NO = "yes_no", _("Yes / no")

    STANDARD = {"customer", "item_type", "name", "status", "manufacturer", "model", "serial_nr", "asset_tag", "location",
                "contact", "description", "purchase_date", "warranty_until", "end_of_life"}
    # Always needed: only the name can change.
    FIXED = {"customer", "item_type", "name"}
    # Has a value of its own when it is not on the form: hidden or required, not optional.
    NOT_OPTIONAL = {"status"}

    key = models.CharField(
        _("code"), max_length=40, unique=True, blank=True,
        validators=[RegexValidator(r"^[a-z][a-z0-9_]*$", _("Lower case letters, digits and _ only."))],
        help_text=_("Internal code, also the column name in import files, e.g. ip_address. Empty: made from the name."),
    )
    name = models.CharField(_("name"), max_length=100)
    mode = models.CharField(_("use"), max_length=8, choices=FieldMode.choices, default=FieldMode.OPTIONAL)
    in_list = models.BooleanField(_("show in the overview"), default=False)
    kind = models.CharField(_("kind"), max_length=10, choices=Kind.choices, default=Kind.TEXT)
    choices = models.TextField(_("choices"), blank=True, help_text=_("For a choice from a list: one option per line."))
    item_types = models.ManyToManyField(ItemType, related_name="own_fields", blank=True, verbose_name=_("item types"))
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("item field")
        verbose_name_plural = _("item fields")
        ordering = ["position", "pk"]

    def __str__(self):
        return self.name

    @classmethod
    def own(cls):
        return cls.objects.exclude(key__in=cls.STANDARD)

    @property
    def is_own(self):
        return self.key not in self.STANDARD

    @property
    def is_required(self):
        return self.mode == FieldMode.REQUIRED

    def clean(self):
        if self.key in self.FIXED and self.mode != FieldMode.REQUIRED:
            raise ValidationError({"mode": _("This field is always needed.")})
        if self.key in self.NOT_OPTIONAL and self.mode == FieldMode.OPTIONAL:
            raise ValidationError({"mode": _("This field is required or hidden.")})
        if self.is_own and self.key in RESERVED_KEYS:
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


class ItemStatus(models.Model):
    """Status of an item, e.g. planned or in use (configurable)."""

    class Colour(models.TextChoices):
        INFO = "info", _("Blue")
        SUCCESS = "success", _("Green")
        WARNING = "warning", _("Orange")
        DANGER = "danger", _("Red")

    key = models.SlugField(_("code"), max_length=32, unique=True,
                           help_text=_("Internal code, also usable in import files, e.g. in_use."))
    name = models.CharField(_("name"), max_length=60)
    colour = models.CharField(_("colour"), max_length=8, choices=Colour.choices, default=Colour.INFO)
    out_of_use = models.BooleanField(_("no longer in use"), default=False,
                                     help_text=_("Items with this status get no warranty reminders."))
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("status")
        verbose_name_plural = _("statuses")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


class RelationKind(models.Model):
    """Kind of relation between two items, e.g. runs on (configurable)."""

    key = models.SlugField(_("code"), max_length=32, unique=True,
                           help_text=_("Internal code, used in the relations column of import files, e.g. runs_on."))
    name = models.CharField(_("name"), max_length=60, help_text=_("Reads as: item … other item, e.g. runs on."))
    counts_for_impact = models.BooleanField(
        _("counts for the impact"), default=True,
        help_text=_("On: the item has a problem when the other item fails."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("order"), default=0)

    class Meta:
        verbose_name = _("relation type")
        verbose_name_plural = _("relation types")
        ordering = ["position", "name"]

    def __str__(self):
        return self.name


def default_status():
    """The status of an item that was not given one."""
    status = ItemStatus.objects.filter(key="in_use").first() or ItemStatus.objects.filter(is_active=True).first()
    return status.pk if status else None


def default_relation_kind():
    kind = RelationKind.objects.filter(key="depends_on").first() or RelationKind.objects.filter(is_active=True).first()
    return kind.pk if kind else None


class ConfigurationItem(models.Model):
    number = models.CharField(_("number"), max_length=32, unique=True, editable=False)
    # Not selectable for customers without the CMDB; this also holds for the search box on the form.
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="configuration_items",
                                 verbose_name=_("customer"), limit_choices_to={"cmdb__enabled": True})
    item_type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="items", verbose_name=_("type"))
    name = models.CharField(_("name"), max_length=120)
    status = models.ForeignKey(ItemStatus, on_delete=models.PROTECT, related_name="items", verbose_name=_("status"),
                               default=default_status)
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
            rows = list(Relation.objects.filter(target_id__in=current, kind__counts_for_impact=True)
                        .exclude(source_id__in=seen)
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

    source = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name="relations_out",
                               verbose_name=_("item"))
    kind = models.ForeignKey(RelationKind, on_delete=models.PROTECT, related_name="relations", verbose_name=_("relation"),
                             default=default_relation_kind)
    target = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name="relations_in",
                               verbose_name=_("other item"))

    class Meta:
        verbose_name = _("relation")
        verbose_name_plural = _("relations")
        constraints = [models.UniqueConstraint(fields=["source", "kind", "target"], name="cmdb_one_relation_of_a_kind")]

    def __str__(self):
        return f"{self.kind} {self.target}"

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
        SCAN = "scan", _("Automatic discovery")

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


class WarrantyReminder(models.Model):
    """A warranty reminder that went out, so it goes out once. A new warranty date starts over."""

    class Audience(models.TextChoices):
        STAFF = "staff", _("Staff")
        CUSTOMER = "customer", _("Customer")

    item = models.ForeignKey(ConfigurationItem, on_delete=models.CASCADE, related_name="warranty_reminders")
    warranty_until = models.DateField(_("warranty until"))
    days = models.PositiveSmallIntegerField(_("days before"))
    audience = models.CharField(_("sent to"), max_length=8, choices=Audience.choices)
    sent_at = models.DateTimeField(_("sent at"), auto_now_add=True)

    class Meta:
        verbose_name = _("warranty reminder")
        verbose_name_plural = _("warranty reminders")
        constraints = [models.UniqueConstraint(fields=["item", "warranty_until", "days", "audience"],
                                               name="cmdb_one_warranty_reminder")]

    def __str__(self):
        return f"{self.item_id}: {self.warranty_until} ({self.days})"


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class DiscoverySource(models.Model):
    """A place that reports items of one customer, e.g. a script on a server there. Only a hash of its key is kept."""

    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="discovery_sources",
                                 verbose_name=_("customer"), limit_choices_to={"cmdb__enabled": True})
    name = models.CharField(_("name"), max_length=100, help_text=_("For yourself, e.g. Main office."))
    item_type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name="+", verbose_name=_("item type"),
                                  help_text=_("The type of new items from this source."))
    auto_accept = models.BooleanField(_("accept automatically"), default=False,
                                      help_text=_("Off: what is found first waits for you under Discovered items."))
    is_active = models.BooleanField(_("active"), default=True)
    token_digest = models.CharField(max_length=64, unique=True, editable=False)
    last_report_at = models.DateTimeField(_("last report"), null=True, blank=True, editable=False)
    created_at = models.DateTimeField(_("created"), auto_now_add=True)

    class Meta:
        verbose_name = _("discovery source")
        verbose_name_plural = _("discovery sources")
        ordering = ["customer__name", "name"]

    def __str__(self):
        return f"{self.customer.name}: {self.name}"

    def new_token(self):
        """Sets a new key and returns it; this is the only moment the key itself is known."""
        token = secrets.token_urlsafe(32)
        self.token_digest = token_hash(token)
        return token

    def reported(self):
        self.last_report_at = timezone.now()
        self.save(update_fields=["last_report_at"])


class DiscoveredItem(models.Model):
    """What a source reported about one thing, until someone decides what happens with it."""

    class Status(models.TextChoices):
        NEW = "new", _("New")
        CHANGED = "changed", _("Differs from the item")
        ACCEPTED = "accepted", _("Accepted")
        IGNORED = "ignored", _("Ignored")

    source = models.ForeignKey(DiscoverySource, on_delete=models.CASCADE, related_name="discovered", verbose_name=_("source"))
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="+", verbose_name=_("customer"))
    key = models.CharField(_("recognised by"), max_length=120,
                           help_text=_("What the source recognises this by, e.g. a serial number."))
    data = models.JSONField(_("reported"), default=dict)
    status = models.CharField(_("status"), max_length=8, choices=Status.choices, default=Status.NEW, db_index=True)
    item = models.ForeignKey(ConfigurationItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="discoveries",
                             verbose_name=_("item"))
    first_seen = models.DateTimeField(_("first seen"), auto_now_add=True)
    last_seen = models.DateTimeField(_("last seen"), default=timezone.now)

    class Meta:
        verbose_name = _("discovered item")
        verbose_name_plural = _("discovered items")
        ordering = ["-last_seen"]
        constraints = [models.UniqueConstraint(fields=["customer", "key"], name="cmdb_one_discovery_per_key")]

    def __str__(self):
        return self.data.get("name") or self.key
