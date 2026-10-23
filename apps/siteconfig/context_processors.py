from .models import visible_for


def site_settings(request):
    # Named `site_settings`, not `site`: Django's auth views put their own
    # `site` (the host name) in the context, which would hide ours.
    site = getattr(request, "site_settings", None)
    if site is None:
        return {"site_settings": None}
    user = request.user if hasattr(request, "user") else None
    return {
        "site_settings": site,
        "menu_items": visible_for(site.menu_items.all(), user) if user else [],
    }
