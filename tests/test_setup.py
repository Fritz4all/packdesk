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
    settings.MAIL_SERVER_FROM_ENV = False  # the wizard asks for the mail server
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
    assert client.get("/admin/").url == "/installatie/"
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
        "name": "Bedrijf BV", "domain": "shop.bedrijf.test", "language": "nl", "languages": ["nl", "en"],
        "admin_language": "en", "email": "info@bedrijf.test",
    })
    assert response.url == "/installatie/mail/"
    site = SiteSettings.load()
    assert site.name == "Bedrijf BV" and site.language_codes == ["nl", "en"] and site.admin_language == "en"

    response = client.post("/installatie/mail/", {
        "mail_host": "smtp.bedrijf.test", "mail_port": "587", "mail_security": "starttls",
        "mail_user": "shop", "mail_password": "mail-geheim", "test_mail": "on",
    })
    assert response.url == "/installatie/numbering/"
    site = SiteSettings.load()
    assert site.mail_host == "smtp.bedrijf.test" and site.get_mail_password() == "mail-geheim"
    assert "mail-geheim" not in site.mail_password_encrypted
    assert mail.outbox[-1].to == ["baas@bedrijf.test"]

    sequences = list(NumberSequence.objects.all())
    data = {f"next_{s.pk}": 5000 for s in sequences}
    assert client.post("/installatie/numbering/", data).url == "/installatie/demo/"
    assert all(s.next_number == 5000 for s in NumberSequence.objects.all())

    assert client.post("/installatie/demo/", {}).url == "/admin/"
    assert SiteSettings.load().setup_completed
    assert client.get("/installatie/").url == "/admin/"  # closed for good
    assert client.get("/").status_code == 200


def test_wizard_refuses_weak_or_different_passwords(client, new_install):
    client.post("/installatie/code/", {"code": setup_code.get_code()})
    page = client.post("/installatie/admin/", {"email": "a@b.test", "password1": "kort", "password2": "anders"})
    assert page.status_code == 200 and not User.objects.exists()


def test_after_the_administrator_only_that_administrator_continues(client, new_install):
    make_user("baas@bedrijf.test", superuser=True)
    response = client.get("/installatie/basics/")
    assert response.url.startswith("/admin/login/")
    assert client.get("/installatie/code/").url.startswith("/admin/login/")  # no second administrator
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
    assert client.get("/static/css/packdesk.css").status_code != 503  # styles are not held back


def test_update_needs_backup_confirmation_and_code(client, db, waiting_changes):
    assert client.post("/database-bijwerken/", {"code": setup_code.get_code()}).status_code == 503
    assert client.post("/database-bijwerken/", {"code": "fout", "backup": "1"}).status_code == 503
    assert not waiting_changes
    response = client.post("/database-bijwerken/", {"code": setup_code.get_code(), "backup": "1"})
    assert response.status_code == 302 and response.url == "/admin/" and waiting_changes


# --- domain and mail server ----------------------------------------------------------------------


def test_domain_limits_host_names(client, site, settings):
    settings.ALLOWED_HOSTS = ["*"]
    SiteSettings.objects.filter(pk=1).update(domain="shop.bedrijf.test")
    assert client.get("/", HTTP_HOST="shop.bedrijf.test").status_code == 200
    assert client.get("/", HTTP_HOST="localhost").status_code == 200
    assert client.get("/", HTTP_HOST="evil.example").status_code == 400


def test_mail_server_from_admin_settings(site, settings):
    from apps.core.mail import SiteEmailBackend

    settings.MAIL_SERVER_FROM_ENV = False
    site.mail_host, site.mail_port, site.mail_security, site.mail_user = "smtp.bedrijf.test", 465, "ssl", "shop"
    site.set_mail_password("geheim")
    site.save()
    backend = SiteEmailBackend()
    assert (backend.host, backend.port, backend.use_ssl, backend.use_tls) == ("smtp.bedrijf.test", 465, True, False)
    assert backend.username == "shop" and backend.password == "geheim"
    settings.MAIL_SERVER_FROM_ENV = True
    assert SiteEmailBackend().host == settings.EMAIL_HOST  # the server settings win


# --- database step -------------------------------------------------------------------------------


def test_database_problems_are_recognised():
    from apps.core import server_setup as s

    assert s.classify(Exception(1049, "Unknown database 'x'")) == s.NO_DATABASE
    assert s.classify(Exception(1045, "Access denied")) == s.BAD_LOGIN
    assert s.classify(Exception(2003, "Can't connect")) == s.UNREACHABLE
    assert s.classify(Exception('FATAL:  database "x" does not exist')) == s.NO_DATABASE
    assert s.classify(Exception("password authentication failed for user")) == s.BAD_LOGIN
    assert s.classify(Exception("connection refused")) == s.UNREACHABLE


def test_database_step_when_database_is_missing(client, monkeypatch, settings, tmp_path):
    from apps.core import middleware, server_config, server_setup

    monkeypatch.setattr(middleware.ServerSetupMiddleware, "working", False)
    monkeypatch.setattr(server_setup, "diagnose", lambda: (server_setup.NO_DATABASE, "Unknown database"))
    page = client.get("/")
    assert page.status_code == 503 and 'name="admin_user"' in page.content.decode()

    calls = []
    monkeypatch.setattr(server_setup, "test", lambda target: None if calls else (server_setup.NO_DATABASE, "x"))
    monkeypatch.setattr(server_setup, "create", lambda target, user, pw: calls.append((target.name, user, pw)))
    monkeypatch.setattr(server_setup, "restart_soon", lambda: calls.append("restart"))
    settings.FIXED_SETTINGS = frozenset()
    data = {"code": setup_code.get_code(), "engine": "mariadb", "host": "db.bedrijf.test", "port": "",
            "name": "packdesk", "user": "packdesk", "password": "pd-geheim",
            "create": "1", "admin_user": "root", "admin_password": "root-geheim"}
    assert client.post("/installatie/database/", {**data, "name": "bad name;"}).status_code == 503 and not calls
    response = client.post("/installatie/database/", data)
    assert response.status_code == 503 and "restart" in calls and ("packdesk", "root", "root-geheim") in calls
    saved = server_config.read(settings.DATA_ROOT)
    assert saved["DB_HOST"] == "db.bedrijf.test" and saved["DB_PASSWORD"] == "pd-geheim"
    assert "root-geheim" not in server_config.path(settings.DATA_ROOT).read_text()  # admin login not stored


def test_server_config_file(tmp_path, monkeypatch):
    from apps.core import server_config

    monkeypatch.delenv("SECRET_KEY", raising=False)
    server_config.ensure_secret_key(tmp_path)
    assert server_config.read(tmp_path)["SECRET_KEY"]
    server_config.write(tmp_path, {"DB_HOST": "x"})
    values = server_config.read(tmp_path)
    assert values["DB_HOST"] == "x" and values["SECRET_KEY"]
    assert oct(server_config.path(tmp_path).stat().st_mode)[-3:] == "600"


def test_empty_values_count_as_not_set(tmp_path, monkeypatch):
    from apps.core import server_config

    server_config.write(tmp_path, {"SECRET_KEY": "saved-key"})
    monkeypatch.setenv("SECRET_KEY", "")  # e.g. "SECRET_KEY=" in .env
    server_config.load(tmp_path)
    server_config.ensure_secret_key(tmp_path)
    import os

    assert os.environ["SECRET_KEY"] == "saved-key"


def test_mail_step_can_be_skipped(client, new_install):
    client.post("/installatie/code/", {"code": setup_code.get_code()})
    client.post("/installatie/admin/", {"email": "baas@bedrijf.test", "password1": "lang-genoeg-wachtwoord",
                                        "password2": "lang-genoeg-wachtwoord"})
    assert client.post("/installatie/mail/", {"skip": "1"}).url == "/installatie/numbering/"
    # An empty server with the test box ticked also just goes on, without a failing test mail.
    assert client.post("/installatie/mail/", {"mail_security": "starttls", "test_mail": "on"}).url == "/installatie/numbering/"
    assert not SiteSettings.load().mail_host


def test_update_page_goes_away_after_migrating_from_the_command_line(monkeypatch):
    from apps.core import database_state

    answers = iter([["app.0002"], []])
    monkeypatch.setattr(database_state, "pending", lambda: next(answers))
    monkeypatch.setattr(database_state, "_pending_cache", None)
    assert database_state.has_pending() is True
    assert database_state.has_pending() is False  # checked again while something was pending


def test_database_step_explains_what_went_wrong(client, monkeypatch, settings):
    from apps.core import middleware, server_setup

    monkeypatch.setattr(middleware.ServerSetupMiddleware, "working", False)
    monkeypatch.setattr(server_setup, "diagnose", lambda: (server_setup.BAD_LOGIN, "old"))
    settings.FIXED_SETTINGS = frozenset()
    base = {"code": setup_code.get_code(), "engine": "mariadb", "host": "db", "port": "", "name": "packdesk",
            "user": "prodpackdesk", "password": "pd-geheim", "create": "1", "admin_user": "app", "admin_password": ""}
    calls = []
    monkeypatch.setattr(server_setup, "create", lambda *a: calls.append(a))
    monkeypatch.setattr(server_setup, "test", lambda target: (server_setup.BAD_LOGIN, "1045 refused"))

    page = client.post("/installatie/database/", base).content.decode()  # no admin password: not even tried
    assert not calls and "fill in the name and password of an administrator" in page.lower() or "beheerder" in page

    def refuse(*a):
        raise Exception(1045, "Access denied for user 'app'@'172.21.0.3' (using password: YES)")

    monkeypatch.setattr(server_setup, "create", refuse)
    page = client.post("/installatie/database/", {**base, "admin_password": "fout"}).content.decode()
    assert page.count('class="notice notice-error"') == 1 and "app" in page

    monkeypatch.setattr(server_setup, "create", lambda *a: calls.append(a))
    page = client.post("/installatie/database/", {**base, "admin_password": "goed"}).content.decode()
    assert calls and "prodpackdesk" in page and page.count('class="notice notice-error"') == 1


def test_refused_login_from_compose_file_is_explained(client, monkeypatch, settings):
    from apps.core import middleware, server_setup

    monkeypatch.setattr(middleware.ServerSetupMiddleware, "working", False)
    monkeypatch.setattr(server_setup, "diagnose", lambda: (server_setup.BAD_LOGIN, "1045"))
    settings.FIXED_SETTINGS = frozenset({"DB_USER", "DB_PASSWORD"})
    page = client.get("/").content.decode()
    assert "MARIADB_PASSWORD" in page and "down -v" in page
    settings.FIXED_SETTINGS = frozenset()
    assert "MARIADB_PASSWORD" not in client.get("/").content.decode()
