"""PackDesk settings. All environment-specific values come from environment variables."""

from pathlib import Path

import environ
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
    "apps.core",
    "apps.siteconfig",
    "apps.numbering",
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
            ],
        },
    },
]

WSGI_APPLICATION = "packdesk.wsgi.application"

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
    "ENVIRONMENT": "apps.core.admin_config.environment_badge",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
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
