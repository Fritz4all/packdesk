from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.db.models import Count
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Role, User
from .password_reset import force_reset
from .permissions import grantable_permissions
from .widgets import PermissionMatrixWidget

admin.site.unregister(Group)


def assignable_roles(user):
    """Roles `user` may give to others: all for a superuser, otherwise roles without extra rights."""
    roles = Role.objects.order_by("name")
    if user.is_superuser:
        return roles
    own = user.get_all_permissions()
    allowed = [
        role.pk
        for role in roles.prefetch_related("permissions__content_type")
        if all(f"{p.content_type.app_label}.{p.codename}" in own for p in role.permissions.all())
    ]
    return roles.filter(pk__in=allowed)


# --- Roles ------------------------------------------------------------------

class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        label=_("Permissions"),
        queryset=None,
        required=False,
        widget=PermissionMatrixWidget,
        help_text=_("Tick what users with this role may see and do. You can only grant rights you have yourself."),
    )

    class Meta:
        model = Role
        fields = ["name", "permissions"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["permissions"].queryset = grantable_permissions(user)

    def save(self, commit=True):
        role = super().save(commit=False)
        role.save()
        chosen = set(self.cleaned_data["permissions"])
        # Keep rights the editor cannot see or grant; they may only change what they control.
        hidden = set(role.permissions.exclude(pk__in=self.fields["permissions"].queryset))
        role.permissions.set(chosen | hidden)
        return role


@admin.register(Role)
class RoleAdmin(ModelAdmin):
    form = RoleForm
    list_display = ["name", "show_users", "show_permissions"]
    search_fields = ["name"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_users=Count("user", distinct=True), n_perms=Count("permissions", distinct=True))

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)

        class RequestRoleForm(form_class):
            def __init__(self, *args, **kw):
                super().__init__(*args, user=request.user, **kw)

        return RequestRoleForm

    def save_related(self, request, form, formsets, change):
        # Permissions are saved in RoleForm.save(); skip the default m2m save that would overwrite them.
        for formset in formsets:
            self.save_formset(request, form, formset, change=change)

    @display(description=_("Users"))
    def show_users(self, obj):
        return obj.n_users

    @display(description=_("Permissions"))
    def show_permissions(self, obj):
        return obj.n_perms

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.user_set.exists():
            return False  # still in use
        return super().has_delete_permission(request, obj)


# --- Users ------------------------------------------------------------------

class RoleFieldMixin(forms.Form):
    role = forms.ModelChoiceField(
        label=_("Role"),
        queryset=Role.objects.none(),
        required=False,
        help_text=_("Required for staff. The role decides what this user sees and may do in the admin."),
    )

    def setup_role(self, request_user):
        self.request_user = request_user
        self.fields["role"].queryset = assignable_roles(request_user)
        if self.instance and self.instance.pk:
            current = self.instance.groups.first()
            if current:
                self.initial["role"] = current.pk

    def clean(self):
        cleaned = super().clean()
        is_super = cleaned.get("is_superuser", getattr(self.instance, "is_superuser", False))
        if cleaned.get("kind") == User.Kind.STAFF and not is_super and not cleaned.get("role"):
            self.add_error("role", _("Staff users need a role."))
        return cleaned


class PackDeskUserCreationForm(RoleFieldMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "kind"]


class PackDeskUserChangeForm(RoleFieldMixin, UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = PackDeskUserChangeForm
    add_form = PackDeskUserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["email", "first_name", "last_name", "kind", "show_role", "is_active", "show_password", "last_login"]
    list_filter = ["kind", "is_active", "groups"]
    actions = ["send_password_reset"]

    @display(description=_("Password"), label={"set": "success", "waiting": "warning"})
    def show_password(self, obj):
        if obj.has_usable_password():
            return "set", gettext("Set")
        return "waiting", gettext("Must choose a new one")

    @admin.action(description=_("Make selected users choose a new password (email with link)"), permissions=["change"])
    def send_password_reset(self, request, queryset):
        report_reset(request, *force_reset(queryset, request))
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]
    readonly_fields = ["last_login", "date_joined"]

    staff_fieldsets = [
        (None, {"fields": ["email", "password"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name", "admin_language"]}),
        (_("Access"), {"fields": ["kind", "role", "is_active"]}),
        (_("Dates"), {"fields": ["last_login", "date_joined"]}),
    ]
    superuser_fieldsets = [
        (None, {"fields": ["email", "password"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name", "admin_language"]}),
        (_("Access"), {"fields": ["kind", "role", "is_active", "is_superuser"]}),
        (_("Dates"), {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (None, {"fields": ["email", "first_name", "last_name", "password1", "password2"]}),
        (_("Access"), {"fields": ["kind", "role"]}),
    ]

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return self.superuser_fieldsets if request.user.is_superuser else self.staff_fieldsets

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)

        class RequestUserForm(form_class):
            def __init__(self, *args, **kw):
                super().__init__(*args, **kw)
                self.setup_role(request.user)

        return RequestUserForm

    def get_queryset(self, request):
        qs = super().get_queryset(request).prefetch_related("groups")
        if request.user.is_superuser:
            return qs
        # Non-superusers cannot see or edit superusers.
        return qs.filter(is_superuser=False)

    @display(description=_("Role"))
    def show_role(self, obj):
        role = obj.groups.first()
        return role.name if role else ("—" if not obj.is_superuser else _("Superuser"))

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.is_superuser = False
        # Staff (admin users) and customers are told apart by `kind`.
        obj.is_staff = obj.kind == User.Kind.STAFF or obj.is_superuser
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        role = form.cleaned_data.get("role")
        user = form.instance
        if user.kind == User.Kind.STAFF and role:
            user.groups.set([role])
        elif user.kind != User.Kind.STAFF:
            user.groups.clear()


def report_reset(request, sent, skipped):
    messages.success(request, gettext("%(n)s email(s) sent with a link to choose a new password; the old passwords "
                                      "no longer work.") % {"n": sent})
    if skipped:
        messages.warning(request, gettext("Not sent (no email address or not active): %(list)s")
                         % {"list": ", ".join(skipped[:20]) + (" …" if len(skipped) > 20 else "")})
