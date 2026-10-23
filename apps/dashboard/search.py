"""Global admin search (Ctrl/Cmd+K): searches every admin list the user may see, using its search fields."""

from django.contrib import admin
from django.urls import reverse
from unfold.dataclasses import SearchResult

ICONS = {
    "customers.customer": "storefront",
    "licences.licence": "verified",
    "accounts.user": "person",
    "licences.supportpack": "inventory_2",
}
MAX_PER_MODEL = 20


def search_everything(request, search_term):
    results = []
    for model, model_admin in admin.site._registry.items():
        if not model_admin.has_view_permission(request):
            continue
        if not model_admin.get_search_fields(request):
            continue
        qs, _dupes = model_admin.get_search_results(request, model_admin.get_queryset(request), search_term)
        label = model._meta.label_lower
        for obj in qs.distinct()[:MAX_PER_MODEL]:
            results.append(SearchResult(
                title=str(obj),
                description=f"{model._meta.app_config.verbose_name} · {str(model._meta.verbose_name).capitalize()}",
                link=reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_change", args=[obj.pk]),
                icon=ICONS.get(label, "data_object"),
            ))
    return results
