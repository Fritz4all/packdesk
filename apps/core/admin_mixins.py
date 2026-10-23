from unfold.admin import ModelAdmin


class TenantScopedAdmin(ModelAdmin):
    """Admin for TenantScopedModel subclasses.

    Superusers see every tenant's rows. Tenant staff only see and create rows
    of their own tenant, and never see the tenant field.
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(tenant=request.user.tenant)

    def get_exclude(self, request, obj=None):
        exclude = list(super().get_exclude(request, obj) or [])
        if not request.user.is_superuser:
            exclude.append("tenant")
        return exclude

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        if request.user.is_superuser and "tenant" not in filters:
            filters.insert(0, "tenant")
        return filters

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.tenant = request.user.tenant
        super().save_model(request, obj, form, change)
