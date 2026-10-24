"""Admin pages for importing the previous webshop: start a trial or a real import, follow it, download the report."""

import threading
from pathlib import Path

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from .models import ExternalDatabase, ImportRun
from .old_shop.importer import progress_path, run_import


def _allowed(request):
    if not request.user.has_perm("legacy.import_data"):
        raise PermissionDenied


def _in_background(run_pk):
    close_old_connections()
    try:
        run_import(ImportRun.objects.get(pk=run_pk))
    finally:
        connection.close()


@staff_member_required
def start(request, pk):
    _allowed(request)
    db = get_object_or_404(ExternalDatabase, pk=pk)
    if request.method == "POST":
        if ImportRun.objects.filter(database=db, status=ImportRun.Status.RUNNING).exists():
            messages.error(request, _("An import of this database is still running."))
            return redirect("legacy_import", db.pk)
        apply = request.POST.get("mode") == "apply"
        if apply and not request.POST.get("confirm"):
            messages.error(request, _("Tick that you have made a backup before importing."))
            return redirect("legacy_import", db.pk)
        run = ImportRun.objects.create(database=db, dry_run=not apply, started_by=request.user)
        threading.Thread(target=_in_background, args=(run.pk,), daemon=True).start()
        return redirect("admin:legacy_importrun_change", run.pk)
    return render(request, "legacy/import_start.html", {
        **admin.site.each_context(request), "title": _("Import from %(name)s") % {"name": db.name}, "db": db,
        "runs": db.imports.all()[:10], "mapped": db.mappings.count(),
    })


@staff_member_required
def report(request, pk):
    _allowed(request)
    run = get_object_or_404(ImportRun, pk=pk)
    reports = (Path(settings.DATA_ROOT) / "imports" / "reports").resolve()
    path = (Path(settings.DATA_ROOT) / run.report_file).resolve()
    if not run.report_file or reports not in path.parents or not path.is_file():
        raise Http404
    return FileResponse(open(path, "rb"), as_attachment=True, filename=f"import-{run.pk}.csv",
                        content_type="text/csv; charset=utf-8")


def progress_text(run):
    path = progress_path(run)
    return path.read_text() if run.status == ImportRun.Status.RUNNING and path.is_file() else ""


def report_url(run):
    return reverse("legacy_import_report", args=[run.pk]) if run.report_file else ""
