from django.core import mail

from apps.customers.models import Contact, Customer
from apps.siteconfig.models import HomeBlock, SiteSettings

from .conftest import make_user


def test_admin_uses_site_admin_language(client, site):
    SiteSettings.objects.filter(pk=1).update(admin_language="en", language="nl", languages="nl")
    client.force_login(make_user("root@example.test", superuser=True))
    assert client.get("/beheer/").headers["Content-Language"] == "en"
    assert client.get("/").headers["Content-Language"] == "nl"  # the website keeps its own language


def test_staff_user_chooses_own_admin_language(client, site):
    user = make_user("root@example.test", superuser=True)
    client.force_login(user)
    response = client.post("/beheer/taal/", {"language": "de", "next": "/beheer/customers/customer/"})
    assert response.status_code == 302 and response.url == "/beheer/customers/customer/"
    user.refresh_from_db()
    assert user.admin_language == "de"
    page = client.get("/beheer/customers/customer/")
    assert page.headers["Content-Language"] == "de" and "Kunden" in page.content.decode()


def test_language_switch_ignores_unknown_language_and_foreign_redirect(client, site):
    user = make_user("root@example.test", superuser=True)
    client.force_login(user)
    response = client.post("/beheer/taal/", {"language": "xx", "next": "https://evil.example/"})
    user.refresh_from_db()
    assert user.admin_language == "" and response.url == "/beheer/"


def test_customer_mail_from_admin_stays_in_site_language(client, site):
    SiteSettings.objects.filter(pk=1).update(language="nl")
    admin_user = make_user("root@example.test", superuser=True)
    admin_user.admin_language = "en"
    admin_user.save()
    customer = Customer.objects.create(name="Klant", status=Customer.Status.ACTIVE, number="1")
    Contact.objects.create(customer=customer, last_name="X", email="x@klant.test")
    client.force_login(admin_user)
    url = f"/beheer/customers/customer/{customer.pk}/action/invite/"
    client.post(url)
    assert mail.outbox[0].subject == "Uw account bij Testshop"


def test_account_menu_opens_site_in_new_tab_and_offers_languages(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    html = client.get("/beheer/").content.decode()
    assert 'target="_blank"' in html and 'name="language" value="de"' in html


def test_home_blocks_and_menu_items_are_collapsed_with_edit_button(client, site):
    HomeBlock.objects.create(settings=site, title="Blok", visibility="all")
    client.force_login(make_user("root@example.test", superuser=True))
    html = client.get(f"/beheer/siteconfig/sitesettings/{site.pk}/change/").content.decode()
    assert "pd-row-edit" in html and "x-show=\"openRow\"" in html
