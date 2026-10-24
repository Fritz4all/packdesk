from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.i18n import set_language
from django.views.static import serve

from apps.accounts import views as account_views
from apps.accounts.forms import EmailAdminAuthenticationForm
from apps.dashboard import reports as dashboard_reports
from apps.dashboard import views as dashboard_views
from apps.legacy import import_views as legacy_import_views
from apps.legacy import views as legacy_views

admin.site.login_form = EmailAdminAuthenticationForm

urlpatterns = [
    path("beheer/dashboard/layout/", dashboard_views.save_layout, name="dashboard_save_layout"),
    path("beheer/dashboard/reset/", dashboard_views.reset_layout, name="dashboard_reset_layout"),
    path("beheer/vergelijken/", legacy_views.choose, name="legacy_choose"),
    path("beheer/importeren/<int:pk>/", legacy_import_views.start, name="legacy_import"),
    path("beheer/importeren/verslag/<int:pk>/", legacy_import_views.report, name="legacy_import_report"),
    path("beheer/vergelijken/<int:pk>/", legacy_views.overview, name="legacy_compare"),
    path("beheer/vergelijken/<int:pk>/zoeken/", legacy_views.search_view, name="legacy_search"),
    path("beheer/vergelijken/<int:pk>/<str:part_key>/<str:category>/", legacy_views.detail, name="legacy_detail"),
    path("beheer/taal/", account_views.set_admin_language, name="admin_language"),
    path("beheer/rapportage/", dashboard_reports.report_view, name="reports"),
    path("beheer/", admin.site.urls),
    path("taal/", set_language, name="set_language"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.licences.urls")),
    path("", include("apps.faults.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.invoices.urls")),
    path("", include("apps.parts.urls")),
    path("", include("apps.core.urls")),
    # Public assets such as the logo. Private documents (invoices) get
    # their own authenticated views later and never live under MEDIA_URL.
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]
