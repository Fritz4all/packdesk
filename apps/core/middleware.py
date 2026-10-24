"""Situations in which PackDesk shows a setup page instead of the site.

1. No usable database yet: the database step (database server, create the database if needed).
2. A new version has database changes that are not applied yet: the "Update database" page. It
   works without logging in (the user tables may be among the changes). A new, empty database gets
   its tables right away instead.
3. The installation is not finished: every page leads to the installation wizard.
Steps 1 and 2 are protected by the installation code.
"""

import logging
import re

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext as _

from . import database_state, server_setup, setup_code

log = logging.getLogger(__name__)

SERVER_PATH = "/installatie/database/"
UPDATE_PATH = "/database-bijwerken/"
NAME = re.compile(r"^[A-Za-z0-9_]{1,63}$")


class ServerSetupMiddleware:
    """First in the chain: nothing after it can work without a database."""

    working = False  # once the database works, this process stops checking

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if ServerSetupMiddleware.working or request.path.startswith("/static/"):
            return self.get_response(request)
        state, detail = server_setup.diagnose()
        if state == server_setup.OK:
            ServerSetupMiddleware.working = True
            return self.get_response(request)
        translation.activate(settings.LANGUAGE_CODE)
        current = server_setup.current_target()
        context = {"state": state, "detail": detail, "problem": server_setup.message(state), "target": current,
                   "fixed": {k for k in ("DB_ENGINE", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
                             if k in settings.FIXED_SETTINGS},
                   "code_from_env": setup_code.from_env(), "path": SERVER_PATH, "values": {}}
        if request.method == "POST" and request.path == SERVER_PATH:
            done = self._post(request, current, context)
            if done:
                return HttpResponse(render_to_string("setup/restarting.html", {}), status=503)
        return HttpResponse(render_to_string("setup/database.html", context), status=503)

    def _post(self, request, current, context):
        post, fixed = request.POST, context["fixed"]
        context["values"] = {k: post.get(k, "") for k in ("engine", "host", "port", "name", "user", "admin_user")}

        def value(key, field, default):
            return default if key in fixed else post.get(field, "").strip()

        port = value("DB_PORT", "port", str(current.port or ""))
        target = server_setup.Target(
            engine=value("DB_ENGINE", "engine", current.engine),
            host=value("DB_HOST", "host", current.host),
            port=int(port) if port.isdigit() else None,
            name=value("DB_NAME", "name", current.name), user=value("DB_USER", "user", current.user),
            password=current.password if "DB_PASSWORD" in fixed else post.get("password", ""),
        )
        if not setup_code.check(post.get("code")):
            context["error"] = _("The installation code is not correct.")
        elif target.engine not in ("mariadb", "postgres") or not target.host:
            context["error"] = _("Choose the type of database and fill in the server.")
        elif not NAME.match(target.name) or not NAME.match(target.user):
            context["error"] = _("Database name and user: letters, digits and _ only.")
        elif not target.password:
            context["error"] = _("Fill in a password for PackDesk's database user.")
        else:
            problem = server_setup.test(target)
            if problem and problem[0] in (server_setup.NO_DATABASE, server_setup.BAD_LOGIN) and post.get("create"):
                try:
                    server_setup.create(target, post.get("admin_user", "").strip(), post.get("admin_password", ""))
                except Exception as exc:
                    context["error"] = _("Creating the database did not work: %(error)s") % {"error": exc}
                    return False
                problem = server_setup.test(target)
            if problem:
                context["error"] = server_setup.message(problem[0]) or problem[1]
                context["detail"] = problem[1]
                context["offer_create"] = problem[0] in (server_setup.NO_DATABASE, server_setup.BAD_LOGIN)
                return False
            server_setup.save(target)
            server_setup.restart_soon()
            return True
        return False


WIZARD_PATH = "/installatie/"


class DatabaseUpdateMiddleware:
    """Placed before everything that reads the database."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/static/") or not database_state.has_pending():
            return self.get_response(request)
        if database_state.is_empty():
            # A new, empty database: nothing can be lost, so create the tables right away.
            database_state.apply_changes()
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
