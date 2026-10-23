import datetime
import random
from decimal import Decimal

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.customers.models import Customer, CustomerType
from apps.licences.models import (
    Category, HardwareClass, HardwareSystem, Licence, LicenceSettings, OptionType, SupportPack, SupportPeriod,
    SupportService, Vendor, add_years,
)

from .conftest import make_user

TODAY = timezone.localdate()


@pytest.fixture
def catalogue(db):
    cat = Category.objects.create(name="Server")
    disk = OptionType.objects.create(name="Schijf", internal=True)
    tape = OptionType.objects.create(name="Tape", internal=False)
    cat.option_types.set([disk, tape])
    cls = HardwareClass.objects.create(name="Klasse A")
    hp = Vendor.objects.create(name="HP", product_nr_regex=r"\d{6}-B21", product_nr_help="Bijv. 826684-B21")
    system = HardwareSystem.objects.create(vendor=hp, hardware_class=cls, name="DL380")
    service = SupportService.objects.create(abbreviation="NBD", name="On site")
    three = SupportPeriod.objects.create(years=3)
    post = SupportPeriod.objects.create(years=1, post_warranty=True)
    pack = SupportPack.objects.create(category=cat, hardware_class=cls, service=service, period=three, price=Decimal("495"),
                                      max_internal_options=2, max_external_options=1, description="Server 3 jaar")
    post_pack = SupportPack.objects.create(category=cat, hardware_class=cls, service=service, period=post, description="Na garantie")
    return {"category": cat, "pack": pack, "post_pack": post_pack, "system": system, "disk": disk, "tape": tape, "hp": hp}


@pytest.fixture
def reseller(db):
    return Customer.objects.create(name="Reseller BV", number="10", status=Customer.Status.ACTIVE,
                                   customer_type=CustomerType.objects.get(is_reseller=True))


@pytest.fixture
def end_customer_type(db):
    return Customer.objects.create(name="Eindklant BV", number="11", status=Customer.Status.ACTIVE,
                                   customer_type=CustomerType.objects.filter(is_reseller=False).first())


# --- numbers -------------------------------------------------------------------

def test_licence_numbers_in_old_format(catalogue, reseller):
    first, second = Licence.create_for(catalogue["pack"], reseller, 2)
    yy = f"{TODAY.year % 100:02d}"
    assert first.number == f"{yy}A0001" and second.number == f"{yy}A0002"
    assert len(first.suffix) == 3 and "O" not in first.suffix
    assert first.full_number == f"{first.number}{first.suffix}-1"


def test_suffix_avoids_forbidden_words():
    rules = LicenceSettings(forbidden_suffixes="AAA", suffix_length=3)

    class Rigged(random.Random):
        values = iter("AAABCD")

        def choice(self, seq):
            return next(self.values)

    assert rules.new_suffix(Rigged()) == "BCD"


def test_find_ignores_case_and_assumes_sequence_1(catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    assert Licence.find(lic.full_number.lower()) == lic
    assert Licence.find(f" {lic.number}{lic.suffix.lower()} ") == lic
    assert Licence.find("nonsense") is None


def test_add_years_handles_leap_day():
    assert add_years(datetime.date(2024, 2, 29), 1) == datetime.date(2025, 2, 28)


# --- cover dates (previous webshop rules) ------------------------------------------------

def test_cover_from_purchase_in_past(catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    purchase = TODAY - datetime.timedelta(days=100)
    assert lic.cover_dates(purchase, None) == (TODAY, add_years(purchase, 3))


def test_cover_from_registration_date_for_category_setting(catalogue, reseller):
    catalogue["category"].end_date_from = Category.EndDateFrom.REGISTRATION
    catalogue["category"].save()
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    assert lic.cover_dates(TODAY - datetime.timedelta(days=100), None) == (TODAY, add_years(TODAY, 3))


def test_purchase_too_old_or_too_far_ahead(catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    with pytest.raises(ValidationError):
        lic.cover_dates(TODAY - datetime.timedelta(days=1921), None)
    with pytest.raises(ValidationError):
        lic.cover_dates(TODAY + datetime.timedelta(days=41), None)
    future = TODAY + datetime.timedelta(days=10)
    assert lic.cover_dates(future, None) == (future, add_years(future, 3))


def test_post_warranty_uses_start_date_minus_one_day(catalogue, reseller):
    lic = Licence.create_for(catalogue["post_pack"], reseller)[0]
    start = TODAY + datetime.timedelta(days=5)
    assert lic.cover_dates(None, start) == (start, add_years(start, 1) - datetime.timedelta(days=1))
    with pytest.raises(ValidationError):
        lic.cover_dates(None, TODAY + datetime.timedelta(days=96))
    with pytest.raises(ValidationError):
        lic.cover_dates(None, None)


# --- admin -------------------------------------------------------------------------

def test_admin_creates_several_licences(client, site, catalogue, reseller, beheerder):
    client.force_login(beheerder)
    response = client.post("/beheer/licences/licence/add/", {
        "pack": catalogue["pack"].pk, "customer": reseller.pk, "order_reference": "PO-9", "quantity": "3",
    })
    assert response.status_code == 302, response.content.decode()[:2000]
    assert Licence.objects.filter(customer=reseller, order_reference="PO-9").count() == 3


def test_employee_role_can_only_view_licences(client, site, catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get(f"/beheer/licences/licence/{lic.pk}/change/").status_code == 200
    assert client.get("/beheer/licences/licence/add/").status_code == 403


# --- registration wizard ---------------------------------------------------------

def run_wizard(client, lic, device=None, options=None, reseller=None):
    client.post("/registreren/", {"number": lic.full_number})
    client.post("/registreren/eindklant/", {"email": "eind@klant.test", "reference": "REF-1"})
    if reseller is not None:
        client.post("/registreren/reseller/", reseller)
    data = {"system": lic.pack.hardware_class.systems.first().pk, "product_nr": "826684-B21", "description": "Server",
            "serial_nr": "SN123", "purchase_date": (TODAY - datetime.timedelta(days=30)).isoformat()}
    data.update(device or {})
    response = client.post("/registreren/apparaat/", data)
    if options is not None:
        response = client.post("/registreren/opties/", options)
    return response


def option_rows(*rows, total=3):
    data = {"options-TOTAL_FORMS": str(total), "options-INITIAL_FORMS": "0", "options-MIN_NUM_FORMS": "0",
            "options-MAX_NUM_FORMS": str(total)}
    for i, row in enumerate(rows):
        data.update({f"options-{i}-{k}": v for k, v in row.items()})
    return data


def test_full_registration(client, site, catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    LicenceSettings.objects.filter(pk=1).update(notify_emails="service@example.test")
    run_wizard(client, lic, options=option_rows(
        {"option_type": catalogue["disk"].pk, "quantity": "2", "description": "1 TB"},
        {"option_type": catalogue["tape"].pk, "vendor": catalogue["hp"].pk, "quantity": "1", "description": "LTO"},
    ))
    response = client.post("/registreren/controle/")
    assert response.status_code == 302 and response["Location"] == "/registreren/klaar/"
    lic.refresh_from_db()
    assert lic.registered_on and lic.status == Licence.Status.REGISTERED
    assert lic.vendor == catalogue["hp"] and lic.system == catalogue["system"]
    assert lic.end_date == add_years(TODAY - datetime.timedelta(days=30), 3)
    assert sorted(lic.options.values_list("serial_nr", flat=True)) == ["SN123/001", "SN123/002", "SN123/003"]
    message = mail.outbox[0]
    assert message.to == ["eind@klant.test"] and message.bcc == ["service@example.test"]
    assert lic.full_number in message.subject and "SN123/003" in message.body


def test_reseller_step_for_non_reseller_customer(client, site, catalogue, end_customer_type):
    lic = Licence.create_for(catalogue["pack"], end_customer_type)[0]
    client.post("/registreren/", {"number": lic.full_number})
    response = client.post("/registreren/eindklant/", {"email": "eind@klant.test"})
    assert response["Location"] == "/registreren/reseller/"
    assert client.get("/registreren/apparaat/").status_code == 302  # reseller step not done yet
    run_wizard(client, lic, reseller={"name": "Wederverkoper", "address": "Straat 1", "postal_code": "1000 AA",
                                       "city": "Utrecht", "phone": "030-1"}, options=option_rows())
    client.post("/registreren/controle/")
    lic.refresh_from_db()
    assert lic.reseller_name == "Wederverkoper" and lic.registered_on


def test_wizard_errors(client, site, catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    page = client.post("/registreren/", {"number": "26Z9999XXX-1"}).content.decode()
    assert "No licence" in page or "Er is geen licentie" in page
    catalogue["pack"].registration_required = False
    catalogue["pack"].save()
    assert client.post("/registreren/", {"number": lic.full_number}).status_code == 200


def test_already_registered_licence(client, site, catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    lic.registered_on = timezone.now()
    lic.save()
    response = client.post("/registreren/", {"number": lic.full_number})
    assert response.status_code == 200 and "registreren/eindklant" not in response.get("Location", "")


def test_contact_category(client, site, catalogue, reseller):
    catalogue["category"].contact_to_register = True
    catalogue["category"].save()
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    page = client.post("/registreren/", {"number": lic.full_number}).content.decode()
    assert LicenceSettings.load().contact_text in page


def test_article_number_check(client, site, catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    response = run_wizard(client, lic, device={"product_nr": "fout"})
    assert response.status_code == 200 and "826684-B21" in response.content.decode()


def test_option_limits(client, site, catalogue, reseller):
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    response = run_wizard(client, lic, options=option_rows({"option_type": catalogue["disk"].pk, "quantity": "3",
                                                            "description": "te veel"}))
    assert response.status_code == 200
    assert client.get("/registreren/controle/").status_code == 302  # options step not completed


def test_monitor_step(client, site, catalogue, reseller):
    catalogue["pack"].requires_monitor = True
    catalogue["pack"].save()
    lic = Licence.create_for(catalogue["pack"], reseller)[0]
    response = run_wizard(client, lic)
    assert response["Location"] == "/registreren/beeldscherm/"
    client.post("/registreren/beeldscherm/", {"vendor": catalogue["hp"].pk, "description": "24 inch", "serial_nr": "MON1"})
    client.post("/registreren/opties/", option_rows())
    client.post("/registreren/controle/")
    monitor = lic.options.get(option_type__is_monitor=True)
    assert monitor.serial_nr == "MON1"


def test_licence_numbers_are_a_source_for_the_check(catalogue, reseller):
    from apps.licences.numbering import licence_numbers
    from apps.numbering.models import NumberSequence

    Licence.create_for(catalogue["pack"], reseller, 2)
    assert sorted(licence_numbers(NumberSequence.objects.get(key="licence"))) == [1, 2]


def test_home_page_links_to_registration(client, site):
    assert 'href="/registreren/"' in client.get("/").content.decode()
