from .models import FaultReport


def new_reports(request):
    if not request.user.has_perm("faults.view_faultreport"):
        return ""
    count = FaultReport.objects.filter(status=FaultReport.Status.NEW).count()
    return str(count) if count else ""
