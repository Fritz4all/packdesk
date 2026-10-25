from django import template

from apps.core.column_filters import header_data

register = template.Library()


@register.simple_tag(takes_context=True)
def column_filter_data(context, cl):
    return header_data(cl, context["request"])
