from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from .models import FaultAttachment, FaultReport, FaultSettings, RepairOption

STATUS_COLOURS = {"new": "warning", "in_progress": "info", "closed": "success"}


class AttachmentInline(TabularInline):
    model = FaultAttachment
    extra = 0
    tab = True
    fields = ["download", "size"]
    readonly_fields = ["download", "size"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @display(description=_("File"))
    def download(self, obj):
        return format_html('<a class="underline" href="{}">{}</a>', reverse("fault_attachment", args=[obj.pk]), obj.name)


@admin.register(FaultReport)
class FaultReportAdmin(ObjectActionsMixin, ModelAdmin):
    inlines = [AttachmentInline]
    list_display = ["number", "created_at", "show_status", "reseller_name", "device", "serial_nr", "show_cover"]
    list_display_links = ["number", "device"]
    list_filter = ["status", "repair_option", "created_at"]
    search_fields = ["number", "serial_nr", "device", "vendor", "reseller_name", "location_name", "location_contact",
                     "location_city", "reference", "licence__full_number", "customer__name"]
    date_hierarchy = "created_at"
    autocomplete_fields = ["customer", "licence"]
    readonly_fields = ["number", "created_at", "reported_by", "covered_until", "show_cover"]
    object_actions = [
        ObjectAction("in-progress", _("Take in progress"), "construction", handler="set_in_progress", show_if="is_new"),
        ObjectAction("close", _("Close"), "task_alt", handler="close", show_if="is_open"),
        ObjectAction("reopen", _("Reopen"), "replay", handler="reopen", show_if="is_closed"),
    ]
    fieldsets = [
        (_("Report"), {"classes": ["tab"], "fields": [
            ("number", "status"), ("created_at", "reported_by"), ("customer", "licence"), ("covered_until", "show_cover"),
            "internal_notes",
        ]}),
        (_("Device and fault"), {"classes": ["tab"], "fields": [
            ("vendor", "device"), "serial_nr", "operating_system", "description", "repair_option", "reference",
        ]}),
        (_("Reseller"), {"classes": ["tab"], "fields": [
            "reseller_name", "reseller_address", ("reseller_postal_code", "reseller_city"), ("reseller_phone", "reseller_email"),
        ]}),
        (_("Location"), {"classes": ["tab"], "fields": [
            "location_name", "location_contact", "location_address", ("location_postal_code", "location_city"),
            "location_country", ("location_phone", "location_email"),
        ]}),
    ]

    def has_add_permission(self, request):
        return False

    @display(description=_("Status"), ordering="status", label=STATUS_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description=_("Cover"), label={"yes": "success", "no": "danger"})
    def show_cover(self, obj):
        if obj.is_covered:
            return "yes", gettext("Covered until %(date)s") % {"date": obj.covered_until.strftime("%d-%m-%Y")}
        return "no", gettext("No cover found")

    def is_new(self, obj):
        return obj.status == FaultReport.Status.NEW

    def is_open(self, obj):
        return obj.status != FaultReport.Status.CLOSED

    def is_closed(self, obj):
        return obj.status == FaultReport.Status.CLOSED

    def _set(self, request, obj, status):
        obj.status = status
        obj.save(update_fields=["status"])
        messages.success(request, gettext("Status changed to “%(s)s”.") % {"s": obj.get_status_display()})

    def set_in_progress(self, request, obj):
        self._set(request, obj, FaultReport.Status.IN_PROGRESS)

    def close(self, request, obj):
        self._set(request, obj, FaultReport.Status.CLOSED)

    def reopen(self, request, obj):
        self._set(request, obj, FaultReport.Status.IN_PROGRESS)


@admin.register(RepairOption)
class RepairOptionAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "position", "is_active"]
    search_fields = ["name"]


@admin.register(FaultSettings)
class FaultSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fieldsets = [
        (_("Form"), {"classes": ["tab"], "fields": ["enabled", "intro", "office_hours_text", "thanks",
                                                    ("max_attachment_mb", "max_attachments")]}),
        (_("Emails"), {"classes": ["tab"], "fields": ["recipients", "cc", "confirmation_subject", "confirmation_body"]}),
    ]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:faults_faultsettings_change", args=[FaultSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
