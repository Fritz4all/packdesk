from django.contrib.auth import views as auth_views

from apps.siteconfig.models import SiteSettings


class PasswordResetView(auth_views.PasswordResetView):
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"

    def form_valid(self, form):
        # Email templates are rendered without a request, so pass the settings explicitly.
        self.extra_email_context = {"site_settings": SiteSettings.load()}
        return super().form_valid(form)
