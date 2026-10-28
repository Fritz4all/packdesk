"""Admin sidebar. Every section can be collapsed. The menu for everyone can be changed under Configuration → Menu
(order and names of the main menus, which items each one holds, extra main menus); on top of that each user can
reorder the main menus for themselves (dashboard → Customise). Configuration is last by default."""

import re

from django.conf import settings
from django.urls import reverse_lazy
from django.utils.functional import lazy
from django.utils.translation import get_language
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
                "title": _("Menu"),
                "icon": "menu_open",
                "link": reverse_lazy("admin_menu"),
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
                "title": _("Invoice design"),
                "icon": "design_services",
                "link": reverse_lazy("admin:invoices_invoicesettings_design"),
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


CUSTOM_KEY = re.compile(r"^custom-[a-z0-9]{1,20}$")
TITLE_LENGTH = 60


def item_key(item):
    """An item is known by its address, e.g. /admin/invoices/invoicesettings/."""
    return str(item["link"])


def _title(texts, standard):
    """The saved name in the language of the page, otherwise the standard name (translated)."""
    def resolve():
        return (texts or {}).get((get_language() or "")[:2]) or str(standard)

    return lazy(resolve, str)()


def menu(layout=None):
    """All main menus with their items, after the changes saved under Configuration → Menu.

    Main menus and items that are new in PackDesk (not in the saved layout) appear in their standard place."""
    if layout is None:
        from .models import AdminMenu

        layout = AdminMenu.load().layout
    builtin = {s["key"]: s for s in SECTIONS}
    home = {item_key(i): (s["key"], i) for s in SECTIONS for i in s["items"]}
    names = layout.get("items") or {}
    entries, placed = [], set()
    for saved in layout.get("sections") or []:
        key = saved.get("key")
        if not (key in builtin or CUSTOM_KEY.match(str(key))) or any(e["key"] == key for e in entries):
            continue
        items = [k for k in saved.get("items") or [] if k in home and k not in placed]
        placed.update(items)
        entries.append({"key": key, "title": saved.get("title") or {}, "items": items})
    for key in DEFAULT_ORDER:
        if not any(e["key"] == key for e in entries):
            entries.append({"key": key, "title": {}, "items": []})
    for key, (section, _item) in home.items():
        if key not in placed:
            next(e for e in entries if e["key"] == section)["items"].append(key)
    return [
        {
            "key": e["key"], "collapsible": True, "custom": e["key"] not in builtin,
            "title": _title(e["title"], builtin[e["key"]]["title"] if e["key"] in builtin else _("New menu")),
            "items": [{**home[k][1], "title": _title(names.get(k), home[k][1]["title"])} for k in e["items"]],
        }
        for e in entries
    ]


def clean_layout(data):
    """The layout as posted by the menu page, with only known menus and items, and without names equal to the
    standard name (so improved standard names and translations still reach those)."""
    from django.utils import translation

    languages = [code for code, _name in settings.LANGUAGES]
    builtin = {s["key"]: s for s in SECTIONS}
    home = {item_key(i): i for s in SECTIONS for i in s["items"]}

    def texts(posted, standard):
        result = {}
        for lang in languages:
            text = str((posted or {}).get(lang) or "").strip()[:TITLE_LENGTH]
            with translation.override(lang):
                if text and text != str(standard):
                    result[lang] = text
        return result

    sections, seen_sections, seen_items = [], set(), set()
    for saved in (data or {}).get("sections") or []:
        key = str(saved.get("key"))
        if key in seen_sections or not (key in builtin or CUSTOM_KEY.match(key)):
            continue
        seen_sections.add(key)
        items = [k for k in saved.get("items") or [] if k in home and k not in seen_items]
        seen_items.update(items)
        standard = builtin[key]["title"] if key in builtin else _("New menu")
        sections.append({"key": key, "title": texts(saved.get("title"), standard), "items": items})
    names = {}
    for key, posted in ((data or {}).get("items") or {}).items():
        if key in home and (found := texts(posted, home[key]["title"])):
            names[key] = found
    return {"sections": sections, "items": names}


def ordered_keys(user, sections=None):
    """The main menus in the order of this user: their own order (dashboard → Customise) first, then the rest
    in the order of the menu for everyone."""
    from .models import DashboardLayout

    keys = [s["key"] for s in (sections if sections is not None else menu())]
    saved = DashboardLayout.objects.filter(user=user).values_list("sidebar_order", flat=True).first() or []
    return [k for k in saved if k in keys] + [k for k in keys if k not in saved]


def _visible(request, section):
    return any(not i.get("permission") or i["permission"](request) for i in section["items"])


def sidebar(request):
    """Called by unfold (UNFOLD["SIDEBAR"]["navigation"]) on every admin page. Main menus without anything
    this user may open are left out."""
    sections = menu()
    if not request.user.is_authenticated:
        return sections
    by_key = {s["key"]: s for s in sections}
    return [by_key[k] for k in ordered_keys(request.user, sections) if _visible(request, by_key[k])]


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
