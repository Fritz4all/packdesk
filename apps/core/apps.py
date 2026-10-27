from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    name = "apps.core"

    def ready(self):
        from . import column_filters

        column_filters.install()
        if settings.DEBUG and not settings.TECHNICAL_404:
            # Development: an unknown address shows PackDesk's own 404 page, as on a server, instead of
            # Django's technical page listing every address (TECHNICAL_404=1 brings that back).
            from django.views import debug
            from django.views.defaults import page_not_found

            debug.technical_404_response = page_not_found
