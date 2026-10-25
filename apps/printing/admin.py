"""Printing services are an archive: everything can be looked at and searched, nothing changed."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from .models import (Consumable, PrintContract, PrintContractLine, Printer, PrintQuote, PrintQuoteLine, SuppliesOrder,
                     SuppliesOrderLine, SupportPlan)

PRICE_FIELDS = ["total_prints", "color_prints", "options_price", "price_print_black", "price_print_color",
                "price_ex_hw", "price_inc_hw", "customer_price_ex_hw", "customer_price_inc_hw"]


class ArchiveMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class ArchiveAdmin(ArchiveMixin, ModelAdmin):
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
