from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.customers.models import customer_of
from apps.numbering.models import NumberSequence

from . import emails
from .forms import FaultReportForm
from .lookup import find_cover, is_covered, prefill_from
from .models import FaultAttachment, FaultReport, FaultSettings


def _check_files(files, rules):
    if len(files) > rules.max_attachments:
        return _("At most %(n)s attachments.") % {"n": rules.max_attachments}
    if sum(f.size for f in files) > rules.max_attachment_mb * 1024 * 1024:
        return _("The attachments together may be at most %(n)s MB.") % {"n": rules.max_attachment_mb}
    return None


def _render(request, form, rules, **extra):
    context = {
        "form": form, "rules": rules, "lookup_fields": form.group("lookup"),
        "device_fields": form.group("vendor", "device", "serial_nr", "operating_system", "repair_option", "reference"),
        "fault_fields": form.group("description"),
        "reseller_fields": form.group("reseller_name", "reseller_address", "reseller_postal_code", "reseller_city",
                                      "reseller_phone", "reseller_email"),
        "location_fields": form.group("location_name", "location_contact", "location_address", "location_postal_code",
                                      "location_city", "location_country", "location_phone", "location_email"),
        **extra,
    }
    return render(request, "faults/report.html", context)


def report(request):
    rules = FaultSettings.load()
    if not rules.enabled:
        raise Http404
    customer = customer_of(request.user)
    initial = {}
    if customer:
        main = customer.address("main")
        initial = {"reseller_name": customer.name, "reseller_phone": customer.phone, "reseller_email": customer.email,
                   "reseller_address": main.line1 if main else "", "reseller_postal_code": main.postal_code if main else "",
                   "reseller_city": main.city if main else ""}
    cover = None
    if request.method == "POST" and request.POST.get("action") == "lookup":
        licence, option, covered_until = find_cover(request.POST.get("lookup"))
        data = request.POST.copy()
        if licence:
            for key, value in prefill_from(licence, option).items():
                if not data.get(key):
                    data[key] = value
        cover = {"searched": request.POST.get("lookup", ""), "found": bool(licence), "until": covered_until,
                 "covered": is_covered(covered_until), "licence": licence}
        form = FaultReportForm(initial=data.dict())
        return _render(request, form, rules, cover=cover)

    form = FaultReportForm(request.POST or None, initial=initial)
    file_error = None
    if request.method == "POST":
        files = request.FILES.getlist("attachments")
        file_error = _check_files(files, rules)
        if form.is_valid() and not file_error:
            licence, _option, covered_until = find_cover(form.cleaned_data.get("lookup") or form.cleaned_data["serial_nr"])
            with transaction.atomic():
                fault = form.save(commit=False)
                _n, fault.number = NumberSequence.issue("ticket")
                fault.licence = licence
                fault.covered_until = covered_until
                fault.customer = customer or (licence.customer if licence else None)
                fault.reported_by = request.user if request.user.is_authenticated else None
                fault.save()
                for f in files:
                    FaultAttachment.objects.create(report=fault, file=f, name=f.name[:200], size=f.size)
            emails.send_report(fault)
            emails.send_confirmation(fault)
            request.session["fault_report"] = fault.pk
            return redirect("fault_done")
    return _render(request, form, rules, cover=cover, file_error=file_error)


def done(request):
    fault = FaultReport.objects.filter(pk=request.session.get("fault_report")).first()
    if fault is None:
        return redirect("fault_report")
    return render(request, "faults/done.html", {"fault": fault, "rules": FaultSettings.load()})


@login_required
def my_reports(request):
    customer = customer_of(request.user)
    if customer is None:
        raise Http404
    reports = customer.fault_reports.all()[:100]
    return render(request, "faults/my_reports.html", {"reports": reports, "today": timezone.localdate()})


@staff_member_required
def attachment(request, pk):
    if not request.user.has_perm("faults.view_faultreport"):
        raise PermissionDenied
    item = get_object_or_404(FaultAttachment, pk=pk)
    return FileResponse(item.file.open("rb"), as_attachment=True, filename=item.name)
