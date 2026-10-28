from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminDecimalFieldWidget, UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from apps.dashboard.templatetags.humanize_nl import money

from . import transfer_views
from .models import Condition, DeliveryOption, Device, DevicePhoto, DeviceType, HardwareSettings, Specification

STATUS_COLOURS = {"draft": "info", "for_sale": "success", "reserved": "warning", "sold": "primary",
                  "written_off": "danger"}
SPEC_PREFIX = "spec_"


class SingletonAdmin(ModelAdmin, TabbedTranslationAdmin):
    def changelist_view(self, request, extra_context=None):
        return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
                                args=[self.model.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HardwareSettings)
class HardwareSettingsAdmin(SingletonAdmin):
    fieldsets = [
        (_("General"), {"classes": ["tab"], "fields": ["enabled", "notify_emails"]}),
        (_("Prices"), {"classes": ["tab"], "fields": ["vat_rate", "default_markup", "default_warranty_months"]}),
        (_("Texts"), {"classes": ["tab"], "fields": ["intro", "terms_text"]}),
    ]


@admin.register(DeviceType)
class DeviceTypeAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "show_devices", "is_active", "position"]
    list_editable = ["position"]

    @display(description=_("Devices"))
    def show_devices(self, obj):
        return obj.devices.count()


@admin.register(Specification)
class SpecificationAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "key", "kind", "unit", "show_types", "required", "in_list", "position"]
    list_editable = ["position"]
    list_filter = ["device_types", "kind"]
    filter_horizontal = ["device_types"]

    @display(description=_("Device types"))
    def show_types(self, obj):
        return ", ".join(str(t) for t in obj.device_types.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("device_types")


@admin.register(Condition)
class ConditionAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "position"]
    list_editable = ["position"]


@admin.register(DeliveryOption)
class DeliveryOptionAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "kind", "price", "is_active", "position"]
    list_editable = ["price", "is_active", "position"]


class PhotoInline(TabularInline):
    model = DevicePhoto
    extra = 0
    fields = ["image", "position"]


# --- devices -----------------------------------------------------------------------------------------------

def spec_field(spec):
    """A form field for one specification; its device types go along, so the page shows only those of the
    chosen type (static/admin/hardware-specs.js)."""
    types = ",".join(str(t.pk) for t in spec.device_types.all())
    attrs = {"data-spec-types": types}
    label = f"{spec.name} ({spec.unit})" if spec.unit else spec.name
    if spec.kind == Specification.Kind.NUMBER:
        return forms.DecimalField(label=label, required=False, widget=UnfoldAdminDecimalFieldWidget(attrs=attrs))
    if spec.kind == Specification.Kind.CHOICE:
        choices = [("", "—")] + [(o, o) for o in spec.options()]
        return forms.ChoiceField(label=label, required=False, choices=choices, widget=UnfoldAdminSelectWidget(attrs=attrs))
    if spec.kind == Specification.Kind.YES_NO:
        choices = [("", "—"), ("1", _("Yes")), ("0", _("No"))]
        return forms.ChoiceField(label=label, required=False, choices=choices, widget=UnfoldAdminSelectWidget(attrs=attrs))
    return forms.CharField(label=label, required=False, max_length=200, widget=UnfoldAdminTextInputWidget(attrs=attrs))


class DeviceForm(forms.ModelForm):
    class Meta:
        model = Device
        exclude = ["specs"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.specs = {s.key: s for s in Specification.objects.prefetch_related("device_types")}
        for key, spec in self.specs.items():
            name = SPEC_PREFIX + key
            if name in self.fields and self.instance.pk:
                value = (self.instance.specs or {}).get(key)
                if spec.kind == Specification.Kind.YES_NO and value is not None:
                    value = "1" if value else "0"
                self.initial[name] = value

    def _type_specs(self):
        device_type = self.cleaned_data.get("device_type")
        if device_type is None:
            return []
        return [s for s in self.specs.values() if any(t.pk == device_type.pk for t in s.device_types.all())]

    def clean(self):
        cleaned = super().clean()
        for spec in self._type_specs():
            name = SPEC_PREFIX + spec.key
            if spec.required and name in self.fields and cleaned.get(name) in (None, ""):
                self.add_error(name, _("Required for this device type."))
        return cleaned

    def save(self, commit=True):
        device = super().save(commit=False)
        specs = {}
        for spec in self._type_specs():  # only the properties of its type; the others are dropped
            value = self.cleaned_data.get(SPEC_PREFIX + spec.key)
            if value in (None, ""):
                continue
            if spec.kind == Specification.Kind.YES_NO:
                value = value == "1"
            elif spec.kind == Specification.Kind.NUMBER:
                value = int(value) if value == value.to_integral_value() else float(value)
            specs[spec.key] = value
        device.specs = specs
        if commit:
            device.save()
            self.save_m2m()
        return device


@admin.register(Device)
class DeviceAdmin(ModelAdmin):
    form = DeviceForm
    inlines = [PhotoInline]
    change_list_template = "admin/hardware/device/change_list.html"
    list_display = ["number", "show_type", "brand", "model", "serial_nr", "condition", "show_status",
                    "show_price", "show_price_incl"]
    list_display_links = ["number", "model"]
    list_filter = ["status", "device_type", "condition", "brand"]
    search_fields = ["number", "serial_nr", "model", "brand__name", "supplier"]
    list_select_related = ["device_type", "brand", "condition"]
    readonly_fields = ["number", "sold_at", "created_at", "updated_at", "show_price_summary"]
    autocomplete_fields = ["customer"]
    actions = ["set_for_sale", "set_written_off", "export_xlsx", "export_csv"]

    class Media:
        js = ["admin/hardware-specs.js"]

    def get_form(self, request, obj=None, **kwargs):
        # The specification fields change with the specifications, so they are made per request.
        fields = {SPEC_PREFIX + s.key: spec_field(s) for s in Specification.objects.prefetch_related("device_types")}
        kwargs["form"] = type("DeviceSpecForm", (DeviceForm,), fields)
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        spec_names = [SPEC_PREFIX + key for key in Specification.objects.values_list("key", flat=True)]
        fieldsets = [
            (_("Device"), {"classes": ["tab"], "fields": [
                "number", "device_type", ("brand", "model"), "serial_nr", ("condition", "status"), "description",
            ]}),
            (_("Specifications"), {"classes": ["tab"], "fields": spec_names or ["device_type"]}),
            (_("Prices"), {"classes": ["tab"], "fields": [
                ("purchase_date", "supplier"), ("purchase_price", "sale_price"), "show_price_summary", "warranty_months",
            ]}),
            (_("Sale"), {"classes": ["tab"], "fields": ["customer", "sold_at", "internal_notes", ("created_at", "updated_at")]}),
        ]
        if not spec_names:
            fieldsets.pop(1)
        return fieldsets

    @display(description=_("Device type"), ordering="device_type__name")
    def show_type(self, obj):
        return obj.device_type

    @display(description=_("Status"), ordering="status", label=STATUS_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description=_("Price excl. VAT"))
    def show_price(self, obj):
        return money(obj.price)

    @display(description=_("Price incl. VAT"))
    def show_price_incl(self, obj):
        return money(obj.price_incl_vat())

    @display(description=_("Price for visitors"))
    def show_price_summary(self, obj):
        if obj is None or obj.price is None:
            return gettext("No selling price and no purchase price yet.")
        source = gettext("selling price") if obj.sale_price is not None else gettext("purchase price plus standard markup")
        settings = HardwareSettings.load()
        return format_html("€ {} {} · € {} {} ({}% {}) — {}", money(obj.price), gettext("excl. VAT"),
                           money(obj.price_incl_vat(settings.vat_rate)), gettext("incl. VAT"),
                           money(settings.vat_rate), gettext("VAT"), source)

    def save_model(self, request, obj, form, change):
        if obj.status == Device.Status.SOLD and obj.sold_at is None:
            from django.utils import timezone

            obj.sold_at = timezone.now()
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Put selected devices up for sale"), permissions=["change"])
    def set_for_sale(self, request, queryset):
        n = queryset.filter(status__in=[Device.Status.DRAFT, Device.Status.WRITTEN_OFF]).update(status=Device.Status.FOR_SALE)
        messages.success(request, gettext("%(n)s device(s) put up for sale.") % {"n": n})

    @admin.action(description=_("Write off selected devices"), permissions=["change"])
    def set_written_off(self, request, queryset):
        n = queryset.exclude(status=Device.Status.SOLD).update(status=Device.Status.WRITTEN_OFF)
        messages.success(request, gettext("%(n)s device(s) written off.") % {"n": n})

    @admin.action(description=_("Export selected devices (Excel)"), permissions=["view"])
    def export_xlsx(self, request, queryset):
        return transfer_views.export_response(queryset, "xlsx")

    @admin.action(description=_("Export selected devices (CSV)"), permissions=["view"])
    def export_csv(self, request, queryset):
        return transfer_views.export_response(queryset, "csv")

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("import/", view(transfer_views.import_view), name="hardware_device_import"),
            path("export/", view(transfer_views.ExportView(self)), name="hardware_device_export"),
            path("example/", view(transfer_views.example_view), name="hardware_device_example"),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "can_import": self.has_add_permission(request)
                         and self.has_change_permission(request)}
        return super().changelist_view(request, extra_context)
