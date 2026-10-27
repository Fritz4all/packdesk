import datetime
from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.customers.models import Contact, Customer, CustomerAddress
from apps.faults.models import FaultAttachment, FaultReport, FaultSettings, RepairOption
from apps.licences.models import (
    Category, HardwareClass, HardwareSystem, Licence, LicenceOption, OptionType, SupportPack, SupportPeriod,
    SupportService, Vendor,
)

from .conftest import make_user

TODAY = timezone.localdate()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, settings):
    settings.DATA_ROOT = tmp_path / "data"


@pytest.fixture
def registered(db):
    customer = Customer.objects.create(name="Reseller BV", number="7", status=Customer.Status.ACTIVE,
                                       email="info@reseller.test", phone="020-1")
    CustomerAddress.objects.create(customer=customer, line1="Straat 1", postal_code="1000 AA", city="Amsterdam")
    hp = Vendor.objects.create(name="HP")
    cls = HardwareClass.objects.create(name="A")
    pack = SupportPack.objects.create(category=Category.objects.create(name="Server"), hardware_class=cls,
                                      service=SupportService.objects.create(abbreviation="X", name="On site"),
                                      period=SupportPeriod.objects.create(years=3), price=Decimal("1"))
    lic = Licence.create_for(pack, customer)[0]
    lic.registered_on = timezone.now()
    lic.system = HardwareSystem.objects.create(vendor=hp, hardware_class=cls, name="DL380")
    lic.vendor = hp
    lic.description = "Server"
    lic.serial_nr = "CZJ123"
    lic.start_date, lic.end_date = TODAY, TODAY + datetime.timedelta(days=300)
    lic.save()
    LicenceOption.objects.create(licence=lic, option_type=OptionType.objects.create(name="Disk"), vendor=hp,
                                 description="1 TB", serial_nr="CZJ123/001")
    return lic


def form_data(**extra):
    data = {
        "action": "send", "vendor": "HP", "device": "Server", "serial_nr": "XYZ999", "description": "Start niet op",
        "repair_option": RepairOption.objects.first().pk, "reseller_name": "Reseller BV", "reseller_address": "Straat 1",
        "reseller_postal_code": "1000 AA", "reseller_city": "Amsterdam", "reseller_phone": "020-1",
        "location_name": "Eindklant BV", "location_contact": "Piet", "location_address": "Weg 2",
        "location_postal_code": "2000 BB", "location_city": "Haarlem", "location_phone": "023-1",
        "location_email": "piet@eindklant.test",
    }
    data.update(extra)
    return data


def test_default_options_and_texts(db):
    assert RepairOption.objects.count() == 3
    assert "{number}" in FaultSettings.load().confirmation_subject_nl


def test_report_without_licence(client, site):
    FaultSettings.objects.filter(pk=1).update(recipients="service@example.test", cc="chef@example.test")
    response = client.post("/storing-melden/", form_data())
    assert response.status_code == 302 and response["Location"] == "/storing-melden/verzonden/"
    fault = FaultReport.objects.get()
    assert fault.number == "1" and fault.status == "new" and not fault.is_covered and fault.licence is None
    report, confirmation = mail.outbox
    assert report.to == ["service@example.test"] and report.cc == ["chef@example.test"]
    assert "No cover found" in report.subject or "Geen dekking" in report.subject
    assert confirmation.to == ["piet@eindklant.test"] and "1" in confirmation.subject


def test_lookup_fills_device_and_shows_cover(client, site, registered):
    page = client.post("/storing-melden/", {"action": "lookup", "lookup": registered.full_number}).content.decode()
    assert 'value="CZJ123"' in page and 'value="Reseller BV"' in page
    assert "message-success" in page


def test_lookup_by_option_serial(client, site, registered):
    page = client.post("/storing-melden/", {"action": "lookup", "lookup": "czj123/001"}).content.decode()
    assert 'value="CZJ123/001"' in page and 'value="1 TB"' in page


def test_expired_licence_is_reported_as_not_covered(client, site, registered):
    Licence.objects.filter(pk=registered.pk).update(end_date=TODAY - datetime.timedelta(days=1))
    page = client.post("/storing-melden/", {"action": "lookup", "lookup": "CZJ123"}).content.decode()
    assert "message-error" in page
    client.post("/storing-melden/", form_data(serial_nr="CZJ123"))
    fault = FaultReport.objects.get()
    assert fault.licence == registered and not fault.is_covered


def test_covered_report_links_licence_and_customer(client, site, registered):
    client.post("/storing-melden/", form_data(serial_nr="CZJ123", lookup=registered.full_number))
    fault = FaultReport.objects.get()
    assert fault.licence == registered and fault.customer == registered.customer and fault.is_covered
    assert "UNDER CONTRACT" in mail.outbox[0].subject or "ONDER CONTRACT" in mail.outbox[0].subject


def test_attachments_are_stored_privately_and_mailed(client, site, beheerder):
    data = form_data()
    data["attachments"] = [SimpleUploadedFile("foto.jpg", b"jpgdata", content_type="image/jpeg")]
    client.post("/storing-melden/", data)
    item = FaultAttachment.objects.get()
    assert item.name == "foto.jpg" and item.size == 7
    assert mail.outbox[0].attachments[0][0] == "foto.jpg"
    assert client.get(f"/storing-bijlage/{item.pk}/").status_code == 302  # not logged in → login page
    client.force_login(make_user("klant@example.test"))
    assert client.get(f"/storing-bijlage/{item.pk}/").status_code == 302  # customers are not staff
    client.force_login(beheerder)
    response = client.get(f"/storing-bijlage/{item.pk}/")
    assert response.status_code == 200 and b"".join(response.streaming_content) == b"jpgdata"


def test_attachment_limits(client, site):
    FaultSettings.objects.filter(pk=1).update(max_attachments=1, max_attachment_mb=1)
    data = form_data()
    data["attachments"] = [SimpleUploadedFile("a.txt", b"a"), SimpleUploadedFile("b.txt", b"b")]
    assert client.post("/storing-melden/", data).status_code == 200
    data["attachments"] = [SimpleUploadedFile("big.bin", b"x" * (1024 * 1024 + 1))]
    assert client.post("/storing-melden/", data).status_code == 200
    assert not FaultReport.objects.exists()


def test_required_fields(client, site):
    response = client.post("/storing-melden/", form_data(location_email="", description=""))
    assert response.status_code == 200 and not FaultReport.objects.exists()


def test_logged_in_customer_gets_prefilled_form_and_list(client, site, registered):
    user = make_user("ik@reseller.test")
    Contact.objects.create(customer=registered.customer, user=user, last_name="Ik", email=user.email)
    client.force_login(user)
    assert 'value="Reseller BV"' in client.get("/storing-melden/").content.decode()
    client.post("/storing-melden/", form_data())
    fault = FaultReport.objects.get()
    assert fault.customer == registered.customer and fault.reported_by == user
    assert fault.number in client.get("/mijn/storingen/").content.decode()


def test_disabled_form(client, site):
    FaultSettings.objects.filter(pk=1).update(enabled=False)
    assert client.get("/storing-melden/").status_code == 404


def test_admin_status_actions(client, site, beheerder):
    client.post("/storing-melden/", form_data())
    fault = FaultReport.objects.get()
    client.force_login(beheerder)
    page = client.get(f"/admin/faults/faultreport/{fault.pk}/change/").content.decode()
    assert "/action/in-progress/" in page
    client.post(f"/admin/faults/faultreport/{fault.pk}/action/close/")
    fault.refresh_from_db()
    assert fault.status == "closed"


def test_home_page_links_to_fault_form(client, site):
    assert 'href="/storing-melden/"' in client.get("/").content.decode()
