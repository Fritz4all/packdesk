from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from modeltranslation.admin import TabbedTranslationAdmin, TranslationStackedInline
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import display

from .models import Address, HomeBlock, MenuItem, SiteSettings


class SiteSettingsForm(forms.ModelForm):
    languages = forms.MultipleChoiceField(
        label=_("Available languages"),
        choices=settings.LANGUAGES,
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Languages visitors can choose from."),
    )
    mail_password = forms.CharField(
        label=_("password"), required=False, strip=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Stored encrypted and never shown again. Leave empty to keep the current password."),
    )

    class Meta:
        model = SiteSettings
        fields = "__all__"

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("mail_password"):
            obj.set_mail_password(self.cleaned_data["mail_password"])
        if commit:
            obj.save()
            self.save_m2m()
        return obj

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


class AddressFormSet(forms.BaseInlineFormSet):
    """Each usage (website, invoices, ...) may be ticked on one address only."""

    def clean(self):
        super().clean()
        labels = {f: Address._meta.get_field(f).verbose_name for f in Address.USAGES.values()}
        seen = {}
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE"):
                continue
            for field, label in labels.items():
                if form.cleaned_data.get(field):
                    if field in seen:
                        raise forms.ValidationError(
                            _("“%(usage)s” is ticked on more than one address. Choose one address per usage.")
                            % {"usage": label}
                        )
                    seen[field] = form


class AddressInline(StackedInline):
    model = Address
    formset = AddressFormSet
    extra = 0
    tab = True
    collapsible = True
    fieldsets = [
        (None, {"fields": ["label", "line1", "line2", ("postal_code", "city"), "country", ("phone", "email")]}),
        (
            _("Use this address for"),
            {
                "fields": [("on_website", "on_invoices", "on_quotes"), ("on_orders", "on_mails", "on_labels")],
                "description": _(
                    "Tick where this address appears. Anything not ticked anywhere uses the first address."
                ),
            },
        ),
        (None, {"fields": ["position"]}),
    ]


class HomeBlockInline(StackedInline, TranslationStackedInline):
    model = HomeBlock
    extra = 0
    tab = True
    collapsible = True
    fields = ["icon", "title", "text", ("link_url", "link_text"), ("visibility", "is_active"), "position"]


class MenuItemInline(StackedInline, TranslationStackedInline):
    model = MenuItem
    extra = 0
    tab = True
    collapsible = True
    fields = ["label", ("url", "new_tab"), ("visibility", "is_active"), "position"]


@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    """Single settings page: the list view jumps straight to the form."""

    form = SiteSettingsForm
    inlines = [AddressInline, HomeBlockInline, MenuItemInline]

    readonly_fields = ["updated_at", "show_mail_source"]

    @display(description=_("In use"))
    def show_mail_source(self, obj):
        if settings.MAIL_SERVER_FROM_ENV:
            return gettext("The mail server from the server settings (.env) is used; the values here are ignored.")
        return gettext("The values above are used.") if obj.mail_host else gettext("No mail server entered yet.")
    color_fields = {"primary_color", "accent_color"}
    fieldsets = [
        (_("General"), {"classes": ["tab"], "fields": [
            "name", "domain", "language", "languages", "admin_language", "meta_description", "updated_at",
        ]}),
        (_("Security"), {"classes": ["tab"], "fields": [
            ("session_timeout_staff", "session_timeout_customers"), "trash_retention_days",
        ]}),
        (_("Mail server"), {"classes": ["tab"], "fields": [
            "mail_host", ("mail_port", "mail_security"), ("mail_user", "mail_password"), "show_mail_source",
        ]}),
        (
            _("Branding"),
            {"classes": ["tab"], "fields": ["logo", "favicon", ("primary_color", "accent_color"), "theme", "theme_switch"]},
        ),
        (_("Home page"), {"classes": ["tab"], "fields": ["tagline", "intro_text", "hero_button_text"]}),
        (
            _("Footer"),
            {
                "classes": ["tab"],
                "fields": [
                    "footer_text",
                    ("footer_show_address", "footer_show_phone", "footer_show_email"),
                    ("footer_show_coc", "footer_show_vat"),
                ],
            },
        ),
        (
            _("Company details"),
            {"classes": ["tab"], "fields": ["legal_name", ("phone", "email"), "website", ("coc_number", "vat_number"), "iban"]},
        ),
        (
            _("Maintenance"),
            {
                "classes": ["tab"],
                "fields": [
                    "maintenance_mode",
                    "maintenance_message",
                    "maintenance_until",
                    ("announcement_enabled", "announcement_level"),
                    "announcement_text",
                ],
            },
        ),
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
