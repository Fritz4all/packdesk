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
