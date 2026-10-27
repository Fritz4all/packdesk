import pytest
from django.contrib.auth.models import Group

from apps.accounts.models import User

from .conftest import PASSWORD, make_user


def login(client, email, password=PASSWORD):
    return client.post("/inloggen/", {"username": email, "password": password})


def test_login_with_email_is_case_insensitive(client, site):
    user = make_user("jan@example.test")
    assert login(client, "JAN@Example.test").status_code == 302
    assert client.session["_auth_user_id"] == str(user.pk)


def test_wrong_password_is_rejected(client, site):
    make_user("piet@example.test")
    response = login(client, "piet@example.test", "verkeerd")
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_inactive_user_cannot_log_in(client, site):
    user = make_user("weg@example.test")
    user.is_active = False
    user.save()
    login(client, "weg@example.test")
    assert "_auth_user_id" not in client.session


def test_email_is_unique_regardless_of_case(db):
    make_user("dubbel@example.test")
    try:
        make_user("DUBBEL@example.test")
    except Exception:
        return
    raise AssertionError("duplicate email was accepted")


def test_dashboard_requires_login(client, site):
    assert client.get("/mijn/").status_code == 302


def test_logout(client, site):
    client.force_login(make_user("uit@example.test"))
    client.post("/uitloggen/")
    assert "_auth_user_id" not in client.session


def test_roles_are_created(db):
    codes = set(Group.objects.get(name="Beheerder").permissions.values_list("codename", flat=True))
    assert {"change_sitesettings", "add_user", "change_user"} <= codes
    assert set(Group.objects.values_list("name", flat=True)) >= {"Beheerder", "Financieel", "Service", "Medewerker"}


def test_username_is_generated(db):
    user = make_user("auto@example.test")
    assert len(user.username) == 32
    assert User.objects.get(pk=user.pk).email == "auto@example.test"


def test_user_page_shows_password_status_not_the_hash(client, site):
    from django.core import mail

    admin_user = make_user("root@example.test", superuser=True)
    user = make_user("medewerker@example.test", staff=True, role="Service")
    client.force_login(admin_user)
    page = client.get(f"/admin/accounts/user/{user.pk}/change/").content.decode()
    assert "Password set" in page or "Wachtwoord ingesteld" in page
    assert "pbkdf2" not in page and f"/admin/accounts/user/{user.pk}/password/" in page
    assert client.get(f"/admin/accounts/user/{user.pk}/send-reset/").status_code == 405
    client.post(f"/admin/accounts/user/{user.pk}/send-reset/")
    user.refresh_from_db()
    assert not user.has_usable_password() and mail.outbox[-1].to == ["medewerker@example.test"]
    page = client.get(f"/admin/accounts/user/{user.pk}/change/").content.decode()
    assert "Must choose a new password" in page or "Moet een nieuw wachtwoord kiezen" in page


def test_customer_user_never_becomes_superuser_or_gets_admin_fields(client, site):
    root = make_user("root@example.test", superuser=True)
    customer = make_user("klant@example.test")
    client.force_login(root)
    page = client.get(f"/admin/accounts/user/{customer.pk}/change/").content.decode()
    assert "admin/user-kind.js" in page  # hides admin language, role and superuser for customers
    data = {"email": customer.email, "kind": "customer", "is_active": "on", "is_superuser": "on",
            "admin_language": "en", "first_name": "", "last_name": "Klant"}
    response = client.post(f"/admin/accounts/user/{customer.pk}/change/", data)
    assert response.status_code == 302, response.content.decode()[:3000]
    customer.refresh_from_db()
    assert not customer.is_superuser and not customer.is_staff and customer.admin_language == ""


def test_staff_without_superuser_rights_never_sees_the_superuser_switch(client, site):
    beheer = make_user("beheer@example.test", staff=True, role="Beheerder")
    other = make_user("ander@example.test", staff=True, role="Service")
    client.force_login(beheer)
    assert 'name="is_superuser"' not in client.get(f"/admin/accounts/user/{other.pk}/change/").content.decode()


def test_disable_and_enable_users_in_bulk_but_not_yourself(client, site):
    root = make_user("root@example.test", superuser=True)
    a, b = make_user("a@example.test"), make_user("b@example.test")
    client.force_login(root)
    client.post("/admin/accounts/user/", {"action": "deactivate_selected", "_selected_action": [a.pk, b.pk, root.pk]})
    assert set(User.objects.filter(is_active=False).values_list("email", flat=True)) == {"a@example.test", "b@example.test"}
    client.post("/admin/accounts/user/", {"action": "activate_selected", "_selected_action": [a.pk]})
    a.refresh_from_db()
    assert a.is_active


def test_role_filter_has_superuser_for_superusers_only(client, site):
    from django.contrib.auth.models import Group

    root = make_user("root@example.test", superuser=True)
    make_user("service@example.test", staff=True, role="Service")
    client.force_login(root)
    assert list(client.get("/admin/accounts/user/?role=superuser").context["cl"].result_list) == [root]
    service = Group.objects.get(name="Service")
    assert client.get(f"/admin/accounts/user/?role={service.pk}").context["cl"].result_count == 1
    client.force_login(make_user("beheer@example.test", staff=True, role="Beheerder"))
    page = client.get("/admin/accounts/user/").content.decode()
    assert "?role=superuser" not in page
    assert "Superuser" not in client.get("/admin/accounts/role/").content.decode()  # not a role


def test_minimum_password_length_per_kind_of_user(site):
    from django.contrib.auth.password_validation import password_validators_help_texts, validate_password
    from django.core.exceptions import ValidationError

    site.password_min_length_staff, site.password_min_length_customers = 14, 8
    site.save()
    staff, customer = User(email="s@example.test", kind=User.Kind.STAFF, is_staff=True), User(email="k@example.test")
    validate_password("Paars-Konijn7", customer)  # 13 characters: enough for a customer
    with pytest.raises(ValidationError) as exc:
        validate_password("Paars-Konijn7", staff)
    assert "14" in str(exc.value)
    validate_password("Paars-Konijn-77", staff)
    assert any("14" in text and "8" in text for text in password_validators_help_texts())


def test_wizard_says_how_long_the_admin_password_must_be(site):
    from apps.core.setup_views import AdminForm

    site.password_min_length_staff = 12
    site.save()
    form = AdminForm({"email": "beheer@example.test", "password1": "Kort-1234", "password2": "Kort-1234"})
    assert "12" in str(form.fields["password1"].help_text)
    assert not form.is_valid() and "12" in str(form.errors["password1"])
