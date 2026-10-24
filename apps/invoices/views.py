from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.customers.models import customer_of

from . import services
from .models import Invoice


def _allowed(request, invoice):
    user = request.user
    if user.is_staff and user.has_perm("invoices.view_invoice"):
        return True
    customer = customer_of(user)
    return customer is not None and invoice.customer_id == customer.pk


@login_required
def pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if not _allowed(request, invoice):
        raise PermissionDenied
    if not invoice.has_pdf():
        raise Http404
    disposition = "attachment" if request.GET.get("download") else "inline"
    response = HttpResponse(invoice.pdf_bytes(), content_type="application/pdf")
    response["Content-Disposition"] = f'{disposition}; filename="{invoice.filename}"'
    return response


@login_required
def my_invoices(request):
    customer = customer_of(request.user)
    if customer is None:
        raise Http404
    invoices = customer.invoices.all()[:500]
    return render(request, "invoices/my_invoices.html", {"invoices": invoices})


@login_required
@require_POST
def send_to_me(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    customer = customer_of(request.user)
    if customer is None or invoice.customer_id != customer.pk:
        raise PermissionDenied
    services.send(invoice, request.user.email, by=request.user)
    messages.success(request, _("Invoice %(number)s has been sent to %(email)s.") % {"number": invoice.number,
                                                                                  "email": request.user.email})
    return redirect("my_invoices")
