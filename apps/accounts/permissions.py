"""Which permissions can be put in a role, grouped for the role editor."""

from django.apps import apps
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


def managed_apps():
    """Apps whose functions can be granted to roles: every PackDesk module (apps.*), so a new module or function
    appears in the role editor by itself once its migration has run."""
    return [config.label for config in apps.get_app_configs() if config.name.startswith("apps.")]


ACTIONS = [
    ("view", _("View")),
    ("add", _("Add")),
    ("change", _("Change")),
    ("delete", _("Delete")),
]


# Technical models whose standard permissions make no sense in a role (their special rights still show).
HIDDEN_MODELS = {("dashboard", "dashboardlayout"), ("accounts", "customeruser"),  # customer users: rights of users
                 ("accounts", "roleinfo")}  # role names: part of the role


def managed_permissions():
    hidden = Q(pk__in=[])
    for app_label, model in HIDDEN_MODELS:
        hidden |= Q(content_type__app_label=app_label, content_type__model=model,
                    codename__in=[f"{a}_{model}" for a in ("view", "add", "change", "delete")])
    return (
        Permission.objects.filter(content_type__app_label__in=managed_apps()).exclude(hidden)
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
