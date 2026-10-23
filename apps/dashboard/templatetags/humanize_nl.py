from decimal import Decimal

from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def money(value):
    """Amount with two decimals and thousands separators in the active language (1.234,50 in Dutch)."""
    if value in (None, ""):
        return "–"
    return number_format(Decimal(value).quantize(Decimal("0.01")), 2, use_l10n=True, force_grouping=True)
