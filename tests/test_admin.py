from apps.accounts.models import User

from .conftest import make_user


def test_tenant_admin_sees_only_own_users(client_a, tenant_a, tenant_b):
    admin_a = make_user(tenant_a, "beheer@a.test", staff=True, role="Beheerder")
    make_user(tenant_a, "klant@a.test")
    other = make_user(tenant_b, "klant@b.test")
    client_a.force_login(admin_a)

    page = client_a.get("/beheer/accounts/user/").content.decode()
    assert "klant@a.test" in page
    assert "klant@b.test" not in page
    assert client_a.get(f"/beheer/accounts/user/{other.pk}/change/").status_code == 302


def test_tenant_admin_creates_users_in_own_tenant(client_a, tenant_a, tenant_b):
    admin_a = make_user(tenant_a, "beheer@a.test", staff=True, role="Beheerder")
    client_a.force_login(admin_a)
    client_a.post(
        "/beheer/accounts/user/add/",
        {"email": "nieuw@a.test", "password1": "Een-lang-wachtwoord-42", "password2": "Een-lang-wachtwoord-42"},
    )
    assert User.objects.get(email="nieuw@a.test").tenant == tenant_a


def test_tenant_admin_sees_only_own_settings(client_a, tenant_a, tenant_b):
    admin_a = make_user(tenant_a, "beheer@a.test", staff=True, role="Beheerder")
    client_a.force_login(admin_a)
    page = client_a.get("/beheer/tenants/tenant/").content.decode()
    assert "Tenant A" in page and "Tenant B" not in page
    assert client_a.get(f"/beheer/tenants/tenant/{tenant_b.pk}/change/").status_code == 302
    assert client_a.get("/beheer/tenants/tenant/add/").status_code == 403
    assert client_a.get("/beheer/tenants/domain/").status_code == 403


def test_tenant_admin_can_change_branding(client_a, tenant_a):
    admin_a = make_user(tenant_a, "beheer@a.test", staff=True, role="Beheerder")
    client_a.force_login(admin_a)
    response = client_a.post(
        f"/beheer/tenants/tenant/{tenant_a.pk}/change/",
        {"name": "Nieuwe naam", "primary_color": "#000000", "accent_color": "#ffffff", "country": "NL", "language": "nl"},
    )
    assert response.status_code == 302, response.content.decode()[:2000]
    tenant_a.refresh_from_db()
    assert tenant_a.name == "Nieuwe naam" and tenant_a.primary_color == "#000000"
    assert tenant_a.slug == "a"


def test_invalid_colour_is_rejected(client_a, tenant_a):
    admin_a = make_user(tenant_a, "beheer@a.test", staff=True, role="Beheerder")
    client_a.force_login(admin_a)
    client_a.post(
        f"/beheer/tenants/tenant/{tenant_a.pk}/change/",
        {"name": "X", "primary_color": "red;}</style>", "accent_color": "#ffffff", "country": "NL", "language": "nl"},
    )
    tenant_a.refresh_from_db()
    assert tenant_a.primary_color == "#112233"


def test_platform_admin_sees_all_tenants(client, tenant_a, tenant_b, platform_admin):
    client.force_login(platform_admin)
    page = client.get("/beheer/tenants/tenant/", HTTP_HOST="localhost").content.decode()
    assert "Tenant A" in page and "Tenant B" in page
