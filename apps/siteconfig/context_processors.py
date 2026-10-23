def site_settings(request):
    return {"site": getattr(request, "site_settings", None)}
