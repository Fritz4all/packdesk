from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display
from unfold.widgets import UnfoldAdminBigIntegerFieldWidget, UnfoldAdminTextareaWidget

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from .checks import check
from .models import CounterChange, GapNote, NumberSequence

STATUS_LABELS = {
    "ok": (_("In order"), "success"),
    "empty": (_("No documents yet"), "info"),
    "yearly": (_("Not checked (starts again every year)"), "info"),
    "behind": (_("Counter too low"), "danger"),
    "ahead": (_("Numbers missing at the end"), "warning"),
}


# Shows the next number while the name or pattern is being changed, before saving. Same tokens as
# patterns.render; random letters show as X.
PREVIEW_SCRIPT = """
(function () {
  var box = document.currentScript.previousElementSibling, nr = +box.dataset.pdNumber;
  var name = document.getElementById("id_name"), pattern = document.getElementById("id_pattern");
  if (!pattern) return;
  function pad(v, w) { v = String(v); while (v.length < w) v = "0" + v; return v; }
  function render(p) {
    var d = new Date();
    return p.replace(/\\{(nr|block|year|yy|month|letters)(?::(\\d+))?\\}/g, function (m, t, w) {
      if (t === "nr") return w ? pad(nr, +w) : String(nr);
      if (t === "block") { var size = Math.pow(10, +(w || 4)); return String.fromCharCode(65 + Math.floor(nr / size)) + pad(nr % size, +(w || 4)); }
      if (t === "year") return String(d.getFullYear());
      if (t === "yy") return pad(d.getFullYear() % 100, 2);
      if (t === "month") return pad(d.getMonth() + 1, 2);
      return "XXXXXXXXXX".slice(0, +(w || 1));
    });
  }
  function update() {
    if (name) box.children[0].textContent = name.value;
    box.children[1].textContent = render(pattern.value);
  }
  pattern.addEventListener("input", update);
  if (name) name.addEventListener("input", update);
})();
"""


def gap_text(first, last):
    return f"{first}" if first == last else f"{first} – {last}"


class NumberSequenceForm(forms.ModelForm):
    new_next_number = forms.IntegerField(
        label=_("Correct next number"),
        required=False,
        min_value=1,
        widget=UnfoldAdminBigIntegerFieldWidget,
        help_text=_("Only to fix the counter. It can never be set to a number that was already issued."),
    )
    correction_reason = forms.CharField(
        label=_("Reason for correction"),
        required=False,
        widget=UnfoldAdminTextareaWidget(attrs={"rows": 2}),
        help_text=_("Required when you correct the counter; stored in the log."),
    )

    class Meta:
        model = NumberSequence
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_next_number")
        if new and new != self.instance.next_number:
            if not cleaned.get("correction_reason", "").strip():
                self.add_error("correction_reason", _("Give a reason for the correction."))
            result = check(self.instance)
            if result.highest is not None and new <= result.highest:
                self.add_error(
                    "new_next_number",
                    _("Must be higher than %(highest)s, the highest number already issued.") % {"highest": result.highest},
                )
        return cleaned


class GapNoteInline(TabularInline):
    model = GapNote
    extra = 0
    tab = True
    fields = ["first", "last", "reason", "created_by", "created_at"]
    readonly_fields = ["created_by", "created_at"]


class CounterChangeInline(TabularInline):
    """The log of manual corrections. Someone who may correct counters may also fix the reason or remove
    an entry (it goes to the trash); what the counter was and became stays as it happened."""

    model = CounterChange
    extra = 0
    tab = True
    fields = ["changed_at", "user", "old_value", "new_value", "reason"]
    readonly_fields = ["changed_at", "user", "old_value", "new_value"]

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("numbering.correct_numbersequence")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("numbering.correct_numbersequence")


@admin.register(NumberSequence)
class NumberSequenceAdmin(ObjectActionsMixin, ModelAdmin, TabbedTranslationAdmin):
    form = NumberSequenceForm
    inlines = [GapNoteInline, CounterChangeInline]
    list_display = ["name", "show_preview", "next_number", "show_status"]
    search_fields = ["name", "key", "pattern"]
    readonly_fields = ["key", "next_number", "show_preview", "show_next_name", "status_overview"]
    object_actions = [
        ObjectAction("set-to-highest", _("Set counter to highest number + 1"), "sync", handler="set_to_highest",
                     show_if="counter_differs"),
    ]
    fieldsets = [
        (None, {"fields": ["status_overview"]}),
        (None, {"fields": ["name", "key", "pattern", "show_next_name", "reset_yearly", "archive_regex"]}),
        (_("Counter"), {"fields": ["next_number", "new_next_number", "correction_reason"]}),
    ]

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not request.user.has_perm("numbering.correct_numbersequence"):
            fieldsets = [(t, {**o, "fields": [f for f in o["fields"] if f not in ("new_next_number", "correction_reason")]})
                         for t, o in fieldsets]
        return fieldsets

    @display(description=_("Next number looks like"))
    def show_preview(self, obj):
        return obj.preview() if obj.pk else "–"

    @display(description=_("Next number looks like"))
    def show_next_name(self, obj):
        """What the next document will be called, from the name and the pattern; follows the form while typing."""
        if not obj.pk:
            return "–"
        return format_html(
            '<span data-pd-preview data-pd-number="{}"><span class="font-semibold">{}</span>: <span>{}</span></span>'
            '<script>{}</script>',
            obj._number_for_today(), obj.name, obj.preview(), mark_safe(PREVIEW_SCRIPT),
        )

    @display(description=_("Status"), label={"success": "success", "info": "info", "warning": "warning", "danger": "danger"})
    def show_status(self, obj):
        result = check(obj)
        label, colour = STATUS_LABELS[result.status]
        if result.status == "ok" and result.gaps:
            label, colour = gettext("Unexplained gaps"), "warning"
        return colour, label

    @display(description=_("Check against documents"))
    def status_overview(self, obj):
        if not obj.pk:
            return "–"
        result = check(obj)
        label, _colour = STATUS_LABELS[result.status]
        rows = [(gettext("Status"), label)]
        if not result.source_available:
            rows.append((gettext("Source"), gettext("No documents to compare with yet.")))
        if result.count:
            rows += [
                (gettext("Documents found"), f"{result.count}"),
                (gettext("Lowest / highest number"), f"{result.lowest} / {result.highest}"),
                (gettext("Next number expected"), f"{result.suggested_next}"),
                (gettext("Next number set"), f"{obj.next_number}"),
            ]
        if result.status == "behind":
            rows.append(
                (gettext("Problem"),
                 gettext("The counter would hand out a number that already exists. Correct it before issuing documents."))
            )
        if result.gaps:
            rows.append((gettext("Missing numbers (not explained)"), ", ".join(gap_text(a, b) for a, b in result.gaps[:20])
                         + (" …" if len(result.gaps) > 20 else "")))
        if result.explained:
            rows.append((gettext("Explained gaps"), ", ".join(gap_text(a, b) for a, b, _n in result.explained)))
        table = format_html_join("", "<tr><th style='text-align:left;padding:2px 16px 2px 0'>{}</th><td>{}</td></tr>", rows)
        return format_html("<table>{}</table>", table)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        new = form.cleaned_data.get("new_next_number")
        if new and new != obj.next_number and request.user.has_perm("numbering.correct_numbersequence"):
            result = check(obj)
            obj.correct(new, request.user, form.cleaned_data["correction_reason"].strip(), result.highest)
            messages.success(request, gettext("Counter set to %(n)s.") % {"n": new})

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, GapNote) and not instance.created_by_id:
                instance.created_by = request.user
            instance.save()
        for deleted in formset.deleted_objects:
            self.delete_model(request, deleted)  # to the trash
        formset.save_m2m()

    def counter_differs(self, obj):
        result = check(obj)
        return result.highest is not None and result.suggested_next != obj.next_number

    def set_to_highest(self, request, seq):
        if not request.user.has_perm("numbering.correct_numbersequence"):
            raise PermissionDenied
        result = check(seq)
        try:
            seq.correct(result.suggested_next, request.user, gettext("Set to highest existing number + 1"), result.highest)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(request, gettext("Counter set to %(n)s.") % {"n": result.suggested_next})
