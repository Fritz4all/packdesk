import json
from decimal import Decimal

from apps.customers.models import Customer
from apps.dashboard.models import DashboardLayout
from apps.dashboard.search import search_everything
from apps.licences.models import Category, HardwareClass, Licence, SupportPack, SupportPeriod, SupportService

from .conftest import make_user


def make_licences(n=2, margin=Decimal("10")):
    cat = Category.objects.create(name="Server")
    pack = SupportPack.objects.create(
        category=cat, hardware_class=HardwareClass.objects.create(name="A"),
        service=SupportService.objects.create(abbreviation="X", name="On site"),
        period=SupportPeriod.objects.create(years=3), price=Decimal("100"), cost_price=Decimal("60"),
    )
    customer = Customer.objects.create(name="Koper BV", number="5", status=Customer.Status.ACTIVE, margin_packs=margin)
    return Licence.create_for(pack, customer, n)


# --- dashboard -------------------------------------------------------------------

def test_dashboard_shows_totals(client, site, beheerder):
    Customer.objects.create(name="Wacht", status=Customer.Status.PENDING)
    make_licences(2)
    client.force_login(beheerder)
    page = client.get("/admin/").content.decode()
    assert 'data-key="stats"' in page and "Te keuren aanmeldingen" in page
    assert "pd-stat-warn" in page  # a sign-up is waiting


def test_dashboard_blocks_follow_permissions(client, site):
    client.force_login(make_user("leeg@example.test", staff=True, role="Medewerker"))
    page = client.get("/admin/").content.decode()
    assert 'data-key="pending_signups"' in page  # Medewerker may view customers
    assert "Nummerreeksen met problemen" not in page


def test_layout_is_saved_per_user_and_can_be_reset(client, site, beheerder):
    client.force_login(beheerder)
    order = ["recent_actions", "stats", "pending_signups", "recent_registrations", "ending_licences"]
    client.post("/admin/dashboard/layout/", json.dumps({"order": order, "hidden": ["ending_licences", "bogus"]}),
                content_type="application/json")
    layout = DashboardLayout.objects.get(user=beheerder)
    assert layout.order[0] == "recent_actions" and layout.hidden == ["ending_licences"]
    page = client.get("/admin/").content.decode()
    assert page.index('data-key="recent_actions"') < page.index('data-key="stats"')
    assert 'class="pd-widget' in page and 'data-key="ending_licences" draggable' not in page
    client.post("/admin/dashboard/reset/")
    assert not DashboardLayout.objects.filter(user=beheerder).exists()


def test_layout_endpoints_need_staff_and_post(client, site):
    assert client.post("/admin/dashboard/reset/").status_code == 302  # to login
    client.force_login(make_user("klant@example.test"))
    assert client.post("/admin/dashboard/reset/").status_code == 302


# --- reports ---------------------------------------------------------------------

def test_report_numbers(client, site, beheerder):
    make_licences(2, margin=Decimal("10"))
    client.force_login(beheerder)
    response = client.get("/admin/reports/")
    report = response.context["report"]
    assert report["totals"]["count"] == 2
    assert report["totals"]["revenue"] == Decimal("180.00")  # 2 × 100 minus 10 % discount
    assert report["totals"]["margin"] == Decimal("60.00")  # 180 − 2 × 60
    assert "<svg" in response.content.decode()


def test_report_needs_permission(client, site):
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get("/admin/reports/").status_code == 403


# --- global search ---------------------------------------------------------------------

def test_global_search_finds_part_of_licence_number_and_customer_data(rf, site, beheerder):
    lic = make_licences(1)[0]
    request = rf.get("/")
    request.user = beheerder
    titles = [r.title for r in search_everything(request, lic.suffix.lower())]
    assert lic.full_number in titles
    customer = Customer.objects.get(name="Koper BV")
    customer.vat_number = "NL123456789B01"
    customer.save()
    assert any("Koper BV" in t for t in [r.title for r in search_everything(request, "123456789b01")])


def test_global_search_respects_permissions(rf, site, catalogue_free_user=None):
    make_licences(1)
    user = make_user("geen@example.test", staff=True, role="Medewerker")
    request = rf.get("/")
    request.user = user
    assert not [r for r in search_everything(request, "koper") if "Gebruiker" in r.description]


def test_report_custom_range_and_month_drilldown(client, site, beheerder):
    from django.utils import timezone

    licences = make_licences(2)
    old = licences[0]
    Licence.objects.filter(pk=old.pk).update(created_at=timezone.now().replace(year=timezone.now().year - 2))
    client.force_login(beheerder)
    today = timezone.localdate()
    response = client.get("/admin/reports/", {"from": today.replace(day=1).isoformat(), "to": today.isoformat()})
    assert response.context["period"] == "custom"
    assert response.context["report"]["totals"]["count"] == 1
    page = response.content.decode()
    assert licences[1].full_number in page and old.full_number not in page
    assert f"?from={today.replace(day=1).isoformat()}" in page  # month bar links to that month


def test_report_active_period_is_highlighted(client, site, beheerder):
    client.force_login(beheerder)
    page = client.get("/admin/reports/", {"period": "this_year"}).content.decode()
    assert 'value="this_year" class="pd-btn pd-btn-primary"' in page


def test_configuration_is_last_in_menu_by_default(rf, site, beheerder):
    from apps.dashboard.navigation import sidebar

    request = rf.get("/")
    request.user = beheerder
    assert [s["key"] for s in sidebar(request)][-1] == "configuration"


def test_menu_sections_can_be_reordered_per_user(client, site, beheerder, rf):
    from apps.dashboard.navigation import sidebar

    client.force_login(beheerder)
    new = ["configuration", "users", "faults", "licences", "parts", "telephony", "printing", "orders", "customers", "overview"]
    client.post("/admin/dashboard/layout/", json.dumps({"sidebar": new + ["bogus"]}), content_type="application/json")
    request = rf.get("/")
    request.user = beheerder
    assert [s["key"] for s in sidebar(request)] == new
    other = make_user("ander@example.test", staff=True, role="Beheerder")
    request.user = other
    assert [s["key"] for s in sidebar(request)][0] == "overview"


def test_menu_page_moves_renames_and_adds_main_menus(client, site, beheerder, rf):
    from django.utils import translation

    from apps.dashboard.models import AdminMenu
    from apps.dashboard.navigation import sidebar

    client.force_login(beheerder)
    assert client.get("/admin/menu/").status_code == 200
    layout = {
        "sections": [
            {"key": "configuration", "title": {"nl": "Beheer"},
             "items": ["/admin/invoices/invoicesettings/", "/admin/siteconfig/sitesettings/"]},
            {"key": "custom-finance", "title": {"nl": "Financieel"}, "items": ["/admin/invoices/invoice/"]},
            {"key": "bogus", "items": ["/admin/customers/customer/"]},  # unknown main menus are dropped
            {"key": "orders", "title": {"nl": "Bestellingen en facturen"}, "items": ["/nope/"]},  # = standard name
        ],
        "items": {"/admin/invoices/invoice/": {"nl": "Alle facturen", "xx": "?"}, "/nope/": {"nl": "x"}},
    }
    client.post("/admin/menu/", {"layout": json.dumps(layout)})
    saved = AdminMenu.load().layout
    assert [s["key"] for s in saved["sections"]] == ["configuration", "custom-finance", "orders"]
    assert saved["sections"][2]["title"] == {} and saved["items"] == {"/admin/invoices/invoice/": {"nl": "Alle facturen"}}

    request = rf.get("/")
    request.user = beheerder
    with translation.override("nl"):
        menu = {s["key"]: s for s in sidebar(request)}
        keys = list(menu)
        assert keys[:2] == ["configuration", "custom-finance"]
        assert str(menu["configuration"]["title"]) == "Beheer"
        links = [str(i["link"]) for i in menu["configuration"]["items"]]
        assert links[:2] == ["/admin/invoices/invoicesettings/", "/admin/siteconfig/sitesettings/"]
        assert "/admin/numbering/numbersequence/" in links  # not placed: stays in its standard main menu
        assert [str(i["title"]) for i in menu["custom-finance"]["items"]] == ["Alle facturen"]
        assert "/admin/invoices/invoicesettings/" not in [str(i["link"]) for i in menu["orders"]["items"]]
    with translation.override("de"):
        assert str(menu["configuration"]["title"]) == "Konfiguration"  # no name of its own in German

    client.post("/admin/menu/", {"reset": "1"})
    assert AdminMenu.load().layout == {}


def test_main_menu_can_be_a_fold_out_group_in_another_one(client, site, beheerder):
    from django.utils import translation

    from apps.dashboard.navigation import clean_layout, menu

    layout = clean_layout({"sections": [
        {"key": "configuration", "items": ["group:orders", "/admin/siteconfig/sitesettings/", "group:configuration"]},
        {"key": "orders", "items": ["/admin/orders/order/", "group:parts"]},  # a group holds no groups
        {"key": "custom-shop", "title": {"en": "Shop"}, "items": ["/admin/customers/customer/"]},
    ]})
    assert layout["sections"][0]["items"] == ["group:orders", "/admin/siteconfig/sitesettings/"]
    assert layout["sections"][1]["items"] == ["/admin/orders/order/"]
    with translation.override("nl"):
        sections = {s["key"]: s for s in menu(layout)}
        assert "orders" not in sections and "parts" in sections
        group = sections["configuration"]["items"][0]
        assert str(group["title"]) == "Bestellingen en facturen"
        assert [str(i["link"]) for i in group["items"]][:2] == ["/admin/orders/order/", "/admin/invoices/invoice/"]
        assert str(sections["custom-shop"]["title"]) == "Shop"  # own menu: name from another language

    from apps.dashboard.models import AdminMenu

    AdminMenu.objects.update_or_create(pk=1, defaults={"layout": layout})
    client.force_login(beheerder)
    page = client.get("/admin/").content.decode()
    assert "subnavigationOpen" in page and "/admin/orders/order/" in page
    editor = client.get("/admin/menu/").context["menu_data"]
    configuration = next(s for s in editor if s["key"] == "configuration")
    assert configuration["items"][0]["key"] == "orders" and configuration["items"][0]["items"]
    assert client.get("/admin/orders/").status_code == 200  # section page finds items inside groups


def test_menu_page_needs_the_settings_rights(client, site):
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get("/admin/menu/").status_code == 403
    assert client.post("/admin/menu/", {"reset": "1"}).status_code == 403


def test_single_tiles_can_be_hidden(client, site, beheerder):
    client.force_login(beheerder)
    client.post("/admin/dashboard/layout/", json.dumps({"hidden_items": ["stats:active_customers", "nope:x"]}),
                content_type="application/json")
    assert DashboardLayout.objects.get(user=beheerder).hidden_items == ["stats:active_customers"]
    page = client.get("/admin/").content.decode()
    assert 'data-item="stats:active_customers"' in page  # offered again in the hidden panel
    assert 'pd-stat-wrap" data-item="stats:active_customers"' not in page
