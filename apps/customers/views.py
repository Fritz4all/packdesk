from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from . import emails
from .forms import ContactDetailsForm, SignupForm
from .models import Customer, CustomerAddress, SignupSettings


def signup(request):
    settings = SignupSettings.load()
    if not settings.enabled:
        raise Http404
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST or None, settings=settings)
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        if customer.status == Customer.Status.PENDING:
            emails.notify_new_signup(customer, request)
        return redirect("signup_done")
    def group(*names):
        return [form[name] for name in names if name in form.fields]

    return render(request, "customers/signup.html", {
        "form": form,
        "signup": settings,
        "company_fields": group("company", "phone", "vat_number", "coc_number", "website"),
        "address_fields": group("line1", "line2", "postal_code", "city", "country"),
        "contact_fields": group("salutation", "initials", "first_name", "last_name", "function", "department",
                                "contact_phone", "email", "password1", "password2"),
        "message_fields": group("message"),
    })


def signup_done(request):
    return render(request, "customers/signup_done.html", {"signup": SignupSettings.load()})


@login_required
def my_details(request):
    contact = getattr(request.user, "contact", None)
    if contact is None:
        raise Http404
    form = ContactDetailsForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        request.user.first_name = contact.first_name or contact.initials
        request.user.last_name = contact.last_name
        request.user.save(update_fields=["first_name", "last_name"])
        messages.success(request, _("Your details have been saved."))
        return redirect("my_details")
    customer = contact.customer
    addresses = [(kind.label, customer.address(kind.value)) for kind in CustomerAddress.Kind]
    return render(request, "customers/my_details.html", {"form": form, "customer": customer, "addresses": addresses})
