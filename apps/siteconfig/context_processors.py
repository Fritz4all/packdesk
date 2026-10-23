from .models import visible_for


def site_settings(request):
    site = getattr(request, "site_settings", None)
    if site is None:
        return {"site": None}
    user = request.user if hasattr(request, "user") else None
    return {
        "site": site,
        "menu_items": visible_for(site.menu_items.all(), user) if user else [],
    }
