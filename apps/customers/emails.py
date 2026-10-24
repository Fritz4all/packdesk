"""Emails around customers. Plain text for now; the mail module makes them editable as templates later."""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from apps.siteconfig.language import in_customer_language
from apps.siteconfig.models import SiteSettings

from .models import SignupSettings


def sender():
    site = SiteSettings.load()
    address = site.address_for("mail")
    email = (address.contact_email() if address else "") or site.email or settings.DEFAULT_FROM_EMAIL
    return f"{site.display_name} <{email}>"


def _send(subject, body, to):
    recipients = [r for r in to if r]
    if recipients:
        send_mail(subject, body, sender(), recipients)


def notify_new_signup(customer, request):
    site, signup = SiteSettings.load(), SignupSettings.load()
    url = request.build_absolute_uri(reverse("admin:customers_customer_change", args=[customer.pk]))
    contact = customer.contacts.first()
    body = _("New sign-up: %(company)s\nContact: %(contact)s <%(email)s>\n\nReview and approve: %(url)s") % {
        "company": customer.name,
        "contact": contact.full_name if contact else "-",
        "email": contact.email if contact else "-",
        "url": url,
    }
    _send(_("New sign-up: %(company)s") % {"company": customer.name}, body, [signup.notify_email or site.email])


@in_customer_language
def send_activation(customer, request):
    site, signup = SiteSettings.load(), SignupSettings.load()
    login_url = request.build_absolute_uri(reverse("login"))
    for contact in customer.contacts.filter(user__isnull=False):
        values = {"name": contact.full_name, "company": site.display_name, "number": customer.number, "login_url": login_url}
        subject = (signup.activation_subject or _("Your account is active")).format(**values)
        body = (signup.activation_body or _("Your account has been approved. Log in at {login_url}")).format(**values)
        _send(subject, body, [contact.user.email])


def password_link(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return request.build_absolute_uri(reverse("password_reset_confirm", args=[uid, token]))


@in_customer_language
def send_invite(contact, request):
    site = SiteSettings.load()
    body = _(
        "Dear %(name)s,\n\nAn account has been created for you at %(company)s.\n"
        "Choose your password via this link:\n%(link)s\n\nYour login is your email address: %(email)s"
    ) % {"name": contact.full_name, "company": site.display_name, "link": password_link(contact.user, request),
         "email": contact.user.email}
    _send(_("Your account at %(company)s") % {"company": site.display_name}, body, [contact.user.email])
