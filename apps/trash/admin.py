from django.contrib import admin, messages
from django.shortcuts import redirect
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display

from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from .models import TrashEntry
from .services import RestoreError, delete_for_good, purge_old, restore


@admin.register(TrashEntry)
class TrashEntryAdmin(ObjectActionsMixin, ModelAdmin):
    list_display = ["label", "kind", "show_summary", "deleted_at", "deleted_by"]
    list_display_links = ["label"]
    list_filter = ["kind", "deleted_at", "deleted_by"]
    search_fields = ["label", "kind", "summary", "deleted_by__email"]
    ordering = ["-deleted_at"]
    actions = ["restore_selected", "delete_selected_for_good"]
    readonly_fields = ["label", "kind", "deleted_at", "deleted_by", "object_count", "summary"]
    fields = readonly_fields
    object_actions = [
        ObjectAction("restore", _("Restore"), "restore_from_trash", handler="restore_one",
                     permission="trash.restore_trashentry"),
        ObjectAction("purge", _("Delete for good"), "delete_forever", handler="purge_one", variant="danger",
                     permission="trash.delete_trashentry",
                     confirm=_("Delete for good? This cannot be undone.")),
    ]

    @display(description=_("Deleted along with it"))
    def show_summary(self, obj):
        return obj.summary or "—"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        # "Delete for good" sits at the top with the other buttons; no second delete button below.
        return super().change_view(request, object_id, form_url, {**(extra_context or {}), "show_delete": False})

    def changelist_view(self, request, extra_context=None):
        purge_old(request.site_settings.trash_retention_days)
        return super().changelist_view(request, extra_context)

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)  # replaced by "delete for good"
        return actions

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_restore_permission(self, request):
        return request.user.has_perm("trash.restore_trashentry")

    # The object actions need "change" permission by default; the trash checks its own permissions.
    def _available_actions(self, request, obj):
        return [a for a in self.object_actions if obj is not None and request.user.has_perm(a.permission)]

    def _restore(self, request, entries):
        done, failed = 0, []
        for entry in entries:
            try:
                restore(entry)
                done += 1
            except RestoreError as exc:
                failed.append(f"{entry}: {exc}")
        if done:
            messages.success(request, gettext("%(n)s item(s) restored.") % {"n": done})
        for problem in failed:
            messages.error(request, problem)

    @admin.action(description=_("Restore selected items"), permissions=["restore"])
    def restore_selected(self, request, queryset):
        self._restore(request, list(queryset))

    @admin.action(description=_("Delete selected items for good"), permissions=["delete"])
    def delete_selected_for_good(self, request, queryset):
        count = 0
        for entry in list(queryset):
            delete_for_good(entry)
            count += 1
        messages.success(request, gettext("%(n)s item(s) deleted for good.") % {"n": count})

    def restore_one(self, request, entry):
        self._restore(request, [entry])
        return redirect("admin:trash_trashentry_changelist")

    def purge_one(self, request, entry):
        delete_for_good(entry)
        messages.success(request, gettext("Deleted for good."))
        return redirect("admin:trash_trashentry_changelist")

    # Deleting from the trash itself is permanent.
    def delete_model(self, request, obj):
        delete_for_good(obj)

    def delete_queryset(self, request, queryset):
        for entry in list(queryset):
            delete_for_good(entry)
