from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    """Single settings page: the list view jumps straight to the form."""

    readonly_fields = ["updated_at"]
    color_fields = {"primary_color", "accent_color"}
    fieldsets = [
        (None, {"fields": ["name", "language"]}),
        (_("Branding"), {"fields": ["logo", "favicon", ("primary_color", "accent_color"), "tagline", "intro_text"]}),
        (
            _("Company details"),
            {
                "fields": [
                    "legal_name",
                    "address_line",
                    ("postal_code", "city", "country"),
                    ("phone", "email"),
                    "website",
                    ("coc_number", "vat_number"),
                    "iban",
                ]
            },
        ),
        (None, {"fields": ["updated_at"]}),
    ]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in self.color_fields:
            kwargs["widget"] = forms.TextInput(attrs={"type": "color", "class": "h-10 w-24 cursor-pointer"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def changelist_view(self, request, extra_context=None):
        obj = SiteSettings.load()
        return redirect(reverse("admin:siteconfig_sitesettings_change", args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
