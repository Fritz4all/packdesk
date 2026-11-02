import datetime

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.functional import lazy
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import get_language, gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminDecimalFieldWidget, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from apps.core.object_actions import ObjectAction, ObjectActionsMixin
from apps.customers import overview
from apps.customers.admin import CustomerAdmin
from apps.customers.models import Customer, FieldMode

from . import diagram, discovery, fields, history, transfer_views, warranty
from .models import (
    RESERVED_KEYS, CmdbCustomer, CmdbSettings, ConfigurationItem, DiscoveredItem, DiscoverySource, ItemField, ItemStatus,
    ItemType, Relation, RelationKind,
)

PROPERTY_PREFIX = "prop_"
SOON_DAYS = 90


def in_use():
    return CmdbSettings.load().enabled


class WhenEnabled:
    """Admin pages that only exist while the installation uses the CMDB."""

    def has_module_permission(self, request):
        return in_use() and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return in_use() and super().has_view_permission(request, obj)

    def has_add_permission(self, request, *args):
        return in_use() and super().has_add_permission(request, *args)

    def has_change_permission(self, request, obj=None):
        return in_use() and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return in_use() and super().has_delete_permission(request, obj)


@admin.register(CmdbSettings)
class CmdbSettingsAdmin(ObjectActionsMixin, ModelAdmin, TabbedTranslationAdmin):
    fieldsets = [
        (None, {"fields": ["enabled"]}),
        (_("Warranty reminders"), {"fields": [
            "warranty_mail_enabled", "warranty_mail_days", "warranty_mail_to", "warranty_subject", "warranty_body",
        ]}),
    ]
    object_actions = [
        ObjectAction("send_warranty", _("Send warranty reminders now"), "mail", handler="send_warranty",
                     show_if="can_send_warranty"),
    ]

    def can_send_warranty(self, obj):
        return obj.enabled and obj.warranty_mail_enabled

    def send_warranty(self, request, obj):
        result = warranty.send_due()
        if result["errors"]:
            messages.error(request, gettext("%(n)s mail(s) could not be sent; PackDesk tries again in an hour.")
                           % {"n": result["errors"]})
        messages.success(request, gettext("Sent: %(items)s item(s) in the overview, %(customers)s mail(s) to customers.")
                         % {"items": result["overview"], "customers": result["customers"]})

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:cmdb_cmdbsettings_change", args=[CmdbSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ItemType)
class ItemTypeAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "show_items", "is_active", "position"]
    list_editable = ["position"]

    @display(description=_("Items"))
    def show_items(self, obj):
        return obj.items.count()


class AnyLanguageName(forms.ModelForm):
    """A name in one language is enough: the error of an empty name would otherwise sit on a tab that is not in view."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name_fields = [f"name_{lang}" for lang, _label in settings.LANGUAGES if f"name_{lang}" in self.fields]
        for name in self.name_fields:
            self.fields[name].required = False

    def clean(self):
        cleaned = super().clean()
        filled = next((cleaned[name] for name in self.name_fields if cleaned.get(name)), "")
        default = f"name_{settings.LANGUAGE_CODE[:2]}"
        if filled and not cleaned.get(default):
            cleaned[default] = filled
        elif not filled and self.name_fields:
            shown = f"name_{get_language()}"
            self.add_error(shown if shown in self.name_fields else self.name_fields[0], _("Enter a name."))
        return cleaned


class ItemFieldForm(AnyLanguageName):
    class Meta:
        model = ItemField
        fields = "__all__"

    def _free_key(self, name):
        """A code from the name: "Rack position" → rack_position, with a number when it is taken."""
        base = slugify(name).replace("-", "_")[:36]
        if not base or not base[0].isalpha():
            base = f"field_{base}".rstrip("_")[:36]
        key, n = base, 1
        while key in RESERVED_KEYS or ItemField.objects.filter(key=key).exists():
            n += 1
            key = f"{base}_{n}"
        return key

    def clean(self):
        cleaned = super().clean()
        if "key" in self.fields and not cleaned.get("key") and "key" not in self.errors:
            name = next((cleaned[f] for f in self.name_fields if cleaned.get(f)), "")
            if name:
                cleaned["key"] = self._free_key(name)
        if "item_types" in self.fields and "item_types" in cleaned and not cleaned["item_types"]:
            self.add_error("item_types", _("Choose at least one item type; the field shows for items of those types."))
        return cleaned


def colour_badge(colour, text):
    """A text in the colour of a status; static/admin/packdesk-admin.css has the colours."""
    return format_html('<span class="pd-colour pd-colour-{}">{}</span>', colour, text)


class ColourChoice(forms.RadioSelect):
    """All colours side by side, each as it will look. A dropdown list cannot show colours in every browser."""

    def render(self, name, value, attrs=None, renderer=None):
        options = format_html_join("", '<label class="pd-colour-option"><input type="radio" name="{}" value="{}"{}> {}</label>', (
            (name, code, mark_safe(" checked") if str(value) == str(code) else "", colour_badge(code, label))
            for code, label in self.choices if code))
        return format_html('<div class="pd-colour-choice">{}</div>', options)


class ItemStatusForm(AnyLanguageName):
    class Meta:
        model = ItemStatus
        fields = "__all__"
        widgets = {"colour": ColourChoice}


class RelationKindForm(AnyLanguageName):
    class Meta:
        model = RelationKind
        fields = "__all__"


class ItemTypeForm(AnyLanguageName):
    class Meta:
        model = ItemType
        fields = "__all__"


@admin.register(ItemField)
class ItemFieldAdmin(ModelAdmin, TabbedTranslationAdmin):
    """Own fields can be added and removed; the standard fields stay, and only their name and use change."""

    form = ItemFieldForm
    list_display = ["name", "show_source", "mode", "in_list", "position"]
    list_editable = ["mode", "in_list", "position"]
    list_display_links = ["name"]
    filter_horizontal = ["item_types"]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("item_types")

    @display(description=_("Field"))
    def show_source(self, obj):
        if not obj.is_own:
            return gettext("Standard")
        return f"{obj.get_kind_display()} · " + ", ".join(str(t) for t in obj.item_types.all())

    def get_fieldsets(self, request, obj=None):
        if obj is not None and not obj.is_own:
            names = ["name", "mode", "in_list", "position"]
        else:
            names = ["name", "key", "kind", "choices", "item_types", "mode", "in_list", "position"]
        return [(None, {"fields": self.replace_orig_field(names)})]

    def get_readonly_fields(self, request, obj=None):
        # Stored values and import files go by the code.
        return ["key"] if obj is not None and obj.is_own else []

    def get_changeform_initial_data(self, request):
        last = ItemField.objects.order_by("-position").first()
        return {"position": last.position + 1 if last else 0}

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)  # a list that also holds the standard fields
        return actions

    def has_delete_permission(self, request, obj=None):
        return (obj is None or obj.is_own) and super().has_delete_permission(request, obj)


@admin.register(ItemStatus)
class ItemStatusAdmin(ModelAdmin, TabbedTranslationAdmin):
    form = ItemStatusForm
    list_display = ["name", "key", "show_colour", "out_of_use", "is_active", "position"]
    list_editable = ["position"]

    @display(description=_("Colour"), ordering="colour")
    def show_colour(self, obj):
        return colour_badge(obj.colour, obj.get_colour_display())


@admin.register(RelationKind)
class RelationKindAdmin(ModelAdmin, TabbedTranslationAdmin):
    form = RelationKindForm
    list_display = ["name", "key", "counts_for_impact", "is_active", "position"]
    list_editable = ["position"]


ItemTypeAdmin.form = ItemTypeForm


class CustomerSwitchInline(WhenEnabled, StackedInline):
    """The switches on the customer form. Added here, so the customer module stays unaware of the CMDB."""

    model = CmdbCustomer
    extra = 1
    max_num = 1
    can_delete = False
    tab = True
    fields = ["enabled", "portal_access", "warranty_mail", "show_items"]
    readonly_fields = ["show_items"]

    @display(description=_("Items"))
    def show_items(self, obj):
        if not obj.pk:
            return "–"
        url = reverse("admin:cmdb_configurationitem_changelist")
        return format_html('<a class="underline" href="{}?customer__id__exact={}">{}</a>', url, obj.customer_id,
                           obj.customer.configuration_items.count())


CustomerAdmin.inlines = [*CustomerAdmin.inlines, CustomerSwitchInline]


class RelationForm(forms.ModelForm):
    class Meta:
        model = Relation
        fields = ["kind", "target"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].queryset = RelationKind.objects.filter(Q(is_active=True) | Q(pk=self.instance.kind_id))


class RelationInline(WhenEnabled, TabularInline):
    model = Relation
    form = RelationForm
    fk_name = "source"
    extra = 0
    tab = True
    fields = ["kind", "target"]
    autocomplete_fields = ["target"]


def property_field(prop):
    """A form field for one property; its item types go along, so the page shows only those of the chosen type
    (static/admin/cmdb-properties.js)."""
    attrs = {"data-property-types": ",".join(str(t.pk) for t in prop.item_types.all())}
    if prop.kind == ItemField.Kind.NUMBER:
        return forms.DecimalField(label=prop.name, required=False, widget=UnfoldAdminDecimalFieldWidget(attrs=attrs))
    if prop.kind == ItemField.Kind.CHOICE:
        choices = [("", "—")] + [(o, o) for o in prop.options()]
        return forms.ChoiceField(label=prop.name, required=False, choices=choices, widget=UnfoldAdminSelectWidget(attrs=attrs))
    if prop.kind == ItemField.Kind.YES_NO:
        choices = [("", "—"), ("1", _("Yes")), ("0", _("No"))]
        return forms.ChoiceField(label=prop.name, required=False, choices=choices, widget=UnfoldAdminSelectWidget(attrs=attrs))
    return forms.CharField(label=prop.name, required=False, max_length=200, widget=UnfoldAdminTextInputWidget(attrs=attrs))


class ItemForm(forms.ModelForm):
    class Meta:
        model = ConfigurationItem
        exclude = ["properties"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_properties = list(ItemField.own().exclude(mode=FieldMode.HIDDEN).prefetch_related("item_types"))
        for key, field in fields.config().items():
            if key in self.fields:
                if field.name:
                    self.fields[key].label = field.name
                self.fields[key].required = field.mode == FieldMode.REQUIRED
        if "status" in self.fields:
            self.fields["status"].queryset = ItemStatus.objects.filter(Q(is_active=True) | Q(pk=self.instance.status_id))
        for prop in self.item_properties:
            name = PROPERTY_PREFIX + prop.key
            if name in self.fields and self.instance.pk:
                value = (self.instance.properties or {}).get(prop.key)
                if prop.kind == ItemField.Kind.YES_NO and value is not None:
                    value = "1" if value else "0"
                self.initial[name] = value

    def _type_properties(self):
        item_type = self.cleaned_data.get("item_type")
        if item_type is None:
            return []
        return [p for p in self.item_properties if any(t.pk == item_type.pk for t in p.item_types.all())]

    def clean(self):
        cleaned = super().clean()
        for prop in self._type_properties():
            name = PROPERTY_PREFIX + prop.key
            if prop.is_required and name in self.fields and cleaned.get(name) in (None, ""):
                self.add_error(name, _("Required for this item type."))
        return cleaned

    def save(self, commit=True):
        item = super().save(commit=False)
        shown = {prop.key for prop in self.item_properties}
        hidden = set(ItemField.own().filter(mode=FieldMode.HIDDEN).values_list("key", flat=True))
        values = {k: v for k, v in (item.properties or {}).items() if k in hidden and k not in shown}
        for prop in self._type_properties():  # only the properties of its type; the others are dropped
            value = self.cleaned_data.get(PROPERTY_PREFIX + prop.key)
            if value in (None, ""):
                continue
            if prop.kind == ItemField.Kind.YES_NO:
                value = value == "1"
            elif prop.kind == ItemField.Kind.NUMBER:
                value = int(value) if value == value.to_integral_value() else float(value)
            values[prop.key] = value
        item.properties = values
        if commit:
            item.save()
            self.save_m2m()
        return item


def _column(key, value=None):
    """A column of the item list with the name set under CMDB settings → Fields."""
    name = lazy(fields.label, str)(key)

    @display(description=name, ordering=key)
    def column(self, obj):
        return value(obj) if value else getattr(obj, key)

    return column


def _own_column(field):
    """A column for an own field; those exist per installation, so this is made per request."""
    @display(description=field.name)
    def column(obj):
        return field.display((obj.properties or {}).get(field.key))

    column.__name__ = f"own_{field.key}"
    return column


class WarrantyFilter(SimpleListFilter):
    title = _("warranty")
    parameter_name = "warranty"

    def lookups(self, request, model_admin):
        return [("expired", _("Expired")), ("soon", _("Expires within 90 days"))]

    def queryset(self, request, queryset):
        today = timezone.localdate()
        if self.value() == "expired":
            return queryset.filter(warranty_until__lt=today)
        if self.value() == "soon":
            return queryset.filter(warranty_until__gte=today,
                                   warranty_until__lte=today + datetime.timedelta(days=SOON_DAYS))
        return queryset


@admin.register(ConfigurationItem)
class ConfigurationItemAdmin(WhenEnabled, ModelAdmin):
    form = ItemForm
    change_list_template = "admin/cmdb/configurationitem/change_list.html"
    list_display = ["number", "col_name", "col_customer", "col_item_type", "col_status", "col_serial_nr", "col_location",
                    "col_warranty_until"]
    list_display_links = ["number", "col_name"]
    list_filter = ["status", "item_type", WarrantyFilter, "customer"]
    search_fields = ["number", "name", "serial_nr", "asset_tag", "manufacturer", "model", "location",
                     "customer__name", "customer__number"]
    list_select_related = ["customer", "item_type", "status", "contact"]
    readonly_fields = ["number", "created_at", "updated_at", "show_diagram", "show_impact", "show_history", "show_property_hint"]
    autocomplete_fields = ["customer", "contact"]
    actions = ["export_xlsx", "export_csv"]

    class Media:
        js = ["admin/cmdb-properties.js"]

    def get_queryset(self, request):
        # Items of a customer that no longer uses the CMDB are hidden, and kept.
        return super().get_queryset(request).filter(customer__cmdb__enabled=True)

    col_customer = _column("customer")
    col_item_type = _column("item_type")
    col_name = _column("name")
    col_manufacturer = _column("manufacturer")
    col_model = _column("model")
    col_serial_nr = _column("serial_nr")
    col_asset_tag = _column("asset_tag")
    col_location = _column("location")
    col_contact = _column("contact")
    col_description = _column("description")
    col_purchase_date = _column("purchase_date")
    col_warranty_until = _column("warranty_until")
    col_end_of_life = _column("end_of_life")

    @display(description=lazy(fields.label, str)("status"), ordering="status")
    def col_status(self, obj):
        return colour_badge(obj.status.colour, obj.status)

    def get_list_display(self, request):
        columns = ItemField.objects.filter(in_list=True).exclude(mode=FieldMode.HIDDEN)
        return ["number", *[_own_column(field) if field.is_own else f"col_{field.key}" for field in columns]]

    def get_list_display_links(self, request, list_display):
        return [column for column in ["number", "col_name"] if column in list_display]

    def get_list_filter(self, request):
        hidden = fields.hidden()
        return [f for f in self.list_filter if f not in hidden and not (f is WarrantyFilter and "warranty_until" in hidden)]

    def get_inlines(self, request, obj):
        return [RelationInline] if obj is not None else []  # a relation needs a saved item of a known customer

    def get_form(self, request, obj=None, **kwargs):
        # The property fields change with the properties, so they are made per request.
        fields = {PROPERTY_PREFIX + p.key: property_field(p) for p in ItemField.own().exclude(mode=FieldMode.HIDDEN).prefetch_related("item_types")}
        kwargs["form"] = type("ItemPropertiesForm", (ItemForm,), fields)
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        names = [PROPERTY_PREFIX + key for key in ItemField.own().exclude(mode=FieldMode.HIDDEN).values_list("key", flat=True)]
        hidden = fields.hidden()

        def shown(*names):
            rows = []
            for name in names:
                if isinstance(name, tuple):
                    row = tuple(n for n in name if n not in hidden)
                    if row:
                        rows.append(row if len(row) > 1 else row[0])
                elif name not in hidden:
                    rows.append(name)
            return rows

        fieldsets = [
            (pgettext_lazy("cmdb", "Item"), {"classes": ["tab"], "fields": shown(
                "number", "customer", "item_type", "name", "status", ("manufacturer", "model"),
                ("serial_nr", "asset_tag"), "location", "contact", "description",
            )}),
            (_("Own fields"), {"classes": ["tab"], "fields": ["show_property_hint", *names]}),
            (_("Lifecycle"), {"classes": ["tab"], "fields": shown(
                "purchase_date", "warranty_until", "end_of_life", ("created_at", "updated_at"),
            )}),
        ]
        if not names:
            fieldsets.pop(1)
        if obj is not None:
            fieldsets.append((_("Diagram"), {"classes": ["tab"], "fields": ["show_diagram"]}))
            fieldsets.append((_("Impact"), {"classes": ["tab"], "fields": ["show_impact"]}))
            fieldsets.append((_("History"), {"classes": ["tab"], "fields": ["show_history"]}))
        return fieldsets

    @display(description="")
    def show_property_hint(self, obj):
        # Hidden by static/admin/cmdb-properties.js as soon as the chosen type has properties.
        return format_html('<span data-property-hint>{}</span>', gettext(
            "Choose an item type on the Item tab first; its fields appear here."))

    @display(description=_("How this item is connected"))
    def show_diagram(self, obj):
        drawing = diagram.for_item(obj)
        if drawing is None:
            return gettext("This item has no relations yet.")
        return render_to_string("admin/cmdb/_diagram.html", {"diagram": drawing})

    @display(description=_("Affected when this item fails"))
    def show_impact(self, obj):
        items = obj.affected_items()
        if not items:
            return gettext("Nothing else depends on this item.")
        rows = format_html_join("", '<li><a class="underline" href="{}">{}</a>{}</li>', (
            (reverse("admin:cmdb_configurationitem_change", args=[item.pk]), item,
             f" – {item.contact}" if item.contact_id else "")
            for item in items))
        return format_html('<ul class="list-disc ml-5">{}</ul>', rows)

    @display(description=_("History"))
    def show_history(self, obj):
        changes = obj.changes.select_related("user")[:200]
        if not changes:
            return gettext("Nothing yet.")
        rows = format_html_join("", "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>", (
            (timezone.localtime(c.changed_at).strftime("%Y-%m-%d %H:%M"), c.user.email if c.user else "–",
             c.get_source_display(), c.field, f"{c.old_value or '–'} → {c.new_value or '–'}")
            for c in changes))
        return format_html(
            '<div class="overflow-x-auto"><table class="pd-table text-sm"><thead><tr><th>{}</th><th>{}</th><th>{}</th>'
            "<th>{}</th><th>{}</th></tr></thead><tbody>{}</tbody></table></div>",
            gettext("When"), gettext("Who"), gettext("Source"), gettext("Field"), gettext("Change"), rows)

    def save_model(self, request, obj, form, change):
        before = None
        if change:
            before = history.snapshot(ConfigurationItem.objects.select_related("customer", "contact", "item_type").get(pk=obj.pk))
        super().save_model(request, obj, form, change)
        history.record(obj, before, request.user)

    def save_formset(self, request, form, formset, change):
        if formset.model is not Relation:
            return super().save_formset(request, form, formset, change)
        before = history.relation_texts(form.instance)
        super().save_formset(request, form, formset, change)
        history.record_relations(form.instance, before, request.user)

    @admin.action(description=_("Export selected items (Excel)"), permissions=["export"])
    def export_xlsx(self, request, queryset):
        return transfer_views.export_response(queryset, "xlsx")

    @admin.action(description=_("Export selected items (CSV)"), permissions=["export"])
    def export_csv(self, request, queryset):
        return transfer_views.export_response(queryset, "csv")

    def has_export_permission(self, request):
        return in_use() and request.user.has_perm("cmdb.export_configurationitem")

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("diagram/", view(self.diagram_view), name="cmdb_configurationitem_diagram"),
            path("import/", view(transfer_views.import_view), name="cmdb_configurationitem_import"),
            path("export/", view(transfer_views.ExportView(self)), name="cmdb_configurationitem_export"),
            path("example/", view(transfer_views.example_view), name="cmdb_configurationitem_example"),
        ] + super().get_urls()

    def diagram_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        customers = Customer.objects.filter(cmdb__enabled=True).order_by("name")
        customer = customers.filter(pk=request.GET["customer"]).first() if request.GET.get("customer", "").isdigit() else None
        context = {**self.admin_site.each_context(request), "opts": self.model._meta, "title": gettext("Relation diagram"),
                   "customers": customers, "customer": customer}
        if customer is not None:
            context["diagram"], context["loose"], context["more"] = diagram.for_customer(customer)
        return TemplateResponse(request, "admin/cmdb/diagram.html", context)

    def changelist_view(self, request, extra_context=None):
        if not in_use():
            messages.info(request, gettext("The CMDB is switched off. Switch it on here to use it."))
            return redirect("admin:cmdb_cmdbsettings_changelist")
        extra_context = {**(extra_context or {}),
                         "can_import": request.user.has_perm("cmdb.import_configurationitem"),
                         "can_export": self.has_export_permission(request)}
        return super().changelist_view(request, extra_context)


@admin.register(DiscoveredItem)
class DiscoveredItemAdmin(WhenEnabled, ModelAdmin):
    """What a source reported: it can be decided on, not edited."""

    list_display = ["show_name", "customer", "show_status", "show_item", "show_details", "last_seen"]
    list_filter = ["status", "customer"]
    search_fields = ["key", "customer__name", "customer__number"]
    list_select_related = ["customer", "item", "source"]
    actions = ["accept_selected", "ignore_selected"]
    fields = ["customer", "source", "key", "show_status", "show_item", "show_differences", "show_reported",
              ("first_seen", "last_seen")]
    readonly_fields = ["customer", "source", "key", "show_status", "show_item", "show_differences", "show_reported",
                       "first_seen", "last_seen"]
    STATUS_COLOURS = {"new": "info", "changed": "warning", "accepted": "success", "ignored": "danger"}

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(customer__cmdb__enabled=True)

    def changelist_view(self, request, extra_context=None):
        if not in_use():
            messages.info(request, gettext("The CMDB is switched off. Switch it on here to use it."))
            return redirect("admin:cmdb_cmdbsettings_changelist")
        return super().changelist_view(request, extra_context)

    @display(description=_("Name"), ordering="key")
    def show_name(self, obj):
        return str(obj)

    @display(description=_("Status"), ordering="status", label=STATUS_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description=pgettext_lazy("cmdb", "Item"))
    def show_item(self, obj):
        if obj.item_id is None:
            return "–"
        return format_html('<a class="underline" href="{}">{}</a>',
                           reverse("admin:cmdb_configurationitem_change", args=[obj.item_id]), obj.item)

    @display(description=_("Reported"))
    def show_details(self, obj):
        data = obj.data or {}
        parts = [data.get("manufacturer"), data.get("model"), data.get("serial_nr"), *(data.get("properties") or {}).values()]
        return " · ".join(str(part) for part in parts if part)

    @display(description=_("What accepting changes"))
    def show_differences(self, obj):
        rows = discovery.differences(obj)
        if not rows:
            return gettext("A new item is made.") if obj.item_id is None else gettext("Nothing: the item is the same.")
        return format_html_join("", "<div><strong>{}</strong>: {} → {}</div>", rows)

    @display(description=_("Reported"))
    def show_reported(self, obj):
        data = dict(obj.data or {})
        properties = data.pop("properties", None) or {}
        return format_html_join("", "<div><strong>{}</strong>: {}</div>", [*data.items(), *properties.items()])

    @admin.action(description=_("Accept selected"), permissions=["change"])
    def accept_selected(self, request, queryset):
        done = 0
        for found in queryset.select_related("source", "source__item_type", "customer"):
            if found.status != DiscoveredItem.Status.ACCEPTED:
                discovery.accept(found, request.user)
                done += 1
        messages.success(request, gettext("%(n)s accepted.") % {"n": done})

    @admin.action(description=_("Ignore selected"), permissions=["change"])
    def ignore_selected(self, request, queryset):
        done = queryset.update(status=DiscoveredItem.Status.IGNORED)
        messages.success(request, gettext("%(n)s ignored; they stay ignored when they are reported again.") % {"n": done})


@admin.register(DiscoverySource)
class DiscoverySourceAdmin(ObjectActionsMixin, ModelAdmin):
    list_display = ["name", "customer", "item_type", "auto_accept", "is_active", "last_report_at"]
    list_filter = ["is_active", "customer"]
    search_fields = ["name", "customer__name", "customer__number"]
    list_select_related = ["customer", "item_type"]
    autocomplete_fields = ["customer"]
    fields = ["customer", "name", "item_type", "auto_accept", "is_active", "last_report_at"]
    readonly_fields = ["last_report_at"]
    object_actions = [
        ObjectAction("new_key", _("Make a new key"), "key", handler="new_key",
                     confirm=_("Make a new key? The old key stops working right away.")),
    ]

    def _key_page(self, request, source, token):
        context = {**self.admin_site.each_context(request), "opts": self.model._meta, "source": source, "token": token,
                   "title": gettext("Key of %(name)s") % {"name": source.name}}
        return TemplateResponse(request, "admin/cmdb/discovery_key.html", context)

    def save_model(self, request, obj, form, change):
        if not change:
            self._token = obj.new_token()
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        return self._key_page(request, obj, self._token)

    def new_key(self, request, source):
        token = source.new_token()
        source.save(update_fields=["token_digest"])
        return self._key_page(request, source, token)

    def script_view(self, request, code):
        if not self.has_view_permission(request):
            raise PermissionDenied
        found = discovery.scripts().get(code)
        if found is None:
            raise PermissionDenied
        name, template, _description = found
        url = request.build_absolute_uri(reverse("cmdb_discovery_report"))
        response = HttpResponse(render_to_string(template, {"report_url": url}), content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    def get_urls(self):
        return [path("script/<str:code>/", self.admin_site.admin_view(self.script_view), name="cmdb_discoverysource_script"),
                *super().get_urls()]


def _uses_cmdb(customer):
    return in_use() and CmdbCustomer.objects.filter(customer=customer, enabled=True).exists()


def _overview_items(customer):
    return customer.configuration_items.select_related("item_type", "status").order_by("name")


def _overview_cells(item):
    return [item.number, item.name, str(item.item_type), str(item.status), item.serial_nr, item.location,
            item.warranty_until.isoformat() if item.warranty_until else "–"]


def _overview_block(customer):
    today = timezone.localdate()
    items = customer.configuration_items
    soon = today + datetime.timedelta(days=SOON_DAYS)
    open_found = DiscoveredItem.objects.filter(customer=customer, status__in=[DiscoveredItem.Status.NEW,
                                                                              DiscoveredItem.Status.CHANGED]).count()
    stats = [(gettext("Items"), items.count()),
             (gettext("In use"), items.filter(status__out_of_use=False).count()),
             (gettext("Relations"), Relation.objects.filter(source__customer=customer).count()),
             (gettext("Warranty expired"), items.filter(warranty_until__lt=today).count()),
             (gettext("Warranty ends within 90 days"), items.filter(warranty_until__gte=today, warranty_until__lte=soon).count()),
             (gettext("Discovered, to decide on"), open_found)]
    base = reverse("admin:cmdb_configurationitem_changelist")
    links = [(gettext("All items"), f"{base}?customer__id__exact={customer.pk}"),
             (gettext("Diagram"), reverse("admin:cmdb_configurationitem_diagram") + f"?customer={customer.pk}")]
    if open_found:
        links.append((gettext("Discovered items"), reverse("admin:cmdb_discovereditem_changelist") + f"?customer__id__exact={customer.pk}"))
    return {"stats": stats, "links": links}


overview.register("cmdb", _("CMDB"), "cmdb.configurationitem", _overview_items,
                  [_("Number"), _("Name"), _("Type"), _("Status"), _("Serial number"), _("Location"), _("Warranty until")],
                  _overview_cells, order=65, visible=_uses_cmdb, block=_overview_block)
