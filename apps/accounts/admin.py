from django import forms
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.urls import path, reverse
from django.utils.html import escapejs, format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin
from unfold.decorators import display
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextInputWidget

from apps.core.column_filters import ValueListFilter

from .models import SUPERADMIN, CustomerUser, Role, RoleInfo, User, role_title
from .password_reset import force_reset
from .permissions import grantable_permissions
from .widgets import PermissionMatrixWidget

admin.site.unregister(Group)


def assignable_roles(user):
    """Roles `user` may give to others: all for a superadmin, otherwise roles without extra rights (and never
    Superadmin)."""
    roles = Role.objects.order_by("name")
    if user.is_superuser:
        return roles
    roles = roles.exclude(name=SUPERADMIN)
    own = user.get_all_permissions()
    allowed = [
        role.pk
        for role in roles.prefetch_related("permissions__content_type")
        if all(f"{p.content_type.app_label}.{p.codename}" in own for p in role.permissions.all())
    ]
    return roles.filter(pk__in=allowed)


# --- Roles ------------------------------------------------------------------

def superadmins_left(user=None):
    """How many more superadmins may be made (setting under Configuration → Settings → Security)."""
    from apps.siteconfig.models import SiteSettings

    others = User.objects.filter(is_superuser=True).exclude(pk=getattr(user, "pk", None))
    return SiteSettings.load().max_superadmins - others.count()


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
        fields = ["permissions"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        info = RoleInfo.objects.filter(role_id=self.instance.pk).first() if self.instance.pk else None
        titles = {}
        for i, (lang, name) in enumerate(settings.LANGUAGES):
            titles[f"title_{lang}"] = forms.CharField(
                label=f"{_('Name')} ({name})", max_length=150, required=i == 0,
                widget=UnfoldAdminTextInputWidget,
                initial=getattr(info, f"title_{lang}", "") if info else "",
                help_text=_("Empty = the name in the first language.") if i else "",
            )
        self.fields = {**titles, **self.fields}
        if self.instance.pk and self.instance.name == SUPERADMIN:
            del self.fields["permissions"]
            first = next(iter(titles))
            self.fields[first].help_text = _("Superadmins always have every right, also to everything added later.")
        else:
            self.fields["permissions"].queryset = grantable_permissions(user)

    def _titles(self):
        return {f"title_{lang}": (self.cleaned_data.get(f"title_{lang}") or "").strip() or None
                for lang, _name in settings.LANGUAGES}

    def save(self, commit=True):
        role = super().save(commit=False)
        if not role.pk:  # internal name: the name in the first language, made unique
            base = name = next(t for t in self._titles().values() if t)[:140]
            n = 1
            while Group.objects.filter(name=name).exists():
                n += 1
                name = f"{base} ({n})"
            role.name = name
        role.save()
        RoleInfo.objects.update_or_create(role=role, defaults=self._titles())
        if "permissions" not in self.fields:
            return role
        chosen = set(self.cleaned_data["permissions"])
        # Keep rights the editor cannot see or grant; they may only change what they control.
        hidden = set(role.permissions.exclude(pk__in=self.fields["permissions"].queryset))
        role.permissions.set(chosen | hidden)
        return role


@admin.register(Role)
class RoleAdmin(ModelAdmin):
    form = RoleForm
    list_display = ["show_name", "show_users", "show_permissions"]
    search_fields = ["name", *[f"info__title_{lang}" for lang, _name in settings.LANGUAGES]]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("info").annotate(n_users=Count("user", distinct=True), n_perms=Count("permissions", distinct=True))

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

    @display(description=_("Name"), ordering="name")
    def show_name(self, obj):
        return role_title(obj)

    @display(description=_("Users"))
    def show_users(self, obj):
        return obj.n_users

    @display(description=_("Permissions"))
    def show_permissions(self, obj):
        return gettext("All") if obj.is_superadmin else obj.n_perms

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_superadmin and not request.user.is_superuser:
            return False  # only superadmins rename the Superadmin role
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.is_superadmin or obj.user_set.exists()):
            return False  # always there / still in use
        return super().has_delete_permission(request, obj)


# --- Users ------------------------------------------------------------------

class RoleFieldMixin(forms.Form):
    role = forms.ModelChoiceField(
        label=_("Role"),
        queryset=Role.objects.none(),
        required=False,
        widget=UnfoldAdminSelectWidget,
        help_text=_("Required for staff. The role decides what this user sees and may do in the admin. "
                    "Superadmin: every right, always."),
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
        role = cleaned.get("role")
        staff = cleaned.get("kind", getattr(self.instance, "kind", "")) == User.Kind.STAFF
        superadmin = staff and role is not None and role.is_superadmin
        if staff and not role:
            self.add_error("role", _("Staff users need a role."))
        if superadmin and not self.instance.is_superuser and superadmins_left(self.instance) <= 0:
            self.add_error("role", _("The maximum number of superadmins has been reached (Configuration → Settings → "
                                     "Security)."))
        if self.instance.pk and self.instance.is_superuser and not superadmin and "role" in self.fields \
                and not User.objects.filter(is_superuser=True).exclude(pk=self.instance.pk).exists():
            self.add_error("role", _("This is the last superadmin; there must always be at least one."))
        cleaned["is_superadmin"] = superadmin
        return cleaned


class PackDeskUserCreationForm(RoleFieldMixin, UserCreationForm):
    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "kind"]


class PackDeskUserChangeForm(RoleFieldMixin, UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


class PasswordFilter(ValueListFilter):
    title = _("Password")
    parameter_name = "pw"  # Django refuses parameters that start with "password"
    options = [
        ("set", _("Set"), lambda qs: qs.exclude(password__startswith="!")),
        ("new", _("Must choose a new one"), Q(password__startswith="!")),
    ]


class RoleFilter(SimpleListFilter):
    """The roles and No role. Superadmin is only offered to superadmins, the only ones who can see them."""

    title = _("Role")
    parameter_name = "role"

    def lookups(self, request, model_admin):
        roles = Role.objects.select_related("info").order_by("name")
        if not request.user.is_superuser:
            roles = roles.exclude(name=SUPERADMIN)
        return [(str(role.pk), str(role)) for role in roles] + [("none", _("Staff without a role"))]

    def queryset(self, request, queryset):
        value = self.value()
        if value and value.isdigit() and Role.objects.filter(pk=value, name=SUPERADMIN).exists():
            return queryset.filter(is_superuser=True)
        if value == "none":
            return queryset.filter(kind=User.Kind.STAFF, groups__isnull=True, is_superuser=False)
        if value:
            return queryset.filter(groups__pk=value)
        return queryset


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    column_filters = {"show_password": PasswordFilter, "show_role": RoleFilter}
    form = PackDeskUserChangeForm
    add_form = PackDeskUserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ["email", "first_name", "last_name", "kind", "show_role", "is_active", "show_password", "last_login"]

    class Media:
        js = ["admin/user-kind.js"]
    list_filter = ["kind", "is_active", RoleFilter]
    actions = ["deactivate_selected", "activate_selected", "send_password_reset"]

    @display(description=_("Password"), label={"set": "success", "waiting": "warning"})
    def show_password(self, obj):
        if obj.has_usable_password():
            return "set", gettext("Set")
        return "waiting", gettext("Must choose a new one")

    @admin.action(description=_("Disable selected users (they can no longer log in)"), permissions=["change"])
    def deactivate_selected(self, request, queryset):
        own = queryset.filter(pk=request.user.pk).exists()
        n = queryset.exclude(pk=request.user.pk).filter(is_active=True).update(is_active=False)
        messages.success(request, gettext("%(n)s user(s) disabled.") % {"n": n})
        if own:
            messages.warning(request, gettext("You cannot disable yourself; your own account was skipped."))

    @admin.action(description=_("Enable selected users"), permissions=["change"])
    def activate_selected(self, request, queryset):
        n = queryset.filter(is_active=False).update(is_active=True)
        messages.success(request, gettext("%(n)s user(s) enabled.") % {"n": n})

    @admin.action(description=_("Make selected users choose a new password (email with link)"), permissions=["change"])
    def send_password_reset(self, request, queryset):
        report_reset(request, *force_reset(queryset, request))
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]
    readonly_fields = ["last_login", "date_joined", "password_status"]

    @display(description=_("Password"))
    def password_status(self, obj):
        """Whether a password is set, instead of the technical hash; with buttons to set one or to let the
        user choose one by email. The real password is never stored, so it cannot be shown."""
        if obj is None or not obj.pk:
            return "–"
        if obj.has_usable_password():
            status, colour = gettext("Password set"), "text-green-700 dark:text-green-400"
        else:
            status, colour = gettext("Must choose a new password"), "text-orange-700 dark:text-orange-400"
        return format_html(
            '<div class="flex flex-wrap items-center gap-3"><span class="font-semibold {}">{}</span>'
            '<a class="pd-btn" href="{}"><span class="material-symbols-outlined text-[18px]">password</span>{}</a>'
            '<button type="submit" class="pd-btn" formaction="{}" formnovalidate '
            'onclick="return confirm(\'{}\')"><span class="material-symbols-outlined text-[18px]">mail</span>{}</button>'
            '</div><div class="text-sm text-base-500 mt-1">{}</div>',
            colour, status, reverse(f"admin:{self.password_url_name}", args=[obj.pk]), gettext("Set password"),
            reverse(f"admin:accounts_{self.opts.model_name}_send_reset", args=[obj.pk]),
            escapejs(gettext("The current password stops working and the user gets an email to choose a new one. "
                             "Continue?")),
            gettext("Send reset email"),
            gettext("Passwords are stored encrypted and can never be shown."),
        )

    password_url_name = "auth_user_password_change"  # Django's fixed name for the password page

    def get_urls(self):
        return [path("<int:pk>/send-reset/", self.admin_site.admin_view(self.send_reset_view),
                     name=f"accounts_{self.opts.model_name}_send_reset")] + super().get_urls()

    def send_reset_view(self, request, pk):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        user = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self.has_change_permission(request, user):
            raise PermissionDenied
        report_reset(request, *force_reset(User.objects.filter(pk=user.pk), request))
        return redirect(f"admin:accounts_{self.opts.model_name}_change", user.pk)

    staff_fieldsets = [
        (None, {"fields": ["email", "password_status"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name", "admin_language"]}),
        (_("Access"), {"fields": ["kind", "role", "is_active"]}),
        (_("Dates"), {"fields": ["last_login", "date_joined"]}),
    ]
    superuser_fieldsets = [
        (None, {"fields": ["email", "password_status"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name", "admin_language"]}),
        (_("Access"), {"fields": ["kind", "role", "is_active"]}),
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
        role = obj.groups.select_related("info").first()
        return role_title(role) or "—"

    def save_model(self, request, obj, form, change):
        if "role" in form.fields:  # the Superadmin role makes a superuser; only superadmins can give it
            obj.is_superuser = bool(form.cleaned_data.get("is_superadmin")) and request.user.is_superuser
        if obj.kind == User.Kind.CUSTOMER:
            obj.is_superuser = False  # customers never are one
        if obj.kind == User.Kind.CUSTOMER:
            obj.admin_language = ""
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


@admin.register(CustomerUser)
class CustomerUserAdmin(UserAdmin):
    """Customers → Users: the same user pages, but only logins of customers, and new ones are customers too.
    Uses the rights of users, so roles need nothing extra."""

    list_display = ["email", "first_name", "last_name", "show_customer", "is_active", "show_password", "last_login"]
    list_filter = ["is_active"]
    password_url_name = "accounts_customeruser_password_change"
    customer_fieldsets = [
        (None, {"fields": ["email", "password_status"]}),
        (_("Personal info"), {"fields": ["first_name", "last_name"]}),
        (_("Access"), {"fields": ["is_active"]}),
        (_("Dates"), {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [(None, {"fields": ["email", "first_name", "last_name", "password1", "password2"]})]

    def get_urls(self):
        urls = super().get_urls()
        for url in urls:  # Django names the password page the same for every user admin; this one gets its own
            if getattr(url, "name", None) == "auth_user_password_change":
                url.name = self.password_url_name
        return urls

    def get_queryset(self, request):
        return super().get_queryset(request).filter(kind=User.Kind.CUSTOMER).select_related("contact__customer")

    def get_fieldsets(self, request, obj=None):
        return self.add_fieldsets if obj is None else self.customer_fieldsets

    def save_model(self, request, obj, form, change):
        obj.kind = User.Kind.CUSTOMER
        super().save_model(request, obj, form, change)

    @display(description=_("Customer"))
    def show_customer(self, obj):
        contact = getattr(obj, "contact", None)
        return contact.customer if contact else "—"

    def _user_perm(self, request, action):
        return request.user.has_perm(f"accounts.{action}_user")

    def has_module_permission(self, request):
        return self._user_perm(request, "view") or self._user_perm(request, "change")

    def has_view_permission(self, request, obj=None):
        return self._user_perm(request, "view") or self._user_perm(request, "change")

    def has_add_permission(self, request):
        return self._user_perm(request, "add")

    def has_change_permission(self, request, obj=None):
        return self._user_perm(request, "change")

    def has_delete_permission(self, request, obj=None):
        return self._user_perm(request, "delete")


def report_reset(request, sent, skipped):
    messages.success(request, gettext("%(n)s email(s) sent with a link to choose a new password; the old passwords "
                                      "no longer work.") % {"n": sent})
    if skipped:
        messages.warning(request, gettext("Not sent (no email address or not active): %(list)s")
                         % {"list": ", ".join(skipped[:20]) + (" …" if len(skipped) > 20 else "")})
