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
