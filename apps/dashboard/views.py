import json

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils import translation
from django.utils.translation import gettext, gettext_lazy
from django.views.decorators.http import require_POST

from .models import AdminMenu, DashboardLayout
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
    from .navigation import sidebar

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
    return {
        "dashboard_blocks": blocks, "dashboard_hidden": hidden, "dashboard_hidden_items": hidden_parts,
        "sidebar_sections": [(s["key"], s["title"]) for s in sidebar(request)],
    }


@staff_member_required
@require_POST
def save_layout(request):
    try:
        data = json.loads(request.body)
    except ValueError:
        return HttpResponseBadRequest()
    from .navigation import menu

    allowed = set(available(request.user))
    layout, _created = DashboardLayout.objects.get_or_create(user=request.user)
    if "order" in data:
        layout.order = [k for k in data["order"] if k in allowed]
    if "hidden" in data:
        layout.hidden = [k for k in data["hidden"] if k in allowed]
    if "hidden_items" in data:
        layout.hidden_items = [k for k in data["hidden_items"] if isinstance(k, str) and k.split(":")[0] in allowed]
    if "sidebar" in data:
        known = {s["key"] for s in menu()}
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


def _menu_editor_data(layout):
    """The menu as the menu page shows it: per main menu and item the standard name per language and the saved
    names."""

    from .navigation import SECTIONS, item_key, menu

    languages = [code for code, _name in settings.LANGUAGES]
    standard_sections = {s["key"]: s["title"] for s in SECTIONS}
    standard_items = {item_key(i): i["title"] for s in SECTIONS for i in s["items"]}

    def per_language(text):
        result = {}
        for lang in languages:
            with translation.override(lang):
                result[lang] = str(text)
        return result

    saved_sections = {s["key"]: s.get("title") or {} for s in layout.get("sections") or []}
    saved_items = layout.get("items") or {}
    return [
        {
            "key": section["key"], "custom": section["custom"],
            "standard": per_language(standard_sections.get(section["key"], gettext_lazy("New menu"))),
            "title": saved_sections.get(section["key"], {}),
            "items": [
                {"key": item_key(item), "icon": item.get("icon", ""), "standard": per_language(standard_items[item_key(item)]),
                 "title": saved_items.get(item_key(item), {})}
                for item in section["items"]
            ],
        }
        for section in menu(layout)
    ]


@staff_member_required
def menu_editor(request):
    """Configuration → Menu: the admin menu for everyone. Main menus and items can be dragged to another place
    (items also to another main menu), renamed per language, and extra main menus can be added."""
    from .navigation import clean_layout

    if not request.user.has_perm("siteconfig.view_sitesettings"):
        raise PermissionDenied
    can_change = request.user.has_perm("siteconfig.change_sitesettings")
    saved = AdminMenu.load()
    if request.method == "POST":
        if not can_change:
            raise PermissionDenied
        if request.POST.get("reset"):
            saved.layout = {}
            messages.success(request, gettext("The menu has been set back to the standard."))
        else:
            try:
                saved.layout = clean_layout(json.loads(request.POST.get("layout") or "{}"))
            except (ValueError, AttributeError, TypeError):
                return HttpResponseBadRequest()
            messages.success(request, gettext("The menu has been saved."))
        saved.save()
        return redirect("admin_menu")
    own = bool(DashboardLayout.objects.filter(user=request.user).values_list("sidebar_order", flat=True).first())
    return TemplateResponse(request, "admin/packdesk/menu_editor.html", {
        **admin.site.each_context(request), "title": gettext("Menu"),
        "menu_data": _menu_editor_data(saved.layout), "languages": settings.LANGUAGES,
        "language": (request.LANGUAGE_CODE or "")[:2], "can_change": can_change, "own_order": own,
    })


@staff_member_required
@require_POST
def reset_own_menu_order(request):
    DashboardLayout.objects.filter(user=request.user).update(sidebar_order=[])
    return redirect("admin_menu")
