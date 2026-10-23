from apps.siteconfig.models import SiteSettings


def test_settings_are_created_on_first_use(db):
    assert SiteSettings.objects.count() == 0
    assert SiteSettings.load().name == "PackDesk"
    assert SiteSettings.objects.count() == 1


def test_there_is_only_ever_one_settings_row(db):
    SiteSettings(name="Een").save()
    SiteSettings(name="Twee").save()
    assert SiteSettings.objects.count() == 1
    assert SiteSettings.load().name == "Twee"


def test_home_shows_name_colour_and_company_details(client, site):
    site.legal_name = "Testshop B.V."
    site.coc_number = "12345678"
    site.save()
    page = client.get("/").content.decode()
    assert "Testshop" in page and "#112233" in page
    assert "Testshop B.V." in page and "12345678" in page


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
