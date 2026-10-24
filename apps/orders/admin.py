from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

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
class OrderAdmin(ObjectActionsMixin, ModelAdmin):
    inlines = [LineInline]
    list_display = ["number", "created_at", "customer", "reference", "total", "send_boxes", "boxes_sent"]
    list_display_links = ["number", "customer"]
    list_filter = ["created_at", "send_boxes", "boxes_sent"]
    search_fields = ["number", "reference", "customer__name", "customer__number", "lines__licences__full_number"]
    date_hierarchy = "created_at"
    readonly_fields = ["number", "customer", "created_by", "created_at", "gross", "discount_pct", "discount", "net",
                       "vat_rate", "vat", "total", "show_invoice"]
    object_actions = [
        ObjectAction("invoice", _("Make invoice"), "receipt_long", handler="make_invoice", show_if="has_no_invoice"),
    ]
    fieldsets = [
        (_("Order"), {"classes": ["tab"], "fields": [
            ("number", "created_at"), ("customer", "created_by"), "reference", "show_invoice",
            ("gross", "discount_pct", "discount"), ("net", "vat_rate", "vat"), "total",
        ]}),
        (_("Physical packs"), {"classes": ["tab"], "fields": [
            "send_boxes", "boxes_sent", "delivery_name", "delivery_contact", "delivery_address",
            ("delivery_postal_code", "delivery_city"),
        ]}),
    ]

    def has_add_permission(self, request):
        return False

    @display(description=_("Invoice"))
    def show_invoice(self, obj):
        invoice = getattr(obj, "invoice", None)
        if invoice is None:
            return "—"
        return format_html('<a class="underline" href="{}">{}</a>', reverse("admin:invoices_invoice_change", args=[invoice.pk]),
                           invoice.number)

    def has_no_invoice(self, obj):
        return getattr(obj, "invoice", None) is None

    def make_invoice(self, request, order):
        from apps.invoices.services import InvoiceNumberError, create_for_order

        try:
            invoice = create_for_order(order)
        except InvoiceNumberError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, gettext("Invoice %(number)s made.") % {"number": invoice.number})


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
