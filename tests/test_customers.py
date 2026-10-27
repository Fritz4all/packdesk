import time

import pytest
from django.core import mail, signing

from apps.accounts.models import User
from apps.customers.models import Contact, Country, Customer, CustomerAddress, SignupSettings
from apps.numbering.checks import check
from apps.numbering.models import NumberSequence

from .conftest import make_user

CUSTOMERS = "/admin/customers/customer/"


@pytest.fixture
def signup_settings(site):
    s = SignupSettings.load()
    s.notify_email = "sales@example.test"
    s.save()
    site.email = "info@example.test"
    site.save()
    return s


def signup_data(**extra):
    data = {
        "company": "Nieuwe Reseller BV", "phone": "0201234567", "vat_number": "", "coc_number": "",
        "line1": "Hoofdstraat 1", "postal_code": "1000 AA", "city": "Amsterdam",
        "country": Country.objects.get(code="NL").pk, "salutation": "mr", "initials": "J.", "first_name": "Jan",
        "last_name": "Jansen", "function": "Inkoper", "email": "jan@reseller.test",
        "password1": "Een-lang-wachtwoord-42", "password2": "Een-lang-wachtwoord-42", "message": "Graag!",
        "homepage": "", "started": signing.dumps(time.time() - 60),
    }
    data.update(extra)
    return data


# --- defaults -------------------------------------------------------------------

def test_default_types_and_countries(db):
    assert Country.objects.get(code="NL").vat_number_required is False
    assert Country.objects.get(code="DE").vat_number_required is True
    assert Country.objects.get(code="DE").name_de == "Deutschland"
    assert SignupSettings.load().customer_type.is_reseller


# --- sign-up form ------------------------------------------------------------------

def test_signup_creates_pending_customer(client, signup_settings):
    response = client.post("/aanmelden/", signup_data())
    assert response.status_code == 302 and response["Location"] == "/aanmelden/verzonden/"
    customer = Customer.objects.get(name="Nieuwe Reseller BV")
    assert customer.status == Customer.Status.PENDING and customer.number is None
    assert customer.signup_message == "Graag!"
    assert customer.address(CustomerAddress.Kind.MAIN).city == "Amsterdam"
    contact = customer.contacts.get()
    assert contact.is_primary and contact.user.email == "jan@reseller.test"
    assert not contact.user.is_active
    assert mail.outbox[0].to == ["sales@example.test"] and "Nieuwe Reseller BV" in mail.outbox[0].subject


def test_pending_customer_cannot_log_in(client, signup_settings):
    client.post("/aanmelden/", signup_data())
    client.post("/inloggen/", {"username": "jan@reseller.test", "password": "Een-lang-wachtwoord-42"})
    assert "_auth_user_id" not in client.session


def test_signup_without_approval_is_active_at_once(client, signup_settings):
    signup_settings.require_approval = False
    signup_settings.save()
    client.post("/aanmelden/", signup_data())
    customer = Customer.objects.get(name="Nieuwe Reseller BV")
    assert customer.status == Customer.Status.ACTIVE and customer.number == "1"
    assert customer.contacts.get().user.is_active


def test_vat_number_required_for_foreign_country(client, signup_settings):
    response = client.post("/aanmelden/", signup_data(country=Country.objects.get(code="BE").pk))
    assert response.status_code == 200 and "een btw-nummer verplicht" in response.content.decode()


def test_duplicate_email_rejected(client, signup_settings):
    make_user("jan@reseller.test")
    response = client.post("/aanmelden/", signup_data())
    assert response.status_code == 200 and not Customer.objects.exists()


def test_bots_are_rejected(client, signup_settings):
    client.post("/aanmelden/", signup_data(homepage="http://spam.test"))
    client.post("/aanmelden/", signup_data(started=signing.dumps(time.time())))
    client.post("/aanmelden/", signup_data(started="forged"))
    assert not Customer.objects.exists()


def test_field_modes_are_applied(client, signup_settings):
    signup_settings.field_phone = "hidden"
    signup_settings.field_coc_number = "required"
    signup_settings.save()
    page = client.get("/aanmelden/").content.decode()
    assert 'name="phone"' not in page and 'name="coc_number"' in page
    response = client.post("/aanmelden/", signup_data())
    assert response.status_code == 200  # KvK now required
    assert client.post("/aanmelden/", signup_data(coc_number="12345678")).status_code == 302


def test_signup_disabled(client, signup_settings):
    signup_settings.enabled = False
    signup_settings.save()
    assert client.get("/aanmelden/").status_code == 404
    assert 'href="/aanmelden/"' not in client.get("/inloggen/").content.decode()


def test_signup_texts_per_language(client, signup_settings):
    client.post("/taal/", {"language": "de", "next": "/"})
    assert "Reseller werden" in client.get("/aanmelden/").content.decode()


# --- approval in the admin ------------------------------------------------------

def test_approve_gives_number_activates_and_mails(client, signup_settings, beheerder):
    client.post("/aanmelden/", signup_data())
    customer = Customer.objects.get()
    NumberSequence.objects.filter(key="customer").update(pattern="D{nr:5}", next_number=900)
    mail.outbox.clear()
    client.force_login(beheerder)
    client.post(f"{CUSTOMERS}{customer.pk}/action/approve/")
    customer.refresh_from_db()
    assert customer.status == Customer.Status.ACTIVE and customer.number == "D00900"
    assert customer.approved_by == beheerder
    assert customer.contacts.get().user.is_active
    assert mail.outbox[0].to == ["jan@reseller.test"] and "D00900" in mail.outbox[0].body
    # The customer number sequence now sees this number as issued.
    assert check(NumberSequence.objects.get(key="customer")).highest == 900


def test_block_stops_login(client, site, beheerder):
    customer = Customer.objects.create(name="Klant", status=Customer.Status.ACTIVE, number="5")
    user = make_user("k@klant.test")
    Contact.objects.create(customer=customer, user=user, last_name="K", email=user.email)
    client.force_login(beheerder)
    client.post(f"{CUSTOMERS}{customer.pk}/action/block/")
    user.refresh_from_db()
    assert not user.is_active


def test_invite_creates_login_and_sends_link(client, site, beheerder):
    customer = Customer.objects.create(name="Klant", status=Customer.Status.ACTIVE, number="5")
    Contact.objects.create(customer=customer, last_name="Pietersen", first_name="Piet", email="piet@klant.test")
    client.force_login(beheerder)
    client.post(f"{CUSTOMERS}{customer.pk}/action/invite/")
    user = User.objects.get(email="piet@klant.test")
    assert user.kind == "customer" and not user.has_usable_password()
    assert "/wachtwoord-instellen/" in mail.outbox[0].body
    # The link lets the customer choose a password.
    link = mail.outbox[0].body.split("http://testserver")[1].split()[0]
    response = client.get(link, follow=True)
    form_url = response.redirect_chain[-1][0]
    client.post(form_url, {"new_password1": "Mijn-nieuwe-wachtwoord-9", "new_password2": "Mijn-nieuwe-wachtwoord-9"})
    user.refresh_from_db()
    assert user.check_password("Mijn-nieuwe-wachtwoord-9")


def test_saving_active_customer_assigns_number(client, site, beheerder):
    client.force_login(beheerder)
    data = {"name": "Handmatig BV", "status": "active", "margin_packs": "0", "margin_parts": "15"}
    for prefix in ("addresses", "contacts"):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0",
                     f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000"})
    response = client.post(f"{CUSTOMERS}add/", data)
    assert response.status_code == 302, response.content.decode()[:2000]
    assert Customer.objects.get(name="Handmatig BV").number == "1"


def test_pending_badge(rf, site, beheerder):
    from apps.customers.admin_badge import pending

    Customer.objects.create(name="Wacht", status=Customer.Status.PENDING)
    request = rf.get("/")
    request.user = beheerder
    assert pending(request) == "1"


def test_employee_role_can_view_but_not_change(client, site):
    customer = Customer.objects.create(name="Klant")
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    assert client.get(f"{CUSTOMERS}{customer.pk}/change/").status_code == 200
    assert client.post(f"{CUSTOMERS}{customer.pk}/action/approve/").status_code == 403


# --- customer portal -----------------------------------------------------------

def test_customer_sees_and_edits_own_details(client, site):
    customer = Customer.objects.create(name="Mijn Bedrijf", number="77", status=Customer.Status.ACTIVE)
    user = make_user("ik@bedrijf.test")
    Contact.objects.create(customer=customer, user=user, last_name="Oud", email=user.email)
    client.force_login(user)
    assert "Mijn Bedrijf" in client.get("/mijn/").content.decode()
    page = client.get("/mijn/gegevens/").content.decode()
    assert "Mijn Bedrijf" in page and "77" in page
    client.post("/mijn/gegevens/", {"last_name": "Nieuw", "first_name": "Ik"})
    user.refresh_from_db()
    assert user.last_name == "Nieuw" and Contact.objects.get(user=user).last_name == "Nieuw"


def test_password_reset_email(client, site):
    make_user("vergeten@example.test")
    client.post("/wachtwoord-vergeten/", {"email": "vergeten@example.test"})
    assert len(mail.outbox) == 1 and "/wachtwoord-instellen/" in mail.outbox[0].body
    assert site.name in mail.outbox[0].subject


def test_password_change(client, site):
    user = make_user("wijzig@example.test")
    client.force_login(user)
    client.post("/mijn/wachtwoord/", {"old_password": "correct-horse-battery", "new_password1": "Heel-nieuw-wachtwoord-1",
                                     "new_password2": "Heel-nieuw-wachtwoord-1"})
    user.refresh_from_db()
    assert user.check_password("Heel-nieuw-wachtwoord-1")


def test_signup_texts_in_default_language(client, signup_settings):
    """Regression: a translated text equal to the field default fell back to English."""
    page = client.get("/aanmelden/").content.decode()
    assert "<h1>Reseller worden</h1>" in page and "Become a reseller" not in page


# --- customer page: overview first, edit on request ---------------------------------------------


def test_customer_opens_as_overview_with_edit_button(client, site, beheerder):
    from apps.customers.models import CustomerType

    customer = Customer.objects.create(name="Overzicht BV", number="77", status=Customer.Status.ACTIVE)
    client.force_login(beheerder)
    url = f"/admin/customers/customer/{customer.pk}/change/"
    page = client.get(url)
    assert [t.name for t in page.templates][0] == "admin/customers/customer/overview.html"
    assert "?edit=1" in page.content.decode() and 'name="_save"' not in page.content.decode()
    assert 'name="_save"' in client.get(f"{url}?edit=1").content.decode()

    data = {"number": "77", "status": "active", "name": "Overzicht BV", "margin_packs": "0", "margin_parts": "0",
            "_continue": "1"}
    for prefix in ("addresses", "contacts"):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0", f"{prefix}-MIN_NUM_FORMS": "0",
                     f"{prefix}-MAX_NUM_FORMS": "1000"})
    response = client.post(f"{url}?edit=1", data)
    assert response.status_code == 302 and response["Location"].endswith("?edit=1")

    reseller = CustomerType.objects.create(name="Reseller")
    other = Customer.objects.create(name="Tweede", number="78")
    form = client.post("/admin/customers/customer/", {"action": "change_type_selected",
                                                       "_selected_action": [customer.pk, other.pk]})
    assert form.status_code == 200 and b"Tweede" in form.content
    client.post("/admin/customers/customer/", {"action": "change_type_selected", "apply": "1",
                                                "_selected_action": [customer.pk, other.pk],
                                                "customer_type": reseller.pk})
    assert Customer.objects.filter(customer_type=reseller).count() == 2


def test_customer_with_history_is_not_deleted_but_explained(client, site, beheerder):
    from apps.invoices.models import Invoice
    from apps.trash.models import TrashEntry

    kept = Customer.objects.create(name="Met factuur", number="80")
    Invoice.objects.create(number="F1", customer=kept)
    loose = Customer.objects.create(name="Zonder iets", number="81")
    client.force_login(make_user("root@example.test", superuser=True))
    response = client.post("/admin/customers/customer/", {"action": "delete_selected",
                                                           "_selected_action": [kept.pk, loose.pk]}, follow=True)
    page = response.content.decode()
    assert "Met factuur" in page and "Block the customer instead" in page or "Blokkeer" in page
    assert Customer.objects.count() == 2 and not TrashEntry.objects.exists()
    response = client.get(f"/admin/customers/customer/{kept.pk}/delete/")
    assert response.status_code == 302 and response["Location"].endswith("?edit=1")
    client.post("/admin/customers/customer/", {"action": "delete_selected", "_selected_action": [loose.pk], "post": "yes"})
    assert not Customer.objects.filter(pk=loose.pk).exists()
