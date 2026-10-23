from apps.siteconfig.models import Address, SiteSettings


def test_fresh_install_has_settings_with_defaults(db):
    site = SiteSettings.load()
    assert SiteSettings.objects.count() == 1
    assert site.name == "PackDesk"
    assert site.intro_text_nl and site.intro_text_en and site.intro_text_de
    assert site.home_blocks.count() == 3


def test_there_is_only_ever_one_settings_row(db):
    SiteSettings(name="Een").save()
    SiteSettings(name="Twee").save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().name == "Twee"


def test_home_shows_name_colour_and_company_details(client, site):
    site.legal_name = "Testshop B.V."
    site.coc_number = "12345678"
    site.save()
    Address.objects.create(settings=site, label="Bezoek", line1="Koningsbeltweg 41F", postal_code="1329 AB",
                           city="Almere", on_website=True)
    page = client.get("/").content.decode()
    assert "Testshop" in page and "#112233" in page
    assert "Testshop B.V." in page and "12345678" in page
    assert "Koningsbeltweg 41F, 1329 AB Almere" in page


def test_intro_text_replaces_default(client, site):
    site.intro_text = "Welkom bij onze eigen shop."
    site.save()
    assert "Welkom bij onze eigen shop." in client.get("/").content.decode()


def test_page_language_follows_setting(client, site):
    assert "Inloggen" in client.get("/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    site.language = "en"
    site.save()
    assert "Log in" in client.get("/").content.decode()


def test_unknown_host_is_rejected(client, site):
    assert client.get("/", HTTP_HOST="evil.example").status_code == 400


def test_default_theme_is_auto_with_switch(client, site):
    page = client.get("/").content.decode()
    assert 'data-theme-default="auto"' in page and 'data-theme-switch="1"' in page
    assert 'id="theme-select"' in page
    assert ' data-theme="' not in page


def test_fixed_dark_theme_without_switch(client, site):
    site.theme = "dark"
    site.theme_switch = False
    site.save()
    page = client.get("/").content.decode()
    assert 'data-theme="dark"' in page and 'data-theme-switch="0"' in page
    assert 'id="theme-select"' not in page


def test_theme_switch_is_translated(client, site):
    client.post("/taal/", {"language": "de", "next": "/"})
    page = client.get("/").content.decode()
    assert "Hell" in page and "Dunkel" in page


def test_address_for_without_addresses(site):
    assert site.address_for("invoice") is None


def test_address_specific_contact_details(site):
    site.phone, site.email = "010-1111111", "info@example.test"
    site.save()
    billing = Address.objects.create(settings=site, label="Factuur", line1="Postbus 1", postal_code="1000 AA",
                                     city="Almere", on_invoices=True, email="administratie@example.test")
    assert billing.contact_email() == "administratie@example.test"
    assert billing.contact_phone() == "010-1111111"


def test_login_page_shows_site_name_not_host(client, site):
    page = client.get("/inloggen/").content.decode()
    assert "Testshop" in page
    assert "testserver" not in page
