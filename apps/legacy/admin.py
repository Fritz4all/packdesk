from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from .connection import check_connection
from .models import ExternalDatabase


class ExternalDatabaseForm(forms.ModelForm):
    password = forms.CharField(
        label=_("password"), required=False, strip=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "new-password"}),
        help_text=_("Stored encrypted and never shown again. Leave empty to keep the current password."),
    )

    class Meta:
        model = ExternalDatabase
        fields = ["name", "engine", "host", "port", "database", "user", "password", "notes"]

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("password"):
            obj.set_password(self.cleaned_data["password"])
        if commit:
            obj.save()
        return obj


@admin.register(ExternalDatabase)
class ExternalDatabaseAdmin(ObjectActionsMixin, ModelAdmin):
    form = ExternalDatabaseForm
    list_display = ["name", "engine", "host", "database", "show_status", "last_checked_at"]
    search_fields = ["name", "host", "database"]
    readonly_fields = ["last_checked_at", "show_status", "last_check_message"]
    fieldsets = [
        (None, {"fields": ["name", ("engine", "host", "port"), "database", ("user", "password"), "notes"],
                "description": _("PackDesk only reads from this database and never changes it. "
                                 "For extra safety, give this user read rights only.")}),
        (_("Last test"), {"fields": [("last_checked_at", "show_status"), "last_check_message"]}),
    ]
    object_actions = [
        ObjectAction("test", _("Test connection"), "lan", handler="run_test"),
        ObjectAction("compare", _("Compare with PackDesk"), "compare_arrows", handler="open_compare",
                     permission="legacy.compare_databases"),
    ]

    @display(description=_("Connection"), label={"ok": "success", "error": "danger", "unknown": "info"})
    def show_status(self, obj):
        if obj.last_check_ok is None:
            return "unknown", gettext("Not tested")
        return ("ok", gettext("Works")) if obj.last_check_ok else ("error", gettext("No connection"))

    def run_test(self, request, db):
        ok, message = check_connection(db)
        ExternalDatabase.objects.filter(pk=db.pk).update(
            last_checked_at=timezone.now(), last_check_ok=ok, last_check_message=message,
        )
        (messages.success if ok else messages.error)(request, message)

    def open_compare(self, request, db):
        return redirect(reverse("legacy_compare", args=[db.pk]))
