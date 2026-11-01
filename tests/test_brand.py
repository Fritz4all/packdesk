import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.siteconfig import brand
from apps.siteconfig.models import SiteSettings


@pytest.fixture(autouse=True)
def media(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"


def test_icon_in_the_chosen_colour(client, site):
    assert brand.COLORS["blue"][0] in client.get("/brand/icon.svg").content.decode()  # blue by default
    SiteSettings.objects.update(icon_color="orange")
    svg = client.get("/brand/icon.svg").content.decode()
    assert svg.startswith("<svg") and "#ea580c" in svg
    SiteSettings.objects.update(icon_color="primary")
    assert "#112233" in client.get("/brand/icon.svg").content.decode()  # the website's primary colour


def test_png_and_ico_sizes(client, site):
    from io import BytesIO

    from PIL import Image

    for size in brand.PNG_SIZES:
        response = client.get(f"/brand/icon-{size}.png")
        assert response["Content-Type"] == "image/png" and Image.open(BytesIO(response.content)).size == (size, size)
    assert client.get("/brand/icon-99.png").status_code == 404
    ico = client.get("/favicon.ico")
    assert ico["Content-Type"] == "image/x-icon" and Image.open(BytesIO(ico.content)).format == "ICO"


def test_uploaded_favicon_wins(client, site):
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGB", (32, 32), "red").save(out, "PNG")
    settings_row = SiteSettings.load()
    settings_row.favicon = SimpleUploadedFile("own.png", out.getvalue(), content_type="image/png")
    settings_row.save()
    assert client.get("/favicon.ico")["Location"].endswith(".png")
    assert "/brand/icon.svg" not in client.get("/").content.decode()


def test_website_and_admin_use_the_icon(client, site, beheerder):
    page = client.get("/").content.decode()
    assert '/brand/icon.svg?c=2563eb' in page and "/brand/icon-180.png" in page
    client.force_login(beheerder)
    assert "/brand/icon.svg?c=2563eb" in client.get("/admin/").content.decode()
    SiteSettings.objects.update(icon_color="teal")
    assert "/brand/icon.svg?c=0f766e" in client.get("/admin/").content.decode()  # new colour = new address


def test_admin_sidebar_shows_the_version(client, site, beheerder, settings):
    settings.APP_VERSION = "0.1.99"
    client.force_login(beheerder)
    assert "PackDesk 0.1.99" in client.get("/admin/").content.decode()
    assert "0.1.99" not in client.get("/").content.decode()  # not on the public website


THEMES = ["classic", "workbench", "night_shift", "open_house"]


@pytest.mark.parametrize("theme", THEMES)
def test_every_page_works_in_every_theme(client, site, theme):
    from decimal import Decimal

    from apps.hardware.models import Device, DeviceType

    SiteSettings.objects.update(site_theme=theme)
    device = Device.objects.create(device_type=DeviceType.objects.first(), model="Testmodel", serial_nr="TH-1",
                                   status=Device.Status.FOR_SALE, sale_price=Decimal("100.00"), specs={"cpu": "i5"})
    home = client.get("/").content.decode()
    assert f'data-site-theme="{theme}"' in home
    assert (f"css/themes/{theme}.css" in home) == (theme != "classic")
    shop = client.get("/hardware/").content.decode()
    assert "Testmodel" in shop and "121,00" in shop and "/hardware/" + device.number in shop
    assert client.get(f"/hardware/{device.number}/").status_code == 200
    assert client.get("/hardware/?type=1&q=test&sort=price").status_code == 200
    assert client.get("/login/").status_code == 200
    assert client.get("/signup/").status_code == 200


def test_classic_theme_keeps_the_original_templates(client, site):
    assert "core/home.html" in [t.name for t in client.get("/").templates]
    assert "themes/workbench/core/home.html" not in [t.name for t in client.get("/").templates]
    SiteSettings.objects.update(site_theme="workbench")
    assert "themes/workbench/core/home.html" in [t.name for t in client.get("/").templates]


def test_theme_fonts_are_served_from_this_site(client, site):
    from pathlib import Path

    from django.conf import settings as django_settings

    for theme in THEMES[1:]:
        css = (Path(django_settings.BASE_DIR) / f"static/css/themes/{theme}.css").read_text()
        assert "googleapis" not in css and "fonts/" in css
    assert "fonts.googleapis" not in client.get("/").content.decode()


def test_licence_number_from_the_home_page_is_filled_in(client, site):
    assert 'value="26A0001"' in client.get("/register/?number=26A0001").content.decode()


@pytest.mark.parametrize("theme", THEMES)
def test_hardware_can_be_shown_as_list_or_tiles(client, site, theme):
    from decimal import Decimal

    from apps.hardware.models import Device, DeviceType

    SiteSettings.objects.update(site_theme=theme)
    Device.objects.create(device_type=DeviceType.objects.first(), model="Lijstmodel", serial_nr="TH-2",
                          status=Device.Status.FOR_SALE, sale_price=Decimal("100.00"))
    default = client.get("/hardware/").content.decode()
    assert ('class="hw-list"' in default) == (theme == "workbench")  # a list fits this theme from the start
    page = client.get("/hardware/?view=list").content.decode()
    assert 'class="hw-list"' in page and "Lijstmodel" in page and "121,00" in page
    assert 'class="hw-list"' in client.get("/hardware/").content.decode()  # remembered
    page = client.get("/hardware/?view=tiles").content.decode()
    assert 'class="hw-list"' not in page and "Lijstmodel" in page
    assert 'class="hw-list"' not in client.get("/hardware/?type=1").content.decode()
    assert "view=list" in page and "view=tiles" in page
