from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import render
from django.utils import timezone
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


class MaintenanceModeMiddleware:
    """While maintenance mode is on, visitors only see the maintenance page.

    Staff keep full access, so they can work in the admin and switch it off.
    Customers who are logged in are logged out; the login page is blocked too.
    """

    ALWAYS_ALLOWED = ("/beheer/", "/static/", "/media/", "/taal/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        site = request.site_settings
        if not site.maintenance_mode or request.path.startswith(self.ALWAYS_ALLOWED):
            return self.get_response(request)
        if request.user.is_authenticated and request.user.is_staff:
            return self.get_response(request)
        if request.user.is_authenticated:
            logout(request)
        response = render(request, "core/maintenance.html", status=503)
        if site.maintenance_until:
            seconds = int((site.maintenance_until - timezone.now()).total_seconds())
            if seconds > 0:
                response["Retry-After"] = str(seconds)
        return response
