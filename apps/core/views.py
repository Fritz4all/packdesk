from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.siteconfig.models import visible_for


def home(request):
    blocks = visible_for(request.site_settings.home_blocks.all(), request.user)
    return render(request, "core/home.html", {"blocks": blocks})


@login_required
def dashboard(request):
    from apps.parts.models import PartsSettings
    from apps.telephony.models import TelephonySettings

    return render(request, "core/dashboard.html", {"parts_enabled": PartsSettings.load().enabled,
                                                   "telephony_enabled": TelephonySettings.load().enabled})
