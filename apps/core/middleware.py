"""Two situations in which PackDesk shows a setup page instead of the site.

1. A new version has database changes that are not applied yet: every page shows the
   "Update database" page. It works without logging in (the user tables may be among the
   changes) and is protected by the installation code.
2. The installation is not finished: every page leads to the installation wizard.
"""

import logging

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _

from . import database_state, setup_code

log = logging.getLogger(__name__)

UPDATE_PATH = "/database-bijwerken/"
WIZARD_PATH = "/installatie/"


class DatabaseUpdateMiddleware:
    """Placed before everything that reads the database."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/static/") or not database_state.has_pending():
            return self.get_response(request)
        translation.activate(settings.LANGUAGE_CODE)
        error = ""
        if request.method == "POST" and request.path == UPDATE_PATH:
            if not request.POST.get("backup"):
                error = _("Confirm that a backup has been made.")
            elif not setup_code.check(request.POST.get("code")):
                error = _("The installation code is not correct.")
            else:
                try:
                    database_state.apply_changes()
                except Exception:
                    log.exception("Database update failed")
                    error = _("The update failed. The details are in the log (docker compose logs web).")
                else:
                    setup_code.forget()
                    return redirect("/beheer/")
        html = render_to_string("setup/update.html", {
            "pending": database_state.pending(), "error": error, "code_from_env": setup_code.from_env(),
            "update_path": UPDATE_PATH,
        })
        return HttpResponse(html, status=503)


class FirstRunMiddleware:
    """Runs after the site settings and authentication middleware."""

    ALLOWED = ("/static/", "/media/", "/taal/", WIZARD_PATH, "/beheer/login/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            settings.SETUP_WIZARD
            and not request.site_settings.setup_completed
            and not request.path.startswith(self.ALLOWED)
        ):
            return redirect(WIZARD_PATH)
        return self.get_response(request)
