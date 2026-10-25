from django import forms
from django.contrib import admin, messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminIntegerFieldWidget

from apps.core.column_filters import ValueListFilter

from .models import (
    Category,
    HardwareClass,
    HardwareSystem,
    Licence,
    LicenceOption,
    LicenceSettings,
    OptionType,
    SupportPack,
    SupportPeriod,
    SupportService,
    Vendor,
)

STATUS_COLOURS = {"unregistered": "warning", "registered": "success", "ended": "info"}


# --- Catalogue -------------------------------------------------------------------

@admin.register(Category)
class CategoryAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "end_date_from", "contact_to_register", "position"]
    search_fields = ["name"]
    filter_horizontal = ["option_types"]


@admin.register(HardwareClass)
class HardwareClassAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "position"]
    search_fields = ["name"]


class SystemInline(TabularInline):
    model = HardwareSystem
    extra = 0
    tab = True
    fields = ["hardware_class", "name", "warranty_years", "visible"]


@admin.register(Vendor)
class VendorAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "is_real_vendor", "at_top"]
    search_fields = ["name"]
    inlines = [SystemInline]


@admin.register(HardwareSystem)
class HardwareSystemAdmin(ModelAdmin):
    list_display = ["name", "vendor", "hardware_class", "warranty_years", "visible"]
    list_filter = ["vendor", "hardware_class", "visible"]
    search_fields = ["name", "vendor__name"]


@admin.register(OptionType)
class OptionTypeAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "internal", "is_monitor"]
    search_fields = ["name"]


@admin.register(SupportPeriod)
class SupportPeriodAdmin(ModelAdmin):
    list_display = ["__str__", "years", "post_warranty"]
    search_fields = ["years"]


@admin.register(SupportService)
class SupportServiceAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["abbreviation", "name", "response", "office_hours"]
    search_fields = ["abbreviation", "name", "response"]


@admin.register(SupportPack)
class SupportPackAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["__str__", "code", "category", "hardware_class", "period", "price", "cost_price", "enabled"]
    list_filter = ["enabled", "category", "period", "service"]
    search_fields = ["code", "description"]
    fieldsets = [
        (None, {"fields": ["code", "description", ("category", "hardware_class"), ("service", "period"), ("price", "cost_price"), "enabled"]}),
        (_("Registration"), {"fields": [
            "registration_required", "requires_monitor", ("max_internal_options", "max_external_options"), "remark",
        ]}),
    ]


# --- Licences ---------------------------------------------------------------------

class OptionInline(TabularInline):
    model = LicenceOption
    extra = 0
    tab = True
    fields = ["option_type", "vendor", "description", "product_nr", "serial_nr"]


class LicenceAddForm(forms.ModelForm):
    quantity = forms.IntegerField(
        label=_("Number of licences"), min_value=1, max_value=500, initial=1, widget=UnfoldAdminIntegerFieldWidget,
        help_text=_("Each gets its own licence number."),
    )

    class Meta:
        model = Licence
        fields = ["pack", "customer", "order_reference"]



class LicenceStatusFilter(ValueListFilter):
    title = _("Status")
    parameter_name = "status"
    options = [
        ("unregistered", _("Not registered"), Q(registered_on__isnull=True)),
        ("registered", _("Registered"), lambda qs: qs.filter(registered_on__isnull=False).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=timezone.localdate()))),
        ("ended", _("Ended"), lambda qs: qs.filter(registered_on__isnull=False, end_date__lt=timezone.localdate())),
    ]


@admin.register(Licence)
class LicenceAdmin(ModelAdmin):
    inlines = [OptionInline]
    list_display = ["full_number", "customer", "pack", "show_status", "serial_nr", "end_date"]
    column_filters = {"show_status": LicenceStatusFilter}
    list_filter = ["pack__category", "pack__period", "registered_on", "end_date"]
    search_fields = [
        "full_number", "serial_nr", "product_nr", "description", "customer__name", "customer__number",
        "end_customer_reference", "end_customer_email", "order_reference", "reseller_name", "system__name",
        "options__serial_nr",
    ]
    autocomplete_fields = ["customer", "prolongation_of"]
    readonly_fields = ["full_number", "number", "suffix", "registered_on", "created_at"]
    date_hierarchy = "end_date"
    fieldsets = [
        (_("Licence"), {"classes": ["tab"], "fields": [
            "full_number", ("number", "suffix", "sequence"), "pack", "customer", "order_reference", "prolongation_of", "created_at",
        ]}),
        (_("Device"), {"classes": ["tab"], "fields": [
            "registered_on", ("start_date", "end_date"), ("vendor", "system"), "description", ("product_nr", "serial_nr"), "purchase_date",
        ]}),
        (_("End customer and reseller"), {"classes": ["tab"], "fields": [
            ("end_customer_email", "end_customer_reference"), "memo", "reseller_name", "reseller_address",
            ("reseller_postal_code", "reseller_city"), "reseller_phone",
        ]}),
    ]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = LicenceAddForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [(None, {"fields": ["pack", "customer", "order_reference", "quantity"]})]
        return super().get_fieldsets(request, obj)

    def get_inlines(self, request, obj):
        return self.inlines if obj else []

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        created = Licence.create_for(
            form.cleaned_data["pack"], form.cleaned_data["customer"], form.cleaned_data["quantity"],
            form.cleaned_data.get("order_reference", ""),
        )
        obj.pk = created[0].pk
        self._created = created

    def save_related(self, request, form, formsets, change):
        if change:
            super().save_related(request, form, formsets, change)

    def response_add(self, request, obj, post_url_continue=None):
        created = getattr(self, "_created", [obj])
        messages.success(request, gettext("%(n)s licence(s) created: %(list)s") % {
            "n": len(created), "list": ", ".join(lic.full_number for lic in Licence.objects.filter(pk__in=[c.pk for c in created]))
        })
        return redirect(reverse("admin:licences_licence_changelist"))

    @display(description=_("Status"), label=STATUS_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()


@admin.register(LicenceSettings)
class LicenceSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fieldsets = [
        (_("Rules"), {"classes": ["tab"], "fields": [
            "register_after_days", "register_ahead_days", "register_ahead_days_post_warranty",
            "suffix_length", "forbidden_suffixes", "notify_emails",
        ]}),
        (_("Texts"), {"classes": ["tab"], "fields": ["wizard_intro", "wizard_done", "contact_text"]}),
    ]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:licences_licencesettings_change", args=[LicenceSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
