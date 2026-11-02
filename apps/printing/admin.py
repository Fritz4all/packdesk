"""Printing services are an archive: everything can be looked at and searched, nothing changed."""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from apps.core.module_switch import opens_settings_when_off, when_enabled
from apps.customers import overview

from .models import (Consumable, PrintContract, PrintContractLine, Printer, PrintingSettings, PrintQuote, PrintQuoteLine,
                     SuppliesOrder, SuppliesOrderLine, SupportPlan)

PRICE_FIELDS = ["total_prints", "color_prints", "options_price", "price_print_black", "price_print_color",
                "price_ex_hw", "price_inc_hw", "customer_price_ex_hw", "customer_price_inc_hw"]


def in_use():
    return PrintingSettings.load().enabled


WhenEnabled = when_enabled(in_use)
OpensSettingsWhenOff = opens_settings_when_off(in_use, "admin:printing_printingsettings_changelist",
                                               _("The printing archive is switched off. Switch it on here to see it."))


@admin.register(PrintingSettings)
class PrintingSettingsAdmin(ModelAdmin):
    fields = ["enabled"]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:printing_printingsettings_change", args=[PrintingSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ArchiveMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ArchiveAdmin(OpensSettingsWhenOff, ArchiveMixin, WhenEnabled, ModelAdmin):
    pass


class ArchiveInline(ArchiveMixin, TabularInline):
    extra = 0
    tab = True
    can_delete = False


@admin.register(Printer)
class PrinterAdmin(ArchiveAdmin):
    list_display = ["name", "product_nr", "vendor", "price", "color", "is_deleted"]
    list_filter = ["vendor", "color", "is_deleted"]
    search_fields = ["name", "product_nr", "description"]


@admin.register(Consumable)
class ConsumableAdmin(ArchiveAdmin):
    list_display = ["name", "product_nr", "vendor", "price", "color", "prints"]
    list_filter = ["vendor", "color"]
    search_fields = ["name", "product_nr", "printers__name"]


@admin.register(SupportPlan)
class SupportPlanAdmin(ArchiveAdmin):
    list_display = ["abbreviation", "description", "years", "storage_factor", "lease_factor"]


class QuoteLineInline(ArchiveInline):
    model = PrintQuoteLine
    fields = ["printer", "support", *PRICE_FIELDS]


@admin.register(PrintQuote)
class PrintQuoteAdmin(ArchiveAdmin):
    inlines = [QuoteLineInline]
    list_display = ["number", "created_at", "customer", "reference", "deleted"]
    list_filter = ["deleted", "created_at"]
    search_fields = ["number", "reference", "customer__name", "customer__number", "lines__printer__name"]
    date_hierarchy = "created_at"
    list_select_related = ["customer"]


class ContractLineInline(ArchiveInline):
    model = PrintContractLine
    fields = ["printer", "serial_nr", "support", *PRICE_FIELDS, "min_items", "max_items", "readings"]


@admin.register(PrintContract)
class PrintContractAdmin(ArchiveAdmin):
    inlines = [ContractLineInline]
    list_display = ["number", "customer", "company", "start_date", "end_date", "activated_at"]
    list_filter = ["includes_hardware", "start_date"]
    search_fields = ["number", "company", "contact", "customer__name", "customer__number", "lines__serial_nr"]
    list_select_related = ["customer"]


class SuppliesLineInline(ArchiveInline):
    model = SuppliesOrderLine
    fields = ["consumable", "quantity", "price"]


@admin.register(SuppliesOrder)
class SuppliesOrderAdmin(ArchiveAdmin):
    inlines = [SuppliesLineInline]
    list_display = ["number", "created_at", "contract_line", "contact", "sent_at"]
    search_fields = ["number", "contact", "contract_line__serial_nr", "contract_line__contract__number"]


def _overview_quotes(customer):
    return customer.print_quotes.order_by("-created_at")


def _overview_contracts(customer):
    return customer.print_contracts.order_by("-created_at")


def _shown(customer):
    return in_use()


overview.register("print_quotes", _("Printing quotes"), "printing.printquote", _overview_quotes,
                  [_("Number"), _("Date"), _("Reference")],
                  lambda q: [q.number, overview.short_date(q.created_at), q.reference], order=58, visible=_shown)
overview.register("print_contracts", _("Printing contracts"), "printing.printcontract", _overview_contracts,
                  [_("Number"), _("End customer"), _("Start"), _("End")],
                  lambda c: [c.number, c.company, overview.short_date(c.start_date), overview.short_date(c.end_date)],
                  order=59, visible=_shown)
