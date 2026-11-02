import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from django.core import mail
from django.core.management import call_command

from apps.cmdb import diagram, discovery, transfer, warranty
from apps.cmdb.models import (
    CmdbCustomer, CmdbSettings, ConfigurationItem, DiscoveredItem, DiscoverySource, ItemChange, ItemField,
    ItemStatus, ItemType, Relation, RelationKind, WarrantyReminder,
)
from apps.customers.models import Contact, Customer, FieldMode

from .conftest import make_user

LIST_URL = "/admin/cmdb/configurationitem/"


@pytest.fixture
def on(site):
    settings_row = CmdbSettings.load()
    settings_row.enabled = True
    settings_row.save()
    return settings_row


@pytest.fixture
def customer(on):
    row = Customer.objects.create(name="Klant BV", number="K100")
    CmdbCustomer.objects.create(customer=row, enabled=True)
    return row


@pytest.fixture
def hardware(db):
    return ItemType.objects.get(name_en="Hardware")


def item(customer, item_type, name="Server", **fields):
    return ConfigurationItem.objects.create(customer=customer, item_type=item_type, name=name, **fields)


def kind(key):
    return RelationKind.objects.get(key=key)


def in_use_pk():
    return ItemStatus.objects.get(key="in_use").pk


def csv_rows(text):
    return transfer.read_rows("items.csv", text.encode())


# --- switches ------------------------------------------------------------------------------------------------

def test_off_by_default_and_then_nothing_but_the_settings_can_be_reached(client, site, beheerder):
    client.force_login(beheerder)
    assert CmdbSettings.load().enabled is False
    assert client.get(LIST_URL)["Location"] == "/admin/cmdb/cmdbsettings/"  # a bookmark leads to the switch
    assert client.get(LIST_URL + "import/").status_code == 403
    assert client.get(LIST_URL + "export/").status_code == 403
    assert client.get(LIST_URL + "example/").status_code == 403
    assert client.get("/admin/cmdb/cmdbsettings/1/change/").status_code == 200
    page = client.get("/admin/").content.decode()
    assert LIST_URL not in page and "/admin/cmdb/cmdbsettings/" in page


def test_menu_shows_the_items_once_switched_on(client, on, beheerder):
    client.force_login(beheerder)
    assert LIST_URL in client.get("/admin/").content.decode()
    assert client.get(LIST_URL).status_code == 200


def test_customer_form_has_the_switch_only_while_in_use(client, site, beheerder):
    row = Customer.objects.create(name="Klant BV")
    client.force_login(beheerder)
    url = f"/admin/customers/customer/{row.pk}/change/?edit=1"
    assert "cmdb-0-enabled" not in client.get(url).content.decode()
    settings_row = CmdbSettings.load()
    settings_row.enabled = True
    settings_row.save()
    assert 'name="cmdb-0-enabled"' in client.get(url).content.decode()


def test_items_of_a_customer_that_stops_using_the_cmdb_are_hidden_and_kept(client, customer, hardware, beheerder):
    row = item(customer, hardware)
    client.force_login(beheerder)
    assert row.number in client.get(LIST_URL).content.decode()
    CmdbCustomer.objects.filter(customer=customer).update(enabled=False)
    assert row.number not in client.get(LIST_URL).content.decode()
    assert client.get(f"{LIST_URL}{row.pk}/change/").status_code == 302
    assert ConfigurationItem.objects.filter(pk=row.pk).exists()


def test_new_item_cannot_be_given_to_a_customer_without_the_cmdb(client, on, hardware, beheerder):
    other = Customer.objects.create(name="Ander BV")
    client.force_login(beheerder)
    response = client.post(LIST_URL + "add/", {"customer": other.pk, "item_type": hardware.pk, "name": "X", "status": in_use_pk(),
                                               "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0})
    assert response.status_code == 200 and not ConfigurationItem.objects.exists()


def test_customer_with_items_cannot_be_deleted_by_accident(customer, hardware):
    from django.db.models import ProtectedError

    item(customer, hardware)
    with pytest.raises(ProtectedError):
        customer.delete()


def test_someone_without_the_right_is_not_sent_to_the_settings(client, site):
    from django.contrib.auth.models import Permission

    user = make_user("medewerker@example.test", staff=True)
    client.force_login(user)
    assert client.get("/admin/cmdb/cmdbsettings/1/change/").status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_customer"))
    assert client.get("/admin/customers/customer/add/").status_code == 403


# --- portal --------------------------------------------------------------------------------------------------

def portal_user(customer):
    user = make_user("klant@example.test")
    Contact.objects.create(customer=customer, user=user, last_name="Jansen", email=user.email)
    return user


def test_portal_only_with_its_own_switch_and_only_own_items(client, customer, hardware):
    other = Customer.objects.create(name="Ander BV")
    CmdbCustomer.objects.create(customer=other, enabled=True, portal_access=True)
    item(customer, hardware, "Eigen server", description="Geheime notitie")
    item(other, hardware, "Vreemde server")
    client.force_login(portal_user(customer))
    assert client.get("/my/items/").status_code == 404
    assert "/my/items/" not in client.get("/my/").content.decode()
    CmdbCustomer.objects.filter(customer=customer).update(portal_access=True)
    page = client.get("/my/items/").content.decode()
    assert "Eigen server" in page and "Vreemde server" not in page and "Geheime notitie" not in page
    assert "/my/items/" in client.get("/my/").content.decode()
    CmdbSettings.objects.update(enabled=False)
    assert client.get("/my/items/").status_code == 404


def test_customer_login_cannot_open_the_admin_pages(client, customer):
    client.force_login(portal_user(customer))
    for url in (LIST_URL, LIST_URL + "import/", LIST_URL + "export/", LIST_URL + "example/"):
        assert client.get(url).status_code == 302


# --- items, relations, impact, history ---------------------------------------------------------------------

def test_items_get_a_number_from_the_sequence(customer, hardware):
    first, second = item(customer, hardware), item(customer, hardware, "Twee")
    assert first.number == "CI-00001" and second.number == "CI-00002"


def test_contact_must_belong_to_the_customer(customer, hardware):
    from django.core.exceptions import ValidationError

    other = Customer.objects.create(name="Ander BV")
    contact = Contact.objects.create(customer=other, last_name="Jansen", email="j@example.test")
    row = ConfigurationItem(customer=customer, item_type=hardware, name="X", contact=contact)
    with pytest.raises(ValidationError):
        row.full_clean(exclude=["number"])


def test_relations_stay_within_a_customer_and_not_on_itself(customer, hardware):
    from django.core.exceptions import ValidationError

    other = Customer.objects.create(name="Ander BV")
    CmdbCustomer.objects.create(customer=other, enabled=True)
    one, two, foreign = item(customer, hardware), item(customer, hardware, "Twee"), item(other, hardware, "Vreemd")
    Relation(source=one, target=two).full_clean()
    with pytest.raises(ValidationError):
        Relation(source=one, target=foreign).full_clean()
    with pytest.raises(ValidationError):
        Relation(source=one, target=one).full_clean()


def test_item_with_relations_cannot_move_to_another_customer(customer, hardware):
    from django.core.exceptions import ValidationError

    other = Customer.objects.create(name="Ander BV")
    CmdbCustomer.objects.create(customer=other, enabled=True)
    one, two = item(customer, hardware), item(customer, hardware, "Twee")
    Relation.objects.create(source=one, target=two)
    one.customer = other
    with pytest.raises(ValidationError):
        one.full_clean(exclude=["number"])


def test_impact_follows_relations_and_survives_a_circle(customer, hardware):
    power, server, app, unrelated = (item(customer, hardware, n) for n in ("Stroom", "Server", "App", "Los"))
    Relation.objects.create(source=server, kind=kind("runs_on"), target=power)
    Relation.objects.create(source=app, kind=kind("runs_on"), target=server)
    Relation.objects.create(source=power, kind=kind("depends_on"), target=app)  # a circle
    assert {i.name for i in power.affected_items()} == {"Server", "App"}
    assert unrelated.affected_items() == []


def test_admin_keeps_history_with_who_and_what(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": in_use_pk(),
            "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0}
    assert client.post(LIST_URL + "add/", data).status_code == 302
    row = ConfigurationItem.objects.get()
    assert row.changes.count() == 1 and row.changes.first().user == beheerder
    assert client.post(f"{LIST_URL}{row.pk}/change/", {**data, "name": "Nieuwe naam"}).status_code == 302
    change = row.changes.first()
    assert (change.old_value, change.new_value, change.user) == ("Server", "Nieuwe naam", beheerder)
    page = client.get(f"{LIST_URL}{row.pk}/change/").content.decode()
    assert "Nieuwe naam" in page and beheerder.email in page


def test_saving_without_changes_adds_no_history(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    row = item(customer, hardware)
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": in_use_pk(),
            "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0}
    assert client.post(f"{LIST_URL}{row.pk}/change/", data).status_code == 302
    assert row.changes.count() == 0


def test_properties_on_the_form_follow_the_type(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": in_use_pk(),
            "prop_ip_address": "10.0.0.1", "prop_version": "kept away",
            "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0}
    assert client.post(LIST_URL + "add/", data).status_code == 302
    assert ConfigurationItem.objects.get().properties == {"ip_address": "10.0.0.1"}


# --- import ----------------------------------------------------------------------------------------------------

HEAD = "number;customer;type;name;status;serial_nr;purchase_date;relations\n"


def test_new_rows_with_a_relation_to_a_later_row(customer, hardware):
    rows = csv_rows(HEAD + ";K100;Hardware;Laptop;;S1;2026-01-15;depends_on:Server\n"
                           ";K100;Hardware;Server;In gebruik;S2;;\n")
    outcome = transfer.analyse(rows)
    assert [r["action"] for r in outcome] == [transfer.NEW, transfer.NEW]
    assert not ConfigurationItem.objects.exists()  # the check saves nothing
    assert transfer.run_import(rows) == (2, 0, 0)
    laptop = ConfigurationItem.objects.get(name="Laptop")
    assert laptop.purchase_date == datetime.date(2026, 1, 15) and laptop.number.startswith("CI-")
    assert laptop.relations_out.get().target.name == "Server"
    assert laptop.changes.filter(source=ItemChange.Source.IMPORT).exists()


def test_importing_the_same_file_twice_makes_nothing_double(customer, hardware):
    rows = csv_rows(HEAD + ";K100;Hardware;Laptop;;S1;;depends_on:Server\n;K100;Hardware;Server;;S2;;\n")
    transfer.run_import(rows)
    assert [r["action"] for r in transfer.analyse(rows)] == [transfer.SAME, transfer.SAME]
    assert transfer.run_import(rows) == (0, 0, 0)
    assert ConfigurationItem.objects.count() == 2 and Relation.objects.count() == 1


def test_customer_without_the_cmdb_or_unknown_is_an_error_and_other_rows_go_on(customer, hardware):
    other = Customer.objects.create(name="Ander BV", number="K200")
    rows = csv_rows(HEAD + f";{other.number};Hardware;A;;;;\n;K999;Hardware;B;;;;\n;K100;Hardware;C;;;;\n")
    outcome = transfer.analyse(rows)
    assert [r["action"] for r in outcome] == [transfer.ERROR, transfer.ERROR, transfer.NEW]
    assert "does not use" in outcome[0]["errors"][0] or "gebruikt" in outcome[0]["errors"][0]
    assert transfer.run_import(rows) == (1, 0, 2)
    assert list(ConfigurationItem.objects.values_list("name", flat=True)) == ["C"]


def test_import_does_not_move_or_delete_items(customer, hardware):
    other = Customer.objects.create(name="Ander BV", number="K200")
    CmdbCustomer.objects.create(customer=other, enabled=True)
    row = item(customer, hardware, "Server")
    stays = item(customer, hardware, "Blijft staan")
    rows = csv_rows(HEAD + f"{row.number};K200;Hardware;Server;;;;\n")
    assert transfer.analyse(rows)[0]["action"] == transfer.ERROR
    transfer.run_import(rows)
    row.refresh_from_db()
    assert row.customer == customer and ConfigurationItem.objects.filter(pk=stays.pk).exists()


def test_import_cannot_reach_a_hidden_item_by_its_number(customer, hardware):
    row = item(customer, hardware, "Server")
    CmdbCustomer.objects.filter(customer=customer).update(enabled=False)
    outcome = transfer.analyse(csv_rows("number;name\n" + f"{row.number};Gewijzigd\n"))
    assert outcome[0]["action"] == transfer.ERROR
    transfer.run_import(csv_rows("number;name\n" + f"{row.number};Gewijzigd\n"))
    row.refresh_from_db()
    assert row.name == "Server"


def test_missing_column_leaves_the_field_alone_and_an_empty_cell_empties_it(customer, hardware):
    row = item(customer, hardware, "Server", serial_nr="S1", location="Kelder")
    transfer.run_import(csv_rows("number;serial_nr\n" + f"{row.number};\n"))
    row.refresh_from_db()
    assert row.serial_nr == "" and row.location == "Kelder"


def test_several_items_with_the_name_need_a_number(customer, hardware):
    item(customer, hardware, "Laptop")
    item(customer, hardware, "Laptop")
    outcome = transfer.analyse(csv_rows(HEAD + ";K100;Hardware;Laptop;;;;\n"))
    assert outcome[0]["action"] == transfer.ERROR


def test_same_item_twice_in_a_file_is_an_error(customer, hardware):
    outcome = transfer.analyse(csv_rows(HEAD + ";K100;Hardware;Laptop;;;;\n;K100;Hardware;laptop;;;;\n"))
    assert [r["action"] for r in outcome] == [transfer.NEW, transfer.ERROR]


def test_relation_to_another_customer_or_a_row_that_fails_is_an_error(customer, hardware):
    other = Customer.objects.create(name="Ander BV", number="K200")
    CmdbCustomer.objects.create(customer=other, enabled=True)
    foreign = item(other, hardware, "Vreemd")
    outcome = transfer.analyse(csv_rows(HEAD + f";K100;Hardware;A;;;;runs_on:{foreign.number}\n"
                                               ";K100;Hardware;B;;;;runs_on:C\n"
                                               ";K100;Hardware;C;;;nodate;\n"
                                               ";K100;Hardware;D;;;;bad\n"
                                               ";K100;Hardware;E;;;;runs_on:E\n"))
    assert [r["action"] for r in outcome] == [transfer.ERROR] * 5


def test_relations_column_replaces_the_relations_of_the_item(customer, hardware):
    a, b, c = (item(customer, hardware, n) for n in "ABC")
    Relation.objects.create(source=a, kind=kind("runs_on"), target=b)
    rows = csv_rows("number;relations\n" + f"{a.number};uses:{c.number}\n")
    assert transfer.analyse(rows)[0]["action"] == transfer.UPDATE
    transfer.run_import(rows)
    assert list(a.relations_out.values_list("kind__key", "target__name")) == [("uses", "C")]
    assert "C" in a.changes.first().new_value


def test_renamed_item_keeps_a_relation_pointing_at_its_old_name(customer, hardware):
    a, b = item(customer, hardware, "A"), item(customer, hardware, "B")
    rows = csv_rows("number;name;relations\n" + f"{b.number};Nieuw;\n{a.number};A;runs_on:B\n")
    transfer.run_import(rows)
    assert a.relations_out.get().target == b


def test_properties_in_a_file_are_checked(customer, hardware):
    software = ItemType.objects.get(name_en="Software")
    ItemField.objects.create(key="rack_units", name="Rack", kind="number").item_types.add(hardware)
    head = "customer;type;name;rack_units;version\n"
    outcome = transfer.analyse(csv_rows(head + "K100;Hardware;A;2;\nK100;Hardware;B;twee;\nK100;Hardware;C;;9\n"
                                               f"K100;{software};D;;9\n"))
    assert [r["action"] for r in outcome] == [transfer.NEW, transfer.ERROR, transfer.ERROR, transfer.NEW]


def test_required_property_for_a_new_item(customer, hardware):
    ItemField.objects.create(key="rack_units", name="Rack", mode="required").item_types.add(hardware)
    assert transfer.analyse(csv_rows("customer;type;name\nK100;Hardware;A\n"))[0]["action"] == transfer.ERROR


def test_contact_in_a_file_must_be_of_that_customer(customer, hardware):
    Contact.objects.create(customer=customer, last_name="Jansen", email="j@example.test")
    head = "customer;type;name;contact\n"
    outcome = transfer.analyse(csv_rows(head + "K100;Hardware;A;J@example.test\nK100;Hardware;B;x@example.test\n"))
    assert [r["action"] for r in outcome] == [transfer.NEW, transfer.ERROR]


def test_wrong_file_types_and_headers_are_refused(db):
    with pytest.raises(transfer.ImportFileError):
        transfer.read_rows("items.pdf", b"x")
    with pytest.raises(transfer.ImportFileError):
        transfer.read_rows("items.xlsx", b"not excel")
    with pytest.raises(transfer.ImportFileError):
        transfer.read_rows("items.csv", b"a;b\n1;2\n")
    with pytest.raises(transfer.ImportFileError):
        transfer.read_rows("items.csv", b"x" * (transfer.MAX_BYTES + 1))


def test_import_pages_upload_check_and_confirm(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    upload = SimpleUploadedFile("items.csv", (HEAD + ";K100;Hardware;Laptop;;;;\n").encode())
    page = client.post(LIST_URL + "import/", {"step": "upload", "file": upload})
    assert page.status_code == 200 and not ConfigurationItem.objects.exists()
    token = page.context["token"]
    done = client.post(LIST_URL + "import/", {"step": "run", "token": token})
    assert done.status_code == 302 and ConfigurationItem.objects.get().name == "Laptop"
    again = client.post(LIST_URL + "import/", {"step": "run", "token": token})
    assert again.status_code == 302 and ConfigurationItem.objects.count() == 1  # a token works once


def test_cancelled_import_changes_nothing(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    upload = SimpleUploadedFile("items.csv", (HEAD + ";K100;Hardware;Laptop;;;;\n").encode())
    token = client.post(LIST_URL + "import/", {"step": "upload", "file": upload}).context["token"]
    client.post(LIST_URL + "import/", {"step": "cancel", "token": token})
    assert not ConfigurationItem.objects.exists()


def test_rights_for_import_and_export_are_separate(client, customer, hardware):
    from django.contrib.auth.models import Permission

    user = make_user("medewerker@example.test", staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_configurationitem"))
    client.force_login(user)
    page = client.get(LIST_URL)
    assert page.status_code == 200 and "import/" not in page.content.decode() and "export/" not in page.content.decode()
    for url in ("import/", "export/", "example/"):
        assert client.get(LIST_URL + url).status_code == 403


# --- export and example -------------------------------------------------------------------------------------

def test_export_follows_the_filter_and_can_be_imported_again(client, customer, hardware, beheerder):
    software = ItemType.objects.get(name_en="Software")
    server = item(customer, hardware, "Server", serial_nr="S1", warranty_until=datetime.date(2029, 1, 2),
                  properties={"ip_address": "10.0.0.1"})
    app = item(customer, software, "App", properties={"version": "1.2"})
    Relation.objects.create(source=app, kind=kind("runs_on"), target=server)
    client.force_login(beheerder)
    for fmt in ("csv", "xlsx"):
        response = client.get(LIST_URL + f"export/?format={fmt}")
        rows = transfer.read_rows(f"items.{fmt}", response.content)
        assert {r["name"] for r in rows} == {"Server", "App"}
        assert all(r["action"] == transfer.SAME for r in transfer.analyse(rows)), fmt
    filtered = client.get(LIST_URL + f"export/?format=csv&item_type__id__exact={software.pk}")
    assert [r["name"] for r in transfer.read_rows("items.csv", filtered.content)] == ["App"]


def test_export_makes_formulas_harmless_and_import_restores_them(client, customer, hardware, beheerder):
    from openpyxl import load_workbook

    row = item(customer, hardware, "=SUM(A1)", location="@evil", description="+31 6 123")
    client.force_login(beheerder)
    content = client.get(LIST_URL + "export/?format=xlsx").content
    sheet = load_workbook(io.BytesIO(content)).worksheets[0]
    head = [c.value for c in sheet[1]]
    cells = dict(zip(head, [c for c in sheet[2]]))
    assert cells["name"].data_type == "s" and cells["name"].value == "'=SUM(A1)"
    assert cells["location"].value == "'@evil" and cells["description"].value == "'+31 6 123"
    assert all(r["action"] == transfer.SAME for r in transfer.analyse(transfer.read_rows("items.xlsx", content)))
    assert transfer.analyse(transfer.read_rows("items.xlsx", content))[0]["item"].pk == row.pk


def test_example_can_be_downloaded_and_holds_no_real_customers(client, customer, hardware, beheerder):
    from openpyxl import load_workbook

    client.force_login(beheerder)
    response = client.get(LIST_URL + "example/")
    assert "packdesk-cmdb-example.xlsx" in response["Content-Disposition"]
    book = load_workbook(io.BytesIO(response.content))
    assert len(book.worksheets) == 2
    text = " ".join(str(c.value) for sheet in book.worksheets for line in sheet.iter_rows() for c in line)
    assert "EXAMPLE-CUSTOMER" in text and "Klant BV" not in text and "K100" not in text
    assert [c.value for c in book.worksheets[0][1]][:4] == ["number", "customer", "type", "name"]
    assert "ip_address" in [c.value for c in book.worksheets[0][1]]
    csv_example = client.get(LIST_URL + "example/?format=csv")
    assert "packdesk-cmdb-example.csv" in csv_example["Content-Disposition"]


def test_example_with_a_real_customer_number_imports_cleanly(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    content = client.get(LIST_URL + "example/?format=csv").content.replace(b"EXAMPLE-CUSTOMER", b"K100")
    rows = transfer.read_rows("items.csv", content)
    assert [r["action"] for r in transfer.analyse(rows)] == [transfer.NEW, transfer.NEW]
    assert transfer.run_import(rows) == (2, 0, 0)


# --- fields, statuses and relation types can be changed ---------------------------------------------------------

def form_data(customer, hardware, **extra):
    return {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": in_use_pk(),
            "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0, **extra}


def test_a_hidden_field_leaves_the_form_and_the_list_and_keeps_its_value(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    row = item(customer, hardware, serial_nr="ABC123")
    ItemField.objects.filter(key="serial_nr").update(mode=FieldMode.HIDDEN)
    assert 'name="serial_nr"' not in client.get(f"{LIST_URL}{row.pk}/change/").content.decode()
    assert "ABC123" not in client.get(LIST_URL).content.decode()
    assert client.post(f"{LIST_URL}{row.pk}/change/", form_data(customer, hardware)).status_code == 302
    row.refresh_from_db()
    assert row.serial_nr == "ABC123"


def test_a_required_field_is_required_on_the_form_and_in_an_import(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    ItemField.objects.filter(key="location").update(mode=FieldMode.REQUIRED)
    response = client.post(LIST_URL + "add/", form_data(customer, hardware))
    assert response.status_code == 200 and not ConfigurationItem.objects.exists()
    assert client.post(LIST_URL + "add/", form_data(customer, hardware, location="Kantoor")).status_code == 302
    rows = csv_rows("customer;type;name\nK100;Hardware;Zonder locatie\n")
    assert transfer.analyse(rows)[0]["action"] == transfer.ERROR


def test_field_names_can_change_on_form_list_and_history(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    ItemField.objects.filter(key="location").update(name="Ruimte", name_nl="Ruimte", name_en="Ruimte", in_list=True)
    row = item(customer, hardware)
    assert "Ruimte" in client.get(f"{LIST_URL}{row.pk}/change/").content.decode()
    assert "Ruimte" in client.get(LIST_URL).content.decode()
    client.post(f"{LIST_URL}{row.pk}/change/", form_data(customer, hardware, location="Kelder"))
    assert row.changes.first().field == "Ruimte"


def test_a_field_that_is_always_needed_cannot_be_hidden(db):
    from django.core.exceptions import ValidationError

    field = ItemField.objects.get(key="customer")
    field.mode = FieldMode.HIDDEN
    with pytest.raises(ValidationError):
        field.clean()


def test_own_status_and_relation_type_work_in_form_and_import(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    status = ItemStatus.objects.create(key="on_loan", name="Uitgeleend", name_nl="Uitgeleend", name_en="On loan")
    own = RelationKind.objects.create(key="backs_up", name="back-up van", name_nl="back-up van", name_en="backs up")
    target = item(customer, hardware, "Doel")
    assert client.post(LIST_URL + "add/", form_data(customer, hardware, status=status.pk)).status_code == 302
    rows = csv_rows(f"customer;type;name;status;relations\nK100;Hardware;Nas;Uitgeleend;backs_up:{target.number}\n")
    transfer.run_import(rows)
    nas = ConfigurationItem.objects.get(name="Nas")
    assert nas.status == status and nas.relations_out.get().kind == own


def test_an_inactive_status_stays_on_items_that_have_it(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    old = ItemStatus.objects.create(key="old", name="Oud", name_nl="Oud", is_active=False)
    row = item(customer, hardware, status=old)
    assert client.post(f"{LIST_URL}{row.pk}/change/", form_data(customer, hardware, status=old.pk)).status_code == 302
    assert 'value="%s"' % old.pk not in client.get(LIST_URL + "add/").content.decode().split('id="id_status"')[1].split("</select>")[0]


def test_a_relation_type_can_stay_out_of_the_impact(customer, hardware):
    a, b = item(customer, hardware, "A"), item(customer, hardware, "B")
    Relation.objects.create(source=a, kind=kind("uses"), target=b)
    assert b.affected_items() == [a]
    RelationKind.objects.filter(key="uses").update(counts_for_impact=False)
    assert b.affected_items() == []


def test_portal_leaves_out_a_hidden_field(client, customer, hardware):
    CmdbCustomer.objects.filter(customer=customer).update(portal_access=True)
    item(customer, hardware, serial_nr="SERIEEL1")
    ItemField.objects.filter(key="serial_nr").update(mode=FieldMode.HIDDEN)
    from apps.accounts.models import User

    user = User.objects.create_user(email="portal@example.test", password="x", kind=User.Kind.CUSTOMER)
    Contact.objects.create(customer=customer, user=user, last_name="P", email=user.email)
    client.force_login(user)
    page = client.get("/my/items/").content.decode()
    assert "Server" in page and "SERIEEL1" not in page


# --- diagram ---------------------------------------------------------------------------------------------------

def test_diagram_puts_an_item_above_what_it_needs_and_survives_a_circle(customer, hardware):
    a, b, c = (item(customer, hardware, n) for n in "ABC")
    Relation.objects.create(source=a, kind=kind("runs_on"), target=b)
    Relation.objects.create(source=b, kind=kind("runs_on"), target=c)
    drawing = diagram.for_customer(customer)[0]
    height = {n["full_name"]: n["y"] for n in drawing["nodes"]}
    assert height["A"] < height["B"] < height["C"] and len(drawing["edges"]) == 2
    Relation.objects.create(source=c, kind=kind("depends_on"), target=a)
    assert len(diagram.for_customer(customer)[0]["nodes"]) == 3


def test_diagram_page_shows_only_customers_that_use_the_cmdb(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    a, b = item(customer, hardware, "Links"), item(customer, hardware, "Rechts")
    loose = item(customer, hardware, "Los")
    Relation.objects.create(source=a, kind=kind("uses"), target=b)
    other = Customer.objects.create(name="Andere BV", number="K200")
    assert client.get(LIST_URL + "diagram/").status_code == 200
    page = client.get(LIST_URL + f"diagram/?customer={customer.pk}").content.decode()
    assert "<svg" in page and "Links" in page and "gebruikt" in page and loose.number in page
    assert "Andere BV" not in page
    assert "<svg" not in client.get(LIST_URL + f"diagram/?customer={other.pk}").content.decode().split("pd-diagram")[0]
    assert client.get(LIST_URL + "diagram/?customer=abc").status_code == 200


def test_diagram_escapes_names_and_marks_the_item_and_what_it_affects(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    a, b = item(customer, hardware, "<b>x</b>"), item(customer, hardware, "Basis")
    Relation.objects.create(source=a, kind=kind("uses"), target=b)
    page = client.get(f"{LIST_URL}{b.pk}/change/").content.decode()
    assert "is-focus" in page and "is-affected" in page and "<b>x</b>" not in page


def test_diagram_needs_a_login(client, customer):
    assert client.get(LIST_URL + "diagram/").status_code == 302


# --- warranty mails --------------------------------------------------------------------------------------------

@pytest.fixture
def reminders(on):
    on.warranty_mail_enabled = True
    on.warranty_mail_days = "90,30"
    on.warranty_mail_to = "beheer@example.test"
    on.save()
    return on


def days_from_now(days):
    return datetime.date.today() + datetime.timedelta(days=days)


def test_warranty_overview_goes_once_per_moment(customer, hardware, reminders):
    row = item(customer, hardware, warranty_until=days_from_now(60))
    assert warranty.send_due()["overview"] == 1
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["beheer@example.test"] and row.number in mail.outbox[0].body
    assert warranty.send_due()["overview"] == 0 and len(mail.outbox) == 1
    # Closer to the end: the next moment; a new date starts over.
    assert warranty.send_due(days_from_now(35))["overview"] == 1
    row.warranty_until = days_from_now(70)
    row.save()
    assert warranty.send_due()["overview"] == 1


def test_warranty_leaves_out_what_does_not_count(customer, hardware, reminders):
    retired = ItemStatus.objects.get(key="retired")
    item(customer, hardware, "Buiten gebruik", warranty_until=days_from_now(10), status=retired)
    item(customer, hardware, "Verlopen", warranty_until=days_from_now(-1))
    item(customer, hardware, "Ver weg", warranty_until=days_from_now(200))
    item(customer, hardware, "Geen datum")
    assert warranty.due() == []
    item(customer, hardware, "Wel", warranty_until=days_from_now(10))
    CmdbCustomer.objects.filter(customer=customer).update(enabled=False)
    assert warranty.due() == []


def test_warranty_mail_to_customer_only_when_switched_on(customer, hardware, reminders):
    Customer.objects.filter(pk=customer.pk).update(email="klant@example.test")
    item(customer, hardware, warranty_until=days_from_now(10))
    warranty.send_due()
    assert [m.to for m in mail.outbox] == [["beheer@example.test"]]
    CmdbCustomer.objects.filter(customer=customer).update(warranty_mail=True)
    assert warranty.send_due()["customers"] == 1
    assert mail.outbox[-1].to == ["klant@example.test"] and "Klant BV" in mail.outbox[-1].subject
    assert "{" not in mail.outbox[-1].body
    assert warranty.send_due()["customers"] == 0


def test_warranty_mail_not_to_a_blocked_customer(customer, hardware, reminders):
    Customer.objects.filter(pk=customer.pk).update(email="klant@example.test", status=Customer.Status.BLOCKED)
    CmdbCustomer.objects.filter(customer=customer).update(warranty_mail=True)
    item(customer, hardware, warranty_until=days_from_now(10))
    assert warranty.send_due()["customers"] == 0


def test_warranty_tries_again_after_a_failed_mail(customer, hardware, reminders, monkeypatch):
    item(customer, hardware, warranty_until=days_from_now(10))

    def fail(*args, **kwargs):
        raise OSError("no mail server")

    monkeypatch.setattr(warranty, "send_mail", fail)
    assert warranty.send_due()["errors"] == 1 and not WarrantyReminder.objects.exists()
    monkeypatch.undo()
    assert warranty.send_due()["overview"] == 1


def test_warranty_command_does_nothing_while_switched_off(customer, hardware, on):
    item(customer, hardware, warranty_until=days_from_now(10))
    call_command("cmdb_warranty_mails", "--now")
    assert not mail.outbox
    on.warranty_mail_enabled = True
    on.warranty_mail_to = "beheer@example.test"
    on.save()
    call_command("cmdb_warranty_mails", "--now")
    assert len(mail.outbox) == 1


def test_a_placeholder_text_with_odd_braces_does_not_break(customer, hardware, reminders):
    reminders.warranty_subject = reminders.warranty_subject_nl = reminders.warranty_subject_en = "Let op {onbekend} {count}"
    reminders.save()
    Customer.objects.filter(pk=customer.pk).update(email="klant@example.test")
    CmdbCustomer.objects.filter(customer=customer).update(warranty_mail=True)
    item(customer, hardware, warranty_until=days_from_now(10))
    assert warranty.send_due()["errors"] == 0
    assert mail.outbox[-1].subject == "Let op {onbekend} 1"


# --- automatic discovery ---------------------------------------------------------------------------------------

REPORT_URL = "/cmdb/discovery/report/"


@pytest.fixture
def source(customer, hardware):
    row = DiscoverySource(customer=customer, name="Kantoor", item_type=hardware)
    row.token = row.new_token()
    row.save()
    return row


def post_report(client, token, items):
    import json

    return client.post(REPORT_URL, json.dumps({"items": items}), content_type="application/json",
                       headers={"Authorization": f"Bearer {token}"})


def test_report_needs_a_valid_key_of_an_enabled_source(client, source, customer, on):
    assert post_report(client, "wrong", []).status_code == 401
    assert client.post(REPORT_URL, "{}", content_type="application/json").status_code == 401
    assert client.get(REPORT_URL).status_code == 405
    assert post_report(client, source.token, []).status_code == 200
    source.is_active = False
    source.save()
    assert post_report(client, source.token, []).status_code == 401
    source.is_active = True
    source.save()
    CmdbCustomer.objects.filter(customer=customer).update(enabled=False)
    assert post_report(client, source.token, []).status_code == 401
    CmdbCustomer.objects.filter(customer=customer).update(enabled=True)
    on.enabled = False
    on.save()
    assert post_report(client, source.token, []).status_code == 401


def test_the_key_itself_is_not_stored(source):
    assert source.token not in source.token_digest and len(source.token_digest) == 64


def test_report_rejects_what_is_not_a_report(client, source):
    headers = {"Authorization": f"Bearer {source.token}"}
    assert client.post(REPORT_URL, "not json", content_type="application/json", headers=headers).status_code == 400
    assert client.post(REPORT_URL, "[]", content_type="application/json", headers=headers).status_code == 400
    assert post_report(client, source.token, [{}] * (discovery.MAX_ITEMS + 1)).status_code == 400
    response = post_report(client, source.token, ["x", {"name": ""}, {"key": {"a": 1}}, {"name": 1.5, "properties": "x"}])
    assert response.status_code == 200 and response.json()["skipped"] == 3


def test_new_thing_waits_and_accepting_makes_an_item_with_history(client, source, customer, hardware):
    response = post_report(client, source.token, [{"key": "S1", "name": "Nieuw", "serial_nr": "S1", "manufacturer": "Merk",
                                                   "properties": {"ip_address": "192.0.2.5", "version": "niet voor hardware"}}])
    assert response.json()["new"] == 1 and not ConfigurationItem.objects.exists()
    source.refresh_from_db()
    assert source.last_report_at is not None
    found = DiscoveredItem.objects.get()
    made = discovery.accept(found)
    assert (made.customer, made.item_type, made.name, made.serial_nr) == (customer, hardware, "Nieuw", "S1")
    assert made.properties == {"ip_address": "192.0.2.5"}
    assert made.changes.first().source == ItemChange.Source.SCAN
    assert post_report(client, source.token, [{"key": "S1", "name": "Nieuw", "serial_nr": "S1"}]).json()["accepted"] == 1


def test_report_recognises_an_existing_item_and_only_fills_what_it_knows(client, source, customer, hardware):
    row = item(customer, hardware, "Server", serial_nr="S1", location="Kelder", model="Oud")
    assert post_report(client, source.token, [{"key": "S1", "serial_nr": "S1", "model": "Nieuw", "name": ""}]).json()["changed"] == 1
    found = DiscoveredItem.objects.get()
    assert found.item == row and [d[2] for d in discovery.differences(found)] == ["Nieuw"]
    row.refresh_from_db()
    assert row.model == "Oud"  # nothing changes until it is accepted
    discovery.accept(found)
    row.refresh_from_db()
    assert (row.name, row.model, row.location) == ("Server", "Nieuw", "Kelder")


def test_ignored_stays_ignored_and_auto_accept_skips_the_wait(client, source):
    post_report(client, source.token, [{"key": "X", "name": "X"}])
    DiscoveredItem.objects.update(status=DiscoveredItem.Status.IGNORED)
    assert post_report(client, source.token, [{"key": "X", "name": "X"}]).json()["ignored"] == 1
    source.auto_accept = True
    source.save()
    assert post_report(client, source.token, [{"key": "Y", "name": "Y"}]).json()["accepted"] == 1
    assert ConfigurationItem.objects.filter(name="Y").exists()
    assert not ConfigurationItem.objects.filter(name="X").exists()


def test_a_report_does_not_touch_another_customer(client, source, hardware, on):
    other = Customer.objects.create(name="Andere BV", number="K200")
    CmdbCustomer.objects.create(customer=other, enabled=True)
    row = item(other, hardware, "Zelfde", serial_nr="S9")
    post_report(client, source.token, [{"key": "S9", "name": "Zelfde", "serial_nr": "S9", "model": "Gewijzigd"}])
    assert DiscoveredItem.objects.get().item is None
    row.refresh_from_db()
    assert row.model == ""


def test_admin_actions_on_discovered_items(client, source, beheerder):
    client.force_login(beheerder)
    post_report(client, source.token, [{"key": "A", "name": "A"}, {"key": "B", "name": "<script>B"}])
    a, b = DiscoveredItem.objects.get(key="A"), DiscoveredItem.objects.get(key="B")
    url = "/admin/cmdb/discovereditem/"
    assert "<script>B" not in client.get(url).content.decode()
    assert "<script>B" not in client.get(f"{url}{b.pk}/change/").content.decode()
    assert client.get(url + "add/").status_code == 403
    client.post(url, {"action": "accept_selected", "_selected_action": [a.pk]})
    client.post(url, {"action": "ignore_selected", "_selected_action": [b.pk]})
    a.refresh_from_db(), b.refresh_from_db()
    assert a.status == "accepted" and a.item is not None and b.status == "ignored"
    assert a.item.changes.first().user == beheerder


def test_a_source_shows_its_key_once_and_a_new_key_replaces_it(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    response = client.post("/admin/cmdb/discoverysource/add/", {
        "customer": customer.pk, "name": "Kantoor", "item_type": hardware.pk, "is_active": "on"})
    assert response.status_code == 200 and "packdesk-discovery.ps1" in response.content.decode()
    row = DiscoverySource.objects.get()
    token = response.context["token"]
    assert discovery.source_for(token) == row
    assert token not in client.get(f"/admin/cmdb/discoverysource/{row.pk}/change/").content.decode()
    new = client.post(f"/admin/cmdb/discoverysource/{row.pk}/action/new_key/")
    assert new.status_code == 200 and discovery.source_for(token) is None
    assert discovery.source_for(new.context["token"]) == row


def test_scripts_can_be_downloaded_and_know_the_address(client, on, beheerder):
    client.force_login(beheerder)
    for code in ("windows", "linux"):
        body = client.get(f"/admin/cmdb/discoverysource/script/{code}/").content.decode()
        assert "http://testserver/cmdb/discovery/report/" in body
    assert client.get("/admin/cmdb/discoverysource/script/other/").status_code == 403


# --- customer page ---------------------------------------------------------------------------------------------

def test_customer_page_shows_a_block_only_for_a_customer_with_the_cmdb(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    item(customer, hardware, "Verlopen item", warranty_until=days_from_now(-1))
    page = client.get(f"/admin/customers/customer/{customer.pk}/change/").content.decode()
    assert "Verlopen item" in page and "diagram/?customer=" in page
    other = Customer.objects.create(name="Andere BV", number="K200")
    page = client.get(f"/admin/customers/customer/{other.pk}/change/").content.decode()
    assert "diagram/?customer=" not in page
    CmdbSettings.objects.update(enabled=False)
    page = client.get(f"/admin/customers/customer/{customer.pk}/change/").content.decode()
    assert "Verlopen item" not in page


# --- demo customers --------------------------------------------------------------------------------------------

def test_demo_customers_cover_the_situations_and_are_made_once(site, settings, monkeypatch):
    monkeypatch.setattr("apps.invoices.services.store_pdf", lambda invoice: None)
    settings.DEBUG = False
    with pytest.raises(Exception):
        call_command("load_demo_customers")
    settings.DEBUG = True
    call_command("load_demo_customers")
    count = Customer.objects.count()
    call_command("load_demo_customers")
    assert Customer.objects.count() == count
    assert Customer.objects.get(name="Alleen Gegevens BV").contacts.count() == 0
    assert Customer.objects.get(name="CMDB Zonder Aankopen BV").orders.count() == 0
    assert Customer.objects.get(name="Servicepack Koper BV").licences.exists()
    assert Customer.objects.get(name="Hardware Koper BV").orders.filter(kind="hardware").exists()
    assert not ConfigurationItem.objects.filter(customer__name="Servicepack Koper BV").exists()
    everything = Customer.objects.get(name="Alles Tegelijk BV")
    assert everything.licences.exists() and everything.part_orders.exists() and everything.configuration_items.exists()


# --- adding own fields -----------------------------------------------------------------------------------------

FIELD_URL = "/admin/cmdb/itemfield/"


def own_field_data(hardware, **extra):
    return {"name_nl": "Rackpositie", "name_en": "Rack position", "name_de": "Rackposition", "key": "", "kind": "text",
            "choices": "", "item_types": [hardware.pk], "mode": "optional", "position": 50, **extra}


def test_a_field_can_be_added_and_then_works_everywhere(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    page = client.get(FIELD_URL).content.decode()
    assert FIELD_URL + "add/" in page
    assert client.post(FIELD_URL + "add/", own_field_data(hardware, in_list="on")).status_code == 302
    field = ItemField.objects.get(key="rackpositie")
    assert field.is_own and field.position == 50
    # on the form
    assert 'name="prop_rackpositie"' in client.get(LIST_URL + "add/").content.decode()
    assert client.post(LIST_URL + "add/", form_data(customer, hardware, prop_rackpositie="U12")).status_code == 302
    row = ConfigurationItem.objects.get()
    assert row.properties == {"rackpositie": "U12"}
    # in the list, the history, the export and the import
    assert "U12" in client.get(LIST_URL).content.decode()
    assert "rackpositie" in transfer.header(transfer.properties())
    rows = csv_rows(f"number;rackpositie\n{row.number};U13\n")
    transfer.run_import(rows)
    row.refresh_from_db()
    assert row.properties["rackpositie"] == "U13" and row.changes.first().field == "Rackpositie"


def test_a_field_needs_an_item_type_and_a_free_code(client, on, hardware, beheerder):
    client.force_login(beheerder)
    assert client.post(FIELD_URL + "add/", own_field_data(hardware, item_types=[])).status_code == 200
    assert not ItemField.objects.filter(key="rackpositie").exists()
    assert client.post(FIELD_URL + "add/", own_field_data(hardware, key="serial_nr")).status_code == 200
    assert client.post(FIELD_URL + "add/", own_field_data(hardware, key="relations")).status_code == 200
    assert client.post(FIELD_URL + "add/", own_field_data(hardware, key="Fout!")).status_code == 200
    # An empty code is made from the name and stays free.
    assert client.post(FIELD_URL + "add/", own_field_data(hardware)).status_code == 302
    assert client.post(FIELD_URL + "add/", own_field_data(hardware)).status_code == 302
    assert {"rackpositie", "rackpositie_2"} <= set(ItemField.objects.values_list("key", flat=True))
    assert client.post(FIELD_URL + "add/", own_field_data(hardware, name_nl="123 !")).status_code == 302
    assert ItemField.objects.filter(key="field_123").exists()


def test_only_own_fields_can_be_removed(client, on, hardware, beheerder):
    client.force_login(beheerder)
    standard = ItemField.objects.get(key="location")
    own = ItemField.objects.get(key="ip_address")
    assert client.get(f"{FIELD_URL}{standard.pk}/delete/").status_code == 403
    assert client.post(FIELD_URL, {"action": "delete_selected", "_selected_action": [standard.pk], "post": "yes"}).status_code == 200
    assert ItemField.objects.filter(pk=standard.pk).exists()
    assert client.post(f"{FIELD_URL}{own.pk}/delete/", {"post": "yes"}).status_code == 302
    assert not ItemField.objects.filter(pk=own.pk).exists()


def test_the_code_of_a_field_cannot_change_afterwards(client, on, hardware, beheerder):
    client.force_login(beheerder)
    own = ItemField.objects.get(key="ip_address")
    client.post(f"{FIELD_URL}{own.pk}/change/", own_field_data(hardware, key="iets_anders", mode="required"))
    own.refresh_from_db()
    assert own.key == "ip_address" and own.mode == "required"
    standard = ItemField.objects.get(key="location")
    page = client.get(f"{FIELD_URL}{standard.pk}/change/").content.decode()
    assert 'name="kind"' not in page and 'name="item_types"' not in page


def test_a_hidden_own_field_keeps_its_value(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    row = item(customer, hardware, properties={"ip_address": "192.0.2.1"})
    ItemField.objects.filter(key="ip_address").update(mode="hidden")
    assert 'name="prop_ip_address"' not in client.get(f"{LIST_URL}{row.pk}/change/").content.decode()
    assert client.post(f"{LIST_URL}{row.pk}/change/", form_data(customer, hardware, location="X")).status_code == 302
    row.refresh_from_db()
    assert row.properties == {"ip_address": "192.0.2.1"} and row.location == "X"


def test_a_required_own_field_is_required_for_its_type_only(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    ItemField.objects.filter(key="ip_address").update(mode="required")
    assert client.post(LIST_URL + "add/", form_data(customer, hardware)).status_code == 200
    software = ItemType.objects.get(name_en="Software")
    assert client.post(LIST_URL + "add/", form_data(customer, software)).status_code == 302


@pytest.mark.parametrize("language", ["name_nl", "name_en", "name_de"])
def test_a_name_in_one_language_is_enough(client, on, hardware, beheerder, language):
    client.force_login(beheerder)
    data = own_field_data(hardware, name_nl="", name_en="", name_de="")
    assert client.post(FIELD_URL + "add/", data).status_code == 200
    assert client.post(FIELD_URL + "add/", {**data, language: "Rackplek"}).status_code == 302
    field = ItemField.objects.get(key="rackplek")
    assert field.name_nl == "Rackplek"
    assert client.post("/admin/cmdb/itemstatus/add/", {language: "Uitgeleend", "key": "on_loan", "colour": "teal", "position": 9}).status_code == 302
    assert ItemStatus.objects.get(key="on_loan").name_nl == "Uitgeleend"


def test_status_colours_show_as_an_example_and_in_the_list(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    page = client.get("/admin/cmdb/itemstatus/add/").content.decode()
    for colour in ItemStatus.Colour.values:
        assert f"pd-colour-{colour}" in page and f'value="{colour}"' in page
    status = ItemStatus.objects.get(key="in_use")
    assert status.colour == "green"
    page = client.get(f"/admin/cmdb/itemstatus/{status.pk}/change/").content.decode()
    assert 'value="green" checked' in page
    item(customer, hardware)
    assert "pd-colour-green" in client.get(LIST_URL).content.decode()
    ItemStatus.objects.filter(pk=status.pk).update(name="<b>x</b>", name_nl="<b>x</b>", name_en="<b>x</b>")
    assert "<b>x</b>" not in client.get(LIST_URL).content.decode()


def test_everything_still_works_with_as_few_fields_as_possible(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    ItemField.objects.exclude(key__in=ItemField.FIXED).update(mode=FieldMode.HIDDEN)
    ItemField.objects.update(in_list=False)
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Kaal",
            "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0}
    assert client.post(LIST_URL + "add/", data).status_code == 302
    row = ConfigurationItem.objects.get()
    assert row.status.key == "in_use"
    for url in (LIST_URL, f"{LIST_URL}{row.pk}/change/", LIST_URL + f"diagram/?customer={customer.pk}", LIST_URL + "export/",
                LIST_URL + "example/", f"/admin/customers/customer/{customer.pk}/change/"):
        assert client.get(url).status_code == 200, url
    assert row.number in client.get(LIST_URL).content.decode()
    transfer.run_import(csv_rows("customer;type;name\nK100;Hardware;Via import\n"))
    assert ConfigurationItem.objects.filter(name="Via import").exists()


def test_a_line_that_skips_a_row_goes_around_the_box_there(customer, hardware):
    top, middle, bottom = (item(customer, hardware, n) for n in ("Boven", "Midden", "Onder"))
    Relation.objects.create(source=top, kind=kind("uses"), target=middle)
    Relation.objects.create(source=middle, kind=kind("uses"), target=bottom)
    Relation.objects.create(source=top, kind=kind("runs_on"), target=bottom)  # past Midden
    drawing = diagram.for_customer(customer)[0]
    box = next(n for n in drawing["nodes"] if n["full_name"] == "Midden")
    long_edge = next(e for e in drawing["edges"] if e["label"] == str(kind("runs_on")))
    passing = float(long_edge["path"].split(" L")[1].split()[0])
    assert passing < box["x"] or passing > box["x"] + box["width"]
    assert 0 <= passing <= drawing["width"]
    assert "L" not in next(e for e in drawing["edges"] if e["label"] != str(kind("runs_on")))["path"]
