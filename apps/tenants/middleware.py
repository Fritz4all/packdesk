from django.conf import settings
from django.contrib.auth import logout
from django.http import Http404
from django.utils import translation

from .models import Domain


def host_without_port(request):
    host = request.get_host().lower()
    if host.startswith("["):  # IPv6 literal
        return host.split("]")[0] + "]"
    return host.rsplit(":", 1)[0] if ":" in host else host


class TenantMiddleware:
    """Sets request.tenant from the host name.

    Platform hosts (settings.PLATFORM_HOSTS) have no tenant and only serve the
    admin, for managing all tenants. Unknown hosts get a 404.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = host_without_port(request)
        request.tenant = None
        request.is_platform = host in settings.PLATFORM_HOSTS

        if request.is_platform:
            if not (request.path.startswith("/beheer/") or request.path.startswith(f"/{settings.STATIC_URL}")):
                raise Http404("Platform host only serves the admin.")
        else:
            domain = Domain.objects.select_related("tenant").filter(domain=host, tenant__is_active=True).first()
            if domain is None:
                raise Http404("Unknown domain.")
            request.tenant = domain.tenant

        language = request.tenant.language if request.tenant else settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = language
        return self.get_response(request)


class TenantUserGuardMiddleware:
    """Logs out users whose account does not belong to the current tenant.

    Sessions are per host already; this is a second line of defence.
    Superusers (platform staff) may work on any host.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not user.is_superuser:
            tenant_id = request.tenant.pk if request.tenant else None
            if user.tenant_id != tenant_id:
                logout(request)
        return self.get_response(request)
