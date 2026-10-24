"""Admin sidebar. Sections can be reordered per user (dashboard → Customise); Configuration is last by default."""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

SECTIONS = [
    {
        "key": "overview",
        "title": _("Overview"),
        "items": [
            {"title": _("Dashboard"), "icon": "dashboard", "link": reverse_lazy("admin:index")},
            {
                "title": _("Sales and margin"),
                "icon": "monitoring",
                "link": reverse_lazy("reports"),
                "permission": lambda request: request.user.has_perm("dashboard.view_reports"),
            },
        ],
    },
    {
        "key": "configuration",
        "title": _("Configuration"),
        "items": [
            {
                "title": _("Settings"),
                "icon": "tune",
                "link": reverse_lazy("admin:siteconfig_sitesettings_changelist"),
                "permission": lambda request: request.user.has_perm("siteconfig.view_sitesettings"),
            },
            {
                "title": _("Number sequences"),
                "icon": "pin",
                "link": reverse_lazy("admin:numbering_numbersequence_changelist"),
                "badge": "apps.numbering.admin_badge.problems",
                "permission": lambda request: request.user.has_perm("numbering.view_numbersequence"),
            },
        ],
    },
    {
        "key": "customers",
        "title": _("Customers"),
        "items": [
            {
                "title": _("Customers"),
                "icon": "storefront",
                "link": reverse_lazy("admin:customers_customer_changelist"),
                "badge": "apps.customers.admin_badge.pending",
                "permission": lambda request: request.user.has_perm("customers.view_customer"),
            },
            {
                "title": _("Customer types"),
                "icon": "category",
                "link": reverse_lazy("admin:customers_customertype_changelist"),
                "permission": lambda request: request.user.has_perm("customers.view_customertype"),
            },
            {
                "title": _("Countries"),
                "icon": "public",
                "link": reverse_lazy("admin:customers_country_changelist"),
                "permission": lambda request: request.user.has_perm("customers.view_country"),
            },
            {
                "title": _("Customer settings"),
                "icon": "how_to_reg",
                "link": reverse_lazy("admin:customers_signupsettings_changelist"),
                "permission": lambda request: request.user.has_perm("customers.view_signupsettings"),
            },
        ],
    },
    {
        "key": "orders",
        "title": _("Orders and invoices"),
        "items": [
            {
                "title": _("Orders"),
                "icon": "shopping_cart",
                "link": reverse_lazy("admin:orders_order_changelist"),
                "permission": lambda request: request.user.has_perm("orders.view_order"),
            },
            {
                "title": _("Invoices"),
                "icon": "receipt_long",
                "link": reverse_lazy("admin:invoices_invoice_changelist"),
                "permission": lambda request: request.user.has_perm("invoices.view_invoice"),
            },
            {
                "title": _("Invoice settings"),
                "icon": "description",
                "link": reverse_lazy("admin:invoices_invoicesettings_changelist"),
                "permission": lambda request: request.user.has_perm("invoices.view_invoicesettings"),
            },
            {
                "title": _("Order settings"),
                "icon": "tune",
                "link": reverse_lazy("admin:orders_ordersettings_changelist"),
                "permission": lambda request: request.user.has_perm("orders.view_ordersettings"),
            },
        ],
    },
    {
        "key": "licences",
        "title": _("Service packs and licences"),
        "collapsible": True,
        "items": [
            {
                "title": _("Licences"),
                "icon": "verified",
                "link": reverse_lazy("admin:licences_licence_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_licence"),
            },
            {
                "title": _("Service packs"),
                "icon": "inventory_2",
                "link": reverse_lazy("admin:licences_supportpack_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_supportpack"),
            },
            {
                "title": _("Pack categories"),
                "icon": "folder",
                "link": reverse_lazy("admin:licences_category_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_category"),
            },
            {
                "title": _("Hardware classes"),
                "icon": "dns",
                "link": reverse_lazy("admin:licences_hardwareclass_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_hardwareclass"),
            },
            {
                "title": _("Brands"),
                "icon": "sell",
                "link": reverse_lazy("admin:licences_vendor_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_vendor"),
            },
            {
                "title": _("Device types"),
                "icon": "devices",
                "link": reverse_lazy("admin:licences_hardwaresystem_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_hardwaresystem"),
            },
            {
                "title": _("Option types"),
                "icon": "memory",
                "link": reverse_lazy("admin:licences_optiontype_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_optiontype"),
            },
            {
                "title": _("Support periods"),
                "icon": "schedule",
                "link": reverse_lazy("admin:licences_supportperiod_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_supportperiod"),
            },
            {
                "title": _("Service levels"),
                "icon": "support_agent",
                "link": reverse_lazy("admin:licences_supportservice_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_supportservice"),
            },
            {
                "title": _("Licence settings"),
                "icon": "tune",
                "link": reverse_lazy("admin:licences_licencesettings_changelist"),
                "permission": lambda request: request.user.has_perm("licences.view_licencesettings"),
            },
        ],
    },
    {
        "key": "faults",
        "title": _("Fault reports"),
        "items": [
            {
                "title": _("Fault reports"),
                "icon": "build",
                "link": reverse_lazy("admin:faults_faultreport_changelist"),
                "badge": "apps.faults.admin_badge.new_reports",
                "permission": lambda request: request.user.has_perm("faults.view_faultreport"),
            },
            {
                "title": _("Handling options"),
                "icon": "list",
                "link": reverse_lazy("admin:faults_repairoption_changelist"),
                "permission": lambda request: request.user.has_perm("faults.view_repairoption"),
            },
            {
                "title": _("Fault report settings"),
                "icon": "tune",
                "link": reverse_lazy("admin:faults_faultsettings_changelist"),
                "permission": lambda request: request.user.has_perm("faults.view_faultsettings"),
            },
        ],
    },
    {
        "key": "users",
        "title": _("Users"),
        "items": [
            {
                "title": _("Users"),
                "icon": "person",
                "link": reverse_lazy("admin:accounts_user_changelist"),
                "permission": lambda request: request.user.has_perm("accounts.view_user"),
            },
            {
                "title": _("Roles"),
                "icon": "badge",
                "link": reverse_lazy("admin:accounts_role_changelist"),
                "permission": lambda request: request.user.has_perm("accounts.view_role"),
            },
        ],
    },
]

DEFAULT_ORDER = ["overview", "customers", "orders", "licences", "faults", "users", "configuration"]


def ordered_keys(user):
    from .models import DashboardLayout

    saved = DashboardLayout.objects.filter(user=user).values_list("sidebar_order", flat=True).first() or []
    known = [s["key"] for s in SECTIONS]
    order = [k for k in saved if k in known] + [k for k in DEFAULT_ORDER if k not in saved]
    return order + [k for k in known if k not in order]


def sidebar(request):
    """Called by unfold (UNFOLD["SIDEBAR"]["navigation"]) on every admin page."""
    by_key = {s["key"]: s for s in SECTIONS}
    if not request.user.is_authenticated:
        return [by_key[k] for k in DEFAULT_ORDER]
    return [by_key[k] for k in ordered_keys(request.user)]
