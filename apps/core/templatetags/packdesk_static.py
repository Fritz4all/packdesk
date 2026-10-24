"""{% vstatic 'css/packdesk.css' %}: static URL with the file's change time, so browsers fetch a new copy."""

from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def vstatic(path):
    try:
        return f"{static(path)}?v={int((settings.BASE_DIR / 'static' / path).stat().st_mtime)}"
    except OSError:
        return static(path)
