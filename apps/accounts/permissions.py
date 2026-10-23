"""Which permissions can be put in a role, grouped for the role editor."""

from django.apps import apps
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

# Apps whose functions can be granted to roles. New modules add their app label here.
MANAGED_APPS = ["siteconfig", "numbering", "customers", "accounts"]

ACTIONS = [
    ("view", _("View")),
    ("add", _("Add")),
    ("change", _("Change")),
    ("delete", _("Delete")),
]


def managed_permissions():
    return (
        Permission.objects.filter(content_type__app_label__in=MANAGED_APPS)
        .select_related("content_type")
        .order_by("content_type__app_label", "content_type__model", "codename")
    )


def grantable_permissions(user):
    """Permissions `user` may hand out: all for a superuser, otherwise only the ones they have."""
    qs = managed_permissions()
    if user.is_superuser:
        return qs
    q = Q(pk__in=[])
    for perm in user.get_all_permissions():
        app_label, codename = perm.split(".", 1)
        q |= Q(content_type__app_label=app_label, codename=codename)
    return qs.filter(q)


def matrix_rows(permissions):
    """Group permissions per model: [(app name, model name, {action: perm}, [extra perms])]."""
    rows = {}
    for perm in permissions:
        ct = perm.content_type
        key = (ct.app_label, ct.model)
        if key not in rows:
            model = apps.get_model(ct.app_label, ct.model)
            app_name = apps.get_app_config(ct.app_label).verbose_name
            rows[key] = [app_name, model._meta.verbose_name_plural, {}, []]
        action = perm.codename.split("_", 1)[0]
        if perm.codename == f"{action}_{ct.model}" and action in dict(ACTIONS):
            rows[key][2][action] = perm
        else:
            rows[key][3].append(perm)
    return [tuple(r) for r in rows.values()]
