import datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.customers.models import Contact, Customer
from apps.licences.models import (
    Category, HardwareClass, HardwareSystem, Licence, LicenceOption, OptionType, SupportPack, SupportPeriod,
    SupportService, Vendor, add_years,
)
from apps.orders.models import Order, OrderSettings

from .conftest import make_user

TODAY = timezone.localdate()


@pytest.fixture
def shop(db):
    cat = Category.objects.create(name="Server")
    cls = HardwareClass.objects.create(name="A")
    svc = SupportService.objects.create(abbreviation="X", name="On site")
    new_pack = SupportPack.objects.create(category=cat, hardware_class=cls, service=svc,
                                          period=SupportPeriod.objects.create(years=3), price=Decimal("100.00"))
    ext_pack = SupportPack.objects.create(category=cat, hardware_class=cls, service=svc,
                                          period=SupportPeriod.objects.create(years=1, post_warranty=True),
                                          price=Decimal("40.00"))
    customer = Customer.objects.create(name="Koper BV", number="9", status=Customer.Status.ACTIVE,
                                       margin_packs=Decimal("10"), email="info@koper.test", email_orders="orders@koper.test")
    user = make_user("inkoop@koper.test")
    Contact.objects.create(customer=customer, user=user, last_name="Inkoop", email=user.email)
    OrderSettings.objects.filter(pk=1).update(notify_emails="sales@example.test")
    return {"new": new_pack, "ext": ext_pack, "customer": customer, "user": user}


def order_post(lines, **extra):
    data = {"lines-TOTAL_FORMS": str(len(lines)), "lines-INITIAL_FORMS": "0", "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "50", "reference": "PO-77"}
    for i, (pack, qty) in enumerate(lines):
        data.update({f"lines-{i}-pack": pack.pk, f"lines-{i}-quantity": str(qty), f"lines-{i}-reference": f"R{i}"})
    data.update(extra)
    return data


def test_review_shows_totals_like_old_shop(client, site, shop):
    client.force_login(shop["user"])
    response = client.post("/mijn/bestellen/", order_post([(shop["new"], 2), (shop["ext"], 1)]))
    totals = response.context["totals"]
    assert totals["gross"] == Decimal("240.00")
    assert totals["discount"] == Decimal("24.00")  # customer discount 10 %
    assert totals["net"] == Decimal("216.00")
    assert totals["vat"] == Decimal("45.36")  # 21 %
    assert totals["total"] == Decimal("261.36")
    assert not Order.objects.exists()  # nothing saved before confirming


def test_confirm_places_order_with_licences_and_mail(client, site, shop):
    client.force_login(shop["user"])
    payload = client.post("/mijn/bestellen/", order_post([(shop["new"], 2)])).context["payload"]
    response = client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload})
    assert response["Location"] == "/mijn/bestellen/geplaatst/"
    order = Order.objects.get()
    assert order.number == "1" and order.reference == "PO-77" and order.total == Decimal("217.80")
    licences = Licence.objects.filter(order_line__order=order)
    assert licences.count() == 2 and all(lic.customer == shop["customer"] for lic in licences)
    message = mail.outbox[0]
    assert set(message.to) == {"inkoop@koper.test", "orders@koper.test"} and message.bcc == ["sales@example.test"]
    assert licences.first().full_number in message.body and "217,80" in message.body


def test_tampered_payload_is_rejected(client, site, shop):
    client.force_login(shop["user"])
    payload = client.post("/mijn/bestellen/", order_post([(shop["new"], 1)])).context["payload"]
    client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload[:-2] + "xx"})
    assert not Order.objects.exists()


def test_payload_of_other_customer_is_refused(client, site, shop):
    client.force_login(shop["user"])
    payload = client.post("/mijn/bestellen/", order_post([(shop["new"], 1)])).context["payload"]
    other = Customer.objects.create(name="Ander", status=Customer.Status.ACTIVE)
    user2 = make_user("ander@ander.test")
    Contact.objects.create(customer=other, user=user2, last_name="A", email=user2.email)
    client.force_login(user2)
    assert client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload}).status_code == 403


def test_empty_order_and_box_address_validation(client, site, shop):
    client.force_login(shop["user"])
    assert "payload" not in (client.post("/mijn/bestellen/", order_post([])).context or {})
    response = client.post("/mijn/bestellen/", order_post([(shop["new"], 1)], send_boxes="on"))
    assert "payload" not in response.context


def test_only_active_customers_can_order(client, site, shop):
    client.force_login(make_user("losse@gebruiker.test"))
    assert client.get("/mijn/bestellen/").status_code == 403
    Customer.objects.filter(pk=shop["customer"].pk).update(status=Customer.Status.BLOCKED)


def test_extend_licence(client, site, shop):
    old = Licence.create_for(shop["new"], shop["customer"])[0]
    hp = Vendor.objects.create(name="HP")
    old.registered_on = timezone.now()
    old.vendor, old.serial_nr, old.description = hp, "SN1", "Server"
    old.system = HardwareSystem.objects.create(vendor=hp, hardware_class=shop["new"].hardware_class, name="DL")
    old.start_date, old.end_date = TODAY - datetime.timedelta(days=1000), TODAY + datetime.timedelta(days=30)
    old.save()
    LicenceOption.objects.create(licence=old, option_type=OptionType.objects.create(name="Disk"), serial_nr="SN1/001")
    client.force_login(shop["user"])
    page = client.get("/mijn/licenties/?show=ending").content.decode()
    assert f"/mijn/licenties/{old.pk}/verlengen/" in page
    review = client.post(f"/mijn/licenties/{old.pk}/verlengen/", {"pack": shop["ext"].pk})
    assert review.context["totals"]["net"] == Decimal("36.00")
    client.post(f"/mijn/licenties/{old.pk}/verlengen/", {"action": "confirm", "payload": review.context["payload"]})
    new = Licence.objects.get(prolongation_of=old)
    assert new.registered_on and new.serial_nr == "SN1" and new.system == old.system
    assert new.start_date == old.end_date + datetime.timedelta(days=1)
    assert new.end_date == add_years(new.start_date, 1) - datetime.timedelta(days=1)
    assert new.options.get().serial_nr == "SN1/001"
    # Already extended: no second extend button.
    assert f"/mijn/licenties/{old.pk}/verlengen/" not in client.get("/mijn/licenties/").content.decode()


def test_customer_cannot_extend_someone_elses_licence(client, site, shop):
    other = Customer.objects.create(name="Ander", status=Customer.Status.ACTIVE)
    lic = Licence.create_for(shop["new"], other)[0]
    client.force_login(shop["user"])
    assert client.get(f"/mijn/licenties/{lic.pk}/verlengen/").status_code == 404


def test_my_orders_and_detail(client, site, shop):
    client.force_login(shop["user"])
    payload = client.post("/mijn/bestellen/", order_post([(shop["new"], 1)])).context["payload"]
    client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload})
    order = Order.objects.get()
    assert order.number in client.get("/mijn/bestellingen/").content.decode()
    assert client.get(f"/mijn/bestellingen/{order.pk}/").status_code == 200
    client.force_login(make_user("vreemd@x.test"))
    assert client.get(f"/mijn/bestellingen/{order.pk}/").status_code == 403


def test_admin_order_list_and_number_source(client, site, shop, beheerder):
    from apps.numbering.checks import check
    from apps.numbering.models import NumberSequence

    client.force_login(shop["user"])
    payload = client.post("/mijn/bestellen/", order_post([(shop["new"], 1)])).context["payload"]
    client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload})
    client.force_login(beheerder)
    assert "Koper BV" in client.get("/admin/orders/order/").content.decode()
    assert check(NumberSequence.objects.get(key="order")).status == "ok"


def test_report_uses_order_prices(client, site, shop, beheerder):
    client.force_login(shop["user"])
    payload = client.post("/mijn/bestellen/", order_post([(shop["new"], 2)])).context["payload"]
    client.post("/mijn/bestellen/", {"action": "confirm", "payload": payload})
    SupportPack.objects.filter(pk=shop["new"].pk).update(price=Decimal("999"), cost_price=Decimal("50"))
    client.force_login(beheerder)
    report = client.get("/admin/reports/").context["report"]
    assert report["totals"]["revenue"] == Decimal("180.00")  # 2 × 100 at order time, minus 10 %
    assert report["totals"]["cost"] == Decimal("100.00") and report["totals"]["estimated"] == 0
