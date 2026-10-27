from django.contrib.auth.models import Permission

from apps.accounts.models import Role, User

from .conftest import make_user

ROLES = "/admin/accounts/role/"
USERS = "/admin/accounts/user/"


def perm(code):
    app_label, codename = code.split(".")
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def add_user(client, email, kind="staff", role=None, **extra):
    data = {"email": email, "password1": "Een-lang-wachtwoord-42", "password2": "Een-lang-wachtwoord-42",
            "kind": kind, "role": role.pk if role else ""}
    data.update(extra)
    return client.post(f"{USERS}add/", data)


# --- creating and editing roles ----------------------------------------------

def test_beheerder_creates_role_with_permissions(client, site, beheerder):
    client.force_login(beheerder)
    view_settings = perm("siteconfig.view_sitesettings")
    response = client.post(f"{ROLES}add/", {"name": "Marketing", "permissions": [view_settings.pk]})
    assert response.status_code == 302, response.content.decode()[:2000]
    role = Role.objects.get(name="Marketing")
    assert list(role.permissions.all()) == [view_settings]


def test_role_editor_shows_matrix(client, site, beheerder):
    client.force_login(beheerder)
    page = client.get(f"{ROLES}add/").content.decode()
    assert "permission-matrix" in page
    assert "Nummerreeksen" in page and "Mag nummertellers corrigeren" in page


def test_cannot_grant_rights_you_do_not_have(client, site):
    limited = Role.objects.create(name="Rollenbeheer")
    limited.permissions.set([perm("accounts.view_role"), perm("accounts.add_role"), perm("accounts.change_role")])
    editor = make_user("rollen@example.test", staff=True, role="Rollenbeheer")
    client.force_login(editor)
    page = client.get(f"{ROLES}add/").content.decode()
    assert f'value="{perm("numbering.correct_numbersequence").pk}"' not in page
    client.post(f"{ROLES}add/", {"name": "Stiekem", "permissions": [perm("numbering.correct_numbersequence").pk]})
    role = Role.objects.filter(name="Stiekem").first()
    assert role is None or not role.permissions.filter(codename="correct_numbersequence").exists()


def test_editing_keeps_rights_the_editor_cannot_see(client, site):
    finance = Role.objects.get(name="Financieel")
    before = set(finance.permissions.values_list("codename", flat=True))
    limited = Role.objects.create(name="Rollenbeheer")
    limited.permissions.set([perm("accounts.view_role"), perm("accounts.change_role"), perm("siteconfig.view_sitesettings")])
    client.force_login(make_user("rollen@example.test", staff=True, role="Rollenbeheer"))
    client.post(f"{ROLES}{finance.pk}/change/", {"name": "Financieel", "permissions": [perm("siteconfig.view_sitesettings").pk]})
    after = set(finance.permissions.values_list("codename", flat=True))
    assert before <= after and "view_sitesettings" in after


def test_role_in_use_cannot_be_deleted(client, site, beheerder):
    client.force_login(beheerder)
    role = Role.objects.get(name="Beheerder")
    assert client.get(f"{ROLES}{role.pk}/delete/").status_code == 403
    empty = Role.objects.create(name="Leeg")
    assert client.get(f"{ROLES}{empty.pk}/delete/").status_code == 200


def test_default_roles_are_not_overwritten(db):
    from apps.accounts.roles import ensure_roles

    role = Role.objects.get(name="Medewerker")
    role.permissions.set([perm("siteconfig.view_sitesettings")])
    ensure_roles()
    assert list(role.permissions.values_list("codename", flat=True)) == ["view_sitesettings"]


# --- users get a role ------------------------------------------------------

def test_staff_user_needs_role(client, site, beheerder):
    client.force_login(beheerder)
    response = add_user(client, "zonderrol@example.test")
    assert response.status_code == 200
    assert not User.objects.filter(email="zonderrol@example.test").exists()


def test_staff_user_with_role_gets_admin_access(client, site, beheerder):
    client.force_login(beheerder)
    finance = Role.objects.get(name="Financieel")
    response = add_user(client, "fin2@example.test", role=finance)
    assert response.status_code == 302, response.content.decode()[:2000]
    user = User.objects.get(email="fin2@example.test")
    assert user.is_staff and list(user.groups.all()) == [finance]


def test_customer_gets_no_admin_access_or_role(client, site, beheerder):
    client.force_login(beheerder)
    add_user(client, "klant2@example.test", kind="customer", role=Role.objects.get(name="Financieel"))
    user = User.objects.get(email="klant2@example.test")
    assert not user.is_staff and not user.groups.exists()


def test_role_decides_what_admin_user_sees(client, site):
    viewer = Role.objects.create(name="Alleen instellingen")
    viewer.permissions.set([perm("siteconfig.view_sitesettings")])
    user = make_user("kijker@example.test", staff=True, role="Alleen instellingen")
    client.force_login(user)
    assert client.get("/admin/siteconfig/sitesettings/1/change/").status_code == 200
    assert client.get(USERS).status_code == 403
    assert client.get("/admin/numbering/numbersequence/").status_code == 403
    # Read-only: posting changes is refused.
    assert client.post("/admin/siteconfig/sitesettings/1/change/", {"name": "X"}).status_code == 403


def test_cannot_assign_role_with_more_rights(client, site):
    limited = Role.objects.create(name="Gebruikersbeheer")
    limited.permissions.set([perm("accounts.view_user"), perm("accounts.add_user"), perm("accounts.change_user")])
    client.force_login(make_user("gb@example.test", staff=True, role="Gebruikersbeheer"))
    response = add_user(client, "baas@example.test", role=Role.objects.get(name="Beheerder"))
    assert response.status_code == 200  # Beheerder is not offered
    assert not User.objects.filter(email="baas@example.test").exists()


def test_role_column_in_user_list(client, site, beheerder):
    client.force_login(beheerder)
    assert "Beheerder" in client.get(USERS).content.decode()


def test_new_staff_user_can_log_in_to_admin(client, site, beheerder):
    client.force_login(beheerder)
    add_user(client, "nieuw@example.test", role=Role.objects.get(name="Service"))
    client.logout()
    client.post("/admin/login/", {"username": "nieuw@example.test", "password": "Een-lang-wachtwoord-42"})
    assert client.get("/admin/").status_code == 200
