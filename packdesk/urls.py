import re

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponsePermanentRedirect
from django.urls import include, path, re_path
from django.views.i18n import set_language
from django.views.static import serve

from apps.accounts import views as account_views
from apps.accounts.forms import EmailAdminAuthenticationForm
from apps.dashboard import navigation as dashboard_navigation
from apps.dashboard import reports as dashboard_reports
from apps.dashboard import views as dashboard_views
from apps.legacy import import_views as legacy_import_views
from apps.legacy import views as legacy_views

admin.site.login_form = EmailAdminAuthenticationForm
admin.site.app_index = dashboard_navigation.section_index  # section pages follow the menu


def old_admin_address(request, rest=""):
    """The admin used to be at /beheer/ with Dutch sub-addresses; old links and bookmarks still work."""
    for old, new in (("importeren/verslag/", "import/report/"), ("vergelijken/", "compare/"),
                     ("importeren/", "import/"), ("rapportage/", "reports/"), ("taal/", "language/")):
        if rest.startswith(old):
            rest = new + rest[len(old):]
            break
    rest = re.sub(r"^(compare/\d+/)zoeken/", r"\1search/", rest)
    query = request.META.get("QUERY_STRING")
    return HttpResponsePermanentRedirect(f"/admin/{rest}" + (f"?{query}" if query else ""))


urlpatterns = [
    path("admin/dashboard/layout/", dashboard_views.save_layout, name="dashboard_save_layout"),
    path("admin/dashboard/reset/", dashboard_views.reset_layout, name="dashboard_reset_layout"),
    path("admin/compare/", legacy_views.choose, name="legacy_choose"),
    path("admin/import/<int:pk>/", legacy_import_views.start, name="legacy_import"),
    path("admin/import/report/<int:pk>/", legacy_import_views.report, name="legacy_import_report"),
    path("admin/compare/<int:pk>/", legacy_views.overview, name="legacy_compare"),
    path("admin/compare/<int:pk>/search/", legacy_views.search_view, name="legacy_search"),
    path("admin/compare/<int:pk>/<str:part_key>/<str:category>/", legacy_views.detail, name="legacy_detail"),
    path("admin/language/", account_views.set_admin_language, name="admin_language"),
    path("admin/reports/", dashboard_reports.report_view, name="reports"),
    path("admin/", admin.site.urls),
    re_path(r"^beheer(?:/(?P<rest>.*))?$", old_admin_address),
    path("taal/", set_language, name="set_language"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.customers.urls")),
    path("", include("apps.licences.urls")),
    path("", include("apps.faults.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.invoices.urls")),
    path("", include("apps.parts.urls")),
    path("", include("apps.telephony.urls")),
    path("", include("apps.core.urls")),
    # Public assets such as the logo. Private documents (invoices) get
    # their own authenticated views later and never live under MEDIA_URL.
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]
