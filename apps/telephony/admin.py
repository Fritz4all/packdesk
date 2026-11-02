from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from apps.core.module_switch import opens_settings_when_off, when_enabled
from apps.customers import overview
from apps.customers.admin import CustomerAdmin

from .models import Category, Item, Quote, QuoteLine, TelephonyCustomer, TelephonySettings, uses_telephony


def in_use():
    return TelephonySettings.load().enabled


WhenEnabled = when_enabled(in_use)
OpensSettingsWhenOff = opens_settings_when_off(in_use, "admin:telephony_telephonysettings_changelist",
                                               _("Telephony is switched off. Switch it on here to use it."))


@admin.register(TelephonySettings)
class TelephonySettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fields = ["enabled", "installation_costs", "default_margin", "intro", "terms_text"]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:telephony_telephonysettings_change", args=[TelephonySettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CustomerSwitchInline(WhenEnabled, StackedInline):
    """The switch on the customer form. Added here, so the customer module stays unaware of telephony."""

    model = TelephonyCustomer
    extra = 1
    max_num = 1
    can_delete = False
    tab = True
    fields = ["enabled"]


CustomerAdmin.inlines = [*CustomerAdmin.inlines, CustomerSwitchInline]


@admin.register(Category)
class CategoryAdmin(OpensSettingsWhenOff, WhenEnabled, ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "position"]
    list_editable = ["position"]


@admin.register(Item)
class ItemAdmin(OpensSettingsWhenOff, WhenEnabled, ModelAdmin, TabbedTranslationAdmin):
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
class QuoteAdmin(OpensSettingsWhenOff, WhenEnabled, ModelAdmin):
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


def _overview_quotes(customer):
    return customer.telephony_quotes.order_by("-created_at")


overview.register("telephony_quotes", _("Telephony quotes"), "telephony.quote", _overview_quotes,
                  [_("Number"), _("Date"), _("Reference"), _("View")],
                  lambda q: [f"T{q.pk}", overview.short_date(q.created_at), q.reference, q.get_view_display()], order=57,
                  visible=uses_telephony)
