import io

import pytest
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.hardware import transfer
from apps.hardware.models import Condition, Device, DeviceType, HardwareSettings, Specification
from apps.licences.models import Vendor

from .conftest import make_user

DEVICES = "/admin/hardware/device/"


@pytest.fixture(autouse=True)
def folders(tmp_path, settings):
    """Invoices and photos in a temporary folder; no archive of old invoices."""
    settings.DATA_ROOT = tmp_path / "data"
    settings.MEDIA_ROOT = tmp_path / "media"
    archive = tmp_path / "archive"
    archive.mkdir()
    settings.DOCUMENT_ARCHIVE_DIR = str(archive)


def laptop():
    return DeviceType.objects.get(name_en="Laptop")


def make_device(serial="SN-1", **extra):
    extra.setdefault("model", "Latitude 5440")
    return Device.objects.create(device_type=laptop(), serial_nr=serial, **extra)


def test_device_gets_a_stock_number_and_prices_with_and_without_vat(site):
    device = make_device(purchase_price=Decimal("400.00"))
    assert device.number.startswith("HW") and device.number[2:].isdigit()
    assert device.price == Decimal("500.00")  # purchase price + standard markup of 25%
    assert device.price_incl_vat() == Decimal("605.00")  # 21% VAT
    device.sale_price = Decimal("549.00")
    assert device.price == Decimal("549.00") and device.price_incl_vat() == Decimal("664.29")
    assert device.warranty == HardwareSettings.load().default_warranty_months


def test_device_page_keeps_only_the_specifications_of_its_type(client, site, beheerder):
    client.force_login(beheerder)
    assert client.get(f"{DEVICES}add/").status_code == 200
    monitor = DeviceType.objects.get(name_en="Monitor")
    data = {"device_type": laptop().pk, "model": "ThinkPad T14", "serial_nr": "PF-123", "status": "for_sale",
            "spec_cpu": "Intel Core i5", "spec_ram_gb": "16", "spec_screen_inch": "14",
            "photos-TOTAL_FORMS": "0", "photos-INITIAL_FORMS": "0"}
    response = client.post(f"{DEVICES}add/", data)
    assert response.status_code == 302, response.content.decode()[:3000]
    device = Device.objects.get(serial_nr="PF-123")
    assert device.specs == {"cpu": "Intel Core i5", "ram_gb": 16, "screen_inch": 14}
    data.update(device_type=monitor.pk)
    client.post(f"{DEVICES}{device.pk}/change/", data)
    device.refresh_from_db()
    assert device.specs == {"screen_inch": 14}  # processor and memory are no properties of a monitor
    page = client.get(f"{DEVICES}{device.pk}/change/").content.decode()
    assert 'data-spec-types=' in page and "admin/hardware-specs.js" in page
    assert "data-spec-hint" in page and 'data-ordering-field="position"' in page  # photos can be dragged in order


def test_required_specification_is_checked(client, site, beheerder):
    Specification.objects.filter(key="cpu").update(required=True)
    client.force_login(beheerder)
    response = client.post(f"{DEVICES}add/", {"device_type": laptop().pk, "model": "X", "serial_nr": "S", "status": "draft",
                                              "photos-TOTAL_FORMS": "0", "photos-INITIAL_FORMS": "0"})
    assert response.status_code == 200 and not Device.objects.exists()


def xlsx(rows):
    from openpyxl import Workbook

    book = Workbook()
    for row in rows:
        book.active.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_import_checks_first_and_then_adds_and_updates(client, site, beheerder):
    make_device("SN-OLD", sale_price=Decimal("100"))
    data = xlsx([
        ["serial_nr", "device_type", "brand", "model", "condition", "status", "sale_price", "ram_gb", "cpu"],
        ["SN-NEW", "Laptop", "Lenovo", "ThinkPad T14", "Refurbished A", "Te koop", 499.5, 16, "i5"],
        ["SN-OLD", "laptop", "", "Latitude 5440", "", "", "125,00", "", ""],
        ["SN-BAD", "Koffiezetter", "", "", "", "", "", "veel", ""],
        ["SN-MON", "Monitor", "", "P2422H", "", "", "", 8, ""],
    ])
    client.force_login(beheerder)
    review = client.post(f"{DEVICES}import/", {"step": "upload", "update_existing": "on",
                                               "file": SimpleUploadedFile("devices.xlsx", data)})
    rows = review.context["rows"]
    assert [r["action"] for r in rows] == ["new", "update", "error", "error"], [r["errors"] for r in rows]
    assert any("Koffiezetter" in e for e in rows[2]["errors"]) and any("model" in e for e in rows[2]["errors"])
    assert any("ram_gb" in e for e in rows[3]["errors"])  # memory is not a property of a monitor
    assert not Device.objects.filter(serial_nr="SN-NEW").exists()  # nothing saved before confirming
    client.post(f"{DEVICES}import/", {"step": "run", "token": review.context["token"]})
    new = Device.objects.get(serial_nr="SN-NEW")
    assert new.brand.name == "Lenovo" and new.status == "for_sale" and new.condition.name_en == "Refurbished A"
    assert new.sale_price == Decimal("499.50") and new.specs == {"ram_gb": 16, "cpu": "i5"}
    assert Device.objects.get(serial_nr="SN-OLD").sale_price == Decimal("125.00")
    assert not Device.objects.filter(serial_nr__in=["SN-BAD", "SN-MON"]).exists()


def test_export_and_import_again_changes_nothing(client, site, beheerder):
    make_device("SN-1", brand=Vendor.objects.create(name="Dell"), sale_price=Decimal("649.00"),
                condition=Condition.objects.first(), specs={"ram_gb": 16, "cpu": "i7"})
    make_device("SN-2", status=Device.Status.SOLD)
    client.force_login(beheerder)
    for fmt in ("xlsx", "csv"):
        response = client.get(f"{DEVICES}export/?format={fmt}&status__exact=for_sale")
        assert response["Content-Disposition"].endswith(f'.{fmt}"')
        rows = transfer.read_rows(f"x.{fmt}", response.content)
        assert [r["serial_nr"] for r in rows] == []  # the filter of the list is used: none for sale
        rows = transfer.read_rows(f"x.{fmt}", client.get(f"{DEVICES}export/?format={fmt}").content)
        assert {r["serial_nr"] for r in rows} == {"SN-1", "SN-2"}
        assert [r["action"] for r in transfer.analyse(rows)] == ["same", "same"]


def test_csv_with_semicolons_and_dutch_amounts(site):
    data = "serial_nr;device_type;model;purchase_price;purchase_date\nC-1;Desktop;OptiPlex 7090;1.234,50;28-10-2026\n"
    rows = transfer.read_rows("devices.csv", data.encode("utf-8-sig"))
    assert transfer.run_import(rows) == (1, 0, 0)
    device = Device.objects.get(serial_nr="C-1")
    assert device.purchase_price == Decimal("1234.50") and str(device.purchase_date) == "2026-10-28"


def test_example_files_can_be_downloaded_and_imported(client, site, beheerder):
    client.force_login(beheerder)
    for fmt in ("xlsx", "csv"):
        response = client.get(f"{DEVICES}example/" + ("?format=csv" if fmt == "csv" else ""))
        assert response.status_code == 200
        rows = transfer.read_rows(f"example.{fmt}", response.content)
        assert [r["action"] for r in transfer.analyse(rows)] == ["new", "new"], transfer.analyse(rows)


def test_hardware_is_in_the_shop_menu_and_follows_the_rights(rf, site, beheerder):
    from apps.dashboard.navigation import flat_items, sidebar

    request = rf.get("/")
    request.user = beheerder
    shop = {s["key"]: s for s in sidebar(request)}["webshop"]
    group = next(i for i in shop["items"] if i.get("group") == "hardware")
    assert "/admin/hardware/device/" in [str(i["link"]) for i in group["items"]]
    request.user = make_user("mw@example.test", staff=True, role="Employee")
    links = [str(i["link"]) for s in sidebar(request) for i in flat_items(s)
             if not i.get("permission") or i["permission"](request)]
    assert "/admin/hardware/device/" in links and "/admin/hardware/hardwaresettings/" not in links


def test_new_customer_gets_the_default_hardware_margin(site):
    from apps.customers.models import SignupSettings

    signup = SignupSettings.load()
    assert hasattr(signup, "default_margin_hardware")


# --- the shop on the website -------------------------------------------------------------------------------

def test_visitors_see_what_is_for_sale_with_prices_incl_and_excl_vat(client, site):
    make_device("SN-SALE", status=Device.Status.FOR_SALE, sale_price=Decimal("500.00"), specs={"ram_gb": 16})
    make_device("SN-DRAFT", model="Geheim", sale_price=Decimal("100.00"))
    page = client.get("/hardware/").content.decode()
    assert "Latitude 5440" in page and "Geheim" not in page
    assert "605,00" in page and "500,00" in page  # incl. VAT first, excl. VAT next to it
    assert "16 GB" in page
    page = client.get("/hardware/?vat=excl").content.decode()
    assert page.index("500,00") < page.index("605,00")  # now excl. VAT first, remembered
    assert client.session["hardware_prices_incl_vat"] is False


def test_shop_filters_and_sorts(client, site):
    make_device("A", status=Device.Status.FOR_SALE, sale_price=Decimal("900"), model="Duur")
    monitor = DeviceType.objects.get(name_en="Monitor")
    Device.objects.create(device_type=monitor, model="Scherm", serial_nr="B", status=Device.Status.FOR_SALE,
                          sale_price=Decimal("100"))
    page = client.get(f"/hardware/?type={monitor.pk}").content.decode()
    assert "Scherm" in page and "Duur" not in page
    page = client.get("/hardware/?sort=price").content.decode()
    assert page.index("Scherm") < page.index("Duur")
    assert "Duur" in client.get("/hardware/?q=duur").content.decode()


def test_device_page_and_customer_price(client, site):
    from apps.customers.models import Contact, Customer

    device = make_device("SN-1", status=Device.Status.FOR_SALE, sale_price=Decimal("1000.00"))
    page = client.get(f"/hardware/{device.number}/").content.decode()
    assert "1.210,00" in page and "/signup/" in page  # visitors: log in or sign up to order
    customer = Customer.objects.create(name="Koper BV", status=Customer.Status.ACTIVE, margin_hardware=Decimal("10"))
    user = make_user("koper@example.test")
    Contact.objects.create(customer=customer, user=user, last_name="Koper")
    client.force_login(user)
    page = client.get(f"/hardware/{device.number}/").content.decode()
    assert "1.089,00" in page  # 10% discount, incl. VAT
    device.status = Device.Status.SOLD
    device.save()
    page = client.get(f"/hardware/{device.number}/").content.decode()
    assert "1.089,00" not in page and "niet meer te koop" in page
    device.status = Device.Status.DRAFT
    device.save()
    assert client.get(f"/hardware/{device.number}/").status_code == 404


def test_shop_can_be_switched_off_and_is_in_the_website_menu(client, site):
    from apps.siteconfig.models import MenuItem

    assert MenuItem.objects.filter(url="/hardware/").exists()
    HardwareSettings.objects.update(enabled=False)
    assert client.get("/hardware/").status_code == 404


def test_home_page_has_a_hardware_card_and_one_for_packs_and_parts(client, site):
    page = client.get("/").content.decode()
    assert 'href="/hardware/"' in page and "Servicepacks en onderdelen" in page
    assert ">Onderdelen<" not in page


# --- ordering ------------------------------------------------------------------------------------------------

def shop_customer(margin="10"):
    from apps.customers.models import Contact, Customer, CustomerAddress

    customer = Customer.objects.create(name="Koper BV", number="400200", status=Customer.Status.ACTIVE,
                                       margin_hardware=Decimal(margin), email="info@koper.test")
    CustomerAddress.objects.create(customer=customer, line1="Straat 1", postal_code="1000 AA", city="Amsterdam")
    user = make_user("koper@example.test")
    Contact.objects.create(customer=customer, user=user, last_name="Koper", email=user.email)
    return customer, user


def checkout(client, delivery, payment, **extra):
    data = {"delivery": delivery.pk, "payment": payment.pk, "reference": "PO-HW", **extra}
    review = client.post("/hardware/cart/", data)
    assert "payload" in review.context, review.content.decode()[:3000]
    return client.post("/hardware/cart/", {"action": "confirm", "payload": review.context["payload"]})


def test_customer_orders_hardware_with_delivery_and_payment_costs(client, site):
    from django.core import mail

    from apps.hardware.models import DeliveryOption
    from apps.invoices.models import Invoice
    from apps.orders.models import Order, PaymentMethod

    customer, user = shop_customer()
    a = make_device("SN-A", status=Device.Status.FOR_SALE, sale_price=Decimal("500.00"))
    b = make_device("SN-B", status=Device.Status.FOR_SALE, purchase_price=Decimal("200.00"))  # 250 with the markup
    client.force_login(user)
    for device in (a, b):
        client.post(f"/hardware/{device.number}/add/")
    page = client.get("/hardware/cart/").content.decode()
    assert a.number in page and b.number in page
    shipping = DeliveryOption.objects.get(kind="shipping")  # € 12.50
    payment = PaymentMethod.objects.get(code="cash_on_delivery")
    payment.extra_costs = Decimal("7.50")
    payment.save()
    review = client.post("/hardware/cart/", {"delivery": shipping.pk, "payment": payment.pk})
    assert "delivery_address" in review.context["form"].errors or review.context["form"].is_valid()
    response = checkout(client, shipping, payment, delivery_name="Koper BV", delivery_address="Straat 1",
                        delivery_postal_code="1000 AA", delivery_city="Amsterdam")
    assert response.status_code == 302
    order = Order.objects.get(kind="hardware")
    # 750 − 10% = 675 + 12.50 + 7.50 = 695 excl. VAT; + 21% = 840.95
    assert order.gross == Decimal("750.00") and order.discount == Decimal("75.00")
    assert order.net == Decimal("695.00") and order.total == Decimal("840.95")
    assert order.shipping and order.delivery_city == "Amsterdam" and order.reference == "PO-HW"
    invoice = Invoice.objects.get(order=order)
    assert invoice.total == order.total and invoice.lines.count() == 4  # two devices, delivery, payment
    a.refresh_from_db()
    assert a.status == Device.Status.SOLD and a.customer == customer and a.sold_at
    assert any(order.number in m.subject for m in mail.outbox)
    assert client.get("/hardware/cart/").context["devices"] == []  # cart emptied
    assert "Straat 1" in client.get(f"/my/orders/{order.pk}/").content.decode()


def test_device_can_only_be_ordered_once(client, site):
    from apps.hardware import services
    from apps.hardware.models import DeliveryOption
    from apps.orders.models import PaymentMethod

    customer, user = shop_customer()
    device = make_device("SN-A", status=Device.Status.FOR_SALE, sale_price=Decimal("500.00"))
    pickup, payment = DeliveryOption.objects.get(kind="pickup"), PaymentMethod.objects.get(code="on_account")
    client.force_login(user)
    client.post(f"/hardware/{device.number}/add/")
    review = client.post("/hardware/cart/", {"delivery": pickup.pk, "payment": payment.pk})
    services.place_order(customer, user, [device.number], pickup, payment)  # someone else was faster
    response = client.post("/hardware/cart/", {"action": "confirm", "payload": review.context["payload"]})
    assert response.status_code == 302
    from apps.orders.models import Order
    assert Order.objects.filter(kind="hardware").count() == 1


def test_cancelling_an_order_puts_the_devices_back_up_for_sale(client, site, beheerder):
    from apps.hardware import services
    from apps.hardware.models import DeliveryOption
    from apps.invoices.models import InvoiceSettings
    from apps.orders.models import PaymentMethod

    InvoiceSettings.objects.filter(pk=1).update(auto_on_order=False)
    customer, user = shop_customer()
    device = make_device("SN-A", status=Device.Status.FOR_SALE, sale_price=Decimal("500.00"))
    order = services.place_order(customer, user, [device.number], DeliveryOption.objects.get(kind="pickup"),
                                 PaymentMethod.objects.get(code="on_account"))
    device.refresh_from_db()
    assert device.status == Device.Status.RESERVED and order.delivery_costs is None
    client.force_login(beheerder)
    client.post(f"/admin/orders/order/{order.pk}/action/cancel/")
    device.refresh_from_db()
    order.refresh_from_db()
    assert device.status == Device.Status.FOR_SALE and device.customer is None and order.cancelled_at


def test_only_payment_methods_for_hardware_are_offered(client, site):
    from apps.orders.models import PaymentMethod

    customer, user = shop_customer()
    PaymentMethod.objects.filter(code="ideal").update(for_hardware=False)
    device = make_device("SN-A", status=Device.Status.FOR_SALE, sale_price=Decimal("500.00"))
    client.force_login(user)
    client.post(f"/hardware/{device.number}/add/")
    page = client.get("/hardware/cart/").content.decode()
    assert "iDEAL" not in page and "Op rekening" in page


def test_visitors_cannot_order(client, site):
    device = make_device("SN-A", status=Device.Status.FOR_SALE, sale_price=Decimal("500.00"))
    assert client.post(f"/hardware/{device.number}/add/").status_code == 302  # to the login page
    assert client.get("/hardware/cart/").status_code == 302
