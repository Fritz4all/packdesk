from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, TabularInline

from .models import Domain, Tenant


class DomainInline(TabularInline):
    model = Domain
    extra = 0

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Tenant)
class TenantAdmin(ModelAdmin):
    list_display = ["name", "slug", "is_active", "created_at"]
    search_fields = ["name", "slug"]
    inlines = [DomainInline]
    fieldsets = [
        (None, {"fields": ["name", "slug", "is_active", "language"]}),
        (_("Branding"), {"fields": ["logo", "primary_color", "accent_color", "tagline"]}),
        (
            _("Company details"),
            {
                "fields": [
                    "legal_name",
                    "address_line",
                    ("postal_code", "city", "country"),
                    ("phone", "email"),
                    "website",
                    ("coc_number", "vat_number"),
                    "iban",
                ]
            },
        ),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(pk=request.user.tenant_id)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser:
            return []
        return ["slug", "is_active"]

    def get_inlines(self, request, obj):
        return self.inlines if request.user.is_superuser else []

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    list_display = ["domain", "tenant", "is_primary"]
    list_filter = ["tenant"]
    search_fields = ["domain"]

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
