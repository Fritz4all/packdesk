"""Roles (Django groups) that tenant staff can be given.

Based on the previous webshop's back-office roles. Modules add their permissions
here as they are built.
"""

from django.contrib.auth.models import Group, Permission

ROLES = {
    "Beheerder": [
        "tenants.view_tenant",
        "tenants.change_tenant",
        "accounts.view_user",
        "accounts.add_user",
        "accounts.change_user",
        "accounts.delete_user",
    ],
    "Financieel": ["tenants.view_tenant"],
    "Service": ["tenants.view_tenant"],
    "Medewerker": ["tenants.view_tenant"],
}


def ensure_roles(**kwargs):
    for name, codes in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        perms = []
        for code in codes:
            app_label, codename = code.split(".")
            perms.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        group.permissions.set(perms)
