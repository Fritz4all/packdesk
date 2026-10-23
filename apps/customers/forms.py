import time

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User

from .models import Contact, Country, Customer, CustomerAddress, FieldMode

# Form fields whose visibility is configurable, mapped to SignupSettings.field_<name>.
CONFIGURABLE = {
    "phone": "phone",
    "vat_number": "vat_number",
    "coc_number": "coc_number",
    "website": "website",
    "salutation": "salutation",
    "function": "function",
    "department": "department",
    "contact_phone": "contact_phone",
    "line2": "address_line2",
    "message": "message",
}
MIN_SECONDS = 3  # filled in faster than this = a bot


class SignupForm(forms.Form):
    # Company
    company = forms.CharField(label=_("Company name"), max_length=120)
    phone = forms.CharField(label=_("Phone"), max_length=40)
    vat_number = forms.CharField(label=_("VAT number"), max_length=32)
    coc_number = forms.CharField(label=_("Chamber of Commerce number"), max_length=32)
    website = forms.URLField(label=_("Website"), assume_scheme="https")
    # Address
    line1 = forms.CharField(label=_("Address"), max_length=200)
    line2 = forms.CharField(label=_("Address line 2"), max_length=200)
    postal_code = forms.CharField(label=_("Postal code"), max_length=20)
    city = forms.CharField(label=_("City"), max_length=100)
    country = forms.ModelChoiceField(label=_("Country"), queryset=Country.objects.filter(is_active=True), empty_label=None)
    # Contact
    salutation = forms.ChoiceField(label=_("Salutation"), choices=Contact.Salutation.choices)
    initials = forms.CharField(label=_("Initials"), max_length=16, required=False)
    first_name = forms.CharField(label=_("First name"), max_length=60, required=False)
    last_name = forms.CharField(label=_("Last name"), max_length=80)
    function = forms.CharField(label=_("Job title"), max_length=100)
    department = forms.CharField(label=_("Department"), max_length=100)
    contact_phone = forms.CharField(label=_("Direct phone"), max_length=40)
    email = forms.EmailField(label=_("Email address"), help_text=_("This is also your login."))
    password1 = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label=_("Repeat password"), widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    message = forms.CharField(label=_("Message"), widget=forms.Textarea(attrs={"rows": 3}))
    # Bot protection: a field people do not see, and a signed start time.
    homepage = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))
    started = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, settings, **kwargs):
        super().__init__(*args, **kwargs)
        self.signup_settings = settings
        for field, setting in CONFIGURABLE.items():
            mode = settings.mode(setting)
            if mode == FieldMode.HIDDEN:
                del self.fields[field]
            else:
                self.fields[field].required = mode == FieldMode.REQUIRED
        if not self.is_bound:
            self.initial["started"] = signing.dumps(time.time())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("There is already an account with this email address."))
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("homepage"):
            raise forms.ValidationError(_("The form could not be sent."))
        try:
            started = signing.loads(self.data.get("started", ""), max_age=86400)
        except signing.BadSignature:
            raise forms.ValidationError(_("The form has expired. Please try again."))
        if time.time() - started < MIN_SECONDS:
            raise forms.ValidationError(_("The form could not be sent."))
        country = cleaned.get("country")
        if country and country.vat_number_required and not cleaned.get("vat_number"):
            self.add_error("vat_number", _("A VAT number is required for customers in %(country)s.") % {"country": country})
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("The passwords do not match."))
        elif p1:
            try:
                validate_password(p1, User(email=cleaned.get("email", ""), last_name=cleaned.get("last_name", "")))
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    @transaction.atomic
    def save(self):
        settings, data = self.signup_settings, self.cleaned_data
        approval = settings.require_approval
        customer = Customer.objects.create(
            name=data["company"],
            customer_type=settings.customer_type,
            status=Customer.Status.PENDING if approval else Customer.Status.ACTIVE,
            phone=data.get("phone", ""),
            email=data["email"],
            vat_number=data.get("vat_number", ""),
            coc_number=data.get("coc_number", ""),
            website=data.get("website", ""),
            margin_packs=settings.default_margin_packs,
            margin_parts=settings.default_margin_parts,
            signup_message=data.get("message", ""),
        )
        CustomerAddress.objects.create(
            customer=customer, kind=CustomerAddress.Kind.MAIN, line1=data["line1"], line2=data.get("line2", ""),
            postal_code=data["postal_code"], city=data["city"], country=data["country"],
        )
        user = User(email=data["email"], first_name=data.get("first_name") or data.get("initials", ""),
                    last_name=data["last_name"], kind=User.Kind.CUSTOMER, is_active=not approval)
        user.set_password(data["password1"])
        user.save()
        Contact.objects.create(
            customer=customer, user=user, salutation=data.get("salutation", ""), initials=data.get("initials", ""),
            first_name=data.get("first_name", ""), last_name=data["last_name"], function=data.get("function", ""),
            department=data.get("department", ""), phone=data.get("contact_phone", ""), email=data["email"],
            is_primary=True,
        )
        if not approval:
            customer.approve(None)
        return customer


class ContactDetailsForm(forms.ModelForm):
    """What a logged-in customer may change about themselves."""

    class Meta:
        model = Contact
        fields = ["salutation", "initials", "first_name", "last_name", "function", "department", "phone"]
