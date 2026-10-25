from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline

from .models import Category, Item, Quote, QuoteLine, TelephonySettings


@admin.register(TelephonySettings)
class TelephonySettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fields = ["enabled", "installation_costs", "default_margin", "intro", "terms_text"]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:telephony_telephonysettings_change", args=[TelephonySettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "position"]
    list_editable = ["position"]


@admin.register(Item)
class ItemAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "category", "hire_per_month", "buy_price", "buy_per_month", "is_active", "position"]
    list_editable = ["position"]
    list_filter = ["category", "is_active"]
    search_fields = ["name", "description"]
    filter_horizontal = ["quantity_from"]
    fields = ["category", "name", "description", "image", ("hire_per_month", "buy_price", "buy_per_month"),
              "quantity_from", "is_active", "position"]


class QuoteLineInline(TabularInline):
    model = QuoteLine
    extra = 0
    tab = True
    can_delete = False
    fields = ["item", "quantity", "hire_per_month", "buy_price", "buy_per_month"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Quote)
class QuoteAdmin(ModelAdmin):
    """Quotes are made by customers in the portal; here they can be looked at."""

    inlines = [QuoteLineInline]
    list_display = ["__str__", "created_at", "customer", "view", "margin_hire", "margin_buy"]
    list_filter = ["view", "created_at"]
    search_fields = ["reference", "customer__name", "customer__number"]
    list_select_related = ["customer"]
    readonly_fields = ["customer", "created_by", "reference", "view", "margin_hire", "margin_buy", "installation_costs",
                       "old_price_per_port", "created_at"]

    def has_add_permission(self, request):
        return False
