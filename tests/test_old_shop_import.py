from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.core import mail

from apps.accounts.models import User
from apps.customers.models import Contact, Customer
from apps.invoices.models import Invoice, InvoicePayment
from apps.legacy.models import ExternalDatabase, ImportedRecord, ImportRun
from apps.legacy.old_shop.importer import run_import
from apps.legacy.old_shop.passwords import decrypt
from apps.licences.models import Category, HardwareClass, Licence, LicenceOption, SupportPack
from apps.numbering.models import NumberSequence
from apps.orders.models import Order, OrderLine

from .conftest import make_user
from .old_shop import make_old_shop

# Made with the previous webshop's own User.encrypt("Probeer-Wachtwoord-123!", SALT).
SALT = "8f3a1c9e2b7d4a60e5f1c3b9d2a7e4f0c1b8a9d3"
CRYPTED = "Sv6jWzgM0WlOdfXIRxVDSjK7WsHrkks3"

OLD = {
    "hw_support_category": [{"id": "cat1", "description": "Server", "explanation": "Servers"}],
    "hw_class": [{"id": "cls1", "name": "Klasse A", "position": 1}],
    "vendor": [{"id": "v1", "name": "Dell", "real_vendor": 1}],
    "hw_type": [{"id": "t1", "name": "Extra hardeschijf", "internal": 1}, {"id": "t2", "name": "Monitor", "internal": 0}],
    "hw_support_category_hw_type": [{"hw_support_category_id": "cat1", "hw_type_id": "t1"}],
    "hw_system": [{"id": "s1", "vendor_id": "v1", "hw_class_id": "cls1", "name": "R740", "warranty": 3}],
    "hw_support_period": [{"id": "p1", "duration": 3, "post_warranty": 0}],
    "hw_support_service": [{"id": "sv1", "abbreviation": "NBD", "service": "Next business day", "response": "8u",
                            "officehours": 1}],
    "hw_support_pack": [
        {"id": "pk1", "hw_support_category_id": "cat1", "hw_support_service_id": "sv1", "hw_support_period_id": "p1",
         "hw_class_id": "cls1", "price": "100.00", "enabled": 1, "code": "SRV3", "abbreviation": "S3",
         "monitor": 0, "n_internal_options": 2, "n_external_options": 1, "registration_required": 1},
        {"id": "pk2", "hw_support_category_id": "cat1", "hw_support_service_id": "sv1", "hw_support_period_id": "p1",
         "hw_class_id": "gone", "price": "50.00", "enabled": 1, "code": "OLD", "abbreviation": "O"},
    ],
    "address": [{"id": "a1", "line1": "Straat 1", "zipcode": "1000 AA", "city": "Stad", "country": "Nederland"},
                {"id": "a2", "line1": "Postbus 9", "zipcode": "1000 AB", "city": "Stad", "country": "België"}],
    "customer": [{"id": "c1", "kind": "reseller", "name": "Koper BV", "number_deb": "400123", "number_tax": "NL1",
                  "telephone": "010-1", "fax": "010-2", "email_packs": "orders@koper.test", "email_invoice": "f@koper.test",
                  "margin_packs": "10.00", "activated": 1, "deleted": 0, "address": "a1", "address_invoice": "a2",
                  "contact": "e1", "created_at": "2015-05-01 10:00:00"}],
    "user": [
        {"id": "u1", "login": "ina", "crypted_password": CRYPTED, "salt": SALT, "email": "Ina@Koper.test",
         "name_first": "Ina", "name_last": "Koop", "initials": "I", "created_at": "2015-05-01 10:00:00"},
        {"id": "u2", "login": "dubbel", "crypted_password": CRYPTED, "salt": SALT, "email": "ina@koper.test",
         "name_last": "Dubbel", "initials": "D"},
        {"id": "u3", "login": "weg", "crypted_password": CRYPTED, "salt": SALT, "email": "weg@koper.test", "name_last": "Weg"},
        {"id": "u9", "login": "beheer", "crypted_password": CRYPTED, "salt": SALT, "email": "beheer@shop.test",
         "name_last": "Beheer"},
    ],
    "employee": [
        {"id": "e1", "user_id": "u1", "customer_id": "c1", "gender": "female", "telephone": "06-1", "deleted": 0},
        {"id": "e2", "user_id": "u2", "customer_id": "c1", "gender": "male", "deleted": 0},
        {"id": "e3", "user_id": "u3", "customer_id": "c1", "deleted": 1},
    ],
    "role": [{"id": "r1", "name": "application_maintainer"}],
    "user_role": [{"user_id": "u9", "role_id": "r1"}],
    "hw_support_order": [{"id": 7, "employee_id": "e1", "reference": "PO-7", "discount": "10.00", "tax": "21.00",
                          "created_at": "2016-01-02 09:00:00"}],
    "hw_support_order_entry": [{"id": "oe1", "hw_support_order_id": "7", "hw_support_pack_id": "pk1", "n_packs": 2,
                                "price_each": "100.00", "reference": "R1"},
                               {"id": "oe2", "hw_support_order_id": "7", "hw_support_pack_id": "pk2", "n_packs": 1,
                                "price_each": "50.00"}],
    "hw_support_pack_license": [
        {"id": "l1", "hw_support_order_entry_id": "oe1", "hw_system_id": "s1", "license_nr": "900001", "license_nr_suffix": "AB",
         "license_sequence_nr": 1, "end_date": "2019-01-01", "serial_nr": "SN1", "registered_on": "2016-01-03"},
        {"id": "l2", "hw_support_order_entry_id": "oe1", "prolongation_of": "l1", "license_nr": "900001",
         "license_nr_suffix": "AB", "license_sequence_nr": 2, "end_date": "2022-01-01"},
        {"id": "l3", "hw_support_order_entry_id": "oe2", "license_nr": "04NBH015", "license_nr_suffix": "",
         "license_sequence_nr": 1},
        {"id": "l4", "hw_support_order_entry_id": "oe2", "license_nr": "04NBH015", "license_nr_suffix": "",
         "license_sequence_nr": 1},
    ],
    "hw_support_pack_license_option": [
        {"id": "o1", "hw_support_pack_license_id": "l1", "vendor_id": "v1", "hw_type_id": "t1", "serial_nr": "D1", "is_deleted": 0},
        {"id": "o2", "hw_support_pack_license_id": "l1", "vendor_id": "v1", "hw_type_id": "t1", "serial_nr": "D2", "is_deleted": 1},
    ],
    "part_order": [],
    "invoice": [{"id": 1, "invoice_id": "1017494", "payed_at": "2016-02-01 12:00:00", "hw_support_order_id": "7",
                 "created_at": "2016-01-05 12:00:00"},
                {"id": 2, "invoice_id": "1000001", "payed_at": None, "created_at": "2013-01-05 12:00:00"}],
    "invoice_payment": [{"id": "pay1", "amount": "100.00", "created_at": "2016-02-01 12:00:00", "invoice_id": 1, "user_id": "u9"}],
}


@pytest.fixture
def old_db(tmp_path, db):
    path = make_old_shop(str(tmp_path / "old.sqlite"), OLD)
    return ExternalDatabase.objects.create(name="Vorige webshop", engine="sqlite", host="-", database=path, user="-")


@pytest.fixture
def archived(db):
    return Invoice.objects.create(number="1017494", is_archive=True, archive_file="invoice_0001017494.pdf",
                                  customer_name="Koper BV", total=Decimal("217.80"))


def _run(db, apply):
    run = ImportRun.objects.create(database=db, dry_run=not apply)
    run_import(run)
    run.refresh_from_db()
    assert run.status == ImportRun.Status.DONE, run.notes
    return run


def test_password_decryption_matches_the_old_shop():
    assert decrypt(CRYPTED, SALT) == "Probeer-Wachtwoord-123!"
    assert decrypt("not-base64!!", SALT) is None


def test_trial_run_changes_nothing_but_reports_everything(old_db, settings):
    run = _run(old_db, apply=False)
    assert not Customer.objects.exists() and not Licence.objects.exists() and not ImportedRecord.objects.exists()
    assert run.counts["customers"]["created"] == 1 and run.counts["licences"]["created"] == 3
    report = (settings.DATA_ROOT / run.report_file).read_text()
    assert report.count("\n") > 20 and "deleted in the previous webshop" in report


def test_import_keeps_every_link(old_db, archived):
    run = _run(old_db, apply=True)
    customer = Customer.objects.get(number="400123")
    assert customer.legacy_id == "c1" and customer.customer_type.name == "Reseller" and "Fax: 010-2" in customer.remark
    assert customer.created_at.year == 2015 and customer.addresses.count() == 2
    assert customer.address("invoice").country.code == "BE"

    ina = Contact.objects.get(legacy_id="e1")
    assert ina.is_primary and ina.salutation == "mrs" and ina.user.email == "ina@koper.test"
    assert ina.user.check_password("Probeer-Wachtwoord-123!")  # own password from the previous webshop
    assert Contact.objects.get(legacy_id="e2").user is None  # same email address: no second login
    assert not Contact.objects.filter(legacy_id="e3").exists()  # deleted in the previous webshop
    staff = User.objects.get(email="beheer@shop.test")
    assert staff.is_staff and staff.groups.get().name == "Beheerder"

    order = Order.objects.get(legacy_id="7")
    assert order.customer == customer and order.gross == Decimal("250.00") and order.total == Decimal("272.25")
    first, second = Licence.objects.get(full_number="900001AB-1"), Licence.objects.get(full_number="900001AB-2")
    assert first.order_line.order == order and first.system.name == "R740" and first.vendor.name == "Dell"
    assert second.prolongation_of == first and OrderLine.objects.get(pk=second.order_line_id).extends == first
    assert Licence.objects.filter(full_number="04NBH015-1").count() == 1 and run.counts["licences"]["skipped"] == 1
    assert LicenceOption.objects.get().serial_nr == "D1"  # the deleted option is left out

    assert SupportPack.objects.get(code="OLD").hardware_class.name == "Onbekend (vorige webshop)"
    assert Category.objects.get(name_nl="Server").option_types.get().name_nl == "Extra hardeschijf"

    archived.refresh_from_db()
    assert archived.order == order and archived.customer == customer and archived.paid_on == date(2016, 2, 1)
    assert archived.archive_file == "invoice_0001017494.pdf"  # the PDF link stays
    assert Invoice.objects.get(number="1000001").issued_on == date(2013, 1, 5)
    assert InvoicePayment.objects.get().invoice == archived

    assert NumberSequence.objects.get(key="invoice").next_number == 1017495
    assert NumberSequence.objects.get(key="order").next_number == 8


def test_importing_again_creates_nothing_twice(old_db, archived):
    _run(old_db, apply=True)
    counts = (Customer.objects.count(), Contact.objects.count(), User.objects.count(), Order.objects.count(),
              Licence.objects.count(), LicenceOption.objects.count(), Invoice.objects.count())
    run = _run(old_db, apply=True)
    assert counts == (Customer.objects.count(), Contact.objects.count(), User.objects.count(), Order.objects.count(),
                      Licence.objects.count(), LicenceOption.objects.count(), Invoice.objects.count())
    assert run.counts["licences"].get("created", 0) == 0 and run.counts["licences"]["unchanged"] == 3


# --- admin -------------------------------------------------------------------------------------


def test_import_pages(client, site, old_db, monkeypatch, archived):
    from apps.legacy import import_views

    monkeypatch.setattr(import_views.threading, "Thread", lambda target, args, daemon: type(
        "T", (), {"start": lambda self: run_import(ImportRun.objects.get(pk=args[0]))})())
    client.force_login(make_user("root@example.test", superuser=True))
    assert client.get(f"/beheer/importeren/{old_db.pk}/").status_code == 200
    response = client.post(f"/beheer/importeren/{old_db.pk}/", {"mode": "apply"})
    assert not ImportRun.objects.exists()  # backup not confirmed
    response = client.post(f"/beheer/importeren/{old_db.pk}/", {"mode": "trial"})
    run = ImportRun.objects.get()
    assert response.url == f"/beheer/legacy/importrun/{run.pk}/change/"
    page = client.get(response.url).content.decode()
    assert "verslag" in page.lower() or "report" in page.lower()
    report = client.get(f"/beheer/importeren/verslag/{run.pk}/")
    assert report.status_code == 200 and b"customer" in b"".join(report.streaming_content)


def test_import_needs_permission(client, site, old_db):
    client.force_login(make_user("staff@example.test", staff=True, role="Medewerker"))
    assert client.get(f"/beheer/importeren/{old_db.pk}/").status_code == 403


# --- forced password reset -------------------------------------------------------------------------


def test_selected_contacts_must_choose_a_new_password(client, site):
    customer = Customer.objects.create(name="Klant", number="1", status=Customer.Status.ACTIVE)
    user = make_user("klant@example.test")
    contact = Contact.objects.create(customer=customer, user=user, last_name="K", email=user.email)
    client.force_login(make_user("root@example.test", superuser=True))
    client.post("/beheer/customers/contact/", {"action": "send_password_reset", "_selected_action": [contact.pk]})
    user.refresh_from_db()
    assert not user.has_usable_password() and len(mail.outbox) == 1 and "/wachtwoord-instellen/" in mail.outbox[0].body
    # An expired link is no dead end: "forgot password" works for this account.
    client.logout()
    client.post("/wachtwoord-vergeten/", {"email": "klant@example.test"})
    assert len(mail.outbox) == 2


def test_password_reset_for_the_contacts_of_selected_customers(client, site):
    customer = Customer.objects.create(name="Klant", number="1", status=Customer.Status.ACTIVE)
    for n in range(2):
        user = make_user(f"k{n}@example.test")
        Contact.objects.create(customer=customer, user=user, last_name="K", email=user.email)
    client.force_login(make_user("root@example.test", superuser=True))
    client.post("/beheer/customers/customer/", {"action": "send_password_reset", "_selected_action": [customer.pk]})
    assert len(mail.outbox) == 2 and not User.objects.get(email="k0@example.test").has_usable_password()
