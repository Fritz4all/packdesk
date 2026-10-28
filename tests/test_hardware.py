import io
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile

from apps.hardware import transfer
from apps.hardware.models import Condition, Device, DeviceType, HardwareSettings, Specification
from apps.licences.models import Vendor

from .conftest import make_user

DEVICES = "/admin/hardware/device/"


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
