from apps.siteconfig.models import SiteSettings


def environment_badge(request):
    """Shows the installation's name in the admin header."""
    site = getattr(request, "site_settings", None) or SiteSettings.load()
    return [site.name, "info"]
