from django.conf import settings
from django.utils import translation

from .models import SiteSettings


class SiteSettingsMiddleware:
    """Loads the site settings and activates the visitor's language.

    The visitor's choice (language cookie) wins if that language is available;
    otherwise the default language from the settings is used.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        site = SiteSettings.load()
        request.site_settings = site
        chosen = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        language = chosen if chosen in site.language_codes else site.language
        translation.activate(language)
        request.LANGUAGE_CODE = language
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", language)
        return response
