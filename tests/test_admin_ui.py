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


def test_every_admin_field_uses_the_admin_styling(rf, site):
    """Fields that use Django's plain widgets have no styling and are unreadable in dark mode."""
    from django.contrib import admin as django_admin
    from django.forms import widgets as plain

    request = rf.get("/beheer/")
    request.user = make_user("root@example.test", superuser=True)
    allowed_plain = (plain.HiddenInput, plain.MultipleHiddenInput)
    bad = []
    for model, model_admin in django_admin.site._registry.items():
        if not (model_admin.has_add_permission(request) or model_admin.has_change_permission(request)):
            continue  # read-only archive: nothing to fill in
        try:
            form = model_admin.get_form(request, None)()
        except Exception:  # some admins need an object; their extra fields are covered by other tests
            continue
        for name, field in form.fields.items():
            widget = getattr(field.widget, "widget", field.widget)  # related-field wrapper
            module = type(widget).__module__
            if getattr(widget, "input_type", "") == "color":
                continue  # colour picker
            if module.startswith("django.forms") and not isinstance(widget, allowed_plain):
                bad.append(f"{model._meta.label}.{name}: {type(widget).__name__}")
    assert not bad, bad


def test_column_headers_get_filters_and_they_work(client, site):
    import json
    import re

    root = make_user("root@example.test", superuser=True)
    waiting = make_user("nieuw@example.test")
    waiting.set_unusable_password()
    waiting.save()
    client.force_login(root)
    page = client.get("/beheer/accounts/user/").content.decode()
    data = json.loads(re.search(r'id="pd-column-filters" type="application/json">(.*?)</script>', page).group(1))
    assert {"kind", "is_active", "show_password"} <= set(data)
    assert len(data["show_password"]["choices"]) == 3  # all, set, must choose a new one
    url = data["show_password"]["choices"][2]["url"]
    result = client.get(f"/beheer/accounts/user/{url}").context["cl"].result_list
    assert list(result) == [waiting]


def test_every_list_still_opens(client, site):
    from django.contrib import admin as django_admin
    from django.urls import reverse

    client.force_login(make_user("root@example.test", superuser=True))
    for model in django_admin.site._registry:
        url = reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist")
        assert client.get(url, follow=True).status_code == 200, url


def test_section_page_follows_the_menu(client, site, beheerder):
    client.force_login(beheerder)
    page = client.get("/beheer/licences/").content.decode()
    assert "/beheer/licences/licence/" in page and "/beheer/licences/vendor/" in page
    assert "admin/packdesk/section_index.html" in [t.name for t in client.get("/beheer/licences/").templates]
