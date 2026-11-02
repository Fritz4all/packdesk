import datetime

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminDecimalFieldWidget, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from apps.customers.admin import CustomerAdmin

from . import history, transfer_views
from .models import CmdbCustomer, CmdbSettings, ConfigurationItem, ItemProperty, ItemType, Relation

STATUS_COLOURS = {"planned": "info", "in_use": "success", "in_repair": "warning", "retired": "danger"}
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
class CmdbSettingsAdmin(ModelAdmin):
    fields = ["enabled"]

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


@admin.register(ItemProperty)
class ItemPropertyAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "key", "kind", "show_types", "required", "position"]
    list_editable = ["position"]
    list_filter = ["item_types", "kind"]
    filter_horizontal = ["item_types"]

    @display(description=_("Item types"))
    def show_types(self, obj):
        return ", ".join(str(t) for t in obj.item_types.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("item_types")


class CustomerSwitchInline(WhenEnabled, StackedInline):
    """The switches on the customer form. Added here, so the customer module stays unaware of the CMDB."""

    model = CmdbCustomer
    extra = 1
    max_num = 1
    can_delete = False
    tab = True
    fields = ["enabled", "portal_access", "show_items"]
    readonly_fields = ["show_items"]

    @display(description=_("Items"))
    def show_items(self, obj):
        if not obj.pk:
            return "–"
        url = reverse("admin:cmdb_configurationitem_changelist")
        return format_html('<a class="underline" href="{}?customer__id__exact={}">{}</a>', url, obj.customer_id,
                           obj.customer.configuration_items.count())


CustomerAdmin.inlines = [*CustomerAdmin.inlines, CustomerSwitchInline]


class RelationInline(WhenEnabled, TabularInline):
    model = Relation
    fk_name = "source"
    extra = 0
    tab = True
    fields = ["kind", "target"]
    autocomplete_fields = ["target"]


def property_field(prop):
    """A form field for one property; its item types go along, so the page shows only those of the chosen type
    (static/admin/cmdb-properties.js)."""
    attrs = {"data-property-types": ",".join(str(t.pk) for t in prop.item_types.all())}
    if prop.kind == ItemProperty.Kind.NUMBER:
        return forms.DecimalField(label=prop.name, required=False, widget=UnfoldAdminDecimalFieldWidget(attrs=attrs))
    if prop.kind == ItemProperty.Kind.CHOICE:
        choices = [("", "—")] + [(o, o) for o in prop.options()]
        return forms.ChoiceField(label=prop.name, required=False, choices=choices, widget=UnfoldAdminSelectWidget(attrs=attrs))
    if prop.kind == ItemProperty.Kind.YES_NO:
        choices = [("", "—"), ("1", _("Yes")), ("0", _("No"))]
        return forms.ChoiceField(label=prop.name, required=False, choices=choices, widget=UnfoldAdminSelectWidget(attrs=attrs))
    return forms.CharField(label=prop.name, required=False, max_length=200, widget=UnfoldAdminTextInputWidget(attrs=attrs))


class ItemForm(forms.ModelForm):
    class Meta:
        model = ConfigurationItem
        exclude = ["properties"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.item_properties = list(ItemProperty.objects.prefetch_related("item_types"))
        for prop in self.item_properties:
            name = PROPERTY_PREFIX + prop.key
            if name in self.fields and self.instance.pk:
                value = (self.instance.properties or {}).get(prop.key)
                if prop.kind == ItemProperty.Kind.YES_NO and value is not None:
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
            if prop.required and name in self.fields and cleaned.get(name) in (None, ""):
                self.add_error(name, _("Required for this item type."))
        return cleaned

    def save(self, commit=True):
        item = super().save(commit=False)
        values = {}
        for prop in self._type_properties():  # only the properties of its type; the others are dropped
            value = self.cleaned_data.get(PROPERTY_PREFIX + prop.key)
            if value in (None, ""):
                continue
            if prop.kind == ItemProperty.Kind.YES_NO:
                value = value == "1"
            elif prop.kind == ItemProperty.Kind.NUMBER:
                value = int(value) if value == value.to_integral_value() else float(value)
            values[prop.key] = value
        item.properties = values
        if commit:
            item.save()
            self.save_m2m()
        return item


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
    list_display = ["number", "name", "customer", "item_type", "show_status", "serial_nr", "location", "warranty_until"]
    list_display_links = ["number", "name"]
    list_filter = ["status", "item_type", WarrantyFilter, "customer"]
    search_fields = ["number", "name", "serial_nr", "asset_tag", "manufacturer", "model", "location",
                     "customer__name", "customer__number"]
    list_select_related = ["customer", "item_type"]
    readonly_fields = ["number", "created_at", "updated_at", "show_impact", "show_history", "show_property_hint"]
    autocomplete_fields = ["customer", "contact"]
    actions = ["export_xlsx", "export_csv"]

    class Media:
        js = ["admin/cmdb-properties.js"]

    def get_queryset(self, request):
        # Items of a customer that no longer uses the CMDB are hidden, and kept.
        return super().get_queryset(request).filter(customer__cmdb__enabled=True)

    def get_inlines(self, request, obj):
        return [RelationInline] if obj is not None else []  # a relation needs a saved item of a known customer

    def get_form(self, request, obj=None, **kwargs):
        # The property fields change with the properties, so they are made per request.
        fields = {PROPERTY_PREFIX + p.key: property_field(p) for p in ItemProperty.objects.prefetch_related("item_types")}
        kwargs["form"] = type("ItemPropertiesForm", (ItemForm,), fields)
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        names = [PROPERTY_PREFIX + key for key in ItemProperty.objects.values_list("key", flat=True)]
        fieldsets = [
            (_("Item"), {"classes": ["tab"], "fields": [
                "number", "customer", "item_type", "name", "status", ("manufacturer", "model"),
                ("serial_nr", "asset_tag"), "location", "contact", "description",
            ]}),
            (_("Properties"), {"classes": ["tab"], "fields": ["show_property_hint", *names]}),
            (_("Lifecycle"), {"classes": ["tab"], "fields": [
                "purchase_date", "warranty_until", "end_of_life", ("created_at", "updated_at"),
            ]}),
        ]
        if not names:
            fieldsets.pop(1)
        if obj is not None:
            fieldsets.append((_("Impact"), {"classes": ["tab"], "fields": ["show_impact"]}))
            fieldsets.append((_("History"), {"classes": ["tab"], "fields": ["show_history"]}))
        return fieldsets

    @display(description=_("Status"), ordering="status", label=STATUS_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="")
    def show_property_hint(self, obj):
        # Hidden by static/admin/cmdb-properties.js as soon as the chosen type has properties.
        return format_html('<span data-property-hint>{}</span>', gettext(
            "Choose an item type on the Item tab first; its properties appear here."))

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
            path("import/", view(transfer_views.import_view), name="cmdb_configurationitem_import"),
            path("export/", view(transfer_views.ExportView(self)), name="cmdb_configurationitem_export"),
            path("example/", view(transfer_views.example_view), name="cmdb_configurationitem_example"),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        if not in_use():
            messages.info(request, gettext("The CMDB is switched off. Switch it on here to use it."))
            return redirect("admin:cmdb_cmdbsettings_changelist")
        extra_context = {**(extra_context or {}),
                         "can_import": request.user.has_perm("cmdb.import_configurationitem"),
                         "can_export": self.has_export_permission(request)}
        return super().changelist_view(request, extra_context)
