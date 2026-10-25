from decimal import Decimal

import pytest

from apps.customers.models import Contact, Customer
from apps.printing.models import PrintQuote
from apps.telephony.models import Category, Item, Quote, TelephonySettings

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
    response = client.post("/mijn/telefonie/", {"action": "calculate", f"q-{phones['phone'].pk}": "4",
                                                f"q-{phones['licence'].pk}": "0", "margin_hire": "10", "margin_buy": "0"})
    totals = response.context["totals"]
    # hire: 4 × 2.60 + 4 × 5.90 = 34.00, + 10% = 2.86 + 6.49 each → 11.44 + 25.96
    assert totals["hire_per_month"] == Decimal("37.40") and totals["hire_once"] == Decimal("25")
    assert totals["buy_once"] == Decimal("553.00") and totals["buy_per_month"] == Decimal("23.60")  # 4 × 132 + 25


def test_save_quote_and_see_it(client, site, phones):
    client.force_login(phones["user"])
    response = client.post("/mijn/telefonie/", {"action": "save", f"q-{phones['phone'].pk}": "2", "reference": "Kantoor",
                                                "view": "reseller", "margin_hire": "10", "margin_buy": "10"})
    quote = Quote.objects.get()
    assert response.status_code == 302 and quote.customer == phones["customer"] and quote.lines.count() == 2
    page = client.get(f"/mijn/telefonie/offertes/{quote.pk}/")
    assert page.status_code == 200 and "Gebruikerslicentie" in page.content.decode()
    # Later price changes do not change a saved quote.
    Item.objects.filter(pk=phones["phone"].pk).update(hire_per_month=Decimal("99"))
    assert quote.totals()["hire_per_month"] == Decimal("18.70")  # 2 × (2.86 + 6.49)


def test_calculator_off_or_other_customer(client, site, phones):
    client.force_login(phones["user"])
    client.post("/mijn/telefonie/", {"action": "save", f"q-{phones['phone'].pk}": "1"})
    quote = Quote.objects.get()
    other = Customer.objects.create(name="Ander", number="6", status=Customer.Status.ACTIVE)
    other_user = make_user("ander@x.test")
    Contact.objects.create(customer=other, user=other_user, last_name="A", email=other_user.email)
    client.force_login(other_user)
    assert client.get(f"/mijn/telefonie/offertes/{quote.pk}/").status_code == 404
    TelephonySettings.objects.filter(pk=1).update(enabled=False)
    assert client.get("/mijn/telefonie/").status_code == 403


def test_admin_pages_and_printing_is_read_only(client, site, phones, beheerder):
    PrintQuote.objects.create(number="12", customer=phones["customer"], reference="Kantoor")
    client.force_login(beheerder)
    for url in ("telephony/quote", "telephony/item", "telephony/category", "printing/printquote", "printing/printer",
                "printing/printcontract", "printing/suppliesorder", "printing/consumable", "printing/supportplan"):
        assert client.get(f"/beheer/{url}/").status_code == 200, url
    assert client.get("/beheer/printing/printquote/add/").status_code == 403
    page = client.get(f"/beheer/customers/customer/{phones['customer'].pk}/change/").content.decode()
    assert "Kantoor" in page
