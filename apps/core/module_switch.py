"""For modules that can be switched off for the whole installation."""

from django.contrib import messages
from django.shortcuts import redirect


def when_enabled(in_use):
    """A mixin for admin pages that only exist while the installation uses the module. The module's settings page
    does not use it, or the module could not be switched on again."""

    class WhenEnabled:
        def has_module_permission(self, request):
            return in_use() and super().has_module_permission(request)

        def has_view_permission(self, request, obj=None):
            return in_use() and super().has_view_permission(request, obj)

        def has_add_permission(self, request, *args):
            return in_use() and super().has_add_permission(request, *args)

        def has_change_permission(self, request, obj=None):
            return in_use() and super().has_change_permission(request, obj)

        def has_delete_permission(self, request, obj=None):
            return in_use() and super().has_delete_permission(request, obj)

    return WhenEnabled


def opens_settings_when_off(in_use, settings_list, message):
    """A mixin for the admin lists of such a module: while it is off, a list leads to the place to switch it on."""

    class OpensSettingsWhenOff:
        def changelist_view(self, request, extra_context=None):
            if not in_use():
                messages.info(request, message)
                return redirect(settings_list)
            return super().changelist_view(request, extra_context)

    return OpensSettingsWhenOff
