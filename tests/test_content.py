from datetime import timedelta

from django.utils import timezone

from apps.siteconfig.models import HomeBlock, MenuItem

from .conftest import PASSWORD, make_user


# --- Home page, menu and footer -------------------------------------------

def test_home_blocks_come_from_settings(client, site):
    HomeBlock.objects.filter(settings=site).delete()
    HomeBlock.objects.create(settings=site, title="Eigen blok", text="Eigen tekst", link_url="/x/", link_text="Lees")
    HomeBlock.objects.create(settings=site, title="Verborgen", is_active=False)
    page = client.get("/").content.decode()
    assert "Eigen blok" in page and "Eigen tekst" in page and 'href="/x/"' in page
    assert "Verborgen" not in page
    assert "Servicepacks" not in page


def test_block_visibility_depends_on_login(client, site):
    HomeBlock.objects.create(settings=site, title="Alleen gasten", visibility="anonymous")
    HomeBlock.objects.create(settings=site, title="Alleen klanten", visibility="logged_in")
    page = client.get("/").content.decode()
    assert "Alleen gasten" in page and "Alleen klanten" not in page
    client.force_login(make_user("klant@example.test"))
    page = client.get("/").content.decode()
    assert "Alleen gasten" not in page and "Alleen klanten" in page


def test_menu_items_in_header(client, site):
    MenuItem.objects.create(settings=site, label="Contact", url="/contact/")
    MenuItem.objects.create(settings=site, label="Extern", url="https://example.test", new_tab=True)
    MenuItem.objects.create(settings=site, label="Uit", url="/uit/", is_active=False)
    page = client.get("/").content.decode()
    assert 'href="/contact/"' in page and 'target="_blank"' in page
    assert "/uit/" not in page


def test_translated_block_title(client, site):
    block = HomeBlock.objects.create(settings=site, title_nl="Hallo", title_de="Guten Tag")
    client.post("/language/", {"language": "de", "next": "/"})
    assert block.title_de in client.get("/").content.decode()


def test_hero_button_meta_and_footer(client, site):
    site.hero_button_text = "Start hier"
    site.meta_description = "Beschrijving voor Google"
    site.footer_text = "Alle prijzen excl. btw"
    site.vat_number = "NL000099998B57"
    site.footer_show_vat = True
    site.footer_show_coc = False
    site.coc_number = "87654321"
    site.save()
    page = client.get("/").content.decode()
    assert "Start hier" in page
    assert '<meta name="description" content="Beschrijving voor Google">' in page
    assert "Alle prijzen excl. btw" in page
    assert "NL000099998B57" in page and "87654321" not in page


def test_announcement_bar(client, site):
    site.announcement_text = "Vrijdag onderhoud"
    site.save()
    assert "Vrijdag onderhoud" not in client.get("/").content.decode()
    site.announcement_enabled = True
    site.announcement_level = "warning"
    site.save()
    page = client.get("/").content.decode()
    assert "Vrijdag onderhoud" in page and "announcement-warning" in page


# --- Maintenance mode -------------------------------------------------------

def maintenance_on(site, **extra):
    site.maintenance_mode = True
    site.maintenance_message = "Even geduld"
    for key, value in extra.items():
        setattr(site, key, value)
    site.save()


def test_maintenance_page_for_visitors(client, site):
    maintenance_on(site, maintenance_until=timezone.now() + timedelta(hours=2))
    response = client.get("/")
    assert response.status_code == 503
    assert "Even geduld" in response.content.decode()
    assert 7000 < int(response["Retry-After"]) <= 7200


def test_login_blocked_during_maintenance(client, site):
    make_user("klant@example.test")
    maintenance_on(site)
    assert client.get("/login/").status_code == 503
    client.post("/login/", {"username": "klant@example.test", "password": PASSWORD})
    assert "_auth_user_id" not in client.session


def test_logged_in_customer_is_logged_out(client, site):
    client.force_login(make_user("klant@example.test"))
    maintenance_on(site)
    assert client.get("/my/").status_code == 503
    assert "_auth_user_id" not in client.session


def test_staff_can_work_during_maintenance(client, site, beheerder):
    maintenance_on(site)
    assert client.get("/admin/login/").status_code == 200
    client.force_login(beheerder)
    assert client.get("/").status_code == 200
    assert client.get("/admin/siteconfig/sitesettings/1/change/").status_code == 200


def test_site_back_after_maintenance(client, site):
    maintenance_on(site)
    site.maintenance_mode = False
    site.save()
    assert client.get("/").status_code == 200


def test_mailto_link_goes_to_the_general_email_address(client, site):
    from apps.siteconfig.models import HomeBlock

    site.email = "info@bedrijf.test"
    site.save()
    HomeBlock.objects.all().delete()
    HomeBlock.objects.create(settings=site, title="Onderdelen", link_url="mailto:", link_text="Informatie aanvragen")
    html = client.get("/").content.decode()
    assert 'href="mailto:info@bedrijf.test?subject=Onderdelen"' in html
    site.email = ""
    site.save()
    assert "mailto:" not in client.get("/").content.decode()  # no address: no link


def test_friendly_error_pages(client, site, settings):
    settings.DEBUG = False
    page = client.get("/does-not-exist/")
    assert page.status_code == 404 and "404" in page.content.decode() and 'class="maintenance"' in page.content.decode()
    client.force_login(make_user("mw@example.test", staff=True, role="Medewerker"))
    denied = client.get("/admin/trash/trashentry/")
    assert denied.status_code == 403 and "403" in denied.content.decode()
    from django.template import loader

    assert "500" in loader.get_template("500.html").render({})  # renders without request or database


def test_old_admin_addresses_lead_to_the_new_ones(client, site):
    assert client.get("/beheer/customers/customer/?q=a")["Location"] == "/admin/customers/customer/?q=a"
    assert client.get("/beheer/vergelijken/3/zoeken/")["Location"] == "/admin/compare/3/search/"


def test_old_dutch_website_addresses_lead_to_the_english_ones(client, site):
    assert client.get("/inloggen/")["Location"] == "/login/"
    assert client.get("/mijn/bestellingen/12/?x=1")["Location"] == "/my/orders/12/?x=1"
    assert client.get("/wachtwoord-instellen/MQ/abc-klaar/")["Location"] == "/set-password/MQ/abc-klaar/"
    posted = client.post("/storing-melden/", {"a": "b"})
    assert posted.status_code == 308 and posted["Location"] == "/report-fault/"  # form data kept
    assert client.get("/over-ons/").status_code == 404  # unknown addresses are not touched


def test_development_shows_the_friendly_404_page_too(settings, monkeypatch):
    from django.apps import apps
    from django.views import debug
    from django.views.defaults import page_not_found

    monkeypatch.setattr(debug, "technical_404_response", debug.technical_404_response)  # restored afterwards
    settings.DEBUG, settings.TECHNICAL_404 = True, False
    apps.get_app_config("core").ready()
    assert debug.technical_404_response is page_not_found
