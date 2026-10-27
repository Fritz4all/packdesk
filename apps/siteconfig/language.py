"""Language of the admin, separate from the language of the website.

Staff can work in any language (site default or their own choice), also when the website
itself offers fewer languages. Mails to customers sent from the admin stay in the website's
language, not in the language the staff member happens to work in.
"""

from contextlib import nullcontext
from contextvars import ContextVar
from functools import wraps

from django.conf import settings
from django.utils import translation

ADMIN_PREFIX = "/admin/"
_in_admin = ContextVar("packdesk_in_admin", default=False)
CODES = {code for code, _name in settings.LANGUAGES}


def admin_language_for(user, site):
    own = getattr(user, "admin_language", "") if user.is_authenticated and user.is_staff else ""
    return own if own in CODES else site.admin_language


class AdminLanguageMiddleware:
    """Activates the admin language on admin pages. Runs after authentication."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(ADMIN_PREFIX):
            return self.get_response(request)
        language = admin_language_for(request.user, request.site_settings)
        translation.activate(language)
        request.LANGUAGE_CODE = language
        token = _in_admin.set(True)
        try:
            response = self.get_response(request)
        finally:
            _in_admin.reset(token)
        response.headers["Content-Language"] = language
        return response


def customer_language():
    """Context for texts that go to customers: the website's language when working in the admin."""
    if not _in_admin.get():
        return nullcontext()
    from .models import SiteSettings

    return translation.override(SiteSettings.load().language)


def in_customer_language(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with customer_language():
            return func(*args, **kwargs)

    return wrapper
