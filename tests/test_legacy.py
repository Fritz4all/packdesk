from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.customers.models import Contact, Customer, CustomerAddress
from apps.invoices.models import Invoice
from apps.legacy import crypto
from apps.legacy.compare import compare_archive, compare_mapping, number_tops, search
from apps.legacy.connection import ExternalDatabaseError, open_reader, check_connection
from apps.legacy.models import ExternalDatabase, FieldMapping, TableMapping
from apps.legacy.parts import OLD_SHOP_PRESET, apply_preset
from apps.licences.models import Category, HardwareClass, Licence, SupportPack, SupportPeriod, SupportService

from .conftest import make_user
from .old_shop import make_old_shop

OLD = {
    "address": [{"id": "a1", "line1": "Oude Straat 1", "zipcode": "1000 AA", "city": "Amsterdam"}],
    "customer": [
        {"id": "c1", "name": "Koper BV", "number_deb": "400123", "number_tax": "NL001", "telephone": "020-111",
         "margin_packs": "10.00", "margin_parts": None, "skip_hw_support_pack_invoice": 0, "activated": 1,
         "deleted": 0, "address": "a1"},
        {"id": "c2", "name": "Alleen Oud BV", "number_deb": "400200", "activated": 1, "deleted": 0},
        {"id": "c3", "name": "Verwijderd BV", "number_deb": "400300", "activated": 1, "deleted": 1},
    ],
    "user": [{"id": "u1", "email": "Inkoop@Koper.test", "name_first": "Ina", "name_last": "Koop", "deleted": 0}],
    "employee": [{"id": "e1", "user_id": "u1", "customer_id": "c1", "telephone": "06-1", "deleted": 0}],
    "hw_support_order": [{"id": 7, "employee_id": "e1", "reference": "PO-7", "discount": "10.00"}],
    "hw_support_order_entry": [{"id": "oe1", "hw_support_order_id": "7"}],
    "hw_support_pack_license": [
        {"id": "l1", "hw_support_order_entry_id": "oe1", "license_nr": "900001", "license_nr_suffix": "AB",
         "license_sequence_nr": 1, "end_date": "2027-01-31", "serial_nr": "SN1"},
        {"id": "l2", "hw_support_order_entry_id": "oe1", "license_nr": "900002", "license_nr_suffix": "CD",
         "license_sequence_nr": 1, "end_date": "2027-05-01", "serial_nr": "SN2"},
    ],
    "hw_support_pack_license_option": [
        {"id": "o1", "hw_support_pack_license_id": "l1", "serial_nr": "DISK1", "product_nr": "P1", "is_deleted": 0},
    ],
    "invoice": [{"id": 1, "invoice_id": "1017494", "payed_at": "2020-03-01 10:00:00", "hw_support_order_id": "7"},
                {"id": 2, "invoice_id": "1017495", "payed_at": None, "hw_support_order_id": None}],
}


@pytest.fixture
def old_db(tmp_path, db):
    path = make_old_shop(str(tmp_path / "old.sqlite"), OLD)
    return ExternalDatabase(name="Vorige webshop", engine="sqlite", host="-", database=path, user="-")


@pytest.fixture
def packdesk(db, tmp_path, settings):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "invoice_0001017494.pdf").write_bytes(b"%PDF")
    settings.DOCUMENT_ARCHIVE_DIR = str(archive)
    customer = Customer.objects.create(name="Koper BV", number="400123", legacy_id="c1", vat_number="NL001",
                                       phone="020-999", margin_packs=Decimal("10"), status=Customer.Status.ACTIVE)
    CustomerAddress.objects.create(customer=customer, line1="Oude Straat 1", postal_code="1000 AA", city="Amsterdam")
    Customer.objects.create(name="Alleen Nieuw BV", number="500000")
    Contact.objects.create(customer=customer, email="inkoop@koper.test", first_name="Ina", last_name="Koop", phone="06-1",
                           legacy_id="e1")
    pack = SupportPack.objects.create(
        code="SRV3", category=Category.objects.create(name="Server"), hardware_class=HardwareClass.objects.create(name="A"),
        service=SupportService.objects.create(abbreviation="X", name="On site"), period=SupportPeriod.objects.create(years=3),
        price=Decimal("100.00"),
    )
    Licence.objects.create(number="900001", suffix="AB", pack=pack, customer=customer, end_date=date(2027, 2, 28),
                           serial_nr="SN1")
    Invoice.objects.create(number="1017494", customer=customer, paid_on=date(2020, 3, 1))
    return customer


# --- passwords and connections -------------------------------------------------------------------


def test_password_is_encrypted_and_tied_to_secret_key(settings):
    token = crypto.encrypt("geheim")
    assert "geheim" not in token and crypto.decrypt(token) == "geheim"
    settings.SECRET_KEY = "another-key"
    assert crypto.decrypt(token) is None


def test_admin_stores_password_encrypted_and_keeps_it_when_left_empty(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    data = {"name": "Oud", "engine": "mariadb", "host": "10.0.0.5", "port": "", "database": "oudeshop",
            "user": "lezer", "password": "s3cret", "notes": ""}
    client.post("/beheer/legacy/externaldatabase/add/", data)
    db = ExternalDatabase.objects.get()
    assert db.password_encrypted and "s3cret" not in db.password_encrypted and db.get_password() == "s3cret"
    page = client.get(f"/beheer/legacy/externaldatabase/{db.pk}/change/").content.decode()
    assert "s3cret" not in page and db.password_encrypted not in page
    client.post(f"/beheer/legacy/externaldatabase/{db.pk}/change/", {**data, "password": "", "host": "10.0.0.6"})
    db.refresh_from_db()
    assert db.host == "10.0.0.6" and db.get_password() == "s3cret"


def test_connection_test_recognises_old_shop(old_db):
    ok, message = check_connection(old_db)
    assert ok and ("previous webshop" in message.lower() or "vorige webshop" in message.lower())


def test_failed_connection_is_reported(db):
    bad = ExternalDatabase(name="X", engine="mariadb", host="127.0.0.1", port=1, database="x", user="x")
    ok, message = check_connection(bad)
    assert not ok


def test_reader_only_runs_select_and_cannot_write(old_db):
    with open_reader(old_db) as reader:
        with pytest.raises(ExternalDatabaseError):
            reader.rows("DELETE FROM `customer`")
        with pytest.raises(ExternalDatabaseError):
            reader.rows("SELECT 1; DELETE FROM `customer`")
        with pytest.raises(Exception):
            reader.connection.execute("DELETE FROM `customer`")  # opened read-only
    with open_reader(old_db) as reader:
        assert reader.value("SELECT COUNT(*) FROM `customer`") == 3


# --- comparing ----------------------------------------------------------------------------------


@pytest.fixture
def mapped(old_db):
    old_db.save()
    apply_preset(old_db)
    return old_db


def _compare(db, key):
    with open_reader(db) as reader:
        return compare_mapping(db.mappings.get(part=key), reader)


def test_preset_maps_every_part_once(mapped):
    assert set(mapped.mappings.values_list("part", flat=True)) == set(OLD_SHOP_PRESET)
    assert apply_preset(mapped) == 0  # loading again adds nothing and keeps changes


def test_customers_matched_on_old_id_with_differences(mapped, packdesk):
    result = _compare(mapped, "customers")
    assert result.old_count == 2  # the deleted one is left out
    assert [r["name"] for r in result.only_old] == ["Alleen Oud BV"]
    assert [r["name"] for r in result.only_new] == ["Alleen Nieuw BV"]
    (old, new, diffs), = result.different
    assert new["pk"] == packdesk.pk and [d[0] for d in diffs] in (["Phone"], ["Telefoon"])


def test_contacts_match_and_email_case_does_not_count(mapped, packdesk):
    result = _compare(mapped, "contacts")
    assert result.matched == 1 and not result.different and not result.only_old


def test_licences_match_on_number_and_show_other_end_date(mapped, packdesk):
    result = _compare(mapped, "licences")
    assert result.matched == 1 and [r["full_number"] for r in result.only_old] == ["900002CD-1"]
    (_old, _new, diffs), = result.different
    assert any("31-01-2027" in d[1] and "28-02-2027" in d[2] for d in diffs)


def test_invoices_and_archive_pdfs(mapped, packdesk):
    invoices = _compare(mapped, "invoices")
    assert invoices.matched == 1 and [r["number"] for r in invoices.only_old] == ["1017495"]
    with open_reader(mapped) as reader:
        pdfs = compare_archive(mapped.mappings.get(part="invoices"), reader)
    assert pdfs.matched == 1 and [r["number"] for r in pdfs.only_old] == ["1017495"]


def test_a_mapping_made_by_hand(old_db, packdesk):
    """Any database: a part mapped to a plain table with chosen columns."""
    old_db.save()
    mapping = TableMapping.objects.create(database=old_db, part="customers", source_table="customer",
                                          id_column="id", skip_column="deleted", skip_value="1")
    FieldMapping.objects.create(mapping=mapping, field="name", column="name")
    FieldMapping.objects.create(mapping=mapping, field="number", column="NUMBER_DEB")  # case does not matter
    with open_reader(old_db) as reader:
        result = compare_mapping(mapping, reader)
    assert result.old_count == 2 and result.matched == 1 and not result.different  # phone is not mapped


def test_mapping_accepts_one_select_only(old_db):
    old_db.save()
    for bad in ({"source_table": "customer", "source_query": "SELECT 1"}, {},
                {"source_query": "DELETE FROM customer"}, {"source_query": "SELECT 1; DROP TABLE customer"}):
        with pytest.raises(ValidationError):
            TableMapping(database=old_db, part="users", **bad).full_clean()
    with pytest.raises(ValidationError):
        TableMapping(database=old_db, part="users", source_table="user; drop").full_clean()


def test_number_tops_flag_low_counters(mapped, packdesk):
    with open_reader(mapped) as reader:
        tops = number_tops(mapped, reader)
    invoice = next(t for t in tops if t["old"] == "1017495")
    assert invoice["ok"] is False


def test_search_finds_where_things_are(mapped, packdesk):
    with open_reader(mapped) as reader:
        results = search(mapped, reader, "900001AB-1")
    licences = next(r for r in results if r["old"] or r["new"])
    assert licences["old"] == ["900001AB-1"] and licences["new"][0][0] == "900001AB-1"


# --- pages ---------------------------------------------------------------------------------------


def _saved(old_db):
    old_db.save()
    return old_db


def test_compare_pages(client, site, mapped, packdesk):
    db = mapped
    client.force_login(make_user("root@example.test", superuser=True))
    assert client.get("/beheer/vergelijken/").status_code == 302  # one database: straight to it
    page = client.get(f"/beheer/vergelijken/{db.pk}/")
    assert page.status_code == 200 and any(s["key"] == "customers" and s["only_old"] == 1 for s in page.context["summaries"])
    detail = client.get(f"/beheer/vergelijken/{db.pk}/customers/different/")
    assert detail.status_code == 200 and "020-111" in detail.content.decode()
    csv = client.get(f"/beheer/vergelijken/{db.pk}/licences/only_old/?format=csv")
    assert csv["Content-Type"].startswith("text/csv") and "900002CD-1" in csv.content.decode("utf-8-sig")
    found = client.get(f"/beheer/vergelijken/{db.pk}/zoeken/?q=Koper")
    assert found.status_code == 200 and found.context["results"]
    assert client.post(f"/beheer/vergelijken/{db.pk}/").status_code == 302  # compare again


def test_compare_needs_permission(client, site, old_db):
    db = _saved(old_db)
    client.force_login(make_user("staff@example.test", staff=True, role="Medewerker"))
    assert client.get(f"/beheer/vergelijken/{db.pk}/").status_code == 403
    assert client.get("/beheer/legacy/externaldatabase/").status_code == 403


def test_compare_without_mappings_explains_what_to_do(client, site, old_db):
    db = _saved(old_db)
    client.force_login(make_user("root@example.test", superuser=True))
    page = client.get(f"/beheer/vergelijken/{db.pk}/")
    assert page.status_code == 200 and not page.context["summaries"]
    assert f"/beheer/legacy/tablemapping/add/?database={db.pk}" in page.content.decode()


def test_preset_button_and_mapping_page(client, site, old_db):
    db = _saved(old_db)
    client.force_login(make_user("root@example.test", superuser=True))
    client.post(f"/beheer/legacy/externaldatabase/{db.pk}/action/preset/")
    assert db.mappings.count() == len(OLD_SHOP_PRESET)
    mapping = db.mappings.get(part="customers")
    page = client.get(f"/beheer/legacy/tablemapping/{mapping.pk}/change/").content.decode()
    assert 'id="pd-columns"' in page and "number_deb" in page and "Koper BV" in page  # columns and example rows
    assert client.get("/beheer/legacy/tablemapping/add/").status_code == 200


def test_highest_number_ignores_notes_in_number_fields():
    from apps.legacy.compare import _highest

    assert _highest(["400123", "2000693-use other number", "9"]) == "400123"
    assert _highest(["26A0001", "26A0099"]) == "26A0099"
    assert _highest(["", ""]) is None
