from django.contrib import admin, messages
from django.db.models import Count
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from modeltranslation.admin import TabbedTranslationAdmin
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import display

from apps.accounts.admin import report_reset
from apps.accounts.models import User
from apps.accounts.password_reset import force_reset
from apps.core.object_actions import ObjectAction, ObjectActionsMixin

from . import emails
from . import transfer_views
from .models import Contact, Country, Customer, CustomerAddress, CustomerType, SignupSettings

STATUS_COLOURS = {"pending": "warning", "active": "success", "blocked": "danger"}


class AddressInline(TabularInline):
    model = CustomerAddress
    extra = 0
    tab = True
    fields = ["kind", "attention", "line1", "line2", "postal_code", "city", "country"]


class ContactInline(StackedInline):
    model = Contact
    extra = 0
    tab = True
    collapsible = True
    fields = [
        ("salutation", "initials", "first_name", "last_name"),
        ("function", "department"),
        ("email", "phone"),
        ("is_primary", "show_login"),
        "remark",
    ]
    readonly_fields = ["show_login"]

    @display(description=_("Login"))
    def show_login(self, obj):
        if not obj.pk or not obj.user:
            return gettext("No login yet")
        return gettext("Active") if obj.user.is_active else gettext("Not active (waiting for approval or blocked)")


@admin.register(Customer)
class CustomerAdmin(ObjectActionsMixin, ModelAdmin):
    inlines = [AddressInline, ContactInline]
    list_display = ["show_number", "name", "customer_type", "show_city", "show_status", "n_contacts"]
    list_display_links = ["show_number", "name"]
    list_filter = ["status", "customer_type", "addresses__country"]
    search_fields = [
        "number", "name", "email", "phone", "vat_number", "coc_number", "website",
        "contacts__email", "contacts__first_name", "contacts__last_name", "contacts__phone",
        "addresses__line1", "addresses__postal_code", "addresses__city",
    ]
    readonly_fields = ["approved_at", "approved_by", "created_at", "updated_at", "signup_message"]
    actions = ["approve_selected", "block_selected", "export_selected", "send_password_reset"]
    change_list_template = "admin/customers/customer/change_list.html"
    object_actions = [
        ObjectAction("approve", _("Approve"), "check_circle", handler="approve", show_if="can_approve"),
        ObjectAction("invite", _("Send login to contacts without one"), "mail", handler="send_invites",
                     show_if="has_contacts_without_login"),
        ObjectAction("block", _("Block"), "block", handler="block", show_if="can_block", variant="danger",
                     confirm=_("Block this customer? Its contacts can no longer log in.")),
        ObjectAction("export", _("Export"), "download", handler="export_one", permission="customers.export_customer"),
    ]
    fieldsets = [
        (_("General"), {"classes": ["tab"], "fields": [
            ("number", "status"), "name", "customer_type", ("phone", "email"), "website", ("vat_number", "coc_number"), "logo",
        ]}),
        (_("Email addresses"), {"classes": ["tab"], "fields": ["email_orders", "email_parts", "email_invoices"]}),
        (_("Prices and invoices"), {"classes": ["tab"], "fields": [("margin_packs", "margin_parts"), "no_pack_invoice"]}),
        (_("Notes"), {"classes": ["tab"], "fields": [
            "remark", "signup_message", ("approved_at", "approved_by"), ("created_at", "updated_at"),
        ]}),
    ]

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related("customer_type")
            .prefetch_related("addresses")
            .annotate(contacts_count=Count("contacts", distinct=True))
        )

    def get_changeform_initial_data(self, request):
        signup = SignupSettings.load()
        return {"margin_packs": signup.default_margin_packs, "margin_parts": signup.default_margin_parts}

    @display(description=_("Number"), ordering="number")
    def show_number(self, obj):
        return obj.number or "—"

    @display(description=_("City"))
    def show_city(self, obj):
        main = obj.address(CustomerAddress.Kind.MAIN)
        return main.city if main else "—"

    @display(description=_("Status"), ordering="status", label=STATUS_COLOURS)
    def show_status(self, obj):
        return obj.status, obj.get_status_display()

    @display(description=_("Contacts"), ordering="contacts_count")
    def n_contacts(self, obj):
        return obj.contacts_count

    def save_model(self, request, obj, form, change):
        if obj.status == Customer.Status.ACTIVE:
            obj.assign_number()
        super().save_model(request, obj, form, change)

    # --- approve / block ----------------------------------------------------

    def _approve(self, request, customer):
        was_pending = customer.status == Customer.Status.PENDING
        customer.approve(request.user)
        if was_pending:
            emails.send_activation(customer, request)

    @admin.action(description=_("Approve selected customers"), permissions=["change"])
    def approve_selected(self, request, queryset):
        for customer in queryset:
            self._approve(request, customer)
        messages.success(request, gettext("%(n)s customer(s) approved.") % {"n": queryset.count()})

    @admin.action(description=_("Block selected customers"), permissions=["change"])
    def block_selected(self, request, queryset):
        for customer in queryset:
            customer.block()
        messages.success(request, gettext("%(n)s customer(s) blocked.") % {"n": queryset.count()})

    # --- export / import ----------------------------------------------------

    def get_urls(self):
        return [
            path("import/", self.admin_site.admin_view(transfer_views.import_view), name="customers_customer_import"),
            path("export/", self.admin_site.admin_view(transfer_views.export_view), name="customers_customer_export"),
        ] + super().get_urls()

    @admin.action(description=_("Make the contacts of the selected customers choose a new password"),
                  permissions=["change"])
    def send_password_reset(self, request, queryset):
        users = User.objects.filter(contact__customer__in=queryset).distinct()
        report_reset(request, *force_reset(users, request))

    def has_export_permission(self, request):
        return request.user.has_perm("customers.export_customer")

    @admin.action(description=_("Export selected customers"), permissions=["export"])
    def export_selected(self, request, queryset):
        return transfer_views.export_response(queryset, include_files=True)

    def export_one(self, request, customer):
        return transfer_views.export_response(Customer.objects.filter(pk=customer.pk), include_files=True)

    def changelist_view(self, request, extra_context=None):
        extra_context = {
            **(extra_context or {}),
            "can_import": request.user.has_perm("customers.import_customer"),
            "can_export": self.has_export_permission(request),
        }
        return super().changelist_view(request, extra_context)

    def can_approve(self, obj):
        return obj.status != Customer.Status.ACTIVE

    def can_block(self, obj):
        return obj.status != Customer.Status.BLOCKED

    def has_contacts_without_login(self, obj):
        return obj.contacts.filter(user__isnull=True).exists()

    def approve(self, request, customer):
        self._approve(request, customer)
        messages.success(request, gettext("Customer approved with number %(n)s.") % {"n": customer.number})

    def block(self, request, customer):
        customer.block()
        messages.success(request, gettext("Customer blocked; its contacts can no longer log in."))

    def send_invites(self, request, customer):
        sent, skipped = 0, []
        for contact in customer.contacts.filter(user__isnull=True):
            if User.objects.filter(email__iexact=contact.email).exists():
                skipped.append(contact.email)
                continue
            user = User(email=contact.email, first_name=contact.first_name or contact.initials,
                        last_name=contact.last_name, kind=User.Kind.CUSTOMER,
                        is_active=customer.status == Customer.Status.ACTIVE)
            user.set_unusable_password()
            user.save()
            contact.user = user
            contact.save(update_fields=["user"])
            if user.is_active:
                emails.send_invite(contact, request)
                sent += 1
        messages.success(request, gettext("Logins created; %(n)s invitation(s) sent.") % {"n": sent})
        if skipped:
            messages.warning(request, gettext("Email address already in use: %(list)s") % {"list": ", ".join(skipped)})


@admin.register(CustomerType)
class CustomerTypeAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "is_reseller", "position"]
    search_fields = ["name"]


@admin.register(Country)
class CountryAdmin(ModelAdmin, TabbedTranslationAdmin):
    list_display = ["name", "code", "vat_number_required", "is_active", "position"]
    search_fields = ["name", "code"]
    list_filter = ["is_active"]


@admin.register(SignupSettings)
class SignupSettingsAdmin(ModelAdmin, TabbedTranslationAdmin):
    fieldsets = [
        (_("New customers"), {"classes": ["tab"], "fields": [("default_margin_packs", "default_margin_parts")]}),
        (_("Sign-up form"), {"classes": ["tab"], "fields": [
            "enabled", "menu_label", "title", "intro", "thanks", "customer_type", "require_approval", "notify_email",
        ]}),
        (_("Form fields"), {"classes": ["tab"], "fields": [
            ("field_phone", "field_vat_number", "field_coc_number"),
            ("field_website", "field_salutation", "field_function"),
            ("field_department", "field_contact_phone", "field_address_line2"),
            "field_message",
        ]}),
        (_("Activation email"), {"classes": ["tab"], "fields": ["activation_subject", "activation_body"]}),
    ]

    def changelist_view(self, request, extra_context=None):
        return redirect(reverse("admin:customers_signupsettings_change", args=[SignupSettings.load().pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Contact)
class ContactAdmin(ModelAdmin):
    """All contacts of all customers in one list, e.g. to send several of them a password reset."""

    list_display = ["show_name", "customer", "email", "phone", "show_login", "is_primary"]
    list_filter = ["customer__status", "customer__customer_type", "is_primary", "user__is_active"]
    search_fields = ["first_name", "last_name", "email", "phone", "customer__name", "customer__number"]
    list_select_related = ["customer", "user"]
    autocomplete_fields = ["customer"]
    readonly_fields = ["user"]
    actions = ["send_password_reset"]
    fields = ["customer", ("salutation", "initials", "first_name", "last_name"), ("function", "department"),
              ("email", "phone"), "is_primary", "remark", "user"]

    @display(description=_("Name"), ordering="last_name")
    def show_name(self, obj):
        return obj.full_name

    @display(description=_("Login"), label={"none": "info", "set": "success", "waiting": "warning", "off": "danger"})
    def show_login(self, obj):
        if not obj.user:
            return "none", gettext("No login")
        if not obj.user.is_active:
            return "off", gettext("Not active")
        if not obj.user.has_usable_password():
            return "waiting", gettext("Must choose a new password")
        return "set", gettext("Active")

    @admin.action(description=_("Make selected contacts choose a new password (email with link)"), permissions=["change"])
    def send_password_reset(self, request, queryset):
        users = User.objects.filter(contact__in=queryset)
        report_reset(request, *force_reset(users, request))
