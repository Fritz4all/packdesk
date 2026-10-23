"""PackDesk settings. All environment-specific values come from environment variables."""

from pathlib import Path

import environ
from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    SECURE_COOKIES=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.forms",
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    "apps.core",
    "apps.siteconfig",
    "apps.numbering",
    "apps.customers",
    "apps.licences",
    "apps.dashboard",
    # Last: its post_migrate hook gives roles the permissions of all apps above.
    "apps.accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.siteconfig.middleware.SiteSettingsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.siteconfig.middleware.MaintenanceModeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "packdesk.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.siteconfig.context_processors.site_settings",
                "apps.customers.context_processors.customer",
            ],
        },
    },
]

WSGI_APPLICATION = "packdesk.wsgi.application"
# Widgets use the normal template search path, so project templates can override them.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

DATABASES = {"default": env.db("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.EmailBackend"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

LANGUAGE_CODE = "nl"
LANGUAGES = [("nl", _("Dutch")), ("en", _("English")), ("de", _("German"))]
LOCALE_PATHS = [BASE_DIR / "locale", BASE_DIR / "locale_vendor"]
LANGUAGE_COOKIE_NAME = "packdesk_language"

# Translated content fields (django-modeltranslation): one column per language.
# An empty translation falls back to the next language in this order.
MODELTRANSLATION_DEFAULT_LANGUAGE = "nl"
MODELTRANSLATION_FALLBACK_LANGUAGES = tuple(env.list("FALLBACK_LANGUAGES", default=["nl", "en", "de"]))
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))
# Folder with existing documents (e.g. the previous webshop's invoice PDFs), read-only.
DOCUMENT_ARCHIVE_DIR = env("DOCUMENT_ARCHIVE_DIR", default="")

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if DEBUG
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

FORMS_URLFIELD_ASSUME_HTTPS = True  # Django 6 default
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)

# Behind a TLS-terminating reverse proxy.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env("SECURE_COOKIES")
CSRF_COOKIE_SECURE = env("SECURE_COOKIES")
SESSION_COOKIE_HTTPONLY = True
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
X_FRAME_OPTIONS = "SAMEORIGIN"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
}

UNFOLD = {
    "SITE_TITLE": "PackDesk",
    "SITE_HEADER": "PackDesk",
    "SITE_SYMBOL": "inventory_2",
    "SHOW_HISTORY": True,
    "STYLES": [lambda request: static("admin/packdesk-admin.css")],
    "SCRIPTS": [lambda request: static("admin/packdesk-admin.js")],
    "COMMAND": {"search_callback": "apps.dashboard.search.search_everything", "show_history": True},
    "DASHBOARD_CALLBACK": "apps.dashboard.views.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Overview"),
                "items": [
                    {"title": _("Dashboard"), "icon": "dashboard", "link": reverse_lazy("admin:index")},
                    {
                        "title": _("Sales and margin"),
                        "icon": "monitoring",
                        "link": reverse_lazy("reports"),
                        "permission": lambda request: request.user.has_perm("dashboard.view_reports"),
                    },
                ],
            },
            {
                "title": _("Configuration"),
                "items": [
                    {
                        "title": _("Settings"),
                        "icon": "tune",
                        "link": reverse_lazy("admin:siteconfig_sitesettings_changelist"),
                        "permission": lambda request: request.user.has_perm("siteconfig.view_sitesettings"),
                    },
                    {
                        "title": _("Number sequences"),
                        "icon": "pin",
                        "link": reverse_lazy("admin:numbering_numbersequence_changelist"),
                        "badge": "apps.numbering.admin_badge.problems",
                        "permission": lambda request: request.user.has_perm("numbering.view_numbersequence"),
                    },
                ],
            },
            {
                "title": _("Customers"),
                "items": [
                    {
                        "title": _("Customers"),
                        "icon": "storefront",
                        "link": reverse_lazy("admin:customers_customer_changelist"),
                        "badge": "apps.customers.admin_badge.pending",
                        "permission": lambda request: request.user.has_perm("customers.view_customer"),
                    },
                    {
                        "title": _("Customer types"),
                        "icon": "category",
                        "link": reverse_lazy("admin:customers_customertype_changelist"),
                        "permission": lambda request: request.user.has_perm("customers.view_customertype"),
                    },
                    {
                        "title": _("Countries"),
                        "icon": "public",
                        "link": reverse_lazy("admin:customers_country_changelist"),
                        "permission": lambda request: request.user.has_perm("customers.view_country"),
                    },
                    {
                        "title": _("Customer settings"),
                        "icon": "how_to_reg",
                        "link": reverse_lazy("admin:customers_signupsettings_changelist"),
                        "permission": lambda request: request.user.has_perm("customers.view_signupsettings"),
                    },
                ],
            },
            {
                "title": _("Service packs and licences"),
                "collapsible": True,
                "items": [
                    {
                        "title": _("Licences"),
                        "icon": "verified",
                        "link": reverse_lazy("admin:licences_licence_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_licence"),
                    },
                    {
                        "title": _("Service packs"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:licences_supportpack_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_supportpack"),
                    },
                    {
                        "title": _("Pack categories"),
                        "icon": "folder",
                        "link": reverse_lazy("admin:licences_category_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_category"),
                    },
                    {
                        "title": _("Hardware classes"),
                        "icon": "dns",
                        "link": reverse_lazy("admin:licences_hardwareclass_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_hardwareclass"),
                    },
                    {
                        "title": _("Brands"),
                        "icon": "sell",
                        "link": reverse_lazy("admin:licences_vendor_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_vendor"),
                    },
                    {
                        "title": _("Device types"),
                        "icon": "devices",
                        "link": reverse_lazy("admin:licences_hardwaresystem_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_hardwaresystem"),
                    },
                    {
                        "title": _("Option types"),
                        "icon": "memory",
                        "link": reverse_lazy("admin:licences_optiontype_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_optiontype"),
                    },
                    {
                        "title": _("Support periods"),
                        "icon": "schedule",
                        "link": reverse_lazy("admin:licences_supportperiod_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_supportperiod"),
                    },
                    {
                        "title": _("Service levels"),
                        "icon": "support_agent",
                        "link": reverse_lazy("admin:licences_supportservice_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_supportservice"),
                    },
                    {
                        "title": _("Licence settings"),
                        "icon": "tune",
                        "link": reverse_lazy("admin:licences_licencesettings_changelist"),
                        "permission": lambda request: request.user.has_perm("licences.view_licencesettings"),
                    },
                ],
            },
            {
                "title": _("Users"),
                "items": [
                    {
                        "title": _("Users"),
                        "icon": "person",
                        "link": reverse_lazy("admin:accounts_user_changelist"),
                        "permission": lambda request: request.user.has_perm("accounts.view_user"),
                    },
                    {
                        "title": _("Roles"),
                        "icon": "badge",
                        "link": reverse_lazy("admin:accounts_role_changelist"),
                        "permission": lambda request: request.user.has_perm("accounts.view_role"),
                    },
                ],
            },
        ],
    },
}
