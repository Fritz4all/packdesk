import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_POST

from .models import DashboardLayout
from .widgets import DEFAULT_ORDER, available


def layout_for(user):
    """Visible widgets in the user's order, plus the hidden ones (for the 'customise' panel)."""
    widgets = available(user)
    saved = DashboardLayout.objects.filter(user=user).first()
    order = list(saved.order) if saved else []
    hidden = set(saved.hidden) if saved else set()
    keys = [k for k in order if k in widgets] + [k for k in DEFAULT_ORDER if k in widgets and k not in order]
    return [widgets[k] for k in keys if k not in hidden], [widgets[k] for k in keys if k in hidden]


def dashboard_context(request):
    visible, hidden = layout_for(request.user)
    blocks = [{"widget": w, "data": w.build(request)} for w in visible]
    return {"dashboard_blocks": blocks, "dashboard_hidden": hidden}


@staff_member_required
@require_POST
def save_layout(request):
    try:
        data = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    allowed = set(available(request.user))
    order = [k for k in data.get("order", []) if k in allowed]
    hidden = [k for k in data.get("hidden", []) if k in allowed]
    DashboardLayout.objects.update_or_create(user=request.user, defaults={"order": order, "hidden": hidden})
    return JsonResponse({"ok": True})


@staff_member_required
@require_POST
def reset_layout(request):
    DashboardLayout.objects.filter(user=request.user).delete()
    return JsonResponse({"ok": True})


def dashboard_callback(request, context):
    """Hooked into unfold (UNFOLD["DASHBOARD_CALLBACK"]) to fill the admin home page."""
    context.update(dashboard_context(request))
    return context
