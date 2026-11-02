import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.cmdb import transfer
from apps.cmdb.models import CmdbCustomer, CmdbSettings, ConfigurationItem, ItemChange, ItemProperty, ItemType, Relation
from apps.customers.models import Contact, Customer

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
    response = client.post(LIST_URL + "add/", {"customer": other.pk, "item_type": hardware.pk, "name": "X", "status": "in_use",
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
    Relation.objects.create(source=server, kind="runs_on", target=power)
    Relation.objects.create(source=app, kind="runs_on", target=server)
    Relation.objects.create(source=power, kind="depends_on", target=app)  # a circle
    assert {i.name for i in power.affected_items()} == {"Server", "App"}
    assert unrelated.affected_items() == []


def test_admin_keeps_history_with_who_and_what(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": "in_use",
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
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": "in_use",
            "relations_out-TOTAL_FORMS": 0, "relations_out-INITIAL_FORMS": 0}
    assert client.post(f"{LIST_URL}{row.pk}/change/", data).status_code == 302
    assert row.changes.count() == 0


def test_properties_on_the_form_follow_the_type(client, customer, hardware, beheerder):
    client.force_login(beheerder)
    data = {"customer": customer.pk, "item_type": hardware.pk, "name": "Server", "status": "in_use",
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
    Relation.objects.create(source=a, kind="runs_on", target=b)
    rows = csv_rows("number;relations\n" + f"{a.number};uses:{c.number}\n")
    assert transfer.analyse(rows)[0]["action"] == transfer.UPDATE
    transfer.run_import(rows)
    assert list(a.relations_out.values_list("kind", "target__name")) == [("uses", "C")]
    assert "C" in a.changes.first().new_value


def test_renamed_item_keeps_a_relation_pointing_at_its_old_name(customer, hardware):
    a, b = item(customer, hardware, "A"), item(customer, hardware, "B")
    rows = csv_rows("number;name;relations\n" + f"{b.number};Nieuw;\n{a.number};A;runs_on:B\n")
    transfer.run_import(rows)
    assert a.relations_out.get().target == b


def test_properties_in_a_file_are_checked(customer, hardware):
    software = ItemType.objects.get(name_en="Software")
    ItemProperty.objects.create(key="rack_units", name="Rack", kind="number").item_types.add(hardware)
    head = "customer;type;name;rack_units;version\n"
    outcome = transfer.analyse(csv_rows(head + "K100;Hardware;A;2;\nK100;Hardware;B;twee;\nK100;Hardware;C;;9\n"
                                               f"K100;{software};D;;9\n"))
    assert [r["action"] for r in outcome] == [transfer.NEW, transfer.ERROR, transfer.ERROR, transfer.NEW]


def test_required_property_for_a_new_item(customer, hardware):
    ItemProperty.objects.create(key="rack_units", name="Rack", required=True).item_types.add(hardware)
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
    Relation.objects.create(source=app, kind="runs_on", target=server)
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
