from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.i18n import set_language
from django.views.static import serve

from apps.accounts.forms import EmailAdminAuthenticationForm
from apps.dashboard import reports as dashboard_reports
from apps.dashboard import views as dashboard_views

admin.site.login_form = EmailAdminAuthenticationForm

urlpatterns = [
    path("beheer/dashboard/layout/", dashboard_views.save_layout, name="dashboard_save_layout"),
    path("beheer/dashboard/reset/", dashboard_views.reset_layout, name="dashboard_reset_layout"),
    path("beheer/rapportage/", dashboard_reports.report_view, name="reports"),
    path("beheer/", admin.site.urls),
    path("taal/", set_language, name="set_language"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.licences.urls")),
    path("", include("apps.faults.urls")),
    path("", include("apps.core.urls")),
    # Public assets such as the logo. Private documents (invoices) get
    # their own authenticated views later and never live under MEDIA_URL.
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]
