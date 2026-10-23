"""Roles (Django groups) that staff can be given.

Based on the previous webshop's back-office roles. Modules add their permissions
here as they are built.
"""

from django.contrib.auth.models import Group, Permission

ROLES = {
    "Beheerder": [
        "siteconfig.view_sitesettings",
        "siteconfig.change_sitesettings",
        "siteconfig.view_address",
        "siteconfig.add_address",
        "siteconfig.change_address",
        "siteconfig.delete_address",
        "siteconfig.view_homeblock",
        "siteconfig.add_homeblock",
        "siteconfig.change_homeblock",
        "siteconfig.delete_homeblock",
        "siteconfig.view_menuitem",
        "siteconfig.add_menuitem",
        "siteconfig.change_menuitem",
        "siteconfig.delete_menuitem",
        "accounts.view_user",
        "accounts.add_user",
        "accounts.change_user",
        "accounts.delete_user",
    ],
    "Financieel": [],
    "Service": [],
    "Medewerker": [],
}


def ensure_roles(**kwargs):
    for name, codes in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        perms = []
        for code in codes:
            app_label, codename = code.split(".")
            perms.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        group.permissions.set(perms)
