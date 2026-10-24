"""Installation wizard for a new PackDesk: installation code, first administrator, basic settings,
numbering and (optionally) a demo catalogue. It closes for good once finished.

Which step is shown follows from the database, so the wizard can be left and resumed:
no administrator yet → code and administrator; administrator exists → the remaining steps, for a
logged-in administrator only.
"""

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, password_validation
from django.core.mail import send_mail
from django.core.management import call_command
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.models import User
from apps.numbering.models import NumberSequence
from apps.siteconfig.models import SiteSettings

from . import setup_code

STEPS = [
    ("code", gettext_lazy("Installation code")),
    ("admin", gettext_lazy("Administrator")),
    ("basics", gettext_lazy("Basic settings")),
    ("numbering", gettext_lazy("Numbering")),
    ("demo", gettext_lazy("Demo data")),
]
SESSION_KEY = "setup_code_ok"


class CodeForm(forms.Form):
    code = forms.CharField(label=gettext_lazy("Installation code"), max_length=40)

    def clean_code(self):
        if not setup_code.check(self.cleaned_data["code"]):
            raise forms.ValidationError(_("The installation code is not correct."))
        return self.cleaned_data["code"]


class AdminForm(forms.Form):
    email = forms.EmailField(label=gettext_lazy("Email address"))
    first_name = forms.CharField(label=gettext_lazy("First name"), max_length=150, required=False)
    last_name = forms.CharField(label=gettext_lazy("Last name"), max_length=150, required=False)
    password1 = forms.CharField(label=gettext_lazy("Password"), widget=forms.PasswordInput, strip=False)
    password2 = forms.CharField(label=gettext_lazy("Password again"), widget=forms.PasswordInput, strip=False)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("This email address is already in use."))
        return email

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") and cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", _("The passwords are not the same."))
        elif cleaned.get("password1"):
            user = User(email=cleaned.get("email", ""), first_name=cleaned.get("first_name", ""))
            try:
                password_validation.validate_password(cleaned["password1"], user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class BasicsForm(forms.ModelForm):
    languages = forms.MultipleChoiceField(
        label=gettext_lazy("Available languages"), choices=settings.LANGUAGES, widget=forms.CheckboxSelectMultiple,
    )
    test_mail = forms.BooleanField(label=gettext_lazy("Send a test email to me"), required=False)

    class Meta:
        model = SiteSettings
        fields = ["name", "language", "languages", "admin_language", "email", "logo"]
        labels = {"name": gettext_lazy("Company or shop name"), "email": gettext_lazy("General email address")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["languages"] = self.instance.language_codes

    def clean(self):
        cleaned = super().clean()
        languages = cleaned.get("languages") or []
        if cleaned.get("language") and cleaned["language"] not in languages:
            self.add_error("languages", _("The default language must be one of the available languages."))
        cleaned["languages"] = ",".join(languages)
        return cleaned


class NumberingForm(forms.Form):
    def __init__(self, *args, sequences=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.sequences = list(sequences)
        for seq in self.sequences:
            self.fields[f"next_{seq.pk}"] = forms.IntegerField(
                label=seq.name, min_value=1, initial=seq.next_number,
                help_text=_("Next: %(example)s") % {"example": seq.preview()},
            )

    def save(self):
        for seq in self.sequences:
            seq.next_number = self.cleaned_data[f"next_{seq.pk}"]
            seq.save(update_fields=["next_number"])


class DemoForm(forms.Form):
    demo = forms.BooleanField(label=gettext_lazy("Fill in a small demo catalogue with test licences"), required=False)


def _posted(request):
    """The submitted data, also when a form only has an unticked checkbox (empty POST)."""
    return request.POST if request.method == "POST" else None


def _admin_exists():
    return User.objects.filter(is_superuser=True).exists()


def _render(request, step, form, **extra):
    names = [key for key, _label in STEPS]
    return render(request, "setup/wizard.html", {
        "steps": STEPS, "step": step, "step_index": names.index(step) if step in names else len(names),
        "form": form, "code_from_env": setup_code.from_env(), **extra,
    })


def wizard(request, step=None):
    site = SiteSettings.load()
    if site.setup_completed:
        return redirect("admin:index")
    if not _admin_exists():
        if step not in ("code", "admin"):
            return redirect("setup_step", "code")
    else:
        if not (request.user.is_authenticated and request.user.is_superuser):
            return redirect(f"{reverse('admin:login')}?next={reverse('setup')}")
        if step in (None, "code", "admin"):
            return redirect("setup_step", "basics")
    handler = {"code": _code, "admin": _admin, "basics": _basics, "numbering": _numbering, "demo": _demo}.get(step)
    if handler is None:
        raise Http404
    return handler(request, site)


def _code(request, site):
    form = CodeForm(_posted(request))
    if request.method == "POST" and form.is_valid():
        request.session[SESSION_KEY] = True
        return redirect("setup_step", "admin")
    return _render(request, "code", form)


def _admin(request, site):
    if not request.session.get(SESSION_KEY):
        return redirect("setup_step", "code")
    form = AdminForm(_posted(request))
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        user = User(email=data["email"], first_name=data["first_name"], last_name=data["last_name"],
                    kind=User.Kind.STAFF, is_staff=True, is_superuser=True)
        user.set_password(data["password1"])
        user.save()
        request.session.pop(SESSION_KEY, None)
        setup_code.forget()
        login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])
        return redirect("setup_step", "basics")
    return _render(request, "admin", form)


def _basics(request, site):
    form = BasicsForm(_posted(request), request.FILES or None, instance=site)
    if request.method == "POST" and form.is_valid():
        form.save()
        if form.cleaned_data.get("test_mail"):
            try:
                send_mail(_("Test email from PackDesk"), _("Sending email works."), None, [request.user.email])
            except Exception as exc:  # the wizard goes on; the mail settings live in .env
                return _render(request, "basics", form, mail_error=str(exc))
        return redirect("setup_step", "numbering")
    return _render(request, "basics", form)


def _numbering(request, site):
    form = NumberingForm(_posted(request), sequences=NumberSequence.objects.order_by("name"))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("setup_step", "demo")
    return _render(request, "numbering", form)


def _demo(request, site):
    form = DemoForm(_posted(request))
    if request.method == "POST" and form.is_valid():
        if form.cleaned_data["demo"]:
            call_command("load_demo_catalogue", verbosity=0)
        site.setup_completed = True
        site.save(update_fields=["setup_completed"])
        messages.success(request, _("PackDesk is ready. Everything can be changed later in the admin."))
        return redirect("admin:index")
    return _render(request, "demo", form)
