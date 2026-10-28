import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group, UserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _


class EmailUserManager(UserManager):
    def create_user(self, username=None, email=None, password=None, **extra_fields):
        return super().create_user(username or uuid.uuid4().hex, email, password, **extra_fields)

    def create_superuser(self, username=None, email=None, password=None, **extra_fields):
        return super().create_superuser(username or uuid.uuid4().hex, email, password, **extra_fields)


class User(AbstractUser):
    """A login. Users sign in with their email address.

    `username` is an internal unique key and is never shown.
    """

    class Kind(models.TextChoices):
        STAFF = "staff", _("Staff")
        CUSTOMER = "customer", _("Customer")

    kind = models.CharField(_("kind"), max_length=16, choices=Kind.choices, default=Kind.CUSTOMER)
    # unique=True is enough on MariaDB/MySQL (their text comparison ignores case); PostgreSQL also
    # gets the case-insensitive constraint below, which MariaDB cannot create.
    email = models.EmailField(_("email address"), unique=True)
    admin_language = models.CharField(
        _("admin language"), max_length=8, blank=True, choices=settings.LANGUAGES,
        help_text=_("Language of the admin for this user. Empty: the admin language from the site settings."),
    )

    objects = EmailUserManager()

    REQUIRED_FIELDS = ["email"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [models.UniqueConstraint(Lower("email"), name="unique_email")]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = uuid.uuid4().hex
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class Role(Group):
    """A role for staff users (a Django group). Its permissions decide what a user sees and may do in the admin."""

    class Meta:
        proxy = True
        verbose_name = _("role")
        verbose_name_plural = _("roles")

    def __str__(self):
        return self.name


class CustomerUser(User):
    """The logins of customers only (kind = customer), for the list under Customers. Rights follow those of users."""

    class Meta:
        proxy = True
        verbose_name = _("customer user")
        verbose_name_plural = _("customer users")
