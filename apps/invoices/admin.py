from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from . import design as invoice_design
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
        (_("Layout"), {"classes": ["tab"], "fields": ["logo", "custom_template"]}),
    ]

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("design/", view(self.design_view), name="invoices_invoicesettings_design"),
            path("design/preview/", view(self.design_preview), name="invoices_invoicesettings_design_preview"),
            path("design/pdf/", view(self.design_pdf), name="invoices_invoicesettings_design_pdf"),
        ] + super().get_urls()

    # --- the design page: every part of the invoice on/off with its own wording, with a live preview --------

    def _language(self, request, site):
        codes = [code for code, _name in settings.LANGUAGES]
        lang = request.POST.get("preview_language") or request.GET.get("lang") or site.language
        return lang if lang in codes else site.language

    def design_view(self, request):
        from apps.siteconfig.models import SiteSettings

        if not self.has_view_permission(request):
            raise PermissionDenied
        rules, site = InvoiceSettings.load(), SiteSettings.load()
        if request.method == "POST":
            if not self.has_change_permission(request):
                raise PermissionDenied
            rules.design = {} if request.POST.get("reset") else invoice_design.from_form(request.POST, site)
            rules.save(update_fields=["design"])
            messages.success(request, gettext("The invoice design has been reset to the standard.") if request.POST.get("reset")
                             else gettext("The invoice design has been saved."))
            return redirect(f"{reverse('admin:invoices_invoicesettings_design')}?lang={self._language(request, site)}")
        style = invoice_design.style(rules.design, site)
        low, high, _standard = invoice_design.LOGO_HEIGHT
        return TemplateResponse(request, "admin/invoices/invoicesettings/design.html", {
            **self.admin_site.each_context(request),
            "title": gettext("Invoice design"), "opts": self.model._meta,
            "groups": invoice_design.editor_rows(rules.design, site), "style": style,
            "logo_min": low, "logo_max": high, "languages": settings.LANGUAGES,
            "language": self._language(request, site), "invoice_language": site.language,
            "can_change": self.has_change_permission(request),
            "preview_html": services.render_sample(rules.design, self._language(request, site)),
            "settings_url": reverse("admin:invoices_invoicesettings_change", args=[rules.pk]),
        })

    def _posted_design(self, request):
        from apps.siteconfig.models import SiteSettings

        if request.method != "POST" or not self.has_view_permission(request):
            raise PermissionDenied
        site = SiteSettings.load()
        return invoice_design.from_form(request.POST, site), self._language(request, site)

    def design_preview(self, request):
        design, lang = self._posted_design(request)
        return HttpResponse(services.render_sample(design, lang))

    def design_pdf(self, request):
        design, lang = self._posted_design(request)
        response = HttpResponse(services.render_sample_pdf(design, lang), content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="invoice-example.pdf"'
        return response

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:invoices_invoicesettings_change", args=[InvoiceSettings.load().pk]))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        from apps.siteconfig.models import SiteSettings

        rules = InvoiceSettings.load()
        if not SiteSettings.load().iban and any("{iban}" in (getattr(rules, f"payment_text_{code}", "") or "")
                                                for code, _name in settings.LANGUAGES):
            messages.warning(request, gettext("The payment text mentions the IBAN, but no IBAN is filled in. Fill it in "
                                              "under Settings → Company details, or change the payment text."))
        extra_context = {**(extra_context or {}), "design_url": reverse("admin:invoices_invoicesettings_design")}
        return super().change_view(request, object_id, form_url, extra_context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
