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
    page = client.get("/beheer/").content.decode()
    assert 'data-key="stats"' in page and "Te keuren aanmeldingen" in page
    assert "pd-stat-warn" in page  # a sign-up is waiting


def test_dashboard_blocks_follow_permissions(client, site):
    client.force_login(make_user("leeg@example.test", staff=True, role="Medewerker"))
    page = client.get("/beheer/").content.decode()
    assert 'data-key="pending_signups"' in page  # Medewerker may view customers
    assert "Nummerreeksen met problemen" not in page


def test_layout_is_saved_per_user_and_can_be_reset(client, site, beheerder):
    client.force_login(beheerder)
    order = ["recent_actions", "stats", "pending_signups", "recent_registrations", "ending_licences"]
    client.post("/beheer/dashboard/layout/", json.dumps({"order": order, "hidden": ["ending_licences", "bogus"]}),
                content_type="application/json")
    layout = DashboardLayout.objects.get(user=beheerder)
    assert layout.order[0] == "recent_actions" and layout.hidden == ["ending_licences"]
    page = client.get("/beheer/").content.decode()
    assert page.index('data-key="recent_actions"') < page.index('data-key="stats"')
    assert 'class="pd-widget' in page and 'data-key="ending_licences" draggable' not in page
    client.post("/beheer/dashboard/reset/")
    assert not DashboardLayout.objects.filter(user=beheerder).exists()


def test_layout_endpoints_need_staff_and_post(client, site):
    assert client.post("/beheer/dashboard/reset/").status_code == 302  # to login
    client.force_login(make_user("klant@example.test"))
    assert client.post("/beheer/dashboard/reset/").status_code == 302


# --- reports ---------------------------------------------------------------------

def test_report_numbers(client, site, beheerder):
    make_licences(2, margin=Decimal("10"))
    client.force_login(beheerder)
    response = client.get("/beheer/rapportage/")
    report = response.context["report"]
    assert report["totals"]["count"] == 2
    assert report["totals"]["revenue"] == Decimal("180.00")  # 2 × 100 minus 10 % discount
    assert report["totals"]["margin"] == Decimal("60.00")  # 180 − 2 × 60
    assert "<svg" in response.content.decode()


def test_report_needs_permission(client, site):
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get("/beheer/rapportage/").status_code == 403


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
