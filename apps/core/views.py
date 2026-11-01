from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.siteconfig.models import SiteTheme, visible_for
from apps.siteconfig.themes import template


def home(request):
    blocks = visible_for(request.site_settings.home_blocks.all(), request.user)
    context = {"blocks": blocks}
    if request.site_settings.active_theme != SiteTheme.CLASSIC:
        context.update(_theme_home_context(request))
    return render(request, template(request, "core/home.html"), context)


def _theme_home_context(request):
    """What the home pages of the themes show besides the blocks."""
    from apps.customers.models import SignupSettings
    from apps.hardware import pricing
    from apps.hardware.models import Device, HardwareSettings

    settings = HardwareSettings.load()
    latest = []
    if settings.enabled and request.site_settings.active_theme == SiteTheme.WORKBENCH:
        customer = pricing.shop_customer(request)
        latest = list(Device.objects.filter(status=Device.Status.FOR_SALE)
                      .select_related("device_type", "brand", "condition").order_by("-created_at")[:3])
        for device in latest:
            device.shop_price = pricing.price(device, customer, settings)
    return {"hardware_enabled": settings.enabled, "latest_devices": latest,
            "incl_vat": pricing.show_incl_vat(request, settings), "signup_enabled": SignupSettings.load().enabled}


@login_required
def dashboard(request):
    from apps.parts.models import PartsSettings
    from apps.telephony.models import TelephonySettings

    return render(request, "core/dashboard.html", {"parts_enabled": PartsSettings.load().enabled,
                                                   "telephony_enabled": TelephonySettings.load().enabled})
