from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import User

admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


class PackDeskUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ["email"]


class PackDeskUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = PackDeskUserChangeForm
    add_form = PackDeskUserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["email", "first_name", "last_name", "kind", "is_active", "last_login"]
    list_filter = ["kind", "is_active", "groups"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]
    readonly_fields = ["last_login", "date_joined"]

    staff_fieldsets = [
        (None, {"fields": ["email", "password"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name"]}),
        (_("Access"), {"fields": ["kind", "is_active", "is_staff", "groups"]}),
        (_("Dates"), {"fields": ["last_login", "date_joined"]}),
    ]
    superuser_fieldsets = [
        (None, {"fields": ["tenant", "email", "password"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name"]}),
        (_("Access"), {"fields": ["kind", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"]}),
        (_("Dates"), {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"fields": ["email", "password1", "password2"]}),
    ]

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            if request.user.is_superuser:
                return [(None, {"fields": ["tenant", "email", "password1", "password2"]})]
            return self.add_fieldsets
        return self.superuser_fieldsets if request.user.is_superuser else self.staff_fieldsets

    def get_list_filter(self, request):
        filters = list(super().get_list_filter(request))
        return ["tenant", *filters] if request.user.is_superuser else filters

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(tenant=request.user.tenant, is_superuser=False)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.tenant = request.user.tenant
            obj.is_superuser = False
        super().save_model(request, obj, form, change)
