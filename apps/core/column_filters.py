"""A filter button in the column headers of every admin list.

Clicking it shows the values the column can be filtered on (e.g. Password: Set / Must choose a new one),
the same choices as in the Filters panel. Filterable are columns with fixed choices, yes/no, dates, and links
to short lists (up to MAX_RELATED rows, e.g. role or category). Text columns are left to the search field.

A computed column gets a filter when its admin method has an ordering on a model field, or through
`column_filters = {"column": "field path" or ListFilter class}` on the ModelAdmin.
"""

import re

from django.contrib.admin import ModelAdmin, ShowFacets, SimpleListFilter
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils.html import json_script

MAX_RELATED = 100


def _model_field(model, path):
    if not isinstance(path, str) or path.startswith("-") or "__" in path:
        return None
    try:
        return model._meta.get_field(path)
    except FieldDoesNotExist:
        return None


def _filterable(field):
    if field is None:
        return False
    if field.is_relation:
        if not (field.many_to_one or field.many_to_many or field.one_to_one) or field.related_model is None:
            return False
        try:
            return field.related_model._default_manager.count() <= MAX_RELATED
        except Exception:  # e.g. table not there yet
            return False
    return bool(field.choices) or isinstance(field, (models.BooleanField, models.DateField))


def column_filter(model_admin, column):
    """The list_filter entry for a column (field path or filter class), or None."""
    explicit = getattr(model_admin, "column_filters", {}).get(column)
    if explicit:
        return explicit
    field = _model_field(model_admin.model, column)
    if field is None and not isinstance(column, str):
        return None
    if field is None:
        attr = getattr(model_admin, column, None) or getattr(model_admin.model, column, None)
        order = getattr(attr, "admin_order_field", None)
        field = _model_field(model_admin.model, order)
    return field.name if _filterable(field) else None


def _key(entry):
    if isinstance(entry, (list, tuple)):
        entry = entry[0]
    if isinstance(entry, str):
        return entry
    return getattr(entry, "parameter_name", None) or entry


def columns_with_filters(model_admin, request):
    return {c: f for c in model_admin.get_list_display(request) if isinstance(c, str)
            for f in [column_filter(model_admin, c)] if f}


_original_get_list_filter = ModelAdmin.get_list_filter


def get_list_filter(self, request):
    """The admin's own filters plus one for every filterable column."""
    filters = list(_original_get_list_filter(self, request))
    have = {_key(f) for f in filters}
    for entry in columns_with_filters(self, request).values():
        if _key(entry) not in have:
            filters.append(entry)
            have.add(_key(entry))
    return filters


def install():
    ModelAdmin.get_list_filter = get_list_filter
    # Every filter option shows how many rows it gives, taking the other active filters into account.
    ModelAdmin.show_facets = ShowFacets.ALWAYS


def header_data(cl, request):
    """JSON for the change list: {column: {"title", "choices": [{"label", "url", "selected"}]}}."""
    by_key = {getattr(spec, "field_path", None) or getattr(spec, "parameter_name", None): spec
              for spec in cl.filter_specs}
    data = {}
    for column, entry in columns_with_filters(cl.model_admin, request).items():
        spec = by_key.get(_key(entry))
        if spec is None:
            continue
        choices = []
        for c in spec.choices(cl):
            label = str(c["display"])
            count = re.search(r"\((\d+)\)$", label)
            choices.append({"label": label, "url": c["query_string"], "selected": bool(c.get("selected")),
                            "empty": bool(count) and count.group(1) == "0"})
        if len(choices) > 1:
            data[column] = {"title": str(spec.title), "choices": choices}
    return json_script(data, "pd-column-filters")


class ValueListFilter(SimpleListFilter):
    """Base for a filter on a computed column: subclasses give `options` = [(value, label, Q or callable)]."""

    options = []

    def lookups(self, request, model_admin):
        return [(value, label) for value, label, _q in self.options]

    def queryset(self, request, queryset):
        for value, _label, condition in self.options:
            if self.value() == value:
                return condition(queryset) if callable(condition) else queryset.filter(condition)
        return queryset
