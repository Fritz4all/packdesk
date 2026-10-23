import pytest
from django.core.management import call_command

from apps.tenants.models import Domain, Tenant


def test_unknown_host_is_404(client, db):
    assert client.get("/", HTTP_HOST="unknown.test").status_code == 404


def test_tenant_home_shows_its_own_branding(client, tenant_a, tenant_b):
    page_a = client.get("/", HTTP_HOST="shop-a.test").content.decode()
    page_b = client.get("/", HTTP_HOST="shop-b.test").content.decode()
    assert "Tenant A" in page_a and "#112233" in page_a
    assert "Tenant B" in page_b and "#445566" in page_b
    assert "Tenant B" not in page_a


def test_host_with_port_and_uppercase_matches(client, tenant_a):
    assert client.get("/", HTTP_HOST="SHOP-A.test:8000").status_code == 200


def test_inactive_tenant_is_404(client, tenant_a):
    Tenant.objects.filter(pk=tenant_a.pk).update(is_active=False)
    assert client.get("/", HTTP_HOST="shop-a.test").status_code == 404


def test_platform_host_only_serves_admin(client, db):
    assert client.get("/", HTTP_HOST="localhost").status_code == 404
    assert client.get("/beheer/login/", HTTP_HOST="localhost").status_code == 200


def test_domain_is_stored_lowercase(tenant_a):
    d = Domain.objects.create(tenant=tenant_a, domain="  WWW.Shop-A.Test ")
    assert d.domain == "www.shop-a.test"


def test_create_tenant_command(db):
    call_command("create_tenant", name="Demo", slug="demo", domain="demo.test")
    assert Domain.objects.get(domain="demo.test").tenant.slug == "demo"


def test_page_language_follows_tenant_setting(client, tenant_a):
    assert "Inloggen" in client.get("/", HTTP_HOST="shop-a.test", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    Tenant.objects.filter(pk=tenant_a.pk).update(language="en")
    assert "Log in" in client.get("/", HTTP_HOST="shop-a.test").content.decode()
