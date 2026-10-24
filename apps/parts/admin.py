from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminTextareaWidget

from apps.core.object_actions import ObjectAction, ObjectActionsMixin
from apps.dashboard.templatetags.humanize_nl import money

from . import services
from .models import (DeliveryTime, MarkupTier, PartOrder, PartOrderLine, PartRequest, PartsSettings, PaymentMethod,
                     Remark, RequestLine, selling_price)

REQUEST_COLOURS = {"to_handle": "warning", "answered": "success"}
ORDER_COLOURS = {"payment": "info", "approval": "warning", "deliver": "primary", "done": "success", "cancelled": "danger"}


class RequestLineForm(forms.ModelForm):
    new_remark = forms.CharField(
        label=_("New remark for the customer"), required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
        help_text=_("Shown to the customer with this part."),
    )

    class Meta:
        model = RequestLine
        fields = "__all__"


class RequestLineInline(StackedInline):
    model = RequestLine
    form = RequestLineForm
    extra = 0
    tab = True
    fields = [
        ("article_number", "vendor", "quantity"), "description", ("machine_model", "machine_serial"), "info",
        "status", ("price_new", "time_new"), ("price_pack", "time_pack"), ("price_refurbished", "time_refurbished"),
        "show_selling", "show_remarks", "new_remark", "show_changes",
    ]
    readonly_fields = ["show_selling", "show_remarks", "show_changes"]

    @display(description=_("Selling price (before the customer's discount)"))
    def show_selling(self, obj):
        if not obj.pk:
            return "–"
        parts = [f"{label}: € {money(selling_price(obj.purchase_price(p)))}"
                 for p, label in (("new", gettext("New")), ("pack", gettext("Pack")), ("refurbished", gettext("Refurbished")))
                 if obj.purchase_price(p) is not None]
        return " · ".join(parts) or "–"

    @display(description=_("Remarks"))
    def show_remarks(self, obj):
        if not obj.pk:
            return "–"
        return format_html_join("", "<div><small>{} · {}</small><br>{}</div>", (
            (f"{r.created_at:%d-%m-%Y %H:%M}", gettext("customer") if r.from_customer else (r.author or ""), r.text)
            for r in obj.remarks.select_related("author"))) or "–"

    @display(description=_("History"))
    def show_changes(self, obj):
        if not obj.pk:
            return "–"
        return format_html_join("", "<div><small>{} · {} · {}</small></div>", (
            (f"{c.changed_at:%d-%m-%Y %H:%M}", c.user or "", c.get_status_display())
            for c in obj.changes.select_related("user")[:10])) or "–"


@admin.register(PartRequest)
class PartRequestAdmin(ObjectActionsMixin, ModelAdmin):
    inlines = [RequestLineInline]
    list_display = ["number", "created_at", "customer", "reference", "urgent", "show_status", "valid_until"]
    list_display_links = ["number", "customer"]
    list_filter = ["status", "urgent", "created_at"]
    search_fields = ["number", "reference", "customer__name", "customer__number", "lines__article_number"]
    date_hierarchy = "created_at"
    autocomplete_fields = ["customer"]
    readonly_fields = ["number", "created_by", "created_at", "status", "show_orders"]
    object_actions = [
        ObjectAction("email", _("Email the customer that the request is answered"), "mail", handler="email_customer",
                     show_if="is_answered"),
    ]
    fieldsets = [
        (_("Request"), {"classes": ["tab"], "fields": [
            ("number", "status"), ("customer", "created_by"), "reference", ("created_at", "valid_until"), "show_orders",
        ]}),
        (_("Urgent"), {"classes": ["tab"], "fields": [
            "urgent", ("urgent_possible", "urgent_costs"), ("delivery_name", "delivery_contact"), "delivery_address",
            ("delivery_postal_code", "delivery_city"), ("delivery_country", "delivery_phone"),
        ]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("customer")

    def has_add_permission(self, request):
        return False

    @display(description=_("Status"), ordering="status", label=REQUEST_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description=_("Orders"))
    def show_orders(self, obj):
        return format_html_join(", ", '<a class="underline" href="{}">{}</a>', (
            (reverse("admin:parts_partorder_change", args=[o.pk]), o.number) for o in obj.orders.all())) or "–"

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is RequestLine:
            for line_form in formset.forms:
                text = line_form.cleaned_data.get("new_remark", "").strip() if hasattr(line_form, "cleaned_data") else ""
                if text and line_form.instance.pk:
                    Remark.objects.create(line=line_form.instance, author=request.user, text=text)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if services.answer(form.instance, request.user):
            messages.success(request, gettext("Everything is answered; the customer has been emailed."))

    def is_answered(self, obj):
        return obj.status == PartRequest.Status.ANSWERED

    def email_customer(self, request, part_request):
        from .emails import request_answered

        request_answered(part_request)
        messages.success(request, gettext("The customer has been emailed."))


class OrderLineInline(TabularInline):
    model = PartOrderLine
    extra = 0
    tab = True
    fields = ["request_line", "packing", "quantity", "purchase_price", "unit_price", "show_total", "show_delivered",
              "show_corrected"]
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @display(description=_("Amount"))
    def show_total(self, obj):
        return f"€ {money(obj.line_total)}"

    @display(description=_("Delivered"))
    def show_delivered(self, obj):
        return format_html_join("", "<div>{} · {}</div>", ((d.quantity, f"{d.created_at:%d-%m-%Y}") for d in obj.deliveries.all())) or "–"

    @display(description=_("Corrected"))
    def show_corrected(self, obj):
        return format_html_join("", "<div>{} · {}</div>", ((c.quantity, f"{c.created_at:%d-%m-%Y}") for c in obj.corrections.all())) or "–"


@admin.register(PartOrder)
class PartOrderAdmin(ObjectActionsMixin, ModelAdmin):
    inlines = [OrderLineInline]
    list_display = ["number", "created_at", "customer", "reference", "total", "urgent", "show_status", "being_picked"]
    list_display_links = ["number", "customer"]
    list_filter = ["status", "urgent", "payment_method", "being_picked", "created_at"]
    search_fields = ["number", "reference", "customer__name", "customer__number", "lines__request_line__article_number",
                     "delivery_city", "delivery_postal_code", "delivery_address", "invoice__number"]
    date_hierarchy = "created_at"
    readonly_fields = [
        "number", "request", "customer", "created_by", "created_at", "status", "payment_method", "urgent",
        "discount_pct", "urgent_costs", "small_order_costs", "handling_costs", "payment_costs", "delivery_costs",
        "vat_rate", "gross", "discount", "net", "vat", "total", "approved_at", "approved_by", "cancelled_at",
        "cancel_reason", "show_invoice",
    ]
    object_actions = [
        ObjectAction("approve", _("Approve"), "check_circle", handler="do_approve", show_if="awaits_approval"),
        ObjectAction("paid", _("Payment received"), "payments", handler="do_paid", show_if="awaits_payment"),
        ObjectAction("deliver", _("Deliver"), "local_shipping", handler="go_deliver", show_if="can_deliver",
                     permission="parts.deliver_partorder"),
        ObjectAction("correct", _("Correct"), "edit_note", handler="go_correct", show_if="is_open",
                     permission="parts.deliver_partorder"),
        ObjectAction("picklist", _("Picking list"), "print", handler="go_picklist", show_if="is_open"),
        ObjectAction("invoice", _("Make invoice"), "receipt_long", handler="make_invoice", show_if="has_no_invoice"),
        ObjectAction("cancel", _("Cancel"), "cancel", handler="go_cancel", show_if="is_open", variant="danger",
                     permission="parts.deliver_partorder"),
    ]
    fieldsets = [
        (_("Order"), {"classes": ["tab"], "fields": [
            ("number", "status"), ("customer", "created_by"), ("request", "created_at"), "reference",
            ("payment_method", "urgent"), "being_picked", "show_invoice",
            ("approved_at", "approved_by"), ("cancelled_at", "cancel_reason"),
        ]}),
        (_("Amounts"), {"classes": ["tab"], "fields": [
            ("gross", "discount_pct", "discount"), ("urgent_costs", "small_order_costs", "handling_costs"),
            ("payment_costs", "delivery_costs"), ("net", "vat_rate", "vat"), "total",
        ]}),
        (_("Delivery address"), {"classes": ["tab"], "fields": [
            ("delivery_name", "delivery_contact"), "delivery_address", ("delivery_postal_code", "delivery_city"),
            ("delivery_country", "delivery_phone"),
        ]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("customer")

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("<int:pk>/deliver/", view(self.deliver_view), name="parts_partorder_deliver"),
            path("<int:pk>/correct/", view(self.correct_view), name="parts_partorder_correct"),
            path("<int:pk>/cancel/", view(self.cancel_view), name="parts_partorder_cancel"),
            path("<int:pk>/picklist/", view(self.picklist_view), name="parts_partorder_picklist"),
        ] + super().get_urls()

    @display(description=_("Status"), ordering="status", label=ORDER_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description=_("Invoice"))
    def show_invoice(self, obj):
        invoice = getattr(obj, "invoice", None)
        if invoice is None:
            return "–"
        return format_html('<a class="underline" href="{}">{}</a>', reverse("admin:invoices_invoice_change",
                                                                           args=[invoice.pk]), invoice.number)

    # --- conditions for the buttons ---

    def awaits_approval(self, obj):
        return obj.status == PartOrder.Status.AWAITING_APPROVAL

    def awaits_payment(self, obj):
        return obj.status == PartOrder.Status.AWAITING_PAYMENT

    def can_deliver(self, obj):
        return obj.status == PartOrder.Status.TO_DELIVER

    def is_open(self, obj):
        return obj.is_open()

    def has_no_invoice(self, obj):
        return getattr(obj, "invoice", None) is None and obj.status != PartOrder.Status.CANCELLED

    # --- the buttons ---

    def do_approve(self, request, order):
        services.approve(order, request.user)
        messages.success(request, gettext("Order approved; it can be delivered now."))

    def do_paid(self, request, order):
        services.paid(order)
        messages.success(request, gettext("Payment recorded; the order can be delivered now."))

    def go_deliver(self, request, order):
        return redirect("admin:parts_partorder_deliver", pk=order.pk)

    def go_correct(self, request, order):
        return redirect("admin:parts_partorder_correct", pk=order.pk)

    def go_cancel(self, request, order):
        return redirect("admin:parts_partorder_cancel", pk=order.pk)

    def go_picklist(self, request, order):
        return redirect("admin:parts_partorder_picklist", pk=order.pk)

    def make_invoice(self, request, order):
        from apps.invoices.services import InvoiceNumberError, create_for_part_order

        try:
            invoice = create_for_part_order(order)
        except InvoiceNumberError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, gettext("Invoice %(number)s made.") % {"number": invoice.number})

    # --- pages for deliver, correct, cancel ---

    def _page(self, request, order, template, title, **context):
        return TemplateResponse(request, f"admin/parts/{template}.html", {
            **self.admin_site.each_context(request), "title": f"{title} {order.number}", "order": order,
            "opts": self.model._meta, "lines": order.lines.select_related("request_line"),
            "back": reverse("admin:parts_partorder_change", args=[order.pk]), **context,
        })

    def _order_for(self, request, pk, perm="parts.deliver_partorder"):
        if perm and not request.user.has_perm(perm):
            raise PermissionDenied
        return get_object_or_404(PartOrder, pk=pk)

    @staticmethod
    def _numbers(request, order, prefix):
        values, errors = {}, []
        for line in order.lines.all():
            raw = request.POST.get(f"{prefix}-{line.pk}", "").strip() or "0"
            try:
                values[line.pk] = int(raw)
            except ValueError:
                errors.append(gettext("'%(value)s' is not a number (%(part)s).") % {
                    "value": raw, "part": line.request_line.article_number})
        return values, errors

    def deliver_view(self, request, pk):
        order = self._order_for(request, pk)
        if request.method == "POST":
            values, errors = self._numbers(request, order, "deliver")
            for line in order.lines.all():
                if not 0 <= values.get(line.pk, 0) <= line.to_deliver():
                    errors.append(gettext("%(part)s: at most %(n)s can still be delivered.") % {
                        "part": line.request_line.article_number, "n": line.to_deliver()})
            if not errors and not any(values.values()):
                errors.append(gettext("Fill in what is delivered."))
            if not errors:
                complete = services.deliver(order, values, request.user)
                messages.success(request, gettext("Delivery saved; the order is complete.") if complete
                                 else gettext("Delivery saved."))
                return redirect("admin:parts_partorder_change", order.pk)
            for error in errors:
                messages.error(request, error)
        return self._page(request, order, "deliver", gettext("Deliver"))

    def correct_view(self, request, pk):
        order = self._order_for(request, pk)
        if request.method == "POST":
            values, errors = self._numbers(request, order, "correct")
            reason = request.POST.get("reason", "").strip()
            for line in order.lines.all():
                value = values.get(line.pk, 0)
                if value > 0:
                    errors.append(gettext("%(part)s: a correction can only lower the quantity.") % {
                        "part": line.request_line.article_number})
                elif line.quantity + line.corrected() + value < 0:
                    errors.append(gettext("%(part)s: cannot be corrected by %(n)s.") % {
                        "part": line.request_line.article_number, "n": value})
            if not any(values.values()):
                errors.append(gettext("Fill in the correction."))
            if not reason:
                errors.append(gettext("Give a reason."))
            if not errors:
                credit = services.correct(order, values, reason, request.user)
                messages.success(request, gettext("Correction saved; € %(credit)s to credit. The administration has "
                                                  "been emailed.") % {"credit": money(credit)})
                return redirect("admin:parts_partorder_change", order.pk)
            for error in errors:
                messages.error(request, error)
        return self._page(request, order, "correct", gettext("Correct"))

    def cancel_view(self, request, pk):
        order = self._order_for(request, pk)
        if request.method == "POST":
            reason = request.POST.get("reason", "").strip()
            if not reason:
                messages.error(request, gettext("Give a reason."))
            elif order.is_open():
                services.cancel(order, reason, request.user)
                messages.success(request, gettext("Order cancelled. The administration has been emailed."))
                return redirect("admin:parts_partorder_change", order.pk)
        return self._page(request, order, "cancel", gettext("Cancel"))

    def picklist_view(self, request, pk):
        order = self._order_for(request, pk, perm="parts.view_partorder")
        return self._page(request, order, "picklist", gettext("Picking list"))


class SingletonAdmin(ModelAdmin, TabbedTranslationAdmin):
    def changelist_view(self, request, extra_context=None):
        return redirect(reverse(f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_change",
                                args=[self.model.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PartsSettings)
class PartsSettingsAdmin(SingletonAdmin):
    fieldsets = [
        (_("General"), {"classes": ["tab"], "fields": ["enabled", "quote_valid_days", "max_quantity", "notify_emails"]}),
        (_("Prices and costs"), {"classes": ["tab"], "fields": [
            "vat_rate", ("small_order_limit", "small_order_costs"), ("home_country", "foreign_delivery_costs"),
            "approval_limit",
        ]}),
        (_("Texts"), {"classes": ["tab"], "fields": ["intro", "terms_text"]}),
    ]


@admin.register(MarkupTier)
class MarkupTierAdmin(ModelAdmin):
    list_display = ["above", "factor"]
    list_editable = ["factor"]


@admin.register(DeliveryTime)
class DeliveryTimeAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "code", "position"]
    list_editable = ["position"]


@admin.register(PaymentMethod)
class PaymentMethodAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "code", "on_account", "extra_costs", "is_active", "position"]
    list_editable = ["position"]
