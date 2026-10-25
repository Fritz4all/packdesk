from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from unfold.forms import AuthenticationForm as UnfoldAuthenticationForm


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _("Unknown email address or wrong password."),
    }


class EmailAdminAuthenticationForm(UnfoldAuthenticationForm):
    """The admin login: the admin's own input styling (readable in light and dark mode) and an example in
    each field."""

    username = forms.EmailField(
        label=_("Email address"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )

    error_messages = EmailAuthenticationForm.error_messages

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs["placeholder"] = _("name@company.com")
        self.fields["password"].widget.attrs["placeholder"] = _("Your password")
