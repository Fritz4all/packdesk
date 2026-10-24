"""Make people choose a new password: the current one stops working and they get a link by email.

Used from the admin for several customers, contacts or users at once (e.g. after the import of the
previous webshop, which kept the old passwords). "Forgot password" keeps working for these accounts, so a
link that has expired is never a dead end.
"""

from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.utils.translation import gettext as _

from apps.customers.emails import password_link, sender
from apps.siteconfig.language import in_customer_language
from apps.siteconfig.models import SiteSettings

from .models import User


@in_customer_language
def _mail(user, request):
    site = SiteSettings.load()
    body = _(
        "Dear %(name)s,\n\nFor your account at %(company)s you need to choose a new password; your current "
        "password no longer works.\n\nChoose your new password here (the link is valid for a few days):\n%(link)s\n\n"
        "Expired? Use 'Forgot password' on the login page.\n"
    ) % {"name": user.get_full_name() or user.email, "company": site.display_name, "link": password_link(user, request)}
    send_mail(_("Choose a new password for %(company)s") % {"company": site.display_name}, body, sender(), [user.email])


def force_reset(users, request):
    """Returns (number sent, list of skipped email addresses or names)."""
    sent, skipped = 0, []
    for user in users:
        if not user.email or not user.is_active:
            skipped.append(user.email or str(user))
            continue
        user.set_unusable_password()
        user.save(update_fields=["password"])
        _mail(user, request)
        sent += 1
    return sent, skipped


class ResetFormIncludingUnusable(PasswordResetForm):
    """Django's form leaves out accounts without a usable password; those must be able to reset too."""

    def get_users(self, email):
        return User.objects.filter(email__iexact=email, is_active=True)
