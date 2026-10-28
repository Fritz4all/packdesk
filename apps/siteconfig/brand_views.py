"""The PackDesk icon in the colour of the settings: /brand/icon.svg, /brand/icon-<size>.png and /favicon.ico.
An uploaded favicon wins: /favicon.ico then sends that one."""

from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.views.decorators.cache import cache_control

from . import brand
from .models import SiteSettings

CACHE = 60 * 60 * 24  # the addresses carry the colour (?c=…), so a new colour is a new address


@cache_control(public=True, max_age=CACHE)
def icon_svg(request):
    small = request.GET.get("size") == "small"
    return HttpResponse(brand.svg(brand.color(SiteSettings.load()), small=small), content_type="image/svg+xml")


@cache_control(public=True, max_age=CACHE)
def icon_png(request, size):
    if size not in brand.PNG_SIZES:
        raise Http404
    return HttpResponse(brand.png(brand.color(SiteSettings.load()), size), content_type="image/png")


@cache_control(public=True, max_age=CACHE)
def favicon(request):
    site = SiteSettings.load()
    if site.favicon:
        return HttpResponseRedirect(site.favicon.url)
    return HttpResponse(brand.ico(brand.color(site)), content_type="image/x-icon")


def icon_url(request=None, size=None):
    """Address of the icon for templates and the admin: the uploaded favicon, else the built-in one."""
    from django.urls import reverse

    site = SiteSettings.load()
    if site.favicon:
        return site.favicon.url
    version = brand.color(site).lstrip("#")
    if size:
        return f"{reverse('brand_icon_png', args=[size])}?c={version}"
    return f"{reverse('brand_icon_svg')}?c={version}"
