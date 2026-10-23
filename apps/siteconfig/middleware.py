from django.utils import translation

from .models import SiteSettings


class SiteSettingsMiddleware:
    """Loads the site settings once per request and activates their language."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.site_settings = SiteSettings.load()
        translation.activate(request.site_settings.language)
        request.LANGUAGE_CODE = request.site_settings.language
        return self.get_response(request)
