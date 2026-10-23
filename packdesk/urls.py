from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

urlpatterns = [
    path("beheer/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
    # Public tenant assets such as logos. Private documents (invoices) get
    # their own authenticated views later and never live under MEDIA_URL.
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
]
