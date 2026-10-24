"""Outgoing mail: the mail server from the server settings (environment, .env), otherwise the one
entered in the admin under Settings → Mail server."""

from django.conf import settings
from django.core.mail.backends.smtp import EmailBackend


def site_mail_settings():
    """SMTP options from the settings in the admin, or {} when none are entered."""
    from apps.siteconfig.models import SiteSettings

    site = SiteSettings.load()
    if not site.mail_host:
        return {}
    return {
        "host": site.mail_host, "port": site.mail_port or (465 if site.mail_security == "ssl" else 587),
        "username": site.mail_user, "password": site.get_mail_password(),
        "use_tls": site.mail_security == "starttls", "use_ssl": site.mail_security == "ssl",
    }


class SiteEmailBackend(EmailBackend):
    def __init__(self, **kwargs):
        if not settings.MAIL_SERVER_FROM_ENV:
            options = site_mail_settings()
            options.update(kwargs)
            kwargs = options
        super().__init__(**kwargs)
