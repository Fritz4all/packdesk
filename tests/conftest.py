import pytest
from django.contrib.auth.models import Group

from apps.accounts.models import User
from apps.tenants.models import Domain, Tenant

PASSWORD = "correct-horse-battery"


def make_tenant(slug, domain, color):
    tenant = Tenant.objects.create(name=f"Tenant {slug.upper()}", slug=slug, primary_color=color)
    Domain.objects.create(tenant=tenant, domain=domain, is_primary=True)
    return tenant


def make_user(tenant, email, staff=False, role=None):
    user = User(email=email, tenant=tenant, kind=User.Kind.STAFF if staff else User.Kind.CUSTOMER, is_staff=staff)
    user.set_password(PASSWORD)
    user.save()
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


@pytest.fixture
def tenant_a(db):
    return make_tenant("a", "shop-a.test", "#112233")


@pytest.fixture
def tenant_b(db):
    return make_tenant("b", "shop-b.test", "#445566")


@pytest.fixture
def client_a(client):
    client.defaults["HTTP_HOST"] = "shop-a.test"
    return client


@pytest.fixture
def platform_admin(db):
    user = User(email="root@platform.test", is_staff=True, is_superuser=True, kind=User.Kind.STAFF)
    user.set_password(PASSWORD)
    user.save()
    return user
