from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.admin.sites import site as admin_site
from django.core.files.base import ContentFile
from django.forms import inlineformset_factory
from django.test import RequestFactory
from django.utils import timezone

from apps.customers.models import Contact, Customer, CustomerAddress
from apps.faults.models import FaultAttachment, FaultReport
from apps.licences.models import Category, HardwareClass, Licence, SupportPack, SupportPeriod, SupportService
from apps.orders.models import Order, OrderLine
from apps.trash import admin_hooks
from apps.trash.models import TrashEntry
from apps.trash.services import RestoreError, delete_for_good, delete_to_trash, purge_old, restore

from .conftest import make_user


@pytest.fixture
def customer(db):
    customer = Customer.objects.create(name="Weg BV", number="900", status=Customer.Status.ACTIVE)
    CustomerAddress.objects.create(customer=customer, line1="Straat 1", city="Stad")
    Contact.objects.create(customer=customer, last_name="Jansen", email="jansen@weg.test")
    return customer


def test_deleting_keeps_everything_and_restore_puts_it_back(customer):
    pk, address_pk = customer.pk, customer.addresses.get().pk
    delete_to_trash(customer)
    assert not Customer.objects.exists() and not CustomerAddress.objects.exists() and not Contact.objects.exists()
    entry = TrashEntry.objects.get()
    assert entry.label == "Weg BV (900)" and entry.object_count == 3
    assert entry.summary.count("1×") == 2  # one address and one contact deleted along with it

    restore(entry)
    restored = Customer.objects.get(pk=pk)
    assert restored.number == "900" and restored.addresses.get().pk == address_pk
    assert restored.contacts.get().email == "jansen@weg.test" and not TrashEntry.objects.exists()


def test_links_that_were_emptied_come_back(db):
    customer = Customer.objects.create(name="Koper", number="901")
    pack = SupportPack.objects.create(
        code="X", category=Category.objects.create(name="C"), hardware_class=HardwareClass.objects.create(name="H"),
        service=SupportService.objects.create(abbreviation="S", name="S"), period=SupportPeriod.objects.create(years=1),
        price=Decimal("10"),
    )
    order = Order.objects.create(number="7", customer=customer)
    line = OrderLine.objects.create(order=order, pack=pack, description="d", quantity=1, unit_price=1, line_total=1)
    licence = Licence.objects.create(number="1", pack=pack, customer=customer, order_line=line)
    delete_to_trash(order)
    licence.refresh_from_db()
    assert licence.order_line is None  # the deletion emptied the link

    restore(TrashEntry.objects.get())
    licence.refresh_from_db()
    assert licence.order_line_id == line.pk and Order.objects.get().lines.count() == 1


def test_restore_refuses_when_the_item_exists_again(customer):
    pk = customer.pk
    delete_to_trash(customer)
    Customer.objects.create(pk=pk, name="Nieuw", number="902")
    with pytest.raises(RestoreError):
        restore(TrashEntry.objects.get())
    assert TrashEntry.objects.count() == 1 and Customer.objects.get().name == "Nieuw"


def test_delete_for_good_removes_files(db, settings):
    report = FaultReport.objects.create(number="S1", device="d", description="x", reseller_name="r",
                                        location_name="l", location_contact="c", location_address="a",
                                        location_postal_code="p", location_city="c", location_phone="1",
                                        location_email="l@x.test")
    attachment = FaultAttachment(report=report, name="foto.jpg", size=4)
    attachment.file.save("foto.jpg", ContentFile(b"JPEG"), save=True)
    path = attachment.file.path
    delete_to_trash(report)
    import os

    assert os.path.exists(path)  # kept while in the trash
    delete_for_good(TrashEntry.objects.get())
    assert not os.path.exists(path) and not TrashEntry.objects.exists()


def test_old_items_are_emptied(customer):
    delete_to_trash(customer)
    TrashEntry.objects.update(deleted_at=timezone.now() - timedelta(days=40))
    assert purge_old(0) == 0 and TrashEntry.objects.count() == 1  # 0 = keep
    assert purge_old(30) == 1 and not TrashEntry.objects.exists()


# --- admin -------------------------------------------------------------------------------------


def test_admin_delete_and_bulk_delete_go_to_the_trash(client, site, customer):
    other = Customer.objects.create(name="Ook weg", number="903")
    admin_user = make_user("root@example.test", superuser=True)
    client.force_login(admin_user)
    client.post(f"/admin/customers/customer/{customer.pk}/delete/", {"post": "yes"})
    client.post("/admin/customers/customer/", {"action": "delete_selected", "_selected_action": [other.pk],
                                                 "post": "yes"})
    assert not Customer.objects.exists()
    assert TrashEntry.objects.count() == 2 and TrashEntry.objects.filter(deleted_by=admin_user).count() == 2


def test_rows_removed_in_a_form_go_to_the_trash(customer):
    address = customer.addresses.get()
    FormSet = inlineformset_factory(Customer, CustomerAddress, fields=["line1", "city"], extra=0, can_delete=True)
    data = {"addresses-TOTAL_FORMS": "1", "addresses-INITIAL_FORMS": "1", "addresses-MIN_NUM_FORMS": "0",
            "addresses-MAX_NUM_FORMS": "10", "addresses-0-id": str(address.pk), "addresses-0-line1": "Straat 1",
            "addresses-0-city": "Stad", "addresses-0-DELETE": "on"}
    formset = FormSet(data, instance=customer, prefix="addresses")
    assert formset.is_valid()
    request = RequestFactory().post("/")
    request.user = make_user("root@example.test", superuser=True)
    admin_hooks._save_formset(admin_site._registry[Customer], request, None, formset, True)
    assert not CustomerAddress.objects.exists() and TrashEntry.objects.get().model == "customers.customeraddress"


def test_trash_page_search_restore_and_delete_for_good(client, site, customer):
    other = Customer.objects.create(name="Tweede BV", number="904")
    delete_to_trash(customer)
    delete_to_trash(other)
    client.force_login(make_user("root@example.test", superuser=True))
    page = client.get("/admin/trash/trashentry/?q=Tweede")
    assert page.status_code == 200 and "Tweede BV" in page.content.decode() and "Weg BV" not in page.content.decode()
    assert client.get("/admin/trash/trashentry/?o=-1").status_code == 200  # sortable

    entries = list(TrashEntry.objects.values_list("pk", flat=True))
    client.post("/admin/trash/trashentry/", {"action": "restore_selected", "_selected_action": entries})
    assert Customer.objects.count() == 2 and not TrashEntry.objects.exists()

    delete_to_trash(Customer.objects.get(number="904"))
    client.post("/admin/trash/trashentry/", {"action": "delete_selected_for_good",
                                              "_selected_action": list(TrashEntry.objects.values_list("pk", flat=True))})
    assert not TrashEntry.objects.exists() and not Customer.objects.filter(number="904").exists()


def test_trash_needs_permission(client, site, customer):
    delete_to_trash(customer)
    client.force_login(make_user("staff@example.test", staff=True, role="Medewerker"))
    assert client.get("/admin/trash/trashentry/").status_code == 403


# --- logout timeout ----------------------------------------------------------------------------


def test_logout_timeout_for_staff_and_customers(client, site):
    site.session_timeout_staff, site.session_timeout_customers = 30, 5
    site.save()
    client.force_login(make_user("root@example.test", superuser=True))
    client.get("/admin/")
    assert client.session.get_expiry_age() == 30 * 60
    client.force_login(make_user("klant@example.test"))
    client.get("/")
    assert client.session.get_expiry_age() == 5 * 60
