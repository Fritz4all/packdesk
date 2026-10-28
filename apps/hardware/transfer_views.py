"""Admin pages for importing and exporting devices. The logic is in `transfer.py`.

Import is three steps: upload → check what will happen → import. The uploaded file waits in
DATA_ROOT/imports (never in the website folder) and is removed after the import or when it is cancelled.
"""

import secrets
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import transfer
from .models import Device

SESSION_KEY = "hardware_import"
TYPES = {"xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "csv": "text/csv; charset=utf-8"}


def _upload_dir():
    path = Path(settings.DATA_ROOT) / "imports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _context(request, **extra):
    return {**admin.site.each_context(request), "opts": Device._meta, **extra}


def _file(content, fmt, name):
    response = HttpResponse(content, content_type=TYPES[fmt])
    response["Content-Disposition"] = f'attachment; filename="{name}.{fmt}"'
    return response


def export_response(queryset, fmt):
    specs = transfer.specifications()
    rows = [transfer.device_row(d, specs) for d in queryset.select_related("device_type", "brand", "condition")]
    return _file(transfer.write(rows, fmt, specs), fmt, f"packdesk-hardware-{timezone.localdate():%Y%m%d}")


class ExportView:
    """All devices in the list as it is filtered and searched on the page."""

    def __init__(self, model_admin):
        self.model_admin = model_admin

    def __call__(self, request):
        if not self.model_admin.has_view_permission(request):
            raise PermissionDenied
        fmt = "csv" if request.GET.get("format") == "csv" else "xlsx"
        request.GET = request.GET.copy()
        request.GET.pop("format", None)
        changelist = self.model_admin.get_changelist_instance(request)
        return export_response(changelist.get_queryset(request), fmt)


def example_view(request):
    if not request.user.has_perm("hardware.view_device"):
        raise PermissionDenied
    fmt = "csv" if request.GET.get("format") == "csv" else "xlsx"
    specs = transfer.specifications()
    content = transfer.write(transfer.example_rows(specs), fmt, specs, with_explanation=True)
    return _file(content, fmt, "packdesk-hardware-example")


class UploadForm(forms.Form):
    file = forms.FileField(label=gettext_lazy("Excel or CSV file"))
    update_existing = forms.BooleanField(
        label=gettext_lazy("Also update devices that already exist (same serial number)"), required=False,
        initial=True,
    )


def import_view(request):
    if not (request.user.has_perm("hardware.add_device") and request.user.has_perm("hardware.change_device")):
        raise PermissionDenied
    step = request.POST.get("step", "")
    if request.method == "POST" and step == "upload":
        return _upload(request)
    if request.method == "POST" and step in ("run", "cancel"):
        return _run(request, cancel=step == "cancel")
    return render(request, "admin/hardware/import_upload.html", _context(
        request, title=_("Import devices"), form=UploadForm(),
    ))


def _upload(request):
    form = UploadForm(request.POST, request.FILES)
    page = "admin/hardware/import_upload.html"
    if not form.is_valid():
        return render(request, page, _context(request, title=_("Import devices"), form=form))
    upload = form.cleaned_data["file"]
    data = upload.read()
    try:
        rows = transfer.read_rows(upload.name, data)
    except transfer.ImportFileError as exc:
        form.add_error("file", str(exc))
        return render(request, page, _context(request, title=_("Import devices"), form=form))
    token = secrets.token_hex(16)
    suffix = ".xlsx" if upload.name.lower().endswith(".xlsx") else ".csv"
    (_upload_dir() / f"hardware-{token}{suffix}").write_bytes(data)
    request.session[SESSION_KEY] = {"token": token, "suffix": suffix,
                                    "update": form.cleaned_data["update_existing"]}
    outcome = transfer.analyse(rows)
    counts = {action: sum(1 for r in outcome if r["action"] == action)
              for action in (transfer.NEW, transfer.UPDATE, transfer.SAME, transfer.ERROR)}
    return render(request, "admin/hardware/import_review.html", _context(
        request, title=_("Check the import"), rows=outcome, counts=counts, token=token,
        update_existing=form.cleaned_data["update_existing"],
    ))


def _run(request, cancel):
    saved = request.session.pop(SESSION_KEY, None) or {}
    token = request.POST.get("token", "")
    path = _upload_dir() / f"hardware-{token}{saved.get('suffix', '')}"
    if not token.isalnum() or token != saved.get("token") or not path.is_file():
        messages.error(request, _("This import has expired. Upload the file again."))
        return redirect("admin:hardware_device_import")
    try:
        if cancel:
            messages.info(request, _("Import cancelled; nothing was changed."))
            return redirect("admin:hardware_device_changelist")
        rows = transfer.read_rows(path.name, path.read_bytes())
        added, updated, skipped = transfer.run_import(rows, update_existing=saved.get("update", True))
    finally:
        path.unlink(missing_ok=True)
    messages.success(request, _("Import done: %(added)s added, %(updated)s updated, %(skipped)s skipped.")
                     % {"added": added, "updated": updated, "skipped": skipped})
    return redirect("admin:hardware_device_changelist")
