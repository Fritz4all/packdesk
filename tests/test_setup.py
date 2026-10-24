from io import StringIO

import pytest
from django.core import mail
from django.core.management import call_command

from apps.accounts.models import User
from apps.core import database_state, setup_code
from apps.numbering.models import NumberSequence
from apps.siteconfig.models import SiteSettings

from .conftest import make_user


@pytest.fixture
def new_install(db, settings):
    settings.SETUP_WIZARD = True
    SiteSettings.objects.update_or_create(pk=1, defaults={"setup_completed": False})
    return settings


# --- installation code ---------------------------------------------------------------------------


def test_code_from_env_or_random_file(settings):
    settings.SETUP_CODE = "geheim-123"
    assert setup_code.check("GEHEIM123") and not setup_code.check("fout")
    settings.SETUP_CODE = ""
    code = setup_code.get_code()
    assert code == setup_code.get_code() and setup_code.check(code.lower().replace("-", " "))
    setup_code.forget()
    assert setup_code.get_code() != code  # a new code after use
    assert not setup_code.check("")


def test_startup_command_shows_code_only_while_needed(new_install):
    out = StringIO()
    call_command("setup_database", stdout=out)
    assert "Installation code: " + setup_code.get_code() in out.getvalue()
    SiteSettings.objects.filter(pk=1).update(setup_completed=True)
    out = StringIO()
    call_command("setup_database", stdout=out)
    assert out.getvalue() == ""


def test_database_is_not_empty_and_up_to_date(db):
    assert not database_state.is_empty() and database_state.pending() == []


# --- first-run wizard ----------------------------------------------------------------------------


def test_every_page_leads_to_the_wizard_until_finished(client, new_install):
    assert client.get("/").url == "/installatie/"
    assert client.get("/beheer/").url == "/installatie/"
    assert client.get("/installatie/").url == "/installatie/code/"


def test_wizard_from_code_to_finished(client, new_install):
    assert client.post("/installatie/code/", {"code": "verkeerd"}).status_code == 200
    assert client.get("/installatie/admin/").url == "/installatie/code/"  # not without the code

    client.post("/installatie/code/", {"code": setup_code.get_code()})
    response = client.post("/installatie/admin/", {
        "email": "Baas@Bedrijf.test", "first_name": "Bea", "last_name": "Baas",
        "password1": "lang-genoeg-wachtwoord", "password2": "lang-genoeg-wachtwoord",
    })
    assert response.url == "/installatie/basics/"
    admin = User.objects.get(email="baas@bedrijf.test")
    assert admin.is_superuser and admin.is_staff and admin.kind == User.Kind.STAFF

    response = client.post("/installatie/basics/", {
        "name": "Bedrijf BV", "language": "nl", "languages": ["nl", "en"], "admin_language": "en",
        "email": "info@bedrijf.test", "test_mail": "on",
    })
    assert response.url == "/installatie/numbering/"
    site = SiteSettings.load()
    assert site.name == "Bedrijf BV" and site.language_codes == ["nl", "en"] and site.admin_language == "en"
    assert mail.outbox[-1].to == ["baas@bedrijf.test"]

    sequences = list(NumberSequence.objects.all())
    data = {f"next_{s.pk}": 5000 for s in sequences}
    assert client.post("/installatie/numbering/", data).url == "/installatie/demo/"
    assert all(s.next_number == 5000 for s in NumberSequence.objects.all())

    assert client.post("/installatie/demo/", {}).url == "/beheer/"
    assert SiteSettings.load().setup_completed
    assert client.get("/installatie/").url == "/beheer/"  # closed for good
    assert client.get("/").status_code == 200


def test_wizard_refuses_weak_or_different_passwords(client, new_install):
    client.post("/installatie/code/", {"code": setup_code.get_code()})
    page = client.post("/installatie/admin/", {"email": "a@b.test", "password1": "kort", "password2": "anders"})
    assert page.status_code == 200 and not User.objects.exists()


def test_after_the_administrator_only_that_administrator_continues(client, new_install):
    make_user("baas@bedrijf.test", superuser=True)
    response = client.get("/installatie/basics/")
    assert response.url.startswith("/beheer/login/")
    assert client.get("/installatie/code/").url.startswith("/beheer/login/")  # no second administrator
    client.force_login(User.objects.get(email="baas@bedrijf.test"))
    assert client.get("/installatie/code/").url == "/installatie/basics/"


# --- database update page ------------------------------------------------------------------------


@pytest.fixture
def waiting_changes(monkeypatch):
    applied = []
    monkeypatch.setattr(database_state, "has_pending", lambda: not applied)
    monkeypatch.setattr(database_state, "pending", lambda: ["shop.0099_new_field"])
    monkeypatch.setattr(database_state, "apply_changes", lambda: applied.append(True))
    return applied


def test_update_page_instead_of_the_site(client, db, waiting_changes):
    page = client.get("/")
    assert page.status_code == 503 and "shop.0099_new_field" in page.content.decode()
    assert client.get("/static/css/packdesk.css").status_code == 200


def test_update_needs_backup_confirmation_and_code(client, db, waiting_changes):
    assert client.post("/database-bijwerken/", {"code": setup_code.get_code()}).status_code == 503
    assert client.post("/database-bijwerken/", {"code": "fout", "backup": "1"}).status_code == 503
    assert not waiting_changes
    response = client.post("/database-bijwerken/", {"code": setup_code.get_code(), "backup": "1"})
    assert response.status_code == 302 and response.url == "/beheer/" and waiting_changes
