from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin

from .models import SiteSettings


class SiteSettingsForm(forms.ModelForm):
    languages = forms.MultipleChoiceField(
        label=_("Available languages"),
        choices=settings.LANGUAGES,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Languages visitors can choose from."),
    )

    class Meta:
        model = SiteSettings
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial["languages"] = self.instance.language_codes

    def clean(self):
        cleaned = super().clean()
        languages = cleaned.get("languages") or []
        if cleaned.get("language") and cleaned["language"] not in languages:
            self.add_error("languages", _("The default language must be one of the available languages."))
        cleaned["languages"] = ",".join(languages)
        return cleaned


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    """Single settings page: the list view jumps straight to the form."""

    form = SiteSettingsForm

    readonly_fields = ["updated_at"]
    color_fields = {"primary_color", "accent_color"}
    fieldsets = [
        (None, {"fields": ["name", "language", "languages"]}),
        (_("Branding"), {"fields": ["logo", "favicon", ("primary_color", "accent_color"), "tagline", "intro_text"]}),
        (_("Appearance"), {"fields": ["theme", "theme_switch"]}),
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
