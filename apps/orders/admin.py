from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html_join
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import Order, OrderLine, OrderSettings


class LineInline(TabularInline):
    model = OrderLine
    extra = 0
    tab = True
    fields = ["description", "quantity", "unit_price", "line_total", "reference", "extends", "show_licences"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @display(description=_("Licences"))
    def show_licences(self, obj):
        return format_html_join(", ", '<a class="underline" href="{}">{}</a>', (
            (reverse("admin:licences_licence_change", args=[lic.pk]), lic.full_number) for lic in obj.licences.all()
        )) or "—"


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    inlines = [LineInline]
    list_display = ["number", "created_at", "customer", "reference", "total", "send_boxes", "boxes_sent"]
    list_display_links = ["number", "customer"]
    list_filter = ["created_at", "send_boxes", "boxes_sent"]
    search_fields = ["number", "reference", "customer__name", "customer__number", "lines__licences__full_number"]
    date_hierarchy = "created_at"
    readonly_fields = ["number", "customer", "created_by", "created_at", "gross", "discount_pct", "discount", "net",
                       "vat_rate", "vat", "total"]
    fieldsets = [
        (_("Order"), {"classes": ["tab"], "fields": [
            ("number", "created_at"), ("customer", "created_by"), "reference",
            ("gross", "discount_pct", "discount"), ("net", "vat_rate", "vat"), "total",
        ]}),
        (_("Physical packs"), {"classes": ["tab"], "fields": [
            "send_boxes", "boxes_sent", "delivery_name", "delivery_contact", "delivery_address",
            ("delivery_postal_code", "delivery_city"),
        ]}),
    ]

    def has_add_permission(self, request):
        return False


@admin.register(OrderSettings)
class OrderSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fieldsets = [
        (_("Ordering"), {"classes": ["tab"], "fields": ["enabled", "vat_rate", "allow_boxes", "extend_window_days", "notify_emails"]}),
        (_("Texts"), {"classes": ["tab"], "fields": ["intro", "terms_text", "confirmation_text"]}),
    ]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:orders_ordersettings_change", args=[OrderSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
