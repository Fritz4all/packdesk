from datetime import date
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile

from apps.accounts.models import User
from apps.customers.models import Contact, Country, Customer, CustomerAddress
from apps.customers.transfer import NEW, OVERWRITE, SKIP, ExportFile, ImportFileError, analyse, export_customers, run_import
from apps.faults.models import FaultAttachment, FaultReport
from apps.invoices.models import Invoice, InvoiceLine
from apps.licences.models import Category, HardwareClass, Licence, SupportPack, SupportPeriod, SupportService, Vendor
from apps.orders.models import Order, OrderLine

from .conftest import make_user


@pytest.fixture(autouse=True)
def folders(tmp_path, settings):
    settings.DATA_ROOT = tmp_path / "data"
    settings.DOCUMENT_ARCHIVE_DIR = str(tmp_path / "archive")
    (tmp_path / "archive").mkdir()


@pytest.fixture
def graph(db):
    """A customer with one of everything, linked the way the shop links them."""
    pack = SupportPack.objects.create(
        code="SRV3", category=Category.objects.create(name="Server"), hardware_class=HardwareClass.objects.create(name="A"),
        service=SupportService.objects.create(abbreviation="X", name="On site"), period=SupportPeriod.objects.create(years=3),
        price=Decimal("100.00"),
    )
    vendor = Vendor.objects.create(name="Dell")
    country = Country.objects.get(code="NL")
    customer = Customer.objects.create(name="Koper BV", number="400123", status=Customer.Status.ACTIVE, email="info@koper.test")
    CustomerAddress.objects.create(customer=customer, line1="Straat 1", postal_code="1000 AA", city="Amsterdam", country=country)
    user = make_user("inkoop@koper.test")
    Contact.objects.create(customer=customer, user=user, last_name="Inkoop", email=user.email)
    order = Order.objects.create(number="5001", customer=customer, created_by=user, total=Decimal("121.00"))
    line = OrderLine.objects.create(order=order, pack=pack, description="Server 3 jaar", quantity=1,
                                    unit_price=Decimal("100.00"), line_total=Decimal("100.00"))
    first = Licence.objects.create(number="900001", suffix="AB", pack=pack, customer=customer, vendor=vendor,
                                   order_line=line, end_date=date(2026, 1, 1))
    extension_line = OrderLine.objects.create(order=order, pack=pack, description="Verlenging", quantity=1,
                                              unit_price=Decimal("0"), line_total=Decimal("0"), extends=first)
    second = Licence.objects.create(number="900001", suffix="AB", sequence=2, pack=pack, customer=customer,
                                    order_line=extension_line, prolongation_of=first)
    fault = FaultReport.objects.create(number="S-1", customer=customer, licence=first, device="R740", serial_nr="SN1",
                                       description="Kapot", reseller_name="Koper", location_name="Loc", location_contact="Jan",
                                       location_address="Weg 1", location_postal_code="1000 AA", location_city="Amsterdam",
                                       location_phone="0101", location_email="loc@koper.test")
    attachment = FaultAttachment(report=fault, name="foto.jpg", size=4)
    attachment.file.save("foto.jpg", ContentFile(b"JPEG"), save=True)
    invoice = Invoice(number="1030954", customer=customer, order=order, customer_name="Koper BV", total=Decimal("121.00"))
    invoice.pdf.save("invoice-1030954.pdf", ContentFile(b"%PDF-test"), save=True)
    InvoiceLine.objects.create(invoice=invoice, code="SRV3", description="Server", unit_price=Decimal("100"), amount=Decimal("100"))
    return {"customer": customer, "pack": pack, "first": first, "second": second}


def _export(tmp_path, queryset=None, include_files=True):
    path = tmp_path / "export.zip"
    with open(path, "wb") as f:
        export_customers(queryset or Customer.objects.all(), include_files=include_files, out=f)
    return ExportFile(str(path))


def _wipe():
    """Remove all customer data, as if the export is imported into another installation."""
    Invoice.objects.all().delete()
    FaultReport.objects.all().delete()
    Licence.objects.update(prolongation_of=None)
    Licence.objects.all().delete()
    Order.objects.all().delete()
    Contact.objects.all().delete()
    Customer.objects.all().delete()
    User.objects.filter(kind=User.Kind.CUSTOMER).delete()


def test_round_trip_keeps_all_relations(tmp_path, graph):
    export = _export(tmp_path)
    _wipe()
    rows = analyse(export)
    assert rows[0]["existing"] is None and rows[0]["new"]["counts"]
    assert not Customer.objects.exists()  # the analysis changed nothing

    run_import(export, {0: NEW})
    customer = Customer.objects.get()
    assert customer.number == "400123" and customer.addresses.get().country.code == "NL"
    contact = customer.contacts.get()
    assert contact.user.email == "inkoop@koper.test" and not contact.user.has_usable_password()
    first, second = Licence.objects.get(full_number="900001AB-1"), Licence.objects.get(full_number="900001AB-2")
    assert first.vendor.name == "Dell" and first.order_line.order.number == "5001"
    assert second.prolongation_of == first and second.order_line.extends == first
    fault = FaultReport.objects.get()
    assert fault.licence == first and fault.attachments.get().file.read() == b"JPEG"
    invoice = Invoice.objects.get()
    assert invoice.order.number == "5001" and invoice.customer == customer
    assert invoice.pdf_bytes() == b"%PDF-test" and invoice.lines.count() == 1


def test_existing_customer_is_reported_and_skipped_by_default(tmp_path, graph):
    export = _export(tmp_path)
    Customer.objects.filter(pk=graph["customer"].pk).update(name="Nieuwe naam")
    row = analyse(export)[0]
    assert row["existing"]["pk"] == graph["customer"].pk
    assert any(c["new"] == "Koper BV" and c["old"] == "Nieuwe naam" for c in row["changes"])

    run_import(export, {0: SKIP})
    assert Customer.objects.get().name == "Nieuwe naam"
    run_import(export, {})  # no choice means skip as well
    assert Customer.objects.count() == 1


def test_overwrite_updates_without_duplicates_or_deleting(tmp_path, graph):
    export = _export(tmp_path)
    Customer.objects.filter(pk=graph["customer"].pk).update(name="Nieuwe naam")
    extra = Order.objects.create(number="5002", customer=graph["customer"])
    result = run_import(export, {0: OVERWRITE})[0]
    customer = Customer.objects.get()
    assert customer.name == "Koper BV" and customer.number == "400123"
    assert Licence.objects.count() == 2 and Invoice.objects.count() == 1 and customer.contacts.count() == 1
    assert Order.objects.filter(pk=extra.pk).exists()  # only here: kept
    counts = {c["key"]: c for c in result["counts"]}
    assert counts["licences"]["created"] == 0 and counts["licences"]["unchanged"] == 2
    assert not analyse(_export(tmp_path))[0]["changes"]  # a round trip shows no false differences


def test_import_as_new_gets_new_number_and_skips_taken_numbers(tmp_path, graph):
    export = _export(tmp_path)
    result = run_import(export, {0: NEW})[0]
    assert Customer.objects.count() == 2
    copy = Customer.objects.exclude(pk=graph["customer"].pk).get()
    assert copy.number and copy.number != "400123"
    assert Licence.objects.count() == 2 and Invoice.objects.count() == 1  # numbers must stay unique
    kinds = {s["key"] for s in result["skipped"]}
    assert {"licences", "invoices", "orders"} <= kinds
    assert copy.contacts.get().user is None and result["warnings"]  # login belongs to the other customer


def test_other_customers_items_are_never_touched(tmp_path, graph):
    export = _export(tmp_path)
    other = Customer.objects.create(name="Ander", number="400999")
    Licence.objects.filter(pk=graph["first"].pk).update(customer=other)
    result = run_import(export, {0: OVERWRITE})[0]
    assert Licence.objects.get(pk=graph["first"].pk).customer == other
    assert any("Ander" in s["reason"] for s in result["skipped"])


def test_export_without_files_still_has_relations(tmp_path, graph):
    export = _export(tmp_path, include_files=False)
    assert export.data["includes_files"] is False and not [n for n in export.names if n.startswith("files/")]
    _wipe()
    run_import(export, {0: NEW})
    assert Licence.objects.get(full_number="900001AB-2").prolongation_of.full_number == "900001AB-1"


def test_wrong_file_is_refused(tmp_path, db):
    path = tmp_path / "x.json"
    path.write_text('{"hello": 1}')
    with pytest.raises(ImportFileError):
        ExportFile(str(path))
    path.write_bytes(b"not json")
    with pytest.raises(ImportFileError):
        ExportFile(str(path))


def test_archive_file_cannot_point_outside_the_archive(db, tmp_path):
    (tmp_path / "secret.pdf").write_bytes(b"%PDF")
    invoice = Invoice(number="1", is_archive=True, archive_file="../secret.pdf")
    assert not invoice.has_pdf()


# --- admin pages ---------------------------------------------------------------------------------


def test_admin_import_flow(client, site, tmp_path, graph):
    admin_user = make_user("root@example.test", superuser=True)
    client.force_login(admin_user)
    path = tmp_path / "export.zip"
    with open(path, "wb") as f:
        export_customers(Customer.objects.all(), out=f)
    Customer.objects.filter(pk=graph["customer"].pk).update(name="Nieuwe naam")

    with open(path, "rb") as f:
        page = client.post("/admin/customers/customer/import/", {"step": "upload", "file": f})
    assert page.status_code == 200 and page.context["conflicts"] == 1
    token = page.context["token"]
    assert Customer.objects.get().name == "Nieuwe naam"

    done = client.post("/admin/customers/customer/import/", {"step": "run", "token": token, "choice-0": "overwrite"})
    assert done.status_code == 200 and Customer.objects.get().name == "Koper BV"
    again = client.post("/admin/customers/customer/import/", {"step": "run", "token": token, "choice-0": "new"})
    assert again.status_code == 302 and Customer.objects.count() == 1  # a token works once


def test_admin_export_downloads_zip(client, site, graph):
    client.force_login(make_user("root@example.test", superuser=True))
    response = client.post("/admin/customers/customer/export/", {"include_files": "on"})
    assert response.status_code == 200 and response["Content-Type"] == "application/zip"
    assert b"".join(response.streaming_content)[:2] == b"PK"


def test_import_and_export_need_permission(client, site, graph):
    client.force_login(make_user("staff@example.test", staff=True, role="Medewerker"))
    assert client.get("/admin/customers/customer/import/").status_code == 403
    assert client.get("/admin/customers/customer/export/").status_code == 403


def test_bad_upload_shows_error(client, site, tmp_path):
    client.force_login(make_user("root@example.test", superuser=True))
    path = tmp_path / "x.json"
    path.write_text("[]")
    with open(path, "rb") as f:
        page = client.post("/admin/customers/customer/import/", {"step": "upload", "file": f})
    assert page.status_code == 200 and page.context["form"].errors


def test_import_page_has_a_clear_file_picker(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    html = client.get("/admin/customers/customer/import/").content.decode()
    assert "data-dropzone" in html and 'accept=".zip,.json"' in html
