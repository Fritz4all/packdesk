from decimal import Decimal

import pytest
from django.core import mail

from apps.customers.models import Contact, Country, Customer, CustomerAddress
from apps.invoices.models import Invoice
from apps.licences.models import Vendor
from apps.parts import services
from apps.parts.models import (Correction, DeliveryTime, PartOrder, PartRequest, PartsSettings, PaymentMethod,
                               RequestLine, selling_price)

from .conftest import make_user


@pytest.fixture
def parts(db, settings):
    settings.DOCUMENT_ARCHIVE_DIR = ""  # no archive to check the invoice counter against
    nl = Country.objects.get_or_create(code="NL", defaults={"name": "Nederland"})[0]
    be = Country.objects.get_or_create(code="BE", defaults={"name": "België"})[0]
    customer = Customer.objects.create(name="Koper BV", number="9", status=Customer.Status.ACTIVE,
                                       margin_parts=Decimal("10"), email="info@koper.test")
    CustomerAddress.objects.create(customer=customer, line1="Straat 1", postal_code="1000 AA", city="Stad", country=nl)
    user = make_user("inkoop@koper.test")
    Contact.objects.create(customer=customer, user=user, last_name="Inkoop", email=user.email)
    PartsSettings.objects.filter(pk=1).delete()
    rules = PartsSettings.load()
    rules.home_country, rules.notify_emails = nl, "parts@example.test"
    rules.save()
    return {"customer": customer, "user": user, "vendor": Vendor.objects.create(name="Acer"), "be": be}


def request_post(vendor, **extra):
    data = {"lines-TOTAL_FORMS": "2", "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "0", "lines-MAX_NUM_FORMS": "50",
            "lines-0-vendor": vendor.pk, "lines-0-article_number": "KT.123", "lines-0-quantity": "2",
            "lines-0-description": "Accu", "reference": "PO-P"}
    data.update(extra)
    return data


def answered_request(parts):
    request = PartRequest.objects.create(number="WS17000AA", customer=parts["customer"], created_by=parts["user"])
    RequestLine.objects.create(request=request, article_number="KT.123", vendor=parts["vendor"], quantity=2,
                               status=RequestLine.Status.AGREED, price_new=Decimal("10.00"),
                               time_new=DeliveryTime.objects.get(code="in_stock"))
    services.answer(request, None, notify=False)
    return request


def order_post(request, **extra):
    line = request.lines.get()
    data = {"action": "check", f"q-{line.pk}-new": "2", "reference": "PO-P",
            "payment_method": PaymentMethod.objects.get(code="on_account").pk, "delivery_name": "Koper BV",
            "delivery_address": "Straat 1", "delivery_postal_code": "1000 AA", "delivery_city": "Stad",
            "delivery_country": "Nederland"}
    data.update(extra)
    return data


def test_markup_like_the_old_shop(db):
    assert selling_price(Decimal("10")) == Decimal("20.00")  # up to 19: × 2.00
    assert selling_price(Decimal("50")) == Decimal("75.00")  # above 39: × 1.50
    assert selling_price(Decimal("1000")) == Decimal("1300.00")  # above 999: × 1.30


def test_customer_sends_a_request(client, site, parts):
    client.force_login(parts["user"])
    response = client.post("/mijn/onderdelen/aanvragen/", request_post(parts["vendor"]))
    request = PartRequest.objects.get()
    assert response.status_code == 302 and request.number.startswith("WS17000") and request.created_by == parts["user"]
    assert request.lines.get().quantity == 2 and request.status == PartRequest.Status.TO_HANDLE
    assert mail.outbox[0].to == ["inkoop@koper.test", "info@koper.test"] and mail.outbox[0].bcc == ["parts@example.test"]


def test_urgent_request_needs_an_address(client, site, parts):
    client.force_login(parts["user"])
    response = client.post("/mijn/onderdelen/aanvragen/", request_post(parts["vendor"], urgent="on"))
    assert response.status_code == 200 and not PartRequest.objects.exists()


def test_answer_logs_and_emails_once(parts):
    request = PartRequest.objects.create(number="WS1", customer=parts["customer"], created_by=parts["user"])
    line = RequestLine.objects.create(request=request, article_number="X", quantity=1)
    assert not services.answer(request, None)  # still open
    line.status, line.price_new = RequestLine.Status.AGREED, Decimal("5")
    line.save()
    assert services.answer(request, None) and request.status == PartRequest.Status.ANSWERED and request.valid_until
    assert len(mail.outbox) == 1 and line.changes.count() == 2


def test_order_totals_invoice_and_mail(client, site, parts):
    request = answered_request(parts)
    client.force_login(parts["user"])
    review = client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/", order_post(request))
    order = review.context["order"]
    # 2 × € 20 = 40, 10% discount = 36, small order surcharge 15 = 51, VAT 21% = 10.71
    assert (order.gross, order.discount, order.small_order_costs, order.net, order.vat, order.total) == (
        Decimal("40.00"), Decimal("4.00"), Decimal("15.00"), Decimal("51.00"), Decimal("10.71"), Decimal("61.71"))
    response = client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/",
                           {"action": "confirm", "payload": review.context["payload"]})
    order = PartOrder.objects.get()
    assert response.status_code == 302 and order.number == "WS17000AA-1" and order.status == PartOrder.Status.TO_DELIVER
    invoice = Invoice.objects.get(part_order=order)
    assert invoice.total == Decimal("61.71") and invoice.gross == Decimal("55.00")  # parts + surcharge
    assert invoice.lines.count() == 2 and client.get(f"/mijn/onderdelen/bestelling/{order.pk}/").status_code == 200


def test_tampered_or_foreign_requests_are_refused(client, site, parts):
    request = answered_request(parts)
    client.force_login(parts["user"])
    response = client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/", {"action": "confirm", "payload": "x"})
    assert response.status_code == 302 and not PartOrder.objects.exists()
    other = Customer.objects.create(name="Ander", number="10", status=Customer.Status.ACTIVE)
    other_user = make_user("ander@x.test")
    Contact.objects.create(customer=other, user=other_user, last_name="A", email=other_user.email)
    client.force_login(other_user)
    assert client.get(f"/mijn/onderdelen/aanvraag/{request.pk}/").status_code == 404


def test_abroad_costs_and_no_vat(client, site, parts):
    request = answered_request(parts)
    CustomerAddress.objects.create(customer=parts["customer"], kind="invoice", line1="Rue 1", postal_code="1000",
                                   city="Brussel", country=parts["be"])
    client.force_login(parts["user"])
    order = client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/",
                        order_post(request, delivery_country="België")).context["order"]
    assert order.delivery_costs == Decimal("18.00") and order.vat_rate == 0 and order.total == order.net


def test_large_or_prepaid_orders_wait(client, site, parts):
    request = answered_request(parts)
    rules = PartsSettings.load()
    rules.approval_limit = Decimal("50")
    rules.save()
    client.force_login(parts["user"])
    review = client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/", order_post(request))
    client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/", {"action": "confirm", "payload": review.context["payload"]})
    assert PartOrder.objects.get().status == PartOrder.Status.AWAITING_APPROVAL
    review = client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/", order_post(
        request, payment_method=PaymentMethod.objects.get(code="proforma").pk))
    client.post(f"/mijn/onderdelen/aanvraag/{request.pk}/", {"action": "confirm", "payload": review.context["payload"]})
    assert PartOrder.objects.get(number="WS17000AA-2").status == PartOrder.Status.AWAITING_PAYMENT


def test_staff_deliver_correct_and_cancel(client, site, parts, beheerder):
    request = answered_request(parts)
    order = PartOrder.objects.create(number="WS17000AA-1", request=request, customer=parts["customer"])
    line = order.lines.create(request_line=request.lines.get(), packing="new", quantity=3, unit_price=Decimal("20"))
    client.force_login(make_user("service@example.test", staff=True, role="Service"))
    url = f"/beheer/parts/partorder/{order.pk}"
    assert client.post(f"{url}/deliver/", {f"deliver-{line.pk}": "5"}).status_code == 200  # more than ordered
    client.post(f"{url}/deliver/", {f"deliver-{line.pk}": "1"})
    assert line.delivered() == 1 and PartOrder.objects.get().status == PartOrder.Status.TO_DELIVER
    assert client.post(f"{url}/correct/", {f"correct-{line.pk}": "-2"}).status_code == 200  # reason missing
    mail.outbox.clear()
    client.post(f"{url}/correct/", {f"correct-{line.pk}": "-2", "reason": "Niet leverbaar"})
    assert Correction.objects.get().quantity == -2 and PartOrder.objects.get().status == PartOrder.Status.DONE
    assert mail.outbox[0].to == ["parts@example.test"] and "40,00" in mail.outbox[0].body  # 2 × € 20

    other = PartOrder.objects.create(number="WS17000AA-2", request=request, customer=parts["customer"])
    client.post(f"/beheer/parts/partorder/{other.pk}/cancel/", {"reason": "Klant wil niet meer"})
    assert PartOrder.objects.get(pk=other.pk).status == PartOrder.Status.CANCELLED
    assert client.get(f"/beheer/parts/partorder/{other.pk}/picklist/").status_code == 200


def test_employee_cannot_deliver(client, site, parts):
    request = answered_request(parts)
    order = PartOrder.objects.create(number="WS17000AA-1", request=request, customer=parts["customer"])
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get(f"/beheer/parts/partorder/{order.pk}/deliver/").status_code == 403


def test_customer_page_shows_parts(client, site, parts, beheerder):
    answered_request(parts)
    client.force_login(beheerder)
    page = client.get(f"/beheer/customers/customer/{parts['customer'].pk}/change/").content.decode()
    assert "WS17000AA" in page


def test_parts_in_sales_report(client, site, parts, beheerder):
    request = answered_request(parts)
    order = PartOrder.objects.create(number="WS17000AA-1", request=request, customer=parts["customer"],
                                     discount_pct=Decimal("10"), small_order_costs=Decimal("15"))
    line = order.lines.create(request_line=request.lines.get(), packing="new", quantity=3, unit_price=Decimal("20"),
                              purchase_price=Decimal("10"))
    Correction.objects.create(line=line, quantity=-1)
    PartOrder.objects.create(number="WS17000AA-2", request=request, customer=parts["customer"],
                             status=PartOrder.Status.CANCELLED, small_order_costs=Decimal("15"))
    client.force_login(beheerder)
    report = client.get("/beheer/rapportage/", {"kind": "parts"}).context["report"]
    # 2 parts left × € 20 − 10% = 36, + surcharge 15 = 51; cost 2 × € 10 = 20; the cancelled order is left out
    assert report["totals"]["revenue"] == Decimal("51.00") and report["totals"]["cost"] == Decimal("20.00")
    assert report["totals"]["count"] == 2
    assert client.get("/beheer/rapportage/", {"kind": "packs"}).context["report"]["totals"]["revenue"] == 0
    assert client.get("/beheer/rapportage/").context["report"]["totals"]["revenue"] == Decimal("51.00")
