import importlib
from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib import admin

from apps.customers.models import Contact, Customer
from apps.printing.models import Printer, PrintingSettings, PrintQuote
from apps.telephony.admin import CustomerSwitchInline
from apps.telephony.models import Category, Item, Quote, TelephonyCustomer, TelephonySettings

from .conftest import make_user


@pytest.fixture
def phones(db):
    rules = TelephonySettings.load()
    rules.enabled, rules.installation_costs, rules.default_margin = True, Decimal("25"), Decimal("10")
    rules.save()
    devices, licences = Category.objects.create(name="Toestellen", position=1), Category.objects.create(name="Licenties", position=2)
    phone = Item.objects.create(category=devices, name="IP-toestel", hire_per_month=Decimal("2.60"), buy_price=Decimal("132"))
    licence = Item.objects.create(category=licences, name="Gebruikerslicentie", hire_per_month=Decimal("5.90"),
                                  buy_per_month=Decimal("5.90"))
    licence.quantity_from.set([phone])
    customer = Customer.objects.create(name="Reseller BV", number="5", status=Customer.Status.ACTIVE)
    user = make_user("verkoop@reseller.test")
    Contact.objects.create(customer=customer, user=user, last_name="Verkoop", email=user.email)
    return {"phone": phone, "licence": licence, "customer": customer, "user": user}


def test_calculator_counts_licences_and_compares_hire_with_buy(client, site, phones):
    client.force_login(phones["user"])
    response = client.post("/my/telephony/", {"action": "calculate", f"q-{phones['phone'].pk}": "4",
                                                f"q-{phones['licence'].pk}": "0", "margin_hire": "10", "margin_buy": "0"})
    totals = response.context["totals"]
    # hire: 4 × 2.60 + 4 × 5.90 = 34.00, + 10% = 2.86 + 6.49 each → 11.44 + 25.96
    assert totals["hire_per_month"] == Decimal("37.40") and totals["hire_once"] == Decimal("25")
    assert totals["buy_once"] == Decimal("553.00") and totals["buy_per_month"] == Decimal("23.60")  # 4 × 132 + 25


def test_save_quote_and_see_it(client, site, phones):
    client.force_login(phones["user"])
    response = client.post("/my/telephony/", {"action": "save", f"q-{phones['phone'].pk}": "2", "reference": "Kantoor",
                                                "view": "reseller", "margin_hire": "10", "margin_buy": "10"})
    quote = Quote.objects.get()
    assert response.status_code == 302 and quote.customer == phones["customer"] and quote.lines.count() == 2
    page = client.get(f"/my/telephony/quotes/{quote.pk}/")
    assert page.status_code == 200 and "Gebruikerslicentie" in page.content.decode()
    # Later price changes do not change a saved quote.
    Item.objects.filter(pk=phones["phone"].pk).update(hire_per_month=Decimal("99"))
    assert quote.totals()["hire_per_month"] == Decimal("18.70")  # 2 × (2.86 + 6.49)


def test_calculator_off_or_other_customer(client, site, phones):
    client.force_login(phones["user"])
    client.post("/my/telephony/", {"action": "save", f"q-{phones['phone'].pk}": "1"})
    quote = Quote.objects.get()
    other = Customer.objects.create(name="Ander", number="6", status=Customer.Status.ACTIVE)
    other_user = make_user("ander@x.test")
    Contact.objects.create(customer=other, user=other_user, last_name="A", email=other_user.email)
    client.force_login(other_user)
    assert client.get(f"/my/telephony/quotes/{quote.pk}/").status_code == 404
    TelephonySettings.objects.filter(pk=1).update(enabled=False)
    assert client.get("/my/telephony/").status_code == 403


def test_customer_without_a_switch_uses_telephony_and_can_be_switched_off(client, site, phones):
    client.force_login(phones["user"])
    assert client.get("/my/telephony/").status_code == 200
    assert "/my/telephony/" in client.get("/my/").content.decode()
    client.post("/my/telephony/", {"action": "save", f"q-{phones['phone'].pk}": "1"})
    quote = Quote.objects.get()
    TelephonyCustomer.objects.create(customer=phones["customer"], enabled=False)
    for url in ("/my/telephony/", "/my/telephony/quotes/", f"/my/telephony/quotes/{quote.pk}/"):
        assert client.get(url).status_code == 403, url
    assert "/my/telephony/" not in client.get("/my/").content.decode()
    assert Quote.objects.filter(pk=quote.pk).exists()
    TelephonyCustomer.objects.filter(customer=phones["customer"]).update(enabled=True)
    assert client.get("/my/telephony/").status_code == 200


def test_customer_page_leaves_out_quotes_of_a_customer_switched_off(client, site, phones, beheerder):
    Quote.objects.create(customer=phones["customer"], reference="Kantoor-offerte")
    client.force_login(beheerder)
    url = f"/admin/customers/customer/{phones['customer'].pk}/change/"
    assert "Kantoor-offerte" in client.get(url).content.decode()
    TelephonyCustomer.objects.create(customer=phones["customer"], enabled=False)
    assert "Kantoor-offerte" not in client.get(url).content.decode()


def test_telephony_off_hides_it_in_the_admin_but_not_its_settings(client, site, phones, beheerder):
    Quote.objects.create(customer=phones["customer"], reference="Kantoor-offerte")
    client.force_login(beheerder)
    TelephonySettings.objects.filter(pk=1).update(enabled=False)
    for url in ("telephony/quote", "telephony/item", "telephony/category"):
        assert client.get(f"/admin/{url}/").url == "/admin/telephony/telephonysettings/", url
    assert client.get(f"/admin/telephony/quote/{Quote.objects.get().pk}/change/").status_code in (302, 403)
    assert client.get("/admin/telephony/item/add/").status_code == 403
    page = client.get("/admin/telephony/telephonysettings/", follow=True)
    assert page.status_code == 200
    menu = page.content.decode()
    assert "/admin/telephony/telephonysettings/" in menu and "/admin/telephony/quote/" not in menu
    customer_page = client.get(f"/admin/customers/customer/{phones['customer'].pk}/change/").content.decode()
    assert "Kantoor-offerte" not in customer_page and "telephony-0-enabled" not in customer_page
    assert Quote.objects.exists()


def test_customer_form_keeps_the_switch_off_once_saved_off(db, phones):
    form = CustomerSwitchInline(Customer, admin.site).get_formset(None).form
    assert form().fields["enabled"].initial is True
    unchanged = form(data={"enabled": "on"}, empty_permitted=True, use_required_attribute=False)
    assert not unchanged.has_changed()  # so a customer form saved as it is makes no row, and the customer stays on
    unticked = form(data={}, empty_permitted=True, use_required_attribute=False)
    assert unticked.has_changed()


def test_printing_archive_is_off_by_default_with_its_settings_still_there(client, site, phones, beheerder):
    PrintQuote.objects.create(number="12", customer=phones["customer"], reference="Kantoor")
    client.force_login(beheerder)
    assert not PrintingSettings.load().enabled
    for url in ("printing/printquote", "printing/printer", "printing/printcontract", "printing/suppliesorder",
                "printing/consumable", "printing/supportplan"):
        assert client.get(f"/admin/{url}/").url == "/admin/printing/printingsettings/", url
    page = client.get("/admin/printing/printingsettings/", follow=True)
    assert page.status_code == 200
    menu = page.content.decode()
    assert "/admin/printing/printingsettings/" in menu and "/admin/printing/printquote/" not in menu
    assert "Kantoor" not in client.get(f"/admin/customers/customer/{phones['customer'].pk}/change/").content.decode()
    assert PrintQuote.objects.exists()


def test_installation_with_printing_data_keeps_the_archive_visible(db):
    migration = importlib.import_module("apps.printing.migrations.0004_existing_archive_and_permissions")
    migration.keep_existing_archive_visible(apps, None)
    assert not PrintingSettings.load().enabled
    Printer.objects.create(name="Oude printer")
    migration.keep_existing_archive_visible(apps, None)
    assert PrintingSettings.load().enabled


def test_admin_pages_and_printing_is_read_only(client, site, phones, beheerder):
    PrintingSettings.objects.update_or_create(pk=1, defaults={"enabled": True})
    PrintQuote.objects.create(number="12", customer=phones["customer"], reference="Kantoor")
    client.force_login(beheerder)
    for url in ("telephony/quote", "telephony/item", "telephony/category", "printing/printquote", "printing/printer",
                "printing/printcontract", "printing/suppliesorder", "printing/consumable", "printing/supportplan"):
        assert client.get(f"/admin/{url}/").status_code == 200, url
    assert client.get("/admin/printing/printquote/add/").status_code == 403
    page = client.get(f"/admin/customers/customer/{phones['customer'].pk}/change/").content.decode()
    assert "Kantoor" in page
