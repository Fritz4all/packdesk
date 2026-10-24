from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.siteconfig.models import SiteSettings

from .password_reset import ResetFormIncludingUnusable


class PasswordResetView(auth_views.PasswordResetView):
    form_class = ResetFormIncludingUnusable
    email_template_name = "registration/password_reset_email.txt"
    subject_template_name = "registration/password_reset_subject.txt"

    def form_valid(self, form):
        # Email templates are rendered without a request, so pass the settings explicitly.
        self.extra_email_context = {"site_settings": SiteSettings.load()}
        return super().form_valid(form)


@staff_member_required
@require_POST
def set_admin_language(request):
    """Staff choose the language of the admin for themselves (the website language stays as it is)."""
    language = request.POST.get("language", "")
    if language in {code for code, _name in settings.LANGUAGES}:
        request.user.admin_language = language
        request.user.save(update_fields=["admin_language"])
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
        target = reverse("admin:index")
    return redirect(target)
