"""Website themes: a theme is a stylesheet (static/css/themes/<theme>.css) on top of packdesk.css, for every page,
plus its own templates (templates/themes/<theme>/...) for pages laid out differently. Other pages use the normal
template and follow through the stylesheet.
"""

from .models import SiteTheme


def template(request, name):
    """The template for a page in the theme of the website: the theme's own version when it has one."""
    theme = request.site_settings.site_theme
    return name if theme == SiteTheme.CLASSIC else [f"themes/{theme}/{name}", name]
