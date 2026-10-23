from django.conf import settings
from django.utils.translation import gettext as _


def environment_badge(request):
    """Shows in the admin header which organisation (or the platform) you are managing."""
    if getattr(request, "tenant", None):
        return [request.tenant.name, "info"]
    if settings.DEBUG:
        return [_("Platform (development)"), "warning"]
    return [_("Platform"), "danger"]
