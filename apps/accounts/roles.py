"""Default roles, created on the first migrate.

Based on the previous webshop's back-office roles. After that, roles are managed
in the admin (Users → Roles); this file only seeds new installations.
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
        "numbering.view_numbersequence",
        "numbering.change_numbersequence",
        "numbering.correct_numbersequence",
        "numbering.view_gapnote",
        "numbering.add_gapnote",
        "numbering.view_counterchange",
        "accounts.view_user",
        "accounts.add_user",
        "accounts.change_user",
        "accounts.delete_user",
        "accounts.view_role",
        "accounts.add_role",
        "accounts.change_role",
        "accounts.delete_role",
    ],
    "Financieel": [
        "numbering.view_numbersequence",
        "numbering.change_numbersequence",
        "numbering.correct_numbersequence",
        "numbering.view_gapnote",
        "numbering.add_gapnote",
        "numbering.view_counterchange",
    ],
    "Service": [],
    "Medewerker": [],
}


def ensure_roles(**kwargs):
    """Create the default roles once. Existing roles are never changed, so edits in the admin are kept."""
    for name, codes in ROLES.items():
        group, created = Group.objects.get_or_create(name=name)
        if not created:
            continue
        perms = []
        for code in codes:
            app_label, codename = code.split(".")
            perms.append(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        group.permissions.set(perms)
