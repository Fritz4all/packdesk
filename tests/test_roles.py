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
    response = client.post(f"{ROLES}add/", {"title_nl": "Marketing", "permissions": [view_settings.pk]})
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
    client.post(f"{ROLES}add/", {"title_nl": "Stiekem", "permissions": [perm("numbering.correct_numbersequence").pk]})
    role = Role.objects.filter(name="Stiekem").first()
    assert role is None or not role.permissions.filter(codename="correct_numbersequence").exists()


def test_editing_keeps_rights_the_editor_cannot_see(client, site):
    finance = Role.objects.get(name="Finance")
    before = set(finance.permissions.values_list("codename", flat=True))
    limited = Role.objects.create(name="Rollenbeheer")
    limited.permissions.set([perm("accounts.view_role"), perm("accounts.change_role"), perm("siteconfig.view_sitesettings")])
    client.force_login(make_user("rollen@example.test", staff=True, role="Rollenbeheer"))
    client.post(f"{ROLES}{finance.pk}/change/", {"title_nl": "Financieel", "permissions": [perm("siteconfig.view_sitesettings").pk]})
    after = set(finance.permissions.values_list("codename", flat=True))
    assert before <= after and "view_sitesettings" in after


def test_role_in_use_cannot_be_deleted(client, site, beheerder):
    client.force_login(beheerder)
    role = Role.objects.get(name="Administrator")
    assert client.get(f"{ROLES}{role.pk}/delete/").status_code == 403
    empty = Role.objects.create(name="Leeg")
    assert client.get(f"{ROLES}{empty.pk}/delete/").status_code == 200


def test_default_roles_are_not_overwritten(db):
    from apps.accounts.roles import ensure_roles

    role = Role.objects.get(name="Employee")
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
    finance = Role.objects.get(name="Finance")
    response = add_user(client, "fin2@example.test", role=finance)
    assert response.status_code == 302, response.content.decode()[:2000]
    user = User.objects.get(email="fin2@example.test")
    assert user.is_staff and list(user.groups.all()) == [finance]


def test_customer_gets_no_admin_access_or_role(client, site, beheerder):
    client.force_login(beheerder)
    add_user(client, "klant2@example.test", kind="customer", role=Role.objects.get(name="Finance"))
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
    response = add_user(client, "baas@example.test", role=Role.objects.get(name="Administrator"))
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


# --- Superadmin and role names ----------------------------------------------------------------

def test_role_names_are_shown_per_language(client, site, beheerder):
    from django.utils import translation

    finance = Role.objects.get(name="Finance")
    for lang, title in (("nl", "Financieel"), ("en", "Finance"), ("de", "Finanzen")):
        with translation.override(lang):
            assert str(finance) == title
    client.force_login(beheerder)
    client.post(f"{ROLES}add/", {"title_nl": "Inkoop", "title_en": "Purchasing", "permissions": []})
    role = Role.objects.get(name="Inkoop")
    with translation.override("en"):
        assert str(role) == "Purchasing"
    with translation.override("de"):
        assert str(role) == "Inkoop"  # nothing given: the first language


def test_superadmin_role_follows_the_superuser_flag_and_has_every_right(site):
    root = make_user("root@example.test", superuser=True)
    assert list(root.groups.values_list("name", flat=True)) == ["Superadmin"]
    assert root.has_perm("anything.that_is_added_later")
    root.is_superuser = False
    root.save()
    assert not root.groups.filter(name="Superadmin").exists()


def test_superadmin_is_given_by_role_up_to_the_maximum(client, site):
    from apps.siteconfig.models import SiteSettings

    root = make_user("root@example.test", superuser=True)
    superadmin = Role.objects.get(name="Superadmin")
    client.force_login(root)
    assert add_user(client, "tweede@example.test", role=superadmin).status_code == 302
    second = User.objects.get(email="tweede@example.test")
    assert second.is_superuser and second.is_staff
    response = add_user(client, "derde@example.test", role=superadmin)  # the maximum is 2
    assert response.status_code == 200 and not User.objects.filter(email="derde@example.test").exists()
    SiteSettings.objects.update(max_superadmins=3)
    assert add_user(client, "derde@example.test", role=superadmin).status_code == 302


def test_last_superadmin_keeps_the_role(client, site):
    root = make_user("root@example.test", superuser=True)
    client.force_login(root)
    service = Role.objects.get(name="Service")
    client.post(f"{USERS}{root.pk}/change/", {"email": root.email, "kind": "staff", "role": service.pk, "is_active": "on"})
    root.refresh_from_db()
    assert root.is_superuser


def test_only_superadmins_give_the_role_or_see_the_maximum(client, site, beheerder):
    client.force_login(beheerder)
    superadmin = Role.objects.get(name="Superadmin")
    assert add_user(client, "baas@example.test", role=superadmin).status_code == 200
    assert not User.objects.filter(email="baas@example.test").exists()
    assert client.get(f"{ROLES}{superadmin.pk}/delete/").status_code == 403
    assert "max_superadmins" not in client.get("/admin/siteconfig/sitesettings/1/change/").content.decode()
    client.force_login(make_user("root@example.test", superuser=True))
    assert "max_superadmins" in client.get("/admin/siteconfig/sitesettings/1/change/").content.decode()


def test_role_pages_show_the_names_per_language(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    for role in Role.objects.all():
        page = client.get(f"{ROLES}{role.pk}/change/").content.decode()
        assert 'name="title_nl"' in page and 'name="title_de"' in page, role.name
        assert ("permission-matrix" in page) != role.is_superadmin, role.name  # Superadmin: nothing to tick
    assert 'value="Beheerder"' in client.get(f"{ROLES}{Role.objects.get(name='Administrator').pk}/change/").content.decode()
    superadmin = Role.objects.get(name="Superadmin")
    response = client.post(f"{ROLES}{superadmin.pk}/change/", {"title_nl": "Hoofdbeheer", "title_en": "Head admin"})
    assert response.status_code == 302, response.content.decode()[:2000]
    assert superadmin.info.__class__.objects.get(pk=superadmin.pk).title_nl == "Hoofdbeheer"


def test_superadmin_cannot_be_selected_or_bulk_deleted(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    superadmin = Role.objects.get(name="Superadmin")
    empty = Role.objects.create(name="Leeg")
    page = client.get(ROLES).content.decode()
    assert f'value="{superadmin.pk}"' not in page and f'value="{empty.pk}"' in page
    used = Role.objects.get(name="Administrator")
    make_user("beheer@example.test", staff=True, role="Administrator")
    for chosen in ([superadmin.pk, empty.pk], [used.pk, empty.pk]):  # refused as a whole when one is protected
        client.post(ROLES, {"action": "delete_selected", "_selected_action": chosen, "post": "yes"})
        assert Role.objects.filter(pk__in=chosen).count() == 2
    client.post(ROLES, {"action": "delete_selected", "_selected_action": [empty.pk], "post": "yes"})
    assert not Role.objects.filter(pk=empty.pk).exists()


def test_role_editor_has_every_module_and_toggles(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    page = client.get(f"{ROLES}add/").content.decode()
    for code in ("telephony.view_quote", "printing.view_printer", "parts.view_partorder"):
        assert f'value="{perm(code).pk}"' in page, code  # modules are offered without being listed anywhere
    assert f'value="{perm("accounts.view_roleinfo").pk}"' not in page  # role names belong to the role itself
    assert 'class="pm-toggle" data-col="view"' in page and 'class="pm-toggle" data-app=' in page


def test_role_list_has_a_fixed_order(client, site):
    client.force_login(make_user("root@example.test", superuser=True))
    names = [role.name for role in client.get(ROLES).context["cl"].result_list]
    assert names == ["Administrator", "Employee", "Finance", "Service", "Superadmin"]


def _menu_pages():
    from django.urls import reverse

    from apps.dashboard import navigation as nav

    pages = []
    for section in nav.SECTIONS:
        for item in section["items"]:
            if "settings" in item:
                pages += [(reverse(url), perm) for _t, url, perm, _m, _f in nav.SETTINGS_TABS[item["settings"]][1]]
            elif item.get("permission"):
                pages.append((str(item["link"]), None))
    return pages


def test_staff_without_rights_cannot_open_any_menu_page(client, site):
    nobody = Role.objects.create(name="Niets")
    client.force_login(make_user("leeg@example.test", staff=True, role="Niets"))
    assert nobody.permissions.count() == 0
    open_pages = []
    for url, _perm in _menu_pages():
        response = client.get(url)
        if response.status_code == 200:
            open_pages.append(url)
    assert open_pages == [], open_pages


def test_one_right_opens_exactly_its_own_page(client, site):
    from django.contrib.auth.models import Permission

    users = {}
    for url, perm in _menu_pages():
        if perm is None:
            continue
        if perm not in users:
            app_label, codename = perm.split(".")
            role = Role.objects.create(name=f"Alleen {codename}")
            role.permissions.set([Permission.objects.get(content_type__app_label=app_label, codename=codename)])
            users[perm] = make_user(f"{codename}@example.test", staff=True, role=role.name)
        client.force_login(users[perm])
        assert client.get(url, follow=True).status_code == 200, url
        assert client.get("/admin/accounts/role/").status_code == 403, url  # and nothing else


def test_rights_structure_is_complete(db):
    """Every right named in the menu, the settings tabs and the default roles exists; every admin page can be
    reached from the menu; and the rights of every admin page can be put in a role."""
    import re

    from django.contrib import admin
    from django.urls import reverse

    from apps.accounts.permissions import HIDDEN_MODELS, managed_permissions
    from apps.accounts.roles import ROLES
    from apps.dashboard import navigation as nav

    existing = {f"{a}.{c}" for a, c in Permission.objects.values_list("content_type__app_label", "codename")}
    named = set(re.findall(r'has_perm\("([a-z_]+\.[a-z_]+)"\)', open(nav.__file__).read()))
    named |= {perm for _title, tabs in nav.SETTINGS_TABS.values() for _t, _u, perm, _m, _f in tabs}
    named |= {perm for perms in ROLES.values() for perm in perms}
    assert named - existing == set()
    reachable = {url for url, _perm in _menu_pages()}
    managed = {f"{p.content_type.app_label}.{p.codename}" for p in managed_permissions()}
    for model in admin.site._registry:
        label, name = model._meta.app_label, model._meta.model_name
        assert reverse(f"admin:{label}_{name}_changelist") in reachable, model._meta.label
        assert (label, name) in HIDDEN_MODELS or f"{label}.view_{name}" in managed, model._meta.label
