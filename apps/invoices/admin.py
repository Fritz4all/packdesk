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

from . import services
from .models import Invoice, InvoiceEmail, InvoiceLine, InvoiceSettings


class LineInline(TabularInline):
    model = InvoiceLine
    extra = 0
    tab = True
    fields = ["code", "description", "quantity", "unit_price", "amount"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class EmailInline(TabularInline):
    model = InvoiceEmail
    extra = 0
    tab = True
    fields = ["sent_at", "sent_to", "sent_by"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(ObjectActionsMixin, ModelAdmin):
    inlines = [LineInline, EmailInline]
    list_display = ["number", "issued_on", "customer_name", "customer_number", "total", "show_source", "paid_on", "show_pdf"]
    list_display_links = ["number", "customer_name"]
    list_filter = ["is_archive", "issued_on", "paid_on"]
    search_fields = ["number", "customer_name", "customer_number", "reference", "order__number", "email"]
    date_hierarchy = "issued_on"
    autocomplete_fields = ["customer"]
    readonly_fields = ["number", "order", "issued_on", "due_on", "reference", "customer_name", "customer_number",
                       "customer_vat", "address_attention", "address_line1", "address_line2", "address_postal_code",
                       "address_city", "address_country", "gross", "discount_pct", "discount", "net", "vat_rate", "vat",
                       "total", "is_archive", "archive_file", "show_pdf"]
    object_actions = [
        ObjectAction("resend", _("Send again to customer"), "forward_to_inbox", handler="resend", show_if="can_send"),
    ]
    fieldsets = [
        (_("Invoice"), {"classes": ["tab"], "fields": [
            ("number", "issued_on", "due_on"), "show_pdf", ("customer", "order"), "reference", "email", "paid_on",
        ]}),
        (_("Amounts"), {"classes": ["tab"], "fields": [
            ("gross", "discount_pct", "discount"), ("net", "vat_rate", "vat"), "total",
        ]}),
        (_("Customer details on invoice"), {"classes": ["tab"], "fields": [
            "customer_name", "customer_number", "customer_vat", "address_attention", "address_line1", "address_line2",
            ("address_postal_code", "address_city"), "address_country",
        ]}),
        (_("Archive"), {"classes": ["tab"], "fields": ["is_archive", "archive_file"]}),
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # invoices are never deleted

    @display(description=_("Source"), label={"archive": "info", "packdesk": "success"})
    def show_source(self, obj):
        return ("archive", gettext("Old archive")) if obj.is_archive else ("packdesk", "PackDesk")

    @display(description=_("PDF"))
    def show_pdf(self, obj):
        if not obj.pk or not obj.has_pdf():
            return "—"
        url = reverse("invoice_pdf", args=[obj.pk])
        return format_html('<a class="underline" href="{}" target="_blank">{}</a> · <a class="underline" href="{}?download=1">{}</a>',
                           url, gettext("View"), url, gettext("Download"))

    def can_send(self, obj):
        return obj.has_pdf() and bool(obj.email or (obj.customer and obj.customer.email))

    def resend(self, request, invoice):
        to = invoice.email or invoice.customer.email
        services.send(invoice, to, by=request.user)
        messages.success(request, gettext("Invoice %(number)s has been sent to %(email)s.") % {"number": invoice.number, "email": to})


@admin.register(InvoiceSettings)
class InvoiceSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fieldsets = [
        (_("Invoices"), {"classes": ["tab"], "fields": ["auto_on_order", "send_on_create", "payment_term_days"]}),
        (_("Texts"), {"classes": ["tab"], "fields": ["payment_text", "notice_text", "footer_text", "email_subject", "email_body"]}),
        (_("Layout"), {"classes": ["tab"], "fields": ["custom_template"]}),
    ]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:invoices_invoicesettings_change", args=[InvoiceSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
