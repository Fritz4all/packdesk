from apps.accounts.models import User
from apps.siteconfig.models import Address, SiteSettings

from .conftest import make_user

SETTINGS_URL = "/beheer/siteconfig/sitesettings/"


def settings_form(**overrides):
    data = {
        "name": "Testshop",
        "language": "nl",
        "languages": ["nl", "en", "de"],
        "admin_language": "nl",
        "mail_security": "starttls",
        "session_timeout_staff": "120",
        "session_timeout_customers": "60",
        "password_min_length_staff": "10", "password_min_length_customers": "10",
        "trash_retention_days": "30",
        "primary_color": "#112233",
        "accent_color": "#ffffff",
        "country": "NL",
        "theme": "auto",
        "theme_switch": "on",
        "announcement_level": "info",
        "addresses-TOTAL_FORMS": "0",
        "addresses-INITIAL_FORMS": "0",
        "addresses-MIN_NUM_FORMS": "0",
        "addresses-MAX_NUM_FORMS": "1000",
    }
    for prefix in ("home_blocks", "menu_items"):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0",
                     f"{prefix}-MIN_NUM_FORMS": "0", f"{prefix}-MAX_NUM_FORMS": "1000"})
    data.update(overrides)
    return data


def test_settings_list_opens_the_single_form(client, site, beheerder):
    client.force_login(beheerder)
    response = client.get(SETTINGS_URL)
    assert response.status_code == 302 and response["Location"].endswith("/1/change/")
    assert client.get(SETTINGS_URL + "1/change/").status_code == 200


def test_beheerder_can_change_name_and_colours(client, site, beheerder):
    client.force_login(beheerder)
    response = client.post(SETTINGS_URL + "1/change/", settings_form(name="Klant X", primary_color="#000000"))
    assert response.status_code == 302, response.content.decode()[:2000]
    assert SiteSettings.load().name == "Klant X"
    assert "Klant X" in client.get("/").content.decode()


def test_invalid_colour_is_rejected(client, site, beheerder):
    client.force_login(beheerder)
    client.post(SETTINGS_URL + "1/change/", settings_form(primary_color="red;}</style>"))
    assert SiteSettings.load().primary_color == "#112233"


def test_settings_cannot_be_added_or_deleted(client, site, beheerder):
    client.force_login(beheerder)
    assert client.get(SETTINGS_URL + "add/").status_code == 403
    assert client.get(SETTINGS_URL + "1/delete/").status_code == 403


def test_user_without_role_cannot_open_settings(client, site):
    client.force_login(make_user("medewerker@example.test", staff=True, role="Medewerker"))
    assert client.get(SETTINGS_URL + "1/change/").status_code == 403


def test_beheerder_does_not_see_superusers(client, site, beheerder):
    root = make_user("root@example.test", superuser=True)
    make_user("klant@example.test")
    client.force_login(beheerder)
    page = client.get("/beheer/accounts/user/").content.decode()
    assert "klant@example.test" in page and "root@example.test" not in page
    assert client.get(f"/beheer/accounts/user/{root.pk}/change/").status_code == 302


def test_beheerder_cannot_make_superuser(client, site, beheerder):
    target = make_user("klant@example.test")
    client.force_login(beheerder)
    client.post(
        f"/beheer/accounts/user/{target.pk}/change/",
        {"email": "klant@example.test", "kind": "customer", "is_active": "on", "is_superuser": "on"},
    )
    assert not User.objects.get(pk=target.pk).is_superuser


def test_beheerder_creates_user(client, site, beheerder):
    client.force_login(beheerder)
    client.post(
        "/beheer/accounts/user/add/",
        {"email": "nieuw@example.test", "password1": "Een-lang-wachtwoord-42", "password2": "Een-lang-wachtwoord-42",
         "kind": "customer"},
    )
    assert User.objects.filter(email="nieuw@example.test").exists()


def test_admin_login_asks_for_email(client, site):
    page = client.get("/beheer/login/").content.decode()
    assert "E-mailadres" in page


def test_colour_fields_use_colour_picker(client, site, beheerder):
    client.force_login(beheerder)
    page = client.get(SETTINGS_URL + "1/change/").content.decode()
    assert page.count('type="color"') == 2


def test_tagline_can_be_entered_per_language(client, site, beheerder):
    client.force_login(beheerder)
    client.post(
        SETTINGS_URL + "1/change/",
        settings_form(tagline_nl="Zorgeloos", tagline_en="Carefree", tagline_de="Sorglos"),
    )
    site = SiteSettings.load()
    assert (site.tagline_nl, site.tagline_en, site.tagline_de) == ("Zorgeloos", "Carefree", "Sorglos")


def test_default_language_must_be_available(client, site, beheerder):
    client.force_login(beheerder)
    response = client.post(SETTINGS_URL + "1/change/", settings_form(language="de", languages=["nl", "en"]))
    assert response.status_code == 200
    assert SiteSettings.load().language == "nl"


def test_available_languages_are_saved(client, site, beheerder):
    client.force_login(beheerder)
    client.post(SETTINGS_URL + "1/change/", settings_form(languages=["nl", "de"]))
    assert SiteSettings.load().language_codes == ["nl", "de"]


def test_beheerder_sets_appearance(client, site, beheerder):
    client.force_login(beheerder)
    form = settings_form(theme="light")
    del form["theme_switch"]
    client.post(SETTINGS_URL + "1/change/", form)
    site = SiteSettings.load()
    assert site.theme == "light" and site.theme_switch is False


def address_rows(*rows):
    data = {"addresses-TOTAL_FORMS": str(len(rows))}
    for i, row in enumerate(rows):
        base = {"label": f"Adres {i}", "line1": f"Straat {i}", "postal_code": "1234 AB", "city": "Almere",
                "country": "Nederland", "position": str(i)}
        base.update(row)
        data.update({f"addresses-{i}-{k}": v for k, v in base.items()})
    return data


def test_beheerder_adds_separate_billing_address(client, site, beheerder):
    client.force_login(beheerder)
    form = settings_form(**address_rows(
        {"label": "Bezoekadres", "line1": "Koningsbeltweg 41F", "on_website": "on"},
        {"label": "Factuuradres", "line1": "Postbus 1", "on_invoices": "on", "on_quotes": "on"},
    ))
    response = client.post(SETTINGS_URL + "1/change/", form)
    assert response.status_code == 302, response.content.decode()[:3000]
    site = SiteSettings.load()
    assert site.address_for("website").line1 == "Koningsbeltweg 41F"
    assert site.address_for("invoice").line1 == "Postbus 1"
    assert site.address_for("quote").line1 == "Postbus 1"
    # Nothing ticked for mails: falls back to the first address.
    assert site.address_for("mail").line1 == "Koningsbeltweg 41F"


def test_usage_on_two_addresses_is_rejected(client, site, beheerder):
    client.force_login(beheerder)
    form = settings_form(**address_rows({"on_invoices": "on"}, {"on_invoices": "on"}))
    response = client.post(SETTINGS_URL + "1/change/", form)
    assert response.status_code == 200
    assert "meer dan één adres" in response.content.decode()
    assert Address.objects.count() == 0
