from django.conf import settings
from django.http import HttpResponseBadRequest
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

    LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}

    def __call__(self, request):
        site = SiteSettings.load()
        request.site_settings = site
        if site.domain and settings.ALLOWED_HOSTS == ["*"]:
            # No fixed host list on the server: only the domain from the settings (and localhost) is answered.
            host = request.get_host().rsplit(":", 1)[0].lower()
            if host not in self.LOCAL_HOSTS and host != site.domain.strip().lower():
                return HttpResponseBadRequest("Unknown host name.")
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

    ALWAYS_ALLOWED = ("/admin/", "/static/", "/media/", "/language/")

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


class SessionTimeoutMiddleware:
    """Logs people out after the minutes without activity set under Settings → Security.

    Every request starts the countdown again; staff and customers have their own timeout.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            site = request.site_settings
            minutes = site.session_timeout_staff if user.is_staff else site.session_timeout_customers
            request.session.set_expiry(minutes * 60 if minutes else None)
        return self.get_response(request)
