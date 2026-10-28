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
        "title": _("Printing services"),
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
GROUP = "group:"  # in a main menu's items: another main menu, shown there as a fold-out group with its items
TITLE_LENGTH = 60


def item_key(item):
    """An item is known by its address, e.g. /admin/invoices/invoicesettings/."""
    return str(item["link"])


def _title(texts, standard, any_language=False):
    """The saved name in the language of the page, otherwise the standard name (translated). An own main menu
    has no translated standard name, so there a name saved in another language comes first."""
    def resolve():
        texts_ = texts or {}
        own = texts_.get((get_language() or "")[:2])
        if not own and any_language:
            own = next((t for t in texts_.values() if t), "")
        return own or str(standard)

    return lazy(resolve, str)()


def _is_custom(key):
    return not any(s["key"] == key for s in SECTIONS)


def _standard_title(key):
    return next((s["title"] for s in SECTIONS if s["key"] == key), _("New menu"))


def _structure(layout):
    """The saved main menus [(key, titles, [item keys and "group:<key>"])] with only known menus and items, each
    item once, and groups one level deep (the sidebar has no deeper level): a main menu inside another one
    cannot hold groups itself."""
    builtin = {s["key"] for s in SECTIONS}
    home = {item_key(i) for s in SECTIONS for i in s["items"]}
    entries, seen_items = [], set()
    for saved in (layout or {}).get("sections") or []:
        key = str(saved.get("key"))
        if not (key in builtin or CUSTOM_KEY.match(key)) or any(e[0] == key for e in entries):
            continue
        refs = []
        for ref in saved.get("items") or []:
            ref = str(ref)
            if ref.startswith(GROUP) or (ref in home and ref not in seen_items):
                refs.append(ref)
                seen_items.add(ref)
        entries.append((key, saved.get("title") or {}, refs))
    keys = {e[0] for e in entries}
    parent_of = {}
    for key, _titles, refs in entries:
        for ref in refs:
            child = ref[len(GROUP):]
            if ref.startswith(GROUP) and child in keys and child != key and child not in parent_of:
                parent_of[child] = key
    parent_of = {child: parent for child, parent in parent_of.items() if parent not in parent_of}
    return [
        (key, titles, [r for r in refs if not r.startswith(GROUP) or parent_of.get(r[len(GROUP):]) == key])
        for key, titles, refs in entries
    ], parent_of


def menu(layout=None):
    """All main menus with their items, after the changes saved under Configuration → Menu. A main menu placed
    inside another one is an item there with its own items (a fold-out group), marked with "group": key.

    Main menus and items that are new in PackDesk (not in the saved layout) appear in their standard place."""
    if layout is None:
        from .models import AdminMenu

        layout = AdminMenu.load().layout
    home = {item_key(i): (s["key"], i) for s in SECTIONS for i in s["items"]}
    names = (layout or {}).get("items") or {}
    entries, parent_of = _structure(layout)
    for key in DEFAULT_ORDER:
        if not any(e[0] == key for e in entries):
            entries.append((key, {}, []))
    placed = {ref for _key, _titles, refs in entries for ref in refs}
    for key, (section, _item) in home.items():
        if key not in placed:
            next(e for e in entries if e[0] == section)[2].append(key)
    by_key = {e[0]: e for e in entries}

    def items(refs):
        result = []
        for ref in refs:
            if ref.startswith(GROUP):
                child_key, child_titles, child_refs = by_key[ref[len(GROUP):]]
                children = items(child_refs)
                if children:
                    result.append({
                        "title": _title(child_titles, _standard_title(child_key), _is_custom(child_key)),
                        "icon": "folder", "link": "#",
                        "group": child_key, "items": children,
                        "permission": lambda request, kids=children: any(
                            not k.get("permission") or k["permission"](request) for k in kids),
                    })
            else:
                result.append({**home[ref][1], "title": _title(names.get(ref), home[ref][1]["title"])})
        return result

    return [
        {
            "key": key, "collapsible": True, "custom": _is_custom(key),
            "title": _title(titles, _standard_title(key), _is_custom(key)), "items": items(refs),
        }
        for key, titles, refs in entries
        if key not in parent_of
    ]


def clean_layout(data):
    """The layout as posted by the menu page, with only known menus and items, and without names equal to the
    standard name (so improved standard names and translations still reach those)."""
    from django.utils import translation

    languages = [code for code, _name in settings.LANGUAGES]
    home = {item_key(i): i for s in SECTIONS for i in s["items"]}

    def texts(posted, standard):
        result = {}
        for lang in languages:
            text = str((posted or {}).get(lang) or "").strip()[:TITLE_LENGTH]
            with translation.override(lang):
                if text and text != str(standard):
                    result[lang] = text
        return result

    entries, _parent_of = _structure(data if isinstance(data, dict) else {})
    sections = [{"key": key, "title": texts(titles, _standard_title(key)), "items": refs} for key, titles, refs in entries]
    names = {}
    for key, posted in ((data or {}).get("items") or {}).items():
        if key in home and (found := texts(posted, home[key]["title"])):
            names[key] = found
    return {"sections": sections, "items": names}


def flat_items(section):
    """The items of a main menu, with those of its fold-out groups."""
    for item in section["items"]:
        yield from item["items"] if "group" in item else [item]


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
        items = [i for i in flat_items(section) if not i.get("permission") or i["permission"](request)]
        if any(str(i["link"]).startswith(prefix) for i in items):
            sections.append({"title": section["title"], "items": [{**i, "link": str(i["link"])} for i in items]})
    if not sections:
        return admin.site.__class__.app_index(admin.site, request, app_label, extra_context)
    return TemplateResponse(request, "admin/packdesk/section_index.html", {
        **admin.site.each_context(request), "title": sections[0]["title"], "sections": sections,
    })
