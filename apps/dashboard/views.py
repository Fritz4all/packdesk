import json

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_POST

from .models import DashboardLayout
from .widgets import DEFAULT_ORDER, available


def saved_layout(user):
    return DashboardLayout.objects.filter(user=user).first()


def layout_for(user):
    """Visible widgets in the user's order, plus the hidden ones (for the 'customise' panel)."""
    widgets = available(user)
    saved = DashboardLayout.objects.filter(user=user).first()
    order = list(saved.order) if saved else []
    hidden = set(saved.hidden) if saved else set()
    keys = [k for k in order if k in widgets] + [k for k in DEFAULT_ORDER if k in widgets and k not in order]
    return [widgets[k] for k in keys if k not in hidden], [widgets[k] for k in keys if k in hidden]


def dashboard_context(request):
    from .navigation import SECTIONS, ordered_keys

    visible, hidden = layout_for(request.user)
    saved = saved_layout(request.user)
    hidden_items = set(saved.hidden_items) if saved else set()
    blocks, hidden_parts = [], []
    for widget in visible:
        data = widget.build(request)
        if "cards" in data:
            for card in data["cards"]:
                card["item_key"] = f"{widget.key}:{card['key']}"
            hidden_parts += [c for c in data["cards"] if c["item_key"] in hidden_items]
            data["cards"] = [c for c in data["cards"] if c["item_key"] not in hidden_items]
        blocks.append({"widget": widget, "data": data})
    titles = {s["key"]: s["title"] for s in SECTIONS}
    return {
        "dashboard_blocks": blocks, "dashboard_hidden": hidden, "dashboard_hidden_items": hidden_parts,
        "sidebar_sections": [(k, titles[k]) for k in ordered_keys(request.user)],
    }


@staff_member_required
@require_POST
def save_layout(request):
    try:
        data = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    from .navigation import SECTIONS

    allowed = set(available(request.user))
    layout, _created = DashboardLayout.objects.get_or_create(user=request.user)
    if "order" in data:
        layout.order = [k for k in data["order"] if k in allowed]
    if "hidden" in data:
        layout.hidden = [k for k in data["hidden"] if k in allowed]
    if "hidden_items" in data:
        layout.hidden_items = [k for k in data["hidden_items"] if isinstance(k, str) and k.split(":")[0] in allowed]
    if "sidebar" in data:
        known = {s["key"] for s in SECTIONS}
        layout.sidebar_order = [k for k in data["sidebar"] if k in known]
    layout.save()
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
