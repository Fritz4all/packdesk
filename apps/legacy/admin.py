from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.template.loader import render_to_string
from unfold.admin import ModelAdmin, TabularInline
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget, UnfoldAdminTextInputWidget
from unfold.decorators import display

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from .compare import mapped_rows, show, source_columns
from .connection import ExternalDatabaseError, check_connection, open_reader
from .models import ExternalDatabase, FieldMapping, TableMapping
from .parts import OLD_SHOP_PRESET, PARTS_BY_KEY, apply_preset


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
        ObjectAction("mappings", _("Table mappings"), "link", handler="open_mappings"),
        ObjectAction("preset", _("Load mapping for the previous webshop"), "auto_fix", handler="load_preset",
                     show_if="preset_missing"),
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

    def open_mappings(self, request, db):
        return redirect(reverse("admin:legacy_tablemapping_changelist") + f"?database__id__exact={db.pk}")

    def preset_missing(self, db):
        return db.mappings.filter(part__in=OLD_SHOP_PRESET).count() < len(OLD_SHOP_PRESET)

    def load_preset(self, request, db):
        created = apply_preset(db)
        ExternalDatabase.objects.filter(pk=db.pk).update(updated_at=timezone.now())
        messages.success(request, gettext("%(n)s table mapping(s) for the previous webshop added. Existing mappings were kept.")
                         % {"n": created})

    def open_compare(self, request, db):
        return redirect(reverse("legacy_compare", args=[db.pk]))


# --- table mappings ------------------------------------------------------------------------------


def _touch(db):
    """A changed mapping makes earlier comparison results outdated."""
    ExternalDatabase.objects.filter(pk=db.pk).update(updated_at=timezone.now())


class FieldMappingForm(forms.ModelForm):
    part = None  # set per mapping in TableMappingAdmin.get_formset

    class Meta:
        model = FieldMapping
        fields = ["field", "column"]
        widgets = {"column": UnfoldAdminTextInputWidget(attrs={"list": "pd-columns", "autocomplete": "off"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        part = PARTS_BY_KEY.get(self.part)
        choices = [(f.name, f.label) for f in part.fields] if part else []
        self.fields["field"] = forms.ChoiceField(label=_("PackDesk field"), choices=[("", "---------"), *choices],
                                                 widget=UnfoldAdminSelectWidget)


class FieldMappingInline(TabularInline):
    model = FieldMapping
    form = FieldMappingForm
    extra = 0
    tab = True
    show_title = False
    verbose_name = _("field")
    verbose_name_plural = _("fields")


class TableMappingForm(forms.ModelForm):
    class Meta:
        model = TableMapping
        fields = ["database", "part", "enabled", "source_table", "source_query", "id_column", "skip_column", "skip_value"]
        widgets = {
            "source_table": UnfoldAdminTextInputWidget(attrs={"list": "pd-tables", "autocomplete": "off"}),
            "source_query": UnfoldAdminTextareaWidget(attrs={"rows": 6, "style": "font-family: monospace"}),
            "id_column": UnfoldAdminTextInputWidget(attrs={"list": "pd-columns", "autocomplete": "off"}),
            "skip_column": UnfoldAdminTextInputWidget(attrs={"list": "pd-columns", "autocomplete": "off"}),
        }


@admin.register(TableMapping)
class TableMappingAdmin(ModelAdmin):
    form = TableMappingForm
    inlines = [FieldMappingInline]
    list_display = ["show_part", "database", "show_source", "n_fields", "enabled"]
    list_filter = ["database", "enabled"]
    search_fields = ["source_table", "source_query"]
    readonly_fields = ["show_help"]
    fieldsets = [
        (None, {"fields": ["database", "part", "enabled"]}),
        (_("Source in the external database"), {"fields": [
            "source_table", "source_query", "id_column", ("skip_column", "skip_value"), "show_help",
        ]}),
    ]

    @display(description=_("PackDesk part"), ordering="part")
    def show_part(self, obj):
        return obj.get_part_display()

    @display(description=_("Source"))
    def show_source(self, obj):
        return obj.source_table or (obj.source_query[:60] + ("…" if len(obj.source_query) > 60 else ""))

    @display(description=_("Fields"))
    def n_fields(self, obj):
        return obj.fields.count()

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if request.GET.get("database"):
            initial["database"] = request.GET["database"]
        return initial

    def get_inline_instances(self, request, obj=None):
        # Which fields can be linked depends on the part, so fields come after the first save.
        return super().get_inline_instances(request, obj) if obj else []

    def get_formsets_with_inlines(self, request, obj=None):
        for inline in self.get_inline_instances(request, obj):
            form = type("PartFieldMappingForm", (FieldMappingForm,), {"part": obj.part})
            yield inline.get_formset(request, obj, form=form), inline

    @display(description=_("Tables and columns"))
    def show_help(self, obj):
        """Lists tables and the source's columns (also as suggestions in the fields), plus a few example rows."""
        if obj is None or not obj.pk:
            return gettext("Save first; then the tables, columns and example rows of the external database appear here.")
        try:
            with open_reader(obj.database) as reader:
                tables = sorted(reader.tables())
                columns = source_columns(obj, reader) if (obj.source_table or obj.source_query) else []
                preview = mapped_rows(obj, reader, limit=5) if obj.fields.exists() else []
        except ExternalDatabaseError as exc:
            return gettext("No connection: %(error)s") % {"error": exc}
        part = PARTS_BY_KEY[obj.part]
        keys = [f.field for f in obj.fields.all()]
        return render_to_string("legacy/mapping_help.html", {
            "tables": tables, "columns": columns,
            "headers": [str(part.by_name[k].label) if k in part.by_name else k for k in keys],
            "preview": [[show(row.get(k)) for k in keys] + [row["_id"] or "—"] for row in preview],
        })

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        _touch(form.instance.database)

    def response_add(self, request, obj, post_url_continue=None):
        # Straight on to linking the fields.
        return redirect(reverse("admin:legacy_tablemapping_change", args=[obj.pk]))
