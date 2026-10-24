"""Admin pages for exporting and importing customers. The logic is in `transfer.py`.

Import is three steps: upload → check the report and choose per customer → import.
The uploaded file waits in the private folder (never in the website's media folder) and is
removed after the import or when it is cancelled; leftovers older than a day are cleaned up.
"""

import os
import secrets
import tempfile
import time
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import Customer
from .transfer import NEW, OVERWRITE, SKIP, ExportFile, ImportFileError, analyse, export_customers, run_import

SESSION_KEY = "customer_import"


def _upload_dir():
    path = Path(settings.PRIVATE_MEDIA_ROOT) / "imports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _clean_old_uploads():
    limit = time.time() - 24 * 3600
    for item in _upload_dir().iterdir():
        if item.is_file() and item.stat().st_mtime < limit:
            item.unlink(missing_ok=True)


def _upload_path(token):
    if not token or not token.isalnum():
        return None
    path = _upload_dir() / f"{token}.upload"
    return path if path.is_file() else None


def _context(request, **extra):
    return {**admin.site.each_context(request), "opts": Customer._meta, **extra}


def export_response(queryset, include_files):
    out = export_customers(queryset, include_files=include_files, out=tempfile.TemporaryFile())
    name = f"packdesk-customers-{timezone.localdate():%Y%m%d}.zip"
    return FileResponse(out, as_attachment=True, filename=name, content_type="application/zip")


class ExportForm(forms.Form):
    include_files = forms.BooleanField(
        label=gettext_lazy("Include files (invoice PDFs, fault attachments, logos)"), required=False, initial=True,
        help_text=gettext_lazy("With many invoices the file gets large. Without files the data and all relations "
                               "are still complete."),
    )


def export_view(request):
    if not request.user.has_perm("customers.export_customer"):
        raise PermissionDenied
    form = ExportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return export_response(Customer.objects.all(), form.cleaned_data["include_files"])
    return render(request, "admin/customers/export.html", _context(
        request, title=_("Export customers"), form=form, total=Customer.objects.count(),
    ))


class UploadForm(forms.Form):
    file = forms.FileField(label=gettext_lazy("Export file (.zip or .json)"))


def import_view(request):
    if not request.user.has_perm("customers.import_customer"):
        raise PermissionDenied
    step = request.POST.get("step", "")
    if request.method == "POST" and step == "upload":
        return _upload(request)
    if request.method == "POST" and step in ("run", "cancel"):
        return _run(request, cancel=step == "cancel")
    return render(request, "admin/customers/import_upload.html", _context(
        request, title=_("Import customers"), form=UploadForm(),
    ))


def _upload(request):
    form = UploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "admin/customers/import_upload.html", _context(request, title=_("Import customers"), form=form))
    _clean_old_uploads()
    token = secrets.token_hex(16)
    path = _upload_dir() / f"{token}.upload"
    with open(path, "wb") as f:
        for chunk in form.cleaned_data["file"].chunks():
            f.write(chunk)
    try:
        export = ExportFile(path)
    except ImportFileError as exc:
        path.unlink(missing_ok=True)
        form.add_error("file", str(exc))
        return render(request, "admin/customers/import_upload.html", _context(request, title=_("Import customers"), form=form))
    try:
        rows = analyse(export)
    finally:
        export.close()
    request.session[SESSION_KEY] = token
    return render(request, "admin/customers/import_review.html", _context(
        request, title=_("Check the import"), rows=rows, token=token,
        exported_at=export.data.get("exported_at"), includes_files=export.data.get("includes_files"),
        conflicts=sum(1 for r in rows if r["existing"]),
    ))


def _run(request, cancel):
    token = request.POST.get("token", "")
    if token != request.session.get(SESSION_KEY):
        messages.error(request, _("This import has expired. Upload the file again."))
        return redirect("admin:customers_customer_import")
    path = _upload_path(token)
    request.session.pop(SESSION_KEY, None)
    if path is None:
        messages.error(request, _("This import has expired. Upload the file again."))
        return redirect("admin:customers_customer_import")
    if cancel:
        os.remove(path)
        messages.info(request, _("Import cancelled; nothing was changed."))
        return redirect("admin:customers_customer_changelist")
    try:
        export = ExportFile(path)
        decisions = {}
        for index, block in enumerate(export.customers):
            choice = request.POST.get(f"choice-{index}", SKIP)
            decisions[index] = choice if choice in (SKIP, OVERWRITE, NEW) else SKIP
        results = run_import(export, decisions)
        names = [b.get("fields", {}).get("name", "?") for b in export.customers]
        export.close()
    finally:
        os.remove(path)
    rows = [{"name": name, **result} for name, result in zip(names, results)]
    done = sum(1 for r in rows if r["action"] != SKIP)
    messages.success(request, _("%(n)s customer(s) imported.") % {"n": done})
    return render(request, "admin/customers/import_done.html", _context(
        request, title=_("Import finished"), rows=rows,
        changelist=reverse("admin:customers_customer_changelist"),
    ))
