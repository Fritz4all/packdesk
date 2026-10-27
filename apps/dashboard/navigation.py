"""Admin sidebar. Every section can be collapsed; sections can be reordered per user (dashboard → Customise);
Configuration is last by default."""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

SECTIONS = [
    {
        "key": "overview",
        "collapsible": True,
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
        "collapsible": True,
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
            {
                "title": _("Trash"),
                "icon": "delete",
                "link": reverse_lazy("admin:trash_trashentry_changelist"),
                "permission": lambda request: request.user.has_perm("trash.view_trashentry"),
            },
            {
                "title": _("External databases"),
                "icon": "database",
                "link": reverse_lazy("admin:legacy_externaldatabase_changelist"),
                "permission": lambda request: request.user.has_perm("legacy.view_externaldatabase"),
            },
            {
                "title": _("Table mappings"),
                "icon": "link",
                "link": reverse_lazy("admin:legacy_tablemapping_changelist"),
                "permission": lambda request: request.user.has_perm("legacy.view_tablemapping"),
            },
            {
                "title": _("Imports"),
                "icon": "input",
                "link": reverse_lazy("admin:legacy_importrun_changelist"),
                "permission": lambda request: request.user.has_perm("legacy.import_data"),
            },
            {
                "title": _("Compare databases"),
                "icon": "compare_arrows",
                "link": reverse_lazy("legacy_choose"),
                "permission": lambda request: request.user.has_perm("legacy.compare_databases"),
            },
        ],
    },
    {
        "key": "customers",
        "collapsible": True,
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
                "title": _("Contacts"),
                "icon": "contacts",
                "link": reverse_lazy("admin:customers_contact_changelist"),
                "permission": lambda request: request.user.has_perm("customers.view_contact"),
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
        "collapsible": True,
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
        "key": "parts",
        "collapsible": True,
        "title": _("Spare parts"),
        "items": [
            {
                "title": _("Spare parts requests"),
                "icon": "build",
                "link": reverse_lazy("admin:parts_partrequest_changelist"),
                "permission": lambda request: request.user.has_perm("parts.view_partrequest"),
            },
            {
                "title": _("Spare parts orders"),
                "icon": "local_shipping",
                "link": reverse_lazy("admin:parts_partorder_changelist"),
                "permission": lambda request: request.user.has_perm("parts.view_partorder"),
            },
            {
                "title": _("Payment methods"),
                "icon": "payments",
                "link": reverse_lazy("admin:parts_paymentmethod_changelist"),
                "permission": lambda request: request.user.has_perm("parts.view_paymentmethod"),
            },
            {
                "title": _("Delivery times"),
                "icon": "schedule",
                "link": reverse_lazy("admin:parts_deliverytime_changelist"),
                "permission": lambda request: request.user.has_perm("parts.view_deliverytime"),
            },
            {
                "title": _("Markup tiers"),
                "icon": "percent",
                "link": reverse_lazy("admin:parts_markuptier_changelist"),
                "permission": lambda request: request.user.has_perm("parts.view_markuptier"),
            },
            {
                "title": _("Spare parts settings"),
                "icon": "tune",
                "link": reverse_lazy("admin:parts_partssettings_changelist"),
                "permission": lambda request: request.user.has_perm("parts.view_partssettings"),
            },
        ],
    },
    {
        "key": "licences",
        "collapsible": True,
        "title": _("Service packs and licences"),
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
        "key": "telephony",
        "collapsible": True,
        "title": _("Telephony"),
        "items": [
            {
                "title": _("Telephony quotes"),
                "icon": "request_quote",
                "link": reverse_lazy("admin:telephony_quote_changelist"),
                "permission": lambda request: request.user.has_perm("telephony.view_quote"),
            },
            {
                "title": _("Telephony items"),
                "icon": "call",
                "link": reverse_lazy("admin:telephony_item_changelist"),
                "permission": lambda request: request.user.has_perm("telephony.view_item"),
            },
            {
                "title": _("Telephony categories"),
                "icon": "folder",
                "link": reverse_lazy("admin:telephony_category_changelist"),
                "permission": lambda request: request.user.has_perm("telephony.view_category"),
            },
            {
                "title": _("Telephony settings"),
                "icon": "tune",
                "link": reverse_lazy("admin:telephony_telephonysettings_changelist"),
                "permission": lambda request: request.user.has_perm("telephony.view_telephonysettings"),
            },
        ],
    },
    {
        "key": "printing",
        "collapsible": True,
        "title": _("Printing services (archive)"),
        "items": [
            {
                "title": _("Printing quotes"),
                "icon": "request_quote",
                "link": reverse_lazy("admin:printing_printquote_changelist"),
                "permission": lambda request: request.user.has_perm("printing.view_printquote"),
            },
            {
                "title": _("Printing contracts"),
                "icon": "contract",
                "link": reverse_lazy("admin:printing_printcontract_changelist"),
                "permission": lambda request: request.user.has_perm("printing.view_printcontract"),
            },
            {
                "title": _("Supplies orders"),
                "icon": "inventory",
                "link": reverse_lazy("admin:printing_suppliesorder_changelist"),
                "permission": lambda request: request.user.has_perm("printing.view_suppliesorder"),
            },
            {
                "title": _("Printers"),
                "icon": "print",
                "link": reverse_lazy("admin:printing_printer_changelist"),
                "permission": lambda request: request.user.has_perm("printing.view_printer"),
            },
            {
                "title": _("Supplies"),
                "icon": "water_drop",
                "link": reverse_lazy("admin:printing_consumable_changelist"),
                "permission": lambda request: request.user.has_perm("printing.view_consumable"),
            },
            {
                "title": _("Support plans"),
                "icon": "support_agent",
                "link": reverse_lazy("admin:printing_supportplan_changelist"),
                "permission": lambda request: request.user.has_perm("printing.view_supportplan"),
            },
        ],
    },
    {
        "key": "faults",
        "collapsible": True,
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
        "collapsible": True,
        "title": _("Users and roles"),
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

DEFAULT_ORDER = ["overview", "customers", "orders", "licences", "parts", "telephony", "printing", "faults", "users",
                 "configuration"]


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


def section_index(request, app_label, extra_context=None):
    """The page behind a section in the breadcrumbs (e.g. /admin/licences/): the menu section(s) with items in
    that part of the admin, with the same names, icons and rights as the sidebar, instead of Django's list of
    all tables of the app."""
    from django.contrib import admin
    from django.template.response import TemplateResponse

    prefix = f"/admin/{app_label}/"
    sections = []
    for section in sidebar(request):
        items = [i for i in section["items"] if not i.get("permission") or i["permission"](request)]
        if any(str(i["link"]).startswith(prefix) for i in items):
            sections.append({"title": section["title"], "items": [{**i, "link": str(i["link"])} for i in items]})
    if not sections:
        return admin.site.__class__.app_index(admin.site, request, app_label, extra_context)
    return TemplateResponse(request, "admin/packdesk/section_index.html", {
        **admin.site.each_context(request), "title": sections[0]["title"], "sections": sections,
    })
