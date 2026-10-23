import pytest
from django.contrib.auth.models import Group

from apps.accounts.models import User
from apps.siteconfig.models import SiteSettings

PASSWORD = "correct-horse-battery"


def make_user(email, staff=False, role=None, superuser=False):
    user = User(
        email=email,
        kind=User.Kind.STAFF if staff or superuser else User.Kind.CUSTOMER,
        is_staff=staff or superuser,
        is_superuser=superuser,
    )
    user.set_password(PASSWORD)
    user.save()
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


@pytest.fixture
def site(db):
    site = SiteSettings.load()
    site.name = "Testshop"
    site.primary_color = "#112233"
    site.save()
    return site


@pytest.fixture
def beheerder(db):
    return make_user("beheer@example.test", staff=True, role="Beheerder")


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    """Tests do not run collectstatic, so skip the hashed-manifest storage used in production."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
