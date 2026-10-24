from apps.customers.models import Contact, Customer
from apps.siteconfig.models import Address

from .conftest import make_user


def test_header_path_shows_repeated_titles_once(client, site, beheerder):
    client.force_login(beheerder)
    page = client.get("/beheer/siteconfig/sitesettings/1/change/").content.decode()
    header = page.split("chevron_right")
    assert page.count(">\n            Instellingen\n") <= 1 or len(header) <= 3


def test_add_button_next_to_search(client, site, beheerder):
    client.force_login(beheerder)
    page = client.get("/beheer/customers/customer/").content.decode()
    assert "klant toevoegen" in page.lower()


def test_object_actions_are_buttons_in_form_and_post_only(client, site, beheerder):
    customer = Customer.objects.create(name="Wacht", status=Customer.Status.PENDING)
    client.force_login(beheerder)
    page = client.get(f"/beheer/customers/customer/{customer.pk}/change/").content.decode()
    assert f"/beheer/customers/customer/{customer.pk}/action/approve/" in page
    assert "/action/block/" in page
    assert client.get(f"/beheer/customers/customer/{customer.pk}/action/approve/").status_code == 405


def test_approve_button_hidden_for_active_customer(client, site, beheerder):
    customer = Customer.objects.create(name="Actief", status=Customer.Status.ACTIVE, number="3")
    client.force_login(beheerder)
    page = client.get(f"/beheer/customers/customer/{customer.pk}/change/").content.decode()
    assert "/action/approve/" not in page
    assert client.post(f"/beheer/customers/customer/{customer.pk}/action/approve/").status_code == 403


def test_inline_titles_summarise_rows(site):
    address = Address(settings=site, label="Bezoekadres", line1="Straat 1", postal_code="1000 AA", city="Almere",
                      on_website=True, on_invoices=True)
    assert address.get_inline_title() == (
        'Bezoekadres · Straat 1, 1000 AA Almere, Nederland <span class="pd-dim">— website, facturen</span>'
    )
    contact = Contact(customer=Customer(name="X"), first_name="Jan", last_name="Jansen", function="Inkoop",
                      email="jan@x.test", is_primary=True)
    assert contact.get_inline_title() == (
        'Jan Jansen <span class="pd-dim">— ★ hoofdcontactpersoon · Inkoop · jan@x.test</span>'
    )


def test_related_menu_has_short_labels_and_no_delete(client, site, beheerder):
    customer = Customer.objects.create(name="Klant")
    client.force_login(beheerder)
    page = client.get(f"/beheer/customers/customer/{customer.pk}/change/?edit=1").content.decode()
    assert 'title="klanttype toevoegen"' in page
    assert 'title="Geselecteerde klanttype' not in page and 'title="Nog een klanttype' not in page
    assert 'id="delete_id_customer_type"' not in page
