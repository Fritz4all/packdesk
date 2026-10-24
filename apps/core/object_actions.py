"""Buttons for actions on one object, shown inside its change form (not in the page header).

Usage on a ModelAdmin:

    object_actions = [
        ObjectAction("approve", _("Approve"), "check_circle", handler="do_approve", show_if="can_approve"),
    ]

The handler is a method `(request, obj)` that adds its own messages; it may return a response
(e.g. a download) instead of going back to the form. Buttons post to `<object_id>/action/<name>/`
with a CSRF token; the user needs change permission, or `permission` when that is set.
"""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse


@dataclass
class ObjectAction:
    name: str
    label: str
    icon: str
    handler: str
    show_if: str | None = None
    variant: str = "default"  # default | danger
    confirm: str = ""
    permission: str = ""  # e.g. "customers.export_customer"; empty = change permission


class ObjectActionsMixin:
    object_actions: list[ObjectAction] = []
    change_form_outer_before_template = "admin/packdesk/object_actions.html"

    def get_urls(self):
        info = self.model._meta.app_label, self.model._meta.model_name
        extra = [
            path(
                "<path:object_id>/action/<str:name>/",
                self.admin_site.admin_view(self.run_object_action),
                name="%s_%s_object_action" % info,
            )
        ]
        return extra + super().get_urls()

    def _available_actions(self, request, obj):
        if obj is None:
            return []
        can_change = self.has_change_permission(request, obj)
        return [
            a for a in self.object_actions
            if (request.user.has_perm(a.permission) if a.permission else can_change)
            and (not a.show_if or getattr(self, a.show_if)(obj))
        ]

    def run_object_action(self, request, object_id, name):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        obj = get_object_or_404(self.model, pk=object_id)
        action = next((a for a in self._available_actions(request, obj) if a.name == name), None)
        if action is None:
            raise PermissionDenied
        response = getattr(self, action.handler)(request, obj)
        if response is not None:
            return response
        info = self.model._meta.app_label, self.model._meta.model_name
        return redirect(reverse("admin:%s_%s_change" % info, args=[obj.pk]))

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            info = self.model._meta.app_label, self.model._meta.model_name
            extra_context["object_actions"] = [
                {**a.__dict__, "url": reverse("admin:%s_%s_object_action" % info, args=[obj.pk, a.name])}
                for a in self._available_actions(request, obj)
            ]
        return super().changeform_view(request, object_id, form_url, extra_context)
