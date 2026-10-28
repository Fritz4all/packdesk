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
    names; a main menu inside another one appears among that one's items with "items" of its own."""
    from .navigation import SECTIONS, _standard_title, item_key, menu

    languages = [code for code, _name in settings.LANGUAGES]
    standard_items = {item_key(i): i["title"] for s in SECTIONS for i in s["items"]}
    saved_sections = {s["key"]: s.get("title") or {} for s in layout.get("sections") or []}
    saved_items = layout.get("items") or {}
    builtin = {s["key"] for s in SECTIONS}

    def per_language(text):
        result = {}
        for lang in languages:
            with translation.override(lang):
                result[lang] = str(text)
        return result

    def section(key, items):
        saved = saved_sections.get(key, {})
        standard = per_language(_standard_title(key))
        if key not in builtin and saved:  # own menu: the name given in another language as example
            standard = {lang: next(iter(saved.values())) for lang in languages}
        return {"key": key, "custom": key not in builtin, "standard": standard, "title": saved,
                "items": [entry(i) for i in items]}

    def entry(item):
        if "group" in item:
            return section(item["group"], item["items"])
        key = item_key(item)
        return {"key": key, "icon": item.get("icon", ""), "standard": per_language(standard_items[key]),
                "title": saved_items.get(key, {})}

    sections = [section(s["key"], s["items"]) for s in menu(layout)]
    # Main menus emptied out completely (not shown in the sidebar) stay on the page, so items can go back there.
    shown = {s["key"] for s in sections} | {i["key"] for s in sections for i in s["items"] if "items" in i}
    for key in [s["key"] for s in layout.get("sections") or []] + [s["key"] for s in SECTIONS]:
        if key not in shown and (key in builtin or key in saved_sections):
            sections.append(section(key, []))
            shown.add(key)
    return sections


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
