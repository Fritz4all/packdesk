"""PackDesk settings. All environment-specific values come from environment variables."""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
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
    "apps.faults",
    "apps.orders",
    "apps.invoices",
    "apps.dashboard",
    "apps.legacy",
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
    "apps.siteconfig.language.AdminLanguageMiddleware",
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

# Database: either DATABASE_URL, or the separate DB_* variables (set in .env, used by docker-compose).
# DB_ENGINE is "postgres" or "mariadb" (MySQL works the same way). PackDesk always gets its own
# database; on an existing server that means a new database next to the others.
DB_ENGINES = {
    "postgres": "django.db.backends.postgresql",
    "postgresql": "django.db.backends.postgresql",
    "mariadb": "django.db.backends.mysql",
    "mysql": "django.db.backends.mysql",
}
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    _engine = env("DB_ENGINE", default="postgres").lower()
    if _engine not in DB_ENGINES:
        raise ImproperlyConfigured(f"DB_ENGINE must be one of: {', '.join(DB_ENGINES)}")
    DATABASES = {"default": {
        "ENGINE": DB_ENGINES[_engine],
        "HOST": env("DB_HOST", default="localhost"),
        "PORT": env("DB_PORT", default="3306" if "mysql" in DB_ENGINES[_engine] else "5432"),
        "NAME": env("DB_NAME", default="packdesk"),
        "USER": env("DB_USER", default="packdesk"),
        "PASSWORD": env("DB_PASSWORD", default=""),
    }}
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"].setdefault("OPTIONS", {}).update({
        "charset": "utf8mb4",
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        "isolation_level": "read committed",
    })
    DATABASES["default"]["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}
    # The case-insensitive email constraint cannot be created on MariaDB; the field's own unique
    # index does the same there, because MariaDB compares text without regard to case.
    SILENCED_SYSTEM_CHECKS = ["models.W044"]
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
# All files PackDesk keeps, one folder per purpose (see docs/opslag.md):
#   DATA_ROOT/website            logo, favicon, customer logos; public through MEDIA_URL
#   DATA_ROOT/invoices           invoice PDFs made by PackDesk          } never served directly,
#   DATA_ROOT/fault-attachments  attachments of fault reports           } only through views
#   DATA_ROOT/imports            customer imports waiting to be checked } that check access
# Default outside the repository, so files never end up in Git.
DATA_ROOT = Path(env("DATA_ROOT", default=str(BASE_DIR.parent / "packdesk-data")))
MEDIA_URL = "media/"
MEDIA_ROOT = DATA_ROOT / "website"
# Optional, separate from DATA_ROOT: a folder with existing documents (the previous webshop's invoice PDFs),
# read-only. Empty = no archive. In docker-compose it is /data-sources/archive-invoices: sources from
# other systems live under /data-sources/<name>, outside DATA_ROOT, and are mounted only when given.
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

def _versioned(path):
    """Static URL that changes when the file changes, so browsers never keep an old copy.
    (In production the file name itself carries a hash; the query then does no harm.)"""
    try:
        return f"{static(path)}?v={int((BASE_DIR / 'static' / path).stat().st_mtime)}"
    except OSError:
        return static(path)


UNFOLD = {
    "SITE_TITLE": "PackDesk",
    "SITE_HEADER": "PackDesk",
    "SITE_SYMBOL": "inventory_2",
    "SHOW_HISTORY": True,
    "STYLES": [lambda request: _versioned("admin/packdesk-admin.css")],
    "SCRIPTS": [lambda request: _versioned("admin/packdesk-admin.js")],
    "COMMAND": {"search_callback": "apps.dashboard.search.search_everything", "show_history": True},
    "DASHBOARD_CALLBACK": "apps.dashboard.views.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": "apps.dashboard.navigation.sidebar",
    },
}
