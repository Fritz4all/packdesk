from decimal import Decimal

import pytest
from django.core import mail
from django.core.management import call_command

from apps.customers.models import Contact, Customer, CustomerAddress
from apps.invoices.archive import parse
from apps.invoices.models import Invoice, InvoiceEmail, InvoiceSettings
from apps.licences.models import Category, HardwareClass, SupportPack, SupportPeriod, SupportService
from apps.numbering.models import NumberSequence
from apps.orders.models import OrderSettings

from .conftest import make_user

OLD_INVOICE = """\
Testbedrijf B.V.                                               Factuurnummer                   1030953
T.a.v. Mevr. Test                                              Debiteurnummer                  400123
Teststraat 5                                                   Postbus 1
1234 AB Teststad

Onze referentie                                               Factuurdatum                    2026-10-23
Behandeld door                 Administratie                  Betaalwijze                     Op rekening
Uw referentie                  PO-1

                                                                                         Subtotaal €       100,00
                                                                                         BTW 21.0% €          21,00
                                                                                       Totaal €       121,00
"""


@pytest.fixture(autouse=True)
def folders(tmp_path, settings):
    settings.DATA_ROOT = tmp_path / "data"
    archive = tmp_path / "archive"
    archive.mkdir()
    settings.DOCUMENT_ARCHIVE_DIR = str(archive)
    return archive


@pytest.fixture
def shop(db):
    pack = SupportPack.objects.create(
        code="SRV3", category=Category.objects.create(name="Server"), hardware_class=HardwareClass.objects.create(name="A"),
        service=SupportService.objects.create(abbreviation="X", name="On site"), period=SupportPeriod.objects.create(years=3),
        price=Decimal("100.00"), registration_required=False,
    )
    customer = Customer.objects.create(name="Koper BV", number="400123", status=Customer.Status.ACTIVE,
                                       margin_packs=Decimal("10"), email="info@koper.test", email_invoices="facturen@koper.test")
    CustomerAddress.objects.create(customer=customer, line1="Straat 1", postal_code="1000 AA", city="Amsterdam")
    user = make_user("inkoop@koper.test")
    Contact.objects.create(customer=customer, user=user, last_name="Inkoop", email=user.email)
    OrderSettings.objects.filter(pk=1).update(notify_emails="sales@example.test")
    return {"pack": pack, "customer": customer, "user": user}


def place(client, shop, qty=2):
    client.force_login(shop["user"])
    data = {"lines-TOTAL_FORMS": "1", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "50",
            "lines-0-pack": shop["pack"].pk, "lines-0-quantity": str(qty), "reference": "PO-9"}
    payload = client.post("/mijn/bestellen/", data).context["payload"]
    client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload})


def test_order_makes_invoice_with_pdf_and_email(client, site, shop):
    place(client, shop)
    invoice = Invoice.objects.get()
    assert invoice.number == "1" and invoice.customer == shop["customer"] and invoice.reference == "PO-9"
    assert invoice.total == Decimal("217.80") and invoice.lines.get().code == "SRV3"
    assert invoice.address_city == "Amsterdam" and invoice.due_on is not None
    assert invoice.pdf_bytes().startswith(b"%PDF")
    message = [m for m in mail.outbox if m.attachments][0]
    assert message.to == ["facturen@koper.test"] and message.attachments[0][0] == "invoice-1.pdf"
    assert InvoiceEmail.objects.filter(invoice=invoice).count() == 1


def test_no_invoice_when_switched_off_or_customer_excluded(client, site, shop):
    InvoiceSettings.objects.filter(pk=1).update(auto_on_order=False)
    place(client, shop)
    assert not Invoice.objects.exists()
    InvoiceSettings.objects.filter(pk=1).update(auto_on_order=True)
    Customer.objects.filter(pk=shop["customer"].pk).update(no_pack_invoice=True)
    place(client, shop)
    assert not Invoice.objects.exists()


def test_counter_behind_archive_blocks_invoice_and_warns(client, site, shop, folders, beheerder):
    (folders / "invoice_0001030953.pdf").write_bytes(b"%PDF-1.4 old")
    place(client, shop)
    assert not Invoice.objects.exists()
    warning = [m for m in mail.outbox if "1" in m.subject and m.to == ["sales@example.test"] and not m.attachments][-1]
    assert "Nummerreeksen" in warning.body or "Number sequences" in warning.body
    NumberSequence.objects.filter(key="invoice").update(next_number=1030954)
    order = shop["customer"].orders.get()
    client.force_login(beheerder)
    client.post(f"/admin/orders/order/{order.pk}/action/invoice/")
    assert Invoice.objects.get(order=order).number == "1030954"


def test_pdf_access(client, site, shop, beheerder):
    place(client, shop)
    invoice = Invoice.objects.get()
    url = f"/factuur/{invoice.pk}/pdf/"
    assert client.get(url).status_code == 200  # still logged in as the customer
    assert client.get(url + "?download=1")["Content-Disposition"].startswith("attachment")
    client.force_login(make_user("vreemd@x.test"))
    assert client.get(url).status_code == 403
    client.logout()
    assert client.get(url).status_code == 302
    client.force_login(beheerder)
    assert client.get(url).status_code == 200


def test_customer_list_and_send_to_me(client, site, shop):
    place(client, shop)
    invoice = Invoice.objects.get()
    assert invoice.number in client.get("/mijn/facturen/").content.decode()
    mail.outbox.clear()
    client.post(f"/mijn/facturen/{invoice.pk}/sturen/")
    assert mail.outbox[0].to == ["inkoop@koper.test"] and mail.outbox[0].attachments


def test_admin_resend_and_no_delete(client, site, shop, beheerder):
    place(client, shop)
    invoice = Invoice.objects.get()
    client.force_login(beheerder)
    mail.outbox.clear()
    client.post(f"/admin/invoices/invoice/{invoice.pk}/action/resend/")
    assert mail.outbox[0].to == ["facturen@koper.test"]
    assert InvoiceEmail.objects.filter(invoice=invoice, sent_by=beheerder).exists()
    assert client.get(f"/admin/invoices/invoice/{invoice.pk}/delete/").status_code == 403


# --- old archive -------------------------------------------------------------------

def test_parse_old_invoice_text():
    data = parse(OLD_INVOICE)
    assert data["number"] == "1030953" and data["customer_number"] == "400123"
    assert str(data["issued_on"]) == "2026-10-23"
    assert data["total"] == Decimal("121.00") and data["vat"] == Decimal("21.00") and data["net"] == Decimal("100.00")
    assert data["customer_name"] == "Testbedrijf B.V." and data["address_attention"] == "Mevr. Test"
    assert data["address_line1"] == "Teststraat 5" and data["address_city"] == "Teststad"


def test_import_archive_links_customer_and_serves_original(client, site, shop, folders, monkeypatch):
    original = b"%PDF-1.4 original archived invoice"
    (folders / "invoice_0001030953.pdf").write_bytes(original)
    monkeypatch.setattr("apps.invoices.management.commands.import_invoice_archive.pdf_text", lambda path: OLD_INVOICE)
    call_command("import_invoice_archive")
    invoice = Invoice.objects.get(number="1030953")
    assert invoice.is_archive and invoice.customer == shop["customer"] and invoice.total == Decimal("121.00")
    call_command("import_invoice_archive")  # running again adds nothing
    assert Invoice.objects.count() == 1
    client.force_login(shop["user"])
    assert "1030953" in client.get("/mijn/facturen/").content.decode()
    response = client.get(f"/factuur/{invoice.pk}/pdf/")
    assert response.content == original


def test_relink_after_customers_are_imported(site, folders, monkeypatch):
    (folders / "invoice_0001030953.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr("apps.invoices.management.commands.import_invoice_archive.pdf_text", lambda path: OLD_INVOICE)
    call_command("import_invoice_archive")
    assert Invoice.objects.get().customer is None
    customer = Customer.objects.create(name="Later", number="400123")
    call_command("import_invoice_archive", "--relink")
    assert Invoice.objects.get().customer == customer


def test_parse_uses_date_elsewhere_when_label_is_empty():
    text = OLD_INVOICE.replace("Factuurdatum                    2026-10-23", "Factuurdatum") + "\nGeleverd op 2025-03-04\n"
    assert str(parse(text)["issued_on"]) == "2025-03-04"
