"""Every deletion in the admin goes to the trash.

Installed once at start-up on Django's ModelAdmin, so it covers all admin pages: deleting one item,
"delete selected" in a list, and rows removed inside a form (e.g. an address of a customer).
An admin that defines its own delete methods (like the trash itself) keeps them.
"""

from django.contrib.admin import ModelAdmin

from .services import delete_to_trash, keeps


def _delete_model(self, request, obj):
    if keeps(obj):
        delete_to_trash(obj, request.user)
    else:
        obj.delete()


def _delete_queryset(self, request, queryset):
    for obj in queryset:
        _delete_model(self, request, obj)


def _save_formset(self, request, form, formset, change):
    instances = formset.save(commit=False)
    for obj in formset.deleted_objects:
        _delete_model(self, request, obj)
    for obj in instances:
        obj.save()
    formset.save_m2m()


def install():
    ModelAdmin.delete_model = _delete_model
    ModelAdmin.delete_queryset = _delete_queryset
    ModelAdmin.save_formset = _save_formset
