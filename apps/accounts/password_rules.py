"""Minimum password length from the settings (Settings → Security): one for staff, one for customers."""

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

DEFAULT = 10


def is_staff_user(user):
    from .models import User

    return bool(user is not None and (user.is_staff or user.is_superuser or getattr(user, "kind", "") == User.Kind.STAFF))


def min_length(user=None, staff=None):
    """The minimum for this user (or for staff/customers when there is no user yet)."""
    staff = is_staff_user(user) if staff is None else staff
    try:
        from apps.siteconfig.models import SiteSettings

        site = SiteSettings.load()
    except Exception:  # no database yet
        return DEFAULT
    return site.password_min_length_staff if staff else site.password_min_length_customers


class SiteMinimumLengthValidator:
    def validate(self, password, user=None):
        needed = min_length(user)
        if len(password) < needed:
            raise ValidationError(
                ngettext("This password is too short. It must contain at least %(min_length)d character.",
                         "This password is too short. It must contain at least %(min_length)d characters.", needed),
                code="password_too_short", params={"min_length": needed},
            )

    def get_help_text(self):
        staff, customers = min_length(staff=True), min_length(staff=False)
        if staff == customers:
            return ngettext("Your password must contain at least %(n)d character.",
                            "Your password must contain at least %(n)d characters.", staff) % {"n": staff}
        return _("Your password must contain at least %(staff)d characters for staff and %(customers)d for "
                 "customers.") % {"staff": staff, "customers": customers}
