import pytest
from django.conf import settings

from apps.siteconfig.models import SiteSettings


def switch(client, language):
    return client.post("/taal/", {"language": language, "next": "/"})


def test_three_languages_are_configured():
    assert [code for code, _name in settings.LANGUAGES] == ["nl", "en", "de"]


@pytest.mark.parametrize("language, text", [("nl", "Inloggen"), ("en", "Log in"), ("de", "Anmelden")])
def test_visitor_can_switch_language(client, site, language, text):
    switch(client, language)
    page = client.get("/").content.decode()
    assert text in page
    assert f'<html lang="{language}"' in page


def test_default_language_from_settings(client, site):
    site.language = "de"
    site.save()
    assert "Anmelden" in client.get("/").content.decode()


def test_unavailable_language_falls_back_to_default(client, site):
    site.languages = "nl,en"
    site.save()
    switch(client, "de")
    assert "Inloggen" in client.get("/").content.decode()


def test_switcher_lists_only_available_languages(client, site):
    site.languages = "nl,de"
    site.save()
    page = client.get("/").content.decode()
    assert 'value="de"' in page and 'value="en"' not in page


def test_switcher_hidden_with_one_language(client, site):
    site.languages = "nl"
    site.save()
    assert 'name="language"' not in client.get("/").content.decode()


def test_translated_tagline_with_fallback(client, site):
    site.tagline_nl = "Zorgeloze support"
    site.tagline_de = "Sorgloser Support"
    site.tagline_en = ""
    site.save()
    switch(client, "de")
    assert "Sorgloser Support" in client.get("/").content.decode()
    switch(client, "en")
    assert "Zorgeloze support" in client.get("/").content.decode()


@pytest.mark.parametrize("folder", ["locale", "locale_vendor"])
@pytest.mark.parametrize("lang", ["nl", "de"])
def test_every_message_is_translated(folder, lang):
    """Dutch and German catalogues are complete (no empty or fuzzy entries)."""
    import re
    from pathlib import Path

    po = (Path(settings.BASE_DIR) / folder / lang / "LC_MESSAGES" / "django.po").read_text(encoding="utf-8")
    entries = po.split("\n\n")[1:]
    # An empty msgstr is `msgstr ""` without continuation lines.
    missing = [e for e in entries if re.search(r'^msgstr ""\n(?!")', e + "\n", re.M) and "msgid_plural" not in e]
    assert not missing, f"{len(missing)} untranslated, e.g. {missing[0][:120]}"
    assert "#, fuzzy" not in po
