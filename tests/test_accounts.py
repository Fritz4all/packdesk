from django.contrib.auth.models import Group

from apps.accounts.models import User

from .conftest import PASSWORD, make_user


def login(client, host, email):
    return client.post("/inloggen/", {"username": email, "password": PASSWORD}, HTTP_HOST=host)


def test_same_email_in_two_tenants_logs_into_the_right_one(client, tenant_a, tenant_b):
    user_a = make_user(tenant_a, "jan@example.test")
    user_b = make_user(tenant_b, "jan@example.test")

    assert login(client, "shop-a.test", "jan@example.test").status_code == 302
    assert client.session["_auth_user_id"] == str(user_a.pk)

    client.logout()
    assert login(client, "shop-b.test", "JAN@example.test").status_code == 302
    assert client.session["_auth_user_id"] == str(user_b.pk)


def test_user_cannot_log_in_on_other_tenant(client, tenant_a, tenant_b):
    make_user(tenant_a, "piet@example.test")
    response = login(client, "shop-b.test", "piet@example.test")
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_platform_admin_cannot_log_in_on_tenant_site(client, tenant_a, platform_admin):
    login(client, "shop-a.test", platform_admin.email)
    assert "_auth_user_id" not in client.session


def test_session_of_other_tenant_is_dropped(client, tenant_a, tenant_b):
    user_a = make_user(tenant_a, "kees@example.test")
    client.force_login(user_a)
    assert client.get("/mijn/", HTTP_HOST="shop-a.test").status_code == 200
    response = client.get("/mijn/", HTTP_HOST="shop-b.test")
    assert response.status_code == 302 and "/inloggen/" in response["Location"]


def test_dashboard_requires_login(client_a, tenant_a):
    response = client_a.get("/mijn/")
    assert response.status_code == 302


def test_logout(client_a, tenant_a):
    client_a.force_login(make_user(tenant_a, "uit@example.test"))
    client_a.post("/uitloggen/")
    assert "_auth_user_id" not in client_a.session


def test_roles_are_created(db):
    beheerder = Group.objects.get(name="Beheerder")
    codes = set(beheerder.permissions.values_list("codename", flat=True))
    assert {"change_tenant", "add_user", "change_user"} <= codes
    assert set(Group.objects.values_list("name", flat=True)) >= {"Beheerder", "Financieel", "Service", "Medewerker"}


def test_username_is_generated(tenant_a):
    user = make_user(tenant_a, "auto@example.test")
    assert len(user.username) == 32
    assert User.objects.get(pk=user.pk).email == "auto@example.test"
